"""Leitura do Prontuário por código: o conteúdo (issue #1118, PRD #1113, ADR 0070).

Sobre os documentos que a estrutura monta (`prontuario.ler_prontuario`, #1117),
o código lê o que sustenta cobrança sem passar pela IA: a prescrição, o balanço
hídrico, as glicemias, a internação e a alta, o setor de cada dia com as
transferências, a descrição cirúrgica, a ficha anestésica e a guia TISS.

Entra o mesmo texto por página que a estrutura leu e o Prontuário que ela devolveu;
as páginas de cada documento são lidas pelo número. Função pura: sem banco, sem
rede, sem log (o texto do prontuário nunca vai para log, ADR 0070, decisão 8).
Os campos de texto livre que saem daqui (observação da prescrição, por exemplo)
não estão desidentificados: quem os mandar à IA passa por `desidentificar`.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from app.services.contas_medicas.prescricao import ItemConsolidado, Prescricao, consolidar, ler_itens
from app.services.contas_medicas.prontuario import _RODAPE_GLOBAL, Documento, Prontuario

# ----------------------------------------------------------------------------------
# Balanço hídrico e glicemias
# ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class LinhaDoBalanco:
    item: str
    via: str | None
    # Quantos horários têm valor; o total é o último número da linha (mL nos ganhos).
    lancamentos: int
    total: float


@dataclass(frozen=True)
class Balanco:
    data: date | None
    setor: str | None
    paginas: tuple[int, ...]
    ganhos: tuple[LinhaDoBalanco, ...]
    perdas: tuple[LinhaDoBalanco, ...]
    glicemias: int


@dataclass(frozen=True)
class GlicemiasDoDia:
    """Glicemias de um dia por fonte. A mesma glicemia pode estar na aferição e no
    balanço: somar as duas fontes conta duas vezes, quem confere decide."""

    data: date
    familia: str
    quantidade: int
    paginas: tuple[int, ...]


_VIAS_DO_BALANCO = {"EV", "VO", "SNE", "SNG", "SC", "IM", "GTT", "SOG", "IV"}
_NUMERO = re.compile(r"-?\d+(?:,\d+)?")


def _numero(texto: str) -> float:
    return float(texto.replace(",", "."))


def _ler_balanco(documento: Documento, primeira_pagina: str) -> Balanco:
    """Só a primeira página: a segunda traz os usuários e a assinatura (adendo v1.2, item 6.1).
    A hora de cada valor exige a coluna; aqui saem item, via, lançamentos e total."""
    bloco = None
    ganhos: list[LinhaDoBalanco] = []
    perdas: list[LinhaDoBalanco] = []
    glicemias = 0
    for linha in primeira_pagina.split("\n"):
        texto = linha.strip()
        if texto.startswith("GANHOS"):
            bloco = ganhos
            continue
        if texto.startswith("PERDAS"):
            bloco = perdas
            continue
        if texto.startswith(("SINAIS VITAIS", "Itens de Sinais")):
            bloco = "sinais vitais"
            continue
        if not texto or texto.startswith(("Total", "EVOLUÇÃO")):
            continue
        palavras = texto.split()
        k = len(palavras)
        while k > 0 and _NUMERO.fullmatch(palavras[k - 1]):
            k -= 1
        numeros = palavras[k:]
        if bloco == "sinais vitais":
            if texto.upper().startswith("GLICEMIA"):
                glicemias += len(numeros)
        elif bloco is not None and numeros:
            via = palavras[k - 1] if k > 0 and palavras[k - 1] in _VIAS_DO_BALANCO else None
            item = " ".join(palavras[: k - 1] if via else palavras[:k]).strip(" ,")
            if item:
                bloco.append(LinhaDoBalanco(item, via, len(numeros) - 1, _numero(numeros[-1])))
    return Balanco(
        data=documento.data,
        setor=documento.setor,
        paginas=documento.paginas,
        ganhos=tuple(ganhos),
        perdas=tuple(perdas),
        glicemias=glicemias,
    )


_GLICEMIA_AFERIDA = re.compile(r"^\s*GLICEMIA\b[^\n]*\d", re.M)


def _glicemias(afericoes: list[tuple[Documento, str]], balancos: list[Balanco]) -> tuple[GlicemiasDoDia, ...]:
    por_dia: dict[tuple[date, str], tuple[int, tuple[int, ...]]] = {}
    for documento, texto in afericoes:
        quantas = len(_GLICEMIA_AFERIDA.findall(texto))
        if quantas and documento.data:
            antes, paginas = por_dia.get((documento.data, "AFERICAO"), (0, ()))
            por_dia[documento.data, "AFERICAO"] = (antes + quantas, paginas + documento.paginas)
    for balanco in balancos:
        if balanco.glicemias and balanco.data:
            antes, paginas = por_dia.get((balanco.data, "BALANCO"), (0, ()))
            por_dia[balanco.data, "BALANCO"] = (antes + balanco.glicemias, paginas + balanco.paginas[:1])
    return tuple(
        GlicemiasDoDia(data, familia, quantidade, paginas)
        for (data, familia), (quantidade, paginas) in sorted(por_dia.items())
    )


# ----------------------------------------------------------------------------------
# Leitura
# ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Conteudo:
    prescricoes: tuple[Prescricao, ...]
    prescricao_consolidada: tuple[ItemConsolidado, ...]
    balancos: tuple[Balanco, ...]
    glicemias: tuple[GlicemiasDoDia, ...]


def _paginas(textos: Sequence[str], documento: Documento) -> list[tuple[int, str]]:
    """(número da página no PDF, texto sem o rodapé global) de cada página do documento."""
    return [(n, _RODAPE_GLOBAL.sub("", textos[n - 1])) for n in documento.paginas]


def ler_conteudo(texto_por_pagina: Sequence[str | None], prontuario: Prontuario) -> Conteudo:
    textos = [texto or "" for texto in texto_por_pagina]
    prescricoes: list[Prescricao] = []
    balancos: list[Balanco] = []
    afericoes: list[tuple[Documento, str]] = []
    for d in prontuario.documentos:
        paginas = _paginas(textos, d)
        if d.familia == "PRESCRICAO":
            itens = tuple(ler_itens(paginas))
            prescricoes.append(Prescricao(d.data, d.hora, d.subtipo, d.setor, d.paginas, itens))
        elif d.familia == "BALANCO":
            balancos.append(_ler_balanco(d, paginas[0][1]))
        elif d.familia == "AFERICAO":
            afericoes.append((d, "\n".join(texto for _, texto in paginas)))
    return Conteudo(
        prescricoes=tuple(prescricoes),
        prescricao_consolidada=tuple(consolidar(prescricoes)),
        balancos=tuple(balancos),
        glicemias=_glicemias(afericoes, balancos),
    )
