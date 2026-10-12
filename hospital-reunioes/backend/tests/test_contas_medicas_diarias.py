"""Contador de diárias (issue #1115, PRD #1113, ADR 0070).

Port do `referencia-diarias.mjs` do diretor, parametrizado pelo bloco `diaria` da
memória da operadora. Os parâmetros abaixo são os blocos `diaria` das memórias
(ASSIM v3.2, Unimed v1.0, Leve v1.0) no formato do cabeçalho YAML lido; os casos
e os resultados esperados são os que o diretor validou (`--test` da referência,
LEIA-ME da Unimed, LEVE-DIA-06). D = 01/10/2026.
"""

from datetime import date, datetime
from pathlib import Path

import pytest
from test_contas_medicas_conteudo import CLEXANE, INTERNACAO_COM_TRANSFERENCIA, ler, prescricao

from app.services.contas_medicas.conteudo import Movimentacao
from app.services.contas_medicas.diarias import ParametrosDiaria, contar_diarias, diarias_do_periodo
from app.services.contas_medicas.memoria import ler_memoria, parametros_lidos

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
        [
            mov("INTERNACAO", 0, "21:45", "CTI"),
            mov("TRANSFERENCIA_SETOR", 7, "15:00", "ENFERMARIA"),
            mov("ALTA", 9, "12:00"),
        ],
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
        [
            mov("INTERNACAO", 0, "14:00", "CTI"),
            mov("TRANSFERENCIA_SETOR", 6, "17:00", "ENFERMARIA"),
            mov("ALTA", 7, "14:00"),
        ],
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
        [
            mov("INTERNACAO", 0, "21:00", "CTI"),
            mov("TRANSFERENCIA_SETOR", 3, "08:00", "ENFERMARIA"),
            mov("ALTA", 4, "09:00"),
        ],
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
        [
            mov("INTERNACAO", 0, "21:00", "CTI"),
            mov("TRANSFERENCIA_SETOR", 2, "03:00", "ENFERMARIA"),
            mov("ALTA", 4, "12:00"),
        ],
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


# ----------------------------------------------------------------------------------
# Unimed: transferência de setor sem extra na origem (LEIA-ME do pacote da Unimed)
# ----------------------------------------------------------------------------------

UNIMED = ParametrosDiaria.da_memoria(
    {
        "diaria": {
            **DIARIA_ASSIM,
            "diaria_extra_na_origem_apos_vencimento": ["TRANSFERENCIA_DE_HOSPITAL", "OBITO"],
            "transferencia_antes_do_vencimento_gera_extra": False,
            "acompanhante_segue_a_regra_do_paciente": None,
        }
    }
)

CASOS_UNIMED = {
    "enfermaria 17h D, CTI 16h30 D+2, enfermaria 17h D+5, alta 8h D+6": (
        [
            mov("INTERNACAO", 0, "17:00", "ENFERMARIA"),
            mov("TRANSFERENCIA_SETOR", 2, "16:30", "CTI"),
            mov("TRANSFERENCIA_SETOR", 5, "17:00", "ENFERMARIA"),
            mov("ALTA", 6, "08:00"),
        ],
        [("ENFERMARIA", 2), ("CTI", 3), ("ENFERMARIA", 1)],
    ),
    "internação 6h D, alta 18h D+1": (
        [mov("INTERNACAO", 0, "06:00", "ENFERMARIA"), mov("ALTA", 1, "18:00")],
        [("ENFERMARIA", 1)],
    ),
    "internação 4h D, alta 7h D+2": (
        [mov("INTERNACAO", 0, "04:00", "ENFERMARIA"), mov("ALTA", 2, "07:00")],
        [("ENFERMARIA", 3)],
    ),
    "CTI 12h D, óbito 15h D+2": (
        [mov("INTERNACAO", 0, "12:00", "CTI"), mov("OBITO", 2, "15:00")],
        [("CTI", 3)],
    ),
}


@pytest.mark.parametrize(("movimentacoes", "esperado"), CASOS_UNIMED.values(), ids=CASOS_UNIMED.keys())
def test_os_casos_da_unimed_saem_como_o_diretor_validou(movimentacoes, esperado):
    segmentos = contar_diarias(movimentacoes, UNIMED)

    assert [(s.setor, len(s.diarias)) for s in segmentos] == esperado
    assert [s.validar for s in segmentos] == [()] * len(esperado)


# ----------------------------------------------------------------------------------
# Parametrização: a saída muda com a memória, não com constante
# ----------------------------------------------------------------------------------

CASO_B = CASOS_ASSIM["b: internação 21h45 D, transferência 15h D+7, alta 12h D+9"][0]


def test_parametros_saem_da_memoria_como_a_carga_da_operadora_le_o_cabecalho():
    """A memória sintética ALFA (fixture da carga, #1119) traz `diaria` com setor e óbito
    na lista de extra e sem `transferencia_antes_do_vencimento_gera_extra`."""
    texto = (Path(__file__).parent / "fixtures" / "contas_medicas" / "memoria" / "MEMORIA-ALFA-v1.0.md").read_text(
        encoding="utf-8"
    )

    parametros = ParametrosDiaria.da_memoria(parametros_lidos(ler_memoria(texto).parametros))

    assert parametros.diaria_extra_na_origem_apos_vencimento == {"TRANSFERENCIA_SETOR", "OBITO"}
    assert parametros.transferencia_antes_do_vencimento_gera_extra == "PENDENTE"
    assert [len(s.diarias) for s in contar_diarias(CASO_B, parametros)] == [8, 2]


def test_tirar_a_transferencia_de_setor_da_lista_de_extra_tira_a_extra_da_origem_no_caso_b():
    sem_setor = ParametrosDiaria.da_memoria(
        {"diaria": {**DIARIA_ASSIM, "diaria_extra_na_origem_apos_vencimento": ["TRANSFERENCIA_DE_HOSPITAL", "OBITO"]}}
    )

    assert [len(s.diarias) for s in contar_diarias(CASO_B, ASSIM)] == [8, 2]
    assert [len(s.diarias) for s in contar_diarias(CASO_B, sem_setor)] == [7, 2]


# Caso j: transferência às 8h de D+3, antes do vencimento.
CASO_J = CASOS_ASSIM["j: transferência 8h D+3, PENDENTE: sem extra e Validar"][0]


@pytest.mark.parametrize(
    ("valor", "diarias", "motivos"),
    [
        (True, [4, 1], [[], []]),
        (False, [3, 1], [[], []]),
        ("PENDENTE", [3, 1], [["TRANSFERENCIA_ANTES_DO_VENCIMENTO"], []]),
    ],
)
def test_transferencia_antes_do_vencimento_segue_o_parametro_true_false_ou_pendente(valor, diarias, motivos):
    parametros = ParametrosDiaria.da_memoria(
        {"diaria": {**DIARIA_ASSIM, "transferencia_antes_do_vencimento_gera_extra": valor}}
    )

    segmentos = contar_diarias(CASO_J, parametros)

    assert [len(s.diarias) for s in segmentos] == diarias
    assert [[p.motivo for p in s.validar] for s in segmentos] == motivos


LEVE = ParametrosDiaria.da_memoria(
    {
        "diaria": {
            **DIARIA_ASSIM,
            "diaria_extra_na_origem_apos_vencimento": ["TRANSFERENCIA_DE_HOSPITAL", "OBITO", "TRANSFERENCIA_DE_SETOR"],
            "transferencia_antes_do_vencimento_gera_extra": True,
            "acompanhante_segue_a_regra_do_paciente": None,
        }
    }
)


def test_leve_dia_06_enfermaria_ate_16h_e_cti_a_partir_das_16h_dao_uma_diaria_de_cada_no_dia():
    segmentos = contar_diarias(
        [
            mov("INTERNACAO", 0, "21:00", "ENFERMARIA"),
            mov("TRANSFERENCIA_SETOR", 2, "16:00", "CTI"),
            mov("ALTA", 4, "12:00"),
        ],
        LEVE,
    )

    no_dia = diarias_do_periodo(segmentos, date(2026, 10, 3), date(2026, 10, 3))

    assert [(s.setor, [d.inicio for d in s.diarias]) for s in no_dia] == [
        ("ENFERMARIA", [quando(2, "10:00")]),
        ("CTI", [quando(2, "16:00")]),
    ]
    assert [s.validar for s in segmentos] == [(), ()]


# ----------------------------------------------------------------------------------
# Transferência de setor como janela e a saída exatamente no vencimento
# ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("janela", "diarias", "motivos"),
    [
        # toda antes das 10h: regra da transferência antes do vencimento (PENDENTE na ASSIM)
        (("06:00", "09:30"), [7, 2], [["TRANSFERENCIA_ANTES_DO_VENCIMENTO"], []]),
        # toda depois, começando exatamente às 10h: extra na origem, sem pendência
        (("10:00", "15:00"), [8, 2], [[], []]),
        # atravessa as 10h: calcula pelo fim da janela e devolve Validar
        (("09:00", "15:00"), [8, 2], [["JANELA_ATRAVESSA_O_VENCIMENTO"], []]),
    ],
    ids=["toda antes", "toda depois", "atravessa"],
)
def test_janela_da_transferencia_que_atravessa_o_vencimento_vira_validar_e_inteira_de_um_lado_aplica_a_regra(
    janela, diarias, motivos
):
    de, ate = janela
    segmentos = contar_diarias(
        [
            mov("INTERNACAO", 0, "21:45", "CTI"),
            mov("TRANSFERENCIA_SETOR", 7, ate, "ENFERMARIA", (quando(7, de), quando(7, ate))),
            mov("ALTA", 9, "12:00"),
        ],
        ASSIM,
    )

    assert [len(s.diarias) for s in segmentos] == diarias
    assert [[p.motivo for p in s.validar] for s in segmentos] == motivos


@pytest.mark.parametrize(
    ("parametro", "valor"),
    [
        ("sempre_integral", False),
        ("saida_antes_do_vencimento_paga_diaria_em_curso", False),
        ("alta_depois_do_vencimento_paga_o_dia", True),
        ("destino_inicia_na_hora_da_transferencia", False),
    ],
)
def test_parametro_com_valor_que_nenhuma_memoria_definiu_vira_validar_em_vez_de_conta_silenciosa(parametro, valor):
    parametros = ParametrosDiaria.da_memoria({"diaria": {**DIARIA_ASSIM, parametro: valor}})

    segmentos = contar_diarias(CASO_B, parametros)

    assert [[(p.motivo, parametro in p.texto) for p in s.validar] for s in segmentos] == [
        [("PARAMETRO_NAO_SUPORTADO", True)],
        [],
    ]


@pytest.mark.parametrize(("hora", "diarias"), [("10:00", 3), ("09:59", 2)])
def test_saida_exatamente_as_10h_conta_como_depois_do_vencimento(hora, diarias):
    segmentos = contar_diarias([mov("INTERNACAO", 0, "21:00", "CTI"), mov("OBITO", 2, hora)], ASSIM)

    assert len(segmentos[0].diarias) == diarias


# ----------------------------------------------------------------------------------
# Conta parcial e acompanhante
# ----------------------------------------------------------------------------------


@pytest.mark.parametrize("divisa", range(2, 10))
def test_a_diaria_do_dia_de_divisa_cai_em_exatamente_uma_parcial(divisa):
    """Caso b (10 diárias, a última começa em 09/10) cortado em [01, divisa - 1] e [divisa, 10]."""
    segmentos = contar_diarias(CASO_B, ASSIM)

    primeira = diarias_do_periodo(segmentos, date(2026, 10, 1), date(2026, 10, divisa - 1))
    segunda = diarias_do_periodo(segmentos, date(2026, 10, divisa), date(2026, 10, 10))

    def inicios(parcial):
        return [(s.setor, d.inicio) for s in parcial for d in s.diarias]

    do_dia = [(setor, inicio) for setor, inicio in inicios(segmentos) if inicio.day == divisa]
    assert do_dia
    for diaria in do_dia:
        assert (diaria in inicios(primeira), diaria in inicios(segunda)) == (False, True)
    assert sorted(inicios(primeira) + inicios(segunda)) == sorted(inicios(segmentos))


@pytest.mark.parametrize(
    ("parametros", "idade", "acompanhante"),
    [
        (ASSIM, 60, True),
        (ASSIM, 17, True),
        (ASSIM, 59, False),
        (ASSIM, 18, False),
        (ASSIM, None, False),
        (UNIMED, 80, False),
    ],
)
def test_acompanhante_segue_a_regra_do_paciente_com_60_anos_ou_mais_ou_menor_de_18(parametros, idade, acompanhante):
    segmentos = contar_diarias(CASO_B, parametros, idade_anos=idade)

    assert [s.acompanhante for s in segmentos] == [acompanhante, acompanhante]


# ----------------------------------------------------------------------------------
# Integração com a leitura do conteúdo (#1118)
# ----------------------------------------------------------------------------------

# A internação com transferência do teste do conteúdo: CTI ADULTO desde 02/10 22:40, o
# último documento no CTI é a prescrição de 05/10 09:00, o primeiro na ENFERMARIA 3 é o
# SAE de 05/10 16:46, alta em 06/10 15:20. Na outra versão, a prescrição de 05/10 é às
# 10:30 e a janela fica inteira depois do vencimento.
JANELA_ATRAVESSA = INTERNACAO_COM_TRANSFERENCIA
JANELA_DEPOIS = [
    prescricao(5, CLEXANE, hora="10:30") if p == prescricao(5, CLEXANE, hora="09:00") else p for p in JANELA_ATRAVESSA
]


@pytest.mark.parametrize(
    ("partes", "motivos"),
    [(JANELA_ATRAVESSA, [["JANELA_ATRAVESSA_O_VENCIMENTO"], []]), (JANELA_DEPOIS, [[], []])],
    ids=["janela atravessa as 10h", "janela toda depois das 10h"],
)
def test_movimentacoes_lidas_do_prontuario_entram_no_contador_sem_conversao(partes, motivos):
    movimentacoes = ler(*partes).movimentacoes

    segmentos = contar_diarias(movimentacoes, ASSIM)

    # CTI: vencimentos de 03, 04 e 05/10 e a extra na origem (transferência depois das 10h);
    # enfermaria: da transferência ao vencimento de 06/10, alta às 15:20 sem diária no dia.
    assert [(s.setor, len(s.diarias)) for s in segmentos] == [("CTI ADULTO", 4), ("ENFERMARIA 3", 1)]
    assert [s.diarias[0].inicio for s in segmentos] == [datetime(2026, 10, 2, 22, 40), datetime(2026, 10, 5, 16, 46)]
    assert [[p.motivo for p in s.validar] for s in segmentos] == motivos


def test_sem_travessao_nem_meia_risca_no_contador_nem_nos_textos_das_pendencias():
    texto = (Path(__file__).parents[1] / "app" / "services" / "contas_medicas" / "diarias.py").read_text(
        encoding="utf-8"
    )

    assert chr(0x2014) not in texto
    assert chr(0x2013) not in texto
