"""Conferências por código e montagem do Guia (issue #1122, PRD #1113, ADR 0070).

`conferir` é uma função pura: recebe a Conta lida, o Prontuário lido (estrutura,
conteúdo e o texto das páginas), a Memória vigente e a busca de preço, e devolve
as linhas do Guia prontas para gravar em `cm_guia_linha`, as descartadas com o
motivo e a nota de entrada. Sem banco, sem rota, sem log: o texto do prontuário
nunca vai para log (ADR 0070, decisão 8).

As conferências seguem a spec do diretor (v1.0, itens 9.3 a 9.8, e adendo v1.3,
item 6). Toda linha cita a regra da memória que a sustenta. O ID da regra é de
cada operadora (a prescrição plena é ASSIM-PRI-07 e LEVE-PRI-02), por isso a
conferência usa uma chave fixa (`preco`, `diaria`, `prescricao`...) e a memória
diz, no bloco `regras_das_conferencias` do cabeçalho, qual regra é de cada chave.
Chave sem regra, ou regra que não existe na memória: a linha é descartada e
registrada. Regra pendente: a linha sai Validar, nunca ordem.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from app.services.contas_medicas.conteudo import Conteudo
from app.services.contas_medicas.dicionario import casar
from app.services.contas_medicas.guia import NotaDeEntrada, agrupar_por_dia_e_setor, nota_de_entrada
from app.services.contas_medicas.memoria import MemoriaLida
from app.services.contas_medicas.prescricao import ItemPrescrito, Prescricao
from app.services.contas_medicas.prontuario import Prontuario
from app.services.contas_medicas.tabelas import NAO_CONFERIDO, PACOTE
from app.services.contas_medicas_conta import Conta, ItemConta, coluna_do_plano

__all__ = ["BuscaDePreco", "Conferencia", "ProntuarioLido", "conferir"]

CENTAVO = Decimal("0.01")
TOLERANCIA = Decimal("0.01")

# A busca de preço de `tabelas.preco` sem o banco: (categoria, código, data, coluna)
# devolve o preço, `NAO_CONFERIDO` ou `PACOTE`.
BuscaDePreco = Callable[[str, str, date, str | None], Decimal | str]

# Grupo da conta do MV → categoria da tabela de preço. Grupo fora daqui não tem
# preço conferido nesta fatia (exame, OPME, hemoderivado, dieta).
_CATEGORIA_DO_GRUPO = {
    "MATERIAIS DESCARTAVEIS": "MATERIAL",
    "MEDICAMENTOS": "MEDICAMENTO",
    "DIARIAS": "DIARIA_TAXA",
    "TAXAS": "DIARIA_TAXA",
    "GASES MEDICINAIS": "DIARIA_TAXA",
    "PACOTES ESPECIAIS": "PACOTE",
    "HONORARIOS MEDICOS": "HONORARIO",
}


@dataclass(frozen=True)
class ProntuarioLido:
    """O que a leitura do prontuário entrega: a estrutura (#1117), o conteúdo
    (#1118) e o texto de cada página, para procurar a menção a um item."""

    estrutura: Prontuario
    conteudo: Conteudo
    texto_por_pagina: Sequence[str]


@dataclass(frozen=True)
class Conferencia:
    # Prontas para `cm_guia_linha`: datas em ISO, números em float, na ordem do Guia.
    linhas: tuple[dict[str, Any], ...]
    # A linha que caiu e o porquê (regra que a memória não tem, fora do período).
    descartadas: tuple[dict[str, Any], ...]
    nota: NotaDeEntrada


@dataclass(frozen=True)
class _Linha:
    acao: str
    # Chave da regra em `regras_das_conferencias`.
    chave: str
    data: date | None
    setor: str | None
    codigo: str | None
    descricao: str | None
    motivo: str
    nivel: str
    causa: str
    pagina: int | None
    trecho: str | None
    quantidade_lancada: Decimal | None = None
    quantidade_devida: Decimal | None = None
    preco_lancado: Decimal | None = None
    preco_tabela: Decimal | None = None
    valor: Decimal | None = None
    data_fim: date | None = None
    confianca: str = "ALTA"
    regra: str | None = None


def _dinheiro(valor: Decimal) -> Decimal:
    return valor.quantize(CENTAVO, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class _Contexto:
    conta: Conta
    prontuario: ProntuarioLido
    parametros: Mapping[str, Any]
    preco: BuscaDePreco
    coluna: str | None
    dicionario: Mapping[str, set[str]]

    def no_periodo(self, data: date) -> bool:
        inicio, fim = self.conta.periodo_inicio, self.conta.periodo_fim
        return (inicio is None or inicio <= data) and (fim is None or data <= fim)

    @property
    def medicamentos(self) -> list[dict[str, Any]]:
        """Os medicamentos da conta no formato do casamento do dicionário."""
        return [
            {"codigo": i.codigo, "descricao": i.descricao, "item": i}
            for i in self.conta.itens
            if i.grupo == "MEDICAMENTOS"
        ]

    def unitario_da_conta(self, codigo: str) -> Decimal | None:
        return next((i.unitario for i in self.conta.itens if i.codigo == codigo and i.unitario > 0), None)

    def valor_de_inclusao(
        self, categoria: str, codigo: str | None, data: date, quantidade: Decimal
    ) -> tuple[Decimal | None, Decimal | None, Decimal | None, str]:
        """(preço lançado, preço de tabela, valor, etiqueta) de uma linha Incluir.

        Sem preço em tabela, vale o unitário que a conta já lançou para o mesmo
        código, com a etiqueta; sem ele, a linha fica sem valor (spec, 9.5, passo 10).
        """
        tabela = self.preco(categoria, codigo, data, self.coluna) if codigo else NAO_CONFERIDO
        if isinstance(tabela, Decimal):
            return None, tabela, _dinheiro(tabela * quantidade), ""
        unitario = self.unitario_da_conta(codigo) if codigo and tabela != PACOTE else None
        if unitario is None:
            return None, None, None, ""
        return unitario, None, _dinheiro(unitario * quantidade), " Valor pelo preço da conta, não conferido."


def _coluna(conta: Conta, parametros: Mapping[str, Any]) -> str | None:
    colunas = parametros.get("colunas_de_preco") or {}
    if colunas.get("CARIOCA"):
        return coluna_do_plano(conta.plano, colunas["CARIOCA"])
    return colunas.get("padrao")


def _trecho_do_item(item: ItemConta) -> str:
    return f"{item.data:%d/%m/%Y} {item.codigo} {item.descricao} {item.quantidade} x {item.unitario}"


# ----------------------------------------------------------------------------------
# (1) Preço
# ----------------------------------------------------------------------------------


def _precos(ctx: _Contexto) -> list[_Linha]:
    linhas = []
    for item in ctx.conta.itens:
        categoria = _CATEGORIA_DO_GRUPO.get(item.grupo or "")
        if categoria is None or item.unitario == 0:
            continue
        tabela = ctx.preco(categoria, item.codigo, item.data, ctx.coluna)
        if not isinstance(tabela, Decimal) or abs(item.unitario - tabela) <= TOLERANCIA:
            continue
        linhas.append(
            _Linha(
                acao="CORRIGIR_PRECO",
                chave="preco",
                data=item.data,
                setor=item.setor,
                codigo=item.codigo,
                descricao=item.descricao,
                motivo=f"Lançado a {item.unitario}, tabela {tabela} na coluna {ctx.coluna}.",
                nivel="POR_REGRA",
                causa="CADASTRO_PRECO",
                pagina=item.pagina,
                trecho=_trecho_do_item(item),
                quantidade_lancada=item.quantidade,
                quantidade_devida=item.quantidade,
                preco_lancado=item.unitario,
                preco_tabela=tabela,
                valor=_dinheiro((tabela - item.unitario) * item.quantidade),
            )
        )
    return linhas


# ----------------------------------------------------------------------------------
# (3) Prescrição × conta
# ----------------------------------------------------------------------------------


def _prescrito_no_dia(conteudo: Conteudo, nome: str, data: date) -> tuple[Prescricao, ItemPrescrito] | None:
    for prescricao in conteudo.prescricoes:
        if prescricao.data == data:
            for item in prescricao.itens:
                if item.nome == nome and not item.suspenso:
                    return prescricao, item
    return None


def _prescricao_x_conta(ctx: _Contexto) -> list[_Linha]:
    """Item já cobrado na conta, prescrito em dia do período sem lançamento naquele
    dia: Incluir as doses do dia. "Se necessário" é da fatia do PRESCRITO_SN (#1134)."""
    conteudo = ctx.prontuario.conteudo
    linhas = []
    for consolidado in conteudo.prescricao_consolidada:
        if consolidado.se_necessario or not (consolidado.secao or "").upper().startswith("MEDICAMENTO"):
            continue
        casamento = casar(consolidado.nome, ctx.medicamentos, ctx.dicionario)
        if not casamento.itens:
            continue
        lancado = casamento.itens[0]["item"]
        dias_lancados = {par["item"].data for par in casamento.itens}
        for data, doses in sorted(consolidado.doses_por_dia.items()):
            if data in dias_lancados or not ctx.no_periodo(data):
                continue
            quantidade = Decimal(doses or 1)
            preco_lancado, preco_tabela, valor, etiqueta = ctx.valor_de_inclusao(
                "MEDICAMENTO", lancado.codigo, data, quantidade
            )
            achado = _prescrito_no_dia(conteudo, consolidado.nome, data)
            linhas.append(
                _Linha(
                    acao="INCLUIR",
                    chave="prescricao",
                    data=data,
                    setor=achado[0].setor if achado else lancado.setor,
                    codigo=lancado.codigo,
                    descricao=lancado.descricao,
                    motivo=f"Prescrito ({consolidado.nome}) e sem lançamento no dia.{etiqueta}",
                    nivel="PRESCRITO",
                    causa="DISPENSACAO",
                    pagina=achado[1].pagina if achado else consolidado.paginas[0],
                    trecho=f"{achado[1].nome} {achado[1].colunas}" if achado else consolidado.nome,
                    quantidade_lancada=Decimal(0),
                    quantidade_devida=quantidade,
                    preco_lancado=preco_lancado,
                    preco_tabela=preco_tabela,
                    valor=valor,
                    confianca=casamento.confianca or "ALTA",
                )
            )
    return linhas


# ----------------------------------------------------------------------------------
# Regra citada, período e montagem
# ----------------------------------------------------------------------------------


def _soma(a: Decimal | None, b: Decimal | None) -> Decimal | None:
    return None if a is None or b is None else a + b


def _diario(linhas: list[_Linha]) -> list[_Linha]:
    """Item diário repetido vira uma linha com data e data fim: dias seguidos da
    mesma ação, regra, código e setor somam quantidade e valor."""
    unidas: list[_Linha] = []
    for linha in sorted(linhas, key=lambda x: (x.acao, x.chave, x.codigo or "", x.setor or "", x.data or date.min)):
        anterior = unidas[-1] if unidas else None
        if (
            anterior is not None
            and linha.data is not None
            and anterior.data is not None
            and (anterior.acao, anterior.chave, anterior.codigo, anterior.setor)
            == (linha.acao, linha.chave, linha.codigo, linha.setor)
            and linha.codigo is not None
            and (anterior.data_fim or anterior.data) + timedelta(days=1) == linha.data
        ):
            unidas[-1] = replace(
                anterior,
                data_fim=linha.data_fim or linha.data,
                quantidade_lancada=_soma(anterior.quantidade_lancada, linha.quantidade_lancada),
                quantidade_devida=_soma(anterior.quantidade_devida, linha.quantidade_devida),
                valor=_soma(anterior.valor, linha.valor),
            )
            continue
        unidas.append(linha)
    return unidas


def _com_regra(
    linhas: list[_Linha], memoria: MemoriaLida, descartadas: list[dict[str, Any]]
) -> list[_Linha]:
    """A regra de cada linha pela chave; sem regra, descarta; pendente, Validar."""
    ids = memoria.parametros.get("regras_das_conferencias") or {}
    regras = {regra.codigo: regra for regra in memoria.regras}
    validas = []
    for linha in linhas:
        codigo = ids.get(linha.chave)
        regra = regras.get(codigo) if codigo else None
        if regra is None:
            motivo = (
                f"A regra {codigo} não existe na memória."
                if codigo
                else f"A memória não diz a regra da conferência {linha.chave} (regras_das_conferencias)."
            )
            descartadas.append({"linha": _registro(linha), "motivo": motivo})
            continue
        validas.append(replace(linha, regra=regra.codigo))
    return validas


def _numero(valor: Decimal | None) -> float | None:
    return float(valor) if valor is not None else None


def _registro(linha: _Linha) -> dict[str, Any]:
    return {
        "acao": linha.acao,
        "data": linha.data.isoformat() if linha.data else None,
        "data_fim": linha.data_fim.isoformat() if linha.data_fim else None,
        "setor": linha.setor,
        "codigo": linha.codigo,
        "descricao": linha.descricao,
        "quantidade_lancada": _numero(linha.quantidade_lancada),
        "quantidade_devida": _numero(linha.quantidade_devida),
        "preco_lancado": _numero(linha.preco_lancado),
        "preco_tabela": _numero(linha.preco_tabela),
        "valor_diferenca": _numero(linha.valor),
        "regra_codigo": linha.regra,
        "motivo": linha.motivo,
        "evidencia_pagina": linha.pagina,
        "evidencia_trecho": (linha.trecho or "")[:300] or None,
        "nivel_evidencia": linha.nivel,
        "causa_raiz": linha.causa,
        "confianca": linha.confianca,
        "origem": "CODIGO",
    }


def conferir(
    conta: Conta,
    prontuario: ProntuarioLido,
    memoria: MemoriaLida,
    preco: BuscaDePreco,
    *,
    dicionario: Mapping[str, set[str]] | None = None,
) -> Conferencia:
    """As linhas do Guia da Conta, pelas conferências por código.

    `dicionario` é o dicionário de itens do hospital (`dicionario_do_banco`).
    """
    ctx = _Contexto(
        conta=conta,
        prontuario=prontuario,
        parametros=memoria.parametros,
        preco=preco,
        coluna=_coluna(conta, memoria.parametros),
        dicionario=dicionario or {},
    )
    descartadas: list[dict[str, Any]] = []
    geradas = [*_precos(ctx), *_prescricao_x_conta(ctx)]
    linhas = _diario(_com_regra(geradas, memoria, descartadas))
    registros = []
    for grupo in agrupar_por_dia_e_setor(_registro(linha) for linha in linhas):
        for registro in grupo["linhas"]:
            registro.pop("nao_conferido", None)
            registros.append({**registro, "ordem": len(registros) + 1})
    return Conferencia(
        linhas=tuple(registros),
        descartadas=tuple(descartadas),
        nota=nota_de_entrada(registros, conta.total),
    )
