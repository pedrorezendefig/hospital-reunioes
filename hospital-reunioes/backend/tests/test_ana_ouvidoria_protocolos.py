"""Testes da ouvidoria ponta a ponta na API da Ana (issue #290, ADR 0031 decisões 5 e 7).

Cobre (critérios de aceite):
- Dois registros seguidos recebem números sequenciais no formato ANO-NNNN,
  gerados pelo banco (a aplicação nunca compõe o número).
- Registro sem campo crítico é recusado pela API (e pelo banco, via contrato
  da migration, se a API for contornada).
- A consulta devolve o protocolo registrado; schema e respostas sem nome,
  CPF nem relato (índice, não dossiê).
- Import do NocoDB: a sequence continua do último número usado.
"""

from __future__ import annotations

import os
import re
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

CHAVE_CORRETA = "chave-teste-ana-para-pytest"


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


class _BancoOuvidoriaFake:
    """Simula o comportamento do banco (migration 062): quem numera e formata
    o protocolo é o Postgres (sequence + coluna gerada), nunca a aplicação."""

    def __init__(self, proximo_numero: int = 1, data_abertura: str = "2026-08-14"):
        self._proximo_numero = proximo_numero
        self._data_abertura = data_abertura
        self.rows: list[dict] = []

    def inserir(self, payload: dict) -> dict:
        ano = self._data_abertura[:4]
        row = {
            "id": f"uuid-{self._proximo_numero}",
            "numero": self._proximo_numero,
            "protocolo": f"{ano}-{self._proximo_numero:04d}",
            "data_abertura": self._data_abertura,
            "prazo_resposta": "2026-08-21",
            "status": "aberto",
            "categoria": payload["categoria"],
            "setor": payload["setor"],
            "resumo": payload["resumo"],
            "conversa_id": payload.get("conversa_id", ""),
        }
        self._proximo_numero += 1
        self.rows.append(row)
        return row


class _Query:
    def __init__(self, banco: _BancoOuvidoriaFake):
        self._banco = banco
        self._filters: dict = {}
        self._pending_insert: dict | None = None

    def select(self, *_args, **_kwargs):
        return self

    def insert(self, payload: dict):
        self._pending_insert = payload
        return self

    def eq(self, col, value):
        self._filters[col] = value
        return self

    def order(self, *_args, **_kwargs):
        return self

    def execute(self):
        if self._pending_insert is not None:
            data = [self._banco.inserir(self._pending_insert)]
        else:
            data = [dict(r) for r in self._banco.rows if all(r.get(c) == v for c, v in self._filters.items())]
        return type("R", (), {"data": data})()


def _make_app(banco: _BancoOuvidoriaFake | None = None) -> TestClient:
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(RequestContextMiddleware)
    app.include_router(ana_router.router, prefix="/api")

    banco = banco or _BancoOuvidoriaFake()

    class _SupabaseMock:
        def table(self, name: str):
            assert name == "ouvidoria_protocolos", f"Tabela inesperada: {name}"
            return _Query(banco)

    app.dependency_overrides[get_supabase_client] = _SupabaseMock
    return TestClient(app)


def _payload_valido(**overrides) -> dict:
    payload = {
        "categoria": "Demora",
        "setor": "Recepcao",
        "resumo": "Paciente relata espera acima de duas horas na recepcao.",
        "conversa_id": "conv-4711",
    }
    payload.update(overrides)
    return payload


class TestRegistroDeProtocolo:
    def test_dois_registros_seguidos_recebem_numeros_sequenciais(self, monkeypatch):
        monkeypatch.setattr(settings, "ana_api_key", CHAVE_CORRETA)
        client = _make_app(_BancoOuvidoriaFake(proximo_numero=7))

        r1 = client.post(
            "/api/ana/ouvidoria/protocolos",
            json=_payload_valido(),
            headers={"X-API-Key": CHAVE_CORRETA},
        )
        r2 = client.post(
            "/api/ana/ouvidoria/protocolos",
            json=_payload_valido(categoria="Higiene", setor="Enfermagem"),
            headers={"X-API-Key": CHAVE_CORRETA},
        )

        assert r1.status_code == 201
        assert r2.status_code == 201
        assert r1.json()["protocolo"] == "2026-0007"
        assert r2.json()["protocolo"] == "2026-0008"
        for r in (r1, r2):
            assert re.fullmatch(r"\d{4}-\d{4}", r.json()["protocolo"])
        assert r1.json()["status"] == "aberto"


class TestRecusaDeCampoCritico:
    """Defesa contra a falha silenciosa de interpolação do cliente da Ana
    (ADR 0031, decisão 7): registro sem campo crítico é recusado com erro claro."""

    @pytest.mark.parametrize("campo", ["categoria", "setor", "resumo"])
    def test_campo_critico_ausente_e_recusado(self, monkeypatch, campo):
        monkeypatch.setattr(settings, "ana_api_key", CHAVE_CORRETA)
        banco = _BancoOuvidoriaFake()
        client = _make_app(banco)

        payload = _payload_valido()
        del payload[campo]
        r = client.post("/api/ana/ouvidoria/protocolos", json=payload, headers={"X-API-Key": CHAVE_CORRETA})

        assert r.status_code == 422
        assert campo in r.text
        assert banco.rows == []

    @pytest.mark.parametrize("vazio", ["", "   "])
    @pytest.mark.parametrize("campo", ["categoria", "setor", "resumo"])
    def test_campo_critico_vazio_e_recusado(self, monkeypatch, campo, vazio):
        monkeypatch.setattr(settings, "ana_api_key", CHAVE_CORRETA)
        banco = _BancoOuvidoriaFake()
        client = _make_app(banco)

        r = client.post(
            "/api/ana/ouvidoria/protocolos",
            json=_payload_valido(**{campo: vazio}),
            headers={"X-API-Key": CHAVE_CORRETA},
        )

        assert r.status_code == 422
        assert campo in r.text
        assert banco.rows == []

    def test_conversa_id_ausente_nao_recusa(self, monkeypatch):
        """conversa_id não é crítico (ressalva do ADR-0010 da Ana): o vínculo
        pode se fazer na direção inversa, pelo resumo da escalada."""
        monkeypatch.setattr(settings, "ana_api_key", CHAVE_CORRETA)
        client = _make_app(_BancoOuvidoriaFake())

        payload = _payload_valido()
        del payload["conversa_id"]
        r = client.post("/api/ana/ouvidoria/protocolos", json=payload, headers={"X-API-Key": CHAVE_CORRETA})

        assert r.status_code == 201
        assert r.json()["conversa_id"] == ""


class TestConsultaDeProtocolo:
    def test_consulta_devolve_o_protocolo_registrado(self, monkeypatch):
        monkeypatch.setattr(settings, "ana_api_key", CHAVE_CORRETA)
        client = _make_app(_BancoOuvidoriaFake(proximo_numero=7))

        registrado = client.post(
            "/api/ana/ouvidoria/protocolos",
            json=_payload_valido(),
            headers={"X-API-Key": CHAVE_CORRETA},
        ).json()

        r = client.get("/api/ana/ouvidoria/protocolos/2026-0007", headers={"X-API-Key": CHAVE_CORRETA})

        assert r.status_code == 200
        consultado = r.json()
        assert consultado["protocolo"] == "2026-0007"
        assert consultado["categoria"] == registrado["categoria"]
        assert consultado["setor"] == registrado["setor"]
        assert consultado["resumo"] == registrado["resumo"]
        assert consultado["status"] == "aberto"

    def test_protocolo_inexistente_devolve_404(self, monkeypatch):
        monkeypatch.setattr(settings, "ana_api_key", CHAVE_CORRETA)
        client = _make_app(_BancoOuvidoriaFake())

        r = client.get("/api/ana/ouvidoria/protocolos/2026-9999", headers={"X-API-Key": CHAVE_CORRETA})

        assert r.status_code == 404


class TestAuthPorApiKey:
    @pytest.mark.parametrize("headers", [{}, {"X-API-Key": "chave-errada"}])
    def test_registro_sem_chave_ou_com_chave_errada_e_recusado(self, monkeypatch, headers):
        monkeypatch.setattr(settings, "ana_api_key", CHAVE_CORRETA)
        banco = _BancoOuvidoriaFake()
        client = _make_app(banco)

        r = client.post("/api/ana/ouvidoria/protocolos", json=_payload_valido(), headers=headers)

        assert r.status_code == 401
        assert banco.rows == []

    @pytest.mark.parametrize("headers", [{}, {"X-API-Key": "chave-errada"}])
    def test_consulta_sem_chave_ou_com_chave_errada_e_recusada(self, monkeypatch, headers):
        monkeypatch.setattr(settings, "ana_api_key", CHAVE_CORRETA)
        client = _make_app(_BancoOuvidoriaFake())

        r = client.get("/api/ana/ouvidoria/protocolos/2026-0007", headers=headers)

        assert r.status_code == 401


# O índice completo da manifestação, e nada além dele (ADR 0031, decisão 3).
CAMPOS_DO_INDICE = {
    "id",
    "numero",
    "protocolo",
    "data_abertura",
    "prazo_resposta",
    "status",
    "categoria",
    "setor",
    "resumo",
    "conversa_id",
}


class TestContratoDePrivacidade:
    """Índice, não dossiê: nome, CPF e relato vivem na conversa do Chatwoot da
    Ana e nunca entram neste app. O contrato fecha o conjunto de campos: campo
    novo na resposta só entra por decisão revisada."""

    def test_respostas_expoem_exatamente_o_indice(self, monkeypatch):
        monkeypatch.setattr(settings, "ana_api_key", CHAVE_CORRETA)
        client = _make_app(_BancoOuvidoriaFake(proximo_numero=7))

        registrado = client.post(
            "/api/ana/ouvidoria/protocolos",
            json=_payload_valido(),
            headers={"X-API-Key": CHAVE_CORRETA},
        ).json()
        consultado = client.get("/api/ana/ouvidoria/protocolos/2026-0007", headers={"X-API-Key": CHAVE_CORRETA}).json()

        assert set(registrado.keys()) == CAMPOS_DO_INDICE
        assert set(consultado.keys()) == CAMPOS_DO_INDICE

    def test_schema_da_tabela_nao_tem_coluna_de_dado_pessoal(self):
        """A migration não cria coluna de nome, CPF ou relato: se o banco vazar,
        sai '2026-0007, Demora, Recepcao, aberto', não quem reclamou."""
        migration = os.path.join(
            os.path.dirname(__file__), "..", "..", "supabase", "migrations", "062_ouvidoria_protocolos_ana.sql"
        )
        with open(migration, encoding="utf-8") as f:
            ddl = f.read().lower()
        for proibido in ("nome", "cpf", "relato", "paciente", "solicitante", "telefone", "email"):
            assert proibido not in ddl, f"Coluna/termo de dado pessoal no schema: {proibido}"


def _ddl_migration() -> str:
    migration = os.path.join(
        os.path.dirname(__file__), "..", "..", "supabase", "migrations", "062_ouvidoria_protocolos_ana.sql"
    )
    with open(migration, encoding="utf-8") as f:
        return f.read()


class TestDefesaNoBanco:
    """Se a API for contornada, o banco recusa registro vazio e continua sendo
    o único a numerar (ADR 0031, decisões 5 e 7). Sem Postgres na suíte, o
    contrato é amarrado na DDL da migration, como a 061 amarrou o seed."""

    def test_banco_numera_e_formata_o_protocolo(self):
        ddl = _ddl_migration().lower()
        assert "create sequence" in ddl
        assert "nextval('ouvidoria_protocolos_numero_seq')" in ddl
        assert "generated always as" in ddl
        assert "lpad(numero::text, 4, '0')" in ddl

    def test_banco_recusa_campo_critico_vazio_ou_nulo(self):
        ddl = _ddl_migration().lower()
        for campo in ("categoria", "setor", "resumo"):
            assert f"{campo} text not null check (btrim({campo}) <> '')" in ddl

    def test_tabela_nova_tem_rls_default_deny(self):
        assert "ENABLE ROW LEVEL SECURITY" in _ddl_migration()


class TestImportDoExport:
    """Import dos protocolos existentes do NocoDB (ato da virada, fora do git):
    preserva numero e data (numeros ja comunicados seguem consultaveis) e a
    sequence continua do ultimo numero usado, mesmo com buraco na numeracao
    (o NocoDB consumiu Ids de registros de teste apagados)."""

    def _rows(self):
        from app.scripts.import_ouvidoria_protocolos import parse_export

        fixture = os.path.join(os.path.dirname(__file__), "fixtures", "export_nocodb_ouvidoria_protocolos.csv")
        return parse_export(fixture)

    def test_import_preserva_numero_data_e_status(self):
        rows = self._rows()
        assert [r["numero"] for r in rows] == [2, 3, 5]
        assert rows[0]["data_abertura"] == "2026-08-12"
        assert rows[2]["data_abertura"] == "2026-08-13"
        assert [r["status"] for r in rows] == ["aberto", "respondido", "aberto"]
        assert rows[0]["conversa_id"] == "conv-101"
        assert rows[2]["conversa_id"] == ""
        assert rows[2]["categoria"] == "Elogio"

    def test_protocolo_do_export_confere_com_o_que_o_banco_vai_gerar(self):
        """O parser recusa export inconsistente: o Protocolo da fonte tem que
        recompor de numero + ano, senao o numero comunicado mudaria de dono."""
        for row, esperado in zip(self._rows(), ["2026-0002", "2026-0003", "2026-0005"]):
            ano = row["data_abertura"][:4]
            assert f"{ano}-{row['numero']:04d}" == esperado

    def test_tipografia_sanitizada_no_import(self):
        for row in self._rows():
            for valor in row.values():
                if isinstance(valor, str):
                    assert "—" not in valor
                    assert "–" not in valor
        assert self._rows()[1]["resumo"] == (
            "Manifestante descreve espera acima de duas horas, sem atualizacao da fila."
        )

    def test_sql_do_import_continua_a_sequence_do_ultimo_numero(self):
        from app.scripts.import_ouvidoria_protocolos import to_sql

        sql = to_sql(self._rows())
        assert "INSERT INTO ouvidoria_protocolos" in sql
        assert "(2, '2026-08-12'" in sql
        assert "(5, '2026-08-13'" in sql
        assert "ON CONFLICT (numero) DO NOTHING" in sql
        # A sequence nasce do maior numero ja usado: o proximo protocolo e o 6.
        assert "setval('ouvidoria_protocolos_numero_seq', (SELECT MAX(numero) FROM ouvidoria_protocolos))" in sql
