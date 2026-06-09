"""Conversão local de documentos (PDF/DOCX) para Markdown via markitdown.

100% offline — nenhuma chamada externa, nenhum token de LLM. Para PDF o
markitdown usa o pdfminer.six (mesmo motor do pdfplumber já presente no
projeto); para DOCX usa mammoth (preserva headings, negrito e listas).
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from functools import lru_cache

from markitdown import MarkItDown, StreamInfo

logger = logging.getLogger(__name__)

_CHARS_PROIBIDOS = set('/\\:*?"<>|')


class ConversaoError(Exception):
    """Falha na conversão do documento (corrompido, protegido por senha etc.)."""


@dataclass
class ResultadoConversao:
    markdown: str
    title: str | None


@lru_cache(maxsize=1)
def _get_markitdown() -> MarkItDown:
    """Instância única do conversor, criada sob demanda.

    A primeira instância carrega o modelo do magika (detecção de tipo de
    arquivo, ~1s) — custo que não deve ser pago no boot nem a cada request.
    """
    return MarkItDown(enable_plugins=False)


def converter_para_markdown(dados: bytes, extensao: str) -> ResultadoConversao:
    """Converte os bytes de um documento em Markdown (CPU-bound, síncrona).

    Chamar via thread (anyio.to_thread.run_sync) para não bloquear o event loop.
    """
    try:
        result = _get_markitdown().convert_stream(io.BytesIO(dados), stream_info=StreamInfo(extension=extensao))
    except Exception as e:
        logger.error(f"[utilitarios] Falha na conversão de {extensao}: {e}")
        raise ConversaoError(str(e)) from e
    return ResultadoConversao(markdown=result.markdown, title=result.title)


def sugerir_nome_md(filename: str | None) -> str:
    """Nome do .md de saída a partir do nome enviado pelo cliente.

    Descarta diretórios (separadores / e \\), troca a extensão por .md e
    remove caracteres problemáticos preservando acentos. Fallback: documento.md.
    """
    nome = (filename or "").replace("\\", "/").rsplit("/", 1)[-1]
    stem = nome.rsplit(".", 1)[0] if "." in nome else nome
    limpo = "".join(c for c in stem if c not in _CHARS_PROIBIDOS and ord(c) >= 32).strip(" .")
    return f"{limpo or 'documento'}.md"
