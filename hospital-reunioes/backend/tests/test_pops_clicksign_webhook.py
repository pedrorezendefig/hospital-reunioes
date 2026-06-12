"""Testes do webhook ClickSign com roteamento por Envelope (issue #87).

O webhook existente (Reuniões) ganha roteamento: document.key resolve para
uma Reunião (fluxo atual, intacto) ou para uma Versão de POP — com todas as
assinaturas, salva o PDF assinado no storage, marca PUBLICADO, audita e
notifica o criador. Idempotente a eventos duplicados; HMAC inválido rejeita.

Primeiro teste do webhook no repo: o fluxo de Reunião entra como contrato
de regressão do roteamento. ClickSign/storage SEMPRE mockados (o .env de
teste carrega credenciais reais). Terminologia: docs/pops/CONTEXT.md.
"""

from __future__ import annotations

import hashlib
import hmac as hmac_lib
import json
import os
import sys
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.config import settings  # noqa: E402
from app.dependencies import get_supabase_client  # noqa: E402
from app.routers import webhooks as webhooks_router  # noqa: E402
from app.services import clicksign_service, pendencia_service, pops_email_service, storage  # noqa: E402

SECRET = "test-secret"

# ─── Mock Supabase (padrão dos testes de POPs) ───────────────────────────────


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


def _pop(**over) -> dict:
    base = {
        "id": "pop-1",
        "setor_id": "s-cti",
        "codigo": "HSM_CTI-001",
        "nome": "Cateter Venoso Central",
        "criticidade": "CRITICA",
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
        "estado": "EM_ASSINATURA",
        "rascunho": {"objetivo": "Padronizar."},
        "envelope_id_clicksign": "env-1",
        "envelope_key_clicksign": "doc-key-pop",
        "url_pdf_assinado": None,
        "data_publicacao": None,
    }
    base.update(over)
    return base


def _pessoa(pid: str) -> dict:
    return {
        "id": pid,
        "auth_user_id": f"auth-{pid}",
        "email": f"{pid.lower()}@hsm.com",
        "nome_completo": f"Pessoa {pid}",
        "perfil_pop": "coordenador",
        "ativo": True,
    }


def _sb(versao: dict | None = None, reunioes: list[dict] | None = None) -> _SupabaseMock:
    return _SupabaseMock(
        {
            "reunioes": reunioes if reunioes is not None else [],
            "pops_versoes": [versao or _versao()],
            "pops": [_pop()],
            "pops_setores": [{"id": "s-cti", "nome": "Coordenação do CTI", "sigla": "CTI"}],
            "participantes": [_pessoa("P1"), _pessoa("P2"), _pessoa("P3"), _pessoa("P6")],
            "audit_log": [],
        }
    )


def _client(sb: _SupabaseMock) -> TestClient:
    app = FastAPI()
    app.include_router(webhooks_router.router, prefix="/api")
    app.dependency_overrides[get_supabase_client] = lambda: sb
    return TestClient(app)


def _post(client: TestClient, payload: dict, *, secret: str = SECRET) -> Any:
    body = json.dumps(payload).encode("utf-8")
    assinatura = hmac_lib.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return client.post(
        "/api/webhooks/clicksign",
        content=body,
        headers={"Content-Hmac": f"sha256={assinatura}", "Content-Type": "application/json"},
    )


def _evento(nome: str, key: str) -> dict:
    return {"event": {"name": nome}, "document": {"key": key}}


# ─── Mocks de integração ─────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _secret(monkeypatch):
    monkeypatch.setattr(settings, "clicksign_webhook_secret", SECRET)


@pytest.fixture(autouse=True)
def _bloquear_httpx(monkeypatch):
    import httpx

    def _explode(*_a, **_kw):
        raise AssertionError("Chamada httpx real bloqueada nos testes")

    monkeypatch.setattr(httpx, "Client", _explode)


@pytest.fixture
def pdf_assinado(monkeypatch) -> list[str]:
    """get_signed_document mockado — registra o id consultado."""
    chamadas: list[str] = []

    def _fake(envelope_id: str):
        chamadas.append(envelope_id)
        return b"%PDF-signed"

    monkeypatch.setattr(clicksign_service, "get_signed_document", _fake)
    return chamadas


@pytest.fixture
def uploads(monkeypatch) -> list[dict]:
    feitos: list[dict] = []

    def _fake(supabase, bucket, path, content, content_type="application/octet-stream"):
        feitos.append({"bucket": bucket, "path": path, "content": content})
        return f"http://storage/{bucket}/{path}"

    monkeypatch.setattr(storage, "upload_file", _fake)
    return feitos


@pytest.fixture(autouse=True)
def emails_enviados(monkeypatch) -> list[dict]:
    enviados: list[dict] = []

    def _fake_enviar(destinatario, assunto, html, texto=None):
        enviados.append({"destinatario": destinatario, "assunto": assunto, "html": html})
        return True

    monkeypatch.setattr(pops_email_service, "_enviar_email", _fake_enviar)
    return enviados


@pytest.fixture
def pendencias_liberadas(monkeypatch) -> list[str]:
    chamadas: list[str] = []

    def _fake(supabase, id_reuniao, origem=""):
        chamadas.append(id_reuniao)
        return 0

    monkeypatch.setattr(pendencia_service, "liberar_pendencias", _fake)
    return chamadas


# ═══════════════════════════════════════════════════════════════════════════
# CA: HMAC inválido é rejeitado
# ═══════════════════════════════════════════════════════════════════════════


class TestHmac:
    def test_hmac_invalido_rejeitado(self, pdf_assinado, uploads):
        client = _client(_sb())

        res = _post(client, _evento("AutoClose", "doc-key-pop"), secret="segredo-errado")

        assert res.status_code == 401
        assert uploads == []

    def test_sem_header_hmac_rejeitado(self):
        client = _client(_sb())
        body = json.dumps(_evento("AutoClose", "doc-key-pop")).encode()

        res = client.post("/api/webhooks/clicksign", content=body, headers={"Content-Type": "application/json"})

        assert res.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════
# CA: todas as assinaturas → PUBLICADO + PDF assinado no storage + email
# ═══════════════════════════════════════════════════════════════════════════


class TestPublicacao:
    def test_autoclose_publica_versao_com_pdf_e_email(self, pdf_assinado, uploads, emails_enviados):
        sb = _sb()
        client = _client(sb)

        res = _post(client, _evento("AutoClose", "doc-key-pop"))

        assert res.status_code == 200

        # PDF assinado baixado pelo ENVELOPE id (API v3), não pela document key
        assert pdf_assinado == ["env-1"]

        # Salvo no storage com a nomenclatura travada (status ASSINADO)
        assert len(uploads) == 1
        up = uploads[0]
        assert up["bucket"] == settings.supabase_storage_bucket_pdfs_assinados
        assert up["path"].startswith("pops/pop-1/HSM_CTI-001_")
        assert up["path"].endswith("_ASSINADO.pdf")
        assert up["content"] == b"%PDF-signed"

        # Versão PUBLICADO com data e URL persistidas
        versao = sb.tables["pops_versoes"][0]
        assert versao["estado"] == "PUBLICADO"
        assert versao["data_publicacao"]
        assert versao["url_pdf_assinado"] == f"http://storage/{up['bucket']}/{up['path']}"

        # Auditoria da publicação (ator: sistema/webhook)
        acoes = [r["action"] for r in sb.tables["audit_log"]]
        assert "POPS_PUBLICAR" in acoes

        # Email ao criador do POP (P6), não aos signatários (ClickSign cuida)
        assert len(emails_enviados) == 1
        email = emails_enviados[0]
        assert email["destinatario"] == "p6@hsm.com"
        assert "HSM_CTI-001" in email["assunto"]

    def test_evento_duplicado_e_idempotente(self, pdf_assinado, uploads, emails_enviados):
        """CA: evento duplicado não re-baixa PDF, não re-sobe storage, não
        re-envia email, não re-audita — a Versão já PUBLICADO encerra."""
        sb = _sb(
            versao=_versao(
                estado="PUBLICADO",
                url_pdf_assinado="http://storage/ja-publicado.pdf",
                data_publicacao="2026-06-10T10:00:00+00:00",
            )
        )
        client = _client(sb)

        res = _post(client, _evento("AutoClose", "doc-key-pop"))

        assert res.status_code == 200
        assert pdf_assinado == []
        assert uploads == []
        assert emails_enviados == []
        versao = sb.tables["pops_versoes"][0]
        assert versao["data_publicacao"] == "2026-06-10T10:00:00+00:00"
        assert versao["url_pdf_assinado"] == "http://storage/ja-publicado.pdf"

    def test_pdf_indisponivel_publica_sem_url(self, monkeypatch, uploads, emails_enviados):
        """ClickSign sem o PDF (None): a publicação acontece mesmo assim —
        sem upload e sem url_pdf_assinado; o download fica indisponível até
        correção manual, mas o ciclo formal fecha e o criador é avisado."""
        monkeypatch.setattr(clicksign_service, "get_signed_document", lambda _id: None)
        sb = _sb()
        client = _client(sb)

        res = _post(client, _evento("AutoClose", "doc-key-pop"))

        assert res.status_code == 200
        versao = sb.tables["pops_versoes"][0]
        assert versao["estado"] == "PUBLICADO"
        assert versao["data_publicacao"]
        assert versao["url_pdf_assinado"] is None
        assert uploads == []
        assert len(emails_enviados) == 1

    def test_key_desconhecida_ignorada_sem_efeito(self, pdf_assinado, uploads):
        sb = _sb()
        client = _client(sb)

        res = _post(client, _evento("AutoClose", "doc-key-fantasma"))

        assert res.status_code == 200
        assert uploads == []
        assert sb.tables["pops_versoes"][0]["estado"] == "EM_ASSINATURA"


# ═══════════════════════════════════════════════════════════════════════════
# CA: fluxo de assinatura de Reunião segue intacto (roteamento)
# ═══════════════════════════════════════════════════════════════════════════


class TestRoteamentoReuniao:
    def test_envelope_de_reuniao_segue_fluxo_de_reuniao(
        self, pdf_assinado, uploads, pendencias_liberadas, emails_enviados
    ):
        """Regressão do roteamento: document.key de Reunião processa o fluxo
        atual (ASSINADA + pendências liberadas) e não toca em POPs."""
        reuniao = {
            "id_reuniao": "R1",
            "status_ata": "AGUARDANDO_ASSINATURA",
            "envelope_key_clicksign": "doc-key-reuniao",
        }
        sb = _sb(reunioes=[reuniao])
        client = _client(sb)

        res = _post(client, _evento("AutoClose", "doc-key-reuniao"))

        assert res.status_code == 200
        assert sb.tables["reunioes"][0]["status_ata"] == "ASSINADA"
        assert pendencias_liberadas == ["R1"]
        # Comportamento atual preservado: o fluxo de Reunião consulta o
        # ClickSign pela document key gravada em envelope_key_clicksign.
        assert pdf_assinado == ["doc-key-reuniao"]
        # POPs intactos
        assert sb.tables["pops_versoes"][0]["estado"] == "EM_ASSINATURA"
        assert emails_enviados == []

    def test_envelope_de_pop_nao_toca_reunioes(self, pdf_assinado, uploads):
        reuniao = {
            "id_reuniao": "R1",
            "status_ata": "AGUARDANDO_ASSINATURA",
            "envelope_key_clicksign": "doc-key-reuniao",
        }
        sb = _sb(reunioes=[reuniao])
        client = _client(sb)

        res = _post(client, _evento("AutoClose", "doc-key-pop"))

        assert res.status_code == 200
        assert sb.tables["reunioes"][0]["status_ata"] == "AGUARDANDO_ASSINATURA"
        assert sb.tables["pops_versoes"][0]["estado"] == "PUBLICADO"


# ═══════════════════════════════════════════════════════════════════════════
# Interrupção do Envelope (Refused/Expired/Cancelled) — re-tentável
# ═══════════════════════════════════════════════════════════════════════════


class TestEnvelopeInterrompido:
    def test_refused_limpa_envelope_e_mantem_em_assinatura(self, pdf_assinado, uploads):
        """Envelope recusado/expirado morreu no ClickSign: limpa os IDs da
        Versão (o reenvio cria Envelope novo) e mantém EM_ASSINATURA."""
        sb = _sb()
        client = _client(sb)

        res = _post(client, _evento("Refused", "doc-key-pop"))

        assert res.status_code == 200
        versao = sb.tables["pops_versoes"][0]
        assert versao["estado"] == "EM_ASSINATURA"
        assert versao["envelope_id_clicksign"] is None
        assert versao["envelope_key_clicksign"] is None
        assert uploads == []

        acoes = [r["action"] for r in sb.tables["audit_log"]]
        assert "POPS_ASSINATURA_INTERROMPIDA" in acoes
