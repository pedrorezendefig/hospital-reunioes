"""Aba Produção do Hospital OS (issue #945, ADR 0062, decisões 2 e 8).

A aba lê só `history.json` e `state.json` da `origin/main`: no topo, a versão
no ar e os serviços com o health; abaixo, uma linha por versão (deploys da
mesma versão juntos), a mais recente primeiro e sem teto. Aberta, a versão
mostra PRs, issues, migration, health, duração, env e notas, com chips que
navegam dentro do painel. O coletor não lê mais o CHANGELOG (apagado no #939).

O app.js roda de verdade no Node (molde do test_router.py): DOM mínimo de
mentira, `location`/`history` que guardam o hash e o `fetch` do /api/data
respondendo com o payload do teste. O CSS segue lido como texto, no bloco
delimitado da aba (padrão Baseline, issue 259).
"""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

DASH = Path(__file__).resolve().parents[1]
STATIC = DASH / "static"
CSS = (STATIC / "style.css").read_text(encoding="utf-8")
APP_JS = (STATIC / "app.js").read_text(encoding="utf-8")
sys.path.insert(0, str(DASH))

import collect  # noqa: E402

com_node = pytest.mark.skipif(not shutil.which("node"), reason="node ausente")


# ---------- coletor: só history.json e state.json ----------


def test_coletor_le_da_origin_main_so_o_history_e_o_state_e_nao_tem_changelog(monkeypatch, tmp_path):
    deploy = tmp_path / "docs" / "spec" / "deploy"
    deploy.mkdir(parents=True)
    (deploy / "history.json").write_text(json.dumps({"deploys": [{"app_version": "0.163.4"}]}))
    (deploy / "state.json").write_text(json.dumps({"last_app_version": "0.163.4", "services": []}))
    pedidos = []

    def run(cmd, cwd, timeout=None):
        pedidos.append(" ".join(cmd))
        raise RuntimeError("offline")  # git e gh fora: o coletor cai no clone

    monkeypatch.setattr(collect, "_run", run)
    data = collect.collect(tmp_path)

    assert [p for p in pedidos if p.startswith("git show")] == [
        "git show origin/main:docs/spec/deploy/state.json",
        "git show origin/main:docs/spec/deploy/history.json",
    ]
    assert data["history"] == [{"app_version": "0.163.4", "pr_numbers": [], "issue_numbers": []}]
    assert data["state"]["last_app_version"] == "0.163.4"
    assert "changelog" not in data
    assert not hasattr(collect, "_parse_changelog")


# ---------- front: o app.js inteiro no Node ----------


def _deploy(versao, sha, *, at, prs=(), issues=(), result="healthy", dur=120, migrations=(), notes="", env=()):
    """Deploy no shape do history.json, já correlacionado pelo coletor."""
    return {
        "at": at,
        "sha": sha,
        "app_version": versao,
        "subject": f"onda da {versao or sha}",
        "raw_subject": "chore(deploy): registro",
        "scope": ["backend"],
        "prds": [],
        "result": result,
        "duration_seconds": dur,
        "services_touched": ["backend"],
        "env_changes": list(env),
        "migrations_applied": list(migrations),
        "rollback_target_sha": None,
        "notes": notes,
        "pr_numbers": list(prs),
        "issue_numbers": list(issues),
    }


def _servico(sid, status, http=200, ms=140):
    return {
        "id": sid,
        "domain": f"{sid}.exemplo",
        "status": status,
        "last_deploy_at": "2026-10-06T13:38:54-03:00",
        "last_health_check": {"at": "2026-10-06T16:38:54Z", "latency_ms": ms, "http_status": http, "body_ok": http == 200},
    }


ENV_APP_VERSION = {"service": "backend", "action": "update", "keys": ["APP_VERSION"]}

# history.json mais recente primeiro (o rabo grava em [0]); a 0.161.0 subiu
# duas vezes, uma com "v" e outra sem, e o deploy sem versão vira linha própria
HISTORY = [
    _deploy("0.163.4", "aaa1111", at="2026-10-06T16:38:54Z", prs=[70], issues=[904], dur=57),
    _deploy(
        "v0.161.0",
        "ccc3333",
        at="2026-10-05T18:00:00Z",
        prs=[69],
        issues=[903],
        dur=45,
        notes="redeploy depois do health vermelho",
        env=[ENV_APP_VERSION],
    ),
    _deploy(
        "0.161.0",
        "bbb2222",
        at="2026-10-05T17:00:00Z",
        prs=[68],
        issues=[902],
        result="failed",
        dur=300,
        migrations=["114_migracoes_aplicadas.sql"],
        notes="primeira subida da onda",
    ),
    _deploy(None, "ddd4444", at="2026-10-05T14:46:19Z"),
    _deploy("0.160.0", "eee5555", at="2026-10-04T10:00:00Z", prs=[60]),
]


def _iss(n, *, state="OPEN"):
    return {
        "number": n,
        "title": f"Fatia {n}",
        "state": state,
        "labels": [],
        "assignees": [],
        "author": "ana",
        "url": f"https://github.com/x/y/issues/{n}",
        "body": f"corpo da {n}",
        "created_at": "2026-10-01T10:00:00Z",
        "closed_at": "2026-10-05T18:00:00Z" if state == "CLOSED" else None,
        "blocked_by": [],
        "parent": None,
        "children": [],
        "is_prd": False,
        "criteria": {"done": 0, "total": 0},
        "prs": [],
        "deploys": [],
    }


DADOS = {
    "generated_at": "2026-10-06T17:00:00Z",
    "repo_url": "https://github.com/x/y",
    "repo_slug": "x/y",
    "github": {"error": None, "error_kind": None, "issues": [_iss(903, state="CLOSED")], "prs": [], "prds": []},
    "fases": {
        "issues": {
            "903": {
                "fase": "em_producao",
                "sub": None,
                "branch": None,
                "pr": 69,
                "sinal": None,
                "tentativas": [],
                "versao": "0.161.0",
                "em_producao_em": "2026-10-05T18:00:00Z",
            }
        },
        "prs": {},
        "timelines": {},
        "ondas": {},
        "funil": {"total": {}, "por_responsavel": {}},
    },
    "history": HISTORY,
    "state": {
        "updated_at": "2026-10-06T13:38:54-03:00",
        "last_app_version": "0.163.4",
        "services": [
            _servico("backend", "healthy", ms=143),
            _servico("frontend", "healthy", ms=151),
            _servico("supabase", "warning", http=None, ms=None),
        ],
    },
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
globalThis.setInterval = () => 0;
globalThis.fetch = url => url.startsWith('/api/data')
  ? Promise.resolve({ json: () => Promise.resolve(_DADOS) })
  : new Promise(() => {});
const _esperar = () => new Promise(r => setTimeout(r, 0));
/* clique de verdade: o mesmo ouvinte delegado que o navegador chama no #view */
function _clicar(dataset) {
  const alvo = { dataset, classList: { contains: () => false } };
  const ev = { target: { closest: sel => (sel === '[data-act]' ? alvo : null) } };
  _view._ouvintes.forEach(fn => fn(ev));
}
/* o endereço trocado por fora: link do chip, voltar do navegador, URL colada */
function _navegar(hash) {
  location.hash = hash;
  (_janela.hashchange || []).forEach(fn => fn());
}
"""


def _app(tmp_path, expr, antes="", hash_inicial="#producao", dados=None):
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
    out = subprocess.run(["node", str(arq)], capture_output=True, text=True, check=False, env={**os.environ, "TZ": "UTC"})
    assert out.returncode == 0, out.stderr
    linha = [x for x in out.stdout.splitlines() if x.startswith("@@")][-1]
    return json.loads(linha[2:])


def _versoes(html):
    """(rótulo da versão, em destaque?, html do card) de cada versão, na ordem da tela."""
    return [
        (re.search(r'class="pd-ver[^"]*">([^<]*)<', m.group(0)).group(1), 'aria-current="true"' in m.group(1), m.group(0))
        for m in re.finditer(r"(<article[^>]*>)[\s\S]*?</article>", html)
    ]


def _chips(html):
    """{texto: href} de cada chip que é link."""
    return {m.group(2): m.group(1) for m in re.finditer(r'<a class="chip[^"]*" href="([^"]*)"[^>]*>([^<]*)</a>', html)}


# ---------- lista de versões ----------


@com_node
def test_producao_lista_uma_linha_por_versao_a_mais_recente_primeiro(tmp_path):
    html = _app(tmp_path, "_view.innerHTML")
    assert [v for v, _, _ in _versoes(html)] == ["v0.163.4", "v0.161.0", "ddd4444", "v0.160.0"]


@com_node
def test_producao_mostra_o_history_inteiro_sem_teto(tmp_path):
    # o history.json perdeu o teto de 50 no #939; a aba não pode cortar de novo
    longo = [_deploy(f"0.{200 - n}.0", f"{n:07d}", at="2026-10-01T10:00:00Z") for n in range(75)]
    html = _app(tmp_path, "_view.innerHTML", dados={**DADOS, "history": longo})
    versoes = [v for v, _, _ in _versoes(html)]
    assert len(versoes) == 75
    assert (versoes[0], versoes[-1]) == ("v0.200.0", "v0.126.0")


@com_node
def test_versao_aberta_mostra_prs_issues_migration_health_duracao_env_e_notas(tmp_path):
    fechada, aberta = _app(
        tmp_path,
        "[_fechada, _view.innerHTML]",
        antes="const _fechada = _view.innerHTML; _clicar({ act: 'dep', i: '1' });",
    )
    _, _, card_fechado = _versoes(fechada)[1]
    rotulo, _, card = _versoes(aberta)[1]
    assert rotulo == "v0.161.0"
    # o que entrou nas duas subidas da versão, com chips que ficam no painel
    assert _chips(card) == {"PR #69": "#prs/69", "PR #68": "#prs/68", "#903": "#issues/903", "#902": "#issues/902"}
    assert "⛁ 114_migracoes_aplicadas.sql" in card
    # cada deploy da versão: health, build, commit, env e notas
    deploys = re.findall(r'<div class="pd-dep">[\s\S]*?</p>\s*</div>', card)
    assert len(deploys) == 2
    novo, velho = deploys
    assert ">healthy<" in novo and "45s" in novo and "ccc3333" in novo
    assert "env: backend update APP_VERSION" in novo and "redeploy depois do health vermelho" in novo
    assert ">failed<" in velho and "5m00s" in velho and "bbb2222" in velho
    assert "primeira subida da onda" in velho and "env:" not in velho
    # fechada, a versão não mostra o miolo dos deploys
    for so_aberta in ("pd-dep", "redeploy depois", "primeira subida", "env:", "bbb2222"):
        assert so_aberta not in card_fechado, so_aberta


# ---------- faixa do topo: state.json ----------


@com_node
def test_faixa_do_topo_mostra_a_versao_no_ar_e_cada_servico_com_o_health_do_state(tmp_path):
    # a versão no ar vem do state.json, não do topo do history
    estado = {**DADOS["state"], "last_app_version": "0.170.0"}
    html = _app(tmp_path, "_view.innerHTML", dados={**DADOS, "state": estado})
    faixa = re.search(r'<section class="prod-band[\s\S]*?</section>', html).group(0)
    celulas = re.findall(
        r'class="prod-cell rv ?([^"]*)"[^>]*>\s*<div class="prod-v">([^<]*)</div>\s*'
        r'<div class="prod-k">([^<]*)</div>\s*<div class="prod-s">([^<]*)</div>',
        faixa,
    )
    assert celulas == [
        ("", "v0.170.0", "no ar", "atualizado 6 out, 16:38"),
        ("prod-ok", "healthy", "backend", "HTTP 200 · 143 ms · 6 out, 16:38"),
        ("prod-ok", "healthy", "frontend", "HTTP 200 · 151 ms · 6 out, 16:38"),
        ("prod-warn", "warning", "supabase", "sem HTTP · 6 out, 16:38"),
    ]
    assert "history.json + state.json" in faixa


def _bloco_producao():
    """O bloco de CSS delimitado da aba Produção, do marcador de abertura ao de fim."""
    m = re.search(r"/\* =+ PRODUÇÃO[^*]*\*/(.*?)/\* =+ fim PRODUÇÃO[^*]*\*/", CSS, re.S)
    assert m, "style.css sem bloco delimitado da aba Produção (issue 259)"
    return m.group(1)


def _regra(css: str, seletor: str) -> str:
    m = re.search(re.escape(seletor) + r"\{[^}]*\}", css)
    assert m, f"regra {seletor} ausente"
    return m.group(0)


# ---------- faixa navy (padrão Baseline, issue 259) ----------


def test_faixa_do_topo_em_fundo_navy():
    banda = _regra(_bloco_producao(), ".prod-band")
    assert "var(--navy)" in banda, "faixa do topo sem fundo navy"


def test_celula_com_borda_superior_translucida_valor_gigante_e_rotulo_65():
    bloco = _bloco_producao()
    celula = _regra(bloco, ".prod-cell")
    assert "border-top" in celula and "var(--w20)" in celula, "célula sem borda superior branca translúcida a 20%"
    valor = _regra(bloco, ".prod-v")
    assert "font-weight:500" in valor, "valor da célula fora do peso 500"
    assert "clamp(" in valor, "valor da célula sem escala gigante"
    rotulo = _regra(bloco, ".prod-k")
    assert "var(--w65)" in rotulo, "rótulo da célula fora do branco a 65%"


def test_celulas_com_reveal_escalonado_por_indice():
    m = re.search(r'class="prod-cell[^"]*\brv\b[^"]*"[^>]*--i:', APP_JS)
    assert m, "células da faixa sem reveal escalonado (.rv com --i por índice)"


def test_cabecalho_da_faixa_usa_eyebrow():
    m = re.search(r"prod-band[\s\S]{0,400}?class=\"eyebrow\"", APP_JS)
    assert m, "faixa navy sem cabeçalho eyebrow"


# ---------- lista de versões em cartões claros ----------


def test_versoes_em_cartoes_claros_com_hairlines():
    bloco = _bloco_producao()
    cartao = _regra(bloco, ".pd-card")
    assert "var(--hairline)" in cartao, "cartão da versão sem hairline dos tokens"
    corpo = _regra(bloco, ".pd-body")
    assert "var(--hairline)" in corpo, "corpo expandido sem hairline de separação"
    entre = _regra(bloco, ".pd-dep + .pd-dep")
    assert "var(--hairline)" in entre, "deploys da mesma versão sem hairline entre eles"


# ---------- sparkline ----------


def test_sparkline_usa_somente_cores_de_token():
    m = re.search(r"function spark[\s\S]*?\n\}", APP_JS)
    assert m, "sparkline sumiu do app.js"
    corpo = m.group(0)
    assert "var(--" in corpo, "sparkline sem cores de token"
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", corpo), "cor hex fixa no sparkline"
    assert not re.search(r"\b(?:rgba?|hsla?)\(", corpo), "rgb()/hsl() no sparkline"


# ---------- semânticas nos dois planos ----------


def test_verde_vermelho_ambar_legiveis_sobre_navy():
    """Sobre o navy os status clareiam por color-mix a partir dos tokens
    (nenhuma cor nova); no plano claro valem os washes da fundação."""
    bloco = _bloco_producao()
    for cor in ("green", "red", "amber"):
        assert re.search(r"color-mix\([^)]*var\(--" + cor + r"\)[^)]*\)", bloco), (
            f"status {cor} sem variante legível sobre navy"
        )


def test_washes_da_fundacao_seguem_disponiveis_no_plano_claro():
    for classe in (".b-green", ".b-red", ".b-amber"):
        assert classe in CSS, f"badge {classe} sumiu do plano claro"


# ---------- nenhuma cor fixa fora dos tokens ----------


def test_bloco_producao_sem_cor_fixa():
    bloco = _bloco_producao()
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", bloco), "cor hex no bloco da aba"
    assert not re.search(r"\b(?:rgba?|hsla?)\(", bloco), "rgb()/hsl() no bloco da aba"
