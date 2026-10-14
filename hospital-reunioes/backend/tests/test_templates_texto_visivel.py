"""Texto que os templates de PDF e email mostram ao leitor (issue #1229, ADR 0071).

A varredura passou os templates pelo humanizer uma vez; daqui para frente o que
dá para pegar por regex trava aqui, com a mesma lista do lint do Manual e do
ESLint do front (`tools/tells_texto.py`). O lint de travessão do CI procura o
caractere no arquivo e não vê a entidade HTML (`&mdash;`), que o navegador e o
WeasyPrint desenham como travessão: por isso a conferência é sobre o texto já
decodificado.
"""

from __future__ import annotations

import html
import importlib.util
import re
import sys
from pathlib import Path

import pytest

TEMPLATES = Path(__file__).resolve().parents[1] / "app" / "templates"
TELLS_TEXTO = Path(__file__).resolve().parents[3] / "tools" / "tells_texto.py"

_spec = importlib.util.spec_from_file_location("tells_texto", TELLS_TEXTO)
tells_texto = importlib.util.module_from_spec(_spec)
# O dataclass do módulo procura o próprio módulo em sys.modules.
sys.modules[_spec.name] = tells_texto
_spec.loader.exec_module(tells_texto)

_ESTILO = re.compile(r"<style.*?</style>", re.S)
_COMENTARIO_JINJA = re.compile(r"\{#.*?#\}", re.S)
_COMENTARIO_HTML = re.compile(r"<!--.*?-->", re.S)
_TAG = re.compile(r"<[^>]+>")


def texto_visivel(fonte: str) -> str:
    """O que o leitor vê: sem CSS, sem comentário, sem tag, entidades decodificadas."""
    for padrao in (_ESTILO, _COMENTARIO_JINJA, _COMENTARIO_HTML):
        fonte = padrao.sub("", fonte)
    return html.unescape(_TAG.sub("\n", fonte))


ARQUIVOS = sorted(TEMPLATES.glob("*.html"))


def test_a_varredura_alcanca_os_templates_de_pdf_e_email():
    nomes = {a.name for a in ARQUIVOS}
    assert {"ata_template.html", "pop_template.html", "email_base.html"} <= nomes
    assert len(ARQUIVOS) >= 25


@pytest.mark.parametrize("arquivo", ARQUIVOS, ids=lambda a: a.name)
def test_template_sai_sem_cacoete_de_texto_gerado(arquivo):
    achados = tells_texto.achar_tells(texto_visivel(arquivo.read_text(encoding="utf-8")))
    assert [(o.cacoete, o.trecho) for o in achados] == []


@pytest.mark.parametrize("arquivo", ARQUIVOS, ids=lambda a: a.name)
def test_template_sai_sem_travessao_nem_escrito_como_entidade(arquivo):
    texto = texto_visivel(arquivo.read_text(encoding="utf-8"))
    assert "—" not in texto
    assert "–" not in texto
