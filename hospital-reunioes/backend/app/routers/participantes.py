"""Cadastro de participantes: o diretório do hospital e a edição dele.

**Por que o gate é por rota, e não no router (issue #440).** Até a #440 este
router não tinha dependency nenhuma, e "ter login" bastava para ler o diretório
inteiro e para gravar em qualquer linha. Fechar tudo com uma dependency de
router seria largo demais: `/me`, `/cargos` e `/setores` são consumidos por
POPs e pela Ouvidoria, contextos cujas pessoas têm `access_profile = NULL`
(ADR 0007) e que ficariam sem tela. Por isso cada rota carrega o gate que lhe
cabe, e as três que ficam abertas dizem no próprio corpo por que ficaram:

- `/me`, `/cargos`, `/setores`: qualquer pessoa logada. `/me` é a própria
  pessoa; as outras duas são listas canônicas do organograma, sem dado pessoal
  de terceiro, e todo contexto do app depende delas.
- `GET ""`, `GET /facilitadores`, `GET /{id}`: `require_participante_reunioes`,
  e não `require_acesso_reunioes`. São nome, email, cargo, setor e role de
  TERCEIROS, dado do contexto Reuniões. A diferença entre os dois gates é o
  token órfão: `require_acesso_reunioes` deixa `me=None` passar de propósito,
  porque as rotas dos routers que o usam já tratam esse caso devolvendo 404 ou
  lista vazia. As daqui **não tratam**: `GET ""` devolveria o diretório
  inteiro, com o email do Super Admin dentro. E o token órfão é alcançável, não
  hipotético, pelo hard delete de `/admin/usuarios` e pela RPC de merge, que
  apagam o vínculo e deixam a conta autenticando no GoTrue. Endurecer
  `require_acesso_reunioes` fecharia isto também, mas ela é dependency de
  router em Reuniões, Pendências, Comentários e Transcrição: mudaria o
  comportamento dos quatro de uma vez, fora do que esta issue pede. Então o
  gate estrito entra por rota, e é o que `dependencies.py` já expõe para quem
  precisa do participante resolvido.
- `POST ""`: `require_role("diretor", "gerente")`, a mesma autoridade do
  `DELETE` logo abaixo. Criar aqui provisiona conta de login, e quem admite é
  quem desliga.
- `PATCH /{id}`: dono ou Super Admin (`autorizar_edicao_participante`). Era a
  porta de tomada de conta: a rota sincroniza o email novo no Supabase Auth
  com `email_confirm=True`, então trocar o email de um Super Admin e pedir
  "esqueci minha senha" entregava a conta dele a qualquer pessoa logada.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ValidationError

from app.dependencies import (
    barrar_desligado,
    get_current_user,
    get_participante_for_user,
    get_participante_id_for_user,
    get_supabase_client,
    is_super_admin,
    require_participante_reunioes,
    require_role,
)
from app.models.schemas import FacilitadorOption, ParticipanteCreate, ParticipanteResponse
from app.services.auth_provisioning import definir_login_liberado
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


async def autorizar_edicao_participante(
    participante_id: str,
    current_user: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
) -> dict:
    """Gate de escrita no cadastro: dono da linha ou Super Admin (issue #440).

    Papel nas Reuniões não basta aqui. Esta rota grava o email, que é a
    identidade de login, e o sincroniza no Auth: qualquer facilitador que
    passasse continuaria capaz de assumir a conta de um Super Admin pelo
    "esqueci minha senha". Editar terceiros é ato de administração e tem a
    porta própria em `/admin/usuarios` (`require_super_admin`).

    `me=None` (token válido sem linha em `participantes`) NÃO passa: sem
    participante não há dono nem papel. Vale para as leituras daqui também,
    e é por isso que elas usam `require_participante_reunioes` em vez de
    `require_acesso_reunioes` (ver o docstring do módulo).
    """
    me = await get_participante_for_user(current_user, supabase)
    barrar_desligado(me)
    if me and (me["id"] == participante_id or is_super_admin(me)):
        return me
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Edição restrita ao próprio cadastro ou ao Super Admin",
    )


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
    _gate: dict = Depends(require_participante_reunioes),
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

    Aberta a qualquer pessoa logada de propósito (issue #440): é lista
    canônica, não tem dado pessoal de terceiro, e POPs e Ouvidoria a consomem
    sem ter papel nas Reuniões.
    """
    return list_cargos()


@router.get("/setores", response_model=list[str])
async def list_setores(
    _: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    """Retorna a lista canonica de setores ativos.

    Aberta a qualquer pessoa logada de propósito (issue #440): nomes de setor
    não são dado pessoal, e as telas de POPs e de Ouvidoria dependem dela sem
    ter papel nas Reuniões. Fechar aqui derruba tela sem fechar buraco.

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
    _: dict = Depends(require_participante_reunioes),
    supabase=Depends(get_supabase_client),
):
    """Lista participantes que já foram facilitadores de alguma reunião viva.

    Usado pelo filtro "Facilitador" no calendário e nas telas de pendências.
    Lista enxuta (DISTINCT) para não poluir o dropdown com gente que nunca
    facilitou. Visível para quem tem papel nas Reuniões (issue #440): o filtro
    é só uma view sobre dados que essa pessoa já enxerga na lista, e por isso
    carrega o mesmo gate da lista.
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
    _: dict = Depends(require_role("diretor", "gerente")),
    supabase=Depends(get_supabase_client),
):
    """Cadastra a pessoa e provisiona a conta de login dela.

    Mesma autoridade do `DELETE` (issue #440): quem admite alguém no hospital
    é quem desliga. Antes bastava ter login, e a rota que cria conta de acesso
    é justamente a que não pode ficar aberta.
    """
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
        fields=(
            "id, nome_completo, email, cargo, area, setor, role, ativo, is_externo, "
            "is_super_admin, perfil_ouvidoria, data_cadastro"
        ),
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
    _: dict = Depends(require_participante_reunioes),
    supabase=Depends(get_supabase_client),
):
    """Cadastro de um participante. Gate de contexto Reuniões (issue #440):
    a resposta é a linha de um terceiro, não a da própria pessoa."""
    result = supabase.table("participantes").select("*").eq("id", participante_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Participante não encontrado")
    return result.data[0]


@router.patch("/{participante_id}", response_model=ParticipanteResponse)
async def update_participante(
    participante_id: str,
    body: ParticipanteUpdate,
    _: dict = Depends(autorizar_edicao_participante),
    supabase=Depends(get_supabase_client),
):
    """Edita o cadastro. Só o dono da linha ou o Super Admin chegam aqui
    (`autorizar_edicao_participante`, issue #440)."""
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
    """Desliga a pessoa do hospital: soft delete na tabela e conta de login
    fechada no mesmo ato (issue #415).

    A ordem é tabela primeiro, Auth depois, ao contrário da troca de email
    logo acima. Lá o Auth vem antes porque o login pelo email antigo é o
    estado errado a evitar; aqui o estado errado a evitar é a pessoa continuar
    ATIVA, então a gravação que não pode falhar é a da tabela. Por isso o Auth
    não compensa nem levanta 500: `definir_login_liberado` registra e segue.
    """
    result = supabase.table("participantes").update({"ativo": False}).eq("id", participante_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Participante não encontrado")

    definir_login_liberado(supabase, result.data[0].get("auth_user_id"), liberado=False)
