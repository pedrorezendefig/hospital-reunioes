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

**Só leitura.** Três ferramentas, cada uma casca fina sobre o que a Central já
lê: o Ao vivo (as pessoas no site agora, sem cache, `provedor_google.
pessoas_no_site_agora`) e os números do Site e do Instagram por período (#823).
As duas de período leem do MESMO cache das telas (o painel e o registro de
telas, #815/#818/#819), sem leitura própria nem ida à fonte por conta: o Site
sai do bloco de Visitantes do painel e da tela Dados do Google, o Instagram da
tela do Instagram. O contrato é o do conector antigo (ADR 0006 de lá), com uma
diferença de nome no payload do Site: as áreas do hospital com página são as
Áreas do site (o nome da casa, ADR 0058, decisão 7), no lugar do nome antigo, de
marca. O protocolo não expõe escrita nenhuma; método desconhecido é erro
JSON-RPC "método não encontrado".
"""

from __future__ import annotations

import json
import logging
import math
import time
from dataclasses import dataclass
from datetime import datetime

import anyio.to_thread
import httpx
from jose import jwt

from app.config import settings
from app.services.central_de_comando import cache, provedor_google, provedor_instagram, telas, visao_geral
from app.services.central_de_comando.variacao import variacao_relativa

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

# As ferramentas mantêm os nomes do conector antigo, para o contrato não mudar
# para quem já conecta (ADR 0058, decisão 3).
FERRAMENTA_AO_VIVO = "get_active_now"
FERRAMENTA_SITE = "get_site_analytics"
FERRAMENTA_INSTAGRAM = "get_instagram_analytics"

# Os períodos que cada ferramenta de tendência aceita: o Site tem 7, 28 e 90
# dias; o Instagram só 7 e 28 (a Graph API entrega no máximo 30 dias por
# consulta), exatamente como as telas da Central.
_PERIODOS_SITE = ("7d", "28d", "90d")
_PERIODOS_INSTAGRAM = ("7d", "28d")

# O nome da tela Dados do Google no registro de telas. A chave de cache de uma
# tela é `(nome, período)` (o mesmo par que o Atualizar agora endereça), então o
# Site usa este nome nos dois lugares: para ler o payload e para ancorar nela
# metade do frescor.
_TELA_DADOS_DO_GOOGLE = "dados-do-google"

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

# O JWKS por emissor, em memória do processo, com validade curta. O cache serve
# a chave normal sem tocar a rede; passado o TTL, a próxima verificação rebusca,
# e é por aí que a chave rotacionada do AuthKit entra sem redeploy. O TTL também
# fecha a amplificação: um token com `kid` aleatório não dispara uma ida de rede
# por requisição (a assinatura seria negada de qualquer forma).
_JWKS_TTL_SEGUNDOS = 600
# Circuit breaker: um emissor fora do ar não pode multiplicar bloqueio de thread
# (o pool é o mesmo do Ao vivo). A primeira falha "abre o circuito" por este
# tempo, e nele o fetch é pulado (nega direto), em vez de cada requisição prender
# uma thread no timeout da rede.
_JWKS_FALHA_COOLDOWN_SEGUNDOS = 30
_jwks_cache: dict[str, tuple[dict, float]] = {}
_jwks_falha_ate: dict[str, float] = {}


def _buscar_jwks(jwks_uri: str) -> dict:
    """A ida de rede ao JWKS do emissor. O único ponto de rede da verificação;
    os testes o dublam (chaves geradas no próprio teste, sem rede)."""
    with httpx.Client(timeout=_TIMEOUT) as cliente:
        resposta = cliente.get(jwks_uri)
        resposta.raise_for_status()
        return resposta.json()


def jwks_do_emissor(cfg: ConfiguracaoMCP) -> dict:
    """O JWKS do emissor: do cache enquanto está fresco (TTL), senão rebusca e
    guarda. Falha de rede abre o circuito por um cooldown curto (o fetch seguinte
    é pulado, sem tocar a rede) e sobe para o `autorizar`, que a traduz em 401."""
    agora = time.monotonic()
    entrada = _jwks_cache.get(cfg.jwks_uri)
    if entrada is not None and (agora - entrada[1]) < _JWKS_TTL_SEGUNDOS:
        return entrada[0]
    aberto_ate = _jwks_falha_ate.get(cfg.jwks_uri)
    if aberto_ate is not None and agora < aberto_ate:
        raise RuntimeError("JWKS do emissor indisponível (circuito aberto)")
    try:
        jwks = _buscar_jwks(cfg.jwks_uri)
    except Exception:
        _jwks_falha_ate[cfg.jwks_uri] = time.monotonic() + _JWKS_FALHA_COOLDOWN_SEGUNDOS
        raise
    _jwks_cache[cfg.jwks_uri] = (jwks, time.monotonic())
    _jwks_falha_ate.pop(cfg.jwks_uri, None)
    return jwks


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


def _token_bem_formado(token: str) -> bool:
    """O token tem os 3 segmentos de um JWS compacto e um header decodificável
    com `alg`. Conferido ANTES de qualquer rede: um Bearer malformado é negado
    sem gastar o fetch do JWKS nem prender uma thread no timeout do emissor."""
    if token.count(".") != 2:
        return False
    try:
        header = jwt.get_unverified_header(token)
    except Exception:  # noqa: BLE001 - header ilegível: token malformado, nega
        return False
    return isinstance(header, dict) and bool(header.get("alg"))


def autorizar(token: str | None, supabase, cfg: ConfiguracaoMCP) -> dict:
    """As duas etapas do gate, na ordem: o token do AuthKit, depois o
    participante Super admin. Devolve o participante, ou levanta
    `AcessoNegadoMCPError` (sempre 401).

    Fail-closed ponta a ponta: token ausente ou malformado nega ANTES de tocar a
    rede (sem fetch do JWKS); JWKS indisponível e qualquer falha inesperada do
    gate (I/O ao Supabase) também viram 401, nunca 500. Faz I/O de rede (JWKS) e
    ao banco, então o chamador roda em thread para não travar o event loop."""
    if not token:
        raise AcessoNegadoMCPError("token ausente")
    if not _token_bem_formado(token):
        raise AcessoNegadoMCPError("token malformado")
    try:
        jwks = jwks_do_emissor(cfg)
    except Exception as exc:  # noqa: BLE001 - JWKS indisponível: fail-closed, nega (qualquer falha é 401)
        raise AcessoNegadoMCPError(f"JWKS indisponível ({type(exc).__name__})") from exc
    email = verificar_acesso(token, jwks, cfg)
    try:
        return resolver_super_admin(supabase, email)
    except AcessoNegadoMCPError:
        raise
    except Exception as exc:  # noqa: BLE001 - falha inesperada do gate (I/O ao banco): fail-closed, 401
        raise AcessoNegadoMCPError(f"falha no gate de participante ({type(exc).__name__})") from exc


# ─── O protocolo MCP (transporte Streamable HTTP, JSON-RPC 2.0) ──────────────


# O glossário que cada ferramenta carrega na descrição, da seção "Central de
# Comando" do CONTEXT.md: é ele que faz o Claude falar a língua da casa
# (Visitantes, Áreas do site, Alcance) e tratar o que não é medido como não
# medido, nunca como zero (honestidade do dado). Porte do `glossario.ts` do
# conector antigo, com o nome novo da Área do site.
GLOSSARIO_SITE = (
    "Números do Site do Hospital São Matheus (fonte: Google Analytics), somente leitura. "
    'O campo "visitantes" traz as pessoas diferentes que acessaram o Site no período (os usuários '
    'ativos do Google), com o número do período anterior de mesmo tamanho e "variacaoPct" (12 quer '
    "dizer +12%; null quer dizer que não há base para comparar). "
    '"areasDoSite" é o ranking das Áreas do site, os grupos de páginas por serviço do hospital '
    "(Maternidade, Emergência 24h, Centro de Imagem, Centro Médico, Laboratório); o número fala do "
    "site, não da procura real pelo serviço. "
    '"origens" é a Origem do público (busca, direto, redes, anúncios, e os rótulos gentis Outros e '
    'Não identificado para o que o Google não classificou). "dispositivos" são as Visitas por '
    'dispositivo. Em "contatos", cada canal tem um "estado": "medido" traz os "cliques" reais (hoje '
    'WhatsApp e Fale Conosco), "em-construcao" quer dizer que o Site ainda não avisa o Google quando '
    'o contato acontece, e "nao-medido" quer dizer que não há como medir; "em-construcao" e '
    '"nao-medido" nunca são zero. Em "frescor", "atualizadoHaMin" diz há quantos minutos o dado foi '
    'lido e "falhaAoAtualizar" verdadeiro quer dizer que é o último valor bom guardado. Não invente '
    "números que não estejam no payload."
)

GLOSSARIO_INSTAGRAM = (
    "Números do Instagram do Hospital São Matheus, somente leitura. "
    '"disponivel" falso quer dizer que o dado não pôde ser lido agora (por exemplo, token ou '
    'configuração), e não é zero nem "sem seguidores": diga que está indisponível, com o motivo, '
    "nunca relate como queda. As métricas comparadas (Alcance, Visualizações, Interações, Contas "
    'que engajaram) trazem o atual, o anterior e "variacaoPct". "alcance" são as contas diferentes '
    'que viram o conteúdo (pessoas); "visualizacoes" são as vezes que o conteúdo foi exibido. '
    '"seguidores" é estoque (o total agora), sem variação percentual: o que varia por período é o '
    '"crescimento". "interacoes" é a soma de curtidas, comentários, salvamentos e compartilhamentos, '
    'e "detalheInteracoes" abre essas quatro partes. "principaisPublicacoes" vêm ordenadas por '
    "interações no período, sem Stories. Não invente números que não estejam no payload."
)


def ferramentas() -> list[dict]:
    """A lista de ferramentas do `tools/list`: o Ao vivo, os números do Site e os
    do Instagram. As descrições carregam o glossário da seção "Central de
    Comando" do CONTEXT.md, para o Claude falar a língua da casa."""
    return [
        {
            "name": FERRAMENTA_AO_VIVO,
            "title": "Pessoas no site agora",
            "description": (
                "Quantas pessoas estão no site do hospital agora, em tempo real (o Ao vivo da Central de "
                "Comando). Sem ninguém no site, é zero de verdade, não falta de dado. Não recebe argumentos."
            ),
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": FERRAMENTA_SITE,
            "title": "Números do Site",
            "description": f"Os números do Site do hospital no período pedido (a Central de Comando). {GLOSSARIO_SITE}",
            "inputSchema": _schema_de_periodo(_PERIODOS_SITE, "7d, 28d ou 90d"),
        },
        {
            "name": FERRAMENTA_INSTAGRAM,
            "title": "Números do Instagram",
            "description": (
                f"Os números do Instagram do hospital no período pedido (a Central de Comando). {GLOSSARIO_INSTAGRAM}"
            ),
            "inputSchema": _schema_de_periodo(_PERIODOS_INSTAGRAM, "7d ou 28d"),
        },
    ]


def _schema_de_periodo(permitidos: tuple[str, ...], texto: str) -> dict:
    """O `inputSchema` de uma ferramenta de período: um `period` obrigatório,
    restrito aos períodos que a ferramenta aceita (o Instagram não tem 90 dias)."""
    return {
        "type": "object",
        "properties": {
            "period": {"type": "string", "enum": list(permitidos), "description": f"A janela de tempo: {texto}."}
        },
        "required": ["period"],
        "additionalProperties": False,
    }


async def _executar_ferramenta(nome: str, argumentos: dict) -> dict:
    """Roda a ferramenta pedida e devolve o resultado do `tools/call`. Falha da
    fonte vira resultado com `isError`, o jeito do MCP de dizer "a ferramenta
    respondeu que não deu", nunca um número inventado. As duas ferramentas de
    período fazem I/O (o cache das telas, que pode ir à GA4 ou à Graph API), então
    rodam em thread, no mesmo molde do Ao vivo, para não travar o event loop."""
    if nome == FERRAMENTA_AO_VIVO:
        return await _ferramenta_ao_vivo()
    if nome == FERRAMENTA_SITE:
        return await anyio.to_thread.run_sync(_ferramenta_site, argumentos)
    if nome == FERRAMENTA_INSTAGRAM:
        return await anyio.to_thread.run_sync(_ferramenta_instagram, argumentos)
    return _resultado_de_erro(f"Ferramenta desconhecida: {nome}")


async def _ferramenta_ao_vivo() -> dict:
    """O Ao vivo: as pessoas no site agora, sem cache (o único número em tempo
    real da Central), casca fina sobre o provedor do Google."""
    try:
        pessoas = await anyio.to_thread.run_sync(provedor_google.pessoas_no_site_agora)
    except (provedor_google.GoogleNaoConfiguradoError, provedor_google.GoogleError) as exc:
        return _resultado_de_erro(str(exc))
    return _resultado_estruturado(
        {"pessoasAgora": pessoas},
        texto=f"{pessoas} pessoas estão no site do hospital agora.",
    )


def _ferramenta_site(argumentos: dict) -> dict:
    """Os números do Site no período, lidos do MESMO cache das telas: os
    Visitantes comparados vêm do bloco do painel (`visao_geral.ler_visitantes`) e
    o resto da tela Dados do Google (`telas.ler`). O frescor é o pior caso das
    duas chaves (`_frescor_do_site`), para não dizer "fresco" com o manchete de
    Visitantes velho. Fonte fora sem número guardado ou não configurada viram
    resultado com `isError`, com a frase segura da Central, nunca um número
    inventado."""
    periodo = _periodo_valido(argumentos, _PERIODOS_SITE)
    if periodo is None:
        return _resultado_de_erro(f"Período inválido. Use um de: {', '.join(_PERIODOS_SITE)}.")
    try:
        visitantes, chave_visitantes = visao_geral.ler_visitantes(periodo)
        if visitantes["estado"] != "ok":
            return _resultado_de_erro(visitantes.get("motivo") or "Os números do Site estão indisponíveis agora.")
        google = telas.ler(_TELA_DADOS_DO_GOOGLE, periodo)
    except (provedor_google.GoogleNaoConfiguradoError, provedor_google.GoogleError) as exc:
        return _resultado_de_erro(str(exc))
    frescor = _frescor_do_site(chave_visitantes, periodo)
    return _resultado_estruturado(serializar_site(periodo, visitantes, google, frescor, cache.agora_utc()))


def _frescor_do_site(chave_visitantes: tuple | None, periodo: str) -> dict:
    """O frescor do Site é o PIOR caso entre as chaves que compõem o payload: os
    Visitantes (a chave do painel) e a tela Dados do Google. Combina pela mesma
    `cache.frescor` que o painel usa (a hora do número mais velho, e "falhou" se
    a renovação de qualquer uma falhou). As duas chaves têm TTL e estado de falha
    independentes; sem combinar, o payload poderia dizer "fresco, sem falha" com
    o manchete de Visitantes velho renovando com erro, a desonestidade que o
    glossário proíbe. É o que o conector antigo fazia ancorando o frescor do Site
    na fonte dos Visitantes."""
    return cache.cache_da_central.frescor(chave_visitantes, (_TELA_DADOS_DO_GOOGLE, periodo)).como_dict()


def _ferramenta_instagram(argumentos: dict) -> dict:
    """Os números do Instagram no período, lidos do MESMO cache da tela
    (`telas.ler`). Não configurado, token vencido sem número guardado ou fonte
    fora sem número guardado viram "indisponível" com o motivo (glossário:
    `disponivel:false` não é zero nem queda), nunca um `isError`."""
    periodo = _periodo_valido(argumentos, _PERIODOS_INSTAGRAM)
    if periodo is None:
        return _resultado_de_erro(f"Período inválido. Use um de: {', '.join(_PERIODOS_INSTAGRAM)}.")
    try:
        tela = telas.ler("instagram", periodo)
    except (provedor_instagram.InstagramNaoConfiguradoError, provedor_instagram.InstagramError) as exc:
        return _resultado_estruturado(serializar_instagram_indisponivel(periodo, str(exc)))
    return _resultado_estruturado(serializar_instagram_disponivel(periodo, tela, cache.agora_utc()))


def _periodo_valido(argumentos: dict, permitidos: tuple[str, ...]) -> str | None:
    """O `period` do pedido, se for um dos que a ferramenta aceita; senão `None`,
    e a ferramenta responde com uma frase clara (como o `assertPreset` do conector
    antigo), sem tocar a fonte."""
    periodo = (argumentos or {}).get("period")
    return periodo if periodo in permitidos else None


# ─── A serialização do payload (porte do `serialize.ts` do conector antigo,
# testada direto, com a chave das áreas renomeada para "areasDoSite") ────────


def serializar_site(periodo: str, visitantes: dict, google: dict, frescor: dict, agora: datetime) -> dict:
    """O payload do Site para o Claude, equivalente ao `serializeSite` do conector
    antigo, com a chave das áreas renomeada para "areasDoSite" (o nome da casa).
    Os Visitantes vêm do bloco do painel; movimento, áreas, origens, dispositivos
    e contatos, da tela Dados do Google. O `frescor` chega pronto do chamador (o
    pior caso das duas chaves, `_frescor_do_site`), e não sai de uma chave só, que
    mentiria se a outra tivesse vencido com falha de renovação."""
    return {
        "periodo": periodo,
        "visitantes": _comparado(visitantes["atual"], visitantes["anterior"]),
        "movimento": [
            {"data": dia["data"], "visitantes": dia["visitantes"], "anterior": dia["visitantes_anterior"]}
            for dia in google["movimento"]
        ],
        "areasDoSite": {
            "disponivel": True,
            "itens": [
                {
                    "chave": area["chave"],
                    "nome": area["nome"],
                    "visitas": area["visitas"],
                    "visitasAnterior": area["visitas_anterior"],
                    "variacaoPct": _variacao_pct(area["visitas"], area["visitas_anterior"]),
                }
                for area in google["areas_do_site"]
            ],
        },
        "origens": [
            {"chave": o["chave"], "rotulo": o["rotulo"], "visitas": o["visitas"]} for o in google["origem_do_publico"]
        ],
        "dispositivos": [
            {"chave": d["chave"], "rotulo": d["rotulo"], "visitas": d["visitas"]} for d in google["dispositivos"]
        ],
        "contatos": [_contato(canal) for canal in google["contatos_gerados"]],
        "frescor": serializar_frescor(frescor, agora),
    }


def _contato(canal: dict) -> dict:
    """Um canal de Contatos gerados: o medido traz os cliques, os outros só o
    estado honesto (o `ContatoPayload` do conector antigo)."""
    contato = {"chave": canal["chave"], "rotulo": canal["rotulo"], "estado": canal["estado"]}
    if canal["estado"] == "medido":
        contato["cliques"] = canal["cliques"]
    return contato


def serializar_instagram_disponivel(periodo: str, tela: dict, agora: datetime) -> dict:
    """O payload do Instagram quando os números vieram, equivalente ao
    `serializeInstagram` do conector antigo com a saúde presente."""
    seguidores = tela["seguidores"]
    engajamento = tela["engajamento"]
    partes = {parte["chave"]: parte["valor"] for parte in engajamento["partes"]}
    return {
        "periodo": periodo,
        "disponivel": True,
        "seguidores": {
            "total": seguidores["total"],
            "crescimento": _comparado(seguidores["crescimento"], seguidores["crescimento_anterior"]),
        },
        "alcance": _comparado(tela["alcance"]["atual"], tela["alcance"]["anterior"]),
        "visualizacoes": _comparado(tela["visualizacoes"]["atual"], tela["visualizacoes"]["anterior"]),
        "interacoes": _comparado(engajamento["interacoes"], engajamento["interacoes_anterior"]),
        "contasEngajadas": _comparado(engajamento["contas_engajadas"], engajamento["contas_engajadas_anterior"]),
        "detalheInteracoes": {
            "curtidas": partes["curtidas"],
            "comentarios": partes["comentarios"],
            "salvamentos": partes["salvamentos"],
            "compartilhamentos": partes["compartilhamentos"],
        },
        "principaisPublicacoes": [
            {
                "id": pub["id"],
                "legenda": pub["legenda"],
                "tipo": pub["tipo"],
                "interacoes": pub["interacoes"],
                "link": pub["link"],
                "quando": pub["data"],
            }
            for pub in tela["principais_publicacoes"]
        ],
        "frescor": serializar_frescor(tela["frescor"], agora),
    }


def serializar_instagram_indisponivel(periodo: str, motivo: str) -> dict:
    """O payload do Instagram quando o dado não pôde ser lido (não configurado,
    token vencido ou fonte fora, sem número guardado): "indisponível" com o
    motivo, nunca zero nem erro. Equivale ao `serializeInstagram` do conector
    antigo com a saúde nula, e o glossário manda dizer indisponível, não queda."""
    return {
        "periodo": periodo,
        "disponivel": False,
        "principaisPublicacoes": [],
        "frescor": {"atualizadoHaMin": None, "falhaAoAtualizar": True, "motivo": motivo},
    }


def serializar_frescor(frescor: dict, agora: datetime) -> dict:
    """O frescor pronto para o Claude: há quantos minutos o dado foi lido e se a
    atualização falhou. Porte do `serializeFrescor` do conector antigo, sobre o
    frescor que a leitura pelo cache devolve (`atualizado_em` em ISO 8601, ou nulo
    quando a chave nunca foi lida)."""
    atualizado_em = frescor.get("atualizado_em")
    if atualizado_em is None:
        atualizado_ha_min = None
    else:
        minutos = (agora - datetime.fromisoformat(atualizado_em)).total_seconds() / 60
        atualizado_ha_min = math.floor(minutos + 0.5)
    return {
        "atualizadoHaMin": atualizado_ha_min,
        "falhaAoAtualizar": bool(frescor.get("atualizacao_falhou")),
        "motivo": frescor.get("motivo"),
    }


def _comparado(atual: int, anterior: int) -> dict:
    """Um número comparado: o atual, o anterior e a variação em pontos percentuais
    (o `Comparado` do conector antigo)."""
    return {"atual": atual, "anterior": anterior, "variacaoPct": _variacao_pct(atual, anterior)}


def _variacao_pct(atual: int, anterior: int) -> int | None:
    """A variação em pontos percentuais inteiros (0,12 vira 12), ou `None` sem base
    de comparação. Arredonda meio ponto para cima, como o `Math.round` que o
    conector antigo usava, para o número bater com o dele."""
    fracao = variacao_relativa(atual, anterior)
    return None if fracao is None else math.floor(fracao * 100 + 0.5)


def _resultado_estruturado(payload: dict, *, texto: str | None = None) -> dict:
    """O resultado de uma ferramenta que devolve um objeto: o objeto em
    `structuredContent` e o mesmo em texto (uma frase, ou o JSON), no molde do Ao
    vivo. Nunca é `isError`: um Instagram indisponível é resposta válida, não
    falha."""
    corpo = texto if texto is not None else json.dumps(payload, ensure_ascii=False)
    return {
        "content": [{"type": "text", "text": corpo}],
        "structuredContent": payload,
        "isError": False,
    }


def _resultado_de_erro(mensagem: str) -> dict:
    return {"content": [{"type": "text", "text": mensagem}], "isError": True}


async def responder_mcp(mensagem: object) -> dict | None:
    """Responde uma mensagem JSON-RPC do MCP (objeto único). Devolve o objeto de
    resposta, ou `None` para notificação (sem resposta).

    Sem batching: o JSON-RPC batching foi removido no protocolo 2025-06-18. Uma
    lista, ou qualquer coisa que não seja um objeto JSON-RPC 2.0, cai em -32600
    (requisição inválida), nunca é processada como lote."""
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
        params = mensagem.get("params")
        if params is not None and not isinstance(params, dict):
            # `params` fora do objeto JSON-RPC (string, número, lista): -32602,
            # nunca um 500 por desreferenciar o que não é dict.
            return _erro(id_, -32602, "Params inválidos")
        params = params or {}
        argumentos = params.get("arguments")
        if argumentos is not None and not isinstance(argumentos, dict):
            # `arguments` que não é objeto (array, string, número): -32602, no
            # mesmo molde do `params`, nunca um 500 quando a ferramenta for
            # desreferenciar o que não é dict.
            return _erro(id_, -32602, "Argumentos inválidos")
        resultado = await _executar_ferramenta(params.get("name"), argumentos or {})
        return _ok(id_, resultado)
    if metodo == "ping":
        return _ok(id_, {})
    return _erro(id_, -32601, f"Método não encontrado: {metodo}")


def _ok(id_: object, resultado: dict) -> dict:
    return {"jsonrpc": "2.0", "id": id_, "result": resultado}


def _erro(id_: object, codigo: int, mensagem: str) -> dict:
    return {"jsonrpc": "2.0", "id": id_, "error": {"code": codigo, "message": mensagem}}
