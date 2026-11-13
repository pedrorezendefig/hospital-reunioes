"""As consultas das telas de Reuniões, num lugar só (issue #1610, ADR 0085).

A lista de Reuniões (`GET /reunioes`), os Participantes vinculados do
calendário (`GET /reunioes/calendario`) e a ferramenta de Reuniões do Conector
chamam estas funções, e é por isso que o Claude recebe as mesmas Reuniões que a
tela mostra à pessoa.

Quem chama resolve antes quem é e passa `allowed_reuniao_ids` (None é sem
filtro, a visão de Super admin e da Secretária).
"""

from __future__ import annotations

from datetime import date

# As colunas de texto em que o termo da busca procura: o título, o objetivo e o
# resumo executivo da Ata.
_COLUNAS_DO_TERMO = ("titulo", "objetivo", "json_ata->>resumo_executivo")


def consultar_reunioes(
    supabase,
    *,
    allowed_reuniao_ids: list[str] | None,
    statuses: list[str] | None = None,
    tipos: list[str] | None = None,
    facilitadores: list[str] | None = None,
    data_inicio: date | None = None,
    data_fim: date | None = None,
    termo: str | None = None,
    limit: int,
    offset: int = 0,
) -> tuple[list[dict], int]:
    """As Reuniões visíveis com os filtros, da mais recente para a mais antiga,
    cortadas em `limit` a partir de `offset`. Devolve as linhas e o total antes
    do corte. `termo` já vem limpo de caractere que o filtro `or` do PostgREST
    leia como sintaxe."""
    if allowed_reuniao_ids is not None and not allowed_reuniao_ids:
        return [], 0

    query = supabase.table("reunioes").select("*", count="exact").is_("deleted_at", "null")

    if statuses:
        query = query.in_("status_ata", statuses) if len(statuses) > 1 else query.eq("status_ata", statuses[0])
    if tipos:
        query = query.in_("tipo", tipos) if len(tipos) > 1 else query.eq("tipo", tipos[0])
    if facilitadores:
        query = (
            query.in_("facilitador_id", facilitadores)
            if len(facilitadores) > 1
            else query.eq("facilitador_id", facilitadores[0])
        )
    if data_inicio:
        query = query.gte("data", str(data_inicio))
    if data_fim:
        query = query.lte("data", str(data_fim))
    if termo:
        query = query.or_(",".join(f"{coluna}.ilike.*{termo}*" for coluna in _COLUNAS_DO_TERMO))

    # Visibilidade binária
    if allowed_reuniao_ids is not None:
        query = query.in_("id_reuniao", allowed_reuniao_ids)

    result = query.order("data", desc=True).range(offset, offset + limit - 1).execute()
    return result.data or [], result.count or 0


def participantes_por_reuniao(supabase, ids: list[str]) -> dict[str, list[dict]]:
    """Os Participantes vinculados de cada Reunião (`reuniao_participantes`),
    com nome e cargo do cadastro. Vínculo sem nome no cadastro fica de fora."""
    participantes_map: dict[str, list[dict]] = {r: [] for r in ids}
    if not ids:
        return participantes_map
    part_result = (
        supabase.table("reuniao_participantes")
        .select("id_reuniao, participante_id, participantes(nome_completo, cargo)")
        .in_("id_reuniao", ids)
        .execute()
    )
    for row in part_result.data:
        rid = row["id_reuniao"]
        if rid in participantes_map:
            part = row.get("participantes")
            if isinstance(part, list) and part:
                part = part[0]
            if part and isinstance(part, dict) and part.get("nome_completo"):
                participantes_map[rid].append(
                    {
                        "id": row["participante_id"],
                        "nome": part["nome_completo"],
                        "cargo": part.get("cargo", ""),
                    }
                )
    return participantes_map
