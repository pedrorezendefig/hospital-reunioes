"""Contrato estático da interação do ER na aba Mapa (redesenho visual-first).

Como no test_front.py, aqui mora só o que é contrato estático dos arquivos
servidos (diagramas.js + app.js + style.css): popover de colunas no hover
(clique fixa), tela cheia, zoom/pan e o botão ajustar. O comportamento vivo é
verificado via Chrome headless contra o serve.py, fora do pytest.
"""

from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "static"
JS = (STATIC / "diagramas.js").read_text(encoding="utf-8")
APP = (STATIC / "app.js").read_text(encoding="utf-8")
CSS = (STATIC / "style.css").read_text(encoding="utf-8")


# ---------- popover de colunas (hover mostra, clique fixa) ----------


def test_hover_mostra_popover_e_clique_fixa_com_aria():
    # hover/foco mostram o popover; clique e teclado fixam, com estado acessível
    assert "mouseenter" in JS
    assert "er-pop" in JS
    assert "addEventListener('click'" in JS
    assert "aria-expanded" in JS
    assert "keydown" in JS


def test_popover_lista_colunas_com_tipo_e_marcadores():
    # linhas de coluna com tipo e os marcadores de chave PK/FK
    assert "er-col-nome" in JS
    assert "er-col-tipo" in JS
    assert "er-k" in JS
    assert "er-k-pk" in JS and "er-k-fk" in JS
    # a truncagem do snapshot (extras) aparece como linha própria, não some
    assert "er-col-extra" in JS


def test_popover_tem_camada_funcional_curada():
    # o verbete funcional vem de static/content/tabelas.js; sem verbete o
    # popover avisa em vez de quebrar
    assert "content/tabelas.js" in JS
    assert "er-pop-resumo" in JS
    assert "sem-verbete" in JS
    assert (STATIC / "content" / "tabelas.js").exists()


def test_popover_liga_pra_ficha_completa_em_entidades():
    # o link "ficha completa" salta pro catálogo de ENTIDADES na tabela certa
    assert 'data-act="ficha"' in JS
    assert "'ficha'" in APP and "ENTIDADES" in APP


def test_zoom_e_pan_soltam_o_popover():
    # o popover ancora num card que muda de lugar na tela: zoom/pan soltam
    assert "soltaPop" in JS


# ---------- tela cheia ----------


def test_mapa_tem_tela_cheia_com_escape():
    assert 'data-act="erfull"' in APP
    assert "erFull" in APP
    assert "Escape" in APP
    assert ".er-full" in CSS
    assert "er-lock" in CSS


# ---------- zoom, pan e ajustar ----------


def test_controles_de_zoom_e_ajustar_existem():
    for acao in ('data-er="mais"', 'data-er="menos"', 'data-er="ajustar"'):
        assert acao in JS


def test_zoom_por_scroll_nao_rola_a_pagina():
    # wheel com preventDefault e listener não-passivo: o scroll fora do
    # canvas segue normal, dentro dele vira zoom
    assert "'wheel'" in JS
    assert "preventDefault" in JS
    assert "passive: false" in JS


def test_pan_por_arrasto_com_pointer_capture():
    assert "'pointerdown'" in JS
    assert "'pointermove'" in JS
    assert "setPointerCapture" in JS


def test_ajustar_reenquadra_para_o_viewbox_base():
    # o viewBox de enquadramento total viaja no data-vb e o ajustar volta a ele
    assert "data-vb" in JS
    assert "viewBox" in JS


# ---------- reduceMotion ----------


def test_navegacao_animada_respeita_reduce_motion():
    # animações dirigidas por JS (reenquadramento do ajustar) checam a
    # preferência; as de CSS já morrem na regra global de prefers-reduced-motion
    assert "reduceMotion" in JS
    assert "prefers-reduced-motion" in CSS


# ---------- CSS ----------


def test_css_estiliza_controles_e_popover():
    assert ".er-controls" in CSS
    assert ".er-pop" in CSS
    assert "grab" in CSS
