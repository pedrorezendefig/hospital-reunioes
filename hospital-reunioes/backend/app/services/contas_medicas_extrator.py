"""Extrator de texto de PDF do módulo Contas médicas (issue #1116, ADR 0070).

Conta e Prontuário chegam do MV em PDF e viram texto pelo `pdftotext -layout`
(poppler-utils): as expressões da leitura por código foram calibradas na saída
do `-layout`, e ela preserva a coluna de cada campo.

O `pdftotext` é parser de arquivo que vem de fora, e o uvicorn sobe com um
worker só. Por isso ele roda isolado, com o mesmo orçamento do extrator de
documentos que já existe (`transcricao_extractor`, issue #758): o mesmo teto de
memória vigiado pelo pai, o mesmo `RLIMIT_AS` instalado no filho, o mesmo
ambiente mínimo sem chave nenhuma, e o mesmo número de vagas. O prazo é outro:
120 segundos, porque um Prontuário tem centenas de páginas e a leitura roda na
fila, não na frente de alguém esperando.

As vagas são do módulo e não as do extrator de documentos: dividir o mesmo
semáforo deixaria um Prontuário de dois minutos segurando a vaga de quem sobe a
transcrição de uma Ata, e a pessoa levaria "tente de novo" sem nada de errado.

As palavras com a posição de cada uma (`extrair_palavras`, #1133) saem do mesmo
filho, pelo `pdfplumber`, com o mesmo orçamento: a prescrição lê por elas a
coordenada das colunas.

No Prontuário, as páginas digitalizadas (imagem, sem texto) são lidas por OCR
no mesmo filho e com o mesmo orçamento (#1191): `pdftoppm` rasteriza, o
`tesseract -l por` lê. A Conta não passa por OCR.

O texto devolvido tem dado de paciente: nunca vai para log, nem em caso de erro.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import tempfile
import threading
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import NamedTuple

from app.services import contas_medicas_extrator_filho as filho
from app.services import contas_medicas_marcacoes_filho as filho_das_marcacoes
from app.services import transcricao_extractor as orcamento
from app.services.contas_medicas.marcacoes import inserir_nas_paginas
from app.services.contas_medicas.prontuario import MARCA_DO_OCR, e_digitalizada, e_formulario

logger = logging.getLogger(__name__)

PRAZO_DA_LEITURA = 120.0
VAGAS_DE_LEITURA = orcamento.VAGAS_DE_EXTRACAO
_vagas = threading.BoundedSemaphore(VAGAS_DE_LEITURA)

# O teto do canal de volta é maior que o do extrator de documentos (16 MB): o
# `-layout` preenche cada linha com espaços até a coluna do campo, uma página
# de Prontuário passa de 10 KB, e o Prontuário real do diretor tem 952 páginas.
# 64 MB cabem seis mil páginas assim, e ainda são número que se confere contra
# a memória do container, vezes as duas vagas.
TETO_DO_TEXTO_DEVOLVIDO = 64 * 1024 * 1024

MENSAGEM_PDF_GRANDE_DEMAIS = (
    "O PDF é grande ou complexo demais para ser lido de uma vez. A leitura foi "
    "interrompida para não comprometer o sistema."
)
MENSAGEM_PDF_ILEGIVEL = "Não consegui ler o PDF. Confira se ele abre no computador e envie de novo."

_CAMINHO_DO_FILHO = os.path.abspath(filho.__file__)
_CAMINHO_DAS_MARCACOES = os.path.abspath(filho_das_marcacoes.__file__)


@dataclass(frozen=True)
class ErroLeitura:
    """Leitura que não pode ser usada. `motivo` é a frase que vai para a tela."""

    motivo: str


@dataclass(frozen=True)
class Pagina:
    """Texto de uma página, com a numeração do PDF (a primeira é 1). `ocr` diz que
    a página é digitalizada e o texto da imagem veio do `tesseract` (#1191)."""

    numero: int
    texto: str
    sem_texto: bool
    ocr: bool = False


def _paginas(texto: str) -> list[Pagina]:
    # O `pdftotext` fecha toda página com um form feed, inclusive a última.
    partes = texto.split("\f")
    if partes and partes[-1] == "":
        partes.pop()
    return [
        Pagina(numero=n, texto=t, sem_texto=not t.strip(), ocr=MARCA_DO_OCR in t) for n, t in enumerate(partes, start=1)
    ]


def texto_para_guardar(paginas: Sequence[Pagina]) -> bytes:
    """O texto extraído no formato do próprio `pdftotext`, para guardar no
    bucket ao lado do PDF: o envio extrai uma vez e a fila lê daí (#1124)."""
    return "".join(f"{pagina.texto}\f" for pagina in paginas).encode("utf-8")


def paginas_do_texto_guardado(bruto: bytes) -> list[Pagina]:
    """As páginas do texto que `texto_para_guardar` gravou."""
    return _paginas(bruto.decode("utf-8", errors="replace"))


@dataclass(frozen=True)
class _Desfecho:
    motivo: str | None
    codigo: int
    bruto: bytes
    diagnostico: str


def _rodar(argv: list[str], pasta: str, nome: str) -> _Desfecho:
    """Um filho com o orçamento da leitura: prazo, teto de memória e canal de volta."""
    saida = os.path.join(pasta, f"{nome}.saida")
    erro = os.path.join(pasta, f"{nome}.erro")
    with open(saida, "wb") as f_saida, open(erro, "wb") as f_erro:
        proc = subprocess.Popen(
            [sys.executable, "-P", *argv],
            stdin=subprocess.DEVNULL,
            stdout=f_saida,
            stderr=f_erro,
            env=orcamento._ambiente_do_filho(),
        )
        motivo = orcamento._acompanhar(
            proc,
            saida,
            erro,
            prazo=PRAZO_DA_LEITURA,
            teto_da_saida=TETO_DO_TEXTO_DEVOLVIDO,
        )
    if motivo is None and orcamento._tamanho(saida) > TETO_DO_TEXTO_DEVOLVIDO:
        motivo = "saida"
    bruto = b"" if motivo is not None else orcamento._ler(saida)
    return _Desfecho(motivo, proc.returncode, bruto, orcamento._ler_cauda(erro, orcamento.RABO_DO_ERRO_NO_LOG))


def _marcacoes(entrada: str, pasta: str, paginas: list[Pagina]) -> dict[int, list[list[str]]]:
    """As marcações dos formulários, lidas num segundo filho com o mesmo orçamento.
    Só as páginas de formulário: um Prontuário tem centenas de páginas e o
    `pdfplumber` é lento. Se a leitura falhar, o texto segue sem as marcações."""
    formularios = [p.numero for p in paginas if not p.sem_texto and e_formulario(p.texto)]
    if not formularios:
        return {}
    limite = str(orcamento.LIMITE_DE_ENDERECAMENTO)
    lista = ",".join(map(str, formularios))
    desfecho = _rodar([_CAMINHO_DAS_MARCACOES, limite, entrada, lista], pasta, "marcacoes")
    if desfecho.motivo is not None or desfecho.codigo != 0:
        logger.warning(
            "Leitura das marcacoes falhou (%s): o texto segue sem elas",
            desfecho.motivo or f"codigo {desfecho.codigo}: {desfecho.diagnostico}",
        )
        return {}
    try:
        lidas = json.loads(desfecho.bruto)
        return {int(numero): linhas for numero, linhas in lidas.items()}
    except (ValueError, AttributeError):
        logger.warning("Leitura das marcacoes devolveu saida ilegivel: o texto segue sem elas")
        return {}


def _ocr(entrada: str, pasta: str, paginas: list[Pagina]) -> dict[int, str]:
    """O texto das páginas digitalizadas do Prontuário, lido pelo `tesseract` num
    filho com o mesmo orçamento (#1191). Só o Prontuário: a Conta sai do MV em
    texto. Se a leitura falhar ou passar do prazo, as páginas seguem sem texto."""
    # Import tardio: `contas_medicas_conta` importa o `ErroLeitura` deste módulo.
    from app.services.contas_medicas_conta import detectar_tipo_do_arquivo

    if not paginas or detectar_tipo_do_arquivo(paginas[0].texto) != "PRONTUARIO":
        return {}
    digitalizadas = [p.numero for p in paginas if e_digitalizada(p.texto)]
    if not digitalizadas:
        return {}
    limite = str(orcamento.LIMITE_DE_ENDERECAMENTO)
    lista = ",".join(map(str, digitalizadas))
    # O filho para antes do vigia, para devolver o que já leu em vez de morrer.
    prazo = str(PRAZO_DA_LEITURA * 0.9)
    desfecho = _rodar([_CAMINHO_DO_FILHO, limite, entrada, "--ocr", lista, prazo], pasta, "ocr")
    if desfecho.motivo is not None or desfecho.codigo != 0:
        logger.warning(
            "OCR das paginas digitalizadas falhou (%s): elas seguem sem texto",
            desfecho.motivo or f"codigo {desfecho.codigo}: {desfecho.diagnostico}",
        )
        return {}
    try:
        lidas = json.loads(desfecho.bruto)
        return {int(numero): texto for numero, texto in lidas.items()}
    except (ValueError, AttributeError):
        logger.warning("OCR das paginas digitalizadas devolveu saida ilegivel: elas seguem sem texto")
        return {}


def extrair_paginas(pdf: bytes) -> list[Pagina] | ErroLeitura:
    """Texto do PDF por página, lido pelo `pdftotext -layout` num processo isolado,
    com as marcações de caixa e botão dos formulários no lugar das imagens e, no
    Prontuário, o texto das páginas digitalizadas lido por OCR."""
    if not _vagas.acquire(timeout=PRAZO_DA_LEITURA):
        logger.warning("Leitura de PDF sem vaga apos %ss", PRAZO_DA_LEITURA)
        return ErroLeitura(orcamento.MENSAGEM_FILA_CHEIA)

    try:
        with tempfile.TemporaryDirectory(prefix="contas-medicas-") as pasta:
            entrada = os.path.join(pasta, "entrada.pdf")
            with open(entrada, "wb") as f:
                f.write(pdf)

            desfecho = _rodar([_CAMINHO_DO_FILHO, str(orcamento.LIMITE_DE_ENDERECAMENTO), entrada], pasta, "texto")
            if desfecho.motivo is not None or desfecho.codigo != 0:
                paginas, marcacoes, lidas_por_ocr = [], {}, {}
            else:
                paginas = _paginas(desfecho.bruto.decode("utf-8", errors="replace"))
                marcacoes = _marcacoes(entrada, pasta, paginas)
                lidas_por_ocr = _ocr(entrada, pasta, paginas)
    finally:
        _vagas.release()

    if desfecho.motivo is not None or desfecho.codigo < 0:
        # Código negativo é sinal: o filho foi morto (OOM do cgroup), não terminou.
        return ErroLeitura(MENSAGEM_PDF_GRANDE_DEMAIS)

    if desfecho.codigo != 0:
        # O `stderr` do `pdftotext` só tem diagnóstico do arquivo, nunca o texto.
        logger.error("Leitura de PDF falhou (codigo %s): %s", desfecho.codigo, desfecho.diagnostico)
        return ErroLeitura(MENSAGEM_PDF_ILEGIVEL)

    if marcacoes:
        textos = inserir_nas_paginas([p.texto for p in paginas], marcacoes)
        paginas = [Pagina(p.numero, texto, p.sem_texto) for p, texto in zip(paginas, textos, strict=True)]
    if lidas_por_ocr:
        paginas = [_com_ocr(p, lidas_por_ocr[p.numero]) if p.numero in lidas_por_ocr else p for p in paginas]
    return paginas


def _com_ocr(pagina: Pagina, lido: str) -> Pagina:
    """O texto do OCR vai depois do que o `pdftotext` leu (rodapé e assinatura), atrás
    da marca: a leitura do Prontuário estrutura a página só pelo que vem antes dela."""
    return Pagina(pagina.numero, f"{pagina.texto}\n{MARCA_DO_OCR}\n{lido}\n", sem_texto=False, ocr=True)


def _no_filho(pdf: bytes, *argumentos: str) -> bytes | ErroLeitura:
    """A saída do filho sobre o PDF, num processo isolado, dentro do orçamento."""
    if not _vagas.acquire(timeout=PRAZO_DA_LEITURA):
        logger.warning("Leitura de PDF sem vaga apos %ss", PRAZO_DA_LEITURA)
        return ErroLeitura(orcamento.MENSAGEM_FILA_CHEIA)

    try:
        with tempfile.TemporaryDirectory(prefix="contas-medicas-") as pasta:
            entrada = os.path.join(pasta, "entrada.pdf")
            with open(entrada, "wb") as f:
                f.write(pdf)
            argv = [_CAMINHO_DO_FILHO, str(orcamento.LIMITE_DE_ENDERECAMENTO), entrada, *argumentos]
            desfecho = _rodar(argv, pasta, "filho")
    finally:
        _vagas.release()

    if desfecho.motivo is not None or desfecho.codigo < 0:
        # Código negativo é sinal: o filho foi morto (OOM do cgroup), não terminou.
        return ErroLeitura(MENSAGEM_PDF_GRANDE_DEMAIS)

    if desfecho.codigo != 0:
        # O `stderr` do filho só tem diagnóstico do arquivo, nunca o texto.
        logger.error("Leitura de PDF falhou (codigo %s): %s", desfecho.codigo, desfecho.diagnostico)
        return ErroLeitura(MENSAGEM_PDF_ILEGIVEL)

    return desfecho.bruto


class Palavra(NamedTuple):
    """Uma palavra da página com a posição, em pontos a partir do canto de cima à esquerda."""

    x0: float
    x1: float
    topo: float
    texto: str


def extrair_palavras(pdf: bytes, paginas: Iterable[int]) -> dict[int, list[Palavra]] | ErroLeitura:
    """As palavras de cada página pedida, com a posição, lidas pelo `extract_words`
    do `pdfplumber` no mesmo processo isolado (#1133). Página fora do PDF não volta."""
    pedidas = sorted(set(paginas))
    if not pedidas:
        return {}
    bruto = _no_filho(pdf, ",".join(str(n) for n in pedidas))
    if isinstance(bruto, ErroLeitura):
        return bruto
    try:
        lidas = json.loads(bruto.decode("utf-8", errors="replace"))
    except ValueError:
        return ErroLeitura(MENSAGEM_PDF_ILEGIVEL)
    return {int(n): [Palavra(*p) for p in palavras] for n, palavras in lidas.items()}
