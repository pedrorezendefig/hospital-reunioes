"""Contrato estático da interação do ER na aba Mapa (issue #215, ADR 0025).

Como no test_front.py, aqui mora só o que é contrato estático dos arquivos
servidos (diagramas.js + style.css): expansão de colunas, zoom/pan e o botão
ajustar. O comportamento vivo é verificado via Chrome headless contra o
serve.py, fora do pytest.
"""

from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "static"
JS = (STATIC / "diagramas.js").read_text(encoding="utf-8")
CSS = (STATIC / "style.css").read_text(encoding="utf-8")


# ---------- expansão de colunas ----------


def test_clique_na_tabela_alterna_expansao_com_aria():
    # o card é alternável por clique e por teclado, com estado acessível
    assert "addEventListener('click'" in JS
    assert "aria-expanded" in JS
    assert "keydown" in JS


def test_card_expandido_lista_colunas_com_tipo_e_marcadores():
    # linhas de coluna com tipo e os marcadores de chave PK/FK
    assert "er-col-nome" in JS
    assert "er-col-tipo" in JS
    assert "er-k" in JS
    assert "'PK'" in JS and "'FK'" in JS
    # a truncagem do snapshot (extras) aparece como linha própria, não some
    assert "er-col-extra" in JS


def test_expansao_recalcula_o_layout_inteiro():
    # o desenho (cards, arestas e viewBox) sai de uma única função de layout
    # parametrizada pelo conjunto de tabelas expandidas: as arestas seguem
    # o card redimensionado porque tudo é recomputado junto
    assert "expandidas" in JS


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
    # animações dirigidas por JS (reenquadramento, FLIP da expansão) checam
    # a preferência; as de CSS já morrem na regra global de prefers-reduced-motion
    assert "reduceMotion" in JS
    assert "prefers-reduced-motion" in CSS


# ---------- CSS ----------


def test_css_estiliza_controles_e_estado_expandido():
    assert ".er-controls" in CSS
    assert ".er-col" in CSS
    assert "grab" in CSS


def test_rerender_nao_reexecuta_a_entrada_em_cascata():
    # a re-renderização pós-clique não replay o stagger de entrada dos cards
    assert ".er-live" in CSS
