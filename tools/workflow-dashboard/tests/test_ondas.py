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
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

DASH = Path(__file__).resolve().parents[1]
CSS = (DASH / "static" / "style.css").read_text(encoding="utf-8")
sys.path.insert(0, str(DASH))

from fases import FASES_ISSUE, montar_fases  # noqa: E402
from test_aba_issues import PRELUDIO, _modulo_app, com_node  # noqa: E402
from test_reskin_mapa import _cores_fixas  # noqa: E402


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


def _nos(svg):
    """{fatia: (coluna, classes, style)} de cada nó do desenho."""
    nos = {}
    for tag in re.findall(r"<g class=\"onda-no[^>]*>", svg):
        n = int(re.search(r'data-n="(\d+)"', tag).group(1))
        col = int(re.search(r'data-col="(\d+)"', tag).group(1))
        classes = re.search(r'class="([^"]*)"', tag).group(1).split()
        style = re.search(r'style="([^"]*)"', tag).group(1)
        nos[n] = (col, classes, style)
    return nos


def _setas(svg):
    return {(int(a), int(b)) for a, b in re.findall(r'class="onda-seta" data-de="(\d+)" data-para="(\d+)"', svg)}


# ---------- nós, bordas e setas ----------


@com_node
def test_tres_ondas_e_fatia_sem_dependencia_na_primeira_coluna(tmp_path):
    svg = _svg(_rodar(tmp_path, _card(PRD)))
    colunas = {n: c for n, (c, _, _) in _nos(svg).items()}
    assert colunas == {951: 0, 952: 0, 955: 0, 956: 0, 957: 0, 953: 1, 954: 2}
    assert re.findall(r'class="onda-col"[^>]*>([^<]+)<', svg) == ["onda 1", "onda 2", "onda 3"]


@com_node
def test_no_na_cor_de_quem_assumiu_e_ninguem_assumiu_na_cor_sem_dono(tmp_path):
    html, cores = _rodar(
        tmp_path,
        f"[{_card(PRD)}, ['pedrorezendefig', 'lucassampaioc1', 'pedroribbe', null].map(corDaPessoa)]",
    )
    pedro, lucas, rib, ninguem = cores
    nos = _nos(_svg(html))
    pessoa = {n: re.search(r"--pessoa:([^;]+)", s).group(1) for n, (_, _, s) in nos.items()}
    assert pessoa == {951: pedro, 952: ninguem, 953: lucas, 954: rib, 955: pedro, 956: ninguem, 957: ninguem}
    assert re.search(r"\.onda-corpo\{[^}]*fill:var\(--pessoa\)", CSS)


@com_node
def test_borda_do_no_segue_a_fase_do_payload(tmp_path):
    nos = _nos(_svg(_rodar(tmp_path, _card(PRD))))
    fase = {n: [c for c in classes if c.startswith("onda-f-")] for n, (_, classes, _) in nos.items()}
    assert fase == {
        951: ["onda-f-em_andamento"],
        952: ["onda-f-fila"],
        953: ["onda-f-bloqueada"],
        954: ["onda-f-bloqueada"],
        955: ["onda-f-encerrada_sem_pr"],
        956: ["onda-f-fila"],
        957: ["onda-f-bloqueada"],
    }
    cores = {}
    for f in FASES_ISSUE:
        m = re.search(rf"\.onda-f-{f}\{{--fase:(var\(--[\w-]+\))\}}", CSS)
        assert m, f"fase {f} sem cor de borda"
        cores[f] = m.group(1)
    assert cores["bloqueada"] != cores["fila"] != cores["em_andamento"]
    assert re.search(r"\.onda-anel\{[^}]*stroke:var\(--fase\)", CSS)


@com_node
def test_setas_seguem_so_o_blocked_by_aberto_dentro_do_prd(tmp_path):
    # 955 -> 956: bloqueadora fechada; 999 -> 957: bloqueadora de fora do PRD
    assert _setas(_svg(_rodar(tmp_path, _card(PRD)))) == {(951, 953), (952, 954), (953, 954)}


# ---------- clique no nó ----------


def _fatias_abertas(html):
    """Fatias com o card aberto dentro do grupo expandido de um PRD."""
    filhos = html.split('<div class="children">', 1)
    if len(filhos) < 2:
        return []
    cards = re.split(r'<article class="nrow', filhos[1])[1:]
    return [int(re.search(r'data-act="iss" data-n="(\d+)"', c).group(1)) for c in cards if 'class="iss-body"' in c]


@com_node
def test_clicar_num_no_abre_o_card_da_fatia_na_lista(tmp_path):
    antes = "_clicar({ act: 'onda', n: '953', prd: '950' });"
    html, buscas = _rodar(tmp_path, "[issueListHtml(), _buscas]", antes=antes)
    assert _fatias_abertas(html) == [953]
    assert "corpo da 953" in html
    assert {"/api/issue/953", "/api/issue/953/timeline"} <= set(buscas)


@com_node
def test_clicar_no_no_de_fatia_escondida_pelo_filtro_limpa_o_filtro(tmp_path):
    antes = "S.fIssues.state = 'CLOSED'; _clicar({ act: 'onda', n: '953', prd: '950' });"
    html, estado = _rodar(tmp_path, "[issueListHtml(), S.fIssues.state]", antes=antes)
    assert estado == "all"
    assert _fatias_abertas(html) == [953]


@com_node
def test_clicar_de_novo_no_mesmo_no_nao_fecha_o_card(tmp_path):
    antes = "_clicar({ act: 'onda', n: '953', prd: '950' }); _clicar({ act: 'onda', n: '953', prd: '950' });"
    assert _fatias_abertas(_rodar(tmp_path, "issueListHtml()", antes=antes)) == [953]


# ---------- reduceMotion ----------


@com_node
def test_reduce_motion_desenha_sem_a_classe_que_anima(tmp_path):
    parado = _svg(_rodar(tmp_path, _card(PRD)))  # o DOM de mentira pede movimento reduzido
    animado = _svg(_rodar(tmp_path, _card(PRD), antes="globalThis.matchMedia = () => ({ matches: false });"))
    assert "onda-anima" not in parado
    assert re.match(r'<svg class="onda-svg onda-anima"', animado)


def test_toda_animacao_do_desenho_depende_da_classe_que_anima():
    bloco = CSS.split("desenho das ondas no card do PRD (issue 943)", 1)[1].split("fim desenho das ondas", 1)[0]
    bloco = re.sub(r"/\*.*?\*/", "", bloco, flags=re.S)
    regras = re.findall(r"([^{}]+)\{([^{}]*)\}", bloco)
    animadas = [sel.strip() for sel, corpo in regras if re.search(r"\b(animation|transition)\s*:", corpo)]
    assert animadas, "o desenho não anima nada: o critério de reduceMotion ficaria vácuo"
    for sel in animadas:
        assert all(".onda-anima" in s for s in sel.split(",")), f"animação fora de .onda-anima: {sel}"


# ---------- estrutura do módulo ----------

ONDAS_JS = (DASH / "static" / "ondas.js").read_text(encoding="utf-8")
APP_JS = (DASH / "static" / "app.js").read_text(encoding="utf-8")


def test_modulo_proprio_entra_no_app_por_um_gancho_so_no_card_do_prd():
    assert "export function renderOndas(" in ONDAS_JS
    assert APP_JS.count("from './ondas.js'") == 1
    assert "import { renderOndas } from './ondas.js';" in APP_JS
    assert len(re.findall(r"\brenderOndas\(", APP_JS)) == 1
    assert "${prd ? renderOndas(i, S.data, FASES) : ''}" in _funcao(APP_JS, "issueCard")
    outros = [p.name for p in (DASH / "static").glob("*.js") if p.name != "app.js" and "ondas.js" in p.read_text()]
    assert outros == []


def test_modulo_sem_dependencia_externa():
    origens = re.findall(r"^import [^;]+ from '([^']+)';", ONDAS_JS, re.M)
    assert origens, "ondas.js sem import: o teste ficaria vácuo"
    for origem in origens:
        assert origem.startswith("./") and (DASH / "static" / origem).is_file(), origem
    assert len(origens) == ONDAS_JS.count("import ")
    for proibido in ("import(", "http:", "https:", "window.", "<script", "fetch("):
        assert proibido not in ONDAS_JS, proibido


def test_modulo_sem_cor_fixa_e_com_tokens_que_existem():
    assert _cores_fixas(ONDAS_JS) == []
    root = re.search(r":root\{(.*?)\}", CSS, re.S).group(1)
    for var in set(re.findall(r"var\((--[\w-]+)\)", ONDAS_JS)):
        assert f"{var}:" in root, var


# ---------- render no Chrome headless, contra o serve.py com fixture ----------

CHROME = next(
    (
        c
        for c in ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "google-chrome", "chromium")
        if Path(c).is_file() or shutil.which(c)
    ),
    None,
)
com_chrome = pytest.mark.skipif(not CHROME, reason="Chrome ausente")


def _dom_no_chrome(tmp_path, monkeypatch, *flags):
    """DOM da home renderizada pelo Chrome headless, com o /api/data da fixture.

    O Chrome novo imprime o DOM e às vezes não sai (o updater segura o
    processo): lê a saída até o </html> e derruba o grupo de processos.
    """
    import serve

    fixture = tmp_path / "dados.json"
    fixture.write_text(json.dumps(DADOS), encoding="utf-8")
    monkeypatch.setattr(serve, "FIXTURE", fixture)
    servidor = serve.ThreadingHTTPServer(("127.0.0.1", 0), serve.Handler)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{servidor.server_address[1]}/"
    saida = tmp_path / "dom.html"
    cmd = [CHROME, "--headless=new", "--disable-gpu", "--no-first-run", f"--user-data-dir={tmp_path / 'perfil'}"]
    cmd += [*flags, "--virtual-time-budget=3000", "--dump-dom", url]
    with saida.open("wb") as f:
        p = subprocess.Popen(cmd, stdout=f, stderr=subprocess.DEVNULL, start_new_session=True)
    try:
        prazo = time.monotonic() + 60
        while time.monotonic() < prazo and p.poll() is None and b"</html>" not in saida.read_bytes():
            time.sleep(0.2)
    finally:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        p.wait()
        servidor.shutdown()
    dom = saida.read_text(encoding="utf-8")
    assert "</html>" in dom, "o Chrome não devolveu o DOM"
    return dom


@com_chrome
def test_chrome_headless_desenha_as_tres_ondas_do_prd_da_fixture(tmp_path, monkeypatch):
    dom = _dom_no_chrome(tmp_path, monkeypatch)
    assert dom.count('<svg class="onda-svg') == 1  # só o PRD aberto com fatias
    svg = _svg(dom)
    assert 'aria-label="Ondas do PRD #950: 3 ondas, 7 fatias"' in svg
    assert {n: c for n, (c, _, _) in _nos(svg).items()} == {951: 0, 952: 0, 955: 0, 956: 0, 957: 0, 953: 1, 954: 2}
    assert _setas(svg) == {(951, 953), (952, 954), (953, 954)}
    assert re.match(r'<svg class="onda-svg onda-anima"', svg)


@com_chrome
def test_chrome_headless_com_movimento_reduzido_desenha_parado(tmp_path, monkeypatch):
    svg = _svg(_dom_no_chrome(tmp_path, monkeypatch, "--force-prefers-reduced-motion"))
    assert re.match(r'<svg class="onda-svg"', svg)
    assert len(_nos(svg)) == 7


def _funcao(js, nome):
    i = js.index(f"function {nome}(")
    j = js.index("{", i)
    fundo = 0
    for k in range(j, len(js)):
        fundo += {"{": 1, "}": -1}.get(js[k], 0)
        if fundo == 0:
            return js[i : k + 1]
    raise AssertionError(nome)
