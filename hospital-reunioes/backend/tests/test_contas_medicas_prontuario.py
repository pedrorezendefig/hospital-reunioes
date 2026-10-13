"""Leitura do Prontuário por código, a estrutura (issue #1117, PRD #1113, ADR 0070).

As fixtures são sintéticas, em texto, uma por Família de documento, no layout do
MV (`tests/fixtures/contas_medicas/prontuario/`). A paciente é fictícia: ANTÔNIA
MELO FARIAS, mãe JOSEFA RIBEIRO COSTA, Atendimento 31245; o pronto-socorro que
vem no mesmo arquivo é o Atendimento 31190. PDF real nunca entra em teste.

O montador abaixo faz o papel do extrator: junta as páginas das fixtures na
ordem pedida e põe em cada uma o rodapé global do MV, "Impressão de Prontuário -
Página N de T".
"""

import logging
import re
import unicodedata
from datetime import date, time
from pathlib import Path

import pytest

from app.services.contas_medicas.prontuario import MARCA_DO_OCR, ErroLeitura, ler_prontuario

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
    # sem pista no corpo e com 7 dígitos: só a troca pelo valor da capa os apaga
    "data de nascimento": "14/03/1951",
    "RG": "20.481.337-6",
    "carteira": "0817734",
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


def sae_em(data_e_hora: str) -> list[str]:
    primeira, segunda = paginas_da_fixture("sae")
    return [primeira.replace("03/10/2026 08:00", data_e_hora), segunda]


def test_sae_igual_ao_anterior_do_mesmo_tipo_vira_uma_linha_so():
    # o de 04/10 vem antes no arquivo; a comparação é com a véspera, depois de ordenar
    paginas = montar("capa", sae_em("04/10/2026 08:00"), sae_em("03/10/2026 08:00"))

    primeiro, segundo = ler_prontuario(paginas, ATENDIMENTO).documentos

    assert (primeiro.data, segundo.data) == (date(2026, 10, 3), date(2026, 10, 4))
    assert "Eliminações: sonda vesical de demora com diurese clara. Lesão por pressão sacral grau 2." in primeiro.linhas
    assert segundo.linhas == ("(igual ao documento anterior do mesmo tipo)",)


def test_prescricao_de_enfermagem_que_mudou_um_item_manda_so_a_diferenca():
    vespera = paginas_da_fixture("prescricao_enfermagem")
    dia_seguinte = [
        vespera[0]
        .replace("03/10/2026 07:00", "04/10/2026 07:00")
        .replace("COM HIDROCOLOIDE      ", "COM ALGINATO DE CÁLCIO")
    ]

    _, segunda = ler_prontuario(montar("capa", vespera, dia_seguinte), ATENDIMENTO).documentos

    assert segunda.linhas == (
        "(em relação ao anterior do mesmo tipo)",
        "+ 4  CURATIVO EM REGIÃO SACRAL COM ALGINATO DE CÁLCIO  . 10",
        "- 4  CURATIVO EM REGIÃO SACRAL COM HIDROCOLOIDE  . 10",
    )


def test_pagina_sem_texto_e_listada_e_ate_10_por_cento_nao_da_parecer_parcial():
    # 25 páginas do Atendimento (28 menos a capa e as 2 do pronto-socorro), 1 digitalizada
    resultado = ler_prontuario(montar(*PRONTUARIO_COMPLETO), ATENDIMENTO)

    assert resultado.paginas_sem_texto == (23,)
    assert resultado.parecer_parcial == ()


def test_mais_de_10_por_cento_das_paginas_sem_texto_da_parecer_parcial():
    # página 3 é imagem pura (só o rodapé global); página 4 só tem o bloco de assinatura
    paginas = montar(CAPA_QUE_BATE, "evolucao", [""], "digitalizado", "prescricao_medica", "anotacao_enf")

    resultado = ler_prontuario(paginas, ATENDIMENTO)

    assert resultado.paginas_sem_texto == (3, 4)
    assert resultado.parecer_parcial == ("O arquivo tem 2 de 6 páginas sem texto, mais de 10%.",)


def test_nenhuma_linha_de_log_nem_a_mensagem_de_erro_carrega_texto_do_prontuario(caplog):
    caplog.set_level(logging.DEBUG)
    completo = montar(*PRONTUARIO_COMPLETO)
    incompleto = montar(*PRONTUARIO_COMPLETO, total_no_rodape=99)
    trechos = {linha.strip() for pagina in completo for linha in pagina.split("\n") if len(linha.strip()) >= 12}

    ler_prontuario(completo, ATENDIMENTO)
    with pytest.raises(ErroLeitura) as erro:
        ler_prontuario(incompleto, ATENDIMENTO)

    escrito = [registro.getMessage() for registro in caplog.records] + [str(erro.value)]
    assert [t for t in trechos if any(t in mensagem for mensagem in escrito)] == []


MODULOS = Path(__file__).parents[1] / "app" / "services" / "contas_medicas"


@pytest.mark.parametrize("arquivo", ["prontuario.py", "desidentificacao.py"])
def test_sem_travessao_nem_meia_risca_no_codigo_nem_nas_frases_que_a_faturista_ve(arquivo):
    """As frases do Parecer parcial e do erro moram no código (ADR 0013)."""
    texto = (MODULOS / arquivo).read_text(encoding="utf-8")

    assert chr(0x2014) not in texto
    assert chr(0x2013) not in texto


def test_so_o_texto_livre_vai_para_a_ia_e_o_resto_sai_sem_linhas():
    # sem valor de cobrança: AVALIACAO, DIAG_ENF, CHECKLIST_CIRURGIA, ESCALA, DIAGNOSTICO,
    # ANEXO e DIGITALIZADO; o código estrutura AFERICAO, BALANCO, FICHA_ANESTESICA,
    # GUIA_TISS e a prescrição médica pelas páginas
    resultado = ler_prontuario(montar(*PRONTUARIO_COMPLETO), ATENDIMENTO)

    assert {d.familia for d in resultado.documentos if d.linhas} == {
        "ADMISSAO_UNIDADE",
        "FISIO_ADMISSAO",
        "SAE",
        "EVOLUCAO",
        "DOC_EDITOR",
        "ANOTACAO_ENF",
        "FISIO_RESP",
        "FISIO_MOTORA",
        "NAO_RECONHECIDO",
        "RESUMO_ALTA",
    }


@pytest.mark.parametrize(
    ("fixture", "subtipo_que_vai", "subtipo_descartado"),
    [
        ("sae", "EXAME FISICO SAE GERAL", "HISTORICO DE ENFERMAGEM"),
        ("evolucao", "EVOLUÇÃO MEDICA", "EVOLUÇÃO SERVICO SOCIAL"),
        ("doc_editor", "ANAMNESE UTI", "RECEITUÁRIO"),
    ],
)
def test_subtipo_sem_valor_de_cobranca_sai_sem_linhas(fixture, subtipo_que_vai, subtipo_descartado):
    paginas = [p.replace(subtipo_que_vai, subtipo_descartado) for p in paginas_da_fixture(fixture)]

    (documento,) = ler_prontuario(montar("capa", paginas), ATENDIMENTO).documentos

    assert documento.linhas == ()


def test_rodape_com_total_diferente_do_numero_de_paginas_e_arquivo_incompleto():
    paginas = montar("capa", "evolucao", "anotacao_enf", total_no_rodape=5)

    with pytest.raises(ErroLeitura, match="arquivo incompleto"):
        ler_prontuario(paginas, ATENDIMENTO)


def test_rodape_com_total_igual_ao_numero_de_paginas_le_o_prontuario():
    paginas = montar("capa", "evolucao", "anotacao_enf")

    assert ler_prontuario(paginas, ATENDIMENTO).total_paginas == 3


# OCR das páginas digitalizadas (issue #1191): o extrator põe o texto da imagem
# depois do que o `pdftotext` leu, atrás da marca.
TERMO_LIDO_POR_OCR = (
    "TERMO DE CONSENTIMENTO PARA TRANSFUSÃO DE SANGUE\n"
    "Eu, ANTÔNIA MELO FARIAS, autorizo a transfusão de concentrado de hemácias."
)


def com_ocr(pagina: str, lido: str) -> str:
    return f"{pagina}\n{MARCA_DO_OCR}\n{lido}\n"


def test_pagina_digitalizada_lida_por_ocr_vai_a_ia_como_digitalizado_e_deixa_de_contar_como_sem_texto():
    paginas = montar(CAPA_QUE_BATE, "evolucao", [""], "digitalizado", "prescricao_medica", "anotacao_enf")
    paginas[2] = com_ocr(paginas[2], TERMO_LIDO_POR_OCR)

    resultado = ler_prontuario(paginas, ATENDIMENTO)

    (termo,) = [d for d in resultado.documentos if d.paginas == (3,)]
    assert termo.familia == "DIGITALIZADO"
    assert termo.linhas == (
        "TERMO DE CONSENTIMENTO PARA TRANSFUSÃO DE SANGUE",
        "Eu, PACIENTE, autorizo a transfusão de concentrado de hemácias.",
    )
    assert resultado.paginas_sem_texto == (4,)
    assert resultado.parecer_parcial == ("O arquivo tem 1 de 6 páginas sem texto, mais de 10%.",)


def test_rodape_de_outro_arquivo_lido_por_ocr_nao_vira_arquivo_incompleto():
    # o termo digitalizado é a foto de uma folha impressa de outro prontuário
    paginas = montar("capa", "evolucao", [""], "anotacao_enf")
    paginas[2] = com_ocr(paginas[2], "Impressão de Prontuário - Página 7 de 300")

    assert ler_prontuario(paginas, ATENDIMENTO).total_paginas == 4
