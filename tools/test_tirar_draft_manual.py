"""O manual entra no ar junto com a funcionalidade (issue #735).

Quem tira o `draft` das páginas não é gente: é o `/deploy ship`, logo depois do
bookkeeping, para cada PRD que subiu naquele deploy. Estes testes provam o que
o passo faz e, principalmente, o que ele **não** faz: página de PRD que ainda
não subiu continua invisível.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SCRIPT = RAIZ / "tools" / "tirar_draft_manual.py"

PAGINA = """---
title: Registrar uma manifestação
description: Uma frase.
prd: [{prds}]
draft: {draft}
papel: [Ouvidoria]
---

## Quando usar
"""


def escrever(raiz: Path, caminho: str, prds: str, draft: str = "true") -> Path:
    arquivo = raiz / "src" / "content" / "docs" / caminho
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    arquivo.write_text(PAGINA.format(prds=prds, draft=draft), encoding="utf-8")
    return arquivo


def rodar(raiz: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--dir", str(raiz), *args],
        capture_output=True,
        text=True,
    )


def test_pagina_do_prd_que_subiu_sai_do_draft(tmp_path):
    arquivo = escrever(tmp_path, "ouvidoria/registrar.md", "731")

    saida = rodar(tmp_path, "--prd", "731")

    assert saida.returncode == 0, saida.stderr
    assert "draft: false" in arquivo.read_text(encoding="utf-8")
    assert "ouvidoria/registrar.md" in saida.stdout


def test_pagina_de_outro_prd_fica_intacta(tmp_path):
    """O deploy de um PRD não pode publicar a tela que outro ainda não subiu."""
    arquivo = escrever(tmp_path, "pops/aprovar.md", "740")
    antes = arquivo.read_text(encoding="utf-8")

    saida = rodar(tmp_path, "--prd", "731")

    assert saida.returncode == 0, saida.stderr
    assert arquivo.read_text(encoding="utf-8") == antes


def test_sem_pagina_em_draft_o_passo_e_silencioso(tmp_path):
    """Critério de aceite da #735: sem draft, não faz nada e diz isso no log."""
    escrever(tmp_path, "ouvidoria/registrar.md", "731", draft="false")

    saida = rodar(tmp_path, "--prd", "731")

    assert saida.returncode == 0, saida.stderr
    assert "nenhuma página" in saida.stdout.lower()


def test_dry_run_diz_o_que_mudaria_sem_escrever(tmp_path):
    arquivo = escrever(tmp_path, "ouvidoria/registrar.md", "731")
    antes = arquivo.read_text(encoding="utf-8")

    saida = rodar(tmp_path, "--prd", "731", "--dry-run")

    assert saida.returncode == 0, saida.stderr
    assert "ouvidoria/registrar.md" in saida.stdout
    assert arquivo.read_text(encoding="utf-8") == antes


def test_comentario_na_linha_nao_engana_a_leitura(tmp_path):
    """O molde da `/manual` comenta a linha do `draft`, e o número do ADR mora
    no comentário do `prd`. Ler a linha crua publicaria a página errada."""
    pagina = tmp_path / "src" / "content" / "docs" / "ouvidoria" / "registrar.md"
    pagina.parent.mkdir(parents=True, exist_ok=True)
    pagina.write_text(
        "---\n"
        "title: Registrar\n"
        "prd: [731]                 # ADR 0057\n"
        "draft: true                # sai quando o PRD sobe para produção\n"
        "papel: [Ouvidoria]\n"
        "---\n\n## Quando usar\n",
        encoding="utf-8",
    )

    saida = rodar(tmp_path, "--prd", "57")
    assert "nenhuma página" in saida.stdout.lower(), "o 0057 do comentário virou PRD"

    rodar(tmp_path, "--prd", "731")
    texto = pagina.read_text(encoding="utf-8")
    assert "draft: false" in texto
    assert "sai quando o PRD sobe para produção" in texto


def test_pagina_de_varios_prds_sai_do_draft_uma_vez_so(tmp_path):
    """Página tocada por dois PRDs sobe quando o primeiro deles sobe."""
    arquivo = escrever(tmp_path, "reunioes/criar-meta.md", "731, 740")

    saida = rodar(tmp_path, "--prd", "740", "--prd", "731")

    assert saida.returncode == 0, saida.stderr
    assert saida.stdout.count("reunioes/criar-meta.md") == 1
    assert "draft: false" in arquivo.read_text(encoding="utf-8")


def test_pasta_sem_site_e_erro_de_uso(tmp_path):
    """Rodar na pasta errada não pode passar por 'nada em draft'."""
    saida = rodar(tmp_path / "vazio", "--prd", "731")

    assert saida.returncode == 1
    assert "src/content/docs" in saida.stderr
