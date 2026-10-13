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
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from zoneinfo import ZoneInfo

from app.dependencies import selecionar_participantes
from app.services.contas_medicas.guia import linha_nao_conferida
from app.services.paginacao import ler_tudo

__all__ = ["montar_painel", "segunda_da_semana"]

FUSO_DO_HOSPITAL = ZoneInfo("America/Sao_Paulo")

# Quantas semanas as séries mostram, terminando na semana escolhida.
SEMANAS_NA_SERIE = 8

# As situações de quem foi concluída. Retorno também: foi concluída e a
# Validação devolveu uma Linha.
CONCLUIDAS = ("CONCLUIDA", "CONCLUIDA_COM_PENDENCIA", "RETORNO")

# A ordem da spec do diretor (item 15.2).
CAUSAS = ("DISPENSACAO", "REGRA_AUTOMATICA", "CADASTRO_PRECO", "REGISTRO_ASSISTENCIAL", "LANCAMENTO_MANUAL")

# Os níveis de evidência, na ordem do adendo v1.1 (item 4).
NIVEIS = ("REGISTRADO", "PRESCRITO", "PRESCRITO_SN", "POR_REGRA")

# Quantos itens a fila de parametrização para a consultoria do MV mostra.
ITENS_QUE_FALTAM = 10

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


def _filtrar(supabase, contas: list[dict], operadora_id: str | None, tipo: str | None) -> list[dict]:
    """Recorta as Contas pela operadora do atendimento e pelo tipo de conta:
    Parcial quando o atendimento tem mais de uma conta, Única quando tem uma."""
    if operadora_id:
        atendimentos = _em_lotes(
            supabase, "cm_atendimento", "id, operadora_id", "id", (c["atendimento_id"] for c in contas), "atendimentos"
        )
        da_operadora = {a["id"] for a in atendimentos if a.get("operadora_id") == operadora_id}
        contas = [c for c in contas if c["atendimento_id"] in da_operadora]
    if tipo:
        irmas = _em_lotes(
            supabase, "cm_conta", "id, atendimento_id", "atendimento_id", (c["atendimento_id"] for c in contas), "parciais"
        )
        quantas: dict[str, int] = defaultdict(int)
        for conta in irmas:
            quantas[conta["atendimento_id"]] += 1
        contas = [c for c in contas if (quantas[c["atendimento_id"]] > 1) == (tipo == "parcial")]
    return contas


def _operadoras(supabase) -> list[dict[str, Any]]:
    return supabase.table("cm_operadora").select("id, sigla, nome").order("sigla").execute().data or []


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


def _percentual(parte: Decimal, total: Decimal) -> float:
    if not total:
        return 0.0
    return float((parte * 100 / total).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def _por_causa_raiz(linhas: list[dict]) -> list[dict[str, Any]]:
    """O R$ apontado de cada causa-raiz, com o percentual do total."""
    soma = dict.fromkeys(CAUSAS, Decimal(0))
    for linha in linhas:
        if _apontada(linha) and linha.get("causa_raiz") in soma:
            soma[linha["causa_raiz"]] += abs(_valor(linha))
    total = sum(soma.values(), Decimal(0))
    return [{"causa": c, "valor": _dinheiro(v), "percentual": _percentual(v, total)} for c, v in soma.items()]


def _itens_que_faltam(linhas: list[dict]) -> list[dict[str, Any]]:
    """Os códigos com mais Contas com Linha Incluir. A Linha Não procede sai:
    o item não faltava."""
    por_codigo: dict[str, dict[str, Any]] = {}
    for linha in linhas:
        if linha.get("acao") != "INCLUIR" or linha.get("estado") == "NAO_PROCEDE" or not linha.get("codigo"):
            continue
        item = por_codigo.setdefault(
            linha["codigo"], {"descricao": linha.get("descricao"), "contas": set(), "valor": Decimal(0)}
        )
        item["contas"].add(linha["conta_id"])
        item["valor"] += _valor(linha)
    ordem = sorted(por_codigo.items(), key=lambda par: (-len(par[1]["contas"]), -par[1]["valor"], par[0]))
    return [
        {"codigo": codigo, "descricao": item["descricao"], "contas": len(item["contas"]), "valor": _dinheiro(item["valor"])}
        for codigo, item in ordem[:ITENS_QUE_FALTAM]
    ]


def _producao(supabase, contas: list[dict], linhas_por_conta: dict[str, list[dict]]) -> list[dict[str, Any]]:
    """Uma linha por faturista: Contas concluídas, com pendência, R$ incluído,
    R$ retirado (glosa evitada) e a taxa de Não procede."""
    por_faturista: dict[str | None, list[dict]] = defaultdict(list)
    for conta in contas:
        por_faturista[conta.get("faturista_id")].append(conta)
    ids = [fid for fid in por_faturista if fid]
    nomes = {}
    if ids:
        pessoas = selecionar_participantes(supabase, "id, nome_completo", lambda q: q.in_("id", ids)).data or []
        nomes = {p["id"]: p.get("nome_completo") for p in pessoas}

    producao = []
    for fid, delas in por_faturista.items():
        linhas = [linha for conta in delas for linha in linhas_por_conta[conta["id"]]]
        feitas = [linha for linha in linhas if linha.get("estado") == "FEITO"]
        producao.append(
            {
                "faturista_id": fid,
                "nome": nomes.get(fid),
                "contas": len(delas),
                "com_pendencia": sum(1 for c in delas if c.get("situacao") == "CONCLUIDA_COM_PENDENCIA"),
                "valor_incluido": _dinheiro(sum((_incluido(linha) for linha in feitas), Decimal(0))),
                "valor_retirado": _dinheiro(sum((-min(_valor(linha), Decimal(0)) for linha in feitas), Decimal(0))),
                "taxa_nao_procede": _nao_procede(linhas)["taxa"],
            }
        )
    return sorted(producao, key=lambda linha: (linha["nome"] is None, linha["nome"] or ""))


def _incluido_por_nivel(linhas: list[dict]) -> dict[str, float]:
    soma = dict.fromkeys(NIVEIS, Decimal(0))
    for linha in linhas:
        if linha.get("nivel_evidencia") in soma:
            soma[linha["nivel_evidencia"]] += _incluido(linha)
    return {nivel: _dinheiro(valor) for nivel, valor in soma.items()}


def _custo_ia(contas: list[dict]) -> dict[str, Any]:
    """A soma do custo de IA das Contas (o de todas as chamadas de cada uma,
    inclusive as de uma nova análise) e a média por Conta."""
    total = sum((Decimal(str(c.get("custo_usd") or 0)) for c in contas), Decimal(0))
    medio = total / len(contas) if contas else Decimal(0)
    return {"total_usd": float(round(total, 4)), "medio_por_conta_usd": float(round(medio, 4)), "contas": len(contas)}


def _nota_media(contas: list[dict]) -> float | None:
    notas = [float(c["nota_entrada"]) for c in contas if c.get("nota_entrada") is not None]
    return round(sum(notas) / len(notas), 1) if notas else None


def montar_painel(
    supabase, *, semana: date, operadora_id: str | None = None, tipo: str | None = None
) -> dict[str, Any]:
    segunda = segunda_da_semana(semana)
    primeira = segunda - timedelta(weeks=SEMANAS_NA_SERIE - 1)
    contas = _filtrar(supabase, _contas_concluidas(supabase, primeira, segunda + timedelta(weeks=1)), operadora_id, tipo)

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
    semanas = [primeira + timedelta(weeks=i) for i in range(SEMANAS_NA_SERIE)]

    return {
        "semana": {"inicio": segunda.isoformat(), "fim": (segunda + timedelta(days=6)).isoformat()},
        "filtros": {"operadoras": _operadoras(supabase)},
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
        "nota_por_semana": [
            {"semana": s.isoformat(), "nota_media": _nota_media(por_semana[s]), "contas": len(por_semana[s])}
            for s in semanas
        ],
        "causa_raiz": _por_causa_raiz(linhas_da_semana),
        "itens_que_faltam": _itens_que_faltam(linhas_da_semana),
        "producao": _producao(supabase, da_semana, linhas_por_conta),
        "nivel_evidencia": [
            {"semana": s.isoformat(), **_incluido_por_nivel([l for c in por_semana[s] for l in linhas_por_conta[c["id"]]])}
            for s in semanas
        ],
        "custo_ia": _custo_ia(da_semana),
    }
