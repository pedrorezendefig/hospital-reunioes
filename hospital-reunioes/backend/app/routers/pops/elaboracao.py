"""Router /pops/{pop_id}/elaboracao — o POP vivo com chat do agente (issue #83).

A Elaboração (PRD #76): o Elaborador designado conversa com o agente e as
seções do template institucional tomam forma ao vivo. Chat stateless no
padrão da Ata Guiada (ADR 0006), com a diferença deliberada de que o
rascunho PERSISTE na Versão a cada interação — elaboração dura dias e
reabrir a tela recupera o estado; o histórico do chat é efêmero.

Guardas (papel × estado) vivem em app.services.pops_dominio — transições
como ações nomeadas e auditadas; nenhum endpoint manipula status solto.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from starlette.requests import Request

from app.config import settings
from app.dependencies import get_supabase_client, require_perfil_pop
from app.limiter import limiter
from app.models.pops_schemas import (
    PERFIS_POP,
    PeriodicidadeEscolhaRequest,
    PopElaboracaoChatRequest,
    PopElaboracaoResponse,
    PopMateriaisUploadResponse,
    PopMaterialReferenciaResponse,
    PopMaterialUploadErro,
)
from app.routers.pops.versao_view import montar_versao_response, nomes_designados
from app.services import audit, pops_dominio, pops_email_service, storage
from app.services.transcricao_extractor import CONTENT_TYPE_BY_EXT, extrair_texto

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pops/{pop_id}/elaboracao", tags=["pops"])


def _carregar_contexto(pop_id: str, actor: dict, supabase) -> tuple[dict, dict, dict]:
    """POP + Setor + Versão corrente, com as guardas comuns da elaboração:
    404 para POP/Versão inexistente, 403 para quem não é o Elaborador
    designado (a designação formal vence o escopo de Setor)."""
    pop_q = supabase.table("pops").select("*").eq("id", pop_id).limit(1).execute()
    if not pop_q.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="POP não encontrado")
    pop = pop_q.data[0]

    try:
        pops_dominio.exigir_elaborador(actor, pop)
    except pops_dominio.AcessoNegadoError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

    setor_q = supabase.table("pops_setores").select("id, nome, sigla").eq("id", pop["setor_id"]).limit(1).execute()
    setor = setor_q.data[0] if setor_q.data else {}

    # Leva 1: cada POP tem uma única Versão (a 1.0).
    versao_q = supabase.table("pops_versoes").select("*").eq("pop_id", pop_id).limit(1).execute()
    if not versao_q.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Versão do POP não encontrada")
    versao = versao_q.data[0]

    return pop, setor, versao


def _materiais_da_versao(supabase, versao_id: str) -> list[dict]:
    """Materiais de referência da Versão, na ordem de envio — a mesma lista
    alimenta a tela (sem o texto) e o contexto do agente (com o texto)."""
    result = (
        supabase.table("pops_materiais_referencia").select("*").eq("versao_id", versao_id).order("created_at").execute()
    )
    return result.data or []


def _material_response(row: dict) -> PopMaterialReferenciaResponse:
    return PopMaterialReferenciaResponse(
        id=row["id"],
        filename=row["filename"],
        extensao=row["extensao"],
        tamanho_bytes=row["tamanho_bytes"],
        created_at=row.get("created_at"),
    )


@router.get("", response_model=PopElaboracaoResponse)
async def carregar_elaboracao(
    pop_id: str,
    actor: dict = Depends(require_perfil_pop(*PERFIS_POP)),
    supabase=Depends(get_supabase_client),
):
    """Estado completo da tela de elaboração — reabrir recupera o rascunho
    persistido na Versão, em qualquer estado (a edição é que tem gate).
    As Devoluções acompanham: os comentários ficam visíveis na elaboração.
    Os Materiais de referência idem — a lista carrega com a tela (#84)."""
    pop, setor, versao = _carregar_contexto(pop_id, actor, supabase)
    devolucoes = pops_dominio.listar_devolucoes(supabase, versao)
    materiais = [_material_response(m) for m in _materiais_da_versao(supabase, versao["id"])]
    return montar_versao_response(pop, setor, versao, nomes_designados(supabase, pop), devolucoes, materiais)


@router.post("/chat")
@limiter.limit("10/minute")
async def chat_elaboracao(
    request: Request,
    pop_id: str,
    req: PopElaboracaoChatRequest,
    actor: dict = Depends(require_perfil_pop(*PERFIS_POP)),
    supabase=Depends(get_supabase_client),
):
    """Chat do agente de elaboração — stateless, síncrono, sem pipeline.

    Recebe o rascunho + as mensagens (+ a seção apontada ⌖) e devolve
    `{ reply, rascunho, periodicidade_sugerida }`. O rascunho devolvido
    persiste na Versão; a primeira interação real move A_ELABORAR →
    EM_ELABORACAO (auditado). Erro de IA não persiste nem transiciona.
    """
    pop, setor, versao = _carregar_contexto(pop_id, actor, supabase)
    try:
        pops_dominio.exigir_estado_de_elaboracao(versao)
    except pops_dominio.TransicaoInvalidaError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    from app.services.ai_processor import chat_elaboracao_pop

    # Comentários de Devolução entram no contexto do agente (issue #85) — com
    # o autor resolvido (sempre o Revisor ou o Validador designados).
    nomes = nomes_designados(supabase, pop)
    devolucoes = [
        {**d, "autor_nome": nomes.get(d.get("autor_id"))} for d in pops_dominio.listar_devolucoes(supabase, versao)
    ]

    # Materiais de referência persistem na Versão: o contexto do agente vem
    # do banco em toda interação — não depende do cliente reenviar (#84).
    materiais = _materiais_da_versao(supabase, versao["id"])

    out = chat_elaboracao_pop(
        rascunho=req.rascunho,
        messages=[{"role": m.role, "content": m.content} for m in req.messages],
        section_context=req.section_context,
        pop_contexto={
            "codigo": pop["codigo"],
            "nome": pop["nome"],
            "setor_nome": setor.get("nome"),
            "criticidade": pop["criticidade"],
            "base_normativa": pop.get("base_normativa"),
            "numero_versao": versao["numero_versao"],
        },
        devolucoes=devolucoes,
        materiais=[{"filename": m["filename"], "texto": m["texto"]} for m in materiais],
    )

    if not out.pop("_erro", False):
        # Diferença deliberada da Ata Guiada (PRD #76): o rascunho persiste na
        # Versão a cada interação. A sugestão de periodicidade só atualiza
        # quando o agente trouxer uma nova — null não apaga a anterior.
        updates: dict = {"rascunho": out["rascunho"]}
        if out.get("periodicidade_sugerida"):
            updates["periodicidade_sugerida"] = out["periodicidade_sugerida"]
        supabase.table("pops_versoes").update(updates).eq("id", versao["id"]).execute()
        versao = pops_dominio.iniciar_elaboracao_se_preciso(supabase, versao, actor=actor, request=request)

    if out.get("periodicidade_sugerida") is None:
        # Devolve a sugestão efetiva (a já gravada) para a UI manter o card.
        out["periodicidade_sugerida"] = versao.get("periodicidade_sugerida")
    return out


@router.post("/materiais", response_model=PopMateriaisUploadResponse)
async def enviar_materiais(
    pop_id: str,
    files: list[UploadFile] = File(...),
    actor: dict = Depends(require_perfil_pop(*PERFIS_POP)),
    supabase=Depends(get_supabase_client),
):
    """Upload múltiplo de Materiais de referência (.pdf/.docx/.txt/.md) — o
    agente os usa ATIVAMENTE (conduta oposta ao Documento de apoio da Guiada).

    Por-arquivo: extração reusa o extractor existente; o texto extraído
    persiste vinculado à Versão (insumo do agente) e o arquivo original vai
    ao storage best-effort (storage_path nulo se indisponível). Arquivo
    recusado (formato/tamanho) volta em `erros` com a mensagem do extractor —
    sem derrubar os válidos nem a tela.
    """
    _pop, _setor, versao = _carregar_contexto(pop_id, actor, supabase)
    try:
        pops_dominio.exigir_estado_de_elaboracao(versao)
    except pops_dominio.TransicaoInvalidaError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    materiais: list[PopMaterialReferenciaResponse] = []
    erros: list[PopMaterialUploadErro] = []
    for file in files:
        filename = file.filename or ""
        file_bytes = await file.read()
        try:
            texto, extensao = extrair_texto(filename, file_bytes)
        except ValueError as e:
            erros.append(PopMaterialUploadErro(filename=filename, detail=str(e)))
            continue

        path = f"versao-{versao['id']}/{uuid.uuid4().hex}{extensao}"
        url = storage.upload_file(
            supabase,
            bucket=settings.supabase_storage_bucket_materiais_pops,
            path=path,
            content=file_bytes,
            content_type=CONTENT_TYPE_BY_EXT.get(extensao, "application/octet-stream"),
        )
        if url is None:
            logger.warning(f"Storage indisponível para {filename} — material segue só com o texto extraído")

        inserted = (
            supabase.table("pops_materiais_referencia")
            .insert(
                {
                    "versao_id": versao["id"],
                    "filename": filename,
                    "extensao": extensao,
                    "tamanho_bytes": len(file_bytes),
                    "storage_path": path if url is not None else None,
                    "texto": texto,
                    "criado_por": actor["id"],
                }
            )
            .execute()
        )
        materiais.append(_material_response(inserted.data[0]))

    return PopMateriaisUploadResponse(materiais=materiais, erros=erros)


@router.delete("/materiais/{material_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remover_material(
    pop_id: str,
    material_id: str,
    actor: dict = Depends(require_perfil_pop(*PERFIS_POP)),
    supabase=Depends(get_supabase_client),
):
    """Remove um Material de referência — sai do contexto das interações
    seguintes do agente. Material de outra Versão é inalcançável (404)."""
    _pop, _setor, versao = _carregar_contexto(pop_id, actor, supabase)
    try:
        pops_dominio.exigir_estado_de_elaboracao(versao)
    except pops_dominio.TransicaoInvalidaError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    material_q = (
        supabase.table("pops_materiais_referencia")
        .select("*")
        .eq("id", material_id)
        .eq("versao_id", versao["id"])
        .limit(1)
        .execute()
    )
    if not material_q.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Material não encontrado")
    material = material_q.data[0]

    if material.get("storage_path"):
        storage.delete_file(
            supabase, bucket=settings.supabase_storage_bucket_materiais_pops, path=material["storage_path"]
        )
    supabase.table("pops_materiais_referencia").delete().eq("id", material_id).execute()


@router.patch("/periodicidade")
async def escolher_periodicidade(
    pop_id: str,
    req: PeriodicidadeEscolhaRequest,
    request: Request,
    actor: dict = Depends(require_perfil_pop(*PERFIS_POP)),
    supabase=Depends(get_supabase_client),
):
    """Escolha final do Elaborador para a Periodicidade de revisão — o agente
    sugere, ele decide (DRF §4.2). Grava no POP (campo institucional)."""
    pop, _setor, versao = _carregar_contexto(pop_id, actor, supabase)
    try:
        pops_dominio.exigir_estado_de_elaboracao(versao)
    except pops_dominio.TransicaoInvalidaError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    supabase.table("pops").update({"periodicidade_revisao": req.periodicidade_revisao}).eq("id", pop["id"]).execute()
    audit.log_action(
        supabase,
        actor=actor,
        action="POPS_ESCOLHER_PERIODICIDADE",
        target_type="pop",
        target_id=pop["id"],
        metadata={
            "de": pop.get("periodicidade_revisao"),
            "para": req.periodicidade_revisao,
            "sugerida_pelo_agente": versao.get("periodicidade_sugerida"),
        },
        request=request,
    )
    return {"periodicidade_revisao": req.periodicidade_revisao}


@router.post("/aprovar")
async def aprovar_versao_final(
    pop_id: str,
    request: Request,
    actor: dict = Depends(require_perfil_pop(*PERFIS_POP)),
    supabase=Depends(get_supabase_client),
):
    """ "Aprovar versão final": EM_ELABORACAO → EM_REVISAO (auditado) + email
    ao Revisor designado com link e prazo. Reenvio após Devolução do
    Validador vai direto a EM_VALIDACAO (retorno a quem devolveu, issue #85)
    — aí o email é ao Validador. Usa o rascunho persistido na Versão — a
    última interação do chat já é a fonte da verdade."""
    pop, setor, versao = _carregar_contexto(pop_id, actor, supabase)
    try:
        versao = pops_dominio.aprovar_versao_final(supabase, versao, actor=actor, request=request)
    except pops_dominio.TransicaoInvalidaError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    if versao["estado"] == "EM_VALIDACAO":
        pops_email_service.send_validacao_pendente_notification(
            supabase, pop, setor, remetente_nome=actor.get("nome_completo")
        )
    else:
        pops_email_service.send_elaboracao_concluida_notification(
            supabase, pop, setor, elaborador_nome=actor.get("nome_completo")
        )
    return {"estado": versao["estado"]}
