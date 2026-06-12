"""Montagem da resposta "Versão completa" de um POP (issues #83/#85).

A mesma renderização das 11 seções serve a tela de elaboração (POP vivo) e
a leitura formal da Revisão/Validação: identificação derivada do POP (nomes
dos designados resolvidos), rascunho persistido na Versão e as Devoluções
com autor e timestamp.
"""

from __future__ import annotations

from app.models.pops_schemas import (
    PopDevolucaoResponse,
    PopElaboracaoPopInfo,
    PopElaboracaoResponse,
    PopVersaoResponse,
)


def nomes_designados(supabase, pop: dict) -> dict[str, str | None]:
    """Nomes de Elaborador/Revisor/Validador por id — também cobrem os
    autores de Devolução (sempre o Revisor ou o Validador designados)."""
    ids = list({pop["elaborador_id"], pop["revisor_id"], pop["validador_id"]})
    result = supabase.table("participantes").select("id, nome_completo").in_("id", ids).execute()
    return {row["id"]: row.get("nome_completo") for row in (result.data or [])}


def montar_versao_response(
    pop: dict,
    setor: dict,
    versao: dict,
    nomes: dict,
    devolucoes: list[dict] | None = None,
) -> PopElaboracaoResponse:
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
        devolucoes=[
            PopDevolucaoResponse(
                id=d["id"],
                autor_id=d["autor_id"],
                autor_nome=nomes.get(d["autor_id"]),
                etapa_retorno=d["etapa_retorno"],
                comentarios=d["comentarios"],
                created_at=d.get("created_at"),
            )
            for d in (devolucoes or [])
        ],
    )
