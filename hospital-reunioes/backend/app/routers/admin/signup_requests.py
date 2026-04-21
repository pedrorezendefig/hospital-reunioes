"""Router /admin/signup-requests — gestao da fila de cadastros pendentes.

Escopo (Fase 2 super-admin CRUD):
- Listar solicitacoes (pendentes / confirmadas / expiradas).
- Rejeitar (DELETE) com motivo obrigatorio.
- Expirar manualmente (seta expires_at=now) para invalidar link ativo.

Nao expomos "aprovar manualmente" porque a senha e criptografada com
derivacao do token em claro; sem o token, nao ha como materializar a
conta auth. O fluxo de aprovacao tem que ser o clique no link enviado
por email (POST /auth/verify/{token}).

Reenvio de email fica fora desta primeira implementacao — reuso do
mailer exige duplicar parte do signup.py, e o link e o mesmo (basta
re-disparar). Fica para polish posterior.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from supabase import Client

from app.dependencies import get_supabase_client, require_super_admin
from app.models.admin_schemas import (
    ReasonRequest,
    SignupRequestItem,
    SignupRequestListResponse,
)
from app.services import audit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/signup-requests", tags=["admin", "signup-requests"])


def _is_expired(row: dict) -> bool:
    val = row.get("expires_at")
    if not val:
        return False
    try:
        dt = datetime.fromisoformat(str(val).replace("Z", "+00:00"))
        return datetime.now(timezone.utc) > dt
    except Exception:
        return False


def _classify(row: dict) -> str:
    if row.get("confirmado"):
        return "confirmado"
    if _is_expired(row):
        return "expirado"
    return "pendente"


@router.get("", response_model=SignupRequestListResponse)
async def list_signup_requests(
    status_filter: Literal["pendente", "confirmado", "expirado", "todos"] = Query(
        "pendente", alias="status"
    ),
    q: Optional[str] = Query(None, description="Busca por nome ou email"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    _actor: dict = Depends(require_super_admin),
    supabase: Client = Depends(get_supabase_client),
):
    """Lista solicitacoes paginada. Status e filtrado em Python porque
    "expirado" depende de expires_at vs now() — dar round-trip no DB com
    isso embutido exigiria uma view ou PostgREST operator complicado.
    """
    query = supabase.table("signup_requests").select("*")
    if q:
        like = f"%{q}%"
        query = query.or_(f"nome_completo.ilike.{like},email.ilike.{like}")
    result = query.order("created_at", desc=True).execute()
    all_rows = result.data or []

    filtered = [r for r in all_rows if status_filter == "todos" or _classify(r) == status_filter]
    total = len(filtered)
    start = (page - 1) * limit
    page_rows = filtered[start : start + limit]

    return {
        "data": page_rows,
        "total": total,
        "page": page,
        "limit": limit,
    }


@router.delete("/{request_id}", status_code=status.HTTP_200_OK)
async def reject_signup_request(
    request_id: str,
    body: ReasonRequest,
    request: Request,
    actor: dict = Depends(require_super_admin),
    supabase: Client = Depends(get_supabase_client),
) -> dict:
    """Rejeita uma solicitacao: deleta a linha. Motivo obrigatorio."""
    alvo = (
        supabase.table("signup_requests").select("*").eq("id", request_id).execute()
    )
    if not alvo.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Solicitacao nao encontrada",
        )

    (
        supabase.table("signup_requests")
        .delete()
        .eq("id", request_id)
        .execute()
    )

    audit.log_action(
        supabase,
        actor=actor,
        action="signup_request_reject",
        target_type="signup_request",
        target_id=request_id,
        metadata={
            "email": alvo.data[0].get("email"),
            "nome_completo": alvo.data[0].get("nome_completo"),
        },
        reason=body.reason,
        request=request,
    )
    return {"success": True, "id": request_id}


@router.post("/{request_id}/expire", status_code=status.HTTP_200_OK)
async def expire_signup_request(
    request_id: str,
    body: ReasonRequest,
    request: Request,
    actor: dict = Depends(require_super_admin),
    supabase: Client = Depends(get_supabase_client),
) -> dict:
    """Invalida o link ativo: forca expires_at=now."""
    alvo = (
        supabase.table("signup_requests").select("*").eq("id", request_id).execute()
    )
    if not alvo.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Solicitacao nao encontrada",
        )

    now_iso = datetime.now(timezone.utc).isoformat()
    (
        supabase.table("signup_requests")
        .update({"expires_at": now_iso})
        .eq("id", request_id)
        .execute()
    )

    audit.log_action(
        supabase,
        actor=actor,
        action="signup_request_expire",
        target_type="signup_request",
        target_id=request_id,
        metadata={"email": alvo.data[0].get("email")},
        reason=body.reason,
        request=request,
    )
    return {"success": True, "id": request_id, "expires_at": now_iso}
