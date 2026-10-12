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

import math
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from app.services.contas_medicas.cirurgia import DescricaoCirurgica
from app.services.contas_medicas.conteudo import Conteudo, Movimentacao
from app.services.contas_medicas.diarias import ParametrosDiaria, Segmento, contar_diarias, diarias_do_periodo
from app.services.contas_medicas.dicionario import _generico, _marca, _norm, casar
from app.services.contas_medicas.guia import NotaDeEntrada, agrupar_por_dia_e_setor, nota_de_entrada
from app.services.contas_medicas.memoria import MemoriaLida
from app.services.contas_medicas.prescricao import ItemPrescrito, Prescricao
from app.services.contas_medicas.prontuario import Prontuario
from app.services.contas_medicas.tabelas import NAO_CONFERIDO, PACOTE, Pacote
from app.services.contas_medicas_conta import Conta, ItemConta, coluna_do_plano

__all__ = ["BuscaDePacote", "BuscaDePreco", "Conferencia", "Pacote", "ProntuarioLido", "conferir"]

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


# A busca do pacote pelo TUSS na tabela de pacotes da operadora: (TUSS, data).
BuscaDePacote = Callable[[str, date], Pacote | None]


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


def _reais(valor: Decimal) -> str:
    """O valor como a faturista lê: R$ 1.234,56."""
    return "R$ " + f"{valor:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


@dataclass(frozen=True)
class _Contexto:
    conta: Conta
    prontuario: ProntuarioLido
    parametros: Mapping[str, Any]
    preco: BuscaDePreco
    coluna: str | None
    dicionario: Mapping[str, set[str]]
    # Nome do setor no MV, normalizado → acomodação (`cm_setor`).
    setores: Mapping[str, str]
    # IDs das regras que a memória tem.
    regras: frozenset[str]

    def tem_regra(self, chave: str) -> bool:
        return (self.parametros.get("regras_das_conferencias") or {}).get(chave) in self.regras

    def acomodacao_do_setor(self, setor: str | None) -> str | None:
        return self.setores.get(_norm(setor))

    def no_centro_cirurgico(self, setor: str | None) -> bool:
        return self.acomodacao_do_setor(setor) == "CENTRO_CIRURGICO" or "CIRURG" in _norm(setor)

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

    @property
    def diaria_global(self) -> bool:
        return bool(self.parametros.get("diaria_global"))

    def cobravel(self, categoria: str, codigo: str, data: date) -> bool | None:
        """Material ou medicamento cobrado à parte? Com diária global (Unimed, Leve),
        só o que tem preço contratual a partir do corte (`precos.corte_valor_unitario`):
        o resto entra na conta sem cobrança, de propósito. `None`: sem preço para
        saber se passa do corte."""
        if not self.diaria_global:
            return True
        corte = (self.parametros.get("precos") or {}).get("corte_valor_unitario")
        if corte is None:
            return False
        tabela = self.preco(categoria, codigo, data, self.coluna)
        if isinstance(tabela, Decimal):
            return tabela >= Decimal(str(corte))
        return None if tabela == NAO_CONFERIDO else False

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
    return f"{item.data:%d/%m/%Y} {item.codigo} {item.descricao}: {item.quantidade:g} x {_reais(item.unitario)}"


# ----------------------------------------------------------------------------------
# (1) Preço
# ----------------------------------------------------------------------------------


_OPOSTA = {"COMUM": "CARIOCA", "CARIOCA": "COMUM"}

# Contraprova da coluna (spec, 9.5, passo 2): a partir desta parte dos materiais
# batendo com a coluna oposta, o plano é que está em dúvida, não os preços.
_CONTRAPROVA = Decimal("0.8")


def _bate(a: Decimal, b: Decimal | str) -> bool:
    return isinstance(b, Decimal) and abs(a - b) <= TOLERANCIA


def _precos(ctx: _Contexto) -> list[_Linha]:
    """Unitário lançado contra a tabela da categoria, na coluna do plano.

    Item com unitário zero entra na conta sem cobrança de propósito (honorário da
    equipe, item incluso em diária ou pacote) e não é conferido.
    """
    oposta = _OPOSTA.get(ctx.coluna or "")
    precos = []
    for item in ctx.conta.itens:
        categoria = _CATEGORIA_DO_GRUPO.get(item.grupo or "")
        if categoria is None or item.unitario == 0:
            continue
        if categoria in {"MATERIAL", "MEDICAMENTO"} and ctx.cobravel(categoria, item.codigo, item.data) is not True:
            # Com diária global, só o item cobrável tem o preço conferido (LEVE-PRI-07).
            continue
        tabela = ctx.preco(categoria, item.codigo, item.data, ctx.coluna)
        outra = ctx.preco(categoria, item.codigo, item.data, oposta) if oposta else NAO_CONFERIDO
        precos.append((item, categoria, tabela, outra))

    # Só material com as duas colunas diferentes diz de que coluna é o preço lançado.
    materiais = [
        (item, outra)
        for item, categoria, tabela, outra in precos
        if categoria == "MATERIAL" and isinstance(tabela, Decimal) and isinstance(outra, Decimal) and tabela != outra
    ]
    na_oposta = sum(1 for item, outra in materiais if _bate(item.unitario, outra))
    contraprova = bool(materiais) and Decimal(na_oposta) / len(materiais) >= _CONTRAPROVA
    linhas = []
    if contraprova:
        linhas.append(
            _Linha(
                acao="VALIDAR",
                chave="coluna_do_plano",
                data=None,
                setor=None,
                codigo=None,
                descricao="Coluna de preço do plano",
                motivo=(
                    f"Plano e preços apontam colunas diferentes: o plano {ctx.conta.plano} usa a coluna "
                    f"{ctx.coluna}, e {na_oposta} de {len(materiais)} materiais batem com a coluna {oposta}. "
                    "Nenhuma correção de preço por coluna até decidir."
                ),
                nivel="POR_REGRA",
                causa="CADASTRO_PRECO",
                pagina=materiais[0][0].pagina,
                trecho=f"Plano: {ctx.conta.plano}",
            )
        )

    for item, _categoria, tabela, outra in precos:
        if not isinstance(tabela, Decimal) or _bate(item.unitario, tabela):
            continue
        if contraprova and isinstance(outra, Decimal) and outra != tabela:
            # Com o plano em dúvida, nada de correção em massa pela coluna.
            continue
        coluna_errada = f" Lançado no preço da coluna {oposta}: coluna errada." if _bate(item.unitario, outra) else ""
        linhas.append(
            _Linha(
                acao="CORRIGIR_PRECO",
                chave="preco",
                data=item.data,
                setor=item.setor,
                codigo=item.codigo,
                descricao=item.descricao,
                motivo=(
                    f"Lançado a {_reais(item.unitario)}, tabela {_reais(tabela)}"
                    + (f" na coluna {ctx.coluna}." if ctx.coluna else ".")
                    + coluna_errada
                ),
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
# (2) Diárias
# ----------------------------------------------------------------------------------

_SAIDAS = frozenset({"ALTA", "OBITO", "TRANSFERENCIA_HOSPITAL"})

_NOME_DA_ACOMODACAO = {
    "CTI": "CTI",
    "ENFERMARIA": "enfermaria",
    "APARTAMENTO": "apartamento",
    "ISOLAMENTO": "isolamento",
    "HOSPITAL_DIA": "hospital-dia",
    "PEDIATRIA": "pediatria",
    "UTI_PEDIATRICA": "UTI pediátrica",
    "UTI_NEONATAL": "UTI neonatal",
}


@dataclass(frozen=True)
class _Devida:
    """Uma diária (ou taxa diária) que a conta deve ter, num dia."""

    data: date
    codigo: str
    # Códigos que valem pela mesma diária na comparação (as classes de UTI).
    familia: frozenset[str]
    chave: str
    descricao: str
    observacao: str
    setor: str | None
    pagina: int | None
    trecho: str
    # A do setor (CTI, ISOLAMENTO...), mesmo quando o código é o da contratada: é a do teto.
    acomodacao: str
    # Diária do paciente (as que contam para o teto), não de acompanhante nem taxa.
    do_paciente: bool = True


def _codigo_configurado(parametros: Mapping[str, Any], nome: str) -> str | None:
    """O código pelo nome da acomodação: na `diaria_global` (Unimed, Leve) ou em
    `diaria.codigos` (a operadora de diária por acomodação, como a ASSIM)."""
    bloco = (parametros.get("diaria_global") or {}).get(nome)
    if isinstance(bloco, dict) and bloco.get("codigo"):
        return str(bloco["codigo"])
    codigo = ((parametros.get("diaria") or {}).get("codigos") or {}).get(nome)
    return str(codigo) if codigo else None


def _codigos_de_diaria(parametros: Mapping[str, Any]) -> set[str]:
    """Todo código de diária que a memória conhece, para achar o que foi lançado."""
    codigos = {
        str(bloco["codigo"])
        for bloco in (parametros.get("diaria_global") or {}).values()
        if isinstance(bloco, dict) and bloco.get("codigo")
    }
    return codigos | {str(c) for c in ((parametros.get("diaria") or {}).get("codigos") or {}).values() if c}


def _contratada(conta: Conta) -> str | None:
    """A acomodação contratada pelo cabeçalho da conta: é a cobrada (ASSIM-DIA-11)."""
    acomodacao = _norm(conta.acomodacao)
    if "APART" in acomodacao:
        return "apartamento"
    if "ENF" in acomodacao:
        return "enfermaria"
    return None


def _evidencia_do_segmento(ctx: _Contexto, segmento: Segmento) -> tuple[int | None, str]:
    documento = next(
        (
            d
            for d in ctx.prontuario.estrutura.documentos
            if d.setor == segmento.setor and d.data == segmento.inicio.date()
        ),
        None,
    )
    return (
        documento.pagina_inicial if documento else None,
        f"Setor {segmento.setor}: de {segmento.inicio:%d/%m/%Y %H:%M} a {segmento.fim:%d/%m/%Y %H:%M}",
    )


def _segmentos(ctx: _Contexto) -> list[Segmento] | str:
    """Os segmentos do contador no período da conta, ou o motivo de não contar."""
    movimentacoes = list(ctx.prontuario.conteudo.movimentacoes)
    if not movimentacoes:
        return []
    if movimentacoes[-1].tipo not in _SAIDAS:
        if ctx.conta.periodo_fim is None:
            return []
        # Segue internado: a parcial fecha no fim do período, com a diária em curso.
        fim = datetime.combine(ctx.conta.periodo_fim + timedelta(days=1), time.min)
        ultima = movimentacoes[-1]
        movimentacoes.append(Movimentacao("EM_CURSO", max(fim, ultima.data_hora), ultima.setor))
    try:
        segmentos = contar_diarias(
            movimentacoes, ParametrosDiaria.da_memoria(ctx.parametros), ctx.prontuario.estrutura.idade_anos
        )
    except ValueError as erro:
        return str(erro)
    inicio, fim = ctx.conta.periodo_inicio, ctx.conta.periodo_fim
    return diarias_do_periodo(segmentos, inicio, fim) if inicio and fim else segmentos


def _devidas_do_segmento(ctx: _Contexto, segmento: Segmento, acomodacao: str) -> tuple[list[_Devida] | None, list[str]]:
    """As diárias devidas do segmento e as pendências (texto) que viram Validar.
    Devidas `None`: o segmento não foi contado (a memória não traz o código)."""
    pagina, trecho = _evidencia_do_segmento(ctx, segmento)
    global_ = ctx.parametros.get("diaria_global") or {}
    contratada = _contratada(ctx.conta)
    pendencias = [p.texto for p in segmento.validar]

    def devida(data: date, codigo: str, chave: str, descricao: str, observacao: str = "", familia=None) -> _Devida:
        return _Devida(
            data=data,
            codigo=codigo,
            familia=frozenset(familia or {codigo}),
            chave=chave,
            descricao=descricao,
            observacao=observacao,
            setor=segmento.setor,
            pagina=pagina,
            trecho=trecho,
            acomodacao=acomodacao,
            do_paciente=chave not in {"acompanhante", "taxa_isolamento"},
        )

    dias = [d.inicio.date() for d in segmento.diarias]
    chave, observacao, familia = "diaria", "", None
    # A acomodação cobrada é a contratada, mesmo que o MV mostre outra (ASSIM-DIA-11).
    cobrada = acomodacao.lower()
    if acomodacao == "HOSPITAL_DIA" and dias:
        # Pernoitou: troca para a diária da acomodação contratada (LEVE-DIA-16).
        chave, observacao, cobrada = "hospital_dia_pernoite", " Conferir pernoite.", contratada or "contratada"
    elif acomodacao == "HOSPITAL_DIA":
        # Sem vencimento no hospital-dia: é uma diária de hospital-dia, não pendência.
        pendencias = [p.texto for p in segmento.validar if p.motivo != "SEM_VENCIMENTO"]
        dias = [segmento.inicio.date()] if ctx.no_periodo(segmento.inicio.date()) else []
        if not _codigo_configurado(ctx.parametros, cobrada) and contratada:
            cobrada = f"hospital_dia_{contratada}"
    elif acomodacao == "CTI":
        classes = sorted(nome for nome in global_ if nome.startswith("uti_adulto_classe"))
        if classes:
            # Classe do dia é do Passo B (PRD 2): sai a mais baixa, para conferir.
            familia = {c for c in (_codigo_configurado(ctx.parametros, n) for n in classes) if c}
            cobrada, observacao = classes[0], " Conferir classe de UTI."
    elif acomodacao in {"ENFERMARIA", "APARTAMENTO", "ISOLAMENTO"} and contratada:
        cobrada = contratada
    codigo = _codigo_configurado(ctx.parametros, cobrada)

    nome = _NOME_DA_ACOMODACAO.get(cobrada.upper(), cobrada.replace("_", " "))
    descricao = f"Diária de {nome}"
    if dias and codigo is None:
        pendencias.append(f"A memória não traz o código da diária de {nome}.")
        return None, pendencias
    devidas = [devida(data, codigo, chave, descricao, observacao, familia) for data in dias if codigo]

    acompanhante = _codigo_configurado(ctx.parametros, "acompanhante")
    if segmento.acompanhante and acompanhante:
        devidas += [devida(data, acompanhante, "acompanhante", "Diária de acompanhante") for data in dias]
    taxa = _codigo_configurado(ctx.parametros, "taxa_isolamento_dia")
    if acomodacao == "ISOLAMENTO" and taxa:
        devidas += [devida(data, taxa, "taxa_isolamento", "Taxa de isolamento") for data in dias]
    return devidas, pendencias


def _diarias(ctx: _Contexto, pacote: Pacote | None) -> tuple[list[_Linha], list[_Devida]]:
    """Diárias devidas (contador) contra lançadas: Incluir ou Retirar a diferença.

    A comparação é por código no período; com a mesma quantidade, o lançamento em
    data diferente não gera linha (a IA e a faturista veem a data). Com pacote pelo
    TUSS, as primeiras diárias do paciente estão no pacote e só as excedentes são
    cobradas. Devolve também as devidas, que são as diárias pagas do teto por dia.

    Retirar só sai com a contagem completa: sem movimentação, com setor sem
    acomodação ou sem o código na memória, a diária lançada não foi conferida.
    """
    segmentos = _segmentos(ctx)
    if isinstance(segmentos, str):
        return [_validar_diaria(f"Diárias não contadas: {segmentos}", None, None)], []
    completa = bool(segmentos)
    devidas: list[_Devida] = []
    linhas: list[_Linha] = []
    for segmento in segmentos:
        acomodacao = ctx.acomodacao_do_setor(segmento.setor)
        if acomodacao is None:
            pendencias = [f"Setor {segmento.setor} sem acomodação cadastrada: diárias não conferidas."]
            devidas_do_segmento: list[_Devida] | None = None
        elif acomodacao == "CENTRO_CIRURGICO":
            continue
        else:
            devidas_do_segmento, pendencias = _devidas_do_segmento(ctx, segmento, acomodacao)
        if devidas_do_segmento is None:
            completa = False
        devidas += devidas_do_segmento or []
        if segmento.diarias or acomodacao is not None:
            linhas += [_validar_diaria(texto, segmento.inicio.date(), segmento.setor) for texto in pendencias]

    cobradas = _excedentes(devidas, pacote) if pacote else devidas
    familias: dict[frozenset[str], list[_Devida]] = {}
    for d in cobradas:
        familias.setdefault(d.familia, []).append(d)
    if completa:
        conhecidos = set().union(*familias) if familias else set()
        for codigo in _codigos_de_diaria(ctx.parametros) - conhecidos:
            familias[frozenset({codigo})] = []
    for familia, devidas_da_familia in familias.items():
        lancados = [i for i in ctx.conta.itens if i.codigo in familia]
        linhas += _comparar_diarias(ctx, devidas_da_familia, lancados, retirar=completa)
    return linhas, devidas


def _excedentes(devidas: list[_Devida], pacote: Pacote) -> list[_Devida]:
    """As diárias do paciente além da permanência do pacote (LEVE-PAC-04)."""
    do_paciente = [d for d in devidas if d.do_paciente]
    no_pacote = {id(d) for d in do_paciente[: pacote.permanencia]}
    return [
        replace(d, chave="pacote_pelo_tuss", observacao=f" Excedente do pacote {pacote.codigo}.")
        if d.do_paciente
        else d
        for d in devidas
        if id(d) not in no_pacote
    ]


def _validar_diaria(texto: str, data: date | None, setor: str | None) -> _Linha:
    return _Linha(
        acao="VALIDAR",
        chave="diaria",
        data=data,
        setor=setor,
        codigo=None,
        descricao="Diária",
        motivo=texto,
        nivel="POR_REGRA",
        causa="REGRA_AUTOMATICA",
        pagina=None,
        trecho=None,
    )


def _comparar_diarias(
    ctx: _Contexto, devidas: list[_Devida], lancados: list[ItemConta], *, retirar: bool = True
) -> list[_Linha]:
    lancada = sum((i.quantidade for i in lancados), Decimal(0))
    diferenca = len(devidas) - lancada
    if diferenca == 0 or (diferenca < 0 and not retirar):
        return []
    por_data_devida: dict[date, int] = {}
    for d in devidas:
        por_data_devida[d.data] = por_data_devida.get(d.data, 0) + 1
    por_data_lancada: dict[date, Decimal] = {}
    for i in lancados:
        por_data_lancada[i.data] = por_data_lancada.get(i.data, Decimal(0)) + i.quantidade
    resumo = f"{len(devidas)} devidas e {lancada:g} lançadas no período."
    linhas = []
    if diferenca > 0:
        faltam = diferenca
        for d in devidas:
            if faltam <= 0:
                break
            if por_data_lancada.get(d.data, Decimal(0)) > 0:
                por_data_lancada[d.data] -= 1
                continue
            preco_lancado, preco_tabela, valor, etiqueta = ctx.valor_de_inclusao(
                "DIARIA_TAXA", d.codigo, d.data, Decimal(1)
            )
            linhas.append(
                _Linha(
                    acao="INCLUIR",
                    chave=d.chave,
                    data=d.data,
                    setor=d.setor,
                    codigo=d.codigo,
                    descricao=d.descricao,
                    motivo=f"{d.descricao}: {resumo}{d.observacao}{etiqueta}",
                    nivel="POR_REGRA",
                    causa="REGRA_AUTOMATICA",
                    pagina=d.pagina,
                    trecho=d.trecho,
                    quantidade_lancada=Decimal(0),
                    quantidade_devida=Decimal(1),
                    preco_lancado=preco_lancado,
                    preco_tabela=preco_tabela,
                    valor=valor,
                )
            )
            faltam -= 1
        return linhas
    sobram = -diferenca
    chave = devidas[0].chave if devidas else "diaria"
    for item in sorted(lancados, key=lambda i: i.data, reverse=True):
        excesso = min(item.quantidade, sobram, max(Decimal(0), item.quantidade - por_data_devida.get(item.data, 0)))
        por_data_devida[item.data] = max(0, por_data_devida.get(item.data, 0) - int(item.quantidade))
        if excesso <= 0:
            continue
        linhas.append(
            _Linha(
                acao="RETIRAR",
                chave=chave,
                data=item.data,
                setor=item.setor,
                codigo=item.codigo,
                descricao=item.descricao,
                motivo=f"Lançado a mais: {resumo}",
                nivel="POR_REGRA",
                causa="REGRA_AUTOMATICA",
                pagina=item.pagina,
                trecho=_trecho_do_item(item),
                quantidade_lancada=excesso,
                quantidade_devida=Decimal(0),
                preco_lancado=item.unitario,
                valor=-_dinheiro(item.unitario * excesso),
            )
        )
        sobram -= excesso
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
            cobravel = ctx.cobravel("MEDICAMENTO", lancado.codigo, data)
            if cobravel is False:
                continue
            quantidade = Decimal(doses or 1)
            preco_lancado, preco_tabela, valor, etiqueta = ctx.valor_de_inclusao(
                "MEDICAMENTO", lancado.codigo, data, quantidade
            )
            if cobravel is None:
                etiqueta += " Sem preço conferível na tabela: conferir se passa do corte."
            achado = _prescrito_no_dia(conteudo, consolidado.nome, data)
            linhas.append(
                _Linha(
                    acao="INCLUIR" if cobravel else "VALIDAR",
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
# (4) Lançado sem registro
# ----------------------------------------------------------------------------------

# Soluções de diluição e hidratação: vêm como componente ou hidratação, com outro nome.
_SOLUCOES = re.compile(r"^(AGUA PARA INJECAO|AGUA DESTILADA|CLORETO DE SODIO|RINGER|GLICOSE|SORO)")


def _termos_do_item(item: ItemConta, dicionario: Mapping[str, set[str]]) -> set[str]:
    """Os nomes pelos quais o prontuário pode citar o item: marca, genérico e dicionário."""
    termos = {_marca(item.descricao)}
    termos |= {parte.strip() for parte in re.split(r"[+/,]", _generico(item.descricao) or "")}
    termos |= {termo for termo, codigos in dicionario.items() if item.codigo in codigos}
    return {termo for termo in termos if len(termo) >= 4}


def _sem_registro(ctx: _Contexto) -> list[_Linha]:
    """Medicamento da conta sem menção no prontuário inteiro: Validar, sugestão retirar.
    Só com impressão completa: na parcial, a ausência não prova nada."""
    if not (ctx.prontuario.estrutura.tipo_impressao or "").upper().startswith("COMPLETA"):
        return []
    texto = _norm("\n".join(ctx.prontuario.texto_por_pagina))
    linhas = []
    for item in ctx.conta.itens:
        if item.grupo != "MEDICAMENTOS" or _SOLUCOES.match(_norm(item.descricao)):
            continue
        # Item incluso na diária global entra sem cobrança: nunca vira retirar.
        if not ctx.cobravel("MEDICAMENTO", item.codigo, item.data):
            continue
        termos = _termos_do_item(item, ctx.dicionario)
        # Marca curta sem genérico (AAS, KCL): sem termo, o texto não foi procurado.
        if not termos:
            continue
        if any(re.search(r"(?<![A-Z])" + re.escape(termo) + r"(?![A-Z])", texto) for termo in termos):
            continue
        linhas.append(
            _Linha(
                acao="VALIDAR",
                chave="sem_registro",
                data=item.data,
                setor=item.setor,
                codigo=item.codigo,
                descricao=item.descricao,
                motivo="Lançado sem nenhuma menção no prontuário (marca, genérico ou dicionário). Sugestão: retirar.",
                nivel="POR_REGRA",
                causa="REGISTRO_ASSISTENCIAL",
                pagina=item.pagina,
                trecho=_trecho_do_item(item),
                quantidade_lancada=item.quantidade,
                quantidade_devida=Decimal(0),
                preco_lancado=item.unitario,
                valor=-item.total,
                confianca="MEDIA",
            )
        )
    return linhas


# ----------------------------------------------------------------------------------
# (5) Ficha anestésica × conta
# ----------------------------------------------------------------------------------


def _codigo_no_dicionario(nome: str, dicionario: Mapping[str, set[str]]) -> str | None:
    codigos = dicionario.get(_norm(nome)) or set()
    return min(codigos) if len(codigos) == 1 else None


def _ficha_x_conta(ctx: _Contexto) -> list[_Linha]:
    """Medicamento da ficha sem item no centro cirúrgico: Incluir. Lançado menor que
    a ficha: Validar (a unidade da conta pode ser mL, e a ficha conta ampolas)."""
    no_centro_cirurgico = [m for m in ctx.medicamentos if ctx.no_centro_cirurgico(m["item"].setor)]
    setor = no_centro_cirurgico[0]["item"].setor if no_centro_cirurgico else None
    linhas = []
    for ficha in ctx.prontuario.conteudo.fichas_anestesicas:
        for medicamento in ficha.medicamentos:
            casamento = casar(medicamento.nome, no_centro_cirurgico, ctx.dicionario)
            quantidade = Decimal(medicamento.quantidade)
            trecho = (
                f"{medicamento.nome} {medicamento.quantidade}"
                if medicamento.anotado
                else f"[ {medicamento.quantidade} ] {medicamento.nome}"
            )
            comum = {
                "chave": "ficha_anestesica",
                "data": ficha.data,
                "setor": setor,
                "nivel": "REGISTRADO",
                "causa": "DISPENSACAO",
                "pagina": ficha.paginas[0],
                "trecho": trecho,
                "quantidade_devida": quantidade,
            }
            if not casamento.itens:
                codigo = _codigo_no_dicionario(medicamento.nome, ctx.dicionario)
                data = ficha.data or ctx.conta.periodo_inicio
                if codigo and data:
                    cobravel = ctx.cobravel("MEDICAMENTO", codigo, data)
                else:
                    cobravel = None if ctx.diaria_global else True
                if cobravel is False:
                    continue
                preco_lancado, preco_tabela, valor, etiqueta = (
                    ctx.valor_de_inclusao("MEDICAMENTO", codigo, data, quantidade) if data else (None, None, None, "")
                )
                if cobravel is None:
                    etiqueta += " Sem preço conferível na tabela: conferir se passa do corte."
                linhas.append(
                    _Linha(
                        acao="INCLUIR" if cobravel else "VALIDAR",
                        codigo=codigo,
                        descricao=medicamento.nome,
                        motivo=f"Registrado na ficha anestésica ({medicamento.quantidade}), sem lançamento no centro "
                        f"cirúrgico.{etiqueta}",
                        quantidade_lancada=Decimal(0),
                        preco_lancado=preco_lancado,
                        preco_tabela=preco_tabela,
                        valor=valor,
                        **comum,
                    )
                )
                continue
            itens = [par["item"] for par in casamento.itens]
            lancada = sum((i.quantidade for i in itens), Decimal(0))
            if lancada < quantidade and not any(i.unidade.upper().startswith("ML") for i in itens):
                linhas.append(
                    _Linha(
                        acao="VALIDAR",
                        codigo=itens[0].codigo,
                        descricao=itens[0].descricao,
                        motivo=f"Ficha anestésica registra {medicamento.quantidade}, lançado {lancada:g}.",
                        quantidade_lancada=lancada,
                        preco_lancado=itens[0].unitario,
                        confianca=casamento.confianca or "ALTA",
                        **comum,
                    )
                )
    return linhas


# ----------------------------------------------------------------------------------
# (6) Gás do centro cirúrgico
# ----------------------------------------------------------------------------------


def _gases(ctx: _Contexto) -> list[_Linha]:
    """Oxigênio da ficha anestésica: vazão arredondada para a faixa da tabela e horas
    para cima. O código de cada faixa vem da memória (`gases_centro_cirurgico`)."""
    faixas = {
        Decimal(str(vazao)): codigo for vazao, codigo in (ctx.parametros.get("gases_centro_cirurgico") or {}).items()
    }
    codigos_de_oxigenio = {codigo for codigo in faixas.values() if codigo}
    lancados = [
        i
        for i in ctx.conta.itens
        if i.grupo == "GASES MEDICINAIS" and i.codigo in codigos_de_oxigenio and ctx.no_centro_cirurgico(i.setor)
    ]
    linhas = []
    for ficha in ctx.prontuario.conteudo.fichas_anestesicas:
        for gas in ficha.gases:
            vazao = Decimal(str(gas.litros_por_minuto))
            faixa = next((f for f in sorted(faixas) if f >= vazao), None)
            esperado = faixas.get(faixa) if faixa is not None else None
            if gas.gas != "O2" or not esperado or not lancados:
                continue
            horas = Decimal(math.ceil(gas.minutos / 60))
            lancada = sum((i.quantidade for i in lancados), Decimal(0))
            if all(i.codigo == esperado for i in lancados) and lancada == horas:
                continue
            data = ficha.data or lancados[0].data
            tabela = ctx.preco("DIARIA_TAXA", esperado, data, ctx.coluna)
            total = sum((i.total for i in lancados), Decimal(0))
            linhas.append(
                _Linha(
                    acao="AJUSTAR_QUANTIDADE",
                    chave="gas",
                    data=data,
                    setor=lancados[0].setor,
                    codigo=esperado,
                    descricao=f"Oxigênio {faixa:g} L/min no centro cirúrgico, por hora",
                    motivo=(
                        f"Ficha anestésica: O2 {vazao:g} L/min por {gas.minutos} min. Lançado "
                        + ", ".join(f"{i.codigo} x {i.quantidade:g}" for i in lancados)
                        + f"; devido {esperado} x {horas} h."
                    ),
                    nivel="REGISTRADO",
                    causa="LANCAMENTO_MANUAL",
                    pagina=ficha.paginas[0],
                    trecho=f"O2 {vazao:g}L/min: {gas.minutos} min",
                    quantidade_lancada=lancada,
                    quantidade_devida=horas,
                    preco_lancado=lancados[0].unitario,
                    preco_tabela=tabela if isinstance(tabela, Decimal) else None,
                    valor=_dinheiro(tabela * horas - total) if isinstance(tabela, Decimal) else None,
                )
            )
    return linhas


# ----------------------------------------------------------------------------------
# (7) Procedimento do cabeçalho × descrição cirúrgica
# ----------------------------------------------------------------------------------


def _procedimento_do_cabecalho(ctx: _Contexto) -> list[_Linha]:
    """Código do cabeçalho fora da descrição cirúrgica: Validar, porque muda pacote,
    porte da taxa de sala e autorização. O cabeçalho não é lançamento (ASSIM-PRI-12)."""
    codigo = ctx.conta.procedimento_codigo
    linhas = []
    for descricao in ctx.prontuario.conteudo.descricoes_cirurgicas:
        if not codigo or not descricao.procedimentos or codigo in {p.codigo for p in descricao.procedimentos}:
            continue
        registrados = "; ".join(f"{p.codigo} {p.descricao}" for p in descricao.procedimentos)
        linhas.append(
            _Linha(
                acao="VALIDAR",
                chave="procedimento_do_cabecalho",
                data=descricao.inicio.date() if descricao.inicio else None,
                setor=None,
                codigo=codigo,
                descricao=ctx.conta.procedimento_descricao,
                motivo=(
                    f"Procedimento do cabeçalho fora da descrição cirúrgica, que registra "
                    f"{len(descricao.procedimentos)} procedimentos: {registrados}. "
                    "Define pacote, porte da taxa de sala e autorização."
                ),
                nivel="REGISTRADO",
                causa="LANCAMENTO_MANUAL",
                pagina=descricao.paginas[0],
                trecho=registrados,
            )
        )
    return linhas


# ----------------------------------------------------------------------------------
# Pacote pelo TUSS realizado
# ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class _PacoteDoAtendimento:
    pacote: Pacote
    tuss: str
    procedimento: str
    descricao: DescricaoCirurgica


def _pacote_do_atendimento(ctx: _Contexto, pacote_do_tuss: BuscaDePacote | None) -> _PacoteDoAtendimento | None:
    """O pacote do TUSS que a descrição cirúrgica registra, quando a memória da
    operadora tem a regra (LEVE-PAC-03). Na ASSIM só é pacote com o código de pacote
    lançado (ASSIM-PRI-12): a memória dela não traz a regra e nada muda."""
    if pacote_do_tuss is None or not ctx.tem_regra("pacote_pelo_tuss"):
        return None
    for descricao in ctx.prontuario.conteudo.descricoes_cirurgicas:
        data = descricao.inicio.date() if descricao.inicio else ctx.conta.periodo_inicio
        for procedimento in descricao.procedimentos:
            pacote = pacote_do_tuss(procedimento.codigo, data) if data else None
            if pacote:
                return _PacoteDoAtendimento(pacote, procedimento.codigo, procedimento.descricao, descricao)
    return None


def _pacote_pelo_tuss(ctx: _Contexto, achado: _PacoteDoAtendimento | None) -> list[_Linha]:
    """TUSS realizado com pacote e o pacote fora da conta: Incluir o pacote."""
    if achado is None or achado.pacote.codigo in {i.codigo for i in ctx.conta.itens}:
        return []
    pacote, descricao = achado.pacote, achado.descricao
    data = descricao.inicio.date() if descricao.inicio else ctx.conta.periodo_inicio
    if pacote.valor is not None:
        preco_lancado, preco_tabela, valor, etiqueta = None, pacote.valor, pacote.valor, ""
    else:
        preco_lancado, preco_tabela, valor, etiqueta = ctx.valor_de_inclusao("PACOTE", pacote.codigo, data, Decimal(1))
    return [
        _Linha(
            acao="INCLUIR",
            chave="pacote_pelo_tuss",
            data=data,
            setor=None,
            codigo=pacote.codigo,
            descricao=pacote.descricao,
            motivo=(
                f"A descrição cirúrgica registra o TUSS {achado.tuss}, que tem pacote na tabela "
                f"({pacote.permanencia} diárias incluídas).{etiqueta}"
            ),
            nivel="REGISTRADO",
            causa="LANCAMENTO_MANUAL",
            pagina=descricao.paginas[0],
            trecho=f"{achado.tuss} {achado.procedimento}",
            quantidade_lancada=Decimal(0),
            quantidade_devida=Decimal(1),
            preco_lancado=preco_lancado,
            preco_tabela=preco_tabela,
            valor=valor,
        )
    ]


# ----------------------------------------------------------------------------------
# (8) Teto por dia
# ----------------------------------------------------------------------------------

# Acomodação que a memória pode juntar sob `internacao` no teto (fralda: CTI e internação).
_INTERNACAO = frozenset({"ENFERMARIA", "APARTAMENTO", "ISOLAMENTO", "PEDIATRIA", "HOSPITAL_DIA"})


def _teto_do_dia(teto: Mapping[str, Any], acomodacao: str) -> Decimal | None:
    for chave in (acomodacao.lower(), "internacao" if acomodacao in _INTERNACAO else None, "por_dia"):
        if chave and teto.get(chave) is not None:
            return Decimal(str(teto[chave]))
    return None


def _tetos(ctx: _Contexto, pagas: list[_Devida]) -> list[_Linha]:
    """Consumível com teto (`tetos_por_dia`): devida = diárias pagas × teto diário,
    sem proporção por horário. Lançado acima do teto: Ajustar quantidade. Abaixo, a
    condição de uso (acamado, curativo, sonda) é do Passo B, não do código."""
    do_paciente = [d for d in pagas if d.do_paciente]
    if not do_paciente:
        return []
    cirurgias = len(ctx.prontuario.conteudo.descricoes_cirurgicas)
    linhas = []
    for nome, teto in (ctx.parametros.get("tetos_por_dia") or {}).items():
        if not isinstance(teto, dict) or not teto.get("codigo"):
            continue
        lancados = [i for i in ctx.conta.itens if i.codigo == str(teto["codigo"])]
        por_dia = [_teto_do_dia(teto, d.acomodacao) for d in do_paciente]
        if not lancados or any(valor is None for valor in por_dia):
            # Diária em acomodação sem teto na memória: não dá para dizer o máximo.
            continue
        devida = sum(por_dia, Decimal(0)) + Decimal(str(teto.get("centro_cirurgico_por_cirurgia") or 0)) * cirurgias
        lancada = sum((i.quantidade for i in lancados), Decimal(0))
        if lancada <= devida:
            continue
        datas = sorted({d.data for d in do_paciente})
        item = lancados[0]
        linhas.append(
            _Linha(
                acao="VALIDAR" if str(teto.get("situacao") or "").upper() == "PENDENTE" else "AJUSTAR_QUANTIDADE",
                chave="teto",
                data=datas[0],
                data_fim=datas[-1] if datas[-1] != datas[0] else None,
                setor=do_paciente[0].setor,
                codigo=item.codigo,
                descricao=item.descricao,
                motivo=f"Teto por dia ({nome}): {devida:g} para {len(do_paciente)} diárias pagas; lançado {lancada:g}.",
                nivel="POR_REGRA",
                causa="LANCAMENTO_MANUAL",
                pagina=item.pagina,
                trecho=_trecho_do_item(item),
                quantidade_lancada=lancada,
                quantidade_devida=devida,
                preco_lancado=item.unitario,
                valor=-_dinheiro((lancada - devida) * item.unitario),
            )
        )
    return linhas


# ----------------------------------------------------------------------------------
# Regra citada, período e montagem
# ----------------------------------------------------------------------------------


def _no_periodo(ctx: _Contexto, linhas: list[_Linha], descartadas: list[dict[str, Any]]) -> list[_Linha]:
    """Linha com data fora do período da conta cai: é de outra parcial."""
    dentro = []
    for linha in linhas:
        if linha.data is None or ctx.no_periodo(linha.data):
            dentro.append(linha)
        else:
            descartadas.append({"linha": _registro(linha), "motivo": "Data fora do período da conta."})
    return dentro


def _sem_duplicadas(linhas: list[_Linha]) -> list[_Linha]:
    """Mesma ação, código e período: fica a primeira, na ordem das conferências."""
    vistas: set[tuple] = set()
    unicas = []
    for linha in linhas:
        chave = (linha.acao, linha.codigo, linha.data, linha.data_fim)
        if linha.codigo is not None and chave in vistas:
            continue
        vistas.add(chave)
        unicas.append(linha)
    return unicas


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


def _com_regra(linhas: list[_Linha], memoria: MemoriaLida, descartadas: list[dict[str, Any]]) -> list[_Linha]:
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
        if regra.status != "VIGENTE" and linha.acao != "VALIDAR":
            linha = replace(linha, acao="VALIDAR", motivo=f"Regra {regra.codigo} pendente. {linha.motivo}")
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
    setores: Mapping[str, str] | None = None,
    dicionario: Mapping[str, set[str]] | None = None,
    pacote_do_tuss: BuscaDePacote | None = None,
) -> Conferencia:
    """As linhas do Guia da Conta, pelas conferências por código.

    `setores` liga o nome do setor no MV à acomodação (`cm_setor`); `dicionario` é
    o dicionário de itens do hospital (`dicionario_do_banco`); `pacote_do_tuss`
    acha o pacote da tabela da operadora pelo TUSS realizado.
    """
    ctx = _Contexto(
        conta=conta,
        prontuario=prontuario,
        parametros=memoria.parametros,
        preco=preco,
        coluna=_coluna(conta, memoria.parametros),
        dicionario=dicionario or {},
        setores={_norm(nome): acomodacao for nome, acomodacao in (setores or {}).items()},
        regras=frozenset(regra.codigo for regra in memoria.regras),
    )
    descartadas: list[dict[str, Any]] = []
    pacote = _pacote_do_atendimento(ctx, pacote_do_tuss)
    diarias, pagas = _diarias(ctx, pacote.pacote if pacote else None)
    geradas = [
        *_precos(ctx),
        *diarias,
        *_prescricao_x_conta(ctx),
        *_sem_registro(ctx),
        *_ficha_x_conta(ctx),
        *_gases(ctx),
        *_procedimento_do_cabecalho(ctx),
        *_pacote_pelo_tuss(ctx, pacote),
        *_tetos(ctx, pagas),
    ]
    linhas = _com_regra(geradas, memoria, descartadas)
    linhas = _diario(_sem_duplicadas(_no_periodo(ctx, linhas, descartadas)))
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
