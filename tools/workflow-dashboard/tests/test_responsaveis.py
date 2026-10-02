"""Testes do módulo responsaveis: o agrupamento por responsável do painel.

Comportamento externo apenas: issues, PRs, mapa PRD -> fatias e o history.json
(no shape do collect.py) entram, grupos por responsável saem. Sem rede, sem gh.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from responsaveis import agrupar_por_responsavel  # noqa: E402

AGORA = datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)


def _issue(number, *, state="OPEN", labels=(), assignees=(), closed_at=None):
    """Issue no shape que o collect.py entrega ao módulo."""
    return {
        "number": number,
        "title": f"Fatia #{number}",
        "state": state,
        "labels": list(labels),
        "assignees": list(assignees),
        "closed_at": closed_at,
        "url": f"https://github.com/x/y/issues/{number}",
    }


def _agrupar(issues, prs=(), fatias_por_prd=None, history=()):
    return agrupar_por_responsavel(list(issues), list(prs), fatias_por_prd or {}, list(history), agora=AGORA)


def _numeros_por_grupo(resultado):
    return {g["responsavel"]: [i["number"] for i in g["itens"]] for g in resultado["grupos"]}


def test_issue_com_assignee_entra_no_grupo_dele():
    resultado = _agrupar([_issue(11, assignees=["ana"])])

    assert _numeros_por_grupo(resultado) == {"ana": [11]}
