#!/usr/bin/env python3
"""Grava o link da Demonstração no corpo da issue-raiz (ADR 0084, decisão 9).

Uso: marcar_demonstracao.py <issue> <url>

Acrescenta `<!-- demonstracao: <url> -->` no fim do corpo, ou troca o que já existe.
O webhook do app lê o marcador e o card da Tecnologia ganha o selo "Tem demonstração".
Só aceita `https`. Lê e grava pela REST do `gh` (o GraphQL pode estar sem cota).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile

MARCADOR = re.compile(r"\n*<!-- demonstracao: [^\n]*? -->\n*")
URL_VALIDA = re.compile(r"^https://[^\s<>\"']+$")


def com_marcador(corpo: str, url: str) -> str:
    """O corpo com um marcador só, no fim, apontando para `url`."""
    if not URL_VALIDA.match(url):
        raise ValueError(f"o link precisa ser https e sem espaço: {url}")
    sem = MARCADOR.sub("\n\n", corpo).rstrip()
    return f"{sem}\n\n<!-- demonstracao: {url} -->\n"


def _gh(*args: str) -> str:
    return subprocess.run(
        ["gh", *args], check=True, capture_output=True, text=True
    ).stdout


def main(argv: list[str]) -> int:
    if len(argv) != 2 or not argv[0].isdigit():
        print("uso: marcar_demonstracao.py <issue> <url>", file=sys.stderr)
        return 2
    issue, url = argv
    if not URL_VALIDA.match(url):
        print(f"o link precisa ser https e sem espaço: {url}", file=sys.stderr)
        return 1
    repo = _gh(
        "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"
    ).strip()
    corpo = json.loads(_gh("api", f"repos/{repo}/issues/{issue}"))["body"] or ""
    with tempfile.NamedTemporaryFile(
        "w", suffix=".json", delete=False, encoding="utf-8"
    ) as f:
        json.dump({"body": com_marcador(corpo, url)}, f)
    try:
        _gh("api", "-X", "PATCH", f"repos/{repo}/issues/{issue}", "--input", f.name)
    finally:
        os.unlink(f.name)
    print(f"#{issue}: demonstração {url}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
