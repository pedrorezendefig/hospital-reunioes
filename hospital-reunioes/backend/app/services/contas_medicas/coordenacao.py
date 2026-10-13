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
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.services.contas_medicas import ia
from app.services.contas_medicas.painel import _em_lotes, _filtrar, _meia_noite, segunda_da_semana
from app.services.paginacao import ler_tudo
from app.services.prompt_loader import load_prompt
from app.utils.text_sanitizer import sanitizar_estrutura

__all__ = [
    "CONFERIR_EVIDENCIA",
    "CenarioNaoEncontradoError",
    "LembreteJaMarcadoError",
    "LembreteNaoEncontradoError",
    "aba_de_cenarios",
    "editar_cenario",
    "incluido_pela_coordenacao",
    "itens_dos_cenarios",
    "lembretes_abertos",
    "listar_cenarios",
    "marcar_lembrete",
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


class LembreteNaoEncontradoError(Exception):
    """O lembrete da rota não existe."""


class LembreteJaMarcadoError(Exception):
    """O lembrete já saiu de aberto."""


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


def itens_dos_cenarios(supabase, ids: list[str]) -> dict[str, list[dict]]:
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
    itens = itens_dos_cenarios(supabase, [c["id"] for c in cenarios])
    siglas = {o["id"]: o["sigla"] for o in _operadoras(supabase)}
    return [_cenario_para_a_tela(c, itens[c["id"]], siglas) for c in cenarios]


def aba_de_cenarios(supabase) -> dict[str, Any]:
    """A aba Cenários: a lista e as operadoras, para o cadastro escolher uma ou todas."""
    operadoras = [{"sigla": o["sigla"], "nome": o.get("nome")} for o in _operadoras(supabase)]
    return {"cenarios": listar_cenarios(supabase), "operadoras": operadoras}


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
    antes_itens = itens_dos_cenarios(supabase, [cenario_id])[cenario_id]
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


# ----------------------------------------------------------------------------------
# Os lembretes
# ----------------------------------------------------------------------------------


def _dinheiro(valor: Decimal) -> float:
    return float(round(valor, 2))


def _por_id(linhas: list[dict]) -> dict[str, dict]:
    return {linha["id"]: linha for linha in linhas}


def _numero_ou_nada(valor: Any) -> float | None:
    return float(valor) if valor is not None else None


def _lembrete_para_a_tela(lembrete: dict, cenario: dict, itens: list[dict]) -> dict[str, Any]:
    """O lembrete como a coordenadora lê. A etiqueta mora na observação do
    lembrete aberto (a 118 não tem coluna para ela)."""
    etiqueta = lembrete.get("estado") == "ABERTO" and lembrete.get("observacao") == CONFERIR_EVIDENCIA
    return {
        "id": lembrete["id"],
        "cenario": {
            "codigo": cenario.get("codigo"),
            "nome": cenario.get("nome"),
            "orientacao": cenario.get("orientacao"),
        },
        "data": lembrete.get("data"),
        "setor": lembrete.get("setor"),
        "evidencia_pagina": lembrete.get("evidencia_pagina"),
        "evidencia_trecho": lembrete.get("evidencia_trecho"),
        "etiquetas": [CONFERIR_EVIDENCIA] if etiqueta else [],
        "criado_em": lembrete.get("criado_em"),
        "insumos": [
            {
                "codigo": item["codigo"],
                "descricao": item.get("descricao"),
                "quantidade": _numero_ou_nada(item.get("quantidade")),
                "preco_tabela": _numero_ou_nada(item.get("preco_tabela")),
                "valor": _numero_ou_nada(item.get("valor")),
            }
            for item in itens
        ],
    }


def _conta_para_a_tela(conta: dict, atendimento: dict, siglas: dict[str, str]) -> dict[str, Any]:
    return {
        "conta_id": conta["id"],
        "numero_atendimento": atendimento.get("numero_atendimento"),
        "paciente_rotulo": atendimento.get("paciente_rotulo"),
        "numero_conta": conta.get("numero_conta"),
        "operadora": siglas.get(atendimento.get("operadora_id") or ""),
        "situacao": conta.get("situacao"),
        "concluida_em": conta.get("concluida_em"),
        "periodo_inicio": conta.get("periodo_inicio"),
        "periodo_fim": conta.get("periodo_fim"),
        "lembretes": [],
    }


def lembretes_abertos(supabase) -> dict[str, Any]:
    """Os três números do topo e os lembretes abertos agrupados por conta, a
    conta do lembrete mais antigo primeiro. As leituras por id vão em lotes."""
    lembretes = ler_tudo(
        lambda: supabase.table("cm_lembrete").select("*").eq("estado", "ABERTO").order("criado_em").order("id"),
        rotulo="lembretes abertos",
    )
    itens: dict[str, list[dict]] = defaultdict(list)
    for item in _em_lotes(
        supabase, "cm_lembrete_item", "*", "lembrete_id", (lb["id"] for lb in lembretes), "insumos dos lembretes"
    ):
        itens[item["lembrete_id"]].append(item)
    cenarios = _por_id(
        _em_lotes(
            supabase,
            "cm_cenario",
            "id, codigo, nome, orientacao",
            "id",
            (lb["cenario_id"] for lb in lembretes),
            "cenários dos lembretes",
        )
    )
    contas = _por_id(
        _em_lotes(
            supabase,
            "cm_conta",
            "id, atendimento_id, numero_conta, situacao, concluida_em, periodo_inicio, periodo_fim",
            "id",
            (lb["conta_id"] for lb in lembretes),
            "contas com lembrete",
        )
    )
    atendimentos = _por_id(
        _em_lotes(
            supabase,
            "cm_atendimento",
            "id, numero_atendimento, paciente_rotulo, operadora_id",
            "id",
            (c["atendimento_id"] for c in contas.values() if c.get("atendimento_id")),
            "atendimentos com lembrete",
        )
    )
    siglas = {o["id"]: o["sigla"] for o in _operadoras(supabase)}

    por_conta: dict[str, dict[str, Any]] = {}
    total = Decimal(0)
    for lembrete in lembretes:
        conta = contas.get(lembrete["conta_id"])
        if conta is None:
            continue
        if conta["id"] not in por_conta:
            atendimento = atendimentos.get(conta.get("atendimento_id") or "") or {}
            por_conta[conta["id"]] = _conta_para_a_tela(conta, atendimento, siglas)
        do_lembrete = itens[lembrete["id"]]
        total += sum((Decimal(str(i.get("valor") or 0)) for i in do_lembrete), Decimal(0))
        cenario = cenarios.get(lembrete["cenario_id"]) or {}
        por_conta[conta["id"]]["lembretes"].append(_lembrete_para_a_tela(lembrete, cenario, do_lembrete))

    return {
        "numeros": {
            "lembretes_abertos": sum(len(conta["lembretes"]) for conta in por_conta.values()),
            "contas_com_lembrete": len(por_conta),
            "valor_a_conferir": _dinheiro(total),
        },
        "contas": list(por_conta.values()),
    }


def marcar_lembrete(
    supabase, lembrete_id: str, estado: str, observacao: str | None, autor_id: str | None
) -> dict[str, Any]:
    """Incluído ou Não se aplica, com quem marcou, quando e a observação
    opcional, que substitui a etiqueta do lembrete aberto. Condicional no
    estado: duas marcações ao mesmo tempo gravam uma vez."""
    if not (supabase.table("cm_lembrete").select("id").eq("id", lembrete_id).execute().data or []):
        raise LembreteNaoEncontradoError("Lembrete não encontrado")
    marcado = (
        supabase.table("cm_lembrete")
        .update(
            {
                "estado": estado,
                "observacao": (observacao or "").strip() or None,
                "marcado_por": autor_id,
                "marcado_em": _agora(),
            }
        )
        .eq("id", lembrete_id)
        .eq("estado", "ABERTO")
        .execute()
        .data
        or []
    )
    if not marcado:
        raise LembreteJaMarcadoError("Este lembrete já foi marcado")
    (lembrete,) = marcado
    return {chave: lembrete.get(chave) for chave in ("id", "estado", "observacao", "marcado_por", "marcado_em")}


# ----------------------------------------------------------------------------------
# O cartão do Painel
# ----------------------------------------------------------------------------------


def incluido_pela_coordenacao(
    supabase, *, semana: date, operadora_id: str | None = None, tipo: str | None = None
) -> dict[str, Any]:
    """O R$ dos lembretes marcados Incluído na semana (segunda a domingo, pela
    data da marcação), com os filtros do Painel. Fica numa chave própria, fora
    da nota de entrada e da produção das faturistas."""
    segunda = segunda_da_semana(semana)
    lembretes = ler_tudo(
        lambda: (
            supabase.table("cm_lembrete")
            .select("id, conta_id, marcado_em")
            .eq("estado", "INCLUIDO")
            .gte("marcado_em", _meia_noite(segunda))
            .lt("marcado_em", _meia_noite(segunda + timedelta(weeks=1)))
            .order("id")
        ),
        rotulo="lembretes incluídos",
    )
    contas = _em_lotes(
        supabase, "cm_conta", "id, atendimento_id", "id", (lb["conta_id"] for lb in lembretes), "contas do cartão"
    )
    filtradas = {conta["id"] for conta in _filtrar(supabase, contas, operadora_id, tipo)}
    lembretes = [lb for lb in lembretes if lb["conta_id"] in filtradas]
    itens = _em_lotes(
        supabase, "cm_lembrete_item", "lembrete_id, valor", "lembrete_id", (lb["id"] for lb in lembretes), "R$ incluído"
    )
    total = sum((Decimal(str(item.get("valor") or 0)) for item in itens), Decimal(0))
    return {"valor_incluido": _dinheiro(total), "lembretes_incluidos": len(lembretes)}
