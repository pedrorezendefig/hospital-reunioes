"""As Entregas da Tecnologia (issue #1556, PRD #1548, ADR 0084, decisao 8).

Regras puras, sem I/O: o router le as Demandas e passa por aqui. Conta por
card, nunca por parte. Entregue e a Demanda com a data de entrega que o
Documento do card mostra (`entregue_na_data`: o fechamento da issue-raiz, so
com a Etapa Entregue ou Em producao). O dia e o do hospital, em Sao Paulo: o
card fechado as 22h de domingo e do domingo, e nao da segunda em UTC.
"""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

from app.services.tecnologia import (
    ORIGEM_DIRETOR,
    entregue_na_data,
    instante_do_banco,
    login_do_responsavel,
    origem_da_demanda,
    responsavel_da_demanda,
)

FUSO_DO_HOSPITAL = ZoneInfo("America/Sao_Paulo")

Agrupamento = Literal["semana", "mes"]
Tamanho = Literal["P", "M", "G"]


def tamanho_da_entrega(partes: int | None) -> Tamanho:
    """O Tamanho da entrega pelo numero de partes (ADR 0092, decisao 3): ate 1
    parte e P, de 2 a 5 e M, 6 ou mais e G. Nunca estimado nem digitado; o bug
    sem sub-issue (partes nulas) e P."""
    if (partes or 0) <= 1:
        return "P"
    if partes <= 5:
        return "M"
    return "G"


def dia_da_entrega(demanda: dict[str, Any]) -> date | None:
    """O dia do hospital em que o card foi entregue, ou `None` se nao foi."""
    instante = instante_do_banco(entregue_na_data(demanda))
    return instante.astimezone(FUSO_DO_HOSPITAL).date() if instante else None


def chave_do_responsavel(demanda: dict[str, Any]) -> str | None:
    """O valor do filtro Responsavel: o id do usuario, ou o login do dono no
    GitHub quando ele nao e usuario do app (issue #1534)."""
    return responsavel_da_demanda(demanda) or login_do_responsavel(demanda)


def inicio_do_periodo(dia: date, agrupar: Agrupamento) -> date:
    """A segunda-feira da semana, ou o dia 1 do mes."""
    if agrupar == "mes":
        return dia.replace(day=1)
    return dia - timedelta(days=dia.weekday())


def contagem(dias: list[date], agrupar: Agrupamento) -> list[dict[str, Any]]:
    """Quantos cards por periodo, do mais recente para o mais antigo. Periodo
    sem entrega nao aparece."""
    contados = Counter(inicio_do_periodo(dia, agrupar) for dia in dias)
    return [{"inicio": inicio.isoformat(), "total": total} for inicio, total in sorted(contados.items(), reverse=True)]


SEMANAS_DO_GRAFICO = 12
SEMANAS_DO_TOPO = 4


def dia_do_pedido(demanda: dict[str, Any]) -> date | None:
    """O dia do hospital em que o card nasceu, ou `None` na conversa sem card.

    A criacao da issue-raiz que a foto do GitHub guarda (`criada_em`, issue
    #1702) vale para as duas Origens: na do diretor, ela e o proprio Criar o
    card. Sem ela, o Criar o card que o app gravou (`envio_em`) na Origem
    diretor e, por ultimo, a criacao da Demanda, que na Origem Vitta e o dia em
    que o app carregou a issue.
    """
    if not demanda.get("github_issue_numero"):
        return None
    foto = demanda.get("github_foto") if isinstance(demanda.get("github_foto"), dict) else {}
    candidatos = [foto.get("criada_em")]
    if origem_da_demanda(demanda) == ORIGEM_DIRETOR:
        candidatos.append(demanda.get("envio_em"))
    candidatos.append(demanda.get("criado_em"))
    for candidato in candidatos:
        if (instante := instante_do_banco(candidato)) is not None:
            return instante.astimezone(FUSO_DO_HOSPITAL).date()
    return None


def ritmo(demandas: list[dict[str, Any]], *, agora: datetime) -> dict[str, Any]:
    corrente = inicio_do_periodo(agora.astimezone(FUSO_DO_HOSPITAL).date(), "semana")
    do_topo = corrente - timedelta(weeks=SEMANAS_DO_TOPO - 1)
    das_anteriores = do_topo - timedelta(weeks=SEMANAS_DO_TOPO)
    inicios = [corrente - timedelta(weeks=atras) for atras in range(SEMANAS_DO_GRAFICO - 1, -1, -1)]
    semanas = {inicio: {"inicio": inicio.isoformat(), "pedidos": 0, "entregas": []} for inicio in inicios}
    pedidos = {"total": 0, "anteriores": 0}
    entregas = {"total": 0, "anteriores": 0}

    def janela(dia: date) -> str | None:
        inicio = inicio_do_periodo(dia, "semana")
        if do_topo <= inicio <= corrente:
            return "total"
        if das_anteriores <= inicio < do_topo:
            return "anteriores"
        return None

    for demanda in demandas:
        if (dia := dia_do_pedido(demanda)) is not None:
            if (onde := janela(dia)) is not None:
                pedidos[onde] += 1
            if (semana := semanas.get(inicio_do_periodo(dia, "semana"))) is not None:
                semana["pedidos"] += 1
        if (dia := dia_da_entrega(demanda)) is not None:
            if (onde := janela(dia)) is not None:
                entregas[onde] += 1
            if (semana := semanas.get(inicio_do_periodo(dia, "semana"))) is not None:
                semana["entregas"].append(
                    {"titulo": demanda.get("titulo") or "", "tamanho": tamanho_da_entrega(demanda.get("partes_total"))}
                )
    return {"topo": {"pedidos": pedidos, "entregas": entregas}, "semanas": list(semanas.values())}
