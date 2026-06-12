"""Router /pops — criação de POP e lista por estado (issue #82).

O nascimento de um POP: formulário institucional, Código travado
`HSM_[SIGLA]-[NNN]` (sequência por Setor, imutável — nenhum endpoint o
altera) e a Versão 1.0 nascendo em A_ELABORAR. Gating explícito por
endpoint (ADR 0002); escopo por perfil via app.services.pops_dominio.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from starlette.requests import Request
from supabase import Client

from app.dependencies import get_supabase_client, require_perfil_pop
from app.models.pops_schemas import (
    PERFIS_POP,
    DesignavelResponse,
    EstadoVersaoPop,
    PopCreate,
    PopResponse,
    PopVersaoResponse,
)
from app.services import audit, pops_dominio, pops_email_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pops", tags=["pops"])


def _pop_response(pop: dict, setor: dict, versao: dict | None) -> PopResponse:
    return PopResponse(
        id=pop["id"],
        codigo=pop["codigo"],
        nome=pop["nome"],
        setor_id=pop["setor_id"],
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
        criado_por=pop.get("criado_por"),
        created_at=pop.get("created_at"),
        versao=PopVersaoResponse(**{k: versao[k] for k in ("id", "numero_versao", "estado")}) if versao else None,
    )


@router.get("/designaveis", response_model=list[DesignavelResponse])
async def listar_designaveis(
    _actor: dict = Depends(require_perfil_pop(*PERFIS_POP)),
    supabase: Client = Depends(get_supabase_client),
):
    """Usuários elegíveis a Elaborador/Revisor/Validador no formulário de criação."""
    result = (
        supabase.table("participantes")
        .select("id, nome_completo, email, perfil_pop, ativo")
        .order("nome_completo")
        .execute()
    )
    return [row for row in (result.data or []) if row.get("perfil_pop") and row.get("ativo", True)]


@router.get("", response_model=list[PopResponse])
async def listar_pops(
    estado: EstadoVersaoPop | None = Query(None, description="Filtra pelo estado da versão corrente"),
    actor: dict = Depends(require_perfil_pop(*PERFIS_POP)),
    supabase: Client = Depends(get_supabase_client),
):
    """Lista os POPs do escopo do perfil, com a versão corrente de cada um."""
    escopo = pops_dominio.setores_do_escopo(actor, supabase)
    if escopo is not None and not escopo:
        return []

    query = supabase.table("pops").select("*")
    if escopo is not None:
        query = query.in_("setor_id", sorted(escopo))
    pops = query.execute().data or []
    if not pops:
        return []

    versoes = (
        supabase.table("pops_versoes")
        .select("id, pop_id, numero_versao, estado")
        .in_("pop_id", [p["id"] for p in pops])
        .execute()
    )
    # Leva 1: cada POP tem uma única Versão (a 1.0) — o dict guarda a última lida.
    versao_por_pop = {v["pop_id"]: v for v in (versoes.data or [])}

    setores = supabase.table("pops_setores").select("id, nome, sigla").execute()
    setor_por_id = {s["id"]: s for s in (setores.data or [])}

    items = []
    for pop in pops:
        versao = versao_por_pop.get(pop["id"])
        if estado and (not versao or versao["estado"] != estado):
            continue
        items.append(_pop_response(pop, setor_por_id.get(pop["setor_id"], {}), versao))
    items.sort(key=lambda item: item.codigo)
    return items


@router.post("", response_model=PopResponse, status_code=status.HTTP_201_CREATED)
async def criar_pop(
    body: PopCreate,
    request: Request,
    actor: dict = Depends(require_perfil_pop(*PERFIS_POP)),
    supabase: Client = Depends(get_supabase_client),
):
    """Cria um POP no Setor informado: gera o Código travado e a Versão 1.0."""
    setor_q = supabase.table("pops_setores").select("id, nome, sigla").eq("id", body.setor_id).execute()
    if not setor_q.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Setor não encontrado")
    setor = setor_q.data[0]

    escopo = pops_dominio.setores_do_escopo(actor, supabase)
    if escopo is not None and body.setor_id not in escopo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você só pode criar POPs nos Setores do seu escopo",
        )

    # Designados precisam de perfil POP: sem ele a pessoa não loga no contexto
    # e o fluxo de elaboração/revisão/validação (fatias #83+) nasceria morto.
    designados_ids = list({body.elaborador_id, body.revisor_id, body.validador_id})
    designados_q = supabase.table("participantes").select("id, perfil_pop").in_("id", designados_ids).execute()
    com_perfil = {row["id"] for row in (designados_q.data or []) if row.get("perfil_pop")}
    invalidos = sorted(set(designados_ids) - com_perfil)
    if invalidos:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Elaborador, Revisor e Validador devem ser usuários com perfil POP. "
                f"Sem perfil ou inexistente(s): {', '.join(invalidos)}"
            ),
        )

    numero, codigo = pops_dominio.gerar_codigo(supabase, setor)

    pop_insert = (
        supabase.table("pops")
        .insert(
            {
                "setor_id": body.setor_id,
                "numero": numero,
                "codigo": codigo,
                "nome": body.nome.strip(),
                "criticidade": body.criticidade,
                "base_normativa": body.base_normativa,
                "periodicidade_revisao": body.periodicidade_revisao,
                "prazo_elaboracao_dias": body.prazo_elaboracao_dias,
                "prazo_revisao_dias": body.prazo_revisao_dias,
                "elaborador_id": body.elaborador_id,
                "revisor_id": body.revisor_id,
                "validador_id": body.validador_id,
                "criado_por": actor.get("id"),
            }
        )
        .execute()
    )
    if not pop_insert.data:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro ao criar POP")
    pop = pop_insert.data[0]

    versao_insert = (
        supabase.table("pops_versoes")
        .insert({"pop_id": pop["id"], "numero_versao": "1.0", "estado": "A_ELABORAR"})
        .execute()
    )
    versao = versao_insert.data[0] if versao_insert.data else None

    audit.log_action(
        supabase,
        actor=actor,
        action="POPS_CRIAR_POP",
        target_type="pop",
        target_id=pop["id"],
        metadata={
            "codigo": codigo,
            "nome": pop["nome"],
            "setor_id": body.setor_id,
            "elaborador_id": body.elaborador_id,
            "revisor_id": body.revisor_id,
            "validador_id": body.validador_id,
        },
        request=request,
    )

    pops_email_service.send_pop_criado_notification(supabase, pop, setor, criador_nome=actor.get("nome_completo"))

    return _pop_response(pop, setor, versao)
