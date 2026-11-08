"""O Faltou isto por falta de regra vira proposta de Regra (issue #1496, PRD #1484, ADR 0081, decisões 4 a 6).

Quando o Auditor classifica o Faltou isto como REGRA, ele mesmo propõe a Regra
que faz o Guia apontar o item. Quem aponta decide o caminho:

- quem tem "Regra contratual e tabelas" (gestão e as duas diretorias): a
  proposta entra no lote aberto da conversa da Operadora, com a Prova da
  regra, e o "ok" ali grava a Regra vigente numa versão nova da Memória;
- faturista ou coordenadora: a Regra entra pendente numa versão nova da
  Memória, e um Tema de validação abre para a diretoria decidir.

O apontamento fica ligado ao item do lote, que guarda o código da Regra.

Tudo pela rota de verdade, com o cenário do Faltou isto (#1489): a Conta com o
Guia pronto e o provedor da IA dublado no transporte HTTP.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from test_contas_medicas_faltou_isto import (
    DIAGNOSTICO,
    PESSOAS,
    _apontar,
    _cliente,
    _conta_no_guia,
)
from test_contas_medicas_faltou_isto import _extrator as _extrator  # noqa: F401
from test_contas_medicas_faltou_isto import _reset_rate_limiter as _reset_rate_limiter  # noqa: F401
from test_contas_medicas_faltou_isto import ia_falsa as ia_falsa  # noqa: F401
from test_contas_medicas_processamento import _Banco
from test_contas_medicas_validacao import _BancoDaValidacao

from app.routers import contas_medicas_conversa as conversa_router
from app.services.contas_medicas.validacao import fila_de_validacao

LOTE = "LoteDoAuditor"

EXPLICACAO = "A página 2 foi lida e o acesso periférico está no evento, mas nenhuma regra manda cobrar o equipo."
ESPERADO = "Incluir 1 equipo macrogotas em 03/10, pelo acesso periférico da admissão."
REGRA_DO_EQUIPO = "Acesso venoso periférico instalado cobra 1 equipo macrogotas no dia da instalação."
RESPOSTA_DO_AUDITOR = "Proponho uma regra nova para o equipo do acesso periférico."


def _proposta(**campos: Any) -> dict[str, Any]:
    return {
        "tipo": "REGRA_NOVA",
        "regra_codigo": "",
        "secao": "INS",
        "texto": REGRA_DO_EQUIPO,
        "tipo_regra": "OPERACIONAL",
        "origem": "PRÁTICA",
        "parametro": "",
        "valor_json": "",
        "motivo": "O Guia passa a pedir o equipo do acesso periférico.",
        "conflitos": [],
        **campos,
    }


@pytest.fixture
def falta_regra(ia_falsa):  # noqa: F811
    ia_falsa.respostas[DIAGNOSTICO] = {"classificacao": "REGRA", "explicacao": EXPLICACAO, "esperado": ESPERADO}
    ia_falsa.respostas[LOTE] = {"resposta": RESPOSTA_DO_AUDITOR, "propostas": [_proposta()]}
    return ia_falsa


def _na_conta() -> tuple[_Banco, str]:
    """A Conta com o Guia pronto (#1489), no dublê da Validação: os DEFAULT da
    118 no Tema e a paginação que a fila de Validação lê."""
    banco, conta_id = _conta_no_guia()
    banco.__class__ = _BancoDaValidacao
    return banco, conta_id


def _com_a_conversa(banco: _Banco, quem: str) -> TestClient:
    cliente = _cliente(banco, quem)
    cliente.app.include_router(conversa_router.router, prefix="/api")
    return cliente


CONVERSA = "/api/contas-medicas/operadoras/ALFA/conversa"


def _vigente(banco: _Banco) -> dict[str, Any]:
    (vigente,) = [v for v in banco.tabelas["cm_memoria_versao"] if v["operadora_id"] == "op-alfa" and v["vigente"]]
    return vigente


def _regra_do_equipo(banco: _Banco) -> dict[str, Any] | None:
    vigente = _vigente(banco)
    return next(
        (
            r
            for r in banco.tabelas["cm_regra"]
            if r["memoria_versao_id"] == vigente["id"] and r["texto"] == REGRA_DO_EQUIPO
        ),
        None,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 1. Da gestão ou da diretoria: o lote da Operadora e o "ok"
# ═══════════════════════════════════════════════════════════════════════════


class TestDeQuemDecide:
    @pytest.mark.parametrize("quem", ["gestao", "diretoria_medica", "diretoria_executiva"])
    def test_o_faltou_isto_de_quem_decide_vira_item_no_lote_da_operadora_e_o_ok_grava_a_regra_vigente(
        self, falta_regra, quem
    ):
        banco, conta_id = _na_conta()
        antes = _vigente(banco)

        resposta = _apontar(banco, conta_id, quem)

        assert resposta.status_code == 200, resposta.text
        # Antes do ok, a Memória não muda: o item espera no lote da conversa da Operadora, com a prova.
        assert _vigente(banco)["id"] == antes["id"]
        conversa = _com_a_conversa(banco, quem).get(CONVERSA).json()
        (item,) = conversa["lote"]["itens"]
        assert (item["tipo"], item["proposta"]["texto"], item["proposta"]["secao"]) == (
            "REGRA_NOVA",
            REGRA_DO_EQUIPO,
            "INS",
        )
        assert item["prova"] is not None
        assert {lote["fonte"] for lote in banco.tabelas["cm_lote"]} == {"FALTOU_ISTO"}
        assert [(m["autor"], m["texto"]) for m in conversa["mensagens"]] == [
            ("PESSOA", "Faltou isto no Guia, em 03/10: Equipo macrogotas."),
            ("AUDITOR", RESPOSTA_DO_AUDITOR),
        ]

        ok = _com_a_conversa(banco, quem).post(CONVERSA, json={"texto": "ok"})

        assert ok.status_code == 200, ok.text
        nova = _vigente(banco)
        assert nova["id"] != antes["id"]
        regra = _regra_do_equipo(banco)
        assert regra is not None
        assert (regra["status"], regra["validado_por"]) == ("VIGENTE", PESSOAS[quem]["id"])
        assert regra["codigo"] == "ALFA-INS-01"


    def test_a_proposta_entra_no_lote_que_ja_estava_aberto_sem_descarta_lo(self, falta_regra):
        banco, conta_id = _na_conta()
        assert _com_a_conversa(banco, "gestao").post(CONVERSA, json={"texto": "Ensina o equipo."}).status_code == 200

        _apontar(banco, conta_id, "gestao")

        lote = _com_a_conversa(banco, "gestao").get(CONVERSA).json()["lote"]
        assert [i["numero"] for i in lote["itens"]] == [1, 2]
        assert {item["estado"] for item in banco.tabelas["cm_lote_item"]} == {"PROPOSTO"}

    def test_auditor_fora_na_proposta_responde_503_e_nada_fica_gravado(self, falta_regra):
        banco, conta_id = _na_conta()
        falta_regra.fora_do_formato_em = {LOTE}

        resposta = _apontar(banco, conta_id, "gestao")

        assert resposta.status_code == 503
        for tabela in ("cm_faltou_isto", "cm_conversa", "cm_lote", "cm_lote_item"):
            assert banco.tabelas.get(tabela, []) == [], tabela


# ═══════════════════════════════════════════════════════════════════════════
# 2. Da faturista ou da coordenadora: Regra pendente e Tema de validação
# ═══════════════════════════════════════════════════════════════════════════


class TestDeQuemNaoDecide:
    @pytest.mark.parametrize("quem", ["faturista", "coordenadora"])
    def test_o_faltou_isto_de_quem_nao_decide_grava_a_regra_pendente_e_abre_o_tema_de_validacao(
        self, falta_regra, quem
    ):
        banco, conta_id = _na_conta()
        antes = _vigente(banco)

        resposta = _apontar(banco, conta_id, quem)

        assert resposta.status_code == 200, resposta.text
        # A Regra entra pendente numa versão nova, sem esperar ok de ninguém.
        assert _vigente(banco)["id"] != antes["id"]
        regra = _regra_do_equipo(banco)
        assert regra is not None
        assert (regra["status"], regra.get("validado_por"), regra["codigo"]) == ("PENDENTE", None, "ALFA-INS-01")
        # Nada fica esperando o ok na conversa da Operadora.
        assert _com_a_conversa(banco, "gestao").get(CONVERSA).json()["lote"] is None

        # O Tema chega na fila de Validação, com a Conta do apontamento.
        (tema,) = [t for t in banco.tabelas["cm_validacao_tema"] if t["regra_codigo"] == "ALFA-INS-01"]
        assert (tema["tipo"], tema["estado"], tema["operadora_id"]) == ("REGRA_PENDENTE", "ABERTO", "op-alfa")
        (cartao,) = [c for c in fila_de_validacao(banco)["temas"] if c["id"] == tema["id"]]
        assert (cartao["contas"], cartao["regra"]["status"]) == (1, "PENDENTE")


# ═══════════════════════════════════════════════════════════════════════════
# 3. O apontamento fica ligado à Regra gerada
# ═══════════════════════════════════════════════════════════════════════════


def _no_guia(banco: _Banco, conta_id: str, quem: str) -> dict[str, Any]:
    guia = _cliente(banco, quem).get(f"/api/contas-medicas/contas/{conta_id}/guia")
    assert guia.status_code == 200, guia.text
    (apontamento,) = guia.json()["faltou_isto"]
    return apontamento


def _regra_do_apontamento(banco: _Banco) -> str | None:
    (apontamento,) = banco.tabelas["cm_faltou_isto"]
    (item,) = [i for i in banco.tabelas["cm_lote_item"] if i["id"] == apontamento["lote_item_id"]]
    return item.get("regra_codigo")


class TestOApontamentoLigadoARegra:
    def test_o_ok_liga_o_apontamento_de_quem_decide_a_regra_vigente(self, falta_regra):
        banco, conta_id = _na_conta()
        _apontar(banco, conta_id, "gestao")

        # Antes do ok, o apontamento aponta para o item que espera na conversa da Operadora.
        assert _regra_do_apontamento(banco) is None
        assert _no_guia(banco, conta_id, "gestao")["proposta_de_regra"] == (
            'A proposta de Regra está na conversa da Operadora, esperando o "ok".'
        )

        assert _com_a_conversa(banco, "gestao").post(CONVERSA, json={"texto": "ok"}).status_code == 200

        assert _regra_do_apontamento(banco) == _regra_do_equipo(banco)["codigo"] == "ALFA-INS-01"
        assert _no_guia(banco, conta_id, "gestao")["proposta_de_regra"] == "A Regra ALFA-INS-01 entrou na memória."

    def test_a_mensagem_nova_na_conversa_da_operadora_descarta_a_proposta_e_o_guia_diz(self, falta_regra):
        banco, conta_id = _na_conta()
        _apontar(banco, conta_id, "gestao")

        outra = _com_a_conversa(banco, "gestao").post(CONVERSA, json={"texto": "Na ALFA o equipo é por dia."})

        assert outra.status_code == 200, outra.text
        assert _no_guia(banco, conta_id, "gestao")["proposta_de_regra"] == (
            "A proposta de Regra foi descartada na conversa da Operadora."
        )

    def test_o_apontamento_da_faturista_fica_ligado_a_regra_pendente(self, falta_regra):
        banco, conta_id = _na_conta()

        _apontar(banco, conta_id)

        assert _regra_do_apontamento(banco) == _regra_do_equipo(banco)["codigo"] == "ALFA-INS-01"
        assert _no_guia(banco, conta_id, "faturista")["proposta_de_regra"] == (
            "A Regra ALFA-INS-01 entrou na memória como pendente e foi para a Validação."
        )

    def test_sem_falta_de_regra_nao_ha_proposta(self):
        banco, conta_id = _na_conta()

        _apontar(banco, conta_id)

        assert banco.tabelas.get("cm_lote_item", []) == []
        assert _no_guia(banco, conta_id, "faturista")["proposta_de_regra"] is None
