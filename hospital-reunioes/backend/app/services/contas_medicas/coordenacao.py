"""A Conferência da coordenação de Contas médicas (issue #1143, PRD #1129, adendo v1.1).

A segunda checagem que só a coordenadora vê. A gestão cadastra os cenários
(`cm_cenario`, `cm_cenario_item`): o procedimento que dispara, em texto livre,
e os insumos a conferir. O Passo C (`passo_c.py`) acha as ocorrências e cria os
lembretes (`cm_lembrete`, `cm_lembrete_item`). Este módulo é o da tela: o
cadastro com a proposta da IA, a lista por conta, a marcação e o cartão do
Painel.

Cenário e lembrete nunca entram no Passo B, no Guia, na nota nem na produção
da faturista. Quem barra o acesso é a rota (permissão "conferência da
coordenação"; o cadastro pede também "incluir regra operacional").
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.services.contas_medicas import ia
from app.services.contas_medicas.painel import _em_lotes
from app.services.paginacao import ler_tudo
from app.services.prompt_loader import load_prompt
from app.utils.text_sanitizer import sanitizar_estrutura

__all__ = [
    "CONFERIR_EVIDENCIA",
    "CenarioNaoEncontradoError",
    "editar_cenario",
    "listar_cenarios",
    "novo_cenario",
    "propor_cenario",
]

ENTIDADE_CENARIO = "cm_cenario"

# A etiqueta do lembrete cujo trecho não está na página citada nem na vizinha.
# A 118 não tem coluna para ela: o lembrete aberto a guarda na observação, que
# a marcação da coordenadora substitui.
CONFERIR_EVIDENCIA = "conferir evidência"

# O texto da pessoa que vai para a IA: um cenário cabe em poucas linhas.
TETO_DO_TEXTO = 4000

_CODIGO = re.compile(r"^CEN-(\d+)$")


class CenarioNaoEncontradoError(Exception):
    """O cenário da rota não existe."""


def _agora() -> str:
    return datetime.now(UTC).isoformat()


# ----------------------------------------------------------------------------------
# O cadastro
# ----------------------------------------------------------------------------------


class _Estrito(BaseModel):
    model_config = ConfigDict(extra="forbid")


class InsumoProposto(_Estrito):
    codigo: str
    descricao: str | None
    quantidade: float


class CenarioProposto(_Estrito):
    """O que a IA devolve do texto da pessoa (adendo v1.1, item 3.2)."""

    nome: str
    operadora: str | None
    gatilho_texto: str
    orientacao: str | None
    insumos: list[InsumoProposto]


def _operadoras(supabase) -> list[dict[str, Any]]:
    return supabase.table("cm_operadora").select("id, sigla, nome").order("sigla").execute().data or []


def operadora_da_sigla(supabase, sigla: str | None) -> str | None:
    """O id da operadora pela sigla, sem diferença de maiúscula; None para "todas"."""
    if not sigla:
        return None
    alvo = sigla.strip().upper()
    return next((o["id"] for o in _operadoras(supabase) if (o.get("sigla") or "").upper() == alvo), None)


def _sigla(supabase, operadora_id: str | None) -> str | None:
    if not operadora_id:
        return None
    return next((o["sigla"] for o in _operadoras(supabase) if o["id"] == operadora_id), None)


def codigos_fora_da_tabela(supabase, codigos: list[str], operadora_id: str | None) -> list[str]:
    """Os códigos que não estão em tabela de preço nenhuma da operadora (ou de
    nenhuma operadora, no cenário que vale para todas), pelo código ou pelo
    código alternativo. É o que a pessoa confere antes de salvar."""
    procurados = sorted({c.strip() for c in codigos if c and c.strip()})
    if not procurados:
        return []
    tabelas: list[str] | None = None
    if operadora_id:
        ligacoes = (
            supabase.table("cm_operadora_tabela").select("tabela_id").eq("operadora_id", operadora_id).execute().data
            or []
        )
        tabelas = [ligacao["tabela_id"] for ligacao in ligacoes]
    achados: set[str] = set()
    for campo in ("codigo", "codigo_alternativo"):
        consulta = supabase.table("cm_tabela_preco_item").select(f"tabela_id, {campo}").in_(campo, procurados)
        for item in consulta.execute().data or []:
            if tabelas is None or item.get("tabela_id") in tabelas:
                achados.add(item[campo])
    return [codigo for codigo in procurados if codigo not in achados]


def propor_cenario(supabase, texto: str) -> dict[str, Any]:
    """Os campos que a IA lê do texto da pessoa, com cada código conferido
    contra a tabela. Nada é gravado: a pessoa confere e salva.

    O custo vai para `cm_chamada_ia` como chamada curta (passo OBSERVACAO): o
    CHECK da migration 117 não tem um passo próprio para cenário."""
    siglas = ", ".join(o["sigla"] for o in _operadoras(supabase)) or "(nenhuma)"
    proposta = ia.chamada_curta(
        load_prompt("contas_medicas_cenario"),
        f"OPERADORAS\n{siglas}\n\nTEXTO DA PESSOA\n{texto[:TETO_DO_TEXTO]}",
        CenarioProposto,
        passo="OBSERVACAO",
        supabase=supabase,
        conta_id=None,
    )
    campos = sanitizar_estrutura(proposta.model_dump())
    operadora_id = operadora_da_sigla(supabase, campos["operadora"])
    fora = codigos_fora_da_tabela(supabase, [i["codigo"] for i in campos["insumos"]], operadora_id)
    insumos = []
    for insumo in campos["insumos"]:
        codigo = insumo["codigo"].strip()
        insumos.append({**insumo, "codigo": codigo, "na_tabela": bool(codigo) and codigo not in fora})
    return {
        "campos": {
            "nome": campos["nome"],
            "operadora_sigla": _sigla(supabase, operadora_id),
            "gatilho_texto": campos["gatilho_texto"],
            "orientacao": campos["orientacao"],
            "ativo": True,
            "insumos": insumos,
        },
        "codigos_fora_da_tabela": fora,
    }


def _proximo_codigo(supabase) -> str:
    numeros = [
        int(achado.group(1))
        for cenario in supabase.table("cm_cenario").select("codigo").execute().data or []
        if (achado := _CODIGO.match(cenario.get("codigo") or ""))
    ]
    return f"CEN-{max(numeros, default=0) + 1:03d}"


def _registrar(supabase, autor_id: str | None, cenario_id: str, antes: dict | None, depois: dict) -> None:
    supabase.table("cm_registro").insert(
        {
            "autor_id": autor_id,
            "data": _agora(),
            "entidade": ENTIDADE_CENARIO,
            "entidade_id": cenario_id,
            "antes_json": antes,
            "depois_json": depois,
        }
    ).execute()


def _itens_dos_cenarios(supabase, ids: list[str]) -> dict[str, list[dict]]:
    por_cenario: dict[str, list[dict]] = defaultdict(list)
    for item in _em_lotes(supabase, "cm_cenario_item", "*", "cenario_id", ids, "insumos dos cenários"):
        por_cenario[item["cenario_id"]].append(item)
    return por_cenario


def _cenario_para_a_tela(cenario: dict, itens: list[dict], siglas: dict[str, str]) -> dict[str, Any]:
    return {
        "id": cenario["id"],
        "codigo": cenario["codigo"],
        "nome": cenario["nome"],
        "operadora_sigla": siglas.get(cenario.get("operadora_id") or ""),
        "gatilho_texto": cenario["gatilho_texto"],
        "orientacao": cenario.get("orientacao"),
        "ativo": bool(cenario.get("ativo")),
        "criado_em": cenario.get("criado_em"),
        "insumos": [
            {"codigo": i["codigo"], "descricao": i.get("descricao"), "quantidade": float(i.get("quantidade") or 0)}
            for i in itens
        ],
    }


def listar_cenarios(supabase) -> list[dict[str, Any]]:
    """Todos os cenários, ativos e inativos, na ordem do código."""
    cenarios = ler_tudo(lambda: supabase.table("cm_cenario").select("*").order("codigo"), rotulo="cenários")
    itens = _itens_dos_cenarios(supabase, [c["id"] for c in cenarios])
    siglas = {o["id"]: o["sigla"] for o in _operadoras(supabase)}
    return [_cenario_para_a_tela(c, itens[c["id"]], siglas) for c in cenarios]


def _linha_do_cenario(campos: dict[str, Any], operadora_id: str | None) -> dict[str, Any]:
    return {
        "nome": campos["nome"].strip(),
        "operadora_id": operadora_id,
        "gatilho_texto": campos["gatilho_texto"].strip(),
        "orientacao": (campos.get("orientacao") or "").strip() or None,
        "ativo": bool(campos.get("ativo", True)),
    }


def _gravar_insumos(supabase, cenario_id: str, insumos: list[dict[str, Any]]) -> None:
    if not insumos:
        return
    supabase.table("cm_cenario_item").insert(
        [
            {
                "cenario_id": cenario_id,
                "codigo": insumo["codigo"].strip(),
                "descricao": (insumo.get("descricao") or "").strip() or None,
                "quantidade": float(insumo["quantidade"]),
            }
            for insumo in insumos
        ]
    ).execute()


def novo_cenario(supabase, campos: dict[str, Any], autor_id: str | None) -> dict[str, Any]:
    """Grava o cenário conferido, com o próximo código CEN-NNN, o autor e o
    registro. Código fora da tabela não impede: é apontado na resposta."""
    operadora_id = operadora_da_sigla(supabase, campos.get("operadora_sigla"))
    linha = {**_linha_do_cenario(campos, operadora_id), "codigo": _proximo_codigo(supabase), "autor_id": autor_id}
    (cenario,) = supabase.table("cm_cenario").insert(linha).execute().data
    _gravar_insumos(supabase, cenario["id"], campos["insumos"])
    _registrar(supabase, autor_id, cenario["id"], None, {**linha, "insumos": campos["insumos"]})
    return _resposta_do_cenario(supabase, cenario["id"], campos, operadora_id)


def _resposta_do_cenario(supabase, cenario_id: str, campos: dict[str, Any], operadora_id: str | None) -> dict:
    (cenario,) = [c for c in listar_cenarios(supabase) if c["id"] == cenario_id]
    fora = codigos_fora_da_tabela(supabase, [i["codigo"] for i in campos["insumos"]], operadora_id)
    return {"cenario": cenario, "codigos_fora_da_tabela": fora}


def editar_cenario(supabase, cenario_id: str, campos: dict[str, Any], autor_id: str | None) -> dict[str, Any]:
    """Troca os campos e os insumos do cenário (inclusive ativar e desativar),
    com o antes e o depois no registro. Vale para as contas analisadas dali em
    diante: o lembrete já criado fica como está."""
    atuais = supabase.table("cm_cenario").select("*").eq("id", cenario_id).execute().data or []
    if not atuais:
        raise CenarioNaoEncontradoError("Cenário não encontrado")
    (atual,) = atuais
    antes_itens = _itens_dos_cenarios(supabase, [cenario_id])[cenario_id]
    operadora_id = operadora_da_sigla(supabase, campos.get("operadora_sigla"))
    linha = _linha_do_cenario(campos, operadora_id)
    supabase.table("cm_cenario").update(linha).eq("id", cenario_id).execute()
    supabase.table("cm_cenario_item").delete().eq("cenario_id", cenario_id).execute()
    _gravar_insumos(supabase, cenario_id, campos["insumos"])
    antes = {
        **{chave: atual.get(chave) for chave in linha},
        "insumos": [{c: i.get(c) for c in ("codigo", "descricao", "quantidade")} for i in antes_itens],
    }
    _registrar(supabase, autor_id, cenario_id, antes, {**linha, "insumos": campos["insumos"]})
    return _resposta_do_cenario(supabase, cenario_id, campos, operadora_id)
