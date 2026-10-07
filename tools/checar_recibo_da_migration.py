#!/usr/bin/env python3
"""Recusa migration nova que não termina gravando o próprio número (issue #969).

A subida (`fechar_onda.py`) só mergeia um lote com migration depois que o
`/api/health` devolve o número dela, e quem põe o número lá é a própria
migration: a última instrução de toda migration nova é

    INSERT INTO migracoes_aplicadas (numero) VALUES (<N>) ON CONFLICT (numero) DO NOTHING;

com N igual ao prefixo do arquivo. Sem ela, ou com o número de outra, a subida
esperaria 24 h por um número que nunca chega. Comentário e linha em branco
depois do insert não contam; o `ON CONFLICT` é opcional (deixa reaplicar).

Migration nova é a que a branch ADICIONOU contra a base, como na guarda de
número repetido: renomear ou editar uma antiga não conta, nem a que a base já
tem com o mesmo nome (branch empilhada sobre um PR que entrou por squash). Só
usa `git`.

Uso: python3 tools/checar_recibo_da_migration.py [--base origin/main] [--head HEAD]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# mesma pasta, mesmo prefixo numérico e mesmo `git` da guarda de número repetido
from checar_migration_repetida import PASTA, _git, _numero

RE_RECIBO = re.compile(
    r"insert\s+into\s+(?:public\.)?migracoes_aplicadas\s*\(\s*numero\s*\)\s*"
    r"values\s*\(\s*(\d+)\s*\)\s*(?:on\s+conflict\s*(?:\(\s*numero\s*\)\s*)?do\s+nothing\s*)?;?\s*\Z",
    re.IGNORECASE,
)


def recibo(numero: int) -> str:
    return f"INSERT INTO migracoes_aplicadas (numero) VALUES ({numero}) ON CONFLICT (numero) DO NOTHING;"


def numero_do_recibo(sql: str) -> int | None:
    """O número que a última instrução da migration grava, ou None se ela não
    termina no insert do recibo."""
    sem_comentarios = re.sub(r"--[^\n]*", "", re.sub(r"/\*.*?\*/", "", sql, flags=re.S))
    m = RE_RECIBO.search(sem_comentarios)
    return int(m.group(1)) if m else None


def sem_recibo(repo: Path, base: str = "origin/main", head: str = "HEAD") -> list[str]:
    """Nome de cada migration nova da branch que não termina gravando o próprio número."""
    raiz = Path(_git(repo, "rev-parse", "--show-toplevel").strip())
    adicionadas = _git(
        raiz, "diff", "--name-only", "-M", "--diff-filter=A", f"{base}...{head}", "--", PASTA
    ).split()
    na_base = set(_git(raiz, "ls-tree", "-r", "--name-only", base, "--", PASTA).split())
    ruins = []
    for caminho in adicionadas:
        nome = Path(caminho).name
        if caminho in na_base or not nome.endswith(".sql"):
            continue
        if numero_do_recibo(_git(raiz, "show", f"{head}:{caminho}")) != _numero(nome):
            ruins.append(nome)
    return ruins


def mensagem(ruins: list[str]) -> str:
    linhas = [
        f"migration sem recibo: {nome} precisa terminar com {recibo(_numero(nome))}"
        for nome in ruins
    ]
    linhas.append(
        "A subida só mergeia depois que o /api/health devolve esse número (issue #969)."
    )
    return "\n".join(linhas)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", default="origin/main", help="referência da base (default: origin/main)")
    ap.add_argument("--head", default="HEAD", help="referência da branch (default: HEAD)")
    args = ap.parse_args(argv)
    ruins = sem_recibo(Path.cwd(), args.base, args.head)
    if ruins:
        print(mensagem(ruins))
        return 1
    print(f"migrations: toda migration nova termina com o recibo contra {args.base}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
