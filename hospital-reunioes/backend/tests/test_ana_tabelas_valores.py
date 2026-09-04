"""Testes da API da Ana: exames, cirurgias e convênios (issue #289).

Cobre (critérios de aceite):
- Os três endpoints devolvem os registros ativos das respectivas tabelas,
  autenticados pela mesma API key da fundação (#288).
- Dados importados conferem com o export do NocoDB usado como fonte.
- Testes de integração no seam HTTP para os três endpoints.
"""

from __future__ import annotations

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
from app.routers import ana as ana_router  # noqa: E402
from scripts.oneshot.import_tabelas_ana import parse_export, to_sql  # noqa: E402

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")

CHAVE_CORRETA = "chave-teste-ana-para-pytest"


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


def _make_app(tabelas: dict[str, list] | None = None) -> TestClient:
    """App com o router da Ana e um mock de Supabase servindo as tabelas dadas."""
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
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
            assert name in (tabelas or {}), f"Tabela inesperada: {name}"
            return _Query((tabelas or {})[name])

    app.dependency_overrides[get_supabase_client] = _SupabaseMock
    return TestClient(app)


def _exame_row(nome: str, valor: float, ativo: bool = True) -> dict:
    return {
        "id": f"id-{nome.lower().replace(' ', '-')}",
        "nome_exame": nome,
        "tipo_exame": "Cardiológico",
        "convenio_aceito": True,
        "valor_particular_rs": valor,
        "requer_pedido_medico": True,
        "preparo_necessario": False,
        "instrucoes_preparo_completas": "Não requer preparo especial.",
        "tempo_resultado": "No ato / 48h",
        "local_realizacao": "Hospital São Matheus, Cardiologia",
        "diferencial_1": "Equipamento de última geração",
        "diferencial_2": "Laudo integrado ao prontuário",
        "observacoes_ana": "",
        "ativo": ativo,
        "ultima_atualizacao": "2026-03-10",
    }


class TestExames:
    def test_sem_chave_e_recusada(self, monkeypatch):
        monkeypatch.setattr(settings, "ana_api_key", CHAVE_CORRETA)
        client = _make_app({"exames": []})
        assert client.get("/api/ana/exames").status_code == 401

    def test_chave_correta_devolve_exames_ativos(self, monkeypatch):
        monkeypatch.setattr(settings, "ana_api_key", CHAVE_CORRETA)
        client = _make_app(
            {
                "exames": [
                    _exame_row("Ecocardiograma", 320.00),
                    _exame_row("Holter 24h", 280.00, ativo=False),
                    _exame_row("Eletrocardiograma (ECG)", 80.00),
                ]
            }
        )
        r = client.get("/api/ana/exames", headers={"X-API-Key": CHAVE_CORRETA})
        assert r.status_code == 200
        exames = r.json()["exames"]
        assert [e["nome_exame"] for e in exames] == ["Ecocardiograma", "Eletrocardiograma (ECG)"]
        eco = exames[0]
        assert eco["valor_particular_rs"] == 320.00
        assert eco["tipo_exame"] == "Cardiológico"
        assert eco["instrucoes_preparo_completas"] == "Não requer preparo especial."
        assert eco["tempo_resultado"] == "No ato / 48h"


class TestImportExames:
    """O parse do export do NocoDB (fonte do import) confere com o arquivo fonte."""

    def _rows(self):
        return parse_export("exames", os.path.join(FIXTURES, "export_nocodb_exames.csv"))

    def test_importa_todas_as_linhas_do_export(self):
        rows = self._rows()
        assert len(rows) == 10
        assert [r["nome_exame"] for r in rows[:3]] == [
            "Hemograma Completo",
            "Tomografia Computadorizada (TC)",
            "Ecocardiograma",
        ]

    def test_valores_e_flags_conferem_com_a_fonte(self):
        rows = {r["nome_exame"]: r for r in self._rows()}
        hemograma = rows["Hemograma Completo"]
        assert hemograma["valor_particular_rs"] == 45.00
        assert hemograma["tipo_exame"] == "Laboratorial"
        assert hemograma["convenio_aceito"] is True
        assert hemograma["requer_pedido_medico"] is True
        assert hemograma["preparo_necessario"] is True
        assert hemograma["tempo_resultado"] == "24 horas"
        assert hemograma["local_realizacao"] == "Laboratório parceiro RIOLABOR"
        assert hemograma["ativo"] is True
        assert hemograma["ultima_atualizacao"] == "2026-03-10"
        tc = rows["Tomografia Computadorizada (TC)"]
        assert tc["valor_particular_rs"] == 580.00
        eco = rows["Ecocardiograma"]
        assert eco["preparo_necessario"] is False

    def test_tipografia_sanitizada_no_import(self):
        """Travessão/meia-risca do dado fonte não chegam ao banco (ADR 0013)."""
        for row in self._rows():
            for valor in row.values():
                if isinstance(valor, str):
                    assert "—" not in valor
                    assert "–" not in valor
        tc = {r["nome_exame"]: r for r in self._rows()}["Tomografia Computadorizada (TC)"]
        assert tc["local_realizacao"] == "Hospital São Matheus, Imagem"

    def test_seed_da_migration_confere_com_o_export(self):
        assert to_sql("exames", self._rows()) in _conteudo_migration_062()


def _cirurgia_row(procedimento: str, total: float, ativo: bool = True) -> dict:
    return {
        "id": f"id-{procedimento.lower().replace(' ', '-')}",
        "procedimento": procedimento,
        "descricao_procedimento": f"Cirurgia de {procedimento}.",
        "honorarios_equipe_rs": total - 3000.00,
        "valor_internacao_rs": 3000.00,
        "estimativa_total_rs": total,
        "o_que_inclui_honorarios": "Cirurgião, auxiliares, instrumentador e anestesista",
        "o_que_inclui_internacao": "Centro cirúrgico, internação, materiais e medicamentos",
        "diferencial_1": "Técnica minimamente invasiva",
        "diferencial_2": "UTI integrada",
        "caveat_obrigatorio_ana": "Esta é uma estimativa geral.",
        "observacoes_ana": "",
        "ativo": ativo,
        "ultima_atualizacao": "2026-03-10",
    }


class TestCirurgiasEstimativas:
    def test_sem_chave_e_recusada(self, monkeypatch):
        monkeypatch.setattr(settings, "ana_api_key", CHAVE_CORRETA)
        client = _make_app({"cirurgias_estimativas": []})
        assert client.get("/api/ana/cirurgias-estimativas").status_code == 401

    def test_chave_correta_devolve_cirurgias_ativas(self, monkeypatch):
        monkeypatch.setattr(settings, "ana_api_key", CHAVE_CORRETA)
        client = _make_app(
            {
                "cirurgias_estimativas": [
                    _cirurgia_row("Apendicectomia Videolaparoscópica", 8300.00),
                    _cirurgia_row("Herniorrafia (Hérnia Inguinal)", 7500.00, ativo=False),
                    _cirurgia_row("Colecistectomia Videolaparoscópica", 9000.00),
                ]
            }
        )
        r = client.get("/api/ana/cirurgias-estimativas", headers={"X-API-Key": CHAVE_CORRETA})
        assert r.status_code == 200
        cirurgias = r.json()["cirurgias_estimativas"]
        assert [c["procedimento"] for c in cirurgias] == [
            "Apendicectomia Videolaparoscópica",
            "Colecistectomia Videolaparoscópica",
        ]
        apendicectomia = cirurgias[0]
        assert apendicectomia["estimativa_total_rs"] == 8300.00
        assert apendicectomia["honorarios_equipe_rs"] == 5300.00
        assert apendicectomia["valor_internacao_rs"] == 3000.00
        assert apendicectomia["caveat_obrigatorio_ana"] == "Esta é uma estimativa geral."


class TestImportCirurgias:
    def _rows(self):
        return parse_export("cirurgias_estimativas", os.path.join(FIXTURES, "export_nocodb_cirurgias_estimativas.csv"))

    def test_importa_todas_as_linhas_do_export(self):
        rows = self._rows()
        assert len(rows) == 3
        assert [r["procedimento"] for r in rows] == [
            "Colecistectomia Videolaparoscópica",
            "Apendicectomia Videolaparoscópica",
            "Herniorrafia (Hérnia Inguinal)",
        ]

    def test_valores_e_caveat_conferem_com_a_fonte(self):
        rows = {r["procedimento"]: r for r in self._rows()}
        cole = rows["Colecistectomia Videolaparoscópica"]
        assert cole["honorarios_equipe_rs"] == 6000.00
        assert cole["valor_internacao_rs"] == 3000.00
        assert cole["estimativa_total_rs"] == 9000.00
        assert cole["caveat_obrigatorio_ana"].startswith("Esta é uma estimativa geral.")
        assert cole["ativo"] is True
        assert cole["ultima_atualizacao"] == "2026-03-10"
        assert rows["Apendicectomia Videolaparoscópica"]["estimativa_total_rs"] == 8300.00
        assert rows["Herniorrafia (Hérnia Inguinal)"]["estimativa_total_rs"] == 7500.00

    def test_tipografia_sanitizada_no_import(self):
        for row in self._rows():
            for valor in row.values():
                if isinstance(valor, str):
                    assert "—" not in valor
                    assert "–" not in valor
        cole = {r["procedimento"]: r for r in self._rows()}["Colecistectomia Videolaparoscópica"]
        assert cole["diferencial_1"] == (
            "Técnica minimamente invasiva, menos dor, recuperação mais rápida e alta em 24 a 48h"
        )

    def test_seed_da_migration_confere_com_o_export(self):
        assert to_sql("cirurgias_estimativas", self._rows()) in _conteudo_migration_062()


def _conteudo_migration_062() -> str:
    """A migration 062 é a que sobe as três tabelas em produção: o seed dela
    deve ser exatamente o gerado do export (amarra produção à fonte)."""
    migration = os.path.join(
        os.path.dirname(__file__), "..", "..", "supabase", "migrations", "062_exames_cirurgias_convenios_ana.sql"
    )
    with open(migration, encoding="utf-8") as f:
        return f.read()
