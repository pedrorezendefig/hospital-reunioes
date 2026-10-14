#!/usr/bin/env python3
"""Confere o vídeo do Manual: fonte versionada, MP4 fora do git.

Desde a issue #1260 (emenda de 14/10/2026 à ADR 0057) o vídeo do Manual é o
Vídeo de visão geral, um por módulo, na abertura do módulo
(`<modulo>/index.md`). A página inicial mostra o de Primeiros passos, então a
composição dela mora em `video/primeiros-passos/`. Página de tarefa não exibe
vídeo: o campo `video` fora da abertura é recusado, porque o tema não o
desenha e ele sumiria calado.

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
RE_ESTILO = re.compile(r"<style\b[^>]*>(.*?)</style>", re.S | re.I)
RE_SELETOR_DE_CLASSE = re.compile(r"\.([A-Za-z_][\w-]*)")
RE_ATRIBUTO_CLASS = re.compile(r'\bclass="([^"]*)"')
RE_REGISTRO = re.compile(
    r"window\.__timelines(?:\[\s*[\"']([\w-]+)[\"']\s*\]|\.([\w$]+))\s*=\s*([\w$]+)"
)


class _Elementos(HTMLParser):
    """Os elementos com tempo ou com `data-composition-id` (raiz, clipes, hosts)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.elementos: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        atributos = {nome: valor or "" for nome, valor in attrs}
        if "data-start" in atributos or "data-composition-id" in atributos:
            self.elementos.append(atributos)


def elementos(html: str) -> list[dict[str, str]]:
    """Também usado pelo tools/strips_video_manual.py para achar os cortes."""
    leitor = _Elementos()
    leitor.feed(html)
    return leitor.elementos


def _composicoes(html: str) -> list[dict[str, str]]:
    return [e for e in elementos(html) if "data-composition-id" in e]


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


def _classes_da_raiz(html: str) -> set[str]:
    """As classes que o `<style>` da composição estiliza."""
    css = " ".join(RE_ESTILO.findall(html))
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    css = re.sub(r"url\([^)]*\)", "", css)  # o `.ttf` da fonte não é classe
    return set(RE_SELETOR_DE_CLASSE.findall(css))


def _classes_em_comum(raiz: str, card: str, rotulo_card: str) -> list[str]:
    """Regra de classe da raiz que pega um elemento do card montado.

    Depois de montado, o card divide a página com a réplica da tela: um `.tela`
    da réplica também posiciona o `.tela` do lower-third (issue #1231).
    """
    usadas = {c for attr in RE_ATRIBUTO_CLASS.findall(card) for c in attr.split()}
    return [
        f"{rotulo_card}: a composição estiliza .{classe}, que é também uma classe "
        "do card, e a regra da réplica deforma o card montado. Dê à classe da "
        "réplica um nome próprio (por exemplo, .ap-" + classe + ")."
        for classe in sorted(_classes_da_raiz(raiz) & usadas)
    ]


def _timeline_curto(
    rotulo: str, composicao: str, dura: float, slot: float
) -> list[str]:
    if dura >= slot:
        return []
    return [
        (
            f"{rotulo}: o timeline de '{composicao}' garante {dura:g}s e o slot pede "
            f"{slot:g}s. Termine o timeline com tl.to({{}}, {{ duration: {slot:g} }}, 0) "
            "para ele preencher o slot inteiro, sem quadro preto no fim."
        )
    ]


def _gates_da_composicao(arquivo: Path, rotulo: str) -> list[str]:
    """Cor, fonte e timeline da raiz e de cada card montado nela."""
    html = arquivo.read_text(encoding="utf-8")
    problemas = _cor_e_fonte(html, rotulo)
    composicoes = _composicoes(html)
    if not composicoes:
        return problemas + [f"{rotulo}: sem elemento raiz com data-composition-id."]
    raiz, hosts = composicoes[0], composicoes[1:]
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
        problemas += _classes_em_comum(html, html_card, rotulo_card)
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


# A página inicial não é de módulo nenhum e mostra o vídeo de Primeiros passos.
MODULO_DA_PAGINA_INICIAL = "primeiros-passos"


def modulo_da_abertura(relativo: Path) -> str | None:
    """O módulo cuja abertura é esta página, ou None se ela não é abertura.

    Também usado pelo tools/tirar_draft_manual.py para achar o MP4.
    """
    if relativo.stem != "index":
        return None
    if len(relativo.parts) == 1:
        return MODULO_DA_PAGINA_INICIAL
    if len(relativo.parts) == 2:
        return relativo.parts[0]
    return None


def checar(raiz: Path) -> list[str]:
    conteudo = raiz / "src" / "content" / "docs"
    problemas: list[str] = []
    # (modulo, slug) -> as páginas que exibem o vídeo
    exibidas: dict[tuple[str, str], list[str]] = {}
    pendentes = _pendentes(raiz)

    for arquivo in sorted(conteudo.rglob("*.md*")):
        if arquivo.suffix not in (".md", ".mdx"):
            continue
        relativo = arquivo.relative_to(conteudo)
        slug = ler_frontmatter(arquivo.read_text(encoding="utf-8")).get("video", "")
        if not slug:
            continue
        modulo = modulo_da_abertura(relativo)
        if modulo is None:
            problemas.append(
                f"{relativo}: declara o vídeo '{slug}' e não é a abertura de um "
                "módulo. O Manual tem um Vídeo de visão geral por módulo, na "
                "abertura (<modulo>/index.md); Página de tarefa não exibe vídeo "
                "(emenda de 14/10/2026 à ADR 0057). Tire o campo `video`."
            )
            continue
        exibidas.setdefault((modulo, slug), []).append(str(relativo))

    for (modulo, slug), paginas in sorted(exibidas.items()):
        composicao = raiz / "video" / modulo / slug / "index.html"
        if not composicao.is_file():
            problemas.append(
                f"{', '.join(paginas)}: exibe o vídeo '{slug}' e não tem "
                f"composição em video/{modulo}/{slug}/index.html. O MP4 fica "
                "fora do git: sem a composição, ninguém regera o vídeo (ADR "
                "0057, decisão 3)."
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
        # A página inicial divide o vídeo com a abertura de Primeiros passos: o
        # carimbo aponta uma das duas.
        esperado = {"modulo": modulo, "slug": slug}
        divergentes = [
            f"{campo}: '{carimbo[campo]}' no lugar de '{valor}'"
            for campo, valor in esperado.items()
            if carimbo.get(campo) and carimbo[campo] != valor
        ]
        if carimbo.get("pagina") and carimbo["pagina"] not in paginas:
            divergentes.append(
                f"pagina: '{carimbo['pagina']}' no lugar de '{' ou '.join(paginas)}'"
            )
        if divergentes:
            problemas.append(
                f"video/{modulo}/{slug}/index.html: carimbo de outra página "
                f"({'; '.join(divergentes)}). Copiar a pasta de uma composição "
                "pronta traz o carimbo do vídeo antigo: troque os campos pelos "
                "deste vídeo (ADR 0057, decisão 3)."
            )

        if (modulo, slug) in pendentes:
            continue  # vídeo de antes do estilo: a campanha de rerender refaz
        if not (composicao.parent / "VERIFY.md").is_file():
            problemas.append(
                f"video/{modulo}/{slug}: sem VERIFY.md. Grave ao lado da "
                "composição o que foi conferido (strips de cada corte, check, "
                "quadros olhados) antes do render final (emenda de 13/10/2026 à "
                "ADR 0057)."
            )
        problemas += _gates_da_composicao(
            composicao, f"video/{modulo}/{slug}/index.html"
        )

    for card in sorted((raiz / "video" / ESTILO / "cards").glob("*/index.html")):
        problemas += _gates_da_composicao(
            card, f"video/{ESTILO}/cards/{card.parent.name}"
        )

    for pasta in sorted((raiz / "video").glob("*/*")):
        if not pasta.is_dir() or pasta.parent.name == ESTILO:
            continue
        if (pasta.parent.name, pasta.name) not in exibidas:
            problemas.append(
                f"video/{pasta.parent.name}/{pasta.name}: composição que página "
                "nenhuma exibe. Aponte a abertura do módulo para ela pelo campo "
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
            "Conferidor do vídeo do Manual falhou:\n"
            + "\n".join(f"  - {p}" for p in problemas),
            file=sys.stderr,
        )
        return 1
    print("Vídeos do Manual OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
