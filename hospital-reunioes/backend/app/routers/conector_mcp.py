"""Rotas do conector MCP da Central (ADR 0058, decisões 3 e 4; PRD #809).

As duas portas HTTP do conector, montadas na raiz (o metadata) e em `/api/mcp`
(o transporte). **Nenhuma passa pelo gate de sessão do app** (`get_current_user`
/ `require_*`): são endpoints do conector MCP e do OAuth, com o seu próprio gate,
a verificação do token do WorkOS AuthKit (`services/central_de_comando/
conector_mcp.py`). O cliente é o claude.ai de quem é Super admin, não o front.

A lógica toda mora no service; aqui fica só a tradução para HTTP: o 503 de
configuração ausente, o 401 com o cabeçalho que aponta o metadata, o CORS do
metadata e o 202 das notificações JSON-RPC.
"""

from __future__ import annotations

import logging

import anyio.to_thread
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response

from app.config import settings
from app.dependencies import get_supabase_client
from app.services.central_de_comando import conector_mcp

logger = logging.getLogger(__name__)

router = APIRouter(tags=["conector-mcp"])

# O transporte fica sob o prefixo da API (`/api/mcp`, ADR 0058, decisão 3); o
# metadata, na raiz do domínio (RFC 9728), fora do prefixo.
CAMINHO_DO_TRANSPORTE = f"{settings.api_prefix}/mcp"

# O metadata é lido pelo cliente MCP de outra origem (claude.ai), então precisa
# de CORS. Simples GET, sem preflight: o cabeçalho na resposta basta, e o CORS
# global do app (preso ao front) não o remove.
_CORS_DO_METADATA = {"Access-Control-Allow-Origin": "*"}


@router.get(conector_mcp.CAMINHO_DO_METADATA)
async def metadata_do_recurso_protegido() -> Response:
    """O documento de metadados do recurso protegido (RFC 9728). Sem config, é
    503 (erro de configuração), nunca um metadata que aponta um login inválido."""
    try:
        cfg = conector_mcp.configuracao_mcp()
    except conector_mcp.ConectorNaoConfiguradoError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=503, headers=_CORS_DO_METADATA)
    return JSONResponse(conector_mcp.metadados_do_recurso(cfg), headers=_CORS_DO_METADATA)


@router.post(CAMINHO_DO_TRANSPORTE)
async def transporte_mcp(request: Request, supabase=Depends(get_supabase_client)) -> Response:
    """O transporte Streamable HTTP do MCP. Config ausente é 503; token que não
    passa no gate é 401 com o cabeçalho que aponta o metadata; notificação
    JSON-RPC é 202 sem corpo."""
    try:
        cfg = conector_mcp.configuracao_mcp()
    except conector_mcp.ConectorNaoConfiguradoError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=503)

    token = _bearer(request)
    try:
        # O `autorizar` faz I/O síncrono (JWKS e banco); roda em thread para não
        # travar o event loop, no mesmo molde da leitura do Google no Ao vivo.
        await anyio.to_thread.run_sync(conector_mcp.autorizar, token, supabase, cfg)
    except conector_mcp.AcessoNegadoMCPError as exc:
        logger.info("[ConectorMCP] acesso negado: %s", exc)
        return JSONResponse(
            {"error": "unauthorized"},
            status_code=401,
            headers={"WWW-Authenticate": conector_mcp.desafio_www_authenticate(cfg)},
        )

    try:
        corpo = await request.json()
    except Exception:  # noqa: BLE001 - JSON malformado é erro de protocolo, não do servidor
        return JSONResponse(conector_mcp._erro(None, -32700, "JSON inválido"))

    resposta = await conector_mcp.responder_mcp(corpo)
    if resposta is None:
        return Response(status_code=202)
    return JSONResponse(resposta)


def _bearer(request: Request) -> str | None:
    """O token do cabeçalho `Authorization: Bearer <token>`, ou None."""
    autorizacao = request.headers.get("authorization", "")
    if autorizacao[:7].lower() == "bearer ":
        return autorizacao[7:].strip() or None
    return None
