"""Testes do utilitário Super Admin de conversão PDF/DOCX → Markdown (issue #38).

Conversão 100% local via markitdown (sem mock — determinística e offline).
Fixtures binárias commitadas em tests/fixtures/ (geradas por script descartável,
validadas com o próprio markitdown antes do commit):
- exemplo.pdf          — PDF nativo com texto pt-BR (>200 chars extraíveis)
- exemplo_sem_texto.pdf — PDF válido só com gráfico (simula escaneado)
- exemplo.docx         — DOCX mínimo com heading + negrito + acentos
"""

from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.dependencies import require_super_admin
from app.routers.admin import utilitarios as utilitarios_router
from app.services import markdown_converter
from app.services.markdown_converter import sugerir_nome_md

FIXTURES = Path(__file__).parent / "fixtures"
URL = "/api/admin/utilitarios/converter-markdown"
ADMIN = {"id": "ADM1", "nome_completo": "Admin Teste", "access_profile": "super_admin"}


def _fixture(nome: str) -> bytes:
    return (FIXTURES / nome).read_bytes()


@pytest.fixture
def make_client(monkeypatch):
    """Factory: TestClient com o router de utilitários e o gate de super admin plugado.

    O limiter fica desabilitado (este arquivo dispara mais requests que o limite
    de 10/minute); o decorator @limiter.limit exige app.state.limiter mesmo assim.
    """

    def _factory(*, admin: bool = True) -> TestClient:
        from slowapi import _rate_limit_exceeded_handler
        from slowapi.errors import RateLimitExceeded

        from app.limiter import limiter

        monkeypatch.setattr(limiter, "enabled", False)

        app = FastAPI()
        app.state.limiter = limiter
        app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
        app.include_router(utilitarios_router.router, prefix="/api")

        if admin:
            app.dependency_overrides[require_super_admin] = lambda: dict(ADMIN)
        else:

            def _negar():
                raise HTTPException(status_code=403, detail="Acao restrita a super admins")

            app.dependency_overrides[require_super_admin] = _negar
        return TestClient(app)

    return _factory


# ═══════════════════════════════════════════════════════════════════════════
# Conversões com sucesso
# ═══════════════════════════════════════════════════════════════════════════


class TestConversao:
    def test_converte_pdf_com_texto_retorna_markdown(self, make_client):
        """PDF nativo converte: conteúdo fiel (acentos), nome .md sugerido e,
        por ter pouco texto (<1000 chars), o aviso de conferência."""
        client = make_client()
        r = client.post(URL, files={"file": ("Relatório 2026.pdf", _fixture("exemplo.pdf"), "application/pdf")})
        assert r.status_code == 200
        body = r.json()
        assert "três pendências" in body["markdown"]
        assert "Reunião" in body["markdown"]
        assert body["nome_arquivo_sugerido"] == "Relatório 2026.md"
        assert isinstance(body["avisos"], list) and len(body["avisos"]) == 1
        assert "title" in body

    def test_converte_docx_retorna_markdown_estruturado(self, make_client):
        """DOCX preserva estrutura: heading vira '#', negrito vira '**'."""
        client = make_client()
        r = client.post(
            URL,
            files={
                "file": (
                    "exemplo.docx",
                    _fixture("exemplo.docx"),
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert "# Relatório de Teste" in body["markdown"]
        assert "**três pendências**" in body["markdown"]
        assert body["nome_arquivo_sugerido"] == "exemplo.md"
        assert body["avisos"] == []


# ═══════════════════════════════════════════════════════════════════════════
# Validações de entrada
# ═══════════════════════════════════════════════════════════════════════════


class TestValidacoes:
    def test_extensao_invalida_retorna_400(self, make_client):
        client = make_client()
        r = client.post(URL, files={"file": ("notas.txt", b"texto qualquer", "text/plain")})
        assert r.status_code == 400
        assert ".pdf ou .docx" in r.json()["detail"]

    def test_sem_extensao_retorna_400(self, make_client):
        client = make_client()
        r = client.post(URL, files={"file": ("arquivo", b"conteudo", "application/octet-stream")})
        assert r.status_code == 400

    def test_arquivo_vazio_retorna_400(self, make_client):
        client = make_client()
        r = client.post(URL, files={"file": ("vazio.pdf", b"", "application/pdf")})
        assert r.status_code == 400
        assert r.json()["detail"] == "Arquivo vazio"

    def test_arquivo_acima_de_15mb_retorna_413(self, make_client):
        client = make_client()
        gigante = b"0" * (utilitarios_router.MAX_FILE_BYTES + 1)
        r = client.post(URL, files={"file": ("grande.pdf", gigante, "application/pdf")})
        assert r.status_code == 413
        assert "15 MB" in r.json()["detail"]

    def test_pdf_sem_texto_retorna_422(self, make_client):
        """PDF válido sem camada de texto (escaneado) → orienta o usuário."""
        client = make_client()
        r = client.post(URL, files={"file": ("scan.pdf", _fixture("exemplo_sem_texto.pdf"), "application/pdf")})
        assert r.status_code == 422
        assert "escaneado" in r.json()["detail"]

    def test_pdf_corrompido_com_header_cai_no_422(self, make_client):
        """pdfminer é leniente: lixo com header %PDF extrai vazio → mesmo 422
        do escaneado (markitdown não levanta exceção nesse caso)."""
        client = make_client()
        r = client.post(URL, files={"file": ("corrompido.pdf", b"%PDF-1.4 lixo sem estrutura", "application/pdf")})
        assert r.status_code == 422


# ═══════════════════════════════════════════════════════════════════════════
# Falha interna e autorização
# ═══════════════════════════════════════════════════════════════════════════


class TestFalhasEAcesso:
    def test_falha_do_conversor_retorna_500_com_mensagem_amigavel(self, make_client, monkeypatch):
        """Se o markitdown levantar qualquer exceção, o router responde 500
        com mensagem pt-BR (sem vazar stacktrace)."""

        def _boom(*_a, **_kw):
            raise markdown_converter.ConversaoError("Falha simulada")

        monkeypatch.setattr(markdown_converter, "converter_para_markdown", _boom)
        client = make_client()
        r = client.post(URL, files={"file": ("ata.pdf", _fixture("exemplo.pdf"), "application/pdf")})
        assert r.status_code == 500
        assert "Falha ao converter" in r.json()["detail"]

    def test_nao_admin_retorna_403(self, make_client):
        client = make_client(admin=False)
        r = client.post(URL, files={"file": ("ata.pdf", _fixture("exemplo.pdf"), "application/pdf")})
        assert r.status_code == 403


# ═══════════════════════════════════════════════════════════════════════════
# Unit: sugestão de nome do arquivo de saída
# ═══════════════════════════════════════════════════════════════════════════


class TestSugerirNomeMd:
    def test_troca_extensao_preservando_acentos(self):
        assert sugerir_nome_md("Relatório Final v2.PDF") == "Relatório Final v2.md"

    def test_descarta_path_do_cliente(self):
        assert sugerir_nome_md("../../etc/passwd.pdf") == "passwd.md"
        assert sugerir_nome_md("C:\\Users\\x\\ata.docx") == "ata.md"

    def test_remove_caracteres_problematicos(self):
        assert sugerir_nome_md('a:b*c?"d.pdf') == "abcd.md"

    def test_fallback_para_documento(self):
        assert sugerir_nome_md(None) == "documento.md"
        assert sugerir_nome_md("") == "documento.md"
        assert sugerir_nome_md(".pdf") == "documento.md"
