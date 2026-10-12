"""Leitura do Prontuário por código: o conteúdo (issue #1118, PRD #1113, ADR 0070).

Sobre os documentos que a estrutura monta (#1117), o código lê a prescrição, o
balanço hídrico, as glicemias, a internação e a alta, o setor de cada dia e os
papéis do centro cirúrgico. As fixtures são sintéticas, em texto, no layout do
MV (`tests/fixtures/contas_medicas/conteudo/` e, para as Famílias que a
estrutura já tinha, `.../prontuario/`). A paciente é fictícia, Atendimento 31245.

O caminho testado é o do pipeline: `ler_prontuario` monta os documentos e
`ler_conteudo` lê as páginas de cada um.
"""

from datetime import date, datetime
from pathlib import Path

from app.services.contas_medicas.conteudo import ler_conteudo
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
