import logging

from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import get_current_user, get_participante_for_user, get_supabase_client
from app.models.schemas import PerfilStats

router = APIRouter(prefix="/perfil", tags=["perfil"])
logger = logging.getLogger(__name__)


@router.get("/stats", response_model=PerfilStats)
async def get_stats(
    current_user: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    participante = await get_participante_for_user(current_user, supabase, fields="id")
    if not participante:
        raise HTTPException(status_code=404, detail="Participante não encontrado")

    pid = participante["id"]

    reunioes_result = (
        supabase.table("reuniao_participantes")
        .select("id", count="exact")
        .eq("participante_id", pid)
        .execute()
    )
    reunioes_count = reunioes_result.count or 0

    ativas_result = (
        supabase.table("pendencias")
        .select("id", count="exact")
        .eq("responsavel_id", pid)
        .in_("status", ["PENDENTE", "EM_PROGRESSO"])
        .execute()
    )
    ativas_count = ativas_result.count or 0

    concluidas_result = (
        supabase.table("pendencias")
        .select("id, updated_at, prazo", count="exact")
        .eq("responsavel_id", pid)
        .eq("status", "CONCLUIDO")
        .execute()
    )
    concluidas_count = concluidas_result.count or 0

    no_prazo_pct = 0.0
    if concluidas_count > 0 and concluidas_result.data:
        no_prazo = 0
        for p in concluidas_result.data:
            if p.get("prazo") and p.get("updated_at"):
                updated = p["updated_at"][:10]
                if updated <= p["prazo"]:
                    no_prazo += 1
            elif not p.get("prazo"):
                no_prazo += 1
        no_prazo_pct = round((no_prazo / concluidas_count) * 100, 1)

    return PerfilStats(
        reunioes=reunioes_count,
        pendencias_ativas=ativas_count,
        concluidas=concluidas_count,
        no_prazo_percentual=no_prazo_pct,
    )
