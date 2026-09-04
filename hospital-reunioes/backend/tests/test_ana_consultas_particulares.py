"""Testes da API da Ana: auth por API key de serviço + consultas particulares (issue #288).

Cobre (critérios de aceite):
- Requisição sem chave ou com chave errada é recusada; com a chave correta,
  devolve as consultas particulares ativas com preços e diferenciais.
- A chave não aparece em logs nem em respostas.
- Os dados importados conferem com o export do NocoDB usado como fonte.
"""

from __future__ import annotations

import logging
import os
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.config import settings  # noqa: E402
from app.dependencies import get_supabase_client  # noqa: E402
from app.limiter import limiter  # noqa: E402
from app.middleware.request_context import RequestContextMiddleware  # noqa: E402
from app.routers import ana as ana_router  # noqa: E402
from scripts.oneshot.import_consultas_particulares import parse_export, to_sql  # noqa: E402

CHAVE_CORRETA = "chave-teste-ana-para-pytest"


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


def _make_app(consultas: list | None = None) -> TestClient:
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    # Middleware real de log por request: o teste de vazamento da chave observa
    # o mesmo pipeline de logging que roda em produção.
    app.add_middleware(RequestContextMiddleware)
    app.include_router(ana_router.router, prefix="/api")

    class _Query:
        def __init__(self, rows: list):
            self._rows = rows
            self._filters: dict = {}

        def select(self, *_args, **_kwargs):
            return self

        def eq(self, col, value):
            self._filters[col] = value
            return self

        def order(self, *_args, **_kwargs):
            return self

        def execute(self):
            data = [dict(r) for r in self._rows if all(r.get(c) == v for c, v in self._filters.items())]
            self._filters = {}
            return type("R", (), {"data": data})()

    class _SupabaseMock:
        def table(self, name: str):
            assert name == "consultas_particulares", f"Tabela inesperada: {name}"
            return _Query(consultas or [])

    app.dependency_overrides[get_supabase_client] = _SupabaseMock
    return TestClient(app)


class TestAuthPorApiKey:
    def test_sem_chave_e_recusada(self, monkeypatch):
        monkeypatch.setattr(settings, "ana_api_key", CHAVE_CORRETA)
        client = _make_app()
        r = client.get("/api/ana/consultas-particulares")
        assert r.status_code == 401

    def test_chave_errada_e_recusada(self, monkeypatch):
        monkeypatch.setattr(settings, "ana_api_key", CHAVE_CORRETA)
        client = _make_app()
        r = client.get("/api/ana/consultas-particulares", headers={"X-API-Key": "chave-errada"})
        assert r.status_code == 401

    def test_chave_nao_configurada_recusa_tudo(self, monkeypatch):
        monkeypatch.setattr(settings, "ana_api_key", "")
        client = _make_app()
        r = client.get("/api/ana/consultas-particulares", headers={"X-API-Key": ""})
        assert r.status_code == 401


def _consulta_row(especialidade: str, valor: float, ativo: bool = True) -> dict:
    return {
        "id": f"id-{especialidade.lower()}",
        "especialidade": especialidade,
        "valor_rs": valor,
        "descricao_servico": f"Consulta de {especialidade}.",
        "diferencial_1": "Estrutura hospitalar completa",
        "diferencial_2": "Equipe experiente",
        "diferencial_3": "Exames integrados",
        "alta_demanda": False,
        "observacoes_ana": "",
        "ativo": ativo,
        "ultima_atualizacao": "2026-03-10",
    }


class TestLeituraConsultasParticulares:
    def test_chave_correta_devolve_ativas_com_precos_e_diferenciais(self, monkeypatch):
        monkeypatch.setattr(settings, "ana_api_key", CHAVE_CORRETA)
        client = _make_app(
            consultas=[
                _consulta_row("Cardiologia", 380.00),
                _consulta_row("Ginecologia", 340.00, ativo=False),
                _consulta_row("Pediatria", 320.00),
            ]
        )
        r = client.get("/api/ana/consultas-particulares", headers={"X-API-Key": CHAVE_CORRETA})
        assert r.status_code == 200
        consultas = r.json()["consultas_particulares"]
        assert [c["especialidade"] for c in consultas] == ["Cardiologia", "Pediatria"]
        cardio = consultas[0]
        assert cardio["valor_rs"] == 380.00
        assert cardio["diferencial_1"] == "Estrutura hospitalar completa"
        assert cardio["diferencial_2"] == "Equipe experiente"
        assert cardio["diferencial_3"] == "Exames integrados"


class TestChaveNaoVaza:
    def test_chave_nao_aparece_em_logs_nem_em_respostas(self, monkeypatch, caplog):
        monkeypatch.setattr(settings, "ana_api_key", CHAVE_CORRETA)
        client = _make_app(consultas=[_consulta_row("Cardiologia", 380.00)])

        with caplog.at_level(logging.DEBUG):
            r_errada = client.get("/api/ana/consultas-particulares", headers={"X-API-Key": "chave-errada"})
            r_sem = client.get("/api/ana/consultas-particulares")
            r_ok = client.get("/api/ana/consultas-particulares", headers={"X-API-Key": CHAVE_CORRETA})

        for resposta in (r_errada, r_sem, r_ok):
            assert CHAVE_CORRETA not in resposta.text
        assert "chave-errada" not in r_errada.text
        assert CHAVE_CORRETA not in caplog.text
        assert "chave-errada" not in caplog.text


class TestImportDoExport:
    """O parse do export do NocoDB (fonte do import) confere com o arquivo fonte."""

    def _rows(self):
        fixture = os.path.join(os.path.dirname(__file__), "fixtures", "export_nocodb_consultas_particulares.csv")
        return parse_export(fixture)

    def test_importa_todas_as_linhas_do_export(self):
        rows = self._rows()
        assert len(rows) == 10
        assert [r["especialidade"] for r in rows[:3]] == ["Cardiologia", "Pediatria", "Ortopedia"]

    def test_valores_e_flags_conferem_com_a_fonte(self):
        rows = {r["especialidade"]: r for r in self._rows()}
        cardio = rows["Cardiologia"]
        assert cardio["valor_rs"] == 380.00
        assert cardio["alta_demanda"] is True
        assert cardio["ativo"] is True
        assert cardio["ultima_atualizacao"] == "2026-03-10"
        assert cardio["diferencial_1"] == (
            "Estrutura hospitalar completa com UTI e centro cirúrgico cardíaco no mesmo complexo"
        )
        assert cardio["descricao_servico"].startswith("Consulta com cardiologista adulto")
        # Ginecologia é a única inativa no export
        assert rows["Ginecologia"]["ativo"] is False
        assert rows["Ginecologia"]["valor_rs"] == 340.00
        assert rows["Ortopedia"]["alta_demanda"] is False

    def test_tipografia_sanitizada_no_import(self):
        """Travessão/meia-risca do dado fonte não chegam ao banco (ADR 0013):
        a Ana repassa esses campos literalmente a pacientes."""
        for row in self._rows():
            for valor in row.values():
                if isinstance(valor, str):
                    assert "—" not in valor
                    assert "–" not in valor
        # A sanitização preserva o conteúdo (vírgula no lugar do travessão)
        cardio = {r["especialidade"]: r for r in self._rows()}["Cardiologia"]
        assert cardio["diferencial_3"] == "Resultados de exames integrados, médico já acessa tudo na consulta"

    def test_seed_da_migration_confere_com_o_export(self):
        """O bloco INSERT da migration 061 é exatamente o gerado do export
        (amarra o que sobe em produção à fonte, não só o parser)."""
        migration = os.path.join(
            os.path.dirname(__file__), "..", "..", "supabase", "migrations", "061_consultas_particulares_ana.sql"
        )
        with open(migration, encoding="utf-8") as f:
            conteudo = f.read()
        assert to_sql(self._rows()) in conteudo
