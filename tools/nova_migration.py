#!/usr/bin/env python3
"""Cria a migration nova já com o próximo número e o recibo.

O recibo (issue #969) é a última instrução de toda migration nova, e quem cria
o arquivo na mão esquece: foram 4 PRs vermelhos em uma semana pela guarda
`checar_recibo_da_migration.py`. Aqui o arquivo nasce com o recibo, e o corpo
vai acima dele.

O número é um a mais que o maior entre a pasta local e a `origin/main`
recém-buscada, para não repetir o número de uma migration que outra sessão já
mergeou (issue #903).

Uso: python3 tools/nova_migration.py <slug>
     (ex.: python3 tools/nova_migration.py ouvidoria_nota_do_google)
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from checar_migration_repetida import PASTA, _numero  # noqa: E402
from checar_recibo_da_migration import recibo  # noqa: E402

RE_SLUG = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")


def _git(raiz: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=raiz, capture_output=True, text=True, encoding="utf-8"
    )
    return proc.stdout if proc.returncode == 0 else ""


def proximo_numero(raiz: Path, base: str = "origin/main") -> int:
    nomes = [p.name for p in (raiz / PASTA).glob("*.sql")]
    nomes += [Path(c).name for c in _git(raiz, "ls-tree", "-r", "--name-only", base, "--", PASTA).split()]
    numeros = [n for n in map(_numero, nomes) if n is not None]
    return max(numeros, default=0) + 1


def conteudo(numero: int) -> str:
    return (
        "-- Escreva a migration acima do recibo.\n"
        "\n"
        "\n"
        "-- recibo: a subida espera este número no /api/health (issue #969)\n"
        f"{recibo(numero)}\n"
    )


def criar(raiz: Path, slug: str, base: str = "origin/main") -> Path:
    if not RE_SLUG.match(slug):
        raise ValueError(f"slug em minúsculas com _ entre as palavras: {slug!r}")
    numero = proximo_numero(raiz, base)
    arquivo = raiz / PASTA / f"{numero:03d}_{slug}.sql"
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    arquivo.write_text(conteudo(numero), encoding="utf-8")
    return arquivo


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("slug", help="nome da migration, ex.: ouvidoria_nota_do_google")
    ap.add_argument("--base", default="origin/main", help="referência da base (default: origin/main)")
    ap.add_argument("--sem-fetch", action="store_true", help="não busca a base antes")
    args = ap.parse_args(argv)
    raiz = Path(_git(Path.cwd(), "rev-parse", "--show-toplevel").strip() or Path.cwd())
    if not args.sem_fetch:
        _git(raiz, "fetch", "-q", "origin", "main")
    try:
        arquivo = criar(raiz, args.slug, args.base)
    except ValueError as erro:
        print(erro, file=sys.stderr)
        return 2
    print(arquivo.relative_to(raiz))
    return 0


if __name__ == "__main__":
    sys.exit(main())
