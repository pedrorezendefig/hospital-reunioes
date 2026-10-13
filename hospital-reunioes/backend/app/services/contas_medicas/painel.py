"""O Painel de Contas médicas (issue #1137, PRD #1128, ADR 0070).

Os agregados das Contas concluídas, por semana de segunda a domingo no fuso do
hospital. A semana de uma Conta é a do dia em que ela foi concluída
(`concluida_em`). A Conta que foi concluída e enviada de novo voltou para a
fila: sai do Painel até ser concluída outra vez.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from app.services.contas_medicas.guia import linha_nao_conferida
from app.services.paginacao import ler_tudo

__all__ = ["montar_painel", "segunda_da_semana"]

FUSO_DO_HOSPITAL = ZoneInfo("America/Sao_Paulo")

# Quantas semanas as séries mostram, terminando na semana escolhida.
SEMANAS_NA_SERIE = 8

# As situações de quem foi concluída. Retorno também: foi concluída e a
# Validação devolveu uma Linha.
CONCLUIDAS = ("CONCLUIDA", "CONCLUIDA_COM_PENDENCIA", "RETORNO")

_CAMPOS_DA_CONTA = "id, atendimento_id, faturista_id, situacao, nota_entrada, concluida_em, custo_usd"
_CAMPOS_DA_LINHA = "id, conta_id, acao, codigo, descricao, valor_diferenca, preco_tabela, estado, causa_raiz, nivel_evidencia"

# Quantos ids cabem num `in_` por vez: o cliente do PostgREST põe a lista na
# querystring, e algumas centenas de UUIDs estouram o header do proxy.
LOTE_DE_IDS = 100


def segunda_da_semana(dia: date) -> date:
    return dia - timedelta(days=dia.weekday())


def _meia_noite(dia: date) -> str:
    return datetime.combine(dia, time(0), tzinfo=FUSO_DO_HOSPITAL).isoformat()


def _semana_da_conta(conta: dict) -> date:
    instante = datetime.fromisoformat(conta["concluida_em"]).astimezone(FUSO_DO_HOSPITAL)
    return segunda_da_semana(instante.date())


def _contas_concluidas(supabase, de: date, ate: date) -> list[dict]:
    """As Contas concluídas de `de` (segunda) até antes de `ate` (segunda)."""
    return ler_tudo(
        lambda: (
            supabase.table("cm_conta")
            .select(_CAMPOS_DA_CONTA)
            .in_("situacao", list(CONCLUIDAS))
            .gte("concluida_em", _meia_noite(de))
            .lt("concluida_em", _meia_noite(ate))
            .order("id")
        ),
        rotulo="contas do Painel",
    )


def _em_lotes(supabase, tabela: str, campos: str, coluna: str, ids: Iterable[str], rotulo: str) -> list[dict]:
    ids = list(dict.fromkeys(ids))
    linhas: list[dict] = []
    for i in range(0, len(ids), LOTE_DE_IDS):
        lote = ids[i : i + LOTE_DE_IDS]
        linhas += ler_tudo(
            lambda lote=lote: supabase.table(tabela).select(campos).in_(coluna, lote).order("id"), rotulo=rotulo
        )
    return linhas


def _valor(linha: dict) -> Decimal:
    return Decimal(str(linha.get("valor_diferenca") or 0))


def _dinheiro(valor: Decimal) -> float:
    return float(round(valor, 2))


def _apontada(linha: dict) -> bool:
    """A Linha que entra no R$ apontado da nota de entrada: sem Validar, sem
    Não conferido e sem Não procede (a nota é refeita sem elas na conclusão)."""
    return linha.get("acao") != "VALIDAR" and not linha_nao_conferida(linha) and linha.get("estado") != "NAO_PROCEDE"


def _incluido(linha: dict) -> Decimal:
    """O R$ incluído de uma Linha: a diferença positiva, se ela foi Feito."""
    return max(_valor(linha), Decimal(0)) if linha.get("estado") == "FEITO" else Decimal(0)


def _nao_procede(linhas: list[dict]) -> dict[str, Any]:
    """Linhas Não procede ÷ Linhas apontadas, sem Validar."""
    de = [linha for linha in linhas if linha.get("acao") != "VALIDAR"]
    nao = sum(1 for linha in de if linha.get("estado") == "NAO_PROCEDE")
    return {"linhas": nao, "de": len(de), "taxa": round(nao / len(de), 4) if de else None}


def _nota_media(contas: list[dict]) -> float | None:
    notas = [float(c["nota_entrada"]) for c in contas if c.get("nota_entrada") is not None]
    return round(sum(notas) / len(notas), 1) if notas else None


def montar_painel(supabase, *, semana: date) -> dict[str, Any]:
    segunda = segunda_da_semana(semana)
    primeira = segunda - timedelta(weeks=SEMANAS_NA_SERIE - 1)
    contas = _contas_concluidas(supabase, primeira, segunda + timedelta(weeks=1))

    por_semana: dict[date, list[dict]] = defaultdict(list)
    for conta in contas:
        por_semana[_semana_da_conta(conta)].append(conta)
    da_semana = por_semana[segunda]

    linhas_por_conta: dict[str, list[dict]] = defaultdict(list)
    for linha in _em_lotes(
        supabase, "cm_guia_linha", _CAMPOS_DA_LINHA, "conta_id", (c["id"] for c in contas), "linhas do Painel"
    ):
        linhas_por_conta[linha["conta_id"]].append(linha)
    linhas_da_semana = [linha for conta in da_semana for linha in linhas_por_conta[conta["id"]]]

    return {
        "semana": {"inicio": segunda.isoformat(), "fim": (segunda + timedelta(days=6)).isoformat()},
        "nota_media": {
            "semana": _nota_media(da_semana),
            "anterior": _nota_media(por_semana[segunda - timedelta(weeks=1)]),
        },
        "contas_concluidas": {"total": len(da_semana)},
        "valor_apontado": {
            "total": _dinheiro(sum((abs(_valor(linha)) for linha in linhas_da_semana if _apontada(linha)), Decimal(0))),
            "ja_incluido": _dinheiro(sum((_incluido(linha) for linha in linhas_da_semana), Decimal(0))),
        },
        "nao_procede": _nao_procede(linhas_da_semana),
    }
