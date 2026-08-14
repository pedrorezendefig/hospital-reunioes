import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import settings
from app.cron.scheduler import start_scheduler, stop_scheduler
from app.limiter import limiter
from app.middleware.request_context import RequestContextMiddleware, configure_logging
from app.routers import (
    aceite,
    admin,
    ana,
    auth,
    comentarios,
    configuracoes,
    health,
    notificacoes,
    ouvidoria,
    participantes,
    pendencias,
    perfil,
    reunioes,
    transcricao,
    webhooks,
)
from app.routers.admin import super_admins as admin_super_admins
from app.routers.admin import taxonomia as admin_taxonomia
from app.routers.admin import usuarios as admin_usuarios
from app.routers.admin import utilitarios as admin_utilitarios
from app.routers.pops import assinatura as pops_assinatura
from app.routers.pops import biblioteca as pops_biblioteca
from app.routers.pops import documento as pops_documento
from app.routers.pops import elaboracao as pops_elaboracao
from app.routers.pops import pops as pops_pops
from app.routers.pops import revisao as pops_revisao
from app.routers.pops import setores as pops_setores
from app.routers.pops import usuarios as pops_usuarios

configure_logging()

_unhandled_logger = logging.getLogger("unhandled")


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"🚀 {settings.app_name} v{settings.app_version} starting...")
    start_scheduler()
    yield
    stop_scheduler()
    print("👋 Shutting down...")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
    docs_url=f"{settings.api_prefix}/docs" if settings.debug else None,
    openapi_url=f"{settings.api_prefix}/openapi.json" if settings.debug else None,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

_cors_origins = [settings.frontend_url]
if settings.debug:
    _cors_origins.append("http://localhost:3000")

# CORS é registrado primeiro pra que RequestContextMiddleware (registrado depois)
# fique outermost no pipeline ASGI e logue tudo, inclusive preflight OPTIONS.
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
    expose_headers=["X-Total-Count", "X-Request-ID"],
)
app.add_middleware(RequestContextMiddleware)

# Routers
app.include_router(health.router, prefix=settings.api_prefix)
app.include_router(auth.router, prefix=settings.api_prefix)
app.include_router(participantes.router, prefix=settings.api_prefix)
app.include_router(reunioes.router, prefix=settings.api_prefix)
app.include_router(transcricao.router, prefix=settings.api_prefix)
app.include_router(pendencias.router, prefix=settings.api_prefix)
app.include_router(webhooks.router, prefix=settings.api_prefix)
app.include_router(aceite.router, prefix=settings.api_prefix)
app.include_router(ana.router, prefix=settings.api_prefix)
app.include_router(comentarios.router, prefix=settings.api_prefix)
app.include_router(notificacoes.router, prefix=settings.api_prefix)
app.include_router(ouvidoria.router, prefix=settings.api_prefix)
app.include_router(perfil.router, prefix=settings.api_prefix)
app.include_router(configuracoes.router, prefix=settings.api_prefix)
app.include_router(admin.router, prefix=settings.api_prefix)
app.include_router(admin_super_admins.router, prefix=settings.api_prefix)
app.include_router(admin_usuarios.router, prefix=settings.api_prefix)
app.include_router(admin_taxonomia.router, prefix=settings.api_prefix)
app.include_router(admin_utilitarios.router, prefix=settings.api_prefix)
app.include_router(pops_pops.router, prefix=settings.api_prefix)
app.include_router(pops_biblioteca.router, prefix=settings.api_prefix)
app.include_router(pops_elaboracao.router, prefix=settings.api_prefix)
app.include_router(pops_documento.router, prefix=settings.api_prefix)
app.include_router(pops_revisao.router, prefix=settings.api_prefix)
app.include_router(pops_assinatura.router, prefix=settings.api_prefix)
app.include_router(pops_setores.router, prefix=settings.api_prefix)
app.include_router(pops_usuarios.router, prefix=settings.api_prefix)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    _unhandled_logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": f"{type(exc).__name__}: {exc}"},
    )
