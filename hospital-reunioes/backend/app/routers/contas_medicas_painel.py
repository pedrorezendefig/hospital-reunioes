"""O Painel de Contas médicas (issue #1137, PRD #1128, ADR 0070).

A rota de agregados da tela `/contas-medicas/painel`. Cada cartão e cada bloco
tem a própria chave no payload, para um cartão novo entrar sem reescrever os
outros.

Router próprio, com o mesmo prefixo do módulo, para o Painel andar sem disputar
o arquivo das outras telas.
"""

from __future__ import annotations

from datetime import date
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from app.dependencies import get_supabase_client, require_permissao_cm
from app.limiter import limiter
from app.services.contas_medicas.coordenacao import incluido_pela_coordenacao
from app.services.contas_medicas.painel import montar_painel

router = APIRouter(prefix="/contas-medicas", tags=["contas-medicas"])


@router.get("/painel")
@limiter.limit("60/minute")
async def painel(
    request: Request,
    semana: date = Query(...),
    operadora_id: UUID | None = Query(default=None),
    tipo: Literal["parcial", "unica"] | None = Query(default=None),
    me: dict = Depends(require_permissao_cm()),
    supabase=Depends(get_supabase_client),
) -> dict:
    """Os agregados da semana escolhida (qualquer dia dela), da operadora e do
    tipo de conta, quando vierem.

    Basta ter o eixo do módulo. Quem não tem "painel completo" recebe só a
    própria linha de produção, filtrada no servidor.
    """
    completo = "painel_completo" in me["permissoes_cm"]
    operadora = str(operadora_id) if operadora_id else None
    painel = montar_painel(
        supabase,
        semana=semana,
        operadora_id=operadora,
        tipo=tipo,
        so_da_faturista=None if completo else me["id"],
    )
    # O cartão da coordenação (#1143): só com a permissão, fora da nota e da produção.
    if "conferencia_coordenacao" in me["permissoes_cm"]:
        painel["coordenacao"] = incluido_pela_coordenacao(supabase, semana=semana, operadora_id=operadora, tipo=tipo)
    return painel
