"""Regra: as Interações caíram, mas o Alcance se manteve (issue #820).

Porte de `src/lib/objetivos/regras/queda-de-interacoes.ts`.
"""

from __future__ import annotations

from app.services.central_de_comando.objetivos.tipos import Contexto, Sugestao

from ._ajudantes import nao_caiu, pct, queda_alem

LIMIAR_QUEDA = 0.05


def queda_de_interacoes(ctx: Contexto) -> Sugestao | None:
    """As Interações caíram, mas o Alcance não: é hora de puxar comentário na
    legenda. Sem o Alcance no contexto, não dá para afirmar, e a regra cala."""
    inter = ctx.numeros.get("interactions")
    reach = ctx.extras.reach
    if inter is None:
        return None
    v = queda_alem(inter.valor, inter.anterior, LIMIAR_QUEDA)
    if v is None:
        return None
    if reach is None or not nao_caiu(reach.valor, reach.anterior, LIMIAR_QUEDA):
        return None
    return Sugestao(
        id="queda-de-interacoes",
        titulo="Engajamento caiu, mas o alcance não",
        detalhe=("As pessoas estão vendo e interagindo menos. Puxe um comentário: termine a legenda com uma pergunta."),
        porque=f"Interações -{pct(v)} no período, com o alcance mantido.",
        tom="atencao",
    )
