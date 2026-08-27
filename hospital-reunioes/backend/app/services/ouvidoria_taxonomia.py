"""O tipo da manifestação e a regra de sigilo que sai dele (issue #372).

Até aqui o sigilo era decidido por texto livre: `nasce_sigilosa()` procurava as
palavras "denuncia" e "relato de conduta" no que o ouvidor tinha digitado. Um
caso classificado como "Assédio moral" não casava com nenhuma das duas, e o
email de acionamento chegava ao setor acusado com o nome de quem manifestou.

A partir daqui quem decide é o tipo, que é lista fechada (ADR 0034, decisão 1).
O texto livre continua existindo como rótulo humano na coluna `categoria`, mas
não decide nada.
"""

from __future__ import annotations

from typing import Literal

# A lista fechada. Vive aqui e no CHECK da migration 077: a aplicação recusa
# antes, o banco recusa depois, e nenhuma das duas confia na outra.
TipoManifestacao = Literal["denuncia", "reclamacao", "sugestao", "elogio", "relato_de_conduta"]
TIPOS_MANIFESTACAO: tuple[str, ...] = ("denuncia", "reclamacao", "sugestao", "elogio", "relato_de_conduta")

# O marcador de "ainda não classificado" que o canal aberto grava. `categoria`,
# `setor` e `resumo` são NOT NULL com CHECK anti-vazio desde a migration 063, e
# o formulário público não pergunta nem o tema nem a área: em vez de um palpite
# que passaria por classificação de verdade, o caso entra marcado.
#
# Vive aqui, e não na rota que o escreve, porque quem CONTA precisa reconhecê-lo
# tanto quanto quem grava: "A classificar" liderando os cinco temas mais
# frequentes é a fila de triagem aparecendo como se fosse tema (PRD #319).
CATEGORIA_PENDENTE = "A classificar"
SETOR_PENDENTE = "A definir"
NAO_CLASSIFICADO = frozenset({CATEGORIA_PENDENTE, SETOR_PENDENTE})

# Sigilosos por natureza (ADR 0034, decisão 1): o sigilo vem junto do tipo, sem
# ato humano, nos três canais de entrada.
TIPOS_SIGILOSOS = frozenset({"denuncia", "relato_de_conduta"})


def nasce_sigilosa(tipo: str | None) -> bool:
    """O caso nasce sigiloso?

    Fail-closed: sem tipo, o caso ainda não foi classificado, e o índice de
    quem está fora da Ouvidoria mostra o `resumo`, que é o começo do relato.
    Uma denúncia escrita no formulário público viraria texto visível na fila de
    todo mundo até alguém classificar. A saída é a classificação, não afrouxar
    a entrada (issue #372, decisão 4)."""
    return tipo is None or tipo in TIPOS_SIGILOSOS


# O rótulo que aparece na trilha do caso e na tela. O valor gravado é o da
# lista fechada; o humano lê a palavra dele.
ROTULO_TIPO: dict[str, str] = {
    "denuncia": "Denúncia",
    "reclamacao": "Reclamação",
    "sugestao": "Sugestão",
    "elogio": "Elogio",
    "relato_de_conduta": "Relato de conduta",
}


class SigiloTravadoError(ValueError):
    """Pedido de abaixar o sigilo de um tipo que é sigiloso por natureza."""


def resolver_sigilo(tipo: str | None, *, sigilo_atual: bool, sigilo_pedido: bool | None) -> bool:
    """O sigilo do caso depois da classificação.

    A regra automática é PISO, nunca teto: o tipo sigiloso por natureza sobe o
    sigilo sozinho e não aceita descer (issue #372, decisão 5), e para os
    demais o ouvidor decide, inclusive elevando um caso que a lista não previu.
    Sem pedido explícito, o sigilo de hoje é mantido: descer é ato consciente,
    não efeito colateral de classificar."""
    if nasce_sigilosa(tipo):
        if sigilo_pedido is False:
            raise SigiloTravadoError(
                "Denúncia e relato de conduta são sigilosos por natureza: o sigilo não pode ser retirado."
            )
        return True
    return sigilo_atual if sigilo_pedido is None else sigilo_pedido
