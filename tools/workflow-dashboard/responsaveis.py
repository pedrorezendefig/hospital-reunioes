"""Agrupamento por responsável da aba Issues do painel (ADR 0061, decisão 5).

Função pura: issues, PRs, mapa PRD -> fatias e o history.json (no shape do
collect.py) entram, grupos por responsável saem. O front só desenha.
"""

from __future__ import annotations

from datetime import datetime, timezone


def agrupar_por_responsavel(
    issues: list[dict],
    prs: list[dict],
    fatias_por_prd: dict[int, list[int]],
    history: list[dict],
    agora: datetime | None = None,
) -> dict:
    grupos: dict[str | None, list[dict]] = {}
    for i in issues:
        for quem in i["assignees"]:
            grupos.setdefault(quem, []).append({"number": i["number"]})
    return {"grupos": [{"responsavel": quem, "itens": itens} for quem, itens in grupos.items()]}
