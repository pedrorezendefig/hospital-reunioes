"""Os períodos da Central de Comando e o período anterior de cada um.

Porte de `src/lib/analytics/period.ts` do repositório antigo, com a mesma conta,
porque é ela que decide QUAIS dias entram no número: se a Central nova somasse
dias diferentes da antiga, os Visitantes não bateriam no "mesmo período".

Duas regras que parecem detalhe e não são:

- **Termina ontem.** O período atual são N dias completos terminando no dia
  anterior a hoje. O dia de hoje ainda está pela metade: contá-lo faria todo
  período parecer em queda de manhã.
- **No dia do hospital.** O "hoje" é a data em Brasília (`FUSO_DO_HOSPITAL`),
  o fuso da propriedade da GA4 e o mesmo com que a tela escreve o dia. A GA4
  recebe só a data (`YYYY-MM-DD`) e interpreta no fuso da propriedade. A Central
  antiga usava a data em UTC, e das 21h à meia-noite de Brasília isso punha no
  período o hoje de Brasília, ainda pela metade, com o número mudando às 21h
  (issue #857).

Regras puras: nenhuma função daqui fala com rede, banco ou relógio, exceto
`hoje_utc`, que é o relógio em si e fica isolado para os testes o fixarem.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Literal, get_args
from zoneinfo import ZoneInfo

Periodo = Literal["7d", "28d", "90d"]

# Na ordem do seletor da tela.
PERIODOS: tuple[Periodo, ...] = get_args(Periodo)

# O período de quando ninguém escolheu nenhum (e de quando escolheram um que
# não existe): o mesmo da Central antiga.
PERIODO_PADRAO: Periodo = "28d"

_DIAS: dict[Periodo, int] = {"7d": 7, "28d": 28, "90d": 90}

# O fuso do hospital, que é o da propriedade da GA4. Fixo no código, e não lido
# da GA4 a cada pedido: se um dia a propriedade mudar de fuso, muda aqui.
FUSO_DO_HOSPITAL = ZoneInfo("America/Sao_Paulo")


@dataclass(frozen=True)
class Intervalo:
    """Um intervalo de datas, inclusive nas duas pontas."""

    inicio: date
    fim: date

    def como_dict(self) -> dict[str, str]:
        """O intervalo como a tela e a GA4 leem: datas ISO (`YYYY-MM-DD`)."""
        return {"inicio": self.inicio.isoformat(), "fim": self.fim.isoformat()}


def hoje_utc(agora: datetime | None = None) -> date:
    """A data de hoje no hospital. O único relógio do módulo.

    O nome ficou do tempo em que o relógio era UTC: os chamadores e o relógio
    fixo dos testes chamam por ele. `agora` (com fuso) fixa o instante; sem
    ele, vale o relógio do servidor.
    """
    instante = agora if agora is not None else datetime.now(UTC)
    return instante.astimezone(FUSO_DO_HOSPITAL).date()


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
