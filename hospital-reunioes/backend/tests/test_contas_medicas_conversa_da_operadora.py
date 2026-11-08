"""A conversa da Operadora com o Auditor e o lote de propostas (issue #1490, PRD #1484, ADR 0081).

Quem tem "Regra contratual e tabelas" fala com o Auditor na Memória da
operadora. O texto vira um lote de propostas tipadas (Regra nova, Regra
alterada, parâmetro), cada uma com o motivo, os conflitos com as Regras que
existem e a Prova da regra. O "ok" aplica o lote numa versão nova só da
Memória; "corrige o item N" refaz só aquele item. A conversa fica guardada,
ligada à versão que gerou, e nunca entra no prompt do Passo A nem do Passo B.

Tudo pela rota de verdade, com o dublê do banco da carga da operadora e o
provedor da IA dublado no transporte HTTP (o adaptador roda inteiro). O
provedor responde pelo schema pedido.
"""

from __future__ import annotations

import json
import re
from typing import Any

import httpx2
import pytest
from anthropic_apoio import cliente_por_transporte, mensagem, nome_do_schema, nomear_schemas
from test_contas_medicas_memoria_tela import DIA_01_ANTES, DIA_01_DEPOIS, _importar, _versoes
from test_contas_medicas_operadoras import GESTAO
from test_contas_medicas_prova_da_regra import _linha_do_guia, _semear
from test_contas_medicas_regra_nova import _cliente as _cliente_da_memoria

from app.limiter import limiter
from app.routers import contas_medicas_conversa as conversa_router
from app.services.contas_medicas import ia


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


ROTA = "/api/contas-medicas/operadoras/ALFA/conversa"


def _cliente(pessoa: dict[str, Any], ligar: tuple[str, ...] = ()):
    """O app da Memória da operadora com a conversa."""
    cliente, banco = _cliente_da_memoria(pessoa, ligar=ligar)
    cliente.app.include_router(conversa_router.router, prefix="/api")
    return cliente, banco


DIA_03 = "Transferência de setor antes das 12h não gera diária extra no setor de origem."
DIA_02 = "Transferência de setor antes das 10h: gera ou não diária extra no setor de origem."
PEDIDO = "Na ALFA a transferência antes do meio-dia não gera diária extra, e a diária vence ao meio-dia."


def _proposta(**campos: Any) -> dict[str, Any]:
    """Um item no formato da IA: a regra nova da transferência, com o que o teste trocar."""
    return {
        "tipo": "REGRA_NOVA",
        "regra_codigo": "",
        "secao": "DIA",
        "texto": DIA_03,
        "tipo_regra": "CONTRATUAL",
        "origem": "PRÁTICA",
        "parametro": "",
        "valor_json": "",
        "motivo": "A transferência antes do meio-dia deixa de gerar diária extra na origem.",
        "conflitos": [],
        **campos,
    }


LOTE = {
    "resposta": "Entendi três mudanças. Confira a prova de cada regra e responda ok.",
    "propostas": [
        # ALFA-DIA-99 não existe: a IA inventou, e o lote não repassa.
        _proposta(
            conflitos=[
                {"codigo": "ALFA-DIA-02", "resolucao": "SUBSTITUIR"},
                {"codigo": "ALFA-DIA-99", "resolucao": "JUNTAR"},
            ]
        ),
        _proposta(
            tipo="REGRA_ALTERADA",
            regra_codigo="ALFA-DIA-01",
            texto=DIA_01_DEPOIS,
            motivo="A diária passa a vencer ao meio-dia.",
        ),
        _proposta(
            tipo="PARAMETRO",
            texto="",
            parametro="diaria.hora_vencimento",
            valor_json='"12:00"',
            motivo="O cabeçalho acompanha o vencimento novo.",
        ),
    ],
}


class _Provedor:
    """A Anthropic do teste: responde pelo schema pedido. O Passo B da prova
    responde pela Conta do pedido (o código do item dela na tabela CONTA)."""

    def __init__(self, nomes: dict[str, str]):
        self.nomes = nomes
        self.pedidos: list[tuple[str, str]] = []
        self.lote: dict = LOTE
        self.correcao: dict | None = None
        self.por_codigo: dict[str, list[dict]] = {}

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        corpo = json.loads(request.content)
        formato = nome_do_schema(self.nomes, corpo)
        texto = "\n".join(bloco["text"] for m in corpo["messages"] for bloco in m["content"])
        self.pedidos.append((formato, texto))
        if formato == "LinhasDaComparacao":
            codigo = re.search(r"\bM\d{3}\b", texto.split("CONTA\n", 1)[1]).group(0)
            resposta = {"linhas": self.por_codigo.get(codigo, []), "resumo": "Comparada."}
        elif formato == "ItemCorrigido":
            resposta = self.correcao
        else:
            resposta = self.lote
        return httpx2.Response(200, json=mensagem(json.dumps(resposta)))

    def da_prova(self) -> list[str]:
        return [texto for formato, texto in self.pedidos if formato == "LinhasDaComparacao"]


@pytest.fixture
def provedor(monkeypatch) -> _Provedor:
    duble = _Provedor(nomear_schemas(monkeypatch))
    monkeypatch.setattr(ia, "_cliente", lambda: cliente_por_transporte(duble))
    monkeypatch.setattr(ia, "_esperar", lambda _segundos: None)
    return duble


@pytest.fixture
def cenario(provedor):
    """A ALFA com a memória 1.0 e doze Contas concluídas para a prova."""
    cliente, banco = _cliente(GESTAO)
    _importar(cliente)
    _importar(cliente, "MEMORIA-BETA-v1.0.md")
    _semear(banco)
    return cliente, banco, provedor


def _item(corpo: dict, numero: int) -> dict:
    return next(i for i in corpo["lote"]["itens"] if i["numero"] == numero)


# ═══════════════════════════════════════════════════════════════════════════
# 1. O texto vira um lote com a proposta, os conflitos e a prova
# ═══════════════════════════════════════════════════════════════════════════


class TestOTextoViraLote:
    def test_enviar_um_texto_de_regra_devolve_o_lote_com_proposta_conflitos_e_prova(self, cenario):
        cliente, banco, provedor = cenario
        # A regra nova tira uma Linha Feito da c12.
        banco.tabelas["cm_guia_linha"] = [_linha_do_guia("c12", "M012", "2026-10-12", 2.0, estado="FEITO")]

        resposta = cliente.post(ROTA, json={"texto": PEDIDO})

        assert resposta.status_code == 200, resposta.text
        corpo = resposta.json()
        assert [(i["numero"], i["tipo"]) for i in corpo["lote"]["itens"]] == [
            (1, "REGRA_NOVA"),
            (2, "REGRA_ALTERADA"),
            (3, "PARAMETRO"),
        ]

        nova = _item(corpo, 1)
        assert nova["proposta"] == {"secao": "DIA", "texto": DIA_03, "tipo": "CONTRATUAL", "origem": "PRÁTICA"}
        assert nova["motivo"] == LOTE["propostas"][0]["motivo"]
        # O texto da regra em conflito vem da memória, e o ID inventado fica de fora.
        assert nova["conflitos"] == [{"codigo": "ALFA-DIA-02", "texto": DIA_02, "resolucao": "SUBSTITUIR"}]
        assert (nova["prova"]["contas"], nova["prova"]["mudaria"], nova["prova"]["feitas_que_sumiriam"]) == (
            10,
            True,
            1,
        )

        alterada = _item(corpo, 2)
        assert alterada["regra_codigo"] == "ALFA-DIA-01"
        assert (alterada["proposta"]["texto_anterior"], alterada["proposta"]["texto"]) == (DIA_01_ANTES, DIA_01_DEPOIS)
        assert alterada["prova"]["contas"] == 10

        parametro = _item(corpo, 3)
        assert parametro["proposta"] == {"chave": "diaria.hora_vencimento", "antes": "10:00", "depois": "12:00"}
        assert parametro["prova"] is None

        # As falas ficam na conversa; a Memória não muda antes do ok.
        assert [(m["autor"], m["texto"]) for m in corpo["mensagens"]] == [
            ("PESSOA", PEDIDO),
            ("AUDITOR", LOTE["resposta"]),
        ]
        assert _versoes(banco, "ALFA") == {"1.0": True}
        # Uma chamada da conversa e dez da prova por regra.
        assert sorted(c["passo"] for c in banco.linhas("cm_chamada_ia")) == ["CONVERSA"] + ["PROVA"] * 20

    def test_a_prova_da_regra_alterada_troca_o_texto_da_antiga_na_memoria_candidata(self, cenario):
        cliente, _banco, provedor = cenario
        provedor.lote = {**LOTE, "propostas": [LOTE["propostas"][1]]}

        assert cliente.post(ROTA, json={"texto": PEDIDO}).status_code == 200

        pedido = provedor.da_prova()[0]
        assert f"| ALFA-DIA-01 | {DIA_01_DEPOIS} |" in pedido
        assert DIA_01_ANTES not in pedido

    def test_a_ia_recebe_a_memoria_e_so_a_mensagem_desta_vez(self, cenario):
        cliente, _banco, provedor = cenario
        provedor.lote = {"resposta": "Entendi.", "propostas": []}
        cliente.post(ROTA, json={"texto": "Primeira mensagem, já passada."})

        cliente.post(ROTA, json={"texto": PEDIDO})

        _, pedido = [p for p in provedor.pedidos if p[0] == "LoteDoAuditor"][-1]
        assert f"| ALFA-DIA-01 | {DIA_01_ANTES} |" in pedido
        assert PEDIDO in pedido
        assert "Primeira mensagem" not in pedido
