"""A fila de Validação de Contas médicas (issue #1142, PRD #1129, ADR 0070).

As rotas da tela `/contas-medicas/validacao`: os temas abertos e as decisões
de cada um. Toda rota passa pelo gate "decidir na validação".

Router próprio, com o mesmo prefixo do módulo, para a tela andar sem disputar
o arquivo das outras telas.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.dependencies import get_supabase_client, require_permissao_cm
from app.limiter import limiter
from app.services.contas_medicas.validacao import fila_de_validacao

router = APIRouter(prefix="/contas-medicas", tags=["contas-medicas"])

_PODE_DECIDIR = require_permissao_cm("decidir_validacao")


@router.get("/validacao")
@limiter.limit("60/minute")
async def ver_fila_de_validacao(
    request: Request,
    me: dict = Depends(_PODE_DECIDIR),
    supabase=Depends(get_supabase_client),
) -> dict:
    """Os temas abertos, do maior R$ em jogo para o menor, e os três números do topo."""
    return fila_de_validacao(supabase)
