"""Fases do Hospital OS: em que pé está cada issue e cada PR (ADR 0062, decisões 4 a 7).

Função pura: issues, PRs, deploys do history.json e branches remotas (no shape
do collect.py) entram; fase por issue, fase por PR, timeline, ondas por PRD e
contagens do funil saem. Nada aqui consulta rede ou disco.
"""

from __future__ import annotations

from datetime import datetime, timezone


def montar_fases(issues: list[dict], prs: list[dict], deploys: list[dict], branches: list[str],
                 timelines: dict | None = None, agora: datetime | None = None) -> dict:
    abertas = {i["number"] for i in issues if i["state"] == "OPEN"}
    return {"issues": {i["number"]: {"fase": _fase_issue(i, abertas)} for i in issues}}


def _fase_issue(issue: dict, abertas: set[int]) -> str:
    """Régua da issue, na precedência da ADR 0062: a primeira regra que vale decide."""
    labels = set(issue["labels"])
    if "ready-for-human" in labels:
        return "humana"
    if issue["state"] != "OPEN":
        return "encerrada_sem_pr"
    if "blocked" in labels or any(b in abertas for b in issue["blocked_by"]):
        return "bloqueada"
    if "in-progress" in labels or issue["assignees"]:
        return "em_andamento"
    if "ready-for-agent" in labels:
        return "fila"
    return "triagem"
