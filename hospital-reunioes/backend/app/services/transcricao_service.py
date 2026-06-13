"""Transcrição de voz (issue #35; contrato OpenRouter — issue #44).

Módulo profundo com uma porta de entrada: `transcrever(audio, formato) →
texto`. O Facilitador dita (Ata Guiada, chat de POPs); o front grava o áudio
e manda os bytes; aqui eles viram texto que cai **editável** no destino da
tela. Chama o endpoint
`/audio/transcriptions` do OpenRouter com um corpo **JSON** — o áudio em
base64 dentro de `input_audio` —, autenticado com a mesma `OPENROUTER_API_KEY`
do Pipeline. O texto vem no campo `text` da resposta.

O áudio **não é persistido** em lugar nenhum — entra como bytes, sai como
texto, e nada é gravado. Se a transcrição falhar (sem chave, áudio vazio ou
API fora), levanta `TranscricaoIndisponivelError` para o endpoint devolver um
aviso claro e o Facilitador digitar como fallback.
"""

import base64
import logging

import httpx

from app.config import settings
from app.services.ai_processor import _OPENROUTER_HEADERS, _llm_provider, _log_llm_call

logger = logging.getLogger(__name__)

# Timeout generoso: transcrição de áudio é mais lenta que um chat completion.
_TIMEOUT = httpx.Timeout(60.0, connect=10.0)


class TranscricaoIndisponivelError(RuntimeError):
    """Não foi possível transcrever: provider ausente, áudio vazio ou API fora."""


# `format` enviado ao OpenRouter, derivado do MIME do MediaRecorder. Default
# webm (Chrome/Firefox); Safari grava mp4. O OpenRouter usa o container pra
# decodificar o áudio embutido em base64.
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
        formato: MIME do áudio (ex.: "audio/webm;codecs=opus"). Define o
            `format` enviado ao OpenRouter.

    Returns:
        O texto transcrito, sem espaços nas bordas. String vazia se o áudio
        não tiver fala reconhecível.

    Raises:
        TranscricaoIndisponivelError: sem chave do OpenRouter, áudio vazio, ou a
            API de transcrição falhou.
    """
    if not audio:
        raise TranscricaoIndisponivelError("Áudio vazio — nada a transcrever")

    provider = _llm_provider()
    if provider == "mock":
        raise TranscricaoIndisponivelError("Nenhuma chave do OpenRouter configurada para transcrição")

    model = settings.transcricao_model
    _log_llm_call("transcricao-voz", provider, model)

    # Normaliza o MIME: o MediaRecorder do Chrome manda "audio/webm;codecs=opus";
    # o `format` do OpenRouter é só o container ("webm").
    mime = (formato or "audio/webm").split(";")[0].strip()
    fmt = _EXT_POR_MIME.get(mime, "webm")

    payload = {
        "model": model,
        "input_audio": {"data": base64.b64encode(audio).decode("ascii"), "format": fmt},
        "language": "pt",
    }
    headers = {"Authorization": f"Bearer {settings.openrouter_api_key}", **_OPENROUTER_HEADERS}
    url = f"{settings.openrouter_base_url}/audio/transcriptions"

    try:
        resposta = httpx.post(url, json=payload, headers=headers, timeout=_TIMEOUT)
        resposta.raise_for_status()
        dados = resposta.json()
    except Exception as e:
        logger.error(f"[Transcricao] Falha na transcrição via {provider}: {type(e).__name__}: {e}")
        raise TranscricaoIndisponivelError(str(e)) from e

    texto = (dados.get("text") or "").strip()
    logger.info(f"[Transcricao] {len(audio)} bytes ({mime}) → {len(texto)} chars via {provider}")
    return texto
