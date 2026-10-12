"""Leitura do Prontuário por código: o conteúdo (issue #1118, PRD #1113, ADR 0070).

Sobre os documentos que a estrutura monta (#1117), o código lê a prescrição, o
balanço hídrico, as glicemias, a internação e a alta, o setor de cada dia e os
papéis do centro cirúrgico. As fixtures são sintéticas, em texto, no layout do
MV (`tests/fixtures/contas_medicas/conteudo/` e, para as Famílias que a
estrutura já tinha, `.../prontuario/`). A paciente é fictícia, Atendimento 31245.

O caminho testado é o do pipeline: `ler_prontuario` monta os documentos e
`ler_conteudo` lê as páginas de cada um.
"""

from datetime import date, datetime, time
from pathlib import Path

import pytest

from app.services.contas_medicas.conteudo import Movimentacao, ler_conteudo
from app.services.contas_medicas.prontuario import ler_prontuario

FIXTURES = Path(__file__).parent / "fixtures" / "contas_medicas"
QUEBRA = "<<<QUEBRA DE PÁGINA>>>"
ATENDIMENTO = "31245"


def paginas_da_fixture(nome: str) -> list[str]:
    """`nome` é `pasta/arquivo`, sem a extensão."""
    return [p.strip("\n") for p in (FIXTURES / f"{nome}.txt").read_text(encoding="utf-8").split(QUEBRA)]


def montar(*partes: str | list[str]) -> list[str]:
    """Cada parte é uma fixture ou uma lista de páginas prontas; cada página ganha o rodapé global do MV."""
    paginas: list[str] = []
    for parte in partes:
        paginas += paginas_da_fixture(parte) if isinstance(parte, str) else parte
    return [
        f"{texto}\n\n          Impressão de Prontuário - Página {n} de {len(paginas)}"
        for n, texto in enumerate(paginas, start=1)
    ]


def ler(*partes: str | list[str]):
    paginas = montar(*partes)
    return ler_conteudo(paginas, ler_prontuario(paginas, ATENDIMENTO))


# ----------------------------------------------------------------------------------
# Prescrição
# ----------------------------------------------------------------------------------


def test_cada_item_da_prescricao_sai_com_os_campos_lidos_da_tabela():
    # a capa ocupa a página 1: a página do item é a do PDF, a que o Guia mostra
    (prescricao,) = ler("prontuario/capa", "conteudo/prescricao").prescricoes
    itens = {item.numero: item for item in prescricao.itens}

    assert prescricao.data == date(2026, 10, 20)
    assert prescricao.subtipo == "PRESCRIÇÃO MÉDICA"
    assert sorted(itens) == list(range(1, 10))
    assert [itens[n].secao for n in (1, 7, 8)] == [
        "MEDICAMENTOS NORMAIS",
        "MEDICAMENTOS ANTIBIOTICOS",
        "EXAMES LABORATORIAL",
    ]

    pantocal = itens[1]
    assert pantocal.nome == "PANTOCAL 40MG EV FR/AMP (PANTOPRAZOL)"
    assert pantocal.generico == "PANTOPRAZOL"
    assert pantocal.dose == "1 FRASCO/AM"
    assert pantocal.frequencia == "24HS/24HS"
    assert pantocal.via == "EV"
    assert pantocal.horarios == ("06",)
    assert pantocal.doses_por_dia == 1
    assert pantocal.se_necessario is False
    assert pantocal.pagina == 2

    # S na coluna SN: se necessário, e a observação sem o rótulo
    dipirona = itens[2]
    assert (dipirona.se_necessario, dipirona.doses_por_dia, dipirona.obs) == (True, 4, "EM CASO DE DOR OU FEBRE")

    # 8HS/8HS sem horário aprazado: 3 doses; o componente vem junto
    ondansetrona = itens[3]
    assert (ondansetrona.frequencia, ondansetrona.doses_por_dia) == ("8HS/8HS", 3)
    assert ondansetrona.componentes == ("SERINGA DESCARTAVEL 10ML 1 UNIDADE",)

    # horários aprazados têm prioridade sobre a frequência: 6HS/6HS daria 4
    assert itens[4].horarios == ("06", "14", "22")
    assert itens[4].doses_por_dia == 3

    # ACM: se necessário, sem número de doses
    assert (itens[5].se_necessario, itens[5].doses_por_dia) == (True, None)

    # nome em duas linhas, princípio ativo na segunda, suspenso
    clexane = itens[6]
    assert clexane.nome == "CLEXANE 40MG/0,4ML SER PREENCH (ENOXAPARINA)"
    assert clexane.generico == "ENOXAPARINA"
    assert (clexane.via, clexane.suspenso) == ("SC", True)
    assert [itens[n].suspenso for n in (1, 2, 3, 4, 5, 7, 8, 9)] == [False] * 8

    # o dia do antimicrobiano sai do nome
    ceftriaxona = itens[7]
    assert ceftriaxona.nome == "CEFTRIAXONA 1G FR/AMP"
    assert ceftriaxona.componentes == ("AGUA DESTILADA 10ML 1 AMPOLA",)

    # exame: pedido lido, preparo descartado, na segunda página do documento
    hemograma = itens[8]
    assert (hemograma.nome, hemograma.pedido, hemograma.obs) == ("HEMOGRAMA COMPLETO", "3014", "")
    assert hemograma.pagina == 3
    # quem assina, na linha acima do CRM, não é continuação do último item
    assert (itens[9].nome, itens[9].pedido) == ("UREIA", "3015")



def test_exames_pedidos_saem_com_nome_numero_do_pedido_data_e_pagina():
    exames = ler("prontuario/capa", "conteudo/prescricao").exames_pedidos

    assert [(e.nome, e.pedido, e.data, e.pagina) for e in exames] == [
        ("HEMOGRAMA COMPLETO", "3014", date(2026, 10, 20), 3),
        ("UREIA", "3015", date(2026, 10, 20), 3),
    ]


CABECALHO_DA_TABELA = (
    "MEDICAMENTOS NORMAIS                       Dose Padrão     Duração   Frequência   SN   Apl   Datas/Horários"
)


def prescricao(dia: int, *itens: str, hora: str = "10:15", unidade: str = "CTI ADULTO", leito: str = "CTI-04"):
    """Uma prescrição médica de uma página, de outubro de 2026."""
    return [
        "\n".join(
            [
                "HOSPITAL SÃO MATHEUS                                                    Página: 1 / 1",
                f"Prescrição.: {778800 + dia}  Data: {dia:02d}/10/2026 {hora}",
                f"Atendimento: {ATENDIMENTO}",
                f"Unid. Int..: {unidade}   Leito..: {leito}   Cobertura: UTI ADULTO GERAL",
                "Internação.: 02/10/2026 22:40",
                "PRESCRIÇÃO MÉDICA",
                CABECALHO_DA_TABELA,
                *itens,
            ]
        )
    ]


CEFTRIAXONA = " 1 ({}) CEFTRIAXONA 1G FR/AMP           2 FRASCO/AM     10 DIAS   {}"
CLEXANE = " 2 CLEXANE 40MG/0,4ML SER PREENCH          1 SERINGA                 24HS/24HS          SC    . 22"
CLEXANE_SUSPENSO = CLEXANE + "\n                                           Suspenso dia.: 04"


def test_o_mesmo_item_em_tres_dias_vira_um_registro_com_as_doses_de_cada_dia_e_o_suspenso_fica_fora_do_dia():
    conteudo = ler(
        prescricao(3, CEFTRIAXONA.format("D2/10", "12HS/12HS          EV"), CLEXANE),
        prescricao(4, CEFTRIAXONA.format("D3/10", "12HS/12HS          EV    . 08 . 20"), CLEXANE_SUSPENSO),
        prescricao(5, CEFTRIAXONA.format("D4/10", "24HS/24HS          EV    . 10"), CLEXANE),
    )
    registros = {r.nome: r for r in conteudo.prescricao_consolidada}

    assert sorted(registros) == ["CEFTRIAXONA 1G FR/AMP", "CLEXANE 40MG/0,4ML SER PREENCH"]
    ceftriaxona = registros["CEFTRIAXONA 1G FR/AMP"]
    assert ceftriaxona.doses_por_dia == {date(2026, 10, 3): 2, date(2026, 10, 4): 2, date(2026, 10, 5): 1}
    assert (ceftriaxona.subtipo, ceftriaxona.secao) == ("PRESCRIÇÃO MÉDICA", "MEDICAMENTOS NORMAIS")
    assert ceftriaxona.paginas == (1, 2, 3)
    assert registros["CLEXANE 40MG/0,4ML SER PREENCH"].doses_por_dia == {date(2026, 10, 3): 1, date(2026, 10, 5): 1}


# ----------------------------------------------------------------------------------
# Balanço hídrico e glicemias
# ----------------------------------------------------------------------------------


def afericao(hora: str, *, com_glicemia: bool = True) -> list[str]:
    """A aferição da estrutura (#1117), na hora pedida, com ou sem a linha de glicemia."""
    (texto,) = paginas_da_fixture("prontuario/afericao")
    texto = texto.replace("03/10/2026 06:00", f"03/10/2026 {hora}")
    if not com_glicemia:
        texto = "\n".join(linha for linha in texto.split("\n") if not linha.startswith("GLICEMIA"))
    return [texto]


def test_balanco_vira_itens_com_via_lancamentos_e_total_conta_as_glicemias_e_descarta_a_pagina_2():
    (balanco,) = ler("conteudo/balanco").balancos

    assert (balanco.data, balanco.setor, balanco.paginas) == (date(2026, 10, 3), "CTI ADULTO", (1, 2))
    assert [(g.item, g.via, g.lancamentos, g.total) for g in balanco.ganhos] == [
        ("SORO FISIOLOGICO 0,9%", "EV", 5, 105),
        ("DIETA ENTERAL", "SNE", 3, 150),
    ]
    # os usuários da página 2 (COREN no fim da linha) não viram perda
    assert [(p.item, p.total) for p in balanco.perdas] == [("DIURESE", 250)]
    assert balanco.glicemias == 4


def test_glicemias_saem_por_dia_de_cada_fonte_com_as_paginas():
    conteudo = ler("conteudo/balanco", afericao("06:00"), afericao("12:00"), afericao("18:00", com_glicemia=False))

    assert [(g.data, g.familia, g.quantidade, g.paginas) for g in conteudo.glicemias] == [
        (date(2026, 10, 3), "AFERICAO", 2, (3, 4)),
        (date(2026, 10, 3), "BALANCO", 4, (1,)),
    ]


# ----------------------------------------------------------------------------------
# Internação e alta
# ----------------------------------------------------------------------------------


def resumo_de_alta(data_de_atendimento: str = "02/10/2026 22:40") -> list[str]:
    (texto,) = paginas_da_fixture("prontuario/resumo_alta")
    return [texto.replace("DATA DE ATENDIMENTO: 02/10/2026 22:40", f"DATA DE ATENDIMENTO: {data_de_atendimento}")]


def test_internacao_vem_da_prescricao_e_a_alta_com_o_motivo_vem_do_resumo_de_alta():
    # o resumo diz 21:00 só para mostrar de qual campo a internação saiu
    internacao = ler(
        "prontuario/admissao_unidade", prescricao(3, CLEXANE), resumo_de_alta("02/10/2026 21:00")
    ).internacao

    assert internacao.entrada == datetime(2026, 10, 2, 22, 40)
    assert internacao.alta == datetime(2026, 10, 6, 15, 20)
    assert internacao.motivo_alta == "MELHORADO"
    assert (internacao.acomodacao_na_admissao, internacao.leito_na_admissao) == ("UTI ADULTO", "CTI-04")


def test_sem_prescricao_a_internacao_vem_da_data_de_atendimento_do_resumo_de_alta():
    internacao = ler(resumo_de_alta("02/10/2026 21:00")).internacao

    assert internacao.entrada == datetime(2026, 10, 2, 21, 0)
    assert internacao.alta == datetime(2026, 10, 6, 15, 20)


# ----------------------------------------------------------------------------------
# Setor por dia e movimentações
# ----------------------------------------------------------------------------------


def sae(data_e_hora: str, setor: str) -> list[str]:
    paginas = paginas_da_fixture("prontuario/sae")
    return [
        p.replace("Data do Hist.: 03/10/2026 08:00", f"Data do Hist.: {data_e_hora}").replace(
            "Setor: CTI ADULTO", f"Setor: {setor}"
        )
        for p in paginas
    ]


# Admissão no CTI em 02/10 23:05; o leito muda no balanço (BOX-07) e na prescrição de
# 04/10 (CTI-06) sem mudar a unidade; o último documento no CTI é a prescrição de
# 05/10 09:00 e o primeiro na enfermaria é o SAE de 05/10 16:46; alta em 06/10 15:20.
INTERNACAO_COM_TRANSFERENCIA = [
    "prontuario/admissao_unidade",
    prescricao(3, CLEXANE, hora="10:15"),
    "conteudo/balanco",
    prescricao(4, CLEXANE, hora="10:20", leito="CTI-06"),
    prescricao(5, CLEXANE, hora="09:00"),
    sae("05/10/2026 16:46", "ENFERMARIA 3"),
    prescricao(6, CLEXANE, hora="10:00", unidade="ENFERMARIA 3", leito="305"),
    resumo_de_alta(),
]


def test_setor_de_cada_dia_vem_da_unidade_e_o_leito_que_muda_nao_e_transferencia():
    conteudo = ler(*INTERNACAO_COM_TRANSFERENCIA)

    assert conteudo.setor_por_dia == {
        date(2026, 10, 2): ("CTI ADULTO",),
        date(2026, 10, 3): ("CTI ADULTO",),
        date(2026, 10, 4): ("CTI ADULTO",),
        date(2026, 10, 5): ("CTI ADULTO", "ENFERMARIA 3"),
        date(2026, 10, 6): ("ENFERMARIA 3",),
    }
    assert [m.tipo for m in conteudo.movimentacoes] == ["INTERNACAO", "TRANSFERENCIA_SETOR", "ALTA"]


def test_mudanca_de_unidade_vira_transferencia_com_janela_do_ultimo_documento_no_setor_antigo_ao_primeiro_no_novo():
    internacao, transferencia, alta = ler(*INTERNACAO_COM_TRANSFERENCIA).movimentacoes

    assert (internacao.data_hora, internacao.setor) == (datetime(2026, 10, 2, 22, 40), "CTI ADULTO")
    assert transferencia.janela == (datetime(2026, 10, 5, 9, 0), datetime(2026, 10, 5, 16, 46))
    assert (transferencia.data_hora, transferencia.setor) == (datetime(2026, 10, 5, 16, 46), "ENFERMARIA 3")
    assert (alta.data_hora, alta.setor, alta.janela) == (datetime(2026, 10, 6, 15, 20), "ENFERMARIA 3", None)


@pytest.mark.parametrize(
    ("motivo", "tipo"),
    [("MELHORADO", "ALTA"), ("ÓBITO", "OBITO"), ("TRANSFERÊNCIA PARA OUTRO HOSPITAL", "TRANSFERENCIA_HOSPITAL")],
)
def test_a_saida_segue_o_motivo_da_alta(motivo, tipo):
    resumo = [p.replace("MOTIVO DA ALTA: MELHORADO", f"MOTIVO DA ALTA: {motivo}") for p in resumo_de_alta()]

    saida = ler(prescricao(3, CLEXANE), resumo).movimentacoes[-1]

    assert (saida.tipo, saida.data_hora) == (tipo, datetime(2026, 10, 6, 15, 20))



def test_movimentacoes_saem_no_formato_de_entrada_do_contador_de_diarias():
    """Entrada do contador (#1115 e `referencia-diarias.mjs`): em ordem de data e hora, a
    primeira é a INTERNACAO, a última é a saída, cada uma com o setor. O registro feito
    depois da alta (SAE em outro setor às 18:00) não vira transferência depois da saída,
    que o contador recusa como fora de ordem."""
    movimentacoes = ler(
        "prontuario/admissao_unidade",
        prescricao(3, CLEXANE),
        resumo_de_alta(),
        sae("06/10/2026 18:00", "ENFERMARIA 3"),
    ).movimentacoes

    assert movimentacoes == (
        Movimentacao("INTERNACAO", datetime(2026, 10, 2, 22, 40), "CTI ADULTO"),
        Movimentacao("ALTA", datetime(2026, 10, 6, 15, 20), "CTI ADULTO"),
    )

# ----------------------------------------------------------------------------------
# Centro cirúrgico
# ----------------------------------------------------------------------------------


def test_descricao_cirurgica_devolve_a_principal_e_as_adicionais_com_codigo_horarios_peca_e_consignados():
    (descricao,) = ler("conteudo/descricao_cirurgica").descricoes_cirurgicas

    # a principal aparece também na tabela: 1 principal e 4 adicionais, 5 códigos
    assert [(p.codigo, p.principal) for p in descricao.procedimentos] == [
        ("31005497", True),
        ("31005519", False),
        ("31009158", False),
        ("30715016", False),
        ("40813363", False),
    ]
    assert descricao.procedimentos[0].descricao == "COLECISTECTOMIA COM COLANGIOGRAFIA"
    assert (descricao.inicio, descricao.fim) == (datetime(2026, 10, 4, 17, 40), datetime(2026, 10, 4, 20, 0))
    assert descricao.anatomopatologico == "VESICULA BILIAR"
    assert descricao.consignados == "CLIPS DE TITANIO MEDIO, 2 CARTUCHOS"
    assert descricao.paginas == (1,)


def test_ficha_anestesica_devolve_horarios_gases_com_minutos_medicamentos_com_quantidade_e_monitorizacao():
    (ficha,) = ler("conteudo/ficha_anestesica").fichas_anestesicas

    assert (ficha.data, ficha.inicio, ficha.fim) == (date(2026, 10, 4), time(16, 50), time(19, 20))
    assert ficha.tecnica == "GERAL BALANCEADA"
    assert [(g.gas, g.litros_por_minuto, g.minutos) for g in ficha.gases] == [("O2", 2, 150), ("AR", 2, 150)]
    assert ficha.volatil == "sevoflurano 2,5%"
    # um marcado no campo, outro anotado ao lado pelo anestesista
    assert [(m.nome, m.quantidade, m.anotado) for m in ficha.medicamentos] == [
        ("Alfentanila", 1, False),
        ("sugamadex", 1, True),
    ]
    assert ficha.monitorizacao == ("Cardioscopia", "Oximetria", "PNI")


def test_guia_tiss_devolve_o_procedimento_solicitado_e_a_acomodacao_autorizada():
    (guia,) = ler("prontuario/guia_tiss").guias_tiss

    assert (guia.procedimento_codigo, guia.procedimento_descricao) == ("10102019", "VISITA HOSPITALAR")
    assert guia.acomodacao_autorizada == "APARTAMENTO"


MODULOS = Path(__file__).parents[1] / "app" / "services" / "contas_medicas"


@pytest.mark.parametrize("arquivo", ["conteudo.py", "prescricao.py", "cirurgia.py"])
def test_sem_travessao_nem_meia_risca_no_codigo(arquivo):
    texto = (MODULOS / arquivo).read_text(encoding="utf-8")

    assert chr(0x2014) not in texto
    assert chr(0x2013) not in texto
