"""A pergunta respondida encolhe numa linha (issue #1594, PRD #1591).

A linha é coisa da tela (`ChatDaTecnologia.test.tsx`); aqui fica o kit, que é a
língua em que o Assistente explica a conversa ao diretor.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.conhecimento import CONHECIMENTO_DIR  # noqa: E402


def test_o_texto_da_tecnologia_no_kit_diz_que_a_pergunta_respondida_encolhe_numa_linha():
    texto = (CONHECIMENTO_DIR / "tecnologia.md").read_text(encoding="utf-8")

    for titulo in ("## A conversa com o Assistente", "## O Planejamento da Demanda"):
        secao = texto.split(titulo, 1)[1].split("\n## ", 1)[0]
        for trecho in (
            "a pergunta encolhe numa linha com o número, o título e a sua escolha",
            "o começo do que você escreveu",
            "Um clique na linha abre a pergunta inteira de novo, só para ler, e outro clique fecha",
        ):
            assert trecho in secao, (titulo, trecho)
