"""Máquina de estados da Manifestação (issue #320, ADR 0034).

Porta de entrada única: nenhuma rota escreve `status` direto. Quem muda o
estado passa por aqui, que valida a regra, e a gravação vai para a RPC
`ouvidoria_transicionar`, que aplica status e movimento na mesma transação.

O estado `aguardando_manifestante` (pausa) é do PRD de governança de prazo e
não existe nesta fatia.
"""

from __future__ import annotations

# Grafo do PRD. Chave: estado atual. Valor: para onde pode ir.
# `encerrado` é terminal e por isso não aparece como chave.
TRANSICOES: dict[str, frozenset[str]] = {
    "novo": frozenset({"em_classificacao"}),
    "em_classificacao": frozenset({"aguardando_area", "encerrado"}),
    "aguardando_area": frozenset({"respondido", "encerrado"}),
    "respondido": frozenset({"encerrado"}),
}

ESTADOS = frozenset(TRANSICOES) | {"encerrado"}

# Encerrar é o único ato que fecha o caso para o manifestante: exige dizer no
# que deu e por quê (RN do PRD, refletida no critério de aceite da #320).
DESFECHOS = frozenset({"procedente", "improcedente", "parcialmente_procedente", "sem_condicoes_de_apuracao"})


class TransicaoInvalidaError(Exception):
    """O caminho não existe no grafo (ex.: pular a etapa da área)."""


class DadosInsuficientesError(Exception):
    """O caminho existe, mas falta o que a regra exige para percorrê-lo."""


def validar_transicao(
    estado_atual: str,
    estado_novo: str,
    desfecho: str | None = None,
    desfecho_descricao: str | None = None,
) -> None:
    """Levanta se a transição não puder acontecer. Silêncio significa liberado."""
    if estado_novo not in ESTADOS:
        raise TransicaoInvalidaError(f"Estado desconhecido: {estado_novo}")

    permitidos = TRANSICOES.get(estado_atual, frozenset())
    if estado_novo not in permitidos:
        if estado_atual == "encerrado":
            raise TransicaoInvalidaError("Manifestação encerrada não muda de estado")
        raise TransicaoInvalidaError(f"Não é possível ir de {estado_atual} para {estado_novo}")

    if estado_novo == "encerrado":
        if desfecho not in DESFECHOS:
            raise DadosInsuficientesError("Encerrar exige um desfecho válido")
        if not (desfecho_descricao or "").strip():
            raise DadosInsuficientesError("Encerrar exige a descrição do desfecho")
