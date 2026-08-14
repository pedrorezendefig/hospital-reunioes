"""Painel de ouvidoria (issue #292, ADR 0031 decisão 3): a equipe do hospital
enxerga os protocolos registrados pela Ana e marca cada um como respondido.

Fluxo JWT (usuário logado), fora da API de serviço da Ana. Índice, não dossiê:
o painel expõe os mesmos campos da API da Ana e nada além deles; protocolo
nasce só pelo registro da Ana (não existe rota de criação aqui).
"""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from postgrest.exceptions import APIError
from pydantic import BaseModel
from supabase import Client

from app.dependencies import (
    get_current_user,
    get_participante_for_user,
    get_supabase_client,
    tem_acesso_reunioes,
)
from app.limiter import limiter
from app.routers.ana import _CAMPOS_PROTOCOLO, _CAMPOS_PROTOCOLO_TUPLA

router = APIRouter(prefix="/ouvidoria", tags=["ouvidoria"])


async def require_acesso_painel(
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
) -> None:
    """Gate do painel: facilitadores, secretárias e super admins (qualquer papel
    no contexto Reuniões). Quem só tem perfil POP, ou token órfão, recebe 403."""
    me = await get_participante_for_user(current_user, supabase)
    if not me or not tem_acesso_reunioes(me):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito à equipe de Reuniões",
        )


@router.get("/protocolos", dependencies=[Depends(require_acesso_painel)])
@limiter.limit("60/minute")
async def listar_protocolos(
    request: Request,
    supabase=Depends(get_supabase_client),
):
    """Todos os protocolos, mais recentes primeiro, com prazo e status."""
    result = supabase.table("ouvidoria_protocolos").select(_CAMPOS_PROTOCOLO).order("numero", desc=True).execute()
    return {"protocolos": result.data or []}


class MudancaStatus(BaseModel):
    """O painel só alterna entre aberto e respondido: 'encerrado' existe no
    CHECK do banco, mas não é ação da equipe pela tela."""

    status: Literal["aberto", "respondido"]


@router.patch("/protocolos/{protocolo_id}/status", dependencies=[Depends(require_acesso_painel)])
@limiter.limit("60/minute")
async def mudar_status_protocolo(
    request: Request,
    protocolo_id: str,
    mudanca: MudancaStatus,
    supabase=Depends(get_supabase_client),
):
    """Persiste o novo status; a consulta da API da Ana enxerga na hora
    (leitura direta, sem cache)."""
    try:
        atual = supabase.table("ouvidoria_protocolos").select("id, status").eq("id", protocolo_id).execute()
    except APIError as exc:
        # Id malformado (não-UUID) estoura no PostgREST: vira 404, sem vazar
        # detalhe interno do Postgres pelo handler global.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Protocolo não encontrado") from exc
    if not atual.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Protocolo não encontrado")
    # 'encerrado' entra pelo import do NocoDB e é terminal: o painel só
    # alterna aberto/respondido e não pode destruir esse estado.
    if atual.data[0]["status"] == "encerrado":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Protocolo encerrado não pode ser alterado",
        )
    result = supabase.table("ouvidoria_protocolos").update({"status": mudanca.status}).eq("id", protocolo_id).execute()
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Protocolo não encontrado")
    row = result.data[0]
    return {campo: row.get(campo) for campo in _CAMPOS_PROTOCOLO_TUPLA}
