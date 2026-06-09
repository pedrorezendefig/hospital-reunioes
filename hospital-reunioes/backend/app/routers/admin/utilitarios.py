"""Router /admin/utilitarios — ferramentas utilitárias para super admins.

Hoje: conversão local de PDF/DOCX em Markdown (zero tokens de LLM).
Stateless — nada é persistido; o arquivo existe só na memória do request.
"""

from __future__ import annotations

import logging
from pathlib import PurePosixPath

import anyio.to_thread
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from starlette.requests import Request

from app.dependencies import require_super_admin
from app.limiter import limiter
from app.models.admin_schemas import ConversaoMarkdownResponse
from app.services import markdown_converter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/utilitarios", tags=["admin", "utilitarios"])

EXTENSOES_ACEITAS = {".pdf", ".docx"}
MAX_FILE_BYTES = 15 * 1024 * 1024  # 15 MB — mesmo teto da importação de atas
MIN_MARKDOWN_CHARS = 200  # abaixo disso, PDF presume-se escaneado/vazio
AVISO_POUCO_TEXTO_CHARS = 1000


@router.post("/converter-markdown", response_model=ConversaoMarkdownResponse)
@limiter.limit("10/minute")
async def converter_markdown(
    request: Request,
    file: UploadFile = File(...),
    _me: dict = Depends(require_super_admin),
):
    """Converte um PDF ou DOCX em Markdown localmente, sem consumo de IA."""
    extensao = PurePosixPath(file.filename or "").suffix.lower()
    if extensao not in EXTENSOES_ACEITAS:
        raise HTTPException(400, "Somente arquivos .pdf ou .docx são aceitos")

    dados = await file.read()
    if len(dados) == 0:
        raise HTTPException(400, "Arquivo vazio")
    if len(dados) > MAX_FILE_BYTES:
        raise HTTPException(413, f"Arquivo excede o limite de {MAX_FILE_BYTES // (1024 * 1024)} MB")

    # Conversão é CPU-bound (pdfminer/mammoth): roda em thread para não
    # bloquear o event loop (uvicorn single-worker).
    try:
        resultado = await anyio.to_thread.run_sync(markdown_converter.converter_para_markdown, dados, extensao)
    except markdown_converter.ConversaoError:
        raise HTTPException(
            500,
            "Falha ao converter o arquivo para Markdown. "
            "Verifique se o arquivo não está corrompido ou protegido por senha.",
        )

    texto = resultado.markdown.strip()
    if extensao == ".pdf" and len(texto) < MIN_MARKDOWN_CHARS:
        raise HTTPException(422, "PDF parece escaneado ou sem texto extraível. Envie uma versão com texto nativo.")
    if extensao == ".docx" and not texto:
        raise HTTPException(422, "O documento não contém texto extraível.")

    avisos: list[str] = []
    if extensao == ".pdf" and len(texto) < AVISO_POUCO_TEXTO_CHARS:
        avisos.append("O documento gerou pouco texto; confira se o resultado está completo.")

    logger.info(f"[utilitarios] {_me.get('id')} converteu '{file.filename}' ({len(dados)} bytes)")
    return ConversaoMarkdownResponse(
        markdown=resultado.markdown,
        nome_arquivo_sugerido=markdown_converter.sugerir_nome_md(file.filename),
        title=resultado.title,
        avisos=avisos,
    )
