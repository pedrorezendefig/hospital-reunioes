"""
Service de provisionamento de autenticação de participantes.

Ao criar um novo participante no banco, este módulo cria automaticamente
uma conta em auth.users no Supabase usando a API de Admin, permitindo
que o colaborador faça login na plataforma.

Fluxo:
  1. Verifica se já existe auth.users com aquele e-mail
  2. Se não existe → cria via supabase.auth.admin.create_user()
  3. Retorna UUID do auth user → caller vincula em participantes.auth_user_id
"""
import logging
import secrets

from typing import Optional

logger = logging.getLogger(__name__)


def provision_auth_user(supabase, nome: str, email: str, role: str, password: Optional[str] = None) -> Optional[str]:
    """
    Cria um usuário em auth.users via Supabase Admin API.

    Args:
        supabase: Cliente Supabase com service_role_key (bypassa RLS).
        nome: Nome completo do participante (sem prefixo).
        email: E-mail do participante (padrão pmrdef+slug@gmail.com).
        role: Role na hierarquia (diretor, presidente, gerente, coordenador).
        password: Senha customizada. Se None, gera aleatória.

    Returns:
        UUID do auth user criado, ou None em caso de erro.
    """
    if password is None:
        password = secrets.token_urlsafe(16)

    try:
        response = supabase.auth.admin.create_user({
            "email": email,
            "password": password,
            "email_confirm": True,
            "user_metadata": {
                "nome": nome,
                "role": role,
            },
        })

        if response and response.user:
            uid = str(response.user.id)
            logger.info(f"[AuthProvisioning] Usuário provisionado: {email} → {uid[:8]}...")
            return uid

        logger.warning(f"[AuthProvisioning] Resposta inesperada ao criar {email}: {response}")
        return None

    except Exception as e:
        err_str = str(e)
        # Usuário já existe no Supabase Auth — buscar UUID existente
        if "already been registered" in err_str or "already exists" in err_str or "duplicate" in err_str.lower():
            logger.info(f"[AuthProvisioning] Usuário {email} já existe em auth.users — buscando UUID")
            return _find_existing_auth_user(supabase, email)

        logger.error(f"[AuthProvisioning] Erro ao provisionar {email}: {e}")
        return None


def _find_existing_auth_user(supabase, email: str) -> Optional[str]:
    """Busca UUID de um auth.user existente pelo e-mail.

    Estratégia em duas etapas:
      1. Consulta participantes.auth_user_id (rápido, sem listar todos os users)
      2. Fallback: Admin API get_user_by_email (busca direta no auth.users)
    """
    # 1. Tentar via tabela participantes (lookup direto por email)
    try:
        result = (
            supabase.table("participantes")
            .select("auth_user_id")
            .eq("email", email)
            .limit(1)
            .execute()
        )
        if result.data and result.data[0].get("auth_user_id"):
            uid = result.data[0]["auth_user_id"]
            logger.info(f"[AuthProvisioning] UUID encontrado via participantes: {email} → {uid[:8]}...")
            return str(uid)
    except Exception as e:
        logger.warning(f"[AuthProvisioning] Fallback: consulta participantes falhou para {email}: {e}")

    # Supabase Admin API não tem search por email; precisamos paginar até encontrar.
    # Custo O(n/50) — aceitável até ~1000 usuários.
    try:
        page = 1
        per_page = 50
        while True:
            response = supabase.auth.admin.list_users(page=page, per_page=per_page)
            users = getattr(response, "users", []) or []
            for user in users:
                if getattr(user, "email", "") == email:
                    logger.info(f"[AuthProvisioning] UUID encontrado via list_users paginado: {email}")
                    return str(user.id)
            if len(users) < per_page:
                break
            page += 1

        logger.warning(f"[AuthProvisioning] Usuário {email} não encontrado em auth.users")
        return None
    except Exception as e:
        logger.error(f"[AuthProvisioning] Erro ao buscar usuário existente {email}: {e}")
        return None


def provision_with_compensation(
    supabase,
    participante_data: dict,
    role: Optional[str] = None,
    password: Optional[str] = None,
) -> tuple[dict, Optional[str]]:
    """Insere participante + provisiona auth user com rollback (saga manual).

    Padrão de compensação: se a chamada à Admin API do Supabase falhar
    após o INSERT do participante, executa DELETE do participante recém-criado
    para evitar registro órfão (sem auth_user_id). Re-raise para o caller decidir.

    Args:
        supabase: cliente Supabase (com service_role).
        participante_data: dict com campos para INSERT em participantes
            (deve conter ao menos `email` e `nome_completo`).
        role: role para provisionamento auth (padrão: usa role do participante_data
            ou "coordenador").
        password: senha customizada para auth user (None gera aleatória).

    Returns:
        Tupla (participante_dict_com_auth_user_id, auth_user_id).
        Se a Admin API NÃO levantou exceção mas retornou None (ex.: e-mail já existe
        em auth.users sem o UUID ser localizável), retorna (participante, None) sem
        rollback — o participante fica registrado, apenas sem auth vinculado.

    Raises:
        RuntimeError: se o INSERT do participante não retornar dados.
        Re-raise da exceção original da Admin API após executar rollback.
    """
    inserted = supabase.table("participantes").insert(participante_data).execute()
    if not inserted.data:
        raise RuntimeError("INSERT participante não retornou dados")
    participante = inserted.data[0]
    pid = participante["id"]

    effective_role = (
        role
        or participante_data.get("role")
        or participante.get("role")
        or "coordenador"
    )
    nome = (
        participante.get("nome_completo")
        or participante_data.get("nome_completo")
        or participante.get("nome")
        or ""
    )
    email = participante.get("email") or participante_data.get("email")

    try:
        auth_uid = provision_auth_user(
            supabase,
            nome,
            email,
            str(effective_role),
            password=password,
        )
    except Exception:
        # Rollback: remove participante recém-inserido para evitar órfão.
        try:
            supabase.table("participantes").delete().eq("id", pid).execute()
        except Exception:
            logger.exception(
                "[AuthProvisioning] Compensação falhou: participante %s pode estar órfão",
                pid,
            )
        logger.exception(
            "[AuthProvisioning] provision_with_compensation: rollback de %s executado",
            pid,
        )
        raise

    if auth_uid:
        supabase.table("participantes").update(
            {"auth_user_id": auth_uid}
        ).eq("id", pid).execute()
        participante["auth_user_id"] = auth_uid

    return participante, auth_uid
