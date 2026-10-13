"""Marcações de caixa e botão no texto do Prontuário (issue #1132, PRD #1128).

Dois passos, os dois função pura e sem log (o texto do prontuário nunca vai para
log, ADR 0070, decisão 8):

1. `inserir_marcacoes`: na extração, cada `[X]` ou `[ ]` que o filho achou entra
   na linha do `pdftotext -layout`, antes da palavra que vem à direita da imagem.
   O texto guardado fica com as duas marcas, para quem precisar da pergunta inteira.
2. `so_o_marcado`: no texto que vai à IA, a linha com marcação fica só com a opção
   à direita de cada `[X]`, e o rótulo da pergunta, quando está na linha logo acima
   e termina em dois-pontos, vem junto. Linha sem nada marcado sai.

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


def _posicoes(itens: Sequence[str], comeco: int) -> list[tuple[int, str]]:
    """(caractere visível da linha antes do qual a marca entra, marca), com a linha
    começando em `comeco` caracteres visíveis antes do primeiro item."""
    posicoes = []
    antes = comeco
    for item in itens:
        if item in _MARCAS:
            posicoes.append((antes, item))
        else:
            antes += len(_sem_espaco(item))
    return posicoes


def _com_marcas(linha: str, posicoes: Sequence[tuple[int, str]]) -> str:
    """Põe cada marca antes do caractere visível que vem depois dela no PDF."""
    colunas = [i for i, c in enumerate(linha) if not c.isspace()]
    # Do fim para o começo; duas marcas antes do mesmo caractere ficam na ordem do PDF.
    for _, (antes, marca) in sorted(enumerate(posicoes), key=lambda par: (par[1][0], par[0]), reverse=True):
        if antes < len(colunas):
            coluna = colunas[antes]
            linha = f"{linha[:coluna]}{marca} {linha[coluna:]}"
        else:
            linha = f"{linha.rstrip()} {marca}"
    return linha


def _trecho_livre(limpa: str, chave: str, usados: Sequence[tuple[int, int]]) -> int | None:
    comeco = limpa.find(chave)
    while comeco >= 0:
        fim = comeco + len(chave)
        if all(fim <= de or comeco >= ate for de, ate in usados):
            return comeco
        comeco = limpa.find(chave, comeco + 1)
    return None


def inserir_marcacoes(texto: str, linhas_com_marcas: Sequence[Sequence[str]]) -> str:
    """O texto da página com as marcas. A linha do `pdftotext` é achada pelas mesmas
    palavras, sem contar os espaços, inteiras ou como trecho dela: no MV o rótulo
    fica uns pontos acima das opções ("Espontânea: sem O2" e "com O2"), o
    `pdfplumber` dá duas linhas e o `pdftotext` uma. A busca segue a ordem da
    página, a partir da última linha achada, e um trecho já usado não casa de novo;
    linha que não casa fica como veio."""
    linhas = texto.split("\n")
    limpas = [_sem_espaco(linha) for linha in linhas]
    usados: dict[int, list[tuple[int, int]]] = {}
    posicoes: dict[int, list[tuple[int, str]]] = {}
    inicio = 0
    for itens in linhas_com_marcas:
        chave = _sem_espaco("".join(item for item in itens if item not in _MARCAS))
        if not chave:
            continue
        for i in [*range(inicio, len(linhas)), *range(inicio)]:
            comeco = _trecho_livre(limpas[i], chave, usados.get(i, []))
            if comeco is not None:
                usados.setdefault(i, []).append((comeco, comeco + len(chave)))
                posicoes.setdefault(i, []).extend(_posicoes(itens, comeco))
                inicio = i
                break
    for i, da_linha in posicoes.items():
        linhas[i] = _com_marcas(linhas[i], da_linha)
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
        if resto:
            saida.append("  ".join(resto))
        # O rótulo leva só as opções da linha logo abaixo. No MV o rótulo de várias
        # perguntas vem depois das opções ("SEDAÇÃO", "Via aérea artificial:"): a
        # resposta da pergunta seguinte ia parar no rótulo da anterior.
        rotulo = None
    return saida
