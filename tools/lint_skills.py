#!/usr/bin/env python3
"""Lint do cabeçalho YAML das skills (.claude/skills/*/SKILL.md), issue #807.

Uso: python3 tools/lint_skills.py [--dir .claude/skills]
Sai com código 1 se houver qualquer violação.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

FRONTMATTER = re.compile(r"^---\r?\n(.*?)\r?\n---", re.DOTALL)


def _problema(arquivo: Path) -> str | None:
    m = FRONTMATTER.match(arquivo.read_text(encoding="utf-8"))
    if not m:
        return "sem cabeçalho YAML entre `---` na primeira linha."
    try:
        cabecalho = yaml.safe_load(m.group(1))
    except yaml.YAMLError as e:
        return f"cabeçalho YAML não parseia ({str(e).splitlines()[0]})."
    if not isinstance(cabecalho, dict):
        return "cabeçalho YAML não é um mapa de campos."
    faltando = [
        campo
        for campo in ("name", "description")
        if not isinstance(cabecalho.get(campo), str) or not cabecalho[campo].strip()
    ]
    if faltando:
        return "falta " + " e ".join(f"`{c}`" for c in faltando) + " no cabeçalho."
    return None


def problemas(pasta: Path) -> list[str]:
    """Um texto por SKILL.md cujo cabeçalho o Claude Code descartaria."""
    arquivos = sorted(pasta.glob("*/SKILL.md"))
    if not arquivos:
        return [f"{pasta}: nenhum */SKILL.md encontrado; confira o --dir."]
    erros: list[str] = []
    for arquivo in arquivos:
        problema = _problema(arquivo)
        if problema:
            erros.append(f"{arquivo}: {problema}")
    return erros


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=".claude/skills")
    args = ap.parse_args()

    erros = problemas(Path(args.dir))
    for erro in erros:
        print(erro)
    return 1 if erros else 0


if __name__ == "__main__":
    sys.exit(main())
