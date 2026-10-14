"""A reescrita única da seção Valor entregue dos PRs da janela do Hospital OS
(issue #1222, ADR 0071, decisão 4).

O par Antes e Depois vira o parágrafo "O que muda"; `Closes #N`, a seção de
migration conferida por hash e o resto do corpo ficam byte a byte iguais. A
transformação é pura (sem API); o `main` recebe o `gh` por injeção, e o teste
do `--dry-run` confere que nenhuma chamada de escrita sai.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import reescrever_valor_entregue as rv  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent / "workflow-dashboard"))
from collect import resumo_funcional  # noqa: E402

PARAGRAFO = "o secretário baixa a Ata pronta em PDF com um clique e manda por email."

CABECA = "<!-- automacao -->\nCloses #812\n\n"
VALOR_ANTIGO = (
    "## 💬 Valor entregue\n\n"
    "**Antes:** a Ata saía só na tela.\n"
    "**Depois:** a Ata sai em PDF.\n\n"
)
RESTO = (
    "## 🎯 Contexto\n\nO secretário copiava a Ata para o Word.\n\n"
    "## 🗄️ Migration\n\n"
    "sha256 `9f2c1e0b7a`, conferido contra `hospital-reunioes/supabase/migrations/151_ata_pdf.sql`\n\n"
    "```sql\nALTER TABLE atas ADD COLUMN pdf_path text;\n```\n\n"
    "## Closes\n\nCloses #812\n"
)
CORPO_ANTIGO = CABECA + VALOR_ANTIGO + RESTO


def test_antes_e_depois_viram_o_que_muda_e_o_resto_fica_igual():
    novo = rv.reescrever_corpo(CORPO_ANTIGO, PARAGRAFO)

    assert novo == CABECA + "## 💬 Valor entregue\n\n**O que muda:** " + PARAGRAFO + "\n\n" + RESTO
    # o hover do Hospital OS lê o parágrafo novo
    assert resumo_funcional(novo)["o_que_muda"] == PARAGRAFO


def test_pr_sem_a_secao_ganha_valor_entregue_logo_abaixo_do_marcador():
    corpo = "<!-- automacao -->\nRegistro do deploy de producao.\n\nCloses #942\n"

    novo = rv.reescrever_corpo(corpo, PARAGRAFO)

    assert novo == (
        "<!-- automacao -->\n## 💬 Valor entregue\n\n**O que muda:** "
        + PARAGRAFO
        + "\n\nRegistro do deploy de producao.\n\nCloses #942\n"
    )
    assert resumo_funcional(novo)["o_que_muda"] == PARAGRAFO
