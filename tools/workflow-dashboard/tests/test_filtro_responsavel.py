"""Aba Issues: filtro por um responsável e visor dele (troca o agrupar por responsável do #908).

Responsável é quem está designado (assignee); "sem responsável" pega as issues
sem ninguém designado. Com o filtro ligado, a lista filtra e um visor com as
contas da pessoa aparece abaixo dos cards gerais. O coletor traz todas as
issues, sem o teto de 200.

As funções do app.js rodam de verdade no Node (corpo extraído por contagem de
chaves, mesmo molde de test_front_plano_issues.py) com stubs mínimos.
"""

import json
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

DASH = Path(__file__).resolve().parents[1]
APP_JS = (DASH / "static" / "app.js").read_text(encoding="utf-8")
sys.path.insert(0, str(DASH))

pytestmark = pytest.mark.skipif(not shutil.which("node"), reason="node ausente")


def _bloco(i):
    j = APP_JS.index("{", i)
    depth = 0
    for k in range(j, len(APP_JS)):
        if APP_JS[k] == "{":
            depth += 1
        elif APP_JS[k] == "}":
            depth -= 1
            if depth == 0:
                return APP_JS[i:k + 1]
    raise AssertionError("bloco sem fechamento")


def _fn(nome):
    i = APP_JS.find(f"function {nome}(")
    assert i >= 0, f"app.js sem function {nome}"
    return _bloco(i)


def _const(nome):
    i = APP_JS.find(f"const {nome} =")
    assert i >= 0, f"app.js sem const {nome}"
    return APP_JS[i:APP_JS.index("\n", i)]


def _node(expr, issues, f_issues=None):
    """Avalia expr no Node com as funções reais do filtro e do visor."""
    fns = "\n".join([_const("SEM_RESP"), _fn("doResponsavel"), _fn("matchIssue"),
                     _fn("leadAvg"), _fn("visorResponsavelHtml")])
    prog = f"""
const esc = s => String(s);
const spanH = ms => Math.round(ms / 36e5) + 'h';
const S = {{ fIssues: {json.dumps(f_issues or {"state": "all", "label": "", "q": "", "resp": ""})} }};
const iss = {json.dumps(issues)};
let n = 0; const rv = () => `data-i="${{n++}}"`;
{fns}
console.log(JSON.stringify({expr}));
"""
    out = subprocess.run(["node", "-e", prog], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def _iss(n, state="OPEN", assignees=(), labels=(), dias_fechada=None):
    agora = datetime.now(timezone.utc)
    criada = agora - timedelta(days=60)
    fechada = agora - timedelta(days=dias_fechada) if dias_fechada is not None else None
    return {"number": n, "title": f"issue {n}", "state": state, "assignees": list(assignees),
            "labels": list(labels), "created_at": criada.isoformat(),
            "closed_at": fechada.isoformat() if fechada else None}


ISSUES = [
    _iss(1, assignees=["ana"], labels=["in-progress"]),
    _iss(2, assignees=["ana"], labels=["ready-for-agent"]),
    _iss(3, state="CLOSED", assignees=["ana"], dias_fechada=5),
    _iss(4, state="CLOSED", assignees=["ana", "bia"], dias_fechada=45),
    _iss(5, assignees=["bia"]),
    _iss(6),
    _iss(7, labels=["ready-for-agent"]),
    _iss(8, state="CLOSED", dias_fechada=2),
]


def _filtradas(resp, state="all"):
    f = {"state": state, "label": "", "q": "", "resp": resp}
    return _node("iss.filter(matchIssue).map(i => i.number)", ISSUES, f)


# ---------- filtro ----------


def test_sem_filtro_de_responsavel_mostra_todas():
    assert _filtradas("") == [1, 2, 3, 4, 5, 6, 7, 8]


def test_filtro_por_pessoa_mostra_so_as_designadas_a_ela():
    assert _filtradas("ana") == [1, 2, 3, 4]
    assert _filtradas("bia") == [4, 5]


def test_sem_responsavel_mostra_so_as_sem_ninguem_designado():
    sem = _node("SEM_RESP", [])
    assert _filtradas(sem) == [6, 7, 8]
    assert _filtradas(sem, state="OPEN") == [6, 7]


def test_filtro_de_responsavel_soma_com_o_de_estado():
    assert _filtradas("ana", state="OPEN") == [1, 2]


# ---------- visor ----------


def _visor(resp):
    return _node(f"visorResponsavelHtml(iss, {json.dumps(resp)}, rv)", ISSUES)


def _card(html, k):
    """Valor e subtítulo do card de rótulo k no visor."""
    i = html.index(f'<div class="k">{k}</div>')
    v = html[html.index('">', html.index('class="v"', i)) + 2:]
    s = html[html.index('class="s">', i) + len('class="s">'):]
    return v[:v.index("<")], s[:s.index("<")]


def test_visor_da_pessoa_conta_abertas_entregues_e_fila_so_dela():
    html = _visor("ana")
    assert "ana · 4 issues" in html
    assert _card(html, "abertas") == ("2", "1 em andamento")
    assert _card(html, "entregues") == ("2", "1 nos últimos 30 dias")
    assert _card(html, "prontas p/ agente") == ("1", "fila ready-for-agent")


def test_visor_sem_responsavel_conta_as_sem_ninguem_designado():
    html = _visor(_node("SEM_RESP", []))
    assert "sem responsável · 3 issues" in html
    assert _card(html, "abertas") == ("2", "0 em andamento")
    assert _card(html, "entregues") == ("1", "1 nos últimos 30 dias")
    assert _card(html, "prontas p/ agente") == ("1", "fila ready-for-agent")


def test_visor_so_aparece_com_o_filtro_ligado():
    corpo = _fn("renderIssues")
    assert "${f.resp ? visorResponsavelHtml(iss, f.resp, rv) : ''}" in corpo
    assert 'data-act="fagrupar"' not in APP_JS


def test_select_de_responsavel_lista_todos_sem_responsavel_e_as_pessoas_designadas():
    corpo = _fn("renderIssues")
    assert 'id="fresp"' in corpo
    assert "const pessoas = [...new Set(iss.flatMap(i => i.assignees))].sort();" in corpo
    assert "responsável: todos" in corpo and "sem responsável" in corpo


# ---------- coletor ----------


def test_coletor_traz_issues_e_prs_sem_o_teto_de_200(monkeypatch):
    import collect

    chamadas = []

    def fake_run(cmd, cwd, timeout=None):
        chamadas.append(cmd)
        return "[]"

    monkeypatch.setattr(collect, "_run", fake_run)
    collect._gh_issues(DASH)
    collect._gh_prs(DASH)
    limites = [int(c[c.index("--limit") + 1]) for c in chamadas]
    assert len(limites) == 2
    assert all(n >= 10000 for n in limites), limites
