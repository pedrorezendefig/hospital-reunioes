"""A regra do ciclo de vida da Pendência (ADR 0098, decisões 4 e 5; issue #1862).

Função pura: recebe quem age, o comando e o estado atual, e devolve a mudança
(estado, prazo, conclusão e se conta atraso) ou recusa. Não lê nem grava
nada; quem grava é a função `registrar_acao_da_pendencia` do Postgres
(migration 169), que atualiza a Pendência e insere o evento no Histórico na
mesma transação.

O banco guarda quatro estados. Atrasada é calculada (aberta com prazo
vencido) e Repactuada também (há Repactuação no histórico).

A Contestação (issue #1870): só o responsável contesta o item, e só com a Ata
em assinatura; o Facilitador e o Super admin ajustam ou recusam. Nenhum dos
três muda o estado, então o item contestado segue cobrado. O ajuste corrige o
prazo, o responsável ou os dois. Se há Contestação aberta sai do histórico e
chega aqui como `contestada`.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from enum import StrEnum


class Comando(StrEnum):
    INICIAR = "iniciar"
    ANOTAR = "anotar"
    CONCLUIR = "concluir"
    REPACTUAR = "repactuar"
    CANCELAR = "cancelar"
    REABRIR = "reabrir"
    CONTESTAR = "contestar"
    AJUSTAR = "ajustar"
    RECUSAR = "recusar"


class Papel(StrEnum):
    RESPONSAVEL = "responsavel"
    CO_RESPONSAVEL = "co_responsavel"
    FACILITADOR = "facilitador"
    SUPER_ADMIN = "super_admin"


ABERTOS = frozenset({"PENDENTE", "EM_PROGRESSO"})
FECHADOS = frozenset({"CONCLUIDO", "CANCELADO"})

_DO_RESPONSAVEL = frozenset({Comando.INICIAR, Comando.ANOTAR, Comando.CONCLUIR, Comando.REPACTUAR})

# Só o responsável pelo item contesta (decisão 12 do diretor no PRD #1757).
PERMISSOES: dict[Papel, frozenset[Comando]] = {
    Papel.RESPONSAVEL: _DO_RESPONSAVEL | {Comando.CONTESTAR},
    Papel.CO_RESPONSAVEL: _DO_RESPONSAVEL,
    Papel.FACILITADOR: frozenset(
        {Comando.REPACTUAR, Comando.CANCELAR, Comando.REABRIR, Comando.AJUSTAR, Comando.RECUSAR}
    ),
    Papel.SUPER_ADMIN: frozenset(Comando) - {Comando.CONTESTAR},
}

# De onde cada comando parte.
_PARTIDA: dict[Comando, frozenset[str]] = {
    Comando.INICIAR: frozenset({"PENDENTE"}),
    Comando.ANOTAR: ABERTOS,
    Comando.CONCLUIR: ABERTOS,
    Comando.REPACTUAR: ABERTOS,
    Comando.CANCELAR: ABERTOS,
    Comando.REABRIR: FECHADOS,
    Comando.CONTESTAR: ABERTOS,
    Comando.AJUSTAR: ABERTOS,
    Comando.RECUSAR: ABERTOS,
}

_COM_PRAZO_NOVO = frozenset({Comando.REPACTUAR, Comando.REABRIR})
# O ajuste pode trocar o prazo, e pode não trocar (o erro era outro).
_PRAZO_NOVO_OPCIONAL = frozenset({Comando.AJUSTAR})
_RESPONDEM_A_CONTESTACAO = frozenset({Comando.AJUSTAR, Comando.RECUSAR})


class AcaoRecusada(Exception):  # noqa: N818, o nome do domínio
    """`tipo`: `permissao` (quem age não pode), `transicao` (não parte deste
    estado) ou `dados` (anotação vazia, prazo novo ausente ou no passado)."""

    def __init__(self, tipo: str, motivo: str):
        super().__init__(motivo)
        self.tipo = tipo
        self.motivo = motivo


@dataclass(frozen=True)
class Mudanca:
    status: str
    prazo: date | None
    # True grava a data de conclusão, False a apaga, None não mexe.
    concluida: bool | None
    # Repactuação ou Reabertura feita com o prazo já vencido (ranking).
    conta_atraso: bool
    # O responsável novo do ajuste (issue #1870); None não mexe.
    responsavel_id: str | None = None


def esta_atrasada(status: str, prazo: date | None, hoje: date) -> bool:
    """O prazo de um dia só vence quando esse dia acaba."""
    return status in ABERTOS and prazo is not None and prazo < hoje


def situacao(status: str, prazo: date | None, hoje: date, *, repactuada: bool) -> str:
    """O que a tela mostra: o estado gravado, ou ATRASADO e REPACTUADA,
    calculados, para a Pendência aberta."""
    if esta_atrasada(status, prazo, hoje):
        return "ATRASADO"
    if status in ABERTOS and repactuada:
        return "REPACTUADA"
    return status


def _permitidos(papeis: Iterable[Papel]) -> frozenset[Comando]:
    return frozenset().union(*(PERMISSOES[p] for p in papeis))


def _cabe_no_momento(comando: Comando, *, ata_em_assinatura: bool, contestada: bool) -> bool:
    """A Contestação só vale com a Ata em assinatura e sem outra aberta;
    ajustar e recusar só respondem a uma Contestação aberta."""
    if comando is Comando.CONTESTAR:
        return ata_em_assinatura and not contestada
    if comando in _RESPONDEM_A_CONTESTACAO:
        return contestada
    return True


def acoes_disponiveis(
    papeis: Iterable[Papel], status: str, *, ata_em_assinatura: bool = False, contestada: bool = False
) -> list[Comando]:
    """Os comandos que quem age pode dar agora, na ordem do enum."""
    permitidos = _permitidos(papeis)
    return [
        c
        for c in Comando
        if c in permitidos
        and status in _PARTIDA[c]
        and _cabe_no_momento(c, ata_em_assinatura=ata_em_assinatura, contestada=contestada)
    ]


def decidir(
    comando: Comando,
    papeis: Iterable[Papel],
    *,
    status: str,
    prazo: date | None,
    hoje: date,
    anotacao: str | None,
    prazo_novo: date | None = None,
    responsavel_novo: str | None = None,
    ata_em_assinatura: bool = False,
    contestada: bool = False,
) -> Mudanca:
    if comando not in _permitidos(papeis):
        raise AcaoRecusada("permissao", "Você não pode fazer esta ação nesta pendência.")
    if not (anotacao or "").strip():
        raise AcaoRecusada("dados", "Escreva a anotação: toda ação na pendência pede uma.")
    if status not in _PARTIDA[comando]:
        raise AcaoRecusada("transicao", f"Esta ação não vale para uma pendência {status}.")
    if comando is Comando.CONTESTAR and not ata_em_assinatura:
        raise AcaoRecusada("transicao", "Só dá para contestar o item enquanto a Ata está em assinatura.")
    if comando is Comando.CONTESTAR and contestada:
        raise AcaoRecusada("transicao", "Este item já está contestado. Espere o facilitador responder.")
    if comando in _RESPONDEM_A_CONTESTACAO and not contestada:
        raise AcaoRecusada("transicao", "Não há contestação aberta neste item.")

    if comando in _COM_PRAZO_NOVO and prazo_novo is None:
        raise AcaoRecusada("dados", "Informe o prazo novo.")
    if prazo_novo is not None:
        if comando not in _COM_PRAZO_NOVO | _PRAZO_NOVO_OPCIONAL:
            raise AcaoRecusada("dados", "Só repactuar, reabrir e ajustar mudam o prazo.")
        if prazo_novo < hoje:
            raise AcaoRecusada("dados", "O prazo novo não pode estar no passado.")
    if responsavel_novo is not None and comando is not Comando.AJUSTAR:
        raise AcaoRecusada("dados", "Só o ajuste de uma contestação troca o responsável.")

    vencido = prazo is not None and prazo < hoje

    if comando is Comando.INICIAR:
        return Mudanca("EM_PROGRESSO", prazo, None, False)
    if comando in (Comando.ANOTAR, Comando.CONTESTAR, Comando.RECUSAR):
        return Mudanca(status, prazo, None, False)
    if comando is Comando.AJUSTAR:
        return Mudanca(status, prazo_novo or prazo, None, False, responsavel_novo)
    if comando is Comando.CONCLUIR:
        return Mudanca("CONCLUIDO", prazo, True, False)
    if comando is Comando.CANCELAR:
        return Mudanca("CANCELADO", prazo, None, False)
    if comando is Comando.REPACTUAR:
        return Mudanca(status, prazo_novo, None, vencido)
    # REABRIR
    return Mudanca("PENDENTE", prazo_novo, False, vencido)
