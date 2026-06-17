"""Sanitização do SVG do fluxograma antes de persistir (issue #153, ADR 0017).

O diagrama Mermaid é renderizado NO CLIENTE e o SVG é persistido com a Versão;
o PDF (WeasyPrint) embute esse SVG cru. WeasyPrint resolve referências externas
(`file://`, `http://`) ao desenhar, então um SVG hostil vindo de um cliente
autenticado viraria leitura de arquivo local ou SSRF na geração do PDF
(`<image href="file:///app/.env">`, `<use href="http://169.254.169.254/">`,
`<foreignObject>`, `<script>`, handlers `on*`). Como o ADR 0017 proíbe
re-renderizar o Mermaid no servidor (sem Chromium), a defesa fica na ENTRADA:
sanitizar o SVG antes de gravar.

A sanitização:
1. Parseia com um parser sem rede e sem entidades (anti-XXE/SSRF no próprio
   parse). Falha de parse, ou raiz que não é `<svg>`, vira `SvgInvalidoError`
   (o endpoint responde 400 e não persiste).
2. Remove elementos perigosos por localname (ignorando namespace): `script`,
   `foreignObject`, `iframe`, `image`, `use`, `a`, `animate`, `animateMotion`,
   `animateTransform`, `set`. O `<foreignObject>` some sem prejuízo visual: o
   WeasyPrint já ignora o XHTML dele no PDF.
3. Remove atributos perigosos em todos os elementos: handlers `on*`; qualquer
   `href`/`xlink:href`/`src`/`action`/`formaction` cujo valor não comece com `#`
   (referência de fragmento same-document, que o mermaid usa em marcadores e
   gradientes, é preservada); e em `style=` (inline), neutraliza `url(...)` que
   não seja `url(#...)`.
4. Mantém o `<style>` interno do qual o desenho depende, mas limpa o CSS (sem
   `@import`, sem `url(...)` externa).
5. Re-serializa o SVG limpo. É esse markup, não o original, que se persiste.
"""

from __future__ import annotations

import re

from lxml import etree

XHTML_NS = "http://www.w3.org/1999/xhtml"

# Elementos que não têm razão de existir num diagrama de fluxo e abrem porta a
# carga externa / execução. Comparados por localname (sem namespace).
_TAGS_PROIBIDAS: frozenset[str] = frozenset(
    {
        "script",
        "foreignobject",
        "iframe",
        "image",
        "use",
        "a",
        "animate",
        "animatemotion",
        "animatetransform",
        "set",
    }
)

# Atributos que carregam referência a recurso: só sobrevivem se o valor for uma
# âncora de fragmento (`#...`), referência interna ao próprio documento.
_ATTRS_REFERENCIA: frozenset[str] = frozenset({"href", "src", "action", "formaction"})

# url(...) que NÃO é url(#fragmento): busca externa, neutralizada no CSS/style.
_URL_EXTERNA = re.compile(r"url\(\s*['\"]?\s*(?!#)[^)]*\)", re.IGNORECASE)
# @import em CSS: sempre carrega recurso externo.
_AT_IMPORT = re.compile(r"@import[^;]*;?", re.IGNORECASE)


class SvgInvalidoError(ValueError):
    """O conteúdo não é um SVG parseável (ou a raiz não é `<svg>`)."""


def _localname(tag) -> str:
    """Localname sem namespace e em minúsculas (`{ns}rect` -> `rect`). Tags de
    comentário/PI do lxml (callables) viram string vazia."""
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1].lower()


def _attr_localname(nome: str) -> str:
    return nome.rsplit("}", 1)[-1].lower()


def _limpar_css(texto: str | None) -> str:
    """Remove `@import` e `url(...)` externa de um trecho de CSS, preservando
    `url(#fragmento)` e o resto das regras."""
    if not texto:
        return ""
    texto = _AT_IMPORT.sub("", texto)
    texto = _URL_EXTERNA.sub("none", texto)
    return texto


def _sanitizar_elemento(el) -> None:
    """Limpa um elemento in-place: remove filhos proibidos (recursivo), limpa o
    `<style>` e tira os atributos perigosos."""
    # 1. Remove filhos proibidos antes de descer (não sanitiza o que vai sair).
    for filho in list(el):
        if _localname(filho.tag) in _TAGS_PROIBIDAS:
            el.remove(filho)
        else:
            _sanitizar_elemento(filho)

    # 2. <style>: mantém, mas limpa o CSS (sem @import nem url externa).
    if _localname(el.tag) == "style":
        el.text = _limpar_css(el.text)

    # 3. Atributos perigosos.
    for nome, valor in list(el.attrib.items()):
        local = _attr_localname(nome)
        if local.startswith("on"):
            del el.attrib[nome]
            continue
        if local in _ATTRS_REFERENCIA and not (valor or "").lstrip().startswith("#"):
            del el.attrib[nome]
            continue
        if local == "style":
            limpo = _URL_EXTERNA.sub("none", valor or "")
            if limpo != valor:
                el.attrib[nome] = limpo


def sanitizar_svg(svg: str) -> str:
    """Sanitiza o SVG do fluxograma e devolve o markup limpo (ADR 0017).

    Levanta `SvgInvalidoError` se o conteúdo não parsear como XML ou se a raiz
    não for `<svg>` — o caller responde 400 e não persiste. Caso contrário,
    remove elementos/atributos perigosos e re-serializa.
    """
    if not isinstance(svg, str) or not svg.strip():
        raise SvgInvalidoError("SVG vazio")

    # Parser endurecido: sem resolução de entidades (anti-XXE) e sem rede; não
    # carrega DTD. É a primeira linha de defesa, já no parse.
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
    try:
        root = etree.fromstring(svg.encode("utf-8"), parser)
    except etree.XMLSyntaxError as e:
        raise SvgInvalidoError(f"SVG não parseável: {e}") from e

    if root is None or _localname(root.tag) != "svg":
        raise SvgInvalidoError("a raiz do documento não é <svg>")

    _sanitizar_elemento(root)

    return etree.tostring(root, encoding="unicode")
