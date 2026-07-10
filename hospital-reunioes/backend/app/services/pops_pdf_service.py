"""Documento oficial do POP em PDF — WeasyPrint, como a Ata (issue #86).

As seções dinâmicas do POP (ADR 0016) com identidade visual HSM. A seção de
fluxograma é Mermaid (ADR 0017): o SVG renderizado no cliente é capturado e
persistido com a Versão (campo `svg` da seção), e o PDF EMBUTE esse SVG
diretamente (WeasyPrint suporta SVG; sem render de diagrama no servidor, sem
Chromium, sem serviço externo, por privacidade self-hosted). Sem SVG (ainda
não capturado ou Mermaid inválido), o PDF cai no texto bruto, sem quebrar.

Nomenclatura travada do DRF §3.3:
`HSM_[SETOR]-[NNN]_[NOME-ABREVIADO]_v[VERSÃO]_[AAAAMM]_[STATUS].pdf`.
"""

from __future__ import annotations

import io
import ipaddress
import logging
import os
import re
import socket
import unicodedata
from datetime import datetime
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)

CRITICIDADE_LABELS = {"CRITICA": "Crítica", "ALTA": "Alta", "MEDIA": "Média"}
PERIODICIDADE_LABELS = {"3_meses": "3 meses", "6_meses": "6 meses", "1_ano": "1 ano", "2_anos": "2 anos"}
ESTADO_LABELS = {
    "A_ELABORAR": "A Elaborar",
    "EM_ELABORACAO": "Em Elaboração",
    "EM_REVISAO": "Em Revisão",
    "EM_VALIDACAO": "Em Validação",
    "EM_ASSINATURA": "Em Assinatura",
    "PUBLICADO": "Publicado",
}

# ─── Nomenclatura travada (DRF §3.3) ─────────────────────────────────────────

# Palavras de ligação que saem do NOME-ABREVIADO do arquivo.
_STOPWORDS_NOME = frozenset(
    "a o as os à às ao aos de da do das dos e em no na nos nas um uma para por com pela pelo pelas pelos".split()
)
_MAX_NOME_ABREVIADO = 40


def _ascii_fold(texto: str) -> str:
    """Remove acentos/diacríticos (Higienização → Higienizacao)."""
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")


def nome_abreviado(nome: str, max_len: int = _MAX_NOME_ABREVIADO) -> str:
    """`Higienização das Mãos` → `Higienizacao-Maos`: Title-Case com hífens,
    ASCII puro, sem stopwords, truncado em fronteira de palavra."""
    palavras = [p for p in re.split(r"\W+", nome) if p]
    uteis = [p for p in palavras if p.lower() not in _STOPWORDS_NOME] or palavras
    partes: list[str] = []
    for palavra in uteis:
        plana = _ascii_fold(palavra)
        if not plana:
            continue
        formatada = plana[0].upper() + plana[1:]
        if partes and len("-".join([*partes, formatada])) > max_len:
            break
        partes.append(formatada)
    return "-".join(partes)


def nome_arquivo_pop(
    *,
    codigo: str,
    nome: str,
    numero_versao: str,
    status: str = "PRELIMINAR",
    quando: datetime | None = None,
) -> str:
    """Nome travado do DRF: o Código já carrega `HSM_[SIGLA]-[NNN]`; AAAAMM é
    a competência da geração; o ASSINADO chega na fatia de publicação."""
    quando = quando or datetime.now()
    nome_arquivo = f"{codigo}_{nome_abreviado(nome)}_v{numero_versao}_{quando.strftime('%Y%m')}_{status}.pdf"
    # O nome vai em header HTTP (Content-Disposition) e no ClickSign (fatia de
    # assinatura): ASCII imprimível por construção, garantido no boundary —
    # Starlette não valida CRLF em headers (security-review #108).
    return re.sub(r'[^\x20-\x7e]|["\\]', "", nome_arquivo)


# ─── Markdown das seções de texto → HTML (linguagem visual da Ata) ───────────

# Allowlist apertada do HTML que sai do markdown da seção. O conteúdo vem do
# LLM (que lê Materiais de referência enviados pelo usuário), então HTML cru
# iria parar no WeasyPrint: `<img src="file:///app/.env">` ou um host interno
# faria leitura de arquivo local / SSRF na geração do PDF. Higienizamos com
# bleach antes de devolver. SEM img, script, style, iframe, object, embed, svg:
# isso remove qualquer fetch dirigido por conteúdo (security-review do PR #161).
_TAGS_PERMITIDAS = frozenset(
    {
        "p",
        "strong",
        "em",
        "b",
        "i",
        "u",
        "s",
        "ul",
        "ol",
        "li",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "blockquote",
        "code",
        "pre",
        "br",
        "hr",
        "table",
        "thead",
        "tbody",
        "tr",
        "th",
        "td",
        "a",
    }
)
_PROTOCOLOS_PERMITIDOS = ["http", "https"]
# Esquemas de href aceitos. Vazio = link relativo/âncora. Um filtro próprio
# (não só o `protocols` do bleach) porque o bleach deixa passar payloads de
# token único como `javascript:1` (o `1` não casa a heurística de URL dele);
# checamos o esquema explicitamente para fechar essa brecha.
_ESQUEMAS_HREF_OK = frozenset({"", "http", "https"})


def _atributo_permitido(tag: str, nome: str, valor: str) -> bool:
    """Allowlist de atributos para o bleach. Em `a/href`, só esquema seguro
    (http/https/relativo); `a/title` e `th|td/align` liberados; resto removido."""
    from urllib.parse import urlsplit

    if tag == "a" and nome == "href":
        return urlsplit(valor).scheme.lower() in _ESQUEMAS_HREF_OK
    if tag == "a" and nome == "title":
        return True
    if tag in ("th", "td") and nome == "align":
        return True
    return False


def markdown_secao_html(conteudo: str) -> str:
    """Converte o conteúdo markdown de uma seção de texto em HTML higienizado
    (negrito, listas, blocos), o mesmo vocabulário visual da Ata.

    Reaproveita a lib `markdown`: `extra` cobre listas, negrito e tabelas;
    `nl2br` faz a quebra simples de linha virar `<br>` (preserva a sensação de
    quebras que o autor digita em prosa corrida). A saída passa por
    `bleach.clean` com allowlist apertada (sem img/script/iframe/...): tags e
    atributos fora da lista são removidos e protocolos fora de http/https saem
    do href, fechando o vetor de leitura de arquivo local / SSRF no WeasyPrint.
    Conteúdo vazio vira string vazia, para a microcopy de "seção ainda não
    elaborada" assumir no template. O CSS do `.topico` (left-border,
    espaçamento) é aplicado pelo container no template; aqui só sai o HTML.
    """
    import bleach
    import markdown as _markdown

    texto = (conteudo or "").strip()
    if not texto:
        return ""
    bruto = _markdown.markdown(texto, extensions=["extra", "nl2br", "sane_lists"])
    return bleach.clean(
        bruto,
        tags=_TAGS_PERMITIDAS,
        attributes=_atributo_permitido,
        protocols=_PROTOCOLOS_PERMITIDOS,
        strip=True,
    )


# ─── url_fetcher do PDF: defesa em profundidade contra file:// / SSRF ────────


def _host_e_privado(host: str) -> bool:
    """True se o host resolve para um endereço privado, loopback ou link-local
    (127.0.0.0/8, 10/8, 172.16/12, 192.168/16, 169.254/16, ::1, fc00::/7...).
    Resolve nomes (localhost e DNS apontando para rede interna) antes de julgar.
    """
    if not host:
        return True
    host = host.strip("[]")
    candidatos: list[str] = []
    try:
        candidatos.append(str(ipaddress.ip_address(host)))
    except ValueError:
        try:
            infos = socket.getaddrinfo(host, None)
            candidatos.extend(info[4][0] for info in infos)
        except (OSError, UnicodeError):
            # Não resolveu: trata como não confiável (fail-closed).
            return True
    for endereco in candidatos:
        try:
            ip = ipaddress.ip_address(endereco.split("%")[0])
        except ValueError:
            return True
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_unspecified:
            return True
    return False


def _pdf_url_fetcher(url: str, allowed_file_uris: frozenset[str] = frozenset()):
    """url_fetcher do WeasyPrint para o PDF do POP. Recusa todo `file://` que
    não seja um asset legítimo do template (logo/fonte do próprio app) e todo
    host privado/loopback/link-local, fechando o vetor de leitura de arquivo
    local / SSRF. O conteúdo já é higienizado pelo bleach; isto é a segunda
    camada. Levanta `ValueError` no que recusa; delega o resto ao fetcher
    padrão do WeasyPrint.
    """
    from weasyprint import default_url_fetcher

    partes = urlsplit(url)
    esquema = partes.scheme.lower()

    if esquema == "file":
        if url in allowed_file_uris:
            return default_url_fetcher(url)
        raise ValueError(f"file:// não permitido no PDF do POP: {url}")

    if esquema in ("http", "https"):
        if _host_e_privado(partes.hostname or ""):
            raise ValueError(f"host privado/loopback recusado no PDF do POP: {url}")
        return default_url_fetcher(url)

    if esquema == "data":
        return default_url_fetcher(url)

    raise ValueError(f"esquema de URL não permitido no PDF do POP: {esquema or url}")


# ─── Geração do PDF ──────────────────────────────────────────────────────────


def gerar_pdf_pop(*, pop: dict, setor: dict, versao: dict, nomes_designados: dict[str, str | None]) -> bytes:
    """Renderiza o documento institucional do POP (seções dinâmicas) e devolve os
    bytes do PDF — mesma mecânica de `gerar_pdf_ata` (template + WeasyPrint).
    """
    # Lazy como no pipeline (orchestrator): o WeasyPrint exige libs nativas
    # (glib/pango) que não existem em todo ambiente de teste — só quem gera
    # PDF de fato paga o import.
    from weasyprint import HTML

    from app.services.pdf_generator import env, formatar_data

    template = env.get_template("pop_template.html")
    # Estrutura dinâmica (ADR 0016): o rascunho é uma lista ordenada de seções.
    # Rascunho legado (chaves fixas) é migrado na leitura — POPs em andamento
    # antes da mudança seguem renderizando. A numeração começa em 2 (a seção 1,
    # Identificação, é do cabeçalho). As seções de texto têm o markdown
    # convertido para HTML com a linguagem visual da Ata; a seção de fluxograma
    # (ADR 0017) embute o SVG capturado no cliente (campo `svg`), e sem SVG
    # (ainda não capturado ou Mermaid inválido) cai no texto bruto.
    from app.services.pops_secoes import migrar_rascunho_legado

    rascunho = migrar_rascunho_legado(versao.get("rascunho"))

    from app.models.pops_fluxograma import fluxograma_texto_fallback

    secoes = []
    for indice, secao_rascunho in enumerate(rascunho["secoes"], start=2):
        bruto = secao_rascunho.get("conteudo")
        if isinstance(bruto, dict):
            # Fluxograma como objeto da gramática restrita (ADR 0024): o texto
            # de fallback (sem SVG capturado) é a lista numerada derivada do
            # objeto, não o dump do JSON.
            conteudo = fluxograma_texto_fallback(bruto)
        else:
            conteudo = (bruto or "").strip()
        secao = {
            "numero": indice,
            "titulo": secao_rascunho.get("titulo") or "",
            "tipo": secao_rascunho.get("tipo") or "texto",
            "conteudo": conteudo,
        }
        if secao["tipo"] == "fluxograma":
            svg = secao_rascunho.get("svg")
            secao["svg"] = svg if isinstance(svg, str) and svg.strip() else None
        else:
            secao["conteudo_html"] = markdown_secao_html(conteudo)
        secoes.append(secao)

    # Caminhos absolutos (sem `..`) para a URI `file://` bater exatamente com o
    # allowlist do url_fetcher, mesmo após a normalização do WeasyPrint.
    logo_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "static", "images", "logo_hospital.png"))
    font_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "static", "fonts", "HPSimplified_Rg.ttf"))
    if not os.path.exists(font_path):
        logger.warning(f"Fonte HPSimplified_Rg.ttf não encontrada em {font_path}; PDF usará fallback do sistema")
        font_path = None

    logo_uri = f"file://{logo_path}"
    font_uri = f"file://{font_path}" if font_path else None
    assets_permitidos = frozenset(uri for uri in (logo_uri, font_uri) if uri)

    html_content = template.render(
        pop=pop,
        setor=setor,
        versao=versao,
        secoes=secoes,
        nomes=nomes_designados,
        criticidade_label=CRITICIDADE_LABELS.get(pop.get("criticidade"), pop.get("criticidade")),
        periodicidade_label=PERIODICIDADE_LABELS.get(
            pop.get("periodicidade_revisao"), pop.get("periodicidade_revisao")
        ),
        estado_label=ESTADO_LABELS.get(versao.get("estado"), versao.get("estado")),
        data_criacao=formatar_data(str(pop.get("created_at") or "")[:10]),
        data_geracao=datetime.now().strftime("%d/%m/%Y às %H:%M"),
        logo_path=logo_uri,
        font_path=font_uri,
    )

    # Defesa em profundidade: além do bleach no conteúdo, o fetcher recusa
    # qualquer file:// fora dos assets do template e qualquer host privado.
    def _fetcher(url: str):
        return _pdf_url_fetcher(url, assets_permitidos)

    pdf_file = io.BytesIO()
    HTML(string=html_content).write_pdf(target=pdf_file, url_fetcher=_fetcher)
    pdf_bytes = pdf_file.getvalue()
    logger.info(f"PDF do POP {pop.get('codigo')} v{versao.get('numero_versao')} gerado ({len(pdf_bytes)} bytes)")
    return pdf_bytes
