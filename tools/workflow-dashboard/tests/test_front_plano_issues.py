"""Critérios estruturais do reskin das abas Plano e Issues (issue #260).

Padrão Baseline de linhas numeradas: índice, hairline entre linhas e seta
em círculo de hairline que desliza no hover (só desktop). Tudo consumindo
os tokens da fundação (#258); nenhuma cor fixa entra por aqui, o guarda
global vive em test_front.py.
"""

import re
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "static"
CSS = (STATIC / "style.css").read_text(encoding="utf-8")
APP_JS = (STATIC / "app.js").read_text(encoding="utf-8")
UI_JS = (STATIC / "ui.js").read_text(encoding="utf-8")


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
                return APP_JS[i:k + 1]
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
                    blocos.append(CSS[j:k + 1])
                    break
    return blocos


# ---------- linhas numeradas (Plano e Issues) ----------


def test_fatias_do_plano_sao_linhas_numeradas():
    linha = _fn("fatiaRow")
    assert 'class="nrow' in linha, "fatia não virou linha numerada"
    assert "nrow-idx" in linha, "linha sem índice numerado"
    assert "padStart(2" in linha, "índice sem zero à esquerda (01, 02, …)"
    assert "nrow-go" in linha and "nrow-arrow" in linha, "linha sem seta em círculo"
    onda = _fn("ondaHtml")
    assert "fatiaRow" in onda, "onda não lista as fatias como linhas"


def test_issues_sao_linhas_numeradas():
    card = _fn("issueCard")
    assert 'class="nrow' in card, "issue não virou linha numerada"
    assert "nrow-idx" in card and "padStart(2" in card
    assert "nrow-go" in card and "nrow-arrow" in card


def test_hairline_entre_linhas_vem_dos_tokens():
    m = re.search(r"\.nrows > \.nrow \+ \.nrow[^{]*\{[^}]*\}", CSS)
    assert m, "sem hairline entre linhas da lista"
    assert "var(--hairline)" in m.group(0)


def test_seta_em_circulo_de_hairline():
    go = re.search(r"\.nrow-go\{[^}]*\}", CSS)
    assert go, "seta sem círculo (.nrow-go)"
    assert "var(--hairline)" in go.group(0), "círculo sem borda hairline"
    assert "var(--r-pill)" in go.group(0), "círculo fora do raio pill"


def test_hover_da_seta_desliza_so_no_desktop():
    assert ".nrow:hover" in CSS, "linhas sem hover"
    desktop = "".join(_blocos_media("@media (min-width:769px)"))
    assert ".nrow:hover .nrow-arrow" in desktop, "deslize fora do gate desktop"
    assert "translateX" in desktop
    assert ".nrow:hover .nrow-go" in desktop and "opacity:1" in desktop
    fora = CSS
    for b in _blocos_media("@media (min-width:769px)"):
        fora = fora.replace(b, "")
    assert ".nrow:hover" not in fora, "hover de deslize vazando pra fora do desktop"


# ---------- árvore PRD e chips ----------


def test_arvore_prd_com_fatias_como_subitens():
    lista = _fn("issueListHtml")
    assert "prd-group" in lista and "children" in lista
    m = re.search(r"\.children > \.nrow \+ \.nrow[^{]*\{[^}]*\}", CSS)
    assert m and "var(--hairline)" in m.group(0), "sub-itens sem hairline entre linhas"


def test_chips_de_estado_tamanho_e_lead_time():
    card = _fn("issueCard")
    assert "stateTag" in card, "issue sem chip de estado"
    assert "labelBadge" in card, "issue sem chips de label (tamanho fatia:P/M/G)"
    assert "nrow-lead" in card, "issue fechada sem chip de lead time"
    linha = _fn("fatiaRow")
    assert "ESTADO_FATIA" in linha and "labelBadge('fatia:'" in linha


def test_estados_de_fatia_distinguiveis():
    m = re.search(r"const ESTADO_FATIA = \{(.*?)\n\};", APP_JS, re.S)
    assert m, "ESTADO_FATIA sumiu"
    classes = set(re.findall(r"badge (b-\w+)", m.group(1)))
    assert len(classes) == 5, f"estados com badges repetidas: {classes}"


# ---------- copiáveis ----------


def test_copiavel_em_mono_sobre_superficie():
    base = re.search(r"\.cmd-code\{[^}]*\}", CSS)
    assert base and "var(--mono)" in base.group(0), "copiável fora da fonte mono"
    escopo = re.search(r"\.tab-plano \.cmd-code\{[^}]*\}", CSS)
    assert escopo, "copiável do Plano sem re-estilo"
    assert "var(--surface)" in escopo.group(0), "copiável fora da superfície"


def test_botao_de_copiar_pill_ghost_funcionando_como_antes():
    botao = re.search(r"\.tab-plano \.cmd-copy\{[^}]*\}", CSS)
    assert botao, "botão de copiar sem re-estilo no Plano"
    assert "var(--r-pill)" in botao.group(0), "botão fora do formato pill"
    assert "transparent" in botao.group(0), "botão sem fundo ghost"
    # o mecanismo de cópia é o mesmo da fundação (data-act=copy + copyBlock)
    assert 'data-act="copy"' in UI_JS
    assert "copyBlock(" in _fn("fatiaRow")
    assert "act === 'copy'" in APP_JS


# ---------- eyebrows e reveals ----------


def test_cabecalhos_de_secao_com_eyebrow():
    cab = _fn("cabecalho")
    assert 'class="eyebrow"' in cab, "cabeçalho sem eyebrow"
    assert "clip-inner" in cab, "título do cabeçalho sem clip-mask da fundação"
    assert "cabecalho(" in _fn("planoBody"), "Plano fora do cabeçalho com eyebrow"
    assert "cabecalho(" in _fn("renderIssues"), "Issues fora do cabeçalho com eyebrow"


def test_eyebrow_legivel_no_plano_claro():
    m = re.search(r"\.sec-ey \.eyebrow\{[^}]*\}", CSS)
    assert m and "var(--ink-soft)" in m.group(0), "eyebrow com a cor do plano navy"


def test_reveals_escalonados_nas_linhas():
    for nome in ("fatiaRow", "issueCard"):
        corpo = _fn(nome)
        assert "rv" in re.findall(r'class="([^"]*)"', corpo)[0].split() or " rv" in corpo, \
            f"{nome} sem reveal .rv"
        assert "--i:" in corpo, f"{nome} sem stagger por índice"


# ---------- comentários e escopo ----------


def test_comentarios_com_tipografia_nova():
    assert 'class="comment"' in _fn("commentsHtml")
    m = re.search(r"\.tab-issues \.comment \.md\{[^}]*\}", CSS)
    assert m, "comentários sem tipografia re-estilizada"


def test_abas_embrulhadas_para_escopo_de_estilo():
    assert 'class="tab-plano"' in _fn("renderPlano")
    assert 'class="tab-issues"' in _fn("renderIssues")
