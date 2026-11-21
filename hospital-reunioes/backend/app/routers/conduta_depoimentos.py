"""Canal de Conduta, os depoimentos da Apuração (issue #1830, PRD #1786, ADR
0097, decisão 2).

O cartão de cada pessoa ouvida, os três botões de arquivo (transcrição, áudio
e termo assinado), a lista de conferência e a conclusão. Toda rota passa pelo
portão (`app.services.conduta.portao`). Arquivo nenhum sai por URL do bucket:
a rota confere o acesso, decifra e entrega.
"""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from pydantic import BaseModel, Field
from supabase import Client

from app.dependencies import get_supabase_client
from app.services.conduta import cifra, depoimentos
from app.services.conduta.portao import INDISPONIVEL, CasoAberto, portao_da_acao

router = APIRouter(prefix="/comite-de-conduta", tags=["canal-de-conduta"])


class PessoaAOuvir(BaseModel):
    nome: str = Field(default="", max_length=400)
    cargo: str = Field(default="", max_length=400)
    papel: Literal["acusado", "testemunha", "denunciante"]


def _agir(funcao, *argumentos, **nomeados):
    try:
        return funcao(*argumentos, **nomeados)
    except depoimentos.DepoimentoRecusadoError as recusa:
        raise HTTPException(status_code=recusa.status, detail=recusa.mensagem) from recusa
    except cifra.CifraIndisponivelError as erro:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=INDISPONIVEL) from erro


@router.post("/casos/{caso_id}/depoimentos")
async def adicionar_pessoa_a_ouvir(
    corpo: PessoaAOuvir, aberto: CasoAberto = Depends(portao_da_acao), supabase: Client = Depends(get_supabase_client)
) -> dict:
    depoimento = _agir(depoimentos.adicionar_pessoa, supabase, aberto, **corpo.model_dump())
    return {"depoimento": {"id": depoimento["id"]}}


async def _ler(tipo: str, enviados: list[UploadFile]) -> list[depoimentos.ArquivoRecebido]:
    """Lê cada arquivo depois de conferir o tamanho anunciado: um áudio grande
    demais é recusado antes de ir para a memória. O tamanho lido manda."""
    recebidos = []
    for enviado in enviados:
        _agir(depoimentos.conferir_arquivo, tipo, enviado.filename or "", enviado.size or 1)
        conteudo = await enviado.read()
        _agir(depoimentos.conferir_arquivo, tipo, enviado.filename or "", len(conteudo))
        recebidos.append(depoimentos.ArquivoRecebido(enviado.filename or "", conteudo))
    return recebidos


async def _anexar(supabase, aberto: CasoAberto, depoimento_id: UUID, tipo: str, enviados: list[UploadFile]) -> dict:
    recebidos = await _ler(tipo, enviados)
    return _agir(depoimentos.anexar, supabase, aberto, str(depoimento_id), tipo, recebidos)


@router.post("/casos/{caso_id}/depoimentos/{depoimento_id}/transcricao")
async def anexar_transcricao(
    depoimento_id: UUID,
    arquivo: UploadFile = File(...),
    aberto: CasoAberto = Depends(portao_da_acao),
    supabase: Client = Depends(get_supabase_client),
) -> dict:
    return await _anexar(supabase, aberto, depoimento_id, "transcricao", [arquivo])


@router.post("/casos/{caso_id}/depoimentos/{depoimento_id}/audio")
async def anexar_audio(
    depoimento_id: UUID,
    arquivo: UploadFile = File(...),
    aberto: CasoAberto = Depends(portao_da_acao),
    supabase: Client = Depends(get_supabase_client),
) -> dict:
    return await _anexar(supabase, aberto, depoimento_id, "audio", [arquivo])


@router.post("/casos/{caso_id}/depoimentos/{depoimento_id}/termo-assinado")
async def anexar_termo_assinado(
    depoimento_id: UUID,
    arquivo: list[UploadFile] = File(...),
    aberto: CasoAberto = Depends(portao_da_acao),
    supabase: Client = Depends(get_supabase_client),
) -> dict:
    """Arquivo ou câmera do celular: uma foto por página, até cinco."""
    return await _anexar(supabase, aberto, depoimento_id, "termo_assinado", arquivo)


@router.get("/casos/{caso_id}/depoimentos/{depoimento_id}/arquivos/{arquivo_id}")
async def abrir_arquivo(
    depoimento_id: UUID,
    arquivo_id: UUID,
    aberto: CasoAberto = Depends(portao_da_acao),
    supabase: Client = Depends(get_supabase_client),
) -> Response:
    """O arquivo decifrado, entregue pelo backend. Nada de cache no navegador
    nem no caminho."""
    conteudo, content_type = _agir(depoimentos.abrir_arquivo, supabase, aberto, str(depoimento_id), str(arquivo_id))
    return Response(
        content=conteudo,
        media_type=content_type,
        headers={"Cache-Control": "no-store", "Content-Disposition": "inline"},
    )
