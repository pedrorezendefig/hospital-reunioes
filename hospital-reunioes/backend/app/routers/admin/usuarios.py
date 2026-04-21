"""Router /admin/usuarios — CRUD administrativo cross-user de participantes.

Todos os endpoints exigem `require_super_admin`. Efeitos destrutivos (create,
edit, delete, reset-password) sao gravados em `audit_log` via
`app.services.audit.log_action`.

Endpoints:
- GET    /admin/usuarios                    lista com filtros e paginacao.
- GET    /admin/usuarios/{id}               detalhe + ultimos 20 audit logs.
- POST   /admin/usuarios                    cria novo participante (ID P001...).
- PATCH  /admin/usuarios/{id}               atualizacao parcial.
- DELETE /admin/usuarios/{id}               hard delete (motivo obrigatorio).
- POST   /admin/usuarios/{id}/reset-password reseta senha no Supabase Auth.
"""
from __future__ import annotations

import logging
import re
import secrets
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from starlette.requests import Request
from supabase import Client

from app.dependencies import get_supabase_client, require_super_admin
from app.utils.postgrest_filters import validate_pid_for_filter
from app.models.admin_schemas import (
    AdminResetPasswordRequest,
    AdminResetPasswordResponse,
    AdminUsuarioCreate,
    AdminUsuarioDeleteRequest,
    AdminUsuarioDetalhe,
    AdminUsuarioResponse,
    AdminUsuarioUpdate,
    AuditLogRow,
)
from app.services import audit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/usuarios", tags=["admin", "usuarios"])


# ─── Helpers ─────────────────────────────────────────────────────────────────

# Campos que exibimos/retornamos sempre que possivel.
_SELECT_FIELDS = (
    "id, nome_completo, email, cargo, area, setor, role, ativo, "
    "is_externo, is_super_admin, auth_user_id, data_cadastro"
)


def _next_participant_id(supabase: Client) -> str:
    """Gera o proximo ID sequencial (P001, P002, ...)."""
    result = (
        supabase.table("participantes")
        .select("id")
        .order("id", desc=True)
        .limit(1)
        .execute()
    )
    if result.data:
        last_id = result.data[0]["id"]
        num = int(re.sub(r"[^0-9]", "", last_id) or "0")
        return f"P{num + 1:03d}"
    return "P001"


def _fetch_usuario(supabase: Client, participante_id: str) -> dict:
    """Busca participante por id — 404 se nao existir."""
    result = (
        supabase.table("participantes")
        .select(_SELECT_FIELDS)
        .eq("id", participante_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Participante nao encontrado",
        )
    return result.data[0]


def _assert_email_disponivel(
    supabase: Client, email: str, exclude_id: Optional[str] = None
) -> None:
    """409 se outro participante ja usa este email."""
    query = supabase.table("participantes").select("id").eq("email", email)
    result = query.execute()
    conflito = [
        row for row in (result.data or []) if row.get("id") != exclude_id
    ]
    if conflito:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email ja cadastrado em outro participante",
        )


def _generate_password() -> str:
    """Gera uma senha aleatoria forte (>=12 chars url-safe)."""
    return secrets.token_urlsafe(16)


# ─── Endpoints ───────────────────────────────────────────────────────────────


@router.get("", response_model=list[AdminUsuarioResponse])
async def list_usuarios(
    q: Optional[str] = Query(None, description="Busca por nome ou email"),
    setor: Optional[str] = Query(None),
    ativo: Optional[bool] = Query(None),
    is_super_admin_filter: Optional[bool] = Query(
        None, alias="is_super_admin", description="Filtra por flag super admin"
    ),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    _actor: dict = Depends(require_super_admin),
    supabase: Client = Depends(get_supabase_client),
):
    """Lista participantes (incluindo inativos) com filtros e paginacao."""
    query = supabase.table("participantes").select(_SELECT_FIELDS)

    if setor:
        # Aceita multiplos valores separados por virgula (multi-select no frontend).
        setores = [s.strip() for s in setor.split(",") if s.strip()]
        if len(setores) == 1:
            query = query.eq("setor", setores[0])
        elif len(setores) > 1:
            query = query.in_("setor", setores)
    if ativo is not None:
        query = query.eq("ativo", ativo)
    if is_super_admin_filter is not None:
        query = query.eq("is_super_admin", is_super_admin_filter)
    if q:
        # Busca case-insensitive em nome_completo OU email.
        like = f"%{q}%"
        query = query.or_(f"nome_completo.ilike.{like},email.ilike.{like}")

    result = (
        query.order("nome_completo").range(offset, offset + limit - 1).execute()
    )
    return result.data or []


@router.get("/{participante_id}", response_model=AdminUsuarioDetalhe)
async def get_usuario(
    participante_id: str,
    _actor: dict = Depends(require_super_admin),
    supabase: Client = Depends(get_supabase_client),
):
    """Detalhe + ultimos 20 audit logs em que o participante e actor ou target."""
    usuario = _fetch_usuario(supabase, participante_id)

    logs: list[dict] = []
    try:
        # Busca audit_log onde participante e actor OU target.
        # Defense-in-depth: valida ID antes da interpolacao em filtro PostgREST.
        safe_pid = validate_pid_for_filter(participante_id)
        res = (
            supabase.table("audit_log")
            .select("*")
            .or_(
                f"actor_id.eq.{safe_pid},"
                f"and(target_type.eq.participante,target_id.eq.{safe_pid})"
            )
            .order("timestamp", desc=True)
            .limit(20)
            .execute()
        )
        logs = res.data or []
    except Exception as e:  # noqa: BLE001 — fallback sem filtro composto
        logger.warning(
            f"[admin.usuarios] Falha ao consultar audit_log (filtro composto): {e}"
        )
        try:
            res_actor = (
                supabase.table("audit_log")
                .select("*")
                .eq("actor_id", participante_id)
                .order("timestamp", desc=True)
                .limit(20)
                .execute()
            )
            res_target = (
                supabase.table("audit_log")
                .select("*")
                .eq("target_type", "participante")
                .eq("target_id", participante_id)
                .order("timestamp", desc=True)
                .limit(20)
                .execute()
            )
            combined = (res_actor.data or []) + (res_target.data or [])
            # Dedup por id, manter ordem por timestamp desc.
            seen: set[str] = set()
            logs = []
            for row in sorted(
                combined,
                key=lambda r: r.get("timestamp") or "",
                reverse=True,
            ):
                rid = str(row.get("id"))
                if rid in seen:
                    continue
                seen.add(rid)
                logs.append(row)
                if len(logs) >= 20:
                    break
        except Exception as e2:  # noqa: BLE001
            logger.warning(f"[admin.usuarios] Fallback de audit_log falhou: {e2}")
            logs = []

    return AdminUsuarioDetalhe(
        usuario=AdminUsuarioResponse(**usuario),
        audit_logs=[AuditLogRow(**row) for row in logs],
    )


@router.post(
    "",
    response_model=AdminUsuarioResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_usuario(
    body: AdminUsuarioCreate,
    request: Request,
    actor: dict = Depends(require_super_admin),
    supabase: Client = Depends(get_supabase_client),
):
    """Cria um novo participante. Loga CREATE_USUARIO em audit_log."""
    _assert_email_disponivel(supabase, body.email)

    new_id = _next_participant_id(supabase)
    role_value = body.role.value if hasattr(body.role, "value") else str(body.role)
    payload = {
        "id": new_id,
        "nome_completo": body.nome_completo,
        "email": body.email,
        "cargo": body.cargo,
        "area": body.area,
        "setor": body.setor,
        "role": role_value,
        "is_externo": body.is_externo,
        "ativo": body.ativo,
    }

    # Saga manual: INSERT participante + auth user com rollback se Admin API
    # falhar (evita registro órfão sem auth_user_id). Mantemos a postura
    # "best effort" do auth: se falhar, o helper já fez o rollback do INSERT,
    # então propagamos como 500 (admin sabe que precisa reprovisionar).
    from app.services.auth_provisioning import provision_with_compensation

    try:
        novo, _auth_uid = provision_with_compensation(
            supabase,
            payload,
            role=role_value,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(
            f"[admin.usuarios] Falha ao criar/provisionar usuário {body.email}: {e}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao criar participante",
        )

    audit.log_action(
        supabase,
        actor=actor,
        action="CREATE_USUARIO",
        target_type="participante",
        target_id=new_id,
        metadata={
            "email": body.email,
            "nome_completo": body.nome_completo,
            "cargo": body.cargo,
            "role": role_value,
            "is_externo": body.is_externo,
        },
        request=request,
    )

    # Completa campos faltantes no response.
    for campo in (
        "cargo",
        "area",
        "setor",
        "role",
        "ativo",
        "is_externo",
        "is_super_admin",
        "data_cadastro",
    ):
        novo.setdefault(campo, payload.get(campo))
    novo.setdefault("is_super_admin", False)
    return novo


@router.patch("/{participante_id}", response_model=AdminUsuarioResponse)
async def update_usuario(
    participante_id: str,
    body: AdminUsuarioUpdate,
    request: Request,
    actor: dict = Depends(require_super_admin),
    supabase: Client = Depends(get_supabase_client),
):
    """Atualizacao parcial. Loga EDIT_USUARIO com antes/depois por campo."""
    atual = _fetch_usuario(supabase, participante_id)

    data = body.model_dump(exclude_unset=True)
    reason = data.pop("reason", None)

    if not data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nenhum campo para atualizar",
        )

    # Normaliza enum role -> string.
    if "role" in data and hasattr(data["role"], "value"):
        data["role"] = data["role"].value

    # Valida unicidade de email.
    if "email" in data and data["email"] != atual.get("email"):
        _assert_email_disponivel(
            supabase, data["email"], exclude_id=participante_id
        )

    # Monta changes (antes/depois) apenas para campos realmente alterados.
    changes: dict[str, dict] = {}
    for campo, novo_valor in data.items():
        valor_antes = atual.get(campo)
        if valor_antes != novo_valor:
            changes[campo] = {"antes": valor_antes, "depois": novo_valor}

    if not changes:
        # Nada mudou de fato — nao loga, retorna estado atual.
        return atual

    update = (
        supabase.table("participantes")
        .update(data)
        .eq("id", participante_id)
        .execute()
    )
    if not update.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao atualizar participante",
        )
    atualizado = update.data[0]

    audit.log_action(
        supabase,
        actor=actor,
        action="EDIT_USUARIO",
        target_type="participante",
        target_id=participante_id,
        metadata={"changes": changes},
        reason=reason,
        request=request,
    )

    return atualizado


@router.delete("/{participante_id}", status_code=status.HTTP_200_OK)
async def delete_usuario(
    participante_id: str,
    body: AdminUsuarioDeleteRequest,
    request: Request,
    actor: dict = Depends(require_super_admin),
    supabase: Client = Depends(get_supabase_client),
) -> dict:
    """Hard delete. Motivo obrigatorio. Bloqueia auto-delete."""
    if actor.get("id") == participante_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Voce nao pode deletar a si mesmo",
        )

    alvo = _fetch_usuario(supabase, participante_id)

    delete = (
        supabase.table("participantes")
        .delete()
        .eq("id", participante_id)
        .execute()
    )
    if not delete.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao deletar participante",
        )

    audit.log_action(
        supabase,
        actor=actor,
        action="DELETE_USUARIO",
        target_type="participante",
        target_id=participante_id,
        metadata={
            "email": alvo.get("email"),
            "nome_completo": alvo.get("nome_completo"),
            "cargo": alvo.get("cargo"),
            "role": alvo.get("role"),
            "is_super_admin": alvo.get("is_super_admin"),
        },
        reason=body.reason,
        request=request,
    )

    return {"success": True, "id": participante_id}


@router.post(
    "/{participante_id}/reset-password",
    response_model=AdminResetPasswordResponse,
)
async def reset_password(
    participante_id: str,
    body: AdminResetPasswordRequest,
    request: Request,
    actor: dict = Depends(require_super_admin),
    supabase: Client = Depends(get_supabase_client),
):
    """Reseta senha no Supabase Auth. Motivo obrigatorio.

    Se `new_password` nao for informado, gera uma senha aleatoria.
    Retorna a senha em claro (o frontend deve exibi-la uma unica vez).
    """
    alvo = _fetch_usuario(supabase, participante_id)
    email = alvo.get("email")
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Participante sem email cadastrado",
        )

    auth_uid = alvo.get("auth_user_id")

    # Se nao ha auth_user_id vinculado, tenta provisionar antes.
    if not auth_uid:
        try:
            from app.services.auth_provisioning import provision_auth_user

            role = alvo.get("role") or "coordenador"
            auth_uid = provision_auth_user(
                supabase, alvo.get("nome_completo") or "", email, str(role)
            )
            if auth_uid:
                supabase.table("participantes").update(
                    {"auth_user_id": auth_uid}
                ).eq("id", participante_id).execute()
        except Exception as e:  # noqa: BLE001
            logger.error(
                f"[admin.usuarios] Falha ao provisionar auth para {email}: {e}"
            )

    if not auth_uid:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Participante sem conta em auth.users — provisione antes de resetar senha",
        )

    nova_senha = body.new_password or _generate_password()

    try:
        supabase.auth.admin.update_user_by_id(
            auth_uid, {"password": nova_senha}
        )
    except Exception as e:  # noqa: BLE001
        logger.error(f"[admin.usuarios] Erro ao resetar senha de {email}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao resetar senha no provedor de autenticacao",
        )

    audit.log_action(
        supabase,
        actor=actor,
        action="RESET_PASSWORD",
        target_type="participante",
        target_id=participante_id,
        metadata={
            "email": email,
            "gerada_aleatoria": body.new_password is None,
        },
        reason=body.reason,
        request=request,
    )

    return AdminResetPasswordResponse(
        participante_id=participante_id,
        email=email,
        new_password=nova_senha,
    )
