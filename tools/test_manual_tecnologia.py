"""A página do manual da aba Tecnologia mostra a tela de hoje (issue #1066).

A aba fica fora do site do Manual (ADR 0057) e tem página própria em
`docs/manual/tecnologia/index.html`. O que dá para provar de um texto curado é
que cada parte da tela nova tem o seu print, e que todo print citado existe:
uma imagem citada e não commitada sai como moldura vazia no site publicado.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PASTA = Path(__file__).resolve().parents[1] / "docs" / "manual" / "tecnologia"
PAGINA = PASTA / "index.html"

# As partes da tela que o PRD #1056 mudou, cada uma com o print que a mostra e
# a seção da página onde ele mora.
PRINT_DA_PARTE = {
    "quadro": ("img/quadro.png", "quadro"),
    "painel": ("img/painel.png", "avisos"),
    "card com anexos": ("img/card.png", "anexos"),
    "produtos pela engrenagem": ("img/produtos.png", "onde"),
}


def _html() -> str:
    return PAGINA.read_text(encoding="utf-8")


def _imagens_citadas(html: str) -> list[str]:
    return re.findall(r'<img[^>]*\ssrc="(img/[^"]+)"', html)


def _trecho_da_secao(html: str, ancora: str) -> str:
    """Do `id` da âncora até o fim da `<section>` que a contém."""
    inicio = html.index(f'id="{ancora}"')
    return html[inicio : html.index("</section>", inicio)]


@pytest.mark.parametrize("parte", sorted(PRINT_DA_PARTE))
def test_cada_parte_da_tela_nova_tem_o_seu_print_na_secao_certa(parte):
    imagem, ancora = PRINT_DA_PARTE[parte]
    assert f'src="{imagem}"' in _trecho_da_secao(_html(), ancora)


def test_todo_print_citado_existe_na_pasta():
    citadas = _imagens_citadas(_html())
    assert len(citadas) >= len(PRINT_DA_PARTE) + 1  # piso: os novos e o do assistente
    assert [imagem for imagem in citadas if not (PASTA / imagem).is_file()] == []


def test_a_etapa_em_producao_esta_na_tabela_das_etapas():
    etapas = _trecho_da_secao(_html(), "seisetapas")
    assert '<span class="etapa e-pro">Em produção</span>' in etapas


def test_o_detector_de_imagem_ve_o_src():
    """O detector também tem mutante: uma regex que não casa daria a lista
    vazia, e a varredura de existência passaria verde sobre nada."""
    assert _imagens_citadas('<figure><img alt="x" src="img/a.png"></figure>') == ["img/a.png"]
