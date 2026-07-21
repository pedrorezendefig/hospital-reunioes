"""Contrato estático da interação do ER na aba Mapa (colunas aparentes, #255).

Como no test_front.py, aqui mora só o que é contrato estático dos arquivos
servidos (diagramas.js + app.js + style.css): todas as colunas desenhadas nos
cards (sem popover de hover), hover que só destaca (card e linha FK), salto
pra ficha no ENTIDADES, tela cheia com rolagem interna e o fim do zoom/pan.
O comportamento vivo é verificado via Chrome headless contra o serve.py,
fora do pytest.
"""

from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "static"
JS = (STATIC / "diagramas.js").read_text(encoding="utf-8")
APP = (STATIC / "app.js").read_text(encoding="utf-8")
CSS = (STATIC / "style.css").read_text(encoding="utf-8")


# ---------- colunas aparentes no card (sem popover) ----------


def test_card_lista_colunas_com_tipo_e_marcadores():
    # linhas de coluna com tipo e os marcadores de chave PK/FK, direto no card
    assert "er-col-nome" in JS
    assert "er-col-tipo" in JS
    assert "er-k-pk" in JS and "er-k-fk" in JS
    # a truncagem do snapshot (extras) aparece como linha própria, não some
    assert "er-col-extra" in JS


def test_coluna_fk_mostra_destino_inline():
    # a linha FK troca o tipo pelo destino (setor_id → setores) e carrega os
    # data-attrs que o hover usa pra acender a aresta específica
    assert "er-col-dest" in JS
    assert "er-col-fk" in JS
    assert "data-dest" in JS
    assert 'data-col="' in JS


def test_popover_morreu():
    # nenhum popover de hover no ER: as colunas são sempre aparentes
    assert "er-pop" not in JS
    assert "er-pop" not in CSS
    assert "popHtml" not in JS


def test_card_tem_verbete_funcional_curado():
    # o verbete de static/content/tabelas.js vira linha clampada no card;
    # sem verbete o card avisa em vez de quebrar
    assert "content/tabelas.js" in JS
    assert "er-tab-verbete" in JS
    assert "sem-verbete" in JS
    assert (STATIC / "content" / "tabelas.js").exists()


def test_nome_da_tabela_salta_pra_ficha_em_entidades():
    # clique no nome (e Enter/Espaço no card) saltam pro catálogo de ENTIDADES
    assert 'data-act="ficha"' in JS
    assert "keydown" in JS
    assert "'ficha'" in APP and "ENTIDADES" in APP


# ---------- hover só destaca ----------


def test_hover_destaca_vizinhanca_e_linha_fk():
    assert "mouseenter" in JS
    assert "er-hover" in JS
    assert "focarFk" in JS
    assert ".er-hover .er-tab:not(.on)" in CSS


def test_arestas_sem_rotulo_fixo():
    # a coluna FK já está aparente no card; a aresta fica limpa
    assert "er-rel-label" not in JS
    assert "er-rel-label" not in CSS


def test_animacoes_de_fluxo_e_entrada():
    # fluxo contínuo sutil nas arestas + stagger de entrada + traço do hover
    assert "erFluxo" in CSS
    assert "erIn" in CSS
    assert "erTraco" in CSS


# ---------- altura natural: zoom/pan morreu, scroll é scroll ----------


def test_zoom_e_pan_morreram():
    assert "'wheel'" not in JS
    assert "setPointerCapture" not in JS
    for acao in ('data-er="mais"', 'data-er="menos"', 'data-er="ajustar"'):
        assert acao not in JS
    assert ".er-controls" not in CSS
    assert "grabbing" not in CSS


# ---------- tela cheia ----------


def test_mapa_tem_tela_cheia_com_escape_e_rolagem_interna():
    assert 'data-act="erfull"' in APP
    assert "erFull" in APP
    assert "Escape" in APP
    assert ".er-full" in CSS
    assert "er-lock" in CSS
    # o desenho mantém o tamanho natural e rola dentro da tela cheia
    assert "overflow:auto" in CSS.split(".er-capa.er-full .er-canvas", 1)[1].split("}", 1)[0]


# ---------- reduceMotion ----------


def test_animacoes_respeitam_reduce_motion():
    # animações dirigidas por JS (play da sequência) checam a preferência;
    # as de CSS morrem na regra global de prefers-reduced-motion
    assert "reduceMotion" in JS
    assert "prefers-reduced-motion" in CSS
