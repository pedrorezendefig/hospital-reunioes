"""Testes da camada super admin (Fase 01).

Cobre:
- is_super_admin(participante) — true com flag, false sem.
- require_super_admin dependency — 403 sem flag, participante com flag.
- audit.log_action() — grava linha com os campos esperados, nao levanta em falha.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import Any

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.dependencies import is_super_admin, require_super_admin  # noqa: E402
from app.services import audit  # noqa: E402

# ─── Mocks ────────────────────────────────────────────────────────────────────


@dataclass
class _Result:
    data: list


class _ParticipantesQuery:
    def __init__(self, rows):
        self._rows = rows
        self._filters: dict = {}

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, col, value):
        self._filters[col] = value
        return self

    def execute(self):
        filtered = self._rows
        for col, value in self._filters.items():
            filtered = [r for r in filtered if r.get(col) == value]
        return _Result(data=filtered)

    def update(self, *_args, **_kwargs):  # noqa: ARG002
        return self


class _AuditInsert:
    def __init__(self, sink):
        self._sink = sink
        self._pending = None

    def insert(self, row):
        self._pending = row
        return self

    def execute(self):
        if self._pending is not None:
            self._sink.append(self._pending)
        return _Result(data=[self._pending] if self._pending else [])


class _AuditFailingInsert:
    def insert(self, _row):
        return self

    def execute(self):
        raise RuntimeError("supabase indisponivel")


@dataclass
class _SupabaseMock:
    participantes: list = field(default_factory=list)
    audit_rows: list = field(default_factory=list)
    fail_audit: bool = False

    def table(self, name):
        if name == "participantes":
            return _ParticipantesQuery(self.participantes)
        if name == "audit_log":
            return _AuditFailingInsert() if self.fail_audit else _AuditInsert(self.audit_rows)
        raise AssertionError(f"Tabela inesperada: {name}")


# ─── Testes: is_super_admin ───────────────────────────────────────────────────


class TestIsSuperAdmin:
    def test_true_quando_flag_true(self):
        assert is_super_admin({"id": "P1", "is_super_admin": True}) is True

    def test_false_quando_flag_false(self):
        assert is_super_admin({"id": "P1", "is_super_admin": False}) is False

    def test_false_quando_flag_ausente(self):
        # Diretor SEM flag — comportamento novo: nao e super admin.
        assert is_super_admin({"id": "P1", "role": "diretor"}) is False

    def test_false_quando_none(self):
        assert is_super_admin(None) is False

    def test_levanta_para_string(self):
        # Proteje contra chamada antiga is_super_admin("diretor").
        with pytest.raises(TypeError):
            is_super_admin("diretor")  # type: ignore[arg-type]


# ─── Testes: require_super_admin dependency ───────────────────────────────────


class TestRequireSuperAdmin:
    @pytest.mark.asyncio
    async def test_403_quando_sem_flag(self):
        sb = _SupabaseMock(
            participantes=[
                {
                    "id": "P10",
                    "auth_user_id": "auth-10",
                    "email": "diretor@ex.com",
                    "role": "diretor",
                    "is_super_admin": False,
                    "nome_completo": "Diretor Comum",
                }
            ]
        )
        with pytest.raises(HTTPException) as exc:
            await require_super_admin(
                current_user={"id": "auth-10", "email": "diretor@ex.com", "metadata": {}},
                supabase=sb,
            )
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_403_quando_sem_participante(self):
        sb = _SupabaseMock(participantes=[])
        with pytest.raises(HTTPException) as exc:
            await require_super_admin(
                current_user={"id": "auth-x", "email": "novo@ex.com", "metadata": {}},
                supabase=sb,
            )
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_retorna_participante_quando_super_admin(self):
        sb = _SupabaseMock(
            participantes=[
                {
                    "id": "P20",
                    "auth_user_id": "auth-20",
                    "email": "admin@ex.com",
                    "role": "coordenador",
                    "is_super_admin": True,
                    "nome_completo": "Pedro Super",
                }
            ]
        )
        me = await require_super_admin(
            current_user={"id": "auth-20", "email": "admin@ex.com", "metadata": {}},
            supabase=sb,
        )
        assert me["id"] == "P20"
        assert me["is_super_admin"] is True


# ─── Testes: audit.log_action ─────────────────────────────────────────────────


class _FakeRequest:
    def __init__(self, ip: str):
        self.client = type("Client", (), {"host": ip})()
        self.headers: dict[str, Any] = {}


class TestAuditLogAction:
    def test_grava_linha_completa(self):
        sb = _SupabaseMock()
        audit.log_action(
            sb,
            actor={"id": "P01", "email": "admin@ex.com"},
            action="DELETE_ATA",
            target_type="reuniao",
            target_id="RD_20260101_ABC",
            metadata={"status_before": "ASSINADA"},
            reason="ata duplicada",
            request=_FakeRequest("10.0.0.1"),
        )
        assert len(sb.audit_rows) == 1
        row = sb.audit_rows[0]
        assert row["actor_id"] == "P01"
        assert row["actor_email"] == "admin@ex.com"
        assert row["action"] == "DELETE_ATA"
        assert row["target_type"] == "reuniao"
        assert row["target_id"] == "RD_20260101_ABC"
        assert row["metadata"] == {"status_before": "ASSINADA"}
        assert row["reason"] == "ata duplicada"
        assert row["ip_address"] == "10.0.0.1"

    def test_sem_actor_grava_email_desconhecido(self):
        sb = _SupabaseMock()
        audit.log_action(
            sb,
            actor=None,
            action="PROMOTE_SUPER_ADMIN",
            target_type="participante",
            target_id="P99",
        )
        assert len(sb.audit_rows) == 1
        row = sb.audit_rows[0]
        assert row["actor_id"] is None
        assert row["actor_email"] == "desconhecido"
        assert row["metadata"] == {}
        assert "reason" not in row
        assert "ip_address" not in row

    def test_falha_supabase_nao_propaga(self):
        # audit NUNCA deve quebrar o caller.
        sb = _SupabaseMock(fail_audit=True)
        audit.log_action(
            sb,
            actor={"id": "P01", "email": "admin@ex.com"},
            action="RESET_PASSWORD",
            target_type="participante",
            target_id="P02",
        )
        # Se chegou aqui, nao levantou.
        assert sb.audit_rows == []
