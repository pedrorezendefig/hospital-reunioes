"""Router /pops/{pop_id}/documento — o documento oficial do POP em PDF (issue #86).

Preview (inline) e download (attachment) do documento preliminar nas etapas
de Revisão/Validação em diante — o PDF assinado chega na fatia de publicação.
Gerado on-the-fly do rascunho persistido na Versão (nada vai a storage).

Guardas (papel × estado × Setor) vivem em app.services.pops_dominio.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from starlette.requests import Request

from app.dependencies import get_supabase_client, require_perfil_pop
from app.limiter import limiter
from app.models.pops_schemas import PERFIS_POP
from app.services import pops_dominio, pops_pdf_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pops/{pop_id}/documento", tags=["pops"])


@router.get("")
@limiter.limit("30/minute")
async def documento_pop(
    request: Request,
    pop_id: str,
    download: bool = Query(False, description="1 baixa o arquivo (attachment); padrão abre inline (preview)"),
    actor: dict = Depends(require_perfil_pop(*PERFIS_POP)),
    supabase=Depends(get_supabase_client),
):
    """PDF institucional das 11 seções, com o nome travado do DRF §3.3.

    Rate-limit como no chat da elaboração: o render WeasyPrint é CPU-bound
    (~1-2s) — o limite barra loop de preview sem atrapalhar uso real.
    """
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

    # PUBLICADO: o PDF assinado substitui o download (issue #87) — o oficial
    # da Biblioteca é o documento com as assinaturas, nunca regenerado.
    if versao["estado"] == "PUBLICADO":
        pdf_bytes, nome_arquivo = _pdf_assinado(supabase, pop, versao)
    else:
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


def _pdf_assinado(supabase, pop: dict, versao: dict) -> tuple[bytes, str]:
    """Bytes e nome do PDF assinado no storage. O path é determinístico:
    nomenclatura travada com status ASSINADO e a competência da publicação
    (o webhook gravou o arquivo com quando=data_publicacao)."""
    from datetime import datetime

    from app.config import settings
    from app.services import storage

    data_publicacao = versao.get("data_publicacao")
    quando = datetime.fromisoformat(data_publicacao) if data_publicacao else None
    nome_arquivo = pops_pdf_service.nome_arquivo_pop(
        codigo=pop["codigo"],
        nome=pop["nome"],
        numero_versao=versao["numero_versao"],
        status="ASSINADO",
        quando=quando,
    )
    pdf_bytes = storage.download_file(
        supabase,
        settings.supabase_storage_bucket_pdfs_assinados,
        f"pops/{pop['id']}/{nome_arquivo}",
    )
    if not pdf_bytes:
        logger.error(f"[documento_pop] PDF assinado ausente no storage para o POP {pop.get('codigo')}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="PDF assinado indisponível no storage — contate a administração",
        )
    return pdf_bytes, nome_arquivo
