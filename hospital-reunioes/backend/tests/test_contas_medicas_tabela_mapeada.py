"""Tabela de preço em PDF ou planilha, com o mapeamento proposto pela IA (issue #1146, PRD #1129).

A tabela que o convênio manda no formato dele (PDF, XLSX ou CSV com outro
cabeçalho) entra em dois passos: a proposta, em que a IA diz qual coluna é
código, descrição, unidade e preço e a tela mostra 20 linhas convertidas e o
total, sem gravar nada; e a confirmação, que grava pelo importador das
tabelas com o mapeamento e a chave do arquivo. O arquivo com o cabeçalho de um
mapeamento já confirmado reaproveita o mapeamento, sem IA.

A IA é dublada na porta do módulo (`chamada_curta`), com a contagem de
chamadas. As planilhas são montadas aqui, com as partes que o Excel grava.
"""

from __future__ import annotations

import io
import json
import zipfile
from datetime import date
from decimal import Decimal
from html import escape
from types import SimpleNamespace

import pytest
from test_contas_medicas_operadoras import FATURISTA, GESTAO, _Banco, _cliente, _com_operadoras

from app.limiter import limiter
from app.services.contas_medicas import tabela_mapeada
from app.services.contas_medicas.tabelas import preco

DIA = date(2026, 10, 5)

ROTA_PROPOSTA = "/api/contas-medicas/operadoras/ALFA/tabelas/proposta"
ROTA_CONFIRMACAO = "/api/contas-medicas/operadoras/ALFA/tabelas/mapeada"

# O cabeçalho do convênio: outra ordem e outros nomes que os dos CSVs do diretor.
CABECALHO = ["Preço (R$)", "Descrição do item", "Cód. TUSS", "Unid.", "Cód. interno"]

# O que a IA dublada responde para esse cabeçalho.
PROPOSTA_DA_IA = {
    "codigo": "Cód. TUSS",
    "codigo_alternativo": "Cód. interno",
    "descricao": "Descrição do item",
    "unidade": "Unid.",
    "precos": [{"chave": "valor", "coluna": "Preço (R$)"}],
}


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


class _IaDublada:
    """A porta curta do adaptador: guarda o que recebeu e devolve a proposta."""

    def __init__(self, resposta: dict):
        self.resposta = resposta
        self.chamadas: list[dict] = []

    def __call__(self, instrucao, conteudo, saida, **kwargs):
        self.chamadas.append({"instrucao": instrucao, "conteudo": conteudo, **kwargs})
        return saida.model_validate(self.resposta)


@pytest.fixture
def ia(monkeypatch) -> _IaDublada:
    dublada = _IaDublada(PROPOSTA_DA_IA)
    monkeypatch.setattr(tabela_mapeada, "chamada_curta", dublada)
    return dublada


class _Bucket:
    def __init__(self, banco, nome: str):
        self._banco = banco
        self._nome = nome

    def upload(self, caminho, conteudo, _opcoes=None):
        self._banco.bucket[(self._nome, caminho)] = conteudo
        return SimpleNamespace(path=caminho)


def _banco_com_bucket(banco: _Banco) -> _Banco:
    banco.bucket = {}
    banco.storage = SimpleNamespace(from_=lambda nome: _Bucket(banco, nome))
    return banco


def _linhas(n: int) -> list[list[str | float]]:
    """N itens: o código TUSS 7000000<i>, o interno A<i> e o preço 1,50 + i."""
    return [[1.5 + i, f"Item {i}", f"7000{i:04d}", "UN", f"A{i}"] for i in range(n)]


def _coluna(indice: int) -> str:
    letras = ""
    indice += 1
    while indice:
        indice, resto = divmod(indice - 1, 26)
        letras = chr(65 + resto) + letras
    return letras


def _xlsx(cabecalho: list[str], linhas: list[list[str | float]]) -> bytes:
    """Uma planilha com as partes que o Excel grava: o texto em `sharedStrings`
    e o número na própria célula."""
    textos: list[str] = []

    def celula(ref: str, valor) -> str:
        if isinstance(valor, int | float):
            return f'<c r="{ref}"><v>{valor}</v></c>'
        textos.append(str(valor))
        return f'<c r="{ref}" t="s"><v>{len(textos) - 1}</v></c>'

    xml_linhas = []
    for numero, valores in enumerate([cabecalho, *linhas], start=1):
        celulas = "".join(celula(f"{_coluna(i)}{numero}", v) for i, v in enumerate(valores))
        xml_linhas.append(f'<row r="{numero}">{celulas}</row>')
    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    dados = "".join(xml_linhas)
    planilha = f'<?xml version="1.0" encoding="UTF-8"?><worksheet {ns}><sheetData>{dados}</sheetData></worksheet>'
    compartilhados = "".join(f"<si><t>{escape(t)}</t></si>" for t in textos)
    strings = f'<?xml version="1.0" encoding="UTF-8"?><sst {ns} count="{len(textos)}">{compartilhados}</sst>'
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as zf:
        zf.writestr("[Content_Types].xml", "<Types/>")
        zf.writestr("xl/workbook.xml", f"<workbook {ns}/>")
        zf.writestr("xl/worksheets/sheet1.xml", planilha)
        zf.writestr("xl/sharedStrings.xml", strings)
    return saida.getvalue()


XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _propor(cliente, nome: str, conteudo: bytes, tipo: str = XLSX, mapeamento: dict | None = None):
    dados = {"mapeamento": json.dumps(mapeamento)} if mapeamento else {}
    return cliente.post(ROTA_PROPOSTA, data=dados, files={"arquivo": (nome, conteudo, tipo)})


def _confirmar(cliente, nome: str, conteudo: bytes, mapeamento: dict, tipo: str = XLSX, categoria="MATERIAL"):
    dados = {"categoria": categoria, "vigencia_inicio": "2026-05-01", "mapeamento": json.dumps(mapeamento)}
    return cliente.post(ROTA_CONFIRMACAO, data=dados, files={"arquivo": (nome, conteudo, tipo)})


# ═══════════════════════════════════════════════════════════════════════════
# 1. A proposta: a IA diz as colunas, a tela vê a amostra, nada é gravado
# ═══════════════════════════════════════════════════════════════════════════


class TestProposta:
    def test_planilha_de_outro_cabecalho_ganha_o_mapeamento_da_ia_a_amostra_de_20_e_o_total_sem_gravar(self, ia):
        cliente, banco = _cliente(GESTAO, _banco_com_bucket(_com_operadoras("ALFA")))

        resposta = _propor(cliente, "tabela-alfa.xlsx", _xlsx(CABECALHO, _linhas(25)))

        assert resposta.status_code == 200, resposta.text
        corpo = resposta.json()
        assert corpo["cabecalho"] == CABECALHO
        assert corpo["mapeamento"] == PROPOSTA_DA_IA
        assert corpo["origem"] == "IA"
        assert corpo["total"] == 25
        assert len(corpo["amostra"]) == 20
        assert corpo["amostra"][3] == {
            "codigo": "70000003",
            "codigo_alternativo": "A3",
            "descricao": "Item 3",
            "unidade": "UN",
            "precos": {"valor": 4.5},
        }
        assert corpo["erro"] is None
        # A IA viu o cabeçalho do arquivo.
        [chamada] = ia.chamadas
        assert "Cód. TUSS" in chamada["conteudo"]
        # Nada vale antes de confirmar: nem tabela, nem item, nem arquivo guardado.
        assert banco.linhas("cm_tabela_preco") == []
        assert banco.linhas("cm_tabela_preco_item") == []
        assert banco.linhas("cm_operadora_tabela") == []
        assert banco.bucket == {}

    def test_a_pessoa_ajusta_o_mapeamento_e_a_amostra_sai_pelo_ajuste_sem_ia(self, ia):
        cliente, _banco = _cliente(GESTAO, _banco_com_bucket(_com_operadoras("ALFA")))
        ajuste = {**PROPOSTA_DA_IA, "codigo": "Cód. interno", "codigo_alternativo": "Cód. TUSS"}

        resposta = _propor(cliente, "tabela-alfa.xlsx", _xlsx(CABECALHO, _linhas(3)), mapeamento=ajuste)

        assert resposta.status_code == 200, resposta.text
        corpo = resposta.json()
        assert (corpo["origem"], corpo["total"]) == ("PESSOA", 3)
        assert [i["codigo"] for i in corpo["amostra"]] == ["A0", "A1", "A2"]
        assert ia.chamadas == []

    def test_mapeamento_com_coluna_de_preco_que_nao_e_numero_volta_com_o_erro_para_ajustar(self, ia):
        cliente, banco = _cliente(GESTAO, _banco_com_bucket(_com_operadoras("ALFA")))
        errado = {**PROPOSTA_DA_IA, "precos": [{"chave": "valor", "coluna": "Descrição do item"}]}

        resposta = _propor(cliente, "tabela-alfa.xlsx", _xlsx(CABECALHO, _linhas(3)), mapeamento=errado)

        assert resposta.status_code == 200, resposta.text
        assert "Linha 2" in resposta.json()["erro"]
        assert resposta.json()["total"] == 0
        assert banco.linhas("cm_tabela_preco") == []

    def test_csv_com_cabecalho_de_formato_conhecido_vai_pela_carga_direta_sem_ia(self, ia):
        cliente, _banco = _cliente(GESTAO, _banco_com_bucket(_com_operadoras("ALFA")))
        texto = "secao;codigo;descricao;valor\nDIARIA;60000090;Diária;1050.00\n"

        resposta = _propor(cliente, "diarias.csv", texto.encode("utf-8"), tipo="text/csv")

        assert resposta.status_code == 200, resposta.text
        assert resposta.json() == {"conhecido": True, "descricao_formato": "diárias e taxas com valor único"}
        assert ia.chamadas == []


# ═══════════════════════════════════════════════════════════════════════════
# 2. A confirmação: grava pelo importador e a busca de preço acha pela chave
# ═══════════════════════════════════════════════════════════════════════════


class TestConfirmacao:
    def test_confirmado_os_itens_sao_gravados_com_o_mapeamento_e_o_arquivo_e_o_preco_acha_pela_chave(self, ia):
        cliente, banco = _cliente(GESTAO, _banco_com_bucket(_com_operadoras("ALFA")))
        planilha = _xlsx(CABECALHO, _linhas(25))

        resposta = _confirmar(cliente, "tabela-alfa.xlsx", planilha, PROPOSTA_DA_IA)

        assert resposta.status_code == 201, resposta.text
        assert (resposta.json()["itens"], resposta.json()["categoria"]) == (25, "MATERIAL")
        [tabela] = banco.linhas("cm_tabela_preco")
        assert tabela["mapeamento_json"]["colunas"] == PROPOSTA_DA_IA
        assert tabela["mapeamento_json"]["cabecalho"] == CABECALHO
        assert banco.bucket == {("contas-medicas", tabela["arquivo_original"]): planilha}
        assert len(banco.linhas("cm_tabela_preco_item")) == 25
        # O preço do item 3 é 4,50; o código alternativo acha o mesmo item.
        assert preco(banco, "op-ALFA", "MATERIAL", "70000003", DIA) == Decimal("4.5")
        assert preco(banco, "op-ALFA", "MATERIAL", "A3", DIA) == Decimal("4.5")
        # A confirmação não pergunta de novo à IA.
        assert ia.chamadas == []

    def test_dois_precos_por_plano_saem_pela_coluna_do_plano(self, ia):
        cliente, banco = _cliente(GESTAO, _banco_com_bucket(_com_operadoras("ALFA")))
        texto = 'Codigo,Produto,Valor Enfermaria,Valor Apto\n10101012,Visita,"R$ 1.234,56","R$ 2.000,00"\n'
        mapeamento = {
            "codigo": "Codigo",
            "codigo_alternativo": None,
            "descricao": "Produto",
            "unidade": None,
            "precos": [{"chave": "comum", "coluna": "Valor Enfermaria"}, {"chave": "carioca", "coluna": "Valor Apto"}],
        }

        resposta = _confirmar(cliente, "honorarios.csv", texto.encode("utf-8"), mapeamento, tipo="text/csv")

        assert resposta.status_code == 201, resposta.text
        assert preco(banco, "op-ALFA", "MATERIAL", "10101012", DIA, "COMUM") == Decimal("1234.56")
        assert preco(banco, "op-ALFA", "MATERIAL", "10101012", DIA, "CARIOCA") == Decimal("2000.00")

    def test_mapeamento_que_aponta_coluna_fora_do_arquivo_e_recusado_e_nada_e_gravado(self, ia):
        cliente, banco = _cliente(GESTAO, _banco_com_bucket(_com_operadoras("ALFA")))
        errado = {**PROPOSTA_DA_IA, "codigo": "Código"}

        resposta = _confirmar(cliente, "tabela-alfa.xlsx", _xlsx(CABECALHO, _linhas(3)), errado)

        assert resposta.status_code == 422
        assert "Código" in resposta.json()["detail"]
        assert banco.linhas("cm_tabela_preco") == []
        assert banco.bucket == {}


# ═══════════════════════════════════════════════════════════════════════════
# 3. O mesmo cabeçalho reaproveita o mapeamento confirmado, sem IA
# ═══════════════════════════════════════════════════════════════════════════


class TestReaproveitamento:
    def test_segundo_arquivo_com_o_mesmo_cabecalho_nao_chama_a_ia(self, ia):
        cliente, _banco = _cliente(GESTAO, _banco_com_bucket(_com_operadoras("ALFA")))
        primeiro = _xlsx(CABECALHO, _linhas(25))
        assert _propor(cliente, "maio.xlsx", primeiro).json()["origem"] == "IA"
        assert _confirmar(cliente, "maio.xlsx", primeiro, PROPOSTA_DA_IA).status_code == 201

        resposta = _propor(cliente, "junho.xlsx", _xlsx(CABECALHO, _linhas(30)))

        assert resposta.status_code == 200, resposta.text
        assert (resposta.json()["origem"], resposta.json()["total"]) == ("CONFIRMADO", 30)
        assert resposta.json()["mapeamento"] == PROPOSTA_DA_IA
        assert len(ia.chamadas) == 1

    def test_segundo_arquivo_com_o_cabecalho_em_outra_caixa_reaproveita_com_os_nomes_do_arquivo_novo(self, ia):
        cliente, _banco = _cliente(GESTAO, _banco_com_bucket(_com_operadoras("ALFA")))
        primeiro = _xlsx(CABECALHO, _linhas(5))
        _propor(cliente, "maio.xlsx", primeiro)
        assert _confirmar(cliente, "maio.xlsx", primeiro, PROPOSTA_DA_IA).status_code == 201

        resposta = _propor(cliente, "junho.xlsx", _xlsx([c.upper() for c in CABECALHO], _linhas(7)))

        corpo = resposta.json()
        assert (corpo["origem"], corpo["erro"], corpo["total"]) == ("CONFIRMADO", None, 7)
        assert corpo["mapeamento"]["codigo"] == "CÓD. TUSS"
        assert corpo["mapeamento"]["precos"] == [{"chave": "valor", "coluna": "PREÇO (R$)"}]
        assert len(ia.chamadas) == 1

    def test_cabecalho_diferente_pergunta_a_ia_de_novo(self, ia):
        cliente, _banco = _cliente(GESTAO, _banco_com_bucket(_com_operadoras("ALFA")))
        primeiro = _xlsx(CABECALHO, _linhas(5))
        _propor(cliente, "maio.xlsx", primeiro)
        _confirmar(cliente, "maio.xlsx", primeiro, PROPOSTA_DA_IA)

        _propor(cliente, "outra.xlsx", _xlsx([*CABECALHO, "Observação"], [[*linha, "x"] for linha in _linhas(5)]))

        assert len(ia.chamadas) == 2


# ═══════════════════════════════════════════════════════════════════════════
# 4. O PDF passa pelo mesmo caminho
# ═══════════════════════════════════════════════════════════════════════════


def _pdf_de_verdade(*paginas: str) -> bytes:
    """PDF gerado pelo WeasyPrint do projeto, uma página por texto, em `<pre>`
    para o `pdftotext -layout` devolver as colunas como estão."""
    from weasyprint import HTML

    corpo = "".join(
        f'<pre style="page-break-before: always; font-size: 8pt">{escape(texto)}</pre>' for texto in paginas
    )
    return HTML(string=f"<html><body>{corpo}</body></html>").write_pdf()


def _pagina_do_pdf(linhas: list[list[str | float]]) -> str:
    """A tabela como o convênio imprime: título, cabeçalho e colunas alinhadas,
    com o preço em vírgula decimal."""
    larguras = (14, 22, 12, 8, 12)
    texto = ["CONVENIO ALFA", "Tabela de materiais", ""]
    for valores in [CABECALHO, *linhas]:
        celulas = [(f"{v:.2f}".replace(".", ",") if isinstance(v, float) else str(v)) for v in valores]
        texto.append("".join(c.ljust(larguras[i]) for i, c in enumerate(celulas)).rstrip())
    return "\n".join(texto)


class TestPdf:
    def test_pdf_de_tabela_passa_pela_proposta_e_pela_confirmacao(self, ia):
        cliente, banco = _cliente(GESTAO, _banco_com_bucket(_com_operadoras("ALFA")))
        linhas = _linhas(25)
        pdf = _pdf_de_verdade(_pagina_do_pdf(linhas[:15]), _pagina_do_pdf(linhas[15:]))

        proposta = _propor(cliente, "tabela-alfa.pdf", pdf, tipo="application/pdf")

        assert proposta.status_code == 200, proposta.text
        corpo = proposta.json()
        assert (corpo["origem"], corpo["total"], len(corpo["amostra"])) == ("IA", 25, 20)
        assert corpo["cabecalho"] == CABECALHO
        assert corpo["amostra"][3]["precos"] == {"valor": 4.5}
        assert banco.linhas("cm_tabela_preco") == []

        confirmada = _confirmar(cliente, "tabela-alfa.pdf", pdf, corpo["mapeamento"], tipo="application/pdf")

        assert confirmada.status_code == 201, confirmada.text
        assert confirmada.json()["itens"] == 25
        assert preco(banco, "op-ALFA", "MATERIAL", "70000020", DIA) == Decimal("21.5")


# ═══════════════════════════════════════════════════════════════════════════
# 5. A permissão
# ═══════════════════════════════════════════════════════════════════════════


class TestPermissao:
    @pytest.mark.parametrize("rota", ["proposta", "confirmacao"])
    def test_quem_nao_tem_regra_contratual_e_tabelas_recebe_403_sem_ia_e_sem_gravar(self, ia, rota):
        cliente, banco = _cliente(FATURISTA, _banco_com_bucket(_com_operadoras("ALFA")))
        planilha = _xlsx(CABECALHO, _linhas(3))

        if rota == "proposta":
            resposta = _propor(cliente, "tabela-alfa.xlsx", planilha)
        else:
            resposta = _confirmar(cliente, "tabela-alfa.xlsx", planilha, PROPOSTA_DA_IA)

        assert resposta.status_code == 403
        assert ia.chamadas == []
        assert banco.linhas("cm_tabela_preco") == []
        assert banco.bucket == {}


class TestAsRotasEstaoNoApp:
    def test_o_app_de_verdade_registra_a_proposta_e_a_confirmacao(self):
        """Fonte: o schema OpenAPI, e não `app.routes` (FastAPI 0.141, issues #542 e #546)."""
        from app.main import app

        cache = app.openapi_schema
        try:
            caminhos = app.openapi()["paths"]
        finally:
            app.openapi_schema = cache

        assert len(caminhos) > 50
        assert "post" in caminhos["/api/contas-medicas/operadoras/{sigla}/tabelas/proposta"]
        assert "post" in caminhos["/api/contas-medicas/operadoras/{sigla}/tabelas/mapeada"]
