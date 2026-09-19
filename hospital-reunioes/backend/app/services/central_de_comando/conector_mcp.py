"""Conector MCP da Central de Comando (ADR 0058, decisões 3 e 4; PRD #809).

O primeiro resource server OAuth do backend. Publica os números da Central para
o Claude de quem é Super admin, por um servidor MCP só-leitura no domínio da
API, portado do conector da Central antiga (`central-de-comando-hsm`, ADR 0006
de lá). Duas portas HTTP, montadas pelo `routers/conector_mcp.py`, as duas FORA
do gate de sessão do app:

- `GET /.well-known/oauth-protected-resource`: o documento de metadados do
  recurso protegido (RFC 9728), na raiz do domínio da API, servido com CORS. É
  o que o claude.ai lê para achar o servidor de login (o WorkOS AuthKit).
- `POST /api/mcp`: o transporte Streamable HTTP do MCP, atrás da verificação do
  token do WorkOS e do gate de Super admin.

**O gate, em duas etapas.** Primeiro o token do AuthKit: assinatura contra o
JWKS do emissor, `iss`, `aud` (o Resource Indicator), expiração, o escopo de
leitura e `email_verified` verdadeiro. Depois o participante: o e-mail
verificado do token acha a pessoa no cadastro, e ela precisa estar ativa e ser
Super admin. Rebaixou ou desligou, o conector para na hora, sem editar lista
nenhuma. A lista de e-mails em variável de ambiente do conector antigo NÃO foi
portada (ADR 0058, decisão 4).

**Fail-closed.** Qualquer falha de autorização é `AcessoNegadoMCPError`, que a rota
devolve como 401 com o cabeçalho que aponta os metadados, nunca 403: o cliente
MCP responde ao 401 refazendo o login OAuth. E `email_verified` ausente é negado
(estar no cadastro não basta). Config ausente é `ConectorNaoConfiguradoError`:
sem emissor ou sem recurso, nenhum token é aceito e nenhuma ferramenta roda.

**Só leitura.** A única ferramenta desta fatia é o Ao vivo (as pessoas no site
agora), casca fina sobre `provedor_google.pessoas_no_site_agora`. O protocolo
não expõe escrita nenhuma; método desconhecido é erro JSON-RPC "método não
encontrado".
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import anyio.to_thread
import httpx
from jose import jwt

from app.config import settings
from app.services.central_de_comando import provedor_google

logger = logging.getLogger(__name__)

# O caminho bem conhecido do metadata do recurso protegido (RFC 9728), na raiz
# do domínio, nunca sob `/api`: é ali que o cliente MCP procura.
CAMINHO_DO_METADATA = "/.well-known/oauth-protected-resource"

# O escopo de leitura que o token precisa carregar. O mesmo nome que o conector
# antigo concedia; o claude.ai o pede porque o metadata o anuncia, e o WorkOS o
# emite no claim `scope` do token. Sem ele, o token é negado (um token de outro
# app do mesmo AuthKit não abre a Central).
ESCOPO_DE_LEITURA = "read:analytics"

# A versão do protocolo MCP que este servidor fala. Portado read-only: sem
# batching (removido na 2025-06-18), sem escrita, sem stream iniciado pelo
# servidor (o GET no transporte é 405, tratado pelo próprio FastAPI).
PROTOCOLO_MCP = "2025-06-18"

_SERVIDOR = {"name": "central-de-comando-hsm", "version": settings.app_version}

# A ferramenta do Ao vivo mantém o nome do conector antigo, para o contrato não
# mudar para quem já conecta (ADR 0058, decisão 3).
FERRAMENTA_AO_VIVO = "get_active_now"

_TIMEOUT = httpx.Timeout(10.0, connect=3.0)


class ConectorNaoConfiguradoError(RuntimeError):
    """Falta configurar o conector MCP no backend (o emissor do AuthKit ou o
    recurso). Fecha a porta: sem config, a rota responde erro de configuração e
    nenhum token é aceito. A mensagem não ecoa nome de variável ao cliente."""


class AcessoNegadoMCPError(Exception):
    """Qualquer falha de autorização do conector: token ausente, inválido, sem
    escopo, e-mail não verificado, e-mail sem participante, participante inativo
    ou que não é Super admin. Sempre 401 (nunca 403): o cliente MCP responde ao
    401 refazendo o login. O motivo fica no log, não no corpo ao cliente."""


@dataclass(frozen=True)
class ConfiguracaoMCP:
    """O emissor do AuthKit, o JWKS dele e o recurso (o Resource Indicator, que
    é a audiência do token). Lida do ambiente pelo `configuracao_mcp`."""

    emissor: str
    jwks_uri: str
    recurso: str


def configuracao_mcp(cfg=settings) -> ConfiguracaoMCP:
    """Lê a config do conector do ambiente, ou levanta `ConectorNaoConfigurado
    Error`. JWKS padrão = `<emissor>/oauth2/jwks` (formato AuthKit); a variável
    própria só é precisa se o provedor expõe o JWKS noutro caminho.

    Emissor e recurso sem barra final: o `iss` e o `aud` do token do AuthKit não
    a têm, e uma barra sobrando faria a validação falhar em silêncio."""
    emissor = (cfg.mcp_auth_issuer or "").strip().rstrip("/")
    recurso = (cfg.mcp_resource_url or "").strip().rstrip("/")
    jwks_uri = (cfg.mcp_auth_jwks_uri or "").strip() or (f"{emissor}/oauth2/jwks" if emissor else "")
    if not emissor or not recurso or not jwks_uri:
        raise ConectorNaoConfiguradoError("O conector MCP da Central ainda não está configurado no backend.")
    return ConfiguracaoMCP(emissor=emissor, jwks_uri=jwks_uri, recurso=recurso)


# ─── O metadata do recurso protegido (RFC 9728) ──────────────────────────────


def metadados_do_recurso(cfg: ConfiguracaoMCP) -> dict:
    """O documento que o cliente MCP lê no caminho bem conhecido: o recurso, o
    servidor de login (o emissor do AuthKit) e o escopo de leitura."""
    return {
        "resource": cfg.recurso,
        "authorization_servers": [cfg.emissor],
        "scopes_supported": [ESCOPO_DE_LEITURA],
        "bearer_methods_supported": ["header"],
    }


def url_do_metadata(cfg: ConfiguracaoMCP) -> str:
    """O endereço público do metadata, montado a partir do recurso (não do host
    do request): o recurso É o domínio público da API, então não depende de o
    proxy do Coolify sobrescrever o `x-forwarded-host`."""
    return f"{cfg.recurso}{CAMINHO_DO_METADATA}"


def desafio_www_authenticate(cfg: ConfiguracaoMCP) -> str:
    """O cabeçalho `WWW-Authenticate` do 401, que aponta o metadata (RFC 9728,
    seção 5.1). É por ele que o cliente MCP acha o caminho bem conhecido."""
    return f'Bearer resource_metadata="{url_do_metadata(cfg)}"'


# ─── A verificação do token do WorkOS AuthKit ────────────────────────────────


def verificar_acesso(token: str | None, jwks: dict, cfg: ConfiguracaoMCP) -> str:
    """Confere o token do AuthKit e devolve o e-mail verificado, ou levanta
    `AcessoNegadoMCPError`.

    Todas têm de valer: assinatura RS256 contra o JWKS do emissor, `iss`, `aud`
    (o recurso), `exp` presente, o escopo de leitura no claim `scope`/`scp` e
    `email_verified` verdadeiro. O algoritmo é fixado em RS256 de propósito: sem
    isso, um token `alg: none` ou HS256 assinado com um segredo público passaria.
    """
    if not token:
        raise AcessoNegadoMCPError("token ausente")
    try:
        claims = jwt.decode(
            token,
            jwks,
            algorithms=["RS256"],
            audience=cfg.recurso,
            issuer=cfg.emissor,
            options={"require_exp": True, "require_aud": True, "verify_aud": True, "verify_iss": True},
        )
    except Exception as exc:  # noqa: BLE001 - gate de segurança: qualquer erro de decodificação nega
        raise AcessoNegadoMCPError(f"token inválido ({type(exc).__name__})") from exc

    if ESCOPO_DE_LEITURA not in _escopos(claims):
        raise AcessoNegadoMCPError("token sem o escopo de leitura")

    verificado = claims.get("email_verified")
    if verificado is not True and verificado != "true":
        # Fail-closed: claim ausente ou falso nega. Estar no cadastro não basta.
        raise AcessoNegadoMCPError("e-mail não verificado")

    email = claims.get("email")
    if not isinstance(email, str) or not email.strip():
        raise AcessoNegadoMCPError("token sem e-mail")
    return email.strip().lower()


def _escopos(claims: dict) -> list[str]:
    """Os escopos do token, do `scope` (string separada por espaço, padrão
    OAuth) ou do `scp` (lista). Claim ausente ou malformado é lista vazia, e a
    verificação nega por falta de escopo."""
    escopo = claims.get("scope")
    if isinstance(escopo, str):
        return escopo.split()
    scp = claims.get("scp")
    if isinstance(scp, list):
        return [s for s in scp if isinstance(s, str)]
    return []


# ─── O JWKS do emissor ───────────────────────────────────────────────────────

# O JWKS por emissor, em memória do processo. Chave rara de rodar, e trocar o
# emissor exige redeploy (zera o cache). Refetch quando o `kid` do token não
# está no cache guardado: é como a chave rotacionada entra sem redeploy.
_JWKS_CACHE: dict[str, dict] = {}


def _buscar_jwks(jwks_uri: str) -> dict:
    """A ida de rede ao JWKS do emissor. O único ponto de rede da verificação;
    os testes o dublam (chaves geradas no próprio teste, sem rede)."""
    with httpx.Client(timeout=_TIMEOUT) as cliente:
        resposta = cliente.get(jwks_uri)
        resposta.raise_for_status()
        return resposta.json()


def jwks_do_emissor(cfg: ConfiguracaoMCP, kid: str | None = None) -> dict:
    """O JWKS do emissor, do cache quando o `kid` já está nele; senão busca e
    guarda. Sem `kid`, serve o cache se houver."""
    cache = _JWKS_CACHE.get(cfg.jwks_uri)
    if cache is not None and (not kid or _tem_kid(cache, kid)):
        return cache
    jwks = _buscar_jwks(cfg.jwks_uri)
    _JWKS_CACHE[cfg.jwks_uri] = jwks
    return jwks


def _tem_kid(jwks: dict, kid: str) -> bool:
    return any(isinstance(k, dict) and k.get("kid") == kid for k in jwks.get("keys", []))


def _kid_do_token(token: str) -> str | None:
    try:
        return jwt.get_unverified_header(token).get("kid")
    except Exception:  # noqa: BLE001 - token malformado: sem kid, a verificação nega adiante
        return None


# ─── O gate de Super admin, pelo participante ────────────────────────────────

# Só os campos que o gate lê: nenhum dos opcionais da migration (que o fallback
# de coluna trataria), então o select é o mesmo em qualquer ambiente.
_CAMPOS_DO_GATE = "id, email, ativo, is_super_admin, access_profile"


def resolver_super_admin(supabase, email: str) -> dict:
    """Acha o participante pelo e-mail verificado e exige ativo e Super admin,
    ou levanta `AcessoNegadoMCPError`. Reusa os mesmos predicados do gate de sessão
    (`is_super_admin`, `foi_desligado`), mas nega com 401, não com o 403 do
    `require_super_admin`: aqui a resposta a "não pode" é refazer o login."""
    from app.dependencies import foi_desligado, is_super_admin, selecionar_participantes

    resultado = selecionar_participantes(supabase, _CAMPOS_DO_GATE, lambda q: q.eq("email", email))
    linhas = resultado.data or []
    if not linhas:
        raise AcessoNegadoMCPError("e-mail sem participante no cadastro")
    participante = linhas[0]
    if foi_desligado(participante):
        raise AcessoNegadoMCPError("participante desativado")
    if not is_super_admin(participante):
        raise AcessoNegadoMCPError("participante não é Super admin")
    return participante


def autorizar(token: str | None, supabase, cfg: ConfiguracaoMCP) -> dict:
    """As duas etapas do gate, na ordem: o token do AuthKit, depois o
    participante Super admin. Devolve o participante, ou levanta `AcessoNegado
    MCP`."""
    if not token:
        raise AcessoNegadoMCPError("token ausente")
    jwks = jwks_do_emissor(cfg, _kid_do_token(token))
    email = verificar_acesso(token, jwks, cfg)
    return resolver_super_admin(supabase, email)


# ─── O protocolo MCP (transporte Streamable HTTP, JSON-RPC 2.0) ──────────────


def ferramentas() -> list[dict]:
    """A lista de ferramentas do `tools/list`. Só o Ao vivo nesta fatia."""
    return [
        {
            "name": FERRAMENTA_AO_VIVO,
            "title": "Pessoas no site agora",
            "description": (
                "Quantas pessoas estão no site do hospital agora, em tempo real (o Ao vivo da Central de "
                "Comando). Sem ninguém no site, é zero de verdade, não falta de dado. Não recebe argumentos."
            ),
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        }
    ]


async def _executar_ferramenta(nome: str, _argumentos: dict) -> dict:
    """Roda a ferramenta pedida e devolve o resultado do `tools/call`. Falha da
    fonte vira resultado com `isError`, o jeito do MCP de dizer "a ferramenta
    respondeu que não deu", nunca um número inventado."""
    if nome != FERRAMENTA_AO_VIVO:
        return _resultado_de_erro(f"Ferramenta desconhecida: {nome}")
    try:
        pessoas = await anyio.to_thread.run_sync(provedor_google.pessoas_no_site_agora)
    except (provedor_google.GoogleNaoConfiguradoError, provedor_google.GoogleError) as exc:
        return _resultado_de_erro(str(exc))
    return {
        "content": [{"type": "text", "text": f"{pessoas} pessoas estão no site do hospital agora."}],
        "structuredContent": {"pessoasAgora": pessoas},
        "isError": False,
    }


def _resultado_de_erro(mensagem: str) -> dict:
    return {"content": [{"type": "text", "text": mensagem}], "isError": True}


async def responder_mcp(mensagem: object) -> dict | list | None:
    """Responde uma mensagem JSON-RPC do MCP, ou uma lista delas. Devolve o
    objeto de resposta, uma lista de respostas, ou `None` quando não há resposta
    a enviar (notificação, ou um lote só de notificações)."""
    if isinstance(mensagem, list):
        respostas = [r for m in mensagem if (r := await _responder_uma(m)) is not None]
        return respostas or None
    return await _responder_uma(mensagem)


async def _responder_uma(mensagem: object) -> dict | None:
    if not isinstance(mensagem, dict) or mensagem.get("jsonrpc") != "2.0":
        return _erro(None, -32600, "Requisição JSON-RPC inválida")
    if "id" not in mensagem:
        return None  # notificação JSON-RPC (ex.: notifications/initialized): sem resposta

    metodo = mensagem.get("method")
    id_ = mensagem.get("id")

    if metodo == "initialize":
        return _ok(
            id_,
            {
                "protocolVersion": PROTOCOLO_MCP,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": _SERVIDOR,
            },
        )
    if metodo == "tools/list":
        return _ok(id_, {"tools": ferramentas()})
    if metodo == "tools/call":
        params = mensagem.get("params") or {}
        resultado = await _executar_ferramenta(params.get("name"), params.get("arguments") or {})
        return _ok(id_, resultado)
    if metodo == "ping":
        return _ok(id_, {})
    return _erro(id_, -32601, f"Método não encontrado: {metodo}")


def _ok(id_: object, resultado: dict) -> dict:
    return {"jsonrpc": "2.0", "id": id_, "result": resultado}


def _erro(id_: object, codigo: int, mensagem: str) -> dict:
    return {"jsonrpc": "2.0", "id": id_, "error": {"code": codigo, "message": mensagem}}
