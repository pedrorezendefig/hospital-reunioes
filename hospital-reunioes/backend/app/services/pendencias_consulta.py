"""A consulta da lista de Pendências, num lugar só (issue #1609, ADR 0085).

É a consulta da tela de Pendências (`GET /pendencias`) e da ferramenta de
pendências do Conector: as duas chamam esta função, e é por isso que a
pendência que o Claude recebe como atrasada é a que a tela mostra como
atrasada. Atrasada é o status `ATRASADO`, que o job `marcar_atrasadas` grava
na pendência PENDENTE de prazo vencido; nenhuma das duas portas recalcula.

Quem chama resolve antes quem é (a visibilidade das Reuniões) e passa:
`allowed_reuniao_ids` (None é sem filtro, a visão de Super admin) e o id do
participante, para o OR de co-responsável.
"""

from __future__ import annotations

from datetime import date


def consultar_pendencias(
    supabase,
    *,
    allowed_reuniao_ids: list[str] | None,
    my_participante_id: str | None,
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
    query = supabase.table("pendencias").select("*", count="exact").is_("deleted_at", "null")

    # Resolve filtro de facilitador cedo (afeta a aplicação de visibilidade)
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

    # Visibilidade binária + filtro facilitador.
    # Quando facilitador está presente, é mais restritivo: ignoramos o OR de co-responsável
    # para que "filtrar pelo facilitador X" signifique exatamente "pendências das reuniões dele".
    if facilitator_meeting_ids is not None:
        if allowed_reuniao_ids is not None:
            allowed_set = set(allowed_reuniao_ids)
            facilitator_meeting_ids = [m for m in facilitator_meeting_ids if m in allowed_set]
            if not facilitator_meeting_ids:
                return [], 0
        query = query.in_("id_reuniao", facilitator_meeting_ids)
    elif allowed_reuniao_ids is not None:
        if not allowed_reuniao_ids and not my_participante_id:
            return [], 0
        elif my_participante_id:
            # Visível: reuniões permitidas OU co-responsável.
            condicoes = [f"co_responsavel_id.eq.{my_participante_id}"]
            if allowed_reuniao_ids:
                condicoes.insert(0, f"id_reuniao.in.({','.join(allowed_reuniao_ids)})")
            query = query.or_(",".join(condicoes))
        else:
            query = query.in_("id_reuniao", allowed_reuniao_ids)

    # Filtro por setor (super user only)
    if setores and allowed_reuniao_ids is None:
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
        query = query.eq("status", status)
    if id_reuniao:
        query = query.eq("id_reuniao", id_reuniao)
    if prazo_de:
        query = query.gte("prazo", str(prazo_de))
    if prazo_ate:
        query = query.lte("prazo", str(prazo_ate))

    result = query.order("prazo", desc=False, nullsfirst=False).range(offset, offset + limit - 1).execute()
    return result.data or [], result.count or 0
