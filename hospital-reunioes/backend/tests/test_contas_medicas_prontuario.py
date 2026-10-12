"""Leitura do Prontuário por código, a estrutura (issue #1117, PRD #1113, ADR 0070).

As fixtures são sintéticas, em texto, uma por Família de documento, no layout do
MV (`tests/fixtures/contas_medicas/prontuario/`). A paciente é fictícia: ANTÔNIA
MELO FARIAS, mãe JOSEFA RIBEIRO COSTA, Atendimento 31245; o pronto-socorro que
vem no mesmo arquivo é o Atendimento 31190. PDF real nunca entra em teste.

O montador abaixo faz o papel do extrator: junta as páginas das fixtures na
ordem pedida e põe em cada uma o rodapé global do MV, "Impressão de Prontuário -
Página N de T".
"""

import re
import unicodedata
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


def test_capa_que_declara_grupo_essencial_que_o_corpo_nao_traz_da_parecer_parcial_com_grupo_e_quantidade():
    sem_prescricao_nem_evolucao = capa({"PRESCRICAO MEDICA": 40, "EVOLUÇÃO MEDICA": 12, "ANOTAÇÕES DE ENFERMAGEM": 1})
    paginas = montar(sem_prescricao_nem_evolucao, "sae", "anotacao_enf")

    resultado = ler_prontuario(paginas, ATENDIMENTO)

    assert resultado.parecer_parcial == (
        "O arquivo não trouxe: prescrição médica (40 na capa), evolução médica (12 na capa).",
    )


def test_capa_que_bate_com_o_corpo_nao_da_parecer_parcial():
    paginas = montar(CAPA_QUE_BATE, "evolucao", "prescricao_medica", "anotacao_enf")

    assert ler_prontuario(paginas, ATENDIMENTO).parecer_parcial == ()


def sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def aparece(valor: str, texto: str) -> bool:
    """Procura sem acento, sem caixa e com limite de palavra: "MELO" não está em "MELOXICAM"."""
    alvo = re.escape(sem_acento(valor).upper()).replace(r"\ ", r"\s+")
    return re.search(rf"(?<!\w){alvo}(?!\w)", sem_acento(texto).upper()) is not None


def texto_de_saida(prontuario) -> str:
    return "\n".join(linha for documento in prontuario.documentos for linha in documento.linhas)


# Cada valor da capa, cada palavra do nome e o que a ouvidoria já reconhecia.
VALORES_PESSOAIS = {
    "nome completo": "ANTÔNIA MELO FARIAS",
    "nome truncado": "ANTONIA MELO",
    "primeira palavra do nome": "ANTÔNIA",
    "segunda palavra do nome": "MELO",
    "última palavra do nome": "FARIAS",
    "nome da mãe": "JOSEFA RIBEIRO COSTA",
    "CPF": "529.982.247-25",
    "data de nascimento": "14/03/1951",
    "RG": "20.481.337-6",
    "carteira": "0081234500098765432",
    "CPF do médico na assinatura": "111.444.777-35",
    "telefone": "98765-4321",
}


def test_o_corpo_da_fixture_traz_cada_valor_pessoal():
    """Guarda do teste de baixo: sem isto ele passaria sobre um texto que nunca teve o dado."""
    entrada = "\n".join(montar(*PRONTUARIO_COMPLETO)[3:])
    for nome, valor in VALORES_PESSOAIS.items():
        assert aparece(valor, entrada), nome


def test_nenhum_valor_pessoal_sobrevive_no_texto_de_saida_e_o_nome_vira_paciente():
    resultado = ler_prontuario(montar(*PRONTUARIO_COMPLETO), ATENDIMENTO)
    saida = texto_de_saida(resultado)

    vazados = [nome for nome, valor in VALORES_PESSOAIS.items() if aparece(valor, saida)]
    assert vazados == []
    assert "Nome do paciente: PACIENTE" in saida
    assert "Paciente PACIENTE, 75 anos, segue em ventilação espontânea" in saida
    assert "acompanhou a internação de PACIENTE." in saida


def test_palavra_do_nome_que_e_prefixo_de_outra_palavra_nao_apaga_a_outra():
    # MELO, sobrenome da paciente, é o começo de MELOXICAM, que a análise precisa ler
    resultado = ler_prontuario(montar(*PRONTUARIO_COMPLETO), ATENDIMENTO)

    assert "Iniciado MELOXICAM 15 MG por dor lombar." in texto_de_saida(resultado)


def test_da_identificacao_da_capa_sai_so_o_rotulo_e_a_idade():
    resultado = ler_prontuario(montar(*PRONTUARIO_COMPLETO), ATENDIMENTO)

    # nascida em 14/03/1951; o primeiro documento do Atendimento é de 02/10/2026
    assert (resultado.paciente_rotulo, resultado.idade_anos) == ("Antônia F.", 75)


def evolucao_em(data_e_hora: str) -> list[str]:
    return [paginas_da_fixture("evolucao")[0].replace("03/10/2026 09:12", data_e_hora)]


def test_documentos_saem_pela_data_de_cada_um_e_nao_pela_ordem_das_paginas():
    # página 2 é de 05/10, página 3 de 03/10 e página 4 de 04/10
    paginas = montar("capa", evolucao_em("05/10/2026 08:00"), "anotacao_enf", evolucao_em("04/10/2026 09:00"))

    resultado = ler_prontuario(paginas, ATENDIMENTO)

    assert [(d.pagina_inicial, d.data) for d in resultado.documentos] == [
        (3, date(2026, 10, 3)),
        (4, date(2026, 10, 4)),
        (2, date(2026, 10, 5)),
    ]


def test_rodape_com_total_diferente_do_numero_de_paginas_e_arquivo_incompleto():
    paginas = montar("capa", "evolucao", "anotacao_enf", total_no_rodape=5)

    with pytest.raises(ErroLeitura, match="arquivo incompleto"):
        ler_prontuario(paginas, ATENDIMENTO)


def test_rodape_com_total_igual_ao_numero_de_paginas_le_o_prontuario():
    paginas = montar("capa", "evolucao", "anotacao_enf")

    assert ler_prontuario(paginas, ATENDIMENTO).total_paginas == 3
