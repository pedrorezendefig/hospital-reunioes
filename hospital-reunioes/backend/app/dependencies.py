from __future__ import annotations

from contextvars import ContextVar
from functools import lru_cache
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from supabase import Client, create_client

from app.config import settings
from app.middleware.request_context import set_user_id

bearer_scheme = HTTPBearer(auto_error=False)

# Cache do participante escopado por request (task asyncio). Evita SELECT duplicado
# em participantes quando várias dependências (get_allowed_reuniao_ids +
# get_participante_id_for_user + is_super_admin etc.) rodam no mesmo request.
# Escopo: cada request do FastAPI roda em uma Task própria, e writes em ContextVar
# ficam isoladas por Task, então não há risco de vazar entre requests.
_participante_ctx: ContextVar[dict | None] = ContextVar("participante_ctx", default=None)


@lru_cache
def get_supabase_client() -> Client:
    """Retorna client do Supabase (singleton via cache)."""
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
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
        user_id = str(response.user.id)
        set_user_id(user_id)
        return {
            "id": user_id,
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
    "id, nome_completo, cargo, email, role, setor, area, ativo, is_externo, "
    "is_super_admin, access_profile, perfil_pop, auth_user_id, data_cadastro"
)


async def get_participante_for_user(
    current_user: dict,
    supabase,
    fields: str = _PARTICIPANTE_FULL_FIELDS,
) -> dict | None:
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
    result = supabase.table("participantes").select(fetch_fields).eq("auth_user_id", auth_uid).execute()

    me: dict | None = None
    if result.data:
        me = result.data[0]
    elif email:
        # Fallback: lookup by email
        result = supabase.table("participantes").select(fetch_fields).eq("email", email).execute()
        if result.data:
            me = result.data[0]
            if not me.get("auth_user_id"):
                supabase.table("participantes").update({"auth_user_id": auth_uid}).eq("id", me["id"]).execute()
                me["auth_user_id"] = auth_uid

    if me is not None:
        _participante_ctx.set(me)
    return me


def is_super_admin(participante: dict[str, Any] | None) -> bool:
    """Super admin identificado por access_profile == 'super_admin'.

    Fallback (fase 1 da migração 035): se access_profile não estiver presente
    no dict, lê da flag legada is_super_admin. Isso mantém o comportamento em
    ambientes onde o backfill ainda não rodou. Aceita só dict do participante.
    """
    if participante is None:
        return False
    if not isinstance(participante, dict):
        raise TypeError(
            "is_super_admin espera dict do participante. Passe o objeto carregado do banco, não a string de role."
        )
    ap = participante.get("access_profile")
    if ap is not None:
        return ap == "super_admin"
    return bool(participante.get("is_super_admin"))


def is_secretaria(participante: dict[str, Any] | None) -> bool:
    """Retorna True se o participante tem access_profile = 'secretaria'."""
    if participante is None or not isinstance(participante, dict):
        return False
    return participante.get("access_profile") == "secretaria"


def is_regular(participante: dict[str, Any] | None) -> bool:
    """Retorna True se o participante é usuário regular (nem super_admin nem secretaria)."""
    if participante is None or not isinstance(participante, dict):
        return False
    ap = participante.get("access_profile")
    if ap is not None:
        return ap == "regular"
    # Fallback compat: sem access_profile, regular = não-super_admin.
    return not bool(participante.get("is_super_admin"))


async def get_allowed_reuniao_ids(current_user: dict, supabase) -> list[str] | None:
    """Retorna IDs de reuniões visíveis ao usuário. None = acesso irrestrito.

    Regras por perfil:
    - super_admin: None (sem filtro).
    - secretaria: None (sem filtro). Secretária tem visão de calendário global
      do hospital — vê todas as reuniões em qualquer status. O acesso a ata,
      pendências e comentários é bloqueado por gates 403 explícitos nos
      endpoints correspondentes (defense-in-depth, não depende deste filtro).
    - regular: reuniões em que aparece em reuniao_participantes.
    """
    me = await get_participante_for_user(current_user, supabase)
    if not me:
        return []
    if is_super_admin(me) or is_secretaria(me):
        return None
    my_id = me["id"]
    result = supabase.table("reuniao_participantes").select("id_reuniao").eq("participante_id", my_id).execute()
    return [row["id_reuniao"] for row in (result.data or [])]


def tem_acesso_reunioes(participante: dict[str, Any] | None) -> bool:
    """True se a pessoa tem papel no contexto Reuniões (ADR 0007).

    access_profile é o eixo de permissão das Reuniões; NULL explícito significa
    "sem papel nesse contexto" (ex.: Coordenador de POPs que ganhou login pelo
    provisionamento do POPs). Dict sem a chave (callers antigos) mantém o
    comportamento legado: considera com acesso.
    """
    if participante is None or not isinstance(participante, dict):
        return False
    if "access_profile" in participante:
        return participante["access_profile"] is not None
    return True


async def require_acesso_reunioes(
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
) -> None:
    """Gate de contexto: 403 para quem não tem papel nas Reuniões.

    Aplicado no nível dos routers de Reuniões/Pendências/Comentários/Transcrição.
    `me=None` (token órfão) passa adiante — cada endpoint já trata esse caso
    hoje (404/lista vazia); o gate só decide sobre o eixo de contexto.
    """
    me = await get_participante_for_user(current_user, supabase)
    if me is not None and not tem_acesso_reunioes(me):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito ao contexto Reuniões",
        )


async def require_super_admin(
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
) -> dict:
    """Dependency que 403 se o participante atual nao for super admin.

    Retorna o dict do participante (com campos basicos) para uso no endpoint.
    """
    me = await get_participante_for_user(current_user, supabase)
    if not me or not is_super_admin(me):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acao restrita a super admins",
        )
    return me


async def require_secretaria(
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
) -> dict:
    """Dependency que 403 se o participante atual não for secretária."""
    me = await get_participante_for_user(current_user, supabase)
    if not me or not is_secretaria(me):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acao restrita a secretarias",
        )
    return me


async def get_participante_id_for_user(current_user: dict, supabase) -> str | None:
    """Returns just the participante ID for the current user, or None."""
    me = await get_participante_for_user(current_user, supabase, fields="id")
    return me["id"] if me else None


def require_perfil_pop(*perfis_permitidos: str):
    """Dependency factory do contexto POPs: 403 se perfil_pop não estiver na lista.

    Eixo de permissão próprio do POPs (ADR 0007), ortogonal ao access_profile
    das Reuniões — Facilitador/Secretária/Super admin sem perfil_pop NÃO passam.
    Retorna o dict do participante para uso no endpoint.
    """

    async def checker(
        current_user: dict = Depends(get_current_user),
        supabase: Client = Depends(get_supabase_client),
    ) -> dict:
        me = await get_participante_for_user(current_user, supabase)
        if not me or me.get("perfil_pop") not in perfis_permitidos:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Ação restrita a perfis do contexto POPs",
            )
        return me

    return checker


def require_super_admin_ou_perfil_pop(*perfis_permitidos: str):
    """Aceita Super Admin de Reuniões OU um dos perfis POPs informados.

    Autoridade de administração unificada (ADR 0014): o Super Admin das Reuniões
    pode administrar a concessão de perfil_pop sem que isso lhe conceda ACESSO
    aos dados do contexto POPs — a ortogonalidade de acesso do ADR 0007 se mantém.
    Retorna o dict do participante (actor) para auditoria e checagens no endpoint.
    """

    async def checker(
        current_user: dict = Depends(get_current_user),
        supabase: Client = Depends(get_supabase_client),
    ) -> dict:
        me = await get_participante_for_user(current_user, supabase)
        if me and (is_super_admin(me) or me.get("perfil_pop") in perfis_permitidos):
            return me
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Ação restrita ao Super Admin ou a perfis do contexto POPs",
        )

    return checker


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
            .select("role, is_super_admin, access_profile")
            .eq("auth_user_id", user_id)
            .execute()
        )
        if not result.data:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permissão insuficiente")
        participante = result.data[0]
        if is_super_admin(participante):
            return current_user  # super-admin bypassa role check
        user_role = participante.get("role") or ""
        if user_role not in allowed_roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permissão insuficiente")
        return current_user

    return checker
