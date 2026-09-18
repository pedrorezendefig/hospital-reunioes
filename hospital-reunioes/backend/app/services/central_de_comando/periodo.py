"""Os períodos da Central de Comando e o período anterior de cada um.

Porte de `src/lib/analytics/period.ts` do repositório antigo, com a mesma conta,
porque é ela que decide QUAIS dias entram no número: se a Central nova somasse
dias diferentes da antiga, os Visitantes não bateriam no "mesmo período".

Duas regras que parecem detalhe e não são:

- **Termina ontem.** O período atual são N dias completos terminando no dia
  anterior a hoje. O dia de hoje ainda está pela metade: contá-lo faria todo
  período parecer em queda de manhã.
- **Em UTC.** O "hoje" é a data em UTC, como na Central antiga. A GA4 recebe só
  a data (`YYYY-MM-DD`) e interpreta no fuso da propriedade; o que importa aqui
  é escolher os MESMOS dias que a antiga escolhia.

Regras puras: nenhuma função daqui fala com rede, banco ou relógio, exceto
`hoje_utc`, que é o relógio em si e fica isolado para os testes o fixarem.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Literal, get_args

Periodo = Literal["7d", "28d", "90d"]

# Na ordem do seletor da tela.
PERIODOS: tuple[Periodo, ...] = get_args(Periodo)

# O período de quando ninguém escolheu nenhum (e de quando escolheram um que
# não existe): o mesmo da Central antiga.
PERIODO_PADRAO: Periodo = "28d"

_DIAS: dict[Periodo, int] = {"7d": 7, "28d": 28, "90d": 90}


@dataclass(frozen=True)
class Intervalo:
    """Um intervalo de datas, inclusive nas duas pontas."""

    inicio: date
    fim: date

    def como_dict(self) -> dict[str, str]:
        """O intervalo como a tela e a GA4 leem: datas ISO (`YYYY-MM-DD`)."""
        return {"inicio": self.inicio.isoformat(), "fim": self.fim.isoformat()}


def hoje_utc() -> date:
    """A data de hoje em UTC. O único relógio do módulo."""
    return datetime.now(UTC).date()


def ler_periodo(valor: str | None, permitidos: tuple[Periodo, ...] = PERIODOS) -> Periodo:
    """Lê o período pedido. Ausente, inválido ou fora de `permitidos` vira o
    padrão: quem digita um período que não existe vê o de 28 dias, não um erro.

    `permitidos` existe para o Instagram, que não tem 90 dias.
    """
    if valor in permitidos:
        return valor  # type: ignore[return-value]
    return PERIODO_PADRAO


def dias_do_periodo(periodo: Periodo) -> int:
    return _DIAS[periodo]


def intervalo_atual(periodo: Periodo, hoje: date) -> Intervalo:
    """Os N dias completos terminando ontem."""
    fim = hoje - timedelta(days=1)
    inicio = fim - timedelta(days=dias_do_periodo(periodo) - 1)
    return Intervalo(inicio=inicio, fim=fim)


def intervalo_anterior(periodo: Periodo, hoje: date) -> Intervalo:
    """O bloco de mesmo tamanho imediatamente antes do atual, sem buraco nem
    sobreposição: é a base do "em relação ao período anterior"."""
    fim = intervalo_atual(periodo, hoje).inicio - timedelta(days=1)
    inicio = fim - timedelta(days=dias_do_periodo(periodo) - 1)
    return Intervalo(inicio=inicio, fim=fim)


def dias_do_intervalo(intervalo: Intervalo) -> list[date]:
    """Cada dia do intervalo, inclusive nas pontas. É o eixo de uma série por
    dia: o dia sem dado entra, com zero, em vez de sumir do gráfico."""
    total = (intervalo.fim - intervalo.inicio).days + 1
    return [intervalo.inicio + timedelta(days=i) for i in range(total)]
