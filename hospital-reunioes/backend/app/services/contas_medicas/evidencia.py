"""A conferência da evidência que a IA cita (issue #1131, PRD #1128, spec 9.6).

O trecho que a IA copia do prontuário tem de existir na página citada ou na
vizinha. A comparação é sem acento, sem espaço e sem caixa, e aceita 85% de
semelhança: a IA erra uma letra, junta duas linhas, troca um acento.
"""

from __future__ import annotations

import unicodedata

__all__ = ["normalizar"]


def normalizar(texto: str) -> str:
    """Sem acento, sem espaço nenhum e sem caixa."""
    sem_acento = "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")
    return "".join(sem_acento.split()).casefold()
