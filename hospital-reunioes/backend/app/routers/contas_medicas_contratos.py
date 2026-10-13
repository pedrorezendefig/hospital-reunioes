"""Contratos de Contas médicas (issue #1144, PRD #1129, ADR 0070).

As rotas da tela `/contas-medicas/contratos`: a lista das operadoras com o
contrato, os dias que faltam e a situação; o envio do contrato ou do aditivo,
que volta com os campos propostos pela IA; a confirmação, que é o que faz os
campos valerem; e o arquivo confirmado, para baixar.

Ver e receber o aviso é da permissão "contratos e avisos". Mudar o contrato
pede também "regra contratual e tabelas": o credenciamento vê a tela e recebe
o aviso, mas quem muda o contrato é a gestão e a diretoria (403 no POST).
"""

from __future__ import annotations

import os
from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile, status
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.dependencies import get_supabase_client, require_permissao_cm
from app.limiter import limiter
from app.services.ai_processor import chamar_ia_fora_do_loop
from app.services.contas_medicas.contratos import (
    TIPOS_DO_ARQUIVO,
    ArquivoDoContratoRecusadoError,
    ContratoRecusadoError,
    arquivo_do_contrato,
    confirmar_contrato,
    hoje_em_sao_paulo,
    ler_contrato_enviado,
    listar_contratos,
    operadora_da_sigla,
)

router = APIRouter(prefix="/contas-medicas", tags=["contas-medicas"])

PERMISSAO = "contratos_avisos"
PERMISSAO_DE_MUDAR = "regra_contratual_tabelas"
_PODE_VER = require_permissao_cm(PERMISSAO)

# O contrato da ASSIM com os 110 aditivos, escaneado, é o maior que se espera.
TETO_DO_ARQUIVO = 50 * 1024 * 1024


class ContratoConfirmado(BaseModel):
    data_assinatura: date | None = None
    aditivo_numero: str | None = Field(default=None, max_length=40)
    aditivo_data: date | None = None
    vigencia_inicio: date | None = None
    vencimento: date | None = None
    vencimento_calculado: bool = False
    arquivo: str | None = Field(default=None, max_length=300)


def _pode_mudar(me: dict) -> bool:
    return PERMISSAO_DE_MUDAR in me["permissoes_cm"]


def _barrar_quem_so_ve(me: dict) -> None:
    if not _pode_mudar(me):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você vê os contratos e recebe o aviso; quem muda o contrato é a gestão.",
        )


def _operadora(supabase, sigla: str) -> str:
    operadora_id = operadora_da_sigla(supabase, sigla)
    if operadora_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Operadora não cadastrada")
    return operadora_id


@router.get("/contratos")
@limiter.limit("60/minute")
async def contratos(
    request: Request,
    me: dict = Depends(_PODE_VER),
    supabase=Depends(get_supabase_client),
) -> dict:
    """Uma linha por operadora, com o contrato, os dias que faltam e a situação."""
    return {"contratos": listar_contratos(supabase, hoje_em_sao_paulo()), "pode_editar": _pode_mudar(me)}


@router.post("/contratos/{sigla}/arquivo")
@limiter.limit("20/minute")
async def enviar_contrato(
    request: Request,
    sigla: str,
    arquivo: UploadFile = File(...),
    me: dict = Depends(_PODE_VER),
    supabase=Depends(get_supabase_client),
) -> dict:
    """Guarda o contrato ou o aditivo e devolve os campos que a IA leu, para a
    pessoa conferir. Nada vale antes da confirmação."""
    _barrar_quem_so_ve(me)
    operadora_id = _operadora(supabase, sigla)
    conteudo = await arquivo.read(TETO_DO_ARQUIVO + 1)
    if len(conteudo) > TETO_DO_ARQUIVO:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="O arquivo passa de 50 MB.")
    try:
        # A leitura do PDF e a IA levam segundos: fora do laço de eventos.
        return await chamar_ia_fora_do_loop(
            ler_contrato_enviado, supabase, operadora_id, arquivo.filename or "", conteudo
        )
    except ArquivoDoContratoRecusadoError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from None


@router.post("/contratos/{sigla}")
@limiter.limit("30/minute")
async def confirmar(
    request: Request,
    sigla: str,
    corpo: ContratoConfirmado,
    me: dict = Depends(_PODE_VER),
    supabase=Depends(get_supabase_client),
) -> dict:
    """Os campos confirmados passam a valer, com quem confirmou e quando."""
    _barrar_quem_so_ve(me)
    operadora_id = _operadora(supabase, sigla)
    try:
        return await run_in_threadpool(
            confirmar_contrato, supabase, operadora_id, corpo.model_dump(), me.get("id"), datetime.now(UTC)
        )
    except ContratoRecusadoError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from None


@router.get("/contratos/{sigla}/arquivo")
@limiter.limit("60/minute")
async def baixar_contrato(
    request: Request,
    sigla: str,
    _me: dict = Depends(_PODE_VER),
    supabase=Depends(get_supabase_client),
) -> Response:
    """O contrato ou o aditivo confirmado da operadora."""
    operadora_id = _operadora(supabase, sigla)
    guardado = await run_in_threadpool(arquivo_do_contrato, supabase, operadora_id)
    if guardado is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Operadora sem contrato enviado")
    chave, conteudo = guardado
    extensao = os.path.splitext(chave)[1].lower()
    nome = "".join(c for c in f"CONTRATO-{sigla.strip().upper()}{extensao}" if c.isalnum() or c in "._-")
    return Response(
        content=conteudo,
        media_type=TIPOS_DO_ARQUIVO.get(extensao, "application/octet-stream"),
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )
