"""Modo interno: recusa, cancelamento e deadline sem assinaturas (issue #276, ADR 0030).

Seam: POST /api/webhooks/clicksign com payloads oficiais da ClickSign
(eventos `refusal`, `cancel` e `deadline`, snake_case). Recusa, cancelamento
manual ou deadline com zero assinaturas abrem o modo interno: a Reuniao
permanece em AGUARDANDO_ASSINATURA com flag persistida (`modo_interno_desde`),
as Pendencias ja nascidas sao mantidas e nao ha mais volta para
AGUARDANDO_VALIDACAO. `deadline` com ao menos uma assinatura e finalizacao
(fatia #275) e nao abre o modo interno.

ClickSign SEMPRE mockado (o .env de teste carrega credenciais reais).
"""

from __future__ import annotations

import hashlib
import hmac as hmac_lib
import json
import os
import sys
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.config import settings  # noqa: E402
from app.dependencies import get_supabase_client  # noqa: E402
from app.routers import webhooks as webhooks_router  # noqa: E402
from app.services import clicksign_service, storage  # noqa: E402

SECRET = "test-secret"
DOC_KEY = "doc-key-r1"

# ─── Mock Supabase (mesmo estilo de test_aceites_sign_incremental) ───────────


class _Result:
    def __init__(self, data: list):
        self.data = data


class _TableQuery:
    def __init__(self, rows: list[dict]):
        self._rows = rows
        self._filters: dict = {}
        self._is_filters: dict = {}
        self._in_filters: dict = {}
        self._limit: int | None = None
        self._insert_payload: list[dict] | None = None
        self._update_payload: dict | None = None

    def select(self, *_a, **_kw):
        return self

    def eq(self, col, value):
        self._filters[col] = value
        return self

    def in_(self, col, values):
        self._in_filters[col] = list(values)
        return self

    def is_(self, col, value):
        self._is_filters[col] = None if value in ("null", None) else value
        return self

    def order(self, *_a, **_kw):
        return self

    def limit(self, n):
        self._limit = n
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
            for row in self._insert_payload:
                row.setdefault("id", f"row-{len(self._rows) + 1}")
                self._rows.append(dict(row))
            return _Result(data=[dict(r) for r in self._insert_payload])

        filtered = [
            r
            for r in self._rows
            if all(r.get(c) == v for c, v in self._filters.items())
            and all(r.get(c) in vs for c, vs in self._in_filters.items())
            and all(r.get(c) == v for c, v in self._is_filters.items())
        ]
        if self._update_payload is not None:
            for row in filtered:
                row.update(self._update_payload)
            return _Result(data=[dict(r) for r in filtered])
        if self._limit is not None:
            filtered = filtered[: self._limit]
        return _Result(data=[dict(r) for r in filtered])


class _SupabaseMock:
    def __init__(self, tables: dict[str, list[dict]]):
        self.tables = tables

    def table(self, name: str):
        if name not in self.tables:
            raise AssertionError(f"Tabela inesperada: {name}")
        return _TableQuery(self.tables[name])


# ─── Dados ───────────────────────────────────────────────────────────────────


def _participante(pid: str, nome: str, email: str) -> dict:
    return {"id": pid, "nome_completo": nome, "email": email, "cargo": "Cargo", "setor": "Setor", "ativo": True}


def _quadro() -> list[dict]:
    return [
        {"acao": "Revisar protocolo", "responsavel": "Ana Lima", "responsavel_id": "P_ANA", "prazo": "2026-09-01"},
        {"acao": "Comprar insumos", "responsavel": "Bruno Costa", "responsavel_id": "P_BRUNO", "prazo": "10/09/2026"},
    ]


def _sb(**reuniao_over) -> _SupabaseMock:
    reuniao = {
        "id_reuniao": "R1",
        "status_ata": "AGUARDANDO_ASSINATURA",
        "envelope_key_clicksign": DOC_KEY,
        "envelope_id_clicksign": "env-r1",
        "facilitador_id": "P_FAC",
        "modo_interno_desde": None,
        "json_ata": {"quadro_atribuicoes": _quadro()},
    }
    reuniao.update(reuniao_over)
    return _SupabaseMock(
        {
            "reunioes": [reuniao],
            "pops_versoes": [],
            "participantes": [
                _participante("P_FAC", "Fabio Facilitador", "fabio@hsm.com"),
                _participante("P_ANA", "Ana Lima", "ana@hsm.com"),
                _participante("P_BRUNO", "Bruno Costa", "bruno@hsm.com"),
            ],
            "reuniao_participantes": [
                {"id_reuniao": "R1", "participante_id": "P_FAC"},
                {"id_reuniao": "R1", "participante_id": "P_ANA"},
                {"id_reuniao": "R1", "participante_id": "P_BRUNO"},
            ],
            "pendencias": [],
            "reuniao_aceites": [],
        }
    )


def _client(sb: _SupabaseMock) -> TestClient:
    app = FastAPI()
    app.include_router(webhooks_router.router, prefix="/api")
    app.dependency_overrides[get_supabase_client] = lambda: sb
    return TestClient(app, raise_server_exceptions=False)


def _post(client: TestClient, payload: dict, *, secret: str = SECRET) -> Any:
    body = json.dumps(payload).encode("utf-8")
    assinatura = hmac_lib.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return client.post(
        "/api/webhooks/clicksign",
        content=body,
        headers={"Content-Hmac": f"sha256={assinatura}", "Content-Type": "application/json"},
    )


def _evento_refusal() -> dict:
    """Payload oficial do evento `refusal` (developers.clicksign.com/docs/evento-refusal)."""
    return {
        "event": {
            "name": "refusal",
            "data": {
                "signer": {"key": "sk-ana", "email": "ana@hsm.com", "name": "Ana Lima"},
                "refusal": {"reasons": ["Nao concordo com o texto"], "comment": "Rever item 2"},
            },
            "occurred_at": "2026-08-14T12:00:00.000-03:00",
        },
        "document": {"key": DOC_KEY},
    }


def _evento_cancel() -> dict:
    """Payload oficial do evento `cancel` (developers.clicksign.com/docs/evento-cancel)."""
    return {
        "event": {
            "name": "cancel",
            "data": {"user": {"email": "operador@hsm.com", "name": "Operador"}, "account": {"key": "acc-1"}},
            "occurred_at": "2026-08-14T12:00:00.000-03:00",
        },
        "document": {"key": DOC_KEY},
    }


def _evento_deadline() -> dict:
    """Payload oficial do evento `deadline` (developers.clicksign.com/docs/evento-deadline)."""
    return {
        "event": {
            "name": "deadline",
            "data": {"reached_at": "2026-08-14T12:00:00.000-03:00"},
            "occurred_at": "2026-08-14T12:00:00.000-03:00",
        },
        "document": {"key": DOC_KEY},
    }


def _evento(nome: str) -> dict:
    return {
        "event": {"name": nome, "data": None, "occurred_at": "2026-08-14T12:00:00.000-03:00"},
        "document": {"key": DOC_KEY},
    }


def _aceite_clicksign(pid: str, signer_key: str, email: str) -> dict:
    return {
        "id": f"aceite-{pid}",
        "id_reuniao": "R1",
        "participante_id": pid,
        "signer_key": signer_key,
        "email": email,
        "origem": "clicksign",
        "aceito_em": "2026-08-10T10:00:00-03:00",
    }


def _pendencia_nascida(id_acao: str, quadro_pos: int, responsavel_id: str) -> dict:
    return {
        "id_acao": id_acao,
        "id_reuniao": "R1",
        "status": "PENDENTE",
        "responsavel_id": responsavel_id,
        "quadro_pos": quadro_pos,
    }


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _secret(monkeypatch):
    monkeypatch.setattr(settings, "clicksign_webhook_secret", SECRET)


@pytest.fixture(autouse=True)
def _bloquear_httpx(monkeypatch):
    import httpx

    def _explode(*_a, **_kw):
        raise AssertionError("Chamada httpx real bloqueada nos testes")

    monkeypatch.setattr(httpx, "Client", _explode)


@pytest.fixture(autouse=True)
def _clicksign_e_storage_mockados(monkeypatch):
    monkeypatch.setattr(clicksign_service, "get_signed_document", lambda _env: b"%PDF-signed")
    monkeypatch.setattr(storage, "upload_file", lambda *_a, **_kw: "http://storage/pdfs/ata_assinada.pdf")
    # Consulta de signers indisponível: `houve_assinatura` decide o desfecho do
    # `deadline` pelo fallback dos aceites `clicksign` locais (issue #275).
    monkeypatch.setattr(clicksign_service, "list_signers", lambda _env: None)


def _reuniao(sb: _SupabaseMock) -> dict:
    return sb.tables["reunioes"][0]


# ═══════════════════════════════════════════════════════════════════════════
# CA: refusal, cancel e deadline com zero assinaturas abrem o modo interno
# ═══════════════════════════════════════════════════════════════════════════


class TestAberturaDoModoInterno:
    @pytest.mark.parametrize(
        "payload",
        [_evento_refusal(), _evento_cancel(), _evento_deadline()],
        ids=["refusal", "cancel", "deadline-zero-assinaturas"],
    )
    def test_evento_abre_modo_interno_sem_voltar_para_validacao(self, payload):
        sb = _sb()
        res = _post(_client(sb), payload)

        assert res.status_code == 200
        reuniao = _reuniao(sb)
        assert reuniao["status_ata"] == "AGUARDANDO_ASSINATURA"
        assert reuniao["modo_interno_desde"]

    def test_deadline_com_assinatura_finaliza_sem_abrir_modo_interno(self):
        """`deadline` com ao menos um aceite clicksign e finalizacao real
        (fatia #275): a Reuniao vira ASSINADA e o modo interno nao abre."""
        sb = _sb()
        sb.tables["reuniao_aceites"].append(_aceite_clicksign("P_ANA", "sk-ana", "ana@hsm.com"))

        res = _post(_client(sb), _evento_deadline())

        assert res.status_code == 200
        reuniao = _reuniao(sb)
        assert reuniao["status_ata"] == "ASSINADA"
        assert not reuniao["modo_interno_desde"]

    def test_refusal_com_reuniao_assinada_e_ignorado(self):
        sb = _sb(status_ata="ASSINADA")
        res = _post(_client(sb), _evento_refusal())

        assert res.status_code == 200
        reuniao = _reuniao(sb)
        assert reuniao["status_ata"] == "ASSINADA"
        assert not reuniao["modo_interno_desde"]

    def test_evento_repetido_e_idempotente(self):
        """Redelivery de refusal/cancel nao reabre nem reescreve o timestamp."""
        sb = _sb()
        client = _client(sb)
        _post(client, _evento_refusal())
        primeiro = _reuniao(sb)["modo_interno_desde"]
        assert primeiro

        res = _post(client, _evento_cancel())
        assert res.status_code == 200
        assert _reuniao(sb)["modo_interno_desde"] == primeiro

    def test_abertura_e_um_unico_update_condicionado(self):
        """abrir_modo_interno guarda a idempotencia no proprio UPDATE (WHERE
        modo_interno_desde IS NULL), sem janela de leitura-e-escrita: dois
        webhooks concorrentes nunca reabrem o modo interno um por cima do
        outro (a segunda chamada nao encontra linha pra afetar e retorna
        False sem reescrever o timestamp)."""
        from app.services import aceite_service

        sb = _sb()
        primeira = aceite_service.abrir_modo_interno(sb, "R1", evento="refusal")
        assert primeira is True
        timestamp = _reuniao(sb)["modo_interno_desde"]
        assert timestamp

        segunda = aceite_service.abrir_modo_interno(sb, "R1", evento="cancel")
        assert segunda is False
        assert _reuniao(sb)["modo_interno_desde"] == timestamp


# ═══════════════════════════════════════════════════════════════════════════
# CA: Pendencias ja nascidas sao mantidas intactas
# ═══════════════════════════════════════════════════════════════════════════


class TestPendenciasMantidas:
    def test_refusal_mantem_pendencias_nascidas(self):
        sb = _sb()
        sb.tables["reuniao_aceites"].append(_aceite_clicksign("P_ANA", "sk-ana", "ana@hsm.com"))
        sb.tables["pendencias"].append(_pendencia_nascida("A001", 0, "P_ANA"))
        antes = [dict(p) for p in sb.tables["pendencias"]]

        res = _post(_client(sb), _evento_refusal())

        assert res.status_code == 200
        assert sb.tables["pendencias"] == antes
        assert _reuniao(sb)["modo_interno_desde"]

    def test_cancel_nao_cria_pendencia_nova(self):
        sb = _sb()
        res = _post(_client(sb), _evento_cancel())

        assert res.status_code == 200
        assert sb.tables["pendencias"] == []


# ═══════════════════════════════════════════════════════════════════════════
# Nomes inexistentes na doc oficial sairam do mapeamento (PRD #272)
# ═══════════════════════════════════════════════════════════════════════════


class TestNomesLegadosRemovidos:
    @pytest.mark.parametrize("nome", ["Refused", "refused", "Expired", "Cancelled", "expired", "cancelled"])
    def test_nome_inexistente_nao_tem_acao(self, nome):
        """Os nomes que nao existem na doc oficial deixam de devolver a
        Reuniao para AGUARDANDO_VALIDACAO (caem no ramo sem acao)."""
        sb = _sb()
        res = _post(_client(sb), _evento(nome))

        assert res.status_code == 200
        reuniao = _reuniao(sb)
        assert reuniao["status_ata"] == "AGUARDANDO_ASSINATURA"
        assert not reuniao["modo_interno_desde"]
