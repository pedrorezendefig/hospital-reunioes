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
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.dependencies import get_current_user, get_supabase_client, require_permissao_cm  # noqa: E402
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


class TestQuemNaoTemOEixo:
    def test_sem_perfil_de_contas_medicas_recebe_403(self):
        """Mutante: tirar o gate da rota. Quem e so de Reunioes receberia 200."""
        pessoa = _pessoa(access_profile="regular", perfil_ouvidoria="ouvidor")

        assert _cliente(pessoa).get(ROTA_ME).status_code == 403

    def test_pessoa_desligada_recebe_403_mesmo_com_o_perfil(self):
        pessoa = _pessoa(perfil_contas_medicas="diretoria_medica", ativo=False)

        assert _cliente(pessoa).get(ROTA_ME).status_code == 403


# ═══════════════════════════════════════════════════════════════════════════
# 2. A matriz inicial bate com a spec
# ═══════════════════════════════════════════════════════════════════════════

TODAS = (
    "enviar_corrigir_contas",
    "decidir_validacao",
    "incluir_regra_operacional",
    "regra_contratual_tabelas",
    "contratos_avisos",
    "painel_completo",
    "habilitar_pessoas",
    "conferencia_coordenacao",
)

# Escrito a mao a partir da spec (secao 3) e do adendo v1.1, e nao derivado da
# migration: e a fonte independente que pode discordar dela.
ESPERADO_POR_PERFIL = {
    "faturista": ["enviar_corrigir_contas"],
    "coordenadora": ["enviar_corrigir_contas", "painel_completo", "conferencia_coordenacao"],
    "gestao_contas_medicas": [p for p in TODAS if p != "habilitar_pessoas"],
    "diretoria_medica": list(TODAS),
    "diretoria_executiva": list(TODAS),
    "credenciamento": ["contratos_avisos"],
}


class TestSuperAdminPassa:
    def test_super_admin_sem_perfil_passa_com_as_oito_permissoes(self):
        """Super admin do app passa, como nos outros modulos (ADR 0070)."""
        resposta = _cliente(_pessoa(access_profile="super_admin", is_super_admin=True)).get(ROTA_ME)

        assert resposta.status_code == 200
        assert resposta.json() == {"perfil": None, "permissoes": list(TODAS)}


class TestMatrizInicial:
    @pytest.mark.parametrize("perfil", sorted(ESPERADO_POR_PERFIL))
    def test_a_rota_devolve_as_permissoes_do_perfil_na_carga_da_migration(self, perfil):
        """Mutante: ligar "incluir regra operacional" para a coordenadora na
        migration. A rota passa a devolve-la e o teste do perfil fica vermelho."""
        resposta = _cliente(_pessoa(perfil_contas_medicas=perfil)).get(ROTA_ME)

        assert resposta.status_code == 200
        assert resposta.json() == {"perfil": perfil, "permissoes": ESPERADO_POR_PERFIL[perfil]}

    def test_a_carga_tem_as_oito_permissoes_de_cada_um_dos_seis_perfis(self):
        """Toda combinacao existe, ligada ou nao: a Habilitacao liga e desliga
        linha que ja esta la. Tambem e o piso do leitor do INSERT: se a regex
        parar de casar, a matriz volta vazia e os testes acima mentem."""
        matriz = _matriz_da_migration()
        pares = {(linha["perfil"], linha["permissao"]) for linha in matriz}

        assert len(matriz) == 48
        assert pares == {(perfil, p) for perfil in ESPERADO_POR_PERFIL for p in TODAS}


# ═══════════════════════════════════════════════════════════════════════════
# 3. O guard por permissao
# ═══════════════════════════════════════════════════════════════════════════


def _cliente_com_sonda(pessoa: dict[str, Any], permissao: str) -> TestClient:
    """Uma rota de mentira atras de `require_permissao_cm(permissao)`: as rotas
    de verdade que usam cada permissao chegam nas fatias seguintes."""
    app = FastAPI()

    @app.get("/sonda")
    async def _sonda(me: dict = Depends(require_permissao_cm(permissao))) -> dict:
        return {"id": me["id"]}

    return _cliente(pessoa, app)


class TestGuardPorPermissao:
    def test_quem_tem_a_permissao_ligada_passa(self):
        pessoa = _pessoa(perfil_contas_medicas="coordenadora")

        assert _cliente_com_sonda(pessoa, "painel_completo").get("/sonda").status_code == 200

    def test_quem_tem_o_eixo_sem_a_permissao_recebe_403(self):
        """Mutante: o guard conferir so o eixo e ignorar a matriz."""
        pessoa = _pessoa(perfil_contas_medicas="faturista")

        assert _cliente_com_sonda(pessoa, "painel_completo").get("/sonda").status_code == 403

    def test_permissao_desligada_na_matriz_recusa(self):
        pessoa = _pessoa(perfil_contas_medicas="coordenadora")

        assert _cliente_com_sonda(pessoa, "incluir_regra_operacional").get("/sonda").status_code == 403

    def test_super_admin_passa_em_qualquer_permissao(self):
        pessoa = _pessoa(access_profile="super_admin", is_super_admin=True)

        assert _cliente_com_sonda(pessoa, "habilitar_pessoas").get("/sonda").status_code == 200

    def test_permissao_escrita_errada_quebra_na_montagem_e_nao_em_producao(self):
        with pytest.raises(ValueError):
            require_permissao_cm("painel")


class TestARotaEstaNoApp:
    def test_o_app_de_verdade_registra_a_rota(self):
        """O router tem `include_router` proprio no `main.py`. A fonte e o
        schema OpenAPI, e nao `app.routes` (FastAPI 0.141, issues #542 e #546)."""
        from app.main import app

        cache = app.openapi_schema
        try:
            caminhos = app.openapi()["paths"]
        finally:
            app.openapi_schema = cache

        assert len(caminhos) > 50
        assert "get" in caminhos[ROTA_ME]
