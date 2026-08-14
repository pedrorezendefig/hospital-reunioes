"""Modo interno nos endpoints de Reuniao (issue #276, ADR 0030).

Seams: PATCH /reunioes/{id}/quadro-atribuicoes/{index} (edicao parcial: acao
com Pendencia nascida fica travada; acao sem Pendencia segue editavel),
POST /reunioes/{id}/signatarios/{signer_id}/lembrar (bloqueado: nenhuma acao
via ClickSign no modo interno) e GET /reunioes/{id}/signatarios/status
(variante do modo interno: lista local + Registro de Aceites, sem consultar a
ClickSign de um Envelope morto).
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

from app.dependencies import get_current_user, get_supabase_client  # noqa: E402
from app.routers import reunioes as reunioes_router  # noqa: E402

MODO_INTERNO_DESDE = "2026-08-14T12:00:00+00:00"

# ─── Mock Supabase (mesmo estilo de test_signatarios_status) ─────────────────


@dataclass
class _Result:
    data: Any


class _TableQuery:
    def __init__(self, rows_ref: list):
        self._rows = rows_ref
        self._op: str = "select"
        self._payload: Any = None
        self._filters: list[tuple[str, Any]] = []
        self._is_filters: list[tuple[str, Any]] = []

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

    def is_(self, col, value):
        self._is_filters.append((col, None if value in ("null", None) else value))
        return self

    def limit(self, _n):
        return self

    def _matches(self, r: dict) -> bool:
        return all(r.get(c) == v for c, v in self._filters) and all(r.get(c) == v for c, v in self._is_filters)

    def execute(self):
        matched = [r for r in self._rows if self._matches(r)]
        if self._op == "update":
            for r in matched:
                r.update(self._payload or {})
            return _Result(data=list(matched))
        return _Result(data=list(matched))


@dataclass
class _SupabaseMock:
    participantes: list = field(default_factory=list)
    reuniao_participantes: list = field(default_factory=list)
    reunioes: list = field(default_factory=list)
    pendencias: list = field(default_factory=list)
    reuniao_aceites: list = field(default_factory=list)

    def table(self, name: str):
        if name == "participantes":
            return _TableQuery(self.participantes)
        if name == "pendencias":
            return _TableQuery(self.pendencias)
        if name == "reunioes":
            return _TableQuery(self.reunioes)
        if name == "reuniao_aceites":
            return _TableQuery(self.reuniao_aceites)
        if name == "reuniao_participantes":
            hydrated: list[dict] = []
            for rp in self.reuniao_participantes:
                p_match = next((p for p in self.participantes if p["id"] == rp.get("participante_id")), None)
                row = dict(rp)
                if p_match:
                    row["participantes"] = {
                        "id": p_match.get("id"),
                        "nome_completo": p_match.get("nome_completo"),
                        "email": p_match.get("email"),
                        "cargo": p_match.get("cargo"),
                    }
                hydrated.append(row)
            return _TableQuery(hydrated)
        raise AssertionError(f"Tabela inesperada: {name}")


# ─── App fixture ─────────────────────────────────────────────────────────────

CURRENT_USER = {"id": "auth-uid-1", "email": "facilitador@hospital.com"}


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    from app.limiter import limiter

    limiter._storage.reset()
    yield
    limiter._storage.reset()


@pytest.fixture
def make_client(monkeypatch):
    def _factory(supabase: _SupabaseMock, *, is_secretaria_override: bool = False) -> TestClient:
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
            return {"id": "P_FAC", "access_profile": "regular"}

        async def _fake_allowed(*_a, **_kw):
            return None  # sem restricao de visibilidade

        monkeypatch.setattr(reunioes_router, "get_participante_for_user", _fake_get_participante)
        monkeypatch.setattr(reunioes_router, "get_allowed_reuniao_ids", _fake_allowed)
        monkeypatch.setattr(reunioes_router, "is_secretaria", lambda _me: is_secretaria_override)

        return TestClient(app)

    return _factory


def _participante(pid, nome, email):
    return {"id": pid, "nome_completo": nome, "email": email, "cargo": "Cargo"}


def _quadro() -> list[dict]:
    return [
        {"acao": "Revisar protocolo", "responsavel": "Ana Lima", "responsavel_id": "P_ANA", "prazo": "2026-09-01"},
        {"acao": "Comprar insumos", "responsavel": "Bruno Costa", "responsavel_id": "P_BRUNO", "prazo": "2026-09-10"},
    ]


def _sb(*, status_ata="AGUARDANDO_ASSINATURA", modo_interno_desde=MODO_INTERNO_DESDE, pendencias=None, aceites=None):
    return _SupabaseMock(
        participantes=[
            _participante("P_FAC", "Fabio Facilitador", "fabio@hsm.com"),
            _participante("P_ANA", "Ana Lima", "ana@hsm.com"),
            _participante("P_BRUNO", "Bruno Costa", "bruno@hsm.com"),
        ],
        reuniao_participantes=[
            {"id_reuniao": "R1", "participante_id": "P_FAC"},
            {"id_reuniao": "R1", "participante_id": "P_ANA"},
            {"id_reuniao": "R1", "participante_id": "P_BRUNO"},
        ],
        reunioes=[
            {
                "id_reuniao": "R1",
                "status_ata": status_ata,
                "envelope_key_clicksign": "doc-key",
                "envelope_id_clicksign": "env-id-1",
                "modo_interno_desde": modo_interno_desde,
                "json_ata": {"quadro_atribuicoes": _quadro()},
            }
        ],
        pendencias=list(pendencias or []),
        reuniao_aceites=list(aceites or []),
    )


def _pendencia(quadro_pos, responsavel_id="P_ANA"):
    return {
        "id_acao": f"A00{(quadro_pos or 0) + 1}",
        "id_reuniao": "R1",
        "status": "PENDENTE",
        "responsavel_id": responsavel_id,
        "quadro_pos": quadro_pos,
        "deleted_at": None,
    }


def _aceite(pid, email, aceito_em="2026-08-10T10:00:00-03:00"):
    return {
        "id": f"aceite-{pid}",
        "id_reuniao": "R1",
        "participante_id": pid,
        "signer_key": f"sk-{pid}",
        "email": email,
        "origem": "clicksign",
        "aceito_em": aceito_em,
    }


# ═══════════════════════════════════════════════════════════════════════════
# CA: acao com Pendencia travada; acao sem Pendencia segue editavel
# ═══════════════════════════════════════════════════════════════════════════


class TestPatchQuadroNoModoInterno:
    def test_acao_sem_pendencia_segue_editavel(self, make_client):
        sb = _sb(pendencias=[_pendencia(0)])
        client = make_client(sb)

        r = client.patch("/api/reunioes/R1/quadro-atribuicoes/1", json={"responsavel": "Novo Responsavel"})

        assert r.status_code == 200
        item = sb.reunioes[0]["json_ata"]["quadro_atribuicoes"][1]
        assert item["responsavel"] == "Novo Responsavel"
        assert item["editado_manualmente"] is True

    def test_acao_com_pendencia_nascida_fica_travada(self, make_client):
        sb = _sb(pendencias=[_pendencia(0)])
        client = make_client(sb)

        r = client.patch("/api/reunioes/R1/quadro-atribuicoes/0", json={"responsavel": "Outro Nome"})

        assert r.status_code == 409
        assert "travada" in r.json()["detail"].lower()
        item = sb.reunioes[0]["json_ata"]["quadro_atribuicoes"][0]
        assert item["responsavel"] == "Ana Lima"

    def test_edicao_no_modo_interno_redispara_a_coleta(self, make_client, monkeypatch):
        """Reatribuicao no modo interno re-dispara a coleta de aceites (issue
        #277): o novo responsavel ganha link ou liberacao direta."""
        from app.services import aceite_service

        chamadas: list[str] = []
        monkeypatch.setattr(aceite_service, "iniciar_coleta_interna", lambda _sb, rid: chamadas.append(rid))
        sb = _sb(pendencias=[_pendencia(0)])
        client = make_client(sb)

        r = client.patch("/api/reunioes/R1/quadro-atribuicoes/1", json={"responsavel": "Novo Responsavel"})

        assert r.status_code == 200
        assert chamadas == ["R1"]

    def test_edicao_em_validacao_nao_dispara_coleta(self, make_client, monkeypatch):
        from app.services import aceite_service

        chamadas: list[str] = []
        monkeypatch.setattr(aceite_service, "iniciar_coleta_interna", lambda _sb, rid: chamadas.append(rid))
        sb = _sb(status_ata="AGUARDANDO_VALIDACAO", modo_interno_desde=None)
        client = make_client(sb)

        r = client.patch("/api/reunioes/R1/quadro-atribuicoes/0", json={"responsavel": "Novo"})

        assert r.status_code == 200
        assert chamadas == []

    def test_pendencia_legada_sem_quadro_pos_trava_tudo(self, make_client):
        """Liberacao total pre-incremental (sem quadro_pos): nao da para saber
        qual acao corresponde a qual Pendencia, entao todas ficam travadas."""
        sb = _sb(pendencias=[_pendencia(None)])
        client = make_client(sb)

        r = client.patch("/api/reunioes/R1/quadro-atribuicoes/1", json={"responsavel": "Novo"})

        assert r.status_code == 409

    def test_aguardando_assinatura_sem_modo_interno_continua_bloqueado(self, make_client):
        sb = _sb(modo_interno_desde=None)
        client = make_client(sb)

        r = client.patch("/api/reunioes/R1/quadro-atribuicoes/0", json={"responsavel": "Novo"})

        assert r.status_code == 400

    def test_aguardando_validacao_continua_editavel(self, make_client):
        """Regressao: a janela atual de edicao (AGUARDANDO_VALIDACAO) nao muda."""
        sb = _sb(status_ata="AGUARDANDO_VALIDACAO", modo_interno_desde=None)
        client = make_client(sb)

        r = client.patch("/api/reunioes/R1/quadro-atribuicoes/0", json={"responsavel": "Novo"})

        assert r.status_code == 200

    def test_secretaria_segue_403(self, make_client):
        """Gate atual da Secretaria preservado (defense-in-depth)."""
        sb = _sb()
        client = make_client(sb, is_secretaria_override=True)

        r = client.patch("/api/reunioes/R1/quadro-atribuicoes/1", json={"responsavel": "Novo"})

        assert r.status_code == 403


# ═══════════════════════════════════════════════════════════════════════════
# CA: nenhuma acao de reenvio ao ClickSign no modo interno
# ═══════════════════════════════════════════════════════════════════════════


class TestLembrarNoModoInterno:
    def test_lembrar_bloqueado_no_modo_interno(self, make_client, monkeypatch):
        from app.services import clicksign_service

        def _explode(*_a, **_kw):
            raise AssertionError("ClickSign nao deve ser chamada no modo interno")

        monkeypatch.setattr(clicksign_service, "remind_signer", _explode)

        sb = _sb()
        client = make_client(sb)
        r = client.post("/api/reunioes/R1/signatarios/s1/lembrar")

        assert r.status_code == 400
        assert "interno" in r.json()["detail"].lower()


# ═══════════════════════════════════════════════════════════════════════════
# CA: card de Signatarios exibe a variante do modo interno
# ═══════════════════════════════════════════════════════════════════════════


class TestStatusNoModoInterno:
    def test_status_modo_interno_sem_consultar_clicksign(self, make_client, monkeypatch):
        from app.services import clicksign_service

        def _explode(*_a, **_kw):
            raise AssertionError("ClickSign nao deve ser consultada no modo interno (Envelope morto)")

        monkeypatch.setattr(clicksign_service, "list_signers", _explode)

        sb = _sb(aceites=[_aceite("P_ANA", "ana@hsm.com")])
        client = make_client(sb)
        r = client.get("/api/reunioes/R1/signatarios/status")

        assert r.status_code == 200
        body = r.json()
        assert body["modo_interno"] is True
        assert body["total"] == 3
        assert body["assinaram"] == 1
        por_email = {s["email"]: s for s in body["signatarios"]}
        assert por_email["ana@hsm.com"]["status"] == "signed"
        assert por_email["ana@hsm.com"]["signed_at"] == "2026-08-10T10:00:00-03:00"
        assert por_email["fabio@hsm.com"]["status"] == "pending"
        assert por_email["bruno@hsm.com"]["status"] == "pending"

    def test_status_modo_interno_expoe_participante_id_para_o_aceite_manual(self, make_client):
        """O botão "Registrar aceite manualmente" (issue #278) age por
        participante: cada linha da variante interna carrega o id."""
        sb = _sb(aceites=[_aceite("P_ANA", "ana@hsm.com")])
        client = make_client(sb)
        r = client.get("/api/reunioes/R1/signatarios/status")

        assert r.status_code == 200
        por_email = {s["email"]: s for s in r.json()["signatarios"]}
        assert por_email["ana@hsm.com"]["participante_id"] == "P_ANA"
        assert por_email["fabio@hsm.com"]["participante_id"] == "P_FAC"
        assert por_email["bruno@hsm.com"]["participante_id"] == "P_BRUNO"

    def test_status_fora_do_modo_interno_nao_marca_flag(self, make_client, monkeypatch):
        from app.services import clicksign_service

        monkeypatch.setattr(
            clicksign_service,
            "list_signers",
            lambda _env: [
                {"signer_id": "s1", "nome": "Ana Lima", "email": "ana@hsm.com", "status": "pending", "signed_at": None}
            ],
        )

        sb = _sb(modo_interno_desde=None)
        client = make_client(sb)
        r = client.get("/api/reunioes/R1/signatarios/status")

        assert r.status_code == 200
        assert not r.json().get("modo_interno")
