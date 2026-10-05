"""Fases do Hospital OS: em que pé está cada issue e cada PR (ADR 0062, decisões 4 a 7).

Função pura: issues, PRs, deploys do history.json e branches remotas (no shape
do collect.py) entram; fase por issue, fase por PR, timeline, ondas por PRD e
contagens do funil saem. Nada aqui consulta rede ou disco.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone


def montar_fases(issues: list[dict], prs: list[dict], deploys: list[dict], branches: list[str],
                 timelines: dict | None = None, agora: datetime | None = None) -> dict:
    abertas = {i["number"] for i in issues if i["state"] == "OPEN"}
    producao = _Producao(deploys)
    prs_por_issue: dict[int, list[dict]] = {}
    for p in prs:
        for n in p["closes"]:
            prs_por_issue.setdefault(n, []).append(p)
    return {"issues": {i["number"]: _fase_issue(i, prs_por_issue.get(i["number"], []), abertas, producao)
                       for i in issues}}


def _dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


class _Producao:
    """Em que deploy do history.json cada PR subiu.

    O rabo escreve os PRs no texto do deploy ("PR #896", "PRs #874 #875 #876");
    número de issue e de PR não colidem no GitHub, então basta o PR ser citado.
    """

    def __init__(self, deploys: list[dict]):
        self.deploys = []
        for d in deploys:
            if d.get("result", "healthy") != "healthy" or not _dt(d.get("at")):
                continue
            texto = " ".join(str(d.get(k) or "") for k in ("subject", "raw_subject", "notes"))
            citados = {int(n) for n in re.findall(r"#(\d+)", texto)} | set(d.get("pr_numbers") or [])
            self.deploys.append((_dt(d["at"]), d, citados))
        self.deploys.sort(key=lambda t: t[0])

    def do_pr(self, pr: dict) -> dict | None:
        """Primeiro deploy que cita o PR mergeado: a versão em que ele entrou em produção."""
        if pr["state"] != "MERGED":
            return None
        for _, d, citados in self.deploys:
            if pr["number"] in citados:
                return d
        return None


def _fase_issue(issue: dict, prs: list[dict], abertas: set[int], producao: _Producao) -> dict:
    """Régua da issue, na precedência da ADR 0062: a primeira regra que vale decide."""
    labels = set(issue["labels"])
    mergeados = [p for p in prs if p["state"] == "MERGED"]
    abertos = [p for p in prs if p["state"] == "OPEN"]
    out = {"fase": None, "pr": None, "versao": None, "em_producao_em": None}
    if "ready-for-human" in labels:
        out["fase"] = "humana"
    elif issue["state"] != "OPEN" and not mergeados:
        out["fase"] = "encerrada_sem_pr"
    elif mergeados:
        deploys = [d for d in (producao.do_pr(p) for p in mergeados) if d]
        out["pr"] = mergeados[-1]["number"]
        if deploys:
            primeiro = min(deploys, key=lambda d: _dt(d["at"]))
            out.update(fase="em_producao", versao=primeiro.get("app_version"), em_producao_em=primeiro["at"])
        else:
            out["fase"] = "mergeada"
    elif abertos:
        out.update(fase="pr_aberto", pr=abertos[-1]["number"])
    elif "blocked" in labels or any(b in abertas for b in issue["blocked_by"]):
        out["fase"] = "bloqueada"
    elif "in-progress" in labels or issue["assignees"]:
        out["fase"] = "em_andamento"
    elif "ready-for-agent" in labels:
        out["fase"] = "fila"
    else:
        out["fase"] = "triagem"
    return out
