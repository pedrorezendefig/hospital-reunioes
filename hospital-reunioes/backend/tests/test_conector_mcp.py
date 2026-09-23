"""O conector MCP da Central de Comando (issue #822, ADR 0058, decisões 3 e 4).

O primeiro resource server OAuth do backend. Portado do conector da Central
antiga (ADR 0006 de lá), com uma diferença de projeto: a lista de e-mails em
variável de ambiente morreu; quem conecta é quem é Super admin no cadastro
(ADR 0058, decisão 4).

Os seams testados:

- `verificar_acesso`: a verificação do token do WorkOS AuthKit, pura, com chaves
  RSA geradas no próprio teste (a trava de rede da suíte continua de pé e nada
  sai da máquina). Cobre a recusa de cada claim: assinatura, emissor, audiência,
  expiração, escopo e `email_verified`.
- `resolver_super_admin`: o gate pelo participante (e-mail sem cadastro, inativo,
  não Super admin).
- As duas ROTAS HTTP, o seam das outras fatias da Central: o metadata com CORS e
  o transporte, com o gate de pé e as ferramentas de verdade (o Ao vivo pela
  fonte de tempo real dublada, como na #816).

Chaves RSA e JWKS são montados aqui; nenhuma credencial de verdade, nenhuma
rede: o `_buscar_jwks` do módulo é dublado, e a fonte do Google é o
`google_falso` do apoio compartilhado.
"""

from __future__ import annotations

import base64
import json
import os
import sys
import time

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient
from jose import jwk as jose_jwk
from jose import jwt as jose_jwt

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from central_de_comando_apoio import (  # noqa: E402
    FACILITADOR,
    SECRETARIA,
    SUPER_ADMIN,
    SupabaseDosParticipantes,
    pessoa,
)

from app.config import settings  # noqa: E402
from app.services.central_de_comando import conector_mcp  # noqa: E402

pytestmark = pytest.mark.usefixtures("gate_e_limitador_zerados")

EMISSOR = "https://hsm-teste.authkit.app"
RECURSO = "https://api.hsm-teste.cloud"
KID = "chave-de-teste-1"
_OMITIR = object()  # sentinela: claim que o token NÃO traz


# ─── Chaves e tokens montados no teste (sem rede) ────────────────────────────


@pytest.fixture(scope="session")
def chave_do_emissor() -> rsa.RSAPrivateKey:
    """A chave RSA que o emissor de mentira usa para assinar. Uma por execução:
    a assinatura é de verdade, o emissor não."""
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(scope="session")
def outra_chave() -> rsa.RSAPrivateKey:
    """Uma segunda chave, para o token de assinatura inválida: assinado por ela,
    conferido contra o JWKS da primeira."""
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _pem_privada(chave: rsa.RSAPrivateKey) -> str:
    return chave.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()


def _pem_publica(chave: rsa.RSAPrivateKey) -> str:
    return (
        chave.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )


def jwks_de(chave: rsa.RSAPrivateKey, kid: str = KID) -> dict:
    """O JWKS que o emissor publicaria, montado da chave pública."""
    jwk_dict = jose_jwk.construct(_pem_publica(chave), algorithm="RS256").to_dict()
    jwk_dict.update({"kid": kid, "use": "sig", "alg": "RS256"})
    return {"keys": [jwk_dict]}


def token(
    chave: rsa.RSAPrivateKey,
    *,
    kid: str = KID,
    email: object = "super@hsm.com",
    email_verified: object = True,
    scope: object = "openid email read:analytics",
    aud: object = RECURSO,
    iss: object = EMISSOR,
    exp_delta: int = 3600,
    incluir_exp: bool = True,
) -> str:
    """Um token do AuthKit assinado no teste. Cada parâmetro isola um claim para
    a recusa; `_OMITIR` deixa o claim de fora."""
    agora = int(time.time())
    claims: dict = {"sub": "user_123", "iat": agora}
    for chave_claim, valor in (
        ("iss", iss),
        ("aud", aud),
        ("email", email),
        ("email_verified", email_verified),
        ("scope", scope),
    ):
        if valor is not _OMITIR:
            claims[chave_claim] = valor
    if incluir_exp:
        claims["exp"] = agora + exp_delta
    return jose_jwt.encode(claims, _pem_privada(chave), algorithm="RS256", headers={"kid": kid})


@pytest.fixture
def cfg() -> conector_mcp.ConfiguracaoMCP:
    return conector_mcp.ConfiguracaoMCP(emissor=EMISSOR, jwks_uri=f"{EMISSOR}/oauth2/jwks", recurso=RECURSO)


@pytest.fixture
def mcp_configurado(monkeypatch) -> conector_mcp.ConfiguracaoMCP:
    """As variáveis do conector preenchidas no `settings`, como no `.env` de
    quem liga a Central (as variáveis nasceram na #814, não recriadas aqui)."""
    monkeypatch.setattr(settings, "mcp_auth_issuer", EMISSOR)
    monkeypatch.setattr(settings, "mcp_resource_url", RECURSO)
    monkeypatch.setattr(settings, "mcp_auth_jwks_uri", "")
    return conector_mcp.configuracao_mcp()


@pytest.fixture
def jwks_no_emissor(monkeypatch, chave_do_emissor) -> dict:
    """Dubla a única ida de rede da verificação: o `_buscar_jwks` devolve o JWKS
    da chave de teste, e o cache nasce e morre vazio."""
    conector_mcp._jwks_cache.clear()
    conector_mcp._jwks_falha_ate.clear()
    jwks = jwks_de(chave_do_emissor)
    monkeypatch.setattr(conector_mcp, "_buscar_jwks", lambda _uri: jwks)
    yield jwks
    conector_mcp._jwks_cache.clear()
    conector_mcp._jwks_falha_ate.clear()


# ─── 1. Configuração ausente: erro de config, nunca porta aberta ─────────────


class TestConfiguracaoAusente:
    def test_sem_variaveis_levanta_nao_configurado(self, monkeypatch):
        monkeypatch.setattr(settings, "mcp_auth_issuer", "")
        monkeypatch.setattr(settings, "mcp_resource_url", "")
        monkeypatch.setattr(settings, "mcp_auth_jwks_uri", "")
        with pytest.raises(conector_mcp.ConectorNaoConfiguradoError):
            conector_mcp.configuracao_mcp()

    def test_so_emissor_ainda_e_nao_configurado(self, monkeypatch):
        monkeypatch.setattr(settings, "mcp_auth_issuer", EMISSOR)
        monkeypatch.setattr(settings, "mcp_resource_url", "")
        monkeypatch.setattr(settings, "mcp_auth_jwks_uri", "")
        with pytest.raises(conector_mcp.ConectorNaoConfiguradoError):
            conector_mcp.configuracao_mcp()

    def test_jwks_padrao_derivado_do_emissor(self, mcp_configurado):
        assert mcp_configurado.jwks_uri == f"{EMISSOR}/oauth2/jwks"
        assert mcp_configurado.recurso == RECURSO

    def test_barra_final_nao_atrapalha(self, monkeypatch):
        monkeypatch.setattr(settings, "mcp_auth_issuer", f"{EMISSOR}/")
        monkeypatch.setattr(settings, "mcp_resource_url", f"{RECURSO}/")
        monkeypatch.setattr(settings, "mcp_auth_jwks_uri", "")
        cfg = conector_mcp.configuracao_mcp()
        assert cfg.emissor == EMISSOR
        assert cfg.recurso == RECURSO
        assert cfg.jwks_uri == f"{EMISSOR}/oauth2/jwks"


# ─── 2. verificar_acesso: cada claim, com chave gerada no teste ──────────────


class TestVerificarAcesso:
    def test_token_valido_de_super_admin_devolve_email(self, cfg, chave_do_emissor):
        email = conector_mcp.verificar_acesso(token(chave_do_emissor), jwks_de(chave_do_emissor), cfg)
        assert email == "super@hsm.com"

    def test_email_normalizado_para_minusculas(self, cfg, chave_do_emissor):
        tok = token(chave_do_emissor, email="Super@HSM.com")
        assert conector_mcp.verificar_acesso(tok, jwks_de(chave_do_emissor), cfg) == "super@hsm.com"

    def test_sem_token_nega(self, cfg, chave_do_emissor):
        with pytest.raises(conector_mcp.AcessoNegadoMCPError):
            conector_mcp.verificar_acesso(None, jwks_de(chave_do_emissor), cfg)

    def test_assinatura_invalida_nega(self, cfg, chave_do_emissor, outra_chave):
        # Assinado pela outra chave, conferido contra o JWKS da primeira.
        tok = token(outra_chave)
        with pytest.raises(conector_mcp.AcessoNegadoMCPError):
            conector_mcp.verificar_acesso(tok, jwks_de(chave_do_emissor), cfg)

    def test_emissor_errado_nega(self, cfg, chave_do_emissor):
        tok = token(chave_do_emissor, iss="https://outro.authkit.app")
        with pytest.raises(conector_mcp.AcessoNegadoMCPError):
            conector_mcp.verificar_acesso(tok, jwks_de(chave_do_emissor), cfg)

    def test_audiencia_errada_nega(self, cfg, chave_do_emissor):
        tok = token(chave_do_emissor, aud="https://central.mala-ia.cloud")
        with pytest.raises(conector_mcp.AcessoNegadoMCPError):
            conector_mcp.verificar_acesso(tok, jwks_de(chave_do_emissor), cfg)

    def test_expirado_nega(self, cfg, chave_do_emissor):
        tok = token(chave_do_emissor, exp_delta=-60)
        with pytest.raises(conector_mcp.AcessoNegadoMCPError):
            conector_mcp.verificar_acesso(tok, jwks_de(chave_do_emissor), cfg)

    def test_sem_exp_nega(self, cfg, chave_do_emissor):
        tok = token(chave_do_emissor, incluir_exp=False)
        with pytest.raises(conector_mcp.AcessoNegadoMCPError):
            conector_mcp.verificar_acesso(tok, jwks_de(chave_do_emissor), cfg)

    def test_sem_escopo_de_leitura_nega(self, cfg, chave_do_emissor):
        tok = token(chave_do_emissor, scope="openid email")
        with pytest.raises(conector_mcp.AcessoNegadoMCPError):
            conector_mcp.verificar_acesso(tok, jwks_de(chave_do_emissor), cfg)

    def test_escopo_ausente_nega(self, cfg, chave_do_emissor):
        tok = token(chave_do_emissor, scope=_OMITIR)
        with pytest.raises(conector_mcp.AcessoNegadoMCPError):
            conector_mcp.verificar_acesso(tok, jwks_de(chave_do_emissor), cfg)

    def test_escopo_pela_lista_scp_vale(self, cfg, chave_do_emissor):
        # WorkOS pode serializar o escopo como lista `scp` em vez de string.
        tok = jose_jwt.encode(
            {
                "sub": "u",
                "iss": EMISSOR,
                "aud": RECURSO,
                "email": "super@hsm.com",
                "email_verified": True,
                "scp": ["read:analytics"],
                "exp": int(time.time()) + 3600,
            },
            _pem_privada(chave_do_emissor),
            algorithm="RS256",
            headers={"kid": KID},
        )
        assert conector_mcp.verificar_acesso(tok, jwks_de(chave_do_emissor), cfg) == "super@hsm.com"

    def test_email_nao_verificado_nega(self, cfg, chave_do_emissor):
        tok = token(chave_do_emissor, email_verified=False)
        with pytest.raises(conector_mcp.AcessoNegadoMCPError):
            conector_mcp.verificar_acesso(tok, jwks_de(chave_do_emissor), cfg)

    def test_email_verified_ausente_nega(self, cfg, chave_do_emissor):
        tok = token(chave_do_emissor, email_verified=_OMITIR)
        with pytest.raises(conector_mcp.AcessoNegadoMCPError):
            conector_mcp.verificar_acesso(tok, jwks_de(chave_do_emissor), cfg)

    def test_email_verified_string_true_vale(self, cfg, chave_do_emissor):
        # O JWT Template do AuthKit pode serializar o booleano como a string "true".
        tok = token(chave_do_emissor, email_verified="true")
        assert conector_mcp.verificar_acesso(tok, jwks_de(chave_do_emissor), cfg) == "super@hsm.com"

    def test_sem_email_nega(self, cfg, chave_do_emissor):
        tok = token(chave_do_emissor, email=_OMITIR)
        with pytest.raises(conector_mcp.AcessoNegadoMCPError):
            conector_mcp.verificar_acesso(tok, jwks_de(chave_do_emissor), cfg)

    def test_alg_none_recusado(self, cfg, chave_do_emissor):
        """`alg: none` (token sem assinatura) é recusado: o verificador fixa
        RS256, então nenhum token sem assinatura passa (invariante travada)."""

        def _seg(dado: dict) -> str:
            return base64.urlsafe_b64encode(json.dumps(dado).encode()).rstrip(b"=").decode()

        payload = {
            "sub": "u",
            "iss": EMISSOR,
            "aud": RECURSO,
            "email": "super@hsm.com",
            "email_verified": True,
            "scope": "read:analytics",
            "exp": int(time.time()) + 3600,
        }
        tok = f"{_seg({'alg': 'none', 'typ': 'JWT'})}.{_seg(payload)}."
        with pytest.raises(conector_mcp.AcessoNegadoMCPError):
            conector_mcp.verificar_acesso(tok, jwks_de(chave_do_emissor), cfg)

    def test_confusao_de_algoritmo_hs256_recusada(self, cfg, chave_do_emissor):
        """Token HS256 assinado com um segredo qualquer é recusado: com RS256
        fixo, a chave pública do JWKS nunca é usada como segredo HMAC (a confusão
        de algoritmo clássica de resource server)."""
        tok = jose_jwt.encode(
            {
                "sub": "u",
                "iss": EMISSOR,
                "aud": RECURSO,
                "email": "super@hsm.com",
                "email_verified": True,
                "scope": "read:analytics",
                "exp": int(time.time()) + 3600,
            },
            "segredo-publico-qualquer",
            algorithm="HS256",
        )
        with pytest.raises(conector_mcp.AcessoNegadoMCPError):
            conector_mcp.verificar_acesso(tok, jwks_de(chave_do_emissor), cfg)


# ─── 3. resolver_super_admin: o gate pelo participante ───────────────────────


class TestResolverSuperAdmin:
    def test_super_admin_ativo_passa(self):
        supabase = SupabaseDosParticipantes([SUPER_ADMIN])
        assert conector_mcp.resolver_super_admin(supabase, "super@hsm.com")["id"] == "super"

    def test_email_sem_participante_nega(self):
        supabase = SupabaseDosParticipantes([SUPER_ADMIN])
        with pytest.raises(conector_mcp.AcessoNegadoMCPError):
            conector_mcp.resolver_super_admin(supabase, "ninguem@hsm.com")

    def test_participante_inativo_nega(self):
        desligado = pessoa("super", "super_admin", ativo=False)
        supabase = SupabaseDosParticipantes([desligado])
        with pytest.raises(conector_mcp.AcessoNegadoMCPError):
            conector_mcp.resolver_super_admin(supabase, "super@hsm.com")

    @pytest.mark.parametrize("quem", [SECRETARIA, FACILITADOR], ids=["secretaria", "facilitador"])
    def test_participante_que_nao_e_super_admin_nega(self, quem):
        supabase = SupabaseDosParticipantes([quem])
        with pytest.raises(conector_mcp.AcessoNegadoMCPError):
            conector_mcp.resolver_super_admin(supabase, quem["email"])


# ─── 4. A rota do metadata: RFC 9728, com CORS ───────────────────────────────


def _app_metadata(com_cors: bool = False) -> TestClient:
    from app.routers import conector_mcp as router_mcp

    app = FastAPI()
    if com_cors:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[settings.frontend_url],
            allow_credentials=True,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type"],
        )
    app.include_router(router_mcp.router)
    return TestClient(app)


class TestMetadataDoRecurso:
    def test_metadata_publica_recurso_emissor_e_escopo(self, mcp_configurado):
        resposta = _app_metadata().get(conector_mcp.CAMINHO_DO_METADATA)

        assert resposta.status_code == 200, resposta.text
        corpo = resposta.json()
        assert corpo["resource"] == RECURSO
        assert corpo["authorization_servers"] == [EMISSOR]
        assert conector_mcp.ESCOPO_DE_LEITURA in corpo["scopes_supported"]

    def test_metadata_vem_com_cors(self, mcp_configurado):
        """O claude.ai lê o metadata de outra origem: o cabeçalho de CORS sobra
        mesmo com o CORS global do app preso ao endereço do front."""
        resposta = _app_metadata(com_cors=True).get(
            conector_mcp.CAMINHO_DO_METADATA, headers={"Origin": "https://claude.ai"}
        )

        assert resposta.status_code == 200
        assert resposta.headers["access-control-allow-origin"] == "*"

    def test_metadata_sem_config_e_503(self, monkeypatch):
        monkeypatch.setattr(settings, "mcp_auth_issuer", "")
        monkeypatch.setattr(settings, "mcp_resource_url", "")
        monkeypatch.setattr(settings, "mcp_auth_jwks_uri", "")

        assert _app_metadata().get(conector_mcp.CAMINHO_DO_METADATA).status_code == 503


# ─── 5. A rota do transporte: gate, ferramenta e degradação ──────────────────

CAMINHO_MCP = f"{settings.api_prefix}/mcp"


def _cliente_mcp(participantes: list[dict] | None = None, supabase: object | None = None) -> TestClient:
    """O router de verdade num app mínimo, com o limitador de taxa ligado como
    no `main.py` (a resposta do 429 é a do handler da casa)."""
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded

    from app.dependencies import get_supabase_client
    from app.limiter import limiter
    from app.routers import conector_mcp as router_mcp

    if supabase is None:
        tabela = participantes if participantes is not None else [SUPER_ADMIN, SECRETARIA, FACILITADOR]
        supabase = SupabaseDosParticipantes(tabela)
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(router_mcp.router)
    app.dependency_overrides[get_supabase_client] = lambda: supabase
    return TestClient(app)


def _rpc(cliente: TestClient, corpo: dict, tok: str | None) -> object:
    cabecalhos = {"Authorization": f"Bearer {tok}"} if tok else {}
    return cliente.post(CAMINHO_MCP, json=corpo, headers=cabecalhos)


INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}}


@pytest.fixture
def ao_vivo_na_ga4(google_falso):
    """A fonte de tempo real do Google de mentira, respondendo o Ao vivo, no
    molde da #816. Sem ela, o `runRealtimeReport` cairia no 400 do dublê."""

    def responder(metodo: str, corpo: dict) -> dict | None:
        if (
            metodo != "runRealtimeReport"
            or corpo.get("metrics") != [{"name": "activeUsers"}]
            or corpo.get("dimensions")
        ):
            return None
        return {
            "metricHeaders": [{"name": "activeUsers", "type": "TYPE_INTEGER"}],
            "rows": [{"metricValues": [{"value": "42"}]}],
            "rowCount": 1,
        }

    google_falso.respondedores.append(responder)
    return google_falso


@pytest.mark.usefixtures("mcp_configurado", "jwks_no_emissor")
class TestTransporteComTokenValido:
    def test_initialize_responde_capabilities(self, chave_do_emissor):
        resposta = _rpc(_cliente_mcp(), INIT, token(chave_do_emissor))

        assert resposta.status_code == 200, resposta.text
        corpo = resposta.json()
        assert corpo["result"]["protocolVersion"] == conector_mcp.PROTOCOLO_MCP
        assert "tools" in corpo["result"]["capabilities"]

    def test_tools_list_traz_o_ao_vivo(self, chave_do_emissor):
        pedido = {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
        resposta = _rpc(_cliente_mcp(), pedido, token(chave_do_emissor))

        nomes = [f["name"] for f in resposta.json()["result"]["tools"]]
        assert conector_mcp.FERRAMENTA_AO_VIVO in nomes

    def test_ferramenta_ao_vivo_responde_o_numero(self, chave_do_emissor, central_configurada, ao_vivo_na_ga4):
        """O critério central: token válido de Super admin ativo, a ferramenta
        responde. O número vem da fonte de tempo real dublada."""
        pedido = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": conector_mcp.FERRAMENTA_AO_VIVO, "arguments": {}},
        }
        resposta = _rpc(_cliente_mcp(), pedido, token(chave_do_emissor))

        assert resposta.status_code == 200, resposta.text
        resultado = resposta.json()["result"]
        assert resultado["isError"] is False
        assert resultado["structuredContent"] == {"pessoasAgora": 42}

    def test_notificacao_initialized_nao_tem_corpo(self, chave_do_emissor):
        pedido = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        resposta = _rpc(_cliente_mcp(), pedido, token(chave_do_emissor))

        assert resposta.status_code == 202
        assert resposta.content == b""

    def test_metodo_desconhecido_e_erro_json_rpc(self, chave_do_emissor):
        pedido = {"jsonrpc": "2.0", "id": 9, "method": "resources/write", "params": {}}
        resposta = _rpc(_cliente_mcp(), pedido, token(chave_do_emissor))

        assert resposta.status_code == 200
        assert resposta.json()["error"]["code"] == -32601


@pytest.mark.usefixtures("mcp_configurado", "jwks_no_emissor")
class TestTransporteRecusaCom401:
    def test_sem_token_e_401_com_cabecalho_do_metadata(self, chave_do_emissor):
        resposta = _rpc(_cliente_mcp(), INIT, None)

        assert resposta.status_code == 401
        desafio = resposta.headers["www-authenticate"]
        assert "resource_metadata=" in desafio
        assert conector_mcp.CAMINHO_DO_METADATA in desafio

    @pytest.mark.parametrize(
        "tok_kwargs",
        [
            {"aud": "https://central.mala-ia.cloud"},
            {"iss": "https://outro.authkit.app"},
            {"exp_delta": -60},
            {"scope": "openid email"},
            {"email_verified": False},
        ],
        ids=["audiencia", "emissor", "expirado", "sem-escopo", "email-nao-verificado"],
    )
    def test_token_ruim_e_401(self, chave_do_emissor, tok_kwargs):
        resposta = _rpc(_cliente_mcp(), INIT, token(chave_do_emissor, **tok_kwargs))

        assert resposta.status_code == 401
        assert "resource_metadata=" in resposta.headers["www-authenticate"]

    def test_assinatura_invalida_e_401(self, outra_chave):
        resposta = _rpc(_cliente_mcp(), INIT, token(outra_chave))

        assert resposta.status_code == 401

    def test_jwks_indisponivel_e_401_nao_500(self, monkeypatch, chave_do_emissor):
        """JWKS fora do ar é falha de autorização, não erro do servidor: qualquer
        falha é 401 (fail-closed), nunca um 500 que vaze rastro interno."""

        def _falha(_uri):
            raise RuntimeError("emissor fora do ar")

        conector_mcp._jwks_cache.clear()
        monkeypatch.setattr(conector_mcp, "_buscar_jwks", _falha)

        resposta = _rpc(_cliente_mcp(), INIT, token(chave_do_emissor))

        assert resposta.status_code == 401
        assert "resource_metadata=" in resposta.headers["www-authenticate"]

    def test_bearer_malformado_nega_antes_de_tocar_a_rede(self, monkeypatch):
        """Bearer lixo (não é JWT) é 401 ANTES de qualquer rede: o fetch do JWKS
        nem é chamado, senão um flood de tokens malformados prenderia threads do
        pool (o mesmo do Ao vivo) no timeout de um emissor lento."""
        tocou = {"fetch": False}

        def _marca(_uri):
            tocou["fetch"] = True
            raise RuntimeError("não podia ter sido chamado")

        conector_mcp._jwks_cache.clear()
        conector_mcp._jwks_falha_ate.clear()
        monkeypatch.setattr(conector_mcp, "_buscar_jwks", _marca)

        resposta = _rpc(_cliente_mcp(), INIT, "isto-nao-e-um-jwt")

        assert resposta.status_code == 401
        assert tocou["fetch"] is False, "o fetch do JWKS foi tocado por um Bearer malformado"

    def test_emissor_fora_nao_multiplica_o_fetch(self, monkeypatch, chave_do_emissor):
        """Emissor fora do ar abre o circuito: a segunda requisição dentro do
        cooldown nega sem tocar a rede de novo (não multiplica bloqueio de thread)."""
        chamadas = {"n": 0}

        def _falha(_uri):
            chamadas["n"] += 1
            raise RuntimeError("emissor fora do ar")

        conector_mcp._jwks_cache.clear()
        conector_mcp._jwks_falha_ate.clear()
        monkeypatch.setattr(conector_mcp, "_buscar_jwks", _falha)
        cliente = _cliente_mcp()

        r1 = _rpc(cliente, INIT, token(chave_do_emissor))
        r2 = _rpc(cliente, INIT, token(chave_do_emissor))

        assert r1.status_code == 401
        assert r2.status_code == 401
        assert chamadas["n"] == 1, "o circuito devia pular o segundo fetch"

    def test_falha_inesperada_do_gate_e_401_nao_500(self, chave_do_emissor):
        """Falha inesperada no gate de participante (I/O ao banco) é 401
        (fail-closed), não 500 que vaze rastro interno."""

        class SupabaseQueQuebra:
            def table(self, _nome):
                raise RuntimeError("banco fora do ar")

        resposta = _rpc(_cliente_mcp(supabase=SupabaseQueQuebra()), INIT, token(chave_do_emissor))

        assert resposta.status_code == 401

    def test_email_sem_participante_e_401(self, chave_do_emissor):
        resposta = _rpc(_cliente_mcp([SUPER_ADMIN]), INIT, token(chave_do_emissor, email="ninguem@hsm.com"))

        assert resposta.status_code == 401

    def test_participante_inativo_e_401(self, chave_do_emissor):
        desligado = pessoa("super", "super_admin", ativo=False)
        resposta = _rpc(_cliente_mcp([desligado]), INIT, token(chave_do_emissor, email="super@hsm.com"))

        assert resposta.status_code == 401

    @pytest.mark.parametrize("quem", [SECRETARIA, FACILITADOR], ids=["secretaria", "facilitador"])
    def test_participante_que_nao_e_super_admin_e_401(self, chave_do_emissor, quem):
        resposta = _rpc(_cliente_mcp([quem]), INIT, token(chave_do_emissor, email=quem["email"]))

        assert resposta.status_code == 401


class TestTransporteSemConfig:
    def test_config_ausente_e_503_e_a_ferramenta_nao_roda(self, monkeypatch, chave_do_emissor):
        monkeypatch.setattr(settings, "mcp_auth_issuer", "")
        monkeypatch.setattr(settings, "mcp_resource_url", "")
        monkeypatch.setattr(settings, "mcp_auth_jwks_uri", "")
        chamou = {"provedor": False}

        def _nunca():
            chamou["provedor"] = True
            return 0

        monkeypatch.setattr(conector_mcp.provedor_google, "pessoas_no_site_agora", _nunca)
        pedido = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": conector_mcp.FERRAMENTA_AO_VIVO, "arguments": {}},
        }

        resposta = _rpc(_cliente_mcp(), pedido, token(chave_do_emissor))

        assert resposta.status_code == 503
        assert chamou["provedor"] is False


# ─── 6. Fora do gate de sessão e visível ao enumerador do snapshot ───────────


class TestForaDoGateDeSessao:
    @staticmethod
    def _nomes_de_deps(dependant, acc: set[str]) -> set[str]:
        for sub in getattr(dependant, "dependencies", []):
            nome = getattr(getattr(sub, "call", None), "__name__", None)
            if nome:
                acc.add(nome)
            TestForaDoGateDeSessao._nomes_de_deps(sub, acc)
        return acc

    def _rotas_do_conector(self):
        """As rotas pelo próprio router, não por `app.routes`: desde o FastAPI
        0.141 o `include_router` guarda o router incluído em vez de copiar as
        rotas para cima, e `app.routes` volta sem APIRoute de router (o venv
        local está na 0.136, o CI na nova; isto vale nas duas). Que elas cheguem
        ao app montado é o que `test_as_rotas_estao_no_schema_publico` prova."""
        from fastapi.routing import APIRoute

        from app.routers import conector_mcp as router_mcp

        alvos = {conector_mcp.CAMINHO_DO_METADATA, CAMINHO_MCP}
        return [r for r in router_mcp.router.routes if isinstance(r, APIRoute) and r.path in alvos]

    def test_as_duas_rotas_do_conector_existem(self):
        caminhos = {r.path for r in self._rotas_do_conector()}
        assert caminhos == {conector_mcp.CAMINHO_DO_METADATA, CAMINHO_MCP}

    def test_nenhuma_passa_pelo_gate_de_sessao(self):
        for rota in self._rotas_do_conector():
            deps = self._nomes_de_deps(rota.dependant, set())
            assert not any(d.startswith("require_") for d in deps), f"{rota.path} tem gate de papel: {deps}"
            assert "get_current_user" not in deps, f"{rota.path} passa pelo gate de sessão: {deps}"

    def test_as_rotas_estao_no_schema_publico(self):
        """No schema quer dizer visíveis ao enumerador do snapshot (que conta
        pelo OpenAPI): assim `no_app == no_schema` continua valendo."""
        from app.main import app

        caminhos = set(app.openapi()["paths"])
        assert conector_mcp.CAMINHO_DO_METADATA in caminhos
        assert CAMINHO_MCP in caminhos


# ─── 7. Decisões de protocolo do dispatch (direto no responder_mcp) ──────────


class TestProtocoloJsonRpc:
    """As decisões de protocolo do `responder_mcp`, testadas na função (o gate
    já é coberto pelas rotas): params inválido e o batching removido no 2025-06-18."""

    async def test_tools_call_com_params_nao_dict_e_invalid_params(self):
        """`params` que não é objeto (string, número, lista) é -32602, nunca um
        500 por desreferenciar o que não é dict."""
        resposta = await conector_mcp.responder_mcp(
            {"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": "isto-devia-ser-objeto"}
        )

        assert resposta["error"]["code"] == -32602

    async def test_lista_nao_e_tratada_como_batch(self):
        """Batching foi removido no protocolo 2025-06-18: uma lista não é lote,
        é requisição inválida (-32600), e a resposta é um objeto, nunca uma lista."""
        resposta = await conector_mcp.responder_mcp([{"jsonrpc": "2.0", "id": 1, "method": "ping"}])

        assert isinstance(resposta, dict)
        assert resposta["error"]["code"] == -32600

    async def test_mensagem_que_nao_e_objeto_json_rpc_e_invalida(self):
        assert (await conector_mcp.responder_mcp(42))["error"]["code"] == -32600


# ─── 8. O limite de requisições da rota pública (issue #866) ─────────────────


@pytest.mark.usefixtures("mcp_configurado", "jwks_no_emissor")
class TestLimiteDeRequisicoes:
    """A rota do transporte é pública (o gate é o token, não a sessão do app),
    então tem teto por endereço, no molde das portas públicas da Ouvidoria:
    60 por minuto."""

    def test_o_61o_pedido_no_mesmo_minuto_e_429_e_nao_chega_ao_gate(self, monkeypatch, chave_do_emissor):
        """Quem martela a rota leva 429 no 61º pedido do mesmo minuto. O teto
        vale antes do gate: nem um token válido fura, e o pedido barrado não
        gasta a verificação do token (JWKS e banco)."""
        cliente = _cliente_mcp()
        dentro_do_teto = [_rpc(cliente, INIT, None) for _ in range(60)]
        assert [r.status_code for r in dentro_do_teto] == [401] * 60

        chamou_o_gate = {"n": 0}
        autorizar_de_verdade = conector_mcp.autorizar

        def _conta(*args, **kwargs):
            chamou_o_gate["n"] += 1
            return autorizar_de_verdade(*args, **kwargs)

        monkeypatch.setattr(conector_mcp, "autorizar", _conta)

        passou_do_teto = _rpc(cliente, INIT, token(chave_do_emissor))

        assert passou_do_teto.status_code == 429
        assert chamou_o_gate["n"] == 0, "o pedido acima do teto chegou ao gate"

    def test_a_conversa_normal_do_conector_passa_folgada(self, chave_do_emissor, central_configurada, ao_vivo_na_ga4):
        """Uma conversa no claude.ai: initialize, a notificação de pronto,
        tools/list e três chamadas de ferramenta. Cinco conversas inteiras no
        mesmo minuto (30 pedidos, metade do teto), mais do que qualquer uso de
        uma pessoa, passam sem nenhum 429 e com as respostas de verdade."""
        chamada_do_ao_vivo = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": conector_mcp.FERRAMENTA_AO_VIVO, "arguments": {}},
        }
        conversa = [
            INIT,
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {**chamada_do_ao_vivo, "id": 3},
            {**chamada_do_ao_vivo, "id": 4},
            {**chamada_do_ao_vivo, "id": 5},
        ]
        cliente = _cliente_mcp()
        tok = token(chave_do_emissor)

        respostas = [_rpc(cliente, pedido, tok) for _ in range(5) for pedido in conversa]

        assert len(respostas) == 30
        assert [r.status_code for r in respostas] == [200, 202, 200, 200, 200, 200] * 5
        ultima = respostas[-1].json()["result"]
        assert ultima["isError"] is False
        assert ultima["structuredContent"] == {"pessoasAgora": 42}
