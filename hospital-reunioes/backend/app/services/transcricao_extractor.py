"""
Extrator de texto de transcricoes em multiplos formatos.

Aceita .txt, .md, .pdf e .docx. Rejeita .doc legado e PDFs escaneados sem OCR.
Usado pelos endpoints /anexar-transcricao e /upload-transcricao para normalizar
o input antes de mandar para a IA gerar a ata.
"""

from __future__ import annotations

import logging
import os
from io import BytesIO

import docx2txt
import pdfplumber

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".txt", ".md", ".pdf", ".docx"}
MAX_BYTES_TEXT = 5 * 1024 * 1024
MAX_BYTES_BINARY = 15 * 1024 * 1024
MIN_PDF_TEXT_BYTES = 200

CONTENT_TYPE_BY_EXT = {
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def _normalizar_extensao(filename: str) -> str:
    _, ext = os.path.splitext(filename or "")
    return ext.lower()


def _extrair_pdf(file_bytes: bytes) -> str:
    partes: list[str] = []
    with pdfplumber.open(BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            texto = page.extract_text() or ""
            if texto:
                partes.append(texto)
    return "\n\n".join(partes).strip()


def _extrair_docx(file_bytes: bytes) -> str:
    texto = docx2txt.process(BytesIO(file_bytes)) or ""
    return texto.strip()


def extrair_texto(filename: str, file_bytes: bytes) -> tuple[str, str]:
    """
    Extrai texto plano UTF-8 de uma transcricao em txt/md/pdf/docx.

    Retorna (texto, extensao_normalizada). Levanta ValueError com mensagem
    em pt-BR pronta para virar HTTPException(422).
    """
    if not filename:
        raise ValueError("Arquivo sem nome. Anexe novamente.")

    ext = _normalizar_extensao(filename)

    if ext == ".doc":
        raise ValueError("Formato .doc nao suportado. Salve como .docx ou PDF antes de enviar.")

    if ext not in SUPPORTED_EXTENSIONS:
        aceitos = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise ValueError(f"Formato nao suportado. Aceitos: {aceitos}.")

    tamanho = len(file_bytes)
    if ext in {".txt", ".md"}:
        if tamanho > MAX_BYTES_TEXT:
            raise ValueError(f"Arquivo de texto excede o limite de {MAX_BYTES_TEXT // (1024 * 1024)} MB.")
    else:
        if tamanho > MAX_BYTES_BINARY:
            raise ValueError(f"Arquivo excede o limite de {MAX_BYTES_BINARY // (1024 * 1024)} MB.")

    if tamanho == 0:
        raise ValueError("Arquivo vazio. Anexe um arquivo com conteudo.")

    try:
        if ext == ".txt" or ext == ".md":
            texto = file_bytes.decode("utf-8", errors="replace").strip()
        elif ext == ".pdf":
            texto = _extrair_pdf(file_bytes)
            if len(texto.encode("utf-8")) < MIN_PDF_TEXT_BYTES:
                raise ValueError(
                    "PDF parece ser escaneado (sem texto extraivel). Faca OCR antes ou envie a transcricao em texto."
                )
        elif ext == ".docx":
            texto = _extrair_docx(file_bytes)
        else:
            raise ValueError("Formato nao suportado.")
    except ValueError:
        raise
    except Exception as e:
        logger.exception(f"Falha ao extrair texto de {filename} ({ext}): {e}")
        raise ValueError(f"Nao foi possivel ler o arquivo {ext}. Verifique se nao esta corrompido.") from e

    if not texto.strip():
        raise ValueError("Nao foi possivel extrair texto do arquivo. Verifique o conteudo.")

    return texto, ext
