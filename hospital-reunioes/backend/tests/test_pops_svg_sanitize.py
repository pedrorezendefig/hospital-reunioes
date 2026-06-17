"""Testes da sanitização do SVG do fluxograma (issue #153, ADR 0017).

O SVG do diagrama Mermaid é renderizado NO CLIENTE e persistido com a Versão;
o PDF (WeasyPrint) o embute cru. Um cliente autenticado malicioso poderia
POSTar um SVG com referências a arquivos locais ou URLs externas
(`<image href="file:///app/.env">`, `<use href="http://169.254.169.254/">`,
`<foreignObject>`, `<script>`, handlers `on*`) e transformar a geração do PDF
em leitura de arquivo local / SSRF. Como o ADR 0017 proíbe re-renderizar o
Mermaid no servidor, a defesa é SANITIZAR o SVG na entrada (antes de persistir).

`sanitizar_svg` parseia o SVG com um parser sem rede e sem entidades (anti-XXE),
remove elementos e atributos perigosos e re-serializa o markup limpo. SVG que
não parseia, ou cuja raiz não é `<svg>`, é rejeitado (`SvgInvalidoError`).

Estes testes fixam o contrato externo: o que é neutralizado e o que sobrevive
(um SVG típico do mermaid: path, rect, g, text, marker/gradiente com `url(#...)`
e ref de fragmento, mais o `<style>` interno do qual o diagrama depende).
"""

from __future__ import annotations

import re

import pytest

from app.services.pops_svg_sanitize import SvgInvalidoError, sanitizar_svg

# ─── SVG representativo do mermaid (estrutura real do export v11) ──────────────
# Reproduz os elementos que o mermaid emite e dos quais o desenho depende:
# <style> interno, <defs> com <marker> e <linearGradient>, nós com url(#...) e
# uma aresta com marker-end="url(#...)". É o "feliz" que deve sobreviver intacto.
SVG_MERMAID = (
    '<svg id="probe" width="200" height="120" viewBox="0 0 200 120"'
    ' xmlns="http://www.w3.org/2000/svg" class="flowchart">'
    "<style>#probe .node rect{fill:#EEF0FB;stroke:#2B2E7E;}"
    "#probe .marker{fill:#94A3B8;}@keyframes dash{to{stroke-dashoffset:0;}}</style>"
    "<defs>"
    '<marker id="probe_pointEnd" markerWidth="8" markerHeight="8" orient="auto">'
    '<path d="M0,0 L8,4 L0,8 z"/></marker>'
    '<linearGradient id="probe-gradient"><stop offset="0%" stop-color="#fff"/></linearGradient>'
    "</defs>"
    '<g class="root">'
    '<g class="node"><rect x="10" y="10" width="80" height="30" fill="url(#probe-gradient)"/>'
    '<text x="50" y="28">Inicio</text></g>'
    '<path class="flowchart-link" d="M50,40 L50,80" marker-end="url(#probe_pointEnd)"/>'
    '<g class="node"><rect x="10" y="80" width="80" height="30"/><text x="50" y="98">Fim</text></g>'
    "</g>"
    "</svg>"
)


def _xml(svg: str):
    """Re-parse do SVG limpo para inspecionar a árvore sem depender de string."""
    from lxml import etree

    return etree.fromstring(svg.encode("utf-8"), etree.XMLParser(resolve_entities=False, no_network=True))


def _localnames(root) -> set[str]:
    return {etree_localname(el.tag) for el in root.iter() if isinstance(el.tag, str)}


def etree_localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


# ═══════════════════════════════════════════════════════════════════════════
# O caminho feliz: um SVG legítimo do mermaid sobrevive íntegro
# ═══════════════════════════════════════════════════════════════════════════


class TestSvgLegitimoPreservado:
    def test_mermaid_tipico_sobrevive_e_continua_valido(self):
        limpo = sanitizar_svg(SVG_MERMAID)
        root = _xml(limpo)  # parseável => válido
        assert etree_localname(root.tag) == "svg"
        nomes = _localnames(root)
        # Os elementos estruturais do diagrama permanecem.
        for esperado in ("svg", "g", "rect", "path", "text", "defs", "marker", "linearGradient", "stop", "style"):
            assert esperado in nomes, f"{esperado} deveria sobreviver"

    def test_refs_de_fragmento_same_document_preservadas(self):
        """url(#...) (marcadores e gradientes do mermaid) é referência interna,
        não busca externa: tem que sobreviver, senão o diagrama perde setas e
        preenchimentos."""
        limpo = sanitizar_svg(SVG_MERMAID)
        assert "url(#probe-gradient)" in limpo
        assert 'marker-end="url(#probe_pointEnd)"' in limpo or "url(#probe_pointEnd)" in limpo
        assert 'id="probe_pointEnd"' in limpo
        assert 'id="probe-gradient"' in limpo

    def test_style_interno_preservado_sem_import_nem_url_externa(self):
        """O <style> do mermaid é mantido (o desenho depende dele), mas limpo:
        sem @import e sem url(...) que não seja fragmento."""
        svg = SVG_MERMAID.replace(
            "@keyframes dash{to{stroke-dashoffset:0;}}",
            "@import url('http://evil.test/x.css');#probe .bg{background:url('http://evil.test/p.png');}",
        )
        limpo = sanitizar_svg(svg)
        assert "@import" not in limpo
        assert "evil.test" not in limpo
        # O conteúdo legítimo do style continua lá.
        assert "#probe .node rect" in limpo

    def test_conteudo_textual_dos_nos_preservado(self):
        limpo = sanitizar_svg(SVG_MERMAID)
        assert "Inicio" in limpo
        assert "Fim" in limpo


# ═══════════════════════════════════════════════════════════════════════════
# Elementos perigosos removidos (leitura de arquivo local / SSRF / XSS)
# ═══════════════════════════════════════════════════════════════════════════


class TestElementosPerigososRemovidos:
    def test_image_com_file_uri_removida(self):
        """`<image href="file:///...">` faria o WeasyPrint ler arquivo local."""
        svg = SVG_MERMAID.replace(
            "</defs>", '</defs><image href="file:///app/.env" x="0" y="0" width="10" height="10"/>'
        )
        limpo = sanitizar_svg(svg)
        assert "<image" not in limpo
        assert "file:///app/.env" not in limpo
        assert "image" not in _localnames(_xml(limpo))

    def test_use_com_url_externa_removido(self):
        """`<use href="http://169.254.169.254/...">` é vetor de SSRF (metadata)."""
        svg = SVG_MERMAID.replace("</defs>", '</defs><use href="http://169.254.169.254/latest/meta-data/"/>')
        limpo = sanitizar_svg(svg)
        assert "<use" not in limpo
        assert "169.254.169.254" not in limpo

    def test_script_removido(self):
        svg = SVG_MERMAID.replace("</defs>", "</defs><script>fetch('http://evil.test')</script>")
        limpo = sanitizar_svg(svg)
        assert "<script" not in limpo
        assert "evil.test" not in limpo

    def test_foreign_object_removido(self):
        """`<foreignObject>` embute XHTML arbitrário; o WeasyPrint já o ignora no
        PDF, então removê-lo não muda o desenho e fecha a superfície. (XHTML
        bem-formado, como o mermaid emite: img auto-fechado.)"""
        svg = SVG_MERMAID.replace(
            "</defs>",
            '</defs><foreignObject width="10" height="10"><div xmlns="http://www.w3.org/1999/xhtml">'
            '<img src="http://evil.test/x.png"/></div></foreignObject>',
        )
        limpo = sanitizar_svg(svg)
        assert "foreignObject" not in _localnames(_xml(limpo))
        assert "evil.test" not in limpo

    def test_iframe_e_animacoes_com_href_removidos(self):
        svg = SVG_MERMAID.replace(
            "</defs>",
            '</defs><iframe src="http://evil.test"></iframe>'
            '<animate href="http://evil.test" attributeName="x"/>'
            '<set href="http://evil.test" attributeName="y"/>',
        )
        limpo = sanitizar_svg(svg)
        nomes = _localnames(_xml(limpo))
        for proibido in ("iframe", "animate", "set"):
            assert proibido not in nomes
        assert "evil.test" not in limpo

    def test_link_anchor_removido_mas_filhos_seguros_nao_precisam_sobreviver(self):
        """`<a href="http://...">` é removido (o link inteiro sai)."""
        svg = SVG_MERMAID.replace(
            "</defs>", '</defs><a href="http://evil.test"><rect x="0" y="0" width="1" height="1"/></a>'
        )
        limpo = sanitizar_svg(svg)
        assert "<a " not in limpo and "evil.test" not in limpo


# ═══════════════════════════════════════════════════════════════════════════
# Atributos perigosos neutralizados
# ═══════════════════════════════════════════════════════════════════════════


class TestAtributosPerigososRemovidos:
    def test_handlers_on_event_removidos(self):
        svg = SVG_MERMAID.replace('<rect x="10" y="10"', '<rect onload="alert(1)" onclick="x()" x="10" y="10"')
        limpo = sanitizar_svg(svg)
        assert "onload" not in limpo
        assert "onclick" not in limpo

    def test_href_externo_em_elemento_mantido_e_removido(self):
        """Um href externo num elemento que sobrevive (ex.: <rect>) é tirado, mas
        o elemento permanece (sem o atributo perigoso)."""
        svg = SVG_MERMAID.replace('<rect x="10" y="10"', '<rect href="http://evil.test" x="10" y="10"')
        limpo = sanitizar_svg(svg)
        assert "evil.test" not in limpo
        # O rect continua (só perdeu o href externo).
        assert "rect" in _localnames(_xml(limpo))

    def test_style_inline_com_url_externa_neutralizado(self):
        svg = SVG_MERMAID.replace(
            '<rect x="10" y="10"', '<rect style="fill:url(\'http://evil.test/p.png\')" x="10" y="10"'
        )
        limpo = sanitizar_svg(svg)
        assert "evil.test" not in limpo

    def test_style_inline_com_url_de_fragmento_preservado(self):
        """url(#id) inline é referência interna legítima: fica."""
        svg = SVG_MERMAID.replace('<rect x="10" y="10"', '<rect style="fill:url(#probe-gradient)" x="10" y="10"')
        limpo = sanitizar_svg(svg)
        assert "url(#probe-gradient)" in limpo

    def test_xlink_href_externo_removido(self):
        svg = SVG_MERMAID.replace(
            '<rect x="10" y="10"',
            '<rect xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="http://evil.test" x="10" y="10"',
        )
        limpo = sanitizar_svg(svg)
        assert "evil.test" not in limpo


# ═══════════════════════════════════════════════════════════════════════════
# Entrada inválida e anti-XXE
# ═══════════════════════════════════════════════════════════════════════════


class TestEntradaInvalida:
    def test_nao_svg_rejeitado(self):
        with pytest.raises(SvgInvalidoError):
            sanitizar_svg("<html><body>oi</body></html>")

    def test_string_lixo_rejeitada(self):
        with pytest.raises(SvgInvalidoError):
            sanitizar_svg("isto não é xml <<<")

    def test_vazio_rejeitado(self):
        with pytest.raises(SvgInvalidoError):
            sanitizar_svg("")

    def test_xxe_nao_resolve_entidade_externa(self):
        """DOCTYPE com entidade externa apontando para arquivo local NÃO pode ser
        resolvido (anti-XXE): ou rejeita, ou o conteúdo do arquivo nunca aparece
        no resultado."""
        ataque = (
            '<?xml version="1.0"?>'
            '<!DOCTYPE svg [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
            '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><text>&xxe;</text></svg>'
        )
        try:
            limpo = sanitizar_svg(ataque)
        except SvgInvalidoError:
            return  # rejeitar é aceitável
        assert "root:" not in limpo
        assert "/bin/" not in limpo


# ═══════════════════════════════════════════════════════════════════════════
# Idempotência e robustez
# ═══════════════════════════════════════════════════════════════════════════


class TestRobustez:
    def test_sanitizacao_e_idempotente(self):
        uma = sanitizar_svg(SVG_MERMAID)
        duas = sanitizar_svg(uma)
        # Re-sanitizar o já-limpo não muda mais nada de relevante.
        assert _localnames(_xml(uma)) == _localnames(_xml(duas))

    def test_resultado_nao_tem_quebra_de_linha_de_controle_perigosa(self):
        """Sanidade: a saída é uma string de SVG (começa com <svg após strip)."""
        limpo = sanitizar_svg(SVG_MERMAID).strip()
        assert re.match(r"^<svg[\s>]", limpo)
