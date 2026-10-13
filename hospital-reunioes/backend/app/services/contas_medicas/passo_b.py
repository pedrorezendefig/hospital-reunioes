"""O passo B de Contas médicas: a conta comparada com a memória (issue #1135, PRD #1128).

A IA recebe a memória inteira da operadora (bloco em cache), os eventos do
prontuário no período da conta com um dia de margem, os itens da conta e os
CÁLCULOS do código (diárias pagas, tetos, coluna de preço e as linhas que as
conferências já geraram) e devolve linhas do Guia, sem valor em reais.

Nenhuma linha da IA chega à faturista sem as conferências do código.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from app.services.contas_medicas import ia
from app.services.contas_medicas.conferencia import BuscaDePreco, Conferencia, ProntuarioLido
from app.services.contas_medicas.dicionario import _norm, casar
from app.services.contas_medicas.evidencia import trecho_confere
from app.services.contas_medicas.guia import agrupar_por_dia_e_setor
from app.services.contas_medicas.memoria_texto import gerar_texto_memoria
from app.services.contas_medicas.passo_a import _identificacao, _ler_quando, _texto_da_pagina
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


@dataclass(frozen=True)
class _Periodo:
    acao: str
    codigo: str
    inicio: date
    fim: date

    def mesma_linha(self, outra: _Periodo) -> bool:
        """Mesma ação no mesmo código, com os períodos se cruzando."""
        return (self.acao, self.codigo) == (outra.acao, outra.codigo) and (
            self.inicio <= outra.fim and outra.inicio <= self.fim
        )


def _periodo_da_linha(linha: Mapping[str, Any]) -> _Periodo | None:
    inicio = _dia(linha.get("data"))
    if not linha.get("codigo") or inicio is None:
        return None
    return _Periodo(linha["acao"], linha["codigo"], inicio, _dia(linha.get("data_fim")) or inicio)


@dataclass
class _Conferencias:
    """O que o código confere em cada linha da IA."""

    conta: Conta
    conferencia: Conferencia
    regras: Mapping[str, Mapping[str, Any]]
    preco: BuscaDePreco
    dicionario: Mapping[str, set[str]]
    texto_da_pagina: Any
    apontadas: list[_Periodo]
    descartadas: list[dict[str, Any]]

    def _codigo_pela_descricao(self, descricao: str) -> str | None:
        """O código da linha que a IA deixou sem: o termo do dicionário na
        descrição ou, sem ele, o item da conta de mesma marca. Só um código vale."""
        texto = _norm(descricao)
        codigos = {
            codigo
            for termo, do_termo in self.dicionario.items()
            if termo and re.search(r"(?<![A-Z])" + re.escape(termo) + r"(?![A-Z])", texto)
            for codigo in do_termo
        }
        if not codigos:
            itens = [{"codigo": item.codigo, "descricao": item.descricao} for item in self.conta.itens]
            codigos = {item["codigo"] for item in casar(descricao, itens, {}).itens}
        return next(iter(codigos)) if len(codigos) == 1 else None

    def _unitario_da_conta(self, codigo: str | None) -> Decimal | None:
        return next((i.unitario for i in self.conta.itens if i.codigo == codigo and i.unitario > 0), None)

    def _no_periodo(self, dia: date) -> bool:
        inicio, fim = self.conta.periodo_inicio, self.conta.periodo_fim
        return (inicio is None or inicio <= dia) and (fim is None or dia <= fim)

    def _descartar(self, linha: ia.LinhaDaComparacao, motivo: str) -> None:
        self.descartadas.append({"linha": linha.model_dump(), "motivo": motivo})

    def registro(self, linha: ia.LinhaDaComparacao) -> dict[str, Any] | None:
        """A linha pronta para o Guia, ou None quando ela cai (e fica registrada)."""
        regra = self.regras.get(linha.regra_id)
        if regra is None:
            self._descartar(linha, f"A regra {linha.regra_id} não existe na memória.")
            return None
        inicio = _dia(linha.data)
        fim = _dia(linha.data_fim) or inicio
        if inicio is None or not self._no_periodo(inicio) or not self._no_periodo(fim):
            self._descartar(linha, "Data fora do período da conta.")
            return None
        codigo = linha.codigo or self._codigo_pela_descricao(linha.descricao)
        if codigo:
            periodo = _Periodo(linha.acao, codigo, inicio, fim)
            if any(periodo.mesma_linha(apontada) for apontada in self.apontadas):
                self._descartar(linha, "A mesma linha já está no Guia.")
                return None
            self.apontadas.append(periodo)

        acao, motivo = linha.acao, linha.motivo
        if regra.get("status") != "VIGENTE" and acao != "VALIDAR":
            acao, motivo = "VALIDAR", f"Regra {regra['codigo']} pendente. {motivo}"

        lancada, devida = Decimal(str(linha.quantidade_lancada)), Decimal(str(linha.quantidade_devida))
        teto = next((t for t in self.conferencia.tetos if t["codigo"] == codigo), None)
        if teto is not None and linha.acao != "RETIRAR":
            devida = teto["devida"]
            motivo += f" Teto pelo código: {devida:g} para {teto['diarias_pagas']} diárias pagas."

        # Incluir e Ajustar valem pelo preço da tabela ou, fora dela, pelo
        # unitário que a conta já lançou, com a etiqueta. Retirar tira o que foi
        # lançado, pelo preço lançado. Sem nenhum dos dois, a linha fica sem
        # valor: "não conferido".
        lancado = self._unitario_da_conta(codigo)
        tabela = None
        if linha.acao != "RETIRAR" and codigo:
            tabela = _preco_da_tabela(self.preco, codigo, inicio, self.conferencia.coluna)
        unitario = tabela if tabela is not None else lancado
        if codigo is None:
            motivo += " Sem código."
        elif tabela is None and lancado is not None and linha.acao != "RETIRAR":
            motivo += " Valor pelo preço da conta, não conferido."
        valor = None
        if unitario is not None:
            valor = (unitario * (devida - lancada)).quantize(CENTAVO, rounding=ROUND_HALF_UP)

        confere = trecho_confere(linha.evidencia.trecho, linha.evidencia.pagina, self.texto_da_pagina)
        return {
            "acao": acao,
            "data": inicio.isoformat(),
            "data_fim": fim.isoformat() if fim != inicio else None,
            "setor": linha.setor,
            "codigo": codigo,
            "descricao": linha.descricao,
            "quantidade_lancada": float(lancada),
            "quantidade_devida": float(devida),
            "preco_lancado": _numero(lancado),
            "preco_tabela": _numero(tabela),
            "valor_diferenca": _numero(valor),
            "regra_codigo": regra["codigo"],
            "motivo": motivo,
            "evidencia_pagina": linha.evidencia.pagina,
            "evidencia_trecho": (linha.evidencia.trecho or "")[:300] or None,
            "nivel_evidencia": linha.nivel_evidencia,
            "causa_raiz": linha.causa_raiz,
            "confianca": linha.confianca if confere else "BAIXA",
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
    dicionario: Mapping[str, set[str]],
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
    conferencias = _Conferencias(
        conta=conta,
        conferencia=conferencia,
        regras={regra["codigo"]: regra for regra in memoria["regras"]},
        preco=preco,
        dicionario=dicionario,
        texto_da_pagina=_texto_da_pagina(prontuario, _identificacao(prontuario)),
        apontadas=[p for p in map(_periodo_da_linha, conferencia.linhas) if p is not None],
        descartadas=[],
    )
    linhas = [r for r in map(conferencias.registro, resposta.linhas) if r is not None]
    # O texto que a IA escreveu vai para a tela: sem travessão nem meia-risca.
    return LinhasDaIA(
        linhas=tuple(sanitizar_estrutura(linhas)), descartadas=tuple(sanitizar_estrutura(conferencias.descartadas))
    )


def juntar(do_codigo: Sequence[dict[str, Any]], da_ia: Sequence[dict[str, Any]]) -> tuple[dict[str, Any], ...]:
    """As linhas da IA e as do código num Guia só, por dia e setor, com uma
    ordem só."""
    registros: list[dict[str, Any]] = []
    for grupo in agrupar_por_dia_e_setor([*do_codigo, *da_ia]):
        for registro in grupo["linhas"]:
            registro.pop("nao_conferido", None)
            registros.append({**registro, "ordem": len(registros) + 1})
    return tuple(registros)
