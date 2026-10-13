"""O Painel de Contas médicas (issue #1137, PRD #1128, ADR 0070).

Os agregados das Contas concluídas, por semana de segunda a domingo no fuso do
hospital. A semana de uma Conta é a do dia em que ela foi concluída
(`concluida_em`). A Conta que foi concluída e enviada de novo voltou para a
fila: sai do Painel até ser concluída outra vez.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.services.paginacao import ler_tudo

__all__ = ["montar_painel", "segunda_da_semana"]

FUSO_DO_HOSPITAL = ZoneInfo("America/Sao_Paulo")

# Quantas semanas as séries mostram, terminando na semana escolhida.
SEMANAS_NA_SERIE = 8

# As situações de quem foi concluída. Retorno também: foi concluída e a
# Validação devolveu uma Linha.
CONCLUIDAS = ("CONCLUIDA", "CONCLUIDA_COM_PENDENCIA", "RETORNO")

_CAMPOS_DA_CONTA = "id, atendimento_id, faturista_id, situacao, nota_entrada, concluida_em, custo_usd"


def segunda_da_semana(dia: date) -> date:
    return dia - timedelta(days=dia.weekday())


def _meia_noite(dia: date) -> str:
    return datetime.combine(dia, time(0), tzinfo=FUSO_DO_HOSPITAL).isoformat()


def _semana_da_conta(conta: dict) -> date:
    instante = datetime.fromisoformat(conta["concluida_em"]).astimezone(FUSO_DO_HOSPITAL)
    return segunda_da_semana(instante.date())


def _contas_concluidas(supabase, de: date, ate: date) -> list[dict]:
    """As Contas concluídas de `de` (segunda) até antes de `ate` (segunda)."""
    return ler_tudo(
        lambda: (
            supabase.table("cm_conta")
            .select(_CAMPOS_DA_CONTA)
            .in_("situacao", list(CONCLUIDAS))
            .gte("concluida_em", _meia_noite(de))
            .lt("concluida_em", _meia_noite(ate))
            .order("id")
        ),
        rotulo="contas do Painel",
    )


def _nota_media(contas: list[dict]) -> float | None:
    notas = [float(c["nota_entrada"]) for c in contas if c.get("nota_entrada") is not None]
    return round(sum(notas) / len(notas), 1) if notas else None


def montar_painel(supabase, *, semana: date) -> dict[str, Any]:
    segunda = segunda_da_semana(semana)
    primeira = segunda - timedelta(weeks=SEMANAS_NA_SERIE - 1)
    contas = _contas_concluidas(supabase, primeira, segunda + timedelta(weeks=1))

    por_semana: dict[date, list[dict]] = defaultdict(list)
    for conta in contas:
        por_semana[_semana_da_conta(conta)].append(conta)
    da_semana = por_semana[segunda]

    return {
        "semana": {"inicio": segunda.isoformat(), "fim": (segunda + timedelta(days=6)).isoformat()},
        "nota_media": {
            "semana": _nota_media(da_semana),
            "anterior": _nota_media(por_semana[segunda - timedelta(weeks=1)]),
        },
    }
