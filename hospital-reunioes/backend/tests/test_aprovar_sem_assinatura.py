"""Testes do endpoint `POST /reunioes/{id}/aprovar-sem-assinatura` (issue #26).

Fluxo de aprovação sem ClickSign: o Facilitador finaliza a Ata direto, as
Pendências do `quadro_atribuicoes` nascem na hora e a Reunião vai para o estado
terminal `APROVADA` — sem Envelope, sem aguardar assinaturas.

Espelha as guardas do `/aprovar` (Secretária 403, status 400, reunião 404) e
reusa o módulo `liberar_pendencias` (idempotente). Padrão de mock copiado de
`test_signatarios_status.py`.
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
    """Mock fluente: select/insert/update/delete + eq/in_/ilike/order/limit."""

    def __init__(self, rows_ref: list):
        self._rows = rows_ref
        self._op: str = "select"
        self._payload: Any = None
        self._filters: list[tuple[str, Any]] = []
        self._in_filters: list[tuple[str, list]] = []
        self._ilike: tuple[str, str] | None = None
        self._order: tuple[str, bool] | None = None
        self._limit: int | None = None

    def select(self, *_a, **_kw):
        self._op = "select"
        return self

    def insert(self, payload):
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

    def ilike(self, col, pattern):
        self._ilike = (col, pattern)
        return self

    def order(self, col, desc=False):
        self._order = (col, desc)
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
        if self._ilike is not None:
            col, pattern = self._ilike
            needle = pattern.strip("%").lower()
            if needle not in str(r.get(col) or "").lower():
                return False
        return True

    def execute(self):
        if self._op == "insert":
            items = self._payload if isinstance(self._payload, list) else [self._payload]
            for it in items:
                self._rows.append(dict(it))
            return _Result(data=[dict(it) for it in items])

        matched = [r for r in self._rows if self._matches(r)]
        if self._order is not None:
            col, desc = self._order
            matched.sort(key=lambda r: str(r.get(col) or ""), reverse=desc)
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
    pendencias: list = field(default_factory=list)
    audit_log: list = field(default_factory=list)

    def table(self, name: str):
        if name == "participantes":
            return _TableQuery(self.participantes)
        if name == "reunioes":
            return _TableQuery(self.reunioes)
        if name == "pendencias":
            return _TableQuery(self.pendencias)
        if name == "audit_log":
            return _TableQuery(self.audit_log)
        raise AssertionError(f"Tabela inesperada: {name}")


# ─── App fixture ──────────────────────────────────────────────────────────────


CURRENT_USER = {"id": "auth-uid-1", "email": "diretor@hospital.com"}
FACILITADOR = {"id": "P_DIR", "email": "diretor@hospital.com", "access_profile": "regular"}


@pytest.fixture
def make_client(monkeypatch):
    """Factory que monta TestClient com supabase mock + auth/papel plugados.

    Por padrão o usuário é um Facilitador comum (não Secretária). O ClickSign é
    espionado: o endpoint sem assinatura NÃO deve invocá-lo.
    """

    def _factory(
        supabase: _SupabaseMock,
        *,
        is_secretaria_override: bool = False,
        clicksign_spy: dict | None = None,
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
            return None  # sem restrição de visibilidade

        monkeypatch.setattr(reunioes_router, "get_participante_for_user", _fake_get_participante)
        monkeypatch.setattr(reunioes_router, "get_allowed_reuniao_ids", _fake_allowed)
        monkeypatch.setattr(reunioes_router, "is_secretaria", lambda _me: is_secretaria_override)

        # Espiona o ClickSign: qualquer chamada marca a flag (não deve acontecer).
        from app.services import clicksign_service

        def _spy(*_a, **_kw):
            if clicksign_spy is not None:
                clicksign_spy["chamado"] = True

        monkeypatch.setattr(clicksign_service, "start_signature_flow", _spy)

        return TestClient(app)

    return _factory


def _acao(acao: str, responsavel: str, prazo: str | None = None) -> dict:
    return {"acao": acao, "responsavel": responsavel, "prazo": prazo}


def _reuniao_aguardando(quadro: list[dict] | None) -> dict:
    return {
        "id_reuniao": "R1",
        "status_ata": "AGUARDANDO_VALIDACAO",
        "url_pdf_preliminar": "https://x/preliminar.pdf",
        "tipo": "Gerencial",
        "objetivo": "Acompanhamento",
        "json_ata": {"quadro_atribuicoes": quadro} if quadro is not None else {},
    }


# ═══════════════════════════════════════════════════════════════════════════
# POST /reunioes/{id}/aprovar-sem-assinatura
# ═══════════════════════════════════════════════════════════════════════════


class TestAprovarSemAssinatura:
    def test_finaliza_cria_pendencias_e_marca_aprovada(self, make_client):
        """Facilitador finaliza sem assinatura: nasce uma Pendência por ação do
        quadro de atribuições, a Ata vira APROVADA e o ClickSign não é tocado."""
        spy = {"chamado": False}
        sb = _SupabaseMock(
            participantes=[
                {"id": "P1", "nome_completo": "Pedro Rezende", "cargo": "Diretor"},
                {"id": "P2", "nome_completo": "Ana Lima", "cargo": "Coordenadora"},
            ],
            reunioes=[
                _reuniao_aguardando(
                    [
                        _acao("Comprar insumos", "Pedro Rezende", "2026-06-10"),
                        _acao("Revisar protocolo", "Ana Lima", "10/06/2026"),
                    ]
                )
            ],
        )

        client = make_client(sb, clicksign_spy=spy)
        r = client.post("/api/reunioes/R1/aprovar-sem-assinatura")

        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "APROVADA"
        assert body["total_pendencias"] == 2
        assert "message" in body

        # Efeito no domínio: Ata terminal + Pendências criadas.
        assert sb.reunioes[0]["status_ata"] == "APROVADA"
        assert len(sb.pendencias) == 2
        assert all(p["status"] == "PENDENTE" for p in sb.pendencias)
        assert all(p["id_reuniao"] == "R1" for p in sb.pendencias)

        # Não passa pelo ClickSign.
        assert spy["chamado"] is False

    def test_secretaria_bloqueada_403(self, make_client):
        """Secretária não aprova Atas — nem com, nem sem assinatura (regra atual)."""
        spy = {"chamado": False}
        sb = _SupabaseMock(reunioes=[_reuniao_aguardando([_acao("X", "Pedro Rezende")])])
        client = make_client(sb, is_secretaria_override=True, clicksign_spy=spy)
        r = client.post("/api/reunioes/R1/aprovar-sem-assinatura")
        assert r.status_code == 403
        # Guard vem antes de tudo: nada é criado nem alterado.
        assert sb.pendencias == []
        assert sb.reunioes[0]["status_ata"] == "AGUARDANDO_VALIDACAO"
        assert spy["chamado"] is False

    def test_exige_aguardando_validacao_400(self, make_client):
        """Só Ata em AGUARDANDO_VALIDACAO pode ser finalizada sem assinatura."""
        sb = _SupabaseMock(
            reunioes=[{"id_reuniao": "R1", "status_ata": "AGUARDANDO_ASSINATURA", "json_ata": {}}]
        )
        client = make_client(sb)
        r = client.post("/api/reunioes/R1/aprovar-sem-assinatura")
        assert r.status_code == 400
        assert sb.pendencias == []
        assert sb.reunioes[0]["status_ata"] == "AGUARDANDO_ASSINATURA"

    def test_reuniao_inexistente_404(self, make_client):
        sb = _SupabaseMock(reunioes=[])
        client = make_client(sb)
        r = client.post("/api/reunioes/NOPE/aprovar-sem-assinatura")
        assert r.status_code == 404

    def test_quadro_vazio_aprova_com_zero_pendencias(self, make_client):
        """Ata sem ações (quadro vazio) ainda finaliza: vira APROVADA com 0 Pendências."""
        sb = _SupabaseMock(reunioes=[_reuniao_aguardando([])])
        client = make_client(sb)
        r = client.post("/api/reunioes/R1/aprovar-sem-assinatura")
        assert r.status_code == 200
        assert r.json()["total_pendencias"] == 0
        assert r.json()["status"] == "APROVADA"
        assert sb.reunioes[0]["status_ata"] == "APROVADA"
        assert sb.pendencias == []

    def test_idempotente_nao_duplica_em_retentativa(self, make_client):
        """Re-tentativa após falha parcial: as Pendências já existem mas o status
        ainda é AGUARDANDO_VALIDACAO. A 2ª passada não duplica (retorna 0) e fecha
        em APROVADA — reuso da idempotência do liberar_pendencias."""
        sb = _SupabaseMock(
            participantes=[{"id": "P1", "nome_completo": "Pedro Rezende", "cargo": "Diretor"}],
            reunioes=[_reuniao_aguardando([_acao("Comprar insumos", "Pedro Rezende")])],
            pendencias=[{"id_acao": "A001", "id_reuniao": "R1", "status": "PENDENTE"}],
        )
        client = make_client(sb)
        r = client.post("/api/reunioes/R1/aprovar-sem-assinatura")
        assert r.status_code == 200
        assert r.json()["total_pendencias"] == 0  # não recriou
        assert sb.reunioes[0]["status_ata"] == "APROVADA"
        assert len(sb.pendencias) == 1  # nenhuma duplicada

    def test_segunda_chamada_http_e_terminal_400(self, make_client):
        """APROVADA é terminal: depois de finalizar, repetir a ação dá 400 (já não
        está em AGUARDANDO_VALIDACAO) — nada é duplicado."""
        sb = _SupabaseMock(
            participantes=[{"id": "P1", "nome_completo": "Pedro Rezende", "cargo": "Diretor"}],
            reunioes=[_reuniao_aguardando([_acao("Comprar insumos", "Pedro Rezende")])],
        )
        client = make_client(sb)
        r1 = client.post("/api/reunioes/R1/aprovar-sem-assinatura")
        r2 = client.post("/api/reunioes/R1/aprovar-sem-assinatura")
        assert r1.status_code == 200
        assert r2.status_code == 400
        assert len(sb.pendencias) == 1

    def test_registra_auditoria(self, make_client):
        """Finalizar sem assinatura deixa rastro: quem dispensou a assinatura e quando."""
        sb = _SupabaseMock(
            participantes=[{"id": "P1", "nome_completo": "Pedro Rezende", "cargo": "Diretor"}],
            reunioes=[_reuniao_aguardando([_acao("Comprar insumos", "Pedro Rezende")])],
        )
        client = make_client(sb)
        r = client.post("/api/reunioes/R1/aprovar-sem-assinatura")
        assert r.status_code == 200
        assert len(sb.audit_log) == 1
        log = sb.audit_log[0]
        assert log["action"] == "APROVACAO_SEM_ASSINATURA"
        assert log["target_type"] == "reuniao"
        assert log["target_id"] == "R1"
        assert log["actor_id"] == "P_DIR"
        assert log["metadata"]["total_pendencias"] == 1
