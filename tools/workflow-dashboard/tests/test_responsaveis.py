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


def test_fatia_sem_assignee_herda_o_dono_do_prd_pai():
    issues = [_issue(10, assignees=["bia"]), _issue(11), _issue(12, assignees=["ana"])]

    resultado = _agrupar(issues, fatias_por_prd={10: [11, 12]})

    grupos = _numeros_por_grupo(resultado)
    assert grupos["bia"] == [11, 10]
    assert grupos["ana"] == [12]


def test_sem_assignee_nem_dono_do_prd_cai_em_sem_responsavel_no_fim():
    issues = [_issue(10), _issue(11), _issue(20, assignees=["caio"]), _issue(30)]

    resultado = _agrupar(issues, fatias_por_prd={10: [11]})

    assert [g["responsavel"] for g in resultado["grupos"]] == ["caio", None]
    assert _numeros_por_grupo(resultado)[None] == [30, 11, 10]


def test_issue_com_dois_assignees_aparece_nos_dois_grupos():
    resultado = _agrupar([_issue(11, assignees=["bia", "ana"])])

    assert _numeros_por_grupo(resultado) == {"ana": [11], "bia": [11]}


def test_prd_com_dois_donos_leva_a_fatia_sem_assignee_aos_dois_grupos():
    issues = [_issue(10, assignees=["ana", "bia"]), _issue(11)]

    resultado = _agrupar(issues, fatias_por_prd={10: [11]})

    assert _numeros_por_grupo(resultado) == {"ana": [11, 10], "bia": [11, 10]}


def test_ordem_no_grupo_em_andamento_planejadas_demais_abertas_e_fechadas_recentes_primeiro():
    issues = [
        _issue(1, state="CLOSED", assignees=["ana"], closed_at="2026-09-20T10:00:00Z"),
        _issue(2, state="CLOSED", assignees=["ana"], closed_at="2026-09-01T10:00:00Z"),
        _issue(3, labels=["needs-triage"], assignees=["ana"]),
        _issue(4, labels=["ready-for-agent"], assignees=["ana"]),
        _issue(5, labels=["in-progress"], assignees=["ana"]),
        _issue(6, labels=["ready-for-human"], assignees=["ana"]),
        _issue(7, labels=["blocked"], assignees=["ana"]),
    ]

    itens = _agrupar(issues)["grupos"][0]["itens"]

    assert [(i["number"], i["secao"]) for i in itens] == [
        (5, "em_andamento"),
        (6, "planejada"),
        (4, "planejada"),
        (7, "aberta"),
        (3, "aberta"),
        (1, "fechada"),
        (2, "fechada"),
    ]
