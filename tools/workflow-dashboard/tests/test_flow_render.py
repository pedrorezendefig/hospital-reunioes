"""Contrato estático do renderer de flowchart na aba Mapa (issue #218, ADR 0025).

Como no test_er_interacao.py, aqui mora só o que é contrato estático dos
arquivos servidos (diagramas.js + style.css): registro do tipo, espinha com
desvio lateral, decisão em destaque com ramos rotulados e reduceMotion. O
comportamento vivo é verificado via Chrome headless contra o serve.py.
"""

from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "static"
JS = (STATIC / "diagramas.js").read_text(encoding="utf-8")
CSS = (STATIC / "style.css").read_text(encoding="utf-8")


def test_tipo_flow_registrado_sem_tocar_nos_chamadores():
    # o contrato da fatia: registrar em RENDERERS, chamadores intactos
    assert "flow: flowSvg" in JS


def test_espinha_do_caminho_feliz_com_desvio_lateral():
    # nós da espinha e do desvio têm classes próprias, como no renderer de estado
    assert "fl-no-feliz" in JS
    assert "fl-no-desvio" in JS
    assert ".fl-no-feliz" in CSS
    assert ".fl-no-desvio" in CSS


def test_decisao_desenha_em_losango_destacado():
    # a decisão (nomes casados ou não) é um losango com classe própria
    assert "fl-no-decisao" in JS
    assert ".fl-no-decisao" in CSS


def test_ramos_da_decisao_ficam_rotulados_e_visiveis():
    # sim/nao são parte do desenho, não segredo de hover
    assert "fl-rotulo" in JS
    assert ".fl-rotulo" in CSS
    assert ".fl-rotulo{opacity:0" not in CSS.replace(" ", "")


def test_animacoes_do_flow_morrem_com_reduce_motion():
    # o renderer só anima via CSS; a regra global de prefers-reduced-motion
    # zera animação e transição, então nada roda com a preferência ativa
    assert ".fl-no{animation" in CSS.replace("  ", " ")
    assert "prefers-reduced-motion" in CSS


def test_flow_br_sobrando_nao_vira_linha_em_branco():
    import sys

    sys.path.insert(0, str(STATIC.parent))
    from diagramas import parse_bloco

    d = parse_bloco("flowchart TD\n    A[Fim<br/>] --> B[Meio<br/><br/>duplo]\n")
    nos = {n["id"]: n for n in d["nos"]}
    assert nos["A"]["linhas"] == ["Fim"]
    assert nos["B"]["linhas"] == ["Meio", "duplo"]


def test_svg_do_flow_e_acessivel():
    assert 'class="fl-svg"' in JS
    assert "Fluxograma" in JS
