"""Router da transcrição de voz (issue #35; movido de Notas — ADR 0011).

O comando por voz nasceu na Nota, mas sobreviveu à descontinuação dela
(ADR 0011) porque a Ata Guiada (#50) e o chat de elaboração de POPs também
ditam por aqui: o front grava o áudio (MediaRecorder), manda os bytes e o
texto transcrito cai **editável** no destino da tela (input do chat).
"""

import logging

import anyio
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.dependencies import (
    get_current_user,
    get_participante_for_user,
    get_supabase_client,
    require_acesso_reunioes,
)
from app.models.schemas import TranscricaoResponse
from app.services.transcricao_service import TranscricaoIndisponivelError, transcrever

router = APIRouter(
    prefix="/transcricao",
    tags=["transcricao"],
    # Gate de contexto (ADR 0007): sem papel nas Reuniões -> 403 em todo o router
    # (preserva o comportamento do antigo POST /notas/transcrever).
    dependencies=[Depends(require_acesso_reunioes)],
)
logger = logging.getLogger(__name__)

# Teto do upload de áudio do comando por voz (issue #35): 25 MB = limite da API
# de transcrição (Whisper). Barra antes de gastar memória/IA.
MAX_AUDIO_BYTES = 25 * 1024 * 1024


@router.post("/voz", response_model=TranscricaoResponse)
async def transcrever_voz(
    audio: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    """Comando por voz (issue #35): recebe o áudio ditado e devolve o texto
    transcrito para cair **editável no destino** — nada é persistido aqui.

    O áudio **não é persistido**: entra como bytes em memória, vira texto e é
    descartado. Falha de transcrição vira 502 com aviso claro — o front mostra
    o aviso e o Facilitador digita como fallback.
    """
    me = await get_participante_for_user(current_user, supabase)
    if not me:
        raise HTTPException(status_code=403, detail="Participante não encontrado")

    conteudo = await audio.read()
    if len(conteudo) > MAX_AUDIO_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Áudio acima do limite de {MAX_AUDIO_BYTES // (1024 * 1024)} MB.",
        )

    # Transcrição é chamada de rede bloqueante — roda em thread para não travar
    # o event loop (uvicorn single-worker), padrão do PR #39.
    try:
        texto = await anyio.to_thread.run_sync(transcrever, conteudo, audio.content_type or "audio/webm")
    except TranscricaoIndisponivelError as e:
        logger.warning(f"Transcrição de voz indisponível para {me['id']}: {e}")
        raise HTTPException(
            status_code=502,
            detail="Não foi possível transcrever o áudio agora. Digite o texto manualmente.",
        ) from e
    logger.info(f"Voz transcrita para {me['id']}: {len(texto)} chars")
    return {"texto": texto}
