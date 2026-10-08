import asyncio
import logging

from fastapi import APIRouter, Response

from app.config import settings
from app.dependencies import get_supabase_client

router = APIRouter(tags=["health"])
_logger = logging.getLogger("app.health")

_DB_CHECK_TIMEOUT_SECONDS = 2.0


def _ler_estado_do_banco() -> tuple[bool, int | None]:
    """Uma leitura só, numa thread só: ping no PostgREST e maior número em
    `migracoes_aplicadas` (issue #969), em sequência pelo mesmo cliente.
    O cliente Supabase é singleton (HTTP/2) e não aguenta duas threads ao
    mesmo tempo: em produção isso derrubava o backend por minutos."""
    client = get_supabase_client()
    client.table("participantes").select("id").limit(1).execute()
    try:
        linhas = client.table("migracoes_aplicadas").select("numero").order("numero", desc=True).limit(1).execute().data
    except Exception as exc:
        _logger.warning("health: migracoes_aplicadas indisponivel: %s", exc)
        return True, None
    return True, (linhas[0]["numero"] if linhas else None)


async def _estado_do_banco() -> tuple[bool, int | None]:
    try:
        return await asyncio.wait_for(asyncio.to_thread(_ler_estado_do_banco), timeout=_DB_CHECK_TIMEOUT_SECONDS)
    except Exception:
        _logger.exception("health: db check failed")
        return False, None


@router.get("/health")
async def health_check(response: Response):
    db_ok, migracao = await _estado_do_banco()
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
