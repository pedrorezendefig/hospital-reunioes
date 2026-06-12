"""Router /pops/{pop_id}/assinatura — reenvio do Envelope ClickSign (issue #87).

O disparo normal é automático na aprovação do Validador; este endpoint é a
re-tentativa quando aquele envio falhou (ou o Envelope foi recusado/expirou
e o webhook limpou os IDs): mesma orquestração, sem duplicar Envelope — com
envio anterior OK, é no-op idempotente.

Guardas (papel × estado) vivem em app.services.pops_dominio.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from starlette.requests import Request

from app.dependencies import get_supabase_client, require_perfil_pop
from app.models.pops_schemas import PERFIS_POP
from app.routers.pops.revisao import _carregar_pop_setor_versao
from app.services import pops_clicksign_service, pops_dominio

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pops/{pop_id}/assinatura", tags=["pops"])


@router.post("/reenviar")
async def reenviar_assinatura(
    pop_id: str,
    request: Request,
    actor: dict = Depends(require_perfil_pop(*PERFIS_POP)),
    supabase=Depends(get_supabase_client),
):
    """Re-tenta o envio ao ClickSign de uma Versão EM_ASSINATURA. Exclusivo
    do Validador designado — o mesmo papel cujo aprovar disparou o envio."""
    pop, setor, versao = _carregar_pop_setor_versao(pop_id, supabase)
    try:
        pops_dominio.exigir_validador(actor, pop)
    except pops_dominio.AcessoNegadoError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    try:
        pops_dominio.exigir_estado_em_assinatura(versao)
    except pops_dominio.TransicaoInvalidaError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    enviada = pops_clicksign_service.enviar_para_assinatura(supabase, pop, setor, versao, actor=actor, request=request)
    return {"estado": versao["estado"], "assinatura_enviada": enviada is not None}
