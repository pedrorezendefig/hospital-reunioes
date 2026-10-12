"""A fundacao do modulo Contas medicas (issue #1114, PRD #1113, ADR 0070).

O eixo de permissao proprio (`perfil_contas_medicas`, ADR 0070 decisao 10), a
matriz perfil x permissao que a migration 116 carrega e a rota que diz a
pessoa o que ela pode fazer no modulo.

A matriz do dublê do banco e lida da PROPRIA migration, nao decorada aqui: o
que o teste confere e o que o Studio vai gravar. O esperado de cada perfil, ao
contrario, e escrito a mao a partir da spec do diretor (secao 3 e adendo
v1.1), para o teste poder discordar da migration.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.dependencies import get_current_user, get_supabase_client  # noqa: E402
from app.limiter import limiter  # noqa: E402
from app.routers import contas_medicas as contas_medicas_router  # noqa: E402

MIGRATION = Path(__file__).resolve().parents[2] / "supabase" / "migrations" / "116_contas_medicas_fundacao.sql"

ROTA_ME = "/api/contas-medicas/me"


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


def _matriz_da_migration() -> list[dict[str, Any]]:
    """As linhas do INSERT em `cm_perfil_permissao`, como o banco as tera."""
    sql = MIGRATION.read_text(encoding="utf-8")
    bloco = re.search(r"INSERT INTO cm_perfil_permissao\s*\([^)]*\)\s*VALUES(.*?);", sql, flags=re.DOTALL)
    assert bloco, "a migration 116 nao carrega a matriz"
    linhas = re.findall(r"\(\s*'(\w+)'\s*,\s*'(\w+)'\s*,\s*(true|false)\s*\)", bloco.group(1))
    return [{"perfil": p, "permissao": k, "ligada": v == "true"} for p, k, v in linhas]


class _Consulta:
    def __init__(self, linhas: list[dict]):
        self._linhas = linhas
        self._eq: dict[str, Any] = {}

    def select(self, *_a, **_kw):
        return self

    def eq(self, coluna, valor):
        self._eq[coluna] = valor
        return self

    def execute(self):
        casam = [dict(linha) for linha in self._linhas if all(linha.get(c) == v for c, v in self._eq.items())]
        return SimpleNamespace(data=casam)


class _Banco:
    def __init__(self, tabelas: dict[str, list[dict]]):
        self.tabelas = tabelas

    def table(self, nome: str):
        return _Consulta(self.tabelas.setdefault(nome, []))


def _pessoa(**campos) -> dict[str, Any]:
    base = {
        "id": "P1",
        "auth_user_id": "auth-p1",
        "nome_completo": "Pessoa de Teste",
        "email": "p1@hsm.test",
        "cargo": None,
        "area": None,
        "setor": None,
        "role": None,
        "ativo": True,
        "is_externo": False,
        "is_super_admin": False,
        "access_profile": None,
        "perfil_pop": None,
        "perfil_ouvidoria": None,
        "perfil_contas_medicas": None,
        "github_login": None,
        "data_cadastro": "2026-01-01",
    }
    return {**base, **campos}


def _cliente(pessoa: dict[str, Any], app: FastAPI | None = None) -> TestClient:
    app = app or FastAPI()
    app.state.limiter = limiter
    app.include_router(contas_medicas_router.router, prefix="/api")
    banco = _Banco({"participantes": [pessoa], "cm_perfil_permissao": _matriz_da_migration()})

    async def _usuario() -> dict[str, Any]:
        return {"id": pessoa["auth_user_id"], "email": pessoa["email"], "metadata": {}}

    app.dependency_overrides[get_current_user] = _usuario
    app.dependency_overrides[get_supabase_client] = lambda: banco
    return TestClient(app)


# ═══════════════════════════════════════════════════════════════════════════
# 1. GET /api/contas-medicas/me
# ═══════════════════════════════════════════════════════════════════════════


class TestQuemTemOEixo:
    def test_a_faturista_recebe_o_perfil_e_as_permissoes_ligadas(self):
        resposta = _cliente(_pessoa(perfil_contas_medicas="faturista")).get(ROTA_ME)

        assert resposta.status_code == 200
        assert resposta.json() == {"perfil": "faturista", "permissoes": ["enviar_corrigir_contas"]}
