"""Router /pops/{pop_id}/documento — o documento oficial do POP em PDF (issue #86).

Preview (inline) e download (attachment) do documento preliminar nas etapas
de Revisão/Validação em diante — o PDF assinado chega na fatia de publicação.
Gerado on-the-fly do rascunho persistido na Versão (nada vai a storage).

Guardas (papel × estado × Setor) vivem em app.services.pops_dominio.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.dependencies import get_supabase_client, require_perfil_pop
from app.models.pops_schemas import PERFIS_POP
from app.services import pops_dominio, pops_pdf_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pops/{pop_id}/documento", tags=["pops"])


@router.get("")
async def documento_pop(
    pop_id: str,
    download: bool = Query(False, description="1 baixa o arquivo (attachment); padrão abre inline (preview)"),
    actor: dict = Depends(require_perfil_pop(*PERFIS_POP)),
    supabase=Depends(get_supabase_client),
):
    """PDF institucional das 11 seções, com o nome travado do DRF §3.3."""
    pop_q = supabase.table("pops").select("*").eq("id", pop_id).limit(1).execute()
    if not pop_q.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="POP não encontrado")
    pop = pop_q.data[0]

    try:
        pops_dominio.exigir_leitura_do_pop(actor, pop, supabase)
    except pops_dominio.AcessoNegadoError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

    versao_q = supabase.table("pops_versoes").select("*").eq("pop_id", pop_id).limit(1).execute()
    if not versao_q.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Versão do POP não encontrada")
    versao = versao_q.data[0]

    try:
        pops_dominio.exigir_documento_disponivel(versao)
    except pops_dominio.TransicaoInvalidaError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    setor_q = supabase.table("pops_setores").select("id, nome, sigla").eq("id", pop["setor_id"]).limit(1).execute()
    setor = setor_q.data[0] if setor_q.data else {}

    ids = list({pop["elaborador_id"], pop["revisor_id"], pop["validador_id"]})
    pessoas = supabase.table("participantes").select("id, nome_completo").in_("id", ids).execute()
    nomes = {row["id"]: row.get("nome_completo") for row in (pessoas.data or [])}

    pdf_bytes = pops_pdf_service.gerar_pdf_pop(pop=pop, setor=setor, versao=versao, nomes_designados=nomes)
    nome_arquivo = pops_pdf_service.nome_arquivo_pop(
        codigo=pop["codigo"], nome=pop["nome"], numero_versao=versao["numero_versao"]
    )
    disposition = "attachment" if download else "inline"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'{disposition}; filename="{nome_arquivo}"'},
    )
