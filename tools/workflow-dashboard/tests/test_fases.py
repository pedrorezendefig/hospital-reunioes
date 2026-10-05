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


def _pr(
    number,
    closes,
    *,
    state="OPEN",
    created_at="2026-10-03T10:00:00Z",
    closed_at=None,
    merged_at=None,
    head_ref=None,
    author="bia",
    checks=(),
    merge_state=None,
    reviews=(),
    vereditos=(),
):
    """PR no shape que o collect.py entrega (checks e veredito só nos abertos)."""
    return {
        "number": number,
        "title": f"PR #{number}",
        "state": state,
        "created_at": created_at,
        "closed_at": closed_at,
        "merged_at": merged_at,
        "head_ref": head_ref or f"feat/x-{closes[0] if closes else number}",
        "author": author,
        "is_draft": False,
        "url": f"https://github.com/x/y/pull/{number}",
        "closes": list(closes),
        "checks": list(checks),
        "merge_state": merge_state,
        "reviews": list(reviews),
        "comentarios": len(vereditos),
        "vereditos": list(vereditos),
    }


def _check(conclusao="SUCCESS", *, status="COMPLETED", inicio="2026-10-03T10:05:00Z", fim="2026-10-03T10:20:00Z"):
    return {"nome": "CI", "status": status, "conclusao": conclusao, "inicio": inicio,
            "fim": fim if status == "COMPLETED" else None}


def _deploy(versao, at, texto):
    """Deploy no shape do history.json; o texto cita PRs e issues como o rabo escreve."""
    return {"app_version": versao, "at": at, "result": "healthy", "subject": texto,
            "raw_subject": "chore(deploy): registro", "notes": ""}


def _merged(number, closes, merged_at="2026-10-04T10:00:00Z"):
    return _pr(number, closes, state="MERGED", merged_at=merged_at, closed_at=merged_at)


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


def test_pr_aberto_que_fecha_a_issue_poe_a_issue_em_pr_aberto():
    issue = _issue(8, labels=["in-progress"], assignees=["bia"])
    fase = _fase(issue, prs=[_pr(108, [8])])
    assert fase["fase"] == "pr_aberto"
    assert fase["pr"] == 108


def test_pr_mergeado_com_versao_no_history_poe_a_issue_em_producao():
    issue = _issue(9, state="CLOSED", closed_at="2026-10-04T10:00:00Z")
    deploys = [_deploy("0.162.0", "2026-10-04T10:20:00-03:00", "PR #109, issue #9: algo")]
    fase = _fase(issue, prs=[_merged(109, [9])], deploys=deploys)
    assert fase["fase"] == "em_producao"
    assert fase["versao"] == "0.162.0"
    assert fase["em_producao_em"] == "2026-10-04T10:20:00-03:00"


def test_mergeada_sem_versao_no_history_fica_mergeada():
    issue = _issue(10, state="CLOSED", closed_at="2026-10-04T10:00:00Z")
    outro = [_deploy("0.161.0", "2026-10-03T09:00:00-03:00", "PR #50, issue #40: antes do merge")]
    fase = _fase(issue, prs=[_merged(110, [10])], deploys=outro)
    assert fase["fase"] == "mergeada"
    assert fase["versao"] is None
