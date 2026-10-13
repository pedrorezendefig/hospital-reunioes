"""Ensinar uma regra nova na Memória da operadora (issue #1141, PRD #1129, ADR 0070).

A pessoa escreve a regra em linguagem comum; a IA propõe a regra no formato da
memória, o parâmetro do cabeçalho que muda, as regras com que ela conflita e o
efeito no Guia. Nada é gravado até o "Validar regra", que cria uma versão nova
da memória como a edição pela tela faz. As contas A fazer e Em correção da
operadora analisadas com a versão anterior ganham a marca "regra nova desde a
análise" e o botão "Reanalisar com a regra nova".

Tudo pela rota de verdade, com o dublê do banco da carga da operadora e o
provedor da IA dublado no transporte HTTP (o adaptador roda inteiro).
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
from test_contas_medicas_memoria_tela import _importar, _operadora_id, _versao, _versoes
from test_contas_medicas_operadoras import GESTAO, _Banco, _matriz_da_migration, _pessoa

from app.dependencies import get_current_user, get_supabase_client
from app.limiter import limiter
from app.routers import contas_medicas_guia as guia_router
from app.routers import contas_medicas_memoria as memoria_router
from app.routers import contas_medicas_operadoras as operadoras_router
from app.services.contas_medicas import ia
from app.services.contas_medicas.memoria import ler_memoria
from app.services.contas_medicas.operadoras import memoria_vigente


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


DIA_03 = "Transferência de setor antes das 12h não gera diária extra no setor de origem."

PROPOSTA_DA_IA = {
    "regra": {"secao": "DIA", "texto": DIA_03, "tipo": "CONTRATUAL", "origem": "PRÁTICA"},
    "parametro": {"chave": "diaria.hora_vencimento", "valor_json": '"12:00"'},
    # ALFA-DIA-99 não existe: a IA inventou, e a rota não repassa.
    "conflitos": ["ALFA-DIA-01", "ALFA-DIA-99"],
    "efeito_no_guia": "A diária do dia da transferência deixa de ser cobrada no setor de origem.",
}


class _Provedor:
    """O OpenRouter do teste: guarda o corpo de cada requisição e devolve a proposta."""

    def __init__(self):
        self.corpos: list[dict] = []
        self.resposta: dict = PROPOSTA_DA_IA

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.corpos.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "id": "gen-1",
                "object": "chat.completion",
                "created": 1,
                "model": self.corpos[-1]["model"],
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": json.dumps(self.resposta)},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 900, "completion_tokens": 120, "total_tokens": 1020, "cost": 0.004},
            },
        )


@pytest.fixture
def provedor(monkeypatch) -> _Provedor:
    duble = _Provedor()

    def cliente():
        return OpenAI(
            api_key="chave-de-teste",
            base_url="https://openrouter.ai/api/v1",
            http_client=httpx.Client(transport=httpx.MockTransport(duble)),
            max_retries=0,
        )

    monkeypatch.setattr(ia, "_cliente", cliente)
    monkeypatch.setattr(ia, "_esperar", lambda _segundos: None)
    return duble


def _cliente(
    pessoa: dict[str, Any], banco: _Banco | None = None, ligar: tuple[str, ...] = ()
) -> tuple[TestClient, _Banco]:
    """O app com a carga, a Memória por tela e o Guia. `ligar` liga permissões
    no perfil da pessoa, como a Habilitação faria."""
    banco = banco or _Banco()
    banco.tabelas["participantes"] = [pessoa]
    matriz = _matriz_da_migration()
    for linha in matriz:
        if linha["perfil"] == pessoa["perfil_contas_medicas"] and linha["permissao"] in ligar:
            linha["ligada"] = True
    banco.tabelas["cm_perfil_permissao"] = matriz
    app = FastAPI()
    app.state.limiter = limiter
    app.include_router(operadoras_router.router, prefix="/api")
    app.include_router(memoria_router.router, prefix="/api")
    app.include_router(guia_router.router, prefix="/api")

    async def _usuario() -> dict[str, Any]:
        return {"id": pessoa["auth_user_id"], "email": pessoa["email"], "metadata": {}}

    app.dependency_overrides[get_current_user] = _usuario
    app.dependency_overrides[get_supabase_client] = lambda: banco
    return TestClient(app), banco


def _proposta(sigla: str) -> str:
    return f"/api/contas-medicas/operadoras/{sigla}/regras/proposta"


def _validar(sigla: str) -> str:
    return f"/api/contas-medicas/operadoras/{sigla}/regras"


# ═══════════════════════════════════════════════════════════════════════════
# 1. A proposta da IA
# ═══════════════════════════════════════════════════════════════════════════


class TestPropostaDaIa:
    def test_a_proposta_traz_os_quatro_blocos_e_nao_grava_nada(self, provedor):
        cliente, banco = _cliente(GESTAO)
        _importar(cliente)
        regras_antes = len(banco.linhas("cm_regra"))

        resposta = cliente.post(
            _proposta("ALFA"), json={"texto": "Na ALFA a transferência antes do meio-dia não gera diária extra."}
        )

        assert resposta.status_code == 200, resposta.text
        corpo = resposta.json()
        assert corpo["regra"] == {"secao": "DIA", "texto": DIA_03, "tipo": "CONTRATUAL", "origem": "PRÁTICA"}
        # O antes vem da memória vigente, não da IA.
        assert corpo["parametro"] == {"chave": "diaria.hora_vencimento", "antes": "10:00", "depois": "12:00"}
        assert corpo["conflitos"] == [
            {"codigo": "ALFA-DIA-01", "texto": "A diária começa em qualquer horário, vence às 10h e é sempre integral."}
        ]
        assert corpo["efeito_no_guia"] == PROPOSTA_DA_IA["efeito_no_guia"]

        # Nada gravado antes do Validar.
        assert _versoes(banco, "ALFA") == {"1.0": True}
        assert len(banco.linhas("cm_regra")) == regras_antes
        assert banco.linhas("cm_regra_historico") == []

        # A IA recebeu o texto da pessoa e a memória vigente.
        [corpo_da_ia] = provedor.corpos
        conteudo = json.dumps(corpo_da_ia["messages"], ensure_ascii=False)
        assert "transferência antes do meio-dia" in conteudo
        assert "ALFA-DIA-01" in conteudo
        assert corpo_da_ia["response_format"]["json_schema"]["strict"] is True


# ═══════════════════════════════════════════════════════════════════════════
# 2. Validar regra
# ═══════════════════════════════════════════════════════════════════════════

REGRA_VALIDADA = {
    "secao": "DIA",
    # A pessoa editou o texto que a IA propôs.
    "texto": "Transferência de setor antes das 12h não gera diária extra na origem.",
    "tipo": "CONTRATUAL",
    "origem": "PRÁTICA",
    "parametro": {"chave": "diaria.hora_vencimento", "valor": "12:00"},
}


def _regra_da_versao(banco: _Banco, versao: dict, codigo: str) -> dict:
    return next(r for r in banco.linhas("cm_regra") if r["memoria_versao_id"] == versao["id"] and r["codigo"] == codigo)


class TestValidarRegra:
    def test_validar_cria_versao_nova_com_a_regra_o_historico_e_o_parametro(self):
        cliente, banco = _cliente(GESTAO)
        _importar(cliente)

        resposta = cliente.post(_validar("ALFA"), json=REGRA_VALIDADA)

        assert resposta.status_code == 200, resposta.text
        assert (resposta.json()["versao"], resposta.json()["regra"]) == ("1.1", "ALFA-DIA-03")
        assert _versoes(banco, "ALFA") == {"1.0": False, "1.1": True}
        nova = _versao(banco, "ALFA", "1.1")
        assert nova["autor_id"] == "P1"

        # O parâmetro mudou no cabeçalho da versão nova; o resto ficou, e a anterior não mudou.
        assert nova["parametros_json"]["diaria"]["hora_vencimento"] == "12:00"
        assert nova["parametros_json"]["diaria"]["limite_madrugada"] == "05:00"
        assert nova["parametros_json"]["opme"]["fornecida_por"] == "OPERADORA"
        assert _versao(banco, "ALFA", "1.0")["parametros_json"]["diaria"]["hora_vencimento"] == "10:00"

        # A regra entra vigente, com quem validou e a data, ao lado das cinco que já estavam.
        assert len(memoria_vigente(banco, _operadora_id(banco, "ALFA"))["regras"]) == 6
        regra = _regra_da_versao(banco, nova, "ALFA-DIA-03")
        assert (regra["texto"], regra["secao"], regra["tipo"], regra["origem"], regra["status"]) == (
            REGRA_VALIDADA["texto"],
            "DIA",
            "CONTRATUAL",
            "PRÁTICA",
            "VIGENTE",
        )
        assert regra["validado_por"] == "P1"
        assert regra["validado_em"]

        # O histórico guarda a regra nova, sem texto anterior.
        [historico] = banco.linhas("cm_regra_historico")
        assert (historico["regra_id"], historico["texto_anterior"], historico["texto_novo"]) == (
            regra["id"],
            None,
            REGRA_VALIDADA["texto"],
        )

        # O texto da versão nova, gerado do banco, já tem a regra e o parâmetro.
        lida = ler_memoria(nova["texto_md"])
        assert "ALFA-DIA-03" in {r.codigo for r in lida.regras}
        assert lida.parametros["diaria"]["hora_vencimento"] == "12:00"

    def test_sem_parametro_o_cabecalho_fica_como_estava(self):
        cliente, banco = _cliente(GESTAO)
        _importar(cliente)

        resposta = cliente.post(_validar("ALFA"), json={**REGRA_VALIDADA, "parametro": None})

        assert resposta.status_code == 200, resposta.text
        assert _versao(banco, "ALFA", "1.1")["parametros_json"]["diaria"]["hora_vencimento"] == "10:00"

    def test_permissao_segue_o_tipo_da_regra_e_a_recusa_nao_grava_nada(self):
        """Só a operacional ligada: 403 na regra contratual e na operacional que
        mexe em parâmetro do cabeçalho; a operacional sem parâmetro entra. Só a
        contratual: 403 na operacional."""
        banco = _Banco()
        gestao, _ = _cliente(GESTAO, banco)
        _importar(gestao)
        coordenadora, _ = _cliente(
            _pessoa(perfil_contas_medicas="coordenadora"), banco, ligar=("incluir_regra_operacional",)
        )
        operacional = {**REGRA_VALIDADA, "secao": "PRI", "tipo": "OPERACIONAL", "parametro": None}

        contratual = coordenadora.post(_validar("ALFA"), json=REGRA_VALIDADA)
        com_parametro = coordenadora.post(
            _validar("ALFA"), json={**operacional, "parametro": REGRA_VALIDADA["parametro"]}
        )

        assert (contratual.status_code, com_parametro.status_code) == (403, 403)
        assert _versoes(banco, "ALFA") == {"1.0": True}
        assert banco.linhas("cm_regra_historico") == []

        resposta = coordenadora.post(_validar("ALFA"), json=operacional)
        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["regra"] == "ALFA-PRI-04"

        so_contratual, _ = _cliente(
            _pessoa(perfil_contas_medicas="credenciamento"), banco, ligar=("regra_contratual_tabelas",)
        )
        assert so_contratual.post(_validar("ALFA"), json=operacional).status_code == 403
        assert _versoes(banco, "ALFA") == {"1.0": False, "1.1": True}

    def test_regra_com_cpf_ou_chave_protegida_e_recusada(self):
        cliente, banco = _cliente(GESTAO)
        _importar(cliente)

        com_cpf = cliente.post(_validar("ALFA"), json={**REGRA_VALIDADA, "texto": "Paciente 123.456.789-09 paga."})
        protegida = cliente.post(
            _validar("ALFA"), json={**REGRA_VALIDADA, "parametro": {"chave": "versao_memoria", "valor": "9.9"}}
        )

        assert (com_cpf.status_code, protegida.status_code) == (409, 409)
        assert _versoes(banco, "ALFA") == {"1.0": True}
