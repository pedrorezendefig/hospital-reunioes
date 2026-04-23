import logging

from fastapi import APIRouter, Depends, HTTPException, status
from starlette.requests import Request

from app.dependencies import get_current_user, get_supabase_client, require_role
from app.limiter import limiter

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)


@router.get("/me")
async def me(current_user: dict = Depends(get_current_user)) -> dict:
    """Retorna dados do usuário autenticado via JWT."""
    return current_user


@router.post("/invite/{participante_id}")
@limiter.limit("5/minute")
async def invite_participant(
    request: Request,
    participante_id: str,
    current_user: dict = Depends(require_role("diretor", "coordenador")),
    supabase=Depends(get_supabase_client),
) -> dict:
    """
    Envia e-mail de redefinição de senha para um participante.
    Permite que o colaborador defina sua própria senha e acesse a plataforma.
    Requer autenticação do administrador.
    """
    # Busca o participante e seu e-mail
    result = (
        supabase.table("participantes")
        .select("id, nome_completo, email, auth_user_id")
        .eq("id", participante_id)
        .eq("ativo", True)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Participante não encontrado")

    participante = result.data[0]
    email = participante.get("email")

    if not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Participante sem e-mail cadastrado")

    # Garante que o auth_user_id existe — provisiona se necessário
    if not participante.get("auth_user_id"):
        logger.info(f"[Invite] Provisionando auth.user para {participante_id} antes de enviar convite")
        from app.services.auth_provisioning import provision_auth_user

        role_result = supabase.table("participantes").select("role, nome_completo").eq("id", participante_id).execute()
        role = role_result.data[0].get("role", "coordenador") if role_result.data else "coordenador"
        nome = role_result.data[0].get("nome_completo", "") if role_result.data else ""
        auth_uid = provision_auth_user(supabase, nome, email, role)
        if auth_uid:
            supabase.table("participantes").update({"auth_user_id": auth_uid}).eq("id", participante_id).execute()

    # Dispara e-mail de reset de senha via Supabase Auth Admin
    try:
        supabase.auth.admin.generate_link(
            {
                "type": "recovery",
                "email": email,
            }
        )
        logger.info(f"[Invite] Link de recuperação enviado para {email} (participante {participante_id})")
        return {
            "success": True,
            "message": f"E-mail de acesso enviado para {email}",
            "participante_id": participante_id,
            "nome": participante.get("nome_completo"),
        }
    except Exception as e:
        logger.error(f"[Invite] Erro ao enviar convite para {email}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao enviar convite. Entre em contato com o administrador.",
        )
