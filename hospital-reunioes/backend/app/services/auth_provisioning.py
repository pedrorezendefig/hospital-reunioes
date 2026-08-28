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

logger = logging.getLogger(__name__)


def provision_auth_user(supabase, nome: str, email: str, role: str, password: str | None = None) -> str | None:
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
        response = supabase.auth.admin.create_user(
            {
                "email": email,
                "password": password,
                "email_confirm": True,
                "user_metadata": {
                    "nome": nome,
                    "role": role,
                },
            }
        )

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


def _find_existing_auth_user(supabase, email: str) -> str | None:
    """Busca UUID de um auth.user existente pelo e-mail.

    Estratégia em duas etapas:
      1. Consulta participantes.auth_user_id (rápido, sem listar todos os users)
      2. Fallback: Admin API get_user_by_email (busca direta no auth.users)
    """
    # 1. Tentar via tabela participantes (lookup direto por email)
    try:
        result = supabase.table("participantes").select("auth_user_id").eq("email", email).limit(1).execute()
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
    role: str | None = None,
    password: str | None = None,
) -> tuple[dict, str | None]:
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

    effective_role = role or participante_data.get("role") or participante.get("role") or "coordenador"
    nome = participante.get("nome_completo") or participante_data.get("nome_completo") or participante.get("nome") or ""
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
        supabase.table("participantes").update({"auth_user_id": auth_uid}).eq("id", pid).execute()
        participante["auth_user_id"] = auth_uid
        # Nascer desligado é raro, mas `ativo` aceita False nas duas portas de
        # criação, e o provisionamento acima sempre cria a conta viva. Sem esta
        # trava o vínculo nasceria inativo com login eterno, que é o buraco da
        # issue #415 pelo avesso: ninguém desliga, então nada bane, e a janela
        # nunca fecha. `ativo` ausente significa ativo (BOOLEAN DEFAULT TRUE),
        # nunca desligado: só o False explícito tranca.
        if participante.get("ativo") is False or participante_data.get("ativo") is False:
            definir_login_liberado(supabase, auth_uid, liberado=False)

    return participante, auth_uid


# 100 anos. O GoTrue não tem "banido para sempre", só duração; um século é o
# jeito de escrever "enquanto alguém não reabrir de propósito".
_BAN_PERPETUO = "876000h"


def _avisar_falha_no_login(auth_user_id: str, liberado: bool, erro: Exception, supabase) -> None:
    """Leva a falha do Auth a um humano, não só ao log do servidor.

    Log não é rastro acionável: ninguém lê. E o estado que sobra da falha é
    justamente o que a issue #415 veio fechar, com a agravante de ser
    invisível. Quem desligou viu "204 No Content" e foi embora; a pessoa
    continua `ativo = false` na tabela, com a conta viva renovando sessão pelo
    refresh token, e a janela curta e aceita virou permanente sem ninguém
    saber. O canal é o mesmo que o alerta de setor sem titular passou a usar.

    Import local porque `avisar_admins_tecnicos` mora no serviço da Ouvidoria,
    e este módulo é do tronco de auth: no topo o import seria circular. Engole
    a própria falha porque quem chama promete nunca levantar.
    """
    acao = "reabrir" if liberado else "banir"
    try:
        from app.services import ouvidoria_notificacoes

        ouvidoria_notificacoes.avisar_admins_tecnicos(
            supabase,
            f"Conta de login ficou fora de sincronia: falhou ao {acao}",
            f"O vínculo do participante já foi gravado na tabela, mas o Supabase Auth recusou {acao} a conta "
            f"{auth_user_id}. Causa: {erro}. Enquanto isso não for refeito, a conta segue no estado antigo: se "
            "era um desligamento, o refresh token continua renovando sessão. Refaça a operação pela mesma tela "
            "para tentar de novo.",
        )
    except Exception:  # noqa: BLE001
        logger.exception("[AuthProvisioning] Falha ao avisar o admin técnico sobre o login %s", auth_user_id)


def definir_login_liberado(supabase, auth_user_id: str | None, *, liberado: bool) -> bool:
    """Abre ou fecha a conta de login que corresponde ao vínculo com o hospital.

    Fechar é banir no Supabase Auth (issue #415): o desligamento era só
    `ativo = false` na tabela, e a conta seguia viva emitindo sessão nova pelo
    refresh token, para sempre. O ban invalida o refresh token; o access token
    que já estava na mão expira sozinho, e essa janela curta é a única que
    sobra. Abrir é o inverso, e existe porque sem ele o ban viraria armadilha:
    a reativação devolveria a pessoa à tabela com o login trancado.

    `sign_out` não serve no lugar do ban: ele exige o JWT da própria pessoa,
    que quem desliga não tem.

    Participante sem `auth_user_id` é o Colaborador que só recebe email, e
    passa direto: não há conta para mexer.

    **Nunca levanta.** Devolve True se o Auth foi mexido de fato. A tabela é a
    fonte de verdade do vínculo e já foi gravada quando chegamos aqui; derrubar
    o desligamento porque o GoTrue piscou deixaria a pessoa ATIVA, que é o pior
    dos dois lados. O gate de papel do PR #414 lê a tabela e continua barrando
    mesmo com a conta viva, então a falha aqui custa a janela, não a porta. Mas
    a janela não é inofensiva (ver `barrar_desligado`), e por isso a falha
    chama `_avisar_falha_no_login` em vez de morrer no log.
    """
    if not auth_user_id:
        return False

    ban = "none" if liberado else _BAN_PERPETUO
    try:
        supabase.auth.admin.update_user_by_id(auth_user_id, {"ban_duration": ban})
    except Exception as e:  # noqa: BLE001
        logger.error(
            "[AuthProvisioning] Falha ao %s o login %s no Supabase Auth: %s",
            "reabrir" if liberado else "banir",
            auth_user_id,
            e,
        )
        _avisar_falha_no_login(auth_user_id, liberado, e, supabase)
        return False
    logger.info(
        "[AuthProvisioning] Login %s %s no Supabase Auth",
        auth_user_id,
        "reaberto" if liberado else "banido",
    )
    return True
