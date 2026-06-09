"""Testes da Extração de Pendências por IA + roster da Nota (issue #34, ADR 0004).

A Nota ganha o **roster** de Participantes (Colaborador do cadastro OU nome
avulso, para externos) e o botão de extrair: a partir do corpo, a IA **propõe**
Pendências (descrição, responsável casado roster-first, prazo parseado de
linguagem natural) que o Facilitador confirma/edita/descarta antes de criar —
a criação reusa a fatia anterior (POST /notas/{id}/pendencias, issue #33).

Escopo: roster (endpoints), `extracao_pendencias_service.extrair` com LLM
**100% mockado** (nenhum teste depende de chave/provider real) e o endpoint de
extração. Mock Supabase fluente espelhado de `test_pendencias_origem_nota.py`.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.dependencies import (  # noqa: E402
    get_current_user,
    get_supabase_client,
)
from app.routers import notas as notas_router  # noqa: E402

# ─── Mock Supabase ───────────────────────────────────────────────────────────


@dataclass
class _Result:
    data: Any
    count: int | None = None


class _TableQuery:
    """Mock fluente: select/insert/update/delete + eq/in_/is_/ilike/order/limit.

    `autoid` espelha os defaults do Postgres (id UUID + created_at) no insert.
    """

    def __init__(self, rows_ref: list, autoid: bool = False):
        self._rows = rows_ref
        self._autoid = autoid
        self._op: str = "select"
        self._payload: Any = None
        self._filters: list[tuple[str, Any]] = []
        self._in_filters: list[tuple[str, list]] = []
        self._is_filters: list[tuple[str, str]] = []
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

    def is_(self, col, value):
        self._is_filters.append((col, value))
        return self

    def ilike(self, col, pattern):
        self._ilike = (col, pattern)
        return self

    def order(self, col, desc=False, **_kw):
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
        for col, value in self._is_filters:
            is_null = r.get(col) is None
            if value == "null" and not is_null:
                return False
            if value == "not.null" and is_null:
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
            inserted = []
            for it in items:
                row = dict(it)
                if self._autoid:
                    row.setdefault("id", f"row{len(self._rows) + 1}")
                    row.setdefault("created_at", "2026-06-09T12:00:00Z")
                self._rows.append(row)
                inserted.append(dict(row))
            return _Result(data=inserted)

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
        return _Result(data=list(matched), count=len(matched))


@dataclass
class _SupabaseMock:
    participantes: list = field(default_factory=list)
    notas: list = field(default_factory=list)
    nota_participantes: list = field(default_factory=list)
    pendencias: list = field(default_factory=list)

    def table(self, name: str):
        if name == "participantes":
            return _TableQuery(self.participantes)
        if name == "notas":
            return _TableQuery(self.notas)
        if name == "nota_participantes":
            return _TableQuery(self.nota_participantes, autoid=True)
        if name == "pendencias":
            return _TableQuery(self.pendencias)
        raise AssertionError(f"Tabela inesperada: {name}")


# ─── App fixture ─────────────────────────────────────────────────────────────


CURRENT_USER = {"id": "auth-uid-1", "email": "diretor@hospital.com"}


def _participante(pid: str, profile: str = "regular") -> dict:
    """Participante logado. `profile` ∈ {regular, secretaria, super_admin}."""
    return {"id": pid, "nome_completo": f"Facilitador {pid}", "access_profile": profile}


def _nota(nid: str, autor: str, corpo: str | None = None) -> dict:
    return {"id": nid, "corpo": corpo or f"nota {nid}", "autor_id": autor, "created_at": "2026-06-01T09:00:00Z"}


@pytest.fixture
def make_client(monkeypatch):
    """Factory: TestClient do router de notas com supabase mock + logado plugado."""

    def _factory(supabase: _SupabaseMock, *, me: dict) -> TestClient:
        app = FastAPI()
        app.include_router(notas_router.router, prefix="/api")

        app.dependency_overrides[get_current_user] = lambda: CURRENT_USER
        app.dependency_overrides[get_supabase_client] = lambda: supabase

        async def _fake_get_participante(*_a, **_kw):
            return dict(me)

        monkeypatch.setattr(notas_router, "get_participante_for_user", _fake_get_participante)
        return TestClient(app)

    return _factory


# ═══════════════════════════════════════════════════════════════════════════
# Roster da Nota: PUT/GET /notas/{id}/participantes
# ═══════════════════════════════════════════════════════════════════════════


class TestRosterDaNota:
    def test_autor_marca_colaborador_do_cadastro_e_nome_avulso(self, make_client):
        """Critério 1: o editor da Nota marca quem participou — Colaborador do
        cadastro (vira vínculo com nome canônico) OU nome avulso (externo não
        cadastrado, fica só como nome)."""
        me = _participante("P1")
        sb = _SupabaseMock(
            participantes=[me, {"id": "P2", "nome_completo": "Ana Lima", "cargo": "Coordenadora"}],
            notas=[_nota("n1", autor="P1")],
        )
        client = make_client(sb, me=me)

        r = client.put(
            "/api/notas/n1/participantes",
            json={"participantes": [{"participante_id": "P2"}, {"nome_avulso": "Fulano Aliado"}]},
        )
        assert r.status_code == 200
        roster = r.json()
        assert len(roster) == 2
        por_nome = {item["nome"]: item for item in roster}
        assert por_nome["Ana Lima"]["participante_id"] == "P2"
        assert por_nome["Fulano Aliado"]["participante_id"] is None
        assert por_nome["Fulano Aliado"]["nome_avulso"] == "Fulano Aliado"

        # GET devolve o roster persistido.
        g = client.get("/api/notas/n1/participantes")
        assert g.status_code == 200
        assert {i["nome"] for i in g.json()} == {"Ana Lima", "Fulano Aliado"}

    def test_entrada_do_roster_exige_cadastro_ou_avulso_exatamente_um(self, make_client):
        """Critério 1 (borda): cada entrada é Colaborador OU nome avulso —
        nunca os dois, nunca nenhum (422); nada é gravado."""
        me = _participante("P1")
        sb = _SupabaseMock(
            participantes=[me, {"id": "P2", "nome_completo": "Ana Lima"}],
            notas=[_nota("n1", autor="P1")],
        )
        client = make_client(sb, me=me)

        ambos = {"participantes": [{"participante_id": "P2", "nome_avulso": "Ana Lima"}]}
        assert client.put("/api/notas/n1/participantes", json=ambos).status_code == 422

        nenhum = {"participantes": [{}]}
        assert client.put("/api/notas/n1/participantes", json=nenhum).status_code == 422

        assert sb.nota_participantes == []

    def test_editar_roster_substitui_a_lista_anterior(self, make_client):
        """Critério 1: o editor regrava o roster como um todo — quem saiu da
        lista sai do vínculo; lista vazia limpa o roster."""
        me = _participante("P1")
        sb = _SupabaseMock(
            participantes=[me, {"id": "P2", "nome_completo": "Ana Lima"}],
            notas=[_nota("n1", autor="P1")],
        )
        client = make_client(sb, me=me)

        client.put("/api/notas/n1/participantes", json={"participantes": [{"participante_id": "P2"}]})
        r = client.put("/api/notas/n1/participantes", json={"participantes": [{"nome_avulso": "Dr. Externo"}]})
        assert r.status_code == 200
        assert [i["nome"] for i in r.json()] == ["Dr. Externo"]
        assert len(sb.nota_participantes) == 1

        vazio = client.put("/api/notas/n1/participantes", json={"participantes": []})
        assert vazio.status_code == 200
        assert vazio.json() == []
        assert sb.nota_participantes == []

    def test_roster_de_nota_alheia_nem_aparece_e_secretaria_le_sem_editar(self, make_client):
        """O roster herda o acesso da Nota: outro Facilitador regular recebe
        404 (anti-enumeration); a Secretária enxerga (visão global de leitura)
        mas não edita — editar é do autor ou Super admin."""
        sb = _SupabaseMock(
            participantes=[_participante("P1"), _participante("P2"), _participante("P9", "secretaria")],
            notas=[_nota("n1", autor="P1")],
            nota_participantes=[{"id": "r1", "id_nota": "n1", "participante_id": None, "nome_avulso": "Fulano"}],
        )

        intruso = make_client(sb, me=_participante("P2"))
        assert intruso.get("/api/notas/n1/participantes").status_code == 404
        corpo = {"participantes": [{"nome_avulso": "Invasor"}]}
        assert intruso.put("/api/notas/n1/participantes", json=corpo).status_code == 404

        secretaria = make_client(sb, me=_participante("P9", "secretaria"))
        leitura = secretaria.get("/api/notas/n1/participantes")
        assert leitura.status_code == 200
        assert [i["nome"] for i in leitura.json()] == ["Fulano"]
        assert secretaria.put("/api/notas/n1/participantes", json=corpo).status_code == 403

        # Nada mudou no roster.
        assert [r["nome_avulso"] for r in sb.nota_participantes] == ["Fulano"]

    def test_colaborador_inexistente_no_cadastro_e_rejeitado(self, make_client):
        """Critério 1 (borda): participante_id que não existe no cadastro é
        rejeitado com 422 — o vínculo só nasce de Colaborador real."""
        me = _participante("P1")
        sb = _SupabaseMock(participantes=[me], notas=[_nota("n1", autor="P1")])
        client = make_client(sb, me=me)

        r = client.put("/api/notas/n1/participantes", json={"participantes": [{"participante_id": "P404"}]})
        assert r.status_code == 422
        assert sb.nota_participantes == []
