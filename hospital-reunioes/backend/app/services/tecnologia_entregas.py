"""As Entregas da Tecnologia (issue #1556, PRD #1548, ADR 0084, decisao 8).

Regras puras, sem I/O: o router le as Demandas e passa por aqui. Conta por
card, nunca por parte. Entregue e a Demanda com a data de entrega que o
Documento do card mostra (`entregue_na_data`: o fechamento da issue-raiz, so
com a Etapa Entregue ou Em producao). O dia e o do hospital, em Sao Paulo: o
card fechado as 22h de domingo e do domingo, e nao da segunda em UTC.
"""

from __future__ import annotations

from collections import Counter
from datetime import date, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

from app.services.tecnologia import (
    entregue_na_data,
    instante_do_banco,
    login_do_responsavel,
    responsavel_da_demanda,
)

FUSO_DO_HOSPITAL = ZoneInfo("America/Sao_Paulo")

Agrupamento = Literal["semana", "mes"]


def dia_da_entrega(demanda: dict[str, Any]) -> date | None:
    """O dia do hospital em que o card foi entregue, ou `None` se nao foi."""
    instante = instante_do_banco(entregue_na_data(demanda))
    return instante.astimezone(FUSO_DO_HOSPITAL).date() if instante else None


def chave_do_responsavel(demanda: dict[str, Any]) -> str | None:
    """O valor do filtro Responsavel: o id do usuario, ou o login do dono no
    GitHub quando ele nao e usuario do app (issue #1534)."""
    return responsavel_da_demanda(demanda) or login_do_responsavel(demanda)


def inicio_do_periodo(dia: date, agrupar: Agrupamento) -> date:
    """A segunda-feira da semana, ou o dia 1 do mes."""
    if agrupar == "mes":
        return dia.replace(day=1)
    return dia - timedelta(days=dia.weekday())


def contagem(dias: list[date], agrupar: Agrupamento) -> list[dict[str, Any]]:
    """Quantos cards por periodo, do mais recente para o mais antigo. Periodo
    sem entrega nao aparece."""
    contados = Counter(inicio_do_periodo(dia, agrupar) for dia in dias)
    return [{"inicio": inicio.isoformat(), "total": total} for inicio, total in sorted(contados.items(), reverse=True)]
