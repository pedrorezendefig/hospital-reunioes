"""O segundo agente (issue #1493, PRD #1484, ADR 0081, decisão 14).

Uma vez por semana, sorteia até 10 Contas concluídas que ainda não revisou e
relê cada uma a partir do que a análise guardou (os eventos que a leitura do
prontuário achou, os documentos, as páginas sem texto, o Guia e os itens da
conta), procurando o que o prontuário registra como administrado e não foi
cobrado. Cada achado vira um Faltou isto de origem AGENTE, já classificado e
explicado como o Auditor faz com o da pessoa.

A Conta revisada é a que tem chamada REVISOR com sucesso em `cm_chamada_ia`:
é ela que tira a Conta do sorteio das semanas seguintes, e a falha da IA
deixa a Conta no sorteio da próxima semana. Nenhuma Conta, Linha do Guia ou
Memória muda aqui.
"""

from __future__ import annotations

import json
import logging
import random
from collections.abc import Callable
from datetime import date
from typing import Any

from app.services.contas_medicas import ia
from app.services.contas_medicas.faltou_isto import (
    _CAMPOS_DA_LINHA,
    _CAMPOS_DO_ITEM,
    _LISTAS_DO_DIA,
    _agora,
    _eventos_guardados,
    _juntar,
    fora_do_periodo,
)
from app.services.contas_medicas.memoria_texto import gerar_texto_memoria
from app.services.contas_medicas.prova_da_regra import CONCLUIDAS
from app.services.paginacao import ler_tudo
from app.utils.text_sanitizer import sanitizar_travessao

__all__ = ["CONTAS_POR_SEMANA", "revisar_semana"]

logger = logging.getLogger(__name__)

CONTAS_POR_SEMANA = 10

Sorteio = Callable[[list[dict[str, Any]], int], list[dict[str, Any]]]


def _ja_revisadas(supabase) -> set[str]:
    chamadas = ler_tudo(
        lambda: (
            supabase.table("cm_chamada_ia")
            .select("id, conta_id")
            .eq("passo", "REVISOR")
            .eq("sucesso", True)
            .order("id")
        ),
        rotulo="contas revisadas pelo segundo agente",
    )
    return {c["conta_id"] for c in chamadas if c.get("conta_id")}


def _a_revisar(supabase) -> list[dict[str, Any]]:
    """As Contas concluídas que o segundo agente ainda não revisou."""
    revisadas = _ja_revisadas(supabase)
    concluidas = ler_tudo(
        lambda: (
            supabase.table("cm_conta")
            .select("id, atendimento_id, periodo_inicio, periodo_fim, memoria_versao_id")
            .in_("situacao", list(CONCLUIDAS))
            .order("id")
        ),
        rotulo="contas concluídas para o segundo agente",
    )
    return [c for c in concluidas if c["id"] not in revisadas]


def _a_conta_para_a_ia(supabase, conta: dict[str, Any]) -> dict[str, Any]:
    """O que o segundo agente lê da Conta: o mesmo recorte do Faltou isto, com
    a Conta inteira no lugar do dia. Sem o número do atendimento e a idade, que
    a leitura também devolve, e sem preço."""
    eventos = _eventos_guardados(supabase, conta["atendimento_id"])
    da_ia = eventos.get("ia") or {}
    linhas = supabase.table("cm_guia_linha").select("*").eq("conta_id", conta["id"]).execute().data or []
    itens = supabase.table("cm_conta_item").select("*").eq("conta_id", conta["id"]).execute().data or []
    return {
        "periodo": {"inicio": conta.get("periodo_inicio"), "fim": conta.get("periodo_fim")},
        "paginas_do_prontuario": eventos.get("total_paginas"),
        "paginas_sem_texto": eventos.get("paginas_sem_texto") or [],
        "documentos": eventos.get("documentos") or [],
        "eventos": {lista: da_ia.get(lista) or [] for lista in _LISTAS_DO_DIA},
        "linhas_do_guia": [
            {"data": linha.get("data"), "data_fim": linha.get("data_fim"), **{c: linha.get(c) for c in _CAMPOS_DA_LINHA}}
            for linha in linhas
        ],
        "itens_da_conta": [{"data": item.get("data"), **{c: item.get(c) for c in _CAMPOS_DO_ITEM}} for item in itens],
    }


def _o_faltou_isto(conta: dict[str, Any], achado: ia.AchadoDoRevisor) -> dict[str, Any] | None:
    """O achado como Faltou isto do agente; None quando o dia não é da Conta ou
    o item veio vazio."""
    item = sanitizar_travessao(achado.item).strip()
    try:
        dia = date.fromisoformat(achado.data)
    except ValueError:
        return None
    if not item or fora_do_periodo(conta, dia):
        return None
    return {
        "conta_id": conta["id"],
        "data": dia.isoformat(),
        "item": item,
        "pagina": achado.pagina if achado.pagina >= 1 else None,
        "origem": "AGENTE",
        "classificacao": achado.classificacao,
        "explicacao": _juntar(achado.explicacao, achado.esperado),
        "classificado_em": _agora(),
    }


def _revisar(supabase, conta: dict[str, Any]) -> int:
    atendimento = (
        supabase.table("cm_atendimento").select("id, operadora_id").eq("id", conta["atendimento_id"]).execute().data
        or [{}]
    )[0]
    memoria = gerar_texto_memoria(supabase, atendimento.get("operadora_id"), conta.get("memoria_versao_id"))
    revisao = ia.revisar_conta(
        memoria,
        json.dumps(_a_conta_para_a_ia(supabase, conta), ensure_ascii=False, default=str),
        supabase=supabase,
        conta_id=conta["id"],
        atendimento_id=conta.get("atendimento_id"),
    )
    achados = [f for f in (_o_faltou_isto(conta, a) for a in revisao.achados) if f]
    if achados:
        supabase.table("cm_faltou_isto").insert(achados).execute()
    return len(achados)


def revisar_semana(supabase, sortear: Sorteio = random.sample) -> int:
    """A rodada da semana: até `CONTAS_POR_SEMANA` Contas concluídas ainda não
    revisadas, sorteadas. Devolve quantos Faltou isto o agente gravou.

    A falha numa Conta não para as outras; a IA sem crédito para a rodada. O
    log leva só o tipo do erro: a mensagem pode citar o prontuário."""
    candidatas = _a_revisar(supabase)
    achados = 0
    for conta in sortear(candidatas, min(CONTAS_POR_SEMANA, len(candidatas))):
        try:
            achados += _revisar(supabase, conta)
        except ia.IASemCredito:
            logger.error("[ContasMedicas] Segundo agente parado: a IA está sem crédito")
            break
        except Exception as erro:
            logger.error("[ContasMedicas] Segundo agente na conta %s: %s", conta["id"], type(erro).__name__)
    return achados
