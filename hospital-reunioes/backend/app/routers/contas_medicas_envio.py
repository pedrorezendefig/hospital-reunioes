"""Envio e fila de Contas médicas (issue #1123, PRD #1113, ADR 0070).

A tela Contas: a faturista arrasta a Conta e o Prontuário do MV, recebe na
hora o "Último envio" por atendimento e vê a fila em ordem de envio. A regra do
envio mora em `services/contas_medicas/envio`; aqui ficam o gate e o formato.

Router próprio, com o mesmo prefixo do módulo, como o do Guia e o das
operadoras. Toda rota passa por "enviar e corrigir contas"; a fila filtra por
`faturista_id` no servidor para quem não tem "painel completo".
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from supabase import Client

from app.dependencies import get_supabase_client, require_permissao_cm
from app.limiter import limiter
from app.services.contas_medicas.envio import (
    LIMITE_POR_ARQUIVO,
    ArquivoRecebido,
    EnvioNaoEncontradoError,
    receber,
)

router = APIRouter(prefix="/contas-medicas", tags=["contas-medicas"])

_PODE_ENVIAR = require_permissao_cm("enviar_corrigir_contas")


@router.post("/envios")
@limiter.limit("60/minute")
async def enviar_arquivos(
    request: Request,
    arquivos: list[UploadFile] = File(...),
    envio_id: UUID | None = Form(default=None),
    me: dict = Depends(_PODE_ENVIAR),
    supabase: Client = Depends(get_supabase_client),
) -> dict:
    """Um lote de PDFs de um envio. Sem `envio_id`, abre um envio novo; com
    ele, o lote entra no mesmo envio. Devolve o "Último envio" e as recusas."""
    recebidos = []
    for arquivo in arquivos:
        # Lê um byte além do limite: basta para recusar sem ler o resto.
        conteudo = await arquivo.read(LIMITE_POR_ARQUIVO + 1)
        recebidos.append(ArquivoRecebido(nome=arquivo.filename or "arquivo.pdf", conteudo=conteudo))
    try:
        # A leitura dos PDFs leva segundos: fora do laço de eventos.
        return await run_in_threadpool(
            receber,
            supabase,
            me["id"],
            str(envio_id) if envio_id else None,
            recebidos,
            datetime.now(UTC),
        )
    except EnvioNaoEncontradoError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Envio não encontrado") from None
