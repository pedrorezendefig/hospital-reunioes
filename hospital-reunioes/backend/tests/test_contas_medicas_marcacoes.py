"""Marcações de caixa e botão e formulário em branco aprendido (issue #1132, PRD #1128).

No PDF do MV a marcação não está no texto: cada caixa (14 x 14) e cada botão
(140 x 160) é uma imagem, e o `pdftotext` devolve "VMI VNI Cateter nasal" sem
dizer qual foi marcado. O PDF dos testes é montado aqui, à mão, com texto em
Helvetica e imagens em tons de cinza cuja fração de pixels escuros é a medida
pelo diretor nos desenhos do MV (caixa vazia 0,27 e marcada 0,39; botão vazio
0,48 e marcado 0,61). PDF real nunca entra em teste.
"""

from __future__ import annotations

import zlib

from test_contas_medicas_prontuario import ATENDIMENTO, CAPA_QUE_BATE, montar

from app.services.contas_medicas.prontuario import ler_prontuario
from app.services.contas_medicas_extrator import extrair_paginas

CAIXA_VAZIA = (14, 14, 0.27)
CAIXA_MARCADA = (14, 14, 0.39)
BOTAO_VAZIO = (140, 160, 0.48)
BOTAO_MARCADO = (140, 160, 0.61)


def _pixels(largura: int, altura: int, fracao_escura: float) -> bytes:
    escuros = round(largura * altura * fracao_escura)
    return bytes([0] * escuros + [255] * (largura * altura - escuros))


def _pdf(textos: list[tuple[int, int, str]], imagens: list[tuple[int, int, int, int, tuple]]) -> bytes:
    """Uma página A4. `textos`: (x, y, texto); `imagens`: (x, y, largura e altura
    desenhadas em pontos, (largura, altura, fração escura) da imagem). Origem embaixo."""
    conteudo = [f"BT /F1 10 Tf {x} {y} Td ({t}) Tj ET" for x, y, t in textos]
    conteudo += [f"q {w} 0 0 {h} {x} {y} cm /Im{i} Do Q" for i, (x, y, w, h, _) in enumerate(imagens)]
    stream = "\n".join(conteudo).encode("latin-1")
    xobjetos = " ".join(f"/Im{i} {6 + i} 0 R" for i in range(len(imagens)))
    objetos = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R "
            f"/Resources << /Font << /F1 5 0 R >> /XObject << {xobjetos} >> >> >>"
        ).encode(),
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    ]
    for *_, (largura, altura, fracao) in imagens:
        dados = zlib.compress(_pixels(largura, altura, fracao))
        objetos.append(
            b"<< /Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace /DeviceGray "
            b"/BitsPerComponent 8 /Filter /FlateDecode /Length %d >>\nstream\n"
            % (largura, altura, len(dados))
            + dados
            + b"\nendstream"
        )
    saida = bytearray(b"%PDF-1.4\n")
    posicoes = []
    for numero, objeto in enumerate(objetos, start=1):
        posicoes.append(len(saida))
        saida += b"%d 0 obj\n" % numero + objeto + b"\nendobj\n"
    inicio_da_xref = len(saida)
    saida += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objetos) + 1)
    for posicao in posicoes:
        saida += b"%010d 00000 n \n" % posicao
    saida += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objetos) + 1, inicio_da_xref)
    return bytes(saida)


# Um formulário do editor de documentos do MV (Família DOC_EDITOR): cabeçalho com
# PACIENTE e ATENDIMENTO, título, texto livre e duas perguntas. A ventilação tem o
# rótulo na linha de cima e caixas; a dieta tem o rótulo na mesma linha e botões.
FORMULARIO = _pdf(
    [
        (50, 800, "PACIENTE: PACIENTE FICTICIA"),
        (50, 788, "ATENDIMENTO: 31245"),
        (50, 760, "EVOLUCAO DE FONOAUDIOLOGIA"),
        (50, 745, "Paciente colaborativa, alerta, responde a comandos simples durante a sessao."),
        (50, 730, "Degluticao avaliada com consistencia pastosa, sem sinais de aspiracao."),
        (50, 700, "Suporte ventilat\xf3rio:"),
        (62, 685, "VMI"),
        (122, 685, "VNI"),
        (50, 660, "Dieta:"),
        (100, 660, "VO"),
        (160, 660, "SNE"),
    ],
    [
        (50, 684, 8, 8, CAIXA_VAZIA),
        (110, 684, 8, 8, CAIXA_MARCADA),
        (88, 659, 8, 9, BOTAO_MARCADO),
        (148, 659, 8, 9, BOTAO_VAZIO),
    ],
)


def _linhas(texto: str) -> list[str]:
    return [" ".join(linha.split()) for linha in texto.split("\n") if linha.strip()]


def test_caixa_e_botao_viram_x_ou_colchete_vazio_na_linha_da_opcao():
    paginas = extrair_paginas(FORMULARIO)

    linhas = _linhas(paginas[0].texto)
    assert "Suporte ventilatório:" in linhas
    assert "[ ] VMI [X] VNI" in linhas
    assert "Dieta: [X] VO [ ] SNE" in linhas


def _linhas_para_a_ia() -> list[str]:
    """O formulário extraído, lido como página de um Prontuário: as linhas que vão à IA."""
    pagina = extrair_paginas(FORMULARIO)[0].texto
    prontuario = ler_prontuario(montar(CAPA_QUE_BATE, [pagina]), ATENDIMENTO)
    (documento,) = prontuario.documentos
    assert documento.familia == "DOC_EDITOR"
    return list(documento.linhas)


def test_so_a_opcao_a_direita_do_x_fica_no_texto_que_vai_a_ia():
    linhas = _linhas_para_a_ia()

    assert "Dieta: [X] VO" in linhas
    texto = "\n".join(linhas)
    assert "SNE" not in texto
    assert "VMI" not in texto
    assert "[ ]" not in texto


def test_rotulo_na_linha_de_cima_com_dois_pontos_vai_junto_da_opcao_marcada():
    linhas = _linhas_para_a_ia()

    assert "Suporte ventilatório: [X] VNI" in linhas
    assert "Suporte ventilatório:" not in linhas
