#!/usr/bin/env python3
"""Confere o build do Manual: draft não vira página nem entra na busca.

`draft: true` é o único mecanismo de invisibilidade do manual (ADR 0057,
decisão 5): página de funcionalidade que ainda não subiu fica escrita e fora do
ar. Este conferidor roda depois do `astro build` e prova, no HTML que foi
gerado de verdade, o que o site promete ao usuário:

- nenhuma página em draft virou HTML em `dist/` nem entrou no índice do Pagefind;
- toda página publicada está no índice (piso de sanidade: sem ele, um build
  vazio passaria como "nenhum draft no ar");
- todo ícone declarado no HTML existe no `dist/` (o site pediu um
  `/favicon.svg` inexistente por meses, e o build ficava verde);
- nenhum grupo da sidebar mostra o nome cru da pasta (`como-funciona` em vez de
  "Como funciona"): o `autogenerate` do Starlight rotula com o nome do
  diretório e quem conserta é o route middleware, que pode ser desligado sem
  ninguém perceber.

Sem dependências externas. Uso: python3 tools/checar_build_manual.py [--dir docs/manual]
Sai com código 1 se houver qualquer violação.
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
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


RE_LINK = re.compile(r"<link\b[^>]*>", re.IGNORECASE)
RE_REL = re.compile(r'\brel="([^"]*)"', re.IGNORECASE)
RE_HREF = re.compile(r'\bhref="([^"]*)"', re.IGNORECASE)


def icones_declarados(html: str) -> set[str]:
    """Os `href` de todo `<link>` de ícone da página.

    Qualquer `rel` que contenha `icon` (`icon`, `shortcut icon`,
    `apple-touch-icon`) e qualquer extensão: trocar o ícone amanhã não pode
    quebrar o conferidor por motivo errado.
    """
    achados: set[str] = set()
    for tag in RE_LINK.findall(html):
        rel = RE_REL.search(tag)
        href = RE_HREF.search(tag)
        if not rel or not href:
            continue
        if any("icon" in parte for parte in rel.group(1).lower().split()):
            achados.add(href.group(1))
    return achados


def pastas_que_viram_grupo(conteudo: Path) -> set[str]:
    """Nome das subpastas de módulo, que o `autogenerate` transforma em grupo.

    O primeiro nível é o módulo (`ouvidoria/`), que já tem rótulo escrito à mão
    no `astro.config.mjs`. Do segundo nível em diante o Starlight rotula com o
    nome do diretório, e é aí que o nome cru vaza para a tela.
    """
    return {
        pasta.name
        for pasta in conteudo.rglob("*")
        if pasta.is_dir() and len(pasta.relative_to(conteudo).parts) >= 2
    }


def checar_icone(dist: Path, paginas: list[Path]) -> list[str]:
    """Todo ícone declarado no HTML tem que existir no `dist`."""
    problemas: list[str] = []
    declarados: set[str] = set()
    for pagina in paginas:
        declarados |= icones_declarados(pagina.read_text(encoding="utf-8"))

    if not declarados:
        # Piso de sanidade: o Starlight sempre declara um ícone, nem que seja o
        # `/favicon.svg` do padrão dele. Zero aqui é varredura quebrada, não
        # site sem ícone, e sem este piso a checagem ficaria verde sobre nada.
        problemas.append(
            "nenhuma página do dist declarou ícone: a varredura não está achando "
            "o <link rel=icon>."
        )

    for href in sorted(declarados):
        alvo = href.split("?")[0].split("#")[0]
        if alvo.startswith(("http://", "https://", "//", "data:")):
            continue
        if not (dist / alvo.lstrip("/")).is_file():
            problemas.append(
                f"o HTML pede o ícone '{href}' e ele não existe em dist. "
                "Aponte a opção `favicon` do Starlight para um arquivo que o "
                "`prebuild` coloque em public/."
            )
    return problemas


def checar_rotulos(conteudo: Path, dist: Path, paginas: list[Path]) -> list[str]:
    """Nenhum grupo da sidebar pode mostrar o nome cru da pasta.

    A sidebar sai em toda página do site, então um rótulo cru aparece nas 49 de
    uma vez. Uma linha por pasta, com um exemplo: o que o humano precisa é do
    nome da pasta, não de 49 vezes a mesma frase.
    """
    pastas = pastas_que_viram_grupo(conteudo)
    if not pastas:
        return []
    onde: dict[str, list[str]] = {}
    for pagina in paginas:
        html = pagina.read_text(encoding="utf-8")
        for nome in sorted(pastas):
            if f">{nome}<" in html:
                onde.setdefault(nome, []).append(
                    str(pagina.relative_to(dist))
                )
    return [
        f"a sidebar mostra o nome cru da pasta '{nome}' em {len(paginas_com)} "
        f"página(s) do dist (ex.: {paginas_com[0]}). Dê um rótulo a ela em "
        "src/rotulos-da-sidebar.ts."
        for nome, paginas_com in sorted(onde.items())
    ]


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

    paginas = sorted(dist.rglob("*.html"))
    if not paginas:
        problemas.append("dist não tem nenhuma página HTML: o build não gerou site.")
    problemas += checar_icone(dist, paginas)
    problemas += checar_rotulos(conteudo, dist, paginas)

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
    print(
        "Conferidor do build do Manual OK (draft fora do ar, publicado na busca, "
        "ícone no lugar, sidebar com rótulo de gente)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
