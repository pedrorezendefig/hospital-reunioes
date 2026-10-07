"""Aba Produção do Hospital OS (issue #945, ADR 0062, decisões 2 e 8).

No topo, a versão no ar e os serviços com o health (`state.json` da
`origin/main`); o semáforo do mast tem três estados (verde, âmbar, vermelho).
Abaixo, a linha do tempo do repositório: merges do GitHub (`gh`, com
`mergedBy`) e deploys do `history.json` numa trilha só, costurados pelo número
do PR. Cada deploy é um card (versão, subject, resultado, responsável, PRs com a
bolinha de quem mergeou, issues, migrations e a barra das etapas); merge que
não entrou em deploy é um nó tracejado na cor da pessoa. Aberto, o deploy mostra
commit, env e notas. Filtro por pessoa no dropdown da aba Issues. O coletor não
lê mais as notas de versão em Markdown (o arquivo saiu no #939) e o /api/data
não tem mais o campo `changelog`.

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
from datetime import UTC, datetime
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
        "last_health_check": {
            "at": "2026-10-06T16:38:54Z",
            "latency_ms": ms,
            "http_status": http,
            "body_ok": http == 200,
        },
    }


ENV_APP_VERSION = {"service": "backend", "action": "update", "keys": ["APP_VERSION"]}

# history.json mais recente primeiro (a subida grava em [0]); a 0.161.0 subiu
# duas vezes, uma com "v" e outra sem, e o deploy sem versão vira linha própria
HISTORY = [
    # entrada nova: a subida mediu as etapas e gravou quem a rodou
    {
        **_deploy("0.163.4", "aaa1111", at="2026-10-06T16:38:54Z", prs=[70], issues=[904], dur=57),
        "etapas": {"merge_s": 4, "build_s": {"backend": 34, "frontend": None}, "health_s": 2},
        "responsavel": "pedro",
    },
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


def _pr(n, *, merged, created, por, closes=(), labels=(), title=None):
    """PR mergeado no shape do coletor (`_gh_prs`), com `mergeado_por` e `labels`."""
    return {
        "number": n,
        "title": title or f"feat(x): fatia {n}",
        "state": "MERGED",
        "merged_at": merged,
        "head_ref": f"feature/fatia-{n}",
        "url": f"https://github.com/x/y/pull/{n}",
        "closes": list(closes),
        "created_at": created,
        "closed_at": merged,
        "author": por,
        "is_draft": False,
        "mergeado_por": por,
        "labels": list(labels),
        "checks": [],
        "merge_state": None,
        "reviews": [],
        "comentarios": None,
        "vereditos": [],
    }


AGORA = datetime(2026, 10, 6, 17, 30, tzinfo=UTC)
FIX, FEAT, CHORE = ["type:fix"], ["type:feature"], ["type:chore"]

# 70, 69, 68 e 60 entraram em deploys; 71 é ferramenta (type:chore, nenhum deploy);
# 72 é do app e espera o próximo deploy; 50 é anterior ao deploy mais antigo
PRS = [
    _pr(72, merged="2026-10-06T17:20:00Z", created="2026-10-06T12:00:00Z", por="bia", closes=[905], labels=FIX),
    _pr(
        71,
        merged="2026-10-06T17:10:00Z",
        created="2026-10-06T16:00:00Z",
        por="ana",
        labels=CHORE,
        title="chore(skills): afina o router",
    ),
    _pr(70, merged="2026-10-06T16:30:00Z", created="2026-10-06T10:00:00Z", por="ana", closes=[904], labels=FIX),
    _pr(69, merged="2026-10-05T17:50:00Z", created="2026-10-04T09:00:00Z", por="bia", closes=[903], labels=FEAT),
    _pr(68, merged="2026-10-05T16:40:00Z", created="2026-10-05T08:00:00Z", por="bia", closes=[902], labels=FEAT),
    _pr(60, merged="2026-10-04T09:50:00Z", created="2026-10-03T09:00:00Z", por="ana", closes=[901], labels=FIX),
    _pr(50, merged="2026-09-01T09:50:00Z", created="2026-08-30T09:00:00Z", por="ana", labels=CHORE),
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
    "github": {"error": None, "error_kind": None, "issues": [_iss(903, state="CLOSED")], "prs": PRS, "prds": []},
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
    # o que o coletor monta dos dois lados (merges do gh, deploys do history)
    "linha_do_tempo": collect._linha_do_tempo(HISTORY, PRS, agora=AGORA),
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


def _estado(*servicos):
    return {**DADOS, "state": {**DADOS["state"], "services": list(servicos)}}


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
    out = subprocess.run(
        ["node", str(arq)], capture_output=True, text=True, check=False, env={**os.environ, "TZ": "UTC"}
    )
    assert out.returncode == 0, out.stderr
    linha = [x for x in out.stdout.splitlines() if x.startswith("@@")][-1]
    return json.loads(linha[2:])


def _versoes(html):
    """(rótulo da versão, em destaque?, html do card) de cada versão, na ordem da tela."""
    return [
        (
            re.search(r'class="pd-ver[^"]*">([^<]*)<', m.group(0)).group(1),
            'aria-current="true"' in m.group(1),
            m.group(0),
        )
        for m in re.finditer(r"(<article[^>]*>)[\s\S]*?</article>", html)
    ]


def _chips(html):
    """{texto: href} de cada chip que é link (a bolinha da pessoa, se houver, sai do texto)."""
    return {
        re.sub(r"<[^>]+>", "", m.group(2)).strip(): m.group(1)
        for m in re.finditer(r'<a class="chip[^"]*" href="([^"]*)"[^>]*>(.*?)</a>', html)
    }


# ---------- a trilha: um card por deploy, nós para os merges sem deploy ----------


def _nos(html):
    """(tipo, html) de cada nó da trilha, na ordem da tela."""
    return [(m.group(1), m.group(0)) for m in re.finditer(r'<li class="lt-no lt-(deploy|merge)[\s\S]*?</li>', html)]


@com_node
def test_trilha_mistura_merges_e_deploys_do_mais_recente_ao_mais_antigo(tmp_path):
    html = _app(tmp_path, "_view.innerHTML")
    # um card por deploy (a 0.161.0 subiu duas vezes: dois cards), os dois merges
    # de depois do último deploy como nós em cima; 70, 69, 68 e 60 entraram em
    # deploys e não viram nó (ficam dentro do card); 50 é anterior à janela
    assert [t for t, _ in _nos(html)] == ["merge", "merge", "deploy", "deploy", "deploy", "deploy", "deploy"]
    assert [v for v, _, _ in _versoes(html)] == ["v0.163.4", "v0.161.0", "v0.161.0", "ddd4444", "v0.160.0"]
    assert "PR #50" not in html
    nos = [h for _, h in _nos(html)]
    assert "PR #72" in nos[0] and "PR #71" in nos[1]


@com_node
def test_merge_sem_deploy_e_no_tracejado_na_cor_de_quem_mergeou_com_a_etiqueta(tmp_path):
    html = _app(tmp_path, "_view.innerHTML")
    ferramenta = next(h for t, h in _nos(html) if t == "merge" and "PR #71" in h)
    app = next(h for t, h in _nos(html) if t == "merge" and "PR #72" in h)
    # a cor da pessoa entra pelo --pessoa do nó (pessoas.js); o contorno tracejado é do CSS
    assert re.search(r'<li class="lt-no lt-merge rv" style="--i:\d+;--pessoa:var\(--[a-z-]+\)"', ferramenta)
    assert "só merge · ferramenta" in ferramenta and "chore(skills): afina o router" in ferramenta
    assert "mergeado · sem deploy" in app and "#issues/905" in app
    assert ">ana<" in ferramenta and ">bia<" in app
    assert "mergeado · sem deploy" not in ferramenta and "ferramenta" not in app


@com_node
def test_card_do_deploy_mostra_responsavel_prs_com_a_bolinha_issues_migration_e_etapas(tmp_path):
    html = _app(tmp_path, "_view.innerHTML")
    versoes = _versoes(html)
    _, _, novo = versoes[0]
    # responsável do history (quem rodou a subida) e não quem mergeou o PR
    assert ">pedro<" in novo and ">ana<" not in novo
    # o PR do lote vira chip com a bolinha de quem mergeou, dentro do card
    chip = re.search(r'<a class="chip chip-pr" href="#prs/70"[^>]*>[\s\S]*?</a>', novo).group(0)
    assert "pessoa-dot" in chip and re.search(r'style="--pessoa:var\(--[a-z-]+\)"', chip)
    assert _chips(novo)["#904"] == "#issues/904"
    # etapas medidas pela subida mais as derivadas do GitHub: aberto, fila, merge, build, health
    assert re.findall(r'class="etapa etapa-(\w+)"', novo) == ["aberto", "fila", "merge", "build", "health"]
    assert "aberto 6h30m" in novo and "fila até produção 8m54s" in novo and "build 34s" in novo
    assert "merge 4s" in novo and "health 2s" in novo
    _, _, velho = versoes[2]
    assert "⛁ 114_migracoes_aplicadas.sql" in velho and ">failed<" in velho and ">bia<" in velho
    # entrada antiga, sem etapas: só aberto, fila e o total da subida
    assert re.findall(r'class="etapa etapa-(\w+)"', velho) == ["aberto", "fila", "total"]
    assert "total 5m00s" in velho
    _, _, sem_versao = versoes[3]
    assert re.findall(r'class="etapa etapa-(\w+)"', sem_versao) == ["total"]


@com_node
def test_rotulo_so_no_segmento_largo_o_bastante_e_tooltip_em_todos(tmp_path):
    html = _app(tmp_path, "_view.innerHTML")
    _, _, novo = _versoes(html)[0]
    segmentos = re.findall(
        r'<span class="etapa etapa-(\w+)" style="flex-basis:([\d.]+)%" title="([^"]*)">(.*?)</span>', novo
    )
    assert [s[0] for s in segmentos] == ["aberto", "fila", "merge", "build", "health"]
    for _, pct, title, miolo in segmentos:
        assert title, "todo segmento tem tooltip"
        assert (float(pct) >= 14) == ("etapa-rot" in miolo), (pct, miolo)
    assert any("etapa-rot" in s[3] for s in segmentos) and not all("etapa-rot" in s[3] for s in segmentos)
    assert "backend 34s" in next(t for k, _, t, _ in segmentos if k == "build")


@com_node
def test_deploy_aberto_mostra_commit_env_e_notas_e_fechado_nao(tmp_path):
    fechada, aberta = _app(
        tmp_path,
        "[_fechada, _view.innerHTML]",
        antes="const _fechada = _view.innerHTML; _clicar({ act: 'dep', i: '1' });",
    )
    _, _, card_fechado = _versoes(fechada)[1]
    rotulo, _, card = _versoes(aberta)[1]
    assert rotulo == "v0.161.0"
    assert _chips(card) == {"PR #69": "#prs/69", "#903": "#issues/903"}
    [detalhe] = re.findall(r'<div class="pd-dep">[\s\S]*?</p>\s*</div>', card)
    assert "ccc3333" in detalhe and "45s" in detalhe
    assert "env: backend update APP_VERSION" in detalhe and "redeploy depois do health vermelho" in detalhe
    # o outro deploy da versão é card próprio e segue fechado
    _, _, outro = _versoes(aberta)[2]
    assert 'class="pd-body"' not in outro and "primeira subida" not in outro
    for so_aberta in ("pd-dep", "redeploy depois", "env:"):
        assert so_aberta not in card_fechado, so_aberta


@com_node
def test_filtro_por_pessoa_recorta_merges_e_deploys_e_vai_para_o_hash(tmp_path):
    html, hash_ = _app(tmp_path, "[_view.innerHTML, location.hash]", antes="_clicar({ act: 'lfresp', v: 'bia' });")
    # bia mergeou o 72 (sem deploy), o 69 e o 68 (deploys da 0.161.0); ana e pedro saem
    assert [t for t, _ in _nos(html)] == ["merge", "deploy", "deploy"]
    assert [v for v, _, _ in _versoes(html)] == ["v0.161.0", "v0.161.0"]
    trilha = html.split('<ol class="lt">')[1]
    assert "PR #71" not in trilha and "v0.163.4" not in trilha
    assert hash_ == "#producao?resp=bia"
    assert 'class="dd-opt on"' in html and 'data-act="lflimpar"' in html
    # a faceta conta eventos de cada pessoa: ana mergeou 71, 70 e 60 e responde pela 0.160.0
    assert re.search(r'data-v="ana"[^>]*>[\s\S]*?<span class="dd-n">4</span>', html)


@com_node
def test_hash_com_pessoa_abre_a_aba_ja_filtrada(tmp_path):
    html, resp = _app(tmp_path, "[_view.innerHTML, S.fProd.resp]", hash_inicial="#producao?resp=ana")
    assert resp == "ana"
    # o 71 (ferramenta), o 70 (entrou na 0.163.4, que é do pedro e sai do recorte: o
    # merge volta a aparecer como nó, dizendo onde está no ar) e a 0.160.0 (60, da ana)
    assert [t for t, _ in _nos(html)] == ["merge", "merge", "deploy"]
    no_70 = next(h for t, h in _nos(html) if t == "merge" and "PR #70" in h)
    assert "no ar na v0.163.4" in no_70


# ---------- #producao/vX e o chip de versão ----------


def _abertas(html):
    """(versão, em destaque?) das versões abertas, na ordem da tela."""
    return [(v, destaque) for v, destaque, card in _versoes(html) if "pd-body" in card]


@com_node
@pytest.mark.parametrize(
    "versao, sha",
    [
        ("v0.161.0", "ccc3333"),  # a versão subiu duas vezes: abre a subida mais recente
        ("v0.160.0", "eee5555"),  # depois do grupo: a posição na tela não é o índice no history
    ],
)
def test_hash_da_versao_abre_o_deploy_mais_recente_dela_com_destaque(tmp_path, versao, sha):
    html = _app(tmp_path, "_view.innerHTML", hash_inicial=f"#producao/{versao}")
    assert _abertas(html) == [(versao, True)]
    assert [v for v, destaque, _ in _versoes(html) if destaque] == [versao]
    card = next(card for v, _, card in _versoes(html) if v == versao)
    assert sha in card.split('class="pd-body"')[1]


@com_node
def test_chip_de_versao_no_card_da_issue_leva_a_versao_aberta_com_destaque(tmp_path):
    href, tab, item, html = _app(
        tmp_path,
        "[_href, S.tab, S.item, _view.innerHTML]",
        hash_inicial="#issues",
        antes="""
        const _href = issueCard(S.data.github.issues[0], 0).match(/class="chip chip-versao" href="([^"]*)"/)[1];
        _navegar(_href);
        """,
    )
    assert href == "#producao/v0.161.0"
    assert (tab, item) == ("producao", "v0.161.0")
    assert _abertas(html) == [("v0.161.0", True)]


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
        ("prod-warn", "warning", "supabase", "sem verificação · 6 out, 16:38"),
    ]
    assert "history.json + state.json" in faixa


def _supabase(status, body_ok):
    """O supabase como a subida o grava agora: sem HTTP próprio, status pelo health do backend."""
    s = _servico("supabase", status, http=None, ms=None)
    s["health_path"] = None
    s["last_health_check"]["body_ok"] = body_ok
    return s


@com_node
def test_servico_sem_http_proprio_diz_via_backend_quando_o_health_do_backend_deu_ok(tmp_path):
    dados = _estado(_servico("backend", "healthy"), _supabase("healthy", True))
    html = _app(tmp_path, "_view.innerHTML", dados=dados)
    celulas = re.findall(r'<div class="prod-k">supabase</div>\s*<div class="prod-s">([^<]*)</div>', html)
    assert celulas == ["via backend · 6 out, 16:38"]
    # serviço com health_path e sem resposta segue "sem HTTP"
    dados = _estado({**_servico("backend", "warning", http=None, ms=None), "health_path": "/api/health"})
    html = _app(tmp_path, "_view.innerHTML", dados=dados)
    assert re.findall(r'<div class="prod-k">backend</div>\s*<div class="prod-s">([^<]*)</div>', html) == [
        "sem HTTP · 6 out, 16:38"
    ]


# ---------- semáforo do mast: verde, âmbar, vermelho ----------


def _mast(tmp_path, *servicos):
    html = _app(tmp_path, "_els['#mast-status'].innerHTML", dados=_estado(*servicos))
    m = re.search(r'<span class="dot ([^"]*)"></span>\s*<b>[^<]*</b>&nbsp;· prod ([^<]*)</span>', html)
    return m.group(1), m.group(2)


@com_node
def test_mast_verde_so_com_todos_healthy_e_checados(tmp_path):
    assert _mast(
        tmp_path, _servico("backend", "healthy"), _servico("frontend", "healthy"), _supabase("healthy", True)
    ) == ("ok pulse", "healthy")


@com_node
@pytest.mark.parametrize(
    "terceiro",
    [_supabase("warning", False), {**_servico("supabase", "healthy"), "last_health_check": None}],
    ids=["warning", "sem-check"],
)
def test_mast_ambar_com_warning_ou_sem_verificacao_e_ninguem_fora(tmp_path, terceiro):
    assert _mast(tmp_path, _servico("backend", "healthy"), _servico("frontend", "healthy"), terceiro) == (
        "warn",
        "2/3 ok",
    )


@com_node
@pytest.mark.parametrize(
    "ruim",
    [_servico("backend", "down"), _servico("backend", "unhealthy"), _servico("backend", "warning", http=503)],
    ids=["down", "unhealthy", "http-503"],
)
def test_mast_vermelho_so_com_servico_fora_ou_http_fora_de_2xx(tmp_path, ruim):
    assert _mast(tmp_path, ruim, _servico("frontend", "healthy"), _supabase("healthy", True)) == ("bad", "2/3 ok")


def test_dot_warn_na_cor_ambar_do_badge_warning():
    assert "var(--amber)" in _regra(CSS, ".dot.warn")
    assert "var(--amber)" in _regra(CSS, ".b-amber")
    assert "var(--amber)" in _regra(_bloco_producao(), ".prod-warn .prod-v")


# ---------- coletor: a linha do tempo ----------


def _evento(eventos, tipo, chave, valor):
    return next(e for e in eventos if e["tipo"] == tipo and e[chave] == valor)


def test_coletor_costura_merges_e_deploys_pelo_numero_do_pr_do_mais_recente_ao_mais_antigo():
    eventos = collect._linha_do_tempo(HISTORY, PRS, agora=AGORA)
    assert [e["at"] for e in eventos] == sorted((e["at"] for e in eventos), reverse=True)
    assert [e["tipo"] for e in eventos].count("deploy") == 5
    # merge que entrou num deploy aponta o sha dele; o de ferramenta e o que espera, não
    assert _evento(eventos, "merge", "pr", 70)["deploy_sha"] == "aaa1111"
    assert _evento(eventos, "merge", "pr", 71) == {
        "tipo": "merge",
        "at": "2026-10-06T17:10:00Z",
        "pr": 71,
        "titulo": "chore(skills): afina o router",
        "autor": "ana",
        "mergeado_por": "ana",
        "issues": [],
        "ferramenta": True,
        "deploy_sha": None,
    }
    espera = _evento(eventos, "merge", "pr", 72)
    assert (espera["ferramenta"], espera["deploy_sha"], espera["issues"]) == (False, None, [905])
    # merge anterior ao deploy mais antigo da janela fica de fora
    assert all(e.get("pr") != 50 for e in eventos)


def test_coletor_deriva_as_etapas_do_github_e_soma_as_do_history():
    eventos = collect._linha_do_tempo(HISTORY, PRS, agora=AGORA)
    novo = _evento(eventos, "deploy", "sha", "aaa1111")
    assert novo["etapas"] == {
        "aberto_s": 23400,
        "fila_s": 534,
        "merge_s": 4,
        "build_s": {"backend": 34, "frontend": None},
        "health_s": 2,
    }
    assert novo["responsavel"] == "pedro"  # quem rodou a subida manda sobre quem mergeou
    assert (novo["prs"], novo["issues"], novo["app_version"], novo["result"]) == ([70], [904], "0.163.4", "healthy")
    velho = _evento(eventos, "deploy", "sha", "bbb2222")
    assert velho["etapas"] == {"aberto_s": 31200, "fila_s": 1200}
    assert velho["responsavel"] == "bia" and velho["migrations_applied"] == ["114_migracoes_aplicadas.sql"]
    sem_pr = _evento(eventos, "deploy", "sha", "ddd4444")
    assert (sem_pr["etapas"], sem_pr["responsavel"], sem_pr["prs"]) == ({}, None, [])


def test_coletor_lista_os_responsaveis_quando_o_lote_tem_mais_de_um():
    lote = [{**HISTORY[0], "etapas": None, "responsavel": None, "pr_numbers": [70, 69]}]
    [deploy] = [e for e in collect._linha_do_tempo(lote, PRS, agora=AGORA) if e["tipo"] == "deploy"]
    assert deploy["responsavel"] == ["ana", "bia"]


def test_janela_e_60_dias_ou_40_deploys_o_que_for_maior():
    def deploys(n, dia):
        return [_deploy(f"0.{n - i}.0", f"{i:07d}", at=f"2026-{dia}T10:00:00Z", prs=[]) for i in range(n)]

    # 75 deploys antigos (fora dos 60 dias): ficam os 40 mais recentes
    antigos = deploys(75, "06-01")
    assert sum(e["tipo"] == "deploy" for e in collect._linha_do_tempo(antigos, [], agora=AGORA)) == 40
    # 75 deploys nos últimos 60 dias: ficam todos
    recentes = deploys(75, "10-01")
    assert sum(e["tipo"] == "deploy" for e in collect._linha_do_tempo(recentes, [], agora=AGORA)) == 75
    # sem deploy nenhum, os merges dos últimos 60 dias entram (o 50, de 1 de setembro, inclusive)
    assert [e["pr"] for e in collect._linha_do_tempo([], PRS, agora=AGORA)] == [72, 71, 70, 69, 68, 60, 50]


def test_coletor_pede_merged_by_e_labels_ao_gh_e_os_entrega_no_pr(monkeypatch):
    item = {
        "number": 1,
        "title": "t",
        "state": "MERGED",
        "mergedAt": "2026-10-06T17:10:00Z",
        "mergedBy": {"login": "ana", "id": "U_1", "is_bot": False},
        "labels": [{"name": "type:chore"}],
    }
    monkeypatch.setattr(collect, "_run", lambda cmd, cwd, timeout=None: json.dumps([item]))
    assert {"mergedBy", "labels"} <= set(collect.PR_FIELDS.split(","))
    [pr] = collect._gh_prs(DASH)
    assert (pr["mergeado_por"], pr["labels"]) == ("ana", ["type:chore"])


@com_node
def test_payload_leva_a_linha_do_tempo_e_a_aba_sem_ela_nao_quebra(tmp_path):
    html = _app(tmp_path, "_view.innerHTML", dados={k: v for k, v in DADOS.items() if k != "linha_do_tempo"})
    assert "nenhum merge nem deploy" in html and "prod-band" in html


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
