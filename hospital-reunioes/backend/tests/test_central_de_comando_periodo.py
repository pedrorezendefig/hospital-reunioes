"""As regras puras de período da Central de Comando (issue #814, ADR 0058).

Porte de `src/lib/analytics/period.test.ts` e `variation.test.ts` do
repositório antigo (`pedroribbe/central-de-comando-hsm`): os testes de lá são a
especificação do porte, e a conta tem de dar o mesmo dia que a Central antiga
dava, senão o número da tela nova não bate com o da antiga no "mesmo período".

Sem I/O: só datas e números. O "hoje" entra por parâmetro, fixo, como lá, e o
instante do relógio também (issue #857).
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, date, datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.central_de_comando.periodo import (  # noqa: E402
    PERIODO_PADRAO,
    PERIODOS,
    Intervalo,
    dias_do_intervalo,
    dias_do_periodo,
    hoje_utc,
    intervalo_anterior,
    intervalo_atual,
    ler_periodo,
)
from app.services.central_de_comando.variacao import variacao_relativa  # noqa: E402

# O "hoje" fixo do teste de lá (2026-06-17T10:00:00Z), 7h em Brasília: a data
# do hospital é o que conta, e às 7h ela é a mesma em UTC.
HOJE = date(2026, 6, 17)


class TestDiasDoPeriodo:
    def test_mapeia_os_tres_rotulos(self):
        assert dias_do_periodo("7d") == 7
        assert dias_do_periodo("28d") == 28
        assert dias_do_periodo("90d") == 90


class TestIntervaloAtual:
    """N dias completos terminando ONTEM: o dia de hoje ainda está pela metade,
    e contá-lo derrubaria o número de todo período que termina nele."""

    def test_28_dias_terminando_ontem(self):
        assert intervalo_atual("28d", HOJE) == Intervalo(inicio=date(2026, 5, 20), fim=date(2026, 6, 16))

    def test_7_dias_terminando_ontem(self):
        assert intervalo_atual("7d", HOJE) == Intervalo(inicio=date(2026, 6, 10), fim=date(2026, 6, 16))

    def test_90_dias_terminando_ontem(self):
        assert intervalo_atual("90d", HOJE) == Intervalo(inicio=date(2026, 3, 19), fim=date(2026, 6, 16))


# Brasília: UTC-3 o ano todo, sem horário de verão desde 2019. Escrito à mão,
# e não importado do módulo: é a fonte independente contra a qual ele é conferido.
_BRASILIA = timezone(timedelta(hours=-3))


def _as(hora: int, minuto: int, dia: int) -> datetime:
    """Um instante de setembro de 2026 no relógio de Brasília, entregue em UTC,
    como o servidor o vê."""
    return datetime(2026, 9, dia, hora, minuto, tzinfo=_BRASILIA).astimezone(UTC)


class TestFimNoDiaDoHospital:
    """O período termina no "ontem" de Brasília, e não no de UTC (issue #857).

    Das 21h à meia-noite de Brasília, a data em UTC já é a de amanhã: com o
    relógio em UTC, o "ontem" seria o hoje de Brasília, ainda pela metade, e os
    números mudariam às 21h. O relógio entra fixo, por parâmetro.
    """

    def test_as_22h_de_brasilia_o_periodo_termina_no_dia_anterior_de_brasilia(self):
        # 22h de 18/09 em Brasília é 01h de 19/09 em UTC.
        hoje = hoje_utc(_as(22, 0, dia=18))

        assert hoje == date(2026, 9, 18)
        assert intervalo_atual("28d", hoje) == Intervalo(inicio=date(2026, 8, 21), fim=date(2026, 9, 17))

    def test_a_virada_das_21h_nao_muda_o_periodo(self):
        """Às 21h de Brasília o UTC vira o dia; o período, não."""
        antes = intervalo_atual("7d", hoje_utc(_as(20, 59, dia=18)))
        depois = intervalo_atual("7d", hoje_utc(_as(21, 0, dia=18)))

        assert antes == depois == Intervalo(inicio=date(2026, 9, 11), fim=date(2026, 9, 17))

    def test_a_meia_noite_de_brasilia_o_periodo_anda_um_dia(self):
        """É a meia-noite de Brasília, e não a de UTC, que fecha o dia: às
        23h59 o 18 ainda está pela metade; à 0h do 19 ele entra inteiro."""
        antes = intervalo_atual("7d", hoje_utc(_as(23, 59, dia=18)))
        depois = intervalo_atual("7d", hoje_utc(_as(0, 0, dia=19)))

        assert antes == Intervalo(inicio=date(2026, 9, 11), fim=date(2026, 9, 17))
        assert depois == Intervalo(inicio=date(2026, 9, 12), fim=date(2026, 9, 18))


class TestIntervaloAnterior:
    """O bloco de mesmo tamanho imediatamente antes do atual: é a base do
    "em relação ao período anterior"."""

    def test_28_dias_imediatamente_antes(self):
        assert intervalo_anterior("28d", HOJE) == Intervalo(inicio=date(2026, 4, 22), fim=date(2026, 5, 19))

    def test_7_dias_imediatamente_antes(self):
        assert intervalo_anterior("7d", HOJE) == Intervalo(inicio=date(2026, 6, 3), fim=date(2026, 6, 9))

    def test_encosta_no_atual_sem_buraco_nem_sobreposicao(self):
        """O dia seguinte ao fim do anterior é o início do atual, nos três."""
        for periodo in PERIODOS:
            anterior = intervalo_anterior(periodo, HOJE)
            atual = intervalo_atual(periodo, HOJE)
            assert (atual.inicio - anterior.fim).days == 1, periodo


class TestLerPeriodo:
    def test_aceita_os_periodos_validos(self):
        assert ler_periodo("7d") == "7d"
        assert ler_periodo("28d") == "28d"
        assert ler_periodo("90d") == "90d"

    @pytest.mark.parametrize("valor", [None, "", "xpto", "7", "90", " 7d"])
    def test_cai_no_padrao_28d_para_ausente_ou_invalido(self, valor):
        assert ler_periodo(valor) == "28d"

    def test_restringe_a_lista_de_permitidos_quando_passada(self):
        """O Instagram não tem 90 dias: fora da lista permitida, vale o padrão."""
        assert ler_periodo("90d", ("7d", "28d")) == "28d"
        assert ler_periodo("7d", ("7d", "28d")) == "7d"

    def test_o_padrao_e_28_dias(self):
        assert PERIODO_PADRAO == "28d"


class TestPeriodos:
    def test_os_tres_periodos_na_ordem_do_seletor(self):
        assert PERIODOS == ("7d", "28d", "90d")


class TestDiasDoIntervalo:
    def test_lista_as_datas_inclusive_nas_pontas(self):
        intervalo = Intervalo(inicio=date(2026, 6, 10), fim=date(2026, 6, 16))

        assert dias_do_intervalo(intervalo) == [
            date(2026, 6, 10),
            date(2026, 6, 11),
            date(2026, 6, 12),
            date(2026, 6, 13),
            date(2026, 6, 14),
            date(2026, 6, 15),
            date(2026, 6, 16),
        ]

    def test_alinha_com_os_dias_do_periodo_no_intervalo_atual(self):
        assert len(dias_do_intervalo(intervalo_atual("28d", HOJE))) == 28


class TestVariacaoRelativa:
    """A fração de variação do anterior para o atual. A tela só formata: a
    conta é do backend (PRD #809, "o front não faz conta")."""

    def test_calcula_a_fracao_do_anterior_para_o_atual(self):
        assert variacao_relativa(112, 100) == pytest.approx(0.12)
        assert variacao_relativa(80, 100) == pytest.approx(-0.2)

    def test_e_zero_quando_nao_mudou(self):
        assert variacao_relativa(100, 100) == 0

    def test_sem_base_de_comparacao_devolve_none(self):
        """Anterior zero ou negativo: não existe variação honesta, e a tela não
        mostra seta nenhuma em vez de mostrar um infinito ou um zero."""
        assert variacao_relativa(100, 0) is None
        assert variacao_relativa(100, -5) is None
