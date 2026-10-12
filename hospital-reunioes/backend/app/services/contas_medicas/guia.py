"""O Guia da faturista: a nota de entrada e os números do topo (issue #1121,
PRD #1113, ADR 0070).

Função pura sobre as linhas de `cm_guia_linha` como o banco as devolve
(dicts). A fórmula é a da spec do diretor (item 9.7):

* diferença da linha: valor com sinal (Incluir e preço a maior, positivo;
  Retirar e quantidade a menos, negativo);
* R$ apontado (o "R$ a ajustar" da tela): soma dos valores absolutos, sem as
  linhas Validar e sem as Não conferido;
* R$ devido: total lançado na conta mais as diferenças com sinal das mesmas
  linhas que entram no apontado;
* nota: `100 × (1 − R$ apontado ÷ R$ devido)`, arredondada, mínimo 0;
* R$ em validação: soma das linhas Validar, mostrada à parte.

A conclusão chama a mesma função sem as linhas Não procede: é a `nota_entrada`
que o Painel usa. A original fica em `nota_bruta`.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

CENTAVO = Decimal("0.01")


def _dinheiro(valor) -> Decimal:
    return Decimal(str(valor or 0)).quantize(CENTAVO, rounding=ROUND_HALF_UP)


def linha_nao_conferida(linha: dict) -> bool:
    """A linha cujo valor não foi conferido contra a tabela da operadora.

    É a etiqueta cinza "Não conferido": fica fora da nota e do R$ a ajustar.
    Vale para a linha sem valor e para a que ficou sem preço de tabela (o
    valor saiu do unitário da própria conta, ou não saiu). Retirar não entra:
    tira o que foi lançado, e o valor é o da conta. Validar tem conta própria.
    """
    if linha.get("acao") == "VALIDAR":
        return False
    if linha.get("valor_diferenca") is None:
        return True
    return linha.get("acao") != "RETIRAR" and linha.get("preco_tabela") is None


@dataclass(frozen=True)
class NotaDeEntrada:
    nota: int
    apontado: Decimal
    devido: Decimal
    em_validacao: Decimal
    itens_apontados: int


def nota_de_entrada(linhas: Iterable[dict], total_lancado) -> NotaDeEntrada:
    """A nota de entrada da Conta e os valores que a tela mostra no topo."""
    apontado = Decimal("0.00")
    com_sinal = Decimal("0.00")
    em_validacao = Decimal("0.00")
    itens = 0
    for linha in linhas:
        valor = _dinheiro(linha.get("valor_diferenca"))
        if linha.get("acao") == "VALIDAR":
            em_validacao += abs(valor)
            continue
        if linha_nao_conferida(linha):
            continue
        apontado += abs(valor)
        com_sinal += valor
        itens += 1
    devido = _dinheiro(total_lancado) + com_sinal
    if devido <= 0:
        nota = 100 if apontado == 0 else 0
    else:
        nota = max(0, int((Decimal(100) * (1 - apontado / devido)).quantize(Decimal(1), rounding=ROUND_HALF_UP)))
    return NotaDeEntrada(
        nota=nota,
        apontado=apontado,
        devido=devido,
        em_validacao=em_validacao,
        itens_apontados=itens,
    )
