"""As Definições de processo do setor (ADR 0098, decisão 9; issue #1875).

Quem vê sai do vínculo, até o organograma: o Facilitador vê a lista dos
setores em que conduz Reuniões; o Super admin vê todas, fora as Reuniões do
Núcleo que ele não alcança; a Secretária recebe 403. Tirar da lista pede
anotação e cabe ao Facilitador da Reunião de origem e ao Super admin. Sem
lembrete: a lista é só consulta.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.dependencies import (
    get_current_user,
    get_participante_for_user,
    get_supabase_client,
    is_secretaria,
    is_super_admin,
    require_acesso_reunioes,
    reunioes_ocultas,
)
from app.services import definicao_processo_service as servico

router = APIRouter(
    prefix="/definicoes-processo",
    tags=["definicoes-processo"],
    # Gate de contexto (ADR 0007): sem papel nas Reuniões -> 403 em todo o router.
    dependencies=[Depends(require_acesso_reunioes)],
)
logger = logging.getLogger(__name__)


class AnotacaoRequest(BaseModel):
    # O mesmo teto da anotação da Pendência.
    anotacao: str | None = Field(default=None, max_length=5000)


class DefinicaoProcessoResponse(BaseModel):
    id: str
    id_reuniao: str
    reuniao_titulo: str | None = None
    reuniao_data: date | None = None
    setor_id: str | None = None
    setor_nome: str | None = None
    trecho: str
    objetivo: str | None = None
    created_at: datetime | None = None
    pode_retirar: bool


async def _quem_pede(current_user: dict, supabase) -> dict | None:
    me = await get_participante_for_user(current_user, supabase)
    if is_secretaria(me):
        raise HTTPException(status_code=403, detail="Secretária não tem acesso às Definições de processo")
    return me


@router.get("", response_model=list[DefinicaoProcessoResponse])
async def listar_definicoes(
    current_user: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    """A lista de definições de processo dos setores de quem pede."""
    me = await _quem_pede(current_user, supabase)
    if not me:
        return []
    return servico.listar(
        supabase,
        me_id=me.get("id"),
        super_admin=is_super_admin(me),
        ocultas=set(reunioes_ocultas(supabase, me)),
    )


@router.post("/{id_definicao}/retirar")
async def retirar_definicao(
    id_definicao: UUID,
    body: AnotacaoRequest,
    current_user: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    """Tira o item da lista (repetido ou que deixou de valer), com anotação."""
    me = await _quem_pede(current_user, supabase)
    if not me:
        raise HTTPException(status_code=404, detail="Definição de processo não encontrada")
    try:
        retirada = servico.retirar(
            supabase,
            str(id_definicao),
            body.anotacao,
            me_id=me.get("id"),
            autor_nome=me.get("nome_completo") or current_user.get("email") or "Sem nome",
            super_admin=is_super_admin(me),
            ocultas=set(reunioes_ocultas(supabase, me)),
        )
    except servico.ItemInexistente as recusa:
        raise HTTPException(status_code=404, detail=str(recusa)) from recusa
    except servico.SemPermissao as recusa:
        raise HTTPException(status_code=403, detail=str(recusa)) from recusa
    except servico.RetiradaRecusada as recusa:
        raise HTTPException(status_code=422, detail=str(recusa)) from recusa
    except servico.JaRetirada as recusa:
        raise HTTPException(status_code=409, detail=str(recusa)) from recusa
    logger.info("[Processo] %s retirada da lista por %s", id_definicao, me.get("id"))
    return {"id": retirada.get("id", str(id_definicao)), "status": retirada.get("status")}
