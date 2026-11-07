"""A Previsão de Contas médicas (issue #1417, PRD #1415).

O módulo é função pura: recebe as contas Na fila e Processando, o histórico
das contas prontas e o `agora`, e devolve a Previsão de cada conta e o resumo
da barra da aba Envios. Os esperados são contas feitas à mão: o histórico
padrão leva 6 segundos por página do Prontuário.
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime, timedelta

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.contas_medicas.previsao import ContaEmAndamento, ContaPronta, prever  # noqa: E402

AGORA = datetime(2026, 11, 7, 14, 0, tzinfo=UTC)


def _min(minutos: float) -> timedelta:
    return timedelta(minutes=minutos)


def _pronta(ha_horas: float = 1, *, segundos: float = 600, paginas: int = 100, espera_min: float = 5) -> ContaPronta:
    """Uma conta pronta há `ha_horas`, que levou `segundos` de processamento
    e esperou `espera_min` minutos na fila antes da vaga."""
    pronta_em = AGORA - timedelta(hours=ha_horas)
    enviada_em = pronta_em - timedelta(seconds=segundos) - _min(espera_min)
    return ContaPronta(enviada_em=enviada_em, pronta_em=pronta_em, processamento_s=segundos, paginas=paginas)


def _historico(quantas: int = 5, **kw) -> list[ContaPronta]:
    return [_pronta(ha_horas=n + 1, **kw) for n in range(quantas)]


def _processando(id_: str, ordem: int, paginas: int, ha_min: float) -> ContaEmAndamento:
    return ContaEmAndamento(
        id=id_, situacao="PROCESSANDO", ordem_fila=ordem, paginas=paginas, processando_desde=AGORA - _min(ha_min)
    )


def _na_fila(id_: str, ordem: int, paginas: int) -> ContaEmAndamento:
    return ContaEmAndamento(id=id_, situacao="NA_FILA", ordem_fila=ordem, paginas=paginas, processando_desde=None)


class TestSemPrevisao:
    @pytest.mark.parametrize(
        ("prontas", "tem_previsao"),
        [(0, False), (1, False), (4, False), (5, True), (6, True)],
    )
    def test_com_menos_de_5_contas_prontas_nao_ha_previsao(self, prontas, tem_previsao):
        contas = [_processando("a", 1, 100, ha_min=2), _na_fila("b", 2, 100)]

        previsoes, resumo = prever(contas, _historico(prontas), AGORA, vagas=2)

        assert (previsoes["a"].pronta is not None) is tem_previsao
        assert (previsoes["b"].inicio is not None) is tem_previsao
        assert (resumo.fila_esvazia_em is not None) is tem_previsao

    def test_conta_pronta_ha_mais_de_7_dias_nao_conta_para_as_5(self):
        historico = _historico(4) + [_pronta(ha_horas=7 * 24 + 1)]

        previsoes, _ = prever([_processando("a", 1, 100, ha_min=2)], historico, AGORA, vagas=2)

        assert previsoes["a"].pronta is None
        assert previsoes["a"].demorando is False


class TestVagas:
    def test_duas_processando_e_tres_na_fila_comecam_quando_as_vagas_abrem(self):
        """6 s por página. A (100 pág.) começou há 4 min e acaba às 14:06; B
        (200 pág.) começou há 10 min e acaba às 14:10. C pega a vaga de A às
        14:06 e acaba às 14:11; D pega a de B às 14:10 e acaba às 14:20; E
        pega a de C às 14:11 e acaba às 14:16. A fila esvazia às 14:20."""
        contas = [
            _processando("A", 1, 100, ha_min=4),
            _processando("B", 2, 200, ha_min=10),
            _na_fila("C", 3, 50),
            _na_fila("D", 4, 100),
            _na_fila("E", 5, 50),
        ]

        previsoes, resumo = prever(contas, _historico(), AGORA, vagas=2)

        def horas(i: str) -> tuple[datetime | None, datetime]:
            return previsoes[i].inicio, previsoes[i].pronta

        assert horas("A") == (AGORA - _min(4), AGORA + _min(6))
        assert horas("B") == (AGORA - _min(10), AGORA + _min(10))
        assert horas("C") == (AGORA + _min(6), AGORA + _min(11))
        assert horas("D") == (AGORA + _min(10), AGORA + _min(20))
        assert horas("E") == (AGORA + _min(11), AGORA + _min(16))
        assert resumo.fila_esvazia_em == AGORA + _min(20)
        assert [previsoes[i].posicao for i in "ABCDE"] == [None, None, 1, 2, 3]

    def test_a_ordem_de_envio_manda_e_nao_a_ordem_em_que_as_contas_chegam(self):
        contas = [_na_fila("depois", 9, 100), _na_fila("antes", 3, 100)]

        previsoes, _ = prever(contas, _historico(), AGORA, vagas=1)

        assert previsoes["antes"].inicio == AGORA
        assert previsoes["depois"].inicio == AGORA + _min(10)
        assert (previsoes["antes"].posicao, previsoes["depois"].posicao) == (1, 2)

    def test_conta_que_ja_passou_da_previsao_libera_a_vaga_agora_e_nao_no_passado(self):
        contas = [_processando("A", 1, 100, ha_min=15), _na_fila("B", 2, 100)]

        previsoes, _ = prever(contas, _historico(), AGORA, vagas=1)

        assert previsoes["A"].pronta == AGORA
        assert previsoes["B"].inicio == AGORA


class TestProporcional:
    def test_prontuario_de_1000_paginas_leva_10_vezes_o_de_100(self):
        contas = [_na_fila("cem", 1, 100), _na_fila("mil", 2, 1000)]

        previsoes, _ = prever(contas, _historico(), AGORA, vagas=2)

        assert previsoes["cem"].pronta == AGORA + _min(10)
        assert previsoes["mil"].pronta == AGORA + _min(100)

    def test_segundos_por_pagina_e_a_media_das_ultimas_20_prontas(self):
        """20 recentes a 6 s por página e 5 mais antigas a 60 s: só as 20 contam."""
        historico = _historico(20) + [_pronta(ha_horas=30 + n, segundos=6000) for n in range(5)]

        previsoes, _ = prever([_na_fila("a", 1, 100)], historico, AGORA, vagas=1)

        assert previsoes["a"].pronta == AGORA + _min(10)


class TestJanelaDe7Dias:
    def test_contas_prontas_ha_mais_de_7_dias_ficam_fora_das_medias(self):
        """Cinco recentes de 10 min de processamento e 5 de espera; uma de 8
        dias atrás, de 100 min e 100 de espera, ficaria nas médias e na Previsão."""
        historico = _historico() + [_pronta(ha_horas=8 * 24, segundos=6000, espera_min=100)]

        previsoes, resumo = prever([_na_fila("a", 1, 100)], historico, AGORA, vagas=1)

        assert resumo.tempo_processamento_s == 600
        assert resumo.tempo_envio_a_fila_s == 900
        assert previsoes["a"].pronta == AGORA + _min(10)


class TestDemora:
    @pytest.mark.parametrize(("ha_min", "demorando"), [(19, False), (20, False), (21, True)])
    def test_demorando_quando_o_tempo_decorrido_passa_de_2_vezes_a_previsao(self, ha_min, demorando):
        previsoes, _ = prever([_processando("a", 1, 100, ha_min=ha_min)], _historico(), AGORA, vagas=2)

        assert previsoes["a"].demorando is demorando

    def test_conta_na_fila_nunca_esta_demorando(self):
        previsoes, _ = prever([_na_fila("a", 1, 100)], _historico(), AGORA, vagas=1)

        assert previsoes["a"].demorando is False


class TestResumo:
    def test_conta_quantas_processando_e_quantas_na_fila(self):
        contas = [_processando("a", 1, 100, ha_min=1), _na_fila("b", 2, 100), _na_fila("c", 3, 100)]

        _, resumo = prever(contas, [], AGORA, vagas=2)

        assert (resumo.processando, resumo.na_fila) == (1, 2)
        assert resumo.tempo_processamento_s is None
        assert resumo.tempo_envio_a_fila_s is None
        assert resumo.fila_esvazia_em is None

    def test_sem_conta_em_andamento_nao_ha_hora_de_esvaziar(self):
        _, resumo = prever([], _historico(), AGORA, vagas=2)

        assert resumo.fila_esvazia_em is None
