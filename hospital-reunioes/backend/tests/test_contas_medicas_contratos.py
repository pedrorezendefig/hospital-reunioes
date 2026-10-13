"""Contratos e aviso de reajuste de Contas medicas (issue #1144, PRD #1129).

Cada operadora tem um contrato (`cm_contrato`) com assinatura, ultimo aditivo,
inicio da vigencia e vencimento. Ele nasce do bloco `contrato` da memoria da
operadora e muda pela tela: a pessoa envia o contrato ou o aditivo, a IA
propoe os quatro campos e nada vale antes de a pessoa confirmar. A rotina
diaria calcula os dias que faltam e, na data do aviso (vencimento menos a
antecedencia da memoria), manda um aviso CONTAS_MEDICAS ao sino de quem tem
"contratos e avisos", uma vez so (`cm_aviso`).

O duble do banco e o da carga da operadora (`test_contas_medicas_operadoras`),
com as restricoes da migration 118 que esta fatia pode ferir: um contrato por
operadora e um aviso por contrato e data.
"""

from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from test_contas_medicas_operadoras import (  # noqa: E402
    _Banco,
    _enviar_memoria,
    _erro,
    _matriz_da_migration,
    _memoria,
    _pessoa,
)
from test_contas_medicas_operadoras import _cliente as _cliente_da_carga  # noqa: E402

from app.dependencies import get_current_user, get_supabase_client  # noqa: E402
from app.limiter import limiter  # noqa: E402

MEMORIA_ALFA = _memoria("MEMORIA-ALFA-v1.0.md")
BLOCO_ALFA = """contrato:
  assinatura: 2015-10-01
  ultimo_aditivo: { numero: 12, inicio_vigencia: 2026-05-01 }
  aviso_antecedencia_dias: 60
"""


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


def _memoria_com_contrato(bloco: str) -> str:
    assert BLOCO_ALFA in MEMORIA_ALFA, "o bloco contrato da fixture ALFA mudou"
    return MEMORIA_ALFA.replace(BLOCO_ALFA, bloco)


class _BancoDosContratos(_Banco):
    """O duble da carga com os UNIQUE da migration 118."""

    def _validar(self, tabela: str, linha: dict, ignorar: dict | None = None) -> None:
        super()._validar(tabela, linha, ignorar)
        outras = [o for o in self.linhas(tabela) if o is not ignorar]
        if tabela == "cm_contrato" and any(o["operadora_id"] == linha["operadora_id"] for o in outras):
            raise _erro("23505", "duplicate key value violates unique constraint cm_contrato_operadora_id_key")
        if tabela == "cm_aviso" and any(
            (o["contrato_id"], o["data_prevista"]) == (linha["contrato_id"], linha["data_prevista"]) for o in outras
        ):
            raise _erro("23505", "duplicate key value violates unique constraint cm_aviso_contrato_id_data_prevista_key")


GESTAO = _pessoa(perfil_contas_medicas="gestao_contas_medicas")


# ═══════════════════════════════════════════════════════════════════════════
# 1. O contrato nasce da memoria
# ═══════════════════════════════════════════════════════════════════════════


class TestContratoDaMemoria:
    def test_memoria_sem_vencimento_cria_o_contrato_com_vigencia_mais_um_ano_calculado(self):
        cliente, banco = _cliente_da_carga(GESTAO, _BancoDosContratos())

        resposta = _enviar_memoria(cliente, MEMORIA_ALFA)

        assert resposta.status_code == 201, resposta.text
        [operadora] = banco.linhas("cm_operadora")
        [contrato] = banco.linhas("cm_contrato")
        assert contrato["operadora_id"] == operadora["id"]
        assert contrato["data_assinatura"] == "2015-10-01"
        assert contrato["aditivo_numero"] == "12"
        assert contrato["vigencia_inicio"] == "2026-05-01"
        assert contrato["vencimento"] == "2027-05-01"
        assert contrato["vencimento_calculado"] is True
        assert contrato["vencimento_e_negociacao"] is False
        assert contrato["aviso_dias"] == 60

    def test_comentario_que_diz_que_a_data_nao_e_vencimento_marca_a_negociacao(self):
        """O bloco da memoria da Unimed: o YAML joga o comentario fora, e e ele
        que diz que a data e o inicio do debate do reajuste."""
        unimed = _memoria_com_contrato(
            "contrato:\n"
            "  assinatura: null            # corpo do contrato nao disponivel\n"
            "  ultimo_aditivo: { numero: null, inicio_vigencia: 2026-04-15 }\n"
            "  vencimento: 2027-01-15      # NÃO é vencimento contratual. É a data do debate do reajuste\n"
            "  aviso_antecedencia_dias: 0  # alerta na propria data\n"
        )
        cliente, banco = _cliente_da_carga(GESTAO, _BancoDosContratos())

        assert _enviar_memoria(cliente, unimed).status_code == 201

        [contrato] = banco.linhas("cm_contrato")
        assert contrato["vencimento"] == "2027-01-15"
        assert contrato["vencimento_calculado"] is False
        assert contrato["vencimento_e_negociacao"] is True
        assert contrato["aviso_dias"] == 0
        assert contrato["data_assinatura"] is None
        assert contrato["aditivo_numero"] is None

    def test_vencimento_escrito_e_marcado_calculado_no_comentario_fica_calculado(self):
        """O bloco da ASSIM: a data esta escrita, e o comentario diz que foi calculada."""
        assim = _memoria_com_contrato(
            "contrato:\n"
            "  assinatura: 2015-10-01\n"
            "  ultimo_aditivo: { numero: 110, inicio_vigencia: 2026-05-01 }\n"
            "  vencimento: 2027-05-01      # CALCULADO: 1 ano após a vigência do último aditivo. Confirmar.\n"
            "  aviso_antecedencia_dias: 60\n"
        )
        cliente, banco = _cliente_da_carga(GESTAO, _BancoDosContratos())

        assert _enviar_memoria(cliente, assim).status_code == 201

        [contrato] = banco.linhas("cm_contrato")
        assert (contrato["vencimento"], contrato["vencimento_calculado"]) == ("2027-05-01", True)
        assert contrato["vencimento_e_negociacao"] is False

    def test_memoria_nova_nao_desfaz_o_que_a_pessoa_confirmou(self):
        cliente, banco = _cliente_da_carga(GESTAO, _BancoDosContratos())
        assert _enviar_memoria(cliente, MEMORIA_ALFA).status_code == 201
        [contrato] = banco.linhas("cm_contrato")
        contrato.update({"vencimento": "2027-09-30", "vencimento_calculado": False, "confirmado_em": "2026-10-10"})
        nova = MEMORIA_ALFA.replace("aviso_antecedencia_dias: 60", "aviso_antecedencia_dias: 90")

        assert _enviar_memoria(cliente, nova).status_code == 201

        [contrato] = banco.linhas("cm_contrato")
        assert (contrato["vencimento"], contrato["vencimento_calculado"]) == ("2027-09-30", False)
        assert contrato["aviso_dias"] == 90

    def test_memoria_sem_bloco_contrato_nao_cria_contrato(self):
        cliente, banco = _cliente_da_carga(GESTAO, _BancoDosContratos())

        assert _enviar_memoria(cliente, _memoria_com_contrato("")).status_code == 201

        assert banco.linhas("cm_contrato") == []


# ═══════════════════════════════════════════════════════════════════════════
# 2. Dias que faltam e situacao
# ═══════════════════════════════════════════════════════════════════════════

HOJE = date(2027, 3, 2)


def _banco_com_contratos(*contratos: tuple[str, str | None, dict[str, Any]]) -> _BancoDosContratos:
    """Uma operadora por tupla `(sigla, vencimento, campos)`; vencimento `None` = sem contrato."""
    banco = _BancoDosContratos()
    for sigla, vencimento, campos in contratos:
        operadora = banco.inserir("cm_operadora", {"sigla": sigla, "nome": f"{sigla.title()} Saude"})
        if vencimento is not None:
            banco.inserir(
                "cm_contrato",
                {
                    "operadora_id": operadora["id"],
                    "vencimento": vencimento,
                    "vencimento_calculado": False,
                    "vencimento_e_negociacao": False,
                    "aviso_dias": 60,
                    **campos,
                },
            )
    return banco


class TestSituacaoDoContrato:
    def test_61_60_1_e_menos_1_dias_e_sem_contrato(self):
        from app.services.contas_medicas.contratos import listar_contratos

        banco = _banco_com_contratos(
            ("A61", "2027-05-02", {}),
            ("B60", "2027-05-01", {}),
            ("C01", "2027-03-03", {}),
            ("D00", "2027-03-01", {}),
            ("ESEM", None, {}),
        )

        linhas = {linha["sigla"]: linha for linha in listar_contratos(banco, HOJE)}

        assert {s: (linha["dias"], linha["situacao"]) for s, linha in linhas.items()} == {
            "A61": (61, "EM_DIA"),
            "B60": (60, "NEGOCIAR"),
            "C01": (1, "NEGOCIAR"),
            "D00": (-1, "VENCIDO"),
            "ESEM": (None, "SEM_CONTRATO"),
        }
        assert linhas["B60"]["contrato"]["vencimento"] == "2027-05-01"
        assert linhas["ESEM"]["contrato"] is None

    def test_contrato_sem_vencimento_e_sem_contrato(self):
        from app.services.contas_medicas.contratos import listar_contratos

        banco = _banco_com_contratos(("ALFA", "", {}))
        banco.linhas("cm_contrato")[0]["vencimento"] = None

        [linha] = listar_contratos(banco, HOJE)

        assert (linha["dias"], linha["situacao"]) == (None, "SEM_CONTRATO")
