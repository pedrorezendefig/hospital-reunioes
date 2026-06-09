"""Transcrição de voz da Nota (issue #35).

Módulo profundo com uma porta de entrada: `transcrever(audio, formato) →
texto`. O Facilitador dita a Nota; o front grava o áudio e manda os bytes;
aqui eles viram texto que cai **editável no corpo**. Reusa a chave/billing do
Pipeline (`_get_llm`) chamando o endpoint `/audio/transcriptions` do OpenRouter
com `gpt-4o-mini-transcribe`.

O áudio **não é persistido** em lugar nenhum — entra como bytes, sai como
texto, e nada é gravado. Se a transcrição falhar (sem chave, áudio vazio ou
API fora), levanta `TranscricaoIndisponivelError` para o endpoint devolver um
aviso claro e o Facilitador digitar como fallback.
"""

import logging

from app.config import settings
from app.services.ai_processor import _get_llm, _llm_provider, _log_llm_call

logger = logging.getLogger(__name__)


class TranscricaoIndisponivelError(RuntimeError):
    """Não foi possível transcrever: provider ausente, áudio vazio ou API fora."""


# Extensão do arquivo enviado ao endpoint a partir do MIME do MediaRecorder.
# O OpenRouter/OpenAI usa o nome só para inferir o container; default webm
# (Chrome/Firefox); Safari grava mp4.
_EXT_POR_MIME = {
    "audio/webm": "webm",
    "audio/mp4": "mp4",
    "audio/mpeg": "mp3",
    "audio/mpga": "mp3",
    "audio/ogg": "ogg",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
}


def transcrever(audio: bytes, formato: str) -> str:
    """Transcreve o áudio ditado em texto pt-BR.

    Args:
        audio: bytes do áudio gravado pelo MediaRecorder. Vazio → erro (não
            chama a IA).
        formato: MIME do áudio (ex.: "audio/webm;codecs=opus"). Define a
            extensão do arquivo enviado ao endpoint.

    Returns:
        O texto transcrito, sem espaços nas bordas. String vazia se o áudio
        não tiver fala reconhecível.

    Raises:
        TranscricaoIndisponivelError: sem chave LLM, áudio vazio, ou a API de
            transcrição falhou.
    """
    if not audio:
        raise TranscricaoIndisponivelError("Áudio vazio — nada a transcrever")

    provider = _llm_provider()
    if provider == "mock":
        raise TranscricaoIndisponivelError("Nenhuma chave LLM configurada para transcrição")

    client, _chat_model, extra = _get_llm()
    model = settings.transcricao_model
    _log_llm_call("transcricao-nota", provider, model)

    mime = (formato or "audio/webm").split(";")[0].strip()
    ext = _EXT_POR_MIME.get(mime, "webm")

    try:
        resposta = client.audio.transcriptions.create(
            model=model,
            file=(f"nota-voz.{ext}", audio, formato or "audio/webm"),
            **extra,
        )
    except Exception as e:
        logger.error(f"[Transcricao] Falha na transcrição via {provider}: {type(e).__name__}: {e}")
        raise TranscricaoIndisponivelError(str(e)) from e

    texto = (resposta.text or "").strip()
    logger.info(f"[Transcricao] {len(audio)} bytes ({mime}) → {len(texto)} chars via {provider}")
    return texto
