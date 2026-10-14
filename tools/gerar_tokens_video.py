#!/usr/bin/env python3
"""Gera o tokens.css do Estilo do manual a partir do globals.css do frontend.

O Vídeo de tarefa é réplica do app: a cor e a fonte que a tela mostra são as
que o vídeo usa (emenda de 13/10/2026 à ADR 0057, issue #1230). Por isso o
`docs/manual/video/_estilo/tokens.css` nunca é escrito à mão: sai daqui, com

- a paleta e as fontes que o app herda pelo `@import "tailwindcss"` (o
  `theme.css` do Tailwind instalado no frontend), porque a tela usa
  `text-slate-500` e companhia muito mais do que os tokens próprios;
- os tokens próprios do app (`:root` e `@theme` do globals.css), a fonte do
  `body` como `--font-app` e o `@font-face` apontando para `assets/fonts/`;
- os tokens do Estilo do manual (`--video-*`), que só derivam dos do app por
  `var()` e `color-mix()`: nenhuma cor nova nasce aqui.

Uso:
  python3 tools/gerar_tokens_video.py [--globals ...] [--tema ...] [--saida ...]

Num worktree o frontend não tem `node_modules`: aponte `--tema` para o
`theme.css` da árvore principal ou instale as dependências do frontend.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
FRONTEND = RAIZ / "hospital-reunioes" / "frontend"
GLOBALS_PADRAO = FRONTEND / "src" / "app" / "globals.css"
TEMA_PADRAO = FRONTEND / "node_modules" / "tailwindcss" / "theme.css"
SAIDA_PADRAO = RAIZ / "docs" / "manual" / "video" / "_estilo" / "tokens.css"

RE_COMENTARIO = re.compile(r"/\*.*?\*/", re.S)
RE_DECLARACAO = re.compile(r"(--[\w-]+)\s*:\s*([^;{}]+);")
RE_BLOCO_APP = re.compile(r"(?::root|@theme)\s*\{([^{}]*)\}")
RE_FONT_FACE = re.compile(r"@font-face\s*\{([^{}]*)\}")
RE_FONTE_DO_BODY = re.compile(r"\bbody\s*\{[^{}]*?font-family\s*:\s*([^;{}]+);")
RE_TEMA_TAILWIND = re.compile(r"^(?:--color-[\w-]+|--font-(?:sans|serif|mono))$")

# Os tokens do Estilo do manual. Cada um diz o que significa (DESIGN.md, seção
# Paleta): a cor só entra no vídeo se tiver um papel. Valor sempre derivado de
# um token do app, para o vídeo acompanhar o app quando o app mudar.
ESTILO_DO_MANUAL: list[tuple[str, str, str]] = [
    (
        "--video-palco",
        "color-mix(in srgb, var(--color-primary) 6%, var(--color-bg))",
        "fundo atrás da tela do app",
    ),
    ("--video-marca", "var(--color-primary)", "o hospital: título e carimbo"),
    ("--video-texto", "var(--color-text)", "texto corrido dos cards"),
    (
        "--video-texto-apoio",
        "var(--color-text-secondary)",
        "texto de apoio (selos, linha do carimbo)",
    ),
    ("--video-foco", "var(--color-primary-light)", "onde olhar: anel, marcador, dedo"),
    (
        "--video-foco-halo",
        "color-mix(in srgb, var(--color-primary-light) 22%, transparent)",
        "halo em volta do foco",
    ),
    ("--video-passo", "var(--color-accent)", "número do passo"),
    ("--video-atencao", "var(--color-warning)", "aviso do que não tem volta"),
    ("--video-legenda-fundo", "var(--color-primary-dark)", "placa da legenda"),
    ("--video-legenda-texto", "var(--color-bg)", "texto sobre a placa"),
    ("--video-cartao", "var(--color-surface)", "fundo dos cards claros"),
    ("--video-borda", "var(--color-border)", "borda dos cards claros"),
    ("--video-sombra", "var(--shadow-premium-strong)", "sombra dos cards"),
    # Geometria da placa da legenda, no quadro de 1920x1080. O card
    # `legenda-de-passo` desenha a placa com estes números e o gate de strips
    # (tools/strips_video_manual.py) procura a placa no mesmo retângulo.
    ("--video-legenda-esquerda", "160px", "placa da legenda: borda esquerda"),
    ("--video-legenda-topo", "904px", "placa da legenda: borda de cima"),
    ("--video-legenda-largura", "1600px", "placa da legenda: largura"),
    ("--video-legenda-altura", "128px", "placa da legenda: altura"),
]


def _declaracoes(css: str) -> list[tuple[str, str]]:
    return [(nome, " ".join(valor.split())) for nome, valor in RE_DECLARACAO.findall(css)]


def _paleta_do_tailwind(tema: str) -> dict[str, str]:
    return {
        nome: valor
        for nome, valor in _declaracoes(RE_COMENTARIO.sub("", tema))
        if RE_TEMA_TAILWIND.match(nome)
    }


def _tokens_do_app(globals_css: str) -> dict[str, str]:
    tokens: dict[str, str] = {}
    for bloco in RE_BLOCO_APP.findall(globals_css):
        for nome, valor in _declaracoes(bloco):
            if valor == f"var({nome})":
                continue  # o @theme repete o :root para o Tailwind ver
            tokens[nome] = valor
    fonte = RE_FONTE_DO_BODY.search(globals_css)
    if fonte:
        tokens["--font-app"] = " ".join(fonte.group(1).split())
    return tokens


def _font_faces(globals_css: str) -> list[str]:
    blocos = []
    for corpo in RE_FONT_FACE.findall(globals_css):
        campos = dict(
            (chave.strip(), " ".join(valor.split()))
            for chave, valor in re.findall(r"([\w-]+)\s*:\s*([^;]+);", corpo)
        )
        arquivo = re.search(r"url\(\s*[\"']?([^\"')]+)", campos.get("src", ""))
        if not arquivo:
            continue
        nome = Path(arquivo.group(1)).name
        linhas = [
            f"  font-family: {campos.get('font-family', '')};",
            f'  src: url("assets/fonts/{nome}") format("truetype");',
        ]
        for chave in ("font-weight", "font-style"):
            if chave in campos:
                linhas.append(f"  {chave}: {campos[chave]};")
        blocos.append("@font-face {\n" + "\n".join(linhas) + "\n}")
    return blocos


def gerar(globals_css: str, tema_tailwind: str | None) -> str:
    """O tokens.css inteiro, determinístico para a mesma entrada."""
    globals_css = RE_COMENTARIO.sub("", globals_css)
    if '@import "tailwindcss"' in globals_css and tema_tailwind is None:
        raise ValueError(
            'o globals.css importa o Tailwind e o theme.css dele não foi achado'
        )
    partes = [
        "/* GERADO por tools/gerar_tokens_video.py a partir do globals.css do\n"
        "   frontend. Não edite à mão: mude o globals.css (ou o gerador) e rode\n"
        "   python3 tools/gerar_tokens_video.py de novo. */",
        *_font_faces(globals_css),
    ]
    raiz = [":root {"]
    if tema_tailwind is not None:
        raiz.append('  /* Paleta e fontes que o app herda pelo @import "tailwindcss" */')
        raiz += [f"  {n}: {v};" for n, v in _paleta_do_tailwind(tema_tailwind).items()]
    raiz.append("  /* Tokens do app (globals.css) */")
    raiz += [f"  {n}: {v};" for n, v in _tokens_do_app(globals_css).items()]
    raiz.append("  /* Estilo do manual: derivados dos tokens do app, sem cor nova */")
    raiz += [f"  {n}: {v}; /* {sentido} */" for n, v, sentido in ESTILO_DO_MANUAL]
    raiz.append("}")
    partes.append("\n".join(raiz))
    return "\n\n".join(partes) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--globals", type=Path, default=GLOBALS_PADRAO)
    ap.add_argument("--tema", type=Path, default=TEMA_PADRAO)
    ap.add_argument("--saida", type=Path, default=SAIDA_PADRAO)
    args = ap.parse_args()

    tema = args.tema.read_text(encoding="utf-8") if args.tema.is_file() else None
    try:
        tokens = gerar(args.globals.read_text(encoding="utf-8"), tema)
    except ValueError as erro:
        print(
            f"Gerador de tokens falhou: {erro} ({args.tema}). Instale as "
            "dependências do frontend (corepack pnpm@9 install em "
            "hospital-reunioes/frontend) ou aponte --tema para o theme.css do "
            "Tailwind da árvore principal.",
            file=sys.stderr,
        )
        return 1
    args.saida.parent.mkdir(parents=True, exist_ok=True)
    args.saida.write_text(tokens, encoding="utf-8")
    print(f"tokens gravados em {args.saida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
