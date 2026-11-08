"""A conversa da Operadora com o Auditor (issue #1490, PRD #1484, ADR 0081).

Duas rotas na Memória da operadora: ler a conversa (as falas e o lote aberto)
e mandar uma mensagem, que vira lote, aplica o lote ("ok") ou refaz um item
("corrige o item N"). As duas atrás de "Regra contratual e tabelas": a
conversa da Operadora é de quem decide a regra do convênio (decisão 5), e o
que essa pessoa aplica nasce vigente.

Router próprio, com o mesmo prefixo do módulo, para a conversa andar sem
disputar o arquivo da Memória por tela.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.dependencies import get_supabase_client, require_permissao_cm
from app.limiter import limiter
from app.services.ai_processor import chamar_ia_fora_do_loop
from app.services.contas_medicas.auditor import LoteRecusadoError, conversa_da_operadora, conversar
from app.services.contas_medicas.ia import ErroDaIA, IASemCredito
from app.services.contas_medicas.memoria_edicao import MudancaRecusadaError, RegraNaoEncontradaError

router = APIRouter(prefix="/contas-medicas", tags=["contas-medicas"])

PERMISSAO = "regra_contratual_tabelas"

MENSAGEM_AUDITOR_FORA = "O Auditor não respondeu agora. Nada foi gravado: tente de novo em alguns minutos."


class MensagemAoAuditor(BaseModel):
    """O que quem decide escreveu ou ditou: um texto, "ok" ou "corrige o item N"."""

    texto: str = Field(..., max_length=4000)


@router.get("/operadoras/{sigla}/conversa")
@limiter.limit("60/minute")
async def ler_conversa(
    request: Request,
    sigla: str,
    _me: dict = Depends(require_permissao_cm(PERMISSAO)),
    supabase=Depends(get_supabase_client),
) -> dict:
    """As falas da conversa da Operadora e o lote aberto."""
    try:
        return conversa_da_operadora(supabase, sigla)
    except RegraNaoEncontradaError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from None


@router.post("/operadoras/{sigla}/conversa")
@limiter.limit("20/minute")
async def mandar_mensagem(
    request: Request,
    sigla: str,
    corpo: MensagemAoAuditor,
    me: dict = Depends(require_permissao_cm(PERMISSAO)),
    supabase=Depends(get_supabase_client),
) -> dict:
    """A mensagem ao Auditor. Devolve a conversa como fica e, no ok, a versão
    nova da memória."""
    try:
        return await chamar_ia_fora_do_loop(conversar, supabase, sigla, corpo.texto, me.get("id"))
    except RegraNaoEncontradaError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from None
    except (LoteRecusadoError, MudancaRecusadaError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from None
    except IASemCredito as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from None
    except ErroDaIA:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=MENSAGEM_AUDITOR_FORA) from None
