"""O Painel de Contas médicas (issue #1137, PRD #1128, ADR 0070).

A rota de agregados da tela `/contas-medicas/painel`. Cada cartão e cada bloco
tem a própria chave no payload, para um cartão novo entrar sem reescrever os
outros.

Router próprio, com o mesmo prefixo do módulo, para o Painel andar sem disputar
o arquivo das outras telas.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query, Request

from app.dependencies import get_supabase_client, require_permissao_cm
from app.limiter import limiter
from app.services.contas_medicas.painel import montar_painel

router = APIRouter(prefix="/contas-medicas", tags=["contas-medicas"])


@router.get("/painel")
@limiter.limit("60/minute")
async def painel(
    request: Request,
    semana: date = Query(...),
    me: dict = Depends(require_permissao_cm()),
    supabase=Depends(get_supabase_client),
) -> dict:
    """Os agregados da semana escolhida (qualquer dia dela)."""
    return montar_painel(supabase, semana=semana)
