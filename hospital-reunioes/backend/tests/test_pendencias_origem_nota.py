"""Testes da Pendência com origem **Nota** — add manual (issue #33, ADR 0004).

A Pendência passa a nascer de duas origens: de uma Reunião que chega a estado
terminal (ASSINADA/APROVADA) ou direto de uma **Nota**. Nesta fatia o
Facilitador adiciona a Pendência à mão (descrição, responsável do cadastro,
prazo) e ela cai no mesmo acompanhamento das demais — painel, alerta de
atraso, Repactuação e comentários.

Escopo: comportamento observável do `pendencia_service` (origem correta, IDs
`A###` sequenciais, idempotência) e dos endpoints. Mock Supabase fluente
espelhado de `test_notas.py`/`test_aprovar_sem_assinatura.py`.
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
from app.routers import comentarios as comentarios_router  # noqa: E402
from app.routers import notas as notas_router  # noqa: E402
from app.routers import pendencias as pendencias_router  # noqa: E402
from app.services.pendencia_service import criar_pendencias_de_nota  # noqa: E402

# ─── Mock Supabase ───────────────────────────────────────────────────────────


@dataclass
class _Result:
    data: Any
    count: int | None = None


def _parse_or_expr(expr: str) -> list[tuple[str, str, str]]:
    """Parseia uma expressão `or` do PostgREST em termos (col, op, valor).

    Suporta o subset usado pelo router: `col.eq.valor` e `col.in.(a,b,c)`.
    """
    termos: list[tuple[str, str, str]] = []
    depth = 0
    atual = ""
    for ch in expr + ",":
        if ch == "," and depth == 0:
            if atual:
                col, op, valor = atual.split(".", 2)
                termos.append((col, op, valor))
            atual = ""
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        atual += ch
    return termos


class _TableQuery:
    """Mock fluente: select/insert/update/delete + eq/in_/is_/ilike/or_/order/range/limit.

    `autoid` espelha os defaults do Postgres (id UUID + created_at) no insert —
    usado pela tabela de comentários, cujo response exige esses campos.
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
        self._or: str | None = None
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

    def or_(self, expr):
        self._or = expr
        return self

    def order(self, col, desc=False, **_kw):
        self._order = (col, desc)
        return self

    def range(self, _start, _end):
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
        if self._or is not None:
            algum = False
            for col, op, valor in _parse_or_expr(self._or):
                if op == "eq" and r.get(col) == valor:
                    algum = True
                elif op == "in" and r.get(col) in valor.strip("()").split(","):
                    algum = True
            if not algum:
                return False
        return True

    def execute(self):
        if self._op == "insert":
            items = self._payload if isinstance(self._payload, list) else [self._payload]
            inserted = []
            for it in items:
                row = dict(it)
                if self._autoid:
                    row.setdefault("id", f"c{len(self._rows) + 1}")
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


class _Rpc:
    def execute(self):
        return _Result(data=None)


@dataclass
class _SupabaseMock:
    participantes: list = field(default_factory=list)
    notas: list = field(default_factory=list)
    pendencias: list = field(default_factory=list)
    comentarios: list = field(default_factory=list)
    rpc_calls: list = field(default_factory=list)

    def table(self, name: str):
        if name == "participantes":
            return _TableQuery(self.participantes)
        if name == "notas":
            return _TableQuery(self.notas)
        if name == "pendencias":
            return _TableQuery(self.pendencias)
        if name == "comentarios_pendencias":
            return _TableQuery(self.comentarios, autoid=True)
        raise AssertionError(f"Tabela inesperada: {name}")

    def rpc(self, name: str, params: dict | None = None):
        self.rpc_calls.append((name, params))
        return _Rpc()


# ─── App fixture (endpoint de add manual no router de notas) ────────────────


CURRENT_USER = {"id": "auth-uid-1", "email": "diretor@hospital.com"}


def _participante(pid: str, profile: str = "regular") -> dict:
    """Participante logado. `profile` ∈ {regular, secretaria, super_admin}."""
    return {"id": pid, "nome_completo": f"Facilitador {pid}", "access_profile": profile}


def _nota(nid: str, autor: str) -> dict:
    return {"id": nid, "corpo": f"nota {nid}", "autor_id": autor, "created_at": "2026-06-01T09:00:00Z"}


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


@pytest.fixture
def make_client_pendencias(monkeypatch):
    """Factory: TestClient do router de pendências como Facilitador **regular**.

    `allowed` é a lista de reuniões visíveis (visibilidade binária do painel);
    a Pendência origem Nota deve abrir caminho próprio: a Nota é do usuário.
    """

    def _factory(supabase: _SupabaseMock, *, me: dict, allowed: list[str]) -> TestClient:
        app = FastAPI()
        app.include_router(pendencias_router.router, prefix="/api")

        app.dependency_overrides[get_current_user] = lambda: CURRENT_USER
        app.dependency_overrides[get_supabase_client] = lambda: supabase

        async def _fake_get_participante(*_a, **_kw):
            return dict(me)

        async def _fake_allowed(*_a, **_kw):
            return list(allowed)

        async def _fake_my_id(*_a, **_kw):
            return me["id"]

        monkeypatch.setattr(pendencias_router, "get_participante_for_user", _fake_get_participante)
        monkeypatch.setattr(pendencias_router, "get_allowed_reuniao_ids", _fake_allowed)
        monkeypatch.setattr(pendencias_router, "get_participante_id_for_user", _fake_my_id)
        return TestClient(app)

    return _factory


# ═══════════════════════════════════════════════════════════════════════════
# Service: criar_pendencias_de_nota
# ═══════════════════════════════════════════════════════════════════════════


class TestCriarPendenciasDeNota:
    def test_pendencia_de_nota_nasce_com_origem_nota_e_id_sequencial(self):
        """Critério 3: a Pendência criada de uma Nota nasce com `id_nota`
        setado e `id_reuniao` nulo, com ID `A###` sequencial e status PENDENTE
        — cai no mesmo acompanhamento das demais."""
        sb = _SupabaseMock(
            pendencias=[{"id_acao": "A007", "id_reuniao": "R1", "descricao_acao": "antiga", "status": "PENDENTE"}],
        )

        criadas = criar_pendencias_de_nota(
            sb,
            id_nota="n1",
            confirmadas=[{"descricao_acao": "Enviar orçamento ao aliado", "prazo": "2026-06-12"}],
        )

        assert len(criadas) == 1
        nova = criadas[0]
        assert nova["id_nota"] == "n1"
        assert nova["id_reuniao"] is None
        assert nova["id_acao"] == "A008"  # continua a sequência global A###
        assert nova["status"] == "PENDENTE"
        assert nova["descricao_acao"] == "Enviar orçamento ao aliado"
        assert nova["prazo"] == "2026-06-12"

        # Persistiu na tabela `pendencias` — mesmo lugar das demais.
        assert len(sb.pendencias) == 2

    def test_reexecutar_a_mesma_criacao_nao_duplica_mas_aceita_novo_add(self):
        """Critério 6: a criação é idempotente — reexecutar com a mesma lista
        (retry/double-click) não duplica. Um add manual NOVO na mesma Nota
        continua entrando: a Nota acumula Pendências ao longo do tempo."""
        sb = _SupabaseMock()

        primeira = criar_pendencias_de_nota(
            sb,
            id_nota="n1",
            confirmadas=[{"descricao_acao": "Enviar orçamento", "prazo": "2026-06-12"}],
        )
        assert len(primeira) == 1

        # Reexecução idêntica: nada novo.
        repetida = criar_pendencias_de_nota(
            sb,
            id_nota="n1",
            confirmadas=[{"descricao_acao": "Enviar orçamento", "prazo": "2026-06-12"}],
        )
        assert repetida == []
        assert len(sb.pendencias) == 1

        # Add manual de uma Pendência diferente na MESMA Nota: entra normal.
        nova = criar_pendencias_de_nota(
            sb,
            id_nota="n1",
            confirmadas=[{"descricao_acao": "Agendar reunião de follow-up", "prazo": "2026-06-20"}],
        )
        assert len(nova) == 1
        assert len(sb.pendencias) == 2
        assert nova[0]["id_acao"] == "A002"

    def test_responsavel_escolhido_do_cadastro_resolve_nome_e_cargo_canonicos(self):
        """Critério 2: o responsável é escolhido do cadastro — a Pendência
        nasce com nome e cargo canônicos do Participante, e o prazo em formato
        brasileiro é normalizado para o Postgres (YYYY-MM-DD)."""
        sb = _SupabaseMock(
            participantes=[{"id": "P2", "nome_completo": "Ana Lima", "cargo": "Coordenadora"}],
        )

        criadas = criar_pendencias_de_nota(
            sb,
            id_nota="n1",
            confirmadas=[
                {"descricao_acao": "Revisar protocolo", "responsavel_id": "P2", "prazo": "12/06/2026"},
            ],
        )

        assert len(criadas) == 1
        nova = criadas[0]
        assert nova["responsavel_id"] == "P2"
        assert nova["responsavel_nome"] == "Ana Lima"
        assert nova["cargo"] == "Coordenadora"
        assert nova["prazo"] == "2026-06-12"


# ═══════════════════════════════════════════════════════════════════════════
# Endpoint: POST /notas/{id_nota}/pendencias (add manual)
# ═══════════════════════════════════════════════════════════════════════════


class TestAddManualNaNota:
    def test_facilitador_adiciona_pendencia_manual_a_sua_nota(self, make_client):
        """Critério 2: dentro de uma Nota sua, o Facilitador adiciona uma
        Pendência à mão (descrição, responsável do cadastro, prazo) e ela nasce
        com a origem correta."""
        me = _participante("P1")
        sb = _SupabaseMock(
            participantes=[me, {"id": "P2", "nome_completo": "Ana Lima", "cargo": "Coordenadora"}],
            notas=[_nota("n1", autor="P1")],
        )
        client = make_client(sb, me=me)

        r = client.post(
            "/api/notas/n1/pendencias",
            json={
                "pendencias": [
                    {"descricao_acao": "Enviar orçamento ao aliado", "responsavel_id": "P2", "prazo": "2026-06-12"}
                ]
            },
        )

        assert r.status_code == 201
        criadas = r.json()
        assert len(criadas) == 1
        assert criadas[0]["id_nota"] == "n1"
        assert criadas[0]["id_reuniao"] is None
        assert criadas[0]["id_acao"] == "A001"
        assert criadas[0]["responsavel_nome"] == "Ana Lima"
        assert criadas[0]["status"] == "PENDENTE"

        # Persistiu na tabela compartilhada de pendências.
        assert len(sb.pendencias) == 1

    def test_outro_facilitador_nao_adiciona_pendencia_a_nota_alheia(self, make_client):
        """A Nota é privada — outro Facilitador regular nem a enxerga (404,
        anti-enumeration) e nada é criado."""
        sb = _SupabaseMock(
            participantes=[_participante("P1"), _participante("P2")],
            notas=[_nota("n1", autor="P1")],
        )
        client = make_client(sb, me=_participante("P2"))

        r = client.post(
            "/api/notas/n1/pendencias",
            json={"pendencias": [{"descricao_acao": "invadindo"}]},
        )
        assert r.status_code == 404
        assert sb.pendencias == []

    def test_secretaria_ve_a_nota_mas_nao_adiciona_pendencia(self, make_client):
        """A Secretária tem visão global de leitura das Notas, mas não age
        sobre Pendências (espelha o gate 403 do painel)."""
        sb = _SupabaseMock(
            participantes=[_participante("P1")],
            notas=[_nota("n1", autor="P1")],
        )
        client = make_client(sb, me=_participante("P9", "secretaria"))

        r = client.post(
            "/api/notas/n1/pendencias",
            json={"pendencias": [{"descricao_acao": "como secretária"}]},
        )
        assert r.status_code == 403
        assert sb.pendencias == []

    def test_super_admin_adiciona_pendencia_a_nota_alheia(self, make_client):
        """O Super admin espelha o poder irrestrito que já tem sobre a Nota —
        adiciona Pendência em Nota de qualquer autor."""
        sb = _SupabaseMock(
            participantes=[_participante("P1")],
            notas=[_nota("n1", autor="P1")],
        )
        client = make_client(sb, me=_participante("P0", "super_admin"))

        r = client.post(
            "/api/notas/n1/pendencias",
            json={"pendencias": [{"descricao_acao": "ajuste do super admin"}]},
        )
        assert r.status_code == 201
        assert len(sb.pendencias) == 1
        assert sb.pendencias[0]["id_nota"] == "n1"

    def test_nota_arquivada_nao_aceita_pendencia_nova(self, make_client):
        """Nota arquivada (soft-delete) sai do fluxo ativo: não recebe
        Pendências novas — as já criadas seguem independentes."""
        me = _participante("P1")
        nota_arquivada = {**_nota("n1", autor="P1"), "deleted_at": "2026-06-05T10:00:00Z"}
        sb = _SupabaseMock(participantes=[me], notas=[nota_arquivada])
        client = make_client(sb, me=me)

        r = client.post(
            "/api/notas/n1/pendencias",
            json={"pendencias": [{"descricao_acao": "tarde demais"}]},
        )
        assert r.status_code == 404
        assert sb.pendencias == []

    def test_pendencia_sem_descricao_e_rejeitada(self, make_client):
        """Descrição é obrigatória no add manual — payload vazio é 422."""
        me = _participante("P1")
        sb = _SupabaseMock(participantes=[me], notas=[_nota("n1", autor="P1")])
        client = make_client(sb, me=me)

        assert (
            client.post("/api/notas/n1/pendencias", json={"pendencias": [{"descricao_acao": ""}]}).status_code == 422
        )
        assert client.post("/api/notas/n1/pendencias", json={"pendencias": []}).status_code == 422
        assert sb.pendencias == []


# ═══════════════════════════════════════════════════════════════════════════
# Painel: os pontos que assumiam Reunião de origem tratam a origem Nota
# ═══════════════════════════════════════════════════════════════════════════


def _pendencia_de_nota(id_acao: str, id_nota: str, **extra) -> dict:
    return {
        "id_acao": id_acao,
        "id_reuniao": None,
        "id_nota": id_nota,
        "descricao_acao": f"pendência da nota {id_nota}",
        "responsavel_id": None,
        "co_responsavel_id": None,
        "status": "PENDENTE",
        **extra,
    }


class TestVisibilidadeNoPainel:
    def test_autor_da_nota_abre_a_pendencia_dela_no_painel(self, make_client_pendencias):
        """Critério 5: o GET de uma Pendência origem Nota não assume Reunião —
        o autor da Nota a enxerga, mesmo sem reunião alguma visível."""
        me = _participante("P1")
        sb = _SupabaseMock(
            participantes=[me],
            notas=[_nota("n1", autor="P1")],
            pendencias=[_pendencia_de_nota("A001", "n1")],
        )
        client = make_client_pendencias(sb, me=me, allowed=[])

        r = client.get("/api/pendencias/A001")
        assert r.status_code == 200
        body = r.json()
        assert body["id_acao"] == "A001"
        assert body["id_nota"] == "n1"
        assert body["id_reuniao"] is None

    def test_outro_facilitador_nao_abre_pendencia_de_nota_alheia(self, make_client_pendencias):
        """A privacidade da Nota se estende à sua Pendência: outro Facilitador
        regular recebe 404 (anti-enumeration)."""
        sb = _SupabaseMock(
            participantes=[_participante("P1"), _participante("P2")],
            notas=[_nota("n1", autor="P1")],
            pendencias=[_pendencia_de_nota("A001", "n1")],
        )
        client = make_client_pendencias(sb, me=_participante("P2"), allowed=[])

        assert client.get("/api/pendencias/A001").status_code == 404

    def test_pendencia_de_nota_conclui_e_repactua_como_qualquer_outra(self, make_client_pendencias):
        """Critério 4: a Pendência origem Nota responde ao mesmo ciclo das
        demais — concluir e Repactuar funcionam, sem tocar o contador de ações
        de Reunião (não há Reunião de origem)."""
        me = _participante("P1")
        sb = _SupabaseMock(
            participantes=[me],
            notas=[_nota("n1", autor="P1")],
            pendencias=[_pendencia_de_nota("A001", "n1", prazo="2026-06-12")],
        )
        client = make_client_pendencias(sb, me=me, allowed=[])

        # Conclui.
        r = client.patch("/api/pendencias/A001", json={"status": "CONCLUIDO"})
        assert r.status_code == 200
        assert r.json()["status"] == "CONCLUIDO"
        # Não há Reunião de origem: o contador acoes_concluidas não é tocado.
        assert sb.rpc_calls == []

        # Repactua: vira REPACTUADA e o prazo é limpo (vai ganhar Pendência nova).
        r2 = client.patch("/api/pendencias/A001", json={"status": "REPACTUADA"})
        assert r2.status_code == 200
        assert r2.json()["status"] == "REPACTUADA"
        assert sb.pendencias[0]["prazo"] is None
        assert sb.rpc_calls == []

    def test_painel_do_autor_lista_pendencia_de_nota_junto_das_demais(self, make_client_pendencias):
        """Critério 4: a Pendência origem Nota aparece no painel/kanban do
        autor junto das de Reunião — e some do painel de quem não deve ver.
        Os contadores (stats) acompanham."""
        me = _participante("P1")
        sb = _SupabaseMock(
            participantes=[me, _participante("P2")],
            notas=[_nota("n1", autor="P1"), _nota("n2", autor="P2")],
            pendencias=[
                {"id_acao": "A001", "id_reuniao": "R1", "id_nota": None, "descricao_acao": "de reunião", "status": "PENDENTE"},  # noqa: E501
                _pendencia_de_nota("A002", "n1"),
                _pendencia_de_nota("A003", "n2"),  # Nota de OUTRO autor
                {"id_acao": "A004", "id_reuniao": "R9", "id_nota": None, "descricao_acao": "reunião alheia", "status": "PENDENTE"},  # noqa: E501
            ],
        )
        client = make_client_pendencias(sb, me=me, allowed=["R1"])

        # Painel: a da minha Reunião + a da minha Nota; nada das alheias.
        r = client.get("/api/pendencias")
        assert r.status_code == 200
        ids = {p["id_acao"] for p in r.json()}
        assert ids == {"A001", "A002"}

        # Contadores do dashboard acompanham o painel.
        s = client.get("/api/pendencias/stats")
        assert s.status_code == 200
        assert s.json()["pendente"] == 2
        assert s.json()["total"] == 2


# ═══════════════════════════════════════════════════════════════════════════
# Comentários: a Pendência de Nota conversa como qualquer outra
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture
def make_client_comentarios(monkeypatch):
    """Factory: TestClient do router de comentários como Facilitador regular."""

    def _factory(supabase: _SupabaseMock, *, me: dict, allowed: list[str]) -> TestClient:
        app = FastAPI()
        app.include_router(comentarios_router.router, prefix="/api")

        app.dependency_overrides[get_current_user] = lambda: CURRENT_USER
        app.dependency_overrides[get_supabase_client] = lambda: supabase

        async def _fake_get_participante(*_a, **_kw):
            return dict(me)

        async def _fake_allowed(*_a, **_kw):
            return list(allowed)

        monkeypatch.setattr(comentarios_router, "get_participante_for_user", _fake_get_participante)
        monkeypatch.setattr(comentarios_router, "get_allowed_reuniao_ids", _fake_allowed)
        return TestClient(app)

    return _factory


class TestComentariosEmPendenciaDeNota:
    def test_autor_da_nota_comenta_na_pendencia_como_em_qualquer_outra(self, make_client_comentarios):
        """Critério 4: comentários funcionam na Pendência origem Nota — o
        autor da Nota cria e lista comentários; quem não vê a Nota, não vê."""
        me = _participante("P1")
        sb = _SupabaseMock(
            participantes=[me],
            notas=[_nota("n1", autor="P1")],
            pendencias=[_pendencia_de_nota("A001", "n1")],
        )
        client = make_client_comentarios(sb, me=me, allowed=[])

        # Cria um comentário.
        c = client.post("/api/pendencias/A001/comentarios", json={"conteudo": "Cobrei por telefone hoje."})
        assert c.status_code == 201

        # Lista de volta.
        lista = client.get("/api/pendencias/A001/comentarios")
        assert lista.status_code == 200
        assert [x["conteudo"] for x in lista.json()] == ["Cobrei por telefone hoje."]

    def test_outro_facilitador_nao_comenta_pendencia_de_nota_alheia(self, make_client_comentarios):
        sb = _SupabaseMock(
            participantes=[_participante("P1"), _participante("P2")],
            notas=[_nota("n1", autor="P1")],
            pendencias=[_pendencia_de_nota("A001", "n1")],
        )
        client = make_client_comentarios(sb, me=_participante("P2"), allowed=[])

        assert client.get("/api/pendencias/A001/comentarios").status_code == 404
        assert (
            client.post("/api/pendencias/A001/comentarios", json={"conteudo": "intrometido"}).status_code == 404
        )
        assert sb.comentarios == []
