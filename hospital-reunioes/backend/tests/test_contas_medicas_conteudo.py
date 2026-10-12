"""Leitura do Prontuário por código: o conteúdo (issue #1118, PRD #1113, ADR 0070).

Sobre os documentos que a estrutura monta (#1117), o código lê a prescrição, o
balanço hídrico, as glicemias, a internação e a alta, o setor de cada dia e os
papéis do centro cirúrgico. As fixtures são sintéticas, em texto, no layout do
MV (`tests/fixtures/contas_medicas/conteudo/` e, para as Famílias que a
estrutura já tinha, `.../prontuario/`). A paciente é fictícia, Atendimento 31245.

O caminho testado é o do pipeline: `ler_prontuario` monta os documentos e
`ler_conteudo` lê as páginas de cada um.
"""

from datetime import date
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
