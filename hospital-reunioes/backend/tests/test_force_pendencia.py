"""Testes das rotas /pendencias/{id}/force* — super admin only.

Cobre:
- DELETE /force deleta em qualquer status e grava audit_log.
- PATCH /force edita campos e grava audit_log; exige motivo quando muda status ou responsavel.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import Any, Optional

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.models.admin_schemas import ForceEditPendenciaRequest, ReasonRequest  # noqa: E402
from app.models.schemas import StatusPendencia  # noqa: E402
from app.routers.pendencias import (  # noqa: E402
    force_deletar_pendencia,
    force_editar_pendencia,
)


# ─── Mocks ────────────────────────────────────────────────────────────────────


@dataclass
class _Result:
    data: list


class _PendenciasQuery:
    def __init__(self, store: dict[str, dict], deletes_log: list, updates_log: list):
        self._store = store
        self._deletes_log = deletes_log
        self._updates_log = updates_log
        self._filters: dict = {}
        self._pending_update: Optional[dict] = None
        self._mode: Optional[str] = None

    def select(self, *_a, **_kw):
        self._mode = "select"
        return self

    def update(self, data):
        self._mode = "update"
        self._pending_update = data
        return self

    def delete(self):
        self._mode = "delete"
        return self

    def eq(self, col, val):
        self._filters[col] = val
        return self

    def execute(self):
        if self._mode == "select":
            rows = [
                r for r in self._store.values()
                if all(r.get(k) == v for k, v in self._filters.items())
            ]
            return _Result(rows)
        if self._mode == "update":
            target = self._filters.get("id_acao")
            if target in self._store and self._pending_update:
                self._store[target].update(self._pending_update)
                self._updates_log.append({"id": target, "update": dict(self._pending_update)})
                return _Result([self._store[target]])
            return _Result([])
        if self._mode == "delete":
            target = self._filters.get("id_acao")
            if target in self._store:
                deleted = self._store.pop(target)
                self._deletes_log.append({"id": target, "row": deleted})
                return _Result([deleted])
            return _Result([])
        return _Result([])


class _ParticipantesQuery:
    def __init__(self, rows):
        self._rows = rows
        self._filters_eq: dict = {}
        self._filters_in: dict = {}

    def select(self, *_a, **_kw):
        return self

    def eq(self, col, val):
        self._filters_eq[col] = val
        return self

    def in_(self, col, vals):
        self._filters_in[col] = set(vals)
        return self

    def execute(self):
        filtered = []
        for r in self._rows:
            if any(r.get(k) != v for k, v in self._filters_eq.items()):
                continue
            if any(r.get(k) not in vals for k, vals in self._filters_in.items()):
                continue
            filtered.append(r)
        return _Result(filtered)


class _AuditInsert:
    def __init__(self, sink: list):
        self._sink = sink
        self._pending: Optional[dict] = None

    def insert(self, row):
        self._pending = row
        return self

    def execute(self):
        if self._pending:
            self._sink.append(self._pending)
        return _Result([self._pending] if self._pending else [])


@dataclass
class _Sb:
    pendencias: dict[str, dict] = field(default_factory=dict)
    participantes: list = field(default_factory=list)
    audit_rows: list = field(default_factory=list)
    deletes_log: list = field(default_factory=list)
    updates_log: list = field(default_factory=list)
    rpc_calls: list = field(default_factory=list)

    def table(self, name):
        if name == "pendencias":
            return _PendenciasQuery(self.pendencias, self.deletes_log, self.updates_log)
        if name == "participantes":
            return _ParticipantesQuery(self.participantes)
        if name == "audit_log":
            return _AuditInsert(self.audit_rows)
        raise AssertionError(f"Tabela inesperada: {name}")

    def rpc(self, name, params):
        self.rpc_calls.append({"name": name, "params": params})

        class _RpcExec:
            def execute(self_inner):  # noqa: N805
                return _Result([])

        return _RpcExec()


class _FakeRequest:
    def __init__(self, ip: str = "127.0.0.1"):
        self.client = type("Client", (), {"host": ip})()
        self.headers: dict[str, Any] = {}


SUPER_ADMIN = {
    "id": "P01",
    "email": "admin@ex.com",
    "nome_completo": "Pedro Super",
    "is_super_admin": True,
}


# ─── Testes ───────────────────────────────────────────────────────────────────


class TestForceDeletePendencia:
    @pytest.mark.asyncio
    async def test_delete_concluida_decrementa_e_loga(self):
        sb = _Sb(
            pendencias={
                "A001": {
                    "id_acao": "A001",
                    "id_reuniao": "RD_001",
                    "status": "CONCLUIDO",
                    "responsavel_id": "P_RESP",
                    "descricao_acao": "Tarefa X",
                }
            }
        )

        resp = await force_deletar_pendencia(
            id_acao="A001",
            body=ReasonRequest(reason="duplicada no sistema"),
            request=_FakeRequest(),
            actor=SUPER_ADMIN,
            supabase=sb,
        )

        assert resp["id_acao"] == "A001"
        assert "A001" not in sb.pendencias

        # Decrementa foi chamado (era CONCLUIDO)
        assert any(
            c["name"] == "decrementar_acoes_concluidas" for c in sb.rpc_calls
        )

        # Audit
        assert len(sb.audit_rows) == 1
        log = sb.audit_rows[0]
        assert log["action"] == "DELETE_PENDENCIA"
        assert log["target_type"] == "pendencia"
        assert log["target_id"] == "A001"
        assert log["metadata"]["status_before"] == "CONCLUIDO"
        assert log["metadata"]["id_reuniao"] == "RD_001"
        assert log["reason"] == "duplicada no sistema"

    @pytest.mark.asyncio
    async def test_delete_pendente_nao_decrementa(self):
        sb = _Sb(
            pendencias={
                "A002": {
                    "id_acao": "A002",
                    "id_reuniao": "RD_002",
                    "status": "PENDENTE",
                    "responsavel_id": "P_RESP",
                    "descricao_acao": "Outra tarefa",
                }
            }
        )

        await force_deletar_pendencia(
            id_acao="A002",
            body=ReasonRequest(reason="cancelada manualmente"),
            request=_FakeRequest(),
            actor=SUPER_ADMIN,
            supabase=sb,
        )

        assert sb.rpc_calls == []
        assert len(sb.audit_rows) == 1

    @pytest.mark.asyncio
    async def test_delete_404(self):
        sb = _Sb()
        with pytest.raises(HTTPException) as exc:
            await force_deletar_pendencia(
                id_acao="A_X",
                body=ReasonRequest(reason="x"),
                request=_FakeRequest(),
                actor=SUPER_ADMIN,
                supabase=sb,
            )
        assert exc.value.status_code == 404


class TestForceEditPendencia:
    @pytest.mark.asyncio
    async def test_edit_sem_reason_quando_muda_status_422(self):
        sb = _Sb(
            pendencias={
                "A010": {
                    "id_acao": "A010",
                    "id_reuniao": "RD_10",
                    "status": "PENDENTE",
                    "responsavel_id": "P_RESP",
                    "co_responsavel_id": None,
                    "descricao_acao": "Tarefa",
                }
            }
        )
        with pytest.raises(HTTPException) as exc:
            await force_editar_pendencia(
                id_acao="A010",
                body=ForceEditPendenciaRequest(status=StatusPendencia.CONCLUIDO),
                request=_FakeRequest(),
                actor=SUPER_ADMIN,
                supabase=sb,
            )
        assert exc.value.status_code == 422

    @pytest.mark.asyncio
    async def test_edit_muda_status_com_reason_incrementa_e_loga(self):
        sb = _Sb(
            pendencias={
                "A011": {
                    "id_acao": "A011",
                    "id_reuniao": "RD_11",
                    "status": "PENDENTE",
                    "responsavel_id": "P_RESP",
                    "co_responsavel_id": None,
                    "descricao_acao": "Tarefa Y",
                }
            }
        )

        await force_editar_pendencia(
            id_acao="A011",
            body=ForceEditPendenciaRequest(
                status=StatusPendencia.CONCLUIDO,
                reason="fechamento manual solicitado",
            ),
            request=_FakeRequest(),
            actor=SUPER_ADMIN,
            supabase=sb,
        )

        assert sb.pendencias["A011"]["status"] == "CONCLUIDO"
        assert any(
            c["name"] == "incrementar_acoes_concluidas" for c in sb.rpc_calls
        )

        assert len(sb.audit_rows) == 1
        log = sb.audit_rows[0]
        assert log["action"] == "EDIT_PENDENCIA_FORCE"
        assert log["target_id"] == "A011"
        assert log["metadata"]["status_before"] == "PENDENTE"
        assert log["metadata"]["status_after"] == "CONCLUIDO"
        assert "status" in log["metadata"]["campos_mudados"]
        assert log["reason"] == "fechamento manual solicitado"

    @pytest.mark.asyncio
    async def test_edit_descricao_sem_reason_ok(self):
        sb = _Sb(
            pendencias={
                "A012": {
                    "id_acao": "A012",
                    "id_reuniao": "RD_12",
                    "status": "PENDENTE",
                    "responsavel_id": "P_R",
                    "co_responsavel_id": None,
                    "descricao_acao": "Original",
                }
            }
        )

        await force_editar_pendencia(
            id_acao="A012",
            body=ForceEditPendenciaRequest(descricao_acao="Nova descricao"),
            request=_FakeRequest(),
            actor=SUPER_ADMIN,
            supabase=sb,
        )

        assert sb.pendencias["A012"]["descricao_acao"] == "Nova descricao"
        assert len(sb.audit_rows) == 1
        log = sb.audit_rows[0]
        assert log["action"] == "EDIT_PENDENCIA_FORCE"
        assert "descricao_acao" in log["metadata"]["campos_mudados"]
        # reason nao obrigatorio aqui — pode nao aparecer na row
        assert log.get("reason") is None or log["reason"] is None or "reason" not in log
