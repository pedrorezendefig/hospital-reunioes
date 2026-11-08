"""Revisar as Regras pendentes de uma Operadora em lote (issue #1494, PRD #1484, ADR 0081, decisão 6).

Na conversa da Operadora, "revisar pendentes" monta um lote com todas as
Regras pendentes dela, cada uma com a decisão que o Auditor sugere (validar,
alterar ou descartar) e a Prova da regra. O "ok" aplica o lote numa versão
nova da Memória e fecha os Temas de validação dessas Regras, com as Linhas
afetadas seguindo o caminho de hoje da Validação.

Tudo pela rota de verdade, com o dublê do banco da carga da operadora e o
provedor da IA dublado no transporte HTTP.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import httpx2
import pytest
from anthropic_apoio import cliente_por_transporte, mensagem, nome_do_schema, nomear_schemas
from test_contas_medicas_conversa_da_operadora import ROTA, _cliente, _regras_vigentes, _vigente
from test_contas_medicas_memoria_tela import _importar, _versoes
from test_contas_medicas_operadoras import GESTAO
from test_contas_medicas_prova_da_regra import _linha_do_guia, _semear

from app.limiter import limiter
from app.services.contas_medicas import ia


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


# As pendentes da ALFA na memória 1.0 da fixture.
DIA_02 = "Transferência de setor antes das 10h: gera ou não diária extra no setor de origem."
PRI_03 = "Edição do Brasíndice usada pela operadora."
DIA_02_ALTERADA = "Transferência de setor antes das 10h não gera diária extra no setor de origem."


def _decisao(codigo: str, decisao: str, texto: str = "", motivo: str = "") -> dict[str, Any]:
    return {"regra_codigo": codigo, "decisao": decisao, "texto": texto, "motivo": motivo or f"Motivo de {codigo}."}


REVISAO = {
    "resposta": "Revisei as duas pendentes da ALFA. Confira e responda ok.",
    "decisoes": [
        _decisao("ALFA-DIA-02", "ALTERAR", DIA_02_ALTERADA, "A prática da casa já não cobra a diária extra."),
        _decisao("ALFA-PRI-03", "DESCARTAR", motivo="A regra não diz qual edição: não serve para conferir."),
        # A pendente de outra Operadora não entra no lote da ALFA.
        _decisao("BETA-INS-02", "VALIDAR"),
    ],
}


class _Provedor:
    """A Anthropic do teste: responde pelo schema pedido."""

    def __init__(self, nomes: dict[str, str]):
        self.nomes = nomes
        self.pedidos: list[tuple[str, str]] = []
        self.revisao: dict = REVISAO
        self.correcao: dict | None = None

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        corpo = json.loads(request.content)
        formato = nome_do_schema(self.nomes, corpo)
        texto = "\n".join(bloco["text"] for m in corpo["messages"] for bloco in m["content"])
        self.pedidos.append((formato, texto))
        if formato == "LinhasDaComparacao":
            resposta = {"linhas": [], "resumo": "Comparada."}
        elif formato == "PendenteCorrigida":
            resposta = self.correcao
        else:
            resposta = self.revisao
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
    """A ALFA (pendentes DIA-02 e PRI-03) e a BETA (pendente INS-02), com as
    Contas concluídas da ALFA para a prova."""
    cliente, banco = _cliente(GESTAO)
    _importar(cliente)
    _importar(cliente, "MEMORIA-BETA-v1.0.md")
    _semear(banco)
    return cliente, banco, provedor


def _item(corpo: dict, numero: int) -> dict:
    return next(i for i in corpo["lote"]["itens"] if i["numero"] == numero)


# ═══════════════════════════════════════════════════════════════════════════
# 1. O lote traz todas as Regras pendentes da Operadora, e só dela
# ═══════════════════════════════════════════════════════════════════════════


class TestOLoteDasPendentes:
    def test_revisar_pendentes_traz_todas_as_pendentes_da_operadora_e_so_dela(self, cenario):
        cliente, banco, provedor = cenario
        # O Auditor esqueceu a PRI-03: ela entra assim mesmo, para validar como está.
        provedor.revisao = {**REVISAO, "decisoes": [REVISAO["decisoes"][0], REVISAO["decisoes"][2]]}

        resposta = cliente.post(ROTA, json={"texto": "Revisar pendentes"})

        assert resposta.status_code == 200, resposta.text
        corpo = resposta.json()
        assert [(i["numero"], i["regra_codigo"], i["proposta"]["decisao"]) for i in corpo["lote"]["itens"]] == [
            (1, "ALFA-DIA-02", "ALTERAR"),
            (2, "ALFA-PRI-03", "VALIDAR"),
        ]
        alterada = _item(corpo, 1)
        assert (alterada["proposta"]["texto_anterior"], alterada["proposta"]["texto"]) == (DIA_02, DIA_02_ALTERADA)
        assert alterada["motivo"] == "A prática da casa já não cobra a diária extra."
        validada = _item(corpo, 2)
        assert (validada["proposta"]["texto_anterior"], validada["proposta"]["texto"]) == (PRI_03, PRI_03)
        # Cada item com a Prova da regra nas 10 últimas concluídas.
        assert [i["prova"]["contas"] for i in corpo["lote"]["itens"]] == [10, 10]
        # O Auditor recebeu as pendentes da ALFA, e não a vigente nem a da BETA.
        (_, pedido), *_ = [p for p in provedor.pedidos if p[0] == "RevisaoDasPendentes"]
        pendentes = pedido.split("REGRAS PENDENTES\n", 1)[1]
        assert "ALFA-DIA-02" in pendentes and "ALFA-PRI-03" in pendentes
        assert "ALFA-DIA-01" not in pendentes and "BETA-INS-02" not in pendentes
        # Nada muda na Memória antes do ok.
        assert _versoes(banco, "ALFA") == {"1.0": True}
        assert [(m["autor"], m["texto"]) for m in corpo["mensagens"]] == [
            ("PESSOA", "Revisar pendentes"),
            ("AUDITOR", REVISAO["resposta"]),
        ]
        (lote,) = banco.linhas("cm_lote")
        assert lote["fonte"] == "PENDENTES"

    def test_a_prova_da_pendente_validada_traz_a_regra_vigente_e_a_descartada_sem_ela(self, cenario):
        cliente, _banco, provedor = cenario

        assert cliente.post(ROTA, json={"texto": "revisar pendentes"}).status_code == 200

        da_alterada, da_descartada = provedor.da_prova()[0], provedor.da_prova()[10]
        assert re.search(rf"\| ALFA-DIA-02 \| {re.escape(DIA_02_ALTERADA)} \|[^\n]*VIGENTE", da_alterada)
        assert PRI_03 not in da_descartada

    def test_operadora_sem_pendente_ouve_do_auditor_e_nao_ganha_lote(self, cenario):
        cliente, banco, provedor = cenario
        # Valida as duas pendentes da ALFA.
        assert cliente.post(ROTA, json={"texto": "revisar pendentes"}).status_code == 200
        assert cliente.post(ROTA, json={"texto": "ok"}).status_code == 200
        pedidos = len(provedor.pedidos)

        resposta = cliente.post(ROTA, json={"texto": "revisar pendentes"})

        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["lote"] is None
        assert resposta.json()["mensagens"][-1]["texto"] == "A ALFA não tem Regra pendente para revisar."
        assert len(provedor.pedidos) == pedidos
        assert len(banco.linhas("cm_lote")) == 1


# ═══════════════════════════════════════════════════════════════════════════
# 2. O ok gera uma versão da Memória e fecha os Temas de validação
# ═══════════════════════════════════════════════════════════════════════════


def _validar(conta: str, codigo: str, regra: str, lancada: float, devida: float) -> dict[str, Any]:
    """A Linha Validar da Regra pendente, como o Passo B grava."""
    return {
        **_linha_do_guia(conta, codigo, "2026-10-05", devida),
        "acao": "VALIDAR",
        "estado": "EM_VALIDACAO",
        "quantidade_lancada": lancada,
        "regra_codigo": regra,
        "motivo": f"Regra {regra} pendente. Dado na evolução.",
    }


def _tema(banco, tema_id: str, sigla: str, regra: str, linhas: list[dict]) -> None:
    operadora = next(o["id"] for o in banco.linhas("cm_operadora") if o["sigla"] == sigla)
    banco.tabelas.setdefault("cm_validacao_tema", []).append(
        {
            "id": tema_id,
            "operadora_id": operadora,
            "tipo": "REGRA_PENDENTE",
            "regra_codigo": regra,
            "codigo_item": None,
            "item_dicionario_id": None,
            "titulo": f"Regra {regra}",
            "estado": "ABERTO",
            "decisao": None,
            "criado_em": "2026-10-20T10:00:00+00:00",
        }
    )
    banco.tabelas.setdefault("cm_guia_linha", []).extend(linhas)
    banco.tabelas.setdefault("cm_validacao_tema_linha", []).extend(
        {"id": f"tl-{linha['id']}", "tema_id": tema_id, "guia_linha_id": linha["id"], "observacao_id": None}
        for linha in linhas
    )


class TestOOkDasPendentes:
    def test_o_ok_gera_uma_versao_e_fecha_os_temas_de_validacao_das_regras(self, cenario):
        cliente, banco, _provedor = cenario
        # A DIA-02 espera numa conta concluída (c05) com o item a incluir; a
        # PRI-03 numa outra (c06). A pendente da BETA tem o tema dela.
        dia_02 = _validar("c05", "M005", "ALFA-DIA-02", 0.0, 1.0)
        pri_03 = _validar("c06", "M006", "ALFA-PRI-03", 1.0, 2.0)
        _tema(banco, "t-dia-02", "ALFA", "ALFA-DIA-02", [dia_02])
        _tema(banco, "t-pri-03", "ALFA", "ALFA-PRI-03", [pri_03])
        _tema(banco, "t-beta", "BETA", "BETA-INS-02", [])
        assert cliente.post(ROTA, json={"texto": "revisar pendentes"}).status_code == 200

        resposta = cliente.post(ROTA, json={"texto": "ok"})

        assert resposta.status_code == 200, resposta.text
        assert _versoes(banco, "ALFA") == {"1.0": False, "1.1": True}
        assert resposta.json()["aplicado"]["versao"] == "1.1"
        regras = _regras_vigentes(banco)
        assert (regras["ALFA-DIA-02"]["texto"], regras["ALFA-DIA-02"]["status"]) == (DIA_02_ALTERADA, "VIGENTE")
        assert regras["ALFA-DIA-02"]["validado_por"] == GESTAO["id"]
        # A descartada sai da memória.
        assert regras["ALFA-PRI-03"]["ativa"] is False
        assert PRI_03 not in _vigente(banco)["texto_md"]

        temas = {t["id"]: t for t in banco.linhas("cm_validacao_tema")}
        assert {t: (temas[t]["estado"], temas[t]["decisao"]) for t in temas} == {
            "t-dia-02": ("DECIDIDO", "VALIDAR_REGRA"),
            "t-pri-03": ("DECIDIDO", "DESCARTAR"),
            "t-beta": ("ABERTO", None),
        }
        assert {temas[t]["decidido_por"] for t in ("t-dia-02", "t-pri-03")} == {GESTAO["id"]}

        # As Linhas seguem o caminho de hoje: a da regra validada vira a ação e
        # a conta concluída volta em Retorno; a da descartada fica sem ação.
        linhas = {linha["id"]: linha for linha in banco.linhas("cm_guia_linha")}
        assert (linhas[dia_02["id"]]["estado"], linhas[dia_02["id"]]["acao"]) == ("DECIDIDA", "INCLUIR")
        assert (linhas[pri_03["id"]]["estado"], linhas[pri_03["id"]]["acao"]) == ("DECIDIDA", "VALIDAR")
        contas = {c["id"]: c["situacao"] for c in banco.linhas("cm_conta")}
        assert (contas["c05"], contas["c06"]) == ("RETORNO", "CONCLUIDA")
