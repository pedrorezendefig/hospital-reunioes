"""Cacoetes de texto gerado que dão para pegar por expressão regular (ADR 0071).

A lista única dos tells mecânicos: o contraste "não é X, é Y" e as variantes
dele, e o fecho de uma linha repetido ao fim de seções consecutivas. O que não
cabe numa regex (tríade, inflação, abertura encenada) fica com o humanizer.

Quem usa: o `tools/lint_manual.py` (reprova o build do Manual). A regra do
ESLint do front (`hospital-reunioes/frontend/eslint-rules/tells.mjs`) tem as
mesmas regexes, e os dois leem os casos do `tools/tells_casos.json` nos testes,
para concordarem. Mudou um padrão aqui, mude lá e acrescente o caso no JSON.

As regexes são escritas para valer igual em Python e em JavaScript: sem `\\b`
(no JS ele não reconhece letra acentuada), com a classe de letras explícita.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass

# Letra, com acento. Fronteira de palavra portátil entre Python e JS.
L = "A-Za-zÀ-ÖØ-öø-ÿ"
COPULA = "(?:é|são|foi|era)"


@dataclass(frozen=True)
class Ocorrencia:
    cacoete: str
    trecho: str
    posicao: int


@dataclass(frozen=True)
class Cacoete:
    nome: str
    achar: Callable[[str], Iterator[tuple[int, str]]]


def _por_regex(padrao: str) -> Callable[[str], Iterator[tuple[int, str]]]:
    rx = re.compile(padrao, re.IGNORECASE)

    def achar(texto: str) -> Iterator[tuple[int, str]]:
        for m in rx.finditer(texto):
            yield m.start(), m.group(0)

    return achar


RE_TITULO = re.compile(r"^ {0,3}#{1,6}\s")
RE_NAO_LETRA = re.compile(f"[^{L}0-9 ]")


def _fechos_repetidos(texto: str) -> Iterator[tuple[int, str]]:
    """Seções seguidas que terminam num parágrafo de uma linha começado igual.

    Fecho é o último parágrafo da seção, quando ele tem uma linha só, começa
    com letra e a seção tem outro parágrafo antes dele. Dois fechos seguidos
    que abrem igual até a primeira pontuação ("Simples assim.", "Pronto, ...")
    são o cacoete; a ocorrência aponta o segundo.
    """
    secoes: list[list[tuple[int, str]]] = [[]]
    pos = 0
    for linha in texto.split("\n"):
        if RE_TITULO.match(linha):
            secoes.append([])
        else:
            secoes[-1].append((pos, linha))
        pos += len(linha) + 1

    anterior: str | None = None
    for secao in secoes:
        paragrafos: list[list[tuple[int, str]]] = []
        novo = True
        for p, linha in secao:
            if not linha.strip():
                novo = True
            elif novo:
                paragrafos.append([(p, linha)])
                novo = False
            else:
                paragrafos[-1].append((p, linha))
        fecho = None
        if len(paragrafos) >= 2 and len(paragrafos[-1]) == 1:
            p, linha = paragrafos[-1][0]
            limpa = linha.strip().strip("*_")
            # Linha com link aponta para outra página ("Tarefas que mudaram:
            # [...]", "Está em [...]"): é a estrutura das Novidades, não fecho.
            if re.match(f"[{L}]", limpa) and "[" not in limpa:
                inicio = re.split(r"[,.:;!?]", limpa, maxsplit=1)[0]
                chave = " ".join(RE_NAO_LETRA.sub(" ", inicio.lower()).split())
                fecho = (p + linha.index(linha.strip()), linha.strip(), chave)
        if fecho and anterior is not None and fecho[2] == anterior:
            yield fecho[0], fecho[1]
        anterior = fecho[2] if fecho else None


CACOETES: list[Cacoete] = [
    Cacoete(
        "nao-e-x-e-y",
        _por_regex(
            f"(?<![{L}])não\\s+{COPULA}\\s[^\\n.!?;:]{{1,80}}?[,;.]\\s+"
            f"(?:(?:mas\\s+)?{COPULA}|(?:mas|e)\\s+sim)(?![{L}])"
        ),
    ),
    Cacoete(
        "nao-so-x-mas-y",
        _por_regex(
            f"(?<![{L}])não\\s+(?:só|apenas|somente)(?![{L}])[^\\n.!?;]{{1,100}}?"
            f"(?<![{L}])(?:mas|como)(?![{L}])"
        ),
    ),
    Cacoete(
        "nao-x-dois-pontos-y",
        # "Não foi possível X: <causa>" e "não pôde ser lido: <o que fazer>"
        # são aviso de falha, não contraste.
        _por_regex(
            f"(?<![{L}])não\\s+(?!foi\\s+possível|pôde|puderam)"
            f"[^\\n.!?;:,]{{1,40}}:\\s+[{L}]"
        ),
    ),
    Cacoete(
        "mais-do-que-x-y",
        # Só no começo da frase: "custa mais do que o previsto" é comparação.
        _por_regex(
            f"(?<![{L}0-9,;:])(?<![{L}0-9,;:]\\s)mais\\s+(?:do\\s+)?que\\s"
            f"[^\\n.!?;:]{{1,80}}?,"
        ),
    ),
    Cacoete(
        "nao-se-trata-de",
        _por_regex(f"(?<![{L}])não\\s+se\\s+trata\\s+de(?![{L}])"),
    ),
    Cacoete("fecho-repetido", _fechos_repetidos),
]


def achar_tells(texto: str) -> list[Ocorrencia]:
    """As ocorrências dos cacoetes da lista no texto, na ordem em que aparecem."""
    achados = [
        Ocorrencia(c.nome, trecho, pos)
        for c in CACOETES
        for pos, trecho in c.achar(texto)
    ]
    return sorted(achados, key=lambda o: (o.posicao, o.cacoete))
