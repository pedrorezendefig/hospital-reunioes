"""A Previsão de Contas médicas (issue #1417, PRD #1415).

Quanto falta para cada conta ficar pronta e os tempos da barra da aba Envios.
Função pura: não lê banco nem relógio. Quem chama entrega as contas Na fila e
Processando, o histórico das contas prontas e o `agora`.

- Segundos por página do Prontuário: a média das últimas 20 contas prontas
  dos últimos 7 dias, vezes as páginas da conta.
- As vagas são simuladas na ordem de envio: a conta Na fila pega a primeira
  vaga que abre.
- Com menos de 5 contas prontas nos últimos 7 dias não há Previsão, só a
  posição na fila e as médias.
- A conta Processando há mais de 2 vezes a Previsão está "demorando mais que o
  normal".

A ordem de processamento não muda: aqui só se prevê.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta

# O histórico que entra nas médias e na Previsão.
JANELA = timedelta(days=7)
# Quantas contas prontas, as mais recentes, dão os segundos por página.
ULTIMAS = 20
# Abaixo disto, a Previsão não aparece (os primeiros dias do módulo).
MINIMO_DE_PRONTAS = 5
# Passou disto vezes a Previsão: "demorando mais que o normal".
FATOR_DA_DEMORA = 2


@dataclass(frozen=True)
class ContaPronta:
    """Uma conta que ficou pronta: quando foi enviada, quando ficou pronta, a
    soma de `tempos_por_etapa_s` e as páginas do Prontuário dela."""

    enviada_em: datetime | None
    pronta_em: datetime
    processamento_s: float | None
    paginas: int | None


@dataclass(frozen=True)
class ContaEmAndamento:
    """Uma conta Na fila ou Processando."""

    id: str
    situacao: str
    ordem_fila: int
    paginas: int | None
    processando_desde: datetime | None


@dataclass(frozen=True)
class PrevisaoDaConta:
    """A posição na fila (só Na fila, contando de 1) e, com Previsão, a hora
    em que a conta começa e a hora em que fica pronta."""

    posicao: int | None
    inicio: datetime | None
    pronta: datetime | None
    demorando: bool


@dataclass(frozen=True)
class Resumo:
    """A barra da aba Envios."""

    processando: int
    na_fila: int
    tempo_envio_a_fila_s: float | None
    tempo_processamento_s: float | None
    fila_esvazia_em: datetime | None


def _media(valores: list[float]) -> float | None:
    return sum(valores) / len(valores) if valores else None


def _segundos_por_pagina(recentes: list[ContaPronta]) -> float | None:
    com_paginas = [c for c in recentes if c.paginas and c.processamento_s is not None]
    if len(com_paginas) < MINIMO_DE_PRONTAS:
        return None
    ultimas = sorted(com_paginas, key=lambda c: c.pronta_em, reverse=True)[:ULTIMAS]
    return _media([c.processamento_s / c.paginas for c in ultimas])


def prever(
    contas: list[ContaEmAndamento], prontas: list[ContaPronta], agora: datetime, vagas: int
) -> tuple[dict[str, PrevisaoDaConta], Resumo]:
    """A Previsão de cada conta, pelo id, e o resumo da barra."""
    recentes = [c for c in prontas if agora - c.pronta_em <= JANELA]
    por_pagina = _segundos_por_pagina(recentes)
    processando = [c for c in contas if c.situacao == "PROCESSANDO"]
    na_fila = sorted((c for c in contas if c.situacao == "NA_FILA"), key=lambda c: c.ordem_fila)
    resumo = Resumo(
        processando=len(processando),
        na_fila=len(na_fila),
        tempo_envio_a_fila_s=_media(
            [(c.pronta_em - c.enviada_em).total_seconds() for c in recentes if c.enviada_em is not None]
        ),
        tempo_processamento_s=_media([c.processamento_s for c in recentes if c.processamento_s is not None]),
        fila_esvazia_em=None,
    )
    if por_pagina is None:
        previsoes = {c.id: PrevisaoDaConta(None, None, None, False) for c in processando}
        previsoes |= {c.id: PrevisaoDaConta(n, None, None, False) for n, c in enumerate(na_fila, start=1)}
        return previsoes, resumo

    # A conta sem páginas conhecidas leva o tempo médio de processamento.
    def duracao(conta: ContaEmAndamento) -> timedelta:
        if conta.paginas:
            return timedelta(seconds=por_pagina * conta.paginas)
        return timedelta(seconds=resumo.tempo_processamento_s or 0)

    previsoes: dict[str, PrevisaoDaConta] = {}
    # A hora em que cada vaga abre; as que nenhuma conta ocupa já estão livres.
    abertura = [agora] * max(vagas - len(processando), 0)
    for conta in processando:
        inicio = conta.processando_desde or agora
        prevista = duracao(conta)
        # A conta que passou da Previsão ainda está na vaga: ela abre agora, não no passado.
        pronta = max(inicio + prevista, agora)
        demorando = agora - inicio > FATOR_DA_DEMORA * prevista
        previsoes[conta.id] = PrevisaoDaConta(None, inicio, pronta, demorando)
        abertura.append(pronta)
    for posicao, conta in enumerate(na_fila, start=1):
        abertura.sort()
        inicio = abertura.pop(0) if abertura else agora
        pronta = inicio + duracao(conta)
        previsoes[conta.id] = PrevisaoDaConta(posicao, inicio, pronta, False)
        abertura.append(pronta)
    fim = max((p.pronta for p in previsoes.values()), default=None)
    return previsoes, replace(resumo, fila_esvazia_em=fim)
