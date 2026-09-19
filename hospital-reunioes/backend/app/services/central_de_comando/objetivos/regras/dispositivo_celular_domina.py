"""Regra: a maioria acessa o site pelo celular (issue #820).

Porte de `src/lib/objetivos/regras/dispositivo-celular-domina.ts`.
"""

from __future__ import annotations

from app.services.central_de_comando.objetivos.tipos import Contexto, Sugestao

from ._ajudantes import pct

LIMIAR_CELULAR = 0.6


def dispositivo_celular_domina(ctx: Contexto) -> Sugestao | None:
    """O celular passa de 60% das visitas: garantir o site leve no celular."""
    dispositivos = ctx.extras.dispositivos
    total = sum(d.visitas for d in dispositivos)
    if total <= 0:
        return None
    celular = next((d for d in dispositivos if d.dispositivo == "celular"), None)
    if celular is None:
        return None
    fatia = celular.visitas / total
    if fatia < LIMIAR_CELULAR:
        return None
    return Sugestao(
        id="dispositivo-celular-domina",
        titulo="A maioria acessa pelo celular",
        detalhe=("Garanta que o site abra rápido e leve no celular: imagens otimizadas, botões grandes, menos texto."),
        porque=f"{pct(fatia)} das visitas do período vieram do celular.",
        tom="neutro",
    )
