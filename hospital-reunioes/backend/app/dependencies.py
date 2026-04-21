from __future__ import annotations
import warnings
from contextvars import ContextVar
from functools import lru_cache
from typing import Any, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from supabase import Client, create_client

from app.config import settings

bearer_scheme = HTTPBearer(auto_error=False)

# Cache do participante escopado por request (task asyncio). Evita SELECT duplicado
# em participantes quando várias dependências (get_allowed_reuniao_ids +
# get_participante_id_for_user + is_super_admin etc.) rodam no mesmo request.
# Escopo: cada request do FastAPI roda em uma Task própria, e writes em ContextVar
# ficam isoladas por Task, então não há risco de vazar entre requests.
_participante_ctx: ContextVar[Optional[dict]] = ContextVar(
    "participante_ctx", default=None
)


@lru_cache
def get_supabase_client() -> Client:
    """Retorna client do Supabase (singleton via cache)."""
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    supabase: Client = Depends(get_supabase_client),
) -> dict:
    """Valida o JWT Bearer token do Supabase e retorna o usuário autenticado."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido ou ausente",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        response = supabase.auth.get_user(credentials.credentials)
        if not response or not response.user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token inválido ou expirado",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return {
            "id": str(response.user.id),
            "email": response.user.email,
            "metadata": response.user.user_metadata or {},
        }
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido ou expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )


_PARTICIPANTE_FULL_FIELDS = (
    "id, nome_completo, cargo, email, role, setor, area, "
    "ativo, is_externo, is_super_admin, auth_user_id, data_cadastro"
)


async def get_participante_for_user(
    current_user: dict,
    supabase,
    fields: str = _PARTICIPANTE_FULL_FIELDS,
) -> Optional[dict]:
    """Resolve the participante record for the authenticated user.

    Tries auth_user_id first, falls back to email lookup with lazy sync.

    Usa cache request-scoped (ContextVar): a primeira chamada busca sempre o
    record completo; chamadas seguintes no mesmo request retornam do cache. O
    parâmetro `fields` é mantido por compatibilidade mas é ignorado quando há
    cache — callers leem apenas os campos que usam do dict retornado.
    """
    cached = _participante_ctx.get()
    if cached is not None:
        return cached

    auth_uid = current_user["id"]
    email = current_user.get("email")

    # Sempre busca o record completo para popular o cache. O custo extra por
    # colunas é desprezível vs. economizar um round-trip ao PostgREST.
    fetch_fields = _PARTICIPANTE_FULL_FIELDS

    # Try by auth_user_id first
    result = (
        supabase.table("participantes")
        .select(fetch_fields)
        .eq("auth_user_id", auth_uid)
        .execute()
    )

    me: Optional[dict] = None
    if result.data:
        me = result.data[0]
    elif email:
        # Fallback: lookup by email
        result = (
            supabase.table("participantes")
            .select(fetch_fields)
            .eq("email", email)
            .execute()
        )
        if result.data:
            me = result.data[0]
            if not me.get("auth_user_id"):
                supabase.table("participantes").update(
                    {"auth_user_id": auth_uid}
                ).eq("id", me["id"]).execute()
                me["auth_user_id"] = auth_uid

    if me is not None:
        _participante_ctx.set(me)
    return me


def is_super_admin(participante: Optional[dict[str, Any]]) -> bool:
    """Super admin e identificado pela flag boolean is_super_admin no participante.

    Aceita dict do participante (preferencial). Recusa explicitamente strings:
    chamadas antigas com role string devem ser migradas para is_super_admin(me).
    """
    if participante is None:
        return False
    if not isinstance(participante, dict):
        raise TypeError(
            "is_super_admin espera dict do participante. Use is_super_user(role) (deprecated) "
            "apenas como fallback temporario."
        )
    return bool(participante.get("is_super_admin"))


def is_super_user(role: str) -> bool:
    """[DEPRECATED] Use is_super_admin(participante) — identificacao agora e por flag dedicada.

    Mantido por seguranca de compatibilidade: retorna False sempre, pois o novo
    modelo nao usa role para super user. Chamadores devem migrar para
    is_super_admin(participante_dict).
    """
    warnings.warn(
        "is_super_user(role) esta deprecado. Use is_super_admin(participante) com a flag is_super_admin.",
        DeprecationWarning,
        stacklevel=2,
    )
    return False


async def get_allowed_reuniao_ids(current_user: dict, supabase) -> Optional[list[str]]:
    """Retorna IDs de reunioes visiveis ao usuario. None = acesso irrestrito (super admin)."""
    me = await get_participante_for_user(
        current_user, supabase, fields="id, role, auth_user_id, is_super_admin"
    )
    if not me:
        return []
    if is_super_admin(me):
        return None
    my_id = me["id"]
    result = (
        supabase.table("reuniao_participantes")
        .select("id_reuniao")
        .eq("participante_id", my_id)
        .execute()
    )
    return [row["id_reuniao"] for row in (result.data or [])]


async def require_super_admin(
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
) -> dict:
    """Dependency que 403 se o participante atual nao for super admin.

    Retorna o dict do participante (com campos basicos) para uso no endpoint.
    """
    me = await get_participante_for_user(
        current_user,
        supabase,
        fields="id, nome_completo, role, email, auth_user_id, is_super_admin",
    )
    if not me or not is_super_admin(me):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acao restrita a super admins",
        )
    return me


async def get_participante_id_for_user(current_user: dict, supabase) -> Optional[str]:
    """Returns just the participante ID for the current user, or None."""
    me = await get_participante_for_user(current_user, supabase, fields="id")
    return me["id"] if me else None


def require_role(*allowed_roles: str):
    """Dependency factory que verifica se o usuário tem um dos roles permitidos.

    Super admins (flag is_super_admin = True) bypassam a checagem de role.
    """
    async def checker(
        current_user: dict = Depends(get_current_user),
        supabase: Client = Depends(get_supabase_client),
    ) -> dict:
        user_id = current_user["id"]
        result = (
            supabase.table("participantes")
            .select("role, is_super_admin")
            .eq("auth_user_id", user_id)
            .execute()
        )
        if not result.data:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permissão insuficiente")
        participante = result.data[0]
        if participante.get("is_super_admin") is True:
            return current_user  # super-admin bypassa role check
        user_role = participante.get("role", "")
        if user_role not in allowed_roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permissão insuficiente")
        return current_user
    return checker
