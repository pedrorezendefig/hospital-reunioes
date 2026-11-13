"""As Entregas da Tecnologia (issue #1556, PRD #1548; ritmo semanal na issue
#1701, PRD #1689, ADR 0092).

Regras puras, sem I/O: o router le as Demandas e passa por aqui. Conta por
card, nunca por parte. Entregue e a Demanda com a data de entrega que o
Documento do card mostra (`entregue_na_data`: o fechamento da issue-raiz, so
com a Etapa Entregue ou Em producao); Nao sera feita fica de fora. O dia e o
do hospital, em Sao Paulo: o card fechado as 22h de domingo e do domingo, e
nao da segunda em UTC.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

from app.services.chat_tecnologia import CLASSIFICACAO_DO_TIPO
from app.services.tecnologia import (
    ORIGEM_DIRETOR,
    entregue_na_data,
    instante_do_banco,
    login_do_responsavel,
    origem_da_demanda,
    responsavel_da_demanda,
)

FUSO_DO_HOSPITAL = ZoneInfo("America/Sao_Paulo")

# O grafico mostra 12 semanas; o topo, as 4 ultimas (a corrente entra) contra
# as 4 de antes (ADR 0092, decisao 1).
SEMANAS_DO_GRAFICO = 12
SEMANAS_DO_TOPO = 4

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


def chave_do_responsavel(demanda: dict[str, Any]) -> str | None:
    """O valor do filtro Responsavel: o id do usuario, ou o login do dono no
    GitHub quando ele nao e usuario do app (issue #1534)."""
    return responsavel_da_demanda(demanda) or login_do_responsavel(demanda)


def inicio_da_semana(dia: date) -> date:
    """A segunda-feira da semana do dia."""
    return dia - timedelta(days=dia.weekday())


def _instante(par: tuple[datetime, dict[str, str]]) -> datetime:
    return par[0]


@dataclass(frozen=True)
class Filtros:
    """Tipo, Origem e Responsavel da aba (ADR 0092, decisao 7). Combinam entre
    si e valem para o topo, as semanas e a lista. O Responsavel e a
    `chave_do_responsavel`."""

    tipo: Literal["bug", "melhoria"] | None = None
    origem: Literal["diretor", "vitta"] | None = None
    responsavel: str | None = None

    def deixa(self, demanda: dict[str, Any]) -> bool:
        return (
            (self.tipo is None or CLASSIFICACAO_DO_TIPO.get(str(demanda.get("tipo") or "")) == self.tipo)
            and (self.origem is None or origem_da_demanda(demanda) == self.origem)
            and (self.responsavel is None or chave_do_responsavel(demanda) == self.responsavel)
        )


def ritmo(demandas: list[dict[str, Any]], *, agora: datetime, filtros: Filtros | None = None) -> dict[str, Any]:
    """O ritmo da aba Entregas (ADR 0092, decisao 1): o topo e as 12 semanas.

    `demandas` sao as que quem pede ve; os `filtros` cortam por cima. O topo
    conta pedidos e entregas das ultimas 4 semanas, contando a corrente, e das
    4 anteriores, com a composicao so das 4 do topo: bugs e melhorias nos
    pedidos, G, M e P nas entregas. As semanas vem da mais antiga para a
    corrente, comecando na segunda pelo fuso do hospital, cada uma com os
    pedidos, as entregas por tamanho e o que saiu nela (titulo e tamanho, o
    mais novo primeiro). Nada aqui leva numero de issue.
    """
    filtros = filtros or Filtros()
    corrente = inicio_da_semana(agora.astimezone(FUSO_DO_HOSPITAL).date())
    do_topo = corrente - timedelta(weeks=SEMANAS_DO_TOPO - 1)
    das_anteriores = do_topo - timedelta(weeks=SEMANAS_DO_TOPO)
    inicios = [corrente - timedelta(weeks=atras) for atras in range(SEMANAS_DO_GRAFICO - 1, -1, -1)]
    semanas = {inicio: {"inicio": inicio.isoformat(), "pedidos": 0, "g": 0, "m": 0, "p": 0} for inicio in inicios}
    saidas: dict[date, list[tuple[datetime, dict[str, str]]]] = {inicio: [] for inicio in inicios}
    pedidos = {"total": 0, "anteriores": 0, "bugs": 0, "melhorias": 0}
    entregas = {"total": 0, "anteriores": 0, "g": 0, "m": 0, "p": 0}

    def janela(inicio: date) -> str | None:
        if do_topo <= inicio <= corrente:
            return "total"
        if das_anteriores <= inicio < do_topo:
            return "anteriores"
        return None

    for demanda in demandas:
        if not filtros.deixa(demanda):
            continue
        if (dia := dia_do_pedido(demanda)) is not None:
            inicio = inicio_da_semana(dia)
            if (onde := janela(inicio)) is not None:
                pedidos[onde] += 1
                classificacao = CLASSIFICACAO_DO_TIPO.get(str(demanda.get("tipo") or ""))
                if onde == "total" and classificacao:
                    pedidos["bugs" if classificacao == "bug" else "melhorias"] += 1
            if inicio in semanas:
                semanas[inicio]["pedidos"] += 1
        entregue = instante_do_banco(entregue_na_data(demanda))
        if entregue is not None:
            inicio = inicio_da_semana(entregue.astimezone(FUSO_DO_HOSPITAL).date())
            tamanho = tamanho_da_entrega(demanda.get("partes_total"))
            if (onde := janela(inicio)) is not None:
                entregas[onde] += 1
                if onde == "total":
                    entregas[tamanho.lower()] += 1
            if inicio in semanas:
                semanas[inicio][tamanho.lower()] += 1
                saidas[inicio].append((entregue, {"titulo": str(demanda.get("titulo") or ""), "tamanho": tamanho}))
    return {
        "topo": {"pedidos": pedidos, "entregas": entregas},
        "semanas": [
            {**semanas[inicio], "entregas": [e for _, e in sorted(saidas[inicio], key=_instante, reverse=True)]}
            for inicio in inicios
        ],
    }
