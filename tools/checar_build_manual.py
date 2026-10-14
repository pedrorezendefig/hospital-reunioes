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
  ninguém perceber;
- a busca afinada (issue #1221): toda palavra de `busca:` chegou ao índice,
  todo resultado de página de módulo leva o `módulo`, toda página com
  `proximas:` mostra "Tarefas próximas" com os links certos, e a home abre com
  a barra "O que você quer fazer?" acima dos cartões.

Sem dependências externas. Uso: python3 tools/checar_build_manual.py [--dir docs/manual]
Sai com código 1 se houver qualquer violação.
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from lint_manual import ler_frontmatter, ler_lista  # noqa: E402


def url_da_pagina(relativo: Path) -> str:
    """A URL que o Starlight gera para um arquivo de conteúdo."""
    partes = list(relativo.with_suffix("").parts)
    if partes[-1] == "index":
        partes.pop()
    return "/" + "".join(f"{p}/" for p in partes)


def fragmentos_da_busca(dist: Path) -> dict[str, dict]:
    """URL -> fragmento do Pagefind (cada fragmento é um JSON comprimido).

    O fragmento guarda o texto que a busca indexou (`content`) e os metadados
    que o resultado mostra (`meta`).
    """
    fragmentos: dict[str, dict] = {}
    for fragmento in sorted((dist / "pagefind" / "fragment").glob("*.pf_fragment")):
        bruto = gzip.decompress(fragmento.read_bytes()).decode("utf-8")
        _, _, corpo = bruto.partition("{")
        dados = json.loads("{" + corpo)
        fragmentos[dados["url"]] = dados
    return fragmentos


def urls_da_busca(dist: Path) -> set[str]:
    """URLs indexadas pelo Pagefind."""
    return set(fragmentos_da_busca(dist))


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


class ColetorDeRotulos(HTMLParser):
    """Lê o texto de cada `<span class="group-label">` da sidebar.

    Procurar o literal `>nome<` no HTML inteiro era frágil demais para servir
    de trava: `>como-funciona </span>`, com um espaço, é o mesmo bug na tela e
    passava batido. Aqui o rótulo é lido do elemento que o Starlight usa para
    ele, com o texto normalizado, então espaço, quebra de linha, atributo a
    mais e tag aninhada não escondem nada.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rotulos: list[str] = []
        self._aninhamento = 0
        self._pedacos: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "span":
            return
        if self._aninhamento:
            self._aninhamento += 1
            return
        classes = (dict(attrs).get("class") or "").split()
        if "group-label" in classes:
            self._aninhamento = 1
            self._pedacos = []

    def handle_endtag(self, tag: str) -> None:
        if tag != "span" or not self._aninhamento:
            return
        self._aninhamento -= 1
        if self._aninhamento == 0:
            self.rotulos.append(" ".join("".join(self._pedacos).split()))

    def handle_data(self, dados: str) -> None:
        if self._aninhamento:
            self._pedacos.append(dados)


def rotulos_de_grupo(html: str) -> list[str]:
    """Os rótulos dos grupos da sidebar, na ordem em que a página os mostra."""
    coletor = ColetorDeRotulos()
    coletor.feed(html)
    return coletor.rotulos


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
    problemas: list[str] = []
    onde: dict[str, list[str]] = {}
    achou_algum_grupo = False

    for pagina in paginas:
        rotulos = rotulos_de_grupo(pagina.read_text(encoding="utf-8"))
        achou_algum_grupo = achou_algum_grupo or bool(rotulos)
        for rotulo in rotulos:
            if rotulo in pastas:
                onde.setdefault(rotulo, []).append(str(pagina.relative_to(dist)))

    if not achou_algum_grupo:
        # Piso de sanidade, o mesmo do ícone: a sidebar tem um grupo por módulo
        # em toda página do site, então zero rótulo achado é varredura
        # quebrada, não site sem grupo. Sem este piso, esta trava viraria vácuo
        # verde no dia em que o Starlight mudasse o `group-label` de lugar.
        problemas.append(
            "nenhum rótulo de grupo achado no dist: a varredura não está "
            "enxergando a sidebar."
        )

    problemas += [
        f"a sidebar mostra o nome cru da pasta '{nome}' em {len(paginas_com)} "
        f"página(s) do dist (ex.: {paginas_com[0]}). Dê um rótulo a ela em "
        "src/rotulos-da-sidebar.ts."
        for nome, paginas_com in sorted(onde.items())
    ]
    return problemas


class ColetorDeProximas(HTMLParser):
    """Lê o bloco `<nav class="tarefas-proximas">`: o texto e os links dele."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocos: list[tuple[str, set[str]]] = []
        self._aninhamento = 0
        self._pedacos: list[str] = []
        self._links: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        atributos = dict(attrs)
        if self._aninhamento:
            if tag == "nav":
                self._aninhamento += 1
            if tag == "a" and atributos.get("href"):
                self._links.add(atributos["href"] or "")
            return
        classes = (atributos.get("class") or "").split()
        if tag == "nav" and "tarefas-proximas" in classes:
            self._aninhamento = 1
            self._pedacos = []
            self._links = set()

    def handle_endtag(self, tag: str) -> None:
        if tag != "nav" or not self._aninhamento:
            return
        self._aninhamento -= 1
        if self._aninhamento == 0:
            self.blocos.append((" ".join("".join(self._pedacos).split()), self._links))

    def handle_data(self, dados: str) -> None:
        if self._aninhamento:
            self._pedacos.append(dados)


def blocos_de_proximas(html: str) -> list[tuple[str, set[str]]]:
    coletor = ColetorDeProximas()
    coletor.feed(html)
    return coletor.blocos


def publicada(conteudo: Path, modulo: str, slug: str) -> bool:
    for ext in (".md", ".mdx"):
        arquivo = conteudo / modulo / f"{slug}{ext}"
        if arquivo.is_file():
            campos = ler_frontmatter(arquivo.read_text(encoding="utf-8"))
            return campos.get("draft", "").lower() != "true"
    return False


TITULO_PROXIMAS = "Tarefas próximas"


def checar_busca_da_pagina(
    conteudo: Path, relativo: Path, fragmento: dict, html: Path
) -> list[str]:
    """Busca afinada de uma página publicada (issue #1221).

    - toda palavra de `busca:` está no texto que o Pagefind indexou;
    - página de módulo leva o `módulo` no metadado, que o resultado mostra;
    - `proximas:` virou o bloco "Tarefas próximas" com um link por tarefa
      publicada do módulo.
    """
    texto = (conteudo / relativo).read_text(encoding="utf-8")
    problemas: list[str] = []

    indexado = fragmento.get("content", "").lower()
    for palavra in ler_lista(texto, "busca"):
        if palavra.lower() not in indexado:
            problemas.append(
                f"{relativo}: a palavra de busca '{palavra}' não entrou no "
                "índice; quem digita isso não acha a página."
            )

    if len(relativo.parts) < 2:
        return problemas
    modulo = relativo.parts[0]
    no_resultado = (fragmento.get("meta") or {}).get("módulo", "")
    if not no_resultado or no_resultado == modulo:
        problemas.append(
            f"{relativo}: o resultado da busca não mostra o módulo "
            f"(metadado 'módulo' = '{no_resultado}'). O tema grava o nome do "
            "módulo, como no menu, em src/components/MarkdownContent.astro."
        )

    esperados = {
        f"/{modulo}/{slug}/"
        for slug in ler_lista(texto, "proximas")
        if publicada(conteudo, modulo, slug)
    }
    if esperados:
        blocos = blocos_de_proximas(html.read_text(encoding="utf-8"))
        bloco = next((b for b in blocos if TITULO_PROXIMAS in b[0]), None)
        if bloco is None:
            problemas.append(
                f"{relativo}: declara proximas e a página não mostra o bloco "
                f'"{TITULO_PROXIMAS}" no fim.'
            )
        elif bloco[1] != esperados:
            faltam = ", ".join(sorted(esperados - bloco[1])) or "nenhum"
            sobram = ", ".join(sorted(bloco[1] - esperados)) or "nenhum"
            problemas.append(
                f'{relativo}: "{TITULO_PROXIMAS}" não bate com proximas '
                f"(faltam: {faltam}; sobram: {sobram}). Tarefa em draft não "
                "vira link."
            )
    return problemas


RE_BARRA_DA_HOME = re.compile(r'class="[^"]*\bbusca-da-home\b')
RE_CARTOES = re.compile(r'class="[^"]*\bmodulos\b')
CHAMADA_DA_HOME = "O que você quer fazer?"


def checar_home(conteudo: Path, dist: Path) -> list[str]:
    """A home abre pela busca: a barra vem acima dos cartões de módulo."""
    if not any((conteudo / f"index{ext}").is_file() for ext in (".md", ".mdx")):
        return []
    home = dist / "index.html"
    if not home.is_file():
        return []  # o laço principal já cobra a página que não virou HTML
    html = home.read_text(encoding="utf-8")
    barra = RE_BARRA_DA_HOME.search(html)
    cartoes = RE_CARTOES.search(html)
    if (
        barra is None
        or cartoes is None
        or barra.start() > cartoes.start()
        or CHAMADA_DA_HOME not in html[barra.start() : cartoes.start()]
    ):
        return [
            f'a home não abre com a barra "{CHAMADA_DA_HOME}" acima dos cartões '
            "de módulo (src/content/docs/index.mdx)."
        ]
    return []


def checar(raiz: Path) -> list[str]:
    conteudo = raiz / "src" / "content" / "docs"
    dist = raiz / "dist"
    indexadas = fragmentos_da_busca(dist)
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
            else:
                problemas += checar_busca_da_pagina(
                    conteudo, relativo, indexadas[url], html
                )

    paginas = sorted(dist.rglob("*.html"))
    if not paginas:
        problemas.append("dist não tem nenhuma página HTML: o build não gerou site.")
    problemas += checar_icone(dist, paginas)
    problemas += checar_rotulos(conteudo, dist, paginas)
    problemas += checar_home(conteudo, dist)

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
