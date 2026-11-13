"""A orientação embutida da Ouvidoria no Kit de conhecimento (issue #1629,
PRD #1527, ADR 0056 decisão 2).

As telas são do frontend e têm teste lá. Aqui se prova o critério do kit: o
Assistente de Tecnologia responde sobre a Ouvidoria pelo que lê nele, e se o
texto não contar a tela Como funciona e o resto da orientação, ele diz que a
pessoa nova precisa do manual.
"""

from __future__ import annotations

import pytest

from app.services.conhecimento import CONHECIMENTO_DIR

PASSOS = (
    "a manifestação chega",
    "você confere tipo, setor e gravidade",
    "se o sistema alertar, decide sobre o NSP",
    "envia à área e acompanha o prazo",
    "revisa a resposta e envia ao manifestante",
)


@pytest.fixture
def texto() -> str:
    return (CONHECIMENTO_DIR / "ouvidoria.md").read_text(encoding="utf-8")


@pytest.fixture
def secao(texto) -> str:
    """A seção da orientação, do título até o próximo título."""
    marca = "## A orientação nas telas\n"
    assert marca in texto
    resto = texto.split(marca, 1)[1]
    return resto.split("\n## ", 1)[0]


def test_conta_a_tela_como_funciona_com_os_cinco_passos_na_ordem(secao):
    assert "Como funciona a Ouvidoria" in secao
    assert "atalhos" in secao
    posicoes = [secao.find(passo) for passo in PASSOS]
    assert -1 not in posicoes, [p for p, pos in zip(PASSOS, posicoes) if pos == -1]
    assert posicoes == sorted(posicoes)


def test_conta_a_frase_do_topo_o_interrogacao_a_lista_vazia_e_a_legenda(secao):
    assert "frase no topo" in secao
    assert "ponto de interrogação" in secao
    assert "lista vazia diz por que está vazia" in secao
    assert "Legenda" in secao


def test_conta_que_o_botao_da_validacao_virou_enviar_a_area(secao):
    assert "Enviar à área" in secao


def test_a_decisao_entra_na_lista_do_que_ja_foi_decidido(texto):
    decidido = texto.split("## O que já foi decidido\n", 1)[1].split("\n## ", 1)[0]
    achados = [linha for linha in decidido.splitlines() if "Como funciona a Ouvidoria" in linha]
    assert len(achados) == 1, achados
