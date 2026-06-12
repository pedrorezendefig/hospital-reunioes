"""Router /pops/{pop_id} — Revisão e Validação da Versão (issue #85).

As etapas formais do fluxo (PRD #76): Revisor e Validador leem a Versão
completa e aprovam ou lançam Devolução com comentários. Aprovação do
Revisor → EM_VALIDACAO + email ao Validador; aprovação do Validador →
EM_ASSINATURA (o disparo ClickSign chega na fatia de publicação);
Devolução → EM_ELABORACAO + email ao Elaborador, com retorno direto a
quem devolveu no reenvio.

Guardas (papel × estado) vivem em app.services.pops_dominio — transições
como ações nomeadas e auditadas; nenhum endpoint manipula status solto.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from starlette.requests import Request

from app.dependencies import get_supabase_client, require_perfil_pop
from app.models.pops_schemas import PERFIS_POP, PopDevolucaoCreate, PopElaboracaoResponse
from app.routers.pops.versao_view import montar_versao_response, nomes_designados
from app.services import pops_dominio, pops_email_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pops/{pop_id}", tags=["pops"])


def _carregar_pop_setor_versao(pop_id: str, supabase) -> tuple[dict, dict, dict]:
    """POP + Setor + Versão corrente, com 404 para inexistentes. As guardas
    de papel variam por endpoint e ficam com quem chama."""
    pop_q = supabase.table("pops").select("*").eq("id", pop_id).limit(1).execute()
    if not pop_q.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="POP não encontrado")
    pop = pop_q.data[0]

    setor_q = supabase.table("pops_setores").select("id, nome, sigla").eq("id", pop["setor_id"]).limit(1).execute()
    setor = setor_q.data[0] if setor_q.data else {}

    # Leva 1: cada POP tem uma única Versão (a 1.0).
    versao_q = supabase.table("pops_versoes").select("*").eq("pop_id", pop_id).limit(1).execute()
    if not versao_q.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Versão do POP não encontrada")
    versao = versao_q.data[0]

    return pop, setor, versao


@router.get("/versao", response_model=PopElaboracaoResponse)
async def ler_versao(
    pop_id: str,
    actor: dict = Depends(require_perfil_pop(*PERFIS_POP)),
    supabase=Depends(get_supabase_client),
):
    """A Versão completa para leitura formal — mesma renderização das 11
    seções da elaboração, com as Devoluções (nome + timestamp). Leem os
    designados do POP e quem tem o Setor no escopo do perfil."""
    pop, setor, versao = _carregar_pop_setor_versao(pop_id, supabase)
    try:
        pops_dominio.exigir_leitura_do_pop(actor, pop, supabase)
    except pops_dominio.AcessoNegadoError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

    devolucoes = pops_dominio.listar_devolucoes(supabase, versao)
    return montar_versao_response(pop, setor, versao, nomes_designados(supabase, pop), devolucoes)


@router.post("/revisao/aprovar")
async def aprovar_revisao(
    pop_id: str,
    request: Request,
    actor: dict = Depends(require_perfil_pop(*PERFIS_POP)),
    supabase=Depends(get_supabase_client),
):
    """Aprovação do Revisor: EM_REVISAO → EM_VALIDACAO (auditado) + email ao
    Validador designado com link direto."""
    pop, setor, versao = _carregar_pop_setor_versao(pop_id, supabase)
    try:
        pops_dominio.exigir_revisor(actor, pop)
    except pops_dominio.AcessoNegadoError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    try:
        versao = pops_dominio.aprovar_revisao(supabase, versao, actor=actor, request=request)
    except pops_dominio.TransicaoInvalidaError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    pops_email_service.send_validacao_pendente_notification(
        supabase, pop, setor, remetente_nome=actor.get("nome_completo")
    )
    return {"estado": versao["estado"]}


@router.post("/revisao/devolver")
async def devolver_revisao(
    pop_id: str,
    body: PopDevolucaoCreate,
    request: Request,
    actor: dict = Depends(require_perfil_pop(*PERFIS_POP)),
    supabase=Depends(get_supabase_client),
):
    """Devolução do Revisor: EM_REVISAO → EM_ELABORACAO, comentários
    registrados com autor e timestamp (auditado) + email ao Elaborador."""
    pop, setor, versao = _carregar_pop_setor_versao(pop_id, supabase)
    try:
        pops_dominio.exigir_revisor(actor, pop)
    except pops_dominio.AcessoNegadoError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    try:
        versao = pops_dominio.devolver_revisao(
            supabase, versao, actor=actor, comentarios=body.comentarios, request=request
        )
    except pops_dominio.TransicaoInvalidaError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    pops_email_service.send_devolucao_notification(
        supabase,
        pop,
        setor,
        comentarios=body.comentarios,
        autor_nome=actor.get("nome_completo"),
        etapa_label="Revisão",
    )
    return {"estado": versao["estado"]}


@router.post("/validacao/aprovar")
async def aprovar_validacao(
    pop_id: str,
    request: Request,
    actor: dict = Depends(require_perfil_pop(*PERFIS_POP)),
    supabase=Depends(get_supabase_client),
):
    """Aprovação final do Validador: EM_VALIDACAO → EM_ASSINATURA (auditado).
    O disparo ClickSign chega na fatia de publicação — o estado já fica
    visível na lista."""
    pop, _setor, versao = _carregar_pop_setor_versao(pop_id, supabase)
    try:
        pops_dominio.exigir_validador(actor, pop)
    except pops_dominio.AcessoNegadoError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    try:
        versao = pops_dominio.aprovar_validacao(supabase, versao, actor=actor, request=request)
    except pops_dominio.TransicaoInvalidaError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return {"estado": versao["estado"]}


@router.post("/validacao/devolver")
async def devolver_validacao(
    pop_id: str,
    body: PopDevolucaoCreate,
    request: Request,
    actor: dict = Depends(require_perfil_pop(*PERFIS_POP)),
    supabase=Depends(get_supabase_client),
):
    """Devolução do Validador: EM_VALIDACAO → EM_ELABORACAO com etapa de
    retorno EM_VALIDACAO (o reenvio não repassa pelo Revisor) + email ao
    Elaborador com os comentários."""
    pop, setor, versao = _carregar_pop_setor_versao(pop_id, supabase)
    try:
        pops_dominio.exigir_validador(actor, pop)
    except pops_dominio.AcessoNegadoError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    try:
        versao = pops_dominio.devolver_validacao(
            supabase, versao, actor=actor, comentarios=body.comentarios, request=request
        )
    except pops_dominio.TransicaoInvalidaError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    pops_email_service.send_devolucao_notification(
        supabase,
        pop,
        setor,
        comentarios=body.comentarios,
        autor_nome=actor.get("nome_completo"),
        etapa_label="Validação",
    )
    return {"estado": versao["estado"]}
