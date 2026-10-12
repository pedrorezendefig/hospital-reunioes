"""Contador de diárias (issue #1115, PRD #1113, ADR 0070).

Port do `referencia-diarias.mjs` do diretor, parametrizado pelo bloco `diaria` da
memória da operadora. Os parâmetros abaixo são os blocos `diaria` das memórias
(ASSIM v3.2, Unimed v1.0, Leve v1.0) no formato do cabeçalho YAML lido; os casos
e os resultados esperados são os que o diretor validou (`--test` da referência,
LEIA-ME da Unimed, LEVE-DIA-06). D = 01/10/2026.
"""

from datetime import date, datetime

import pytest

from app.services.contas_medicas.conteudo import Movimentacao
from app.services.contas_medicas.diarias import ParametrosDiaria, contar_diarias, diarias_do_periodo

DIARIA_ASSIM = {
    "hora_vencimento": "10:00",
    "limite_madrugada": "05:00",
    "sempre_integral": True,
    "saida_antes_do_vencimento_paga_diaria_em_curso": True,
    "alta_depois_do_vencimento_paga_o_dia": False,
    "diaria_extra_na_origem_apos_vencimento": ["TRANSFERENCIA_DE_SETOR", "TRANSFERENCIA_DE_HOSPITAL", "OBITO"],
    "transferencia_antes_do_vencimento_gera_extra": "PENDENTE",
    "destino_inicia_na_hora_da_transferencia": True,
    "acompanhante_segue_a_regra_do_paciente": True,
    "acomodacao_cobrada": "CONTRATADA",
}
ASSIM = ParametrosDiaria.da_memoria({"diaria": DIARIA_ASSIM})


def quando(n: int, hora: str) -> datetime:
    """Dia D+n às `hora`, com D = 01/10/2026."""
    h, m = hora.split(":")
    return datetime(2026, 10, 1 + n, int(h), int(m))


def mov(tipo: str, n: int, hora: str, setor: str | None = None, janela=None) -> Movimentacao:
    return Movimentacao(tipo, quando(n, hora), setor, janela)


# ----------------------------------------------------------------------------------
# Os casos do `referencia-diarias.mjs --test` (ASSIM)
# ----------------------------------------------------------------------------------

CASOS_ASSIM = {
    "a: internação 21h45 D, alta 17h D+7": (
        [mov("INTERNACAO", 0, "21:45", "ENFERMARIA"), mov("ALTA", 7, "17:00")],
        [7],
        None,
    ),
    "b: internação 21h45 D, transferência 15h D+7, alta 12h D+9": (
        [mov("INTERNACAO", 0, "21:45", "CTI"), mov("TRANSFERENCIA_SETOR", 7, "15:00", "ENFERMARIA"), mov("ALTA", 9, "12:00")],
        [8, 2],
        None,
    ),
    "c: internação 4h D, alta 17h D+1": (
        [mov("INTERNACAO", 0, "04:00", "ENFERMARIA"), mov("ALTA", 1, "17:00")],
        [2],
        None,
    ),
    "d: internação 22h D, alta 8h D+1": (
        [mov("INTERNACAO", 0, "22:00", "ENFERMARIA"), mov("ALTA", 1, "08:00")],
        [1],
        None,
    ),
    "e: internação 8h D, alta 17h D+1": (
        [mov("INTERNACAO", 0, "08:00", "ENFERMARIA"), mov("ALTA", 1, "17:00")],
        [1],
        None,
    ),
    "f: internação 21h45 D, alta 8h D+3": (
        [mov("INTERNACAO", 0, "21:45", "ENFERMARIA"), mov("ALTA", 3, "08:00")],
        [3],
        None,
    ),
    "g: CTI 14h D, transferência 17h D+6, alta do andar 14h D+7": (
        [mov("INTERNACAO", 0, "14:00", "CTI"), mov("TRANSFERENCIA_SETOR", 6, "17:00", "ENFERMARIA"), mov("ALTA", 7, "14:00")],
        [7, 1],
        None,
    ),
    "h: óbito 15h D+2 após internação 21h D, com extra": (
        [mov("INTERNACAO", 0, "21:00", "CTI"), mov("OBITO", 2, "15:00")],
        [3],
        None,
    ),
    "i: óbito 8h D+2 após internação 21h D, diária em curso sem extra": (
        [mov("INTERNACAO", 0, "21:00", "CTI"), mov("OBITO", 2, "08:00")],
        [2],
        None,
    ),
    "j: transferência 8h D+3, PENDENTE: sem extra e Validar": (
        [mov("INTERNACAO", 0, "21:00", "CTI"), mov("TRANSFERENCIA_SETOR", 3, "08:00", "ENFERMARIA"), mov("ALTA", 4, "09:00")],
        [3, 1],
        [1, 0],
    ),
    "k: internação 11h e alta 17h no mesmo dia, sem regra: 0 e Validar": (
        [mov("INTERNACAO", 0, "11:00", "ENFERMARIA"), mov("ALTA", 0, "17:00")],
        [0],
        [1],
    ),
    "l: internação exatamente 5h D, alta 12h D+1, regra da madrugada": (
        [mov("INTERNACAO", 0, "05:00", "ENFERMARIA"), mov("ALTA", 1, "12:00")],
        [2],
        None,
    ),
    "m: transferência 3h D+2, madrugada no destino PENDENTE, alta 12h D+4": (
        [mov("INTERNACAO", 0, "21:00", "CTI"), mov("TRANSFERENCIA_SETOR", 2, "03:00", "ENFERMARIA"), mov("ALTA", 4, "12:00")],
        [2, 2],
        [1, 1],
    ),
}


@pytest.mark.parametrize(("movimentacoes", "diarias", "validar"), CASOS_ASSIM.values(), ids=CASOS_ASSIM.keys())
def test_os_casos_da_referencia_saem_com_as_diarias_e_pendencias_esperadas_na_assim(movimentacoes, diarias, validar):
    segmentos = contar_diarias(movimentacoes, ASSIM)

    assert [len(s.diarias) for s in segmentos] == diarias
    if validar is not None:
        assert [len(s.validar) for s in segmentos] == validar


def test_datas_de_lancamento_do_caso_c_a_primeira_na_hora_da_internacao_e_a_segunda_as_10h():
    (segmento,) = contar_diarias(CASOS_ASSIM["c: internação 4h D, alta 17h D+1"][0], ASSIM)

    assert [d.inicio for d in segmento.diarias] == [quando(0, "04:00"), quando(0, "10:00")]


def test_parciais_do_caso_a_de_01_a_04_e_de_05_a_08_saem_4_e_3():
    segmentos = contar_diarias(CASOS_ASSIM["a: internação 21h45 D, alta 17h D+7"][0], ASSIM)

    primeira = diarias_do_periodo(segmentos, date(2026, 10, 1), date(2026, 10, 4))
    segunda = diarias_do_periodo(segmentos, date(2026, 10, 5), date(2026, 10, 8))

    assert (len(primeira[0].diarias), len(segunda[0].diarias)) == (4, 3)
