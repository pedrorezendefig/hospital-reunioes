"""Testes do router /admin/logs (Fase 02).

Cobre:
- 403 quando nao super admin (via require_super_admin).
- listagem basica + filtros (actor_id, action, target_type, datas).
- paginacao (limit/offset + total).
- /actions retorna DISTINCT dos valores `action`.
- validacao de data (ISO 8601 invalido -> 400).
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.dependencies import require_super_admin  # noqa: E402
from app.routers.admin import logs as logs_router  # noqa: E402

# ─── Mocks Supabase ───────────────────────────────────────────────────────────


@dataclass
class _Result:
    data: list
    count: int | None = None


class _AuditLogQuery:
    """Mock de supabase.table('audit_log').select(...).<filtros>...execute()."""

    def __init__(self, rows: list[dict]):
        self._rows = rows
        self._filters: list[tuple] = []
        self._count_mode = False
        self._order: tuple[str, bool] | None = None
        self._range: tuple[int, int] | None = None
        self._select_fields: str | None = None

    def select(self, fields: str = "*", count: str | None = None, **_kw):
        self._select_fields = fields
        if count == "exact":
            self._count_mode = True
        return self

    def eq(self, col, value):
        self._filters.append(("eq", col, value))
        return self

    def gte(self, col, value):
        self._filters.append(("gte", col, value))
        return self

    def lte(self, col, value):
        self._filters.append(("lte", col, value))
        return self

    def order(self, col, desc: bool = False):
        self._order = (col, desc)
        return self

    def range(self, start: int, end: int):
        self._range = (start, end)
        return self

    def _apply(self) -> list[dict]:
        result = list(self._rows)
        for op, col, value in self._filters:
            if op == "eq":
                result = [r for r in result if r.get(col) == value]
            elif op == "gte":
                result = [r for r in result if r.get(col) is not None and r[col] >= value]
            elif op == "lte":
                result = [r for r in result if r.get(col) is not None and r[col] <= value]
        if self._order:
            col, desc = self._order
            result.sort(key=lambda r: r.get(col) or "", reverse=desc)
        return result

    def execute(self):
        filtered = self._apply()
        total = len(filtered) if self._count_mode else None
        if self._range:
            start, end = self._range
            page = filtered[start : end + 1]
        else:
            page = filtered
        return _Result(data=page, count=total)


@dataclass
class _SupabaseMock:
    audit_rows: list = field(default_factory=list)

    def table(self, name):
        if name == "audit_log":
            return _AuditLogQuery(self.audit_rows)
        raise AssertionError(f"Tabela inesperada: {name}")


def _iso(y: int, mo: int, d: int, h: int = 12) -> str:
    return datetime(y, mo, d, h, 0, 0, tzinfo=UTC).isoformat()


def _seed_rows() -> list[dict]:
    return [
        {
            "id": "A1",
            "timestamp": _iso(2026, 4, 1),
            "actor_id": "P01",
            "actor_email": "admin@ex.com",
            "action": "DELETE_ATA",
            "target_type": "reuniao",
            "target_id": "RD_20260101_AAA",
            "metadata": {"status_before": "ASSINADA"},
            "ip_address": "10.0.0.1",
            "reason": "duplicada",
        },
        {
            "id": "A2",
            "timestamp": _iso(2026, 4, 5),
            "actor_id": "P01",
            "actor_email": "admin@ex.com",
            "action": "RESET_PASSWORD",
            "target_type": "participante",
            "target_id": "P99",
            "metadata": {},
            "ip_address": None,
            "reason": "esqueceu senha",
        },
        {
            "id": "A3",
            "timestamp": _iso(2026, 4, 10),
            "actor_id": "P02",
            "actor_email": "outro@ex.com",
            "action": "PROMOTE_SUPER_ADMIN",
            "target_type": "participante",
            "target_id": "P10",
            "metadata": {"target_email": "x@y"},
            "ip_address": None,
            "reason": None,
        },
        {
            "id": "A4",
            "timestamp": _iso(2026, 4, 15),
            "actor_id": "P01",
            "actor_email": "admin@ex.com",
            "action": "DELETE_ATA",
            "target_type": "reuniao",
            "target_id": "RD_20260115_BBB",
            "metadata": {},
            "ip_address": None,
            "reason": None,
        },
    ]


# ─── Testes: autorizacao ──────────────────────────────────────────────────────


class _ParticipantesForAuth:
    def __init__(self, rows):
        self._rows = rows
        self._filters: dict = {}

    def select(self, *_a, **_kw):
        return self

    def eq(self, col, value):
        self._filters[col] = value
        return self

    def execute(self):
        filtered = self._rows
        for col, value in self._filters.items():
            filtered = [r for r in filtered if r.get(col) == value]
        return _Result(data=filtered)

    def update(self, *_a, **_kw):
        return self


class _AuthSupabase:
    def __init__(self, participantes):
        self._p = participantes

    def table(self, name):
        if name == "participantes":
            return _ParticipantesForAuth(self._p)
        raise AssertionError(name)


class TestRequireSuperAdminAtLogs:
    @pytest.mark.asyncio
    async def test_403_quando_sem_flag(self):
        sb = _AuthSupabase(
            [
                {
                    "id": "P10",
                    "auth_user_id": "auth-10",
                    "email": "diretor@ex.com",
                    "role": "diretor",
                    "is_super_admin": False,
                }
            ]
        )
        with pytest.raises(HTTPException) as exc:
            await require_super_admin(
                current_user={"id": "auth-10", "email": "diretor@ex.com", "metadata": {}},
                supabase=sb,
            )
        assert exc.value.status_code == 403


# ─── Testes: list_logs ────────────────────────────────────────────────────────


class TestListLogs:
    @pytest.mark.asyncio
    async def test_sem_filtros_retorna_todas_ordenadas(self):
        sb = _SupabaseMock(audit_rows=_seed_rows())
        page = await logs_router.list_logs(
            actor_id=None,
            actor_email=None,
            action=None,
            target_type=None,
            target_id=None,
            from_=None,
            to=None,
            limit=50,
            offset=0,
            _actor={"id": "P01"},
            supabase=sb,
        )
        assert page.total == 4
        assert [r.id for r in page.rows] == ["A4", "A3", "A2", "A1"]
        assert page.limit == 50
        assert page.offset == 0

    @pytest.mark.asyncio
    async def test_filtra_por_action(self):
        sb = _SupabaseMock(audit_rows=_seed_rows())
        page = await logs_router.list_logs(
            actor_id=None,
            actor_email=None,
            action="DELETE_ATA",
            target_type=None,
            target_id=None,
            from_=None,
            to=None,
            limit=50,
            offset=0,
            _actor={"id": "P01"},
            supabase=sb,
        )
        assert page.total == 2
        assert {r.id for r in page.rows} == {"A1", "A4"}

    @pytest.mark.asyncio
    async def test_filtra_por_actor_id_e_target_type(self):
        sb = _SupabaseMock(audit_rows=_seed_rows())
        page = await logs_router.list_logs(
            actor_id="P01",
            actor_email=None,
            action=None,
            target_type="participante",
            target_id=None,
            from_=None,
            to=None,
            limit=50,
            offset=0,
            _actor={"id": "P01"},
            supabase=sb,
        )
        assert page.total == 1
        assert page.rows[0].id == "A2"

    @pytest.mark.asyncio
    async def test_filtro_por_data_range(self):
        sb = _SupabaseMock(audit_rows=_seed_rows())
        page = await logs_router.list_logs(
            actor_id=None,
            actor_email=None,
            action=None,
            target_type=None,
            target_id=None,
            from_="2026-04-05",
            to="2026-04-12",
            limit=50,
            offset=0,
            _actor={"id": "P01"},
            supabase=sb,
        )
        ids = {r.id for r in page.rows}
        assert ids == {"A2", "A3"}

    @pytest.mark.asyncio
    async def test_paginacao(self):
        sb = _SupabaseMock(audit_rows=_seed_rows())
        page1 = await logs_router.list_logs(
            actor_id=None,
            actor_email=None,
            action=None,
            target_type=None,
            target_id=None,
            from_=None,
            to=None,
            limit=2,
            offset=0,
            _actor={"id": "P01"},
            supabase=sb,
        )
        assert page1.total == 4
        assert len(page1.rows) == 2
        assert [r.id for r in page1.rows] == ["A4", "A3"]

        page2 = await logs_router.list_logs(
            actor_id=None,
            actor_email=None,
            action=None,
            target_type=None,
            target_id=None,
            from_=None,
            to=None,
            limit=2,
            offset=2,
            _actor={"id": "P01"},
            supabase=sb,
        )
        assert page2.total == 4
        assert [r.id for r in page2.rows] == ["A2", "A1"]

    @pytest.mark.asyncio
    async def test_data_invalida_retorna_400(self):
        sb = _SupabaseMock(audit_rows=_seed_rows())
        with pytest.raises(HTTPException) as exc:
            await logs_router.list_logs(
                actor_id=None,
                actor_email=None,
                action=None,
                target_type=None,
                target_id=None,
                from_="nao-e-data",
                to=None,
                limit=50,
                offset=0,
                _actor={"id": "P01"},
                supabase=sb,
            )
        assert exc.value.status_code == 400


# ─── Testes: list_distinct_actions ───────────────────────────────────────────


class TestListDistinctActions:
    @pytest.mark.asyncio
    async def test_retorna_lista_ordenada_e_distinta(self):
        sb = _SupabaseMock(audit_rows=_seed_rows())
        actions = await logs_router.list_distinct_actions(_actor={"id": "P01"}, supabase=sb)
        assert actions == ["DELETE_ATA", "PROMOTE_SUPER_ADMIN", "RESET_PASSWORD"]

    @pytest.mark.asyncio
    async def test_vazio_retorna_lista_vazia(self):
        sb = _SupabaseMock(audit_rows=[])
        actions = await logs_router.list_distinct_actions(_actor={"id": "P01"}, supabase=sb)
        assert actions == []


# ─── Testes: export CSV ──────────────────────────────────────────────────────


class _InsertAuditLog:
    """Builder de insert para mock (audit_log). Registra a linha inserida."""

    def __init__(self, sink: list[dict]):
        self._sink = sink
        self._pending: dict | None = None

    def insert(self, row: dict):
        self._pending = row
        return self

    def execute(self):
        if self._pending is not None:
            self._sink.append(self._pending)
            self._pending = None
        return _Result(data=[], count=None)


class _SupabaseExportMock:
    """Supabase mock com suporte a select (paginado) E insert no audit_log."""

    def __init__(self, audit_rows: list[dict]):
        self.audit_rows = audit_rows
        self.inserted: list[dict] = []

    def table(self, name):
        if name != "audit_log":
            raise AssertionError(f"Tabela inesperada: {name}")
        # Retorna um builder composto: select() segue _AuditLogQuery; insert() outro path.
        return _CompositeAuditLogTable(self.audit_rows, self.inserted)


class _CompositeAuditLogTable:
    def __init__(self, rows: list[dict], insert_sink: list[dict]):
        self._rows = rows
        self._insert_sink = insert_sink

    def select(self, fields: str = "*", count: str | None = None, **kw):
        return _AuditLogQuery(self._rows).select(fields, count=count, **kw)

    def insert(self, row: dict):
        builder = _InsertAuditLog(self._insert_sink)
        return builder.insert(row)


def _fake_request():
    """Mock minimo de Request com IP via client.host."""

    class _Client:
        host = "127.0.0.1"

    class _Headers:
        def get(self, _name):
            return None

    class _Req:
        headers = _Headers()
        client = _Client()

    return _Req()


class TestExportCsvAuth:
    @pytest.mark.asyncio
    async def test_export_csv_403_sem_super_admin(self):
        sb = _AuthSupabase(
            [
                {
                    "id": "P10",
                    "auth_user_id": "auth-10",
                    "email": "diretor@ex.com",
                    "role": "diretor",
                    "is_super_admin": False,
                }
            ]
        )
        with pytest.raises(HTTPException) as exc:
            await require_super_admin(
                current_user={"id": "auth-10", "email": "diretor@ex.com", "metadata": {}},
                supabase=sb,
            )
        assert exc.value.status_code == 403


class TestExportCsvSucesso:
    @pytest.mark.asyncio
    async def test_export_csv_content_type_e_header(self):
        sb = _SupabaseExportMock(audit_rows=_seed_rows())
        actor = {"id": "P01", "email": "admin@ex.com"}
        resp = await logs_router.export_logs_csv(
            request=_fake_request(),
            actor_id=None,
            actor_email=None,
            action=None,
            target_type=None,
            target_id=None,
            from_=None,
            to=None,
            reason=None,
            actor=actor,
            supabase=sb,
        )
        assert resp.media_type == "text/csv; charset=utf-8"
        disp = resp.headers.get("content-disposition") or resp.headers.get("Content-Disposition")
        assert disp is not None
        assert "audit_log_" in disp
        assert disp.endswith('.csv"')

        # Consome o streaming e valida o header + pelo menos uma linha
        chunks = []
        async for chunk in resp.body_iterator:
            chunks.append(chunk if isinstance(chunk, bytes) else chunk.encode("utf-8"))
        body = b"".join(chunks).decode("utf-8")
        lines = body.strip().split("\n")
        assert lines[0] == ("timestamp,actor_id,actor_email,action,target_type,target_id,reason,ip_address,metadata")
        # 4 linhas seed -> 4 linhas de dados + 1 header
        assert len(lines) == 5

    @pytest.mark.asyncio
    async def test_export_csv_respeita_filtros(self):
        sb = _SupabaseExportMock(audit_rows=_seed_rows())
        actor = {"id": "P01", "email": "admin@ex.com"}
        resp = await logs_router.export_logs_csv(
            request=_fake_request(),
            actor_id=None,
            actor_email=None,
            action="DELETE_ATA",
            target_type=None,
            target_id=None,
            from_=None,
            to=None,
            reason=None,
            actor=actor,
            supabase=sb,
        )
        chunks = []
        async for chunk in resp.body_iterator:
            chunks.append(chunk if isinstance(chunk, bytes) else chunk.encode("utf-8"))
        body = b"".join(chunks).decode("utf-8")
        lines = body.strip().split("\n")
        # header + apenas as 2 linhas DELETE_ATA
        assert len(lines) == 3
        assert all("DELETE_ATA" in line for line in lines[1:])


class TestExportCsvGravaAuditLog:
    @pytest.mark.asyncio
    async def test_export_csv_grava_audit_log(self):
        sb = _SupabaseExportMock(audit_rows=_seed_rows())
        actor = {"id": "P01", "email": "admin@ex.com"}
        resp = await logs_router.export_logs_csv(
            request=_fake_request(),
            actor_id=None,
            actor_email=None,
            action="DELETE_ATA",
            target_type=None,
            target_id=None,
            from_=None,
            to=None,
            reason="auditoria mensal",
            actor=actor,
            supabase=sb,
        )
        # Drena o streaming para completar o endpoint
        async for _ in resp.body_iterator:
            pass

        assert len(sb.inserted) == 1
        logged = sb.inserted[0]
        assert logged["action"] == "EXPORT_LOGS"
        assert logged["target_type"] == "audit_log"
        assert logged["target_id"] == "export"
        assert logged["actor_id"] == "P01"
        assert logged["reason"] == "auditoria mensal"
        meta = logged["metadata"]
        assert meta["linhas_exportadas"] == 2
        assert meta["filtros"] == {"action": "DELETE_ATA"}
        assert meta["limite_seguranca"] == logs_router.EXPORT_CSV_MAX_ROWS


class TestExportCsvLimiteSeguranca:
    @pytest.mark.asyncio
    async def test_export_csv_respeita_limite_seguranca(self, monkeypatch):
        # Cria N+1 linhas sinteticas — maior que o limite reduzido via monkeypatch
        monkeypatch.setattr(logs_router, "EXPORT_CSV_MAX_ROWS", 3)
        monkeypatch.setattr(logs_router, "EXPORT_CSV_BATCH_SIZE", 2)

        big_rows = [
            {
                "id": f"X{i}",
                "timestamp": _iso(2026, 4, 1, h=i % 24),
                "actor_id": "P01",
                "actor_email": "admin@ex.com",
                "action": "DELETE_ATA",
                "target_type": "reuniao",
                "target_id": f"R{i}",
                "metadata": {},
                "ip_address": None,
                "reason": None,
            }
            for i in range(10)  # 10 > limite 3 -> overflow
        ]
        sb = _SupabaseExportMock(audit_rows=big_rows)
        actor = {"id": "P01", "email": "admin@ex.com"}
        with pytest.raises(HTTPException) as exc:
            await logs_router.export_logs_csv(
                request=_fake_request(),
                actor_id=None,
                actor_email=None,
                action=None,
                target_type=None,
                target_id=None,
                from_=None,
                to=None,
                reason=None,
                actor=actor,
                supabase=sb,
            )
        assert exc.value.status_code == 413
        assert "limite de seguranca" in exc.value.detail.lower()
        # Nao deve ter gravado audit quando ocorre overflow
        assert sb.inserted == []
