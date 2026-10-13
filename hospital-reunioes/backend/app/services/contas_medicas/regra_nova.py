"""Ensinar uma regra nova na Memória da operadora (issue #1141, PRD #1129, ADR 0070).

Dois tempos. Na proposta, a pessoa escreve a regra em linguagem comum e a IA
devolve a regra no formato da memória, o parâmetro do cabeçalho que muda, as
regras com que ela conflita e o efeito no Guia; nada é gravado. No "Validar
regra", a regra conferida pela pessoa entra numa versão nova da memória, pelo
mesmo caminho da edição pela tela (`memoria_edicao`): histórico, registro e
texto gerado do banco. O parâmetro, quando há, muda no `parametros_json` da
versão nova.

A conta A fazer ou Em correção analisada com uma versão que não é mais a
vigente fica marcada com "regra nova desde a análise": é ela que o "Reanalisar
com a regra nova" refaz.
"""

from __future__ import annotations

import copy
import json
import re
from typing import Any

from app.services.contas_medicas import ia
from app.services.contas_medicas.memoria import _CPF
from app.services.contas_medicas.memoria_edicao import (
    MudancaRecusadaError,
    RegraNaoEncontradaError,
    SemPermissaoNaRegraError,
    _agora,
    _gravar_versao,
    _regras_da_versao,
    _vigente,
    permissao_do_tipo,
)
from app.services.contas_medicas.memoria_texto import gerar_texto_memoria

__all__ = [
    "SITUACOES_REANALISAVEIS",
    "contas_com_regra_nova",
    "ensinar_regra",
    "propor_regra_nova",
    "regra_nova_desde_a_analise",
]

# As situações em que "Reanalisar" vale: o Guia pronto e ainda em aberto.
SITUACOES_REANALISAVEIS = ("A_FAZER", "EM_CORRECAO")

# A chave do cabeçalho, com ponto entre os níveis. Nome e versão da memória não
# mudam por regra: a versão é do sistema, e a sigla é a operadora.
_CHAVE = re.compile(r"[a-z_][a-z0-9_]*(\.[a-z0-9_]+)*")
_CHAVES_PROTEGIDAS = frozenset({"operadora", "versao_memoria", "nome"})


def _operadora_e_vigente(supabase, sigla: str) -> tuple[str, str, dict]:
    sigla = sigla.strip().upper()
    operadoras = supabase.table("cm_operadora").select("id, sigla").eq("sigla", sigla).execute().data or []
    vigente = _vigente(supabase, operadoras[0]["id"]) if operadoras else None
    if not vigente:
        raise RegraNaoEncontradaError(f"A operadora {sigla} não tem memória carregada.")
    return sigla, operadoras[0]["id"], vigente


def _chave_valida(chave: str) -> bool:
    return bool(_CHAVE.fullmatch(chave)) and chave.split(".")[0] not in _CHAVES_PROTEGIDAS


def _valor_do_parametro(parametros: dict[str, Any], chave: str) -> Any:
    valor: Any = parametros
    for parte in chave.split("."):
        if not isinstance(valor, dict):
            return None
        valor = valor.get(parte)
    return valor


def _com_parametro(parametros: dict[str, Any], chave: str, valor: Any) -> dict[str, Any]:
    """O cabeçalho com a chave trocada; o resto, inclusive o que o código não lê, fica."""
    novo = copy.deepcopy(parametros)
    *caminho, ultima = chave.split(".")
    no = novo
    for parte in caminho:
        if not isinstance(no.get(parte), dict):
            no[parte] = {}
        no = no[parte]
    no[ultima] = valor
    return novo


def _valor_json(valor_json: str) -> Any:
    try:
        return json.loads(valor_json)
    except ValueError:
        return valor_json


def propor_regra_nova(supabase, sigla: str, texto: str) -> dict[str, Any]:
    """A proposta da IA para o texto da pessoa, sem gravar nada na memória.

    O "antes" do parâmetro e o texto das regras em conflito vêm da memória
    vigente, e não da IA; conflito com ID que a memória não tem fica de fora.
    """
    texto = texto.strip()
    if not texto:
        raise MudancaRecusadaError("Escreva a regra.")
    if _CPF.search(texto):
        raise MudancaRecusadaError(
            "O texto tem um número no formato de CPF. A memória não pode ter dado de paciente: tire o número."
        )
    _, operadora_id, vigente = _operadora_e_vigente(supabase, sigla)
    memoria = gerar_texto_memoria(supabase, operadora_id, vigente["id"])
    proposta = ia.propor_regra(texto, memoria, supabase=supabase)

    regras = {r["codigo"]: r for r in _regras_da_versao(supabase, vigente["id"])}
    parametro = None
    if proposta.parametro and _chave_valida(proposta.parametro.chave):
        chave = proposta.parametro.chave
        parametro = {
            "chave": chave,
            "antes": _valor_do_parametro(vigente.get("parametros_json") or {}, chave),
            "depois": _valor_json(proposta.parametro.valor_json),
        }
    return {
        "regra": proposta.regra.model_dump(),
        "parametro": parametro,
        "conflitos": [
            {"codigo": codigo, "texto": regras[codigo]["texto"]}
            for codigo in dict.fromkeys(proposta.conflitos)
            if codigo in regras
        ],
        "efeito_no_guia": proposta.efeito_no_guia,
    }


def _proximo_codigo(sigla: str, secao: str, regras: list[dict[str, Any]]) -> str:
    """`ALFA-DIA-03` quando a seção já tem a 01 e a 02: o maior número da seção mais um."""
    prefixo = f"{sigla}-{secao}-"
    numeros = [
        int(r["codigo"][len(prefixo) :])
        for r in regras
        if r["codigo"].startswith(prefixo) and r["codigo"][len(prefixo) :].isdigit()
    ]
    return f"{prefixo}{max(numeros, default=0) + 1:02d}"


def ensinar_regra(
    supabase,
    sigla: str,
    *,
    secao: str,
    texto: str,
    tipo: str | None,
    origem: str | None,
    parametro: dict[str, Any] | None,
    autor_id: str | None,
    permissoes: list[str],
) -> dict[str, Any]:
    """O "Validar regra": a regra conferida pela pessoa entra vigente numa
    versão nova da memória, com quem validou e a data; o parâmetro, quando há,
    muda no cabeçalho da versão nova.

    Regra operacional pede "incluir regra operacional"; contratual, e qualquer
    regra que mexa em parâmetro do cabeçalho, pede "regra contratual e tabelas".
    """
    sigla, operadora_id, vigente = _operadora_e_vigente(supabase, sigla)
    texto = texto.strip()
    if not texto:
        raise MudancaRecusadaError("Escreva o texto da regra.")
    if _CPF.search(texto):
        raise MudancaRecusadaError(
            "O texto tem um número no formato de CPF. A memória não pode ter dado de paciente: tire o número."
        )
    if parametro and not _chave_valida(parametro["chave"]):
        raise MudancaRecusadaError(f"O parâmetro {parametro['chave']} não pode mudar por regra.")
    pedidas = {permissao_do_tipo(tipo)} | ({permissao_do_tipo(None)} if parametro else set())
    if pedidas - set(permissoes):
        raise SemPermissaoNaRegraError("Sem permissão para incluir este tipo de regra.")

    regras = _regras_da_versao(supabase, vigente["id"])
    codigo = _proximo_codigo(sigla, secao, regras)
    nova_regra = {
        "operadora_id": operadora_id,
        "codigo": codigo,
        "secao": secao,
        "texto": texto,
        "tipo": tipo,
        "origem": (origem or "").strip() or None,
        "status": "VIGENTE",
        "validado_por": autor_id,
        "validado_em": _agora(),
        "ativa": True,
    }
    parametros = None
    resumo = f"{codigo} incluída (regra nova)"
    if parametro:
        parametros = _com_parametro(vigente.get("parametros_json") or {}, parametro["chave"], parametro["valor"])
        resumo += f", com o parâmetro {parametro['chave']}"
    versao = _gravar_versao(
        supabase, operadora_id, vigente, regras, {}, autor_id, resumo, novas=[nova_regra], parametros=parametros
    )
    return {
        "operadora": sigla,
        "versao": versao["versao"],
        "regra": codigo,
        "contas_com_regra_nova": len(contas_com_regra_nova(supabase, sigla)),
    }


def _analisada_antes(conta: dict[str, Any], vigente: dict | None) -> bool:
    """A conta aberta analisada com uma versão da memória que não é mais a vigente.
    Conta sem a versão gravada fica sem marca: não dá para dizer o que mudou."""
    return (
        conta.get("situacao") in SITUACOES_REANALISAVEIS
        and bool(vigente)
        and bool(conta.get("memoria_versao_id"))
        and conta["memoria_versao_id"] != vigente["id"]
    )


def regra_nova_desde_a_analise(supabase, conta: dict[str, Any], operadora_id: str | None) -> bool:
    """A marca "regra nova desde a análise" de uma conta, para o Guia."""
    return bool(operadora_id) and _analisada_antes(conta, _vigente(supabase, operadora_id))


def contas_com_regra_nova(supabase, sigla: str) -> list[dict[str, Any]]:
    """As contas A fazer e Em correção da operadora com a marca "regra nova
    desde a análise", em ordem de atendimento e conta."""
    operadoras = supabase.table("cm_operadora").select("id").eq("sigla", sigla.strip().upper()).execute().data or []
    if not operadoras:
        return []
    vigente = _vigente(supabase, operadoras[0]["id"])
    atendimentos = {
        a["id"]: a.get("numero_atendimento")
        for a in supabase.table("cm_atendimento")
        .select("id, numero_atendimento")
        .eq("operadora_id", operadoras[0]["id"])
        .execute()
        .data
        or []
    }
    if not atendimentos or not vigente:
        return []
    contas = (
        supabase.table("cm_conta")
        .select("id, atendimento_id, numero_conta, situacao, memoria_versao_id")
        .in_("atendimento_id", sorted(atendimentos))
        .in_("situacao", list(SITUACOES_REANALISAVEIS))
        .execute()
        .data
        or []
    )
    marcadas = [
        {
            "id": c["id"],
            "numero_atendimento": atendimentos.get(c["atendimento_id"]),
            "numero_conta": c.get("numero_conta"),
            "situacao": c["situacao"],
        }
        for c in contas
        if _analisada_antes(c, vigente)
    ]
    return sorted(marcadas, key=lambda c: (str(c["numero_atendimento"] or ""), str(c["numero_conta"] or "")))
