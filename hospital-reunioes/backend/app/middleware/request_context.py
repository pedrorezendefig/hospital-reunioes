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

# Quando o roteador não casa rota nenhuma não há `path_params` no scope, e o
# path cru voltaria ao log com o token inteiro. Nesses prefixos o primeiro
# segmento É o token, então ele sai mesmo sem rota casada.
_PREFIXOS_COM_TOKEN_NO_PATH = ("/api/aceite/", "/api/ouvidoria-setor/")


def _mascarar_por_prefixo(path: str) -> str:
    for prefixo in _PREFIXOS_COM_TOKEN_NO_PATH:
        if not path.startswith(prefixo):
            continue
        resto = path[len(prefixo) :]
        if not resto:
            return path
        _, barra, cauda = resto.partition("/")
        return f"{prefixo}{{token}}{barra}{cauda}"
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
    """
    path = scope.get("path", "")
    params = scope.get("path_params")
    if params is None:
        return _mascarar_por_prefixo(path)
    for nome, valor in params.items():
        if nome not in _PARAMS_DE_SEGREDO:
            continue
        texto = str(valor)
        if texto:
            path = path.replace(texto, "{" + nome + "}")
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
                    "status_code": status_code,
                    "latency_ms": latency_ms,
                },
            )
            request_id_var.reset(rid_token)
            user_id_var.reset(uid_token)
