"""API da Ana (ADR 0031): endpoints de serviço consumidos pela agente de IA.

Autenticação por API key de serviço dedicada (header X-API-Key, validado
contra ANA_API_KEY), fora do fluxo JWT. Leitura direta do banco, sem cache:
edição no admin vale na chamada seguinte.
"""

import logging

from fastapi import APIRouter, Depends, Request

from app.dependencies import get_supabase_client, require_ana_api_key
from app.limiter import limiter

router = APIRouter(prefix="/ana", tags=["ana"], dependencies=[Depends(require_ana_api_key)])
logger = logging.getLogger(__name__)


@router.get("/consultas-particulares")
@limiter.limit("60/minute")
async def listar_consultas_particulares(
    request: Request,
    supabase=Depends(get_supabase_client),
):
    """Consultas particulares ativas, com preços e diferenciais."""
    result = supabase.table("consultas_particulares").select("*").eq("ativo", True).order("especialidade").execute()
    return {"consultas_particulares": result.data or []}
