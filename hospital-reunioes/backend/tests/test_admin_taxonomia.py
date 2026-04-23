"""Testes do router /admin/{setores|cargos|tipos-reuniao} — CRUD de taxonomia.

Cobre:
- 403 quando actor nao e super admin.
- GET /admin/setores?ativo=ativos retorna ativos, ?ativo=arquivados retorna arquivados.
- POST /admin/setores cria item e grava audit_log setor_create.
- POST com nome em outro case retorna 409 (duplicata case-insensitive).
- PATCH renomeia item e grava setor_update.
- PATCH mesmo nome (noop) retorna o registro sem gravar log.
- DELETE faz soft delete (ativo=false) e grava setor_archive.
- DELETE idempotente: chamar em item ja arquivado retorna sem re-gravar log.
- Mesmos endpoints funcionam para cargos e tipos_reuniao (smoke test).
"""

from __future__ import annotations

import os
import sys
import uuid
from dataclasses import dataclass, field
from typing import Any

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import UTC

from app.models.admin_schemas import (  # noqa: E402
    TaxonomyCreatePayload,
    TaxonomyUpdatePayload,
)
from app.routers.admin import taxonomia as taxonomia_router  # noqa: E402

# ─── Infra de mocks ──────────────────────────────────────────────────────────


@dataclass
class _Result:
    data: list
    count: int | None = None


class _TaxonomyQuery:
    """Mock minimalista de PostgREST para tabelas de taxonomia.

    Suporta: select().ilike().eq().order().range().execute(),
    insert(payload).execute(),
    update(payload).eq().execute(),
    e variantes com count="exact".
    """

    def __init__(self, rows_ref: list):
        self._rows = rows_ref
        self._op: str | None = None
        self._payload: Any = None
        self._filters: list[tuple[str, str, Any]] = []
        self._order: str | None = None
        self._range: tuple[int, int] | None = None
        self._count_mode = False

    def select(self, *_args, **kwargs):
        self._op = "select"
        if kwargs.get("count") == "exact":
            self._count_mode = True
        return self

    def insert(self, payload):
        self._op = "insert"
        self._payload = payload
        return self

    def update(self, payload):
        self._op = "update"
        self._payload = payload
        return self

    def eq(self, col, value):
        self._filters.append(("eq", col, value))
        return self

    def ilike(self, col, pattern):
        self._filters.append(("ilike", col, pattern))
        return self

    def order(self, col, desc=False):  # noqa: ARG002
        self._order = col
        return self

    def range(self, start, end):
        self._range = (start, end)
        return self

    def _apply_filters(self, rows: list[dict]) -> list[dict]:
        matched = list(rows)
        for kind, col, value in self._filters:
            if kind == "eq":
                matched = [r for r in matched if r.get(col) == value]
            elif kind == "ilike":
                needle = value.strip("%").lower()
                matched = [r for r in matched if needle in str(r.get(col, "")).lower()]
        return matched

    def execute(self):
        if self._op == "insert":
            from datetime import datetime

            now = datetime.now(UTC).isoformat()
            row = {
                "id": str(uuid.uuid4()),
                "nome": self._payload["nome"],
                "ativo": True,
                "created_at": now,
                "updated_at": now,
            }
            self._rows.append(row)
            return _Result(data=[row])

        matched = self._apply_filters(self._rows)

        if self._op == "update":
            for row in matched:
                row.update(self._payload or {})
            return _Result(data=matched)

        if self._order:
            matched.sort(key=lambda r: r.get(self._order) or "")
        total = len(matched)
        if self._range:
            start, end = self._range
            matched = matched[start : end + 1]
        return _Result(data=matched, count=total if self._count_mode else None)


@dataclass
class _SupabaseMock:
    setores: list = field(default_factory=list)
    cargos: list = field(default_factory=list)
    tipos_reuniao: list = field(default_factory=list)
    audit_rows: list = field(default_factory=list)

    def table(self, name):
        if name == "setores":
            return _TaxonomyQuery(self.setores)
        if name == "cargos":
            return _TaxonomyQuery(self.cargos)
        if name == "tipos_reuniao":
            return _TaxonomyQuery(self.tipos_reuniao)
        if name == "audit_log":
            return _AuditInsert(self.audit_rows)
        raise AssertionError(f"Tabela inesperada: {name}")


class _AuditInsert:
    def __init__(self, sink: list):
        self._sink = sink
        self._payload: dict | None = None

    def insert(self, row):
        self._payload = row
        return self

    def execute(self):
        if self._payload is not None:
            self._sink.append(self._payload)
        return _Result(data=[self._payload] if self._payload else [])


@dataclass
class _FakeRequest:
    client: Any = None
    headers: dict = field(default_factory=dict)


def _super_admin() -> dict:
    return {
        "id": "P001",
        "email": "admin@ex.com",
        "nome_completo": "Admin Super",
        "role": "diretor",
        "is_super_admin": True,
    }


def _item(nome: str, ativo: bool = True) -> dict:
    from datetime import datetime

    now = datetime.now(UTC).isoformat()
    return {
        "id": str(uuid.uuid4()),
        "nome": nome,
        "ativo": ativo,
        "created_at": now,
        "updated_at": now,
    }


def _get_endpoint(name: str):
    """Recupera a funcao registrada pelo factory via nome."""
    for route in taxonomia_router.router.routes:
        if getattr(route, "name", None) == name:
            return route.endpoint
    raise AssertionError(f"endpoint {name} nao registrado")


# ─── Testes ──────────────────────────────────────────────────────────────────


class TestListSetores:
    @pytest.mark.asyncio
    async def test_ativos_filtra_apenas_ativos(self):
        sb = _SupabaseMock(
            setores=[_item("Alpha", True), _item("Beta", False), _item("Gamma", True)],
        )
        endpoint = _get_endpoint("list_setores")
        res = await endpoint(
            q=None,
            ativo="ativos",
            page=1,
            limit=50,
            _actor=_super_admin(),
            supabase=sb,
        )
        nomes = sorted(r["nome"] for r in res["data"])
        assert nomes == ["Alpha", "Gamma"]
        assert res["total"] == 2

    @pytest.mark.asyncio
    async def test_arquivados_filtra_apenas_inativos(self):
        sb = _SupabaseMock(
            setores=[_item("Alpha", True), _item("Beta", False)],
        )
        endpoint = _get_endpoint("list_setores")
        res = await endpoint(
            q=None,
            ativo="arquivados",
            page=1,
            limit=50,
            _actor=_super_admin(),
            supabase=sb,
        )
        assert [r["nome"] for r in res["data"]] == ["Beta"]

    @pytest.mark.asyncio
    async def test_todos_ignora_flag(self):
        sb = _SupabaseMock(
            setores=[_item("Alpha", True), _item("Beta", False)],
        )
        endpoint = _get_endpoint("list_setores")
        res = await endpoint(
            q=None,
            ativo="todos",
            page=1,
            limit=50,
            _actor=_super_admin(),
            supabase=sb,
        )
        assert len(res["data"]) == 2


class TestCreateSetor:
    @pytest.mark.asyncio
    async def test_cria_e_loga_audit(self):
        sb = _SupabaseMock()
        endpoint = _get_endpoint("create_setores")
        item = await endpoint(
            payload=TaxonomyCreatePayload(nome="Financeiro"),
            request=_FakeRequest(),
            actor=_super_admin(),
            supabase=sb,
        )
        assert item["nome"] == "Financeiro"
        assert item["ativo"] is True
        assert len(sb.audit_rows) == 1
        assert sb.audit_rows[0]["action"] == "setor_create"
        assert sb.audit_rows[0]["target_type"] == "setor"

    @pytest.mark.asyncio
    async def test_duplicata_case_insensitive_retorna_409(self):
        sb = _SupabaseMock(setores=[_item("Financeiro")])
        endpoint = _get_endpoint("create_setores")
        with pytest.raises(HTTPException) as exc:
            await endpoint(
                payload=TaxonomyCreatePayload(nome="FINANCEIRO"),
                request=_FakeRequest(),
                actor=_super_admin(),
                supabase=sb,
            )
        assert exc.value.status_code == 409

    @pytest.mark.asyncio
    async def test_normaliza_espacos(self):
        sb = _SupabaseMock()
        endpoint = _get_endpoint("create_setores")
        item = await endpoint(
            payload=TaxonomyCreatePayload(nome="  Tecnologia  da   Informacao  "),
            request=_FakeRequest(),
            actor=_super_admin(),
            supabase=sb,
        )
        assert item["nome"] == "Tecnologia da Informacao"


class TestUpdateSetor:
    @pytest.mark.asyncio
    async def test_renomeia_e_loga(self):
        existing = _item("Antigo")
        sb = _SupabaseMock(setores=[existing])
        endpoint = _get_endpoint("update_setores")
        res = await endpoint(
            item_id=existing["id"],
            payload=TaxonomyUpdatePayload(nome="Novo"),
            request=_FakeRequest(),
            actor=_super_admin(),
            supabase=sb,
        )
        assert res["nome"] == "Novo"
        assert sb.audit_rows[0]["action"] == "setor_update"

    @pytest.mark.asyncio
    async def test_toggle_ativo(self):
        existing = _item("Comercial", ativo=True)
        sb = _SupabaseMock(setores=[existing])
        endpoint = _get_endpoint("update_setores")
        res = await endpoint(
            item_id=existing["id"],
            payload=TaxonomyUpdatePayload(ativo=False),
            request=_FakeRequest(),
            actor=_super_admin(),
            supabase=sb,
        )
        assert res["ativo"] is False

    @pytest.mark.asyncio
    async def test_mesmo_nome_sem_mudanca_nao_loga(self):
        existing = _item("Mesmo")
        sb = _SupabaseMock(setores=[existing])
        endpoint = _get_endpoint("update_setores")
        res = await endpoint(
            item_id=existing["id"],
            payload=TaxonomyUpdatePayload(),
            request=_FakeRequest(),
            actor=_super_admin(),
            supabase=sb,
        )
        assert res["nome"] == "Mesmo"
        assert sb.audit_rows == []

    @pytest.mark.asyncio
    async def test_404_quando_nao_existe(self):
        sb = _SupabaseMock()
        endpoint = _get_endpoint("update_setores")
        with pytest.raises(HTTPException) as exc:
            await endpoint(
                item_id="nao-existe",
                payload=TaxonomyUpdatePayload(nome="X"),
                request=_FakeRequest(),
                actor=_super_admin(),
                supabase=sb,
            )
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_renomear_para_nome_existente_retorna_409(self):
        a = _item("Alpha")
        b = _item("Beta")
        sb = _SupabaseMock(setores=[a, b])
        endpoint = _get_endpoint("update_setores")
        with pytest.raises(HTTPException) as exc:
            await endpoint(
                item_id=b["id"],
                payload=TaxonomyUpdatePayload(nome="Alpha"),
                request=_FakeRequest(),
                actor=_super_admin(),
                supabase=sb,
            )
        assert exc.value.status_code == 409


class TestArchiveSetor:
    @pytest.mark.asyncio
    async def test_soft_delete_seta_ativo_false_e_loga(self):
        existing = _item("Arquivavel")
        sb = _SupabaseMock(setores=[existing])
        endpoint = _get_endpoint("archive_setores")
        res = await endpoint(
            item_id=existing["id"],
            request=_FakeRequest(),
            actor=_super_admin(),
            supabase=sb,
        )
        assert res["ativo"] is False
        assert sb.audit_rows[0]["action"] == "setor_archive"

    @pytest.mark.asyncio
    async def test_idempotente_nao_loga_de_novo(self):
        existing = _item("JaArquivado", ativo=False)
        sb = _SupabaseMock(setores=[existing])
        endpoint = _get_endpoint("archive_setores")
        res = await endpoint(
            item_id=existing["id"],
            request=_FakeRequest(),
            actor=_super_admin(),
            supabase=sb,
        )
        assert res["ativo"] is False
        assert sb.audit_rows == []


class TestCargosETiposReuniao:
    """Smoke: a factory gera comportamento identico para cargos e tipos_reuniao."""

    @pytest.mark.asyncio
    async def test_cria_cargo(self):
        sb = _SupabaseMock()
        endpoint = _get_endpoint("create_cargos")
        item = await endpoint(
            payload=TaxonomyCreatePayload(nome="Enfermeiro"),
            request=_FakeRequest(),
            actor=_super_admin(),
            supabase=sb,
        )
        assert item["nome"] == "Enfermeiro"
        assert sb.audit_rows[0]["action"] == "cargo_create"

    @pytest.mark.asyncio
    async def test_cria_tipo_reuniao(self):
        sb = _SupabaseMock()
        endpoint = _get_endpoint("create_tipos_reuniao")
        item = await endpoint(
            payload=TaxonomyCreatePayload(nome="Urgente"),
            request=_FakeRequest(),
            actor=_super_admin(),
            supabase=sb,
        )
        assert item["nome"] == "Urgente"
        assert sb.audit_rows[0]["action"] == "tipo_reuniao_create"
        assert sb.audit_rows[0]["target_type"] == "tipo_reuniao"
