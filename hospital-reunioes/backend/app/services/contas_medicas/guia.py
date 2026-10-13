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
            # A descartada na Validação (Decidida sem ação) já não está em jogo.
            if linha.get("estado") != "DECIDIDA":
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


# A ordem das ações dentro do grupo (spec, item 9.8).
ORDEM_DAS_ACOES = ("INCLUIR", "AJUSTAR_QUANTIDADE", "CORRIGIR_PRECO", "RETIRAR", "VALIDAR")

# O que a faturista marca. Em validação e Decidida não são dela.
MARCADAS = ("FEITO", "NAO_PROCEDE", "BLOQUEADO")

# O que deixa a Conta "Concluída com pendência": linha sem marcação, em
# validação ou bloqueada (spec, item 5).
PENDENTES = ("ABERTA", "EM_VALIDACAO", "BLOQUEADO")


def linha_decidida_a_lancar(linha: dict) -> bool:
    """A linha que a Validação decidiu com uma ação (issue #1142): volta para a
    faturista lançar no MV, e até ela marcar conta como linha sem marcação."""
    return linha.get("estado") == "DECIDIDA" and linha.get("acao") != "VALIDAR"


def linha_pendente(linha: dict) -> bool:
    """A linha que deixa a Conta "Concluída com pendência"."""
    return linha.get("estado") in PENDENTES or linha_decidida_a_lancar(linha)


def _chave_de_ordem(linha: dict) -> tuple:
    acao = linha.get("acao")
    posicao = ORDEM_DAS_ACOES.index(acao) if acao in ORDEM_DAS_ACOES else len(ORDEM_DAS_ACOES)
    data = linha.get("data")
    setor = linha.get("setor")
    ordem = linha.get("ordem")
    return (data is None, data or "", setor is None, setor or "", posicao, ordem is None, ordem or 0)


def agrupar_por_dia_e_setor(linhas: Iterable[dict]) -> list[dict]:
    """As linhas em ordem de data, setor e ação, num grupo por dia e setor."""
    grupos: list[dict] = []
    for linha in sorted(linhas, key=_chave_de_ordem):
        chave = (linha.get("data"), linha.get("setor"))
        if not grupos or (grupos[-1]["data"], grupos[-1]["setor"]) != chave:
            grupos.append({"data": chave[0], "setor": chave[1], "linhas": []})
        grupos[-1]["linhas"].append({**linha, "nao_conferido": linha_nao_conferida(linha)})
    return grupos


def numeros_do_topo(linhas: list[dict], total_lancado, *, concluida: bool) -> dict:
    """Os três números do topo do Guia.

    Antes da conclusão a nota é a bruta, com todas as linhas; depois, a de
    entrada, sem as Não procede. Itens feitos conta as linhas que a faturista
    já marcou (Feito, Não procede ou Bloqueado), de todas as que são dela.
    """
    da_nota = [linha for linha in linhas if linha.get("estado") != "NAO_PROCEDE"] if concluida else linhas
    nota = nota_de_entrada(da_nota, total_lancado)
    dela = [linha for linha in linhas if linha.get("acao") != "VALIDAR"]
    return {
        "nota_entrada": nota.nota,
        "valor_a_ajustar": float(nota.apontado),
        "itens_a_ajustar": nota.itens_apontados,
        "valor_em_validacao": float(nota.em_validacao),
        "itens_feitos": sum(1 for linha in dela if linha.get("estado") in MARCADAS),
        "itens_total": len(dela),
        "itens_sem_marcacao": sum(
            1 for linha in dela if linha.get("estado") == "ABERTA" or linha_decidida_a_lancar(linha)
        ),
    }
