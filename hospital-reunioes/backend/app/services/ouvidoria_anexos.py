"""Regra do Anexo da Manifestação (issue #321, ADR 0034).

Um lugar só decide o que a ouvidoria aceita guardar: quem chama passa nome e
tamanho e recebe a extensão e o content-type canônicos, ou uma recusa com a
mensagem que o ouvidor lê na tela.

O content-type é derivado da extensão, nunca do que o navegador declarou: o
cliente pode mentir no header, e quem serve o arquivo depois é uma URL assinada
do storage.
"""

from __future__ import annotations

import os

# 20 MB por arquivo (critério de aceite da issue #321). Foto de celular e áudio
# de telefonema cabem; vídeo longo não, e isso é de propósito.
LIMITE_BYTES = 20 * 1024 * 1024
LIMITE_LEGIVEL = "20 MB"

# Imagem, PDF, áudio e documento: o que chega de fato pelo balcão e pelo
# telefone. Executável e arquivo compactado ficam de fora.
TIPOS_PERMITIDOS: dict[str, str] = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".heic": "image/heic",
    ".pdf": "application/pdf",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".ogg": "audio/ogg",
    ".wav": "audio/wav",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".odt": "application/vnd.oasis.opendocument.text",
    ".txt": "text/plain",
}


class AnexoRecusadoError(Exception):
    """Base das recusas. A mensagem é escrita para o ouvidor, não para o log."""


class TipoNaoPermitidoError(AnexoRecusadoError):
    """A extensão não está na lista."""


class AnexoGrandeDemaisError(AnexoRecusadoError):
    """Passou do limite por arquivo."""


def validar_anexo(filename: str, tamanho_bytes: int) -> tuple[str, str]:
    """Devolve (extensão, content-type) do anexo aceito.

    Levanta `TipoNaoPermitidoError` ou `AnexoGrandeDemaisError` com a mensagem
    pronta para a tela."""
    nome = (filename or "").strip()
    extensao = os.path.splitext(nome)[1].lower()

    if extensao not in TIPOS_PERMITIDOS:
        aceitos = ", ".join(sorted(TIPOS_PERMITIDOS))
        rotulo = extensao or "sem extensão"
        raise TipoNaoPermitidoError(f"Arquivo {rotulo} não é aceito. Envie imagem, PDF, áudio ou documento: {aceitos}.")

    if tamanho_bytes <= 0:
        raise AnexoRecusadoError("Arquivo vazio: não há o que anexar.")

    if tamanho_bytes > LIMITE_BYTES:
        enviado = tamanho_bytes / (1024 * 1024)
        raise AnexoGrandeDemaisError(
            f"Arquivo de {enviado:.1f} MB passa do limite de {LIMITE_LEGIVEL} por anexo. "
            "Reduza o arquivo ou envie em partes."
        )

    return extensao, TIPOS_PERMITIDOS[extensao]
