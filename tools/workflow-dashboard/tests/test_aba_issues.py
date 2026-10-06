"""Aba Issues do Hospital OS (issue #942, ADR 0062, decisões 3, 5 e 6).

Home do painel: funil das nove fases no topo (contagens do payload, clicável),
filtros em chips (estado, fase, responsável na cor da pessoa, PRD, labels por
prefixo, busca), chip `ready-for-human` com contador, card compacto e, aberto,
a linha do tempo datada. Responsável é só quem assumiu (assignee): "ninguém
assumiu" lista as issues sem assignee, mesmo que alguém tenha criado.

O app.js roda de verdade no Node, inteiro: o módulo é carregado com um DOM
mínimo de mentira, os cliques passam pelo mesmo ouvinte que o navegador usa e
o `fetch` só registra a URL (ou devolve a resposta pré-gravada do teste).
"""

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import urllib.request
from pathlib import Path

import pytest

DASH = Path(__file__).resolve().parents[1]
STATIC = DASH / "static"
APP_JS = (STATIC / "app.js").read_text(encoding="utf-8")
PESSOAS_JS = (STATIC / "pessoas.js").read_text(encoding="utf-8") if (STATIC / "pessoas.js").exists() else ""
INDEX = (STATIC / "index.html").read_text(encoding="utf-8")
CSS = (STATIC / "style.css").read_text(encoding="utf-8")
sys.path.insert(0, str(DASH))

com_node = pytest.mark.skipif(not shutil.which("node"), reason="node ausente")

FASES = [
    "triagem",
    "fila",
    "bloqueada",
    "em_andamento",
    "pr_aberto",
    "mergeada",
    "em_producao",
    "humana",
    "encerrada_sem_pr",
]
# Contagens que a lista de issues do teste não reproduz: o funil tem que ler o payload.
TOTAL = dict(zip(FASES, [31, 12, 4, 7, 5, 2, 260, 3, 40]))
DO_LUCAS = dict(zip(FASES, [0, 0, 1, 6, 2, 0, 9, 0, 0]))


def _fase(fase, **extra):
    base = {"fase": fase, "sub": None, "branch": None, "pr": None, "sinal": None, "tentativas": []}
    return {**base, "versao": None, "em_producao_em": None, **extra}


def _iss(n, *, state="OPEN", assignees=(), author="ana", labels=(), parent=None, children=(), criteria=(0, 0)):
    return {
        "number": n,
        "title": f"Fatia {n}",
        "state": state,
        "labels": list(labels),
        "assignees": list(assignees),
        "author": author,
        "url": f"https://github.com/x/y/issues/{n}",
        "body": f"corpo da {n}",
        "created_at": "2026-10-01T10:00:00Z",
        "closed_at": "2026-10-03T18:00:00Z" if state == "CLOSED" else None,
        "blocked_by": [],
        "parent": parent,
        "children": list(children),
        "is_prd": bool(children),
        "criteria": {"done": criteria[0], "total": criteria[1]},
        "prs": [],
        "deploys": [],
    }


ISSUES = [
    _iss(900, assignees=["pedrorezendefig"], author="pedrorezendefig", children=range(901, 906)),
    _iss(901, labels=["ready-for-agent", "type:feature", "fatia:M"], parent=900),
    _iss(902, assignees=["lucassampaioc1"], labels=["in-progress", "area:infra"], parent=900),
    _iss(903, assignees=["pedroribbe"], author="bia", labels=["type:fix"], parent=900, criteria=(3, 8)),
    _iss(904, state="CLOSED", assignees=["pedrorezendefig"], labels=["type:feature"], parent=900),
    _iss(905, author="pedrorezendefig", labels=["ready-for-human"], parent=900),
    _iss(910, author="bia", labels=["needs-triage"]),
    _iss(911, state="CLOSED", labels=["wontfix"]),
    _iss(912, state="CLOSED", labels=["ready-for-human"]),
]

TIMELINE_902 = [
    {"tipo": "criada", "em": "2026-10-01T10:00:00Z"},
    {"tipo": "designada", "em": "2026-10-02T13:45:00Z", "quem": "lucassampaioc1"},
    {"tipo": "branch", "em": None, "branch": "feat/x-902"},
]

DADOS = {
    "generated_at": "2026-10-06T10:00:00Z",
    "repo_url": "https://github.com/x/y",
    "repo_slug": "x/y",
    "github": {"error": None, "error_kind": None, "issues": ISSUES, "prs": [], "prds": [900]},
    "fases": {
        "issues": {
            "900": _fase("triagem"),
            "901": _fase("fila"),
            "902": _fase("em_andamento", sub="branch_criada", branch="feat/x-902"),
            "903": _fase(
                "pr_aberto",
                pr=77,
                sinal={"ci": "vermelho", "veredito": None, "conflito": False, "tentativa_anterior": False},
            ),
            "904": _fase("em_producao", pr=70, versao="0.163.4", em_producao_em="2026-10-03T18:05:00Z"),
            "905": _fase("humana"),
            "910": _fase("triagem"),
            "911": _fase("encerrada_sem_pr"),
            "912": _fase("humana"),
        },
        "prs": {},
        "timelines": {"902": TIMELINE_902},
        "ondas": {},
        "funil": {"total": TOTAL, "por_responsavel": {"lucassampaioc1": DO_LUCAS}},
    },
    "history": [],
    "state": {},
    "snapshots": [],
    "adrs": [],
}

# DOM mínimo: cada elemento guarda os próprios ouvintes; o #view é um só.
PRELUDIO = r"""
const _el = () => ({
  innerHTML: '', textContent: '', dataset: {}, style: {}, _ouvintes: [],
  classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } },
  addEventListener(tipo, fn) { this._ouvintes.push(fn); },
  querySelector: () => null, querySelectorAll: () => [], setAttribute() {}, closest: () => null,
});
const _view = _el();
globalThis.document = {
  querySelector: s => (s === '#view' ? _view : _el()),
  querySelectorAll: () => [], addEventListener() {}, body: _el(), activeElement: null, createElement: _el,
};
globalThis.window = { addEventListener() {}, scrollTo() {}, matchMedia: () => ({ matches: true }) };
globalThis.matchMedia = window.matchMedia;
globalThis.location = { hash: '' };
globalThis.history = { replaceState() {} };
globalThis.setInterval = () => 0;
const _buscas = [];
const _respostas = {};
globalThis.fetch = url => {
  _buscas.push(url);
  if (url in _respostas) return Promise.resolve({ json: () => Promise.resolve(_respostas[url]) });
  return new Promise(() => {});
};
/* clique de verdade: o mesmo ouvinte delegado que o navegador chama no #view */
function _clicar(dataset) {
  const alvo = { dataset, classList: { contains: () => false } };
  const ev = { target: { closest: sel => (sel === '[data-act]' ? alvo : null) } };
  _view._ouvintes.forEach(fn => fn(ev));
}
const _esperar = () => new Promise(r => setTimeout(r, 0));
"""


def _modulo_app():
    """app.js com os imports relativos apontando para o static/ (o .mjs roda do tmp)."""
    return APP_JS.replace("from './", f"from '{STATIC.as_uri()}/")


def _rodar(tmp_path, expr, antes="", dados=None):
    prog = (
        PRELUDIO
        + _modulo_app()
        + f"\nS.data = {json.dumps(dados or DADOS)};\n{antes}\n"
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


def _botoes(html, act):
    """(data-v, tag de abertura, conteúdo) de cada <button data-act=act>."""
    out = []
    for m in re.finditer(r"(<button[^>]*>)(.*?)</button>", html, re.DOTALL):
        tag = m.group(1)
        if f'data-act="{act}"' in tag:
            v = re.search(r'data-v="([^"]*)"', tag)
            out.append((v.group(1) if v else None, tag, m.group(2)))
    return out


def _passos_do_funil(html):
    passos = []
    for v, tag, corpo in _botoes(html, "ffase"):
        n = re.search(r'class="funil-n">(\d+)<', corpo)
        classes = re.search(r'class="([^"]*)"', tag).group(1).split()
        passos.append((v, int(n.group(1)), "on" in classes))
    return passos


def _cards(html):
    """Números das issues na lista, na ordem em que aparecem."""
    return [int(n) for n in re.findall(r'class="iss-head" data-act="iss" data-n="(\d+)"', html)]


def _lista(tmp_path, antes):
    return _cards(_rodar(tmp_path, "issueListHtml()", antes=antes))


# ---------- abre na aba Issues, com o funil ----------


@com_node
def test_painel_abre_na_aba_issues(tmp_path):
    assert _rodar(tmp_path, "S.tab") == "issues"


@com_node
def test_hash_das_abas_aposentadas_cai_em_issues(tmp_path):
    tabs = _rodar(tmp_path, "abas", antes="const abas = ['plano', 'pendencias', 'guia'].map(t => (setTab(t), S.tab));")
    assert tabs == ["issues", "issues", "issues"]


@com_node
def test_funil_mostra_as_nove_fases_com_as_contagens_do_payload(tmp_path):
    passos = _passos_do_funil(_rodar(tmp_path, "renderIssues()"))
    assert [p[0] for p in passos] == FASES
    assert {p[0]: p[1] for p in passos} == TOTAL
    assert not any(p[2] for p in passos)


@com_node
def test_clicar_numa_fase_filtra_a_lista_e_marca_o_chip(tmp_path):
    html = _rodar(tmp_path, "_view.innerHTML", antes="setTab('issues'); _clicar({ act: 'ffase', v: 'fila' });")
    assert [p[0] for p in _passos_do_funil(html) if p[2]] == ["fila"]
    cards = _cards(html)
    assert 901 in cards
    assert not {902, 903, 904, 905, 910, 911, 912} & set(cards)


@com_node
def test_clicar_de_novo_na_fase_marcada_desliga_o_filtro(tmp_path):
    antes = "setTab('issues'); _clicar({ act: 'ffase', v: 'fila' }); _clicar({ act: 'ffase', v: 'fila' });"
    html = _rodar(tmp_path, "_view.innerHTML", antes=antes)
    assert not any(p[2] for p in _passos_do_funil(html))
    assert {910, 911, 912} <= set(_cards(html))


@com_node
def test_sem_gh_o_funil_avisa_em_vez_de_zerar(tmp_path):
    dados = {**DADOS, "github": {**DADOS["github"], "error": "gh fora", "issues": []}, "fases": None}
    html = _rodar(tmp_path, "renderIssues()", dados=dados)
    assert _passos_do_funil(html) == []
    assert "funil" in html and "gh" in html


# ---------- filtros em chips, sem <select> ----------


def test_nenhum_select_nos_controles():
    assert "<select" not in APP_JS
    assert "<select" not in INDEX
    assert "fsel" not in CSS and "fsel" not in APP_JS


@com_node
def test_filtros_sao_chips_de_estado_fase_responsavel_prd_labels_e_busca(tmp_path):
    html = _rodar(tmp_path, "renderIssues()")
    for act in ("fstate", "ffase", "fresp", "fprd", "flabel", "fhumana"):
        assert _botoes(html, act), f"sem chip {act}"
    assert re.search(r'<input[^>]*type="search"', html)
    assert "<select" not in html
    grupos = re.findall(r'class="filtro-rot">([^<]+)<', html)
    assert {"type", "area", "fatia"} <= set(grupos)
    labels = {v: corpo for v, _, corpo in _botoes(html, "flabel")}
    assert labels["type:fix"].strip() == "fix"  # dentro do grupo, o chip mostra a label sem o prefixo
    assert "ready-for-human" not in labels  # tem chip próprio, com contador


@com_node
def test_chip_de_prd_filtra_o_prd_e_as_fatias_dele(tmp_path):
    assert _lista(tmp_path, "_clicar({ act: 'fprd', v: '900' });") == [900, 901, 902, 903, 904, 905]


@com_node
def test_chip_de_label_e_de_estado_filtram(tmp_path):
    assert _lista(tmp_path, "_clicar({ act: 'flabel', v: 'type:fix' });") == [900, 903]
    assert _lista(tmp_path, "_clicar({ act: 'fstate', v: 'CLOSED' });") == [900, 904, 912, 911]


@com_node
def test_busca_por_numero(tmp_path):
    assert _lista(tmp_path, "S.fIssues.q = '#910';") == [910]


# ---------- responsável: cor da pessoa e "ninguém assumiu" ----------


@com_node
def test_cor_fixa_para_os_tres_socios_e_paleta_por_ordem_de_aparicao(tmp_path):
    expr = "['pedrorezendefig', 'lucassampaioc1', 'pedroribbe', 'zeca', 'ana', 'zeca', null].map(corDaPessoa)"
    cores = _rodar(tmp_path, expr)
    socios, zeca, ana, zeca_de_novo, ninguem = cores[:3], cores[3], cores[4], cores[5], cores[6]
    assert all(c.startswith("var(--") for c in cores)  # só tokens do :root
    assert len(set(socios)) == 3
    assert zeca != ana and zeca == zeca_de_novo
    assert not {zeca, ana} & set(socios)
    assert ninguem not in socios + [zeca, ana]


def test_cor_por_pessoa_mora_numa_funcao_so():
    assert "export function corDaPessoa(" in PESSOAS_JS
    for login in ("pedrorezendefig", "lucassampaioc1", "pedroribbe"):
        assert login in PESSOAS_JS
    assert "import { corDaPessoa } from './pessoas.js';" in APP_JS
    assert "function corDaPessoa(" not in APP_JS


@com_node
def test_chip_de_responsavel_usa_a_cor_da_pessoa(tmp_path):
    html, cor = _rodar(tmp_path, "[renderIssues(), corDaPessoa('lucassampaioc1')]")
    chips = {v: tag for v, tag, _ in _botoes(html, "fresp")}
    assert f"--pessoa:{cor}" in chips["lucassampaioc1"]
    assert "(sem)" in chips  # o chip "ninguém assumiu"
    assert "ana" not in chips  # só criou issues: não é responsável de nenhuma


@com_node
def test_ninguem_assumiu_lista_as_issues_sem_assignee_mesmo_com_autor(tmp_path):
    numeros = _rodar(
        tmp_path, "S.data.github.issues.filter(matchIssue).map(i => i.number)", antes="S.fIssues.resp = SEM_RESP;"
    )
    assert numeros == [901, 905, 910, 911, 912]


@com_node
def test_filtro_por_pessoa_nao_cai_em_quem_criou(tmp_path):
    expr = "['ana', 'pedrorezendefig'].map(p => (S.fIssues.resp = p, S.data.github.issues.filter(matchIssue).map(i => i.number)))"
    ana, pedro = _rodar(tmp_path, expr)
    assert ana == []  # criou quase tudo, não assumiu nada
    assert pedro == [900, 904]  # a 905 ele só criou


@com_node
def test_chip_ready_for_human_mostra_o_contador_e_filtra_a_fila_humana(tmp_path):
    html = _rodar(tmp_path, "renderIssues()")
    [(_, _, corpo)] = _botoes(html, "fhumana")
    assert "ready-for-human" in corpo
    assert re.search(r'class="tab-count">1<', corpo)  # só a aberta conta
    assert _lista(tmp_path, "_clicar({ act: 'fhumana', v: '1' });") == [900, 905]


@com_node
def test_contador_ready_for_human_sem_gh_e_interrogacao(tmp_path):
    dados = {**DADOS, "github": {**DADOS["github"], "error": "gh fora", "issues": []}}
    [(_, _, corpo)] = _botoes(_rodar(tmp_path, "renderIssues()", dados=dados), "fhumana")
    assert re.search(r'class="tab-count">\?<', corpo)


# ---------- responsável filtrado: contagens dele, nada de lead time ----------


@com_node
def test_funil_com_responsavel_filtrado_mostra_as_contagens_dele(tmp_path):
    html = _rodar(tmp_path, "renderIssues()", antes="S.fIssues.resp = 'lucassampaioc1';")
    assert {p[0]: p[1] for p in _passos_do_funil(html)} == DO_LUCAS
    assert "contagens de lucassampaioc1" in html
    assert "lead time" not in html.lower()


@com_node
def test_funil_de_quem_nao_tem_contagem_no_payload_zera(tmp_path):
    html = _rodar(tmp_path, "renderIssues()", antes="S.fIssues.resp = 'zeca';")
    assert {p[0]: p[1] for p in _passos_do_funil(html)} == dict.fromkeys(FASES, 0)


def test_lead_time_sai_do_app_js():
    assert "lead time" not in APP_JS.lower()
    assert "leadAvg" not in APP_JS and "visorResponsavelHtml" not in APP_JS


# ---------- card compacto e linha do tempo ----------


def _card_expr(n):
    return f"issueCard(S.data.github.issues.find(i => i.number === {n}), 0)"


@com_node
def test_card_compacto_mostra_fase_pessoa_idade_criterios_pr_e_versao(tmp_path):
    aberta, fechada, cor = _rodar(tmp_path, f"[{_card_expr(903)}, {_card_expr(904)}, corDaPessoa('pedroribbe')]")
    assert "PR aberto · CI vermelho" in aberta
    assert f'style="--pessoa:{cor}"' in aberta and "pedroribbe" in aberta
    assert "aberta há " in aberta
    assert "3/8" in aberta
    assert ">PR #77<" in aberta
    assert "iss-body" not in aberta and "corpo da 903" not in aberta  # fechado: nada da timeline nem do corpo
    assert "Em produção" in fechada and ">PR #70<" in fechada and "v0.163.4" in fechada
    assert "fechada 3 out" in fechada


@com_node
def test_card_sem_assignee_diz_ninguem_assumiu_e_mostra_o_autor_como_informacao(tmp_path):
    card = _rodar(tmp_path, _card_expr(905))
    assert "ninguém assumiu" in card and "criada por pedrorezendefig" in card


@com_node
def test_card_expandido_mostra_a_linha_do_tempo_com_eventos_datados(tmp_path):
    card = _rodar(tmp_path, _card_expr(902), antes="S.expIss.add(902);")
    eventos = re.findall(r'class="evento-quando">([^<]+)</span>\s*<span class="evento-o-que">([^<]+)<', card)
    assert eventos == [
        ("1 out, 10:00", "criada"),
        ("2 out, 13:45", "designada para lucassampaioc1"),
        ("sem data", "branch feat/x-902"),
    ]
    assert "corpo da 902" in card


@com_node
def test_issue_aberta_usa_a_linha_do_tempo_da_coleta(tmp_path):
    buscas, card = _rodar(
        tmp_path,
        f"[_buscas.filter(u => u.endsWith('/timeline')), {_card_expr(902)}]",
        antes="_clicar({ act: 'iss', n: '902' });",
    )
    assert buscas == []
    assert "designada para lucassampaioc1" in card


@com_node
def test_issue_fechada_busca_a_linha_do_tempo_ao_expandir(tmp_path):
    resposta = {
        "number": 904,
        "error": None,
        "timeline": [{"tipo": "mergeado", "em": "2026-10-03T17:58:00Z", "pr": 70}],
    }
    antes = (
        f"_respostas['/api/issue/904/timeline'] = {json.dumps(resposta)};"
        "_clicar({ act: 'iss', n: '904' }); await _esperar(); await _esperar();"
    )
    buscas, card = _rodar(tmp_path, f"[_buscas.filter(u => u.endsWith('/timeline')), {_card_expr(904)}]", antes=antes)
    assert buscas == ["/api/issue/904/timeline"]
    assert re.search(r'evento-quando">3 out, 17:58</span>\s*<span class="evento-o-que">PR #70 mergeado<', card)


@com_node
def test_linha_do_tempo_que_falhou_tenta_de_novo_ao_reabrir_o_card(tmp_path):
    falha = {"number": 904, "error": "gh: HTTP 502", "timeline": []}
    certa = {"number": 904, "error": None, "timeline": [{"tipo": "mergeado", "em": "2026-10-03T17:58:00Z", "pr": 70}]}
    antes = (
        f"_respostas['/api/issue/904/timeline'] = {json.dumps(falha)};"
        "_clicar({ act: 'iss', n: '904' }); await _esperar(); await _esperar();"
        "const _naFalha = linhaDoTempoHtml(904);"
        "_clicar({ act: 'iss', n: '904' });"  # fecha
        f"_respostas['/api/issue/904/timeline'] = {json.dumps(certa)};"
        "_clicar({ act: 'iss', n: '904' }); await _esperar(); await _esperar();"  # reabre
    )
    buscas, na_falha, card = _rodar(
        tmp_path, f"[_buscas.filter(u => u.endsWith('/timeline')), _naFalha, {_card_expr(904)}]", antes=antes
    )
    assert "linha do tempo indisponível: gh: HTTP 502" in na_falha
    assert buscas == ["/api/issue/904/timeline", "/api/issue/904/timeline"]
    assert "PR #70 mergeado" in card


# ---------- cinco abas; Plano, Pendências e Guia saem ----------


@com_node
def test_aba_prs_fica_vazia_com_texto_de_em_construcao(tmp_path):
    html = _rodar(tmp_path, "_view.innerHTML", antes="setTab('prs');")
    assert "em construção" in html


def test_plano_pendencias_e_guia_sairam_do_painel():
    for nome in ("renderPlano", "renderPendencias", "renderGuia", "fluxoHtml", "FLX_ICONS", "pendenciasHumanas", "copyCmd", "writeClipboard"):
        assert nome not in APP_JS, nome
    for seletor in (".tab-plano", ".leva", ".pend-", ".flx", ".guia-flow", ".visor-resp", ".cmdpill", ".cmd-copy"):
        assert seletor not in CSS, seletor
    assert not (DASH / "plano.py").exists()
    for teste in ("test_plano.py", "test_front_plano_issues.py", "test_filtro_responsavel.py"):
        assert not (DASH / "tests" / teste).exists(), teste


# ---------- a tela nova segue o padrão de linhas numeradas ----------


def test_issues_seguem_em_linhas_numeradas_com_a_arvore_do_prd():
    assert 'class="tab-issues"' in APP_JS
    assert re.search(r'<article class="nrow \$\{prd \? \'prd-row\' : \'\'\} rv"', APP_JS)
    assert "nrow-idx" in APP_JS and "nrow-go" in APP_JS and "padStart(2" in APP_JS
    assert "prd-group" in APP_JS and 'class="children"' in APP_JS
    assert ".tab-issues .comment .md" in CSS


# ---------- estilo da lista que segue vivo (vinha do test_front_plano_issues.py, #260) ----------


def _fn(nome):
    """Corpo de uma function declarada do app.js, por contagem de chaves."""
    i = APP_JS.find(f"function {nome}(")
    assert i >= 0, f"app.js sem function {nome}"
    j = APP_JS.index("{", i)
    depth = 0
    for k in range(j, len(APP_JS)):
        if APP_JS[k] == "{":
            depth += 1
        elif APP_JS[k] == "}":
            depth -= 1
            if depth == 0:
                return APP_JS[i : k + 1]
    raise AssertionError(f"function {nome} sem fechamento")


def _blocos_media(cond):
    """Todos os blocos @media com a condição dada, por contagem de chaves."""
    blocos = []
    for m in re.finditer(re.escape(cond), CSS):
        j = CSS.index("{", m.end())
        depth = 0
        for k in range(j, len(CSS)):
            if CSS[k] == "{":
                depth += 1
            elif CSS[k] == "}":
                depth -= 1
                if depth == 0:
                    blocos.append(CSS[j : k + 1])
                    break
    return blocos


def test_hairline_entre_linhas_e_entre_fatias_vem_dos_tokens():
    for seletor in (r"\.nrows > \.nrow \+ \.nrow", r"\.children > \.nrow \+ \.nrow"):
        m = re.search(seletor + r"[^{]*\{[^}]*\}", CSS)
        assert m, f"sem hairline em {seletor}"
        assert "var(--hairline)" in m.group(0)


def test_seta_em_circulo_de_hairline():
    go = re.search(r"\.nrow-go\{[^}]*\}", CSS)
    assert go, "seta sem círculo (.nrow-go)"
    assert "var(--hairline)" in go.group(0), "círculo sem borda hairline"
    assert "var(--r-pill)" in go.group(0), "círculo fora do raio pill"
    assert 'class="nrow-go"' in _fn("issueCard") and 'class="nrow-arrow"' in _fn("issueCard")


def test_hover_da_seta_desliza_so_no_desktop():
    desktop = "".join(_blocos_media("@media (min-width:769px)"))
    assert ".nrow:hover .nrow-arrow" in desktop, "deslize fora do gate desktop"
    assert "translateX" in desktop
    assert ".nrow:hover .nrow-go" in desktop and "opacity:1" in desktop
    fora = CSS
    for b in _blocos_media("@media (min-width:769px)"):
        fora = fora.replace(b, "")
    assert ".nrow:hover" not in fora, "hover de deslize vazando pra fora do desktop"


def test_reveals_escalonados_nas_linhas():
    card = _fn("issueCard")
    assert re.search(r'<article class="nrow [^"]*\brv"', card), "card sem reveal .rv"
    assert 'style="--i:${idx}"' in card, "card sem stagger por índice"


def test_cabecalho_da_aba_com_eyebrow_legivel():
    assert 'class="eyebrow"' in _fn("cabecalho") and "clip-inner" in _fn("cabecalho")
    assert "cabecalho(" in _fn("renderIssues"), "Issues fora do cabeçalho com eyebrow"
    m = re.search(r"\.sec-ey \.eyebrow\{[^}]*\}", CSS)
    assert m and "var(--ink-soft)" in m.group(0), "eyebrow com a cor do plano navy"


def test_comentarios_com_tipografia_da_aba():
    assert 'class="comment"' in _fn("commentsHtml")
    assert 'class="md"' in _fn("commentsHtml")
    m = re.search(r"\.tab-issues \.comment \.md\{[^}]*\}", CSS)
    assert m and "var(--sans)" in m.group(0), "comentários sem tipografia re-estilizada"


def test_aba_embrulhada_para_escopo_de_estilo():
    assert 'class="tab-issues"' in _fn("renderIssues")


# ---------- fixture para o render no Chrome headless ----------


def test_servidor_serve_o_payload_de_um_arquivo_de_fixture(tmp_path, monkeypatch):
    import serve

    fixture = tmp_path / "dados.json"
    fixture.write_text(json.dumps(DADOS), encoding="utf-8")
    monkeypatch.setattr(serve, "FIXTURE", fixture)
    monkeypatch.setattr(serve.collector, "collect", lambda root: pytest.fail("coletou ao vivo com fixture ligada"))
    servidor = serve.ThreadingHTTPServer(("127.0.0.1", 0), serve.Handler)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{servidor.server_address[1]}/api/data"
        with urllib.request.urlopen(url, timeout=5) as resp:
            corpo = json.loads(resp.read())
    finally:
        servidor.shutdown()
    assert corpo == DADOS


def test_fixture_entra_pela_linha_de_comando():
    import serve

    assert serve.fixture_dos_args(["--no-open", "--fixture", "/tmp/x.json"]) == Path("/tmp/x.json")
    assert serve.fixture_dos_args(["--port", "8765"]) is None
