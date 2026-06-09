"""Router da **Nota** (issues #32/#33): registro leve do Facilitador.

Uma Nota é um corpo de texto livre com histórico próprio e soft-delete. O
acesso espelha a Reunião — o autor vê só as suas; Secretária e Super admin
veem todas. A Nota também origina **Pendências** via add manual
(`POST /{id_nota}/pendencias`, ADR 0004); o roster de Participantes e a
extração por IA chegam em fatias seguintes.
"""

import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import (
    get_current_user,
    get_participante_for_user,
    get_supabase_client,
    is_secretaria,
    is_super_admin,
)
from app.models.schemas import (
    ExtrairPendenciasResponse,
    NotaCreate,
    NotaParticipanteResponse,
    NotaParticipantesRequest,
    NotaResponse,
    NotaUpdate,
    PendenciaResponse,
    PendenciasNotaCreateRequest,
)
from app.services.extracao_pendencias_service import ExtracaoIndisponivelError, extrair
from app.services.pendencia_service import criar_pendencias_de_nota

router = APIRouter(prefix="/notas", tags=["notas"])
logger = logging.getLogger(__name__)


def _ve_todas(me: dict) -> bool:
    """Secretária e Super admin têm visão global das Notas (espelha a Reunião)."""
    return is_super_admin(me) or is_secretaria(me)


def _pode_editar(me: dict, nota: dict) -> bool:
    """Edita/arquiva: o autor da Nota ou o Super admin (poder irrestrito)."""
    return is_super_admin(me) or nota["autor_id"] == me["id"]


def _carregar_nota_visivel(supabase, id_nota: str, me: dict) -> dict:
    """Carrega uma Nota viva visível ao usuário, ou 404.

    404 (não 403) para quem não pode vê-la — não revela a existência de uma
    Nota alheia (anti-enumeration, igual ao GET de Reunião).
    """
    result = supabase.table("notas").select("*").eq("id", id_nota).is_("deleted_at", "null").execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Nota não encontrada")
    nota = result.data[0]
    if not (_ve_todas(me) or nota["autor_id"] == me["id"]):
        raise HTTPException(status_code=404, detail="Nota não encontrada")
    return nota


@router.post("", response_model=NotaResponse, status_code=status.HTTP_201_CREATED)
async def criar_nota(
    req: NotaCreate,
    current_user: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    """Cria uma Nota com o corpo informado, de autoria do Facilitador logado."""
    me = await get_participante_for_user(current_user, supabase)
    if not me:
        raise HTTPException(status_code=403, detail="Participante não encontrado")

    nota = {"id": str(uuid.uuid4()), "corpo": req.corpo, "autor_id": me["id"]}
    result = supabase.table("notas").insert(nota).execute()
    logger.info(f"Nota {nota['id']} criada por {me['id']}")
    return result.data[0] if result.data else nota


@router.get("", response_model=list[NotaResponse])
async def listar_notas(
    current_user: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    """Histórico de Notas vivas, mais recentes primeiro.

    Regular vê só as suas; Secretária e Super admin veem todas.
    """
    me = await get_participante_for_user(current_user, supabase)
    if not me:
        return []

    query = supabase.table("notas").select("*").is_("deleted_at", "null")
    if not _ve_todas(me):
        query = query.eq("autor_id", me["id"])
    result = query.order("created_at", desc=True).execute()
    return result.data or []


@router.get("/{id_nota}", response_model=NotaResponse)
async def obter_nota(
    id_nota: str,
    current_user: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    """Abre uma Nota pelo id (se visível ao usuário)."""
    me = await get_participante_for_user(current_user, supabase)
    if not me:
        raise HTTPException(status_code=403, detail="Participante não encontrado")
    return _carregar_nota_visivel(supabase, id_nota, me)


@router.patch("/{id_nota}", response_model=NotaResponse)
async def editar_nota(
    id_nota: str,
    req: NotaUpdate,
    current_user: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    """Edita o corpo de uma Nota — autor ou Super admin."""
    me = await get_participante_for_user(current_user, supabase)
    if not me:
        raise HTTPException(status_code=403, detail="Participante não encontrado")

    nota = _carregar_nota_visivel(supabase, id_nota, me)
    if not _pode_editar(me, nota):
        raise HTTPException(status_code=403, detail="Sem permissão para editar esta Nota")

    # `.is_(deleted_at, null)` no UPDATE fecha a janela entre o SELECT e a escrita:
    # se a Nota for arquivada por um request concorrente, o PATCH não a edita.
    upd = supabase.table("notas").update({"corpo": req.corpo}).eq("id", id_nota).is_("deleted_at", "null").execute()
    logger.info(f"Nota {id_nota} editada por {me['id']}")
    return upd.data[0] if upd.data else {**nota, "corpo": req.corpo}


def _roster_da_nota(supabase, id_nota: str) -> list[dict]:
    """Roster da Nota com o nome de exibição resolvido: Colaborador do cadastro
    usa o nome canônico (`participantes.nome_completo`); avulso usa o que veio."""
    rows = supabase.table("nota_participantes").select("*").eq("id_nota", id_nota).execute().data or []
    ids = [r["participante_id"] for r in rows if r.get("participante_id")]
    nomes: dict[str, str] = {}
    if ids:
        cad = supabase.table("participantes").select("id, nome_completo").in_("id", ids).execute()
        nomes = {c["id"]: c.get("nome_completo") or "" for c in (cad.data or [])}
    return [
        {
            "id": r.get("id"),
            "participante_id": r.get("participante_id"),
            "nome_avulso": r.get("nome_avulso"),
            "nome": nomes.get(r.get("participante_id")) or r.get("nome_avulso") or "",
        }
        for r in rows
    ]


@router.get("/{id_nota}/participantes", response_model=list[NotaParticipanteResponse])
async def listar_participantes_da_nota(
    id_nota: str,
    current_user: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    """Roster da Nota (issue #34): quem entrou na conversa. Visível a quem vê a Nota."""
    me = await get_participante_for_user(current_user, supabase)
    if not me:
        raise HTTPException(status_code=403, detail="Participante não encontrado")
    _carregar_nota_visivel(supabase, id_nota, me)
    return _roster_da_nota(supabase, id_nota)


@router.put("/{id_nota}/participantes", response_model=list[NotaParticipanteResponse])
async def definir_participantes_da_nota(
    id_nota: str,
    req: NotaParticipantesRequest,
    current_user: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    """Define o roster da Nota (replace-all): cada Participante é um Colaborador
    do cadastro OU um nome avulso (externo não cadastrado). Autor ou Super admin."""
    me = await get_participante_for_user(current_user, supabase)
    if not me:
        raise HTTPException(status_code=403, detail="Participante não encontrado")

    nota = _carregar_nota_visivel(supabase, id_nota, me)
    if not _pode_editar(me, nota):
        raise HTTPException(status_code=403, detail="Sem permissão para editar o roster desta Nota")

    # Valida os Colaboradores ANTES do replace — payload inválido não apaga o roster atual.
    ids = [item.participante_id for item in req.participantes if item.participante_id]
    if ids:
        cad = supabase.table("participantes").select("id").in_("id", ids).execute()
        achados = {c["id"] for c in (cad.data or [])}
        desconhecidos = sorted(set(ids) - achados)
        if desconhecidos:
            raise HTTPException(
                status_code=422,
                detail=f"Participante(s) não encontrado(s) no cadastro: {', '.join(desconhecidos)}",
            )

    supabase.table("nota_participantes").delete().eq("id_nota", id_nota).execute()
    rows = [
        {"id_nota": id_nota, "participante_id": item.participante_id, "nome_avulso": item.nome_avulso}
        for item in req.participantes
    ]
    if rows:
        supabase.table("nota_participantes").insert(rows).execute()
    logger.info(f"Roster da Nota {id_nota} definido com {len(rows)} participantes por {me['id']}")
    return _roster_da_nota(supabase, id_nota)


@router.post(
    "/{id_nota}/pendencias",
    response_model=list[PendenciaResponse],
    status_code=status.HTTP_201_CREATED,
)
async def adicionar_pendencias_a_nota(
    id_nota: str,
    req: PendenciasNotaCreateRequest,
    current_user: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    """Adiciona Pendências manuais a uma Nota (issue #33).

    Elas nascem com `id_nota` setado e `id_reuniao` nulo e caem no mesmo
    acompanhamento das demais — painel, alerta de atraso, Repactuação e
    comentários. Autor da Nota ou Super admin.
    """
    me = await get_participante_for_user(current_user, supabase)
    if not me:
        raise HTTPException(status_code=403, detail="Participante não encontrado")
    # Mesmo gate uniforme dos endpoints de pendências: a Secretária não age
    # sobre Pendências — nem pela porta lateral da própria Nota.
    if is_secretaria(me):
        raise HTTPException(status_code=403, detail="Secretária não tem acesso a pendências")

    nota = _carregar_nota_visivel(supabase, id_nota, me)
    if not _pode_editar(me, nota):
        raise HTTPException(status_code=403, detail="Sem permissão para adicionar Pendências a esta Nota")

    confirmadas = [p.model_dump(mode="json") for p in req.pendencias]
    criadas = criar_pendencias_de_nota(supabase, id_nota, confirmadas)
    logger.info(f"{len(criadas)} pendências adicionadas à Nota {id_nota} por {me['id']}")
    return criadas


@router.post("/{id_nota}/extrair-pendencias", response_model=ExtrairPendenciasResponse)
async def extrair_pendencias_da_nota(
    id_nota: str,
    current_user: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    """A mágica central da Nota (issue #34): a IA propõe Pendências a partir
    do corpo, com o responsável casado contra o roster e prazo parseado.

    Devolve propostas **editáveis** — nada é persistido aqui. Só as que o
    Facilitador confirmar viram Pendências, via `POST /{id_nota}/pendencias`
    (a criação da fatia #33). Gates espelham o add manual.
    """
    me = await get_participante_for_user(current_user, supabase)
    if not me:
        raise HTTPException(status_code=403, detail="Participante não encontrado")
    if is_secretaria(me):
        raise HTTPException(status_code=403, detail="Secretária não tem acesso a pendências")

    nota = _carregar_nota_visivel(supabase, id_nota, me)
    if not _pode_editar(me, nota):
        raise HTTPException(status_code=403, detail="Sem permissão para extrair Pendências desta Nota")

    try:
        propostas = extrair(supabase, nota["corpo"], _roster_da_nota(supabase, id_nota))
    except ExtracaoIndisponivelError as e:
        logger.error(f"Extração de pendências indisponível para a Nota {id_nota}: {e}")
        raise HTTPException(status_code=502, detail="IA indisponível no momento. Tente novamente.") from e
    logger.info(f"{len(propostas)} propostas extraídas da Nota {id_nota} por {me['id']}")
    return {"propostas": propostas}


@router.delete("/{id_nota}")
async def arquivar_nota(
    id_nota: str,
    current_user: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    """Arquiva uma Nota — soft-delete via `deleted_at`, sem hard-delete.

    A Nota some do histórico ativo mas a linha permanece no banco (compliance e
    independência das Pendências que ela vier a gerar em fatias seguintes).
    Autor ou Super admin.
    """
    me = await get_participante_for_user(current_user, supabase)
    if not me:
        raise HTTPException(status_code=403, detail="Participante não encontrado")

    nota = _carregar_nota_visivel(supabase, id_nota, me)
    if not _pode_editar(me, nota):
        raise HTTPException(status_code=403, detail="Sem permissão para arquivar esta Nota")

    supabase.table("notas").update({"deleted_at": datetime.now(UTC).isoformat()}).eq("id", id_nota).is_(
        "deleted_at", "null"
    ).execute()
    logger.info(f"Nota {id_nota} arquivada por {me['id']}")
    return {"message": "Nota arquivada com sucesso.", "id": id_nota}
