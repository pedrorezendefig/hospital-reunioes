"""A conferência da evidência que a IA cita (issue #1131, PRD #1128, spec 9.6).

O trecho que a IA copia do prontuário tem de existir na página citada ou na
vizinha. A comparação é sem acento, sem espaço e sem caixa, e aceita 85% de
semelhança: a IA erra uma letra, junta duas linhas, troca um acento. Serve ao
passo A (cada evento) e ao passo B (cada linha do Guia).
"""

from __future__ import annotations

import unicodedata
from collections.abc import Callable
from difflib import SequenceMatcher

__all__ = ["SEMELHANCA_MINIMA", "normalizar", "trecho_confere"]

SEMELHANCA_MINIMA = 0.85


def normalizar(texto: str) -> str:
    """Sem acento, sem espaço nenhum e sem caixa."""
    sem_acento = "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")
    return "".join(sem_acento.split()).casefold()


def _parecido(trecho: str, pagina: str) -> bool:
    """Algum pedaço da página, do tamanho do trecho, tem 85% de semelhança com
    ele. Os candidatos são os pedaços alinhados a cada bloco em comum entre os
    dois; a conta rápida descarta o pedaço que não chegaria lá."""
    if trecho in pagina:
        return True
    if len(pagina) <= len(trecho):
        return SequenceMatcher(None, trecho, pagina, autojunk=False).ratio() >= SEMELHANCA_MINIMA
    vistos = set()
    for i, j, tamanho in SequenceMatcher(None, trecho, pagina, autojunk=False).get_matching_blocks():
        inicio = max(0, min(j - i, len(pagina) - len(trecho)))
        if not tamanho or inicio in vistos:
            continue
        vistos.add(inicio)
        comparacao = SequenceMatcher(None, trecho, pagina[inicio : inicio + len(trecho)], autojunk=False)
        if comparacao.quick_ratio() >= SEMELHANCA_MINIMA and comparacao.ratio() >= SEMELHANCA_MINIMA:
            return True
    return False


def trecho_confere(trecho: str | None, pagina: int | None, texto_da_pagina: Callable[[int], str | None]) -> bool:
    """O trecho está na página citada ou numa vizinha. `texto_da_pagina`
    devolve o texto da página do PDF pelo número, ou None fora do arquivo."""
    alvo = normalizar(trecho or "")
    if not alvo or pagina is None:
        return False
    for numero in (pagina, pagina - 1, pagina + 1):
        texto = texto_da_pagina(numero)
        if texto and _parecido(alvo, normalizar(texto)):
            return True
    return False
