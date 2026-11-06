"""Caixa alta nos títulos dos PDFs (issue #1456, ADR 0080).

Os títulos e subtítulos da ata, do POP, do relatório e do cartaz da Ouvidoria
saem em caixa alta, e o texto corrido continua com maiúscula e minúscula. A
caixa alta é só da exibição: o `text-transform` do template. O texto que a IA
escreveu (tópico da ata, seção do POP, sugestão do relatório) chega ao HTML
como foi gravado, e é o WeasyPrint que o desenha em maiúscula.

Cada teste olha as duas pontas do mesmo render: o HTML que vai ao WeasyPrint
(o valor original está lá) e o texto lido de volta do PDF (o título impresso em
maiúscula, o parágrafo não). Asserir só o CSS no HTML seria cego a um seletor
que não casa com o elemento.
"""

from __future__ import annotations

import io
import os
import re
import sys

import pdfplumber
import pytest
import weasyprint

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services import pdf_generator  # noqa: E402


def _texto_do_pdf(pdf: bytes) -> str:
    """O texto que o PDF imprime, com os espaços e quebras de linha
    colapsados num espaço só (título longo quebra em duas linhas)."""
    with pdfplumber.open(io.BytesIO(pdf)) as documento:
        texto = "\n".join(pagina.extract_text() or "" for pagina in documento.pages)
    return re.sub(r"\s+", " ", texto)


@pytest.fixture
def htmls(monkeypatch) -> list[str]:
    """O HTML que cada geração entrega ao WeasyPrint. O render segue real: o
    espião só anota a string e chama o HTML de verdade."""
    capturados: list[str] = []
    original = weasyprint.HTML

    class _Espiao(original):
        def __init__(self, *args, string: str | None = None, **kwargs):
            capturados.append(string)
            super().__init__(*args, string=string, **kwargs)

    monkeypatch.setattr(weasyprint, "HTML", _Espiao)
    monkeypatch.setattr(pdf_generator, "HTML", _Espiao)
    return capturados


# ─────────────────────────────── ata ───────────────────────────────

TOPICO_DA_IA = "Escala de plantão da enfermagem"
DESCRICAO_DO_TOPICO = "A coordenação apresentou a nova escala de plantão."


def _ata_pdf() -> bytes:
    reuniao = {"id_reuniao": "reu-1456", "tipo": "Ordinária", "data": "2026-11-06"}
    ata = {
        "objetivo": "Revisar a escala do mês.",
        "participantes": [{"nome": "Ana Souza", "cargo": "Enfermeira", "presente": True}],
        "discussao": [{"titulo": TOPICO_DA_IA, "descricao": DESCRICAO_DO_TOPICO}],
        "quadro_atribuicoes": [],
    }
    return pdf_generator.gerar_pdf_ata(reuniao, ata)


def test_titulos_da_ata_saem_em_caixa_alta_no_pdf(htmls):
    texto = _texto_do_pdf(_ata_pdf())

    assert "ATA DE REUNIÃO" in texto
    assert "4. DISCUSSÃO DOS PONTOS" in texto
    assert f"4.1 {TOPICO_DA_IA.upper()}" in texto


def test_texto_corrido_da_ata_continua_com_maiuscula_e_minuscula(htmls):
    texto = _texto_do_pdf(_ata_pdf())

    assert DESCRICAO_DO_TOPICO in texto
    assert "Hospital São Matheus" in texto


def test_topico_escrito_pela_ia_chega_a_ata_como_foi_gravado(htmls):
    _ata_pdf()

    assert f"4.1 {TOPICO_DA_IA}</p>" in htmls[-1]


# ─────────────────────────────── POP ───────────────────────────────

# A seção vem do modelo de POP que o hospital anexou: o agente segue a
# estrutura dele, e o título chega com a grafia do modelo. O subtítulo dentro
# do conteúdo é o `##` que o agente usa em sub-blocos.
SECAO_DO_MODELO = "Objetivo e campo de aplicação"
SUBTITULO_DA_IA = "Quando lavar as mãos"
PARAGRAFO_DA_SECAO = "Padronizar a higienização das mãos nas unidades assistenciais."


def _pop_pdf() -> bytes:
    from app.services.pops_pdf_service import gerar_pdf_pop

    versao = {
        "id": "v-1",
        "pop_id": "pop-1",
        "numero_versao": "1.0",
        "estado": "EM_REVISAO",
        "rascunho": {
            "secoes": [
                {
                    "id": "sec-obj",
                    "titulo": SECAO_DO_MODELO,
                    "tipo": "texto",
                    "conteudo": f"{PARAGRAFO_DA_SECAO}\n\n## {SUBTITULO_DA_IA}\n\nAntes de tocar o paciente.",
                },
            ]
        },
    }
    pop = {
        "codigo": "HSM_CTI-001",
        "nome": "Higienização das Mãos",
        "criticidade": "CRITICA",
        "periodicidade_revisao": "1_ano",
        "elaborador_id": "P1",
        "created_at": "2026-06-10T12:00:00+00:00",
    }
    setor = {"id": "s-cti", "nome": "Coordenação do CTI", "sigla": "CTI"}
    return gerar_pdf_pop(pop=pop, setor=setor, versao=versao, nomes_designados={"P1": "Pessoa P1"})


def test_titulos_do_pop_saem_em_caixa_alta_no_pdf(htmls):
    texto = _texto_do_pdf(_pop_pdf())

    assert "PROCEDIMENTO OPERACIONAL PADRÃO" in texto
    assert "1. IDENTIFICAÇÃO" in texto
    assert f"2. {SECAO_DO_MODELO.upper()}" in texto
    assert SUBTITULO_DA_IA.upper() in texto


def test_texto_corrido_do_pop_continua_com_maiuscula_e_minuscula(htmls):
    texto = _texto_do_pdf(_pop_pdf())

    assert PARAGRAFO_DA_SECAO in texto
    assert "Antes de tocar o paciente." in texto


def test_secao_escrita_pela_ia_chega_ao_pop_como_foi_gravada(htmls):
    _pop_pdf()

    assert f"<h2>2. {SECAO_DO_MODELO}</h2>" in htmls[-1]
    assert f">{SUBTITULO_DA_IA}</h2>" in htmls[-1]


# ───────────────────────── relatório da Ouvidoria ─────────────────────────

SUGESTAO_DA_IA = "Reforçar a triagem da Recepção"
PORQUE_DA_SUGESTAO = "A Recepção concentra o volume e estoura o prazo da área."


def _registro_mensal() -> dict:
    """Um relatório mensal congelado, no formato que o banco guarda, com uma
    sugestão escrita pela IA."""
    contagem = {"itens": [], "classificados": 0, "nao_classificados": 0}
    return {
        "id": "rel-1456",
        "tipo": "mensal",
        "competencia": "2026-10",
        "medido_em": "2026-11-01T09:00:00+00:00",
        "dados": {
            "periodo": {"inicio": "2026-10-01", "fim": "2026-10-31"},
            "periodo_anterior": {"inicio": "2026-08-31", "fim": "2026-09-30"},
            "degradado": [],
            "volume": {"total": 3, "anterior": 2, "variacao_pct": 50.0, "novos": 3, "reincidentes": 0},
            "prazo": {"trechos": []},
            "pendencias_por_area": [],
            "ranking_areas": [],
            "prorrogacao": {"casos": 0, "com_a_area": 0, "taxa_pct": 0.0, "por_area": []},
            "reincidencia": {"casos": 0, "taxa_pct": 0.0},
            "tempo_pausado": {"casos_com_pausa": 0, "dias_uteis_medios": 0.0},
            "top_temas": contagem,
            "top_areas": contagem,
        },
        "sugestoes": {
            "itens": [{"titulo": SUGESTAO_DA_IA, "porque": PORQUE_DA_SUGESTAO, "acao": "Escalar mais um atendente."}]
        },
    }


def test_titulos_do_relatorio_da_ouvidoria_saem_em_caixa_alta_no_pdf():
    from app.services import ouvidoria_relatorio

    texto = _texto_do_pdf(ouvidoria_relatorio.renderizar_pdf(_registro_mensal()))

    assert "RELATÓRIO MENSAL DA OUVIDORIA" in texto
    assert "VOLUME POR CANAL" in texto
    assert "SUGESTÕES DE AÇÃO CORRETIVA" in texto
    assert SUGESTAO_DA_IA.upper() in texto


def test_texto_corrido_do_relatorio_da_ouvidoria_continua_com_maiuscula_e_minuscula():
    from app.services import ouvidoria_relatorio

    texto = _texto_do_pdf(ouvidoria_relatorio.renderizar_pdf(_registro_mensal()))

    assert PORQUE_DA_SUGESTAO in texto
    assert "Período de 01/10/2026 a 31/10/2026" in texto


def test_sugestao_escrita_pela_ia_chega_ao_relatorio_como_foi_gravada():
    from app.services import ouvidoria_relatorio

    html = ouvidoria_relatorio.montar_html(_registro_mensal())

    assert f'<div class="titulo">{SUGESTAO_DA_IA}</div>' in html


# ───────────────────────── cartaz da Ouvidoria ─────────────────────────

PONTO_DE_ESCUTA = {"codigo": "AB2CD3", "setor": "Recepção Central", "ponto": "Poltrona 12"}


def test_titulo_do_cartaz_da_ouvidoria_sai_em_caixa_alta_no_pdf():
    from app.services.ouvidoria_pontos import pdf_do_cartaz

    texto = _texto_do_pdf(pdf_do_cartaz(PONTO_DE_ESCUTA))

    assert "SUA OPINIÃO MELHORA NOSSO ATENDIMENTO." in texto


def test_texto_corrido_do_cartaz_da_ouvidoria_continua_com_maiuscula_e_minuscula():
    from app.services.ouvidoria_pontos import html_do_cartaz, pdf_do_cartaz

    texto = _texto_do_pdf(pdf_do_cartaz(PONTO_DE_ESCUTA))

    assert "Fale com a gente. Leva menos de um minuto, e você pode ser anônimo." in texto
    assert "Aponte a câmera do celular para o código acima." in texto
    # O setor é digitado pela equipe: sai como foi escrito.
    assert "Recepção Central" in texto
    assert "Sua opinião melhora nosso atendimento." in html_do_cartaz(PONTO_DE_ESCUTA)
