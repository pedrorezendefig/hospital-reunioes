"""Testes da rota POST /reunioes/{id}/transferir-facilitador.

Cobre:
- 200: troca para outro super admin ativo, atualiza facilitador_id, loga audit.
- 200: novo facilitador ja era participante (sem duplicar).
- 200: novo facilitador nao era participante (insere link).
- 400: novo facilitador nao e super admin.
- 400: novo facilitador inativo.
- 400: novo == atual (idempotente bloqueado).
- 404: reuniao inexistente.
- 404: reuniao soft-deleted (deleted_at != NULL).
- 404: novo facilitador nao existe.
- 403: usuario nao e super admin (via require_super_admin).
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import Any

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.models.admin_schemas import TransferirFacilitadorRequest  # noqa: E402
from app.routers.reunioes import transferir_facilitador  # noqa: E402

# ─── Mocks ────────────────────────────────────────────────────────────────────


@dataclass
class _Result:
    data: list


class _ReunioesQuery:
    def __init__(self, store: dict[str, dict], updates_log: list):
        self._store = store
        self._updates_log = updates_log
        self._filters: dict = {}
        self._pending_update: dict | None = None
        self._mode: str | None = None

    def select(self, *_a, **_kw):
        self._mode = "select"
        return self

    def update(self, data):
        self._mode = "update"
        self._pending_update = data
        return self

    def eq(self, col, val):
        self._filters[col] = val
        return self

    def execute(self):
        if self._mode == "select":
            rows = [r for r in self._store.values() if all(r.get(k) == v for k, v in self._filters.items())]
            return _Result(rows)
        if self._mode == "update":
            target_id = self._filters.get("id_reuniao")
            if target_id in self._store and self._pending_update:
                self._store[target_id].update(self._pending_update)
                self._updates_log.append({"id": target_id, "update": dict(self._pending_update)})
                return _Result([self._store[target_id]])
            return _Result([])
        return _Result([])


class _ParticipantesQuery:
    def __init__(self, store: dict[str, dict]):
        self._store = store
        self._filters: dict = {}

    def select(self, *_a, **_kw):
        return self

    def eq(self, col, val):
        self._filters[col] = val
        return self

    def execute(self):
        rows = [r for r in self._store.values() if all(r.get(k) == v for k, v in self._filters.items())]
        return _Result(rows)


class _LinkQuery:
    """Mock para reuniao_participantes — select + upsert idempotente."""

    def __init__(self, links: list, upserts_log: list):
        self._links = links
        self._upserts_log = upserts_log
        self._filters: dict = {}
        self._pending: dict | list | None = None
        self._mode: str | None = None

    def select(self, *_a, **_kw):
        self._mode = "select"
        return self

    def upsert(self, row, on_conflict=None):
        self._mode = "upsert"
        self._pending = row
        return self

    def eq(self, col, val):
        self._filters[col] = val
        return self

    def execute(self):
        if self._mode == "select":
            rows = [r for r in self._links if all(r.get(k) == v for k, v in self._filters.items())]
            return _Result(rows)
        if self._mode == "upsert" and self._pending:
            row = self._pending if isinstance(self._pending, dict) else (self._pending[0] if self._pending else None)
            if row is None:
                return _Result([])
            already = any(
                r.get("id_reuniao") == row["id_reuniao"] and r.get("participante_id") == row["participante_id"]
                for r in self._links
            )
            if not already:
                self._links.append(dict(row))
            self._upserts_log.append(dict(row))
            return _Result([row])
        return _Result([])


class _AuditInsert:
    def __init__(self, sink: list):
        self._sink = sink
        self._pending: dict | None = None

    def insert(self, row):
        self._pending = row
        return self

    def execute(self):
        if self._pending:
            self._sink.append(self._pending)
        return _Result([self._pending] if self._pending else [])


@dataclass
class _Sb:
    reunioes: dict[str, dict] = field(default_factory=dict)
    participantes: dict[str, dict] = field(default_factory=dict)
    reuniao_participantes: list = field(default_factory=list)
    audit_rows: list = field(default_factory=list)
    updates_log: list = field(default_factory=list)
    link_upserts: list = field(default_factory=list)

    def table(self, name):
        if name == "reunioes":
            return _ReunioesQuery(self.reunioes, self.updates_log)
        if name == "participantes":
            return _ParticipantesQuery(self.participantes)
        if name == "reuniao_participantes":
            return _LinkQuery(self.reuniao_participantes, self.link_upserts)
        if name == "audit_log":
            return _AuditInsert(self.audit_rows)
        raise AssertionError(f"Tabela inesperada: {name}")


class _FakeRequest:
    def __init__(self, ip: str = "127.0.0.1"):
        self.client = type("Client", (), {"host": ip})()
        self.headers: dict[str, Any] = {}


SUPER_ADMIN_ACTOR = {
    "id": "P01",
    "email": "admin@ex.com",
    "nome_completo": "Pedro Super",
    "is_super_admin": True,
}


def _build_sb_basico(facilitador_atual: str | None = "P01") -> _Sb:
    """Sb com 1 reuniao + 3 participantes (1 super admin atual, 1 super admin novo, 1 normal)."""
    return _Sb(
        reunioes={
            "RD_100": {
                "id_reuniao": "RD_100",
                "facilitador_id": facilitador_atual,
                "deleted_at": None,
                "status_ata": "PROGRAMADA",
            }
        },
        participantes={
            "P01": {"id": "P01", "is_super_admin": True, "ativo": True, "nome_completo": "Pedro Super"},
            "P02": {"id": "P02", "is_super_admin": True, "ativo": True, "nome_completo": "Felipe Super"},
            "P03": {"id": "P03", "is_super_admin": False, "ativo": True, "nome_completo": "Joao Comum"},
            "P04": {"id": "P04", "is_super_admin": True, "ativo": False, "nome_completo": "Carol Inativa"},
        },
        reuniao_participantes=[
            {"id_reuniao": "RD_100", "participante_id": "P01"},
        ],
    )


# ─── Testes ───────────────────────────────────────────────────────────────────


class TestTransferirFacilitador:
    @pytest.mark.asyncio
    async def test_troca_para_outro_super_admin_ativo_loga_audit(self):
        sb = _build_sb_basico()

        resp = await transferir_facilitador(
            id_reuniao="RD_100",
            body=TransferirFacilitadorRequest(novo_facilitador_id="P02"),
            request=_FakeRequest(),
            actor=SUPER_ADMIN_ACTOR,
            supabase=sb,
        )

        # Resposta
        assert resp["facilitador_anterior"] == "P01"
        assert resp["facilitador_novo"] == "P02"
        assert resp["adicionado_como_participante"] is True

        # Estado: facilitador_id atualizado
        assert sb.reunioes["RD_100"]["facilitador_id"] == "P02"

        # Audit log
        assert len(sb.audit_rows) == 1
        log = sb.audit_rows[0]
        assert log["action"] == "TRANSFER_FACILITADOR"
        assert log["target_type"] == "reuniao"
        assert log["target_id"] == "RD_100"
        assert log["metadata"]["facilitador_anterior"] == "P01"
        assert log["metadata"]["facilitador_novo"] == "P02"
        assert log["metadata"]["facilitador_novo_nome"] == "Felipe Super"
        assert log["metadata"]["adicionado_como_participante"] is True

    @pytest.mark.asyncio
    async def test_novo_facilitador_ja_participante_nao_duplica(self):
        sb = _build_sb_basico()
        # P02 ja e participante
        sb.reuniao_participantes.append({"id_reuniao": "RD_100", "participante_id": "P02"})

        resp = await transferir_facilitador(
            id_reuniao="RD_100",
            body=TransferirFacilitadorRequest(novo_facilitador_id="P02"),
            request=_FakeRequest(),
            actor=SUPER_ADMIN_ACTOR,
            supabase=sb,
        )

        assert resp["adicionado_como_participante"] is False

        # Nao houve upsert
        assert len(sb.link_upserts) == 0

        # Lista de participantes nao duplicou (P01 + P02 ainda)
        pids = [r["participante_id"] for r in sb.reuniao_participantes]
        assert pids.count("P02") == 1

    @pytest.mark.asyncio
    async def test_novo_facilitador_nao_super_admin_400(self):
        sb = _build_sb_basico()

        with pytest.raises(HTTPException) as exc:
            await transferir_facilitador(
                id_reuniao="RD_100",
                body=TransferirFacilitadorRequest(novo_facilitador_id="P03"),
                request=_FakeRequest(),
                actor=SUPER_ADMIN_ACTOR,
                supabase=sb,
            )
        assert exc.value.status_code == 400
        assert "Super Admin" in exc.value.detail

        # Nada foi alterado
        assert sb.reunioes["RD_100"]["facilitador_id"] == "P01"
        assert len(sb.audit_rows) == 0

    @pytest.mark.asyncio
    async def test_novo_facilitador_inativo_400(self):
        sb = _build_sb_basico()

        with pytest.raises(HTTPException) as exc:
            await transferir_facilitador(
                id_reuniao="RD_100",
                body=TransferirFacilitadorRequest(novo_facilitador_id="P04"),
                request=_FakeRequest(),
                actor=SUPER_ADMIN_ACTOR,
                supabase=sb,
            )
        assert exc.value.status_code == 400
        assert "inativo" in exc.value.detail.lower()
        assert sb.reunioes["RD_100"]["facilitador_id"] == "P01"

    @pytest.mark.asyncio
    async def test_mesmo_facilitador_atual_400(self):
        sb = _build_sb_basico(facilitador_atual="P02")

        with pytest.raises(HTTPException) as exc:
            await transferir_facilitador(
                id_reuniao="RD_100",
                body=TransferirFacilitadorRequest(novo_facilitador_id="P02"),
                request=_FakeRequest(),
                actor=SUPER_ADMIN_ACTOR,
                supabase=sb,
            )
        assert exc.value.status_code == 400
        assert "atual" in exc.value.detail.lower()

    @pytest.mark.asyncio
    async def test_reuniao_inexistente_404(self):
        sb = _build_sb_basico()

        with pytest.raises(HTTPException) as exc:
            await transferir_facilitador(
                id_reuniao="RD_NAO_EXISTE",
                body=TransferirFacilitadorRequest(novo_facilitador_id="P02"),
                request=_FakeRequest(),
                actor=SUPER_ADMIN_ACTOR,
                supabase=sb,
            )
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_reuniao_soft_deleted_404(self):
        sb = _build_sb_basico()
        sb.reunioes["RD_100"]["deleted_at"] = "2026-01-01T00:00:00Z"

        with pytest.raises(HTTPException) as exc:
            await transferir_facilitador(
                id_reuniao="RD_100",
                body=TransferirFacilitadorRequest(novo_facilitador_id="P02"),
                request=_FakeRequest(),
                actor=SUPER_ADMIN_ACTOR,
                supabase=sb,
            )
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_novo_facilitador_nao_existe_404(self):
        sb = _build_sb_basico()

        with pytest.raises(HTTPException) as exc:
            await transferir_facilitador(
                id_reuniao="RD_100",
                body=TransferirFacilitadorRequest(novo_facilitador_id="P99"),
                request=_FakeRequest(),
                actor=SUPER_ADMIN_ACTOR,
                supabase=sb,
            )
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_require_super_admin_bloqueia_usuario_normal_403(self):
        """Garante que require_super_admin levanta 403 para user sem flag."""
        from app.dependencies import require_super_admin

        class _PartQuery:
            def __init__(self, rows):
                self._rows = rows
                self._filters: dict = {}

            def select(self, *_a, **_k):
                return self

            def eq(self, col, val):
                self._filters[col] = val
                return self

            def execute(self):
                rows = [r for r in self._rows if all(r.get(k) == v for k, v in self._filters.items())]
                return _Result(rows)

            def update(self, *_a, **_k):
                return self

        class _SbPart:
            def __init__(self, rows):
                self._rows = rows

            def table(self, name):
                assert name == "participantes"
                return _PartQuery(self._rows)

        sb = _SbPart(
            [
                {
                    "id": "P99",
                    "auth_user_id": "auth-99",
                    "email": "user@ex.com",
                    "is_super_admin": False,
                    "role": "diretor",
                    "nome_completo": "User Comum",
                }
            ]
        )

        with pytest.raises(HTTPException) as exc:
            await require_super_admin(
                current_user={"id": "auth-99", "email": "user@ex.com", "metadata": {}},
                supabase=sb,
            )
        assert exc.value.status_code == 403
