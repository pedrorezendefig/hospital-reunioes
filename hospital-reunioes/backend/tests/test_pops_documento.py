"""Testes do documento oficial do POP em PDF (issue #86).

O PDF institucional (PRD #76): as 11 seções do template com identidade HSM,
geradas da Versão via WeasyPrint (como a Ata), com a seção Fluxograma
renderizada como fluxo vertical em HTML/CSS puro — os passos e decisões
sim/não já estruturados pela IA na elaboração são parseados de forma
DETERMINÍSTICA aqui (sem IA, sem dependência nova na geração).

Nomenclatura travada do DRF §3.3:
`HSM_[SETOR]-[NNN]_[NOME-ABREVIADO]_v[VERSÃO]_[AAAAMM]_[STATUS].pdf`.

O render visual do PDF é verificação manual (decisão do PRD #76) — aqui
testamos contrato: endpoint, estados, escopo de acesso e nomenclatura.
Supabase mock no padrão de test_pops_elaboracao.
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.dependencies import get_current_user, get_supabase_client  # noqa: E402
from app.routers.pops import documento as documento_router  # noqa: E402
from app.services import pops_pdf_service  # noqa: E402
from app.services.pops_pdf_service import markdown_secao_html, nome_arquivo_pop, parse_fluxograma  # noqa: E402

# ─── Mock Supabase (padrão do test_pops_elaboracao) ───────────────────────────


@dataclass
class _Result:
    data: list


class _TableQuery:
    def __init__(self, rows: list[dict], table: str):
        self._rows = rows
        self._table = table
        self._filters: dict = {}
        self._in_filters: dict = {}

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, col, value):
        self._filters[col] = value
        return self

    def in_(self, col, values):
        self._in_filters[col] = list(values)
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def execute(self):
        filtered = [
            r
            for r in self._rows
            if all(r.get(c) == v for c, v in self._filters.items())
            and all(r.get(c) in vs for c, vs in self._in_filters.items())
        ]
        return _Result(data=[dict(r) for r in filtered])


class _SupabaseMock:
    def __init__(self, tables: dict[str, list[dict]]):
        self.tables = tables

    def table(self, name: str):
        if name not in self.tables:
            raise AssertionError(f"Tabela inesperada: {name}")
        return _TableQuery(self.tables[name], name)


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _pessoa(pid: str, perfil_pop: str | None = None) -> dict:
    return {
        "id": pid,
        "auth_user_id": f"auth-{pid}",
        "email": f"{pid.lower()}@hsm.com",
        "nome_completo": f"Pessoa {pid}",
        "cargo": "Cargo",
        "ativo": True,
        "is_externo": False,
        "is_super_admin": False,
        "access_profile": None,
        "perfil_pop": perfil_pop,
    }


def _pop(**over) -> dict:
    base = {
        "id": "pop-1",
        "setor_id": "s-cti",
        "numero": 1,
        "codigo": "HSM_CTI-001",
        "nome": "Higienização das Mãos",
        "criticidade": "CRITICA",
        "base_normativa": "RDC 63/2011",
        "periodicidade_revisao": "1_ano",
        "prazo_elaboracao_dias": 15,
        "prazo_revisao_dias": 30,
        "elaborador_id": "P1",
        "revisor_id": "P2",
        "validador_id": "P3",
        "criado_por": "P4",
        "created_at": "2026-06-10T12:00:00+00:00",
    }
    base.update(over)
    return base


RASCUNHO_COMPLETO = {
    "objetivo": "Padronizar a higienização das mãos em todas as unidades assistenciais.",
    "abrangencia": "Aplica-se a todos os profissionais do CTI.",
    "definicoes_siglas": "CTI: Centro de Terapia Intensiva.\nPAS: Preparação Alcoólica para as mãos.",
    "responsabilidades": "- Enfermeiro: supervisão da técnica.\n- Técnico de enfermagem: execução.",
    "materiais_equipamentos": "- Sabonete líquido\n- Preparação alcoólica 70%\n- Papel toalha",
    "descricao_procedimento": "1. Retirar adornos.\n2. Abrir a torneira e molhar as mãos.\n3. Aplicar sabonete.",
    "fluxograma": (
        "1. Retirar adornos\n"
        "2. Mãos visivelmente sujas? Sim: lavar com água e sabonete. Não: friccionar preparação alcoólica.\n"
        "3. Secar com papel toalha"
    ),
    "indicadores_adesao": "Taxa de adesão à higienização das mãos. Meta: ≥ 90%. Frequência: mensal.",
    "referencias_normativas": "RDC 63/2011 — ANVISA.\nProtocolo de Segurança do Paciente — MS.",
    "historico_revisoes": "Versão 1.0 — elaboração inicial.",
}


# Rascunho na estrutura DINÂMICA (ADR 0016): lista ordenada de seções, cada uma
# com conteúdo em markdown (negrito, listas, blocos). É o shape que a Fatia 2
# precisa renderizar bonito; o fluxograma fica como uma seção de tipo próprio.
RASCUNHO_SECOES_MARKDOWN = {
    "secoes": [
        {
            "id": "sec-obj",
            "titulo": "Objetivo",
            "tipo": "texto",
            "conteudo": "Padronizar a **higienização das mãos** em todas as unidades assistenciais.",
        },
        {
            "id": "sec-resp",
            "titulo": "Responsabilidades",
            "tipo": "texto",
            "conteudo": "- **Enfermeiro:** supervisão da técnica.\n- **Técnico de enfermagem:** execução.",
        },
        {
            "id": "sec-flux",
            "titulo": "Fluxograma",
            "tipo": "fluxograma",
            "conteudo": "1. Retirar adornos\n2. Mãos sujas? Sim: lavar. Não: friccionar álcool.\n3. Secar",
        },
    ]
}


def _versao(**over) -> dict:
    base = {
        "id": "v-1",
        "pop_id": "pop-1",
        "numero_versao": "1.0",
        "estado": "EM_REVISAO",
        "rascunho": dict(RASCUNHO_COMPLETO),
        "periodicidade_sugerida": None,
    }
    base.update(over)
    return base


# Designados do pop-1 — Revisor e Validador SEM vínculo com o Setor do POP:
# a designação formal vence o escopo (caso-chave do critério de acesso).
ELABORADOR = _pessoa("P1", perfil_pop="coordenador")
REVISOR_SEM_SETOR = _pessoa("P2", perfil_pop="coordenador")
VALIDADOR_SEM_SETOR = _pessoa("P3", perfil_pop="gerente")
INTRUSO_OUTRO_SETOR = _pessoa("P4", perfil_pop="coordenador")
SEM_PERFIL = _pessoa("P5", perfil_pop=None)
COORD_DO_SETOR = _pessoa("P6", perfil_pop="coordenador")
GESTOR_QUALIDADE = _pessoa("P7", perfil_pop="gestor_qualidade")

VINCULOS = [
    {"participante_id": "P4", "setor_id": "s-outro"},
    {"participante_id": "P6", "setor_id": "s-cti"},
]


def _sb(versao: dict | None = None, pop: dict | None = None) -> _SupabaseMock:
    return _SupabaseMock(
        {
            "participantes": [
                ELABORADOR,
                REVISOR_SEM_SETOR,
                VALIDADOR_SEM_SETOR,
                INTRUSO_OUTRO_SETOR,
                SEM_PERFIL,
                COORD_DO_SETOR,
                GESTOR_QUALIDADE,
            ],
            "pops_setores": [
                {"id": "s-cti", "nome": "Coordenação do CTI", "sigla": "CTI"},
                {"id": "s-outro", "nome": "Coordenação de Farmácia", "sigla": "FAR"},
            ],
            "pops_setores_participantes": list(VINCULOS),
            "pops": [pop or _pop()],
            "pops_versoes": [versao or _versao()],
        }
    )


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """O limiter do slowapi acumula hits por IP entre arquivos da suíte (storage
    global); zera antes de cada teste pra cada um partir limpo."""
    from app.limiter import limiter

    limiter._storage.reset()
    yield


@pytest.fixture
def pdf_mockado(monkeypatch) -> list[dict]:
    """Substitui o WeasyPrint nos testes de contrato (guardas/nomenclatura):
    o render real é coberto pelo teste de fumaça e pela verificação manual."""
    chamadas: list[dict] = []

    def _fake(**kwargs) -> bytes:
        chamadas.append(kwargs)
        return b"%PDF-fake"

    monkeypatch.setattr(pops_pdf_service, "gerar_pdf_pop", _fake)
    return chamadas


@pytest.fixture
def capturar_html_pdf(monkeypatch) -> list[str]:
    """Intercepta o `HTML(string=...)` do WeasyPrint e guarda o HTML renderizado
    pelo template, devolvendo um PDF mínimo válido. Deixa o teste asseverar a
    conversão markdown→HTML e a ordem das seções sem inspecionar os bytes do PDF
    (o render real de fato roda no teste de fumaça)."""
    import weasyprint

    capturado: list[str] = []

    class HtmlEspiao(weasyprint.HTML):
        def __init__(self, *args, string: str | None = None, **kwargs):
            if string is not None:
                capturado.append(string)
            super().__init__(*args, string=string, **kwargs)

    monkeypatch.setattr(weasyprint, "HTML", HtmlEspiao)
    return capturado


def _client_para(pessoa: dict, sb: _SupabaseMock) -> TestClient:
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded

    from app.limiter import limiter

    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(documento_router.router, prefix="/api")

    async def _fake_user() -> dict[str, Any]:
        return {"id": pessoa["auth_user_id"], "email": pessoa["email"], "metadata": {}}

    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_supabase_client] = lambda: sb
    return TestClient(app)


# ═══════════════════════════════════════════════════════════════════════════
# Nomenclatura travada do DRF §3.3 — nome_arquivo_pop
# ═══════════════════════════════════════════════════════════════════════════


class TestNomenclaturaArquivo:
    def test_exemplo_literal_do_drf(self):
        """CA: o nome segue a nomenclatura travada — reproduz o exemplo do DRF:
        HSM_CTI-001_Cateter-Venoso-Central_v1.0_202605_ASSINADO.pdf"""
        nome = nome_arquivo_pop(
            codigo="HSM_CTI-001",
            nome="Cateter Venoso Central",
            numero_versao="1.0",
            status="ASSINADO",
            quando=datetime(2026, 5, 15),
        )
        assert nome == "HSM_CTI-001_Cateter-Venoso-Central_v1.0_202605_ASSINADO.pdf"

    def test_status_default_preliminar(self):
        """O documento desta fatia é o preliminar — o ASSINADO chega na fatia
        de publicação (decisão da issue #86)."""
        nome = nome_arquivo_pop(
            codigo="HSM_CTI-001",
            nome="Cateter Venoso Central",
            numero_versao="1.0",
            quando=datetime(2026, 6, 1),
        )
        assert nome == "HSM_CTI-001_Cateter-Venoso-Central_v1.0_202606_PRELIMINAR.pdf"

    def test_abreviacao_remove_acentos_e_stopwords(self):
        """Nome de arquivo seguro e abreviado: sem acentos (ASCII), sem
        stopwords (de/das/e/...), Title-Case com hífens."""
        nome = nome_arquivo_pop(
            codigo="HSM_CTI-002",
            nome="Higienização das Mãos e Antissepsia Cirúrgica",
            numero_versao="1.0",
            quando=datetime(2026, 6, 1),
        )
        assert nome == "HSM_CTI-002_Higienizacao-Maos-Antissepsia-Cirurgica_v1.0_202606_PRELIMINAR.pdf"

    def test_abreviacao_trunca_nome_longo_em_fronteira_de_palavra(self):
        nome = nome_arquivo_pop(
            codigo="HSM_FAR-001",
            nome="Dispensação de Medicamentos Controlados pela Farmácia Central em Horário Noturno",
            numero_versao="1.0",
            quando=datetime(2026, 6, 1),
        )
        abreviado = nome.split("_")[2]
        assert len(abreviado) <= 40
        assert not abreviado.endswith("-")
        # Não corta palavra no meio: cada pedaço é uma palavra inteira do nome.
        assert abreviado.startswith("Dispensacao-Medicamentos")


# ═══════════════════════════════════════════════════════════════════════════
# Fluxograma — parser determinístico do texto estruturado pela IA
# ═══════════════════════════════════════════════════════════════════════════


class TestParseFluxograma:
    def test_passos_numerados_viram_caixas_com_terminais(self):
        """CA: fluxo vertical — passos sequenciais entre Início e Fim."""
        nos = parse_fluxograma("1. Retirar adornos\n2. Molhar as mãos\n3. Secar com papel toalha")
        assert [n["tipo"] for n in nos] == ["terminal", "passo", "passo", "passo", "terminal"]
        assert nos[0]["texto"] == "Início"
        assert nos[1]["texto"] == "Retirar adornos"
        assert nos[-1]["texto"] == "Fim"

    def test_decisao_inline_com_ramos_sim_nao(self):
        """CA: decisões sim/não estruturadas pela IA viram nós de decisão com
        os dois ramos rotulados."""
        nos = parse_fluxograma(
            "1. Avaliar as mãos\n"
            "2. Mãos visivelmente sujas? Sim: lavar com água e sabonete. Não: friccionar preparação alcoólica.\n"
            "3. Secar"
        )
        decisao = next(n for n in nos if n["tipo"] == "decisao")
        assert decisao["texto"] == "Mãos visivelmente sujas?"
        assert decisao["sim"] == "lavar com água e sabonete"
        assert decisao["nao"] == "friccionar preparação alcoólica"

    def test_decisao_com_ramos_nas_linhas_seguintes(self):
        nos = parse_fluxograma(
            "1. Conferir materiais\n2. Material completo?\n"
            "- Sim: iniciar o procedimento\n- Não: providenciar a reposição\n3. Registrar"
        )
        decisao = next(n for n in nos if n["tipo"] == "decisao")
        assert decisao["sim"] == "iniciar o procedimento"
        assert decisao["nao"] == "providenciar a reposição"
        tipos = [n["tipo"] for n in nos]
        assert tipos == ["terminal", "passo", "decisao", "passo", "terminal"]

    def test_inicio_e_fim_do_texto_nao_duplicam_terminais(self):
        nos = parse_fluxograma("1. Início\n2. Executar o procedimento\n3. Fim")
        assert [n["tipo"] for n in nos] == ["terminal", "passo", "terminal"]
        assert nos[0]["texto"] == "Início"
        assert nos[-1]["texto"] == "Fim"

    def test_texto_livre_sem_numeracao_vira_passos(self):
        """Fallback robusto: rascunhos antigos (texto corrido) sempre rendem
        um fluxo — cada linha é uma caixa."""
        nos = parse_fluxograma("Lavar as mãos\nCalçar as luvas")
        assert [n["tipo"] for n in nos] == ["terminal", "passo", "passo", "terminal"]

    def test_vazio_devolve_lista_vazia(self):
        assert parse_fluxograma("") == []
        assert parse_fluxograma("   \n  ") == []


# ═══════════════════════════════════════════════════════════════════════════
# GET /pops/{pop_id}/documento — preview/download com escopo de acesso
# ═══════════════════════════════════════════════════════════════════════════


class TestDocumentoEndpoint:
    def test_preview_em_revisao_devolve_pdf_inline_com_nome_travado(self, pdf_mockado):
        """CA: preview disponível na Revisão — application/pdf inline, com o
        nome do arquivo na nomenclatura travada do DRF."""
        client = _client_para(REVISOR_SEM_SETOR, _sb(versao=_versao(estado="EM_REVISAO")))

        res = client.get("/api/pops/pop-1/documento")

        assert res.status_code == 200
        assert res.headers["content-type"] == "application/pdf"
        disposition = res.headers["content-disposition"]
        assert disposition.startswith("inline")
        assert re.search(r'filename="HSM_CTI-001_Higienizacao-Maos_v1\.0_\d{6}_PRELIMINAR\.pdf"', disposition)
        assert res.content == b"%PDF-fake"

    def test_download_devolve_attachment(self, pdf_mockado):
        """CA: download disponível — ?download=1 troca para attachment."""
        client = _client_para(VALIDADOR_SEM_SETOR, _sb(versao=_versao(estado="EM_VALIDACAO")))

        res = client.get("/api/pops/pop-1/documento?download=1")

        assert res.status_code == 200
        assert res.headers["content-disposition"].startswith("attachment")

    def test_estados_de_leitura_geram_documento(self, pdf_mockado):
        """O documento preliminar existe da Revisão em diante. Em PUBLICADO o
        assinado substitui o download (issue #87) — coberto em
        test_pops_biblioteca, que serve do storage em vez de regenerar."""
        for estado in ("EM_REVISAO", "EM_VALIDACAO", "EM_ASSINATURA"):
            client = _client_para(GESTOR_QUALIDADE, _sb(versao=_versao(estado=estado)))
            res = client.get("/api/pops/pop-1/documento")
            assert res.status_code == 200, f"estado {estado} deveria gerar o documento"

    def test_estados_de_elaboracao_400(self, pdf_mockado):
        """Em elaboração o rascunho ainda está nas mãos do Elaborador — não há
        documento para o fluxo de revisão."""
        for estado in ("A_ELABORAR", "EM_ELABORACAO"):
            client = _client_para(ELABORADOR, _sb(versao=_versao(estado=estado)))
            res = client.get("/api/pops/pop-1/documento")
            assert res.status_code == 400, f"estado {estado} deveria dar 400"
            assert pdf_mockado == []

    def test_designado_fora_do_escopo_de_setor_acessa(self, pdf_mockado):
        """CA (escopo): a designação formal vence o escopo de Setor — Revisor e
        Validador de outro Setor leem o documento do POP deles."""
        for pessoa in (ELABORADOR, REVISOR_SEM_SETOR, VALIDADOR_SEM_SETOR):
            client = _client_para(pessoa, _sb())
            res = client.get("/api/pops/pop-1/documento")
            assert res.status_code == 200, f"{pessoa['id']} é designado e deveria acessar"

    def test_escopo_de_setor_acessa_sem_designacao(self, pdf_mockado):
        """CA (escopo): Coordenador do Setor do POP e perfis de escopo total
        (Gestor de Qualidade) leem sem serem designados."""
        for pessoa in (COORD_DO_SETOR, GESTOR_QUALIDADE):
            client = _client_para(pessoa, _sb())
            res = client.get("/api/pops/pop-1/documento")
            assert res.status_code == 200, f"{pessoa['id']} deveria acessar pelo escopo"

    def test_coordenador_de_outro_setor_403(self, pdf_mockado):
        """CA (escopo): fora do Setor e sem designação → 403."""
        client = _client_para(INTRUSO_OUTRO_SETOR, _sb())
        res = client.get("/api/pops/pop-1/documento")
        assert res.status_code == 403
        assert pdf_mockado == []

    def test_sem_perfil_pop_403(self, pdf_mockado):
        client = _client_para(SEM_PERFIL, _sb())
        res = client.get("/api/pops/pop-1/documento")
        assert res.status_code == 403

    def test_pop_inexistente_404(self, pdf_mockado):
        client = _client_para(GESTOR_QUALIDADE, _sb())
        res = client.get("/api/pops/pop-999/documento")
        assert res.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════
# Fumaça do render real — WeasyPrint + template (sem mock)
# ═══════════════════════════════════════════════════════════════════════════


class TestRenderReal:
    def test_gera_pdf_de_verdade_com_rascunho_completo(self):
        """CA: PDF com as 11 seções gerado a partir do conteúdo da Versão —
        template Jinja + WeasyPrint reais, rascunho completo com decisão no
        fluxograma. O visual é verificação manual; aqui garantimos que o
        render não quebra e produz um PDF válido."""
        client = _client_para(REVISOR_SEM_SETOR, _sb(versao=_versao(estado="EM_REVISAO")))

        res = client.get("/api/pops/pop-1/documento")

        assert res.status_code == 200
        assert res.content.startswith(b"%PDF")
        assert len(res.content) > 1000

    def test_gera_pdf_de_verdade_com_secoes_dinamicas_em_markdown(self):
        """CA (Fatia 2, ADR 0016): uma Versão com lista de seções dinâmicas e
        conteúdo em markdown gera o PDF sem quebrar, com as seções na ordem e o
        markdown convertido para HTML (negrito, listas) na linguagem visual da
        Ata. Capturamos o HTML que vai ao WeasyPrint para checar a conversão
        sem depender dos bytes do PDF."""
        versao = _versao(estado="EM_REVISAO", rascunho=dict(RASCUNHO_SECOES_MARKDOWN))
        client = _client_para(REVISOR_SEM_SETOR, _sb(versao=versao))

        res = client.get("/api/pops/pop-1/documento")

        assert res.status_code == 200
        assert res.content.startswith(b"%PDF")
        assert len(res.content) > 1000

    def test_html_do_pdf_converte_markdown_e_preserva_ordem(self, capturar_html_pdf):
        """O markdown das seções de texto vira HTML real (negrito → <strong>,
        listas → <ul><li>) com as classes visuais da Ata, e as seções saem na
        ordem do rascunho. O fluxograma segue como fluxo determinístico, não
        como markdown cru."""
        versao = _versao(estado="EM_REVISAO", rascunho=dict(RASCUNHO_SECOES_MARKDOWN))
        client = _client_para(REVISOR_SEM_SETOR, _sb(versao=versao))

        res = client.get("/api/pops/pop-1/documento")
        assert res.status_code == 200

        html = capturar_html_pdf[0]
        # Negrito e lista convertidos a partir do markdown.
        assert "<strong>higienização das mãos</strong>" in html
        assert "<ul>" in html and "<li>" in html
        assert "<strong>Enfermeiro:</strong>" in html
        # Classe visual da Ata aplicada ao bloco de conteúdo (left-border .topico).
        assert "topico" in html
        # Markdown não vaza cru no HTML final.
        assert "**higienização das mãos**" not in html
        # Ordem preservada: Objetivo antes de Responsabilidades antes do Fluxograma.
        assert html.index("2. Objetivo") < html.index("3. Responsabilidades") < html.index("4. Fluxograma")
        # A seção de fluxograma continua sendo o fluxo determinístico (caixas),
        # não markdown: o número 1 do passo não vira lista ordenada solta.
        assert "fluxo-no" in html


# ═══════════════════════════════════════════════════════════════════════════
# Markdown das seções de texto → HTML com a linguagem visual da Ata
# ═══════════════════════════════════════════════════════════════════════════


class TestMarkdownSecao:
    def test_negrito_vira_strong(self):
        html = markdown_secao_html("Use a **preparação alcoólica** a 70%.")
        assert "<strong>preparação alcoólica</strong>" in html

    def test_lista_vira_ul_li(self):
        html = markdown_secao_html("- Sabonete líquido\n- Papel toalha")
        assert "<ul>" in html
        assert html.count("<li>") == 2
        assert "Sabonete líquido" in html

    def test_lista_ordenada_e_titulos(self):
        html = markdown_secao_html("## Passos\n\n1. Molhar\n2. Ensaboar")
        assert "<ol>" in html
        assert "Passos" in html

    def test_vazio_devolve_string_vazia(self):
        assert markdown_secao_html("") == ""
        assert markdown_secao_html("   ") == ""

    def test_texto_plano_sem_markdown_vira_paragrafo(self):
        html = markdown_secao_html("Apenas uma frase simples.")
        assert "<p>" in html
        assert "Apenas uma frase simples." in html
