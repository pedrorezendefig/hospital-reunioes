"""
Router de cadastro por email e senha.

Fluxo:
  1. POST /signup/register  — valida Passe, armazena signup_request, envia email de confirmação
  2. GET  /signup/verify/{token} — confirma email, cria auth.users + participante

Nota sobre a senha:
  A senha informada no cadastro é cifrada com Fernet (chave simétrica em SIGNUP_ENCRYPTION_KEY)
  antes de ser armazenada em signup_requests. Na confirmação do email, o backend decifra a
  senha e cria o auth.user com a senha real escolhida pelo usuário — permitindo login direto
  sem precisar passar por "Esqueci minha senha".

  O registro em signup_requests é deletado logo após a verificação, minimizando a janela de
  exposição. O acesso à tabela é restrito ao service_role key do Supabase.
"""

import logging
from datetime import UTC, datetime

from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from app.config import settings
from app.dependencies import get_supabase_client
from app.limiter import limiter
from app.services.cargo_mapping import get_cargo_info
from app.services.email_service import enviar_email_confirmacao_cadastro
from app.utils.postgrest_filters import (
    validate_email_for_filter,
    validate_uuid_for_filter,
)

router = APIRouter(prefix="/signup", tags=["signup"])
logger = logging.getLogger(__name__)


def _get_fernet() -> Fernet:
    """Retorna uma instância Fernet configurada. Levanta 503 se a chave não estiver configurada."""
    if not settings.signup_encryption_key:
        logger.error("[Signup] SIGNUP_ENCRYPTION_KEY não configurada — cadastro bloqueado.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cadastro temporariamente indisponível. Entre em contato com o administrador.",
        )
    try:
        return Fernet(settings.signup_encryption_key.encode("utf-8"))
    except Exception as e:
        logger.error(f"[Signup] SIGNUP_ENCRYPTION_KEY inválida: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cadastro temporariamente indisponível. Entre em contato com o administrador.",
        )


# ── Schemas ─────────────────────────────────────────────────────────────────


class SignupRequest(BaseModel):
    nome_completo: str
    email: str
    senha: str
    cargo: str
    passe: str


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.post("/register", status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def register(
    request: Request,
    body: SignupRequest,
    supabase=Depends(get_supabase_client),
) -> dict:
    """
    Registra um novo usuário.

    - Valida o código Passe (9876)
    - Infere cargo/setor/role pelo mapeamento do organograma
    - Armazena solicitação pendente em signup_requests
    - Envia email de confirmação via SMTP
    """
    # 1. Validar Passe
    if not settings.signup_passe:
        logger.error("[Signup] SIGNUP_PASSE não configurado — cadastro bloqueado.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cadastro temporariamente indisponível. Entre em contato com o administrador.",
        )
    if body.passe != settings.signup_passe:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Código Passe incorreto. Solicite o código ao administrador do sistema.",
        )

    # 2. Validar cargo
    cargo_info = get_cargo_info(body.cargo)
    if not cargo_info:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cargo inválido. Selecione um cargo da lista disponível.",
        )

    # 3. Validar senha
    if len(body.senha) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A senha deve ter pelo menos 8 caracteres.",
        )
    if len(body.senha) > 128:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A senha deve ter no maximo 128 caracteres.",
        )

    # 4. Verificar se email já existe em participantes (conta ativa)
    existing = supabase.table("participantes").select("id").eq("email", body.email).execute()
    if existing.data:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Este email já está cadastrado no sistema. Faça login ou use a opção de recuperação de senha.",
        )

    # 5. Limpar solicitação anterior (pendente ou expirada) para o mesmo email
    supabase.table("signup_requests").delete().eq("email", body.email).execute()

    # 6. Inserir signup_request com senha cifrada (Fernet) — reversível com SIGNUP_ENCRYPTION_KEY
    fernet = _get_fernet()
    senha_cifrada = fernet.encrypt(body.senha.encode("utf-8")).decode("utf-8")
    insert_result = (
        supabase.table("signup_requests")
        .insert(
            {
                "nome_completo": body.nome_completo,
                "email": body.email,
                "senha_hash": senha_cifrada,  # Ciphertext Fernet — decifrado no /verify
                "cargo": body.cargo,
                "area": cargo_info.area,
                "setor": cargo_info.setor,
                "role": cargo_info.role,
            }
        )
        .execute()
    )

    if not insert_result.data:
        logger.error(f"[Signup] Falha ao inserir signup_request para {body.email}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao processar seu cadastro. Tente novamente.",
        )

    token = insert_result.data[0]["token"]

    # 7. Enviar email de confirmação
    link = f"{settings.frontend_url}/signup/confirmar?token={token}"
    enviado = enviar_email_confirmacao_cadastro(
        destinatario=body.email,
        nome=body.nome_completo,
        link_confirmacao=link,
    )
    if not enviado:
        logger.warning(f"[Signup] Falha ao enviar email de confirmação para {body.email}")

    logger.info(f"[Signup] Solicitação criada para {body.email} (token={str(token)[:8]}...)")
    return {
        "success": True,
        "message": f"Email de confirmação enviado para {body.email}. Verifique sua caixa de entrada.",
    }


@router.get("/verify/{token}")
@limiter.limit("10/minute")
async def verify_email(
    request: Request,
    token: str,
    supabase=Depends(get_supabase_client),
) -> dict:
    """
    Confirma o email e cria a conta do usuário.

    - Valida token (não expirado, não já confirmado)
    - Cria auth.users via Admin API com a senha escolhida pelo usuário
    - Cria registro em participantes
    - Deleta signup_request (dados temporários)
    """
    # 1. Buscar signup_request pelo token
    result = supabase.table("signup_requests").select("*").eq("token", token).execute()

    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Link de confirmação inválido ou não encontrado.",
        )

    req = result.data[0]

    # 2. Verificar se já foi confirmado
    if req.get("confirmado"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Este link já foi utilizado. Sua conta já está criada — faça login.",
        )

    # 3. Verificar expiração
    expires_at_str = req.get("expires_at", "")
    try:
        expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
        if datetime.now(UTC) > expires_at:
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="Link de confirmação expirado. Solicite um novo cadastro na página de registro.",
            )
    except HTTPException:
        raise
    except Exception:
        logger.warning(f"[Signup Verify] Não foi possível parsear expires_at: {expires_at_str}")

    email = req["email"]
    nome = req["nome_completo"]
    cargo = req["cargo"]
    area = req.get("area")
    setor = req.get("setor")
    role = req.get("role", "coordenador")
    senha_cifrada = req.get("senha_hash", "")

    # 4. Decifrar a senha escolhida pelo usuário no cadastro
    try:
        fernet = _get_fernet()
        senha_real = fernet.decrypt(senha_cifrada.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError) as e:
        logger.error(f"[Signup Verify] Falha ao decifrar senha para {email}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=("Erro ao validar sua senha. Solicite um novo cadastro ou entre em contato com o administrador."),
        )

    # 5. Criar auth.user com a senha real escolhida pelo usuário
    auth_uid = None
    try:
        response = supabase.auth.admin.create_user(
            {
                "email": email,
                "password": senha_real,
                "email_confirm": True,
                "user_metadata": {
                    "nome": nome,
                    "role": role,
                },
            }
        )
        if response and response.user:
            auth_uid = str(response.user.id)
            logger.info(f"[Signup Verify] auth.user criado: {email} → {str(auth_uid)[:8]}...")
    except Exception as e:
        err_str = str(e).lower()
        if "already" in err_str or "duplicate" in err_str or "registered" in err_str:
            # Usuário já existe em auth — buscar UUID
            logger.info(f"[Signup Verify] auth.user já existe para {email}, buscando UUID")
            from app.services.auth_provisioning import _find_existing_auth_user

            auth_uid = _find_existing_auth_user(supabase, email)
        else:
            logger.error(f"[Signup Verify] Erro ao criar auth.user para {email}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erro ao criar sua conta. Entre em contato com o administrador.",
            )

    if not auth_uid:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Não foi possível criar a conta. Tente novamente ou contate o administrador.",
        )

    # 5. Verificar se participante já existe para este auth_user_id
    # Defense-in-depth: valida inputs antes da interpolacao em filtro PostgREST.
    safe_auth_uid = validate_uuid_for_filter(auth_uid)
    safe_email = validate_email_for_filter(email)
    existing_part = (
        supabase.table("participantes")
        .select("id")
        .or_(f"auth_user_id.eq.{safe_auth_uid},email.eq.{safe_email}")
        .execute()
    )

    if not existing_part.data:
        # Criar registro em participantes
        part_result = (
            supabase.table("participantes")
            .insert(
                {
                    "nome_completo": nome,
                    "cargo": cargo,
                    "email": email,
                    "area": area,
                    "setor": setor,
                    "role": role,
                    "ativo": True,
                    "auth_user_id": auth_uid,
                }
            )
            .execute()
        )

        if not part_result.data:
            logger.error(f"[Signup Verify] Falha ao criar participante para {email}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Conta criada mas erro ao registrar perfil. Entre em contato com o administrador.",
            )
        logger.info(f"[Signup Verify] Participante criado: {part_result.data[0]['id']}")
    else:
        # Participante já existe — vincular auth_user_id
        supabase.table("participantes").update({"auth_user_id": auth_uid}).eq("email", email).execute()
        logger.info(f"[Signup Verify] Participante já existia para {email}, auth_user_id vinculado")

    # 6. Deletar signup_request (limpar dados temporários com senha)
    supabase.table("signup_requests").delete().eq("token", token).execute()

    logger.info(f"[Signup Verify] Conta criada com sucesso para {email}")
    return {
        "success": True,
        "message": "Conta criada com sucesso! Faça login com o email e a senha escolhidos no cadastro.",
    }
