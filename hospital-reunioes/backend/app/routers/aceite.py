"""Endpoints públicos do Aceite interno (ADR 0030, issue #277).

Casca fina sobre o `aceite_service`: a página pública (sem login) valida o
token opaco de uso único, mostra a ata completa e registra o aceite. Token
reusado, expirado ou inválido falha sem nenhum efeito. Rate limit apertado:
o endpoint é público e o token é a única credencial.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from app.dependencies import get_supabase_client
from app.limiter import limiter
from app.services import aceite_service

router = APIRouter(prefix="/aceite", tags=["aceite"])
logger = logging.getLogger(__name__)

_DETALHE_INVALIDO = "Link de aceite inválido."
_DETALHE_USADO = "Este aceite já foi registrado. Nada mais a fazer por aqui."
_DETALHE_EXPIRADO = "Este link de aceite não está mais ativo."


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
