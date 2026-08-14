"""Envio duplicado de Envelope no `POST /reunioes/{id}/aprovar` (issue #273).

O /aprovar responde na hora e agenda `start_signature_flow` em background; o
status so vira AGUARDANDO_ASSINATURA no fim do fluxo. Antes do fix, a unica
guarda era o status: dois cliques na janela do background passavam pela guarda
e criavam DOIS Envelopes ativos na ClickSign.

Contrato coberto aqui:
  1. O primeiro POST grava a marca de envio em andamento ANTES de agendar o
     fluxo em background.
  2. Segundo POST com envio em andamento responde 400 e nao agenda nada.
  3. Marca velha (processo morto no meio) nao bloqueia: retry permitido.
  4. Sucesso e falha pre-ativacao limpam a marca (retry apos falha funciona);
     falha pos-ativacao ("finalizar") MANTEM a marca (Envelope ja ativo).

Padrao de mock copiado de test_aprovar_sem_assinatura.py / test_falha_envio_assinatura.py.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.dependencies import (  # noqa: E402
    get_current_user,
    get_supabase_client,
    require_acesso_reunioes,
)
from app.routers import reunioes as reunioes_router  # noqa: E402

# ─── Mock Supabase (fluente minimo: select/update + eq) ─────────────────────


@dataclass
class _Result:
    data: Any


class _TableQuery:
    def __init__(self, rows_ref: list):
        self._rows = rows_ref
        self._op = "select"
        self._payload: Any = None
        self._filters: list[tuple[str, Any]] = []
        self._or: str | None = None

    def select(self, *_a, **_kw):
        self._op = "select"
        return self

    def update(self, payload):
        self._op = "update"
        self._payload = payload
        return self

    def eq(self, col, value):
        self._filters.append((col, value))
        return self

    def or_(self, filters: str):
        self._or = filters
        return self

    def order(self, *_a, **_kw):
        return self

    def _passa_or(self, r: dict) -> bool:
        """Avalia o filtro .or_ do PostgREST: 'col.is.null,col.lt.<valor>'.

        Timestamps ISO com o mesmo offset comparam corretamente como string.
        """
        if self._or is None:
            return True
        for cond in self._or.split(","):
            col, op, valor = cond.split(".", 2)
            atual = r.get(col)
            if op == "is" and valor == "null" and atual is None:
                return True
            if op == "lt" and atual is not None and str(atual) < valor:
                return True
        return False

    def execute(self):
        matched = [r for r in self._rows if all(r.get(c) == v for c, v in self._filters) and self._passa_or(r)]
        if self._op == "update":
            for r in matched:
                r.update(self._payload or {})
        return _Result(data=list(matched))


@dataclass
class _SupabaseMock:
    reunioes: list = field(default_factory=list)
    participantes: list = field(default_factory=list)
    reuniao_participantes: list = field(default_factory=list)

    def table(self, name: str):
        rows = getattr(self, name, None)
        if rows is None:
            raise AssertionError(f"Tabela inesperada: {name}")
        return _TableQuery(rows)


CURRENT_USER = {"id": "auth-uid-1", "email": "diretor@hospital.com"}
FACILITADOR = {"id": "P_DIR", "email": "diretor@hospital.com", "access_profile": "regular"}


def _reuniao_aguardando(**extra) -> dict:
    return {
        "id_reuniao": "R1",
        "status_ata": "AGUARDANDO_VALIDACAO",
        "url_pdf_preliminar": "https://x/preliminar.pdf",
        "tipo": "Gerencial",
        "objetivo": "Acompanhamento",
        "falha_envio_assinatura": None,
        "envio_assinatura_iniciado_em": None,
        **extra,
    }


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """O storage do slowapi e global por IP e acumula 429 entre arquivos."""
    from app.limiter import limiter

    limiter._storage.reset()
    yield


@pytest.fixture
def make_client(monkeypatch):
    """TestClient com auth/papel plugados e start_signature_flow espionado.

    O spy registra quantas vezes o fluxo foi agendado e o valor da marca
    `envio_assinatura_iniciado_em` NO MOMENTO do agendamento (para provar que a
    marca e gravada antes do background task).
    """

    def _factory(supabase: _SupabaseMock, spy: dict) -> TestClient:
        from slowapi import _rate_limit_exceeded_handler
        from slowapi.errors import RateLimitExceeded

        from app.limiter import limiter

        app = FastAPI()
        app.state.limiter = limiter
        app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
        app.include_router(reunioes_router.router, prefix="/api")

        app.dependency_overrides[get_current_user] = lambda: CURRENT_USER
        app.dependency_overrides[get_supabase_client] = lambda: supabase
        app.dependency_overrides[require_acesso_reunioes] = lambda: None

        async def _fake_get_participante(*_a, **_kw):
            return dict(FACILITADOR)

        async def _fake_allowed(*_a, **_kw):
            return None

        monkeypatch.setattr(reunioes_router, "get_participante_for_user", _fake_get_participante)
        monkeypatch.setattr(reunioes_router, "get_allowed_reuniao_ids", _fake_allowed)
        monkeypatch.setattr(reunioes_router, "is_secretaria", lambda _me: False)

        from app.services import clicksign_service

        spy.setdefault("chamadas", 0)

        def _spy(sb, id_reuniao, reuniao):
            spy["chamadas"] += 1
            spy["marca_no_agendamento"] = sb.reunioes[0].get("envio_assinatura_iniciado_em")

        monkeypatch.setattr(clicksign_service, "start_signature_flow", _spy)

        return TestClient(app)

    return _factory


# ═══════════════════════════════════════════════════════════════════════════
# 1. Primeiro POST: marca gravada antes de agendar o fluxo
# ═══════════════════════════════════════════════════════════════════════════


def test_primeiro_envio_grava_marca_antes_de_agendar_o_fluxo(make_client):
    spy: dict = {}
    sb = _SupabaseMock(reunioes=[_reuniao_aguardando()])
    client = make_client(sb, spy)

    resp = client.post("/api/reunioes/R1/aprovar")

    assert resp.status_code == 200
    assert spy["chamadas"] == 1
    assert spy["marca_no_agendamento"], (
        "A marca de envio em andamento deve estar gravada ANTES do background task rodar"
    )
    assert sb.reunioes[0]["envio_assinatura_iniciado_em"], "A marca deve persistir na Reuniao"


# ═══════════════════════════════════════════════════════════════════════════
# 2. Segundo POST com envio em andamento: 400, nada agendado
# ═══════════════════════════════════════════════════════════════════════════


def test_segundo_envio_em_andamento_responde_400_e_nao_agenda(make_client):
    spy: dict = {}
    sb = _SupabaseMock(reunioes=[_reuniao_aguardando()])
    client = make_client(sb, spy)

    assert client.post("/api/reunioes/R1/aprovar").status_code == 200
    resp = client.post("/api/reunioes/R1/aprovar")

    assert resp.status_code == 400
    assert "andamento" in resp.json()["detail"].lower()
    assert spy["chamadas"] == 1, "O segundo POST nao pode agendar outro fluxo ClickSign"


# ═══════════════════════════════════════════════════════════════════════════
# 3. Marca velha (processo morto no meio) nao bloqueia o retry
# ═══════════════════════════════════════════════════════════════════════════


def test_marca_velha_nao_bloqueia_novo_envio(make_client):
    spy: dict = {}
    antiga = (datetime.now(UTC) - timedelta(minutes=30)).isoformat()
    sb = _SupabaseMock(reunioes=[_reuniao_aguardando(envio_assinatura_iniciado_em=antiga)])
    client = make_client(sb, spy)

    resp = client.post("/api/reunioes/R1/aprovar")

    assert resp.status_code == 200
    assert spy["chamadas"] == 1
    assert sb.reunioes[0]["envio_assinatura_iniciado_em"] != antiga, "A marca deve ser renovada"


# ═══════════════════════════════════════════════════════════════════════════
# 4. O fluxo limpa a marca em sucesso e em falha (seam do servico)
# ═══════════════════════════════════════════════════════════════════════════


def _supabase_fluxo(marca: str) -> _SupabaseMock:
    return _SupabaseMock(
        participantes=[{"id": "P001", "nome_completo": "Caroline Soares", "email": "caroline@hsm.com"}],
        reuniao_participantes=[{"id_reuniao": "R1", "participante_id": "P001", "sequence_assinatura": 1}],
        reunioes=[
            _reuniao_aguardando(envio_assinatura_iniciado_em=marca),
        ],
    )


def _patch_fluxo_feliz(monkeypatch):
    from app.services import clicksign_service, storage

    monkeypatch.setattr(storage, "download_file", lambda *_a, **_kw: b"PDF_BYTES")
    monkeypatch.setattr(clicksign_service, "create_envelope", lambda _name: "env-id")
    monkeypatch.setattr(clicksign_service, "add_document", lambda *_a, **_kw: "doc-id")
    monkeypatch.setattr(clicksign_service, "add_signer", lambda *_a, **_kw: "signer-id")
    monkeypatch.setattr(clicksign_service, "create_qualification_requirement", lambda *_a, **_kw: "qual-id")
    monkeypatch.setattr(clicksign_service, "create_auth_requirement", lambda *_a, **_kw: "auth-id")
    monkeypatch.setattr(clicksign_service, "activate_envelope", lambda _env: True)
    monkeypatch.setattr(clicksign_service, "notify_signers", lambda _env: True)


def test_sucesso_do_fluxo_limpa_a_marca(monkeypatch):
    from app.services import clicksign_service

    _patch_fluxo_feliz(monkeypatch)
    sb = _supabase_fluxo(marca=datetime.now(UTC).isoformat())

    clicksign_service.start_signature_flow(sb, "R1", {"id_reuniao": "R1"})

    reuniao = sb.reunioes[0]
    assert reuniao["status_ata"] == "AGUARDANDO_ASSINATURA"
    assert reuniao["envio_assinatura_iniciado_em"] is None, "Sucesso deve limpar a marca de envio em andamento"


def test_falha_pos_ativacao_finalizar_mantem_a_marca(monkeypatch):
    """Pos-ativacao ("finalizar") o Envelope ja esta ativo, com emails
    possivelmente enviados: a marca fica, e o reenvio imediato e bloqueado
    (um novo envio criaria um segundo Envelope ativo)."""
    from app.services import clicksign_service

    _patch_fluxo_feliz(monkeypatch)
    marca = datetime.now(UTC).isoformat()
    sb = _supabase_fluxo(marca=marca)

    class _TableExplodeNoSucesso(_TableQuery):
        def update(self, payload):
            if (payload or {}).get("status_ata") == "AGUARDANDO_ASSINATURA":
                raise RuntimeError("update final falhou")
            return super().update(payload)

    class _SupabaseExplodeNoSucesso:
        def table(self, name):
            return _TableExplodeNoSucesso(getattr(sb, name))

    clicksign_service.start_signature_flow(_SupabaseExplodeNoSucesso(), "R1", {"id_reuniao": "R1"})

    reuniao = sb.reunioes[0]
    assert reuniao["falha_envio_assinatura"]["passo"] == "finalizar"
    assert reuniao["envio_assinatura_iniciado_em"] == marca, (
        "Falha pos-ativacao NAO limpa a marca: reenvio imediato criaria um segundo Envelope"
    )


def test_falha_do_fluxo_limpa_a_marca_e_permite_retry(monkeypatch):
    from app.services import clicksign_service

    _patch_fluxo_feliz(monkeypatch)
    monkeypatch.setattr(clicksign_service, "create_envelope", lambda _name: None)
    sb = _supabase_fluxo(marca=datetime.now(UTC).isoformat())

    clicksign_service.start_signature_flow(sb, "R1", {"id_reuniao": "R1"})

    reuniao = sb.reunioes[0]
    assert reuniao["status_ata"] == "AGUARDANDO_VALIDACAO"
    assert reuniao["falha_envio_assinatura"]["passo"] == "criar_envelope"
    assert reuniao["envio_assinatura_iniciado_em"] is None, "Falha deve limpar a marca para o retry manual funcionar"


def test_retry_apos_falha_funciona_ponta_a_ponta(make_client, monkeypatch):
    """POST -> falha do fluxo (limpa a marca) -> novo POST responde 200."""
    from app.services import clicksign_service

    spy: dict = {}
    sb = _SupabaseMock(reunioes=[_reuniao_aguardando()])
    client = make_client(sb, spy)

    assert client.post("/api/reunioes/R1/aprovar").status_code == 200

    # O fluxo em background falhou: o registro de falha real limpa a marca.
    clicksign_service._registrar_falha_envio(sb, "R1", "criar_envelope", "HTTP 500")

    resp = client.post("/api/reunioes/R1/aprovar")
    assert resp.status_code == 200, "Apos falha registrada, o reenvio deve ser aceito"
    assert spy["chamadas"] == 2
    assert sb.reunioes[0]["falha_envio_assinatura"] is None, (
        "Novo envio limpa a falha anterior: 'em andamento' = marca setada e falha nula "
        "(o polling da tela usa falha nova como sinal de erro do envio atual)"
    )
