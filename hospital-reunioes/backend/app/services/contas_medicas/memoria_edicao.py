"""A Memória da operadora por tela (issue #1140, PRD #1129, ADR 0070).

Editar uma regra vigente ou decidir uma pendente não mexe na versão em uso:
cria uma versão nova de `cm_memoria_versao` com todas as regras da vigente
copiadas, a mudada já com o texto novo, e guarda o texto anterior em
`cm_regra_historico`. A conta analisada antes continua apontando para a versão
antiga, que fica como estava.

A ordem da gravação é a da importação (`operadoras.importar_memoria`): a nova
nasce não vigente, recebe as regras e o texto gerado do banco, e só então
troca de lugar com a anterior. Uma falha no meio deixa uma versão órfã fora
de uso, nunca uma operadora com metade das regras.

Quem pode mudar depende do tipo da regra: operacional pede "incluir regra
operacional"; contratual (e a regra sem tipo, que é de preço, diária ou
tabela) pede "regra contratual e tabelas". Trocar o tipo pede as duas.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.services.contas_medicas.memoria import _CPF
from app.services.contas_medicas.memoria_texto import gerar_texto_memoria

__all__ = [
    "MudancaRecusadaError",
    "RegraNaoEncontradaError",
    "SemPermissaoNaRegraError",
    "mudar_regra",
    "permissao_do_tipo",
]


class RegraNaoEncontradaError(LookupError):
    """A operadora, a memória vigente ou a regra não existem."""


class MudancaRecusadaError(ValueError):
    """A mudança não cabe na regra como ela está; a mensagem é para quem pediu."""


class SemPermissaoNaRegraError(PermissionError):
    """A pessoa não tem a permissão que o tipo da regra pede."""


def permissao_do_tipo(tipo: str | None) -> str:
    """A permissão de Contas médicas que mudar uma regra deste tipo pede."""
    return "incluir_regra_operacional" if tipo == "OPERACIONAL" else "regra_contratual_tabelas"


def _agora() -> str:
    return datetime.now(UTC).isoformat()


def _proxima_versao(atual: str, existentes: set[str]) -> str:
    """`1.0` vira `1.1`; versão sem parte menor ganha uma (`2` vira `2.1`).
    Pula a que já existe na operadora."""
    partes = atual.split(".")
    if len(partes) >= 2 and partes[-1].isdigit():
        base, numero = ".".join(partes[:-1]), int(partes[-1])
    else:
        base, numero = atual, 0
    while True:
        numero += 1
        candidata = f"{base}.{numero}"
        if candidata not in existentes:
            return candidata


def _vigente(supabase, operadora_id: str) -> dict | None:
    versoes = (
        supabase.table("cm_memoria_versao")
        .select("id, versao, parametros_json")
        .eq("operadora_id", operadora_id)
        .eq("vigente", True)
        .execute()
        .data
        or []
    )
    return versoes[0] if versoes else None


def _regras_da_versao(supabase, versao_id: str) -> list[dict[str, Any]]:
    return (
        supabase.table("cm_regra").select("*").eq("memoria_versao_id", versao_id).eq("ativa", True).execute().data
        or []
    )


def _gravar_versao(
    supabase,
    operadora_id: str,
    vigente: dict,
    regras: list[dict[str, Any]],
    mudancas: dict[str, dict[str, Any]],
    autor_id: str | None,
    resumo: str,
) -> dict:
    """A versão nova com as regras da vigente e as `mudancas` (por código), já vigente."""
    existentes = {
        v["versao"]
        for v in supabase.table("cm_memoria_versao").select("versao").eq("operadora_id", operadora_id).execute().data
        or []
    }
    agora = _agora()
    nova = (
        supabase.table("cm_memoria_versao")
        .insert(
            {
                "operadora_id": operadora_id,
                "versao": _proxima_versao(vigente["versao"], existentes),
                "parametros_json": vigente.get("parametros_json") or {},
                "vigente": False,
                "autor_id": autor_id,
                "resumo": resumo,
                "criado_em": agora,
            }
        )
        .execute()
        .data[0]
    )
    copias = []
    for regra in regras:
        copia = {chave: valor for chave, valor in regra.items() if chave not in ("id", "criado_em")}
        copia["memoria_versao_id"] = nova["id"]
        copia.update(mudancas.get(regra["codigo"], {}))
        copias.append(copia)
    gravadas = supabase.table("cm_regra").insert(copias).execute().data if copias else []

    antes = {regra["codigo"]: regra for regra in regras}
    for gravada in gravadas:
        if gravada["codigo"] not in mudancas:
            continue
        anterior = antes[gravada["codigo"]]
        supabase.table("cm_regra_historico").insert(
            {
                "regra_id": gravada["id"],
                "memoria_versao_id": nova["id"],
                "texto_anterior": anterior.get("texto"),
                "texto_novo": gravada["texto"],
                "autor_id": autor_id,
                "criado_em": agora,
            }
        ).execute()
        campos = ("texto", "tipo", "origem", "status")
        supabase.table("cm_registro").insert(
            {
                "autor_id": autor_id,
                "data": agora,
                "entidade": "cm_regra",
                "entidade_id": gravada["id"],
                "antes_json": {c: anterior.get(c) for c in campos},
                "depois_json": {c: gravada.get(c) for c in campos},
            }
        ).execute()

    texto_md = gerar_texto_memoria(supabase, operadora_id, nova["id"])
    supabase.table("cm_memoria_versao").update({"texto_md": texto_md}).eq("id", nova["id"]).execute()
    supabase.table("cm_memoria_versao").update({"vigente": False}).eq("operadora_id", operadora_id).eq(
        "vigente", True
    ).execute()
    supabase.table("cm_memoria_versao").update({"vigente": True}).eq("id", nova["id"]).execute()
    return {**nova, "texto_md": texto_md, "vigente": True}


def mudar_regra(
    supabase,
    sigla: str,
    codigo: str,
    *,
    texto: str,
    tipo: str | None,
    origem: str | None,
    decidir: bool,
    autor_id: str | None,
    permissoes: list[str],
) -> dict[str, Any]:
    """Edita a regra vigente (ou decide a pendente, que vira vigente) numa versão nova da memória.

    Quem muda passa a ser quem validou, com a data de agora.
    """
    sigla = sigla.strip().upper()
    operadoras = supabase.table("cm_operadora").select("id, sigla").eq("sigla", sigla).execute().data or []
    vigente = _vigente(supabase, operadoras[0]["id"]) if operadoras else None
    if not vigente:
        raise RegraNaoEncontradaError(f"A operadora {sigla} não tem memória carregada.")
    operadora_id = operadoras[0]["id"]
    regras = _regras_da_versao(supabase, vigente["id"])
    alvo = next((r for r in regras if r["codigo"] == codigo), None)
    if alvo is None:
        raise RegraNaoEncontradaError(f"A regra {codigo} não está na memória vigente de {sigla}.")

    texto = texto.strip()
    if not texto:
        raise MudancaRecusadaError("Escreva o texto da regra.")
    if _CPF.search(texto):
        raise MudancaRecusadaError(
            "O texto tem um número no formato de CPF. A memória não pode ter dado de paciente: tire o número."
        )
    if decidir and alvo["status"] == "VIGENTE":
        raise MudancaRecusadaError(f"A regra {codigo} já está vigente: edite em vez de decidir.")
    if not decidir and alvo["status"] != "VIGENTE":
        raise MudancaRecusadaError(f"A regra {codigo} está pendente: decida em vez de editar.")

    faltam = {permissao_do_tipo(t) for t in (alvo.get("tipo"), tipo)} - set(permissoes)
    if faltam:
        raise SemPermissaoNaRegraError("Sem permissão para mudar este tipo de regra.")

    campos: dict[str, Any] = {
        "texto": texto,
        "tipo": tipo,
        "origem": (origem or "").strip() or None,
        "validado_por": autor_id,
        "validado_em": _agora(),
    }
    if decidir:
        campos["status"] = "VIGENTE"
    resumo = f"{codigo} {'decidida (vigente)' if decidir else 'editada'}"
    nova = _gravar_versao(supabase, operadora_id, vigente, regras, {codigo: campos}, autor_id, resumo)
    return {"operadora": sigla, "versao": nova["versao"], "regra": codigo}
