import asyncio
import logging

from fastapi import APIRouter, Response

from app.config import settings
from app.dependencies import get_supabase_client

router = APIRouter(tags=["health"])
_logger = logging.getLogger("app.health")

_DB_CHECK_TIMEOUT_SECONDS = 2.0


async def _check_db() -> bool:
    """Ping mínimo no Supabase via PostgREST. True se respondeu dentro do timeout."""

    def _ping() -> bool:
        client = get_supabase_client()
        client.table("participantes").select("id").limit(1).execute()
        return True

    try:
        return await asyncio.wait_for(asyncio.to_thread(_ping), timeout=_DB_CHECK_TIMEOUT_SECONDS)
    except Exception:
        _logger.exception("health: db check failed")
        return False


async def _ultima_migracao() -> int | None:
    """Maior número em `migracoes_aplicadas`, a tabela em que toda migration
    termina gravando o próprio número (issue #969). O rabo espera esse número
    antes do merge. None se a tabela está vazia ou ainda não existe."""

    def _ler() -> int | None:
        client = get_supabase_client()
        linhas = client.table("migracoes_aplicadas").select("numero").order("numero", desc=True).limit(1).execute().data
        return linhas[0]["numero"] if linhas else None

    try:
        return await asyncio.wait_for(asyncio.to_thread(_ler), timeout=_DB_CHECK_TIMEOUT_SECONDS)
    except Exception as exc:
        _logger.warning("health: migracoes_aplicadas indisponivel: %s", exc)
        return None


@router.get("/health")
async def health_check(response: Response):
    db_ok, migracao = await asyncio.gather(_check_db(), _ultima_migracao())
    status_value = "healthy" if db_ok else "degraded"
    if not db_ok:
        response.status_code = 503
    return {
        "status": status_value,
        "db": "healthy" if db_ok else "degraded",
        "app": settings.app_name,
        "version": settings.app_version,
        "migracao": migracao,
    }
