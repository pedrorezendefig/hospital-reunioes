"""Para onde sai a IA de texto de Atas, POP, Ouvidoria e Assistente de
Tecnologia (issue #1302, revisão do PR #1313).

Os testes dessas portas trocam `_llm_provider` e `_get_llm` inteiros, então
nenhum deles diria se o cliente voltasse para o OpenRouter ou passasse a ler a
chave do OpenRouter. Aqui o `_get_llm()` é o de verdade: só o transporte HTTP
do SDK é trocado (`httpx2.MockTransport`), e o teste lê o pedido que sairia.
Nenhum chega à rede (a trava da suíte, `conftest.py`, reprova quem tentar).
"""

from __future__ import annotations

import os
import sys

import anthropic
import httpx2
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from anthropic_apoio import mensagem  # noqa: E402

from app.config import settings  # noqa: E402
from app.services import ai_processor  # noqa: E402

CHAVE_DA_ANTHROPIC = "sk-ant-plantada-no-teste"
CHAVE_DO_OPENROUTER = "sk-or-plantada-no-teste"


@pytest.fixture
def chaves(monkeypatch):
    """As duas chaves plantadas, cada uma com um valor que se distingue da
    outra, e sem `ANTHROPIC_BASE_URL` do ambiente desviando o SDK."""
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    monkeypatch.setattr(settings, "anthropic_api_key", CHAVE_DA_ANTHROPIC)
    monkeypatch.setattr(settings, "openrouter_api_key", CHAVE_DO_OPENROUTER)


def _trocar_transporte(monkeypatch) -> list[httpx2.Request]:
    """Faz todo `anthropic.Anthropic(...)` construído durante o teste usar o
    transporte de mentira, mantendo os argumentos que o `_get_llm` passou."""
    pedidos: list[httpx2.Request] = []

    def duble(pedido: httpx2.Request) -> httpx2.Response:
        pedidos.append(pedido)
        return httpx2.Response(200, json=mensagem("resposta"))

    original = anthropic.Anthropic

    def construir(**kwargs):
        transporte = anthropic.DefaultHttpxClient(transport=httpx2.MockTransport(duble))
        return original(**kwargs, http_client=transporte, max_retries=0)

    monkeypatch.setattr(anthropic, "Anthropic", construir)
    return pedidos


class TestGetLlm:
    def test_a_chamada_sai_para_a_api_da_anthropic_com_a_chave_da_anthropic(self, chaves, monkeypatch):
        pedidos = _trocar_transporte(monkeypatch)

        client, model = ai_processor._get_llm()
        texto = ai_processor._pedir_texto(client, model, system="instrucao", conteudo="oi")

        assert texto == "resposta"
        assert len(pedidos) == 1
        assert str(pedidos[0].url) == "https://api.anthropic.com/v1/messages"
        # O SDK manda a chave em `x-api-key` ou, nas versões novas, como
        # `Authorization: Bearer`; o que importa é que seja a da Anthropic.
        cabecalhos = pedidos[0].headers
        credencial = cabecalhos.get("x-api-key") or cabecalhos.get("authorization", "").removeprefix("Bearer ")
        assert credencial == CHAVE_DA_ANTHROPIC
        assert model == settings.llm_model


class TestLlmProvider:
    def test_so_a_chave_da_anthropic_liga_a_ia(self, monkeypatch):
        monkeypatch.setattr(settings, "anthropic_api_key", CHAVE_DA_ANTHROPIC)
        monkeypatch.setattr(settings, "openrouter_api_key", "")
        assert ai_processor._llm_provider() == "anthropic"

    def test_so_a_chave_do_openrouter_fica_no_mock(self, monkeypatch):
        monkeypatch.setattr(settings, "anthropic_api_key", "")
        monkeypatch.setattr(settings, "openrouter_api_key", CHAVE_DO_OPENROUTER)
        assert ai_processor._llm_provider() == "mock"

    def test_sem_chave_nenhuma_fica_no_mock(self, monkeypatch):
        monkeypatch.setattr(settings, "anthropic_api_key", "")
        monkeypatch.setattr(settings, "openrouter_api_key", "")
        assert ai_processor._llm_provider() == "mock"
