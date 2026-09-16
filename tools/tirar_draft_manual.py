#!/usr/bin/env python3
"""Tira o `draft` das páginas do Manual dos PRDs que subiram para produção.

O `draft` é o único mecanismo de invisibilidade do manual (ADR 0057, decisão
5): página de funcionalidade que ainda não está no ar fica fora do build e da
busca. Quem apaga essa marca não é gente: é o `/deploy ship`, logo depois do
bookkeeping, para cada PRD daquele deploy.

Uso:
    python3 tools/tirar_draft_manual.py --prd 731 [--prd 740]
                                        [--dir docs/manual] [--dry-run]

Sai com código 0 mesmo quando não há nada a fazer (deploy sem página em draft é
o caso normal, e o passo é silencioso). Código 1 só quando o uso está errado:
pasta que não é o site do manual.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from inventario_manual import _prds, _valor  # noqa: E402
from lint_manual import ler_frontmatter  # noqa: E402

# A leitura do frontmatter é a mesma do inventário de propósito: se as duas
# divergirem, o inventário da `/montar-manual` acusa `draft-entregue` numa
# página que este passo jura ter publicado.


def paginas_em_draft(conteudo: Path, prds: list[int]) -> list[Path]:
    """As páginas em draft tocadas por pelo menos um dos PRDs, em ordem."""
    achadas = []
    for arquivo in sorted(conteudo.rglob("*.md*")):
        if arquivo.suffix not in (".md", ".mdx"):
            continue
        campos = ler_frontmatter(arquivo.read_text(encoding="utf-8"))
        if _valor(campos, "draft") != "true":
            continue
        if set(_prds(campos)) & set(prds):
            achadas.append(arquivo)
    return achadas


def tirar_draft(arquivo: Path) -> None:
    """Troca `draft: true` por `draft: false`, preservando o resto da linha."""
    linhas = arquivo.read_text(encoding="utf-8").splitlines(keepends=True)
    for i, linha in enumerate(linhas):
        if linha.startswith("draft:"):
            linhas[i] = linha.replace("true", "false", 1)
            break
    arquivo.write_text("".join(linhas), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="docs/manual")
    ap.add_argument(
        "--prd",
        type=int,
        action="append",
        required=True,
        help="número do PRD que subiu; repita para vários",
    )
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    raiz = Path(args.dir)
    conteudo = raiz / "src" / "content" / "docs"
    if not conteudo.is_dir():
        print(
            f"Manual: '{raiz}' não tem src/content/docs. "
            "O site do manual é docs/manual/.",
            file=sys.stderr,
        )
        return 1

    numeros = ", ".join(f"#{n}" for n in args.prd)
    achadas = paginas_em_draft(conteudo, args.prd)
    if not achadas:
        print(f"Manual: nenhuma página em draft do PRD {numeros}.")
        return 0

    for arquivo in achadas:
        if not args.dry_run:
            tirar_draft(arquivo)
        print(f"Manual: {arquivo.relative_to(conteudo)} sai do draft.")
    if args.dry_run:
        print(f"(--dry-run: {len(achadas)} página(s) continuam em draft.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
