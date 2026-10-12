"""Extrator de texto de PDF do módulo Contas médicas (issue #1116, ADR 0070)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ErroLeitura:
    """Leitura que não pode ser usada. `motivo` é a frase que vai para a tela."""

    motivo: str
