"""Regra: o Alcance caiu além do limiar (issue #820).

Porte de `src/lib/objetivos/regras/queda-de-alcance.ts`.
"""

from __future__ import annotations

from app.services.central_de_comando.objetivos.tipos import Contexto, Sugestao

from ._ajudantes import formatar_inteiro, pct, queda_alem

LIMIAR_QUEDA = 0.05


def queda_de_alcance(ctx: Contexto) -> Sugestao | None:
    """O Alcance caiu além de 5% no período: vale revisar horários e formatos."""
    reach = ctx.numeros.get("reach")
    if reach is None:
        return None
    v = queda_alem(reach.valor, reach.anterior, LIMIAR_QUEDA)
    if v is None:
        return None
    return Sugestao(
        id="queda-de-alcance",
        titulo="Seu alcance caiu",
        detalhe=("Menos gente está vendo seus posts. Vale revisar os horários de publicação e testar novos formatos."),
        porque=(
            f"Alcance -{pct(v)} no período "
            f"(de {formatar_inteiro(reach.anterior)} para {formatar_inteiro(reach.valor)})."
        ),
        tom="atencao",
    )
