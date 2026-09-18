"""A Visão Geral da Central de Comando pela rota real (issue #814, ADR 0058).

O seam é a ROTA HTTP, com `require_super_admin` de pé (PRD #809, "Decisões de
teste"). Só três coisas são dubladas:

* `get_current_user` e o cliente Supabase, que dizem quem está logado;
* a fronteira de rede do provedor do Google: o `httpx.Client` ganha um
  transporte de mentira (`httpx.MockTransport`), e todo o resto roda de
  verdade, inclusive a assinatura do JWT da service account.

O Google de mentira (`GoogleFalso`) responde como a GA4 Data API responderia:
confere a assinatura do token com a chave pública da service account do teste,
a propriedade no caminho e devolve os `activeUsers` do intervalo pedido. Por
isso as asserções olham só o que a rota devolve: se o provedor pedisse o
intervalo errado ou a métrica errada, o número da resposta sairia errado.

A service account é de mentira e a chave RSA é gerada aqui, a cada execução:
nenhuma credencial de verdade entra em arquivo. E nenhum teste fala com o
Google: a trava de rede da suíte (`tests/conftest.py`) segue de pé, e o último
bloco prova que ela pega o provedor quando o dublê falta.

Porte dos testes de `src/lib/analytics` do repositório antigo que cabem nesta
fatia: `ga4-provider.test.ts` (Visitantes atual e anterior, erro propagado),
`ga4-mappers.test.ts` (`firstMetric`), `get-provider.test.ts` (credencial
exige propriedade E chave) e `overview.test.ts` (o resumo por período).
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import date
from typing import Any

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from fastapi.testclient import TestClient
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from conftest import TentativaDeRedeNoTeste  # noqa: E402

from app.config import settings  # noqa: E402
from app.dependencies import _participante_ctx, get_current_user, get_supabase_client  # noqa: E402
from app.limiter import limiter  # noqa: E402
from app.routers.admin import central_de_comando as central_router  # noqa: E402
from app.services.central_de_comando import periodo as periodo_da_central  # noqa: E402
from app.services.central_de_comando import provedor_google  # noqa: E402

PREFIXO = "/api/admin/central-de-comando"
PROPRIEDADE = "123456789"
ESCOPO_DE_LEITURA = "https://www.googleapis.com/auth/analytics.readonly"
EMAIL_DA_SERVICE_ACCOUNT = "central-teste@projeto-de-teste.iam.gserviceaccount.com"

# O "hoje" do teste. Os intervalos abaixo foram contados à mão a partir dele:
# N dias completos terminando ontem (17/09) e o bloco de mesmo tamanho antes.
HOJE = date(2026, 9, 18)

VISITANTES_NA_GA4 = {
    # 28 dias: 21/08 a 17/09, contra 24/07 a 20/08.
    ("2026-08-21", "2026-09-17"): 12345,
    ("2026-07-24", "2026-08-20"): 10000,
    # 7 dias: 11/09 a 17/09, contra 04/09 a 10/09.
    ("2026-09-11", "2026-09-17"): 3100,
    ("2026-09-04", "2026-09-10"): 3350,
    # 90 dias: 20/06 a 17/09, contra 22/03 a 19/06.
    ("2026-06-20", "2026-09-17"): 38412,
    ("2026-03-22", "2026-06-19"): 34174,
}


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
def _hoje_fixo(monkeypatch):
    """O relógio é fronteira: o teste diz que dia é hoje."""
    monkeypatch.setattr(periodo_da_central, "hoje_utc", lambda: HOJE)


# ─── A service account de mentira ───────────────────────────────────────────


@pytest.fixture(scope="module")
def chave_rsa():
    """Chave gerada a cada execução: a assinatura é de verdade, a conta não."""
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def credencial(chave_rsa) -> dict:
    privada = chave_rsa.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    return {
        "type": "service_account",
        "project_id": "projeto-de-teste",
        "private_key_id": "id-da-chave-de-teste",
        "private_key": privada,
        "client_email": EMAIL_DA_SERVICE_ACCOUNT,
        "client_id": "000000000000000000000",
        "token_uri": "https://oauth2.googleapis.com/token",
    }


@pytest.fixture
def central_configurada(monkeypatch, credencial):
    """As duas variáveis do Google preenchidas, como no `.env` de quem confere."""
    monkeypatch.setattr(settings, "ga4_property_id", PROPRIEDADE)
    monkeypatch.setattr(settings, "google_application_credentials_json", json.dumps(credencial))


# ─── O Google de mentira ────────────────────────────────────────────────────


def _erro_da_ga4(codigo: int, status: str, mensagem: str) -> httpx.Response:
    """O envelope de erro das APIs do Google."""
    return httpx.Response(codigo, json={"error": {"code": codigo, "message": mensagem, "status": status}})


class GoogleFalso:
    """A GA4 Data API de mentira: responde `runReport` pelo que foi pedido.

    Só sabe responder `activeUsers` sem dimensão, que é o que esta fatia pede.
    Qualquer outra pergunta leva 400, que é barulhento de propósito: um dublê
    que responde qualquer coisa esconderia a pergunta errada.
    """

    def __init__(self, chave_publica, visitantes: dict[tuple[str, str], int]):
        self._chave_publica = chave_publica
        # O que a GA4 "sabe": activeUsers por (início, fim). O teste pode trocar.
        self.visitantes = dict(visitantes)
        self.pedidos: list[httpx.Request] = []
        self.clientes: list[dict[str, Any]] = []
        # Quando preenchido, é o que TODA chamada responde (ou levanta).
        self.forcar: httpx.Response | Exception | None = None

    def __call__(self, pedido: httpx.Request) -> httpx.Response:
        self.pedidos.append(pedido)
        if isinstance(self.forcar, Exception):
            raise self.forcar
        if self.forcar is not None:
            return self.forcar

        if pedido.url.host != "analyticsdata.googleapis.com" or pedido.method != "POST":
            return httpx.Response(404)

        autorizacao = pedido.headers.get("authorization", "")
        if not self._token_valido(autorizacao.removeprefix("Bearer ")):
            return _erro_da_ga4(401, "UNAUTHENTICATED", "Request had invalid authentication credentials.")

        if pedido.url.path != f"/v1beta/properties/{PROPRIEDADE}:runReport":
            # O que a GA4 responde para propriedade em que a conta não tem papel.
            return _erro_da_ga4(403, "PERMISSION_DENIED", "User does not have sufficient permissions.")

        corpo = json.loads(pedido.content)
        faixas = corpo.get("dateRanges") or []
        if corpo.get("metrics") != [{"name": "activeUsers"}] or corpo.get("dimensions") or len(faixas) != 1:
            return _erro_da_ga4(400, "INVALID_ARGUMENT", f"pergunta que o dublê não sabe responder: {corpo}")

        chave = (faixas[0]["startDate"], faixas[0]["endDate"])
        if chave not in self.visitantes:
            # A GA4 omite `rows` quando o intervalo não tem dado nenhum.
            return httpx.Response(200, json={"kind": "analyticsData#runReport", "rowCount": 0})
        return httpx.Response(
            200,
            json={
                "kind": "analyticsData#runReport",
                "metricHeaders": [{"name": "activeUsers", "type": "TYPE_INTEGER"}],
                "rows": [{"metricValues": [{"value": str(self.visitantes[chave])}]}],
                "rowCount": 1,
            },
        )

    def _token_valido(self, token: str) -> bool:
        """O que a GA4 confere: assinatura da service account e o escopo."""
        try:
            claims = jwt.decode(token, self._chave_publica, algorithms=["RS256"], options={"verify_aud": False})
        except jwt.PyJWTError:
            return False
        return claims.get("iss") == EMAIL_DA_SERVICE_ACCOUNT and ESCOPO_DE_LEITURA in claims.get("scope", "").split()


@pytest.fixture
def google(monkeypatch, chave_rsa) -> GoogleFalso:
    """Troca só o transporte do `httpx.Client`: o cliente de verdade monta o
    pedido, e a resposta vem do Google de mentira."""
    falso = GoogleFalso(chave_rsa.public_key(), VISITANTES_NA_GA4)
    cliente_de_verdade = httpx.Client

    def _cliente(*args, **kwargs):
        falso.clientes.append(dict(kwargs))
        return cliente_de_verdade(*args, transport=httpx.MockTransport(falso), **kwargs)

    monkeypatch.setattr(httpx, "Client", _cliente)
    return falso


# ─── Quem está logado ────────────────────────────────────────────────────────


def _pessoa(pid: str, access_profile: str | None, *, ativo: bool = True) -> dict:
    return {
        "id": pid,
        "auth_user_id": f"auth-{pid}",
        "email": f"{pid}@hsm.com",
        "nome_completo": f"Pessoa {pid}",
        "cargo": None,
        "setor": None,
        "area": None,
        "role": None,
        "ativo": ativo,
        "is_externo": False,
        "is_super_admin": access_profile == "super_admin",
        "access_profile": access_profile,
        "perfil_pop": None,
        "perfil_ouvidoria": None,
        "github_login": None,
        "data_cadastro": "2026-01-01",
    }


SUPER_ADMIN = _pessoa("super", "super_admin")
SECRETARIA = _pessoa("secretaria", "secretaria")
FACILITADOR = _pessoa("facilitador", "regular")


class _Resultado:
    def __init__(self, data: list):
        self.data = data


class _ConsultaDeParticipantes:
    def __init__(self, linhas: list[dict]):
        self._linhas = linhas
        self._filtros: list[tuple[str, Any]] = []

    def select(self, *_a, **_kw):
        return self

    def eq(self, coluna, valor):
        self._filtros.append((coluna, valor))
        return self

    def execute(self):
        return _Resultado([dict(li) for li in self._linhas if all(li.get(c) == v for c, v in self._filtros)])


class _SupabaseFalso:
    def __init__(self, participantes: list[dict]):
        self._participantes = participantes

    def table(self, nome: str):
        assert nome == "participantes", f"a Central não lê tabela nenhuma além do gate: {nome}"
        return _ConsultaDeParticipantes(self._participantes)


def _montar(logado: dict | None) -> TestClient:
    """O router de verdade num app mínimo. `logado=None` é o anônimo, que passa
    pelo `get_current_user` de verdade (sem token, 401)."""
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(central_router.router, prefix="/api")

    app.dependency_overrides[get_supabase_client] = lambda: _SupabaseFalso([SUPER_ADMIN, SECRETARIA, FACILITADOR])
    if logado is not None:

        async def _usuario() -> dict[str, Any]:
            return {"id": logado["auth_user_id"], "email": logado["email"], "metadata": {}}

        app.dependency_overrides[get_current_user] = _usuario
    return TestClient(app)


def _visao_geral(periodo: str | None = None, logado: dict | None = SUPER_ADMIN) -> httpx.Response:
    params = {"periodo": periodo} if periodo is not None else None
    return _montar(logado).get(f"{PREFIXO}/visao-geral", params=params)


# ─── 1. Os Visitantes de ponta a ponta ──────────────────────────────────────


@pytest.mark.usefixtures("central_configurada")
class TestVisitantesDoPeriodo:
    def test_super_admin_recebe_os_visitantes_de_28_dias_e_do_periodo_anterior(self, google):
        resposta = _visao_geral("28d")

        assert resposta.status_code == 200, resposta.text
        corpo = resposta.json()
        assert corpo["visitantes"]["atual"] == 12345
        assert corpo["visitantes"]["anterior"] == 10000
        assert corpo["visitantes"]["variacao"] == pytest.approx(0.2345)
        assert corpo["periodo"] == {
            "chave": "28d",
            "dias": 28,
            "atual": {"inicio": "2026-08-21", "fim": "2026-09-17"},
            "anterior": {"inicio": "2026-07-24", "fim": "2026-08-20"},
        }

    @pytest.mark.parametrize(
        ("periodo", "dias", "atual", "anterior", "datas_atual", "datas_anterior"),
        [
            ("7d", 7, 3100, 3350, ("2026-09-11", "2026-09-17"), ("2026-09-04", "2026-09-10")),
            ("28d", 28, 12345, 10000, ("2026-08-21", "2026-09-17"), ("2026-07-24", "2026-08-20")),
            ("90d", 90, 38412, 34174, ("2026-06-20", "2026-09-17"), ("2026-03-22", "2026-06-19")),
        ],
    )
    def test_cada_periodo_traz_os_seus_numeros_e_as_suas_datas(
        self, google, periodo, dias, atual, anterior, datas_atual, datas_anterior
    ):
        corpo = _visao_geral(periodo).json()

        assert corpo["visitantes"]["atual"] == atual
        assert corpo["visitantes"]["anterior"] == anterior
        assert corpo["periodo"]["chave"] == periodo
        assert corpo["periodo"]["dias"] == dias
        assert corpo["periodo"]["atual"] == {"inicio": datas_atual[0], "fim": datas_atual[1]}
        assert corpo["periodo"]["anterior"] == {"inicio": datas_anterior[0], "fim": datas_anterior[1]}

    def test_a_variacao_negativa_vem_com_sinal(self, google):
        """7 dias: 3.100 contra 3.350 é uma queda de 7,46%."""
        assert _visao_geral("7d").json()["visitantes"]["variacao"] == pytest.approx(-0.07462686)

    def test_sem_periodo_vale_o_de_28_dias(self, google):
        corpo = _visao_geral(None).json()

        assert corpo["periodo"]["chave"] == "28d"
        assert corpo["visitantes"]["atual"] == 12345

    @pytest.mark.parametrize("periodo", ["30d", "7", "", "ano"])
    def test_periodo_que_nao_existe_e_recusado_sem_consultar_o_google(self, google, periodo):
        """A API é estrita; quem cai no padrão com o que se digita no endereço
        é a tela."""
        assert _visao_geral(periodo).status_code == 422
        assert google.pedidos == []

    def test_periodo_anterior_sem_visitantes_nao_inventa_variacao(self, google):
        """Anterior zerado: a GA4 respondeu que ninguém veio, e não existe
        variação honesta contra zero. O número atual continua de pé."""
        google.visitantes = {("2026-08-21", "2026-09-17"): 500}

        corpo = _visao_geral("28d").json()

        assert corpo["visitantes"] == {"atual": 500, "anterior": 0, "variacao": None}


# ─── 3. Sem credencial: 503 de configuração, nunca zero ─────────────────────


def _config(monkeypatch, *, propriedade: str, credencial: str) -> None:
    monkeypatch.setattr(settings, "ga4_property_id", propriedade)
    monkeypatch.setattr(settings, "google_application_credentials_json", credencial)


class TestSemCredencial:
    """Porte de `get-provider.test.ts`: a credencial só existe com a
    propriedade E a chave. Lá, sem ela, entrava o provedor de demonstração com
    números inventados; aqui é 503 com o que falta (ADR 0058, decisão 2)."""

    @pytest.mark.parametrize(
        ("propriedade", "tem_chave", "faltando"),
        [
            ("", False, ["GA4_PROPERTY_ID", "GOOGLE_APPLICATION_CREDENTIALS_JSON"]),
            ("", True, ["GA4_PROPERTY_ID"]),
            (PROPRIEDADE, False, ["GOOGLE_APPLICATION_CREDENTIALS_JSON"]),
            ("   ", True, ["GA4_PROPERTY_ID"]),
        ],
        ids=["nenhuma", "sem-propriedade", "sem-chave", "propriedade-em-branco"],
    )
    def test_falta_configurar_e_503_dizendo_o_que_falta(
        self, monkeypatch, google, credencial, propriedade, tem_chave, faltando
    ):
        _config(monkeypatch, propriedade=propriedade, credencial=json.dumps(credencial) if tem_chave else "")

        resposta = _visao_geral("28d")

        assert resposta.status_code == 503
        detalhe = resposta.json()["detail"]
        for nome in faltando:
            assert nome in detalhe
        assert "configurar" in detalhe

    def test_503_nao_traz_numero_nenhum_nem_toca_a_rede(self, monkeypatch, google):
        """Nunca zero: o corpo do erro não tem Visitantes, e o Google nem é
        chamado (não há o que perguntar sem a credencial)."""
        _config(monkeypatch, propriedade="", credencial="")

        corpo = _visao_geral("28d").json()

        assert set(corpo) == {"detail"}
        assert google.pedidos == []

    @pytest.mark.parametrize("propriedade", ["properties/123456789", "12345 6789", "G-ABC123", "123abc"])
    def test_propriedade_que_nao_e_so_numero_e_503(self, monkeypatch, google, credencial, propriedade):
        """O número entra no caminho da URL: o que não for só dígito é
        configuração errada, dita como tal, e não uma chamada ao Google."""
        _config(monkeypatch, propriedade=propriedade, credencial=json.dumps(credencial))

        resposta = _visao_geral("28d")

        assert resposta.status_code == 503
        assert "GA4_PROPERTY_ID" in resposta.json()["detail"]
        assert google.pedidos == []

    @pytest.mark.parametrize(
        "conteudo",
        [
            "/caminho/para/chave.json",
            "{nao e json",
            json.dumps(["lista", "nao", "chave"]),
            json.dumps({"type": "authorized_user", "client_id": "x"}),
            json.dumps({"type": "service_account"}),
        ],
        ids=["caminho-de-arquivo", "json-quebrado", "lista", "outro-tipo", "sem-campos"],
    )
    def test_chave_que_nao_e_de_service_account_e_503(self, monkeypatch, google, conteudo):
        _config(monkeypatch, propriedade=PROPRIEDADE, credencial=conteudo)

        resposta = _visao_geral("28d")

        assert resposta.status_code == 503
        assert "GOOGLE_APPLICATION_CREDENTIALS_JSON" in resposta.json()["detail"]
        assert google.pedidos == []

    def test_chave_privada_estragada_e_503_sem_ecoar_a_chave(self, monkeypatch, google, credencial):
        """O 503 diz o que está errado e nunca devolve o conteúdo da chave."""
        estragada = {
            **credencial,
            "private_key": "-----BEGIN PRIVATE KEY-----\nSEGREDO-QUEBRADO\n-----END PRIVATE KEY-----\n",
        }
        _config(monkeypatch, propriedade=PROPRIEDADE, credencial=json.dumps(estragada))

        resposta = _visao_geral("28d")

        assert resposta.status_code == 503
        assert "SEGREDO-QUEBRADO" not in resposta.text
        assert google.pedidos == []


# ─── 4. A fonte falhou: 502, nunca zero ─────────────────────────────────────


@pytest.mark.usefixtures("central_configurada")
class TestGoogleFalhou:
    """Porte de "propaga erro do client" (`ga4-provider.test.ts`): lá o erro
    subia para o cache; aqui sobe para a rota, que responde 502 com a frase.
    O cache com o último valor bom é a fatia #815."""

    @pytest.mark.parametrize(
        ("resposta_do_google", "trecho"),
        [
            (_erro_da_ga4(500, "INTERNAL", "Internal error encountered."), "HTTP 500"),
            (_erro_da_ga4(503, "UNAVAILABLE", "The service is currently unavailable."), "HTTP 503"),
            (_erro_da_ga4(429, "RESOURCE_EXHAUSTED", "Exhausted property tokens."), "Tente de novo"),
            (httpx.Response(200, content=b"<html>proxy</html>"), "ilegível"),
            (httpx.Response(200, json=["nao", "e", "relatorio"]), "fora do formato"),
            (httpx.Response(200, json={"rows": [{"dimensionValues": []}]}), "fora do formato"),
        ],
        ids=["500", "503", "429", "html", "lista", "linha-sem-metrica"],
    )
    def test_resposta_ruim_do_google_e_502_com_a_frase(self, google, resposta_do_google, trecho):
        google.forcar = resposta_do_google

        resposta = _visao_geral("28d")

        assert resposta.status_code == 502
        assert trecho in resposta.json()["detail"]
        assert "visitantes" not in resposta.json()

    @pytest.mark.parametrize(
        ("falha", "trecho"),
        [
            (httpx.ReadTimeout("lento demais"), "tempo esperado"),
            (httpx.ConnectTimeout("sem conexão"), "tempo esperado"),
            (httpx.ConnectError("rede fora"), "Não foi possível falar"),
        ],
        ids=["timeout-de-leitura", "timeout-de-conexao", "rede-fora"],
    )
    def test_google_que_nao_responde_e_502(self, google, falha, trecho):
        google.forcar = falha

        resposta = _visao_geral("28d")

        assert resposta.status_code == 502
        assert trecho in resposta.json()["detail"]

    def test_propriedade_sem_acesso_e_502_que_manda_conferir_o_papel_de_leitor(self, monkeypatch, google):
        """A GA4 responde 403 para propriedade em que a service account não
        tem papel: é o erro mais provável da conferência com a credencial real,
        e a frase diz onde olhar."""
        monkeypatch.setattr(settings, "ga4_property_id", "999999999")

        resposta = _visao_geral("28d")

        assert resposta.status_code == 502
        assert "Leitor" in resposta.json()["detail"]

    def test_chave_de_outra_service_account_e_recusada_pelo_google(self, monkeypatch, google, credencial):
        """Assinatura que o Google não reconhece: 401 lá, 502 aqui, com a
        mesma frase de conferir o acesso."""
        outra_chave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        credencial_de_outra = {
            **credencial,
            "private_key": outra_chave.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            ).decode(),
        }
        monkeypatch.setattr(settings, "google_application_credentials_json", json.dumps(credencial_de_outra))

        resposta = _visao_geral("28d")

        assert resposta.status_code == 502
        assert "HTTP 401" in resposta.json()["detail"]


@pytest.mark.usefixtures("central_configurada")
class TestPrimeiraMetrica:
    """Porte de `firstMetric` (`ga4-mappers.test.ts`), pela rota."""

    def test_intervalo_sem_dado_e_zero_de_verdade(self, google):
        """A GA4 omite `rows` quando ninguém veio: é resposta, e zero é o
        número honesto (diferente do 503, em que ninguém perguntou)."""
        google.visitantes = {}

        resposta = _visao_geral("28d")

        assert resposta.status_code == 200
        assert resposta.json()["visitantes"] == {"atual": 0, "anterior": 0, "variacao": None}

    def test_valor_que_nao_e_numero_vira_zero_e_nunca_nan(self, google):
        google.forcar = httpx.Response(200, json={"rows": [{"metricValues": [{"value": "(not set)"}]}]})

        resposta = _visao_geral("28d")

        assert resposta.status_code == 200
        assert resposta.json()["visitantes"]["atual"] == 0


# ─── 5. Nenhum teste fala com o Google ──────────────────────────────────────


@pytest.mark.usefixtures("central_configurada")
class TestTravaDeRede:
    def test_sem_o_duble_o_provedor_bate_na_trava_da_suite(self):
        """Sem o fixture `google`, a chamada sairia de verdade para a GA4. A
        trava de `tests/conftest.py` pega antes do primeiro pacote, e é isso que
        garante que nenhum teste da Central fala com o Google."""
        with pytest.raises(TentativaDeRedeNoTeste) as erro:
            provedor_google.visitantes_comparados("28d", HOJE)

        assert "analyticsdata.googleapis.com" in str(erro.value)

    def test_o_provedor_nao_espera_o_google_para_sempre(self, google):
        """Timeout curto no cliente (padrão da casa): erro honesto em segundos
        vale mais que tela pendurada."""
        _visao_geral("28d")

        assert google.clientes, "o provedor não criou cliente nenhum"
        for kwargs in google.clientes:
            timeout = kwargs.get("timeout")
            assert isinstance(timeout, httpx.Timeout)
            assert timeout.read is not None and timeout.read <= 10
            assert timeout.connect is not None and timeout.connect <= 5


# ─── 2. O gate: só Super admin ──────────────────────────────────────────────


def _rotas_da_central() -> list[tuple[str, str]]:
    """Toda rota da Central que o app REAL publica, pelo schema OpenAPI.

    Varredura, e não lista cravada: o gate está no router, e uma rota
    acrescentada por uma fatia seguinte entra aqui sozinha. A fonte é o schema
    e não `app.routes`, que volta quase vazia desde o FastAPI 0.141 (issues
    #542 e #546). O cache do schema volta como estava, para não envelhecer o
    schema de quem acrescenta rota ao app real depois (mesmo cuidado do
    `test_admin_tecnologia.py`).
    """
    from app.main import app

    cache = app.openapi_schema
    try:
        caminhos = app.openapi()["paths"]
    finally:
        app.openapi_schema = cache

    return sorted(
        (metodo.upper(), re.sub(r"\{[^}]+\}", "qualquer", caminho))
        for caminho, operacoes in caminhos.items()
        if caminho.startswith(PREFIXO)
        for metodo in operacoes
    )


ROTAS = _rotas_da_central()


def test_a_varredura_enxerga_as_rotas_da_central_no_app_real():
    """Controle antes da matriz: varredura vazia passaria em "toda rota leva
    403" sem olhar rota nenhuma. Também prova que o router está registrado no
    `main.py`. Fatia que acrescentar rota à Central entra na matriz sozinha."""
    assert ("GET", f"{PREFIXO}/visao-geral") in ROTAS


@pytest.mark.usefixtures("central_configurada", "google")
class TestSoSuperAdmin:
    @pytest.mark.parametrize("metodo,caminho", ROTAS)
    @pytest.mark.parametrize("persona", [SECRETARIA, FACILITADOR], ids=["secretaria", "facilitador"])
    def test_quem_nao_e_super_admin_leva_403(self, persona, metodo, caminho):
        assert _montar(persona).request(metodo, caminho).status_code == 403

    @pytest.mark.parametrize("metodo,caminho", ROTAS)
    def test_anonimo_leva_401(self, metodo, caminho):
        assert _montar(None).request(metodo, caminho).status_code == 401

    @pytest.mark.parametrize("metodo,caminho", ROTAS)
    def test_super_admin_passa(self, metodo, caminho):
        """O par de presença: sem ele, um 403 cravado em toda rota passaria
        pelos dois testes de cima."""
        assert _montar(SUPER_ADMIN).request(metodo, caminho).status_code == 200

    def test_super_admin_desligado_leva_403(self):
        """Sessão viva de quem foi desligado não abre os números (issue #309)."""
        desligado = _pessoa("super", "super_admin", ativo=False)
        cliente = _montar(desligado)
        cliente.app.dependency_overrides[get_supabase_client] = lambda: _SupabaseFalso([desligado])

        assert cliente.get(f"{PREFIXO}/visao-geral").status_code == 403

    def test_quem_nao_passa_no_gate_nao_gasta_consulta_no_google(self, google):
        """O gate responde antes de a fonte ser tocada."""
        _montar(SECRETARIA).get(f"{PREFIXO}/visao-geral")
        _montar(None).get(f"{PREFIXO}/visao-geral")

        assert google.pedidos == []
