"""O Guia da faturista (issue #1121, PRD #1113, ADR 0070).

A faturista abre o Guia de uma Conta, vê o que corrigir linha por linha, marca
Feito, Não procede ou Bloqueado e conclui. As linhas reais chegam pelo
processamento, em outra fatia; aqui os testes semeiam `cm_guia_linha` direto.

A nota de entrada segue a spec do diretor (item 9.7): `100 × (1 − R$ apontado
÷ R$ devido)`, arredondada, mínimo 0. O exemplo da spec é a fonte do esperado:
9 linhas somam R$ 584,60 em valor absoluto e a nota 74 corresponde a um R$
devido de cerca de R$ 2.250.
"""

from __future__ import annotations

import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.contas_medicas.guia import nota_de_entrada  # noqa: E402

# As 9 linhas do exemplo: 584,60 em valor absoluto. Diferença com sinal:
# Incluir e preço a maior são positivos; Retirar e quantidade a menos, negativos.
# A soma com sinal dá 459,98; com 1.790,02 lançados, o R$ devido fica 2.250,00.
TOTAL_LANCADO_DO_EXEMPLO = 1790.02


def _linha(acao: str, valor: float | None, **campos) -> dict:
    base = {
        "id": f"l-{acao}-{valor}",
        "acao": acao,
        "valor_diferenca": valor,
        "preco_lancado": 1.0,
        "preco_tabela": 1.0,
        "estado": "EM_VALIDACAO" if acao == "VALIDAR" else "ABERTA",
    }
    return {**base, **campos}


def _nove_linhas_do_exemplo() -> list[dict]:
    return [
        _linha("INCLUIR", 68.40, id="luva"),
        _linha("AJUSTAR_QUANTIDADE", -4.17, id="lavagem"),
        _linha("RETIRAR", -19.97, id="senha", preco_tabela=None),
        _linha("CORRIGIR_PRECO", 12.72, id="agulha"),
        _linha("INCLUIR", 239.67, id="diaria-acompanhante"),
        _linha("INCLUIR", 120.00, id="fisioterapia"),
        _linha("CORRIGIR_PRECO", 45.50, id="cateter"),
        _linha("AJUSTAR_QUANTIDADE", -38.17, id="fita"),
        _linha("INCLUIR", 36.00, id="lanceta"),
    ]


# ═══════════════════════════════════════════════════════════════════════════
# 1. nota_de_entrada, o helper puro
# ═══════════════════════════════════════════════════════════════════════════


class TestNotaDeEntrada:
    def test_as_nove_linhas_do_exemplo_da_spec_dao_nota_74(self):
        nota = nota_de_entrada(_nove_linhas_do_exemplo(), TOTAL_LANCADO_DO_EXEMPLO)

        assert nota.apontado == Decimal("584.60")
        assert nota.devido == Decimal("2250.00")
        assert nota.nota == 74
        assert nota.itens_apontados == 9

    def test_linha_validar_fica_fora_da_nota_e_vai_para_o_em_validacao(self):
        linhas = [*_nove_linhas_do_exemplo(), _linha("VALIDAR", 1212.00, id="unidade-pendente")]

        nota = nota_de_entrada(linhas, TOTAL_LANCADO_DO_EXEMPLO)

        assert (nota.nota, nota.apontado, nota.itens_apontados) == (74, Decimal("584.60"), 9)
        assert nota.em_validacao == Decimal("1212.00")

    def test_linha_nao_conferido_fica_fora_da_nota(self):
        """Não conferido: Incluir sem preço de tabela (o valor saiu do unitário
        da própria conta) e linha sem valor nenhum."""
        linhas = [
            *_nove_linhas_do_exemplo(),
            _linha("INCLUIR", 300.00, id="preco-da-conta", preco_tabela=None),
            _linha("AJUSTAR_QUANTIDADE", None, id="sem-valor"),
        ]

        nota = nota_de_entrada(linhas, TOTAL_LANCADO_DO_EXEMPLO)

        assert (nota.nota, nota.apontado, nota.itens_apontados) == (74, Decimal("584.60"), 9)

    def test_retirar_sem_preco_de_tabela_entra_na_nota(self):
        """Retirar tira o que foi lançado: o valor vem da conta, não da tabela."""
        nota = nota_de_entrada([_linha("RETIRAR", -100.00, preco_tabela=None)], 1000)

        assert (nota.nota, nota.apontado) == (89, Decimal("100.00"))

    def test_nota_nunca_fica_abaixo_de_zero(self):
        nota = nota_de_entrada([_linha("INCLUIR", 500.00), _linha("RETIRAR", -900.00)], 1000)

        assert nota.nota == 0
