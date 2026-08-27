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

    def __init__(self, handler, chamadas: list, kwargs_client: dict):
        self._handler = handler
        self._chamadas = chamadas
        self._kwargs_client = kwargs_client

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def get(self, url, params=None, headers=None, **_kw):
        self._chamadas.append(
            {"url": url, "params": params, "headers": headers, "kwargs_client": dict(self._kwargs_client)}
        )
        return self._handler(url, params)


def _mock_gh(monkeypatch, handler) -> list:
    """Troca httpx.Client pelo fake e devolve a lista de chamadas feitas.

    Cada chamada guarda também os kwargs com que o client foi construído, o
    que permite provar que o timeout curto chegou até o httpx.
    """
    chamadas: list = []

    def _fabrica(**kwargs_client):
        return _FakeClient(handler, chamadas, kwargs_client)

    monkeypatch.setattr(httpx, "Client", _fabrica)
    return chamadas


def _responde(payload: Any, status_code: int = 200):
    return lambda _url, _params: _FakeResponse(status_code, payload)


def _explode_json():
    """Corpo que não é JSON: httpx levanta ValueError no .json()."""
    raise ValueError("corpo nao e json")


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

# Login válido sem papel nas Reuniões: o caso do Coordenador de POPs, que
# ganhou acesso pelo provisionamento do módulo de POPs (`access_profile` NULL
# explícito, docstring de `tem_acesso_reunioes`). Autentica, mas não pode ver
# a agenda da Global Health.
SEM_PAPEL_NAS_REUNIOES = {
    **FACILITADOR,
    "id": "p-pop",
    "auth_user_id": "auth-pop",
    "email": "pop@ex.com",
    "nome_completo": "Pessoa Coordenadora de POPs",
    "role": "colaborador",
    "access_profile": None,
    "perfil_pop": "coordenador",
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
    def __init__(self, participante: dict):
        self._participante = participante

    def table(self, name: str):
        if name == "participantes":
            return _ParticipantesQuery([self._participante])
        raise AssertionError(f"O Espelho não fala com o banco (tabela {name})")


def _make_app(logado: bool = True, participante: dict = FACILITADOR) -> TestClient:
    """App com o router do Espelho e o participante que o banco vai devolver.

    `logado=False` deixa a dependency real de auth valer: requisição sem
    Bearer token recebe 401. `participante` decide o veredito do gate de
    papel (`require_participante_reunioes`) para quem está autenticado.
    """
    from app.routers.admin import espelho_global_health as espelho_router

    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(espelho_router.router, prefix="/api")

    app.dependency_overrides[get_supabase_client] = lambda: _SupabaseMock(participante)
    if logado:

        async def _fake_user() -> dict[str, Any]:
            return {"id": participante["auth_user_id"], "email": participante["email"], "metadata": {}}

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

    def test_timeout_curto_chega_ao_client(self, monkeypatch):
        """O timeout é o que impede a tela de pendurar: prove que ele desce.

        Sem esta asserção, apagar `_TIMEOUT` do service deixaria a suíte
        verde e a chamada sem prazo.
        """
        from app.services import global_health_service as gh

        chamadas = _mock_gh(monkeypatch, _responde(_pagina([_CARDIO])))
        _make_app().get(ROTA, headers=AUTH)
        timeout = chamadas[0]["kwargs_client"]["timeout"]
        assert timeout is gh._TIMEOUT
        assert timeout.read == 10.0
        assert timeout.connect == 3.0


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

    def test_busca_sem_resultado_nao_diz_que_a_agenda_esta_vazia(self, monkeypatch):
        """Dois vazios diferentes, dois motivos diferentes.

        Com filtro ativo, dizer "nada publicado na agenda" seria mentira: o
        que faltou foi o termo casar.
        """
        _mock_gh(monkeypatch, _responde(_pagina([])))
        body = _make_app().get(ROTA, params={"pesquisa": "ORTOPEDIA"}, headers=AUTH).json()
        assert body["data"] == []
        assert "termo" in body["motivo_vazio"]

        _mock_gh(monkeypatch, _responde(_pagina([])))
        sem_busca = _make_app().get(ROTA, headers=AUTH).json()
        assert "termo" not in sem_busca["motivo_vazio"]
        assert sem_busca["motivo_vazio"] != body["motivo_vazio"]


class TestRespostaMalformada:
    """Corpo estranho da GH é falha, não lista vazia."""

    def test_corpo_que_nao_e_json_vira_502(self, monkeypatch):
        def _handler(_url, _params):
            resposta = _FakeResponse(200, None)
            resposta.json = _explode_json
            return resposta

        _mock_gh(monkeypatch, _handler)
        res = _make_app().get(ROTA, headers=AUTH)
        assert res.status_code == 502
        assert "data" not in res.json()

    def test_corpo_que_nao_e_dict_vira_502(self, monkeypatch):
        _mock_gh(monkeypatch, _responde([_CARDIO]))
        res = _make_app().get(ROTA, headers=AUTH)
        assert res.status_code == 502
        assert "data" not in res.json()

    def test_conteudo_nulo_e_lista_vazia_com_motivo(self, monkeypatch):
        """`conteudo: None` é a página vazia da GH, não um defeito."""
        _mock_gh(monkeypatch, _responde({"conteudo": None}))
        res = _make_app().get(ROTA, headers=AUTH)
        assert res.status_code == 200
        body = res.json()
        assert body["data"] == []
        assert body["motivo_vazio"]

    def test_conteudo_ausente_e_lista_vazia_com_motivo(self, monkeypatch):
        _mock_gh(monkeypatch, _responde({"paginaSeguinte": ""}))
        res = _make_app().get(ROTA, headers=AUTH)
        assert res.status_code == 200
        assert res.json()["data"] == []
        assert res.json()["motivo_vazio"]

    def test_item_sem_id_e_descartado(self, monkeypatch):
        """Item sem id não identifica nada na GH nem serve de chave na tela.

        Dois deles virariam a mesma chave de linha no React e embaralhariam
        a tabela.
        """
        _mock_gh(
            monkeypatch,
            _responde(_pagina([_CARDIO, {"nome": "Sem id"}, {"nome": "Outro sem id"}])),
        )
        res = _make_app().get(ROTA, headers=AUTH)
        assert res.status_code == 200
        body = res.json()
        assert body["total"] == 1
        assert [linha["id"] for linha in body["data"]] == [1843]

    def test_item_que_nao_e_dict_e_descartado(self, monkeypatch):
        _mock_gh(monkeypatch, _responde(_pagina([_CARDIO, "isso nao e um item"])))
        res = _make_app().get(ROTA, headers=AUTH)
        assert res.status_code == 200
        assert res.json()["total"] == 1


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

    def test_autenticado_sem_papel_nas_reunioes_leva_403(self, monkeypatch):
        """A porta do papel, não a do token.

        O anônimo acima é barrado pelo HTTPBearer, antes do gate de papel.
        Aqui o Bearer é válido e o participante existe: quem recusa é o
        `require_participante_reunioes`. Sem este teste, trocar a dependency
        por `get_current_user` abriria a agenda da Global Health para
        qualquer autenticado com a suíte verde.
        """
        chamadas = _mock_gh(monkeypatch, _responde(_pagina([_CARDIO])))
        client = _make_app(participante=SEM_PAPEL_NAS_REUNIOES)
        res = client.get(ROTA, headers=AUTH)
        assert res.status_code == 403
        # Recusado antes da integração: o token da GH nem sai do backend.
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


# ─── Elos 2 e 3 (issue #389): convênios, profissionais e planos ──────────────

_UNIMED = {"id": 12, "nome": "Unimed", "particular": False}
_PARTICULAR = {"id": 1, "nome": "Particular", "particular": True}
_PRESTADOR = {"id": 501, "nome": "Dra. Fulana de Tal"}
_PLANO = {"id": 77, "nome": "Unimed Nacional"}

ID_ESPECIALIDADE = 1843
ID_CONVENIO = 12

ROTA_CONVENIOS = f"{ROTA}/{ID_ESPECIALIDADE}/convenios"
ROTA_PROFISSIONAIS = f"{ROTA}/{ID_ESPECIALIDADE}/profissionais"
ROTA_PLANOS = f"{ROTA}/{ID_ESPECIALIDADE}/convenios/{ID_CONVENIO}/planos"


class TestConvenios:
    """Elo 2a: convênios aceitos na especialidade escolhida."""

    def test_convenios_da_especialidade_chegam_a_tela(self, monkeypatch):
        _mock_gh(monkeypatch, _responde(_pagina([_UNIMED, _PARTICULAR])))
        res = _make_app().get(ROTA_CONVENIOS, headers=AUTH)
        assert res.status_code == 200
        body = res.json()
        assert body["total"] == 2
        assert body["data"] == [
            {"id": 12, "nome": "Unimed", "particular": False},
            {"id": 1, "nome": "Particular", "particular": True},
        ]

    def test_id_da_especialidade_e_o_size_vao_para_a_gh(self, monkeypatch):
        """O id vem do elo anterior e desce inteiro; `size=100` evita paginar.

        Sem esta asserção, chamar a GH sem `idItemAgendamento` devolveria a
        lista de todos os convênios do hospital, e não a da especialidade.
        """
        chamadas = _mock_gh(monkeypatch, _responde(_pagina([_UNIMED])))
        _make_app().get(ROTA_CONVENIOS, headers=AUTH)
        assert len(chamadas) == 1
        assert chamadas[0]["url"] == "https://dem.agenda.globalhealth.mv/rest/whatsapp/convenios"
        assert chamadas[0]["params"] == {"idItemAgendamento": ID_ESPECIALIDADE, "size": 100}

    def test_particular_verdadeiro_chega_como_booleano(self, monkeypatch):
        """A tela destaca a linha por este campo: ele não pode chegar solto."""
        _mock_gh(monkeypatch, _responde(_pagina([{"id": 1, "nome": "Particular", "particular": "true"}])))
        body = _make_app().get(ROTA_CONVENIOS, headers=AUTH).json()
        assert body["data"][0]["particular"] is True

    def test_a_string_false_nao_destaca_o_convenio(self, monkeypatch):
        """O caso que `bool()` sozinho erraria.

        `bool("false")` é `True` em Python: sem leitura pelo valor, uma GH que
        mandasse a string no lugar do booleano faria todo convênio aparecer
        como Particular, o oposto do que a tela promete.
        """
        _mock_gh(monkeypatch, _responde(_pagina([{"id": 12, "nome": "Unimed", "particular": "false"}])))
        body = _make_app().get(ROTA_CONVENIOS, headers=AUTH).json()
        assert body["data"][0]["particular"] is False

    def test_o_s_da_mv_destaca_o_convenio(self, monkeypatch):
        """A GH é sistema MV, e MV costuma publicar flag como "S"/"N"."""
        _mock_gh(monkeypatch, _responde(_pagina([{"id": 1, "nome": "Particular", "particular": "S"}])))
        body = _make_app().get(ROTA_CONVENIOS, headers=AUTH).json()
        assert body["data"][0]["particular"] is True

    def test_o_n_da_mv_nao_destaca_o_convenio(self, monkeypatch):
        _mock_gh(monkeypatch, _responde(_pagina([{"id": 12, "nome": "Unimed", "particular": "N"}])))
        body = _make_app().get(ROTA_CONVENIOS, headers=AUTH).json()
        assert body["data"][0]["particular"] is False

    def test_convenio_sem_o_campo_particular_nao_e_destacado(self, monkeypatch):
        _mock_gh(monkeypatch, _responde(_pagina([{"id": 9, "nome": "Sem campo"}])))
        body = _make_app().get(ROTA_CONVENIOS, headers=AUTH).json()
        assert body["data"][0]["particular"] is False

    def test_convenio_sem_id_e_descartado(self, monkeypatch):
        _mock_gh(monkeypatch, _responde(_pagina([_UNIMED, {"nome": "Sem id"}])))
        body = _make_app().get(ROTA_CONVENIOS, headers=AUTH).json()
        assert [linha["id"] for linha in body["data"]] == [12]

    def test_sem_convenio_publicado_diz_o_motivo(self, monkeypatch):
        _mock_gh(monkeypatch, _responde(_pagina([])))
        res = _make_app().get(ROTA_CONVENIOS, headers=AUTH)
        assert res.status_code == 200
        body = res.json()
        assert body["data"] == []
        assert "convênio" in body["motivo_vazio"].lower()

    def test_lista_cheia_nao_traz_motivo_de_vazio(self, monkeypatch):
        _mock_gh(monkeypatch, _responde(_pagina([_UNIMED])))
        assert _make_app().get(ROTA_CONVENIOS, headers=AUTH).json()["motivo_vazio"] is None

    def test_timeout_da_gh_vira_502_e_nunca_lista_vazia(self, monkeypatch):
        _mock_gh(monkeypatch, _explode(httpx.TimeoutException("devagar")))
        res = _make_app().get(ROTA_CONVENIOS, headers=AUTH)
        assert res.status_code == 502
        assert "data" not in res.json()

    def test_erro_5xx_da_gh_vira_502(self, monkeypatch):
        _mock_gh(monkeypatch, _responde(None, status_code=500))
        res = _make_app().get(ROTA_CONVENIOS, headers=AUTH)
        assert res.status_code == 502
        assert "data" not in res.json()

    def test_corpo_fora_do_formato_vira_502(self, monkeypatch):
        _mock_gh(monkeypatch, _responde([_UNIMED]))
        res = _make_app().get(ROTA_CONVENIOS, headers=AUTH)
        assert res.status_code == 502
        assert "data" not in res.json()

    def test_anonimo_e_recusado(self, monkeypatch):
        chamadas = _mock_gh(monkeypatch, _responde(_pagina([_UNIMED])))
        res = _make_app(logado=False).get(ROTA_CONVENIOS)
        assert res.status_code == 401
        assert chamadas == []

    def test_autenticado_sem_papel_nas_reunioes_leva_403(self, monkeypatch):
        """A porta do papel, não a do token (o anônimo acima para no Bearer)."""
        chamadas = _mock_gh(monkeypatch, _responde(_pagina([_UNIMED])))
        res = _make_app(participante=SEM_PAPEL_NAS_REUNIOES).get(ROTA_CONVENIOS, headers=AUTH)
        assert res.status_code == 403
        assert chamadas == []

    def test_id_de_especialidade_que_nao_e_numero_nao_chega_na_gh(self, monkeypatch):
        """Id vem sempre do elo anterior; lixo é recusado aqui, sem gastar a GH."""
        chamadas = _mock_gh(monkeypatch, _responde(_pagina([_UNIMED])))
        res = _make_app().get(f"{ROTA}/nao-e-id/convenios", headers=AUTH)
        assert res.status_code == 422
        assert chamadas == []


class TestProfissionais:
    """Elo 2b: quem está com o botão ligado no Painel de Controle da GH."""

    def test_profissionais_da_especialidade_chegam_a_tela(self, monkeypatch):
        _mock_gh(monkeypatch, _responde(_pagina([_PRESTADOR])))
        res = _make_app().get(ROTA_PROFISSIONAIS, headers=AUTH)
        assert res.status_code == 200
        assert res.json()["data"] == [{"id": 501, "nome": "Dra. Fulana de Tal"}]

    def test_chama_prestadores_com_o_id_da_especialidade(self, monkeypatch):
        chamadas = _mock_gh(monkeypatch, _responde(_pagina([_PRESTADOR])))
        _make_app().get(ROTA_PROFISSIONAIS, headers=AUTH)
        assert len(chamadas) == 1
        assert chamadas[0]["url"] == "https://dem.agenda.globalhealth.mv/rest/whatsapp/prestadores"
        assert chamadas[0]["params"] == {"idItemAgendamento": ID_ESPECIALIDADE}

    def test_profissional_sem_id_e_descartado(self, monkeypatch):
        _mock_gh(monkeypatch, _responde(_pagina([_PRESTADOR, {"nome": "Sem id"}])))
        assert _make_app().get(ROTA_PROFISSIONAIS, headers=AUTH).json()["total"] == 1

    def test_sem_profissional_o_motivo_aponta_o_botao_no_painel_da_gh(self, monkeypatch):
        """Vazio aqui quase sempre é botão desligado; o texto tem que dizer."""
        _mock_gh(monkeypatch, _responde(_pagina([])))
        body = _make_app().get(ROTA_PROFISSIONAIS, headers=AUTH).json()
        assert body["data"] == []
        motivo = body["motivo_vazio"].lower()
        assert "botão ligado" in motivo
        assert "painel de controle" in motivo

    def test_timeout_da_gh_vira_502_e_nunca_lista_vazia(self, monkeypatch):
        _mock_gh(monkeypatch, _explode(httpx.TimeoutException("devagar")))
        res = _make_app().get(ROTA_PROFISSIONAIS, headers=AUTH)
        assert res.status_code == 502
        assert "data" not in res.json()

    def test_falha_de_rede_vira_502(self, monkeypatch):
        _mock_gh(monkeypatch, _explode(httpx.ConnectError("sem rota")))
        res = _make_app().get(ROTA_PROFISSIONAIS, headers=AUTH)
        assert res.status_code == 502
        assert "data" not in res.json()

    def test_anonimo_e_recusado(self, monkeypatch):
        chamadas = _mock_gh(monkeypatch, _responde(_pagina([_PRESTADOR])))
        assert _make_app(logado=False).get(ROTA_PROFISSIONAIS).status_code == 401
        assert chamadas == []

    def test_id_de_especialidade_que_nao_e_numero_nao_chega_na_gh(self, monkeypatch):
        chamadas = _mock_gh(monkeypatch, _responde(_pagina([_PRESTADOR])))
        res = _make_app().get(f"{ROTA}/nao-e-id/profissionais", headers=AUTH)
        assert res.status_code == 422
        assert chamadas == []

    def test_autenticado_sem_papel_nas_reunioes_leva_403(self, monkeypatch):
        chamadas = _mock_gh(monkeypatch, _responde(_pagina([_PRESTADOR])))
        res = _make_app(participante=SEM_PAPEL_NAS_REUNIOES).get(ROTA_PROFISSIONAIS, headers=AUTH)
        assert res.status_code == 403
        assert chamadas == []


class TestPlanos:
    """Elo 3: planos do convênio, dentro da especialidade escolhida."""

    def test_planos_do_convenio_chegam_a_tela(self, monkeypatch):
        _mock_gh(monkeypatch, _responde(_pagina([_PLANO])))
        res = _make_app().get(ROTA_PLANOS, headers=AUTH)
        assert res.status_code == 200
        assert res.json()["data"] == [{"id": 77, "nome": "Unimed Nacional"}]

    def test_os_dois_ids_dos_elos_anteriores_vao_para_o_lugar_certo(self, monkeypatch):
        """O convênio manda no caminho, a especialidade no parâmetro.

        Trocar os dois de lugar devolveria 200 com os planos de outra coisa,
        sem erro nenhum: por isso a asserção separa caminho de parâmetro.
        """
        chamadas = _mock_gh(monkeypatch, _responde(_pagina([_PLANO])))
        _make_app().get(ROTA_PLANOS, headers=AUTH)
        assert len(chamadas) == 1
        assert chamadas[0]["url"] == (
            f"https://dem.agenda.globalhealth.mv/rest/whatsapp/convenios/{ID_CONVENIO}/planos"
        )
        assert chamadas[0]["params"] == {"idItemAgendamento": ID_ESPECIALIDADE}

    def test_plano_sem_id_e_descartado(self, monkeypatch):
        _mock_gh(monkeypatch, _responde(_pagina([_PLANO, {"nome": "Sem id"}])))
        assert _make_app().get(ROTA_PLANOS, headers=AUTH).json()["total"] == 1

    def test_sem_plano_publicado_diz_o_motivo(self, monkeypatch):
        _mock_gh(monkeypatch, _responde(_pagina([])))
        body = _make_app().get(ROTA_PLANOS, headers=AUTH).json()
        assert body["data"] == []
        assert "plano" in body["motivo_vazio"].lower()

    def test_timeout_da_gh_vira_502_e_nunca_lista_vazia(self, monkeypatch):
        _mock_gh(monkeypatch, _explode(httpx.TimeoutException("devagar")))
        res = _make_app().get(ROTA_PLANOS, headers=AUTH)
        assert res.status_code == 502
        assert "data" not in res.json()

    def test_sem_token_configurado_erro_honesto_e_nao_chama_a_gh(self, monkeypatch):
        monkeypatch.setattr(settings, "gh_token_homolog", "")
        chamadas = _mock_gh(monkeypatch, _responde(_pagina([_PLANO])))
        res = _make_app().get(ROTA_PLANOS, headers=AUTH)
        assert res.status_code == 503
        assert "GH_TOKEN_HOMOLOG" in res.json()["detail"]
        assert chamadas == []

    def test_anonimo_e_recusado(self, monkeypatch):
        chamadas = _mock_gh(monkeypatch, _responde(_pagina([_PLANO])))
        assert _make_app(logado=False).get(ROTA_PLANOS).status_code == 401
        assert chamadas == []

    def test_autenticado_sem_papel_nas_reunioes_leva_403(self, monkeypatch):
        chamadas = _mock_gh(monkeypatch, _responde(_pagina([_PLANO])))
        res = _make_app(participante=SEM_PAPEL_NAS_REUNIOES).get(ROTA_PLANOS, headers=AUTH)
        assert res.status_code == 403
        assert chamadas == []

    def test_id_de_convenio_que_nao_e_numero_nao_chega_na_gh(self, monkeypatch):
        chamadas = _mock_gh(monkeypatch, _responde(_pagina([_PLANO])))
        res = _make_app().get(f"{ROTA}/{ID_ESPECIALIDADE}/convenios/nao-e-id/planos", headers=AUTH)
        assert res.status_code == 422
        assert chamadas == []

    def test_id_de_especialidade_que_nao_e_numero_nao_chega_na_gh(self, monkeypatch):
        chamadas = _mock_gh(monkeypatch, _responde(_pagina([_PLANO])))
        res = _make_app().get(f"{ROTA}/nao-e-id/convenios/{ID_CONVENIO}/planos", headers=AUTH)
        assert res.status_code == 422
        assert chamadas == []


class TestMotivosDeVazioSaoDistintos:
    def test_cada_elo_explica_o_proprio_vazio(self, monkeypatch):
        """Três blocos, três motivos: um "vazio" genérico não ajuda ninguém."""
        motivos = set()
        for rota in (ROTA_CONVENIOS, ROTA_PROFISSIONAIS, ROTA_PLANOS):
            _mock_gh(monkeypatch, _responde(_pagina([])))
            motivos.add(_make_app().get(rota, headers=AUTH).json()["motivo_vazio"])
        assert len(motivos) == 3


class TestIdSoInteiroEntraNaCadeia:
    """O `id` da GH volta para a GH e entra no caminho da URL do navegador.

    Um id de texto vindo da Global Health viraria caminho montado por um
    terceiro: `1/../../participantes` faria o navegador chamar outra rota do
    app com o Bearer de quem está olhando e despejar a resposta na tabela.
    O corte é no service, no mesmo ponto onde item sem id já cai fora.
    """

    @pytest.mark.parametrize(
        "rota,item",
        [
            (ROTA, {**_CARDIO, "id": "1/../../participantes"}),
            (ROTA_CONVENIOS, {**_UNIMED, "id": "1/../../participantes"}),
            (ROTA_PROFISSIONAIS, {**_PRESTADOR, "id": "../../admin/usuarios"}),
            (ROTA_PLANOS, {**_PLANO, "id": "12?x=1"}),
        ],
    )
    def test_id_que_nao_e_inteiro_e_descartado(self, monkeypatch, rota, item):
        _mock_gh(monkeypatch, _responde(_pagina([item])))
        res = _make_app().get(rota, headers=AUTH)
        assert res.status_code == 200
        body = res.json()
        assert body["data"] == []
        assert body["motivo_vazio"]

    def test_id_numerico_em_texto_vira_inteiro(self, monkeypatch):
        """Texto que É um número é dado, não caminho: entra normalizado."""
        _mock_gh(monkeypatch, _responde(_pagina([{**_UNIMED, "id": "12"}])))
        body = _make_app().get(ROTA_CONVENIOS, headers=AUTH).json()
        assert body["data"][0]["id"] == 12

    def test_booleano_nao_passa_por_id(self, monkeypatch):
        """`True` é `int` em Python, e não identifica nada na Global Health."""
        _mock_gh(monkeypatch, _responde(_pagina([{**_UNIMED, "id": True}])))
        assert _make_app().get(ROTA_CONVENIOS, headers=AUTH).json()["data"] == []
