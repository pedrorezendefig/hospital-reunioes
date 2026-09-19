"""O motor de regras de sugestão dos Objetivos (issue #820).

Porte de `src/lib/objetivos/regras/index.ts`: quais regras rodam para cada
Objetivo, e o `rodar_regras` que devolve só as sugestões que dispararam. Cada
regra é uma função pura (uma por arquivo), testada direto.
"""

from __future__ import annotations

from app.services.central_de_comando.objetivos.tipos import (
    Contexto,
    ObjetivoId,
    Regra,
    Sugestao,
)

from .contatos_instrumentar import contatos_instrumentar
from .dispositivo_celular_domina import dispositivo_celular_domina
from .queda_de_alcance import queda_de_alcance
from .queda_de_interacoes import queda_de_interacoes
from .reels_rendem_mais import reels_rendem_mais

# Quais regras rodam para cada Objetivo. Espelha os MONTADORES do montador.py.
REGRAS_POR_OBJETIVO: dict[ObjetivoId, tuple[Regra, ...]] = {
    "instagram-seguidores": (queda_de_alcance,),
    "instagram-engajamento": (queda_de_interacoes, reels_rendem_mais),
    "site-visitantes": (dispositivo_celular_domina,),
    "contatos": (contatos_instrumentar,),
}


def rodar_regras(objetivo_id: ObjetivoId, ctx: Contexto) -> list[Sugestao]:
    """Roda as regras do Objetivo e devolve só as sugestões que dispararam."""
    regras = REGRAS_POR_OBJETIVO.get(objetivo_id, ())
    return [sugestao for regra in regras if (sugestao := regra(ctx)) is not None]


__all__ = [
    "REGRAS_POR_OBJETIVO",
    "contatos_instrumentar",
    "dispositivo_celular_domina",
    "queda_de_alcance",
    "queda_de_interacoes",
    "reels_rendem_mais",
    "rodar_regras",
]
