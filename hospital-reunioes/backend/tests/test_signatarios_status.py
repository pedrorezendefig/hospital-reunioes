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

    def is_(self, col, value):
        # PostgREST: .is_("deleted_at", "null") filtra coluna IS NULL
        self._filters.append((col, None if value in ("null", None) else value))
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
    pendencias: list = field(default_factory=list)

    def table(self, name: str):
        if name == "participantes":
            return _TableQuery(self.participantes)
        if name == "pendencias":
            return _TableQuery(self.pendencias)
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


@pytest.fixture(autouse=True)
def _reset_self_heal_cooldown():
    """Zera o cooldown em memoria do self-heal entre testes (estado de modulo)."""
    reunioes_router._self_heal_failures.clear()
    yield
    reunioes_router._self_heal_failures.clear()


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

    def test_200_legacy_sem_envelope_id(self, make_client, monkeypatch):
        """Reuniao pre-PR2: tem document_id mas nao envelope_id. Quando o self-heal
        NAO recupera (Envelope ausente na conta), permanece em modo degradado."""
        from app.services import clicksign_service

        monkeypatch.setattr(clicksign_service, "find_envelope_id", lambda *_a, **_kw: None)
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

    def test_200_devolve_progresso_de_pendencias(self, make_client, monkeypatch):
        """Contador do nascimento incremental (ADR 0030): Pendencias criadas x
        total de acoes do quadro, pro card mostrar 'Pendencias criadas: X de Y'."""
        sb = _SupabaseMock(
            participantes=[_participante("P1", "Pedro Rezende", "pedro@hsm.com")],
            reuniao_participantes=[{"id_reuniao": "R1", "participante_id": "P1"}],
            reunioes=[
                {
                    "id_reuniao": "R1",
                    "status_ata": "AGUARDANDO_ASSINATURA",
                    "envelope_key_clicksign": "doc-key",
                    "envelope_id_clicksign": "env-id-1",
                    "json_ata": {
                        "quadro_atribuicoes": [
                            {"acao": "Acao 1", "responsavel": "Pedro Rezende"},
                            {"acao": "Acao 2", "responsavel": "Ana Lima"},
                            {"acao": "Acao 3", "responsavel": "Ana Lima"},
                        ]
                    },
                }
            ],
            pendencias=[
                {"id_acao": "A001", "id_reuniao": "R1", "quadro_pos": 0},
                {"id_acao": "A009", "id_reuniao": "R_OUTRA", "quadro_pos": 0},
                # Soft-deleted nao conta no progresso (paridade com o painel)
                {"id_acao": "A010", "id_reuniao": "R1", "quadro_pos": 1, "deleted_at": "2026-08-01T00:00:00Z"},
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
                    "signed_at": None,
                }
            ],
        )

        client = make_client(sb)
        r = client.get("/api/reunioes/R1/signatarios/status")
        assert r.status_code == 200
        body = r.json()
        assert body["pendencias_criadas"] == 1  # so as da R1
        assert body["total_acoes"] == 3

    def test_200_legacy_tambem_devolve_progresso(self, make_client, monkeypatch):
        from app.services import clicksign_service

        monkeypatch.setattr(clicksign_service, "find_envelope_id", lambda *_a, **_kw: None)
        sb = _SupabaseMock(
            participantes=[_participante("P1", "Pedro Rezende", "pedro@hsm.com")],
            reuniao_participantes=[{"id_reuniao": "R1", "participante_id": "P1"}],
            reunioes=[
                {
                    "id_reuniao": "R1",
                    "status_ata": "AGUARDANDO_ASSINATURA",
                    "envelope_key_clicksign": "doc-key",
                    "envelope_id_clicksign": None,
                    "json_ata": {"quadro_atribuicoes": [{"acao": "Acao 1", "responsavel": "Pedro Rezende"}]},
                }
            ],
        )
        client = make_client(sb)
        r = client.get("/api/reunioes/R1/signatarios/status")
        assert r.status_code == 200
        body = r.json()
        assert body["pendencias_criadas"] == 0
        assert body["total_acoes"] == 1

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


# ─── Helpers de payload da API v3 (formato real de produção) ──────────────────
# Importante: o objeto `signer` (GET /signers) NAO carrega status de assinatura
# na v3. Quem assinou so aparece como evento `sign` em GET /events.


def _signer_obj(sid: str, nome: str, email: str) -> dict:
    return {"id": sid, "type": "signers", "attributes": {"name": nome, "email": email}}


def _sign_event(key: str, email: str, nome: str, created: str) -> dict:
    """Evento de assinatura CONCLUIDA (name == 'sign')."""
    return {
        "id": f"ev-sign-{key}",
        "type": "events",
        "attributes": {
            "name": "sign",
            "data": {"signer": {"sign_as": "sign", "key": key, "email": email, "name": nome}},
            "created": created,
        },
    }


def _started_event(key: str, email: str) -> dict:
    """Evento de que o signatario ABRIU o documento (name == 'signature_started').
    NAO significa que assinou — nao deve contar como signed."""
    return {
        "id": f"ev-started-{key}",
        "type": "events",
        "attributes": {
            "name": "signature_started",
            "data": {"signer": {"key": key, "email": email}},
            "created": "2026-05-22T11:00:00.000-03:00",
        },
    }


def _signers_events_handler(signers_payload: dict, events_payload: dict):
    """Handler de _FakeClient que despacha por URL: /signers vs /events."""

    def _handler(method, url, _json):
        assert method == "GET"
        if "/events" in url:
            return _FakeResponse(200, events_payload)
        if "/signers" in url:
            return _FakeResponse(200, signers_payload)
        raise AssertionError(f"URL inesperada: {url}")

    return _handler


class TestListSignersService:
    def test_cruza_signers_com_eventos_sign(self, monkeypatch):
        """O status real vem dos eventos `sign`, nao do objeto signer (que nao
        carrega signed_at na v3). Cenario 5/6: um sem evento sign fica pending."""
        import httpx

        from app.services import clicksign_service

        signers = {
            "data": [
                _signer_obj("106", "Josiane Alves", "josiane@hsm.com.br"),
                _signer_obj("fa0", "Lucas Louro", "ti_lucas@hsm.com.br"),
            ],
            "links": {"next": None},
        }
        events = {
            "data": [
                _started_event("fa0", "ti_lucas@hsm.com.br"),  # so abriu — nao conta
                _sign_event("fa0", "ti_lucas@hsm.com.br", "Lucas Louro", "2026-05-27T15:09:47.224-03:00"),
                # josiane (106) nao tem evento sign -> pending
            ],
            "links": {"next": None},
        }
        monkeypatch.setattr(httpx, "Client", lambda **_kw: _FakeClient(_signers_events_handler(signers, events)))

        result = clicksign_service.list_signers("env-id")
        assert result is not None
        assert len(result) == 2
        by_email = {s["email"]: s for s in result}
        assert by_email["ti_lucas@hsm.com.br"]["status"] == "signed"
        assert by_email["ti_lucas@hsm.com.br"]["signed_at"] == "2026-05-27T15:09:47.224-03:00"
        assert by_email["josiane@hsm.com.br"]["status"] == "pending"
        assert by_email["josiane@hsm.com.br"]["signed_at"] is None

    def test_signature_started_nao_conta_como_assinado(self, monkeypatch):
        """Garante que abrir o documento (signature_started) nao marca como assinado."""
        import httpx

        from app.services import clicksign_service

        signers = {"data": [_signer_obj("k1", "Ana", "ana@ex.com")], "links": {"next": None}}
        events = {"data": [_started_event("k1", "ana@ex.com")], "links": {"next": None}}
        monkeypatch.setattr(httpx, "Client", lambda **_kw: _FakeClient(_signers_events_handler(signers, events)))

        result = clicksign_service.list_signers("env-id")
        assert result == [
            {"signer_id": "k1", "nome": "Ana", "email": "ana@ex.com", "status": "pending", "signed_at": None}
        ]

    def test_fallback_por_email_quando_key_diverge(self, monkeypatch):
        """Robustez: se o signer.key do evento divergir do id do signer, casa por
        email normalizado (case-insensitive)."""
        import httpx

        from app.services import clicksign_service

        signers = {"data": [_signer_obj("ID-DIFERENTE", "Bruno", "Bruno@Ex.com")], "links": {"next": None}}
        events = {
            "data": [_sign_event("KEY-OUTRA", "bruno@ex.com", "Bruno", "2026-05-20T10:00:00.000-03:00")],
            "links": {"next": None},
        }
        monkeypatch.setattr(httpx, "Client", lambda **_kw: _FakeClient(_signers_events_handler(signers, events)))

        result = clicksign_service.list_signers("env-id")
        assert result is not None
        assert result[0]["status"] == "signed"
        assert result[0]["signed_at"] == "2026-05-20T10:00:00.000-03:00"

    def test_evento_sign_sem_created_ainda_conta_como_assinado(self, monkeypatch):
        """Robustez (code-review): a presenca do evento `sign` marca assinado mesmo
        se `created` vier ausente; o status nao deve cair pra pending por isso."""
        import httpx

        from app.services import clicksign_service

        signers = {"data": [_signer_obj("k1", "Ana", "ana@ex.com")], "links": {"next": None}}
        events = {
            "data": [
                {
                    "id": "ev1",
                    "type": "events",
                    "attributes": {"name": "sign", "data": {"signer": {"key": "k1", "email": "ana@ex.com"}}},
                    # sem `created`
                }
            ],
            "links": {"next": None},
        }
        monkeypatch.setattr(httpx, "Client", lambda **_kw: _FakeClient(_signers_events_handler(signers, events)))

        result = clicksign_service.list_signers("env-id")
        assert result is not None
        assert result[0]["status"] == "signed"
        assert result[0]["signed_at"] is None

    def test_eventos_indisponiveis_retorna_none(self, monkeypatch):
        """Sem os eventos nao da pra saber quem assinou: melhor 503 (caller) do que
        afirmar 0/N silenciosamente. /signers ok mas /events 500 -> None."""
        import httpx

        from app.services import clicksign_service

        def _handler(method, url, _json):
            if "/events" in url:
                return _FakeResponse(500, {"errors": []}, text="boom")
            return _FakeResponse(200, {"data": [_signer_obj("k1", "Ana", "ana@ex.com")], "links": {"next": None}})

        monkeypatch.setattr(httpx, "Client", lambda **_kw: _FakeClient(_handler))
        assert clicksign_service.list_signers("env-id") is None

    def test_segue_paginacao_dos_signers(self, monkeypatch):
        """Esconde paginacao: junta signers de todas as paginas (hoje lia so a 1a)."""
        import httpx

        from app.services import clicksign_service

        def _handler(method, url, _json):
            if "/events" in url:
                return _FakeResponse(200, {"data": [], "links": {"next": None}})
            if "page%5Bnumber%5D=2" in url or "page[number]=2" in url:
                return _FakeResponse(200, {"data": [_signer_obj("k2", "Bia", "bia@ex.com")], "links": {"next": None}})
            if "/signers" in url:
                return _FakeResponse(
                    200,
                    {
                        "data": [_signer_obj("k1", "Ana", "ana@ex.com")],
                        "links": {"next": "https://app.clicksign.com/api/v3/envelopes/env-id/signers?page[number]=2"},
                    },
                )
            raise AssertionError(f"URL inesperada: {url}")

        monkeypatch.setattr(httpx, "Client", lambda **_kw: _FakeClient(_handler))
        result = clicksign_service.list_signers("env-id")
        assert result is not None
        assert {s["signer_id"] for s in result} == {"k1", "k2"}

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


class TestListEnvelopeEventsService:
    def test_sucesso_segue_paginacao(self, monkeypatch):
        import httpx

        from app.services import clicksign_service

        def _handler(method, url, _json):
            assert method == "GET"
            if "page%5Bnumber%5D=2" in url or "page[number]=2" in url:
                return _FakeResponse(200, {"data": [{"id": "e2"}], "links": {"next": None}})
            return _FakeResponse(
                200,
                {
                    "data": [{"id": "e1"}],
                    "links": {"next": "https://app.clicksign.com/api/v3/envelopes/env-id/events?page[number]=2"},
                },
            )

        monkeypatch.setattr(httpx, "Client", lambda **_kw: _FakeClient(_handler))
        events = clicksign_service.list_envelope_events("env-id")
        assert events is not None
        assert [e["id"] for e in events] == ["e1", "e2"]

    def test_404_retorna_none(self, monkeypatch):
        import httpx

        from app.services import clicksign_service

        monkeypatch.setattr(
            httpx,
            "Client",
            lambda **_kw: _FakeClient(lambda *_a: _FakeResponse(404, {"errors": []}, text="not found")),
        )
        assert clicksign_service.list_envelope_events("env-id") is None

    def test_timeout_retorna_none(self, monkeypatch):
        import httpx

        from app.services import clicksign_service

        def _handler(*_a):
            raise httpx.TimeoutException("slow")

        monkeypatch.setattr(httpx, "Client", lambda **_kw: _FakeClient(_handler))
        assert clicksign_service.list_envelope_events("env-id") is None


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


# ═══════════════════════════════════════════════════════════════════════════
# Self-heal: recuperacao automatica do envelope_id faltante (Atas pre-039)
# ═══════════════════════════════════════════════════════════════════════════


class TestSelfHealStatus:
    def _sb_legacy(self) -> _SupabaseMock:
        """Reuniao AGUARDANDO_ASSINATURA com document_id mas SEM envelope_id (pre-039)."""
        return _SupabaseMock(
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
                    "envelope_key_clicksign": "doc-123",
                    "envelope_id_clicksign": None,
                }
            ],
        )

    def test_recupera_envelope_faltante_e_exibe_status_real(self, make_client, monkeypatch):
        """Facilitador abre Ata pre-039: o sistema localiza o Envelope na conta,
        grava o envelope_id e passa a exibir o status real de cada Signatario."""
        sb = self._sb_legacy()
        from app.services import clicksign_service

        monkeypatch.setattr(
            clicksign_service,
            "find_envelope_id",
            lambda name, document_id: "env-rec" if document_id == "doc-123" else None,
            raising=False,
        )
        monkeypatch.setattr(
            clicksign_service,
            "list_signers",
            lambda env: (
                [
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
                ]
                if env == "env-rec"
                else None
            ),
        )

        client = make_client(sb)
        r = client.get("/api/reunioes/R1/signatarios/status")

        assert r.status_code == 200
        body = r.json()
        assert body["envelope_id"] == "env-rec"
        assert body["total"] == 2
        assert body["assinaram"] == 1
        assert body["signatarios"][0]["status"] == "signed"
        assert "legacy_warning" not in body  # faixa amarela some
        # persistido no banco — dali em diante o status fica disponivel
        assert sb.reunioes[0]["envelope_id_clicksign"] == "env-rec"

    def test_nao_revarre_quando_ja_tem_envelope_id(self, make_client, monkeypatch):
        """Idempotencia (crit 4): Ata que ja tem o envelope_id segue inalterada,
        sem nova consulta de listagem na conta ClickSign."""
        sb = _SupabaseMock(
            participantes=[_participante("P1", "Pedro Rezende", "pedro@hsm.com")],
            reuniao_participantes=[{"id_reuniao": "R1", "participante_id": "P1"}],
            reunioes=[
                {
                    "id_reuniao": "R1",
                    "status_ata": "AGUARDANDO_ASSINATURA",
                    "envelope_key_clicksign": "doc-123",
                    "envelope_id_clicksign": "env-existente",
                }
            ],
        )
        from app.services import clicksign_service

        def _boom(*_a, **_kw):
            raise AssertionError("find_envelope_id nao deveria ser chamado quando ja ha envelope_id")

        monkeypatch.setattr(clicksign_service, "find_envelope_id", _boom)
        monkeypatch.setattr(
            clicksign_service,
            "list_signers",
            lambda env: (
                [
                    {
                        "signer_id": "s1",
                        "nome": "Pedro Rezende",
                        "email": "pedro@hsm.com",
                        "status": "pending",
                        "signed_at": None,
                    }
                ]
                if env == "env-existente"
                else None
            ),
        )

        client = make_client(sb)
        r = client.get("/api/reunioes/R1/signatarios/status")
        assert r.status_code == 200
        assert r.json()["envelope_id"] == "env-existente"

    def test_cooldown_evita_revarrer_na_falha_persistente(self, make_client, monkeypatch):
        """Anti-sobrecarga (crit 6): em falha persistente, o cooldown evita
        re-varrer a conta a cada atualizacao automatica (polling 30s)."""
        sb = self._sb_legacy()  # envelope_id=None, envelope_key=doc-123
        from app.services import clicksign_service

        calls = {"n": 0}

        def _find(_name, _doc):
            calls["n"] += 1
            return None  # nao recupera (falha persistente)

        monkeypatch.setattr(clicksign_service, "find_envelope_id", _find)

        client = make_client(sb)
        r1 = client.get("/api/reunioes/R1/signatarios/status")
        r2 = client.get("/api/reunioes/R1/signatarios/status")

        assert r1.status_code == 200 and r2.status_code == 200
        assert "legacy_warning" in r1.json()  # permanece degradado
        assert "legacy_warning" in r2.json()
        assert calls["n"] == 1  # a 2a chamada nao re-varreu a conta (cooldown)

    def test_secretaria_barrada_antes_do_self_heal(self, make_client, monkeypatch):
        """Crit 7: a Secretaria segue sem acesso — o guard vem antes do self-heal,
        que nem chega a consultar a conta ClickSign."""
        from app.services import clicksign_service

        def _boom(*_a, **_kw):
            raise AssertionError("self-heal nao deve rodar para Secretaria")

        monkeypatch.setattr(clicksign_service, "find_envelope_id", _boom)
        client = make_client(self._sb_legacy(), is_secretaria_override=True)
        r = client.get("/api/reunioes/R1/signatarios/status")
        assert r.status_code == 403

    def test_fallback_aviso_humano_e_link_quando_nome_nao_casavel(self, make_client, monkeypatch):
        """Issue #21: quando o self-heal nao casa o nome (Envelope cancelado/expirado
        ou Ata antiga fora do padrao), o card mostra um aviso HUMANO + link pro painel
        ClickSign, sem o jargao tecnico 'migration 039'. Signatarios seguem listados."""
        from app.config import settings
        from app.services import clicksign_service

        monkeypatch.setattr(clicksign_service, "find_envelope_id", lambda *_a, **_kw: None)
        client = make_client(self._sb_legacy())  # envelope_id=None
        r = client.get("/api/reunioes/R1/signatarios/status")

        assert r.status_code == 200
        body = r.json()
        # aviso humano, sem o termo tecnico
        assert "migration 039" not in body["legacy_warning"]
        # link pro painel ClickSign
        assert body["clicksign_url"] == settings.clicksign_base_url
        # signatarios seguem listados como pendentes
        assert body["total"] == 2
        assert all(s["status"] == "pending" for s in body["signatarios"])


class TestFindEnvelopeIdService:
    def test_desambigua_reenvio_pelo_document_id(self, monkeypatch):
        """Reenvio: dois Envelopes com o mesmo nome; escolhe o que contem o documento certo."""
        import httpx

        from app.services import clicksign_service

        def _handler(method, url, _json):
            assert method == "GET"
            if url.endswith("/envelopes"):
                return _FakeResponse(
                    200,
                    {
                        "data": [
                            {"id": "env-A", "type": "envelopes", "attributes": {"name": "Ata de Reunião - R1"}},
                            {"id": "env-B", "type": "envelopes", "attributes": {"name": "Ata de Reunião - R1"}},
                        ],
                        "links": {"next": None},
                    },
                )
            if url.endswith("/envelopes/env-A/documents"):
                return _FakeResponse(200, {"data": [{"id": "doc-OUTRO", "type": "documents", "attributes": {}}]})
            if url.endswith("/envelopes/env-B/documents"):
                return _FakeResponse(200, {"data": [{"id": "doc-ALVO", "type": "documents", "attributes": {}}]})
            raise AssertionError(f"URL inesperada: {url}")

        monkeypatch.setattr(httpx, "Client", lambda **_kw: _FakeClient(_handler))
        env_id = clicksign_service.find_envelope_id("Ata de Reunião - R1", "doc-ALVO")
        assert env_id == "env-B"

    def test_erro_http_na_listagem_retorna_none(self, monkeypatch):
        """Falha na conta ClickSign nao deve propagar — caller aplica cooldown."""
        import httpx

        from app.services import clicksign_service

        monkeypatch.setattr(
            httpx,
            "Client",
            lambda **_kw: _FakeClient(lambda *_a: _FakeResponse(500, {"errors": []}, text="boom")),
        )
        assert clicksign_service.find_envelope_id("Ata de Reunião - R1", "doc-x") is None

    def test_timeout_na_listagem_retorna_none(self, monkeypatch):
        import httpx

        from app.services import clicksign_service

        def _handler(*_a):
            raise httpx.TimeoutException("slow")

        monkeypatch.setattr(httpx, "Client", lambda **_kw: _FakeClient(_handler))
        assert clicksign_service.find_envelope_id("Ata de Reunião - R1", "doc-x") is None

    def test_segue_paginacao_ate_achar_o_envelope(self, monkeypatch):
        """Esconde paginacao: segue links.next ate localizar o Envelope certo."""
        import httpx

        from app.services import clicksign_service

        def _handler(method, url, _json):
            assert method == "GET"
            if "page[number]=2" in url:
                return _FakeResponse(
                    200,
                    {
                        "data": [
                            {"id": "env-alvo", "type": "envelopes", "attributes": {"name": "Ata de Reunião - R1"}}
                        ],
                        "links": {"next": None},
                    },
                )
            if url.endswith("/envelopes"):
                return _FakeResponse(
                    200,
                    {
                        "data": [
                            {"id": "env-outro", "type": "envelopes", "attributes": {"name": "Ata de Reunião - OUTRA"}}
                        ],
                        "links": {"next": "https://app.clicksign.com/api/v3/envelopes?page[number]=2"},
                    },
                )
            if url.endswith("/envelopes/env-alvo/documents"):
                return _FakeResponse(200, {"data": [{"id": "doc-ALVO", "type": "documents", "attributes": {}}]})
            raise AssertionError(f"URL inesperada: {url}")

        monkeypatch.setattr(httpx, "Client", lambda **_kw: _FakeClient(_handler))
        env_id = clicksign_service.find_envelope_id("Ata de Reunião - R1", "doc-ALVO")
        assert env_id == "env-alvo"

    def test_nao_casa_quando_nenhum_documento_bate(self, monkeypatch):
        """Seguranca: se o document_id nao bate em nenhum candidato, devolve None —
        nunca escolhe um Envelope errado."""
        import httpx

        from app.services import clicksign_service

        def _handler(method, url, _json):
            if url.endswith("/envelopes"):
                return _FakeResponse(
                    200,
                    {
                        "data": [{"id": "env-X", "type": "envelopes", "attributes": {"name": "Ata de Reunião - R1"}}],
                        "links": {"next": None},
                    },
                )
            if url.endswith("/envelopes/env-X/documents"):
                return _FakeResponse(200, {"data": [{"id": "doc-DIFERENTE", "type": "documents", "attributes": {}}]})
            raise AssertionError(f"URL inesperada: {url}")

        monkeypatch.setattr(httpx, "Client", lambda **_kw: _FakeClient(_handler))
        assert clicksign_service.find_envelope_id("Ata de Reunião - R1", "doc-ALVO") is None

    def test_ignora_candidato_inacessivel_e_acha_o_valido(self, monkeypatch):
        """Reenvio: se um Envelope candidato esta inacessivel (ex: arquivado → 404),
        a busca ignora esse candidato e segue avaliando os demais."""
        import httpx

        from app.services import clicksign_service

        def _handler(method, url, _json):
            if url.endswith("/envelopes"):
                return _FakeResponse(
                    200,
                    {
                        "data": [
                            {"id": "env-A", "type": "envelopes", "attributes": {"name": "Ata de Reunião - R1"}},
                            {"id": "env-B", "type": "envelopes", "attributes": {"name": "Ata de Reunião - R1"}},
                        ],
                        "links": {"next": None},
                    },
                )
            if url.endswith("/envelopes/env-A/documents"):
                return _FakeResponse(404, {"errors": []}, text="not found")  # candidato arquivado
            if url.endswith("/envelopes/env-B/documents"):
                return _FakeResponse(200, {"data": [{"id": "doc-ALVO", "type": "documents", "attributes": {}}]})
            raise AssertionError(f"URL inesperada: {url}")

        monkeypatch.setattr(httpx, "Client", lambda **_kw: _FakeClient(_handler))
        assert clicksign_service.find_envelope_id("Ata de Reunião - R1", "doc-ALVO") == "env-B"


class TestSelfHealLembrar:
    def test_lembrete_se_autocura_antes_de_recusar(self, make_client, monkeypatch):
        """Crit 5: o endpoint de lembrete recupera o envelope_id faltante antes de
        recusar — se auto-cura no primeiro acesso e envia o lembrete."""
        sb = _SupabaseMock(
            reunioes=[
                {
                    "id_reuniao": "R1",
                    "status_ata": "AGUARDANDO_ASSINATURA",
                    "envelope_id_clicksign": None,
                    "envelope_key_clicksign": "doc-123",
                    "tipo": "Diretoria",
                    "data": "2026-05-18",
                }
            ],
        )
        from app.services import clicksign_service

        monkeypatch.setattr(
            clicksign_service,
            "find_envelope_id",
            lambda name, doc: "env-rec" if doc == "doc-123" else None,
        )
        captured: list[tuple] = []

        def _remind(env, sid, message=None):
            captured.append((env, sid, message))
            return True

        monkeypatch.setattr(clicksign_service, "remind_signer", _remind)

        client = make_client(sb)
        r = client.post("/api/reunioes/R1/signatarios/sig-x/lembrar")

        assert r.status_code == 200
        assert len(captured) == 1
        assert captured[0][0] == "env-rec"  # usou o Envelope recuperado
        assert sb.reunioes[0]["envelope_id_clicksign"] == "env-rec"  # gravou (idempotente)
