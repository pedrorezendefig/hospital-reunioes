"""Canal de Conduta, os depoimentos da Apuração (issue #1830, PRD #1786, ADR
0097, decisão 2).

O cartão de cada pessoa ouvida, os três botões de arquivo (transcrição, áudio
e termo assinado), a lista de conferência e a conclusão. Toda rota passa pelo
portão (`app.services.conduta.portao`). Arquivo nenhum sai por URL do bucket:
a rota confere o acesso, decifra e entrega.
"""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
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
