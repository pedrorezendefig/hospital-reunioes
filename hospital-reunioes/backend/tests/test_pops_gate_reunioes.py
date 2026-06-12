"""Gate de contexto: quem só tem perfil POP não acessa Reuniões/Notas/Pendências.

ADR 0007: access_profile é o eixo de permissão do contexto Reuniões;
NULL = sem papel nesse contexto. Coordenador/Gerente de POPs logam no mesmo
app mas recebem 403 nos endpoints de Reuniões, Notas, Pendências e
Comentários (disciplina ADR 0002 — gating na camada de app, sem RLS).
Facilitador (regular) e Secretária seguem passando; quem tem os dois papéis
transita entre os contextos no mesmo login.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.dependencies import get_current_user, get_supabase_client  # noqa: E402
from app.routers import comentarios as comentarios_router  # noqa: E402
from app.routers import notas as notas_router  # noqa: E402
from app.routers import pendencias as pendencias_router  # noqa: E402
from app.routers import reunioes as reunioes_router  # noqa: E402

# ─── Mock Supabase genérico (qualquer tabela; só participantes tem dados) ────


@dataclass
class _Result:
    data: list
    count: int = 0


class _GenericQuery:
    """Builder chainável: aceita qualquer método de filtro; eq() filtra de fato."""

    def __init__(self, rows: list[dict]):
        self._rows = rows
        self._filters: dict = {}

    def eq(self, col, value):
        self._filters[col] = value
        return self

    def __getattr__(self, _name):
        return lambda *_a, **_kw: self

    def execute(self):
        return _Result(data=[dict(r) for r in self._rows if all(r.get(c) == v for c, v in self._filters.items())])


class _SupabaseMock:
    def __init__(self, participantes: list[dict]):
        self._participantes = participantes

    def table(self, name: str):
        return _GenericQuery(self._participantes if name == "participantes" else [])


# ─── Personas ─────────────────────────────────────────────────────────────────


def _pessoa(access_profile: str | None, perfil_pop: str | None) -> dict:
    return {
        "id": "P1",
        "auth_user_id": "auth-1",
        "email": "p1@hsm.com",
        "nome_completo": "Pessoa Um",
        "cargo": None,
        "area": None,
        "setor": None,
        "role": None,
        "ativo": True,
        "is_externo": False,
        "is_super_admin": False,
        "access_profile": access_profile,
        "perfil_pop": perfil_pop,
        "data_cadastro": "2026-06-01",
    }


def _client_para(pessoa: dict) -> TestClient:
    app = FastAPI()
    for mod in (reunioes_router, notas_router, pendencias_router, comentarios_router):
        app.include_router(mod.router, prefix="/api")

    sb = _SupabaseMock(participantes=[pessoa])

    async def _fake_user() -> dict[str, Any]:
        return {"id": pessoa["auth_user_id"], "email": pessoa["email"], "metadata": {}}

    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_supabase_client] = lambda: sb
    return TestClient(app)


ENDPOINTS_REUNIOES = [
    ("GET", "/api/reunioes"),
    ("GET", "/api/reunioes/calendario"),
    ("GET", "/api/notas"),
    ("GET", "/api/pendencias"),
    ("GET", "/api/pendencias/stats"),
    ("GET", "/api/pendencias/A1/comentarios"),
]


# ─── Testes ───────────────────────────────────────────────────────────────────


class TestCoordenadorPopSoVePops:
    @pytest.mark.parametrize("method,path", ENDPOINTS_REUNIOES)
    def test_pop_only_recebe_403_no_contexto_reunioes(self, method, path):
        client = _client_para(_pessoa(access_profile=None, perfil_pop="coordenador"))
        r = client.request(method, path)
        assert r.status_code == 403, f"{method} {path} deveria ser 403 para quem só tem perfil POP"


class TestFacilitadorSeguePassando:
    @pytest.mark.parametrize("method,path", ENDPOINTS_REUNIOES)
    def test_facilitador_regular_nao_toma_403(self, method, path):
        client = _client_para(_pessoa(access_profile="regular", perfil_pop=None))
        r = client.request(method, path)
        assert r.status_code != 403, f"{method} {path} não deveria 403 para facilitador regular"

    def test_secretaria_segue_vendo_o_calendario(self):
        client = _client_para(_pessoa(access_profile="secretaria", perfil_pop=None))
        r = client.get("/api/reunioes/calendario")
        assert r.status_code != 403


class TestPessoaComOsDoisPapeisTransita:
    def test_nao_toma_403_no_contexto_reunioes(self):
        client = _client_para(_pessoa(access_profile="regular", perfil_pop="gerente"))
        r = client.get("/api/reunioes/calendario")
        assert r.status_code != 403
