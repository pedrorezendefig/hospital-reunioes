"""Endpoints públicos do Aceite interno (ADR 0030, issue #277).

Casca fina sobre o `aceite_service`: a página pública (sem login) valida o
token opaco de uso único, mostra a ata completa e registra o aceite. Token
reusado, expirado ou inválido falha sem nenhum efeito. Rate limit apertado:
o endpoint é público e o token é a única credencial.

**Gate por rota, e não no router (issue #440).** As duas rotas de `/{token}`
são públicas de propósito: o signatário que assina pela página não precisa ter
login, e uma dependency de router as fecharia. Quem tem gate é a única rota
autenticada daqui, `POST /meu-link`, e o gate dela é o par (Reunião,
signatário) do usuário logado, mais `barrar_desligado`: sessão do Supabase
Auth sobrevive ao desligamento, então sem essa checagem quem foi desligado
reemitia o próprio link enquanto o access token durasse.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.dependencies import (
    barrar_desligado,
    get_current_user,
    get_participante_for_user,
    get_supabase_client,
)
from app.limiter import limiter
from app.services import aceite_service

router = APIRouter(prefix="/aceite", tags=["aceite"])
logger = logging.getLogger(__name__)

_DETALHE_INVALIDO = "Link de aceite inválido."
_DETALHE_USADO = "Este aceite já foi registrado. Nada mais a fazer por aqui."
_DETALHE_EXPIRADO = "Este link de aceite não está mais ativo."


class MeuLinkRequest(BaseModel):
    id_reuniao: str = Field(min_length=1, max_length=30)


# Declarado ANTES de `/{token}`: caminho fixo precisa casar primeiro, senão a
# rota com parâmetro engole "meu-link".
@router.post("/meu-link")
@limiter.limit("10/minute")
async def meu_link_de_aceite(
    request: Request,
    body: MeuLinkRequest,
    current_user: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    """Link de aceite do próprio signatário, para o sino do Facilitador.

    A notificação in-app não carrega mais o token (issue #295): guardá-lo em
    claro furava o invariante hash-only e, num vazamento do banco, entregava
    tokens utilizáveis. Aqui a autorização é o par (Reunião, signatário) do
    usuário autenticado, então ninguém pega o link de outra pessoa, mais o
    desligamento (issue #440): quem saiu do hospital não reemite link nenhum.

    Como o banco só guarda o hash, o link é reemitido, não lido de volta: o
    link que foi por email deixa de valer a partir daqui.
    """
    me = await get_participante_for_user(current_user, supabase)
    barrar_desligado(me)
    if not me:
        raise HTTPException(status_code=404, detail=_DETALHE_INVALIDO)
    try:
        token = aceite_service.reemitir_link_aceite_interno(supabase, body.id_reuniao, me["id"])
    except aceite_service.TokenInvalidoError:
        raise HTTPException(status_code=404, detail=_DETALHE_INVALIDO)
    except aceite_service.TokenJaUsadoError:
        raise HTTPException(status_code=410, detail=_DETALHE_USADO)
    except aceite_service.TokenExpiradoError:
        raise HTTPException(status_code=410, detail=_DETALHE_EXPIRADO)
    return {"url": f"/aceite/{token}"}


@router.get("/{token}")
@limiter.limit("30/minute")
async def consultar_aceite(
    request: Request,
    token: str,
    supabase=Depends(get_supabase_client),
):
    """Dados da página pública: a ata completa + quem está aceitando."""
    try:
        return aceite_service.consultar_aceite_interno(supabase, token)
    except aceite_service.TokenInvalidoError:
        raise HTTPException(status_code=404, detail=_DETALHE_INVALIDO)
    except aceite_service.TokenJaUsadoError:
        raise HTTPException(status_code=410, detail=_DETALHE_USADO)
    except aceite_service.TokenExpiradoError:
        raise HTTPException(status_code=410, detail=_DETALHE_EXPIRADO)


@router.post("/{token}/aceitar")
@limiter.limit("10/minute")
async def registrar_aceite(
    request: Request,
    token: str,
    supabase=Depends(get_supabase_client),
):
    """Botão "Li e aceito": registra o aceite (origem `aceite_interno`), cria
    as Pendências do signatário e aplica o desfecho terminal quando este era
    o último aceite necessário."""
    try:
        return aceite_service.registrar_aceite_interno(supabase, token)
    except aceite_service.TokenInvalidoError:
        raise HTTPException(status_code=404, detail=_DETALHE_INVALIDO)
    except aceite_service.TokenJaUsadoError:
        raise HTTPException(status_code=410, detail=_DETALHE_USADO)
    except aceite_service.TokenExpiradoError:
        raise HTTPException(status_code=410, detail=_DETALHE_EXPIRADO)
