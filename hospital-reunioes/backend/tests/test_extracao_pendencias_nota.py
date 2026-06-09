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
from app.services import extracao_pendencias_service as extracao  # noqa: E402

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


# ═══════════════════════════════════════════════════════════════════════════
# Service: extracao_pendencias_service.extrair (LLM 100% mockado)
# ═══════════════════════════════════════════════════════════════════════════


HOJE = "2026-06-09"  # terça-feira — base fixa para prazos relativos determinísticos


def _roster_cadastrado(pid: str, nome: str) -> dict:
    return {"participante_id": pid, "nome_avulso": None, "nome": nome}


def _roster_avulso(nome: str) -> dict:
    return {"participante_id": None, "nome_avulso": nome, "nome": nome}


@pytest.fixture
def llm_mock(monkeypatch):
    """Substitui 100% a chamada LLM do service: devolve o JSON programado e
    registra as chamadas — nenhum teste toca provider/chave real."""

    class _Spy:
        def __init__(self):
            self.resposta: dict = {"pendencias": []}
            self.chamadas: list = []

    spy = _Spy()

    def _fake_chamar_llm(*args, **kwargs):
        spy.chamadas.append((args, kwargs))
        return spy.resposta

    monkeypatch.setattr(extracao, "_chamar_llm", _fake_chamar_llm)
    return spy


class TestExtrairPendencias:
    def test_ia_propoe_pendencia_com_responsavel_casado_no_roster(self, llm_mock):
        """Critérios 2 e 3: a IA propõe Pendências a partir do corpo —
        responsável interno casa pro Colaborador certo do roster (vira
        responsavel_id + nome canônico) e o prazo absoluto passa direto."""
        sb = _SupabaseMock(participantes=[{"id": "P2", "nome_completo": "Ana Lima", "cargo": "Coordenadora"}])
        llm_mock.resposta = {
            "pendencias": [{"descricao": "Enviar orçamento ao aliado", "responsavel": "Ana", "prazo": "2026-06-12"}]
        }

        propostas = extracao.extrair(
            sb,
            corpo="Conversa com a Ana: ela envia o orçamento até sexta.",
            roster=[_roster_cadastrado("P2", "Ana Lima")],
            hoje=HOJE,
        )

        assert propostas == [
            {
                "descricao_acao": "Enviar orçamento ao aliado",
                "responsavel_id": "P2",
                "responsavel_nome": "Ana Lima",
                "prazo": "2026-06-12",
            }
        ]
        assert len(llm_mock.chamadas) == 1

    def test_responsavel_externo_fica_so_como_nome_sem_id(self, llm_mock):
        """Critério 3: externo não vira responsável real — quem casa no nome
        avulso do roster herda a grafia do roster; quem não casa em lugar
        nenhum fica com o nome como veio. Ambos sem responsavel_id."""
        sb = _SupabaseMock(participantes=[])
        llm_mock.resposta = {
            "pendencias": [
                {"descricao": "Mandar proposta", "responsavel": "fulano aliado", "prazo": None},
                {"descricao": "Agendar visita", "responsavel": "Dr. Desconhecido", "prazo": None},
                {"descricao": "Definir pauta da próxima conversa", "responsavel": None, "prazo": None},
            ]
        }

        propostas = extracao.extrair(
            sb,
            corpo="O Fulano Aliado manda a proposta; alguém agenda a visita do Dr. Desconhecido.",
            roster=[_roster_avulso("Fulano Aliado")],
            hoje=HOJE,
        )

        assert [(p["responsavel_id"], p["responsavel_nome"]) for p in propostas] == [
            (None, "Fulano Aliado"),  # casou no avulso do roster → grafia do roster
            (None, "Dr. Desconhecido"),  # sem match → nome como veio
            (None, None),  # IA não apontou responsável
        ]

    def test_roster_tem_prioridade_sobre_cadastro_e_cadastro_e_fallback(self, llm_mock):
        """Critério 3: "Ana" casa pra Ana DO ROSTER mesmo havendo outra Ana no
        cadastro (o roster afia o casamento); quem não está no roster mas está
        no cadastro casa pelo cadastro, com nome canônico."""
        sb = _SupabaseMock(
            participantes=[
                {"id": "P5", "nome_completo": "Ana Souza", "cargo": "Gerente"},  # homônima fora do roster
                {"id": "P2", "nome_completo": "Ana Lima", "cargo": "Coordenadora"},
                {"id": "P7", "nome_completo": "Carlos Ferreira", "cargo": "Coordenador Financeiro"},
            ]
        )
        llm_mock.resposta = {
            "pendencias": [
                {"descricao": "Revisar protocolo", "responsavel": "Ana", "prazo": None},
                {"descricao": "Fechar orçamento", "responsavel": "Carlos", "prazo": None},
            ]
        }

        propostas = extracao.extrair(
            sb,
            corpo="Ana revisa o protocolo e Carlos fecha o orçamento.",
            roster=[_roster_cadastrado("P2", "Ana Lima")],
            hoje=HOJE,
        )

        assert [(p["responsavel_id"], p["responsavel_nome"]) for p in propostas] == [
            ("P2", "Ana Lima"),  # roster primeiro — não cai na Ana Souza do cadastro
            ("P7", "Carlos Ferreira"),  # fora do roster → fallback no cadastro, nome canônico
        ]

    def test_prazo_em_linguagem_natural_vira_data_na_proposta(self, llm_mock):
        """Critério 4: quando a IA devolve a expressão crua em vez da data,
        o parse determinístico converte com a data base (9/6/2026, terça):
        "sexta" → a próxima sexta; "semana que vem" → +7; formato brasileiro
        é normalizado; expressão irreconhecível fica sem prazo (editável)."""
        sb = _SupabaseMock(participantes=[])
        llm_mock.resposta = {
            "pendencias": [
                {"descricao": "Enviar orçamento", "responsavel": None, "prazo": "sexta"},
                {"descricao": "Cobrar retorno", "responsavel": None, "prazo": "até sexta-feira"},
                {"descricao": "Agendar conversa", "responsavel": None, "prazo": "semana que vem"},
                {"descricao": "Repassar feedback", "responsavel": None, "prazo": "terça"},
                {"descricao": "Emitir nota", "responsavel": None, "prazo": "12/06/2026"},
                {"descricao": "Revisar escala", "responsavel": None, "prazo": "quando der"},
            ]
        }

        propostas = extracao.extrair(sb, corpo="combinados da conversa", roster=[], hoje=HOJE)

        assert [p["prazo"] for p in propostas] == [
            "2026-06-12",  # sexta desta semana (hoje é terça 09/06)
            "2026-06-12",  # prefixo "até" + sufixo "-feira" não atrapalham
            "2026-06-16",  # +7
            "2026-06-16",  # "terça" sendo terça hoje → a PRÓXIMA, nunca hoje
            "2026-06-12",  # DD/MM/YYYY normalizado
            None,  # irreconhecível → sem prazo, Facilitador edita
        ]

    def test_corpo_vazio_devolve_lista_vazia_sem_chamar_a_ia(self, llm_mock):
        """Critério 7: corpo vazio ou só espaços → nenhuma proposta e a IA nem
        é chamada (sem custo, sem erro)."""
        sb = _SupabaseMock(participantes=[])

        assert extracao.extrair(sb, corpo="", roster=[], hoje=HOJE) == []
        assert extracao.extrair(sb, corpo="   \n  ", roster=[], hoje=HOJE) == []
        assert llm_mock.chamadas == []

    def test_corpo_sem_acoes_devolve_lista_vazia_sem_erro(self, llm_mock):
        """Critério 6: corpo com conteúdo mas sem nenhuma ação → a IA devolve
        lista vazia e a extração repassa, sem erro. Itens sem descrição que a
        IA alucinar são descartados."""
        sb = _SupabaseMock(participantes=[])

        llm_mock.resposta = {"pendencias": []}
        assert extracao.extrair(sb, corpo="Conversa boa, sem encaminhamentos.", roster=[], hoje=HOJE) == []

        llm_mock.resposta = {"pendencias": [{"descricao": "   ", "responsavel": "Ana", "prazo": None}]}
        assert extracao.extrair(sb, corpo="Conversa boa.", roster=[], hoje=HOJE) == []
