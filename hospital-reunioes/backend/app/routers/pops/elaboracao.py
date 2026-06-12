"""Router /pops/{pop_id}/elaboracao — o POP vivo com chat do agente (issue #83).

A Elaboração (PRD #76): o Elaborador designado conversa com o agente e as
seções do template institucional tomam forma ao vivo. Chat stateless no
padrão da Ata Guiada (ADR 0006), com a diferença deliberada de que o
rascunho PERSISTE na Versão a cada interação — elaboração dura dias e
reabrir a tela recupera o estado; o histórico do chat é efêmero.

Guardas (papel × estado) vivem em app.services.pops_dominio — transições
como ações nomeadas e auditadas; nenhum endpoint manipula status solto.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from starlette.requests import Request

from app.dependencies import get_supabase_client, require_perfil_pop
from app.limiter import limiter
from app.models.pops_schemas import (
    PERFIS_POP,
    PeriodicidadeEscolhaRequest,
    PopElaboracaoChatRequest,
    PopElaboracaoPopInfo,
    PopElaboracaoResponse,
    PopVersaoResponse,
)
from app.services import audit, pops_dominio, pops_email_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pops/{pop_id}/elaboracao", tags=["pops"])


def _carregar_contexto(pop_id: str, actor: dict, supabase) -> tuple[dict, dict, dict]:
    """POP + Setor + Versão corrente, com as guardas comuns da elaboração:
    404 para POP/Versão inexistente, 403 para quem não é o Elaborador
    designado (a designação formal vence o escopo de Setor)."""
    pop_q = supabase.table("pops").select("*").eq("id", pop_id).limit(1).execute()
    if not pop_q.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="POP não encontrado")
    pop = pop_q.data[0]

    try:
        pops_dominio.exigir_elaborador(actor, pop)
    except pops_dominio.AcessoNegadoError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

    setor_q = supabase.table("pops_setores").select("id, nome, sigla").eq("id", pop["setor_id"]).limit(1).execute()
    setor = setor_q.data[0] if setor_q.data else {}

    # Leva 1: cada POP tem uma única Versão (a 1.0).
    versao_q = supabase.table("pops_versoes").select("*").eq("pop_id", pop_id).limit(1).execute()
    if not versao_q.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Versão do POP não encontrada")
    versao = versao_q.data[0]

    return pop, setor, versao


def _nomes_designados(supabase, pop: dict) -> dict[str, str | None]:
    ids = list({pop["elaborador_id"], pop["revisor_id"], pop["validador_id"]})
    result = supabase.table("participantes").select("id, nome_completo").in_("id", ids).execute()
    return {row["id"]: row.get("nome_completo") for row in (result.data or [])}


def _resposta_elaboracao(pop: dict, setor: dict, versao: dict, nomes: dict) -> PopElaboracaoResponse:
    return PopElaboracaoResponse(
        pop=PopElaboracaoPopInfo(
            id=pop["id"],
            codigo=pop["codigo"],
            nome=pop["nome"],
            setor_nome=setor.get("nome"),
            setor_sigla=setor.get("sigla"),
            criticidade=pop["criticidade"],
            base_normativa=pop.get("base_normativa"),
            periodicidade_revisao=pop["periodicidade_revisao"],
            prazo_elaboracao_dias=pop["prazo_elaboracao_dias"],
            prazo_revisao_dias=pop["prazo_revisao_dias"],
            elaborador_id=pop["elaborador_id"],
            revisor_id=pop["revisor_id"],
            validador_id=pop["validador_id"],
            elaborador_nome=nomes.get(pop["elaborador_id"]),
            revisor_nome=nomes.get(pop["revisor_id"]),
            validador_nome=nomes.get(pop["validador_id"]),
            created_at=pop.get("created_at"),
        ),
        versao=PopVersaoResponse(id=versao["id"], numero_versao=versao["numero_versao"], estado=versao["estado"]),
        rascunho=versao.get("rascunho"),
        periodicidade_sugerida=versao.get("periodicidade_sugerida"),
    )


@router.get("", response_model=PopElaboracaoResponse)
async def carregar_elaboracao(
    pop_id: str,
    actor: dict = Depends(require_perfil_pop(*PERFIS_POP)),
    supabase=Depends(get_supabase_client),
):
    """Estado completo da tela de elaboração — reabrir recupera o rascunho
    persistido na Versão, em qualquer estado (a edição é que tem gate)."""
    pop, setor, versao = _carregar_contexto(pop_id, actor, supabase)
    return _resposta_elaboracao(pop, setor, versao, _nomes_designados(supabase, pop))


@router.post("/chat")
@limiter.limit("10/minute")
async def chat_elaboracao(
    request: Request,
    pop_id: str,
    req: PopElaboracaoChatRequest,
    actor: dict = Depends(require_perfil_pop(*PERFIS_POP)),
    supabase=Depends(get_supabase_client),
):
    """Chat do agente de elaboração — stateless, síncrono, sem pipeline.

    Recebe o rascunho + as mensagens (+ a seção apontada ⌖) e devolve
    `{ reply, rascunho, periodicidade_sugerida }`. O rascunho devolvido
    persiste na Versão; a primeira interação real move A_ELABORAR →
    EM_ELABORACAO (auditado). Erro de IA não persiste nem transiciona.
    """
    pop, setor, versao = _carregar_contexto(pop_id, actor, supabase)
    try:
        pops_dominio.exigir_estado_de_elaboracao(versao)
    except pops_dominio.TransicaoInvalidaError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    from app.services.ai_processor import chat_elaboracao_pop

    out = chat_elaboracao_pop(
        rascunho=req.rascunho,
        messages=[{"role": m.role, "content": m.content} for m in req.messages],
        section_context=req.section_context,
        pop_contexto={
            "codigo": pop["codigo"],
            "nome": pop["nome"],
            "setor_nome": setor.get("nome"),
            "criticidade": pop["criticidade"],
            "base_normativa": pop.get("base_normativa"),
            "numero_versao": versao["numero_versao"],
        },
    )

    if not out.pop("_erro", False):
        # Diferença deliberada da Ata Guiada (PRD #76): o rascunho persiste na
        # Versão a cada interação. A sugestão de periodicidade só atualiza
        # quando o agente trouxer uma nova — null não apaga a anterior.
        updates: dict = {"rascunho": out["rascunho"]}
        if out.get("periodicidade_sugerida"):
            updates["periodicidade_sugerida"] = out["periodicidade_sugerida"]
        supabase.table("pops_versoes").update(updates).eq("id", versao["id"]).execute()
        versao = pops_dominio.iniciar_elaboracao_se_preciso(supabase, versao, actor=actor, request=request)

    if out.get("periodicidade_sugerida") is None:
        # Devolve a sugestão efetiva (a já gravada) para a UI manter o card.
        out["periodicidade_sugerida"] = versao.get("periodicidade_sugerida")
    return out


@router.patch("/periodicidade")
async def escolher_periodicidade(
    pop_id: str,
    req: PeriodicidadeEscolhaRequest,
    request: Request,
    actor: dict = Depends(require_perfil_pop(*PERFIS_POP)),
    supabase=Depends(get_supabase_client),
):
    """Escolha final do Elaborador para a Periodicidade de revisão — o agente
    sugere, ele decide (DRF §4.2). Grava no POP (campo institucional)."""
    pop, _setor, versao = _carregar_contexto(pop_id, actor, supabase)
    try:
        pops_dominio.exigir_estado_de_elaboracao(versao)
    except pops_dominio.TransicaoInvalidaError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    supabase.table("pops").update({"periodicidade_revisao": req.periodicidade_revisao}).eq("id", pop["id"]).execute()
    audit.log_action(
        supabase,
        actor=actor,
        action="POPS_ESCOLHER_PERIODICIDADE",
        target_type="pop",
        target_id=pop["id"],
        metadata={
            "de": pop.get("periodicidade_revisao"),
            "para": req.periodicidade_revisao,
            "sugerida_pelo_agente": versao.get("periodicidade_sugerida"),
        },
        request=request,
    )
    return {"periodicidade_revisao": req.periodicidade_revisao}


@router.post("/aprovar")
async def aprovar_versao_final(
    pop_id: str,
    request: Request,
    actor: dict = Depends(require_perfil_pop(*PERFIS_POP)),
    supabase=Depends(get_supabase_client),
):
    """ "Aprovar versão final": EM_ELABORACAO → EM_REVISAO (auditado) + email
    ao Revisor designado com link e prazo. Usa o rascunho persistido na
    Versão — a última interação do chat já é a fonte da verdade."""
    pop, setor, versao = _carregar_contexto(pop_id, actor, supabase)
    try:
        versao = pops_dominio.aprovar_versao_final(supabase, versao, actor=actor, request=request)
    except pops_dominio.TransicaoInvalidaError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    pops_email_service.send_elaboracao_concluida_notification(
        supabase, pop, setor, elaborador_nome=actor.get("nome_completo")
    )
    return {"estado": versao["estado"]}
