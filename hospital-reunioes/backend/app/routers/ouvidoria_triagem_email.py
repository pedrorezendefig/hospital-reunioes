"""Rotas da Triagem de e-mail (ADR 0051, PRD #646, issue #648).

Só o Perfil da Ouvidoria entra: o gate é o mesmo do Dossiê
(`require_perfil_ouvidoria`), e Super admin fica de fora como lá. Todo acesso ao
conteúdo de um e-mail recebido entra no log de acesso da Ouvidoria.

Nesta fatia o ouvidor só lê: a lista e o item. As decisões (descartar, virar
manifestação, juntar a um caso) chegam nas fatias seguintes, acrescentadas no
fim deste arquivo.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.config import settings
from app.dependencies import get_supabase_client
from app.limiter import limiter
from app.routers.ouvidoria import EXPIRACAO_URL_ANEXO_SEGUNDOS, require_perfil_ouvidoria
from app.services import ouvidoria_triagem_email as triagem
from app.services import storage

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
