"""Os ajudantes das regras de sugestao (issue #820).

Porte de `src/lib/objetivos/regras/_helpers.ts` (o `pct`, o `quedaAlem` e o
`naoCaiu`) mais o formatador de inteiro pt-BR que o `porque` usa. A conta da
variacao e a mesma da Central (`variacao.py`, PRD #809: a conta mora no
backend).
"""

from __future__ import annotations

import math

from app.services.central_de_comando.variacao import variacao_relativa


def pct(fracao: float) -> str:
    """A fracao como percentual inteiro, sem sinal, para a frase ancorada.
    Ex.: -0,2 vira "20%". Arredonda meio ponto para cima, como o `Math.round`."""
    return f"{math.floor(abs(fracao) * 100 + 0.5)}%"


def formatar_inteiro(n: int) -> str:
    """O inteiro no formato pt-BR: 37650 vira "37.650". O ponto separa milhar,
    como a tela mostra (`formato.ts` no front)."""
    return f"{n:,}".replace(",", ".")


def queda_alem(atual: float, anterior: int | None, limiar: float) -> float | None:
    """A fracao negativa da queda quando `atual` caiu alem de `limiar` em
    relacao a `anterior`; `None` se nao caiu o bastante ou nao ha base de
    comparacao (anterior ausente, zero ou negativo)."""
    if anterior is None:
        return None
    v = variacao_relativa(atual, anterior)
    if v is None or v > -limiar:
        return None
    return v


def nao_caiu(atual: float, anterior: int | None, limiar: float) -> bool:
    """Nao houve queda alem do limiar (estavel, subiu, ou sem base)."""
    return queda_alem(atual, anterior, limiar) is None
