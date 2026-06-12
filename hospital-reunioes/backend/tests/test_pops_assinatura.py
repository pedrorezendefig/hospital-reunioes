"""Testes do disparo ClickSign na aprovação do Validador (issue #87).

A aprovação do Validador (EM_VALIDACAO → EM_ASSINATURA) dispara
automaticamente o envio ao ClickSign: Envelope com o PDF institucional e
3 Signatários nomeados por papel (Elaborador, Revisor, Validador), sem
passo manual. Falha no envio mantém EM_ASSINATURA re-tentável sem duplicar
Envelope (reenvio via POST /pops/{pop_id}/assinatura/reenviar).

ClickSign SEMPRE mockado (primitivos de app.services.clicksign_service):
o pytest carrega o .env real — nenhum teste pode tocar a API de verdade.
Terminologia conforme docs/pops/CONTEXT.md.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.dependencies import get_current_user, get_supabase_client  # noqa: E402
from app.routers.pops import assinatura as assinatura_router  # noqa: E402
from app.routers.pops import revisao as revisao_router  # noqa: E402
from app.services import clicksign_service, pops_email_service, pops_pdf_service  # noqa: E402

# ─── Mock Supabase (padrão do test_pops_criar, com audit e devoluções) ───────


@dataclass
class _Result:
    data: list


class _TableQuery:
    def __init__(self, rows: list[dict], table: str):
        self._rows = rows
        self._table = table
        self._filters: dict = {}
        self._in_filters: dict = {}
        self._insert_payload: list[dict] | None = None
        self._update_payload: dict | None = None

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

    def insert(self, payload: dict | list):
        rows = payload if isinstance(payload, list) else [payload]
        self._insert_payload = [dict(r) for r in rows]
        return self

    def update(self, payload: dict):
        self._update_payload = dict(payload)
        return self

    def execute(self):
        if self._insert_payload is not None:
            inserted = []
            for row in self._insert_payload:
                row = dict(row)
                row.setdefault("id", f"{self._table}-{len(self._rows) + 1}")
                self._rows.append(row)
                inserted.append(dict(row))
            return _Result(data=inserted)

        filtered = [
            r
            for r in self._rows
            if all(r.get(c) == v for c, v in self._filters.items())
            and all(r.get(c) in vs for c, vs in self._in_filters.items())
        ]

        if self._update_payload is not None:
            for row in filtered:
                row.update(self._update_payload)
            return _Result(data=[dict(r) for r in filtered])

        return _Result(data=[dict(r) for r in filtered])


class _SupabaseMock:
    def __init__(self, tables: dict[str, list[dict]]):
        self.tables = tables

    def table(self, name: str):
        if name not in self.tables:
            raise AssertionError(f"Tabela inesperada: {name}")
        return _TableQuery(self.tables[name], name)


# ─── Dados ───────────────────────────────────────────────────────────────────


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


ELABORADOR = _pessoa("P1", perfil_pop="coordenador")
REVISOR = _pessoa("P2", perfil_pop="coordenador")
VALIDADOR = _pessoa("P3", perfil_pop="gerente")
CRIADOR = _pessoa("P6", perfil_pop="coordenador")

NOME_POP = "Cateter Venoso Central"


def _pop(**over) -> dict:
    base = {
        "id": "pop-1",
        "setor_id": "s-cti",
        "numero": 1,
        "codigo": "HSM_CTI-001",
        "nome": NOME_POP,
        "criticidade": "CRITICA",
        "base_normativa": None,
        "periodicidade_revisao": "1_ano",
        "prazo_elaboracao_dias": 15,
        "prazo_revisao_dias": 30,
        "elaborador_id": "P1",
        "revisor_id": "P2",
        "validador_id": "P3",
        "criado_por": "P6",
        "created_at": "2026-06-01T12:00:00+00:00",
    }
    base.update(over)
    return base


def _versao(**over) -> dict:
    base = {
        "id": "v-1",
        "pop_id": "pop-1",
        "numero_versao": "1.0",
        "estado": "EM_VALIDACAO",
        "rascunho": {"objetivo": "Padronizar o procedimento."},
        "periodicidade_sugerida": None,
    }
    base.update(over)
    return base


def _sb(versao: dict | None = None, pop: dict | None = None) -> _SupabaseMock:
    return _SupabaseMock(
        {
            "participantes": [ELABORADOR, REVISOR, VALIDADOR, CRIADOR],
            "pops_setores": [{"id": "s-cti", "nome": "Coordenação do CTI", "sigla": "CTI"}],
            "pops_setores_participantes": [],
            "pops": [pop or _pop()],
            "pops_versoes": [versao or _versao()],
            "pops_devolucoes": [],
            "audit_log": [],
        }
    )


def _client_para(pessoa: dict, sb: _SupabaseMock) -> TestClient:
    app = FastAPI()
    app.include_router(revisao_router.router, prefix="/api")
    app.include_router(assinatura_router.router, prefix="/api")

    async def _fake_user() -> dict[str, Any]:
        return {"id": pessoa["auth_user_id"], "email": pessoa["email"], "metadata": {}}

    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_supabase_client] = lambda: sb
    return TestClient(app)


# ─── Mocks de integração (ClickSign + PDF + email) ───────────────────────────


class _ClickSignMock:
    """Substitui os primitivos do clicksign_service registrando as chamadas.
    `falhar` simula erro de API no passo nomeado (None/False, como o real)."""

    def __init__(self):
        self.calls: dict[str, list] = {
            "create_envelope": [],
            "add_document": [],
            "add_signer": [],
            "create_qualification_requirement": [],
            "create_auth_requirement": [],
            "activate_envelope": [],
            "notify_signers": [],
        }
        self.falhar: set[str] = set()

    def create_envelope(self, name):
        self.calls["create_envelope"].append(name)
        return None if "create_envelope" in self.falhar else "env-1"

    def add_document(self, envelope_id, pdf_bytes, filename):
        self.calls["add_document"].append({"envelope_id": envelope_id, "pdf_bytes": pdf_bytes, "filename": filename})
        return None if "add_document" in self.falhar else "doc-1"

    def add_signer(self, envelope_id, nome, email):
        self.calls["add_signer"].append({"envelope_id": envelope_id, "nome": nome, "email": email})
        return None if "add_signer" in self.falhar else f"signer-{len(self.calls['add_signer'])}"

    def create_qualification_requirement(self, envelope_id, document_id, signer_id):
        self.calls["create_qualification_requirement"].append(signer_id)
        return None if "create_qualification_requirement" in self.falhar else "q-1"

    def create_auth_requirement(self, envelope_id, document_id, signer_id):
        self.calls["create_auth_requirement"].append(signer_id)
        return None if "create_auth_requirement" in self.falhar else "a-1"

    def activate_envelope(self, envelope_id):
        self.calls["activate_envelope"].append(envelope_id)
        return "activate_envelope" not in self.falhar

    def notify_signers(self, envelope_id):
        self.calls["notify_signers"].append(envelope_id)
        return True


@pytest.fixture
def clicksign(monkeypatch) -> _ClickSignMock:
    mock = _ClickSignMock()
    for nome in mock.calls:
        monkeypatch.setattr(clicksign_service, nome, getattr(mock, nome))
    return mock


@pytest.fixture(autouse=True)
def _bloquear_httpx_clicksign(monkeypatch):
    """Rede nunca: qualquer primitivo não mockado explodiria aqui antes de
    tocar a API real (o .env de teste carrega credenciais de verdade)."""
    import httpx

    def _explode(*_a, **_kw):
        raise AssertionError("Chamada httpx real bloqueada nos testes")

    monkeypatch.setattr(httpx, "Client", _explode)


@pytest.fixture
def pdf_mockado(monkeypatch) -> list[dict]:
    chamadas: list[dict] = []

    def _fake(**kwargs) -> bytes:
        chamadas.append(kwargs)
        return b"%PDF-fake"

    monkeypatch.setattr(pops_pdf_service, "gerar_pdf_pop", _fake)
    return chamadas


@pytest.fixture(autouse=True)
def emails_enviados(monkeypatch) -> list[dict]:
    enviados: list[dict] = []

    def _fake_enviar(destinatario, assunto, html, texto=None):
        enviados.append({"destinatario": destinatario, "assunto": assunto, "html": html})
        return True

    monkeypatch.setattr(pops_email_service, "_enviar_email", _fake_enviar)
    return enviados


def _nome_arquivo_esperado(status: str = "PRELIMINAR") -> str:
    return pops_pdf_service.nome_arquivo_pop(codigo="HSM_CTI-001", nome=NOME_POP, numero_versao="1.0", status=status)


# ═══════════════════════════════════════════════════════════════════════════
# CA: aprovação do Validador cria e ativa Envelope com 3 Signatários e o PDF
# ═══════════════════════════════════════════════════════════════════════════


class TestDisparoNaAprovacao:
    def test_aprovacao_dispara_envelope_com_3_signatarios_e_pdf(self, clicksign, pdf_mockado):
        """CA: aprovação do Validador cria e ativa Envelope com 3 Signatários
        nomeados por papel e o PDF institucional, sem passo manual."""
        sb = _sb()
        client = _client_para(VALIDADOR, sb)

        res = client.post("/api/pops/pop-1/validacao/aprovar")

        assert res.status_code == 200
        body = res.json()
        assert body["estado"] == "EM_ASSINATURA"
        assert body["assinatura_enviada"] is True

        # Envelope e Documento com a nomenclatura travada do DRF §3.3
        nome_arquivo = _nome_arquivo_esperado()
        assert clicksign.calls["create_envelope"] == [nome_arquivo.removesuffix(".pdf")]
        assert len(clicksign.calls["add_document"]) == 1
        doc = clicksign.calls["add_document"][0]
        assert doc["envelope_id"] == "env-1"
        assert doc["filename"] == nome_arquivo
        assert doc["pdf_bytes"] == b"%PDF-fake"

        # PDF institucional gerado do rascunho persistido (estado já EM_ASSINATURA)
        assert len(pdf_mockado) == 1
        assert pdf_mockado[0]["pop"]["id"] == "pop-1"
        assert pdf_mockado[0]["versao"]["estado"] == "EM_ASSINATURA"

        # 3 Signatários nomeados por papel: Elaborador, Revisor, Validador
        signers = clicksign.calls["add_signer"]
        assert [s["email"] for s in signers] == ["p1@hsm.com", "p2@hsm.com", "p3@hsm.com"]
        assert all(s["envelope_id"] == "env-1" for s in signers)
        assert len(clicksign.calls["create_qualification_requirement"]) == 3
        assert len(clicksign.calls["create_auth_requirement"]) == 3

        # Envelope ativado e Signatários notificados (emails da própria ClickSign)
        assert clicksign.calls["activate_envelope"] == ["env-1"]
        assert clicksign.calls["notify_signers"] == ["env-1"]

        # IDs persistidos na Versão: envelope p/ consultas, document.key p/ webhook
        versao = sb.tables["pops_versoes"][0]
        assert versao["estado"] == "EM_ASSINATURA"
        assert versao["envelope_id_clicksign"] == "env-1"
        assert versao["envelope_key_clicksign"] == "doc-1"

        acoes = [r["action"] for r in sb.tables["audit_log"]]
        assert "POPS_APROVAR_VALIDACAO" in acoes
        assert "POPS_ENVIAR_ASSINATURA" in acoes

    def test_mesma_pessoa_em_dois_papeis_assina_uma_vez(self, clicksign, pdf_mockado):
        """Revisor e Validador são a mesma pessoa → 1 Signatário só (uma
        assinatura cobre os dois papéis; 2 signers do mesmo email confundem)."""
        sb = _sb(pop=_pop(revisor_id="P3"))  # P3 revisa E valida
        client = _client_para(VALIDADOR, sb)

        res = client.post("/api/pops/pop-1/validacao/aprovar")

        assert res.status_code == 200
        emails = [s["email"] for s in clicksign.calls["add_signer"]]
        assert emails == ["p1@hsm.com", "p3@hsm.com"]
        assert len(clicksign.calls["create_qualification_requirement"]) == 2

    def test_aprovacao_fora_de_estado_nao_toca_clicksign(self, clicksign, pdf_mockado):
        sb = _sb(versao=_versao(estado="EM_REVISAO"))
        client = _client_para(VALIDADOR, sb)

        res = client.post("/api/pops/pop-1/validacao/aprovar")

        assert res.status_code == 400
        assert clicksign.calls["create_envelope"] == []


# ═══════════════════════════════════════════════════════════════════════════
# CA: falha no envio mantém EM_ASSINATURA re-tentável sem duplicar Envelope
# ═══════════════════════════════════════════════════════════════════════════


class TestFalhaParcial:
    def test_falha_ao_criar_envelope_mantem_estado_retentavel(self, clicksign, pdf_mockado):
        """CA: erro no envio mantém EM_ASSINATURA (aprovação não se desfaz) e
        não grava Envelope — o reenvio parte do zero."""
        clicksign.falhar.add("create_envelope")
        sb = _sb()
        client = _client_para(VALIDADOR, sb)

        res = client.post("/api/pops/pop-1/validacao/aprovar")

        assert res.status_code == 200
        body = res.json()
        assert body["estado"] == "EM_ASSINATURA"
        assert body["assinatura_enviada"] is False

        versao = sb.tables["pops_versoes"][0]
        assert versao["estado"] == "EM_ASSINATURA"
        assert not versao.get("envelope_id_clicksign")
        assert not versao.get("envelope_key_clicksign")
        assert clicksign.calls["add_document"] == []

    def test_falha_na_ativacao_nao_grava_envelope_pela_metade(self, clicksign, pdf_mockado):
        """Falha DEPOIS de montar o Envelope: nada persiste (sem half-state) —
        o reenvio cria Envelope novo em vez de apontar para um inativo."""
        clicksign.falhar.add("activate_envelope")
        sb = _sb()
        client = _client_para(VALIDADOR, sb)

        res = client.post("/api/pops/pop-1/validacao/aprovar")

        assert res.status_code == 200
        assert res.json()["assinatura_enviada"] is False
        versao = sb.tables["pops_versoes"][0]
        assert versao["estado"] == "EM_ASSINATURA"
        assert not versao.get("envelope_id_clicksign")
        assert clicksign.calls["notify_signers"] == []


# ═══════════════════════════════════════════════════════════════════════════
# Reenvio — POST /pops/{pop_id}/assinatura/reenviar
# ═══════════════════════════════════════════════════════════════════════════


class TestReenvio:
    def test_reenvio_apos_falha_cria_envelope(self, clicksign, pdf_mockado):
        """EM_ASSINATURA sem Envelope (envio anterior falhou) → o reenvio
        monta o fluxo completo e persiste os IDs."""
        sb = _sb(versao=_versao(estado="EM_ASSINATURA"))
        client = _client_para(VALIDADOR, sb)

        res = client.post("/api/pops/pop-1/assinatura/reenviar")

        assert res.status_code == 200
        assert res.json()["assinatura_enviada"] is True
        assert len(clicksign.calls["create_envelope"]) == 1
        versao = sb.tables["pops_versoes"][0]
        assert versao["envelope_id_clicksign"] == "env-1"
        assert versao["envelope_key_clicksign"] == "doc-1"

    def test_reenvio_com_envelope_ativo_nao_duplica(self, clicksign, pdf_mockado):
        """CA: re-tentativa sem duplicar Envelope — com envio anterior OK, o
        reenvio é no-op idempotente."""
        sb = _sb(
            versao=_versao(
                estado="EM_ASSINATURA",
                envelope_id_clicksign="env-old",
                envelope_key_clicksign="doc-old",
            )
        )
        client = _client_para(VALIDADOR, sb)

        res = client.post("/api/pops/pop-1/assinatura/reenviar")

        assert res.status_code == 200
        assert res.json()["assinatura_enviada"] is True
        assert clicksign.calls["create_envelope"] == []
        versao = sb.tables["pops_versoes"][0]
        assert versao["envelope_id_clicksign"] == "env-old"
        assert versao["envelope_key_clicksign"] == "doc-old"

    def test_reenvio_exige_validador(self, clicksign, pdf_mockado):
        sb = _sb(versao=_versao(estado="EM_ASSINATURA"))
        client = _client_para(REVISOR, sb)

        res = client.post("/api/pops/pop-1/assinatura/reenviar")

        assert res.status_code == 403
        assert clicksign.calls["create_envelope"] == []

    def test_reenvio_exige_estado_em_assinatura(self, clicksign, pdf_mockado):
        sb = _sb(versao=_versao(estado="EM_VALIDACAO"))
        client = _client_para(VALIDADOR, sb)

        res = client.post("/api/pops/pop-1/assinatura/reenviar")

        assert res.status_code == 400
        assert clicksign.calls["create_envelope"] == []
