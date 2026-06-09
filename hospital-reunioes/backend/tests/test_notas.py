"""Testes do router de Notas (issue #32): CRUD, histórico e guardas de acesso.

A **Nota** (CONTEXT.md) é um registro leve do Facilitador — corpo de texto
livre, com histórico próprio e soft-delete. O acesso espelha a Reunião: o autor
vê só as suas; Secretária e Super admin veem todas. Esta fatia fundadora não
tem roster de Participantes nem Pendências — só o corpo.

Escopo: comportamento observável pelos endpoints (cria/lista/abre/edita/arquiva
+ guardas). Mock Supabase fluente espelhado de `test_aprovar_sem_assinatura.py`,
estendido com `.is_()` para o filtro de soft-delete (`deleted_at IS NULL`).
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
from app.routers import notas as notas_router  # noqa: E402

# ─── Mock Supabase ───────────────────────────────────────────────────────────


@dataclass
class _Result:
    data: Any


class _TableQuery:
    """Mock fluente: select/insert/update/delete + eq/in_/is_/order/limit.

    `is_(col, "null")` casa linhas onde a coluna é None/ausente (espelha o
    filtro `deleted_at IS NULL` do PostgREST); `"not.null"` casa o inverso.
    """

    def __init__(self, rows_ref: list):
        self._rows = rows_ref
        self._op: str = "select"
        self._payload: Any = None
        self._filters: list[tuple[str, Any]] = []
        self._in_filters: list[tuple[str, list]] = []
        self._is_filters: list[tuple[str, str]] = []
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
        for col, value in self._is_filters:
            is_null = r.get(col) is None
            if value == "null" and not is_null:
                return False
            if value == "not.null" and is_null:
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
    notas: list = field(default_factory=list)

    def table(self, name: str):
        if name == "participantes":
            return _TableQuery(self.participantes)
        if name == "notas":
            return _TableQuery(self.notas)
        raise AssertionError(f"Tabela inesperada: {name}")


# ─── App fixture ──────────────────────────────────────────────────────────────


CURRENT_USER = {"id": "auth-uid-1", "email": "diretor@hospital.com"}


def _participante(pid: str, profile: str = "regular") -> dict:
    """Participante logado. `profile` ∈ {regular, secretaria, super_admin}."""
    return {"id": pid, "nome_completo": f"Facilitador {pid}", "access_profile": profile}


@pytest.fixture
def make_client(monkeypatch):
    """Factory: TestClient com supabase mock + participante logado plugado.

    `me` é o participante autenticado — o router resolve autor/guardas a partir
    do seu `access_profile` (não monkeypatchamos is_secretaria/is_super_admin;
    eles leem o dict real).
    """

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
# Criar e histórico
# ═══════════════════════════════════════════════════════════════════════════


class TestCriarEHistorico:
    def test_facilitador_cria_nota_e_ela_aparece_no_historico(self, make_client):
        """Critério 1: o Facilitador escreve um corpo de texto livre, a Nota é
        criada e aparece no histórico dele."""
        me = _participante("P1")
        sb = _SupabaseMock(participantes=[me])
        client = make_client(sb, me=me)

        r = client.post("/api/notas", json={"corpo": "Conversa com aliado sobre o orçamento de sexta"})
        assert r.status_code == 201
        body = r.json()
        assert body["corpo"] == "Conversa com aliado sobre o orçamento de sexta"
        assert body["autor_id"] == "P1"
        assert body["id"]  # id gerado pelo backend

        # Aparece no histórico do autor.
        h = client.get("/api/notas")
        assert h.status_code == 200
        notas = h.json()
        assert len(notas) == 1
        assert notas[0]["id"] == body["id"]
        assert notas[0]["corpo"] == "Conversa com aliado sobre o orçamento de sexta"

    def test_nao_cria_nota_com_corpo_vazio(self, make_client):
        """A Nota é um registro de texto — corpo vazio é rejeitado (422)."""
        me = _participante("P1")
        sb = _SupabaseMock(participantes=[me])
        client = make_client(sb, me=me)

        assert client.post("/api/notas", json={"corpo": ""}).status_code == 422
        assert sb.notas == []

    def test_historico_lista_notas_mais_recente_primeiro(self, make_client):
        """Critério 2: o histórico lista as Notas em ordem — mais recente primeiro."""
        me = _participante("P1")
        sb = _SupabaseMock(
            participantes=[me],
            notas=[
                {"id": "n1", "corpo": "primeira", "autor_id": "P1", "created_at": "2026-06-01T09:00:00Z"},
                {"id": "n2", "corpo": "segunda", "autor_id": "P1", "created_at": "2026-06-02T09:00:00Z"},
                {"id": "n3", "corpo": "terceira", "autor_id": "P1", "created_at": "2026-06-03T09:00:00Z"},
            ],
        )
        client = make_client(sb, me=me)

        h = client.get("/api/notas")
        assert h.status_code == 200
        corpos = [n["corpo"] for n in h.json()]
        assert corpos == ["terceira", "segunda", "primeira"]


# ═══════════════════════════════════════════════════════════════════════════
# Abrir e editar
# ═══════════════════════════════════════════════════════════════════════════


class TestAbrirEEditar:
    def test_autor_abre_e_edita_o_corpo_da_nota(self, make_client):
        """Critério 3: o autor abre uma Nota existente e edita o corpo livre."""
        me = _participante("P1")
        sb = _SupabaseMock(
            participantes=[me],
            notas=[{"id": "n1", "corpo": "texto original", "autor_id": "P1", "created_at": "2026-06-01T09:00:00Z"}],
        )
        client = make_client(sb, me=me)

        # Abre a Nota.
        r = client.get("/api/notas/n1")
        assert r.status_code == 200
        assert r.json()["corpo"] == "texto original"

        # Edita o corpo.
        u = client.patch("/api/notas/n1", json={"corpo": "texto corrigido com o nome certo"})
        assert u.status_code == 200
        assert u.json()["corpo"] == "texto corrigido com o nome certo"

        # A edição persistiu.
        r2 = client.get("/api/notas/n1")
        assert r2.json()["corpo"] == "texto corrigido com o nome certo"


# ═══════════════════════════════════════════════════════════════════════════
# Arquivar (soft-delete)
# ═══════════════════════════════════════════════════════════════════════════


class TestArquivar:
    def test_arquivar_nota_e_soft_delete_sem_hard_delete(self, make_client):
        """Critério 4: arquivar tira a Nota do histórico ativo via soft-delete
        (`deleted_at`), sem hard-delete — a linha permanece no banco."""
        me = _participante("P1")
        sb = _SupabaseMock(
            participantes=[me],
            notas=[
                {"id": "n1", "corpo": "registro de feedback", "autor_id": "P1", "created_at": "2026-06-01T09:00:00Z"}
            ],
        )
        client = make_client(sb, me=me)

        d = client.delete("/api/notas/n1")
        assert d.status_code == 200

        # Soft-delete: a linha CONTINUA no banco, marcada com deleted_at.
        assert len(sb.notas) == 1
        assert sb.notas[0]["deleted_at"] is not None

        # Sai do histórico ativo.
        h = client.get("/api/notas")
        assert h.json() == []

        # E não abre mais — está arquivada.
        r = client.get("/api/notas/n1")
        assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════
# Guardas de acesso (espelham a Reunião)
# ═══════════════════════════════════════════════════════════════════════════


class TestAcesso:
    def test_outro_facilitador_nao_enxerga_nota_alheia(self, make_client):
        """Critério 5/6: um Facilitador regular não vê — nem abre, edita ou
        arquiva — Notas que não são dele."""
        sb = _SupabaseMock(
            participantes=[_participante("P1"), _participante("P2")],
            notas=[{"id": "n1", "corpo": "feedback privado", "autor_id": "P1", "created_at": "2026-06-01T09:00:00Z"}],
        )
        # Logado como P2 — outro Facilitador regular.
        client = make_client(sb, me=_participante("P2"))

        assert client.get("/api/notas").json() == []
        assert client.get("/api/notas/n1").status_code == 404
        assert client.patch("/api/notas/n1", json={"corpo": "invadindo"}).status_code == 404
        assert client.delete("/api/notas/n1").status_code == 404

        # A Nota do autor permanece intacta.
        assert sb.notas[0]["corpo"] == "feedback privado"
        assert sb.notas[0].get("deleted_at") is None

    def test_secretaria_enxerga_todas_as_notas(self, make_client):
        """Critério 5/6: a Secretária tem visão global — vê as Notas de todos.
        Sua visão é de leitura: não edita Nota alheia."""
        sb = _SupabaseMock(
            participantes=[_participante("P1"), _participante("P2")],
            notas=[
                {"id": "n1", "corpo": "do P1", "autor_id": "P1", "created_at": "2026-06-01T09:00:00Z"},
                {"id": "n2", "corpo": "do P2", "autor_id": "P2", "created_at": "2026-06-02T09:00:00Z"},
            ],
        )
        client = make_client(sb, me=_participante("P9", "secretaria"))

        ids = {n["id"] for n in client.get("/api/notas").json()}
        assert ids == {"n1", "n2"}
        assert client.get("/api/notas/n1").status_code == 200
        assert client.get("/api/notas/n2").status_code == 200
        # Vê, mas não edita Nota alheia (visão de leitura).
        assert client.patch("/api/notas/n1", json={"corpo": "x"}).status_code == 403

    def test_super_admin_enxerga_e_edita_qualquer_nota(self, make_client):
        """Critério 5/6 + ADR 0004: o Super admin espelha o poder irrestrito que
        já tem sobre Reuniões/Atas — vê, edita e arquiva qualquer Nota."""
        sb = _SupabaseMock(
            participantes=[_participante("P1"), _participante("P2")],
            notas=[
                {"id": "n1", "corpo": "do P1", "autor_id": "P1", "created_at": "2026-06-01T09:00:00Z"},
                {"id": "n2", "corpo": "do P2", "autor_id": "P2", "created_at": "2026-06-02T09:00:00Z"},
            ],
        )
        client = make_client(sb, me=_participante("P0", "super_admin"))

        ids = {n["id"] for n in client.get("/api/notas").json()}
        assert ids == {"n1", "n2"}

        # Edita Nota alheia.
        u = client.patch("/api/notas/n1", json={"corpo": "corrigido pelo super admin"})
        assert u.status_code == 200
        assert u.json()["corpo"] == "corrigido pelo super admin"

        # Arquiva Nota alheia.
        assert client.delete("/api/notas/n2").status_code == 200
        assert sb.notas[1]["deleted_at"] is not None
