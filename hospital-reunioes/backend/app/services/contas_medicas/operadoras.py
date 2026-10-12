"""Carga da operadora (issue #1119, PRD #1113, ADR 0070): memória, planos e setores.

A memória entra por arquivo (`memoria.ler_memoria`) e vira uma versão nova em
`cm_memoria_versao`, com as regras em `cm_regra`. Só uma versão é vigente por
operadora; `memoria_vigente` é o que as conferências leem.

A ordem da gravação protege a versão em uso: a nova nasce não vigente, recebe
as regras e só então troca de lugar com a anterior. Uma falha no meio deixa
uma versão órfã fora de uso, nunca uma operadora com metade das regras.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from app.services.contas_medicas.memoria import MemoriaLida, parametros_lidos
from app.services.contas_medicas_conta import chave_do_plano

__all__ = ["importar_memoria", "memoria_vigente", "reconhecer_plano"]


def _operadora(supabase, memoria: MemoriaLida) -> dict:
    existentes = supabase.table("cm_operadora").select("*").eq("sigla", memoria.sigla).execute().data or []
    if existentes:
        return existentes[0]
    return (
        supabase.table("cm_operadora")
        .insert({"sigla": memoria.sigla, "nome": memoria.nome, "situacao": "SEM_MEMORIA"})
        .execute()
        .data[0]
    )


def importar_memoria(supabase, memoria: MemoriaLida, texto_md: str, autor_id: str | None) -> dict:
    """Grava a memória lida como a versão vigente da operadora e devolve o resumo."""
    operadora = _operadora(supabase, memoria)
    vigentes = sum(1 for r in memoria.regras if r.status == "VIGENTE")
    contagem = {"total": len(memoria.regras), "vigentes": vigentes, "pendentes": len(memoria.regras) - vigentes}

    versao = (
        supabase.table("cm_memoria_versao")
        .insert(
            {
                "operadora_id": operadora["id"],
                "versao": memoria.versao,
                "parametros_json": memoria.parametros,
                "texto_md": texto_md,
                "vigente": False,
                "autor_id": autor_id,
                "resumo": f"{contagem['total']} regras: {vigentes} vigentes e {contagem['pendentes']} pendentes",
            }
        )
        .execute()
        .data[0]
    )
    if memoria.regras:
        supabase.table("cm_regra").insert(
            [
                {
                    "operadora_id": operadora["id"],
                    "memoria_versao_id": versao["id"],
                    "codigo": r.codigo,
                    "secao": r.secao,
                    "texto": r.texto,
                    "tipo": r.tipo,
                    "origem": r.origem,
                    "status": r.status,
                    "validado_em": r.validado_em,
                }
                for r in memoria.regras
            ]
        ).execute()

    supabase.table("cm_memoria_versao").update({"vigente": False}).eq("operadora_id", operadora["id"]).eq(
        "vigente", True
    ).execute()
    supabase.table("cm_memoria_versao").update({"vigente": True}).eq("id", versao["id"]).execute()
    supabase.table("cm_operadora").update({"nome": memoria.nome, "situacao": memoria.situacao}).eq(
        "id", operadora["id"]
    ).execute()

    return {
        "operadora": memoria.sigla,
        "nome": memoria.nome,
        "situacao": memoria.situacao,
        "versao": memoria.versao,
        "regras": contagem,
        "parametros": parametros_lidos(memoria.parametros),
    }


def memoria_vigente(supabase, operadora_id: str) -> dict | None:
    """A versão vigente da memória da operadora: parâmetros lidos e regras ativas.

    Sem memória carregada, `None`: a operadora está SEM_MEMORIA.
    """
    versoes = (
        supabase.table("cm_memoria_versao")
        .select("id, versao, parametros_json")
        .eq("operadora_id", operadora_id)
        .eq("vigente", True)
        .execute()
        .data
        or []
    )
    if not versoes:
        return None
    versao = versoes[0]
    regras = (
        supabase.table("cm_regra")
        .select("codigo, secao, texto, tipo, origem, status")
        .eq("memoria_versao_id", versao["id"])
        .eq("ativa", True)
        .order("codigo")
        .execute()
        .data
        or []
    )
    return {
        "memoria_versao_id": versao["id"],
        "versao": versao["versao"],
        "parametros": parametros_lidos(versao.get("parametros_json") or {}),
        "regras": regras,
    }


def reconhecer_plano(nome_na_conta: str, planos: Iterable[dict[str, Any]]) -> dict[str, Any] | None:
    """O plano cadastrado que corresponde ao nome impresso na conta, ou `None`.

    Mesma comparação da coluna de preço: sem acento, sem diferença de maiúscula
    e ignorando o sufixo de acomodação (ENF, APT).
    """
    chave = chave_do_plano(nome_na_conta)
    return next((p for p in planos if chave_do_plano(p["nome_mv"]) == chave), None)
