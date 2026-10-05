"""Testes do módulo fases: a régua de nove fases da issue e as seis do PR (ADR 0062).

Comportamento externo apenas: issues, PRs, deploys do history.json e branches
remotas (no shape do collect.py) entram; fase por issue, fase por PR, timeline,
ondas por PRD e contagens do funil saem. Sem rede, sem gh, sem filesystem.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fases import montar_fases  # noqa: E402

AGORA = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)


def _issue(
    number,
    *,
    state="OPEN",
    labels=(),
    assignees=(),
    author="ana",
    blocked_by=(),
    children=(),
    is_prd=False,
    created_at="2026-10-01T10:00:00Z",
    closed_at=None,
):
    """Issue no shape que o collect.py entrega ao módulo."""
    return {
        "number": number,
        "title": f"Fatia #{number}",
        "state": state,
        "labels": list(labels),
        "assignees": list(assignees),
        "author": author,
        "blocked_by": sorted(blocked_by),
        "children": sorted(children),
        "is_prd": is_prd,
        "created_at": created_at,
        "closed_at": closed_at,
    }


def _fase(issue, *, outras=(), prs=(), deploys=(), branches=()):
    fases = montar_fases([issue, *outras], list(prs), list(deploys), list(branches), agora=AGORA)
    return fases["issues"][issue["number"]]


# ---------- fase da issue: um caso positivo por fase ----------


def test_needs_triage_fica_em_triagem():
    assert _fase(_issue(1, labels=["needs-triage"]))["fase"] == "triagem"


def test_ready_for_agent_sem_dono_e_sem_bloqueio_fica_na_fila():
    assert _fase(_issue(2, labels=["ready-for-agent"]))["fase"] == "fila"


def test_issue_com_claim_fica_em_andamento():
    issue = _issue(3, labels=["in-progress"], assignees=["bia"])
    assert _fase(issue)["fase"] == "em_andamento"


def test_bloqueadora_aberta_deixa_a_issue_bloqueada():
    issue = _issue(4, labels=["ready-for-agent"], blocked_by=[5])
    assert _fase(issue, outras=[_issue(5, labels=["ready-for-agent"])])["fase"] == "bloqueada"


def test_ready_for_human_fica_na_fase_humana():
    assert _fase(_issue(6, labels=["ready-for-human"]))["fase"] == "humana"


def test_fechada_sem_pr_fica_encerrada_sem_pr():
    issue = _issue(7, state="CLOSED", labels=["wontfix"], closed_at="2026-10-02T10:00:00Z")
    assert _fase(issue)["fase"] == "encerrada_sem_pr"
