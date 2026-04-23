"""Testes das rotas /reunioes/{id}/force* — super admin only.

Cobre:
- 403 quando usuario nao e super admin.
- DELETE /force funciona em qualquer status (inclui ASSINADA), loga em audit.
- PATCH /force-status troca status e loga em audit_log.
- PATCH /force edita campos e loga em audit_log.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import Any

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.models.admin_schemas import (  # noqa: E402
    ForceEditReuniaoRequest,
    ForceStatusReuniaoRequest,
    ReasonRequest,
)
from app.models.schemas import StatusAta  # noqa: E402
from app.routers.reunioes import (  # noqa: E402
    force_deletar_reuniao,
    force_editar_reuniao,
    force_status_reuniao,
)

# ─── Mocks ────────────────────────────────────────────────────────────────────


@dataclass
class _Result:
    data: list


class _ReunioesQuery:
    def __init__(self, store: dict[str, dict], deletes_log: list, updates_log: list):
        self._store = store
        self._deletes_log = deletes_log
        self._updates_log = updates_log
        self._filters: dict = {}
        self._pending_update: dict | None = None
        self._mode: str | None = None  # select/update/delete

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
            rows = [r for r in self._store.values() if all(r.get(k) == v for k, v in self._filters.items())]
            return _Result(rows)
        if self._mode == "update":
            target_id = self._filters.get("id_reuniao")
            if target_id in self._store and self._pending_update:
                self._store[target_id].update(self._pending_update)
                self._updates_log.append({"id": target_id, "update": dict(self._pending_update)})
                return _Result([self._store[target_id]])
            return _Result([])
        if self._mode == "delete":
            target_id = self._filters.get("id_reuniao")
            if target_id in self._store:
                deleted = self._store.pop(target_id)
                self._deletes_log.append({"id": target_id, "row": deleted})
                return _Result([deleted])
            return _Result([])
        return _Result([])


class _ParticipantesLinkQuery:
    """Mock para reuniao_participantes — upsert/delete."""

    def __init__(self, links: list, upserts_log: list, deletes_log: list):
        self._links = links
        self._upserts_log = upserts_log
        self._deletes_log = deletes_log
        self._filters: dict = {}
        self._pending_rows: list | None = None
        self._mode: str | None = None

    def upsert(self, rows, on_conflict=None):
        self._mode = "upsert"
        self._pending_rows = rows
        return self

    def delete(self):
        self._mode = "delete"
        return self

    def eq(self, col, val):
        self._filters[col] = val
        return self

    def execute(self):
        if self._mode == "upsert" and self._pending_rows:
            self._upserts_log.extend(self._pending_rows)
            self._links.extend(self._pending_rows)
            return _Result(self._pending_rows)
        if self._mode == "delete":
            before = len(self._links)
            self._links[:] = [r for r in self._links if not all(r.get(k) == v for k, v in self._filters.items())]
            self._deletes_log.append({"removed": before - len(self._links), "filters": dict(self._filters)})
            return _Result([])
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
    reuniao_participantes: list = field(default_factory=list)
    audit_rows: list = field(default_factory=list)
    deletes_log: list = field(default_factory=list)
    updates_log: list = field(default_factory=list)
    link_upserts: list = field(default_factory=list)
    link_deletes: list = field(default_factory=list)

    def table(self, name):
        if name == "reunioes":
            return _ReunioesQuery(self.reunioes, self.deletes_log, self.updates_log)
        if name == "reuniao_participantes":
            return _ParticipantesLinkQuery(self.reuniao_participantes, self.link_upserts, self.link_deletes)
        if name == "audit_log":
            return _AuditInsert(self.audit_rows)
        raise AssertionError(f"Tabela inesperada: {name}")


class _FakeRequest:
    def __init__(self, ip: str = "127.0.0.1"):
        self.client = type("Client", (), {"host": ip})()
        self.headers: dict[str, Any] = {}


# ─── Testes ───────────────────────────────────────────────────────────────────


SUPER_ADMIN = {
    "id": "P01",
    "email": "admin@ex.com",
    "nome_completo": "Pedro Super",
    "is_super_admin": True,
}


class TestForceDeleteReuniao:
    @pytest.mark.asyncio
    async def test_403_quando_require_super_admin_rejeita(self):
        # Simulamos o dependency ja tendo falhado: se actor nao passasse,
        # FastAPI retornaria 403 antes da funcao. Aqui testamos que a
        # dependency require_super_admin levanta 403 para usuario sem flag.
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
                filtered = [r for r in self._rows if all(r.get(k) == v for k, v in self._filters.items())]
                return _Result(filtered)

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
                    "email": "diretor@ex.com",
                    "is_super_admin": False,
                    "role": "diretor",
                    "nome_completo": "Diretor Comum",
                }
            ]
        )

        with pytest.raises(HTTPException) as exc:
            await require_super_admin(
                current_user={"id": "auth-99", "email": "diretor@ex.com", "metadata": {}},
                supabase=sb,
            )
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_force_delete_em_ata_assinada_grava_audit(self):
        sb = _Sb(
            reunioes={
                "RD_001": {
                    "id_reuniao": "RD_001",
                    "status_ata": "ASSINADA",
                    "titulo": "Reuniao Importante",
                }
            }
        )

        resp = await force_deletar_reuniao(
            id_reuniao="RD_001",
            body=ReasonRequest(reason="ata duplicada erroneamente"),
            request=_FakeRequest(),
            actor=SUPER_ADMIN,
            supabase=sb,
        )

        assert resp["id_reuniao"] == "RD_001"
        assert resp["status_before"] == "ASSINADA"
        # Reuniao foi deletada do store
        assert "RD_001" not in sb.reunioes
        # Audit log gravado
        assert len(sb.audit_rows) == 1
        log = sb.audit_rows[0]
        assert log["action"] == "DELETE_REUNIAO"
        assert log["target_type"] == "reuniao"
        assert log["target_id"] == "RD_001"
        assert log["metadata"]["status_before"] == "ASSINADA"
        assert log["metadata"]["titulo"] == "Reuniao Importante"
        assert log["reason"] == "ata duplicada erroneamente"

    @pytest.mark.asyncio
    async def test_force_delete_404_quando_nao_existe(self):
        sb = _Sb()
        with pytest.raises(HTTPException) as exc:
            await force_deletar_reuniao(
                id_reuniao="RD_NAO_EXISTE",
                body=ReasonRequest(reason="teste"),
                request=_FakeRequest(),
                actor=SUPER_ADMIN,
                supabase=sb,
            )
        assert exc.value.status_code == 404


class TestForceStatusReuniao:
    @pytest.mark.asyncio
    async def test_force_status_altera_e_loga(self):
        sb = _Sb(
            reunioes={
                "RD_002": {
                    "id_reuniao": "RD_002",
                    "status_ata": "ASSINADA",
                }
            }
        )

        resp = await force_status_reuniao(
            id_reuniao="RD_002",
            body=ForceStatusReuniaoRequest(
                novo_status=StatusAta.AGUARDANDO_VALIDACAO,
                reason="reabrir para correção",
            ),
            request=_FakeRequest(),
            actor=SUPER_ADMIN,
            supabase=sb,
        )

        assert resp["status_before"] == "ASSINADA"
        assert resp["status_after"] == "AGUARDANDO_VALIDACAO"
        assert sb.reunioes["RD_002"]["status_ata"] == "AGUARDANDO_VALIDACAO"

        # Audit log
        assert len(sb.audit_rows) == 1
        log = sb.audit_rows[0]
        assert log["action"] == "FORCE_STATUS"
        assert log["target_type"] == "reuniao"
        assert log["target_id"] == "RD_002"
        assert log["metadata"]["status_before"] == "ASSINADA"
        assert log["metadata"]["status_after"] == "AGUARDANDO_VALIDACAO"
        assert log["reason"] == "reabrir para correção"

    @pytest.mark.asyncio
    async def test_force_status_404_quando_nao_existe(self):
        sb = _Sb()
        with pytest.raises(HTTPException) as exc:
            await force_status_reuniao(
                id_reuniao="RD_X",
                body=ForceStatusReuniaoRequest(novo_status=StatusAta.CANCELADA, reason="teste"),
                request=_FakeRequest(),
                actor=SUPER_ADMIN,
                supabase=sb,
            )
        assert exc.value.status_code == 404


class TestForceEditReuniao:
    @pytest.mark.asyncio
    async def test_force_edit_campos_basicos_loga_campos_mudados(self):
        sb = _Sb(
            reunioes={
                "RD_003": {
                    "id_reuniao": "RD_003",
                    "status_ata": "ASSINADA",
                    "titulo": "Antigo",
                }
            }
        )

        resp = await force_editar_reuniao(
            id_reuniao="RD_003",
            body=ForceEditReuniaoRequest(
                titulo="Novo Titulo",
                reason="correção solicitada pelo diretor",
            ),
            request=_FakeRequest(),
            actor=SUPER_ADMIN,
            supabase=sb,
        )

        assert "titulo" in resp["campos_atualizados"]
        assert sb.reunioes["RD_003"]["titulo"] == "Novo Titulo"

        # Audit
        assert len(sb.audit_rows) == 1
        log = sb.audit_rows[0]
        assert log["action"] == "EDIT_REUNIAO_FORCE"
        assert log["target_id"] == "RD_003"
        assert "titulo" in log["metadata"]["campos_mudados"]
        assert log["metadata"]["status_before"] == "ASSINADA"
        assert log["reason"] == "correção solicitada pelo diretor"

    @pytest.mark.asyncio
    async def test_force_edit_substitui_participantes(self):
        sb = _Sb(
            reunioes={"RD_004": {"id_reuniao": "RD_004", "status_ata": "PROGRAMADA"}},
            reuniao_participantes=[{"id_reuniao": "RD_004", "participante_id": "P_OLD"}],
        )

        resp = await force_editar_reuniao(
            id_reuniao="RD_004",
            body=ForceEditReuniaoRequest(
                participante_ids=["P_NEW1", "P_NEW2"],
                reason="time restruturado",
            ),
            request=_FakeRequest(),
            actor=SUPER_ADMIN,
            supabase=sb,
        )

        assert "participante_ids" in resp["campos_atualizados"]
        # Link antigo foi removido e novos inseridos
        current_pids = [r["participante_id"] for r in sb.reuniao_participantes]
        assert "P_OLD" not in current_pids
        assert set(current_pids) == {"P_NEW1", "P_NEW2"}

    @pytest.mark.asyncio
    async def test_force_edit_422_quando_sem_campos(self):
        sb = _Sb(reunioes={"RD_005": {"id_reuniao": "RD_005", "status_ata": "PROGRAMADA"}})
        with pytest.raises(HTTPException) as exc:
            await force_editar_reuniao(
                id_reuniao="RD_005",
                body=ForceEditReuniaoRequest(reason="sem nada"),
                request=_FakeRequest(),
                actor=SUPER_ADMIN,
                supabase=sb,
            )
        assert exc.value.status_code == 422
