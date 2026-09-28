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

FRONTMATTER = re.compile(r"^---\r?\n(.*?)\r?\n---", re.S)


def problemas(pasta: Path) -> list[str]:
    erros: list[str] = []
    for arquivo in sorted(pasta.glob("*/SKILL.md")):
        m = FRONTMATTER.match(arquivo.read_text(encoding="utf-8"))
        try:
            yaml.safe_load(m.group(1))
        except yaml.YAMLError as e:
            linha = str(e).splitlines()[0]
            erros.append(f"{arquivo}: cabeçalho YAML não parseia ({linha}).")
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
