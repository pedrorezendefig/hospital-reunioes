"""Rotas da Triagem de e-mail (ADR 0051, PRD #646, issues #648 e #650).

Só o Perfil da Ouvidoria entra: o gate é o mesmo do Dossiê
(`require_perfil_ouvidoria`), e Super admin fica de fora como lá. Todo acesso ao
conteúdo de um e-mail recebido entra no log de acesso da Ouvidoria.

O ouvidor lê a lista e o item. Das decisões, virar manifestação (#650) mora
aqui só como a pré-carga: quem cria o caso é o registro manual
(`POST /ouvidoria/manifestacoes` com o `email_recebido_id`). Descartar e
juntar a um caso chegam nas fatias seguintes.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from httpx import HTTPError
from postgrest.exceptions import APIError

from app.config import settings
from app.dependencies import get_supabase_client
from app.limiter import limiter
from app.routers.ouvidoria import EXPIRACAO_URL_ANEXO_SEGUNDOS, require_perfil_ouvidoria
from app.services import ouvidoria_triagem_email as triagem
from app.services import storage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ouvidoria/triagem-email", tags=["ouvidoria-triagem-email"])


@router.get("")
@limiter.limit("60/minute")
async def listar_emails_recebidos(
    request: Request,
    me: dict = Depends(require_perfil_ouvidoria),
    supabase=Depends(get_supabase_client),
):
    """Os e-mails recebidos, pendentes primeiro, na ordem de chegada. Só o
    cabeçalho: o corpo sai quando o ouvidor abre o item."""
    return {"emails": triagem.listar(supabase)}


@router.get("/{email_id}")
@limiter.limit("60/minute")
async def ver_email_recebido(
    request: Request,
    email_id: str,
    me: dict = Depends(require_perfil_ouvidoria),
    supabase=Depends(get_supabase_client),
):
    """O item aberto: cabeçalho, corpo em texto e anexos. O HTML do e-mail fica
    guardado e não sai daqui (a tela desenha só o texto)."""
    item = triagem.carregar_item(supabase, email_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="E-mail não encontrado")
    triagem.registrar_acesso_ao_email(supabase, me, email_id, "ver_email_recebido")
    return item


@router.get("/{email_id}/pre-carga")
@limiter.limit("60/minute")
async def pre_carga_da_manifestacao(
    request: Request,
    email_id: str,
    me: dict = Depends(require_perfil_ouvidoria),
    supabase=Depends(get_supabase_client),
):
    """Os valores com que o modal "Nova manifestação" abre quando o e-mail vira
    manifestação (issue #650, ADR 0051 decisão 2). Quem cria o caso continua
    sendo o registro manual, com o `email_recebido_id` desta resposta."""
    item = triagem.carregar_item(supabase, email_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="E-mail não encontrado")
    if item["estado"] != triagem.PENDENTE:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=triagem.RECUSA_JA_DECIDIDO)
    triagem.registrar_acesso_ao_email(supabase, me, email_id, "pre_carga_manifestacao")
    return triagem.pre_carga(item)


@router.get("/{email_id}/anexos/{anexo_id}/url")
@limiter.limit("60/minute")
async def abrir_anexo_do_email(
    request: Request,
    email_id: str,
    anexo_id: str,
    me: dict = Depends(require_perfil_ouvidoria),
    supabase=Depends(get_supabase_client),
):
    """URL assinada, com expiração, para abrir o anexo do e-mail. O bucket é o
    privado da Ouvidoria: caminho público não existe."""
    anexo = triagem.caminho_do_anexo(supabase, email_id, anexo_id)
    if anexo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Anexo não encontrado")
    url = storage.signed_url(
        supabase,
        bucket=settings.supabase_storage_bucket_anexos_ouvidoria,
        path=anexo["storage_path"],
        expires_in=EXPIRACAO_URL_ANEXO_SEGUNDOS,
    )
    if url is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Não foi possível abrir o anexo agora. Tente de novo em instantes.",
        )
    triagem.registrar_acesso_ao_email(supabase, me, email_id, "abrir_anexo_email")
    return {"url": url, "filename": anexo["filename"], "expira_em_segundos": EXPIRACAO_URL_ANEXO_SEGUNDOS}


@router.post("/{email_id}/descarte")
@limiter.limit("60/minute")
async def descartar_email_recebido(
    request: Request,
    email_id: str,
    me: dict = Depends(require_perfil_ouvidoria),
    supabase=Depends(get_supabase_client),
):
    """Descarta o item: fica só o cabeçalho e quem descartou (issue #649, ADR
    0051 decisão 5). Sem motivo obrigatório, e idempotente."""
    try:
        desfecho = triagem.descartar(supabase, me, email_id, datetime.now(UTC))
    except (HTTPError, APIError, OSError) as exc:
        # Banco que não responde é "tente de novo", e não erro de servidor: a
        # mesma régua do registro manual (#650). O descarte é idempotente, e a
        # nova tentativa completa o que tiver ficado pela metade. Só o tipo vai
        # para o log: o `details` do `APIError` traz a linha, com o corpo.
        logger.warning("Falha ao descartar o e-mail recebido %s (%s)", email_id, type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Não foi possível descartar o e-mail agora. Tente de novo em instantes.",
        ) from None
    if desfecho == triagem.DESCARTE_SEM_ITEM:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="E-mail não encontrado")
    if desfecho == triagem.DESCARTE_RECUSADO:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Este e-mail já virou manifestação ou foi juntado a um caso, e não pode ser descartado",
        )
    triagem.registrar_acesso_ao_email(supabase, me, email_id, "descartar_email")
    return triagem.carregar_item(supabase, email_id)
