"""Reskin da aba Mapa (issue #261): diagramas e capas lendo CSS variables.

Guarda anti cor fixa nos módulos de renderização (static/diagramas.js e
static/areas.js) + contrato estático do bloco de reskin no style.css:
legendas das capas em glass caption (navy translúcido + blur, texto branco)
e hierarquia navy nos diagramas (traço base em tinta, destaque em brand,
fundo em superfície). O bloco :root do style.css segue como única fonte
de verdade de cor (test_front.py cobre o CSS; aqui, os renderers JS).
"""

import re
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "static"
CSS = (STATIC / "style.css").read_text(encoding="utf-8")
DIAGRAMAS_JS = (STATIC / "diagramas.js").read_text(encoding="utf-8")
AREAS_JS = (STATIC / "areas.js").read_text(encoding="utf-8")
RENDERERS = {"diagramas.js": DIAGRAMAS_JS, "areas.js": AREAS_JS}

MARCADOR_RESKIN = "Reskin Mapa (issue 261)"


def _sem_comentarios(js):
    """Remove comentários (é onde vivem refs tipo 'issue #255', que parecem hex)."""
    js = re.sub(r"/\*.*?\*/", "", js, flags=re.S)
    return re.sub(r"//[^\n]*", "", js)


def _cores_fixas(js):
    """Toda cor fixa achada no código (fora de comentário): hex, rgb()/hsl(),
    ou propriedade de cor inline cujo valor não é var()/keyword neutro."""
    codigo = _sem_comentarios(js)
    achados = []
    achados += re.findall(r"#[0-9a-fA-F]{3,8}\b", codigo)
    achados += re.findall(r"\b(?:rgba?|hsla?)\([^)]*\)", codigo)
    inline = re.findall(r"\b(fill|stroke|color|background(?:-color)?)\s*:\s*([^;\"'`}<]+)", codigo)
    for prop, valor in inline:
        v = valor.strip()
        if not re.match(r"^(var\(--[\w-]+|none|transparent|inherit|currentColor|\$\{)", v):
            achados.append(f"{prop}:{v}")
    return achados


def _bloco_reskin():
    assert MARCADOR_RESKIN in CSS, "style.css sem o bloco delimitado do reskin do Mapa"
    return CSS.split(MARCADOR_RESKIN, 1)[1]


# ---------- teste de guarda: nenhuma cor fixa nos renderers ----------


def test_guarda_renderers_sem_cor_fixa():
    for nome, js in RENDERERS.items():
        assert _cores_fixas(js) == [], f"cor fixa em {nome}: {_cores_fixas(js)}"


def test_guarda_acusa_cor_fixa_reintroduzida():
    # a guarda tem que FALHAR se alguém voltar a embutir cor no renderer
    assert _cores_fixas('const c = `<rect fill="#fff"/>`;')
    assert _cores_fixas('const c = `<rect fill="#2563c9"/>`;')
    assert _cores_fixas('const c = `<path stroke="rgb(255,0,0)"/>`;')
    assert _cores_fixas('const c = `<path stroke="hsl(210,80%,50%)"/>`;')
    assert _cores_fixas('const c = `<text style="color:red">x</text>`;')


def test_guarda_nao_acusa_vars_nem_refs_de_issue_em_comentario():
    assert _cores_fixas('const c = `<rect fill="var(--card)"/>`; /* issue #255 */') == []
    assert _cores_fixas("// masonry (issue #212)\nconst x = 1;") == []
    assert _cores_fixas('const c = `<rect style="fill:${cor}"/>`;') == []


def test_vars_usadas_pelos_renderers_existem_no_bloco_de_tokens():
    m = re.search(r":root\{(.*?)\}", CSS, re.S)
    assert m, "style.css sem bloco :root de tokens"
    root = m.group(1)
    for nome, js in RENDERERS.items():
        for var in sorted(set(re.findall(r"var\((--[\w-]+)\)", js))):
            assert f"{var}:" in root, f"{nome} lê {var}, ausente do bloco de tokens"


# ---------- glass captions nas legendas das capas ----------


def test_glass_caption_navy_translucida_com_blur_e_texto_branco():
    m = re.search(r"\.glass-cap[^{]*\{([^}]*)\}", CSS)
    assert m, "classe .glass-cap ausente do style.css"
    bloco = m.group(1)
    assert "var(--navy)" in bloco, "glass caption sem fundo navy translúcido"
    assert "backdrop-filter:blur" in bloco, "glass caption sem blur"
    assert "var(--on-navy)" in bloco, "glass caption sem texto branco"
    # a opacity das regras legadas (.85/.8) não pode esmaecer a pill navy:
    # o padrão glass da fundação (.capsule) não usa opacity de elemento
    assert "opacity:1" in bloco, "glass caption herdando opacity esmaecida legada"


def test_legendas_das_capas_usam_glass_caption():
    assert 'class="rt-hint glass-cap"' in AREAS_JS, "legenda de ROTAS sem glass"
    assert "ent-legenda glass-cap" in AREAS_JS, "legenda de ENTIDADES sem glass"
    assert "tr-legenda glass-cap" in AREAS_JS, "legenda de ESTRUTURA sem glass"
    assert "st-hint glass-cap" in DIAGRAMAS_JS, "hint da máquina de estados sem glass"
    assert "fl-hint glass-cap" in DIAGRAMAS_JS, "hint do fluxograma sem glass"


def test_hint_da_capa_er_entra_no_glass_pelo_seletor():
    # a capa ER é montada no app.js; a hint dela vira glass pelo seletor
    # compartilhado, sem mexer no app.js (cobre também a capa de INTEGRACOES)
    m = re.search(r"\.glass-cap([^{]*)\{", CSS)
    assert m and ".er-capa-hint" in m.group(1)


# ---------- hierarquia navy nos diagramas ----------


def test_traco_base_dos_diagramas_em_tinta():
    # base em tinta suave; o destaque (hover, caminho feliz, play) segue
    # em brand pelas regras já existentes, que têm especificidade maior
    reskin = _bloco_reskin().replace(" ", "").replace("\n", "")
    assert ".er-edge{stroke:var(--ink-soft)}" in reskin
    assert ".er-edge-pt{fill:var(--ink-soft)}" in reskin
    assert ".seq-linha,.seq-ponta{stroke:var(--ink-soft)}" in reskin
    assert ".ctx-seta{stroke:var(--ink-soft)}" in reskin
    assert "#ctxPontapath{fill:var(--ink-soft)}" in reskin
    # a ponta da seta (marker SVG não herda cor do path) acompanha o traço
    # brand no hover do serviço, senão a seta destacada fica com duas cores
    assert ".ctx-hover#ctxPontapath{fill:var(--brand)}" in reskin


def test_capa_integracoes_app_central_em_navy():
    reskin = _bloco_reskin().replace(" ", "").replace("\n", "")
    assert ".ctx-apprect{fill:var(--navy);stroke:var(--navy)}" in reskin
    assert ".ctx-app-sub{fill:var(--w70)}" in reskin


def test_legenda_da_estrutura_fala_da_bolinha_na_cor_nova():
    # a bolinha de pasta-chave é var(--brand), azul; a legenda acompanha
    assert "bolinha coral" not in AREAS_JS
    assert "bolinha azul" in AREAS_JS


# ---------- fichas, rotas e migrations nos cartões e chips novos ----------


def test_capas_renderizam_nos_cartoes_e_chips_da_fundacao():
    assert 'class="card rt-dom' in AREAS_JS, "explorador de rotas fora do cartão"
    assert "card ent-ficha" in AREAS_JS, "ficha de tabela fora do cartão"
    assert '<span class="chip">' in AREAS_JS, "capas sem chips da fundação"
    assert "badge b-" in AREAS_JS, "migrations sem badges da fundação"
