"""Aba Issues: filtro por um responsável e visor dele (troca o agrupar por responsável do #908).

Responsável é quem está designado (assignee); sem ninguém designado, cai em quem
criou a issue (author), emenda de 05/10/2026 do ADR 0061. "ninguém assumiu"
filtra as issues sem assignee, que seguem sendo a fila sem claim. O visor da
pessoa separa as assumidas das só criadas, e o "em andamento" conta só issue com
assignee. Com o filtro ligado, a lista filtra e um visor com as contas da pessoa
aparece abaixo dos cards gerais. O coletor traz todas as issues, sem o teto de 200.

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
    """Avalia expr no Node com as funções reais do filtro, do visor e do cartão."""
    fns = "\n".join([_const("SEM_RESP"), _fn("responsaveis"), _fn("doResponsavel"), _fn("matchIssue"),
                     _fn("leadAvg"), _fn("visorResponsavelHtml"), _fn("donoHtml"), _fn("issueCard")])
    prog = f"""
const esc = s => String(s);
const spanH = ms => Math.round(ms / 36e5) + 'h';
const fmtD = s => String(s).slice(0, 10);
const labelBadge = () => '', stateTag = () => '', chainHtml = () => '', commentsHtml = () => '';
const md = s => s, issUrl = n => `#${{n}}`;
const S = {{ fIssues: {json.dumps(f_issues or {"state": "all", "label": "", "q": "", "resp": ""})}, expIss: new Set() }};
const iss = {json.dumps(issues)};
let n = 0; const rv = () => `data-i="${{n++}}"`;
{fns}
console.log(JSON.stringify({expr}));
"""
    out = subprocess.run(["node", "-e", prog], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def _iss(n, state="OPEN", assignees=(), labels=(), dias_fechada=None, author=None):
    agora = datetime.now(timezone.utc)
    criada = agora - timedelta(days=60)
    fechada = agora - timedelta(days=dias_fechada) if dias_fechada is not None else None
    return {"number": n, "title": f"issue {n}", "state": state, "assignees": list(assignees),
            "author": author, "labels": list(labels), "created_at": criada.isoformat(),
            "closed_at": fechada.isoformat() if fechada else None,
            "blocked_by": [], "criteria": {"done": 0, "total": 0}}


ISSUES = [
    _iss(1, assignees=["ana"], labels=["in-progress"], author="bia"),
    _iss(2, assignees=["ana"], labels=["ready-for-agent"], author="ana"),
    _iss(3, state="CLOSED", assignees=["ana"], dias_fechada=5),
    _iss(4, state="CLOSED", assignees=["ana", "bia"], dias_fechada=45),
    _iss(5, assignees=["bia"]),
    _iss(6, author="ana"),
    _iss(7, labels=["ready-for-agent"], author="bia"),
    _iss(8, state="CLOSED", dias_fechada=2),
    _iss(9, labels=["ready-for-agent"]),
    # claim interrompido: label in-progress sem ninguém designado
    _iss(10, labels=["in-progress"], author="ana"),
]


def _filtradas(resp, state="all"):
    f = {"state": state, "label": "", "q": "", "resp": resp}
    return _node("iss.filter(matchIssue).map(i => i.number)", ISSUES, f)


SEM = '(sem)'


def test_sem_resp_e_o_valor_do_select():
    assert _node("SEM_RESP", []) == SEM


# ---------- filtro ----------


def test_sem_filtro_de_responsavel_mostra_todas():
    assert _filtradas("") == list(range(1, 11))


def test_filtro_por_pessoa_pega_as_designadas_e_as_sem_designado_que_ela_criou():
    # 1 foi criada pela bia mas está com a ana: quem assumiu manda sobre quem criou
    assert _filtradas("ana") == [1, 2, 3, 4, 6, 10]
    assert _filtradas("bia") == [4, 5, 7]


def test_ninguem_assumiu_mostra_as_sem_designado_mesmo_com_autor():
    assert _filtradas(SEM) == [6, 7, 8, 9, 10]
    assert _filtradas(SEM, state="OPEN") == [6, 7, 9, 10]


def test_filtro_de_responsavel_soma_com_o_de_estado():
    assert _filtradas("ana", state="OPEN") == [1, 2, 6, 10]


def test_responsaveis_e_o_assignee_senao_o_autor():
    assert _node("responsaveis(iss[0])", ISSUES) == ["ana"]
    assert _node("responsaveis(iss[5])", ISSUES) == ["ana"]
    assert _node("responsaveis(iss[7])", ISSUES) == []


# ---------- visor ----------


def _visor(resp):
    return _node(f"visorResponsavelHtml(iss, {json.dumps(resp)}, rv)", ISSUES)


def _card(html, k):
    """Valor e subtítulo do card de rótulo k no visor."""
    i = html.index(f'<div class="k">{k}</div>')
    v = html[html.index('">', html.index('class="v"', i)) + 2:]
    s = html[html.index('class="s">', i) + len('class="s">'):]
    return v[:v.index("<")], s[:s.index("<")]


def test_visor_da_pessoa_separa_assumidas_de_so_criadas():
    html = _visor("ana")
    assert "ana · 6 issues · 4 assumidas · 2 só criadas" in html
    assert _card(html, "abertas") == ("4", "1 em andamento")
    assert _card(html, "entregues") == ("2", "1 nos últimos 30 dias")
    assert _card(html, "prontas p/ agente") == ("1", "fila ready-for-agent")


def test_visor_ninguem_assumiu_conta_as_sem_designado():
    html = _visor(SEM)
    assert "ninguém assumiu · 5 issues" in html
    assert "assumidas" not in html
    assert _card(html, "abertas") == ("4", "0 em andamento")
    assert _card(html, "entregues") == ("1", "1 nos últimos 30 dias")
    assert _card(html, "prontas p/ agente") == ("2", "fila ready-for-agent")


def test_visor_so_aparece_com_o_filtro_ligado():
    corpo = _fn("renderIssues")
    assert "${f.resp ? visorResponsavelHtml(iss, f.resp, rv) : ''}" in corpo
    assert 'data-act="fagrupar"' not in APP_JS


def test_select_de_responsavel_lista_todos_ninguem_assumiu_e_as_pessoas():
    corpo = _fn("renderIssues")
    assert 'id="fresp"' in corpo
    assert "const pessoas = [...new Set(iss.flatMap(responsaveis))].sort();" in corpo
    assert "responsável: todos" in corpo and ">ninguém assumiu</option>" in corpo


# ---------- cartão ----------


def _cartao(i, prd=False):
    return _node(f"issueCard(iss[0], 0, {json.dumps(prd)})", [i])


def test_cartao_distingue_quem_assumiu_de_quem_criou():
    assumida = _cartao(ISSUES[0])
    assert "<span>👤 ana</span>" in assumida and "criada por" not in assumida
    assert "<span>✎ criada por ana</span>" in _cartao(ISSUES[5])
    assert "👤" not in _cartao(ISSUES[8]) and "criada por" not in _cartao(ISSUES[8])


def test_prd_sem_assignee_mostra_sem_dono_e_quem_criou():
    assert '<span class="prd-dono">👤 ana</span>' in _cartao(ISSUES[0], prd=True)
    assert '<span class="prd-dono">sem dono · ✎ criada por ana</span>' in _cartao(ISSUES[5], prd=True)
    assert '<span class="prd-dono">sem dono</span>' in _cartao(ISSUES[8], prd=True)


# ---------- coletor ----------


def test_coletor_traz_o_autor_da_issue(monkeypatch):
    import collect

    item = {"number": 1, "title": "t", "state": "OPEN", "labels": [], "assignees": [],
            "author": {"login": "fulano"}, "body": ""}
    monkeypatch.setattr(collect, "_run", lambda cmd, cwd, timeout=None: json.dumps([item]))
    assert "author" in collect.ISSUE_FIELDS.split(",")
    assert collect._gh_issues(DASH)[0]["author"] == "fulano"


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
