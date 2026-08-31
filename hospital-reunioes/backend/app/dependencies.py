from __future__ import annotations

import logging
import secrets
from contextvars import ContextVar
from functools import lru_cache
from typing import Any

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from postgrest.exceptions import APIError
from supabase import Client, create_client

from app.config import settings
from app.middleware.request_context import set_user_id

logger = logging.getLogger(__name__)

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
    "is_super_admin, access_profile, perfil_pop, perfil_ouvidoria, auth_user_id, data_cadastro"
)


# Colunas que podem não existir no banco em que este backend subiu. Toda rota
# autenticada seleciona a tupla inteira, então uma coluna nova derrubaria o app
# INTEIRO (500 em tudo) num ambiente onde a migration ainda não rodou: ambiente
# novo, rollback de banco, ordem invertida de deploy (issue #375, item 14).
#
# O corte é por coluna, e nunca vira `select *`: sem a coluna, o gate que ela
# alimenta simplesmente fecha, que é o comportamento seguro. O aviso no log é o
# que impede um ambiente rodar meses com a Ouvidoria invisível sem ninguém
# saber por quê. Coluna sai desta lista quando a migration dela é passado
# garantido em todo ambiente.
_COLUNAS_OPCIONAIS = ("perfil_ouvidoria",)

_COLUNA_INEXISTENTE = "42703"


def selecionar_participantes(supabase, campos: str, montar=None):
    """Um select em `participantes` tolerante a coluna que o banco ainda não tem.

    `montar` recebe a query já com o `select` e devolve a query pronta (filtros,
    ordem, paginação). Fica como callable porque a segunda tentativa precisa
    montar tudo de novo, com a lista de campos reduzida: guardar a query da
    primeira não serviria.

    Toda rota autenticada que lê o participante passa por aqui, e não só o
    tronco: a área admin tem a sua própria lista de campos e cairia igual
    (issue #375, item 14)."""
    montar = montar or (lambda q: q)
    try:
        return montar(supabase.table("participantes").select(campos)).execute()
    except APIError as exc:
        if getattr(exc, "code", None) != _COLUNA_INEXISTENTE:
            raise
        ausente = next((c for c in _COLUNAS_OPCIONAIS if c in str(exc)), None)
        if ausente is None or ausente not in campos:
            raise
        logger.warning(
            "Coluna %s ausente em participantes: o backend subiu antes da migration dela. "
            "As funcionalidades que dependem dela ficam desligadas até a migration rodar.",
            ausente,
        )
        reduzidos = ", ".join(c for c in (p.strip() for p in campos.split(",")) if c != ausente)
        return montar(supabase.table("participantes").select(reduzidos)).execute()


def _buscar_participante(supabase, campos: str, coluna: str, valor):
    """O select do participante por uma coluna, com o fallback acima."""
    return selecionar_participantes(supabase, campos, lambda q: q.eq(coluna, valor))


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
    result = _buscar_participante(supabase, fetch_fields, "auth_user_id", auth_uid)

    me: dict | None = None
    if result.data:
        me = result.data[0]
    elif email:
        # Fallback: lookup by email
        result = _buscar_participante(supabase, fetch_fields, "email", email)
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


def foi_desligado(participante: dict[str, Any] | None) -> bool:
    """True quando a pessoa foi desligada, isto é, `ativo` gravado como False.

    `participantes.ativo` é BOOLEAN DEFAULT TRUE **sem** NOT NULL (migration
    001): linha antiga pode ter NULL, e dict de caller antigo pode nem trazer a
    chave. Nos dois casos a pessoa continua passando, como antes desta função.
    Tratar indefinido como desligado derrubaria gente legítima no deploy
    seguinte, sem aviso (mesma armadilha da issue #175 com coluna nullable).
    Só o desligamento explícito fecha a porta, e é justamente o que o soft
    delete grava.
    """
    if not isinstance(participante, dict):
        return False
    return participante.get("ativo") is False


def barrar_desligado(participante: dict[str, Any] | None) -> None:
    """Porta comum a todo gate de papel (issue #309).

    Sessão do Supabase Auth continua válida depois do desligamento, então sem
    esta checagem a pessoa desligada seguia passando em qualquer gate e editando
    dado que chega ao paciente. Chamada logo após resolver o participante, antes
    de qualquer consulta ao banco: a recusa tem que ser antes do efeito.

    **O que fica de fora, e o que isso custa (issue #415).** Esta guarda mora
    nos gates de papel. Reuniões, Pendências, Comentários e Transcrição estão
    cobertos porque o gate está no próprio router. `participantes.py` e
    `aceite.py` não têm dependency de router, mas desde a issue #440 têm gate
    por rota, e toda rota deles que lê terceiro ou grava passa por aqui: o
    buraco em que qualquer pessoa logada trocava o email de um Super Admin e
    assumia a conta pelo "esqueci minha senha" está fechado, e as três rotas
    que continuam abertas a quem tem login (`/participantes/me`, `/cargos` e
    `/setores`) dizem no próprio corpo por quê.

    Sobram `/auth/me`, `/perfil`, `/notificacoes` e `/configuracoes`: o
    desligado com access token vivo as alcança até o token expirar. Aceitar
    isso é decisão barata, porque o que elas mostram é a pessoa a si mesma.

    O que o #415 faz por essa janela é encurtá-la: o desligamento bane a conta
    no Supabase Auth (`definir_login_liberado`), então o refresh token para de
    renovar e sobra só a vida do access token que já estava na mão.
    """
    if foi_desligado(participante):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso encerrado: participante desativado",
        )


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
    barrar_desligado(me)
    if me is not None and not tem_acesso_reunioes(me):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito ao contexto Reuniões",
        )


async def require_participante_reunioes(
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
) -> dict:
    """Dependency que 403 se o usuário autenticado não tem papel nas Reuniões.

    Gate de leitura do módulo Dados do Atendimento (ADR 0031): facilitador,
    secretária e super admin leem. Retorna o dict do participante.
    """
    me = await get_participante_for_user(current_user, supabase)
    barrar_desligado(me)
    if not me or not tem_acesso_reunioes(me):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito ao contexto Reuniões",
        )
    return me


async def require_super_admin(
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
) -> dict:
    """Dependency que 403 se o participante atual nao for super admin.

    Retorna o dict do participante (com campos basicos) para uso no endpoint.
    """
    me = await get_participante_for_user(current_user, supabase)
    barrar_desligado(me)
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
    barrar_desligado(me)
    if not me or not is_secretaria(me):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acao restrita a secretarias",
        )
    return me


async def require_super_admin_ou_secretaria(
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
) -> dict:
    """Dependency que 403 se o participante não for super admin nem secretária.

    Gate de escrita do módulo Dados do Atendimento (ADR 0031): super admin e
    secretária editam; facilitador só lê. Retorna o dict do participante.
    """
    me = await get_participante_for_user(current_user, supabase)
    barrar_desligado(me)
    if not me or not (is_super_admin(me) or is_secretaria(me)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acao restrita a super admins e secretarias",
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
        barrar_desligado(me)
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
        barrar_desligado(me)
        if me and (is_super_admin(me) or me.get("perfil_pop") in perfis_permitidos):
            return me
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Ação restrita ao Super Admin ou a perfis do contexto POPs",
        )

    return checker


async def require_ana_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Auth de serviço da API da Ana (ADR 0031): valida X-API-Key contra ANA_API_KEY.

    Única porta máquina-a-máquina do app, fora do fluxo JWT. Chave não
    configurada = API desabilitada (recusa tudo). O detail nunca ecoa a chave.
    """
    chave_configurada = settings.ana_api_key
    # compare_digest sobre bytes: header com caractere não-ASCII vira 401, não 500.
    if (
        not chave_configurada
        or not x_api_key
        or not secrets.compare_digest(x_api_key.encode("utf-8"), chave_configurada.encode("utf-8"))
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key inválida ou ausente",
        )


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
            .select("role, is_super_admin, access_profile, ativo")
            .eq("auth_user_id", user_id)
            .execute()
        )
        if not result.data:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permissão insuficiente")
        participante = result.data[0]
        barrar_desligado(participante)
        if is_super_admin(participante):
            return current_user  # super-admin bypassa role check
        user_role = participante.get("role") or ""
        if user_role not in allowed_roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permissão insuficiente")
        return current_user

    return checker
