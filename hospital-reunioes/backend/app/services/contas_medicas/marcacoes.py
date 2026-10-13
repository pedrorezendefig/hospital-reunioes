"""Marcações de caixa e botão no texto do Prontuário (issue #1132, PRD #1128).

Dois passos, os dois função pura e sem log (o texto do prontuário nunca vai para
log, ADR 0070, decisão 8):

1. `inserir_marcacoes`: na extração, cada `[X]` ou `[ ]` que o filho achou entra
   na linha do `pdftotext -layout`, antes da palavra que vem à direita da imagem.
   O texto guardado fica com as duas marcas, para quem precisar da pergunta inteira.
2. `so_o_marcado`: no texto que vai à IA, a linha com marcação fica só com a opção
   à direita de cada `[X]`, e o rótulo da pergunta, quando está na linha de cima e
   termina em dois-pontos, vem junto. Linha sem nada marcado sai.

O `[X]` fica na linha que vai à IA: diz que aquilo foi marcado, e é o que impede o
aprendizado do formulário em branco de tomar a opção escolhida por modelo.

Pendência registrada: a geometria de célula (rótulo na coluna ao lado, tabela de
perguntas) não é lida; só o rótulo na mesma linha ou na de cima.
"""

import re
from collections.abc import Mapping, Sequence

MARCADA = "[X]"
VAZIA = "[ ]"
_MARCAS = (MARCADA, VAZIA)
_SEPARA_MARCAS = re.compile(r"(\[X\]|\[ \])")
# Duas colunas na mesma linha do `-layout` ficam separadas por dois espaços ou mais.
_COLUNA = re.compile(r"\s{2,}")


def _sem_espaco(texto: str) -> str:
    return "".join(texto.split())


def _com_marcas(linha: str, itens: Sequence[str]) -> str:
    """Põe cada marca antes do caractere visível que vem depois dela no PDF."""
    insercoes = []
    antes = 0
    for item in itens:
        if item in _MARCAS:
            insercoes.append((antes, item))
        else:
            antes += len(_sem_espaco(item))
    colunas = [i for i, c in enumerate(linha) if not c.isspace()]
    for antes, marca in reversed(insercoes):
        if antes < len(colunas):
            coluna = colunas[antes]
            linha = f"{linha[:coluna]}{marca} {linha[coluna:]}"
        else:
            linha = f"{linha.rstrip()} {marca}"
    return linha


def inserir_marcacoes(texto: str, linhas_com_marcas: Sequence[Sequence[str]]) -> str:
    """O texto da página com as marcas. A linha do `pdftotext` é achada pelas mesmas
    palavras, sem contar os espaços; linha que não casa fica como veio."""
    linhas = texto.split("\n")
    usadas: set[int] = set()
    inicio = 0
    for itens in linhas_com_marcas:
        chave = _sem_espaco("".join(item for item in itens if item not in _MARCAS))
        if not chave:
            continue
        ordem = [*range(inicio, len(linhas)), *range(inicio)]
        achada = next((i for i in ordem if i not in usadas and _sem_espaco(linhas[i]) == chave), None)
        if achada is None:
            continue
        linhas[achada] = _com_marcas(linhas[achada], itens)
        usadas.add(achada)
        inicio = achada + 1
    return "\n".join(linhas)


def inserir_nas_paginas(textos: Sequence[str], por_pagina: Mapping[int, Sequence[Sequence[str]]]) -> list[str]:
    return [inserir_marcacoes(texto, por_pagina[n]) if n in por_pagina else texto for n, texto in enumerate(textos, 1)]


def _partes(linha: str) -> tuple[str, list[str], list[str]]:
    """(texto antes da primeira marca, opções marcadas, texto de outra coluna que veio
    colado a uma opção)."""
    partes = _SEPARA_MARCAS.split(linha)
    marcadas: list[str] = []
    resto: list[str] = []
    for marca, depois in zip(partes[1::2], partes[2::2], strict=True):
        opcao, *outra_coluna = _COLUNA.split(depois.strip(), maxsplit=1)
        if marca == MARCADA and opcao:
            marcadas.append(opcao)
        resto += [t for t in outra_coluna if t]
    return partes[0].strip(), marcadas, resto


def so_o_marcado(linhas: Sequence[str]) -> list[str]:
    saida: list[str] = []
    rotulo: int | None = None  # posição em `saida` do rótulo que espera as opções
    for linha in linhas:
        if not any(marca in linha for marca in _MARCAS):
            saida.append(linha)
            rotulo = len(saida) - 1 if linha.rstrip().endswith(":") else None
            continue
        prefixo, marcadas, resto = _partes(linha)
        escolhidas = " ".join(f"{MARCADA} {opcao}" for opcao in marcadas)
        if not prefixo and rotulo is not None:
            if escolhidas:
                saida[rotulo] = f"{saida[rotulo]} {escolhidas}"
        elif escolhidas:
            saida.append(f"{prefixo} {escolhidas}".strip())
            rotulo = None
        if resto:
            saida.append("  ".join(resto))
            rotulo = None
    return saida
