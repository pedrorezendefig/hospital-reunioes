"""O passo B de Contas médicas: a conta comparada com a memória (issue #1135, PRD #1128).

A IA recebe a memória inteira da operadora (bloco em cache), os eventos do
prontuário no período da conta com um dia de margem, os itens da conta e os
CÁLCULOS do código (diárias pagas, tetos, coluna de preço e as linhas que as
conferências já geraram) e devolve linhas do Guia, sem valor em reais.

Nenhuma linha da IA chega à faturista sem as conferências do código.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from app.services.contas_medicas import ia
from app.services.contas_medicas.conferencia import BuscaDePreco, Conferencia, ProntuarioLido
from app.services.contas_medicas.guia import agrupar_por_dia_e_setor
from app.services.contas_medicas.memoria_texto import gerar_texto_memoria
from app.services.contas_medicas.passo_a import _ler_quando
from app.services.contas_medicas_conta import Conta
from app.utils.text_sanitizer import sanitizar_estrutura

__all__ = ["LinhasDaIA", "comparar", "juntar"]

CENTAVO = Decimal("0.01")

# As categorias da tabela em que o código da linha da IA é procurado. A linha
# não diz o grupo da conta, e o mesmo código não está em duas tabelas.
_CATEGORIAS = ("MATERIAL", "MEDICAMENTO", "DIARIA_TAXA", "PACOTE")


@dataclass(frozen=True)
class LinhasDaIA:
    # Prontas para `cm_guia_linha`, com origem IA.
    linhas: tuple[dict[str, Any], ...]
    # A linha que caiu e o porquê.
    descartadas: tuple[dict[str, Any], ...]


def _dia(texto: str | None) -> date | None:
    quando = _ler_quando(texto)
    return quando[0] if quando else None


def _numero(valor: Decimal | None) -> float | None:
    return float(valor) if valor is not None else None


def _itens(conta: Conta) -> list[dict[str, Any]]:
    """Os itens lançados, sem o preço: preço é do código, não da IA."""
    return [
        {
            "data": f"{item.data:%d/%m/%Y}",
            "setor": item.setor,
            "grupo": item.grupo,
            "codigo": item.codigo,
            "descricao": item.descricao,
            "quantidade": f"{item.quantidade:g}",
            "unidade": item.unidade,
        }
        for item in conta.itens
    ]


def _calculos(conferencia: Conferencia) -> dict[str, Any]:
    diarias: dict[str, list[str]] = {}
    for diaria in conferencia.diarias_pagas:
        if diaria["do_paciente"]:
            diarias.setdefault(diaria["setor"] or "sem setor", []).append(diaria["data"])
    return {
        "coluna_de_preco": conferencia.coluna,
        "diarias_pagas": diarias,
        "tetos": [
            {"item": teto["item"], "codigo": teto["codigo"], "devida": f"{teto['devida']:g}"}
            for teto in conferencia.tetos
        ],
        "linhas_do_codigo": [
            {chave: linha.get(chave) for chave in ("acao", "codigo", "descricao", "data", "data_fim")}
            for linha in conferencia.linhas
        ],
    }


def _preco_da_tabela(preco: BuscaDePreco, codigo: str, data: date, coluna: str | None) -> Decimal | None:
    for categoria in _CATEGORIAS:
        achado = preco(categoria, codigo, data, coluna)
        if isinstance(achado, Decimal):
            return achado
    return None


def _registro(linha: ia.LinhaDaComparacao, conferencia: Conferencia, preco: BuscaDePreco) -> dict[str, Any]:
    inicio = _dia(linha.data)
    fim = _dia(linha.data_fim) or inicio
    lancada, devida = Decimal(str(linha.quantidade_lancada)), Decimal(str(linha.quantidade_devida))
    tabela = _preco_da_tabela(preco, linha.codigo, inicio, conferencia.coluna) if linha.codigo else None
    valor = (tabela * (devida - lancada)).quantize(CENTAVO, rounding=ROUND_HALF_UP) if tabela is not None else None
    return {
        "acao": linha.acao,
        "data": inicio.isoformat() if inicio else None,
        "data_fim": fim.isoformat() if fim and fim != inicio else None,
        "setor": linha.setor,
        "codigo": linha.codigo,
        "descricao": linha.descricao,
        "quantidade_lancada": float(lancada),
        "quantidade_devida": float(devida),
        "preco_lancado": None,
        "preco_tabela": _numero(tabela),
        "valor_diferenca": _numero(valor),
        "regra_codigo": linha.regra_id,
        "motivo": linha.motivo,
        "evidencia_pagina": linha.evidencia.pagina,
        "evidencia_trecho": (linha.evidencia.trecho or "")[:300] or None,
        "nivel_evidencia": linha.nivel_evidencia,
        "causa_raiz": linha.causa_raiz,
        "confianca": linha.confianca,
        "origem": "IA",
    }


def comparar(
    supabase,
    *,
    conta_id: str,
    atendimento_id: str,
    operadora_id: str,
    memoria: Mapping[str, Any],
    conta: Conta,
    prontuario: ProntuarioLido,
    eventos: Mapping[str, Any],
    conferencia: Conferencia,
    preco: BuscaDePreco,
) -> LinhasDaIA:
    """A chamada do Passo B e as conferências do código sobre cada linha.
    `memoria` é a vigente, como `memoria_vigente` lê."""
    resposta = ia.comparar_conta(
        gerar_texto_memoria(supabase, operadora_id, memoria["memoria_versao_id"]),
        eventos,
        _itens(conta),
        _calculos(conferencia),
        supabase=supabase,
        conta_id=conta_id,
        atendimento_id=atendimento_id,
    )
    linhas = [_registro(linha, conferencia, preco) for linha in resposta.linhas]
    return LinhasDaIA(linhas=tuple(sanitizar_estrutura(linhas)), descartadas=())


def juntar(do_codigo: Sequence[dict[str, Any]], da_ia: Sequence[dict[str, Any]]) -> tuple[dict[str, Any], ...]:
    """As linhas da IA e as do código num Guia só, por dia e setor, com uma
    ordem só."""
    registros: list[dict[str, Any]] = []
    for grupo in agrupar_por_dia_e_setor([*do_codigo, *da_ia]):
        for registro in grupo["linhas"]:
            registro.pop("nao_conferido", None)
            registros.append({**registro, "ordem": len(registros) + 1})
    return tuple(registros)
