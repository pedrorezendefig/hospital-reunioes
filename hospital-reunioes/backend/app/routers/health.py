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


@router.get("/health")
async def health_check(response: Response):
    db_ok = await _check_db()
    status_value = "healthy" if db_ok else "degraded"
    if not db_ok:
        response.status_code = 503
    return {
        "status": status_value,
        "db": "healthy" if db_ok else "degraded",
        "app": settings.app_name,
        "version": settings.app_version,
    }
