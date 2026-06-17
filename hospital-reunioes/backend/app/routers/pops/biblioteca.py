"""Router /pops/biblioteca — o repositório oficial dos POPs (issue #87).

Lista os POPs com Versão Publicada, organizáveis por Setor no frontend:
código, nome, versão vigente, responsáveis designados e as datas de cada
etapa do ciclo (criação, fim da elaboração, aprovações, publicação) — tudo
respeitando o escopo do perfil (Coordenador: seu Setor; Gerente: seus
Setores; Gestor de Qualidade/Superadmin: todos). O download do PDF assinado
vive em GET /pops/{pop_id}/documento (que serve o assinado para PUBLICADO).

As datas de etapa vêm da auditoria das transições (audit_log) — POPs com
trilha incompleta listam com datas nulas, nunca somem da Biblioteca.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from supabase import Client

from app.dependencies import get_supabase_client, require_perfil_pop
from app.models.pops_schemas import PERFIS_POP, BibliotecaItemResponse
from app.services import pops_dominio

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pops/biblioteca", tags=["pops"])

# Transição auditada → campo de data exposto na Biblioteca. Com Devoluções a
# mesma ação aparece mais de uma vez: vale a MAIS RECENTE (o ciclo que valeu).
_ACAO_PARA_DATA = {
    "POPS_APROVAR_VERSAO_FINAL": "elaboracao_concluida_em",
    "POPS_APROVAR_REVISAO": "revisao_aprovada_em",
    "POPS_APROVAR_VALIDACAO": "validacao_aprovada_em",
}


def _datas_de_etapa(supabase: Client, versao_ids: list[str]) -> dict[str, dict[str, str]]:
    """{versao_id: {campo: timestamp ISO}} a partir da trilha de auditoria."""
    result = (
        supabase.table("audit_log")
        .select("action, target_id, timestamp")
        .in_("target_id", versao_ids)
        .in_("action", list(_ACAO_PARA_DATA))
        .execute()
    )
    datas: dict[str, dict[str, str]] = {}
    for row in result.data or []:
        campo = _ACAO_PARA_DATA.get(row.get("action"))
        ts = row.get("timestamp")
        if not campo or not ts:
            continue
        por_versao = datas.setdefault(row["target_id"], {})
        # ISO UTC compara lexicograficamente: fica o mais recente
        if campo not in por_versao or ts > por_versao[campo]:
            por_versao[campo] = ts
    return datas


@router.get("", response_model=list[BibliotecaItemResponse])
async def listar_biblioteca(
    actor: dict = Depends(require_perfil_pop(*PERFIS_POP)),
    supabase: Client = Depends(get_supabase_client),
):
    """Os POPs Publicados do escopo do perfil, com metadados completos."""
    escopo = pops_dominio.setores_do_escopo(actor, supabase)
    if escopo is not None and not escopo:
        return []

    # Colunas explícitas: o rascunho JSONB (as seções de texto) não entra
    # na listagem — só metadados.
    versoes = (
        supabase.table("pops_versoes")
        .select("id, pop_id, numero_versao, estado, data_publicacao")
        .eq("estado", "PUBLICADO")
        .execute()
        .data
        or []
    )
    if not versoes:
        return []
    versao_por_pop = {v["pop_id"]: v for v in versoes}

    pops = supabase.table("pops").select("*").in_("id", list(versao_por_pop)).execute().data or []
    if escopo is not None:
        pops = [p for p in pops if p["setor_id"] in escopo]
    if not pops:
        return []

    setores = supabase.table("pops_setores").select("id, nome, sigla").execute()
    setor_por_id = {s["id"]: s for s in (setores.data or [])}

    designados_ids = sorted({p[papel] for p in pops for papel in ("elaborador_id", "revisor_id", "validador_id")})
    pessoas = supabase.table("participantes").select("id, nome_completo").in_("id", designados_ids).execute()
    nome_por_id = {row["id"]: row.get("nome_completo") for row in (pessoas.data or [])}

    datas = _datas_de_etapa(supabase, [versao_por_pop[p["id"]]["id"] for p in pops])

    itens = []
    for pop in pops:
        versao = versao_por_pop[pop["id"]]
        setor = setor_por_id.get(pop["setor_id"], {})
        etapas = datas.get(versao["id"], {})
        itens.append(
            BibliotecaItemResponse(
                pop_id=pop["id"],
                codigo=pop["codigo"],
                nome=pop["nome"],
                setor_id=pop["setor_id"],
                setor_nome=setor.get("nome"),
                setor_sigla=setor.get("sigla"),
                numero_versao=versao["numero_versao"],
                criticidade=pop["criticidade"],
                periodicidade_revisao=pop["periodicidade_revisao"],
                elaborador_nome=nome_por_id.get(pop["elaborador_id"]),
                revisor_nome=nome_por_id.get(pop["revisor_id"]),
                validador_nome=nome_por_id.get(pop["validador_id"]),
                criado_em=pop.get("created_at"),
                elaboracao_concluida_em=etapas.get("elaboracao_concluida_em"),
                revisao_aprovada_em=etapas.get("revisao_aprovada_em"),
                validacao_aprovada_em=etapas.get("validacao_aprovada_em"),
                publicado_em=versao.get("data_publicacao"),
            )
        )
    itens.sort(key=lambda item: item.codigo)
    return itens
