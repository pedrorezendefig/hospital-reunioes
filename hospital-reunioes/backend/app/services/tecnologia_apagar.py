"""Apagar a Demanda (issue #1549, PRD #1548, ADR 0084, decisao 2).

A Demanda que nao vale mais sai do app e vira lapide: a linha fica, com
`apagada_em` e `apagada_por`, para o webhook reconhecer a issue e nao recria-la.
Quem pode apagar e a regra pura `tecnologia.recusa_de_apagar`; aqui mora o que
o Apagar faz.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.services.tecnologia import TABELA_DEMANDAS


def apagar(supabase, demanda: dict[str, Any], *, ator: dict[str, Any]) -> None:
    """Faz da Demanda uma lapide. Recebe as guardas da rota ja passadas."""
    supabase.table(TABELA_DEMANDAS).update(
        {"apagada_em": datetime.now(UTC).isoformat(), "apagada_por": ator["id"]}
    ).eq("id", str(demanda["id"])).execute()
