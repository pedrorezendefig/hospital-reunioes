"""Testes do endpoint GET /api/participantes (listagem para marcar reunião).

Regressão do incidente "Erro ao buscar participantes" (500 global): uma única
linha com dado fora do schema (role/access_profile/perfil_pop inválido, ou campo
obrigatório nulo) NÃO pode derrubar a lista inteira. A linha malformada é pulada
e logada; o restante do roster é retornado normalmente.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.dependencies import get_current_user, get_supabase_client  # noqa: E402
from app.routers import participantes as participantes_router  # noqa: E402

# ─── Mock Supabase ────────────────────────────────────────────────────────────


@dataclass
class _Result:
    data: list


class _ParticipantesQuery:
    """Mock fiel o suficiente para exercitar paginação e busca por nome.

    Honra eq/ilike/order/range porque a regressão "não acho a Uliandra no
    seletor" nasce justamente da interação entre `order(nome_completo)` +
    `range(limit)` (que trunca o roster) e a busca server-side por `ilike`.
    neq/in_ seguem no-op (não exercitados nestes testes).
    """

    def __init__(self, rows: list):
        self._rows = rows
        self._eq: dict = {}
        self._ilike: list[tuple[str, str]] = []
        self._order: str | None = None
        self._range: tuple[int, int] | None = None

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, col, value):
        self._eq[col] = value
        return self

    def neq(self, *_args, **_kwargs):
        return self

    def ilike(self, col, pattern):
        self._ilike.append((col, pattern))
        return self

    def in_(self, *_args, **_kwargs):
        return self

    def order(self, col, *_args, **_kwargs):
        self._order = col
        return self

    def range(self, start, end):
        self._range = (start, end)
        return self

    def execute(self):
        rows = [r for r in self._rows if all(r.get(c) == v for c, v in self._eq.items())]
        for col, pattern in self._ilike:
            needle = pattern.strip("%").lower()
            rows = [r for r in rows if needle in str(r.get(col) or "").lower()]
        if self._order:
            rows = sorted(rows, key=lambda r: str(r.get(self._order) or ""))
        if self._range:
            start, end = self._range
            rows = rows[start : end + 1]
        return _Result(data=[dict(r) for r in rows])


@dataclass
class _SupabaseMock:
    participantes: list = field(default_factory=list)

    def table(self, name: str):
        if name == "participantes":
            return _ParticipantesQuery(self.participantes)
        raise AssertionError(f"Tabela inesperada: {name}")


def _make_app(participantes: list) -> TestClient:
    app = FastAPI()
    app.include_router(participantes_router.router, prefix="/api")

    async def _fake_user() -> dict[str, Any]:
        return {"id": "auth-1", "email": "facilitador@ex.com", "metadata": {}}

    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_supabase_client] = lambda: _SupabaseMock(participantes=participantes)
    return TestClient(app)


def _row(pid: str, **overrides) -> dict:
    base = {
        "id": pid,
        "auth_user_id": f"auth-{pid}",
        "email": f"{pid}@ex.com",
        "nome_completo": f"Pessoa {pid}",
        "cargo": "Coordenadora",
        "area": "Assistencial",
        "setor": "UTI",
        "role": "coordenador",
        "ativo": True,
        "is_externo": False,
        "is_super_admin": False,
        "access_profile": "regular",
        "data_cadastro": "2026-01-10",
    }
    base.update(overrides)
    return base


# ─── Testes ───────────────────────────────────────────────────────────────────


class TestListParticipantes:
    def test_200_lista_limpa(self):
        client = _make_app([_row("P1"), _row("P2")])
        r = client.get("/api/participantes?ativo=true&limit=200")
        assert r.status_code == 200
        assert {p["id"] for p in r.json()} == {"P1", "P2"}

    def test_stub_externo_sem_email_aparece_na_lista(self):
        # Causa raiz do incidente: migration 026 permite email NULL para stubs
        # externos (técnico de fornecedor sem email). O ParticipanteResponse
        # exigia email obrigatório e 500ava a lista inteira. Agora o stub valida
        # e aparece normalmente no seletor de participantes.
        rows = [_row("P1"), _row("P_EXT", email=None, is_externo=True, role=None)]
        client = _make_app(rows)
        r = client.get("/api/participantes?ativo=true&limit=200")
        assert r.status_code == 200
        body = r.json()
        assert {p["id"] for p in body} == {"P1", "P_EXT"}
        ext = next(p for p in body if p["id"] == "P_EXT")
        assert ext["email"] is None

    def test_linha_com_valor_fora_do_schema_nao_derruba_a_lista(self):
        # Defesa contra drift: uma linha com valor fora do schema (não esperado
        # via app, mas possível por dado legado) é pulada e logada, em vez de
        # retornar 500 e travar a tela de nova reunião para todos.
        rows = [_row("P1"), _row("P_BAD", role="cargo_que_nao_existe"), _row("P2")]
        client = _make_app(rows)
        r = client.get("/api/participantes?ativo=true&limit=200")
        assert r.status_code == 200
        assert {p["id"] for p in r.json()} == {"P1", "P2"}  # válidos ok, linha ruim pulada

    def test_busca_por_nome_acha_quem_esta_na_cauda_do_alfabeto(self):
        # Regressão "não acho a Uliandra no seletor": com o roster acima de 50, o
        # seletor carregava só os 50 primeiros por nome e filtrava no cliente,
        # então nomes na cauda do alfabeto (U...) sumiam. A correção é busca
        # server-side: ?nome=Uliandra acha ela mesmo com roster grande e limit
        # pequeno (é o contrato do qual o seletor agora depende).
        rows = [_row(f"P{i:02d}", nome_completo=f"Ana {i:02d}") for i in range(60)]
        rows.append(_row("ULI", nome_completo="Uliandra Dutra"))
        client = _make_app(rows)
        r = client.get("/api/participantes?ativo=true&nome=Uliandra&limit=10")
        assert r.status_code == 200
        assert "ULI" in {p["id"] for p in r.json()}

    def test_sem_nome_a_primeira_pagina_trunca_o_roster(self):
        # Caracteriza a causa do bug no cliente: sem ?nome= e com o limit default
        # de 50, quem ordena depois da 50a posição não vem. Por isso o seletor
        # passou a buscar server-side e os callers de roster completo passaram a
        # paginar (fetchParticipantesAtivos).
        rows = [_row(f"P{i:02d}", nome_completo=f"Ana {i:02d}") for i in range(60)]
        rows.append(_row("ULI", nome_completo="Uliandra Dutra"))
        client = _make_app(rows)
        r = client.get("/api/participantes?ativo=true")  # sem nome, limit default = 50
        ids = {p["id"] for p in r.json()}
        assert len(ids) == 50
        assert "ULI" not in ids

    def test_paginacao_por_offset_cobre_o_roster_inteiro(self):
        # Contrato do qual fetchParticipantesAtivos depende: paginar por offset
        # devolve o roster inteiro, sem teto silencioso.
        rows = [_row(f"P{i:02d}", nome_completo=f"Ana {i:02d}") for i in range(60)]
        rows.append(_row("ULI", nome_completo="Uliandra Dutra"))
        client = _make_app(rows)
        pag1 = client.get("/api/participantes?ativo=true&limit=50&offset=0").json()
        pag2 = client.get("/api/participantes?ativo=true&limit=50&offset=50").json()
        ids = {p["id"] for p in pag1} | {p["id"] for p in pag2}
        assert "ULI" in ids
        assert len(ids) == 61
