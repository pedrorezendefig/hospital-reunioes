"""O Quadro da Tecnologia no Kit de conhecimento (issue #1642, ADR 0090).

Na tela do computador a aba Conversas virou o Quadro, com os pedidos em colunas
pela Etapa, e o Assistente saiu da tela inicial para o botao "Novo pedido". O
kit e a lingua em que o Assistente fala com o diretor: sem o Quadro escrito,
ele mandaria o diretor procurar a lista ao lado da conversa e o "Nova conversa"
que, no computador, nao existem mais.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.conhecimento import CONHECIMENTO_DIR  # noqa: E402


def _abertura_da_aba() -> str:
    """O texto antes da primeira secao: onde o kit diz o que a aba tem."""
    texto = (CONHECIMENTO_DIR / "tecnologia.md").read_text(encoding="utf-8")
    return texto.split("\n## ", 1)[0]


def test_o_kit_diz_que_a_aba_e_um_quadro_por_etapa():
    abertura = _abertura_da_aba()

    assert "**Quadro**" in abertura
    assert "colunas pela Etapa" in abertura
    for etapa in ("Registrada", "Em análise", "Planejada", "Em desenvolvimento", "Entregue"):
        assert etapa in abertura, etapa


def test_o_kit_diz_onde_fica_o_novo_pedido():
    abertura = _abertura_da_aba()

    assert "**Novo pedido**, no alto da aba" in abertura


def test_o_kit_diz_que_no_celular_a_lista_continua():
    abertura = _abertura_da_aba()

    assert "No celular" in abertura


def test_o_kit_diz_que_o_pedido_abre_num_painel_ao_lado_do_quadro():
    """Issue #1643: o clique no card abre o pedido num painel ao lado do Quadro,
    que continua a vista, e o Ampliar leva a tela toda."""
    abertura = _abertura_da_aba()

    assert "abre o pedido num painel ao lado do Quadro" in abertura
    assert "O clique num card abre o pedido na tela toda" not in abertura
    assert "**Ampliar**" in abertura
