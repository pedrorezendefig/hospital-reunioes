"""Canal de Conduta, o lado público (issue #1820, ADR 0097, decisões 10 e 11).

Sem login. O canal nasce fechado: com `CONDUTA_CANAL_ABERTO` desligada, toda
rota daqui responde 404, como se não existisse. A chave fica no Coolify, e
quem abre é o Pedro, depois do aditivo de sigilo assinado, do layout aprovado
e do teste de anonimato.

A trava vale para o router inteiro (`dependencies`), então rota nova aqui
nasce fechada sem depender de quem a escreve. O log das rotas do módulo sai
sem IP (`app.middleware.request_context`).
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from supabase import Client

from app.config import settings
from app.dependencies import get_supabase_client
from app.services import limite_sem_ip
from app.services.conduta import configuracoes


def exigir_canal_aberto() -> None:
    if not settings.conduta_canal_aberto:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")


router = APIRouter(prefix="/conduta", tags=["canal-de-conduta-publico"], dependencies=[Depends(exigir_canal_aberto)])


@router.get("/abertura")
async def abertura() -> dict:
    """Se o canal está aberto. Fechado, a rota nem aparece (404)."""
    return {"aberto": True}


@router.get("/textos")
@limite_sem_ip.limitar("60/minute")
async def textos(request: Request, supabase: Client = Depends(get_supabase_client)) -> dict:
    """Os textos vigentes das telas públicas (issue #1826), cada um com o
    identificador da versão, para a tela dizer qual versão mostrou. Lê o banco
    a cada chamada, então tem limite por aparelho, sem guardar o endereço
    (decisão 10 da ADR 0097)."""
    return {"textos": configuracoes.vigentes_publicas(supabase)}
