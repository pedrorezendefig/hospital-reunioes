"""A consulta da lista de Pendências, num lugar só (issue #1609, ADR 0085).

É a consulta da tela de Pendências (`GET /pendencias`) e da ferramenta de
pendências do Conector: as duas chamam esta função, e é por isso que a
pendência que o Claude recebe como atrasada é a que a tela mostra como
atrasada. Desde a issue #1862 (ADR 0098, decisão 4) atrasada é calculada:
pendência aberta com prazo vencido no fuso de Brasília, sem job nenhum. E
repactuada é a que tem Repactuação no histórico. Os dois valem como filtro de
`status` (`ATRASADO` e `REPACTUADA`), além dos quatro estados gravados.

Quem chama resolve antes quem é e passa o recorte das Pendências dessa pessoa
(`pendencias_recorte`, issue #1863): o vínculo de responsável, co-responsável
e Facilitador, a visão inteira do Super admin, e as reuniões do Núcleo que a
pessoa não alcança (`ocultas`, issue #1772).
"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.services.paginacao import ler_tudo
from app.services.pendencias_recorte import RecorteDasPendencias

FUSO = ZoneInfo("America/Sao_Paulo")
ABERTOS = ["PENDENTE", "EM_PROGRESSO"]
# Acima disso, ler todas as Repactuações sai mais barato que um `in` gigante.
_LOTE_DO_IN = 200


def hoje_em_brasilia() -> date:
    return datetime.now(FUSO).date()


def as_data(valor) -> date | None:
    """O prazo como vem do PostgREST (texto ISO) ou já como `date`."""
    if valor is None or isinstance(valor, date):
        return valor
    return date.fromisoformat(str(valor)[:10])


def ids_repactuados(supabase, ids: list[str] | None) -> set[str]:
    """As pendências (de `ids`, ou todas com `None`) que têm Repactuação no
    histórico."""
    if ids is not None and not ids:
        return set()
    if ids is not None and len(ids) <= _LOTE_DO_IN:
        res = (
            supabase.table("pendencia_historico")
            .select("id_acao")
            .eq("comando", "repactuar")
            .in_("id_acao", ids)
            .execute()
        )
        return {r["id_acao"] for r in res.data or []}
    achados: set[str] = set()
    inicio = 0
    while True:
        res = (
            supabase.table("pendencia_historico")
            .select("id_acao")
            .eq("comando", "repactuar")
            .order("id")
            .range(inicio, inicio + 999)
            .execute()
        )
        linhas = res.data or []
        achados.update(r["id_acao"] for r in linhas)
        if len(linhas) < 1000:
            break
        inicio += 1000
    return achados if ids is None else achados & set(ids)


# A Contestação (issue #1870) fica aberta até o Facilitador ajustar ou recusar.
_DA_CONTESTACAO = ["contestar", "ajustar", "recusar"]


def contestacoes_abertas(supabase, ids: list[str] | None) -> dict[str, dict]:
    """As pendências (de `ids`, ou todas com `None`) com Contestação aberta,
    cada uma com o evento da Contestação: no histórico, o último evento da
    Contestação dela é `contestar`. Contestação é rara, então a leitura sem
    `ids` lê todos esses eventos, em páginas."""
    if ids is not None and not ids:
        return {}
    em_lote = ids is not None and len(ids) <= _LOTE_DO_IN

    def _consulta():
        q = (
            supabase.table("pendencia_historico")
            .select("id, id_acao, comando, anotacao, autor_nome, criado_em")
            .in_("comando", _DA_CONTESTACAO)
        )
        return q.in_("id_acao", ids) if em_lote else q

    if em_lote:
        eventos = _consulta().execute().data or []
    else:
        eventos = ler_tudo(lambda: _consulta().order("id"), rotulo="contestações")
    ultimo: dict[str, dict] = {}
    for evento in sorted(eventos, key=lambda e: (e.get("criado_em") or "", e.get("id") or 0)):
        ultimo[evento["id_acao"]] = evento
    abertas = {id_acao: e for id_acao, e in ultimo.items() if e["comando"] == "contestar"}
    if ids is None:
        return abertas
    pedidos = set(ids)
    return {id_acao: e for id_acao, e in abertas.items() if id_acao in pedidos}


def filtrar_por_status(query, supabase, status: str):
    """O filtro de status aceita os quatro gravados e os dois calculados, nos
    termos de `pendencia_ciclo.situacao()`: Atrasada vence Repactuada, que vence
    o estado gravado da aberta."""
    hoje = hoje_em_brasilia().isoformat()
    if status == "ATRASADO":
        return query.in_("status", ABERTOS).lt("prazo", hoje)
    if status != "REPACTUADA" and status not in ABERTOS:
        return query.eq("status", status)
    # Aberta que não venceu: sem prazo, ou prazo de hoje em diante.
    query = query.or_(f"prazo.is.null,prazo.gte.{hoje}")
    repactuados = sorted(ids_repactuados(supabase, None))
    if status == "REPACTUADA":
        return query.in_("status", ABERTOS).in_("id_acao", repactuados or ["-"])
    query = query.eq("status", status)
    return query.not_.in_("id_acao", repactuados) if repactuados else query


def sem_reunioes_ocultas(query, ocultas: list[str]):
    """Tira da consulta as pendências das reuniões do Núcleo que a pessoa não
    alcança (issue #1772) e mantém a pendência sem reunião: o `not.in` do
    banco sozinho não casa NULL e a levaria junto."""
    if not ocultas:
        return query
    return query.or_(f"id_reuniao.is.null,id_reuniao.not.in.({','.join(ocultas)})")


def no_recorte(query, recorte: RecorteDasPendencias):
    """Deixa na consulta só as pendências do recorte da pessoa (issue #1863).
    None quer dizer que nada aparece, e quem chama devolve vazio sem ir ao
    banco."""
    query = sem_reunioes_ocultas(query, list(recorte.ocultas))
    filtro = recorte.filtro()
    if filtro is None:
        return query
    if not filtro:
        return None
    return query.or_(filtro)


def consultar_pendencias(
    supabase,
    *,
    recorte: RecorteDasPendencias,
    status: str | None = None,
    responsaveis: list[str] | None = None,
    id_reuniao: str | None = None,
    prazo_de: date | None = None,
    prazo_ate: date | None = None,
    setores: list[str] | None = None,
    facilitadores: list[str] | None = None,
    limit: int,
    offset: int = 0,
) -> tuple[list[dict], int]:
    """As pendências visíveis com os filtros, por prazo (as sem prazo no fim),
    cortadas em `limit` a partir de `offset`. Devolve as linhas e o total antes
    do corte."""
    # A Pendência sem Reunião é o lembrete da Agenda regulatória do Núcleo:
    # nenhuma lista de Pendências o mostra (`e_lembrete_do_nucleo`).
    query = no_recorte(
        supabase.table("pendencias")
        .select("*", count="exact")
        .is_("deleted_at", "null")
        .not_.is_("id_reuniao", "null"),
        recorte,
    )
    if query is None:
        return [], 0

    # Filtro de facilitador: as reuniões que cada facilitador pedido conduz.
    facilitator_meeting_ids: list[str] | None = None
    if facilitadores:
        rq = supabase.table("reunioes").select("id_reuniao").is_("deleted_at", "null")
        rq = (
            rq.in_("facilitador_id", facilitadores)
            if len(facilitadores) > 1
            else rq.eq("facilitador_id", facilitadores[0])
        )
        rq_res = rq.execute()
        facilitator_meeting_ids = [r["id_reuniao"] for r in (rq_res.data or [])]
        if not facilitator_meeting_ids:
            return [], 0

    # O filtro de facilitador vale junto com o recorte: "as do facilitador X"
    # é a parte do recorte que está nas reuniões dele.
    if facilitator_meeting_ids is not None:
        query = query.in_("id_reuniao", facilitator_meeting_ids)

    # Filtro por setor (super user only)
    if setores and recorte.reunioes is None:
        has_sem_setor = "Sem Setor" in setores
        setores_real = [s for s in setores if s != "Sem Setor"]
        pq = supabase.table("participantes").select("id")
        if has_sem_setor and setores_real:
            in_list = ",".join(setores_real)
            pq = pq.or_(f"setor.is.null,setor.in.({in_list})")
        elif has_sem_setor:
            pq = pq.is_("setor", "null")
        elif len(setores_real) == 1:
            pq = pq.eq("setor", setores_real[0])
        else:
            pq = pq.in_("setor", setores_real)
        p_res = pq.execute()
        sector_ids = [p["id"] for p in (p_res.data or [])]
        if sector_ids:
            query = query.in_("responsavel_id", sector_ids)
        else:
            return [], 0

    # Filtro por responsável específico
    if responsaveis:
        if len(responsaveis) == 1:
            query = query.eq("responsavel_id", responsaveis[0])
        else:
            query = query.in_("responsavel_id", responsaveis)

    if status:
        query = filtrar_por_status(query, supabase, status)
    if id_reuniao:
        query = query.eq("id_reuniao", id_reuniao)
    if prazo_de:
        query = query.gte("prazo", str(prazo_de))
    if prazo_ate:
        query = query.lte("prazo", str(prazo_ate))

    result = query.order("prazo", desc=False, nullsfirst=False).range(offset, offset + limit - 1).execute()
    return result.data or [], result.count or 0
