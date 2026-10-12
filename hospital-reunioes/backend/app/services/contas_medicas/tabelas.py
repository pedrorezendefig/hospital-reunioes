"""Tabelas de preço da operadora e a busca de preço (issue #1120, PRD #1113, ADR 0070).

A gestão envia o CSV de cada tabela com a categoria e a vigência. O formato é
reconhecido pelo cabeçalho (os CSVs do diretor: `;`, decimal com ponto,
UTF-8); cada linha vira um item com `precos_json` (`{comum, carioca}`,
`{valor}` ou `{lpm}`) e o resto das colunas em `extra_json`. A versão nova
fica ao lado da anterior: a busca escolhe pela data do atendimento.

A gravação protege o que está em uso: a tabela e os itens nascem soltos e só
a última escrita liga a tabela à operadora. Uma falha no meio deixa uma
tabela órfã, que a busca nunca vê.

`preco` nunca inventa valor. Sem tabela, sem versão na data, preço zero, código
repetido sem desempate ou regra de preço de tabela que não é carregada
(Brasíndice, Simpro, CBHPM) dão `NAO_CONFERIDO`; "PACOTE" na coluna dá `PACOTE`.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

__all__ = [
    "NAO_CONFERIDO",
    "PACOTE",
    "TabelaLida",
    "TabelaRecusadaError",
    "bloco_da_categoria",
    "categoria_da_memoria",
    "importar_tabela",
    "ler_tabela",
    "preco",
]

NAO_CONFERIDO = "NAO_CONFERIDO"
PACOTE = "PACOTE"

# Itens por requisição ao PostgREST: a LPM da Unimed tem 35 mil linhas.
_LOTE = 1000


class TabelaRecusadaError(ValueError):
    """O CSV não entra; a mensagem é para quem enviou."""


@dataclass(frozen=True)
class _Formato:
    nome: str
    descricao: str
    colunas: tuple[str, ...]
    # Coluna do CSV -> campo do item. O que não está aqui vai para `extra_json`.
    codigo: str
    codigo_alternativo: str | None
    precos: dict[str, str]
    regra_preco: str
    chave: str


# A ordem importa: o primeiro formato cujas colunas estão todas no cabeçalho
# vence. Nenhum cabeçalho real casa com dois.
FORMATOS: tuple[_Formato, ...] = (
    _Formato(
        nome="MATERIAIS_COMUM_CARIOCA",
        descricao="materiais com preço Comum e Carioca",
        colunas=("codigo_assim", "codigo_tuss", "grupo", "descricao", "preco_comum", "preco_carioca"),
        codigo="codigo_tuss",
        codigo_alternativo="codigo_assim",
        precos={"comum": "preco_comum", "carioca": "preco_carioca"},
        regra_preco="COLUNA",
        chave="codigo_tuss",
    ),
    _Formato(
        nome="DIARIAS_TAXAS_COMUM_CARIOCA",
        descricao="diárias e taxas com preço Comum e Carioca",
        colunas=("secao_aditivo", "codigo", "descricao", "cbo", "preco_carioca", "preco_comum"),
        codigo="codigo",
        codigo_alternativo=None,
        precos={"comum": "preco_comum", "carioca": "preco_carioca"},
        regra_preco="COLUNA",
        chave="codigo",
    ),
    _Formato(
        nome="PACOTES",
        descricao="pacotes",
        colunas=(
            "grupo",
            "codigo",
            "acomodacao",
            "codigo_tuss",
            "porte",
            "descricao",
            "permanencia",
            "valor",
            "observacao",
        ),
        codigo="codigo",
        codigo_alternativo=None,
        precos={"valor": "valor"},
        regra_preco="COLUNA",
        chave="codigo",
    ),
    _Formato(
        nome="DIARIAS_TAXAS_VALOR",
        descricao="diárias e taxas com valor único",
        colunas=("secao", "codigo", "descricao", "valor"),
        codigo="codigo",
        codigo_alternativo=None,
        precos={"valor": "valor"},
        regra_preco="COLUNA",
        chave="codigo",
    ),
    _Formato(
        nome="LPM",
        descricao="LPM (lista de preços de material e medicamento)",
        colunas=("codigo", "codigo_tiss", "descricao", "preco_lpm", "taxa_custos", "inicio_vigencia", "fim_vigencia"),
        codigo="codigo",
        codigo_alternativo="codigo_tiss",
        precos={"lpm": "preco_lpm"},
        regra_preco="LPM",
        chave="codigo",
    ),
)

_NUMERO = re.compile(r"-?\d+(?:\.\d+)?")

# A chave do bloco `tabelas` da memória para cada categoria. Chave que não
# está aqui vira categoria pelo próprio nome (`sadt` -> SADT): a próxima
# operadora inventa categoria sem pedir deploy.
_CATEGORIA_DA_MEMORIA = {
    "materiais": "MATERIAL",
    "medicamentos": "MEDICAMENTO",
    "diarias_taxas": "DIARIA_TAXA",
    "pacotes": "PACOTE",
    "honorarios": "HONORARIO",
}

# O que o bloco diz da carga, e não da regra de preço.
_CHAVES_DA_CARGA = frozenset({"situacao", "arquivo", "versao"})


@dataclass(frozen=True)
class TabelaLida:
    formato: _Formato
    itens: tuple[dict[str, Any], ...]


def _colunas_esperadas() -> str:
    return " | ".join(f"{f.descricao}: {';'.join(f.colunas)}" for f in FORMATOS)


def _preco_da_celula(texto: str, numero_da_linha: int, coluna: str) -> float | str | None:
    valor = texto.strip()
    if not valor:
        return None
    if valor.upper() == PACOTE:
        return PACOTE
    if not _NUMERO.fullmatch(valor):
        raise TabelaRecusadaError(
            f"Linha {numero_da_linha}: o preço da coluna {coluna} é {valor!r}, que não é número com ponto "
            "decimal nem PACOTE."
        )
    return float(valor)


def _item(formato: _Formato, linha: dict[str, str], numero: int) -> dict[str, Any]:
    proprias = {formato.codigo, "descricao", *formato.precos.values()}
    if formato.codigo_alternativo:
        proprias.add(formato.codigo_alternativo)
    extra = {coluna: valor for coluna, valor in linha.items() if coluna not in proprias and valor}
    if "codigo_tuss" in extra:
        # Pacote com mais de um TUSS (`31309020|31303013`): a busca acha por qualquer um.
        extra["codigos_tuss"] = [t.strip() for t in extra.pop("codigo_tuss").split("|") if t.strip()]
    return {
        "codigo": linha[formato.codigo],
        "codigo_alternativo": linha.get(formato.codigo_alternativo or "") or None,
        "descricao": linha.get("descricao") or None,
        "grupo": linha.get("grupo") or linha.get("secao") or linha.get("secao_aditivo") or None,
        "unidade": linha.get("unidade") or None,
        "precos_json": {
            chave: _preco_da_celula(linha.get(coluna, ""), numero, coluna) for chave, coluna in formato.precos.items()
        },
        "extra_json": extra,
    }


def ler_tabela(texto: str) -> TabelaLida:
    """O CSV lido, com o formato reconhecido pelo cabeçalho, ou `TabelaRecusadaError`."""
    linhas = csv.reader(io.StringIO(texto.lstrip("﻿")), delimiter=";")
    cabecalho = [c.strip().lower() for c in next(linhas, [])]
    formato = next((f for f in FORMATOS if set(f.colunas) <= set(cabecalho)), None)
    if formato is None:
        raise TabelaRecusadaError(
            f"O cabeçalho do CSV ({';'.join(cabecalho)}) não é de nenhum formato conhecido. "
            f"Colunas esperadas, em um destes formatos: {_colunas_esperadas()}."
        )
    itens = []
    for numero, celulas in enumerate(linhas, start=2):
        if not any(c.strip() for c in celulas):
            continue
        linha = {coluna: (celulas[i].strip() if i < len(celulas) else "") for i, coluna in enumerate(cabecalho)}
        if not linha[formato.codigo]:
            raise TabelaRecusadaError(f"Linha {numero}: sem código na coluna {formato.codigo}.")
        itens.append(_item(formato, linha, numero))
    if not itens:
        raise TabelaRecusadaError("O CSV só tem o cabeçalho: nenhum item para carregar.")
    return TabelaLida(formato=formato, itens=tuple(itens))


def categoria_da_memoria(chave: str) -> str:
    """A categoria de tabela de uma chave do bloco `tabelas` da memória."""
    return _CATEGORIA_DA_MEMORIA.get(chave, chave.strip().upper())


def _parametros_vigentes(supabase, operadora_id: str) -> dict[str, Any]:
    versoes = (
        supabase.table("cm_memoria_versao")
        .select("parametros_json")
        .eq("operadora_id", operadora_id)
        .eq("vigente", True)
        .execute()
        .data
        or []
    )
    return (versoes[0].get("parametros_json") or {}) if versoes else {}


def bloco_da_categoria(parametros: dict[str, Any], categoria: str) -> dict[str, Any]:
    """O que a memória diz da tabela da categoria (tipo, regra de preço, chave), ou `{}`."""
    for chave, bloco in (parametros.get("tabelas") or {}).items():
        if isinstance(bloco, dict) and categoria_da_memoria(str(chave)) == categoria:
            return bloco
    return {}


def _regra_de_uso(bloco: dict[str, Any], formato: _Formato) -> dict[str, Any]:
    """A regra de uso da tabela: o bloco da memória inteiro, com a regra de
    preço, a chave de busca e o percentual com sinal (deflator vira negativo)."""
    regra = {k: v for k, v in bloco.items() if k not in _CHAVES_DA_CARGA and v is not None}
    tipo = str(bloco.get("tipo") or "").upper()
    regra["regra_preco"] = str(bloco.get("regra_preco") or ("SIMPRO" if tipo == "SIMPRO" else formato.regra_preco))
    regra["chave"] = bloco.get("chave") or formato.chave
    if bloco.get("deflator_percentual") is not None:
        regra["percentual"] = -bloco["deflator_percentual"]
    regra["formato"] = formato.nome
    return regra


def importar_tabela(
    supabase,
    operadora_id: str,
    categoria: str,
    tabela: TabelaLida,
    *,
    vigencia_inicio: date,
    vigencia_fim: date | None,
    versao: str | None,
    arquivo_nome: str,
    autor_id: str | None,
) -> dict[str, Any]:
    """Grava a tabela lida como uma versão nova da categoria e devolve o resumo.

    Tipo, regra de preço e chave vêm do bloco `tabelas` da memória vigente;
    sem ele, do formato do CSV.
    """
    bloco = bloco_da_categoria(_parametros_vigentes(supabase, operadora_id), categoria)
    versao = versao or (str(bloco["versao"]) if bloco.get("versao") else None)
    gravada = (
        supabase.table("cm_tabela_preco")
        .insert(
            {
                "nome": arquivo_nome,
                "tipo": bloco.get("tipo") or tabela.formato.nome,
                "versao": versao,
                "vigencia_inicio": vigencia_inicio.isoformat(),
                "vigencia_fim": vigencia_fim.isoformat() if vigencia_fim else None,
                "situacao": "CARREGADA",
                "arquivo_nome": arquivo_nome,
                "autor_id": autor_id,
            }
        )
        .execute()
        .data[0]
    )
    itens = [{**item, "tabela_id": gravada["id"]} for item in tabela.itens]
    for inicio in range(0, len(itens), _LOTE):
        supabase.table("cm_tabela_preco_item").insert(itens[inicio : inicio + _LOTE]).execute()
    supabase.table("cm_operadora_tabela").insert(
        {
            "operadora_id": operadora_id,
            "categoria": categoria,
            "tabela_id": gravada["id"],
            "regra_uso_json": _regra_de_uso(bloco, tabela.formato),
        }
    ).execute()
    return {
        "categoria": categoria,
        "formato": tabela.formato.nome,
        "descricao_formato": tabela.formato.descricao,
        "itens": len(itens),
        "versao": versao,
        "vigencia_inicio": vigencia_inicio.isoformat(),
        "vigencia_fim": vigencia_fim.isoformat() if vigencia_fim else None,
    }


def _versao_na_data(supabase, operadora_id: str, categoria: str, data: date) -> dict | None:
    ligacoes = (
        supabase.table("cm_operadora_tabela")
        .select("tabela_id, regra_uso_json")
        .eq("operadora_id", operadora_id)
        .eq("categoria", categoria)
        .execute()
        .data
        or []
    )
    if not ligacoes:
        return None
    tabelas = (
        supabase.table("cm_tabela_preco")
        .select("id, vigencia_inicio, vigencia_fim, criado_em")
        .in_("id", [ligacao["tabela_id"] for ligacao in ligacoes])
        .execute()
        .data
        or []
    )
    vigentes = [
        t
        for t in tabelas
        if t.get("vigencia_inicio")
        and date.fromisoformat(t["vigencia_inicio"]) <= data
        and (not t.get("vigencia_fim") or data <= date.fromisoformat(t["vigencia_fim"]))
    ]
    if not vigentes:
        return None
    # Vigências que se sobrepõem: vale a que começou por último.
    escolhida = max(vigentes, key=lambda t: (t["vigencia_inicio"], t.get("criado_em") or ""))
    regra = next(ligacao["regra_uso_json"] for ligacao in ligacoes if ligacao["tabela_id"] == escolhida["id"])
    return {"id": escolhida["id"], "regra": regra or {}}


def _itens_do_codigo(supabase, tabela_id: str, codigo: str) -> list[dict]:
    for campo in ("codigo", "codigo_alternativo"):
        itens = (
            supabase.table("cm_tabela_preco_item")
            .select("precos_json, extra_json")
            .eq("tabela_id", tabela_id)
            .eq(campo, codigo)
            .execute()
            .data
            or []
        )
        if itens:
            return itens
    return (
        supabase.table("cm_tabela_preco_item")
        .select("precos_json, extra_json")
        .eq("tabela_id", tabela_id)
        .contains("extra_json", {"codigos_tuss": [codigo]})
        .execute()
        .data
        or []
    )


def _validado(parametros: dict[str, Any], codigo: str) -> Decimal | None:
    """O preço que a memória dá como validado para o código (`precos.validados`)."""
    for validado in (parametros.get("precos") or {}).get("validados") or []:
        if not isinstance(validado, dict) or validado.get("valor") is None:
            continue
        if str(validado.get("codigo") or "").strip() == codigo:
            return Decimal(str(validado["valor"]))
    return None


def _valor(precos: dict[str, Any], regra_preco: str, coluna: str | None) -> Decimal | str:
    if regra_preco == "LPM":
        bruto = precos.get("lpm")
    elif regra_preco == "COLUNA":
        bruto = precos.get("valor") if "valor" in precos else precos.get((coluna or "").lower())
    else:
        # PMC, PF, PF_MAIS_PERCENTUAL, SIMPRO: tabela de referência ainda não carregada.
        return NAO_CONFERIDO
    if bruto == PACOTE:
        return PACOTE
    try:
        valor = Decimal(str(bruto))
    except InvalidOperation:
        return NAO_CONFERIDO
    return valor if valor > 0 else NAO_CONFERIDO


def preco(
    supabase,
    operadora_id: str,
    categoria: str,
    codigo: str,
    data: date,
    coluna: str | None = None,
    *,
    cbo: str | None = None,
) -> Decimal | str:
    """O preço do código na tabela da categoria vigente na data, `NAO_CONFERIDO` ou `PACOTE`.

    O preço validado na memória da operadora ganha da tabela.

    `coluna` é a coluna de preço do plano (COMUM, CARIOCA), para a tabela que
    tem duas; `cbo` desempata o código que a tabela repete por especialidade.
    """
    codigo = codigo.strip()
    validado = _validado(_parametros_vigentes(supabase, operadora_id), codigo)
    if validado is not None:
        return validado
    tabela = _versao_na_data(supabase, operadora_id, categoria.strip().upper(), data)
    if tabela is None:
        return NAO_CONFERIDO
    itens = _itens_do_codigo(supabase, tabela["id"], codigo)
    if len(itens) > 1 and cbo:
        itens = [i for i in itens if (i.get("extra_json") or {}).get("cbo") == cbo]
    if len(itens) != 1:
        return NAO_CONFERIDO
    return _valor(itens[0].get("precos_json") or {}, tabela["regra"].get("regra_preco", "COLUNA"), coluna)
