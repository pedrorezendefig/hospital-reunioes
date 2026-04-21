import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import get_current_user, get_participante_for_user, get_supabase_client
from app.models.schemas import UserPreferencesResponse, UserPreferencesUpdate

router = APIRouter(prefix="/configuracoes", tags=["configuracoes"])
logger = logging.getLogger(__name__)

_DEFAULTS = {
    "notificacoes": {
        "mencao": True,
        "prazo_proximo": True,
        "comentario": True,
        "responsavel_atribuido": True,
    },
    "emails": {},
}


@router.get("", response_model=UserPreferencesResponse)
async def get_configuracoes(
    current_user: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    participante = await get_participante_for_user(current_user, supabase, fields="id")
    if not participante:
        raise HTTPException(status_code=404, detail="Participante não encontrado")

    pid = participante["id"]

    result = (
        supabase.table("user_preferences")
        .select("notificacoes, emails")
        .eq("participante_id", pid)
        .execute()
    )

    if result.data:
        row = result.data[0]
        return UserPreferencesResponse(
            notificacoes=row.get("notificacoes") or _DEFAULTS["notificacoes"],
            emails=row.get("emails") or _DEFAULTS["emails"],
        )

    now = datetime.now(timezone.utc).isoformat()
    supabase.table("user_preferences").insert({
        "participante_id": pid,
        "notificacoes": _DEFAULTS["notificacoes"],
        "emails": _DEFAULTS["emails"],
        "created_at": now,
        "updated_at": now,
    }).execute()

    return UserPreferencesResponse()


@router.patch("", response_model=UserPreferencesResponse)
async def update_configuracoes(
    body: UserPreferencesUpdate,
    current_user: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    participante = await get_participante_for_user(current_user, supabase, fields="id")
    if not participante:
        raise HTTPException(status_code=404, detail="Participante não encontrado")

    pid = participante["id"]
    now = datetime.now(timezone.utc).isoformat()

    existing = (
        supabase.table("user_preferences")
        .select("notificacoes, emails")
        .eq("participante_id", pid)
        .execute()
    )

    if existing.data:
        row = existing.data[0]
        notif = row.get("notificacoes") or _DEFAULTS["notificacoes"]
        emails = row.get("emails") or _DEFAULTS["emails"]

        if body.notificacoes is not None:
            notif = body.notificacoes.model_dump()
        if body.emails is not None:
            emails = body.emails.model_dump()

        supabase.table("user_preferences").update({
            "notificacoes": notif,
            "emails": emails,
            "updated_at": now,
        }).eq("participante_id", pid).execute()
    else:
        notif = body.notificacoes.model_dump() if body.notificacoes else _DEFAULTS["notificacoes"]
        emails = body.emails.model_dump() if body.emails else _DEFAULTS["emails"]

        supabase.table("user_preferences").insert({
            "participante_id": pid,
            "notificacoes": notif,
            "emails": emails,
            "created_at": now,
            "updated_at": now,
        }).execute()

    return UserPreferencesResponse(notificacoes=notif, emails=emails)
