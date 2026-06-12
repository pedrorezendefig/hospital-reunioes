"""Critérios estruturais do shell (index.html) — navegação e branding.

O comportamento dinâmico (aba inicial, render das ondas, copiáveis) é
verificado via Chrome headless contra o serve.py; aqui mora só o que é
contrato estático do painel — barato de checar e imune a refactor do JS.
"""

import re
from pathlib import Path

INDEX = (Path(__file__).resolve().parents[1] / "static" / "index.html").read_text(encoding="utf-8")


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
