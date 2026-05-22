"""
Testes dos endpoints `/reunioes/{id}/signatarios/status` (GET, polling) e
`/reunioes/{id}/signatarios/{signer_id}/lembrar` (POST, reenvio de email).

Cobre paths felizes + edge cases (legacy, ClickSign down, secretaria, status
errado, reuniao inexistente) e os helpers do clicksign_service.list_signers /
remind_signer (mock httpx.Client).
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.dependencies import (  # noqa: E402
    get_current_user,
    get_supabase_client,
)
from app.routers import reunioes as reunioes_router  # noqa: E402

# ─── Mock Supabase ───────────────────────────────────────────────────────────


@dataclass
class _Result:
    data: Any


class _TableQuery:
    """Mock fluente compativel com select/update/delete/upsert + eq/in_."""

    def __init__(self, rows_ref: list):
        self._rows = rows_ref
        self._op: str = "select"
        self._payload: Any = None
        self._filters: list[tuple[str, Any]] = []
        self._in_filters: list[tuple[str, list]] = []

    def select(self, *_a, **_kw):
        self._op = "select"
        return self

    def update(self, payload):
        self._op = "update"
        self._payload = payload
        return self

    def delete(self):
        self._op = "delete"
        return self

    def eq(self, col, value):
        self._filters.append((col, value))
        return self

    def in_(self, col, values):
        self._in_filters.append((col, list(values)))
        return self

    def _matches(self, r: dict) -> bool:
        for col, value in self._filters:
            if r.get(col) != value:
                return False
        for col, values in self._in_filters:
            if r.get(col) not in values:
                return False
        return True

    def execute(self):
        matched = [r for r in self._rows if self._matches(r)]
        if self._op == "update":
            for r in matched:
                r.update(self._payload or {})
            return _Result(data=list(matched))
        if self._op == "delete":
            for r in list(matched):
                self._rows.remove(r)
            return _Result(data=list(matched))
        return _Result(data=list(matched))


@dataclass
class _SupabaseMock:
    participantes: list = field(default_factory=list)
    reuniao_participantes: list = field(default_factory=list)
    reunioes: list = field(default_factory=list)

    def table(self, name: str):
        if name == "participantes":
            return _TableQuery(self.participantes)
        if name == "reuniao_participantes":
            # Hidrata o relacionamento participantes(...) inline (mesmo formato do supabase-py)
            hydrated: list[dict] = []
            for rp in self.reuniao_participantes:
                p_match = next((p for p in self.participantes if p["id"] == rp.get("participante_id")), None)
                row = dict(rp)
                if p_match:
                    row["participantes"] = {
                        "nome_completo": p_match.get("nome_completo"),
                        "email": p_match.get("email"),
                    }
                hydrated.append(row)
            return _TableQuery(hydrated)
        if name == "reunioes":
            return _TableQuery(self.reunioes)
        raise AssertionError(f"Tabela inesperada: {name}")


# ─── App fixture ──────────────────────────────────────────────────────────────


CURRENT_USER = {"id": "auth-uid-1", "email": "diretor@hospital.com"}


@pytest.fixture
def make_client(monkeypatch):
    """Factory que monta TestClient com supabase mock + auth/visibilidade plugados."""

    def _factory(
        supabase: _SupabaseMock,
        *,
        is_secretaria_override: bool = False,
        allowed_ids: set | None = None,
    ) -> TestClient:
        from slowapi import _rate_limit_exceeded_handler
        from slowapi.errors import RateLimitExceeded

        from app.limiter import limiter

        app = FastAPI()
        app.state.limiter = limiter
        app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
        app.include_router(reunioes_router.router, prefix="/api")

        app.dependency_overrides[get_current_user] = lambda: CURRENT_USER
        app.dependency_overrides[get_supabase_client] = lambda: supabase

        async def _fake_get_participante(*_a, **_kw):
            return {"id": "P_DIRETOR", "access_profile": "regular"}

        async def _fake_allowed(*_a, **_kw):
            return allowed_ids  # None = sem restrição

        # get_participante_for_user e get_allowed_reuniao_ids sao chamados como
        # funcoes (nao via Depends), entao precisam ser monkeypatched no modulo
        # do router. is_secretaria idem.
        monkeypatch.setattr(reunioes_router, "get_participante_for_user", _fake_get_participante)
        monkeypatch.setattr(reunioes_router, "get_allowed_reuniao_ids", _fake_allowed)
        monkeypatch.setattr(reunioes_router, "is_secretaria", lambda _me: is_secretaria_override)

        return TestClient(app)

    return _factory


def _participante(pid, nome, email):
    return {"id": pid, "nome_completo": nome, "email": email}


# ═══════════════════════════════════════════════════════════════════════════
# GET /reunioes/{id}/signatarios/status
# ═══════════════════════════════════════════════════════════════════════════


class TestSignatariosStatus:
    def test_200_normalizado(self, make_client, monkeypatch):
        sb = _SupabaseMock(
            participantes=[
                _participante("P1", "Pedro Rezende", "pedro@hsm.com"),
                _participante("P2", "Ana Lima", "ana@hsm.com"),
            ],
            reuniao_participantes=[
                {"id_reuniao": "R1", "participante_id": "P1"},
                {"id_reuniao": "R1", "participante_id": "P2"},
            ],
            reunioes=[
                {
                    "id_reuniao": "R1",
                    "status_ata": "AGUARDANDO_ASSINATURA",
                    "envelope_key_clicksign": "doc-key",
                    "envelope_id_clicksign": "env-id-1",
                }
            ],
        )

        from app.services import clicksign_service

        monkeypatch.setattr(
            clicksign_service,
            "list_signers",
            lambda _env: [
                {
                    "signer_id": "s1",
                    "nome": "Pedro Rezende",
                    "email": "pedro@hsm.com",
                    "status": "signed",
                    "signed_at": "2026-05-18T14:32:00Z",
                },
                {
                    "signer_id": "s2",
                    "nome": "Ana Lima",
                    "email": "ana@hsm.com",
                    "status": "pending",
                    "signed_at": None,
                },
            ],
        )

        client = make_client(sb)
        r = client.get("/api/reunioes/R1/signatarios/status")
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 2
        assert body["assinaram"] == 1
        assert body["envelope_id"] == "env-id-1"
        assert body["signatarios"][0]["status"] == "signed"
        assert body["signatarios"][0]["signed_at"] == "2026-05-18T14:32:00Z"
        assert "legacy_warning" not in body

    def test_400_quando_envelope_key_nulo(self, make_client):
        sb = _SupabaseMock(
            reunioes=[
                {
                    "id_reuniao": "R1",
                    "status_ata": "AGUARDANDO_VALIDACAO",
                    "envelope_key_clicksign": None,
                    "envelope_id_clicksign": None,
                }
            ],
        )
        client = make_client(sb)
        r = client.get("/api/reunioes/R1/signatarios/status")
        assert r.status_code == 400
        assert "assinatura" in r.json()["detail"].lower()

    def test_404_quando_reuniao_inexistente(self, make_client):
        sb = _SupabaseMock(reunioes=[])
        client = make_client(sb)
        r = client.get("/api/reunioes/NOPE/signatarios/status")
        assert r.status_code == 404

    def test_503_quando_clicksign_falha(self, make_client, monkeypatch):
        sb = _SupabaseMock(
            reunioes=[
                {
                    "id_reuniao": "R1",
                    "status_ata": "AGUARDANDO_ASSINATURA",
                    "envelope_key_clicksign": "doc-key",
                    "envelope_id_clicksign": "env-id-1",
                }
            ],
        )
        from app.services import clicksign_service

        monkeypatch.setattr(clicksign_service, "list_signers", lambda _env: None)

        client = make_client(sb)
        r = client.get("/api/reunioes/R1/signatarios/status")
        assert r.status_code == 503

    def test_200_legacy_sem_envelope_id(self, make_client):
        """Reuniao pre-PR2: tem document_id mas nao envelope_id → modo degradado."""
        sb = _SupabaseMock(
            participantes=[
                _participante("P1", "Pedro Rezende", "pedro@hsm.com"),
                _participante("P2", "Ana Lima", "ana@hsm.com"),
            ],
            reuniao_participantes=[
                {"id_reuniao": "R1", "participante_id": "P1"},
                {"id_reuniao": "R1", "participante_id": "P2"},
            ],
            reunioes=[
                {
                    "id_reuniao": "R1",
                    "status_ata": "AGUARDANDO_ASSINATURA",
                    "envelope_key_clicksign": "doc-key",
                    "envelope_id_clicksign": None,
                }
            ],
        )
        client = make_client(sb)
        r = client.get("/api/reunioes/R1/signatarios/status")
        assert r.status_code == 200
        body = r.json()
        assert body["envelope_id"] is None
        assert body["assinaram"] == 0
        assert body["total"] == 2
        assert "legacy_warning" in body
        assert all(s["status"] == "pending" for s in body["signatarios"])

    def test_403_secretaria_bloqueada(self, make_client):
        sb = _SupabaseMock(reunioes=[])
        client = make_client(sb, is_secretaria_override=True)
        r = client.get("/api/reunioes/R1/signatarios/status")
        assert r.status_code == 403

    def test_404_visibilidade_negada(self, make_client):
        sb = _SupabaseMock(
            reunioes=[
                {
                    "id_reuniao": "R_OUTRA",
                    "status_ata": "AGUARDANDO_ASSINATURA",
                    "envelope_key_clicksign": "doc-key",
                    "envelope_id_clicksign": "env-id",
                }
            ],
        )
        client = make_client(sb, allowed_ids={"R_PERMITIDA"})  # R_OUTRA fora do allowlist
        r = client.get("/api/reunioes/R_OUTRA/signatarios/status")
        assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════
# POST /reunioes/{id}/signatarios/{signer_id}/lembrar
# ═══════════════════════════════════════════════════════════════════════════


class TestLembrarSignatario:
    def _sb_aguardando(self) -> _SupabaseMock:
        return _SupabaseMock(
            reunioes=[
                {
                    "id_reuniao": "R1",
                    "status_ata": "AGUARDANDO_ASSINATURA",
                    "envelope_id_clicksign": "env-id-1",
                    "tipo": "Diretoria",
                    "data": "2026-05-18",
                }
            ],
        )

    def test_200_lembrete_enviado(self, make_client, monkeypatch):
        sb = self._sb_aguardando()
        from app.services import clicksign_service

        captured: list[tuple] = []

        def _fake_remind(env_id, sid, message=None):
            captured.append((env_id, sid, message))
            return True

        monkeypatch.setattr(clicksign_service, "remind_signer", _fake_remind)
        client = make_client(sb)
        r = client.post("/api/reunioes/R1/signatarios/sig-abc/lembrar")
        assert r.status_code == 200
        assert r.json() == {"sent": True, "signer_id": "sig-abc"}
        assert len(captured) == 1
        env_id, signer_id, message = captured[0]
        assert env_id == "env-id-1"
        assert signer_id == "sig-abc"
        assert "Diretoria" in message
        assert "18/05/2026" in message

    def test_502_quando_clicksign_falha(self, make_client, monkeypatch):
        sb = self._sb_aguardando()
        from app.services import clicksign_service

        monkeypatch.setattr(clicksign_service, "remind_signer", lambda *_a, **_kw: False)
        client = make_client(sb)
        r = client.post("/api/reunioes/R1/signatarios/sig-abc/lembrar")
        assert r.status_code == 502

    def test_400_status_errado(self, make_client):
        sb = _SupabaseMock(
            reunioes=[
                {
                    "id_reuniao": "R1",
                    "status_ata": "AGUARDANDO_VALIDACAO",
                    "envelope_id_clicksign": "env-id-1",
                    "tipo": "Diretoria",
                    "data": "2026-05-18",
                }
            ],
        )
        client = make_client(sb)
        r = client.post("/api/reunioes/R1/signatarios/sig-abc/lembrar")
        assert r.status_code == 400

    def test_400_legacy_sem_envelope_id(self, make_client):
        sb = _SupabaseMock(
            reunioes=[
                {
                    "id_reuniao": "R1",
                    "status_ata": "AGUARDANDO_ASSINATURA",
                    "envelope_id_clicksign": None,
                    "tipo": "Diretoria",
                    "data": "2026-05-18",
                }
            ],
        )
        client = make_client(sb)
        r = client.post("/api/reunioes/R1/signatarios/sig-abc/lembrar")
        assert r.status_code == 400

    def test_403_secretaria(self, make_client):
        sb = self._sb_aguardando()
        client = make_client(sb, is_secretaria_override=True)
        r = client.post("/api/reunioes/R1/signatarios/sig-abc/lembrar")
        assert r.status_code == 403

    def test_404_reuniao_inexistente(self, make_client):
        sb = _SupabaseMock(reunioes=[])
        client = make_client(sb)
        r = client.post("/api/reunioes/NOPE/signatarios/sig-abc/lembrar")
        assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════
# clicksign_service.list_signers + remind_signer (unit, mock httpx)
# ═══════════════════════════════════════════════════════════════════════════


class _FakeResponse:
    def __init__(self, status_code: int, json_body: Any = None, text: str = ""):
        self.status_code = status_code
        self._json = json_body
        self.text = text or ""

    def json(self):
        return self._json

    def raise_for_status(self):
        import httpx

        if self.status_code >= 400:
            req = httpx.Request("GET", "http://x")
            raise httpx.HTTPStatusError("err", request=req, response=httpx.Response(self.status_code))


class _FakeClient:
    """Mock context manager pra httpx.Client. Recebe um handler por método."""

    def __init__(self, handler):
        self._handler = handler

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def get(self, url, headers=None, **_kw):
        return self._handler("GET", url, None)

    def post(self, url, json=None, headers=None, **_kw):
        return self._handler("POST", url, json)


class TestListSignersService:
    def test_sucesso_normaliza_payload(self, monkeypatch):
        import httpx

        from app.services import clicksign_service

        def _handler(method, _url, _json):
            assert method == "GET"
            return _FakeResponse(
                200,
                {
                    "data": [
                        {
                            "id": "s1",
                            "attributes": {
                                "name": "Pedro",
                                "email": "p@ex.com",
                                "signed_at": "2026-05-18T14:32:00Z",
                            },
                        },
                        {
                            "id": "s2",
                            "attributes": {
                                "name": "Ana",
                                "email": "a@ex.com",
                                "signed_at": None,
                            },
                        },
                    ]
                },
            )

        monkeypatch.setattr(httpx, "Client", lambda **_kw: _FakeClient(_handler))
        result = clicksign_service.list_signers("env-id")
        assert result is not None
        assert len(result) == 2
        assert result[0]["status"] == "signed"
        assert result[0]["signed_at"] == "2026-05-18T14:32:00Z"
        assert result[1]["status"] == "pending"
        assert result[1]["signed_at"] is None

    def test_404_retorna_none(self, monkeypatch):
        import httpx

        from app.services import clicksign_service

        monkeypatch.setattr(
            httpx,
            "Client",
            lambda **_kw: _FakeClient(lambda *_a: _FakeResponse(404, {"errors": []}, text="not found")),
        )
        assert clicksign_service.list_signers("env-id") is None

    def test_timeout_retorna_none(self, monkeypatch):
        import httpx

        from app.services import clicksign_service

        def _handler(*_a):
            raise httpx.TimeoutException("slow")

        monkeypatch.setattr(httpx, "Client", lambda **_kw: _FakeClient(_handler))
        assert clicksign_service.list_signers("env-id") is None


class TestRemindSignerService:
    def test_sucesso_passa_message(self, monkeypatch):
        import httpx

        from app.services import clicksign_service

        captured: list[tuple] = []

        def _handler(method, url, body):
            captured.append((method, url, body))
            return _FakeResponse(200, {})

        monkeypatch.setattr(httpx, "Client", lambda **_kw: _FakeClient(_handler))
        ok = clicksign_service.remind_signer("env-id", "sig-abc", message="OLA")
        assert ok is True
        assert len(captured) == 1
        method, url, body = captured[0]
        assert method == "POST"
        assert "/envelopes/env-id/signers/sig-abc/notifications" in url
        assert body["data"]["attributes"]["message"] == "OLA"

    def test_falha_4xx_retorna_false(self, monkeypatch):
        import httpx

        from app.services import clicksign_service

        monkeypatch.setattr(
            httpx,
            "Client",
            lambda **_kw: _FakeClient(lambda *_a: _FakeResponse(422, {}, text="bad")),
        )
        assert clicksign_service.remind_signer("env-id", "sig-abc") is False

    def test_timeout_retorna_false(self, monkeypatch):
        import httpx

        from app.services import clicksign_service

        def _handler(*_a):
            raise httpx.TimeoutException("slow")

        monkeypatch.setattr(httpx, "Client", lambda **_kw: _FakeClient(_handler))
        assert clicksign_service.remind_signer("env-id", "sig-abc") is False
