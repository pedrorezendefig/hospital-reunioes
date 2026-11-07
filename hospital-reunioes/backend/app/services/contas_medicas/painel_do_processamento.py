"""O painel lateral do Processamento de uma conta (issue #1418, PRD #1415).

O clique no cartão do envio abre o detalhe: as cinco Etapas do processamento
com o tempo de cada uma, a tentativa e a posição na fila, para todos. Quem tem
"painel completo" vê também o modelo, as chamadas, os tokens e o custo da IA
daquela conta, somados de `cm_chamada_ia`; para quem não tem, essas chaves não
existem na resposta.

O tempo das etapas feitas vem de `tempos_por_etapa_s`: no fim da análise, em
`faltantes`; durante ela, no detalhe que o Motor grava a cada etapa que começa.
A etapa atual conta de `etapa_desde` até agora.

Quem vê cada conta segue "Meus envios": quem enviou, ou todos com "painel
completo". A conta de outra pessoa responde como a que não existe.
"""

from __future__ import annotations

from datetime import datetime

from app.services.contas_medicas.fila import quem_enviou, ve_todas
from app.services.contas_medicas.processamento import ETAPA_DA_TELA

# As cinco Etapas do processamento, na ordem da tela.
ETAPAS = tuple(dict.fromkeys(ETAPA_DA_TELA.values()))
# As situações em que nenhuma etapa começou nesta tentativa.
_ANTES_DA_ANALISE = ("NA_FILA", "AGUARDANDO_ARQUIVO", "ERRO")


class ContaNaoEncontradaError(LookupError):
    """A conta não existe, ou é de outra pessoa e quem pede não tem "painel completo"."""


def _tempos_feitos(conta: dict) -> dict[str, float]:
    """Os tempos do Motor somados nas cinco etapas da tela; o `total` fica de fora."""
    if conta.get("situacao") == "PROCESSANDO":
        # Até a primeira etapa desta tentativa, o detalhe ainda é o da anterior.
        origem = conta.get("erro_detalhe") if conta.get("etapa_atual") else None
    else:
        origem = conta.get("faltantes")
    internos = (origem or {}).get("tempos_por_etapa_s") or {}
    somados: dict[str, float] = {}
    for interna, segundos in internos.items():
        if interna in ETAPA_DA_TELA:
            tela = ETAPA_DA_TELA[interna]
            somados[tela] = round(somados.get(tela, 0) + float(segundos or 0), 3)
    return somados


def _etapa(etapa: str, estado: str, tempo_s: float | None) -> dict:
    return {"etapa": etapa, "estado": estado, "tempo_s": tempo_s}


def _etapas(conta: dict, agora: datetime) -> list[dict]:
    situacao = conta.get("situacao")
    if situacao in _ANTES_DA_ANALISE:
        return [_etapa(etapa, "falta", None) for etapa in ETAPAS]
    tempos = _tempos_feitos(conta)
    if situacao != "PROCESSANDO":
        return [_etapa(etapa, "feita", tempos.get(etapa)) for etapa in ETAPAS]
    atual = conta.get("etapa_atual")
    indice = ETAPAS.index(atual) if atual in ETAPAS else -1
    desde = conta.get("etapa_desde")
    etapas = []
    for i, etapa in enumerate(ETAPAS):
        if i < indice:
            etapas.append(_etapa(etapa, "feita", tempos.get(etapa)))
        elif i == indice:
            decorrido = round((agora - datetime.fromisoformat(desde)).total_seconds(), 3) if desde else None
            etapas.append(_etapa(etapa, "atual", decorrido))
        else:
            etapas.append(_etapa(etapa, "falta", None))
    return etapas


def _posicao_na_fila(supabase, conta: dict) -> int | None:
    """A vez da conta Na fila, na ordem de envio, contando de 1."""
    if conta.get("situacao") != "NA_FILA":
        return None
    antes = (
        supabase.table("cm_conta")
        .select("id")
        .eq("situacao", "NA_FILA")
        .lt("ordem_fila", conta.get("ordem_fila"))
        .execute()
        .data
        or []
    )
    return len(antes) + 1


def _custo(supabase, conta_id: str) -> dict:
    """O que a IA custou para a conta, somado de todas as chamadas dela."""
    chamadas = (
        supabase.table("cm_chamada_ia")
        .select("modelo, tokens_entrada, tokens_saida, tokens_cache, custo_usd")
        .eq("conta_id", conta_id)
        .order("criado_em")
        .execute()
        .data
        or []
    )
    return {
        "modelo": ", ".join(dict.fromkeys(c["modelo"] for c in chamadas if c.get("modelo"))) or None,
        "chamadas": len(chamadas),
        "tokens_entrada": sum(int(c.get("tokens_entrada") or 0) for c in chamadas),
        "tokens_saida": sum(int(c.get("tokens_saida") or 0) for c in chamadas),
        "tokens_cache": sum(int(c.get("tokens_cache") or 0) for c in chamadas),
        "custo_usd": round(sum(float(c.get("custo_usd") or 0) for c in chamadas), 4),
    }


def detalhe(supabase, conta_id: str, me: dict, agora: datetime) -> dict:
    """O painel lateral da conta. Levanta `ContaNaoEncontradaError` quando a
    conta não existe ou não é da pessoa e ela não tem "painel completo"."""
    contas = supabase.table("cm_conta").select("*").eq("id", conta_id).limit(1).execute().data or []
    if not contas:
        raise ContaNaoEncontradaError(conta_id)
    conta = contas[0]
    gestao = ve_todas(me)
    if not gestao and quem_enviou(supabase, conta) != me.get("id"):
        raise ContaNaoEncontradaError(conta_id)
    processando = conta.get("situacao") == "PROCESSANDO"
    resposta = {
        "id": conta["id"],
        "situacao": conta.get("situacao"),
        "etapas": _etapas(conta, agora),
        "parte": conta.get("etapa_parte") if processando else None,
        "partes": conta.get("etapa_partes") if processando else None,
        "tentativa": conta.get("tentativas") or None,
        "posicao_na_fila": _posicao_na_fila(supabase, conta),
    }
    if gestao:
        resposta |= _custo(supabase, conta["id"])
    return resposta
