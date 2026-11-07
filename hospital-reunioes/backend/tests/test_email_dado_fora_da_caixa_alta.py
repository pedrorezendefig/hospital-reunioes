"""Dado digitado fora da caixa alta nos e-mails (issue #1458, ADR 0080).

A conferência do aceite do diretor renderizou cada template de e-mail com um
marcador no lugar de cada variável impressa e procurou o marcador dentro de um
rótulo com `text-transform:uppercase`. Achou o nome de quem devolveu o POP no
rótulo "Comentários de ..." do e-mail de devolução. Dado digitado aparece como
foi escrito (decisão 3 da ADR 0080); código e rótulo do sistema podem subir.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

import pytest
from jinja2 import ChainableUndefined

from app.services.email_service import TEMPLATES_DIR, jinja_env

# Variável impressa direto: `{{ nome }}` ou `{{ nome | filtro }}`.
_IMPRESSA = re.compile(r"\{\{\s*([a-z_][a-z0-9_]*)\s*(?:\||\}\})")

# O que pode subir: código do POP (sigla, ADR 0080 decisão 4) e a etapa, que é
# rótulo do sistema ("Revisão", "Validação"), não dado digitado.
_PODE_SUBIR = {"codigo", "etapa_label"}

_SEM_FECHAMENTO = {"br", "img", "meta", "hr", "input", "link"}


def _marcador(variavel: str) -> str:
    return f"Marcador{variavel.replace('_', '')}Fim"


class _Leitor(HTMLParser):
    """Anda pelo HTML com a pilha do `text-transform` em vigor e anota o texto
    que o cliente de e-mail desenha em maiúscula."""

    def __init__(self) -> None:
        super().__init__()
        self._pilha: list[tuple[str, str]] = [("", "none")]
        self.em_caixa_alta: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in _SEM_FECHAMENTO:
            return
        estilo = dict(attrs).get("style") or ""
        achado = re.search(r"text-transform\s*:\s*([a-z]+)", estilo)
        self._pilha.append((tag, achado.group(1) if achado else self._pilha[-1][1]))

    def handle_endtag(self, tag):
        for i in range(len(self._pilha) - 1, 0, -1):
            if self._pilha[i][0] == tag:
                del self._pilha[i:]
                return

    def handle_data(self, data):
        if data.strip() and self._pilha[-1][1] == "uppercase":
            self.em_caixa_alta.append(data)


def _templates() -> list[str]:
    return sorted(p.name for p in Path(TEMPLATES_DIR).glob("email_*.html") if p.name != "email_base.html")


def _dados_em_caixa_alta(template: str) -> set[str]:
    fonte = (Path(TEMPLATES_DIR) / template).read_text(encoding="utf-8")
    variaveis = set(_IMPRESSA.findall(fonte)) - {"titulo"}
    ambiente = jinja_env.overlay(undefined=ChainableUndefined)
    html = ambiente.get_template(template).render(**{v: _marcador(v) for v in variaveis})

    leitor = _Leitor()
    leitor.feed(html)
    texto = " ".join(leitor.em_caixa_alta)
    return {v for v in variaveis if _marcador(v) in texto}


@pytest.mark.parametrize("template", _templates())
def test_dado_digitado_nao_aparece_em_caixa_alta_no_email(template):
    assert _dados_em_caixa_alta(template) <= _PODE_SUBIR


def test_nome_de_quem_devolveu_o_pop_aparece_como_foi_escrito():
    assert "autor_nome" not in _dados_em_caixa_alta("email_pop_devolucao.html")


def test_o_leitor_enxerga_o_codigo_do_pop_no_rotulo_em_caixa_alta():
    # Sem isto, um leitor que nunca acha nada passaria os testes acima.
    assert "codigo" in _dados_em_caixa_alta("email_pop_criado.html")
