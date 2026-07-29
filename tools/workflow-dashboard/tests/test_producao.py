"""Critérios da aba Produção (reskin issue 259, padrão Baseline).

Consome os tokens da fundação (#258): stats band navy 4-up no topo,
timeline de deploys em cartões claros com hairlines e chips, sparkline
pintado só com tokens e semânticas legíveis nos dois planos (navy e claro).
O CSS da aba vive num bloco próprio delimitado, apensado ao style.css.
"""

import re
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "static"
CSS = (STATIC / "style.css").read_text(encoding="utf-8")
APP_JS = (STATIC / "app.js").read_text(encoding="utf-8")


def _bloco_producao():
    """O bloco de CSS delimitado da aba Produção, do marcador de abertura ao de fim."""
    m = re.search(r"/\* =+ PRODUÇÃO[^*]*\*/(.*?)/\* =+ fim PRODUÇÃO[^*]*\*/", CSS, re.S)
    assert m, "style.css sem bloco delimitado da aba Produção (issue 259)"
    return m.group(1)


def _regra(css: str, seletor: str) -> str:
    m = re.search(re.escape(seletor) + r"\{[^}]*\}", css)
    assert m, f"regra {seletor} ausente"
    return m.group(0)


# ---------- stats band navy 4-up ----------


def test_stats_band_navy_com_os_quatro_indicadores():
    assert "prod-band" in APP_JS, "renderDeploys sem a faixa navy de estatísticas"
    for rotulo in ("deploys", "saudáveis", "build médio", "última versão"):
        assert rotulo in APP_JS, f"indicador '{rotulo}' ausente da faixa"
    banda = _regra(_bloco_producao(), ".prod-band")
    assert "var(--navy)" in banda, "faixa de estatísticas sem fundo navy"


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


# ---------- timeline nova ----------


def test_timeline_em_cartoes_claros_com_hairlines():
    assert "pd-timeline" in APP_JS, "renderDeploys sem a timeline nova"
    assert "tl-item" not in APP_JS, "timeline antiga (tl-item) ainda no render"
    bloco = _bloco_producao()
    cartao = _regra(bloco, ".pd-card")
    assert "var(--hairline)" in cartao, "cartão do deploy sem hairline dos tokens"
    corpo = _regra(bloco, ".pd-body")
    assert "var(--hairline)" in corpo, "corpo expandido sem hairline de separação"


def test_deploy_card_tem_chips_e_changelog_inline():
    m = re.search(r"function deployCard[\s\S]*?\n\}", APP_JS)
    assert m, "deployCard sumiu do app.js"
    corpo = m.group(0)
    assert 'class="chip"' in corpo, "deployCard sem chips de PR/issue/sha"
    assert "badge" in corpo, "deployCard sem badge de estado"
    assert "changelog" in corpo, "deployCard sem changelog inline"


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
