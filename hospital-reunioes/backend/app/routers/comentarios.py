"""
Router de comentários em pendências.

Endpoints para CRUD de comentários com extração automática de menções @usuario.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from app.dependencies import (
    get_allowed_reuniao_ids,
    get_current_user,
    get_participante_for_user,
    get_supabase_client,
    is_secretaria,
    require_acesso_reunioes,
)
from app.models.schemas import ComentarioCreate, ComentarioResponse
from app.services.notificacao_service import (
    criar_notificacao_comentario,
    criar_notificacao_mencao,
)

router = APIRouter(
    prefix="/pendencias",
    tags=["comentarios"],
    # Gate de contexto (ADR 0007): sem papel nas Reuniões -> 403 em todo o router.
    dependencies=[Depends(require_acesso_reunioes)],
)
logger = logging.getLogger(__name__)


def _participantes_mencionaveis(supabase, pendencia: dict) -> list[dict]:
    """Participantes que enxergam a Pendência: roster da reunião + co-responsável + super admins.

    Secretária fica de fora: os gates 403 a bloqueiam de pendências e comentários,
    então a menção geraria notificação morta.
    """
    result = (
        supabase.table("participantes").select("id, nome_completo, setor, is_super_admin, access_profile").execute()
    )
    participantes = result.data or []

    roster = (
        supabase.table("reuniao_participantes")
        .select("participante_id")
        .eq("id_reuniao", pendencia.get("id_reuniao"))
        .execute()
    )
    visiveis = {row["participante_id"] for row in (roster.data or [])}
    if pendencia.get("co_responsavel_id"):
        visiveis.add(pendencia["co_responsavel_id"])

    return [
        p
        for p in participantes
        if (p.get("is_super_admin") or p["id"] in visiveis) and p.get("access_profile") != "secretaria"
    ]


def _extrair_mencoes(conteudo: str, candidatos: list[dict]) -> list[str]:
    """Extrai IDs de participantes mencionados com @nome no conteúdo, sem usar regex falível."""
    if not candidatos:
        return []

    # O filtro previne matches duplicados (ex. João não deve triggar João Pedro).
    # Como não temos regex garantido por pontuação, organizamos pelo tamanho, testando os maiores primeiro.
    participantes_ordenados = sorted(candidatos, key=lambda p: len(p.get("nome_completo", "")), reverse=True)
    mencionados_ids = []

    texto_restante = conteudo

    for p in participantes_ordenados:
        nome_completo = p.get("nome_completo", "").strip()
        if not nome_completo:
            continue

        assinatura = f"@{nome_completo}"
        if assinatura in texto_restante:
            mencionados_ids.append(p["id"])
            # Removemos do buffer de busca para não parear com nomes menores de base.
            texto_restante = texto_restante.replace(assinatura, "")

    return list(set(mencionados_ids))


async def _carregar_pendencia_visivel(
    id_acao: str,
    current_user: dict,
    me: dict | None,
    supabase,
    fields: str = "id_acao, id_reuniao, co_responsavel_id",
) -> dict:
    """Carrega a Pendência e aplica o gate de visibilidade binária (404 se invisível)."""
    pend = supabase.table("pendencias").select(fields).eq("id_acao", id_acao).execute()
    if not pend.data:
        raise HTTPException(status_code=404, detail="Pendência não encontrada")

    pendencia = pend.data[0]
    allowed_ids = await get_allowed_reuniao_ids(current_user, supabase)
    if allowed_ids is not None:
        my_id = me["id"] if me else None
        if pendencia.get("id_reuniao") not in allowed_ids and pendencia.get("co_responsavel_id") != my_id:
            raise HTTPException(status_code=404, detail="Pendência não encontrada")
    return pendencia


@router.get("/{id_acao}/comentarios", response_model=list[ComentarioResponse])
async def list_comentarios(
    id_acao: str,
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    current_user: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    """Lista comentários de uma pendência, ordenados do mais antigo ao mais recente."""
    me = await get_participante_for_user(current_user, supabase)
    if is_secretaria(me):
        raise HTTPException(status_code=403, detail="Secretária não tem acesso a comentários de pendências")

    await _carregar_pendencia_visivel(id_acao, current_user, me, supabase)

    result = (
        supabase.table("comentarios_pendencias")
        .select("*")
        .eq("id_acao", id_acao)
        .order("created_at", desc=False)
        .range(offset, offset + limit - 1)
        .execute()
    )

    return result.data or []


@router.get("/{id_acao}/mencionaveis")
async def listar_mencionaveis(
    id_acao: str,
    current_user: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
) -> list[dict]:
    """Lista participantes mencionáveis no chat da Pendência (quem enxerga a Pendência)."""
    me = await get_participante_for_user(current_user, supabase)
    if is_secretaria(me):
        raise HTTPException(status_code=403, detail="Secretária não tem acesso a comentários de pendências")

    pendencia = await _carregar_pendencia_visivel(id_acao, current_user, me, supabase)

    return [
        {"id": p["id"], "nome_completo": p.get("nome_completo", ""), "setor": p.get("setor")}
        for p in _participantes_mencionaveis(supabase, pendencia)
    ]


@router.post("/{id_acao}/comentarios", response_model=ComentarioResponse, status_code=201)
async def create_comentario(
    id_acao: str,
    req: ComentarioCreate,
    current_user: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    """Cria um comentário na pendência e gera notificações de menção."""
    me_user = await get_participante_for_user(current_user, supabase)
    if is_secretaria(me_user):
        raise HTTPException(status_code=403, detail="Secretária não tem acesso a comentários de pendências")

    # Verifica se a pendência existe e checa visibilidade
    pendencia = await _carregar_pendencia_visivel(
        id_acao,
        current_user,
        me_user,
        supabase,
        fields="id_acao, descricao_acao, responsavel_id, id_reuniao, co_responsavel_id",
    )

    # Resolve o autor
    autor = await get_participante_for_user(current_user, supabase, fields="id, nome_completo, auth_user_id")
    if not autor:
        raise HTTPException(status_code=403, detail="Participante não encontrado para o usuário autenticado")

    # Extrai menções (restritas a quem enxerga a Pendência)
    mencoes = _extrair_mencoes(req.conteudo, _participantes_mencionaveis(supabase, pendencia))

    # Insere comentário
    comentario_data = {
        "id_acao": id_acao,
        "autor_id": autor["id"],
        "autor_nome": autor["nome_completo"],
        "conteudo": req.conteudo,
        "mencoes": mencoes,
    }
    result = supabase.table("comentarios_pendencias").insert(comentario_data).execute()

    if not result.data:
        raise HTTPException(status_code=500, detail="Erro ao criar comentário")

    comentario = result.data[0]
    logger.info(f"[Comentarios] Criado em {id_acao} por {autor['nome_completo']} ({len(mencoes)} menções)")

    # Notificar mencionados (inclusive automenção: quem se menciona quer o lembrete)
    for mencionado_id in mencoes:
        criar_notificacao_mencao(
            supabase,
            id_acao=id_acao,
            autor_nome=autor["nome_completo"],
            mencionado_id=mencionado_id,
            descricao_acao=pendencia.get("descricao_acao", ""),
        )

    # Notificar responsável da pendência (se não for o autor)
    responsavel_id = pendencia.get("responsavel_id")
    if responsavel_id and responsavel_id != autor["id"] and responsavel_id not in mencoes:
        criar_notificacao_comentario(
            supabase,
            id_acao=id_acao,
            autor_nome=autor["nome_completo"],
            responsavel_id=responsavel_id,
            autor_id=autor["id"],
        )

    return comentario


@router.delete("/{id_acao}/comentarios/{comentario_id}", status_code=204)
async def delete_comentario(
    id_acao: str,
    comentario_id: str,
    current_user: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    """Exclui um comentário. Apenas o autor pode excluir."""
    me_user = await get_participante_for_user(current_user, supabase)
    if is_secretaria(me_user):
        raise HTTPException(status_code=403, detail="Secretária não tem acesso a comentários de pendências")

    # Verifica visibilidade da pendência
    await _carregar_pendencia_visivel(id_acao, current_user, me_user, supabase)

    result = (
        supabase.table("comentarios_pendencias")
        .select("id, autor_id")
        .eq("id", comentario_id)
        .eq("id_acao", id_acao)
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=404, detail="Comentário não encontrado")

    autor = await get_participante_for_user(current_user, supabase, fields="id, nome_completo, auth_user_id")
    if not autor or result.data[0]["autor_id"] != autor["id"]:
        raise HTTPException(status_code=403, detail="Apenas o autor pode excluir o comentário")

    supabase.table("comentarios_pendencias").delete().eq("id", comentario_id).execute()
    logger.info(f"[Comentarios] Excluído {comentario_id} de {id_acao}")
