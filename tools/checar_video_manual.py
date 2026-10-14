#!/usr/bin/env python3
"""Confere os Vídeos de tarefa do Manual: fonte versionada, MP4 fora do git.

Desde a emenda de 13/10/2026 à ADR 0057 (issue #1230), confere também o
Estilo do manual em toda composição que não está na lista de pendentes de
rerender (`video/_estilo/pendentes-de-rerender.txt`) e nos cards de
`video/_estilo/cards/`: `VERIFY.md` ao lado da composição, nenhuma cor em hex
nem fonte fora dos tokens, e todo timeline pelo menos do tamanho do slot.

Uso: python3 tools/checar_video_manual.py [--dir docs/manual]
Sai com código 1 se houver qualquer violação.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from lint_manual import ler_frontmatter  # noqa: E402

RE_CARIMBO = re.compile(r'<script[^>]*id="manual-video-meta"[^>]*>(.*?)</script>', re.S)
CAMPOS_DO_CARIMBO = ["modulo", "slug", "pagina", "app_version", "gerado_em"]
# Pastas regeráveis: o que mora nelas não está no git e não é responsabilidade
# de ninguém (o `renders/` é onde o HyperFrames larga o MP4 quando ninguém diz
# o destino).
FORA_DA_VARREDURA = {"node_modules", "dist", ".astro", "renders"}

ESTILO = "_estilo"
PENDENTES = "pendentes-de-rerender.txt"
# Cor em hex de 3, 4, 6 ou 8 dígitos. O `&` de fora tira a entidade HTML
# (`&#233;`) e a borda depois tira o seletor de id (`#c-tarefa`, `#fone`).
RE_HEX = re.compile(
    r"(?<![&\w])#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3,4})(?![\w-])"
)
RE_FONTE = re.compile(r"\b(?:font-family|fontFamily|font)\s*:\s*([^;}\n]+)")
RE_REGISTRO = re.compile(
    r"window\.__timelines(?:\[\s*[\"']([\w-]+)[\"']\s*\]|\.([\w$]+))\s*=\s*([\w$]+)"
)


class _Composicoes(HTMLParser):
    """Os elementos com `data-composition-id`: a raiz e os hosts de card."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.elementos: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        atributos = {nome: valor or "" for nome, valor in attrs}
        if "data-composition-id" in atributos:
            self.elementos.append(atributos)


def _composicoes(html: str) -> list[dict[str, str]]:
    leitor = _Composicoes()
    leitor.feed(html)
    return leitor.elementos


def _duracao(valor: str) -> float:
    try:
        return float(valor)
    except ValueError:
        return 0.0


def _preenchimento(html: str, composicao: str) -> float:
    """Quanto dura, garantido, o timeline registrado no id: a âncora do slot.

    A lei do kit: todo timeline termina com `tl.to({}, { duration: N }, 0)`.
    Sem ela o tamanho real depende do último tween, e o conferidor não roda o
    GSAP; com ela o número está escrito e dá para comparar com o slot.
    """
    for registro in RE_REGISTRO.finditer(html):
        if composicao not in (registro.group(1), registro.group(2)):
            continue
        variavel = re.escape(registro.group(3))
        ancoras = re.findall(
            rf"\b{variavel}\s*\.to\(\s*\{{\s*\}}\s*,\s*\{{\s*duration\s*:\s*([\d.]+)\s*\}}\s*,\s*0\s*\)",
            html,
        )
        return max((float(a) for a in ancoras), default=0.0)
    return 0.0


def _cor_e_fonte(html: str, rotulo: str) -> list[str]:
    problemas = [
        f"{rotulo}: cor fixa {cor} fora dos tokens. Use a var() do token em "
        "video/_estilo/tokens.css, que sai do globals.css do app pelo "
        "tools/gerar_tokens_video.py (emenda de 13/10/2026 à ADR 0057)."
        for cor in dict.fromkeys(RE_HEX.findall(html))
    ]
    for valor in dict.fromkeys(v.strip() for v in RE_FONTE.findall(html)):
        if "var(--font-" not in valor:
            problemas.append(
                f"{rotulo}: fonte '{valor}' fora dos tokens. Use var(--font-app) "
                "ou outra --font-* do video/_estilo/tokens.css."
            )
    return problemas


def _timeline_curto(rotulo: str, composicao: str, dura: float, slot: float) -> list[str]:
    if dura >= slot:
        return []
    return [
        f"{rotulo}: o timeline de '{composicao}' garante {dura:g}s e o slot pede "
        f"{slot:g}s. Termine o timeline com tl.to({{}}, {{ duration: {slot:g} }}, 0) "
        "para ele preencher o slot inteiro, sem quadro preto no fim."
    ]


def _gates_da_composicao(arquivo: Path, rotulo: str) -> list[str]:
    """Cor, fonte e timeline da raiz e de cada card montado nela."""
    html = arquivo.read_text(encoding="utf-8")
    problemas = _cor_e_fonte(html, rotulo)
    elementos = _composicoes(html)
    if not elementos:
        return problemas + [f"{rotulo}: sem elemento raiz com data-composition-id."]
    raiz, hosts = elementos[0], elementos[1:]
    problemas += _timeline_curto(
        rotulo,
        raiz["data-composition-id"],
        _preenchimento(html, raiz["data-composition-id"]),
        _duracao(raiz.get("data-duration", "")),
    )
    for host in hosts:
        fonte = host.get("data-composition-src", "")
        if not fonte:
            continue
        card = arquivo.parent / fonte
        rotulo_card = f"{rotulo.rsplit('/', 1)[0]}/{fonte}"
        if not card.is_file():
            problemas.append(f"{rotulo}: monta '{fonte}', que não existe.")
            continue
        html_card = card.read_text(encoding="utf-8")
        problemas += _cor_e_fonte(html_card, rotulo_card)
        problemas += _timeline_curto(
            rotulo_card,
            host["data-composition-id"],
            _preenchimento(html_card, host["data-composition-id"]),
            _duracao(host.get("data-duration", "")),
        )
    return problemas


def _pendentes(raiz: Path) -> set[tuple[str, str]]:
    lista = raiz / "video" / ESTILO / PENDENTES
    if not lista.is_file():
        return set()
    linhas = (linha.strip() for linha in lista.read_text(encoding="utf-8").splitlines())
    return {
        tuple(linha.split("/", 1))  # type: ignore[misc]
        for linha in linhas
        if linha and not linha.startswith("#") and "/" in linha
    }


def checar(raiz: Path) -> list[str]:
    conteudo = raiz / "src" / "content" / "docs"
    problemas: list[str] = []
    exibidas: set[tuple[str, str]] = set()
    pendentes = _pendentes(raiz)

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

        # Compor um vídeo novo começa copiando a pasta de um pronto, e o carimbo
        # vem colado junto. Preenchido com os dados do vídeo antigo, ele passa
        # por completo e mente sobre que tela o vídeo retrata.
        esperado = {"modulo": modulo, "slug": slug, "pagina": str(relativo)}
        divergentes = [
            f"{campo}: '{carimbo[campo]}' no lugar de '{valor}'"
            for campo, valor in esperado.items()
            if carimbo.get(campo) and carimbo[campo] != valor
        ]
        if divergentes:
            problemas.append(
                f"video/{modulo}/{slug}/index.html: carimbo de outra página "
                f"({'; '.join(divergentes)}). Copiar a pasta de uma composição "
                "pronta traz o carimbo do vídeo antigo: troque os campos pelos "
                "desta tarefa (ADR 0057, decisão 3)."
            )

        if (modulo, slug) in pendentes:
            continue  # vídeo de antes do estilo: a campanha de rerender refaz
        if not (composicao.parent / "VERIFY.md").is_file():
            problemas.append(
                f"video/{modulo}/{slug}: sem VERIFY.md. Grave ao lado da "
                "composição o que foi conferido (strips de cada corte, check, "
                "quadros olhados) antes do OK humano (emenda de 13/10/2026 à "
                "ADR 0057)."
            )
        problemas += _gates_da_composicao(composicao, f"video/{modulo}/{slug}/index.html")

    for card in sorted((raiz / "video" / ESTILO / "cards").glob("*/index.html")):
        problemas += _gates_da_composicao(card, f"video/{ESTILO}/cards/{card.parent.name}")

    for pasta in sorted((raiz / "video").glob("*/*")):
        if not pasta.is_dir() or pasta.parent.name == ESTILO:
            continue
        if (pasta.parent.name, pasta.name) not in exibidas:
            problemas.append(
                f"video/{pasta.parent.name}/{pasta.name}: composição que página "
                "nenhuma exibe. Aponte uma Página de tarefa para ela pelo campo "
                "`video` do frontmatter, ou apague a pasta."
            )

    for rendido in sorted(raiz.rglob("*.mp4")):
        if any(parte in FORA_DA_VARREDURA for parte in rendido.parts):
            continue
        if rendido.parent.parent == raiz / "public" / "video":
            continue  # destino do render, fora do git pelo .gitignore do site
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
