"""Máquina de estados da Manifestação (issue #320, ADR 0034).

Porta de entrada única: nenhuma rota escreve `status` direto. Quem muda o
estado passa por aqui, que valida a regra, e a gravação vai para a RPC
`ouvidoria_transicionar`, que aplica status e movimento na mesma transação.

O estado `aguardando_manifestante` (pausa) entrou na issue #335: falta dado de
quem reclamou, o relógio da área para, e a volta o retoma.
"""

from __future__ import annotations

from datetime import datetime, timedelta

# Grafo do PRD. Chave: estado atual. Valor: para onde pode ir.
# A devolução por insuficiência (issue #334) acrescenta `respondido ->
# aguardando_area` e o laço `aguardando_area -> aguardando_area`: o PRD #318
# devolve "de respondido ou aguardando área, de volta para aguardando área".
# O laço existe porque o ouvidor pode ler a resposta e devolvê-la depois de o
# caso já ter voltado a esperar a área por outro caminho, e recusar ali
# obrigaria a Ouvidoria a decorar o estado antes de agir.
#
# A issue #335 acrescenta a pausa (`aguardando_area <-> aguardando_manifestante`,
# mais o encerramento por abandono a partir dela) e tira de `encerrado` o
# caráter terminal: a reabertura por reincidência sai dali de volta para a
# área. `encerrado` continua sem saída nenhuma além dessa.
TRANSICOES: dict[str, frozenset[str]] = {
    "novo": frozenset({"em_classificacao"}),
    "em_classificacao": frozenset({"aguardando_area", "encerrado"}),
    "aguardando_area": frozenset({"respondido", "encerrado", "aguardando_area", "aguardando_manifestante"}),
    "aguardando_manifestante": frozenset({"aguardando_area", "encerrado"}),
    "respondido": frozenset({"encerrado", "aguardando_area"}),
    "encerrado": frozenset({"aguardando_area"}),
}

ESTADOS = frozenset(TRANSICOES)

# Encerrar é o único ato que fecha o caso para o manifestante: exige dizer no
# que deu e por quê (RN do PRD, refletida no critério de aceite da #320).
# `sem_retorno_do_manifestante` entrou na issue #335: o manifestante sumiu e o
# caso fecha sem apurar, sem culpar a área e sem entrar na conta de resolvido
# ou não resolvido.
DESFECHO_SEM_RETORNO = "sem_retorno_do_manifestante"
DESFECHOS = frozenset(
    {
        "procedente",
        "improcedente",
        "parcialmente_procedente",
        "sem_condicoes_de_apuracao",
        DESFECHO_SEM_RETORNO,
    }
)

# Os desfechos que ficam FORA da conta de resolvido versus não resolvido
# (PRD #318, história 12). Caso abandonado pelo manifestante não é acerto nem
# erro da Ouvidoria: contá-lo de qualquer um dos lados mente sobre o indicador.
DESFECHOS_NEUTROS = frozenset({DESFECHO_SEM_RETORNO})

# A janela da reincidência, em dias CORRIDOS (PRD #318, história 13). Corridos e
# não úteis de propósito: quem volta a reclamar conta o tempo no calendário da
# vida, não no expediente do hospital.
JANELA_REINCIDENCIA_DIAS = 30


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


def e_pausa(estado_atual: str, estado_novo: str) -> bool:
    """Se esta transição para o relógio da área (issue #335)."""
    return estado_atual == "aguardando_area" and estado_novo == "aguardando_manifestante"


def e_retomada(estado_atual: str, estado_novo: str) -> bool:
    """Se esta transição religa o relógio da área depois da pausa. Quem chama
    usa isto para devolver ao prazo o expediente que o caso ficou parado."""
    return estado_atual == "aguardando_manifestante" and estado_novo == "aguardando_area"


def e_reabertura(estado_atual: str, estado_novo: str) -> bool:
    """Se esta transição tira o caso do encerramento e o devolve à área. Único
    caminho de saída de `encerrado`, e o que marca a reincidência."""
    return estado_atual == "encerrado" and estado_novo == "aguardando_area"


def dentro_da_janela_de_reincidencia(encerrada_em: datetime, agora: datetime) -> bool:
    """Se o manifestante voltou a tempo de o caso original reabrir como
    reincidência (PRD #318, história 13).

    Fora da janela o retorno não é eco do mesmo problema: o caminho vira
    manifestação nova, e reabrir um caso velho embaralharia os marcos T0 a T3
    que os relatórios do PRD 3 leem."""
    return agora - encerrada_em <= timedelta(days=JANELA_REINCIDENCIA_DIAS)


def entra_no_indicador_de_resolucao(desfecho: str | None) -> bool:
    """Se este desfecho conta na divisão entre resolvido e não resolvido
    (PRD #318, história 12). O consumo é do PRD 3; aqui nasce o dado certo."""
    return desfecho is not None and desfecho not in DESFECHOS_NEUTROS


def validar_transicao(
    estado_atual: str,
    estado_novo: str,
    desfecho: str | None = None,
    desfecho_descricao: str | None = None,
    motivo_devolucao: str | None = None,
    motivo_reabertura: str | None = None,
) -> None:
    """Levanta se a transição não puder acontecer. Silêncio significa liberado."""
    if estado_novo not in ESTADOS:
        raise TransicaoInvalidaError(f"Estado desconhecido: {estado_novo}")

    permitidos = TRANSICOES.get(estado_atual, frozenset())
    if estado_novo not in permitidos:
        if estado_atual == "encerrado":
            raise TransicaoInvalidaError("Manifestação encerrada só volta a andar pela reabertura")
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
        if e_reabertura(estado_atual, estado_novo) and not (motivo_reabertura or "").strip():
            # Mesma guarda da devolução, pelo mesmo motivo: a reabertura tem
            # prazo novo e aviso ao setor, e a transição genérica do painel não
            # faz nenhum dos dois. Sem isto ela viraria porta de fundo que
            # devolve o caso à área sem relógio e sem ninguém saber (issue #335).
            raise DadosInsuficientesError("Reabrir a manifestação exige o motivo")
