#!/usr/bin/env python3
"""Confere o build do Manual: draft não vira página nem entra na busca.

`draft: true` é o único mecanismo de invisibilidade do manual (ADR 0057,
decisão 5): página de funcionalidade que ainda não subiu fica escrita e fora do
ar. Este conferidor roda depois do `astro build` e prova as duas metades da
promessa:

- nenhuma página em draft virou HTML em `dist/` nem entrou no índice do Pagefind;
- toda página publicada está no índice (piso de sanidade: sem ele, um build
  vazio passaria como "nenhum draft no ar").

Sem dependências externas. Uso: python3 tools/checar_build_manual.py [--dir docs/manual]
Sai com código 1 se houver qualquer violação.
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from lint_manual import ler_frontmatter  # noqa: E402


def url_da_pagina(relativo: Path) -> str:
    """A URL que o Starlight gera para um arquivo de conteúdo."""
    partes = list(relativo.with_suffix("").parts)
    if partes[-1] == "index":
        partes.pop()
    return "/" + "".join(f"{p}/" for p in partes)


def urls_da_busca(dist: Path) -> set[str]:
    """URLs indexadas pelo Pagefind (cada fragmento é um JSON comprimido)."""
    urls: set[str] = set()
    for fragmento in sorted((dist / "pagefind" / "fragment").glob("*.pf_fragment")):
        bruto = gzip.decompress(fragmento.read_bytes()).decode("utf-8")
        _, _, corpo = bruto.partition("{")
        urls.add(json.loads("{" + corpo)["url"])
    return urls


def checar(raiz: Path) -> list[str]:
    conteudo = raiz / "src" / "content" / "docs"
    dist = raiz / "dist"
    indexadas = urls_da_busca(dist)
    problemas: list[str] = []

    for arquivo in sorted(conteudo.rglob("*.md*")):
        if arquivo.suffix not in (".md", ".mdx"):
            continue
        relativo = arquivo.relative_to(conteudo)
        url = url_da_pagina(relativo)
        campos = ler_frontmatter(arquivo.read_text(encoding="utf-8"))
        e_draft = campos.get("draft", "").lower() == "true"

        html = dist / relativo.with_suffix("").parent / relativo.stem / "index.html"
        if relativo.stem == "index":
            html = dist / relativo.parent / "index.html"

        if e_draft:
            if html.exists():
                problemas.append(
                    f"{relativo}: está em draft e virou página em dist ({url})."
                )
            if url in indexadas:
                problemas.append(f"{relativo}: está em draft e entrou na busca ({url}).")
        else:
            if not html.exists():
                problemas.append(f"{relativo}: publicada e sem página em dist ({url}).")
            elif url not in indexadas:
                problemas.append(f"{relativo}: publicada e fora da busca ({url}).")

    return problemas


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="docs/manual")
    args = ap.parse_args()

    raiz = Path(args.dir)
    if not (raiz / "dist").is_dir():
        print(f"Conferidor do Manual: '{raiz}/dist' não existe. Rode o build antes.", file=sys.stderr)
        return 1

    problemas = checar(raiz)
    if problemas:
        print(
            "Conferidor do build do Manual falhou:\n"
            + "\n".join(f"  - {p}" for p in problemas),
            file=sys.stderr,
        )
        return 1
    print("Conferidor do build do Manual OK (draft fora do ar, publicado na busca).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
