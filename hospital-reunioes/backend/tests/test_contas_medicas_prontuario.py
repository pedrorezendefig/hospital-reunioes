"""Leitura do Prontuário por código, a estrutura (issue #1117, PRD #1113, ADR 0070).

As fixtures são sintéticas, em texto, uma por Família de documento, no layout do
MV (`tests/fixtures/contas_medicas/prontuario/`). A paciente é fictícia: ANTÔNIA
MELO FARIAS, mãe JOSEFA RIBEIRO COSTA, Atendimento 31245; o pronto-socorro que
vem no mesmo arquivo é o Atendimento 31190. PDF real nunca entra em teste.

O montador abaixo faz o papel do extrator: junta as páginas das fixtures na
ordem pedida e põe em cada uma o rodapé global do MV, "Impressão de Prontuário -
Página N de T".
"""

from datetime import date, time
from pathlib import Path

import pytest

from app.services.contas_medicas.prontuario import ErroLeitura, ler_prontuario

FIXTURES = Path(__file__).parent / "fixtures" / "contas_medicas" / "prontuario"
QUEBRA = "<<<QUEBRA DE PÁGINA>>>"
ATENDIMENTO = "31245"


def paginas_da_fixture(nome: str) -> list[str]:
    return [p.strip("\n") for p in (FIXTURES / f"{nome}.txt").read_text(encoding="utf-8").split(QUEBRA)]


def montar(*partes: str | list[str], total_no_rodape: int | None = None) -> list[str]:
    """Cada parte é o nome de uma fixture ou uma lista de páginas já prontas."""
    paginas: list[str] = []
    for parte in partes:
        paginas += paginas_da_fixture(parte) if isinstance(parte, str) else parte
    total = total_no_rodape or len(paginas)
    return [
        f"{texto}\n\n          Impressão de Prontuário - Página {n} de {total}"
        for n, texto in enumerate(paginas, start=1)
    ]


def capa(grupos: dict[str, int]) -> list[str]:
    linhas = [f"Grupo: {grupo:<32}Quantidade: {quantidade}" for grupo, quantidade in grupos.items()]
    return [paginas_da_fixture("capa")[0] + "\n" + "\n".join(linhas)]


# A capa declara o que o corpo traz: sem Parecer parcial pela conferência.
CAPA_QUE_BATE = capa({"PRESCRICAO MEDICA": 1, "EVOLUÇÃO MEDICA": 1, "ANOTAÇÕES DE ENFERMAGEM": 1})

# Capa, o pronto-socorro (páginas 2 e 3) e um documento de cada Família, na ordem
# do arquivo. A posição de cada página está na tabela do teste abaixo.
PRONTUARIO_COMPLETO = [
    CAPA_QUE_BATE,
    "outro_atendimento",
    "admissao_unidade",
    "fisio_admissao",
    "diagnostico",
    "afericao",
    "sae",
    "evolucao",
    "prescricao_medica",
    "doc_editor",
    "avaliacao",
    "diag_enf",
    "anotacao_enf",
    "fisio_resp",
    "fisio_motora",
    "escala",
    "balanco",
    "anexo",
    "digitalizado",
    "nao_reconhecido",
    "ficha_anestesica",
    "checklist_cirurgia",
    "guia_tiss",
    "resumo_alta",
]


def test_cada_familia_vira_um_documento_com_paginas_e_campos_e_o_outro_atendimento_fica_de_fora():
    resultado = ler_prontuario(montar(*PRONTUARIO_COMPLETO), ATENDIMENTO)

    d2, d3, d4, d6 = date(2026, 10, 2), date(2026, 10, 3), date(2026, 10, 4), date(2026, 10, 6)
    # família: (página inicial, página final, atendimento, data, hora, setor)
    esperado = {
        "ADMISSAO_UNIDADE": (4, 4, ATENDIMENTO, d2, time(23, 5), "CTI ADULTO"),
        "FISIO_ADMISSAO": (5, 5, ATENDIMENTO, d2, None, None),
        "DIAGNOSTICO": (6, 6, ATENDIMENTO, d2, None, None),
        "AFERICAO": (7, 7, ATENDIMENTO, d3, time(6, 0), None),
        "SAE": (8, 9, ATENDIMENTO, d3, time(8, 0), "CTI ADULTO"),
        "EVOLUCAO": (10, 10, ATENDIMENTO, d3, time(9, 12), None),
        "PRESCRICAO": (11, 12, ATENDIMENTO, d3, time(10, 15), "CTI ADULTO"),
        "DOC_EDITOR": (13, 13, ATENDIMENTO, d3, time(10, 40), None),
        "AVALIACAO": (14, 14, ATENDIMENTO, d3, time(11, 0), None),
        "DIAG_ENF": (15, 15, ATENDIMENTO, d3, time(12, 0), None),
        "ANOTACAO_ENF": (16, 16, ATENDIMENTO, d3, time(14, 30), None),
        # sem atendimento no cabeçalho: pertence ao da vizinhança
        "FISIO_RESP": (17, 17, ATENDIMENTO, d3, None, None),
        "FISIO_MOTORA": (18, 18, ATENDIMENTO, d3, time(16, 20), None),
        "ESCALA": (19, 19, ATENDIMENTO, d3, time(7, 30), None),
        # o leito do balanço é o box (BOX-07); o setor é a unidade
        "BALANCO": (20, 21, ATENDIMENTO, d3, None, "CTI ADULTO"),
        "ANEXO": (22, 22, ATENDIMENTO, d3, None, None),
        "DIGITALIZADO": (23, 23, ATENDIMENTO, d3, time(9, 0), None),
        # sem data própria: herda a do documento vizinho
        "NAO_RECONHECIDO": (24, 24, ATENDIMENTO, d3, time(9, 0), None),
        "FICHA_ANESTESICA": (25, 25, ATENDIMENTO, d4, None, None),
        "CHECKLIST_CIRURGIA": (26, 26, ATENDIMENTO, d4, time(11, 5), None),
        "GUIA_TISS": (27, 27, ATENDIMENTO, d4, time(11, 5), None),
        "RESUMO_ALTA": (28, 28, ATENDIMENTO, d6, time(15, 20), None),
    }
    lidos = {
        d.familia: (d.pagina_inicial, d.pagina_final, d.atendimento, d.data, d.hora, d.setor)
        for d in resultado.documentos
    }
    assert lidos == esperado
    assert len(resultado.documentos) == len(esperado)
    assert not {2, 3} & {p for d in resultado.documentos for p in d.paginas}
    assert resultado.tipo_impressao == "Completa"
    assert resultado.grupos_da_capa == {"PRESCRICAO MEDICA": 1, "EVOLUÇÃO MEDICA": 1, "ANOTAÇÕES DE ENFERMAGEM": 1}
    conselhos = {d.familia: d.conselho for d in resultado.documentos if d.conselho}
    assert conselhos == {
        "EVOLUCAO": "CRM",
        "DOC_EDITOR": "CRM",
        "ANOTACAO_ENF": "COREN",
        "FISIO_MOTORA": "CREFITO",
        "ESCALA": "COREN",
        "DIGITALIZADO": "COREN",
        "CHECKLIST_CIRURGIA": "COREN",
    }


def test_rodape_com_total_diferente_do_numero_de_paginas_e_arquivo_incompleto():
    paginas = montar("capa", "evolucao", "anotacao_enf", total_no_rodape=5)

    with pytest.raises(ErroLeitura, match="arquivo incompleto"):
        ler_prontuario(paginas, ATENDIMENTO)


def test_rodape_com_total_igual_ao_numero_de_paginas_le_o_prontuario():
    paginas = montar("capa", "evolucao", "anotacao_enf")

    assert ler_prontuario(paginas, ATENDIMENTO).total_paginas == 3
