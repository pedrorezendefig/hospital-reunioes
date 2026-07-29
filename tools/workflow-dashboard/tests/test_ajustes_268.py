"""Ajustes pós-entrega do reskin (issue #268).

Contratos estáticos dos três acabamentos: toggle de fatias funcional sob
filtro, contorno hairline nas fatias e hero sem caps forçado (este último
coberto em test_front.py). Mesmo estilo da suíte: estrutura e contrato,
nunca pixel.
"""

import re
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "static"
APP_JS = (STATIC / "app.js").read_text(encoding="utf-8")
CSS = (STATIC / "style.css").read_text(encoding="utf-8")


# ---------- toggle de fatias respeita o clique mesmo com filtro ativo ----------


def test_toggle_de_fatias_carrega_estado_aberto_no_botao():
    # o handler precisa saber o estado renderizado pra inverter com filtro ativo
    btn = re.search(r'<button class="fatias-toggle"[^>]*>', APP_JS)
    assert btn, "botão fatias-toggle sumiu"
    assert "data-open=" in btn.group(0), "toggle sem data-open: clique não inverte sob filtro"


def test_escolha_do_usuario_vence_o_default_do_filtro():
    # expPrd é um Map de escolha explícita (numero -> bool); o default do
    # filtro (expandir quando há resultado) só vale sem escolha do usuário
    assert re.search(r"expPrd:\s*new Map\(\)", APP_JS), "expPrd deixou de ser Map de escolha explícita"
    assert re.search(r"expPrd\.has\([^)]+\)\s*\?\s*S\.expPrd\.get", APP_JS), (
        "render não consulta a escolha explícita antes do default do filtro"
    )
    assert re.search(r"expPrd\.set\(", APP_JS), "handler não grava a escolha explícita"


# ---------- fatias com contorno hairline ----------


def test_fatia_dentro_do_prd_tem_contorno_hairline():
    regra = re.search(r"\.children\s*>\s*\.nrow\{[^}]*\}", CSS)
    assert regra, "fatias sem regra de contorno (.children > .nrow)"
    bloco = regra.group(0)
    assert "border:1px solid var(--hairline)" in bloco, "contorno da fatia não usa o hairline dos tokens"
    assert "border-radius" in bloco, "contorno da fatia sem cantos arredondados"
