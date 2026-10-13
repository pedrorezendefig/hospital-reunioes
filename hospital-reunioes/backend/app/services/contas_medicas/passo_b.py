"""O passo B de Contas médicas: a conta comparada com a memória (issue #1135, PRD #1128).

A IA recebe a memória inteira da operadora (bloco em cache), os eventos do
prontuário no período da conta com um dia de margem, os itens da conta e os
CÁLCULOS do código (diárias pagas, tetos, coluna de preço e as linhas que as
conferências já geraram) e devolve linhas do Guia, sem valor em reais.

Nenhuma linha da IA chega à faturista sem as conferências do código:

1. a regra citada existe na memória (senão a linha cai e fica registrada);
2. a linha está no período da conta (senão cai e fica registrada);
3. a mesma ação no mesmo código, com o período cruzando o de uma linha que o
   código ou a IA já apontou, é a mesma linha: fica a primeira;
4. regra pendente vira Validar, nunca ordem;
5. o trecho citado está na página ou na vizinha (senão confiança baixa, que a
   tela mostra como "conferir evidência");
6. o código está na tabela da operadora: o preço da tabela dá o valor; fora
   dela, o unitário que a conta já lançou, com a etiqueta; sem nenhum, "não
   conferido". Código nulo tenta o dicionário e a descrição; sem sucesso,
   "sem código";
7. o teto por dia é o do código: diárias pagas do período da linha vezes o teto.

A causa-raiz da IA é sobreposta nos casos óbvios: diária é Regra automática;
regra de preço e item que o MV já bloqueou, Cadastro e preço.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from app.services.contas_medicas import ia
from app.services.contas_medicas.conferencia import (
    BuscaDePreco,
    Conferencia,
    ProntuarioLido,
    _codigos_de_diaria,
)
from app.services.contas_medicas.dicionario import _norm, casar
from app.services.contas_medicas.evidencia import trecho_confere
from app.services.contas_medicas.guia import agrupar_por_dia_e_setor
from app.services.contas_medicas.memoria_texto import gerar_texto_memoria
from app.services.contas_medicas.passo_a import _identificacao, _ler_quando, _texto_da_pagina
from app.services.contas_medicas_conta import Conta
from app.utils.text_sanitizer import sanitizar_estrutura

__all__ = ["LinhasDaIA", "comparar_com_a_ia", "eventos_do_periodo", "juntar"]

CENTAVO = Decimal("0.01")

# Os eventos que vão para a IA: o período da conta e um dia para cada lado.
MARGEM = timedelta(days=1)

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


# As listas datadas do Anexo A: o campo do começo e, na terapia, o do fim.
_LISTAS_COM_DATA = {
    "movimentacoes": ("data_hora", None),
    "terapias": ("inicio", "fim"),
    "prescricoes": ("data", None),
    "procedimentos": ("data_hora", None),
    "cirurgias": ("data", None),
}
_SEM_DATA = ("atendimento", "idade_anos", "documentos_ausentes", "observacoes")


def eventos_do_periodo(eventos: Mapping[str, Any], inicio: date | None, fim: date | None) -> dict[str, Any]:
    """Os eventos que tocam o período da conta com um dia de margem para cada
    lado: a parcial não paga a leitura do atendimento inteiro. A terapia sem
    fim segue em curso; o evento sem data legível vai, por precaução."""
    de = inicio - MARGEM if inicio else None
    ate = fim + MARGEM if fim else None

    def toca(evento: Mapping[str, Any], campo_inicio: str, campo_fim: str | None) -> bool:
        comeco = _dia(evento.get(campo_inicio))
        if comeco is None:
            return True
        termino = comeco
        if campo_fim:
            termino = _dia(evento.get(campo_fim)) or date.max
        return (ate is None or comeco <= ate) and (de is None or termino >= de)

    recorte: dict[str, Any] = {chave: eventos.get(chave) for chave in _SEM_DATA}
    for lista, (campo_inicio, campo_fim) in _LISTAS_COM_DATA.items():
        recorte[lista] = [e for e in eventos.get(lista) or [] if toca(e, campo_inicio, campo_fim)]
    return recorte


def _itens(conta: Conta) -> list[dict[str, Any]]:
    """Os itens lançados, sem o preço: preço é do código, não da IA."""
    return [
        {
            "data": f"{item.data:%d/%m/%Y}",
            "setor": item.setor,
            "grupo": item.grupo,
            "codigo": item.codigo,
            "descricao": item.descricao,
            "quantidade": f"{item.quantidade.normalize():f}",
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


def _devida_no_periodo(teto: Mapping[str, Any], inicio: date, fim: date) -> tuple[Decimal, int]:
    """O teto das diárias pagas e das cirurgias do período da linha, e quantas
    diárias são: duas linhas em períodos que não se cruzam somam o teto da
    conta, nunca o dobro."""
    dias = [devida for dia, devida in teto["por_dia"] if inicio <= dia <= fim]
    cirurgias = sum(1 for dia in teto["cirurgias"] if inicio <= dia <= fim)
    return sum(dias, Decimal(0)) + teto["por_cirurgia"] * cirurgias, len(dias)


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
    # Os códigos de diária da memória e os que o contador deu.
    diarias: frozenset[str]
    # Os códigos que o MV já não deixou lançar (linha marcada Bloqueado).
    bloqueados: frozenset[str]
    texto_da_pagina: Callable[[int], str | None]
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

    def _causa(self, causa: str, regra: Mapping[str, Any], codigo: str | None) -> str:
        """A causa-raiz da IA, menos nos casos óbvios: diária é Regra
        automática; regra de preço e item bloqueado no MV, Cadastro e preço."""
        if codigo in self.diarias or regra.get("secao") == "DIA":
            return "REGRA_AUTOMATICA"
        if codigo in self.bloqueados or regra.get("secao") == "PRC":
            return "CADASTRO_PRECO"
        return causa

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
            devida, diarias = _devida_no_periodo(teto, inicio, fim)
            pagas = "1 diária paga" if diarias == 1 else f"{diarias} diárias pagas"
            motivo += f" Teto pelo código: {devida:g} para {pagas} no período."

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
            "causa_raiz": self._causa(linha.causa_raiz, regra, codigo),
            "confianca": linha.confianca if confere else "BAIXA",
            "origem": "IA",
        }


def _bloqueados(supabase, resposta: ia.LinhasDaComparacao) -> frozenset[str]:
    """Os códigos das linhas da IA que alguma faturista já marcou Bloqueado."""
    codigos = sorted({linha.codigo for linha in resposta.linhas if linha.codigo})
    if not codigos:
        return frozenset()
    marcadas = (
        supabase.table("cm_guia_linha").select("codigo").eq("estado", "BLOQUEADO").in_("codigo", codigos).execute().data
        or []
    )
    return frozenset(linha["codigo"] for linha in marcadas)


def comparar_com_a_ia(
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
        eventos_do_periodo(eventos, conta.periodo_inicio, conta.periodo_fim),
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
        diarias=frozenset(_codigos_de_diaria(memoria["parametros"]))
        | frozenset(diaria["codigo"] for diaria in conferencia.diarias_pagas),
        bloqueados=_bloqueados(supabase, resposta),
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
