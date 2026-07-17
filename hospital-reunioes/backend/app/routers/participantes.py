import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ValidationError

from app.dependencies import (
    get_current_user,
    get_participante_for_user,
    get_participante_id_for_user,
    get_supabase_client,
    require_role,
)
from app.models.schemas import FacilitadorOption, ParticipanteCreate, ParticipanteResponse
from app.services.cargo_mapping import list_cargos

logger = logging.getLogger(__name__)


class ParticipanteUpdate(BaseModel):
    nome_completo: str | None = None
    email: str | None = None
    cargo: str | None = None
    area: str | None = None
    setor: str | None = None
    telefone: str | None = None


router = APIRouter(prefix="/participantes", tags=["participantes"])


@router.get("", response_model=list[ParticipanteResponse])
async def list_participantes(
    nome: str | None = Query(None),
    cargo: str | None = Query(None),
    setor: str | None = Query(None),
    ativo: bool = Query(True),
    exclude_self: bool = Query(False),
    access_profile: str | None = Query(
        None, description="Filtra por perfil de acesso (regular/secretaria/super_admin). Aceita CSV."
    ),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    current_user: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    query = supabase.table("participantes").select("*").eq("ativo", ativo)
    if exclude_self:
        # Exclui só a própria linha, pela PK (nunca NULL). Filtrar por auth_user_id
        # derrubava todo Colaborador sem login (auth_user_id NULL: `NULL <> x` é NULL
        # e o WHERE descarta), não só o self. Ver CONTEXT.md: Facilitador loga,
        # Colaborador não.
        me_id = await get_participante_id_for_user(current_user, supabase)
        if me_id:
            query = query.neq("id", me_id)
    if nome:
        query = query.ilike("nome_completo", f"%{nome}%")
    if cargo:
        query = query.ilike("cargo", f"%{cargo}%")
    if setor:
        query = query.eq("setor", setor)
    if access_profile:
        valores = [v.strip() for v in access_profile.split(",") if v.strip()]
        if valores:
            query = query.in_("access_profile", valores)
    result = query.order("nome_completo").range(offset, offset + limit - 1).execute()
    # Valida linha a linha: uma linha com dado fora do schema (legado/drift) não
    # pode derrubar a lista inteira com 500 e travar quem marca reunião. A linha
    # malformada é logada (id + erro) para correção do dado e pulada da resposta.
    participantes: list[ParticipanteResponse] = []
    for row in result.data or []:
        try:
            participantes.append(ParticipanteResponse.model_validate(row))
        except ValidationError as exc:
            logger.error("[participantes] linha %s ignorada por dado inválido: %s", row.get("id"), exc)
    return participantes


@router.get("/cargos", response_model=list[str])
async def list_cargos_disponiveis(
    _: dict = Depends(get_current_user),
):
    """
    Retorna a lista canônica de cargos do organograma hospitalar.
    Fonte de verdade: cargo_mapping.py. O frontend pode futuramente
    consumir esta rota em vez de manter onboarding-data.ts duplicado.
    """
    return list_cargos()


@router.get("/setores", response_model=list[str])
async def list_setores(
    _: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    """Retorna a lista canonica de setores ativos.

    Fonte primaria: tabela `setores` (Fase 1 super-admin CRUD, migration 027).
    Fallback: DISTINCT sobre `participantes.setor` (usado enquanto a tabela
    `setores` nao estiver populada ou se houver falha de leitura).
    """
    try:
        result = supabase.table("setores").select("nome").eq("ativo", True).order("nome").execute()
        if result.data:
            return [row["nome"] for row in result.data]
    except Exception:
        pass  # cai para o fallback historico

    legacy = supabase.table("participantes").select("setor").eq("ativo", True).execute()
    if not legacy.data:
        return []
    return sorted({p["setor"] for p in legacy.data if p.get("setor")})


@router.get("/facilitadores", response_model=list[FacilitadorOption])
async def list_facilitadores(
    _: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    """Lista participantes que já foram facilitadores de alguma reunião viva.

    Usado pelo filtro "Facilitador" no calendário e nas telas de pendências.
    Lista enxuta (DISTINCT) para não poluir o dropdown com gente que nunca
    facilitou. Visível para qualquer usuário logado — o filtro é só uma view
    sobre dados que o usuário já enxerga (visibilidade não muda).
    """
    rq = (
        supabase.table("reunioes")
        .select("facilitador_id")
        .is_("deleted_at", "null")
        .not_.is_("facilitador_id", "null")
        .execute()
    )
    facilitator_ids = sorted({row["facilitador_id"] for row in (rq.data or []) if row.get("facilitador_id")})
    if not facilitator_ids:
        return []

    pq = (
        supabase.table("participantes")
        .select("id, nome_completo, setor, is_externo, ativo")
        .in_("id", facilitator_ids)
        .order("nome_completo")
        .execute()
    )
    return pq.data or []


@router.post("", response_model=ParticipanteResponse, status_code=status.HTTP_201_CREATED)
async def create_participante(
    body: ParticipanteCreate,
    _: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    existing = supabase.table("participantes").select("id").eq("email", body.email).execute()
    if existing.data:
        raise HTTPException(status_code=409, detail="Email já cadastrado")

    # Provisionar via saga manual: INSERT participante + auth user com rollback
    # automático se Admin API falhar (evita registro órfão sem auth_user_id).
    from app.services.auth_provisioning import provision_with_compensation

    role = body.role.value if hasattr(body.role, "value") else str(body.role or "coordenador")
    try:
        new_participant, _auth_uid = provision_with_compensation(
            supabase,
            body.model_dump(),
            role=role,
        )
    except Exception:
        logger.exception("Erro ao criar participante")
        raise HTTPException(
            status_code=500,
            detail="Erro ao criar participante.",
        )

    return new_participant


@router.get("/me", response_model=ParticipanteResponse)
async def get_me(
    current_user: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    """Retorna o participante do usuario autenticado.

    Fonte unica de verdade para o frontend descobrir is_super_admin, role,
    setor etc. — evita dependencia de user_metadata (que pode ficar stale).
    """
    me = await get_participante_for_user(
        current_user,
        supabase,
        fields=("id, nome_completo, email, cargo, area, setor, role, ativo, is_externo, is_super_admin, data_cadastro"),
    )
    if not me:
        raise HTTPException(
            status_code=404,
            detail="Participante nao encontrado para o usuario autenticado",
        )
    return me


@router.get("/{participante_id}", response_model=ParticipanteResponse)
async def get_participante(
    participante_id: str,
    _: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    result = supabase.table("participantes").select("*").eq("id", participante_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Participante não encontrado")
    return result.data[0]


@router.patch("/{participante_id}", response_model=ParticipanteResponse)
async def update_participante(
    participante_id: str,
    body: ParticipanteUpdate,
    _: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    update_data = body.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    # Email é identidade de login: não pode ser "removido" via PATCH (NULL na
    # tabela com conta auth viva = divergência). Mesma regra do caminho admin.
    if "email" in update_data and update_data["email"] is None:
        raise HTTPException(status_code=400, detail="Email não pode ser removido, envie um email válido")

    # Troca de email tem a mesma semântica do caminho admin (issue #29): valida
    # unicidade e sincroniza o Supabase Auth ANTES da tabela, senão o login
    # continua pelo email antigo (issue #195).
    auth_email_sincronizado = False
    atual: dict | None = None
    if "email" in update_data:
        # Lowercase completo: o GoTrue armazena email em lowercase; manter a
        # tabela igual evita divergência no lookup por email (dependencies.py).
        update_data["email"] = update_data["email"].strip().lower()

        fetch = supabase.table("participantes").select("*").eq("id", participante_id).execute()
        if not fetch.data:
            raise HTTPException(status_code=404, detail="Participante não encontrado")
        atual = fetch.data[0]

        if update_data["email"] != atual.get("email"):
            existing = supabase.table("participantes").select("id").eq("email", update_data["email"]).execute()
            conflito = [row for row in (existing.data or []) if row.get("id") != participante_id]
            if conflito:
                raise HTTPException(status_code=409, detail="Email já cadastrado em outro participante")

            if atual.get("auth_user_id"):
                try:
                    supabase.auth.admin.update_user_by_id(
                        atual["auth_user_id"],
                        {"email": update_data["email"], "email_confirm": True},
                    )
                except Exception as e:  # noqa: BLE001
                    if getattr(e, "code", None) == "email_exists" or "already been registered" in str(e):
                        raise HTTPException(
                            status_code=409,
                            detail="Email já registrado no provedor de autenticação por outra conta",
                        )
                    logger.error(f"[participantes] Erro ao sincronizar email de {participante_id} no auth: {e}")
                    raise HTTPException(
                        status_code=500,
                        detail="Erro ao sincronizar email no provedor de autenticação",
                    )
                auth_email_sincronizado = True

    result = supabase.table("participantes").update(update_data).eq("id", participante_id).execute()
    if not result.data:
        if auth_email_sincronizado and atual:
            # Compensação: o auth já aponta pro email novo, mas a tabela não
            # acompanhou. Reverte o auth pro email antigo (estado consistente).
            try:
                supabase.auth.admin.update_user_by_id(
                    atual["auth_user_id"],
                    {"email": atual["email"], "email_confirm": True},
                )
            except Exception as e:  # noqa: BLE001
                logger.error(f"[participantes] Compensação falhou, auth e tabela divergem para {participante_id}: {e}")
            raise HTTPException(status_code=500, detail="Erro ao atualizar participante")
        raise HTTPException(status_code=404, detail="Participante não encontrado")
    return result.data[0]


@router.delete("/{participante_id}", status_code=status.HTTP_204_NO_CONTENT)
async def soft_delete_participante(
    participante_id: str,
    _: dict = Depends(require_role("diretor", "gerente")),
    supabase=Depends(get_supabase_client),
):
    result = supabase.table("participantes").update({"ativo": False}).eq("id", participante_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Participante não encontrado")
