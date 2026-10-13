"""O Passo C de Contas médicas: os lembretes da coordenação (issue #1143, PRD #1129, adendo v1.1).

Depois do Passo A, uma chamada curta: a IA recebe os eventos do atendimento no
período da conta e os cenários ativos da operadora (os dela e os que valem
para todas) e diz, para cada cenário que ocorreu, a data, o setor, a página e
o trecho. O resto é do código:

1. o cenário citado existe entre os enviados, e a data cai no período da conta;
2. o trecho está na página citada ou na vizinha; senão o lembrete sai com a
   etiqueta "conferir evidência";
3. para cada insumo do cenário, o código já está na conta (a parcial é o
   período): tudo lançado, nada acontece; falta algum, o lembrete leva os que
   faltam, com o valor pela tabela da operadora.

Cenário e lembrete nunca entram no Passo B, no Guia, na nota nem na produção
da faturista: a conta segue para ela como se o Passo C não existisse, inclusive
quando ele falha.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.services.contas_medicas import ia
from app.services.contas_medicas.conferencia import BuscaDePreco, ProntuarioLido
from app.services.contas_medicas.coordenacao import CONFERIR_EVIDENCIA, itens_dos_cenarios
from app.services.contas_medicas.evidencia import trecho_confere
from app.services.contas_medicas.passo_a import _identificacao, _ler_quando, _texto_da_pagina
from app.services.contas_medicas.passo_b import _preco_da_tabela, eventos_do_periodo
from app.services.contas_medicas_conta import Conta
from app.services.prompt_loader import load_prompt
from app.utils.text_sanitizer import sanitizar_estrutura

__all__ = ["OcorrenciasDosCenarios", "lembrar_a_coordenacao"]

CENTAVO = Decimal("0.01")


class _Estrito(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Ocorrencia(_Estrito):
    cenario_id: str
    data: str | None
    setor: str | None
    evidencia: ia.Evidencia


class OcorrenciasDosCenarios(_Estrito):
    """A saída do Passo C (adendo v1.1, item 3.3)."""

    ocorrencias: list[Ocorrencia]


def _cenarios_ativos(supabase, operadora_id: str | None) -> list[dict[str, Any]]:
    """Os cenários ativos da operadora e os que valem para todas. São poucos:
    o recorte pela operadora é aqui, sem `or` na consulta."""
    ativos = supabase.table("cm_cenario").select("*").eq("ativo", True).order("codigo").execute().data or []
    return [c for c in ativos if c.get("operadora_id") in (None, operadora_id)]


def _texto_dos_cenarios(cenarios: Sequence[Mapping[str, Any]]) -> str:
    return "\n".join(f"{c['codigo']}: {c['nome']}. Quando dispara: {c['gatilho_texto']}" for c in cenarios)


def _no_periodo(conta: Conta, dia: date) -> bool:
    inicio, fim = conta.periodo_inicio, conta.periodo_fim
    return (inicio is None or inicio <= dia) and (fim is None or dia <= fim)


def _numero(valor: Decimal | None) -> float | None:
    return float(valor) if valor is not None else None


def _insumo_do_lembrete(item: Mapping[str, Any], preco: BuscaDePreco, dia: date, coluna: str | None) -> dict[str, Any]:
    codigo = item["codigo"].strip()
    quantidade = Decimal(str(item.get("quantidade") or 1))
    tabela = _preco_da_tabela(preco, codigo, dia, coluna)
    valor = (tabela * quantidade).quantize(CENTAVO, rounding=ROUND_HALF_UP) if tabela is not None else None
    return {
        "codigo": codigo,
        "descricao": item.get("descricao"),
        "quantidade": float(quantidade),
        "preco_tabela": _numero(tabela),
        "valor": _numero(valor),
    }


def lembrar_a_coordenacao(
    supabase,
    *,
    conta_id: str,
    atendimento_id: str,
    operadora_id: str | None,
    conta: Conta,
    prontuario: ProntuarioLido,
    eventos: Mapping[str, Any],
    preco: BuscaDePreco,
    coluna: str | None,
) -> int:
    """Os lembretes da conta, e quantos foram criados. O reprocesso troca os
    abertos e preserva os que a coordenadora já marcou: a mesma ocorrência
    (cenário e dia) marcada não volta."""
    existentes = supabase.table("cm_lembrete").select("*").eq("conta_id", conta_id).execute().data or []
    marcados = {(m["cenario_id"], m.get("data")) for m in existentes if m.get("estado") != "ABERTO"}
    supabase.table("cm_lembrete").delete().eq("conta_id", conta_id).eq("estado", "ABERTO").execute()

    cenarios = _cenarios_ativos(supabase, operadora_id)
    if not cenarios:
        return 0
    do_periodo = eventos_do_periodo(eventos, conta.periodo_inicio, conta.periodo_fim)
    resposta = ia.chamada_curta(
        load_prompt("contas_medicas_passo_c"),
        f"EVENTOS\n{json.dumps(do_periodo, ensure_ascii=False, default=str)}\n\n"
        f"CENÁRIOS\n{_texto_dos_cenarios(cenarios)}",
        OcorrenciasDosCenarios,
        # O CHECK da migration 117 não tem passo próprio: vai como chamada curta.
        passo="OBSERVACAO",
        supabase=supabase,
        conta_id=conta_id,
        atendimento_id=atendimento_id,
    )

    por_codigo = {c["codigo"].strip().upper(): c for c in cenarios}
    insumos = itens_dos_cenarios(supabase, [c["id"] for c in cenarios])
    lancados = {item.codigo.strip() for item in conta.itens}
    texto_da_pagina = _texto_da_pagina(prontuario, _identificacao(prontuario))
    vistos = set(marcados)
    criados = 0
    for ocorrencia in sanitizar_estrutura(resposta.model_dump())["ocorrencias"]:
        cenario = por_codigo.get(ocorrencia["cenario_id"].strip().upper())
        quando = _ler_quando(ocorrencia.get("data"))
        dia = quando[0] if quando else None
        if cenario is None or (dia is not None and not _no_periodo(conta, dia)):
            continue
        chave = (cenario["id"], dia.isoformat() if dia else None)
        faltam = [i for i in insumos[cenario["id"]] if i["codigo"].strip() not in lancados]
        if chave in vistos or not faltam:
            continue
        vistos.add(chave)
        evidencia = ocorrencia["evidencia"]
        confere = trecho_confere(evidencia.get("trecho"), evidencia.get("pagina"), texto_da_pagina)
        (lembrete,) = (
            supabase.table("cm_lembrete")
            .insert(
                {
                    "conta_id": conta_id,
                    "cenario_id": cenario["id"],
                    "data": chave[1],
                    "setor": ocorrencia.get("setor"),
                    "evidencia_pagina": evidencia.get("pagina"),
                    "evidencia_trecho": (evidencia.get("trecho") or "")[:300] or None,
                    "estado": "ABERTO",
                    "observacao": None if confere else CONFERIR_EVIDENCIA,
                }
            )
            .execute()
            .data
        )
        dia_do_preco = dia or conta.periodo_inicio or date.today()
        supabase.table("cm_lembrete_item").insert(
            [{"lembrete_id": lembrete["id"], **_insumo_do_lembrete(i, preco, dia_do_preco, coluna)} for i in faltam]
        ).execute()
        criados += 1
    return criados
