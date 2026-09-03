"""Request-scoped context (request_id/user_id) + JSON log formatter + ASGI middleware.

ContextVars compartilhados entre middleware e formatter: o middleware seta
request_id/user_id no início do request, o JsonFormatter lê esses valores em
cada chamada de logging dentro do mesmo request. Pensado como único módulo de
wiring de logs estruturados da app.
"""

from __future__ import annotations

import contextvars
import datetime as _dt
import json
import logging
import re
import sys
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# ---------------------------------------------------------------------------
# ContextVars
# ---------------------------------------------------------------------------

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")
user_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("user_id", default="")


def get_request_id() -> str:
    return request_id_var.get()


def get_user_id() -> str:
    return user_id_var.get()


def set_user_id(value: str | None) -> None:
    user_id_var.set(value or "")


# ---------------------------------------------------------------------------
# Mascaramento de segredo no path
# ---------------------------------------------------------------------------

# Os parâmetros de path que carregam segredo. Hoje só `token`, do portal do
# setor e do Aceite interno; a varredura que trava porta irmã (parâmetro novo
# sem classificação, rota nova com `{token}`) vive em
# `tests/test_token_fora_do_log.py`.
_PARAMS_DE_SEGREDO = frozenset({"token"})

# Barra repetida no path (`//`) é forma válida na requisição e não pode furar a
# comparação de prefixo.
_BARRAS_REPETIDAS = re.compile(r"/{2,}")

# Quando o roteador não casa rota nenhuma não há `path_params` no scope, e o
# path cru voltaria ao log com o token inteiro. Nesses prefixos tudo que vem
# depois é potencialmente o token, então some inteiro: sem rota casada não há
# diagnóstico a preservar ali.
_PREFIXOS_COM_TOKEN_NO_PATH = ("/api/aceite/", "/api/ouvidoria-setor/")


def _mascarar_por_prefixo(path: str) -> str:
    """A rede do 404 do roteador, e ela não pode depender da forma do path.

    Barra repetida (base de URL com barra final), segmento a mais antes do
    token e caixa diferente no prefixo casavam o `startswith` cru de um jeito
    que deixava o token na cauda. Aqui o path é normalizado antes de comparar, e
    o que vem depois do prefixo sai por inteiro, e não só o primeiro segmento.
    """
    normalizado = _BARRAS_REPETIDAS.sub("/", path)
    minusculo = normalizado.lower()
    for prefixo in _PREFIXOS_COM_TOKEN_NO_PATH:
        if not minusculo.startswith(prefixo):
            continue
        if not normalizado[len(prefixo) :]:
            return path
        # A caixa do prefixo vem do path original: o log mostra o que chegou.
        return normalizado[: len(prefixo)] + "{token}"
    return path


def path_para_log(scope: dict) -> str:
    """O path da requisição sem o segredo que ele carrega (issue #465).

    No portal do setor e no Aceite interno o token É o path
    (`/api/ouvidoria-setor/{token}`) e o banco guarda só o hash: gravar o path
    cru entregaria, a quem lê o log do container, um link utilizável até o token
    ser usado ou expirar, sem perfil nenhum na Ouvidoria.

    Sai só o valor do segredo, trocado pelo nome do parâmetro: a rota continua
    reconhecível no log, e id de recurso (manifestação, reunião) continua
    inteiro, porque é ele que liga a linha do log ao caso.

    A troca é por segmento, e não por substring: um token de um caractere faria
    `str.replace` picotar o path inteiro. O `replace` global fica de rede,
    porque um valor que atravesse barra não casaria segmento nenhum e voltaria
    cru ao log.

    O app não roda sob `--root-path`, e por isso `scope["path"]` basta. Se um
    dia rodar, o prefixo do root entra no path e `_PREFIXOS_COM_TOKEN_NO_PATH`
    precisa acompanhar, senão a rede do 404 para de casar.
    """
    path = scope.get("path", "")
    params = scope.get("path_params")
    if params is None:
        return _mascarar_por_prefixo(path)
    for nome, valor in params.items():
        if nome not in _PARAMS_DE_SEGREDO:
            continue
        texto = str(valor)
        if not texto:
            continue
        marca = "{" + nome + "}"
        segmentos = path.split("/")
        if texto in segmentos:
            path = "/".join(marca if segmento == texto else segmento for segmento in segmentos)
        elif texto in path:
            # Rede: valor que atravessa barra não casa segmento nenhum, e sem
            # isto voltaria cru ao log.
            path = path.replace(texto, marca)
    return path


# ---------------------------------------------------------------------------
# JSON formatter
# ---------------------------------------------------------------------------

_STD_KEYS = {
    "args",
    "asctime",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "message",
    "module",
    "msecs",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "thread",
    "threadName",
    "taskName",
}


class JsonFormatter(logging.Formatter):
    """Formata cada LogRecord como linha NDJSON com timestamp ISO 8601 UTC."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": _dt.datetime.now(_dt.UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = get_request_id()
        if request_id:
            payload["request_id"] = request_id
        user_id = get_user_id()
        if user_id:
            payload["user_id"] = user_id
        for key, value in record.__dict__.items():
            if key in _STD_KEYS or key.startswith("_"):
                continue
            payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


def configure_logging(level: int = logging.INFO) -> None:
    """Reconfigura o root logger pra emitir JSON estruturado em stdout."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=level, handlers=[handler], force=True)


# ---------------------------------------------------------------------------
# ASGI middleware
# ---------------------------------------------------------------------------

_request_logger = logging.getLogger("app.requests")


def _ip_do_cliente(request: Request) -> str:
    """O IP que o Starlette resolveu, nunca o header cru (issue #543).

    O container sobe com `--proxy-headers
    --forwarded-allow-ips=<faixas privadas>`, então o `ProxyHeadersMiddleware`
    do uvicorn já decidiu, antes da app, se o `X-Forwarded-For` daquele peer
    vale: quando vale, ele reescreve `scope["client"]`; quando não vale (peer
    fora da lista de confiança), o que fica é o endereço do socket. Ler
    `request.headers` aqui devolveria ao cliente o poder de escrever o próprio
    IP no log, o mesmo furo que a issue #349 fechou no rate limit.

    Volta vazio quando o transporte não informa peer, e não um erro: a linha é
    escrita no `finally` do middleware mais externo, e explodir ali trocaria um
    campo faltando por falha no log de toda requisição.

    O hospital sai por um IP só (NAT): o campo separa tráfego de fora do de
    dentro, e não identifica uma pessoa.
    """
    cliente = request.client
    return cliente.host if cliente else ""


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Gera request_id (ou usa X-Request-ID recebido), mede latência e loga 1 linha por request."""

    async def dispatch(self, request: Request, call_next):
        incoming = request.headers.get("x-request-id")
        request_id = incoming or uuid.uuid4().hex
        rid_token = request_id_var.set(request_id)
        uid_token = user_id_var.set("")
        start = time.perf_counter()
        status_code = 500
        try:
            response: Response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            latency_ms = round((time.perf_counter() - start) * 1000, 2)
            _request_logger.info(
                "request",
                extra={
                    # Nunca `request.url.path` cru: no portal do setor e no
                    # Aceite o token é o path (issue #465).
                    "path": path_para_log(request.scope),
                    "method": request.method,
                    "client_ip": _ip_do_cliente(request),
                    "status_code": status_code,
                    "latency_ms": latency_ms,
                },
            )
            request_id_var.reset(rid_token)
            user_id_var.reset(uid_token)
