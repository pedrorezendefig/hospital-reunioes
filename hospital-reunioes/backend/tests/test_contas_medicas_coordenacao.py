"""A Conferência da coordenação de Contas médicas (issue #1143, PRD #1129, adendo v1.1).

A gestão cadastra os cenários (o procedimento que dispara e os insumos a
conferir) escrevendo em linguagem comum: a IA preenche os campos e a pessoa
confere os códigos contra a tabela. O Passo C roda depois do Passo A: a IA diz
em que data e setor cada cenário ativo da operadora ocorreu, o código confere a
evidência e, quando falta insumo na conta, cria o lembrete com o valor pela
tabela. A coordenadora marca Incluído ou Não se aplica. A faturista não vê
cenário nem lembrete, e o guia, a nota e a produção dela não mudam.

Tudo pelo caminho de verdade, com os dublês do processamento (#1124): a rota de
envio, o job da fila, o adaptador de IA com o transporte HTTP trocado e as
rotas da tela. O provedor responde pelo schema pedido.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from openai import OpenAI
from test_contas_medicas_processamento import (
    PESSOAS,
    _Banco,
    _cenario,
    _Consulta,
    _Extrator,
    _OpenRouter,
    _pessoa,
)

from app.dependencies import get_current_user, get_supabase_client
from app.limiter import limiter
from app.routers import contas_medicas_coordenacao as coordenacao_router
from app.routers import contas_medicas_envio as envio_router
from app.routers import contas_medicas_guia as guia_router
from app.routers import contas_medicas_painel as painel_router
from app.services.contas_medicas import envio as envio_service
from app.services.contas_medicas import ia, processamento

ROTA = "/api/contas-medicas/coordenacao"

# O schema que o cadastro pede à IA.
PROPOSTA = "CenarioProposto"


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


@pytest.fixture(autouse=True)
def _extrator(monkeypatch) -> _Extrator:
    duble = _Extrator()
    monkeypatch.setattr(envio_service, "extrair_paginas", duble)
    monkeypatch.setattr(processamento, "extrair_paginas", duble)
    return duble


@pytest.fixture(autouse=True)
def openrouter(monkeypatch) -> _OpenRouter:
    """O provedor do teste na fronteira HTTP: nada chega ao OpenRouter."""
    duble = _OpenRouter()
    monkeypatch.setattr(
        ia,
        "_cliente",
        lambda: OpenAI(
            api_key="chave-de-teste",
            base_url="https://openrouter.ai/api/v1",
            http_client=httpx.Client(transport=httpx.MockTransport(duble)),
            max_retries=0,
        ),
    )
    monkeypatch.setattr(ia, "_esperar", lambda _segundos: None)
    return duble


# ═══════════════════════════════════════════════════════════════════════════
# O dublê do banco: o do processamento, com o recorte das leituras paginadas
# ═══════════════════════════════════════════════════════════════════════════


class _ConsultaComRecorte(_Consulta):
    def range(self, inicio, fim):
        self._recorte = (inicio, fim)
        return self

    def _executar(self):
        resposta = super()._executar()
        recorte = getattr(self, "_recorte", None)
        if recorte is not None:
            resposta.data = resposta.data[recorte[0] : recorte[1] + 1]
        return resposta


class _BancoDaCoordenacao(_Banco):
    def table(self, nome: str):
        return _ConsultaComRecorte(self, nome)


QUEM = {
    **PESSOAS,
    "coordenadora": _pessoa("CO", "coordenadora"),
    "diretoria": _pessoa("DM", "diretoria_medica"),
}


def _banco() -> _BancoDaCoordenacao:
    """O par sintético do processamento (operadora ALFA, agulha 70000001 na
    tabela de materiais e lançada na conta em 03/10), com a coordenadora e a
    diretoria."""
    banco = _BancoDaCoordenacao(_cenario().tabelas)
    banco.tabelas["participantes"] = list(QUEM.values())
    return banco


def _cliente(banco: _Banco, quem: str) -> TestClient:
    pessoa = QUEM[quem]
    app = FastAPI()
    app.state.limiter = limiter
    for router in (coordenacao_router, envio_router, guia_router, painel_router):
        app.include_router(router.router, prefix="/api")

    async def _usuario() -> dict[str, Any]:
        return {"id": pessoa["auth_user_id"], "email": pessoa["email"], "metadata": {}}

    app.dependency_overrides[get_current_user] = _usuario
    app.dependency_overrides[get_supabase_client] = lambda: banco
    return TestClient(app)


# ═══════════════════════════════════════════════════════════════════════════
# 1. O cadastro do cenário
# ═══════════════════════════════════════════════════════════════════════════

TEXTO_DO_CENARIO = (
    "Sondagem vesical ou cirurgia com lidocaína gel: conferir lidocaína gel, a agulha e o coletor de urina, um de cada."
)

PROPOSTA_DA_IA = {
    "nome": "Lidocaína gel em sondagem ou cirurgia",
    "operadora": None,
    "gatilho_texto": "Cateterismo vesical, ou cirurgia em que foi usada lidocaína gel",
    "orientacao": "Confira se a lidocaína gel e o coletor foram lançados no dia.",
    "insumos": [
        {"codigo": "70000001", "descricao": "AGULHA HIPODERMICA", "quantidade": 1},
        {"codigo": "79999999", "descricao": "COLETOR DE URINA", "quantidade": 1},
    ],
}


def _cenario_enviado(**campos: Any) -> dict[str, Any]:
    return {
        "nome": "Lidocaína gel em sondagem ou cirurgia",
        "operadora_sigla": None,
        "gatilho_texto": "Cateterismo vesical, ou cirurgia em que foi usada lidocaína gel",
        "orientacao": "Confira se a lidocaína gel e o coletor foram lançados no dia.",
        "ativo": True,
        "insumos": [
            {"codigo": "70000001", "descricao": "AGULHA HIPODERMICA", "quantidade": 1},
            {"codigo": "79999999", "descricao": "COLETOR DE URINA", "quantidade": 1},
        ],
        **campos,
    }


class TestCadastroDoCenario:
    def test_a_ia_preenche_os_campos_e_o_codigo_que_nao_esta_na_tabela_e_apontado(self, openrouter):
        openrouter.respostas[PROPOSTA] = PROPOSTA_DA_IA
        banco = _banco()

        resposta = _cliente(banco, "gestao").post(f"{ROTA}/cenarios/proposta", json={"texto": TEXTO_DO_CENARIO})

        assert resposta.status_code == 200, resposta.text
        corpo = resposta.json()
        assert corpo["campos"]["nome"] == "Lidocaína gel em sondagem ou cirurgia"
        assert corpo["campos"]["gatilho_texto"] == "Cateterismo vesical, ou cirurgia em que foi usada lidocaína gel"
        assert [(i["codigo"], i["na_tabela"]) for i in corpo["campos"]["insumos"]] == [
            ("70000001", True),
            ("79999999", False),
        ]
        assert corpo["codigos_fora_da_tabela"] == ["79999999"]
        # O texto da pessoa foi para a IA; nada foi gravado antes de ela conferir.
        (pedido,) = [c for c in openrouter.corpos if c["response_format"]["json_schema"]["name"] == PROPOSTA]
        assert TEXTO_DO_CENARIO in json.dumps(pedido["messages"], ensure_ascii=False)
        assert banco.tabelas.get("cm_cenario", []) == []

    def test_salvar_cria_o_cen_001_com_os_insumos_e_o_autor_e_aponta_o_codigo_fora_da_tabela(self):
        banco = _banco()

        resposta = _cliente(banco, "gestao").post(f"{ROTA}/cenarios", json=_cenario_enviado())

        assert resposta.status_code == 201, resposta.text
        assert resposta.json()["codigos_fora_da_tabela"] == ["79999999"]
        (cenario,) = banco.tabelas["cm_cenario"]
        assert (cenario["codigo"], cenario["autor_id"], cenario["ativo"], cenario["operadora_id"]) == (
            "CEN-001",
            "G1",
            True,
            None,
        )
        insumos = sorted((i["codigo"], i["quantidade"]) for i in banco.tabelas["cm_cenario_item"])
        assert insumos == [("70000001", 1), ("79999999", 1)]
        # A criação fica no registro, com quem e quando.
        (registro,) = [r for r in banco.tabelas["cm_registro"] if r["entidade"] == "cm_cenario"]
        assert (registro["autor_id"], registro["entidade_id"], registro["antes_json"]) == ("G1", cenario["id"], None)

        # O segundo é o CEN-002, na lista de quem cadastra.
        _cliente(banco, "gestao").post(f"{ROTA}/cenarios", json=_cenario_enviado(nome="Outro cenário"))
        lista = _cliente(banco, "gestao").get(f"{ROTA}/cenarios").json()["cenarios"]
        assert [c["codigo"] for c in lista] == ["CEN-001", "CEN-002"]

    @pytest.mark.parametrize("quem", ["coordenadora", "faturista"])
    def test_sem_incluir_regra_operacional_nao_cadastra_nem_pede_a_ia(self, quem, openrouter):
        openrouter.respostas[PROPOSTA] = PROPOSTA_DA_IA
        banco = _banco()
        cliente = _cliente(banco, quem)

        assert cliente.post(f"{ROTA}/cenarios", json=_cenario_enviado()).status_code == 403
        assert cliente.post(f"{ROTA}/cenarios/proposta", json={"texto": TEXTO_DO_CENARIO}).status_code == 403
        assert banco.tabelas.get("cm_cenario", []) == []
        assert openrouter.requisicoes == 0


KIT = Path(__file__).resolve().parents[1] / "app" / "conhecimento" / "contas-medicas.md"
