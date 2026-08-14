"""Testes do painel de ouvidoria (issue #292, ADR 0031 decisão 3).

Cobre (critérios de aceite):
- Facilitador e secretária veem a lista com prazo e status.
- Mudar o status para respondido persiste e aparece na consulta da API da Ana.
- Não existe caminho no painel para criar protocolo nem para ver dado pessoal.
- Rota de mudança de status: papéis e persistência.
"""

from __future__ import annotations

import os
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.dependencies import get_current_user, get_supabase_client  # noqa: E402
from app.limiter import limiter  # noqa: E402
from app.middleware.request_context import RequestContextMiddleware  # noqa: E402
from app.routers import ouvidoria as ouvidoria_router  # noqa: E402

FACILITADOR = {"id": "P01", "nome_completo": "Ana Facilitadora", "access_profile": "regular"}
SECRETARIA = {"id": "P02", "nome_completo": "Sofia Secretaria", "access_profile": "secretaria"}
SUPER_ADMIN = {"id": "P03", "nome_completo": "Pedro Admin", "access_profile": "super_admin"}
POPS_SEM_REUNIOES = {"id": "P04", "nome_completo": "Carlos POPs", "access_profile": None}


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


def _protocolo_row(numero: int = 7, **overrides) -> dict:
    row = {
        "id": f"uuid-{numero}",
        "numero": numero,
        "protocolo": f"2026-{numero:04d}",
        "data_abertura": "2026-08-14",
        "prazo_resposta": "2026-08-21",
        "status": "aberto",
        "categoria": "Demora",
        "setor": "Recepcao",
        "resumo": "Paciente relata espera acima de duas horas na recepcao.",
        "conversa_id": "conv-4711",
    }
    row.update(overrides)
    return row


class _Query:
    def __init__(self, rows: list[dict]):
        self._rows = rows
        self._filters: dict = {}
        self._order: tuple[str, bool] | None = None
        self._pending_update: dict | None = None

    def select(self, *_a, **_kw):
        return self

    def update(self, payload: dict):
        self._pending_update = payload
        return self

    def eq(self, col, value):
        self._filters[col] = value
        return self

    def order(self, col, desc=False):
        self._order = (col, desc)
        return self

    def execute(self):
        matched = [r for r in self._rows if all(r.get(c) == v for c, v in self._filters.items())]
        if self._order is not None:
            col, desc = self._order
            matched.sort(key=lambda r: r[col], reverse=desc)
        if self._pending_update is not None:
            for r in matched:
                r.update(self._pending_update)
        return type("R", (), {"data": [dict(r) for r in matched]})()


class _SupabaseMock:
    def __init__(self, rows: list[dict]):
        self.rows = rows

    def table(self, name: str):
        assert name == "ouvidoria_protocolos", f"Tabela inesperada: {name}"
        return _Query(self.rows)


def _make_client(monkeypatch, participante: dict | None, rows: list[dict] | None = None) -> TestClient:
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(RequestContextMiddleware)
    app.include_router(ouvidoria_router.router, prefix="/api")

    supabase = _SupabaseMock(rows if rows is not None else [_protocolo_row()])

    async def _fake_participante(_user, _sb, fields=None):
        return participante

    monkeypatch.setattr(ouvidoria_router, "get_participante_for_user", _fake_participante)
    app.dependency_overrides[get_current_user] = lambda: {"id": "u1", "email": "u@hsm.br"}
    app.dependency_overrides[get_supabase_client] = lambda: supabase
    return TestClient(app)


class TestListaDoPainel:
    @pytest.mark.parametrize("papel", [FACILITADOR, SECRETARIA, SUPER_ADMIN])
    def test_facilitador_e_secretaria_veem_lista_com_prazo_e_status(self, monkeypatch, papel):
        client = _make_client(monkeypatch, papel)

        r = client.get("/api/ouvidoria/protocolos")

        assert r.status_code == 200
        protocolos = r.json()["protocolos"]
        assert len(protocolos) == 1
        p = protocolos[0]
        assert p["protocolo"] == "2026-0007"
        assert p["prazo_resposta"] == "2026-08-21"
        assert p["status"] == "aberto"
        assert p["categoria"] == "Demora"
        assert p["setor"] == "Recepcao"

    def test_lista_vem_com_mais_recentes_primeiro(self, monkeypatch):
        rows = [_protocolo_row(numero=3), _protocolo_row(numero=8), _protocolo_row(numero=5)]
        client = _make_client(monkeypatch, SECRETARIA, rows=rows)

        r = client.get("/api/ouvidoria/protocolos")

        assert r.status_code == 200
        assert [p["numero"] for p in r.json()["protocolos"]] == [8, 5, 3]

    @pytest.mark.parametrize("sem_acesso", [POPS_SEM_REUNIOES, None])
    def test_quem_nao_e_da_equipe_de_reunioes_recebe_403(self, monkeypatch, sem_acesso):
        client = _make_client(monkeypatch, sem_acesso)

        r = client.get("/api/ouvidoria/protocolos")

        assert r.status_code == 403

    def test_sem_login_recebe_401(self, monkeypatch):
        client = _make_client(monkeypatch, FACILITADOR)
        client.app.dependency_overrides.pop(get_current_user)

        r = client.get("/api/ouvidoria/protocolos")

        assert r.status_code in (401, 403)


CHAVE_ANA = "chave-teste-ana-para-pytest"


class TestMudancaDeStatus:
    """Rota de mudança de status: papéis e persistência (critério de aceite 4)."""

    def _client_com_ana(self, monkeypatch, participante, rows):
        """App com o painel E a API da Ana sobre o mesmo banco: a persistência
        é observada pela consulta que a própria Ana faz."""
        from app.config import settings
        from app.routers import ana as ana_router

        monkeypatch.setattr(settings, "ana_api_key", CHAVE_ANA)
        client = _make_client(monkeypatch, participante, rows=rows)
        client.app.include_router(ana_router.router, prefix="/api")
        return client

    def test_marcar_respondido_persiste_e_aparece_na_consulta_da_ana(self, monkeypatch):
        rows = [_protocolo_row(numero=7)]
        client = self._client_com_ana(monkeypatch, FACILITADOR, rows)

        r = client.patch("/api/ouvidoria/protocolos/uuid-7/status", json={"status": "respondido"})

        assert r.status_code == 200
        assert r.json()["status"] == "respondido"

        consulta_ana = client.get(
            "/api/ana/ouvidoria/protocolos/2026-0007",
            headers={"X-API-Key": CHAVE_ANA},
        )
        assert consulta_ana.status_code == 200
        assert consulta_ana.json()["status"] == "respondido"

    def test_reabrir_protocolo_persiste(self, monkeypatch):
        rows = [_protocolo_row(numero=7, status="respondido")]
        client = _make_client(monkeypatch, SECRETARIA, rows=rows)

        r = client.patch("/api/ouvidoria/protocolos/uuid-7/status", json={"status": "aberto"})

        assert r.status_code == 200
        assert rows[0]["status"] == "aberto"

    def test_status_fora_de_aberto_respondido_e_recusado(self, monkeypatch):
        rows = [_protocolo_row(numero=7)]
        client = _make_client(monkeypatch, SECRETARIA, rows=rows)

        r = client.patch("/api/ouvidoria/protocolos/uuid-7/status", json={"status": "encerrado"})

        assert r.status_code == 422
        assert rows[0]["status"] == "aberto"

    def test_protocolo_inexistente_devolve_404(self, monkeypatch):
        client = _make_client(monkeypatch, SECRETARIA, rows=[])

        r = client.patch("/api/ouvidoria/protocolos/uuid-999/status", json={"status": "respondido"})

        assert r.status_code == 404

    def test_id_malformado_nao_vaza_detalhe_do_banco(self, monkeypatch):
        """Id que não é UUID faz o PostgREST estourar APIError; a resposta vira
        404 sem mensagem interna do Postgres (tabela, tipo, hint)."""
        from postgrest.exceptions import APIError

        class _QueryQueFalha(_Query):
            def execute(self):
                raise APIError({"code": "22P02", "message": 'invalid input syntax for type uuid: "nao-e-uuid"'})

        class _SupabaseQueFalha(_SupabaseMock):
            def table(self, name):
                assert name == "ouvidoria_protocolos"
                return _QueryQueFalha(self.rows)

        client = _make_client(monkeypatch, SECRETARIA)
        client.app.dependency_overrides[get_supabase_client] = lambda: _SupabaseQueFalha([])

        r = client.patch("/api/ouvidoria/protocolos/nao-e-uuid/status", json={"status": "respondido"})

        assert r.status_code == 404
        assert r.json() == {"detail": "Protocolo não encontrado"}
        assert "22P02" not in r.text
        assert "uuid" not in r.text.lower()

    @pytest.mark.parametrize("sem_acesso", [POPS_SEM_REUNIOES, None])
    def test_quem_nao_e_da_equipe_nao_muda_status(self, monkeypatch, sem_acesso):
        rows = [_protocolo_row(numero=7)]
        client = _make_client(monkeypatch, sem_acesso, rows=rows)

        r = client.patch("/api/ouvidoria/protocolos/uuid-7/status", json={"status": "respondido"})

        assert r.status_code == 403
        assert rows[0]["status"] == "aberto"


# O índice completo da manifestação, e nada além dele (ADR 0031, decisão 3).
CAMPOS_DO_INDICE = {
    "id",
    "numero",
    "protocolo",
    "data_abertura",
    "prazo_resposta",
    "status",
    "categoria",
    "setor",
    "resumo",
    "conversa_id",
}


class TestSemCriacaoNemDadoPessoal:
    """Protocolo nasce só pelo registro da Ana; o painel expõe o índice e nada
    além dele (critério de aceite 3)."""

    def test_nao_existe_rota_de_criacao_no_painel(self, monkeypatch):
        client = _make_client(monkeypatch, SECRETARIA)

        r = client.post(
            "/api/ouvidoria/protocolos",
            json={"categoria": "Demora", "setor": "Recepcao", "resumo": "Tentativa manual."},
        )

        assert r.status_code == 405

    def test_resposta_do_patch_expoe_exatamente_o_indice(self, monkeypatch):
        """O update do PostgREST devolve a row inteira: se a tabela ganhar
        coluna nova amanhã, a resposta do PATCH continua fechada no índice."""
        rows = [_protocolo_row(numero=7, coluna_futura="valor que nao pode vazar")]
        client = _make_client(monkeypatch, FACILITADOR, rows=rows)

        atualizado = client.patch("/api/ouvidoria/protocolos/uuid-7/status", json={"status": "respondido"}).json()

        assert set(atualizado.keys()) == CAMPOS_DO_INDICE

    def test_lista_pede_colunas_explicitas_do_indice(self, monkeypatch):
        """O select da lista é a lista fechada de campos do índice: é ele que
        impede dado novo de vazar no painel."""
        pedidos: list[str] = []

        class _QueryEspiona(_Query):
            def select(self, *cols, **_kw):
                pedidos.extend(c.strip() for col in cols for c in col.split(","))
                return self

        class _SupabaseEspiao(_SupabaseMock):
            def table(self, name):
                assert name == "ouvidoria_protocolos"
                return _QueryEspiona(self.rows)

        client = _make_client(monkeypatch, FACILITADOR)
        client.app.dependency_overrides[get_supabase_client] = lambda: _SupabaseEspiao([_protocolo_row()])

        client.get("/api/ouvidoria/protocolos")

        assert set(pedidos) == CAMPOS_DO_INDICE


class TestRegistroNoApp:
    def test_rotas_do_painel_existem_no_app_real(self):
        # Via OpenAPI (API pública): não depende de internals de rota do
        # Starlette, que variam entre versões (o CI instala sem lock).
        from app.main import app as app_real

        paths = set(app_real.openapi()["paths"].keys())
        assert "/api/ouvidoria/protocolos" in paths
        assert "/api/ouvidoria/protocolos/{protocolo_id}/status" in paths
