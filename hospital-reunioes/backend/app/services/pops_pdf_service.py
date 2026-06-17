"""Documento oficial do POP em PDF — WeasyPrint, como a Ata (issue #86).

As 11 seções do template institucional (DRF §4.2) com identidade visual HSM.
A seção Fluxograma vira um fluxo vertical em HTML/CSS puro: o texto
estruturado pela IA na elaboração (passos numerados e decisões sim/não) é
parseado DETERMINISTICAMENTE aqui — sem IA na geração e sem dependência
nova de renderização (decisão do grilling, PRD #76).

Nomenclatura travada do DRF §3.3:
`HSM_[SETOR]-[NNN]_[NOME-ABREVIADO]_v[VERSÃO]_[AAAAMM]_[STATUS].pdf`.
"""

from __future__ import annotations

import io
import logging
import os
import re
import unicodedata
from datetime import datetime

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


# ─── Fluxograma — parser determinístico do texto estruturado pela IA ─────────

_RE_MARCADOR = re.compile(r"^\s*(?:\d+[.)]\s*|[-•*]\s*)")
_RE_RAMO_SIM = re.compile(r"\bsim\b\s*[:→,–-]?\s*", re.IGNORECASE)
_RE_RAMO_NAO = re.compile(r"\bn[ãa]o\b\s*[:→,–-]?\s*", re.IGNORECASE)
# Linha que é SÓ um ramo de decisão exige separador explícito após o rótulo
# ("Sim: …"), para não engolir frases que começam com "Não …".
_RE_LINHA_RAMO = re.compile(r"^(?:se\s+)?(?:sim|n[ãa]o)\s*[:→]", re.IGNORECASE)
_TERMINAIS = {"inicio", "início", "fim", "termino", "término"}


def _no(tipo: str, texto: str, sim: str | None = None, nao: str | None = None) -> dict:
    return {"tipo": tipo, "texto": texto, "sim": sim, "nao": nao}


def _extrair_ramos(trecho: str) -> tuple[str | None, str | None]:
    """Acha `Sim: …` / `Não: …` num trecho (qualquer ordem) e devolve os dois
    textos de ação — None para ramo ausente."""
    marcas = [
        (rotulo, m) for rotulo, m in (("sim", _RE_RAMO_SIM.search(trecho)), ("nao", _RE_RAMO_NAO.search(trecho))) if m
    ]
    marcas.sort(key=lambda item: item[1].start())
    sim = nao = None
    for i, (rotulo, m) in enumerate(marcas):
        fim = marcas[i + 1][1].start() if i + 1 < len(marcas) else len(trecho)
        valor = trecho[m.end() : fim].strip(" .;,–-") or None
        if rotulo == "sim":
            sim = valor
        else:
            nao = valor
    return sim, nao


def parse_fluxograma(texto: str) -> list[dict]:
    """Texto estruturado da seção Fluxograma → nós tipados para o template.

    Uma etapa por linha (numeração/bullets removidos): linha com `?` é uma
    decisão — os ramos vêm inline (`Pergunta? Sim: x. Não: y.`) ou nas linhas
    seguintes (`- Sim: x`). Qualquer outra linha é um passo. Terminais
    Início/Fim são garantidos nas pontas. Vazio → lista vazia (sem diagrama).
    """
    linhas = [_RE_MARCADOR.sub("", linha).strip() for linha in (texto or "").splitlines()]
    linhas = [linha for linha in linhas if linha]
    if not linhas:
        return []

    nos: list[dict] = []
    i = 0
    while i < len(linhas):
        linha = linhas[i]
        if "?" in linha:
            corte = linha.index("?") + 1
            pergunta, resto = linha[:corte].strip(), linha[corte:].strip()
            sim, nao = _extrair_ramos(resto)
            while (sim is None or nao is None) and i + 1 < len(linhas) and _RE_LINHA_RAMO.match(linhas[i + 1]):
                ramo_sim, ramo_nao = _extrair_ramos(linhas[i + 1])
                sim, nao = sim or ramo_sim, nao or ramo_nao
                i += 1
            nos.append(_no("decisao", pergunta, sim, nao))
        else:
            nos.append(_no("passo", linha))
        i += 1

    for indice, rotulo in ((0, "Início"), (-1, "Fim")):
        ponta = nos[indice]
        if ponta["tipo"] == "passo" and ponta["texto"].strip(" .:!").lower() in _TERMINAIS:
            ponta["tipo"] = "terminal"
            ponta["texto"] = rotulo
        elif indice == 0:
            nos.insert(0, _no("terminal", rotulo))
        else:
            nos.append(_no("terminal", rotulo))
    return nos


# ─── Geração do PDF ──────────────────────────────────────────────────────────


def gerar_pdf_pop(*, pop: dict, setor: dict, versao: dict, nomes_designados: dict[str, str | None]) -> bytes:
    """Renderiza o documento institucional do POP (11 seções) e devolve os
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
    # Identificação, é do cabeçalho). A renderização visual rica (markdown) é da
    # Fatia 2; aqui cada seção entra como conteúdo, e o Fluxograma mantém o
    # parser determinístico vigente.
    from app.services.pops_secoes import migrar_rascunho_legado

    rascunho = migrar_rascunho_legado(versao.get("rascunho"))

    secoes = []
    for indice, secao_rascunho in enumerate(rascunho["secoes"], start=2):
        conteudo = (secao_rascunho.get("conteudo") or "").strip()
        secao = {
            "numero": indice,
            "titulo": secao_rascunho.get("titulo") or "",
            "tipo": secao_rascunho.get("tipo") or "texto",
            "conteudo": conteudo,
        }
        if secao["tipo"] == "fluxograma":
            secao["nos"] = parse_fluxograma(conteudo)
        secoes.append(secao)

    logo_path = os.path.join(os.path.dirname(__file__), "..", "static", "images", "logo_hospital.png")
    font_path = os.path.join(os.path.dirname(__file__), "..", "static", "fonts", "HPSimplified_Rg.ttf")
    if not os.path.exists(font_path):
        logger.warning(f"Fonte HPSimplified_Rg.ttf não encontrada em {font_path}; PDF usará fallback do sistema")
        font_path = None

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
        logo_path=f"file://{logo_path}",
        font_path=f"file://{font_path}" if font_path else None,
    )

    pdf_file = io.BytesIO()
    HTML(string=html_content).write_pdf(target=pdf_file)
    pdf_bytes = pdf_file.getvalue()
    logger.info(f"PDF do POP {pop.get('codigo')} v{versao.get('numero_versao')} gerado ({len(pdf_bytes)} bytes)")
    return pdf_bytes
