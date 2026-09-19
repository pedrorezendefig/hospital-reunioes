"""Regra: os Reels são maioria das publicações de maior interação (issue #820).

Porte de `src/lib/objetivos/regras/reels-rendem-mais.ts`.
"""

from __future__ import annotations

from app.services.central_de_comando.objetivos.tipos import Contexto, Sugestao

TOP = 4


def reels_rendem_mais(ctx: Contexto) -> Sugestao | None:
    """Os Reels são maioria estrita das publicações de maior interação (mais da
    metade do topo): priorizar o formato. Empate não dispara."""
    top = list(ctx.extras.publicacoes)[:TOP]
    reels = [p for p in top if p.tipo == "reel"]
    if len(top) < 2 or len(reels) * 2 <= len(top):
        return None
    return Sugestao(
        id="reels-rendem-mais",
        titulo="Reels estão rendendo mais",
        detalhe=("Seus Reels lideram as publicações de maior interação. Priorize esse formato nas próximas semanas."),
        porque=f"{len(reels)} das {len(top)} publicações de maior interação foram Reels.",
        tom="positivo",
    )
