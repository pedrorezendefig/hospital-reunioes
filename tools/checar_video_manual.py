#!/usr/bin/env python3
"""Confere os Vídeos de tarefa do Manual: fonte versionada, MP4 fora do git.

Uso: python3 tools/checar_video_manual.py [--dir docs/manual]
Sai com código 1 se houver qualquer violação.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from lint_manual import ler_frontmatter  # noqa: E402

RE_CARIMBO = re.compile(r'<script[^>]*id="manual-video-meta"[^>]*>(.*?)</script>', re.S)
CAMPOS_DO_CARIMBO = ["modulo", "slug", "pagina", "app_version", "gerado_em"]


def checar(raiz: Path) -> list[str]:
    conteudo = raiz / "src" / "content" / "docs"
    problemas: list[str] = []
    exibidas: set[tuple[str, str]] = set()

    for arquivo in sorted(conteudo.rglob("*.md*")):
        if arquivo.suffix not in (".md", ".mdx"):
            continue
        relativo = arquivo.relative_to(conteudo)
        slug = ler_frontmatter(arquivo.read_text(encoding="utf-8")).get("video", "")
        if not slug:
            continue
        modulo = relativo.parts[0]
        exibidas.add((modulo, slug))
        composicao = raiz / "video" / modulo / slug / "index.html"
        if not composicao.is_file():
            problemas.append(
                f"{relativo}: exibe o vídeo '{slug}' e não tem composição em "
                f"video/{modulo}/{slug}/index.html. O MP4 fica fora do git: "
                "sem a composição, ninguém regera o vídeo (ADR 0057, decisão 3)."
            )
            continue

        achado = RE_CARIMBO.search(composicao.read_text(encoding="utf-8"))
        carimbo = json.loads(achado.group(1)) if achado else {}
        faltando = [c for c in CAMPOS_DO_CARIMBO if not carimbo.get(c)]
        if faltando:
            problemas.append(
                f"video/{modulo}/{slug}/index.html: carimbo de geração sem "
                f"{', '.join(faltando)}. Sem ele ninguém sabe que tela e que "
                "versão do app o vídeo retrata (ADR 0057, decisão 3)."
            )

    for pasta in sorted((raiz / "video").glob("*/*")):
        if not pasta.is_dir():
            continue
        if (pasta.parent.name, pasta.name) not in exibidas:
            problemas.append(
                f"video/{pasta.parent.name}/{pasta.name}: composição que página "
                "nenhuma exibe. Aponte uma Página de tarefa para ela pelo campo "
                "`video` do frontmatter, ou apague a pasta."
            )

    for rendido in sorted((raiz / "video").rglob("*.mp4")):
        problemas.append(
            f"{rendido.relative_to(raiz)}: MP4 dentro da árvore versionada. "
            "O vídeo renderizado mora em public/video/<modulo>/<slug>.mp4, que "
            "fica fora do git (ADR 0057, decisão 3)."
        )

    return problemas


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="docs/manual")
    args = ap.parse_args()

    raiz = Path(args.dir)
    problemas = checar(raiz)
    if problemas:
        print(
            "Conferidor do Vídeo de tarefa falhou:\n"
            + "\n".join(f"  - {p}" for p in problemas),
            file=sys.stderr,
        )
        return 1
    print("Vídeos de tarefa OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
