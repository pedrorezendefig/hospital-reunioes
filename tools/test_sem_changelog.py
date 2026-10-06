"""Fim do CHANGELOG em Markdown (issue #939, ADR 0062, decisão 9).

A timeline dos deploys é o `docs/spec/deploy/history.json`, sem teto, e o
painel a desenha. O arquivo em Markdown e o script que o escrevia foram
apagados. Citação que sobrar em skill, doc ou script manda alguém (ou um
agente) ler ou escrever num arquivo que não existe mais, e só apareceria na
hora do deploy. Este teste varre todo arquivo versionado.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PADRAO = r"CHANGELOG|changelog_prepend"

# Onde a citação é história ou fica para outra fatia.
EXCECOES = [
    "docs/adr/",  # registro do que foi decidido; a ADR 0062 cita o arquivo que apagou
    "docs/spec/deploy/history.json",  # notas de deploys antigos
    "docs/spec/snapshots/",  # auto-gerado; a Action do #940 refaz
    "tools/test_sem_changelog.py",  # este arquivo
]


def citacoes(excecoes: list[str]) -> list[str]:
    proc = subprocess.run(
        [
            "git",
            "grep",
            "-n",
            "-I",
            "-E",
            PADRAO,
            "--",
            ".",
            *(f":(exclude){e}" for e in excecoes),
        ],
        cwd=RAIZ,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.returncode in (0, 1), proc.stderr  # 1: nada encontrado
    return proc.stdout.splitlines()


def test_a_varredura_acha_a_citacao_quando_ela_existe():
    """Piso de sanidade: sem as exceções, a mesma busca acha a ADR 0062."""
    assert [li for li in citacoes([]) if li.startswith("docs/adr/0062-")]


def test_nenhum_arquivo_versionado_cita_o_changelog_fora_das_excecoes():
    assert citacoes(EXCECOES) == []


def test_o_changelog_e_o_script_que_o_escrevia_foram_apagados():
    for caminho in (
        "docs/spec/CHANGELOG.md",
        ".claude/skills/deploy/scripts/changelog_prepend.py",
    ):
        assert not (RAIZ / caminho).exists(), caminho
