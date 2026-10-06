"""Desenho das ondas no card do PRD (issue #943, ADR 0062, decisão 3).

Dentro do card de cada PRD aberto da aba Issues: colunas = ondas do payload
`fases`, nós = fatias na cor do responsável (assignee), borda = fase, setas =
`blocked_by` aberto dentro do PRD. Clicar num nó abre o card da fatia na lista.

O payload das fases sai do `fases.montar_fases` de verdade sobre as issues do
teste; o app.js roda inteiro no Node com o DOM de mentira do test_aba_issues.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

DASH = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DASH))

from fases import montar_fases  # noqa: E402
from test_aba_issues import PRELUDIO, _modulo_app, com_node  # noqa: E402


def _iss(n, *, state="OPEN", assignees=(), labels=(), blocked_by=(), parent=None, children=()):
    return {
        "number": n,
        "title": f"Hospital OS: fatia {n}",
        "state": state,
        "labels": list(labels),
        "assignees": list(assignees),
        "author": "ana",
        "url": f"https://github.com/x/y/issues/{n}",
        "body": f"corpo da {n}",
        "created_at": "2026-10-01T10:00:00Z",
        "closed_at": "2026-10-03T18:00:00Z" if state == "CLOSED" else None,
        "blocked_by": list(blocked_by),
        "parent": parent,
        "children": list(children),
        "is_prd": bool(children),
        "criteria": {"done": 0, "total": 0},
        "prs": [],
        "deploys": [],
    }


# PRD 950 com três ondas:
#   onda 1: 951, 952 (sem dependência), 955 (fechada), 956 (a bloqueadora 955 fechou),
#           957 (bloqueada por 999, de fora do PRD)
#   onda 2: 953 (espera 951)
#   onda 3: 954 (espera 952 e 953)
# PRD 960 aberto sem fatias; PRD 970 fechado com fatia.
ISSUES = [
    _iss(950, assignees=["pedrorezendefig"], children=range(951, 958)),
    _iss(951, assignees=["pedrorezendefig"], labels=["in-progress"], parent=950),
    _iss(952, labels=["ready-for-agent"], parent=950),
    _iss(953, assignees=["lucassampaioc1"], blocked_by=[951], parent=950),
    _iss(954, assignees=["pedroribbe"], blocked_by=[952, 953], parent=950),
    _iss(955, state="CLOSED", assignees=["pedrorezendefig"], parent=950),
    _iss(956, labels=["ready-for-agent"], blocked_by=[955], parent=950),
    _iss(957, labels=["ready-for-agent"], blocked_by=[999], parent=950),
    _iss(960, labels=["needs-triage"]),
    _iss(970, state="CLOSED", children=[971]),
    _iss(971, state="CLOSED", parent=970),
    _iss(999, labels=["ready-for-agent"]),
]
PRD = 950
FATIAS = list(range(951, 958))


def _dados():
    fases = montar_fases(ISSUES, [], [], [])
    return json.loads(
        json.dumps(
            {
                "generated_at": "2026-10-06T10:00:00Z",
                "repo_url": "https://github.com/x/y",
                "repo_slug": "x/y",
                "github": {"error": None, "error_kind": None, "issues": ISSUES, "prs": [], "prds": [950, 960, 970]},
                "fases": fases,
                "history": [],
                "state": {},
                "snapshots": [],
                "adrs": [],
            }
        )
    )


DADOS = _dados()


def _rodar(tmp_path, expr, antes=""):
    prog = PRELUDIO + _modulo_app() + f"\nS.data = {json.dumps(DADOS)};\n{antes}\n"
    prog += f"console.log('@@' + JSON.stringify({expr}));\n"
    arq = tmp_path / "harness.mjs"
    arq.write_text(prog, encoding="utf-8")
    out = subprocess.run(
        ["node", str(arq)], capture_output=True, text=True, check=False, env={**os.environ, "TZ": "UTC"}
    )
    assert out.returncode == 0, out.stderr
    linha = [x for x in out.stdout.splitlines() if x.startswith("@@")][-1]
    return json.loads(linha[2:])


def _card(n):
    return f"issueCard(S.data.github.issues.find(i => i.number === {n}), 0, true)"


def _svg(html):
    m = re.search(r"<svg class=\"onda-svg[^\"]*\".*?</svg>", html, re.S)
    return m.group(0) if m else None


# ---------- quem desenha ----------


@com_node
def test_prd_aberto_com_fatias_mostra_o_desenho_e_sem_fatias_ou_fechado_nao(tmp_path):
    com_fatias, sem_fatias, fechado = _rodar(tmp_path, f"[{_card(950)}, {_card(960)}, {_card(970)}]")
    assert _svg(com_fatias)
    assert not _svg(sem_fatias)
    assert not _svg(fechado)
