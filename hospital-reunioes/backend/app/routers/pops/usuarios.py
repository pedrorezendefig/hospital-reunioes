"""Router /pops/admin/usuarios — administração de acesso do contexto POPs.

O Superadmin (POPs) concede/revoga o `perfil_pop` da pessoa (entidade única
dos dois contextos, ADR 0007). Conceder a quem não loga provisiona o login
automaticamente (reusa app/services/auth_provisioning) sem dar papel no
contexto Reuniões: access_profile fica NULL. Revogar zera o perfil — os
gates `require_perfil_pop` encerram o acesso ao contexto.
"""

from __future__ import annotations

import logging
import secrets

from fastapi import APIRouter, Depends, HTTPException, Query, status
from starlette.requests import Request
from supabase import Client

from app.dependencies import (
    get_supabase_client,
    require_perfil_pop,
    require_super_admin_ou_perfil_pop,
)
from app.models.pops_schemas import (
    PerfilPopResponse,
    PerfilPopUpdate,
    PopsSetorResponse,
    PopsUsuarioResponse,
    VinculosSetorUpdate,
)
from app.services import audit
from app.services.auth_provisioning import provision_auth_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pops/admin/usuarios", tags=["pops", "admin"])


def _fetch_participante(supabase: Client, participante_id: str) -> dict:
    result = (
        supabase.table("participantes")
        .select("id, nome_completo, email, auth_user_id, access_profile, perfil_pop")
        .eq("id", participante_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Participante não encontrado")
    return result.data[0]


@router.get("", response_model=list[PopsUsuarioResponse])
async def listar_usuarios_pops(
    q: str | None = Query(None, description="Busca por nome ou email"),
    com_perfil: bool | None = Query(None, description="True: só quem tem perfil POP"),
    limit: int = Query(50, ge=1, le=500),
    _actor: dict = Depends(require_perfil_pop("superadmin")),
    supabase: Client = Depends(get_supabase_client),
):
    """Lista pessoas para o admin POPs (conceder/revogar perfil, vínculos).

    Filtra em Python: a base de participantes é pequena (centenas) e o
    Superadmin (POPs) não passa pela porta /admin/usuarios das Reuniões.
    """
    result = (
        supabase.table("participantes")
        .select("id, nome_completo, email, perfil_pop, auth_user_id, ativo")
        .order("nome_completo")
        .execute()
    )
    rows = result.data or []
    if com_perfil is not None:
        rows = [r for r in rows if bool(r.get("perfil_pop")) == com_perfil]
    if q:
        needle = q.strip().lower()
        rows = [
            r
            for r in rows
            if needle in (r.get("nome_completo") or "").lower() or needle in (r.get("email") or "").lower()
        ]
    return rows[:limit]


@router.patch("/{participante_id}/perfil-pop", response_model=PerfilPopResponse)
async def definir_perfil_pop(
    participante_id: str,
    body: PerfilPopUpdate,
    request: Request,
    actor: dict = Depends(require_super_admin_ou_perfil_pop("superadmin")),
    supabase: Client = Depends(get_supabase_client),
):
    """Concede, troca ou revoga (null) o perfil POP de uma pessoa.

    Autoridade unificada (ADR 0014): Super Admin de Reuniões OU superadmin POP.
    """
    if body.perfil_pop is None and actor.get("id") == participante_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Você não pode revogar seu próprio perfil POP",
        )

    alvo = _fetch_participante(supabase, participante_id)

    update: dict = {"perfil_pop": body.perfil_pop}
    provisionado = False
    new_password: str | None = None

    if body.perfil_pop and not alvo.get("auth_user_id"):
        email = alvo.get("email")
        if not email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Pessoa sem email cadastrado — informe um email antes de conceder o perfil",
            )
        new_password = secrets.token_urlsafe(16)
        auth_uid = provision_auth_user(
            supabase,
            alvo.get("nome_completo") or "",
            email,
            role=body.perfil_pop,
            password=new_password,
        )
        if not auth_uid:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erro ao provisionar login no provedor de autenticação",
            )
        update["auth_user_id"] = auth_uid
        # Login nasceu pelo POPs: sem papel no contexto Reuniões (ADR 0007).
        update["access_profile"] = None
        provisionado = True

    result = supabase.table("participantes").update(update).eq("id", participante_id).execute()
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao atualizar perfil POP",
        )

    audit.log_action(
        supabase,
        actor=actor,
        action="POPS_PERFIL_POP" if body.perfil_pop else "POPS_PERFIL_POP_REVOKE",
        target_type="participante",
        target_id=participante_id,
        metadata={
            "email": alvo.get("email"),
            "perfil_antes": alvo.get("perfil_pop"),
            "perfil_depois": body.perfil_pop,
            "provisionado": provisionado,
        },
        reason=body.reason,
        request=request,
    )

    return PerfilPopResponse(
        participante_id=participante_id,
        perfil_pop=body.perfil_pop,
        provisionado=provisionado,
        new_password=new_password,
    )


def _setores_da_pessoa(supabase: Client, participante_id: str) -> list[dict]:
    vinculos = (
        supabase.table("pops_setores_participantes").select("setor_id").eq("participante_id", participante_id).execute()
    )
    setor_ids = [v["setor_id"] for v in (vinculos.data or [])]
    if not setor_ids:
        return []
    setores = supabase.table("pops_setores").select("id, nome, sigla").in_("id", setor_ids).order("nome").execute()
    return setores.data or []


@router.put("/{participante_id}/setores", response_model=list[PopsSetorResponse])
async def definir_setores(
    participante_id: str,
    body: VinculosSetorUpdate,
    request: Request,
    actor: dict = Depends(require_perfil_pop("superadmin")),
    supabase: Client = Depends(get_supabase_client),
):
    """Substitui os vínculos pessoa↔Setor pelo conjunto informado."""
    alvo = _fetch_participante(supabase, participante_id)

    setor_ids = list(dict.fromkeys(body.setor_ids))  # dedup preservando ordem
    if setor_ids:
        existentes = supabase.table("pops_setores").select("id").in_("id", setor_ids).execute()
        ids_validos = {row["id"] for row in (existentes.data or [])}
        invalidos = [sid for sid in setor_ids if sid not in ids_validos]
        if invalidos:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Setor(es) inexistente(s): {', '.join(invalidos)}",
            )

    supabase.table("pops_setores_participantes").delete().eq("participante_id", participante_id).execute()
    if setor_ids:
        supabase.table("pops_setores_participantes").insert(
            [{"setor_id": sid, "participante_id": participante_id} for sid in setor_ids]
        ).execute()

    audit.log_action(
        supabase,
        actor=actor,
        action="POPS_VINCULOS_SETOR",
        target_type="participante",
        target_id=participante_id,
        metadata={"email": alvo.get("email"), "setor_ids": setor_ids},
        request=request,
    )

    return _setores_da_pessoa(supabase, participante_id)


@router.get("/{participante_id}/setores", response_model=list[PopsSetorResponse])
async def listar_setores_da_pessoa(
    participante_id: str,
    _actor: dict = Depends(require_perfil_pop("superadmin")),
    supabase: Client = Depends(get_supabase_client),
):
    """Lista os Setores vinculados à pessoa."""
    _fetch_participante(supabase, participante_id)
    return _setores_da_pessoa(supabase, participante_id)
