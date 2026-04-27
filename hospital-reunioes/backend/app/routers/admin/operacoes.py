"""Router /admin/reunioes e /admin/pendencias — CRUD admin operacional.

Fase 3 do super-admin CRUD. Permite ao super-admin corrigir atribuicoes
erradas, destravar pipeline (mudar status_ata manualmente), e
arquivar/restaurar reunioes/pendencias via soft delete (migration 030).

Regras:
- Reunioes com status_ata=ASSINADA tem campos-nucleo bloqueados
  (json_ata, url_pdf_assinado, data_assinatura, envelope_key_clicksign,
  status_ata). Demais campos (titulo, setor, facilitador, etc) sao
  editaveis. Em outros status, tudo e editavel.
- Pendencias sao sempre totalmente editaveis.
- DELETE faz soft delete (seta deleted_at=now). Restore faz deleted_at=NULL.
- Toda mutacao grava em audit_log.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from supabase import Client

from app.dependencies import get_supabase_client, require_super_admin
from app.models.admin_schemas import ReasonRequest
from app.services import audit
from app.utils.query_params import sanitize_for_ilike

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin", "operacoes"])


# ─── Campos bloqueados em ata ASSINADA ────────────────────────────────────────

# Compliance: ata assinada e imutavel no nucleo (conteudo + evidencia de
# assinatura). Super-admin pode editar metadados perifericos (titulo,
# setor, facilitador, grupo de recorrencia).
_REUNIAO_ASSINADA_BLOCKED_FIELDS = {
    "json_ata",
    "url_pdf_assinado",
    "data_assinatura",
    "envelope_key_clicksign",
    "status_ata",
}


# ─── Schemas ─────────────────────────────────────────────────────────────────


class ReuniaoAdminUpdate(BaseModel):
    """PATCH /admin/reunioes/{id}. Todos os campos sao opcionais."""

    titulo: str | None = Field(None, max_length=255)
    setor: str | None = Field(None, max_length=255)
    tipo: str | None = Field(None, max_length=50)
    facilitador_id: str | None = Field(None, max_length=10)
    objetivo: str | None = Field(None, max_length=500)
    nome_grupo_recorrencia: str | None = Field(None, max_length=255)
    id_grupo_recorrencia: str | None = Field(None, max_length=20)
    status_ata: str | None = None
    reason: str | None = Field(None, max_length=1000)


class PendenciaAdminUpdate(BaseModel):
    """PATCH /admin/pendencias/{id}. Todos os campos sao opcionais."""

    descricao_acao: str | None = Field(None, max_length=500)
    status: str | None = None
    responsavel_id: str | None = Field(None, max_length=10)
    responsavel_nome: str | None = Field(None, max_length=255)
    co_responsavel_id: str | None = Field(None, max_length=10)
    co_responsavel_nome: str | None = Field(None, max_length=255)
    cargo: str | None = Field(None, max_length=255)
    prazo: str | None = None  # ISO date string
    meta_entregavel: str | None = Field(None, max_length=500)
    reason: str | None = Field(None, max_length=1000)


# ─── Reunioes ────────────────────────────────────────────────────────────────


@router.get("/reunioes")
async def list_reunioes_admin(
    q: str | None = Query(None, description="Busca por titulo, id ou objetivo"),
    status_ata: str | None = Query(None),
    setor: str | None = Query(None),
    facilitador_id: str | None = Query(None),
    data_de: str | None = Query(None),
    data_ate: str | None = Query(None),
    arquivadas: Literal["excluir", "incluir", "apenas"] = Query("excluir"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    _actor: dict = Depends(require_super_admin),
    supabase: Client = Depends(get_supabase_client),
):
    """Lista reunioes com filtros ricos. Soft delete controlado por flag."""
    query = supabase.table("reunioes").select("*", count="exact")
    if arquivadas == "excluir":
        query = query.is_("deleted_at", "null")
    elif arquivadas == "apenas":
        query = query.not_.is_("deleted_at", "null")
    if status_ata:
        query = query.eq("status_ata", status_ata)
    if setor:
        query = query.eq("setor", setor)
    if facilitador_id:
        query = query.eq("facilitador_id", facilitador_id)
    if data_de:
        query = query.gte("data", data_de)
    if data_ate:
        query = query.lte("data", data_ate)
    if q:
        like = f"%{sanitize_for_ilike(q)}%"
        query = query.or_(f"titulo.ilike.{like},id_reuniao.ilike.{like},objetivo.ilike.{like}")
    start = (page - 1) * limit
    end = start + limit - 1
    result = query.order("data", desc=True).range(start, end).execute()
    total = getattr(result, "count", None) or len(result.data or [])
    return {
        "data": result.data or [],
        "total": total,
        "page": page,
        "limit": limit,
    }


@router.patch("/reunioes/{id_reuniao}")
async def update_reuniao_admin(
    id_reuniao: str,
    body: ReuniaoAdminUpdate,
    request: Request,
    actor: dict = Depends(require_super_admin),
    supabase: Client = Depends(get_supabase_client),
):
    """Editar reuniao. Bloqueia campos-nucleo quando status_ata=ASSINADA."""
    atual = supabase.table("reunioes").select("*").eq("id_reuniao", id_reuniao).execute()
    if not atual.data:
        raise HTTPException(status_code=404, detail="Reuniao nao encontrada")
    reuniao = atual.data[0]

    data = body.model_dump(exclude_unset=True, exclude={"reason"})
    reason = body.reason

    # Compliance: se a ata ja estava ASSINADA, bloqueia campos-nucleo.
    if reuniao.get("status_ata") == "ASSINADA":
        bloqueados = _REUNIAO_ASSINADA_BLOCKED_FIELDS & set(data.keys())
        if bloqueados:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Campos bloqueados em ata ASSINADA: {sorted(bloqueados)}. Altere apenas metadados perifericos."
                ),
            )

    if not data:
        return reuniao

    changes = {k: {"antes": reuniao.get(k), "depois": v} for k, v in data.items() if reuniao.get(k) != v}
    if not changes:
        return reuniao

    update = supabase.table("reunioes").update(data).eq("id_reuniao", id_reuniao).execute()
    if not update.data:
        raise HTTPException(status_code=500, detail="Erro ao atualizar")
    atualizado = update.data[0]

    audit.log_action(
        supabase,
        actor=actor,
        action="update_reuniao",
        target_type="reuniao",
        target_id=id_reuniao,
        metadata={"changes": changes},
        reason=reason,
        request=request,
    )
    return atualizado


@router.delete("/reunioes/{id_reuniao}")
async def archive_reuniao_admin(
    id_reuniao: str,
    body: ReasonRequest,
    request: Request,
    actor: dict = Depends(require_super_admin),
    supabase: Client = Depends(get_supabase_client),
):
    """Soft delete: seta deleted_at=now."""
    now = datetime.now(UTC).isoformat()
    update = (
        supabase.table("reunioes")
        .update({"deleted_at": now})
        .eq("id_reuniao", id_reuniao)
        .is_("deleted_at", "null")
        .execute()
    )
    if not update.data:
        # Ja arquivada ou inexistente — verifica pra responder apropriadamente.
        existing = supabase.table("reunioes").select("id_reuniao, deleted_at").eq("id_reuniao", id_reuniao).execute()
        if not existing.data:
            raise HTTPException(status_code=404, detail="Reuniao nao encontrada")
        return existing.data[0]

    audit.log_action(
        supabase,
        actor=actor,
        action="delete_reuniao",
        target_type="reuniao",
        target_id=id_reuniao,
        metadata={"soft_delete": True},
        reason=body.reason,
        request=request,
    )
    return update.data[0]


@router.post("/reunioes/{id_reuniao}/restore")
async def restore_reuniao_admin(
    id_reuniao: str,
    body: ReasonRequest,
    request: Request,
    actor: dict = Depends(require_super_admin),
    supabase: Client = Depends(get_supabase_client),
):
    """Restaura reuniao arquivada: limpa deleted_at."""
    update = supabase.table("reunioes").update({"deleted_at": None}).eq("id_reuniao", id_reuniao).execute()
    if not update.data:
        raise HTTPException(status_code=404, detail="Reuniao nao encontrada")
    audit.log_action(
        supabase,
        actor=actor,
        action="restore_reuniao",
        target_type="reuniao",
        target_id=id_reuniao,
        metadata={},
        reason=body.reason,
        request=request,
    )
    return update.data[0]


# ─── Pendencias ──────────────────────────────────────────────────────────────


@router.get("/pendencias")
async def list_pendencias_admin(
    q: str | None = Query(None, description="Busca por descricao ou id"),
    status_p: str | None = Query(None, alias="status"),
    responsavel_id: str | None = Query(None),
    id_reuniao: str | None = Query(None),
    prazo_de: str | None = Query(None),
    prazo_ate: str | None = Query(None),
    arquivadas: Literal["excluir", "incluir", "apenas"] = Query("excluir"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    _actor: dict = Depends(require_super_admin),
    supabase: Client = Depends(get_supabase_client),
):
    """Lista pendencias com filtros ricos."""
    query = supabase.table("pendencias").select("*", count="exact")
    if arquivadas == "excluir":
        query = query.is_("deleted_at", "null")
    elif arquivadas == "apenas":
        query = query.not_.is_("deleted_at", "null")
    if status_p:
        query = query.eq("status", status_p)
    if responsavel_id:
        query = query.eq("responsavel_id", responsavel_id)
    if id_reuniao:
        query = query.eq("id_reuniao", id_reuniao)
    if prazo_de:
        query = query.gte("prazo", prazo_de)
    if prazo_ate:
        query = query.lte("prazo", prazo_ate)
    if q:
        like = f"%{sanitize_for_ilike(q)}%"
        query = query.or_(f"descricao_acao.ilike.{like},id_acao.ilike.{like}")
    start = (page - 1) * limit
    end = start + limit - 1
    result = query.order("prazo").range(start, end).execute()
    total = getattr(result, "count", None) or len(result.data or [])
    return {
        "data": result.data or [],
        "total": total,
        "page": page,
        "limit": limit,
    }


@router.patch("/pendencias/{id_acao}")
async def update_pendencia_admin(
    id_acao: str,
    body: PendenciaAdminUpdate,
    request: Request,
    actor: dict = Depends(require_super_admin),
    supabase: Client = Depends(get_supabase_client),
):
    """Editar pendencia. Sempre totalmente editavel — correcao de
    atribuicao e caso real que super-admin precisa tratar.
    """
    atual = supabase.table("pendencias").select("*").eq("id_acao", id_acao).execute()
    if not atual.data:
        raise HTTPException(status_code=404, detail="Pendencia nao encontrada")
    pend = atual.data[0]

    data = body.model_dump(exclude_unset=True, exclude={"reason"})
    reason = body.reason

    if not data:
        return pend

    changes = {k: {"antes": pend.get(k), "depois": v} for k, v in data.items() if pend.get(k) != v}
    if not changes:
        return pend

    update = supabase.table("pendencias").update(data).eq("id_acao", id_acao).execute()
    if not update.data:
        raise HTTPException(status_code=500, detail="Erro ao atualizar")

    audit.log_action(
        supabase,
        actor=actor,
        action="update_pendencia",
        target_type="pendencia",
        target_id=id_acao,
        metadata={"changes": changes},
        reason=reason,
        request=request,
    )
    return update.data[0]


@router.delete("/pendencias/{id_acao}")
async def archive_pendencia_admin(
    id_acao: str,
    body: ReasonRequest,
    request: Request,
    actor: dict = Depends(require_super_admin),
    supabase: Client = Depends(get_supabase_client),
):
    """Soft delete de pendencia."""
    now = datetime.now(UTC).isoformat()
    update = (
        supabase.table("pendencias")
        .update({"deleted_at": now})
        .eq("id_acao", id_acao)
        .is_("deleted_at", "null")
        .execute()
    )
    if not update.data:
        existing = supabase.table("pendencias").select("id_acao, deleted_at").eq("id_acao", id_acao).execute()
        if not existing.data:
            raise HTTPException(status_code=404, detail="Pendencia nao encontrada")
        return existing.data[0]

    audit.log_action(
        supabase,
        actor=actor,
        action="delete_pendencia",
        target_type="pendencia",
        target_id=id_acao,
        metadata={"soft_delete": True},
        reason=body.reason,
        request=request,
    )
    return update.data[0]


@router.post("/pendencias/{id_acao}/restore")
async def restore_pendencia_admin(
    id_acao: str,
    body: ReasonRequest,
    request: Request,
    actor: dict = Depends(require_super_admin),
    supabase: Client = Depends(get_supabase_client),
):
    """Restaura pendencia arquivada."""
    update = supabase.table("pendencias").update({"deleted_at": None}).eq("id_acao", id_acao).execute()
    if not update.data:
        raise HTTPException(status_code=404, detail="Pendencia nao encontrada")
    audit.log_action(
        supabase,
        actor=actor,
        action="restore_pendencia",
        target_type="pendencia",
        target_id=id_acao,
        metadata={},
        reason=body.reason,
        request=request,
    )
    return update.data[0]
