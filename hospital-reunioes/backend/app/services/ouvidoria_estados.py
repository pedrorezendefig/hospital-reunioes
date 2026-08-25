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
# A devolução por insuficiência (issue #334) acrescenta `respondido ->
# aguardando_area` e o laço `aguardando_area -> aguardando_area`: o PRD #318
# devolve "de respondido ou aguardando área, de volta para aguardando área".
# O laço existe porque o ouvidor pode ler a resposta e devolvê-la depois de o
# caso já ter voltado a esperar a área por outro caminho, e recusar ali
# obrigaria a Ouvidoria a decorar o estado antes de agir.
TRANSICOES: dict[str, frozenset[str]] = {
    "novo": frozenset({"em_classificacao"}),
    "em_classificacao": frozenset({"aguardando_area", "encerrado"}),
    "aguardando_area": frozenset({"respondido", "encerrado", "aguardando_area"}),
    "respondido": frozenset({"encerrado", "aguardando_area"}),
}

ESTADOS = frozenset(TRANSICOES) | {"encerrado"}

# Encerrar é o único ato que fecha o caso para o manifestante: exige dizer no
# que deu e por quê (RN do PRD, refletida no critério de aceite da #320).
DESFECHOS = frozenset({"procedente", "improcedente", "parcialmente_procedente", "sem_condicoes_de_apuracao"})


class TransicaoInvalidaError(Exception):
    """O caminho não existe no grafo (ex.: pular a etapa da área)."""


class DadosInsuficientesError(Exception):
    """O caminho existe, mas falta o que a regra exige para percorrê-lo."""


# De onde a volta para `aguardando_area` é DEVOLUÇÃO por insuficiência, e não
# o acionamento da área (issue #334). O acionamento vem de `em_classificacao` e
# não pede motivo; a devolução vem daqui e pede.
ORIGENS_DA_DEVOLUCAO = frozenset({"respondido", "aguardando_area"})


def e_devolucao(estado_atual: str, estado_novo: str) -> bool:
    """Se esta transição é a devolução por insuficiência. Quem chama usa isto
    para saber que precisa mexer no prazo e avisar a área."""
    return estado_novo == "aguardando_area" and estado_atual in ORIGENS_DA_DEVOLUCAO


def validar_transicao(
    estado_atual: str,
    estado_novo: str,
    desfecho: str | None = None,
    desfecho_descricao: str | None = None,
    motivo_devolucao: str | None = None,
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
    else:
        if desfecho is not None or desfecho_descricao is not None:
            # Desfecho é ato de encerramento: aceitar fora dele gravaria um
            # desfecho em caso ainda aberto (a RPC aplica COALESCE sem olhar o
            # estado, então o bloqueio precisa acontecer antes dela).
            raise DadosInsuficientesError("Desfecho só entra no encerramento")
        if e_devolucao(estado_atual, estado_novo) and not (motivo_devolucao or "").strip():
            # Mesma forma do desfecho no encerramento: o dado que a regra exige
            # é checado aqui, não em cada rota. Sem isto a transição genérica do
            # painel viraria porta de fundo da devolução, sem motivo, sem meio
            # prazo novo e sem aviso à área (issue #334).
            raise DadosInsuficientesError("Devolver por insuficiência exige o motivo")
