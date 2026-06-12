"""Testes da issue #78 — vínculo do responsável honrado fim a fim (ADR 0008).

Dois pontos da cadeia existente passam a honrar o `responsavel_id`:

- `PATCH /reunioes/{id}/quadro-atribuicoes/{index}`: escolher um Participante
  no dropdown grava o vínculo no item do `json_ata` (hoje o id é validado e
  descartado); texto livre limpa o vínculo anterior.
- `liberar_pendencias`: item com `responsavel_id` cria a Pendência com esse
  vínculo exato (sem rematch por nome); o fallback por nome permanece para
  itens sem vínculo, atas antigas e ids fora do cadastro.

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
    reuniao_participantes: list = field(default_factory=list)
    reunioes: list = field(default_factory=list)
    pendencias: list = field(default_factory=list)
    audit_log: list = field(default_factory=list)

    def table(self, name: str):
        if name == "participantes":
            return _TableQuery(self.participantes)
        if name == "reuniao_participantes":
            return _TableQuery(self.reuniao_participantes)
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
    """Factory que monta TestClient com supabase mock + auth/papel plugados."""

    def _factory(supabase: _SupabaseMock) -> TestClient:
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
        monkeypatch.setattr(reunioes_router, "is_secretaria", lambda _me: False)

        return TestClient(app)

    return _factory


def _participante(pid: str, nome: str, cargo: str) -> dict:
    return {"id": pid, "nome_completo": nome, "cargo": cargo}


def _no_roster(id_reuniao: str, participante: dict) -> dict:
    """Linha de `reuniao_participantes` com o join `participantes(...)` embutido."""
    return {
        "id_reuniao": id_reuniao,
        "participante_id": participante["id"],
        "participantes": dict(participante),
    }


def _reuniao_aguardando(quadro: list[dict]) -> dict:
    return {
        "id_reuniao": "R1",
        "status_ata": "AGUARDANDO_VALIDACAO",
        "url_pdf_preliminar": "https://x/preliminar.pdf",
        "tipo": "Gerencial",
        "objetivo": "Acompanhamento",
        "json_ata": {"quadro_atribuicoes": quadro},
    }


# ═══════════════════════════════════════════════════════════════════════════
# PATCH /reunioes/{id}/quadro-atribuicoes/{index} — grava e limpa o vínculo
# ═══════════════════════════════════════════════════════════════════════════


class TestPatchQuadroGravaVinculo:
    def test_escolher_participante_no_dropdown_grava_vinculo_no_item(self, make_client):
        """Escolher um Participante no dropdown da validação grava o
        `responsavel_id` no item do quadro, junto do nome/cargo canônicos."""
        ana = _participante("P2", "Ana Lima", "Coordenadora")
        sb = _SupabaseMock(
            participantes=[ana],
            reuniao_participantes=[_no_roster("R1", ana)],
            reunioes=[_reuniao_aguardando([{"acao": "Revisar protocolo", "responsavel": "Ana", "prazo": None}])],
        )

        client = make_client(sb)
        r = client.patch(
            "/api/reunioes/R1/quadro-atribuicoes/0",
            json={"responsavel_participante_id": "P2"},
        )

        assert r.status_code == 200
        assert r.json()["responsavel_id"] == "P2"
        assert r.json()["responsavel"] == "Ana Lima"
        assert r.json()["cargo"] == "Coordenadora"

        # Vínculo persistido no json_ata, não só na resposta.
        item = sb.reunioes[0]["json_ata"]["quadro_atribuicoes"][0]
        assert item["responsavel_id"] == "P2"

    def test_texto_livre_limpa_vinculo_anterior(self, make_client):
        """Digitar texto livre no dropdown limpa o vínculo do item — a Pendência
        não pode apontar para o Colaborador antigo."""
        sb = _SupabaseMock(
            reunioes=[
                _reuniao_aguardando(
                    [
                        {
                            "acao": "Revisar protocolo",
                            "responsavel": "Ana Lima",
                            "cargo": "Coordenadora",
                            "responsavel_id": "P2",
                            "prazo": None,
                        }
                    ]
                )
            ],
        )

        client = make_client(sb)
        r = client.patch(
            "/api/reunioes/R1/quadro-atribuicoes/0",
            json={"responsavel": "Dr. Externo", "cargo": "Consultor"},
        )

        assert r.status_code == 200
        assert r.json()["responsavel"] == "Dr. Externo"
        assert r.json().get("responsavel_id") is None

        item = sb.reunioes[0]["json_ata"]["quadro_atribuicoes"][0]
        assert item.get("responsavel_id") is None


# ═══════════════════════════════════════════════════════════════════════════
# Liberação de Pendências — honra o vínculo, fallback por nome intacto
# ═══════════════════════════════════════════════════════════════════════════


class TestLiberacaoHonraVinculo:
    def test_item_com_vinculo_cria_pendencia_sem_rematch_por_nome(self, make_client):
        """Item vinculado a um homônimo "errado" pro ILIKE: o rematch por nome
        acharia Lucas Silva (primeiro match), mas a Pendência nasce com o
        Colaborador exato do vínculo — Lucas Mendes."""
        sb = _SupabaseMock(
            participantes=[
                _participante("P1", "Lucas Silva", "Analista de TI"),
                _participante("P9", "Lucas Mendes", "Coordenador de RH"),
            ],
            reunioes=[
                _reuniao_aguardando(
                    [{"acao": "Mapear escalas", "responsavel": "Lucas", "responsavel_id": "P9", "prazo": None}]
                )
            ],
        )

        client = make_client(sb)
        r = client.post("/api/reunioes/R1/aprovar-sem-assinatura")

        assert r.status_code == 200
        assert len(sb.pendencias) == 1
        assert sb.pendencias[0]["responsavel_id"] == "P9"
        assert sb.pendencias[0]["responsavel_nome"] == "Lucas Mendes"

    def test_com_vinculo_cargo_da_pendencia_e_o_canonico_do_cadastro(self, make_client):
        """O cargo ouvido na conversa não vaza pra Pendência: com vínculo, vale o
        canônico do cadastro (ADR 0008)."""
        sb = _SupabaseMock(
            participantes=[_participante("P9", "Lucas Mendes", "Coordenador de RH")],
            reunioes=[
                _reuniao_aguardando(
                    [
                        {
                            "acao": "Mapear escalas",
                            "responsavel": "Lucas Mendes",
                            "cargo": "Estagiário",
                            "responsavel_id": "P9",
                            "prazo": None,
                        }
                    ]
                )
            ],
        )

        client = make_client(sb)
        r = client.post("/api/reunioes/R1/aprovar-sem-assinatura")

        assert r.status_code == 200
        assert sb.pendencias[0]["cargo"] == "Coordenador de RH"

    def test_vinculo_fora_do_cadastro_cai_no_fallback_por_nome_sem_erro(self, make_client):
        """`responsavel_id` que não existe no cadastro (colaborador removido,
        dado corrompido) não derruba a liberação: cai na resolução por nome."""
        sb = _SupabaseMock(
            participantes=[_participante("P2", "Ana Lima", "Coordenadora")],
            reunioes=[
                _reuniao_aguardando(
                    [{"acao": "Revisar protocolo", "responsavel": "Ana Lima", "responsavel_id": "GHOST", "prazo": None}]
                )
            ],
        )

        client = make_client(sb)
        r = client.post("/api/reunioes/R1/aprovar-sem-assinatura")

        assert r.status_code == 200
        assert len(sb.pendencias) == 1
        assert sb.pendencias[0]["responsavel_id"] == "P2"  # resolvido por nome
        assert sb.pendencias[0]["cargo"] == "Coordenadora"

    def test_item_sem_vinculo_se_comporta_como_hoje(self, make_client):
        """Ata antiga / item sem `responsavel_id`: resolução por nome intacta —
        nome do quadro preservado na Pendência, match parcial no cadastro, e
        externo sem match fica sem vínculo."""
        sb = _SupabaseMock(
            participantes=[_participante("P1", "Pedro Rezende", "Diretor")],
            reunioes=[
                _reuniao_aguardando(
                    [
                        {"acao": "Comprar insumos", "responsavel": "Pedro", "prazo": None},
                        {"acao": "Auditoria externa", "responsavel": "Dr. Visitante", "prazo": None},
                    ]
                )
            ],
        )

        client = make_client(sb)
        r = client.post("/api/reunioes/R1/aprovar-sem-assinatura")

        assert r.status_code == 200
        assert len(sb.pendencias) == 2

        com_match, externo = sb.pendencias
        assert com_match["responsavel_id"] == "P1"
        assert com_match["responsavel_nome"] == "Pedro"  # texto do quadro, como hoje
        assert com_match["cargo"] == "Diretor"
        assert externo["responsavel_id"] is None
        assert externo["responsavel_nome"] == "Dr. Visitante"


# ═══════════════════════════════════════════════════════════════════════════
# Fim a fim — o que o Facilitador escolhe no dropdown é o que a Pendência grava
# ═══════════════════════════════════════════════════════════════════════════


class TestVinculoFimAFim:
    def test_escolha_no_dropdown_vira_pendencia_com_o_mesmo_vinculo(self, make_client):
        """O elo completo: Facilitador escolhe Lucas Mendes no dropdown da
        validação e a Pendência liberada nasce com exatamente esse vínculo —
        mesmo o ILIKE por nome preferindo o homônimo Lucas Silva."""
        silva = _participante("P1", "Lucas Silva", "Analista de TI")
        mendes = _participante("P9", "Lucas Mendes", "Coordenador de RH")
        sb = _SupabaseMock(
            participantes=[silva, mendes],
            reuniao_participantes=[_no_roster("R1", silva), _no_roster("R1", mendes)],
            reunioes=[_reuniao_aguardando([{"acao": "Mapear escalas", "responsavel": "Lucas", "prazo": None}])],
        )

        client = make_client(sb)
        r_patch = client.patch(
            "/api/reunioes/R1/quadro-atribuicoes/0",
            json={"responsavel_participante_id": "P9"},
        )
        r_aprovar = client.post("/api/reunioes/R1/aprovar-sem-assinatura")

        assert r_patch.status_code == 200
        assert r_aprovar.status_code == 200
        assert len(sb.pendencias) == 1
        assert sb.pendencias[0]["responsavel_id"] == "P9"
        assert sb.pendencias[0]["responsavel_nome"] == "Lucas Mendes"
        assert sb.pendencias[0]["cargo"] == "Coordenador de RH"
