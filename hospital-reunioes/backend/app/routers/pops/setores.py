"""Router /pops/setores — CRUD de Setores do contexto POPs.

Setor: unidade do organograma do HSM, com nome e sigla únicos (a sigla é a
base do Código travado HSM_[SIGLA]-[NNN]). Gestão restrita ao Superadmin
(POPs) — gating explícito por endpoint, sem RLS (ADR 0002).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from supabase import Client

from app.dependencies import get_supabase_client, require_perfil_pop
from app.models.pops_schemas import PERFIS_POP, PopsSetorCreate, PopsSetorResponse, PopsSetorUpdate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pops/setores", tags=["pops", "setores"])


def _assert_nome_sigla_disponiveis(
    supabase: Client,
    nome: str | None,
    sigla: str | None,
    exclude_id: str | None = None,
) -> None:
    """409 se outro Setor já usa o nome ou a sigla (case-insensitive).

    Compara em Python: a tabela é pequena (organograma do HSM) e o índice
    UNIQUE lower() no banco continua sendo a garantia final.
    """
    result = supabase.table("pops_setores").select("id, nome, sigla").execute()
    for row in result.data or []:
        if row.get("id") == exclude_id:
            continue
        if nome and row.get("nome", "").strip().lower() == nome.strip().lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Já existe um Setor com este nome",
            )
        if sigla and row.get("sigla", "").strip().lower() == sigla.strip().lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Já existe um Setor com esta sigla",
            )


@router.post("", response_model=PopsSetorResponse, status_code=status.HTTP_201_CREATED)
async def criar_setor(
    body: PopsSetorCreate,
    _actor: dict = Depends(require_perfil_pop("superadmin")),
    supabase: Client = Depends(get_supabase_client),
):
    """Cria um Setor. Sigla é normalizada para maiúsculas (base do Código)."""
    nome = body.nome.strip()
    sigla = body.sigla.strip().upper()
    _assert_nome_sigla_disponiveis(supabase, nome, sigla)
    result = supabase.table("pops_setores").insert({"nome": nome, "sigla": sigla}).execute()
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao criar Setor",
        )
    return result.data[0]


@router.get("", response_model=list[PopsSetorResponse])
async def listar_setores(
    _actor: dict = Depends(require_perfil_pop(*PERFIS_POP)),
    supabase: Client = Depends(get_supabase_client),
):
    """Lista os Setores. Leitura aberta a todos os perfis do contexto POPs."""
    result = supabase.table("pops_setores").select("id, nome, sigla").order("nome").execute()
    return result.data or []


@router.patch("/{setor_id}", response_model=PopsSetorResponse)
async def editar_setor(
    setor_id: str,
    body: PopsSetorUpdate,
    _actor: dict = Depends(require_perfil_pop("superadmin")),
    supabase: Client = Depends(get_supabase_client),
):
    """Edita nome e/ou sigla de um Setor, mantendo a unicidade dos dois."""
    atual = supabase.table("pops_setores").select("id, nome, sigla").eq("id", setor_id).execute()
    if not atual.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Setor não encontrado")

    data: dict = {}
    if body.nome is not None:
        data["nome"] = body.nome.strip()
    if body.sigla is not None:
        data["sigla"] = body.sigla.strip().upper()
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nenhum campo para atualizar")

    _assert_nome_sigla_disponiveis(supabase, data.get("nome"), data.get("sigla"), exclude_id=setor_id)

    result = supabase.table("pops_setores").update(data).eq("id", setor_id).execute()
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao atualizar Setor",
        )
    return result.data[0]
