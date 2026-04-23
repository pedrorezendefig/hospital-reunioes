"""Router /admin/super-admins — promover e rebaixar super admins.

Acoes:
- GET  /admin/super-admins              lista todos os super admins ativos.
- POST /admin/super-admins/{id}/promote marca is_super_admin=true (motivo obrigatorio).
- POST /admin/super-admins/{id}/demote  marca is_super_admin=false (motivo obrigatorio).

Regras:
- Todas protegidas por `require_super_admin` (so super admins acessam).
- Demote bloqueia auto-demote (actor nao pode rebaixar a si mesmo).
- Demote bloqueia se restaria 0 super admins (nao pode esvaziar o sistema).
- Promote/demote com motivo sao gravados em audit_log via `audit.log_action`.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from starlette.requests import Request
from supabase import Client

from app.dependencies import get_supabase_client, require_super_admin
from app.models.admin_schemas import ReasonRequest, SuperAdminResponse
from app.services import audit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/super-admins", tags=["admin", "super-admins"])


# ─── Helpers internos ────────────────────────────────────────────────────────


def _fetch_participante(supabase: Client, participante_id: str) -> dict:
    """Busca um participante por id. 404 se nao existir."""
    result = (
        supabase.table("participantes")
        .select("id, nome_completo, email, cargo, setor, role, is_super_admin")
        .eq("id", participante_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Participante nao encontrado",
        )
    return result.data[0]


def _count_super_admins(supabase: Client) -> int:
    """Conta quantos participantes tem is_super_admin=true."""
    result = supabase.table("participantes").select("id").eq("is_super_admin", True).execute()
    return len(result.data or [])


# ─── Endpoints ───────────────────────────────────────────────────────────────


@router.get("", response_model=list[SuperAdminResponse])
async def list_super_admins(
    _actor: dict = Depends(require_super_admin),
    supabase: Client = Depends(get_supabase_client),
):
    """Lista todos os participantes com is_super_admin=true."""
    result = (
        supabase.table("participantes")
        .select("id, nome_completo, email, cargo, setor, role")
        .eq("is_super_admin", True)
        .order("nome_completo")
        .execute()
    )
    return result.data or []


@router.post("/{participante_id}/promote", response_model=SuperAdminResponse)
async def promote_super_admin(
    participante_id: str,
    body: ReasonRequest,
    request: Request,
    actor: dict = Depends(require_super_admin),
    supabase: Client = Depends(get_supabase_client),
):
    """Promove um participante a super admin. Motivo obrigatorio. Loga em audit_log."""
    target = _fetch_participante(supabase, participante_id)

    if target.get("is_super_admin"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Participante ja e super admin",
        )

    update = supabase.table("participantes").update({"is_super_admin": True}).eq("id", participante_id).execute()
    if not update.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Falha ao promover participante",
        )

    audit.log_action(
        supabase,
        actor=actor,
        action="PROMOTE_SUPER_ADMIN",
        target_type="participante",
        target_id=participante_id,
        metadata={
            "target_email": target.get("email"),
            "target_nome": target.get("nome_completo"),
        },
        reason=body.reason,
        request=request,
    )

    return {
        "id": target["id"],
        "nome_completo": target["nome_completo"],
        "email": target["email"],
        "cargo": target.get("cargo"),
        "setor": target.get("setor"),
        "role": target.get("role"),
    }


@router.post("/{participante_id}/demote", response_model=SuperAdminResponse)
async def demote_super_admin(
    participante_id: str,
    body: ReasonRequest,
    request: Request,
    actor: dict = Depends(require_super_admin),
    supabase: Client = Depends(get_supabase_client),
):
    """Rebaixa um participante de super admin. Motivo obrigatorio. Loga em audit_log.

    Bloqueios:
    - actor nao pode rebaixar a si mesmo.
    - nao pode deixar o sistema sem nenhum super admin.
    """
    if actor.get("id") == participante_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Voce nao pode rebaixar a si mesmo",
        )

    target = _fetch_participante(supabase, participante_id)

    if not target.get("is_super_admin"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Participante nao e super admin",
        )

    total = _count_super_admins(supabase)
    if total <= 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nao e possivel rebaixar o ultimo super admin do sistema",
        )

    update = supabase.table("participantes").update({"is_super_admin": False}).eq("id", participante_id).execute()
    if not update.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Falha ao rebaixar participante",
        )

    audit.log_action(
        supabase,
        actor=actor,
        action="DEMOTE_SUPER_ADMIN",
        target_type="participante",
        target_id=participante_id,
        metadata={
            "target_email": target.get("email"),
            "target_nome": target.get("nome_completo"),
        },
        reason=body.reason,
        request=request,
    )

    return {
        "id": target["id"],
        "nome_completo": target["nome_completo"],
        "email": target["email"],
        "cargo": target.get("cargo"),
        "setor": target.get("setor"),
        "role": target.get("role"),
    }
