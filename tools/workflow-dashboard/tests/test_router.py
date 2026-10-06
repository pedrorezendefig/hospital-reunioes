"""Router de hash do Hospital OS (issue #944, ADR 0062, decisão 8).

Aba, item aberto e filtros vivem no hash (`#issues/930`, `#prs/930`,
`#producao/v0.161.0`, `#issues?resp=...&fase=...`); abrir o painel com o hash
restaura o estado. Chips de issue, PR e versão navegam dentro do painel; o
GitHub fica no `↗` de cada card.

O router.js e o app.js rodam de verdade no Node: o app.js com um DOM mínimo de
mentira, um `location`/`history` que guardam o hash e os ouvintes de `window`
registrados para o teste disparar o `hashchange`, o ⟳ e a recoleta de 60 s.
"""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

DASH = Path(__file__).resolve().parents[1]
STATIC = DASH / "static"
APP_JS = (STATIC / "app.js").read_text(encoding="utf-8")
ROUTER = STATIC / "router.js"

com_node = pytest.mark.skipif(not shutil.which("node"), reason="node ausente")


def _node(tmp_path, prog):
    arq = tmp_path / "harness.mjs"
    arq.write_text(prog, encoding="utf-8")
    out = subprocess.run(
        ["node", str(arq)], capture_output=True, text=True, check=False, env={**os.environ, "TZ": "UTC"}
    )
    assert out.returncode == 0, out.stderr
    linha = [x for x in out.stdout.splitlines() if x.startswith("@@")][-1]
    return json.loads(linha[2:])


def _router(tmp_path, expr):
    """Avalia `expr` com as funções do router.js importadas."""
    prog = f"import * as R from '{ROUTER.as_uri()}';\nconsole.log('@@' + JSON.stringify({expr}));\n"
    return _node(tmp_path, prog)


def _fase(fase, **extra):
    base = {"fase": fase, "sub": None, "branch": None, "pr": None, "sinal": None, "tentativas": []}
    return {**base, "versao": None, "em_producao_em": None, **extra}


def _iss(n, *, state="OPEN", assignees=(), parent=None, children=()):
    return {
        "number": n,
        "title": f"Fatia {n}",
        "state": state,
        "labels": [],
        "assignees": list(assignees),
        "author": "ana",
        "url": f"https://github.com/x/y/issues/{n}",
        "body": f"corpo da {n}",
        "created_at": "2026-10-01T10:00:00Z",
        "closed_at": "2026-10-03T18:00:00Z" if state == "CLOSED" else None,
        "blocked_by": [],
        "parent": parent,
        "children": list(children),
        "is_prd": bool(children),
        "criteria": {"done": 0, "total": 0},
        "prs": [],
        "deploys": [],
    }


def _deploy(versao, sha, prs, issues):
    return {
        "at": "2026-10-03T18:05:00Z",
        "sha": sha,
        "app_version": versao,
        "subject": f"onda da {versao}",
        "result": "healthy",
        "duration_seconds": 120,
        "pr_numbers": prs,
        "issue_numbers": issues,
        "scope": ["backend"],
    }


DADOS = {
    "generated_at": "2026-10-06T10:00:00Z",
    "repo_url": "https://github.com/x/y",
    "repo_slug": "x/y",
    "github": {
        "error": None,
        "error_kind": None,
        "issues": [
            _iss(900, assignees=["pedrorezendefig"], children=(901, 902, 904)),
            _iss(901, parent=900),
            _iss(902, assignees=["lucassampaioc1"], parent=900),
            _iss(904, state="CLOSED", assignees=["pedroribbe"], parent=900),
            _iss(910),
        ],
        "prs": [],
        "prds": [900],
    },
    "fases": {
        "issues": {
            "900": _fase("triagem"),
            "901": _fase("fila"),
            "902": _fase("pr_aberto", pr=77),
            "904": _fase("em_producao", pr=70, versao="0.163.4", em_producao_em="2026-10-03T18:05:00Z"),
            "910": _fase("triagem"),
        },
        "prs": {},
        "timelines": {},
        "ondas": {},
        "funil": {"total": {}, "por_responsavel": {}},
    },
    "history": [_deploy("0.163.4", "abc1234", [70], [904]), _deploy("v0.163.3", "def5678", [69], [903])],
    "changelog": [],
    "state": {},
    "snapshots": [],
    "adrs": [],
}

# DOM mínimo: cada seletor devolve sempre o mesmo elemento (com os ouvintes
# dele); location/history guardam o hash; window guarda os ouvintes por tipo.
PRELUDIO = r"""
const _el = () => ({
  innerHTML: '', textContent: '', value: '', dataset: {}, style: {}, _ouvintes: [],
  classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } },
  addEventListener(tipo, fn) { this._ouvintes.push(fn); },
  querySelector: () => null, querySelectorAll: () => [], setAttribute() {}, closest: () => null,
});
const _view = _el();
const _els = { '#view': _view };
globalThis.document = {
  querySelector: s => (_els[s] ||= _el()),
  querySelectorAll: () => [], addEventListener() {}, body: _el(), activeElement: null, createElement: _el,
};
const _janela = {};
globalThis.window = {
  addEventListener(tipo, fn) { (_janela[tipo] ||= []).push(fn); },
  scrollTo() {}, matchMedia: () => ({ matches: true }),
};
globalThis.matchMedia = window.matchMedia;
globalThis.location = { hash: _HASH_INICIAL };
globalThis.history = { replaceState(_s, _t, url) { location.hash = url; } };
const _intervalos = {};
globalThis.setInterval = (fn, ms) => { _intervalos[ms] = fn; return 0; };
const _buscas = [];
const _respostas = { '/api/data': _DADOS, '/api/data?fresh=1': { ..._DADOS, generated_at: '2026-10-06T10:01:00Z' } };
globalThis.fetch = url => {
  _buscas.push(url);
  if (url in _respostas) return Promise.resolve({ json: () => Promise.resolve(_respostas[url]) });
  return new Promise(() => {});
};
const _esperar = () => new Promise(r => setTimeout(r, 0));
/* clique de verdade: o mesmo ouvinte delegado que o navegador chama no #view */
function _clicar(dataset) {
  const alvo = { dataset, classList: { contains: () => false } };
  const ev = { target: { closest: sel => (sel === '[data-act]' ? alvo : null) } };
  _view._ouvintes.forEach(fn => fn(ev));
}
function _aba(tab) {
  const ev = { target: { closest: () => ({ dataset: { tab } }) } };
  _els['#tabs']._ouvintes.forEach(fn => fn(ev));
}
function _buscar(texto) {
  _els['#fq'].value = texto;
  _els['#fq']._ouvintes.forEach(fn => fn());
}
/* o endereço trocado por fora: link do chip, voltar do navegador, URL colada */
function _navegar(hash) {
  location.hash = hash;
  (_janela.hashchange || []).forEach(fn => fn());
}
"""


def _app(tmp_path, expr, antes="", hash_inicial="", dados=None):
    """Roda o app.js inteiro (boot incluso) e avalia `expr` depois de `antes`."""
    modulo = APP_JS.replace("from './", f"from '{STATIC.as_uri()}/")
    prog = (
        f"const _HASH_INICIAL = {json.dumps(hash_inicial)};\nconst _DADOS = {json.dumps(dados or DADOS)};\n"
        + PRELUDIO
        + modulo
        + f"\nawait _esperar();\n{antes}\n"
        + f"console.log('@@' + JSON.stringify({expr}));\n"
    )
    return _node(tmp_path, prog)


def _cards(html):
    """(em destaque?, html) de cada <article> renderizado, na ordem."""
    return [
        ('aria-current="true"' in m.group(1), m.group(0)) for m in re.finditer(r"(<article[^>]*>)[\s\S]*?</article>", html)
    ]


def _card(html, n):
    """(em destaque?, html) do card da issue n."""
    for card in _cards(html):
        if f'data-act="iss" data-n="{n}"' in card[1]:
            return card
    raise AssertionError(f"card #{n} fora da lista")


# ---------- o router lê e monta o hash ----------


@com_node
def test_hash_vira_aba_item_e_filtros(tmp_path):
    rotas = _router(
        tmp_path,
        "['#issues/930?resp=lucassampaioc1&fase=pr_aberto', '#prs/930', '#producao/v0.161.0', '#mapa', '']"
        ".map(R.lerHash)",
    )
    assert rotas == [
        {"aba": "issues", "item": "930", "filtros": {"resp": "lucassampaioc1", "fase": "pr_aberto"}},
        {"aba": "prs", "item": "930", "filtros": {}},
        {"aba": "producao", "item": "v0.161.0", "filtros": {}},
        {"aba": "mapa", "item": None, "filtros": {}},
        {"aba": "issues", "item": None, "filtros": {}},
    ]


@com_node
def test_rota_vira_hash_sem_filtro_vazio_e_volta_igual(tmp_path):
    hashes, volta = _router(
        tmp_path,
        "(() => { const rotas = ["
        "{ aba: 'issues', item: '930', filtros: { fase: 'pr_aberto', resp: '', q: 'router de hash' } },"
        "{ aba: 'issues', item: null, filtros: { resp: '(sem)' } },"
        "{ aba: 'producao', item: 'v0.161.0', filtros: {} },"
        "{ aba: 'prs', item: null },"
        "]; const hs = rotas.map(R.montarHash); return [hs, hs.map(R.lerHash)]; })()",
    )
    assert hashes[0].startswith("#issues/930?") and "resp=" not in hashes[0]
    assert hashes[1:] == ["#issues?resp=%28sem%29", "#producao/v0.161.0", "#prs"]
    assert volta[0] == {"aba": "issues", "item": "930", "filtros": {"fase": "pr_aberto", "q": "router de hash"}}
    assert volta[1]["filtros"] == {"resp": "(sem)"}


def test_so_o_router_le_e_escreve_o_hash():
    router = ROUTER.read_text(encoding="utf-8")
    assert "location.hash" in router and "hashchange" in router and "replaceState" in router
    assert re.search(r"from '\./router\.js'", APP_JS), "app.js não importa o router"
    for arq in sorted(STATIC.glob("*.js")):
        if arq.name == "router.js":
            continue
        js = arq.read_text(encoding="utf-8")
        for proibido in ("location.hash", "hashchange", "replaceState", "pushState"):
            assert proibido not in js, f"{arq.name} mexe no hash por fora do router: {proibido}"


# ---------- o estado da tela vai para o hash ----------


@com_node
def test_trocar_de_aba_expandir_card_e_mudar_filtro_atualizam_o_hash(tmp_path):
    passos = _app(
        tmp_path,
        "_h",
        antes="""
        const _h = [];
        const _anotar = () => _h.push(location.hash);
        _aba('producao'); _anotar();
        _clicar({ act: 'dep', i: '0' }); _anotar();
        _clicar({ act: 'dep', i: '0' }); _anotar();
        _aba('issues'); _anotar();
        _clicar({ act: 'iss', n: '902' }); _anotar();
        _clicar({ act: 'ffase', v: 'pr_aberto' }); _anotar();
        _clicar({ act: 'fresp', v: '(sem)' }); _anotar();
        _buscar('fatia 9'); _anotar();
        _clicar({ act: 'iss', n: '902' }); _anotar();
        """,
    )
    assert passos == [
        "#producao",
        "#producao/v0.163.4",
        "#producao",
        "#issues",
        "#issues/902",
        "#issues/902?fase=pr_aberto",
        "#issues/902?fase=pr_aberto&resp=%28sem%29",
        "#issues/902?fase=pr_aberto&resp=%28sem%29&q=fatia+9",
        "#issues?fase=pr_aberto&resp=%28sem%29&q=fatia+9",
    ]


# ---------- abrir o painel com o hash restaura o estado ----------


@com_node
def test_abrir_com_hash_restaura_aba_filtros_e_card_expandido_com_destaque(tmp_path):
    hash_ = "#issues/902?fase=pr_aberto&resp=lucassampaioc1"
    tab, filtros, html, hash_depois = _app(
        tmp_path, "[S.tab, S.fIssues, _view.innerHTML, location.hash]", hash_inicial=hash_
    )
    assert tab == "issues"
    assert filtros["fase"] == "pr_aberto" and filtros["resp"] == "lucassampaioc1"
    assert re.search(r'data-act="ffase" data-v="pr_aberto" aria-pressed="true"', html)
    em_destaque, card = _card(html, 902)
    assert em_destaque
    assert "corpo da 902" in card  # expandido
    assert hash_depois == hash_


@com_node
def test_fatia_do_hash_aparece_com_o_prd_aberto_e_so_ela_em_destaque(tmp_path):
    html = _app(tmp_path, "_view.innerHTML", hash_inicial="#issues/904")
    em_destaque, card = _card(html, 904)
    assert em_destaque and "corpo da 904" in card
    assert [n for n in (900, 901, 902, 904, 910) if _card(html, n)[0]] == [904]


@com_node
def test_abrir_com_hash_de_versao_expande_o_deploy_com_destaque(tmp_path):
    tab, html = _app(tmp_path, "[S.tab, _view.innerHTML]", hash_inicial="#producao/v0.163.3")
    assert tab == "producao"
    (novo_em_destaque, novo), (velho_em_destaque, velho) = _cards(html)
    assert velho_em_destaque and "pd-body" in velho and "def5678" in velho
    assert not novo_em_destaque and "pd-body" not in novo


# ---------- chips navegam dentro do painel ----------


def _chips(html):
    """{texto: href} de cada chip que é link."""
    return {
        m.group(2): m.group(1)
        for m in re.finditer(r'<a class="chip[^"]*" href="([^"]*)"[^>]*>([^<]*)</a>', html)
    }


@com_node
def test_chips_de_issue_pr_e_versao_apontam_para_o_hash_de_cada_um(tmp_path):
    producao, aberta, em_producao = _app(
        tmp_path,
        "[_view.innerHTML, issueCard(S.data.github.issues[2], 0), issueCard(S.data.github.issues[3], 0)]",
        hash_inicial="#producao",
    )
    assert _chips(producao) == {"PR #70": "#prs/70", "#904": "#issues/904", "PR #69": "#prs/69", "#903": "#issues/903"}
    assert _chips(aberta) == {"PR #77": "#prs/77"}
    assert _chips(em_producao) == {"PR #70": "#prs/70", "v0.163.4": "#producao/v0.163.4"}


@com_node
def test_chip_de_issue_abre_o_card_certo_na_aba_issues_com_destaque(tmp_path):
    tab, html = _app(tmp_path, "[S.tab, _view.innerHTML]", hash_inicial="#producao", antes="_navegar('#issues/904');")
    assert tab == "issues"
    em_destaque, card = _card(html, 904)
    assert em_destaque and "corpo da 904" in card


@com_node
def test_chip_de_pr_e_de_versao_levam_a_aba_e_ao_item_do_hash(tmp_path):
    no_pr, na_versao = _app(
        tmp_path,
        "[_noPr, [S.tab, S.item, _cards(_view.innerHTML)]]",
        hash_inicial="#issues",
        antes="""
        _navegar('#prs/77'); const _noPr = [S.tab, S.item, _view.innerHTML];
        _navegar('#producao/v0.163.4');
        const _cards = h => [...h.matchAll(/<article[^>]*>/g)].map(m => m[0].includes('aria-current="true"'));
        """,
    )
    assert no_pr[:2] == ["prs", "77"]
    assert "#77" in no_pr[2]
    assert na_versao == ["producao", "v0.163.4", [True, False]]


# ---------- o GitHub é o ↗ de cada card, nunca o chip ----------


@com_node
def test_todo_card_de_issue_tem_o_link_do_github_e_nenhum_chip_abre_o_github(tmp_path):
    issues, producao = _app(
        tmp_path,
        "[_issues, _view.innerHTML]",
        hash_inicial="#issues",
        antes="""
        _clicar({ act: 'prd', n: '900', open: '0' });
        [900, 901, 902, 904, 910].forEach(n => _clicar({ act: 'iss', n: String(n) }));
        const _issues = _els['#ilist'].innerHTML;  // card clicado redesenha só a lista
        _navegar('#producao'); _clicar({ act: 'dep', i: '0' }); _clicar({ act: 'dep', i: '1' });
        """,
    )
    for n in (900, 901, 902, 904, 910):
        card = _card(issues, n)[1]
        gh = re.findall(r'<a class="nrow-go" href="([^"]+)"[^>]*>([\s\S]*?)</a>', card)
        assert len(gh) == 1, f"#{n} sem o link do GitHub"
        href, conteudo = gh[0]
        assert href == f"https://github.com/x/y/issues/{n}" and "↗" in conteudo
    chips = re.findall(r'<a class="chip[^"]*" href="([^"]*)"', issues + producao)
    assert len(chips) >= 7
    assert all(h.startswith("#") for h in chips), f"chip para fora do painel: {chips}"
    # o deploy também leva o ↗, para o commit; o sha segue visível como texto
    for sha in ("abc1234", "def5678"):
        assert re.search(rf'<a class="pd-gh" href="https://github.com/x/y/commit/{sha}"[^>]*>↗</a>', producao)
        assert f'<span class="chip">{sha}</span>' in producao
