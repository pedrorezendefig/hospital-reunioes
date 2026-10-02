"""A variação de um número da Central contra o período anterior.

Porte de `src/lib/analytics/variation.ts` do repositório antigo. A conta mora
no backend, e a tela só formata (PRD #809: "o front não compõe chamadas nem faz
conta").
"""

from __future__ import annotations


def variacao_relativa(atual: float, anterior: float) -> float | None:
    """A fração de variação do anterior para o atual: 112 contra 100 é 0,12.

    Sem base de comparação (anterior zero ou negativo) devolve `None`, e quem
    mostra decide não desenhar seta nenhuma. Nunca um infinito, nunca um zero
    que diria "não mudou" sobre o que não dá para comparar.
    """
    if anterior <= 0:
        return None
    return (atual - anterior) / anterior
