"""Testes do router /admin/super-admins (Fase 02).

Cobre:
- 403 quando o usuario nao e super admin.
- GET lista todos os super admins.
- POST promote: sucesso + ja era super admin (400).
- POST demote: sucesso + auto-demote (400) + ultimo super admin (400).
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.dependencies import get_current_user, get_supabase_client  # noqa: E402
from app.routers.admin import super_admins as admin_super_admins  # noqa: E402

# ─── Mock Supabase ────────────────────────────────────────────────────────────


@dataclass
class _Result:
    data: list


class _ParticipantesQuery:
    """Mock do query builder do Supabase para a tabela participantes."""

    def __init__(self, rows: list):
        self._rows = rows
        self._filters: dict = {}
        self._update_payload: dict | None = None
        self._order_col: str | None = None

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, col, value):
        self._filters[col] = value
        return self

    def order(self, col, *_args, **_kwargs):
        self._order_col = col
        return self

    def update(self, payload):
        self._update_payload = payload
        return self

    def execute(self):
        filtered = [r for r in self._rows if all(r.get(c) == v for c, v in self._filters.items())]
        if self._update_payload is not None:
            for row in filtered:
                row.update(self._update_payload)
            self._update_payload = None
            self._filters = {}
            return _Result(data=[dict(r) for r in filtered] if filtered else [])
        if self._order_col:
            filtered = sorted(filtered, key=lambda r: r.get(self._order_col) or "")
            self._order_col = None
        self._filters = {}
        return _Result(data=[dict(r) for r in filtered])


class _AuditInsert:
    def __init__(self, sink: list):
        self._sink = sink
        self._pending: dict | None = None

    def insert(self, row):
        self._pending = row
        return self

    def execute(self):
        if self._pending is not None:
            self._sink.append(self._pending)
            self._pending = None
        return _Result(data=[])


@dataclass
class _SupabaseMock:
    participantes: list = field(default_factory=list)
    audit_rows: list = field(default_factory=list)

    def table(self, name: str):
        if name == "participantes":
            return _ParticipantesQuery(self.participantes)
        if name == "audit_log":
            return _AuditInsert(self.audit_rows)
        raise AssertionError(f"Tabela inesperada: {name}")


# ─── Setup app + overrides ────────────────────────────────────────────────────


def _make_app(
    participantes: list,
    current_auth_id: str = "auth-admin",
    current_email: str = "admin@ex.com",
) -> tuple[FastAPI, _SupabaseMock, TestClient]:
    app = FastAPI()
    app.include_router(admin_super_admins.router)

    sb = _SupabaseMock(participantes=participantes)

    async def _fake_user() -> dict[str, Any]:
        return {"id": current_auth_id, "email": current_email, "metadata": {}}

    def _fake_supabase():
        return sb

    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_supabase_client] = _fake_supabase

    return app, sb, TestClient(app)


_MIRROR = "_mirror"


def _admin_row(
    pid: str,
    auth_id: str,
    email: str,
    is_super_admin: bool,
    nome: str | None = None,
    access_profile: str | None = _MIRROR,
) -> dict:
    """Linha de participante. Por default access_profile espelha a flag
    (estado pos-migration 036). Passe access_profile=None para simular NULL
    (pre-backfill) ou um valor explicito para simular divergencia.
    """
    if access_profile == _MIRROR:
        access_profile = "super_admin" if is_super_admin else "regular"
    return {
        "id": pid,
        "auth_user_id": auth_id,
        "email": email,
        "nome_completo": nome or f"User {pid}",
        "cargo": "Diretor",
        "setor": "Setor X",
        "role": "diretor",
        "is_super_admin": is_super_admin,
        "access_profile": access_profile,
    }


# ─── Testes ───────────────────────────────────────────────────────────────────


class TestSuperAdminsRouter:
    def test_403_quando_nao_super_admin(self):
        participantes = [
            _admin_row("P1", "auth-admin", "admin@ex.com", is_super_admin=False),
            _admin_row("P2", "auth-2", "outro@ex.com", is_super_admin=True),
        ]
        _, _, client = _make_app(participantes)
        r = client.get("/admin/super-admins")
        assert r.status_code == 403

    def test_get_lista_super_admins(self):
        participantes = [
            _admin_row("P1", "auth-admin", "admin@ex.com", is_super_admin=True, nome="Alice"),
            _admin_row("P2", "auth-2", "bob@ex.com", is_super_admin=True, nome="Bob"),
            _admin_row("P3", "auth-3", "carol@ex.com", is_super_admin=False, nome="Carol"),
        ]
        _, _, client = _make_app(participantes)
        r = client.get("/admin/super-admins")
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 2
        emails = {row["email"] for row in data}
        assert emails == {"admin@ex.com", "bob@ex.com"}
        # Sanity: nao vaza a flag is_super_admin no response
        assert "is_super_admin" not in data[0]

    def test_promote_sucesso(self):
        participantes = [
            _admin_row("P1", "auth-admin", "admin@ex.com", is_super_admin=True),
            _admin_row("P2", "auth-2", "novo@ex.com", is_super_admin=False),
        ]
        _, sb, client = _make_app(participantes)
        r = client.post(
            "/admin/super-admins/P2/promote",
            json={"reason": "novo diretor medico"},
        )
        assert r.status_code == 200
        assert r.json()["email"] == "novo@ex.com"
        # Flag foi atualizada
        p2 = next(p for p in sb.participantes if p["id"] == "P2")
        assert p2["is_super_admin"] is True
        # Audit log foi gravado
        assert len(sb.audit_rows) == 1
        log = sb.audit_rows[0]
        assert log["action"] == "PROMOTE_SUPER_ADMIN"
        assert log["target_type"] == "participante"
        assert log["target_id"] == "P2"
        assert log["reason"] == "novo diretor medico"

    def test_promote_ja_super_admin_retorna_400(self):
        participantes = [
            _admin_row("P1", "auth-admin", "admin@ex.com", is_super_admin=True),
            _admin_row("P2", "auth-2", "outro@ex.com", is_super_admin=True),
        ]
        _, sb, client = _make_app(participantes)
        r = client.post(
            "/admin/super-admins/P2/promote",
            json={"reason": "x"},
        )
        assert r.status_code == 400
        assert "ja e super admin" in r.json()["detail"].lower()
        # Nao loga em audit se a acao nao teve efeito
        assert sb.audit_rows == []

    def test_promote_sem_reason_retorna_422(self):
        # Motivo OBRIGATORIO — FastAPI/Pydantic valida e retorna 422
        participantes = [
            _admin_row("P1", "auth-admin", "admin@ex.com", is_super_admin=True),
            _admin_row("P2", "auth-2", "novo@ex.com", is_super_admin=False),
        ]
        _, _, client = _make_app(participantes)
        r = client.post("/admin/super-admins/P2/promote", json={})
        assert r.status_code == 422

    def test_demote_sucesso(self):
        participantes = [
            _admin_row("P1", "auth-admin", "admin@ex.com", is_super_admin=True),
            _admin_row("P2", "auth-2", "outro@ex.com", is_super_admin=True),
        ]
        _, sb, client = _make_app(participantes)
        r = client.post(
            "/admin/super-admins/P2/demote",
            json={"reason": "saiu da empresa"},
        )
        assert r.status_code == 200
        p2 = next(p for p in sb.participantes if p["id"] == "P2")
        assert p2["is_super_admin"] is False
        assert len(sb.audit_rows) == 1
        assert sb.audit_rows[0]["action"] == "DEMOTE_SUPER_ADMIN"
        assert sb.audit_rows[0]["reason"] == "saiu da empresa"

    def test_demote_auto_retorna_400(self):
        # Actor (P1) tentando rebaixar a si mesmo.
        participantes = [
            _admin_row("P1", "auth-admin", "admin@ex.com", is_super_admin=True),
            _admin_row("P2", "auth-2", "outro@ex.com", is_super_admin=True),
        ]
        _, sb, client = _make_app(participantes)
        r = client.post(
            "/admin/super-admins/P1/demote",
            json={"reason": "testando"},
        )
        assert r.status_code == 400
        assert "rebaixar a si mesmo" in r.json()["detail"].lower()
        p1 = next(p for p in sb.participantes if p["id"] == "P1")
        assert p1["is_super_admin"] is True
        assert sb.audit_rows == []

    def test_demote_ultimo_super_admin_retorna_400(self):
        # Cenario: 2 super admins no BD (actor + target). Mockamos
        # `_count_super_admins` para simular "restaria 0" e verificar bloqueio.
        # Auto-demote bate antes, entao target precisa ser diferente do actor.
        participantes = [
            _admin_row("P1", "auth-admin", "admin@ex.com", is_super_admin=True),
            _admin_row("P2", "auth-2", "outro@ex.com", is_super_admin=True),
        ]
        _, sb, client = _make_app(participantes)

        import app.routers.admin.super_admins as mod

        original = mod._count_super_admins
        try:
            # Forca count=1 para disparar a regra do ultimo super admin.
            mod._count_super_admins = lambda _sb: 1  # type: ignore[assignment]
            r = client.post(
                "/admin/super-admins/P2/demote",
                json={"reason": "testando"},
            )
        finally:
            mod._count_super_admins = original

        assert r.status_code == 400
        assert "ultimo super admin" in r.json()["detail"].lower()
        p2 = next(p for p in sb.participantes if p["id"] == "P2")
        assert p2["is_super_admin"] is True
        assert sb.audit_rows == []

    def test_demote_participante_nao_super_admin_retorna_400(self):
        participantes = [
            _admin_row("P1", "auth-admin", "admin@ex.com", is_super_admin=True),
            _admin_row("P2", "auth-2", "comum@ex.com", is_super_admin=False),
        ]
        _, sb, client = _make_app(participantes)
        r = client.post(
            "/admin/super-admins/P2/demote",
            json={"reason": "nao era mesmo"},
        )
        assert r.status_code == 400
        assert "nao e super admin" in r.json()["detail"].lower()
        assert sb.audit_rows == []

    def test_promote_participante_inexistente_retorna_404(self):
        participantes = [
            _admin_row("P1", "auth-admin", "admin@ex.com", is_super_admin=True),
        ]
        _, _, client = _make_app(participantes)
        r = client.post(
            "/admin/super-admins/P999/promote",
            json={"reason": "nao existe"},
        )
        assert r.status_code == 404


class TestSuperAdminLegadoFonteDeVerdade:
    """Regressao issue #191: o caminho legado escrevia so a coluna espelho
    is_super_admin, enquanto require_super_admin le access_profile primeiro.
    Promote nao concedia e demote nao revogava de fato.
    """

    def test_regressao_demote_revoga_de_fato(self):
        # Estado de producao (pos-migration 036): access_profile preenchido.
        participantes = [
            _admin_row("P1", "auth-admin", "admin@ex.com", is_super_admin=True),
            _admin_row("P2", "auth-2", "outro@ex.com", is_super_admin=True),
        ]
        _, sb, client = _make_app(participantes)
        r = client.post(
            "/admin/super-admins/P2/demote",
            json={"reason": "saiu da diretoria"},
        )
        assert r.status_code == 200

        # As duas colunas foram revogadas (fonte da verdade + espelho).
        p2 = next(p for p in sb.participantes if p["id"] == "P2")
        assert p2["is_super_admin"] is False
        assert p2["access_profile"] == "regular"

        # E o poder foi removido de fato: como P2, um endpoint protegido por
        # require_super_admin agora responde 403.
        _, _, client_p2 = _make_app(sb.participantes, current_auth_id="auth-2", current_email="outro@ex.com")
        r2 = client_p2.get("/admin/super-admins")
        assert r2.status_code == 403

    def test_regressao_promote_concede_de_fato(self):
        participantes = [
            _admin_row("P1", "auth-admin", "admin@ex.com", is_super_admin=True),
            _admin_row("P2", "auth-2", "novo@ex.com", is_super_admin=False),
        ]
        _, sb, client = _make_app(participantes)
        r = client.post(
            "/admin/super-admins/P2/promote",
            json={"reason": "novo diretor"},
        )
        assert r.status_code == 200

        p2 = next(p for p in sb.participantes if p["id"] == "P2")
        assert p2["is_super_admin"] is True
        assert p2["access_profile"] == "super_admin"

        # Poder concedido de fato: P2 passa em require_super_admin.
        _, _, client_p2 = _make_app(sb.participantes, current_auth_id="auth-2", current_email="novo@ex.com")
        r2 = client_p2.get("/admin/super-admins")
        assert r2.status_code == 200

    def test_demote_ultimo_conta_por_access_profile(self):
        # Divergencia real: actor e super admin so pelo fallback do espelho
        # (access_profile NULL, pre-backfill); o alvo e o UNICO super admin
        # por access_profile. Contando pelo espelho seriam 2 (liberaria);
        # contando pela fonte da verdade e 1 (bloqueia).
        participantes = [
            _admin_row("P1", "auth-admin", "admin@ex.com", is_super_admin=True, access_profile=None),
            _admin_row("P2", "auth-2", "outro@ex.com", is_super_admin=True),
        ]
        _, sb, client = _make_app(participantes)
        r = client.post(
            "/admin/super-admins/P2/demote",
            json={"reason": "testando"},
        )
        assert r.status_code == 400
        assert "ultimo super admin" in r.json()["detail"].lower()
        p2 = next(p for p in sb.participantes if p["id"] == "P2")
        assert p2["access_profile"] == "super_admin"
        assert sb.audit_rows == []

    def test_get_lista_por_access_profile(self):
        # P3 foi "revogado" pelo demote legado pre-fix: espelho False, mas
        # access_profile ainda super_admin (continua com poder). A lista deve
        # mostrar quem tem poder de fato, pela mesma fonte da checagem.
        participantes = [
            _admin_row("P1", "auth-admin", "admin@ex.com", is_super_admin=True, nome="Alice"),
            _admin_row(
                "P3",
                "auth-3",
                "fantasma@ex.com",
                is_super_admin=False,
                nome="Carol",
                access_profile="super_admin",
            ),
        ]
        _, _, client = _make_app(participantes)
        r = client.get("/admin/super-admins")
        assert r.status_code == 200
        emails = {row["email"] for row in r.json()}
        assert emails == {"admin@ex.com", "fantasma@ex.com"}
