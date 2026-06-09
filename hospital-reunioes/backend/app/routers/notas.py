"""Router da **Nota** (issues #32/#33): registro leve do Facilitador.

Uma Nota é um corpo de texto livre com histórico próprio e soft-delete. O
acesso espelha a Reunião — o autor vê só as suas; Secretária e Super admin
veem todas. A Nota também origina **Pendências** via add manual
(`POST /{id_nota}/pendencias`, ADR 0004); o roster de Participantes e a
extração por IA chegam em fatias seguintes.
"""

import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import (
    get_current_user,
    get_participante_for_user,
    get_supabase_client,
    is_secretaria,
    is_super_admin,
)
from app.models.schemas import (
    NotaCreate,
    NotaResponse,
    NotaUpdate,
    PendenciaResponse,
    PendenciasNotaCreateRequest,
)
from app.services.pendencia_service import criar_pendencias_de_nota

router = APIRouter(prefix="/notas", tags=["notas"])
logger = logging.getLogger(__name__)


def _ve_todas(me: dict) -> bool:
    """Secretária e Super admin têm visão global das Notas (espelha a Reunião)."""
    return is_super_admin(me) or is_secretaria(me)


def _pode_editar(me: dict, nota: dict) -> bool:
    """Edita/arquiva: o autor da Nota ou o Super admin (poder irrestrito)."""
    return is_super_admin(me) or nota["autor_id"] == me["id"]


def _carregar_nota_visivel(supabase, id_nota: str, me: dict) -> dict:
    """Carrega uma Nota viva visível ao usuário, ou 404.

    404 (não 403) para quem não pode vê-la — não revela a existência de uma
    Nota alheia (anti-enumeration, igual ao GET de Reunião).
    """
    result = supabase.table("notas").select("*").eq("id", id_nota).is_("deleted_at", "null").execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Nota não encontrada")
    nota = result.data[0]
    if not (_ve_todas(me) or nota["autor_id"] == me["id"]):
        raise HTTPException(status_code=404, detail="Nota não encontrada")
    return nota


@router.post("", response_model=NotaResponse, status_code=status.HTTP_201_CREATED)
async def criar_nota(
    req: NotaCreate,
    current_user: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    """Cria uma Nota com o corpo informado, de autoria do Facilitador logado."""
    me = await get_participante_for_user(current_user, supabase)
    if not me:
        raise HTTPException(status_code=403, detail="Participante não encontrado")

    nota = {"id": str(uuid.uuid4()), "corpo": req.corpo, "autor_id": me["id"]}
    result = supabase.table("notas").insert(nota).execute()
    logger.info(f"Nota {nota['id']} criada por {me['id']}")
    return result.data[0] if result.data else nota


@router.get("", response_model=list[NotaResponse])
async def listar_notas(
    current_user: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    """Histórico de Notas vivas, mais recentes primeiro.

    Regular vê só as suas; Secretária e Super admin veem todas.
    """
    me = await get_participante_for_user(current_user, supabase)
    if not me:
        return []

    query = supabase.table("notas").select("*").is_("deleted_at", "null")
    if not _ve_todas(me):
        query = query.eq("autor_id", me["id"])
    result = query.order("created_at", desc=True).execute()
    return result.data or []


@router.get("/{id_nota}", response_model=NotaResponse)
async def obter_nota(
    id_nota: str,
    current_user: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    """Abre uma Nota pelo id (se visível ao usuário)."""
    me = await get_participante_for_user(current_user, supabase)
    if not me:
        raise HTTPException(status_code=403, detail="Participante não encontrado")
    return _carregar_nota_visivel(supabase, id_nota, me)


@router.patch("/{id_nota}", response_model=NotaResponse)
async def editar_nota(
    id_nota: str,
    req: NotaUpdate,
    current_user: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    """Edita o corpo de uma Nota — autor ou Super admin."""
    me = await get_participante_for_user(current_user, supabase)
    if not me:
        raise HTTPException(status_code=403, detail="Participante não encontrado")

    nota = _carregar_nota_visivel(supabase, id_nota, me)
    if not _pode_editar(me, nota):
        raise HTTPException(status_code=403, detail="Sem permissão para editar esta Nota")

    # `.is_(deleted_at, null)` no UPDATE fecha a janela entre o SELECT e a escrita:
    # se a Nota for arquivada por um request concorrente, o PATCH não a edita.
    upd = supabase.table("notas").update({"corpo": req.corpo}).eq("id", id_nota).is_("deleted_at", "null").execute()
    logger.info(f"Nota {id_nota} editada por {me['id']}")
    return upd.data[0] if upd.data else {**nota, "corpo": req.corpo}


@router.post(
    "/{id_nota}/pendencias",
    response_model=list[PendenciaResponse],
    status_code=status.HTTP_201_CREATED,
)
async def adicionar_pendencias_a_nota(
    id_nota: str,
    req: PendenciasNotaCreateRequest,
    current_user: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    """Adiciona Pendências manuais a uma Nota (issue #33).

    Elas nascem com `id_nota` setado e `id_reuniao` nulo e caem no mesmo
    acompanhamento das demais — painel, alerta de atraso, Repactuação e
    comentários. Autor da Nota ou Super admin.
    """
    me = await get_participante_for_user(current_user, supabase)
    if not me:
        raise HTTPException(status_code=403, detail="Participante não encontrado")

    nota = _carregar_nota_visivel(supabase, id_nota, me)
    if not _pode_editar(me, nota):
        raise HTTPException(status_code=403, detail="Sem permissão para adicionar Pendências a esta Nota")

    confirmadas = [p.model_dump(mode="json") for p in req.pendencias]
    criadas = criar_pendencias_de_nota(supabase, id_nota, confirmadas)
    logger.info(f"{len(criadas)} pendências adicionadas à Nota {id_nota} por {me['id']}")
    return criadas


@router.delete("/{id_nota}")
async def arquivar_nota(
    id_nota: str,
    current_user: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    """Arquiva uma Nota — soft-delete via `deleted_at`, sem hard-delete.

    A Nota some do histórico ativo mas a linha permanece no banco (compliance e
    independência das Pendências que ela vier a gerar em fatias seguintes).
    Autor ou Super admin.
    """
    me = await get_participante_for_user(current_user, supabase)
    if not me:
        raise HTTPException(status_code=403, detail="Participante não encontrado")

    nota = _carregar_nota_visivel(supabase, id_nota, me)
    if not _pode_editar(me, nota):
        raise HTTPException(status_code=403, detail="Sem permissão para arquivar esta Nota")

    supabase.table("notas").update({"deleted_at": datetime.now(UTC).isoformat()}).eq("id", id_nota).is_(
        "deleted_at", "null"
    ).execute()
    logger.info(f"Nota {id_nota} arquivada por {me['id']}")
    return {"message": "Nota arquivada com sucesso.", "id": id_nota}
