"""Router /admin/usuarios — CRUD administrativo cross-user de participantes.

Todos os endpoints exigem `require_super_admin`. Efeitos destrutivos (create,
edit, delete, reset-password) sao gravados em `audit_log` via
`app.services.audit.log_action`.

Endpoints:
- GET    /admin/usuarios                    lista com filtros e paginacao.
- GET    /admin/usuarios/{id}               detalhe + ultimos 20 audit logs.
- POST   /admin/usuarios                    cria novo participante (ID P001...).
- PATCH  /admin/usuarios/{id}               atualizacao parcial.
- DELETE /admin/usuarios/{id}               hard delete (motivo obrigatorio).
- POST   /admin/usuarios/{id}/reset-password reseta senha no Supabase Auth.
"""

from __future__ import annotations

import logging
import re
import secrets

from fastapi import APIRouter, Depends, HTTPException, Query, status
from starlette.requests import Request
from supabase import Client

from app.dependencies import get_supabase_client, require_super_admin
from app.models.admin_schemas import (
    AdminResetPasswordRequest,
    AdminResetPasswordResponse,
    AdminUsuarioCreate,
    AdminUsuarioDeleteRequest,
    AdminUsuarioDetalhe,
    AdminUsuarioResponse,
    AdminUsuarioUpdate,
    AuditLogRow,
    MergeExternoPayload,
    MergeExternoResult,
    PromoteExternoPayload,
    ReasonRequest,
)
from app.services import audit
from app.utils.postgrest_filters import validate_pid_for_filter
from app.utils.query_params import sanitize_for_ilike

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/usuarios", tags=["admin", "usuarios"])


# ─── Helpers ─────────────────────────────────────────────────────────────────

# Campos que exibimos/retornamos sempre que possivel.
_SELECT_FIELDS = (
    "id, nome_completo, email, cargo, area, setor, role, ativo, is_externo, "
    "is_super_admin, access_profile, auth_user_id, data_cadastro"
)


def _normalize_access_profile_fields(payload: dict, is_create: bool = False) -> None:
    """Aplica as regras de exclusão mútua entre access_profile, role e is_super_admin.

    Em ambos os caminhos (create/update), `access_profile` é a fonte da
    verdade. `is_super_admin` é espelhado (compat fase 1). `role` é zerado
    quando o perfil é secretária (não tem cargo hospitalar).

    Mutação in-place no `payload`. No update, omite campos não enviados.
    """
    ap = payload.get("access_profile")
    if ap is None and is_create:
        ap = "regular"
        payload["access_profile"] = ap
    if ap is None:
        return

    if ap == "super_admin":
        payload["is_super_admin"] = True
    elif ap in ("regular", "secretaria"):
        payload["is_super_admin"] = False

    if ap == "secretaria":
        payload["role"] = None


def _next_participant_id(supabase: Client) -> str:
    """Gera o proximo ID sequencial (P001, P002, ...)."""
    result = supabase.table("participantes").select("id").order("id", desc=True).limit(1).execute()
    if result.data:
        last_id = result.data[0]["id"]
        num = int(re.sub(r"[^0-9]", "", last_id) or "0")
        return f"P{num + 1:03d}"
    return "P001"


def _fetch_usuario(supabase: Client, participante_id: str) -> dict:
    """Busca participante por id — 404 se nao existir."""
    result = supabase.table("participantes").select(_SELECT_FIELDS).eq("id", participante_id).execute()
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Participante nao encontrado",
        )
    return result.data[0]


def _assert_email_disponivel(supabase: Client, email: str, exclude_id: str | None = None) -> None:
    """409 se outro participante ja usa este email."""
    query = supabase.table("participantes").select("id").eq("email", email)
    result = query.execute()
    conflito = [row for row in (result.data or []) if row.get("id") != exclude_id]
    if conflito:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email ja cadastrado em outro participante",
        )


def _generate_password() -> str:
    """Gera uma senha aleatoria forte (>=12 chars url-safe)."""
    return secrets.token_urlsafe(16)


def _resolve_taxonomy_ids(
    supabase: Client,
    setor: str | None,
    cargo: str | None,
) -> dict[str, str | None]:
    """Busca setor_id e cargo_id correspondentes aos nomes informados.

    Lookup case-insensitive nas tabelas `setores`/`cargos` (Fase 1 super-admin
    CRUD, migration 027/028). Se o nome nao bater com nenhum registro, o id
    correspondente fica None — backend grava o TEXT mesmo assim (legacy
    tolerance). O super-admin pode depois cadastrar o valor em /admin/setores
    para re-bater.

    Exceptions capturadas silenciosamente: a tabela pode nao existir em
    ambientes antigos (pre-027). Nesse caso, volta dict vazio.
    """
    result: dict[str, str | None] = {"setor_id": None, "cargo_id": None}
    if setor:
        try:
            res = supabase.table("setores").select("id, nome").ilike("nome", setor.strip()).execute()
            for row in res.data or []:
                if row.get("nome", "").strip().lower() == setor.strip().lower():
                    result["setor_id"] = row["id"]
                    break
        except Exception as e:  # noqa: BLE001
            logger.debug(f"[admin.usuarios] lookup setor ignorado: {e}")
    if cargo:
        try:
            res = supabase.table("cargos").select("id, nome").ilike("nome", cargo.strip()).execute()
            for row in res.data or []:
                if row.get("nome", "").strip().lower() == cargo.strip().lower():
                    result["cargo_id"] = row["id"]
                    break
        except Exception as e:  # noqa: BLE001
            logger.debug(f"[admin.usuarios] lookup cargo ignorado: {e}")
    return result


# ─── Endpoints ───────────────────────────────────────────────────────────────


@router.get("", response_model=list[AdminUsuarioResponse])
async def list_usuarios(
    q: str | None = Query(None, description="Busca por nome ou email"),
    setor: str | None = Query(None),
    ativo: bool | None = Query(None),
    is_super_admin_filter: bool | None = Query(None, alias="is_super_admin", description="Filtra por flag super admin"),
    is_externo_filter: bool | None = Query(None, alias="is_externo", description="Filtra por flag externo"),
    access_profile_filter: str | None = Query(
        None, alias="access_profile", description="Filtra por perfil de acesso (regular/secretaria/super_admin)"
    ),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    _actor: dict = Depends(require_super_admin),
    supabase: Client = Depends(get_supabase_client),
):
    """Lista participantes (incluindo inativos) com filtros e paginacao."""
    query = supabase.table("participantes").select(_SELECT_FIELDS)

    if setor:
        # Aceita multiplos valores separados por virgula (multi-select no frontend).
        setores = [s.strip() for s in setor.split(",") if s.strip()]
        if len(setores) == 1:
            query = query.eq("setor", setores[0])
        elif len(setores) > 1:
            query = query.in_("setor", setores)
    if ativo is not None:
        query = query.eq("ativo", ativo)
    if is_super_admin_filter is not None:
        query = query.eq("is_super_admin", is_super_admin_filter)
    if is_externo_filter is not None:
        query = query.eq("is_externo", is_externo_filter)
    if access_profile_filter is not None:
        valores = [v.strip() for v in access_profile_filter.split(",") if v.strip()]
        if valores:
            query = query.in_("access_profile", valores)
    if q:
        # Busca case-insensitive em nome_completo OU email.
        like = f"%{sanitize_for_ilike(q)}%"
        query = query.or_(f"nome_completo.ilike.{like},email.ilike.{like}")

    result = query.order("nome_completo").range(offset, offset + limit - 1).execute()
    return result.data or []


@router.get("/{participante_id}", response_model=AdminUsuarioDetalhe)
async def get_usuario(
    participante_id: str,
    _actor: dict = Depends(require_super_admin),
    supabase: Client = Depends(get_supabase_client),
):
    """Detalhe + ultimos 20 audit logs em que o participante e actor ou target."""
    usuario = _fetch_usuario(supabase, participante_id)

    logs: list[dict] = []
    try:
        # Busca audit_log onde participante e actor OU target.
        # Defense-in-depth: valida ID antes da interpolacao em filtro PostgREST.
        safe_pid = validate_pid_for_filter(participante_id)
        res = (
            supabase.table("audit_log")
            .select("*")
            .or_(f"actor_id.eq.{safe_pid},and(target_type.eq.participante,target_id.eq.{safe_pid})")
            .order("timestamp", desc=True)
            .limit(20)
            .execute()
        )
        logs = res.data or []
    except Exception as e:  # noqa: BLE001 — fallback sem filtro composto
        logger.warning(f"[admin.usuarios] Falha ao consultar audit_log (filtro composto): {e}")
        try:
            res_actor = (
                supabase.table("audit_log")
                .select("*")
                .eq("actor_id", participante_id)
                .order("timestamp", desc=True)
                .limit(20)
                .execute()
            )
            res_target = (
                supabase.table("audit_log")
                .select("*")
                .eq("target_type", "participante")
                .eq("target_id", participante_id)
                .order("timestamp", desc=True)
                .limit(20)
                .execute()
            )
            combined = (res_actor.data or []) + (res_target.data or [])
            # Dedup por id, manter ordem por timestamp desc.
            seen: set[str] = set()
            logs = []
            for row in sorted(
                combined,
                key=lambda r: r.get("timestamp") or "",
                reverse=True,
            ):
                rid = str(row.get("id"))
                if rid in seen:
                    continue
                seen.add(rid)
                logs.append(row)
                if len(logs) >= 20:
                    break
        except Exception as e2:  # noqa: BLE001
            logger.warning(f"[admin.usuarios] Fallback de audit_log falhou: {e2}")
            logs = []

    return AdminUsuarioDetalhe(
        usuario=AdminUsuarioResponse(**usuario),
        audit_logs=[AuditLogRow(**row) for row in logs],
    )


@router.post(
    "",
    response_model=AdminUsuarioResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_usuario(
    body: AdminUsuarioCreate,
    request: Request,
    actor: dict = Depends(require_super_admin),
    supabase: Client = Depends(get_supabase_client),
):
    """Cria um novo participante. Loga CREATE_USUARIO em audit_log."""
    _assert_email_disponivel(supabase, body.email)

    new_id = _next_participant_id(supabase)
    role_raw = body.role
    role_value: str | None = None
    if role_raw is not None:
        role_value = role_raw.value if hasattr(role_raw, "value") else str(role_raw)
    taxonomy_ids = _resolve_taxonomy_ids(supabase, body.setor, body.cargo)
    payload = {
        "id": new_id,
        "nome_completo": body.nome_completo,
        "email": body.email,
        "cargo": body.cargo,
        "area": body.area,
        "setor": body.setor,
        "role": role_value,
        "access_profile": body.access_profile,
        "is_externo": body.is_externo,
        "ativo": body.ativo,
        # FKs resolvidas silenciosamente (Fase 1 super-admin CRUD).
        "setor_id": taxonomy_ids["setor_id"],
        "cargo_id": taxonomy_ids["cargo_id"],
    }
    _normalize_access_profile_fields(payload, is_create=True)

    # Saga manual: INSERT participante + auth user com rollback se Admin API
    # falhar (evita registro órfão sem auth_user_id). Mantemos a postura
    # "best effort" do auth: se falhar, o helper já fez o rollback do INSERT,
    # então propagamos como 500 (admin sabe que precisa reprovisionar).
    from app.services.auth_provisioning import provision_with_compensation

    # Pro auth_provisioning, manda role como string (fallback "coordenador" se None,
    # típico de secretária — não afeta o banco, só o user_metadata do auth.users).
    role_for_auth = role_value or "coordenador"
    try:
        novo, _auth_uid = provision_with_compensation(
            supabase,
            payload,
            role=role_for_auth,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[admin.usuarios] Falha ao criar/provisionar usuário {body.email}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao criar participante",
        )

    audit.log_action(
        supabase,
        actor=actor,
        action="CREATE_USUARIO",
        target_type="participante",
        target_id=new_id,
        metadata={
            "email": body.email,
            "nome_completo": body.nome_completo,
            "cargo": body.cargo,
            "role": role_value,
            "is_externo": body.is_externo,
        },
        request=request,
    )

    # Completa campos faltantes no response.
    for campo in (
        "cargo",
        "area",
        "setor",
        "role",
        "ativo",
        "is_externo",
        "is_super_admin",
        "access_profile",
        "data_cadastro",
    ):
        novo.setdefault(campo, payload.get(campo))
    novo.setdefault("is_super_admin", False)
    novo.setdefault("access_profile", "regular")
    return novo


@router.patch("/{participante_id}", response_model=AdminUsuarioResponse)
async def update_usuario(
    participante_id: str,
    body: AdminUsuarioUpdate,
    request: Request,
    actor: dict = Depends(require_super_admin),
    supabase: Client = Depends(get_supabase_client),
):
    """Atualizacao parcial. Loga EDIT_USUARIO com antes/depois por campo."""
    atual = _fetch_usuario(supabase, participante_id)

    data = body.model_dump(exclude_unset=True)
    reason = data.pop("reason", None)

    if not data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nenhum campo para atualizar",
        )

    # Lowercase completo: o GoTrue armazena email em lowercase; manter a tabela
    # igual evita divergencia no lookup por email (dependencies.py).
    if data.get("email"):
        data["email"] = data["email"].strip().lower()

    # Normaliza enum role -> string.
    if "role" in data and hasattr(data["role"], "value"):
        data["role"] = data["role"].value

    # Se vier access_profile, aplica exclusão mútua: espelha is_super_admin
    # e zera role pra secretária.
    _normalize_access_profile_fields(data, is_create=False)

    # Valida unicidade de email.
    if "email" in data and data["email"] != atual.get("email"):
        _assert_email_disponivel(supabase, data["email"], exclude_id=participante_id)

    # Monta changes (antes/depois) apenas para campos realmente alterados.
    changes: dict[str, dict] = {}
    for campo, novo_valor in data.items():
        valor_antes = atual.get(campo)
        if valor_antes != novo_valor:
            changes[campo] = {"antes": valor_antes, "depois": novo_valor}

    if not changes:
        # Nada mudou de fato — nao loga, retorna estado atual.
        return atual

    # Sincroniza o email de login no Supabase Auth ANTES da tabela — o login
    # vive em auth.users; sem isso a pessoa continua logando pelo email antigo
    # (issue #29). email_confirm=True aplica na hora, sem email de confirmacao.
    auth_email_sincronizado = False
    if "email" in changes and atual.get("auth_user_id"):
        try:
            supabase.auth.admin.update_user_by_id(
                atual["auth_user_id"],
                {"email": data["email"], "email_confirm": True},
            )
        except Exception as e:  # noqa: BLE001
            if getattr(e, "code", None) == "email_exists" or "already been registered" in str(e):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Email ja registrado no provedor de autenticacao por outra conta",
                )
            logger.error(f"[admin.usuarios] Erro ao sincronizar email de {participante_id} no auth: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erro ao sincronizar email no provedor de autenticacao",
            )
        auth_email_sincronizado = True

    # Se setor ou cargo foram alterados, re-resolve as FKs (setor_id/cargo_id).
    if "setor" in data or "cargo" in data:
        novo_setor = data["setor"] if "setor" in data else atual.get("setor")
        novo_cargo = data["cargo"] if "cargo" in data else atual.get("cargo")
        resolved = _resolve_taxonomy_ids(supabase, novo_setor, novo_cargo)
        if "setor" in data:
            data["setor_id"] = resolved["setor_id"]
        if "cargo" in data:
            data["cargo_id"] = resolved["cargo_id"]

    update = supabase.table("participantes").update(data).eq("id", participante_id).execute()
    if not update.data:
        # Compensacao: o auth ja aponta pro email novo, mas a tabela nao
        # acompanhou — reverte o auth pro email antigo (estado consistente).
        if auth_email_sincronizado:
            try:
                supabase.auth.admin.update_user_by_id(
                    atual["auth_user_id"],
                    {"email": atual["email"], "email_confirm": True},
                )
            except Exception as e:  # noqa: BLE001
                logger.error(
                    f"[admin.usuarios] Compensacao falhou — auth e tabela divergem para {participante_id}: {e}"
                )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao atualizar participante",
        )
    atualizado = update.data[0]

    audit.log_action(
        supabase,
        actor=actor,
        action="EDIT_USUARIO",
        target_type="participante",
        target_id=participante_id,
        metadata={"changes": changes},
        reason=reason,
        request=request,
    )

    return atualizado


@router.delete("/{participante_id}", status_code=status.HTTP_200_OK)
async def delete_usuario(
    participante_id: str,
    body: AdminUsuarioDeleteRequest,
    request: Request,
    actor: dict = Depends(require_super_admin),
    supabase: Client = Depends(get_supabase_client),
) -> dict:
    """Hard delete. Motivo obrigatorio. Bloqueia auto-delete."""
    if actor.get("id") == participante_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Voce nao pode deletar a si mesmo",
        )

    alvo = _fetch_usuario(supabase, participante_id)

    delete = supabase.table("participantes").delete().eq("id", participante_id).execute()
    if not delete.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao deletar participante",
        )

    audit.log_action(
        supabase,
        actor=actor,
        action="DELETE_USUARIO",
        target_type="participante",
        target_id=participante_id,
        metadata={
            "email": alvo.get("email"),
            "nome_completo": alvo.get("nome_completo"),
            "cargo": alvo.get("cargo"),
            "role": alvo.get("role"),
            "is_super_admin": alvo.get("is_super_admin"),
        },
        reason=body.reason,
        request=request,
    )

    return {"success": True, "id": participante_id}


@router.post(
    "/{participante_id}/reset-password",
    response_model=AdminResetPasswordResponse,
)
async def reset_password(
    participante_id: str,
    body: AdminResetPasswordRequest,
    request: Request,
    actor: dict = Depends(require_super_admin),
    supabase: Client = Depends(get_supabase_client),
):
    """Reseta senha no Supabase Auth. Motivo obrigatorio.

    Se `new_password` nao for informado, gera uma senha aleatoria.
    Retorna a senha em claro (o frontend deve exibi-la uma unica vez).
    """
    alvo = _fetch_usuario(supabase, participante_id)
    email = alvo.get("email")
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Participante sem email cadastrado",
        )

    auth_uid = alvo.get("auth_user_id")

    # Se nao ha auth_user_id vinculado, tenta provisionar antes.
    if not auth_uid:
        try:
            from app.services.auth_provisioning import provision_auth_user

            role = alvo.get("role") or "coordenador"
            auth_uid = provision_auth_user(supabase, alvo.get("nome_completo") or "", email, str(role))
            if auth_uid:
                supabase.table("participantes").update({"auth_user_id": auth_uid}).eq("id", participante_id).execute()
        except Exception as e:  # noqa: BLE001
            logger.error(f"[admin.usuarios] Falha ao provisionar auth para {email}: {e}")

    if not auth_uid:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Participante sem conta em auth.users — provisione antes de resetar senha",
        )

    nova_senha = body.new_password or _generate_password()

    try:
        supabase.auth.admin.update_user_by_id(auth_uid, {"password": nova_senha})
    except Exception as e:  # noqa: BLE001
        logger.error(f"[admin.usuarios] Erro ao resetar senha de {email}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao resetar senha no provedor de autenticacao",
        )

    audit.log_action(
        supabase,
        actor=actor,
        action="RESET_PASSWORD",
        target_type="participante",
        target_id=participante_id,
        metadata={
            "email": email,
            "gerada_aleatoria": body.new_password is None,
        },
        reason=body.reason,
        request=request,
    )

    return AdminResetPasswordResponse(
        participante_id=participante_id,
        email=email,
        new_password=nova_senha,
    )


# ─── Resolver externo (merge / promote) — Fase 2 super-admin CRUD ────────────


@router.post(
    "/{externo_id}/merge",
    response_model=MergeExternoResult,
)
async def merge_externo(
    externo_id: str,
    body: MergeExternoPayload,
    request: Request,
    actor: dict = Depends(require_super_admin),
    supabase: Client = Depends(get_supabase_client),
):
    """Mescla participante externo com interno existente via RPC atomica.

    Transfere todas as FKs (reuniao_participantes, reunioes.facilitador_id,
    reunioes.importado_por_id, pendencias.responsavel_id,
    pendencias.co_responsavel_id, comentarios_pendencias.autor_id,
    comentarios_pendencias.mencoes[], notificacoes.destinatario_id),
    atualiza caches *_nome, deleta o externo e grava audit_log
    `merge_participante`.

    Validacoes:
    - externo_id != interno_id.
    - externo precisa ter is_externo=true.
    - interno precisa ter is_externo=false.
    - motivo obrigatorio (gravado em audit_log.reason).
    """
    if externo_id == body.interno_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="externo_id e interno_id nao podem ser iguais",
        )

    # Pre-valida os dois existirem e suas flags (a RPC revalida, mas queremos
    # mensagens de erro HTTP adequadas em vez de 500 com stack trace de DB).
    externo = _fetch_usuario(supabase, externo_id)
    if not externo.get("is_externo"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Participante alvo do merge nao e externo",
        )
    interno = _fetch_usuario(supabase, body.interno_id)
    if interno.get("is_externo"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Participante destino do merge nao pode ser externo",
        )

    try:
        res = supabase.rpc(
            "merge_participante_externo",
            {
                "p_externo_id": externo_id,
                "p_interno_id": body.interno_id,
                "p_motivo": body.reason,
                "p_actor_id": actor.get("id"),
                "p_actor_email": actor.get("email"),
            },
        ).execute()
    except Exception:  # noqa: BLE001
        logger.exception(f"[admin.usuarios] Falha no merge {externo_id}->{body.interno_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao mesclar participante.",
        )

    # A RPC retorna uma linha com os contadores; Supabase Python devolve
    # como lista de dicts via postgrest.
    row = (res.data or [{}])[0] if isinstance(res.data, list) else res.data or {}

    return MergeExternoResult(
        externo_id=externo_id,
        interno_id=body.interno_id,
        reuniao_participantes_moved=row.get("reuniao_participantes_moved", 0),
        reuniao_participantes_dropped=row.get("reuniao_participantes_dropped", 0),
        reunioes_facilitador=row.get("reunioes_facilitador", 0),
        reunioes_importado_por=row.get("reunioes_importado_por", 0),
        pendencias_responsavel=row.get("pendencias_responsavel", 0),
        pendencias_co_responsavel=row.get("pendencias_co_responsavel", 0),
        comentarios_autor=row.get("comentarios_autor", 0),
        comentarios_mencoes=row.get("comentarios_mencoes", 0),
        notificacoes=row.get("notificacoes", 0),
    )


@router.patch(
    "/{externo_id}/promote",
    response_model=AdminUsuarioResponse,
)
async def promote_externo(
    externo_id: str,
    body: PromoteExternoPayload,
    request: Request,
    actor: dict = Depends(require_super_admin),
    supabase: Client = Depends(get_supabase_client),
):
    """Promove participante externo a interno.

    Marca is_externo=false, ativa (ativo=true), preenche dados faltantes
    (email, setor, cargo, role, area). O envio de senha/convite e uma
    acao posterior — usar POST /admin/usuarios/{id}/reset-password.

    Valida que o participante atual e externo. Email precisa ser unico
    entre participantes (exclui o proprio).
    """
    atual = _fetch_usuario(supabase, externo_id)
    if not atual.get("is_externo"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Participante ja e interno",
        )

    data: dict = {"is_externo": False, "ativo": True}

    if body.email is not None:
        _assert_email_disponivel(supabase, body.email, exclude_id=externo_id)
        data["email"] = body.email
    if body.cargo is not None:
        data["cargo"] = body.cargo
    if body.setor is not None:
        data["setor"] = body.setor
    if body.area is not None:
        data["area"] = body.area
    if body.role is not None:
        data["role"] = body.role.value if hasattr(body.role, "value") else str(body.role)
    if body.ativo is not None:
        data["ativo"] = body.ativo

    # Re-resolve FKs de taxonomia caso setor/cargo tenham mudado.
    if "setor" in data or "cargo" in data:
        resolved = _resolve_taxonomy_ids(
            supabase,
            data.get("setor", atual.get("setor")),
            data.get("cargo", atual.get("cargo")),
        )
        if "setor" in data:
            data["setor_id"] = resolved["setor_id"]
        if "cargo" in data:
            data["cargo_id"] = resolved["cargo_id"]

    update = supabase.table("participantes").update(data).eq("id", externo_id).execute()
    if not update.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao promover participante",
        )
    atualizado = update.data[0]

    audit.log_action(
        supabase,
        actor=actor,
        action="promote_participante",
        target_type="participante",
        target_id=externo_id,
        metadata={
            "nome": atual.get("nome_completo"),
            "email_antes": atual.get("email"),
            "changes": {k: v for k, v in data.items() if k not in {"setor_id", "cargo_id"}},
        },
        reason=body.reason,
        request=request,
    )

    return atualizado


# ─── Super admin inline (Fase 2) — grant/revoke direto em /admin/usuarios ───


@router.post(
    "/{participante_id}/grant-super-admin",
    response_model=AdminUsuarioResponse,
)
async def grant_super_admin_inline(
    participante_id: str,
    body: ReasonRequest,
    request: Request,
    actor: dict = Depends(require_super_admin),
    supabase: Client = Depends(get_supabase_client),
):
    """Concede flag is_super_admin=true. Motivo obrigatorio.

    Alternativa inline ao fluxo legado /admin/super-admins/{id}/promote —
    permite promover direto do CRUD de Usuarios. Idempotente: se ja e
    super admin, retorna o registro sem re-gravar log.
    """
    alvo = _fetch_usuario(supabase, participante_id)
    if alvo.get("is_super_admin"):
        return alvo

    update = (
        supabase.table("participantes")
        .update({"is_super_admin": True, "access_profile": "super_admin"})
        .eq("id", participante_id)
        .execute()
    )
    if not update.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao conceder super admin",
        )

    audit.log_action(
        supabase,
        actor=actor,
        action="super_admin_grant_inline",
        target_type="participante",
        target_id=participante_id,
        metadata={
            "email": alvo.get("email"),
            "nome_completo": alvo.get("nome_completo"),
        },
        reason=body.reason,
        request=request,
    )
    return update.data[0]


@router.post(
    "/{participante_id}/revoke-super-admin",
    response_model=AdminUsuarioResponse,
)
async def revoke_super_admin_inline(
    participante_id: str,
    body: ReasonRequest,
    request: Request,
    actor: dict = Depends(require_super_admin),
    supabase: Client = Depends(get_supabase_client),
):
    """Revoga flag is_super_admin=false. Motivo obrigatorio.

    Bloqueia self-revoke (voce nao pode remover seu proprio acesso).
    Idempotente para participantes que ja nao sao super admin.
    """
    if actor.get("id") == participante_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Voce nao pode revogar seu proprio super admin",
        )

    alvo = _fetch_usuario(supabase, participante_id)
    if not alvo.get("is_super_admin"):
        return alvo

    update = (
        supabase.table("participantes")
        .update({"is_super_admin": False, "access_profile": "regular"})
        .eq("id", participante_id)
        .execute()
    )
    if not update.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao revogar super admin",
        )

    audit.log_action(
        supabase,
        actor=actor,
        action="super_admin_revoke_inline",
        target_type="participante",
        target_id=participante_id,
        metadata={
            "email": alvo.get("email"),
            "nome_completo": alvo.get("nome_completo"),
        },
        reason=body.reason,
        request=request,
    )
    return update.data[0]
