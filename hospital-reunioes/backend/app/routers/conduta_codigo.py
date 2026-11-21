"""Canal de Conduta, o Código de Conduta do lado do Comitê (issue #1841,
PRD #1786, decisão 37 do diretor).

Só a coordenação vigente do Comitê publica, lista as versões, baixa qualquer
uma e pergunta qual valia numa data (`portao_da_coordenacao`). A vigente, sem
login, sai pela rota pública `/conduta/codigo-de-conduta`, que nasce fechada
com o resto do canal.

Só GET e POST: nenhuma rota troca ou apaga uma versão.
"""

from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from supabase import Client

from app.dependencies import get_supabase_client
from app.services.conduta import codigo
from app.services.conduta.acesso import hoje_em_sao_paulo
from app.services.conduta.portao import portao_da_coordenacao

router = APIRouter(prefix="/comite-de-conduta/codigo-de-conduta", tags=["canal-de-conduta"])


def resposta_em_pdf(linha: dict, conteudo: bytes) -> Response:
    """O PDF, aberto no navegador, com o número da versão no cabeçalho."""
    return Response(
        content=conteudo,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="codigo-de-conduta-v{linha["versao"]}.pdf"',
            "X-Codigo-De-Conduta-Versao": str(linha["versao"]),
        },
    )


def _recusa(recusa: codigo.RecusaDoCodigo) -> HTTPException:
    return HTTPException(status_code=recusa.status_code, detail=recusa.motivo)


@router.get("")
async def listar_versoes(
    _me: dict = Depends(portao_da_coordenacao),
    supabase: Client = Depends(get_supabase_client),
) -> dict:
    return {"versoes": codigo.versoes(supabase)}


@router.post("", status_code=status.HTTP_201_CREATED)
async def publicar_versao(
    arquivo: UploadFile = File(...),
    vigente_desde: date | None = Form(None),
    me: dict = Depends(portao_da_coordenacao),
    supabase: Client = Depends(get_supabase_client),
) -> dict:
    hoje = hoje_em_sao_paulo()
    conteudo = await arquivo.read(codigo.LIMITE_BYTES + 1)
    try:
        return codigo.publicar(
            supabase,
            nome_arquivo=arquivo.filename or "",
            conteudo=conteudo,
            vigente_desde=vigente_desde or hoje,
            autor_id=me["id"],
            hoje=hoje,
        )
    except codigo.RecusaDoCodigo as recusa:
        raise _recusa(recusa) from recusa


@router.get("/vigente")
async def versao_que_valia(
    data: date = Query(...),
    _me: dict = Depends(portao_da_coordenacao),
    supabase: Client = Depends(get_supabase_client),
) -> dict:
    """A versão que valia na data, ou `null` se nenhuma valia ainda."""
    return {"data": data.isoformat(), "versao": codigo.vigente_em(supabase, data)}


@router.get("/arquivo")
async def baixar_versao(
    versao: int = Query(..., ge=1),
    _me: dict = Depends(portao_da_coordenacao),
    supabase: Client = Depends(get_supabase_client),
) -> Response:
    try:
        achada = codigo.pdf_da_versao(supabase, versao)
    except codigo.RecusaDoCodigo as recusa:
        raise _recusa(recusa) from recusa
    if achada is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Versão inexistente")
    return resposta_em_pdf(*achada)
