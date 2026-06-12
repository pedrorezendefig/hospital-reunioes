"""Testes do endpoint GET /api/participantes/me (Fase F06).

Cobre:
- 200 quando usuario autenticado tem participante vinculado.
- Campos essenciais presentes na resposta (inclui is_super_admin).
- 401 quando nao ha Bearer token.
- 404 quando auth.user nao tem participante vinculado (por auth_user_id nem email).
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
from app.routers import participantes as participantes_router  # noqa: E402

# ─── Mock Supabase ────────────────────────────────────────────────────────────


@dataclass
class _Result:
    data: list


class _ParticipantesQuery:
    def __init__(self, rows: list):
        self._rows = rows
        self._filters: dict = {}
        self._update_payload: dict | None = None

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, col, value):
        self._filters[col] = value
        return self

    def order(self, *_args, **_kwargs):
        return self

    def range(self, *_args, **_kwargs):
        return self

    def ilike(self, *_args, **_kwargs):
        return self

    def neq(self, *_args, **_kwargs):
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
            return _Result(data=[dict(r) for r in filtered])
        self._filters = {}
        return _Result(data=[dict(r) for r in filtered])


@dataclass
class _SupabaseMock:
    participantes: list = field(default_factory=list)

    def table(self, name: str):
        if name == "participantes":
            return _ParticipantesQuery(self.participantes)
        raise AssertionError(f"Tabela inesperada: {name}")


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _make_app(
    participantes: list,
    current_user: dict[str, Any] | None = None,
) -> tuple[FastAPI, _SupabaseMock, TestClient]:
    app = FastAPI()
    app.include_router(participantes_router.router, prefix="/api")

    sb = _SupabaseMock(participantes=participantes)

    if current_user is not None:

        async def _fake_user() -> dict[str, Any]:
            return current_user

        app.dependency_overrides[get_current_user] = _fake_user

    def _fake_supabase():
        return sb

    app.dependency_overrides[get_supabase_client] = _fake_supabase
    return app, sb, TestClient(app)


def _participante_row(
    pid: str = "P1",
    auth_id: str = "auth-1",
    email: str = "alice@ex.com",
    is_super_admin: bool = False,
) -> dict:
    return {
        "id": pid,
        "auth_user_id": auth_id,
        "email": email,
        "nome_completo": "Alice Participante",
        "cargo": "Coordenadora",
        "area": "Assistencial",
        "setor": "UTI",
        "role": "coordenador",
        "ativo": True,
        "is_externo": False,
        "is_super_admin": is_super_admin,
        "data_cadastro": "2026-01-10",
    }


# ─── Testes ───────────────────────────────────────────────────────────────────


class TestGetMe:
    def test_200_retorna_participante_com_flag(self):
        rows = [_participante_row(is_super_admin=True)]
        _, _, client = _make_app(
            rows,
            current_user={"id": "auth-1", "email": "alice@ex.com", "metadata": {}},
        )
        r = client.get("/api/participantes/me")
        assert r.status_code == 200
        body = r.json()
        # Campos obrigatorios
        assert body["id"] == "P1"
        assert body["nome_completo"] == "Alice Participante"
        assert body["email"] == "alice@ex.com"
        assert body["cargo"] == "Coordenadora"
        assert body["area"] == "Assistencial"
        assert body["setor"] == "UTI"
        assert body["role"] == "coordenador"
        assert body["ativo"] is True
        assert body["is_externo"] is False
        assert body["is_super_admin"] is True

    def test_200_fallback_por_email_quando_sem_auth_user_id(self):
        row = _participante_row(auth_id=None)  # type: ignore[arg-type]
        row["auth_user_id"] = None
        _, sb, client = _make_app(
            [row],
            current_user={"id": "auth-novo", "email": "alice@ex.com", "metadata": {}},
        )
        r = client.get("/api/participantes/me")
        assert r.status_code == 200
        body = r.json()
        assert body["email"] == "alice@ex.com"
        # Lazy sync: auth_user_id foi preenchido.
        assert sb.participantes[0]["auth_user_id"] == "auth-novo"

    def test_404_quando_user_sem_participante(self):
        _, _, client = _make_app(
            [],
            current_user={"id": "auth-x", "email": "fantasma@ex.com", "metadata": {}},
        )
        r = client.get("/api/participantes/me")
        assert r.status_code == 404

    def test_200_inclui_perfil_pop_e_access_profile_nulo(self):
        # Pessoa só do contexto POPs (ADR 0007): sem papel nas Reuniões
        # (access_profile NULL), com perfil_pop — o frontend decide a
        # navegação a partir destes dois eixos.
        row = _participante_row()
        row["access_profile"] = None
        row["perfil_pop"] = "coordenador"
        _, _, client = _make_app(
            [row],
            current_user={"id": "auth-1", "email": "alice@ex.com", "metadata": {}},
        )
        r = client.get("/api/participantes/me")
        assert r.status_code == 200
        body = r.json()
        assert body["perfil_pop"] == "coordenador"
        assert body["access_profile"] is None

    def test_401_sem_bearer(self):
        # Sem override de get_current_user: roda o dependency real, que
        # valida Bearer e retorna 401 quando ausente.
        app = FastAPI()
        app.include_router(participantes_router.router, prefix="/api")
        sb = _SupabaseMock(participantes=[])
        app.dependency_overrides[get_supabase_client] = lambda: sb
        client = TestClient(app)
        r = client.get("/api/participantes/me")
        assert r.status_code == 401
