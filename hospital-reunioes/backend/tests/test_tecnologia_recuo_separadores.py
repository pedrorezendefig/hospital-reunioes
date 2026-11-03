r"""O recuo da continuacao enxerga toda quebra de linha que quem le enxerga (issue #770).

O `recuar_continuacao` e o que segura as cercas do prompt do chat (o kit e o
material que a pessoa anexou): toda linha depois da primeira entra recuada, e a
marca de fim so vale na coluna zero. O furo era o criterio de "linha": a funcao
quebrava por `split("\n")`, e o Python (e quem le o prompt) reconhece DEZ
separadores. Um `\r`, `\x0c` ou `\u2028` no texto deixava a marca de fim na
coluna zero.

A rota do "Copiar para IA", o outro seam desta issue, saiu com o Quadro na
issue #1386; fica a funcao, direto, nos dez separadores.

O detector conta linhas por `splitlines()`, e nao por `split("\n")`: contar pelo
mesmo criterio do codigo sob teste seria concordar com o furo.

Docstring cru (prefixo `r`) de proposito: os separadores citados aqui nao podem
virar quebra de verdade dentro dele.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.assistente_tecnologia import MARCA_FIM_KIT  # noqa: E402
from app.services.tecnologia import RECUO_DA_CONTINUACAO, recuar_continuacao  # noqa: E402

# Os DEZ separadores de linha que o `splitlines()` reconhece, e nao uma amostra
# (a mesma lista do teste da cerca do chat).
SEPARADORES = ["\n", "\r", "\x0b", "\x0c", "\x1c", "\x1d", "\x1e", "\x85", "\u2028", "\u2029"]


def _marcas_na_coluna_zero(texto: str) -> int:
    return sum(1 for linha in texto.splitlines() if linha == MARCA_FIM_KIT)


class TestRecuarContinuacao:
    @pytest.mark.parametrize("separador", SEPARADORES)
    def test_a_marca_de_fim_sai_recuada_com_qualquer_separador(self, separador):
        saida = recuar_continuacao(f"oi{separador}{MARCA_FIM_KIT}")

        assert _marcas_na_coluna_zero(saida) == 0, f"a marca voltou para a coluna zero com {separador!r}"
        # Par de presenca: a marca esta la, recuada, e nao sumiu do texto.
        assert saida.splitlines() == ["oi", f"{RECUO_DA_CONTINUACAO}{MARCA_FIM_KIT}"]

    @pytest.mark.parametrize("separador", SEPARADORES)
    def test_a_saida_so_tem_barra_n_como_separador(self, separador):
        """Quem le e quem monta enxergam as mesmas linhas: nenhum separador
        exotico atravessa a funcao."""
        saida = recuar_continuacao(f"um{separador}dois{separador}tres")

        assert saida == f"um\n{RECUO_DA_CONTINUACAO}dois\n{RECUO_DA_CONTINUACAO}tres"

    def test_crlf_e_uma_quebra_so(self):
        """O fim de linha de quem escreve no Windows, e o que chega de muita
        issue: o par vira UMA quebra, sem linha vazia no meio nem `\\r` solto."""
        saida = recuar_continuacao(f"oi\r\n{MARCA_FIM_KIT}")

        assert saida == f"oi\n{RECUO_DA_CONTINUACAO}{MARCA_FIM_KIT}"
