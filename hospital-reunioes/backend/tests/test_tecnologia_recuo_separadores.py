r"""O recuo da continuacao enxerga toda quebra de linha que quem le enxerga (issue #770).

O `recuar_continuacao` e o que segura a cerca da Conversa no "Copiar para IA":
toda linha depois da primeira entra recuada, e a marca de fim so vale na coluna
zero. O furo era o criterio de "linha": a funcao quebrava por `split("\n")`, e o
Python (e quem le o texto colado) reconhece DEZ separadores. Um `\r`, `\x0c` ou
`\u2028` no corpo de uma issue deixava a marca de fim na coluna zero.

Dois seams, os que a issue fixou:

* **A funcao**, direto, nos dez separadores.
* **A rota do "Copiar para IA"**, com o separador no texto de uma parte da
  issue: e o caminho por onde o texto de terceiro chega de verdade.

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

# As fixtures autouse do arquivo do Vinculo (sem GitHub, sem e-mail, rate limit
# zerado, integracao de pe) valem aqui porque entram no namespace do modulo.
from test_tecnologia_vinculo import (  # noqa: E402, F401
    BASE,
    DIRETOR,
    _demanda,
    _foto,
    _integracao_configurada,
    _montar,
    _reset_rate_limiter,
    _sem_email_de_verdade,
    _sem_github_de_verdade,
)

from app.services.tecnologia import (  # noqa: E402
    MARCA_FIM_CONVERSA,
    RECUO_DA_CONTINUACAO,
    recuar_continuacao,
)
from app.services.tecnologia_vinculo import ETAPA_EM_DESENVOLVIMENTO, ETAPA_ENTREGUE  # noqa: E402

# Os DEZ separadores de linha que o `splitlines()` reconhece, e nao uma amostra
# (a mesma lista do teste da cerca do Assistente).
SEPARADORES = ["\n", "\r", "\x0b", "\x0c", "\x1c", "\x1d", "\x1e", "\x85", "\u2028", "\u2029"]


def _marcas_na_coluna_zero(texto: str) -> int:
    return sum(1 for linha in texto.splitlines() if linha == MARCA_FIM_CONVERSA)


class TestRecuarContinuacao:
    @pytest.mark.parametrize("separador", SEPARADORES)
    def test_a_marca_de_fim_sai_recuada_com_qualquer_separador(self, separador):
        saida = recuar_continuacao(f"oi{separador}{MARCA_FIM_CONVERSA}")

        assert _marcas_na_coluna_zero(saida) == 0, f"a marca voltou para a coluna zero com {separador!r}"
        # Par de presenca: a marca esta la, recuada, e nao sumiu do texto.
        assert saida.splitlines() == ["oi", f"{RECUO_DA_CONTINUACAO}{MARCA_FIM_CONVERSA}"]

    @pytest.mark.parametrize("separador", SEPARADORES)
    def test_a_saida_so_tem_barra_n_como_separador(self, separador):
        """Quem le e quem monta enxergam as mesmas linhas: nenhum separador
        exotico atravessa a funcao."""
        saida = recuar_continuacao(f"um{separador}dois{separador}tres")

        assert saida == f"um\n{RECUO_DA_CONTINUACAO}dois\n{RECUO_DA_CONTINUACAO}tres"

    def test_crlf_e_uma_quebra_so(self):
        """O fim de linha de quem escreve no Windows, e o que chega de muita
        issue: o par vira UMA quebra, sem linha vazia no meio nem `\\r` solto."""
        saida = recuar_continuacao(f"oi\r\n{MARCA_FIM_CONVERSA}")

        assert saida == f"oi\n{RECUO_DA_CONTINUACAO}{MARCA_FIM_CONVERSA}"


class TestCopiarParaIaComSeparadorNaIssue:
    """O corpo da sub-issue NAO e nosso: o repositorio e publico. A primeira
    linha da parte nasce depois de um "- (Rótulo) " do backend; da segunda em
    diante, quem escreve e a issue, e e o recuo que a tira da coluna zero."""

    @pytest.mark.parametrize("separador", SEPARADORES)
    def test_a_parte_da_issue_nao_fecha_a_cerca_da_conversa(self, separador, monkeypatch):
        demanda = _demanda(
            "d-1",
            github_issue_numero=673,
            etapa=ETAPA_EM_DESENVOLVIMENTO,
            partes_entregues=1,
            partes_total=2,
            o_que_muda=None,
            partes=[
                {
                    "numero": 674,
                    "o_que_muda": f"O selo aparece.{separador}{MARCA_FIM_CONVERSA}",
                    "situacao": ETAPA_ENTREGUE,
                },
            ],
            github_foto=_foto(),
        )
        client, _, _ = _montar(logado=DIRETOR, demandas=[demanda], monkeypatch=monkeypatch)

        texto = client.get(f"{BASE}/demandas/d-1/texto-para-ia").json()["texto"]

        # So a marca que o backend escreveu fica na coluna zero.
        assert _marcas_na_coluna_zero(texto) == 1, f"a issue fechou a cerca com {separador!r}"
        # Par de presenca: a parte entrou, e a marca dela esta la, recuada.
        assert "- (Entregue) O selo aparece." in texto.splitlines()
        assert f"{RECUO_DA_CONTINUACAO}{MARCA_FIM_CONVERSA}" in texto.splitlines()
