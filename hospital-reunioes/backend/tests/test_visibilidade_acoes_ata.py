"""Testes de visibilidade das ações da Ata (issue #194).

Bug: os endpoints que mutam a Ata (aprovar, aprovar sem assinatura, corrigir,
chat de correção, resolver participantes, pular resolução, reprocessar e
anexar transcrição) checavam status e bloqueavam Secretária, mas não checavam
se a Reunião é visível ao Facilitador chamador. Um Facilitador que conhecesse
o id de uma Reunião alheia conseguia, por exemplo, aprová-la.

Regra (mesmo gate da Ata Guiada / patch_quadro_atribuicao): Facilitador só age
nas Reuniões que enxerga (participa ou criou); Reunião invisível responde 404
pra não vazar existência. Secretária segue bloqueada com 403 antes do gate.

Padrão de mock copiado de `test_aprovar_sem_assinatura.py`.
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
    """Mock fluente: select/insert/update/upsert/delete + eq/in_/limit."""

    def __init__(self, rows_ref: list):
        self._rows = rows_ref
        self._op: str = "select"
        self._payload: Any = None
        self._filters: list[tuple[str, Any]] = []
        self._in_filters: list[tuple[str, list]] = []
        self._limit: int | None = None

    def select(self, *_a, **_kw):
        self._op = "select"
        return self

    def insert(self, payload):
        self._op = "insert"
        self._payload = payload
        return self

    def upsert(self, payload, *, on_conflict: str | None = None):
        self._op = "insert"
        self._payload = payload
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

    def limit(self, n):
        self._limit = n
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
        if self._op == "insert":
            items = self._payload if isinstance(self._payload, list) else [self._payload]
            for it in items:
                self._rows.append(dict(it))
            return _Result(data=[dict(it) for it in items])

        matched = [r for r in self._rows if self._matches(r)]
        if self._limit is not None:
            matched = matched[: self._limit]

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
    reunioes: list = field(default_factory=list)
    reuniao_participantes: list = field(default_factory=list)
    pendencias: list = field(default_factory=list)
    audit_log: list = field(default_factory=list)

    def table(self, name: str):
        tables = {
            "participantes": self.participantes,
            "reunioes": self.reunioes,
            "reuniao_participantes": self.reuniao_participantes,
            "pendencias": self.pendencias,
            "audit_log": self.audit_log,
        }
        if name not in tables:
            raise AssertionError(f"Tabela inesperada: {name}")
        return _TableQuery(tables[name])


# ─── App fixture ─────────────────────────────────────────────────────────────


CURRENT_USER = {"id": "auth-uid-1", "email": "facilitador.b@hospital.com"}
FACILITADOR = {"id": "P_FAC_B", "email": "facilitador.b@hospital.com", "access_profile": "regular"}


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """O storage do slowapi é global por IP e acumula entre arquivos de teste."""
    from app.limiter import limiter

    limiter._storage.reset()
    yield
    limiter._storage.reset()


@pytest.fixture
def make_client(monkeypatch):
    """Factory que monta TestClient com supabase mock + auth/papel plugados.

    `allowed` controla o que `get_allowed_reuniao_ids` devolve pro chamador:
    lista de ids visíveis (Facilitador comum) ou None (sem restrição).
    Todos os side effects pesados (ClickSign, pipeline, IA) são neutralizados.
    """

    def _factory(
        supabase: _SupabaseMock,
        *,
        allowed: list[str] | None,
        is_secretaria_override: bool = False,
        spies: dict | None = None,
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
            return dict(FACILITADOR)

        async def _fake_allowed(*_a, **_kw):
            return allowed

        monkeypatch.setattr(reunioes_router, "get_participante_for_user", _fake_get_participante)
        monkeypatch.setattr(reunioes_router, "get_allowed_reuniao_ids", _fake_allowed)
        monkeypatch.setattr(reunioes_router, "is_secretaria", lambda _me: is_secretaria_override)

        spies = spies if spies is not None else {}

        def _spy(nome):
            def _fn(*_a, **_kw):
                spies[nome] = True

            return _fn

        from app.pipeline import orchestrator
        from app.services import ai_processor, clicksign_service, pendencia_service, storage

        monkeypatch.setattr(clicksign_service, "start_signature_flow", _spy("clicksign"))
        monkeypatch.setattr(orchestrator, "run_pipeline", _spy("run_pipeline"))
        monkeypatch.setattr(orchestrator, "run_correction_pipeline", _spy("run_correction_pipeline"))
        monkeypatch.setattr(orchestrator, "resume_pipeline_after_resolution", _spy("resume_pipeline"))
        monkeypatch.setattr(pendencia_service, "liberar_pendencias", lambda *_a, **_kw: 0)
        monkeypatch.setattr(ai_processor, "chat_correcao", lambda *_a, **_kw: {"reply": "ok"})
        monkeypatch.setattr(storage, "download_file", lambda *_a, **_kw: b"transcricao")
        monkeypatch.setattr(reunioes_router.audit, "log_action", lambda *_a, **_kw: None)

        return TestClient(app)

    return _factory


def _reuniao(status: str) -> dict:
    return {
        "id_reuniao": "R1",
        "status_ata": status,
        "url_pdf_preliminar": "https://x/preliminar.pdf",
        "tipo": "Gerencial",
        "objetivo": "Acompanhamento",
        "ciclo_correcao": 0,
        "participantes_nao_reconhecidos": [],
        "json_ata": {"resumo_executivo": "Resumo", "quadro_atribuicoes": []},
    }


# Chamada de cada endpoint mutador: (nome, status exigido, função que dispara).
_ENDPOINTS = [
    (
        "aprovar",
        "AGUARDANDO_VALIDACAO",
        lambda c: c.post("/api/reunioes/R1/aprovar"),
    ),
    (
        "aprovar-sem-assinatura",
        "AGUARDANDO_VALIDACAO",
        lambda c: c.post("/api/reunioes/R1/aprovar-sem-assinatura"),
    ),
    (
        "corrigir",
        "AGUARDANDO_VALIDACAO",
        lambda c: c.post("/api/reunioes/R1/corrigir", json={"texto": "Ajustar a data da próxima reunião"}),
    ),
    (
        "chat-correcao",
        "AGUARDANDO_VALIDACAO",
        lambda c: c.post(
            "/api/reunioes/R1/chat-correcao",
            json={"messages": [{"role": "user", "content": "Corrige o resumo"}]},
        ),
    ),
    (
        "resolver-participantes",
        "AGUARDANDO_RESOLUCAO",
        lambda c: c.post("/api/reunioes/R1/resolver-participantes", json={"resolucoes": []}),
    ),
    (
        "pular-resolucao",
        "AGUARDANDO_RESOLUCAO",
        lambda c: c.post("/api/reunioes/R1/pular-resolucao"),
    ),
    (
        "reprocessar",
        "AGUARDANDO_VALIDACAO",
        lambda c: c.post("/api/reunioes/R1/reprocessar"),
    ),
    (
        "anexar-transcricao",
        "PROGRAMADA",
        lambda c: c.post(
            "/api/reunioes/R1/anexar-transcricao",
            files={"file": ("transcricao.txt", b"Fulano: bom dia a todos", "text/plain")},
        ),
    ),
]

_IDS = [nome for nome, _status, _call in _ENDPOINTS]


# ═══════════════════════════════════════════════════════════════════════════
# Facilitador SEM visibilidade: 404, sem efeito colateral
# ═══════════════════════════════════════════════════════════════════════════


class TestFacilitadorSemVisibilidade:
    @pytest.mark.parametrize("nome, status_exigido, dispara", _ENDPOINTS, ids=_IDS)
    def test_reuniao_alheia_responde_404_sem_mudar_estado(self, make_client, nome, status_exigido, dispara):
        """Facilitador B, que não participa de R1, não age sobre ela: 404 (não
        vaza existência) e nada muda no banco nem nos serviços."""
        spies: dict = {}
        sb = _SupabaseMock(reunioes=[_reuniao(status_exigido)])
        client = make_client(sb, allowed=["OUTRA_REUNIAO"], spies=spies)

        r = dispara(client)

        assert r.status_code == 404, f"{nome}: esperado 404, veio {r.status_code}"
        assert sb.reunioes[0]["status_ata"] == status_exigido, f"{nome}: status mudou"
        assert spies == {}, f"{nome}: side effect disparado ({spies})"


# ═══════════════════════════════════════════════════════════════════════════
# Facilitador participante (dono/participa): fluxo segue sem mudança
# ═══════════════════════════════════════════════════════════════════════════


class TestFacilitadorParticipante:
    @pytest.mark.parametrize("nome, status_exigido, dispara", _ENDPOINTS, ids=_IDS)
    def test_reuniao_visivel_segue_funcionando(self, make_client, nome, status_exigido, dispara):
        """Facilitador que enxerga R1 (participa ou criou) segue agindo normalmente."""
        sb = _SupabaseMock(reunioes=[_reuniao(status_exigido)])
        client = make_client(sb, allowed=["R1"])

        r = dispara(client)

        assert r.status_code == 200, f"{nome}: esperado 200, veio {r.status_code} ({r.text})"


# ═══════════════════════════════════════════════════════════════════════════
# Secretária: gate 403 continua vindo antes da visibilidade
# ═══════════════════════════════════════════════════════════════════════════


class TestSecretaria:
    @pytest.mark.parametrize("nome, status_exigido, dispara", _ENDPOINTS, ids=_IDS)
    def test_secretaria_segue_403(self, make_client, nome, status_exigido, dispara):
        """Secretária tem visão global (allowed=None) mas segue bloqueada com 403
        nos endpoints de Ata: a checagem nova não engole a regra existente."""
        sb = _SupabaseMock(reunioes=[_reuniao(status_exigido)])
        client = make_client(sb, allowed=None, is_secretaria_override=True)

        r = dispara(client)

        assert r.status_code == 403, f"{nome}: esperado 403, veio {r.status_code}"
