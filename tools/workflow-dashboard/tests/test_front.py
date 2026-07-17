"""Critérios estruturais do shell (index.html) — navegação e branding.

O comportamento dinâmico (aba inicial, render das ondas, copiáveis) é
verificado via Chrome headless contra o serve.py; aqui mora só o que é
contrato estático do painel — barato de checar e imune a refactor do JS.
"""

import re
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "static"
INDEX = (STATIC / "index.html").read_text(encoding="utf-8")
# módulos da SPA (vendor/ e content/ ficam de fora: marked é vendorizado de propósito)
SPA_JS = {p.name: p.read_text(encoding="utf-8") for p in sorted(STATIC.glob("*.js"))}


def test_navegacao_tem_exatamente_6_abas_sem_grupos():
    abas = re.findall(r'data-tab="([^"]+)"', INDEX)
    assert abas == ["plano", "issues", "producao", "mapa", "dominio", "guia"]
    assert "tabgroup" not in INDEX  # sem rótulos nem separadores de grupo


def test_titulo_do_painel_e_hospital_reunioes():
    assert re.search(r"<title>Hospital Reuniões", INDEX)
    m = re.search(r'<h1 class="mast-title">(.*?)</h1>', INDEX, re.S)
    assert m, "masthead sem h1"
    texto = re.sub(r"<[^>]+>", "", m.group(1))  # só o texto, sem markup decorativo
    assert "Hospital Reuniões" in texto


def test_spa_nao_carrega_a_biblioteca_mermaid():
    """Os diagramas são dos renderers próprios (ADR 0025); mermaid.js fora.

    A classe `language-mermaid` (fence do markdown dos snapshots) continua
    permitida: é como a SPA localiza os blocos que os renderers substituem.
    """
    proibidos = (
        "loadMermaid",
        "mermaidify",
        "mermaidP",
        "window.mermaid",
        "mermaid.min.js",
    )
    for nome, js in SPA_JS.items():
        for token in proibidos:
            assert token not in js, f"{nome} reintroduziu {token}"


def test_spa_nao_referencia_url_externa():
    """Painel 100% offline (ADR 0025): nenhum módulo da SPA aponta pra http(s)."""
    for nome, js in SPA_JS.items():
        assert "http://" not in js and "https://" not in js, (
            f"{nome} referencia URL externa"
        )


def test_index_so_carrega_script_local():
    srcs = re.findall(r'<script[^>]+src="([^"]+)"', INDEX)
    assert srcs, "index.html sem <script src>"
    for src in srcs:
        assert not src.startswith(("http:", "https:", "//")), f"script de CDN: {src}"
