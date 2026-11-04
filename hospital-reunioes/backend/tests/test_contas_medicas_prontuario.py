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
from decimal import Decimal
from pathlib import Path

import pytest

from app.services.contas_medicas.erro_da_conta import ENVIAR_DE_NOVO, FalhaDeLeitura, classificar
from app.services.contas_medicas.prontuario import (
    MARCA_DO_OCR,
    PESO_DA_FOLHA,
    ErroLeitura,
    bloqueio_das_digitalizadas,
    digitalizadas_da_conta,
    familia_da_folha,
    ler_prontuario,
    ressalva_das_digitalizadas,
)
from app.services.contas_medicas_conta import ItemConta

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


# Qualidade da leitura de cada folha digitalizada (issue #1398): a faixa vem do
# extrator, por página, e o OCR sempre devolve alguma coisa, até da folha ilegível.
PRONTUARIO_COM_DUAS_DIGITALIZADAS = [CAPA_QUE_BATE, "evolucao", "digitalizado", "digitalizado", "prescricao_medica"]


@pytest.mark.parametrize(
    ("qualidade", "parecer_parcial"),
    [
        ("ilegivel", ("O arquivo tem 1 de 6 páginas sem texto, mais de 10%.",)),
        ("nao_lida", ("O arquivo tem 1 de 6 páginas sem texto, mais de 10%.",)),
        ("duvidosa", ()),
        ("legivel", ()),
    ],
)
def test_folha_ilegivel_ou_nao_lida_conta_como_sem_texto_na_regra_dos_10_por_cento(qualidade, parecer_parcial):
    # As duas digitalizadas têm texto do OCR: o teto só passa pela qualidade da página 3.
    paginas = montar(*PRONTUARIO_COM_DUAS_DIGITALIZADAS, "anotacao_enf")
    paginas[2] = com_ocr(paginas[2], TERMO_LIDO_POR_OCR)
    paginas[3] = com_ocr(paginas[3], TERMO_LIDO_POR_OCR)

    resultado = ler_prontuario(paginas, ATENDIMENTO, {3: qualidade, 4: "legivel"})

    assert resultado.paginas_sem_texto == ((3,) if parecer_parcial else ())
    assert resultado.parecer_parcial == parecer_parcial


def test_a_faixa_de_cada_folha_digitalizada_chega_ao_documento():
    paginas = montar(*PRONTUARIO_COM_DUAS_DIGITALIZADAS, "anotacao_enf")
    paginas[2] = com_ocr(paginas[2], TERMO_LIDO_POR_OCR)

    resultado = ler_prontuario(paginas, ATENDIMENTO, {3: "duvidosa", 4: "nao_lida"})

    assert {d.paginas: d.qualidade for d in resultado.documentos if d.familia == "DIGITALIZADO"} == {
        (3,): "duvidosa",
        (4,): "nao_lida",
    }
    assert {d.qualidade for d in resultado.documentos if d.familia != "DIGITALIZADO"} == {None}


def test_digitalizadas_da_conta_sao_as_do_atendimento_com_data_no_periodo():
    fora_do_periodo = [paginas_da_fixture("digitalizado")[0].replace("03/10/2026", "12/10/2026")]
    # 2 e 3: pronto-socorro; 4: digitalizada que herda o Atendimento do pronto-socorro;
    # 6: digitalizada da conta no período; 7: digitalizada da conta fora do período.
    paginas = montar(CAPA_QUE_BATE, "outro_atendimento", "digitalizado", "evolucao", "digitalizado", fora_do_periodo)

    assert digitalizadas_da_conta(paginas, ATENDIMENTO, date(2026, 10, 1), date(2026, 10, 5)) == (6,)
    assert digitalizadas_da_conta(paginas, ATENDIMENTO, date(2026, 10, 1), None) == (6, 7)


# Família da folha digitalizada (issue #1399): o texto do PDF dessas páginas só tem
# rodapé e assinatura, então ela sai do título que o OCR leu. OCR sintético, como o
# tesseract devolve: acento faltando, caixa misturada, sujeira entre as palavras.
@pytest.mark.parametrize(
    ("ocr", "familia", "peso"),
    [
        ("FICHA DE ANESTESIA\nTecnica anestesica: geral balanceada", "ficha de anestesia", "pesa"),
        ("SINAIS VITAIS E MEDICACOES DO INTRA-OPERATORIO\nPA FC SpO2", "ficha de anestesia", "pesa"),
        ("FOLHA DE SALA\nMateriais utilizados na cirurgia", "folha de sala ou de consumo do centro cirúrgico", "pesa"),
        ("CONTROLE DE FIOS CIRURGICOS\nvicryl 2-0 nylon 3-0", "controle de fios", "pesa"),
        ("CONTROLE DE OPME\netiqueta lote ref", "controle de OPME e etiquetas", "pesa"),
        ("REGISTRO DE HORARIOS CIRURGICOS\nentrada na sala 07:40", "registro de horários cirúrgicos", "pesa"),
        ("RELATORIO DE USO DE EQUIPAMENTO\nvideolaparoscopia", "relatório de uso de equipamento", "pesa"),
        ("DESCRICAO CIRURGICA\nachados operatorios: vesicula", "descrição cirúrgica manuscrita", "pesa"),
        ("PRESCRICAO MEDICA\nchecagem e aprazamento", "prescrição ou checagem manuscrita", "pesa"),
        ("SOLICITACAO DE HEMOCOMPONENTE\nconcentrado de hemacias 1 bolsa", "hemoterapia", "pesa"),
        ("BOLETIM DE INTERNACAO\nhora da internacao", "boletim de internação", "ajuda"),
        ("LAUDO DE TOMOGRAFIA\nimpressao diagnostica", "laudo de exame", "ajuda"),
        ("GUIA DE SOLICITACAO DE INTERNACAO\nsenha de autorizacao", "guia da operadora", "ajuda"),
        ("LISTA DE VERIFICACAO CIRURGIA SEGURA\nsign in time out", "checklist de cirurgia segura", "nao_pesa"),
        ("TERMO DE CONSENTIMENTO INFORMADO\ndeclaro que fui informado", "termo de consentimento", "nao_pesa"),
        ("RECEITUARIO\nuso oral", "receituário", "nao_pesa"),
        ("INTEGRADOR QUIMICO\nesterilizacao a vapor", "integrador químico e caixa de instrumental", "nao_pesa"),
        ("ESCALA DE BRADEN\nrisco de lesao por pressao", "escala de risco", "nao_pesa"),
        ("REPUBLICA FEDERATIVA DO BRASIL\ncarteira de identidade", "documento pessoal", "nao_pesa"),
        ("ELETROCARDIOGRAMA\nritmo sinusal ECG 12 derivacoes", "eletrocardiograma", "nao_pesa"),
        ("~~ ;; .. rr !! ii ll", "documento não identificado", "pesa"),
        ("", "documento não identificado", "pesa"),
    ],
)
def test_a_folha_digitalizada_ganha_familia_e_peso_pelo_titulo_que_o_ocr_leu(ocr, familia, peso):
    assert familia_da_folha(ocr) == familia
    assert PESO_DA_FOLHA[familia] == peso


# Ressalva no Parecer parcial (issue #1399): a digitalizada do Atendimento e do
# período da conta, que pesa (ou não foi identificada) e saiu duvidosa ou ilegível.
FICHA_LIDA_POR_OCR = "FICHA DE ANESTESIA\nTecnica anestesica: geral balanceada"
HORARIOS_LIDOS_POR_OCR = "REGISTRO DE HORARIOS CIRURGICOS\nentrada do paciente na sala 07:40"
CONSENTIMENTO_LIDO_POR_OCR = "TERMO DE CONSENTIMENTO INFORMADO\ndeclaro que fui informado"
OUTUBRO_1, OUTUBRO_5 = date(2026, 10, 1), date(2026, 10, 5)


def folha(dia: str = "03/10/2026") -> list[str]:
    """A folha digitalizada da fixture, assinada no dia pedido."""
    return [paginas_da_fixture("digitalizado")[0].replace("03/10/2026", dia)]


def ressalva(partes: list, lidas: dict[int, str], qualidades: dict[int, str], inicio=OUTUBRO_1, fim=OUTUBRO_5):
    """Monta o prontuário, põe o OCR em cada página de `lidas` e devolve a ressalva da conta do período."""
    paginas = montar(*partes)
    for numero, lido in lidas.items():
        paginas[numero - 1] = com_ocr(paginas[numero - 1], lido)
    return ressalva_das_digitalizadas(ler_prontuario(paginas, ATENDIMENTO, qualidades), inicio, fim)


def linha_da_ressalva(pagina: int, documento: str) -> str:
    return (
        f"Confira à mão no prontuário a página {pagina} ({documento}): "
        "é uma folha digitalizada que não consegui ler bem."
    )


def test_a_ressalva_lista_a_folha_que_pesa_e_saiu_duvidosa_ou_ilegivel_com_pagina_e_documento():
    resultado = ressalva(
        [CAPA_QUE_BATE, "evolucao", folha(), "anotacao_enf", folha()],
        {3: FICHA_LIDA_POR_OCR, 5: HORARIOS_LIDOS_POR_OCR},
        {3: "duvidosa", 5: "ilegivel"},
    )

    assert resultado == (
        linha_da_ressalva(3, "ficha de anestesia"),
        linha_da_ressalva(5, "registro de horários cirúrgicos"),
    )


def test_paginas_seguidas_do_mesmo_documento_vao_numa_linha_so():
    resultado = ressalva(
        [CAPA_QUE_BATE, "evolucao", folha(), folha(), "anotacao_enf"],
        {3: FICHA_LIDA_POR_OCR, 4: FICHA_LIDA_POR_OCR},
        {3: "ilegivel", 4: "duvidosa"},
    )

    assert resultado == (
        "Confira à mão no prontuário as páginas 3 e 4 (ficha de anestesia): "
        "são folhas digitalizadas que não consegui ler bem.",
    )


# Em cada caso a página 3, ficha de anestesia ilegível do período, entra: a ressalva
# não está vazia por outro motivo. O que muda é a outra folha, que fica de fora.
@pytest.mark.parametrize(
    ("partes", "lidas", "qualidades"),
    [
        pytest.param([folha()], {4: CONSENTIMENTO_LIDO_POR_OCR}, {4: "ilegivel"}, id="familia_que_nao_pesa"),
        pytest.param([folha()], {4: FICHA_LIDA_POR_OCR}, {4: "legivel"}, id="pagina_legivel"),
        # as páginas 4 e 5 são do pronto-socorro, e a 6 herda o Atendimento dele
        pytest.param(["outro_atendimento", folha()], {6: FICHA_LIDA_POR_OCR}, {6: "ilegivel"}, id="outro_atendimento"),
        pytest.param([folha("12/10/2026")], {4: FICHA_LIDA_POR_OCR}, {4: "ilegivel"}, id="fora_do_periodo"),
    ],
)
def test_nao_entram_na_ressalva(partes, lidas, qualidades):
    resultado = ressalva(
        [CAPA_QUE_BATE, "evolucao", folha(), *partes, "anotacao_enf"],
        {3: FICHA_LIDA_POR_OCR, **lidas},
        {3: "ilegivel", **qualidades},
    )

    assert resultado == (linha_da_ressalva(3, "ficha de anestesia"),)


@pytest.mark.parametrize(
    ("lidas", "qualidade"),
    [
        pytest.param({3: "~~ ;; .. rr !! ii ll"}, "ilegivel", id="ilegivel_sem_titulo"),
        pytest.param({}, "nao_lida", id="nao_lida_por_prazo"),
    ],
)
def test_pagina_ilegivel_sem_titulo_entra_como_documento_nao_identificado(lidas, qualidade):
    resultado = ressalva([CAPA_QUE_BATE, "evolucao", folha(), "anotacao_enf"], lidas, {3: qualidade})

    assert resultado == (linha_da_ressalva(3, "documento não identificado"),)


def test_cada_parcial_do_mesmo_atendimento_lista_so_as_paginas_do_proprio_periodo():
    partes = [CAPA_QUE_BATE, "evolucao", folha("03/10/2026"), "anotacao_enf", folha("05/10/2026")]
    lidas = {3: FICHA_LIDA_POR_OCR, 5: FICHA_LIDA_POR_OCR}
    qualidades = {3: "ilegivel", 5: "ilegivel"}

    primeira = ressalva(partes, lidas, qualidades, date(2026, 10, 2), date(2026, 10, 4))
    segunda = ressalva(partes, lidas, qualidades, date(2026, 10, 5), date(2026, 10, 6))

    assert primeira == (linha_da_ressalva(3, "ficha de anestesia"),)
    assert segunda == (linha_da_ressalva(5, "ficha de anestesia"),)


def test_a_familia_da_folha_vira_o_subtipo_do_documento_digitalizado():
    paginas = montar(CAPA_QUE_BATE, "evolucao", folha(), "anotacao_enf")
    paginas[2] = com_ocr(paginas[2], FICHA_LIDA_POR_OCR)

    (digitalizado,) = [d for d in ler_prontuario(paginas, ATENDIMENTO).documentos if d.familia == "DIGITALIZADO"]

    assert digitalizado.subtipo == "ficha de anestesia"


# Bloqueio pelas folhas digitalizadas (issue #1400): a conta para em Erro
# CM-ARQ-DIGITALIZADO quando as folhas escaneadas que sustentam a cobrança não dão
# para ler. A frase sai do catálogo do Código do erro, como o cartão mostra.
DESCRICAO_EM_TEXTO = [
    p.strip("\n")
    for p in (FIXTURES.parent / "conteudo" / "descricao_cirurgica.txt").read_text(encoding="utf-8").split(QUEBRA)
]
OPME_LIDO_POR_OCR = "CONTROLE DE OPME\netiqueta lote ref"
ECG_LIDO_POR_OCR = "ELETROCARDIOGRAMA\nritmo sinusal ECG 12 derivacoes"
SUJEIRA_DO_OCR = "~~ ;; .. rr !! ii ll"
# Quatro páginas em texto do período: com uma folha ruim, 1 de 5 fica abaixo dos 25%.
EM_TEXTO = ["evolucao", "anotacao_enf", "evolucao", "anotacao_enf"]


def item(grupo: str, descricao: str, *, setor: str = "CTI ADULTO", grupo_procedimento: str = "GERAL", dia: int = 3):
    return ItemConta(
        pagina=1,
        data=date(2026, 10, dia),
        codigo="10000001",
        descricao=descricao,
        unidade="UN",
        percentual=Decimal(100),
        quantidade=Decimal(1),
        unitario=Decimal(10),
        total=Decimal(10),
        grupo=grupo,
        setor_codigo="1",
        setor=setor,
        grupo_procedimento=grupo_procedimento,
    )


TAXA_DE_SALA = item("TAXAS", "TAXA DE SALA CIRURGICA PORTE 3", setor="CENTRO CIRURGICO")
DIARIA = item("DIARIAS", "DIARIA DE UTI ADULTO")


def bloqueio(partes: list, lidas: dict[int, str], qualidades: dict[int, str], itens=(TAXA_DE_SALA,)) -> str | None:
    """Monta o prontuário com o OCR de cada página de `lidas` e devolve a frase do
    Erro da conta de 01 a 05/10 com os `itens`, ou None quando ela segue."""
    paginas = montar(*partes)
    for numero, lido in lidas.items():
        paginas[numero - 1] = com_ocr(paginas[numero - 1], lido)
    prontuario = ler_prontuario(paginas, ATENDIMENTO, qualidades)
    achado = bloqueio_das_digitalizadas(prontuario, paginas, itens, OUTUBRO_1, OUTUBRO_5)
    if achado is None:
        return None
    causa, dados = achado
    erro = classificar(FalhaDeLeitura(causa, **dados), "leitura_do_prontuario")
    assert (erro.codigo, erro.arquivo, erro.acao) == ("CM-ARQ-DIGITALIZADO", "prontuario", ENVIAR_DE_NOVO)
    return erro.frase


def frase_da_cirurgia(folha_ruim: str) -> str:
    return (
        f"Não dá para analisar esta conta: {folha_ruim} é uma folha digitalizada que não consegui ler. "
        "Digitalize de novo, com a folha em pé, e envie o prontuário de novo."
    )


@pytest.mark.parametrize("qualidade", ["ilegivel", "duvidosa"])
def test_conta_cirurgica_sem_ficha_nem_descricao_legiveis_para_na_ficha_ruim(qualidade):
    frase = bloqueio([CAPA_QUE_BATE, *EM_TEXTO, folha()], {6: FICHA_LIDA_POR_OCR}, {6: qualidade})

    assert frase == frase_da_cirurgia("a ficha de anestesia (página 6)")


def test_conta_cirurgica_com_folha_ruim_sem_titulo_aponta_o_documento_nao_identificado():
    frase = bloqueio([CAPA_QUE_BATE, *EM_TEXTO, folha()], {6: SUJEIRA_DO_OCR}, {6: "ilegivel"})

    assert frase == frase_da_cirurgia("o documento não identificado (página 6)")


def test_entre_as_folhas_ruins_a_frase_aponta_a_ficha_de_anestesia():
    partes = [CAPA_QUE_BATE, *EM_TEXTO, folha(), folha(), *EM_TEXTO]
    lidas = {6: OPME_LIDO_POR_OCR, 7: FICHA_LIDA_POR_OCR}

    frase = bloqueio(partes, lidas, {6: "ilegivel", 7: "duvidosa"})

    assert frase == frase_da_cirurgia("a ficha de anestesia (página 7)")


@pytest.mark.parametrize(
    "cirurgico",
    [
        pytest.param(TAXA_DE_SALA, id="taxa_de_sala"),
        pytest.param(
            item("HONORARIOS MEDICOS", "COLECISTECTOMIA", grupo_procedimento="PROCEDIMENTOS CIRURGICOS"),
            id="honorario_de_procedimento_cirurgico",
        ),
        pytest.param(
            item("GASES MEDICINAIS", "OXIGENIO POR HORA", setor="CENTRO CIRURGICO"), id="gas_do_centro_cirurgico"
        ),
        pytest.param(item("MEDICAMENTOS", "SEVOFLURANO 100ML FR"), id="anestesico"),
    ],
)
def test_cada_item_do_centro_cirurgico_faz_a_conta_cirurgica(cirurgico):
    frase = bloqueio([CAPA_QUE_BATE, *EM_TEXTO, folha()], {6: FICHA_LIDA_POR_OCR}, {6: "ilegivel"}, (DIARIA, cirurgico))

    assert frase == frase_da_cirurgia("a ficha de anestesia (página 6)")


@pytest.mark.parametrize(
    ("partes", "lidas", "qualidades", "itens"),
    [
        pytest.param(
            [*EM_TEXTO, folha(), DESCRICAO_EM_TEXTO],
            {6: FICHA_LIDA_POR_OCR},
            {6: "ilegivel"},
            (TAXA_DE_SALA,),
            id="descricao_cirurgica_em_texto",
        ),
        pytest.param(
            [*EM_TEXTO, folha(), folha(), *EM_TEXTO],
            {6: FICHA_LIDA_POR_OCR, 7: OPME_LIDO_POR_OCR},
            {6: "legivel", 7: "ilegivel"},
            (TAXA_DE_SALA,),
            id="ficha_digitalizada_legivel",
        ),
        pytest.param(
            [*EM_TEXTO, folha("12/10/2026")],
            {6: FICHA_LIDA_POR_OCR},
            {6: "ilegivel"},
            (TAXA_DE_SALA,),
            id="pagina_ruim_fora_do_periodo",
        ),
        pytest.param(
            [*EM_TEXTO, folha()],
            {6: FICHA_LIDA_POR_OCR},
            {6: "ilegivel"},
            (item("TAXAS", "TAXA DE SALA CIRURGICA PORTE 3", setor="CENTRO CIRURGICO", dia=12),),
            id="item_do_centro_cirurgico_fora_do_periodo",
        ),
        pytest.param(
            [*EM_TEXTO, folha()],
            {6: FICHA_LIDA_POR_OCR},
            {6: "ilegivel"},
            (DIARIA, item("MEDICAMENTOS", "DIPIRONA 500MG"), item("TAXAS", "TAXA DE ENFERMAGEM")),
            id="conta_sem_item_do_centro_cirurgico",
        ),
        pytest.param(
            [*EM_TEXTO, folha()],
            {6: ECG_LIDO_POR_OCR},
            {6: "ilegivel"},
            (TAXA_DE_SALA,),
            id="folha_ruim_que_nao_pesa",
        ),
        # a não lida é falha da leitura (fila cheia, prazo, PDF que falta), não da folha
        pytest.param(
            [*EM_TEXTO, folha()],
            {6: FICHA_LIDA_POR_OCR},
            {6: "nao_lida"},
            (TAXA_DE_SALA,),
            id="ficha_nao_lida",
        ),
    ],
)
def test_conta_segue_sem_o_bloqueio_da_cirurgia(partes, lidas, qualidades, itens):
    assert bloqueio([CAPA_QUE_BATE, *partes], lidas, qualidades, itens) is None


def frase_das_paginas(ilegiveis: int, paginas: int) -> str:
    return (
        f"Não dá para analisar esta conta: {ilegiveis} das {paginas} páginas do prontuário deste período são "
        "folhas digitalizadas que não consegui ler. Digitalize de novo essas folhas, em pé, e envie o prontuário "
        "de novo."
    )


def test_mais_de_um_quarto_das_paginas_do_periodo_ilegiveis_para_a_conta():
    # 2 de 7 (28%), numa conta sem cirurgia; a folha de fora do período não conta.
    partes = [CAPA_QUE_BATE, *EM_TEXTO, folha(), folha(), "evolucao", folha("12/10/2026")]
    lidas = {6: SUJEIRA_DO_OCR, 7: OPME_LIDO_POR_OCR, 9: SUJEIRA_DO_OCR}
    qualidades = {6: "ilegivel", 7: "ilegivel", 9: "ilegivel"}

    assert bloqueio(partes, lidas, qualidades, (DIARIA,)) == frase_das_paginas(2, 7)


@pytest.mark.parametrize(
    ("partes", "lidas", "qualidades"),
    [
        # 2 de 8 é 25% em ponto
        pytest.param(
            [*EM_TEXTO, folha(), folha(), "evolucao", "anotacao_enf"],
            {6: SUJEIRA_DO_OCR, 7: SUJEIRA_DO_OCR},
            {6: "ilegivel", 7: "ilegivel"},
            id="25_por_cento",
        ),
        # contando o eletrocardiograma seriam 2 de 7
        pytest.param(
            [*EM_TEXTO, folha(), folha(), "evolucao"],
            {6: SUJEIRA_DO_OCR, 7: ECG_LIDO_POR_OCR},
            {6: "ilegivel", 7: "ilegivel"},
            id="eletrocardiograma_ilegivel",
        ),
        # duvidosa não é ilegível: 2 de 7 duvidosas seguem
        pytest.param(
            [*EM_TEXTO, folha(), folha(), "evolucao"],
            {6: SUJEIRA_DO_OCR, 7: SUJEIRA_DO_OCR},
            {6: "duvidosa", 7: "duvidosa"},
            id="duvidosas",
        ),
        # não lida é falha da leitura, não da folha: 2 de 7 não lidas seguem
        pytest.param(
            [*EM_TEXTO, folha(), folha(), "evolucao"],
            {6: SUJEIRA_DO_OCR, 7: OPME_LIDO_POR_OCR},
            {6: "nao_lida", 7: "nao_lida"},
            id="nao_lidas",
        ),
    ],
)
def test_um_quarto_ou_menos_das_paginas_ilegiveis_segue(partes, lidas, qualidades):
    assert bloqueio([CAPA_QUE_BATE, *partes], lidas, qualidades, (DIARIA,)) is None
