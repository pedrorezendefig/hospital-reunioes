"""Regra: nem todos os canais de contato são medidos (issue #820).

Porte de `src/lib/objetivos/regras/contatos-instrumentar.ts`. Instrumentar os
canais que faltam mostra o quadro completo de contatos gerados (ADR 0058).
"""

from __future__ import annotations

from app.services.central_de_comando.objetivos.tipos import Contexto, Sugestao


def contatos_instrumentar(ctx: Contexto) -> Sugestao | None:
    """Há canais de contato ainda não medidos: instrumentá-los mostra o quadro
    completo. O porquê lista quais faltam."""
    canais = ctx.extras.canais
    if len(canais) == 0:
        return None
    pendentes = [c for c in canais if c.estado != "medido"]
    if len(pendentes) == 0:
        return None
    nomes = " e ".join(c.rotulo for c in pendentes)
    return Sugestao(
        id="contatos-instrumentar",
        titulo="Você só enxerga parte dos contatos",
        detalhe=f"Instrumentar {nomes} no site mostra o quadro completo de contatos gerados.",
        porque=f"{len(pendentes)} de {len(canais)} canais ainda não são medidos ({nomes}).",
        tom="neutro",
    )
