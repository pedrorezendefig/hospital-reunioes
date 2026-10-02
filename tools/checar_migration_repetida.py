#!/usr/bin/env python3
"""Recusa migration nova com número que a base já usa (issue #903).

Duas sessões em paralelo podem escolher o mesmo próximo número de migration, e
o erro só aparecia depois de publicado. Esta guarda compara a branch atual com
a base (por padrão `origin/main`): se uma migration que a branch ADICIONOU tem
o prefixo numérico de uma que já está na base, sai com código 1 e nomeia o
número e os dois arquivos. Renumerar é do autor.

Migration renomeada ou editada não conta como adicionada, e o mesmo arquivo
que já está na base também não (branch empilhada sobre um PR que já entrou por
squash traz o commit original de novo).

Roda em dois tempos: no CI de todo pull request e nas pré-condições do
`fechar_onda.py`, contra a `main` recém-buscada. Só usa `git`.

Uso: python3 tools/checar_migration_repetida.py [--base origin/main] [--head HEAD]
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

PASTA = "hospital-reunioes/supabase/migrations"
RE_NUMERO = re.compile(r"^(\d+)_")


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {proc.stderr.strip()}")
    return proc.stdout


def _numero(nome: str) -> int | None:
    m = RE_NUMERO.match(nome)
    return int(m.group(1)) if m else None


def colisoes(
    repo: Path, base: str = "origin/main", head: str = "HEAD"
) -> list[tuple[int, str, str]]:
    """`(número, arquivo da base, arquivo da branch)` de cada número repetido."""
    raiz = Path(_git(repo, "rev-parse", "--show-toplevel").strip())
    na_base: dict[int, list[str]] = {}
    for caminho in _git(raiz, "ls-tree", "-r", "--name-only", base, "--", PASTA).split():
        nome = Path(caminho).name
        numero = _numero(nome)
        if numero is not None:
            na_base.setdefault(numero, []).append(nome)
    adicionadas = _git(
        raiz, "diff", "--name-only", "-M", "--diff-filter=A", f"{base}...{head}", "--", PASTA
    ).split()
    achadas = []
    for caminho in adicionadas:
        nome = Path(caminho).name
        for existente in na_base.get(_numero(nome), []):
            if existente != nome:
                achadas.append((_numero(nome), existente, nome))
    return achadas


def mensagem(achadas: list[tuple[int, str, str]]) -> str:
    linhas = [
        f"migration com número repetido: {numero} já existe na base como {da_base}"
        f" e a branch adiciona {da_branch}."
        for numero, da_base, da_branch in achadas
    ]
    linhas.append("Renumere a migration da branch para o próximo número livre.")
    return "\n".join(linhas)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", default="origin/main", help="referência da base (default: origin/main)")
    ap.add_argument("--head", default="HEAD", help="referência da branch (default: HEAD)")
    args = ap.parse_args(argv)
    achadas = colisoes(Path.cwd(), args.base, args.head)
    if achadas:
        print(mensagem(achadas))
        return 1
    print(f"migrations: nenhum número repetido contra {args.base}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
