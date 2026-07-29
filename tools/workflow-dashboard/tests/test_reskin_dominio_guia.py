"""Fecho do reskin (issue #262): abas Domínio e Guia + varredura final.

Domínio no padrão testimonial da referência: superfície clara (cartão),
glifo de aspas em azul royal (var(--brand)), corpo em destaque e rodapé
com hairline; os estados de ADR seguem em chips das semânticas dos tokens.
Guia re-tipografada com eyebrow e cartão, em Onest 400/500.

Varredura final do painel inteiro: nenhuma cor fixa fora do bloco :root
de tokens em TODO o static/ (style.css, app.js, ui.js, areas.js,
diagramas.js), nenhum peso de fonte fora dos 400/500 carregados, e
nenhuma regra órfã das telas aposentadas (cards antigos de fatia/issue,
Guia recolhível, Setup, seção AGORA, hover-descrição de card).
A identidade antiga (papel/coral, Fraunces, grão) já é travada pelo
test_front.py; o travessão/meia-risca também.
"""

import re
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "static"
CSS = (STATIC / "style.css").read_text(encoding="utf-8")
APP_JS = (STATIC / "app.js").read_text(encoding="utf-8")
UI_JS = (STATIC / "ui.js").read_text(encoding="utf-8")
AREAS_JS = (STATIC / "areas.js").read_text(encoding="utf-8")
DIAGRAMAS_JS = (STATIC / "diagramas.js").read_text(encoding="utf-8")
TODOS_JS = {"app.js": APP_JS, "ui.js": UI_JS, "areas.js": AREAS_JS, "diagramas.js": DIAGRAMAS_JS}


def _bloco(seletor):
    m = re.search(re.escape(seletor) + r"[^{]*\{([^}]*)\}", CSS)
    assert m, f"style.css sem a regra {seletor}"
    return m.group(1)


def _fora_do_root():
    return re.sub(r":root\{.*?\n\}", "", CSS, count=1, flags=re.S)


# ---------- Domínio: cartões testimonial ----------


def test_dominio_com_cabecalho_de_eyebrow():
    fn = re.search(r"function renderDominio\(\)[\s\S]*?\n\}", APP_JS)
    assert fn, "app.js sem renderDominio"
    corpo = fn.group(0)
    assert "cabecalho(" in corpo, "Domínio fora do padrão de cabeçalho com eyebrow"
    assert "Decisões de arquitetura" in corpo
    assert "Glossário do domínio" in corpo


def test_adr_em_cartao_testimonial_com_aspas_em_brand():
    assert 'class="card tst adr' in APP_JS, "ADR fora do cartão testimonial"
    assert "tst-quote" in APP_JS, "cartão de ADR sem glifo de aspas"
    quote = _bloco(".tst-quote")
    assert "var(--brand)" in quote, "glifo de aspas fora do azul royal"


def test_corpo_do_testimonial_em_destaque():
    corpo = _bloco(".tst-corpo")
    m = re.search(r"font-size:(\d+(?:\.\d+)?)px", corpo)
    assert m and float(m.group(1)) >= 16, "corpo do testimonial sem destaque"
    assert "font-weight:500" in corpo or "font-weight:500" in _bloco(".tst-corpo")


def test_rodape_do_testimonial_com_hairline():
    foot = _bloco(".tst-foot")
    assert "border-top" in foot and "var(--hairline)" in foot, "rodapé sem hairline"


def test_chips_de_estado_de_adr_nas_semanticas_dos_tokens():
    m = re.search(r"ADR_STATUS_CLS = \{([\s\S]*?)\}", APP_JS)
    assert m, "app.js sem o mapa de estados de ADR"
    mapa = m.group(1)
    assert "accepted: 'b-green'" in mapa
    assert "superseded: 'b-ghost'" in mapa
    assert "proposed: 'b-blue'" in mapa
    assert "rejected: 'b-red'" in mapa
    # o chip de estado vive no rodapé hairline do cartão
    assert re.search(r'class="tst-foot"[\s\S]{0,400}adrStatusBadge', APP_JS), \
        "chip de estado fora do rodapé do testimonial"


def test_ghostnum_da_identidade_anterior_aposentado():
    assert "ghostnum" not in APP_JS, "ADR ainda usa o número fantasma antigo"
    assert "ghostnum" not in CSS, "CSS ainda estiliza o número fantasma antigo"


def test_glossario_no_mesmo_cartao_testimonial():
    fn = re.search(r"function renderDominio\(\)[\s\S]*?\n\}", APP_JS)
    corpo = fn.group(0)
    assert re.search(r'class="card tst[^"]*"[\s\S]{0,400}context_md', corpo), \
        "glossário fora do cartão testimonial"
    assert re.search(r'tst-foot[\s\S]{0,200}CONTEXT\.md', corpo), \
        "rodapé do glossário sem a fonte CONTEXT.md"


# ---------- Guia: eyebrow + cartão em Onest ----------


def test_guia_com_cabecalho_de_eyebrow_e_cartao():
    fn = re.search(r"function renderGuia\(\)[\s\S]*?\n\}", APP_JS)
    assert fn, "app.js sem renderGuia"
    corpo = fn.group(0)
    assert "cabecalho(" in corpo, "Guia fora do padrão de cabeçalho com eyebrow"
    assert "guia-flow-card" in corpo, "fluxo do Guia fora do cartão"
    assert 'class="eyebrow"' in corpo, "cartão do Guia sem eyebrow interna"


def test_eyebrow_do_cartao_do_guia_legivel_no_plano_claro():
    # a eyebrow base é branca translúcida (navy); dentro do cartão claro
    # precisa da variante em tinta suave com ponto brand
    assert re.search(r"\.guia-flow-head \.eyebrow[^{]*\{[^}]*var\(--ink-soft\)", CSS), \
        "eyebrow do Guia ilegível sobre o cartão claro"


def test_pesos_de_fonte_so_400_e_500():
    # Onest e IBM Plex Mono carregam só 400/500: qualquer outro peso
    # renderiza sintetizado (o 800 do título antigo do Guia, por exemplo)
    pesos = set(re.findall(r"font-weight:\s*(\d+)", CSS))
    pesos |= {m for m in re.findall(r"font:\s*(\d{3})\b", CSS)}
    assert pesos <= {"400", "500"}, f"pesos fora dos carregados: {sorted(pesos)}"


# ---------- tooltips, copiar e recolhíveis no estilo novo ----------


def test_tooltip_no_estilo_novo():
    pop = _bloco(".tip-pop")
    assert "var(--ink)" in pop, "tooltip fora do fundo de tinta"


def test_botao_copiar_no_estilo_novo():
    assert "var(--green)" in _bloco(".cmd-copy.ok"), "feedback de cópia fora do verde dos tokens"
    assert "copyBlock" in UI_JS and "cmd-copy" in UI_JS


def test_recolhivel_com_caret_brand():
    m = re.search(r"\.techbox > summary::before\{([^}]*)\}", CSS)
    assert m and "var(--brand)" in m.group(1), "caret do recolhível fora do brand"


# ---------- varredura: cor fixa em todo o static/ ----------


def _sem_comentarios(js):
    js = re.sub(r"/\*.*?\*/", "", js, flags=re.S)
    return re.sub(r"//[^\n]*", "", js)


def _cores_fixas(js):
    codigo = _sem_comentarios(js)
    achados = []
    # hex curto (3-4) só conta com letra a-f: "#112" em prosa é ref de
    # issue/incidente, não cor (o hex todo-dígito de 6-8 segue flagrado)
    achados += re.findall(r"#[0-9a-fA-F]{6,8}\b", codigo)
    achados += [h for h in re.findall(r"#[0-9a-fA-F]{3,4}\b", codigo)
                if re.search(r"[a-fA-F]", h) and len(h) <= 5]
    achados += re.findall(r"\b(?:rgba?|hsla?)\([^)]*\)", codigo)
    inline = re.findall(r"\b(fill|stroke|color|background(?:-color)?)\s*:\s*([^;\"'`}<]+)", codigo)
    for prop, valor in inline:
        v = valor.strip()
        if not re.match(r"^(var\(--[\w-]+|none|transparent|inherit|currentColor|\$\{)", v):
            achados.append(f"{prop}:{v}")
    return achados


def test_varredura_nenhuma_cor_fixa_nos_modulos_js():
    for nome, js in TODOS_JS.items():
        assert _cores_fixas(js) == [], f"cor fixa em {nome}: {_cores_fixas(js)}"


def test_varredura_nenhuma_cor_fixa_no_css_fora_dos_tokens():
    resto = _fora_do_root()
    hexas = re.findall(r"#[0-9a-fA-F]{3,8}\b", resto)
    assert not hexas, f"cores hex fora do :root: {sorted(set(hexas))}"


# ---------- varredura: regras órfãs das telas aposentadas ----------


def test_css_sem_regras_orfas_das_telas_aposentadas():
    orfas = (
        # cards antigos de fatia (aba Plano pré linhas numeradas, #260)
        ".fatia{", ".fatia.f-", ".onda-fatias",
        # cards antigos de issue
        ".prd-head", ".iss{",
        # Guia recolhível e Setup (mortos desde o fluxograma, #211)
        ".guia-sec", ".guia-body", ".guia-foot", ".guia-paragrafo",
        ".metodo", ".met-passo", ".met-n", ".met-corpo", ".met-frase",
        ".setup-os", ".setup-steps", ".setup-step", ".setup-head",
        ".setup-n", ".setup-intro",
        # seção AGORA (absorvida pela Produção, #259)
        ".svc", ".gate{", ".gate .dot", ".action", ".a-ok", ".a-warn", ".a-info",
        ".commits", ".sec-flag", ".sec-big", ".agora-subject", ".agora-deprow",
        ".gate-resumo", ".git-stale", ".hero-version .v",
        # hover-descrição de card e âncora morta
        ".has-desc", ".desc-pop", ".wf-golink",
        # pontos de status sem uso
        ".dot.info", ".dot.muted", ".dot.warn",
    )
    for sel in orfas:
        assert sel not in CSS, f"regra órfã sobrou no style.css: {sel}"


def test_grid_spans_sem_uso_removidos():
    usados = re.findall(r"\bsp(\d+)\b", APP_JS + AREAS_JS + DIAGRAMAS_JS)
    declarados = re.findall(r"\.sp(\d+)\{", CSS)
    assert set(declarados) <= set(usados), \
        f"spans declarados sem uso: sp{sorted(set(declarados) - set(usados))}"
