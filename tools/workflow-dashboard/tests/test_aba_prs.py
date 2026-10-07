"""Aba PRs do Hospital OS (issue #946, ADR 0062, decisão 7).

Quadro com as sete fases do PR em colunas e uma raia por pessoa, na cor dela.
A pessoa do PR é quem assumiu a issue que ele fecha (assignee; emenda de
06/10/2026 da ADR 0062); sem assignee, quem criou a issue; PR sem issue, quem
abriu o PR.
Card com PR, issue, branch e dias na coluna; conflito vira sinal no card.
Coluna mais cheia e card velho ganham destaque; PRs fechados sem merge ficam
numa faixa cinza embaixo. Filtros pessoa, PRD e só abertos vivem no hash.

O app.js roda de verdade no Node, inteiro e com o boot: DOM mínimo de mentira,
`location`/`history` que guardam o hash e o mesmo ouvinte de clique do navegador.
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
CSS = (STATIC / "style.css").read_text(encoding="utf-8")

com_node = pytest.mark.skipif(not shutil.which("node"), reason="node ausente")

COLUNAS = [
    "aberto_sem_ci",
    "ci_vermelho",
    "esperando_revisor",
    "verde_esperando_merge",
    "mergeado_sem_deploy",
    "em_producao",
    "entregue",
]


def _iss(n, *, assignees=(), author="pedrorezendefig", parent=None, children=()):
    return {
        "number": n,
        "title": f"Issue {n}",
        "state": "OPEN",
        "labels": [],
        "assignees": list(assignees),
        "author": author,
        "url": f"https://github.com/x/y/issues/{n}",
        "body": "",
        "created_at": "2026-09-20T10:00:00Z",
        "closed_at": None,
        "blocked_by": [],
        "parent": parent,
        "children": list(children),
        "is_prd": bool(children),
        "criteria": {"done": 0, "total": 0},
        "prs": [],
        "deploys": [],
    }


ISSUES = [
    _iss(900, assignees=["pedrorezendefig"], children=(901, 902, 903, 904, 905)),
    _iss(901, assignees=["lucassampaioc1"], parent=900),
    _iss(902, assignees=["pedroribbe"], parent=900),
    _iss(903, author="ana", parent=900),  # ninguém assumiu: a raia é de quem criou
    _iss(904, assignees=["lucassampaioc1"], parent=900),
    _iss(905, assignees=["zeca"], parent=900),  # assumiu, mas não tem PR: sem raia
    _iss(920, assignees=["pedrorezendefig"], children=(921,)),
    _iss(921, assignees=["lucassampaioc1"], parent=920),
    _iss(950, assignees=["pedrorezendefig"]),
]

# (número, estado, issues que fecha, fase, dias na coluna, extras do fases.py)
PRS = [
    (80, "OPEN", [901], "aberto_sem_ci", 0, {}),
    (81, "OPEN", [902], "ci_vermelho", 5, {"conflito": True}),
    (82, "OPEN", [903], "esperando_revisor", 1, {}),
    (83, "OPEN", [904], "esperando_revisor", 2, {}),
    (84, "OPEN", [921], "esperando_revisor", 0, {}),
    (85, "OPEN", [950], "verde_esperando_merge", 3, {}),
    (86, "MERGED", [904], "mergeado_sem_deploy", 4, {}),
    (70, "MERGED", [901], "em_producao", 2, {"versao": "0.163.4"}),
    (71, "MERGED", [950], "em_producao", 1, {"versao": "v0.163.5"}),
    (72, "MERGED", [921], "em_producao", 3, {"versao": "0.163.4"}),
    (73, "MERGED", [903], "em_producao", 0, {"versao": "v0.163.5"}),
    (
        61,
        "MERGED",
        [902],
        "em_producao",
        30,
        {"versao": "0.150.0"},
    ),  # fora da janela de 7 dias
    (75, "CLOSED", [902], "fechado_sem_merge", 4, {"desde": "2026-10-02T15:00:00Z"}),
    (76, "CLOSED", [], "fechado_sem_merge", 9, {"desde": "2026-09-27T15:00:00Z"}),
]


def _pr(n, state, closes):
    return {
        "number": n,
        "title": f"PR {n}",
        "state": state,
        "merged_at": None,
        "head_ref": f"feat/fatia-{closes[0] if closes else n}",
        "url": f"https://github.com/x/y/pull/{n}",
        "closes": closes,
        "created_at": "2026-09-25T10:00:00Z",
        "closed_at": None,
        "author": "pedrorezendefig",
        "is_draft": False,
    }


def _fase_pr(fase, dias, extra):
    base = {
        "fase": fase,
        "desde": "2026-10-01T10:00:00Z",
        "dias_na_coluna": dias,
        "ci": None,
        "veredito": None,
        "conflito": False,
        "versao": None,
    }
    return {**base, **extra}


DADOS = {
    "generated_at": "2026-10-06T10:00:00Z",
    "repo_url": "https://github.com/x/y",
    "repo_slug": "x/y",
    "github": {
        "error": None,
        "error_kind": None,
        "issues": ISSUES,
        "prs": [_pr(n, st, cl) for n, st, cl, *_ in PRS],
        "prds": [900, 920],
    },
    "fases": {
        "issues": {},
        "prs": {str(n): _fase_pr(f, d, x) for n, _, _, f, d, x in PRS},
        "timelines": {},
        "ondas": {},
        "funil": {"total": {}, "por_responsavel": {}},
    },
    "history": [],
    "changelog": [],
    "state": {},
    "snapshots": [],
    "adrs": [],
}

PRELUDIO = r"""
const _el = () => ({
  innerHTML: '', textContent: '', value: '', dataset: {}, style: {}, _ouvintes: [],
  classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } },
  addEventListener(tipo, fn) { this._ouvintes.push(fn); },
  querySelector: () => null, querySelectorAll: () => [], setAttribute() {}, closest: () => null,
  scrollIntoView() {},
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
globalThis.setInterval = () => 0;
globalThis.fetch = url => (url === '/api/data'
  ? Promise.resolve({ json: () => Promise.resolve(_DADOS) })
  : new Promise(() => {}));
const _esperar = () => new Promise(r => setTimeout(r, 0));
/* clique de verdade: o mesmo ouvinte delegado que o navegador chama no #view */
function _clicar(dataset) {
  const alvo = { dataset, classList: { contains: () => false } };
  const ev = { target: { closest: sel => (sel === '[data-act]' ? alvo : null) } };
  _view._ouvintes.forEach(fn => fn(ev));
}
function _navegar(hash) {
  location.hash = hash;
  (_janela.hashchange || []).forEach(fn => fn());
}
"""


def _app(tmp_path, expr="_view.innerHTML", antes="", hash_inicial="#prs", dados=None):
    """Roda o app.js inteiro (boot incluso) e avalia `expr` depois de `antes`."""
    modulo = APP_JS.replace("from './", f"from '{STATIC.as_uri()}/")
    prog = (
        f"const _HASH_INICIAL = {json.dumps(hash_inicial)};\nconst _DADOS = {json.dumps(dados or DADOS)};\n"
        + PRELUDIO
        + modulo
        + f"\nawait _esperar();\n{antes}\n"
        + f"console.log('@@' + JSON.stringify({expr}));\n"
    )
    arq = tmp_path / "harness.mjs"
    arq.write_text(prog, encoding="utf-8")
    out = subprocess.run(
        ["node", str(arq)],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "TZ": "UTC"},
    )
    assert out.returncode == 0, out.stderr
    linha = [x for x in out.stdout.splitlines() if x.startswith("@@")][-1]
    return json.loads(linha[2:])


def _blocos(html, classe):
    """(tag de abertura, html inteiro) de cada <div|section|article class="classe ..."> por contagem de tags."""
    out = []
    for m in re.finditer(
        rf'<(div|section|article)\b[^>]*class="{classe}(?=[ "])[^"]*"[^>]*>', html
    ):
        tag = m.group(1)
        depth, k = 0, m.start()
        for t in re.finditer(rf"<(/?){tag}\b[^>]*>", html[m.start() :]):
            depth += -1 if t.group(1) else 1
            if depth == 0:
                k = m.start() + t.end()
                break
        out.append((m.group(0), html[m.start() : k]))
    return out


def _raias(html):
    """{login da raia: html da raia}."""
    return {
        re.search(r'data-raia="([^"]*)"', tag).group(1): bloco
        for tag, bloco in _blocos(html, "pr-raia")
    }


def _celulas(raia):
    """{coluna: [números dos PRs]} de uma raia."""
    return {
        re.search(r'data-col="([^"]*)"', tag).group(1): [
            int(n) for n in re.findall(r'data-act="pr" data-n="(\d+)"', b)
        ]
        for tag, b in _blocos(raia, "pr-celula")
    }


def _no_quadro(html):
    """Números de todos os PRs nas colunas (sem a faixa cinza)."""
    return sorted(
        {
            n
            for raia in _raias(html).values()
            for ns in _celulas(raia).values()
            for n in ns
        }
    )


# ---------- seis colunas, uma raia por pessoa ----------


@com_node
def test_quadro_tem_as_sete_colunas_e_uma_raia_por_pessoa_que_tem_pr(tmp_path):
    html, cores = _app(
        tmp_path,
        "[_view.innerHTML, ['ana', 'lucassampaioc1', 'pedrorezendefig', 'pedroribbe'].map(corDaPessoa)]",
    )
    cab = re.findall(r'class="pr-col-cab[^"]*" data-col="([^"]+)"', html)
    assert cab == COLUNAS
    raias = _raias(html)
    assert list(raias) == ["ana", "lucassampaioc1", "pedrorezendefig", "pedroribbe"]
    for (login, raia), cor in zip(raias.items(), cores):
        assert f"--pessoa:{cor}" in re.match(r"<div[^>]*>", raia).group(0)
        assert list(_celulas(raia)) == COLUNAS
    assert "ninguém assumiu" not in html
    assert "zeca" not in html  # assumiu issue, não tem PR
    assert _celulas(raias["lucassampaioc1"]) == {
        "aberto_sem_ci": [80],
        "ci_vermelho": [],
        "esperando_revisor": [83, 84],
        "verde_esperando_merge": [],
        "mergeado_sem_deploy": [86],
        "em_producao": [72, 70],
        "entregue": [],
    }
    assert _celulas(raias["ana"])["esperando_revisor"] == [82]  # 903 sem assignee: quem criou


# ---------- card: PR, issue, branch, dias; conflito como sinal ----------


def _card(html, n):
    for tag, bloco in _blocos(html, "pr-card"):
        if f'data-n="{n}"' in tag:
            return bloco
    raise AssertionError(f"card do PR #{n} fora do quadro")


def _chips(html):
    """{texto: href} de cada chip que é link."""
    return {
        m.group(2): m.group(1)
        for m in re.finditer(
            r'<a class="chip[^"]*" href="([^"]*)"[^>]*>([^<]*)</a>', html
        )
    }


@com_node
def test_card_mostra_pr_issue_branch_e_dias_na_coluna(tmp_path):
    html = _app(tmp_path)
    card = _card(html, 83)
    assert "PR #83" in card and "PR 83" in card  # número e título
    assert _chips(card) == {"#904": "#issues/904"}
    assert "feat/fatia-904" in card
    assert "2 dias na coluna" in card
    assert "1 dia na coluna" in _card(html, 82)
    assert "hoje na coluna" in _card(html, 80)
    # versão em que subiu, de volta para a aba Produção; GitHub só no ↗
    assert _chips(_card(html, 71)) == {
        "#950": "#issues/950",
        "v0.163.5": "#producao/v0.163.5",
    }
    gh = re.findall(r'<a class="pr-gh" href="([^"]+)"[^>]*>↗</a>', card)
    assert gh == ["https://github.com/x/y/pull/83"]


@com_node
def test_conflito_aparece_como_sinal_no_card(tmp_path):
    html = _app(tmp_path)
    assert re.search(
        r'class="[^"]*\bpr-conflito\b[^"]*"[^>]*>conflito<', _card(html, 81)
    )
    assert "pr-conflito" not in _card(html, 83)


# ---------- gargalo: coluna mais cheia e card velho ----------


def _colunas_cheias(html):
    """Colunas com o destaque de mais cheia, no cabeçalho e em cada célula."""
    cab = re.findall(r'class="pr-col-cab pr-col-cheia" data-col="([^"]+)"', html)
    celulas = re.findall(r'class="pr-celula pr-col-cheia" data-col="([^"]+)"', html)
    return cab, sorted(set(celulas)), len(celulas)


@com_node
def test_coluna_mais_cheia_ganha_destaque_e_em_producao_nao_conta(tmp_path):
    html = _app(tmp_path)
    # Em produção tem mais cards (70, 71, 72, 73), mas é o fim do caminho, não gargalo
    assert _colunas_cheias(html) == (["esperando_revisor"], ["esperando_revisor"], 4)
    contagens = dict(
        re.findall(
            r'data-col="([^"]+)"><span>[^<]+</span><span class="pr-col-n">(\d+)<', html
        )
    )
    assert contagens["esperando_revisor"] == "3" and contagens["aberto_sem_ci"] == "1"


@com_node
def test_empate_de_colunas_nao_destaca_nenhuma(tmp_path):
    fases = {**DADOS["fases"]["prs"]}
    for n in ("80", "85"):
        fases[n] = {
            **fases[n],
            "fase": "ci_vermelho",
        }  # 3 em CI vermelho, 3 esperando revisor
    dados = {**DADOS, "fases": {**DADOS["fases"], "prs": fases}}
    assert _colunas_cheias(_app(tmp_path, dados=dados)) == ([], [], 0)


@com_node
def test_card_acima_do_limite_de_dias_ganha_destaque_menos_em_producao(tmp_path):
    html = _app(tmp_path)
    velhos = sorted(
        int(n) for n in re.findall(r'class="pr-card pr-velho"[^>]*data-n="(\d+)"', html)
    )
    assert velhos == [81, 86]  # 5 e 4 dias; o de 3 dias (85) fica no limite
    assert "pr-velho" not in _card(html, 85)


def _faixa(html):
    [(_, faixa)] = _blocos(html, "pr-tentativas")
    return {
        int(re.search(r'data-n="(\d+)"', tag).group(1)): b
        for tag, b in _blocos(faixa, "pr-tentativa")
    }


@com_node
def test_fechados_sem_merge_ficam_na_faixa_cinza_com_data_e_issue(tmp_path):
    html = _app(tmp_path)
    faixa = _faixa(html)
    assert list(faixa) == [75, 76]  # o fechado mais recente primeiro
    assert "PR #75" in faixa[75] and "fechado 2 out" in faixa[75]
    assert _chips(faixa[75]) == {"#902": "#issues/902"}
    assert "fechado 27 set" in faixa[76] and "sem issue" in faixa[76]
    assert re.search(
        r'<a class="pr-gh" href="https://github.com/x/y/pull/75"', faixa[75]
    )
    assert not {75, 76} & set(_no_quadro(html))
    regras = re.findall(r"\.pr-tentativas\{([^}]*)\}", CSS)
    assert regras and "var(--" in regras[0]


def test_destaques_do_gargalo_tem_estilo_so_com_tokens():
    for classe in ("pr-col-cheia", "pr-velho"):
        regras = re.findall(rf"[^}}]*\.{classe}\b[^{{]*\{{([^}}]*)\}}", CSS)
        assert regras, f"sem estilo para .{classe}"
        assert all("var(--" in r for r in regras)


# ---------- filtros pessoa, PRD e só abertos, no hash ----------


def _botoes(html, act):
    """{data-v: tag de abertura} de cada <button data-act=act>."""
    return {
        re.search(r'data-v="([^"]*)"', m.group(0)).group(1): m.group(0)
        for m in re.finditer(r"<button[^>]*>", html)
        if f'data-act="{act}"' in m.group(0)
    }


def _faixa_ou_vazia(html):
    return list(_faixa(html)) if _blocos(html, "pr-tentativas") else []


@com_node
def test_filtros_sao_chips_de_pessoa_na_cor_dela_prd_e_so_abertos(tmp_path):
    html, cor = _app(tmp_path, "[_view.innerHTML, corDaPessoa('pedroribbe')]")
    pessoas = _botoes(html, "pfresp")
    assert list(pessoas) == ["ana", "lucassampaioc1", "pedrorezendefig", "pedroribbe"]
    assert f"--pessoa:{cor}" in pessoas["pedroribbe"]
    assert list(_botoes(html, "pfprd")) == ["920", "900"]
    assert list(_botoes(html, "pfabertos")) == ["1"]
    assert "<select" not in html
    assert all(
        'aria-pressed="false"' in tag
        for act in ("pfresp", "pfprd", "pfabertos")
        for tag in _botoes(html, act).values()
    )


@com_node
def test_filtro_de_pessoa_soma_raias_e_o_chip_de_novo_tira_a_pessoa(tmp_path):
    lucas, duas, sem, desligado = _app(
        tmp_path,
        "[_lucas, _duas, _sem, _view.innerHTML]",
        antes="""
        _clicar({ act: 'pfresp', v: 'lucassampaioc1' }); const _lucas = _view.innerHTML;
        _clicar({ act: 'pfresp', v: 'ana' }); const _duas = _view.innerHTML;
        _clicar({ act: 'pfresp', v: 'lucassampaioc1' }); const _sem = _view.innerHTML;
        _clicar({ act: 'pfresp', v: 'ana' });
        """,
    )
    assert list(_raias(lucas)) == ["lucassampaioc1"]
    assert _no_quadro(lucas) == [70, 72, 80, 83, 84, 86]
    assert _faixa_ou_vazia(lucas) == []
    assert 'aria-pressed="true"' in _botoes(lucas, "pfresp")["lucassampaioc1"]
    # segunda pessoa entra ao lado, cada uma na sua raia
    assert list(_raias(duas)) == ["ana", "lucassampaioc1"]
    assert _no_quadro(duas) == [70, 72, 73, 80, 82, 83, 84, 86]
    assert all('aria-pressed="true"' in _botoes(duas, "pfresp")[p] for p in ("lucassampaioc1", "ana"))
    assert (
        list(_raias(sem)) == ["ana"]
        and _no_quadro(sem) == [73, 82]
        and _faixa_ou_vazia(sem) == []
    )
    assert len(_raias(desligado)) == 4  # sem ninguém marcado, todas as raias


@com_node
def test_varias_pessoas_vao_para_o_hash_separadas_por_virgula_e_voltam(tmp_path):
    h = _app(
        tmp_path,
        "location.hash",
        antes="_clicar({ act: 'pfresp', v: 'lucassampaioc1' }); _clicar({ act: 'pfresp', v: 'pedroribbe' });",
    )
    assert h == "#prs?resp=lucassampaioc1%2Cpedroribbe"  # a vírgula vai codificada pelo router
    for inicial in ("#prs?resp=lucassampaioc1%2Cpedroribbe", "#prs?resp=lucassampaioc1,pedroribbe"):
        html = _app(tmp_path, hash_inicial=inicial)
        assert list(_raias(html)) == ["lucassampaioc1", "pedroribbe"], inicial
    assert list(_raias(html)) == ["lucassampaioc1", "pedroribbe"]


@com_node
def test_em_producao_e_compacta_uma_linha_por_pr_com_issue_e_versao(tmp_path):
    html = _app(tmp_path)
    mini = _card(html, 70)
    assert 'class="pr-card pr-mini"' in mini
    assert "title=" not in mini.split(">", 1)[0]  # o título vai para o resumo do hover
    assert _chips(mini) == {"#901": "#issues/901", "v0.163.4": "#producao/v0.163.4"}
    assert "na coluna" not in mini and "feat/fatia" not in mini
    assert 'class="pr-card"' in _card(html, 83) or 'class="pr-card ' in _card(html, 83)
    assert "pr-mini" not in _card(html, 83)


@com_node
def test_chip_da_issue_leva_o_titulo_dela(tmp_path):
    html = _app(tmp_path)
    assert re.search(r'<a class="chip" href="#issues/904" title="Issue 904">#904</a>', _card(html, 83))


@com_node
def test_botao_limpar_da_aba_prs_so_com_filtro_e_volta_ao_padrao(tmp_path):
    assert 'data-act="pflimpar"' not in _app(tmp_path)
    html, filtros = _app(
        tmp_path,
        "[_com, S.fPrs]",
        antes="""
        _clicar({ act: 'pfresp', v: 'lucassampaioc1' }); _clicar({ act: 'pfprd', v: '900' });
        const _com = _view.innerHTML;
        _clicar({ act: 'pflimpar' });
        """,
    )
    assert 'data-act="pflimpar"' in html
    assert filtros == {"resp": [], "prd": None, "abertos": False}


@com_node
def test_filtro_de_prd_deixa_os_prs_das_fatias_dele(tmp_path):
    html = _app(tmp_path, antes="_clicar({ act: 'pfprd', v: '900' });")
    assert _no_quadro(html) == [
        61,
        70,
        73,
        80,
        81,
        82,
        83,
        86,
    ]  # o 61 é antigo: com PRD, Em produção mostra tudo
    assert _faixa_ou_vazia(html) == [75]


@com_node
def test_so_abertos_tira_mergeados_e_tentativas(tmp_path):
    html = _app(tmp_path, antes="_clicar({ act: 'pfabertos', v: '1' });")
    assert _no_quadro(html) == [80, 81, 82, 83, 84, 85]
    assert _faixa_ou_vazia(html) == []
    assert (
        re.findall(r'class="pr-col-cab[^"]*" data-col="([^"]+)"', html) == COLUNAS
    )  # as sete colunas ficam


@com_node
def test_filtros_vao_para_o_hash_e_voltam_ao_abrir(tmp_path):
    hashes = _app(
        tmp_path,
        "_h",
        antes="""
        const _h = [];
        _clicar({ act: 'pfresp', v: 'lucassampaioc1' }); _h.push(location.hash);
        _clicar({ act: 'pfprd', v: '900' }); _h.push(location.hash);
        _clicar({ act: 'pfabertos', v: '1' }); _h.push(location.hash);
        _clicar({ act: 'pfresp', v: 'lucassampaioc1' }); _h.push(location.hash);
        """,
    )
    assert hashes == [
        "#prs?resp=lucassampaioc1",
        "#prs?resp=lucassampaioc1&prd=900",
        "#prs?resp=lucassampaioc1&prd=900&abertos=1",
        "#prs?prd=900&abertos=1",
    ]
    html, hash_depois = _app(
        tmp_path,
        "[_view.innerHTML, location.hash]",
        hash_inicial="#prs?prd=900&abertos=1",
    )
    assert _no_quadro(html) == [80, 81, 82, 83]
    assert 'aria-pressed="true"' in _botoes(html, "pfprd")["900"]
    assert 'aria-pressed="true"' in _botoes(html, "pfabertos")["1"]
    assert hash_depois == "#prs?prd=900&abertos=1"


@com_node
def test_cada_aba_guarda_os_proprios_filtros_ao_trocar_de_aba(tmp_path):
    hashes = _app(
        tmp_path,
        "_h",
        hash_inicial="#prs?prd=900",
        antes="""
        const _aba = tab => _els['#tabs']._ouvintes.forEach(fn => fn({ target: { closest: () => ({ dataset: { tab } }) } }));
        const _h = [];
        _aba('issues'); _clicar({ act: 'ffase', v: 'fila' }); _h.push(location.hash);
        _aba('prs'); _h.push(location.hash);
        _aba('issues'); _h.push(location.hash);
        """,
    )
    assert hashes == ["#issues?fase=fila", "#prs?prd=900", "#issues?fase=fila"]


@com_node
def test_sem_gh_o_quadro_avisa_em_vez_de_zerar(tmp_path):
    dados = {
        **DADOS,
        "github": {**DADOS["github"], "error": "gh fora", "prs": []},
        "fases": None,
    }
    html = _app(tmp_path, dados=dados)
    assert "pr-col-cab" not in html
    assert "quadro" in html and "gh" in html


# ---------- #prs/N abre o card com destaque ----------


def _em_destaque(html):
    return [
        int(n)
        for n in re.findall(
            r'<article[^>]*data-n="(\d+)"[^>]*aria-current="true"', html
        )
    ]


@com_node
def test_hash_do_pr_abre_o_card_com_destaque(tmp_path):
    assert _em_destaque(_app(tmp_path, hash_inicial="#prs/81")) == [81]
    assert _em_destaque(_app(tmp_path, hash_inicial="#prs/75")) == [
        75
    ]  # tentativa, na faixa cinza
    antigo = _app(tmp_path, hash_inicial="#prs/61")  # fora da janela de Em produção
    assert _em_destaque(antigo) == [61] and 61 in _no_quadro(antigo)
    for seletor in (
        r"\.pr-card\[aria-current=\"true\"\]",
        r"\.pr-tentativa\[aria-current=\"true\"\]",
    ):
        m = re.search(seletor + r"[^{]*\{([^}]*)\}", CSS)
        assert m and "var(--brand)" in m.group(1), f"sem destaque em {seletor}"


@com_node
def test_chip_de_pr_de_outra_aba_abre_o_card_com_destaque(tmp_path):
    tab, html = _app(
        tmp_path,
        "[S.tab, _view.innerHTML]",
        hash_inicial="#issues",
        antes="_navegar('#prs/84');",
    )
    assert tab == "prs" and _em_destaque(html) == [84]


@com_node
def test_clicar_no_card_marca_o_pr_no_hash_e_clicar_de_novo_desmarca(tmp_path):
    marcado, desmarcado = _app(
        tmp_path,
        "[_marcado, [location.hash, _view.innerHTML]]",
        antes="""
        _clicar({ act: 'pr', n: '83' }); const _marcado = [location.hash, _view.innerHTML];
        _clicar({ act: 'pr', n: '83' });
        """,
    )
    assert marcado[0] == "#prs/83" and _em_destaque(marcado[1]) == [83]
    assert desmarcado[0] == "#prs" and _em_destaque(desmarcado[1]) == []


@com_node
def test_pr_do_hash_fora_do_quadro_avisa_e_leva_ao_github(tmp_path):
    html = _app(tmp_path, hash_inicial="#prs/999")
    [(_, aviso)] = _blocos(html, "pr-fora")
    assert "PR #999" in aviso
    assert 'href="https://github.com/x/y/pull/999"' in aviso


# ---------- Em produção: só a última semana, sem filtro de PRD ----------


@com_node
def test_em_producao_mostra_a_ultima_semana_e_conta_as_mais_antigas(tmp_path):
    html = _app(tmp_path)
    assert 61 not in _no_quadro(html)
    assert {70, 71, 72, 73} <= set(_no_quadro(html))
    assert re.search(r'class="pr-nota[^"]*"[^>]*>[^<]*1 PR mais antigo', html)


# ---------- o texto de em construção saiu ----------


@com_node
def test_texto_em_construcao_da_aba_saiu(tmp_path):
    assert "em construção" not in _app(tmp_path)
    assert "em construção" not in APP_JS


@com_node
def test_em_producao_ordena_pela_versao_e_mostra_a_hora_do_merge(tmp_path):
    # mesma raia, dias na coluna e número fora de ordem de propósito: quem manda é a versão
    prs = [
        (40, "0.161.3", 9, "2026-10-01T09:05:00Z"),
        (41, "0.161.10", 1, "2026-10-03T18:40:00Z"),
        (42, "v0.162.0", 5, "2026-10-04T11:20:00Z"),
        (43, "0.161.2", 0, "2026-10-01T08:00:00Z"),
    ]
    dados = json.loads(json.dumps(DADOS))
    dados["github"]["prs"] = [{**_pr(n, "MERGED", [901]), "merged_at": m} for n, _, _, m in prs]
    dados["fases"]["prs"] = {str(n): _fase_pr("em_producao", 0, {"versao": v, "dias_na_coluna": d}) for n, v, d, _ in prs}
    html = _app(tmp_path, hash_inicial="#prs?prd=900", dados=dados)
    assert _celulas(_raias(html)["lucassampaioc1"])["em_producao"] == [42, 41, 40, 43]
    assert re.search(r'class="pr-quando"[^>]*>4 out, 11:20<', _card(html, 42))
    assert re.search(r'class="pr-quando"[^>]*>1 out, 08:00<', _card(html, 43))


@com_node
def test_pr_sem_issue_fica_na_raia_de_quem_abriu_o_pr(tmp_path):
    dados = json.loads(json.dumps(DADOS))
    dados["github"]["prs"].append({**_pr(90, "MERGED", []), "author": "lucassampaioc1"})
    dados["fases"]["prs"]["90"] = _fase_pr("em_producao", 0, {"versao": "0.163.6"})
    html = _app(tmp_path, dados=dados)
    assert 90 in _celulas(_raias(html)["lucassampaioc1"])["em_producao"]
    assert "(sem)" not in _raias(html)
    # a faixa cinza segue a mesma regra: o #76 (sem issue) é de quem o abriu
    assert _faixa_ou_vazia(_app(tmp_path, antes="_clicar({ act: 'pfresp', v: 'pedrorezendefig' });")) == [76]


# ---------- Entregue: PR de ferramenta, o merge é a entrega ----------


def _com_entregues(*entregues):
    dados = json.loads(json.dumps(DADOS))
    for n, merged_at, dias in entregues:
        dados["github"]["prs"].append({**_pr(n, "MERGED", [904]), "merged_at": merged_at, "title": f"chore(os): {n}"})
        dados["fases"]["prs"][str(n)] = _fase_pr("entregue", dias, {"desde": merged_at})
    return dados


@com_node
def test_entregue_e_coluna_propria_depois_de_em_producao(tmp_path):
    html = _app(tmp_path, dados=_com_entregues((95, "2026-10-06T04:20:00Z", 0)))
    cab = re.findall(r'class="pr-col-cab[^"]*" data-col="([^"]+)"><span>([^<]+)<', html)
    assert cab[-2:] == [("em_producao", "Em produção"), ("entregue", "Entregue")]
    celulas = _celulas(_raias(html)["lucassampaioc1"])
    assert celulas["entregue"] == [95] and 95 not in celulas["em_producao"] + celulas["mergeado_sem_deploy"]


@com_node
def test_entregue_agrupa_por_dia_e_mostra_so_o_numero(tmp_path):
    dados = _com_entregues(
        (95, "2026-10-06T04:20:00Z", 0), (96, "2026-10-06T09:00:00Z", 0), (98, "2026-10-05T10:00:00Z", 1)
    )
    html = _app(tmp_path, dados=dados)
    pilula = _card(html, 95)
    assert re.fullmatch(
        r'<article class="pr-card pr-entregue" data-act="pr" data-n="95">#95'
        r'<a class="pr-gh" href="https://github.com/x/y/pull/95" target="_blank"[^>]*>↗</a></article>', pilula)
    celula = dict(_blocos(_raias(html)["lucassampaioc1"], "pr-celula"))
    entregue = next(b for tag, b in celula.items() if 'data-col="entregue"' in tag)
    dias = re.findall(r'<span class="pr-entregue-data">([^<]+)</span>((?:<article[^>]*>#\d+<a[^>]*>↗</a></article>)+)', entregue)
    assert [(d, re.findall(r">#(\d+)<", ps)) for d, ps in dias] == [("6 out", ["96", "95"]), ("5 out", ["98"])]


@com_node
def test_entregue_ordena_pelo_merge_e_mostra_so_a_ultima_semana(tmp_path):
    dados = _com_entregues(
        (95, "2026-10-04T10:00:00Z", 2), (96, "2026-10-06T09:00:00Z", 0), (97, "2026-09-20T10:00:00Z", 16)
    )
    html = _app(tmp_path, dados=dados)
    assert _celulas(_raias(html)["lucassampaioc1"])["entregue"] == [96, 95]
    assert re.search(r'class="pr-nota[^"]*"[^>]*>[^<]*2 PRs mais antigos', html)  # o #61 e o #97
    com_prd = _app(tmp_path, hash_inicial="#prs?prd=900", dados=dados)
    assert _celulas(_raias(com_prd)["lucassampaioc1"])["entregue"] == [96, 95, 97]


@com_node
def test_entregue_nao_e_gargalo_nem_envelhece(tmp_path):
    dados = _com_entregues(*[(n, "2026-10-01T10:00:00Z", 5) for n in range(110, 116)])
    html = _app(tmp_path, hash_inicial="#prs?prd=900", dados=dados)
    assert 'data-col="entregue"' in html and "pr-col-cheia" not in re.search(r'class="pr-col-cab([^"]*)" data-col="entregue"', html).group(1)
    assert "pr-velho" not in _card(html, 110)


# ---------- hover e clique: o resumo do PR ----------


def _dados_do_pop():
    dados = json.loads(json.dumps(DADOS))
    pr = next(p for p in dados["github"]["prs"] if p["number"] == 70)
    pr.update(
        title="feat(atas): exportar PDF",
        created_at="2026-10-05T22:10:00Z",
        merged_at="2026-10-06T01:30:00Z",
        author="lucassampaioc1",
        mergeado_por="pedrorezendefig",
        labels=["type:feature", "area:atas"],
    )
    return dados


@com_node
def test_hover_e_enxuto_valor_entregue_e_uma_linha_de_rodape(tmp_path):
    dados = _dados_do_pop()
    pr = next(p for p in dados["github"]["prs"] if p["number"] == 70)
    pr["resumo"] = {"antes": "copiava a Ata para o Word.", "depois": "a Ata sai em PDF.", "contexto": None}
    pop = _app(tmp_path, "popDoPr('70', S.data, { fmtDT, depVer })", dados=dados)
    assert "<b>PR #70 · Em produção</b>" in pop
    assert re.search(
        r'<span class="fx-k">valor entregue</span><p><em>Antes</em> copiava a Ata para o Word\.</p>'
        r'<p><em>Depois</em> a Ata sai em PDF\.</p>', pop)
    assert '<p class="pr-pop-rodape">#901 · no ar na v0.163.4 · 6 out, 01:30</p>' in pop
    for fora in ("feat/fatia-901", "type:feature", "aberto por", "levou", "Issue 901", "<a"):
        assert fora not in pop, fora  # enxuto: sem branch, labels, pessoas nem link no hover


@com_node
def test_pr_antigo_mostra_o_contexto_como_valor_entregue(tmp_path):
    dados = _dados_do_pop()
    pr = next(p for p in dados["github"]["prs"] if p["number"] == 70)
    pr["resumo"] = {"antes": None, "depois": None, "contexto": "O quadro ganha <b>uma</b> coluna."}
    pop = _app(tmp_path, "popDoPr('70', S.data, { fmtDT, depVer })", dados=dados)
    assert '<span class="fx-k">valor entregue</span><p>O quadro ganha &lt;b&gt;uma&lt;/b&gt; coluna.</p>' in pop
    assert "<em>Antes</em>" not in pop


@com_node
def test_sem_resumo_o_titulo_fica_no_lugar(tmp_path):
    pop = _app(tmp_path, "popDoPr('70', S.data, { fmtDT, depVer })", dados=_dados_do_pop())
    assert '<p class="pr-pop-tit">feat(atas): exportar PDF</p>' in pop
    assert "valor entregue" not in pop


@com_node
def test_hover_do_entregue_diz_que_o_merge_e_a_entrega(tmp_path):
    dados = json.loads(json.dumps(DADOS))
    dados["github"]["prs"].append({**_pr(95, "MERGED", []), "merged_at": "2026-10-06T04:20:00Z"})
    dados["fases"]["prs"]["95"] = _fase_pr("entregue", 0, {"desde": "2026-10-06T04:20:00Z"})
    pop = _app(tmp_path, "popDoPr('95', S.data, { fmtDT, depVer })", dados=dados)
    assert "<b>PR #95 · Entregue</b>" in pop
    assert '<p class="pr-pop-rodape">sem issue · ferramenta, sem versão · 6 out, 04:20</p>' in pop


@com_node
def test_hover_do_aberto_mostra_dias_na_coluna_e_conflito(tmp_path):
    pop = _app(tmp_path, "popDoPr('81', S.data, { fmtDT, depVer })")
    assert "<b>PR #81 · CI vermelho</b>" in pop
    assert "5 dias na coluna · conflito com a main" in pop


@com_node
def test_clique_fixa_o_resumo_com_link_do_github_e_da_issue(tmp_path):
    html = _app(tmp_path, hash_inicial="#prs/70", dados=_dados_do_pop())
    fixo = re.search(r'<div class="st-pop pr-pop pr-pop-fixo" data-n="70"[^>]*>(.*?)</div>', html, re.S)  # o resumo não tem div dentro
    assert fixo, "o PR do hash abre o resumo fixo"
    corpo = fixo.group(1)
    assert "feat(atas): exportar PDF" in corpo
    assert 'href="https://github.com/x/y/pull/70" target="_blank"' in corpo
    assert 'href="#issues/901"' in corpo


@com_node
def test_sem_pr_no_hash_o_pop_vem_vazio_e_escondido(tmp_path):
    html = _app(tmp_path)
    assert '<div class="st-pop pr-pop" hidden></div>' in html
    assert "pr-pop-fixo" not in html
