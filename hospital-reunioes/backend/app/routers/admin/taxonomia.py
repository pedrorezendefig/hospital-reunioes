"""Router /admin/setores, /admin/cargos, /admin/tipos-reuniao — CRUD de taxonomia.

Todas as rotas exigem super admin. Efeitos destrutivos/criativos gravam em
`audit_log` via `app.services.audit.log_action`.

Os tres sub-recursos tem o mesmo contrato (id, nome, ativo, timestamps) e a
mesma logica, entao os endpoints sao construidos por uma factory
`_register_taxonomy_routes(table, audit_prefix)` que monta 4 rotas por recurso:

- GET    /admin/{recurso}                lista paginada com filtros
- POST   /admin/{recurso}                cria item
- PATCH  /admin/{recurso}/{id}           atualiza nome/ativo
- DELETE /admin/{recurso}/{id}           soft delete (ativo=false)

Hard delete nao e exposto — arquivo-se via PATCH ativo=false. Isso preserva
vinculos historicos (participantes com setor_id apontando para o setor
arquivado continuam renderizando o nome).
"""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from supabase import Client

from app.dependencies import get_supabase_client, require_super_admin
from app.models.admin_schemas import (
    TaxonomyCreatePayload,
    TaxonomyItem,
    TaxonomyListResponse,
    TaxonomyUpdatePayload,
)
from app.services import audit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin", "taxonomia"])


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _normalize_nome(nome: str) -> str:
    """Normaliza entrada: trim + colapsa espacos duplos."""
    return " ".join(nome.strip().split())


def _fetch_by_id(supabase: Client, table: str, item_id: str) -> dict:
    """Busca item por id — 404 se nao existir."""
    result = supabase.table(table).select("*").eq("id", item_id).execute()
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{table} nao encontrado",
        )
    return result.data[0]


def _assert_nome_disponivel(
    supabase: Client,
    table: str,
    nome: str,
    exclude_id: str | None = None,
) -> None:
    """409 se outro item ja usa este nome (case-insensitive)."""
    result = supabase.table(table).select("id, nome").ilike("nome", nome).execute()
    conflito = [
        row
        for row in (result.data or [])
        if row.get("id") != exclude_id and row.get("nome", "").strip().lower() == nome.strip().lower()
    ]
    if conflito:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Nome ja existe (case-insensitive)",
        )


# ─── Factory de rotas ────────────────────────────────────────────────────────


def _register_taxonomy_routes(
    *,
    path: str,
    table: str,
    audit_prefix: str,
    target_type: str,
) -> None:
    """Registra as 4 rotas REST (list, create, update, archive) para um recurso
    de taxonomia.

    Args:
        path: prefixo HTTP (ex: "/setores").
        table: nome da tabela Postgres (ex: "setores").
        audit_prefix: prefixo da acao no audit_log (ex: "setor").
        target_type: target_type usado no audit_log (ex: "setor").
    """

    @router.get(
        path,
        response_model=TaxonomyListResponse,
        name=f"list_{table}",
    )
    async def _list(
        q: str | None = Query(None, description="Busca por nome"),
        ativo: Literal["todos", "ativos", "arquivados"] = Query("ativos"),
        page: int = Query(1, ge=1),
        limit: int = Query(50, ge=1, le=200),
        _actor: dict = Depends(require_super_admin),
        supabase: Client = Depends(get_supabase_client),
    ):
        query = supabase.table(table).select("*", count="exact")
        if q:
            query = query.ilike("nome", f"%{q}%")
        if ativo == "ativos":
            query = query.eq("ativo", True)
        elif ativo == "arquivados":
            query = query.eq("ativo", False)
        start = (page - 1) * limit
        end = start + limit - 1
        result = query.order("nome").range(start, end).execute()
        total = getattr(result, "count", None)
        if total is None:
            total = len(result.data or [])
        return {
            "data": result.data or [],
            "total": total,
            "page": page,
            "limit": limit,
        }

    @router.post(
        path,
        response_model=TaxonomyItem,
        status_code=status.HTTP_201_CREATED,
        name=f"create_{table}",
    )
    async def _create(
        payload: TaxonomyCreatePayload,
        request: Request,
        actor: dict = Depends(require_super_admin),
        supabase: Client = Depends(get_supabase_client),
    ):
        nome = _normalize_nome(payload.nome)
        if not nome:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Nome nao pode ser vazio",
            )
        _assert_nome_disponivel(supabase, table, nome)
        result = supabase.table(table).insert({"nome": nome}).execute()
        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Falha ao criar item",
            )
        item = result.data[0]
        audit.log_action(
            supabase,
            actor=actor,
            action=f"{audit_prefix}_create",
            target_type=target_type,
            target_id=str(item["id"]),
            metadata={"nome": nome},
            request=request,
        )
        return item

    @router.patch(
        f"{path}/{{item_id}}",
        response_model=TaxonomyItem,
        name=f"update_{table}",
    )
    async def _update(
        item_id: str,
        payload: TaxonomyUpdatePayload,
        request: Request,
        actor: dict = Depends(require_super_admin),
        supabase: Client = Depends(get_supabase_client),
    ):
        existing = _fetch_by_id(supabase, table, item_id)

        updates: dict = {}
        if payload.nome is not None:
            nome = _normalize_nome(payload.nome)
            if not nome:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Nome nao pode ser vazio",
                )
            if nome.strip().lower() != existing["nome"].strip().lower():
                _assert_nome_disponivel(supabase, table, nome, exclude_id=item_id)
            updates["nome"] = nome
        if payload.ativo is not None:
            updates["ativo"] = payload.ativo

        if not updates:
            return existing

        result = supabase.table(table).update(updates).eq("id", item_id).execute()
        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"{table} nao encontrado",
            )
        updated = result.data[0]
        audit.log_action(
            supabase,
            actor=actor,
            action=f"{audit_prefix}_update",
            target_type=target_type,
            target_id=str(item_id),
            metadata={
                "antes": {k: existing.get(k) for k in updates},
                "depois": updates,
            },
            request=request,
        )
        return updated

    @router.delete(
        f"{path}/{{item_id}}",
        response_model=TaxonomyItem,
        name=f"archive_{table}",
    )
    async def _archive(
        item_id: str,
        request: Request,
        actor: dict = Depends(require_super_admin),
        supabase: Client = Depends(get_supabase_client),
    ):
        existing = _fetch_by_id(supabase, table, item_id)
        if existing.get("ativo") is False:
            return existing  # ja arquivado — idempotente
        result = supabase.table(table).update({"ativo": False}).eq("id", item_id).execute()
        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"{table} nao encontrado",
            )
        archived = result.data[0]
        audit.log_action(
            supabase,
            actor=actor,
            action=f"{audit_prefix}_archive",
            target_type=target_type,
            target_id=str(item_id),
            metadata={"nome": existing["nome"]},
            request=request,
        )
        return archived


# ─── Registro dos 3 sub-recursos ─────────────────────────────────────────────

_register_taxonomy_routes(
    path="/setores",
    table="setores",
    audit_prefix="setor",
    target_type="setor",
)
_register_taxonomy_routes(
    path="/cargos",
    table="cargos",
    audit_prefix="cargo",
    target_type="cargo",
)
_register_taxonomy_routes(
    path="/tipos-reuniao",
    table="tipos_reuniao",
    audit_prefix="tipo_reuniao",
    target_type="tipo_reuniao",
)
