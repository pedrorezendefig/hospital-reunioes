"""Testes do Espelho da Global Health, elo 1 (issue #388, ADR 0038).

A costura é a rota admin: TestClient sobre o router, com o httpx da Global
Health mockado (mesmo padrão dos testes do serviço ClickSign). Nenhum teste
toca a GH de verdade.

Cobre (critérios de aceite):
- Especialidades publicadas chegam à tela com id, nome e bloqueado.
- `pesquisa` é repassada para a Global Health.
- Timeout e 5xx da GH viram 502 com mensagem, nunca lista vazia.
- Resposta vazia da GH é 200 com motivo, distinta de erro.
- Token ausente vira erro honesto de configuração, nunca lista vazia.
- Auth exigida; o token da GH não vaza para a resposta do navegador.
"""

from __future__ import annotations

import os
import sys
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.config import settings  # noqa: E402
from app.dependencies import _participante_ctx, get_current_user, get_supabase_client  # noqa: E402
from app.limiter import limiter  # noqa: E402

TOKEN_GH = "token-gh-secreto-de-teste"


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


@pytest.fixture(autouse=True)
def _reset_participante_ctx():
    _participante_ctx.set(None)
    yield
    _participante_ctx.set(None)


@pytest.fixture(autouse=True)
def _token_configurado(monkeypatch):
    """Por padrão o token existe; o teste de configuração o apaga."""
    monkeypatch.setattr(settings, "gh_token_homolog", TOKEN_GH)


# ─── Mock do httpx da Global Health ──────────────────────────────────────────


class _FakeResponse:
    def __init__(self, status_code: int, payload: Any = None):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "erro",
                request=httpx.Request("GET", "http://gh"),
                response=httpx.Response(self.status_code),
            )


class _FakeClient:
    """Context manager no lugar do httpx.Client: registra a chamada e responde."""

    def __init__(self, handler, chamadas: list):
        self._handler = handler
        self._chamadas = chamadas

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def get(self, url, params=None, headers=None, **_kw):
        self._chamadas.append({"url": url, "params": params, "headers": headers})
        return self._handler(url, params)


def _mock_gh(monkeypatch, handler) -> list:
    """Troca httpx.Client pelo fake e devolve a lista de chamadas feitas."""
    chamadas: list = []
    monkeypatch.setattr(httpx, "Client", lambda **_kw: _FakeClient(handler, chamadas))
    return chamadas


def _responde(payload: Any, status_code: int = 200):
    return lambda _url, _params: _FakeResponse(status_code, payload)


def _explode(exc: Exception):
    def _handler(_url, _params):
        raise exc

    return _handler


_CARDIO = {"id": 1843, "nome": "Consulta Cardiologica", "bloqueado": False}


def _pagina(itens: list[dict]) -> dict:
    """Envelope paginado da GH."""
    return {"conteudo": itens, "paginaAnterior": "", "paginaSeguinte": ""}


# ─── Participante de teste ───────────────────────────────────────────────────

FACILITADOR = {
    "id": "p-fac",
    "auth_user_id": "auth-fac",
    "email": "fac@ex.com",
    "nome_completo": "Pessoa Facilitadora",
    "cargo": "Cargo X",
    "setor": "Setor X",
    "area": None,
    "role": "facilitador",
    "ativo": True,
    "is_externo": False,
    "is_super_admin": False,
    "access_profile": "regular",
    "perfil_pop": None,
    "data_cadastro": "2026-01-01",
}


class _Result:
    def __init__(self, data: list):
        self.data = data


class _ParticipantesQuery:
    def __init__(self, rows: list):
        self._rows = rows
        self._filters: list[tuple[str, Any]] = []

    def select(self, *_a, **_kw):
        return self

    def eq(self, col, value):
        self._filters.append((col, value))
        return self

    def order(self, *_a, **_kw):
        return self

    def execute(self):
        return _Result([dict(r) for r in self._rows if all(r.get(c) == v for c, v in self._filters)])


class _SupabaseMock:
    def table(self, name: str):
        if name == "participantes":
            return _ParticipantesQuery([FACILITADOR])
        raise AssertionError(f"O Espelho não fala com o banco (tabela {name})")


def _make_app(logado: bool = True) -> TestClient:
    from app.routers.admin import espelho_global_health as espelho_router

    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(espelho_router.router, prefix="/api")

    app.dependency_overrides[get_supabase_client] = lambda: _SupabaseMock()
    if logado:

        async def _fake_user() -> dict[str, Any]:
            return {"id": FACILITADOR["auth_user_id"], "email": FACILITADOR["email"], "metadata": {}}

        app.dependency_overrides[get_current_user] = _fake_user

    return TestClient(app)


ROTA = "/api/admin/espelho-global-health/especialidades"
AUTH = {"Authorization": "Bearer token-fake"}


# ─── Testes ──────────────────────────────────────────────────────────────────


class TestListagem:
    def test_especialidades_publicadas_chegam_a_tela(self, monkeypatch):
        _mock_gh(monkeypatch, _responde(_pagina([_CARDIO])))
        res = _make_app().get(ROTA, headers=AUTH)
        assert res.status_code == 200
        body = res.json()
        assert body["total"] == 1
        assert body["data"] == [{"id": 1843, "nome": "Consulta Cardiologica", "bloqueado": False}]

    def test_chama_a_homologacao_com_o_token_no_header(self, monkeypatch):
        chamadas = _mock_gh(monkeypatch, _responde(_pagina([_CARDIO])))
        _make_app().get(ROTA, headers=AUTH)
        assert len(chamadas) == 1
        assert chamadas[0]["url"] == "https://dem.agenda.globalhealth.mv/rest/whatsapp/consultas"
        assert chamadas[0]["headers"]["Token"] == TOKEN_GH

    def test_pesquisa_e_repassada_para_a_gh(self, monkeypatch):
        chamadas = _mock_gh(monkeypatch, _responde(_pagina([_CARDIO])))
        res = _make_app().get(ROTA, params={"pesquisa": "CARDIO"}, headers=AUTH)
        assert res.status_code == 200
        assert chamadas[0]["params"] == {"pesquisa": "CARDIO"}

    def test_sem_pesquisa_nao_manda_o_parametro(self, monkeypatch):
        chamadas = _mock_gh(monkeypatch, _responde(_pagina([_CARDIO])))
        _make_app().get(ROTA, headers=AUTH)
        assert not chamadas[0]["params"]


class TestVazioNaoEErro:
    def test_lista_vazia_da_gh_vira_200_com_motivo(self, monkeypatch):
        _mock_gh(monkeypatch, _responde(_pagina([])))
        res = _make_app().get(ROTA, headers=AUTH)
        assert res.status_code == 200
        body = res.json()
        assert body["data"] == []
        assert body["total"] == 0
        assert body["motivo_vazio"]
        assert "especialidade" in body["motivo_vazio"].lower()

    def test_lista_cheia_nao_traz_motivo_de_vazio(self, monkeypatch):
        _mock_gh(monkeypatch, _responde(_pagina([_CARDIO])))
        body = _make_app().get(ROTA, headers=AUTH).json()
        assert body["motivo_vazio"] is None


class TestFalhaDaGhNaoViraListaVazia:
    def test_timeout_vira_502_com_mensagem(self, monkeypatch):
        _mock_gh(monkeypatch, _explode(httpx.TimeoutException("devagar")))
        res = _make_app().get(ROTA, headers=AUTH)
        assert res.status_code == 502
        assert res.json()["detail"]
        # A falha é falha: nenhuma lista vazia disfarçada de resposta.
        assert "data" not in res.json()

    def test_erro_5xx_vira_502_com_mensagem(self, monkeypatch):
        _mock_gh(monkeypatch, _responde(None, status_code=500))
        res = _make_app().get(ROTA, headers=AUTH)
        assert res.status_code == 502
        assert "data" not in res.json()

    def test_falha_de_rede_vira_502(self, monkeypatch):
        _mock_gh(monkeypatch, _explode(httpx.ConnectError("sem rota")))
        res = _make_app().get(ROTA, headers=AUTH)
        assert res.status_code == 502
        assert "data" not in res.json()

    def test_mensagem_de_erro_nao_vaza_o_token(self, monkeypatch):
        _mock_gh(monkeypatch, _explode(httpx.TimeoutException("devagar")))
        res = _make_app().get(ROTA, headers=AUTH)
        assert TOKEN_GH not in res.text


class TestConfiguracao:
    def test_sem_token_configurado_erro_honesto_e_nao_chama_a_gh(self, monkeypatch):
        monkeypatch.setattr(settings, "gh_token_homolog", "")
        chamadas = _mock_gh(monkeypatch, _responde(_pagina([_CARDIO])))
        res = _make_app().get(ROTA, headers=AUTH)
        assert res.status_code == 503
        assert "GH_TOKEN_HOMOLOG" in res.json()["detail"]
        assert "data" not in res.json()
        assert chamadas == []


class TestAuth:
    def test_anonimo_e_recusado(self, monkeypatch):
        chamadas = _mock_gh(monkeypatch, _responde(_pagina([_CARDIO])))
        res = _make_app(logado=False).get(ROTA)
        assert res.status_code == 401
        assert chamadas == []

    def test_token_da_gh_nunca_aparece_na_resposta(self, monkeypatch):
        _mock_gh(monkeypatch, _responde(_pagina([_CARDIO])))
        res = _make_app().get(ROTA, headers=AUTH)
        assert TOKEN_GH not in res.text


class TestServiceSoLeitura:
    def test_o_modulo_da_gh_nao_expoe_verbo_de_escrita(self):
        import inspect

        from app.services import global_health_service as gh

        fonte = inspect.getsource(gh)
        for verbo in (".post(", ".put(", ".patch(", ".delete("):
            assert verbo not in fonte, f"O Espelho é somente leitura: {verbo} não pode existir"

    def test_base_aponta_para_homologacao(self):
        from app.services import global_health_service as gh

        assert gh.BASE_URL.startswith("https://dem.agenda.globalhealth.mv")
        assert "app.agenda.globalhealth.mv" not in gh.BASE_URL
