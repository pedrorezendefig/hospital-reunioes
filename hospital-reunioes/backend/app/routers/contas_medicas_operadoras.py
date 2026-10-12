"""Carga da operadora em Contas médicas (issue #1119, PRD #1113, ADR 0070).

As rotas da tela `/contas-medicas/operadoras`: a lista das operadoras com a
situação de cada uma, o envio do arquivo de memória e a exportação dele, e os
cadastros de planos e setores como o MV imprime. Tudo atrás da permissão
"regra contratual e tabelas": quem decide o que é regra do convênio é a gestão,
não a faturista.

Router próprio, com o mesmo prefixo do módulo, para a carga andar sem disputar
o arquivo das rotas de envio, fila e guia.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status

from app.dependencies import get_supabase_client, require_permissao_cm
from app.limiter import limiter
from app.services.contas_medicas.memoria import MemoriaRecusadaError, ler_memoria
from app.services.contas_medicas.operadoras import importar_memoria

router = APIRouter(prefix="/contas-medicas", tags=["contas-medicas"])

PERMISSAO = "regra_contratual_tabelas"

# A memória da ASSIM, a maior, tem 40 KB. Um teto folgado barra o PDF enviado
# no campo errado antes de ele ser lido inteiro para a memória do processo.
TETO_DO_ARQUIVO_DE_MEMORIA = 1024 * 1024


@router.post("/operadoras/memoria", status_code=status.HTTP_201_CREATED)
@limiter.limit("20/minute")
async def enviar_memoria(
    request: Request,
    arquivo: UploadFile = File(...),
    me: dict = Depends(require_permissao_cm(PERMISSAO)),
    supabase=Depends(get_supabase_client),
) -> dict:
    """Importa o arquivo de memória: versão nova, vigente, com as regras dela."""
    conteudo = await arquivo.read(TETO_DO_ARQUIVO_DE_MEMORIA + 1)
    if len(conteudo) > TETO_DO_ARQUIVO_DE_MEMORIA:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="O arquivo é grande demais para uma memória. Envie o MEMORIA-<SIGLA>-v<versão>.md.",
        )
    try:
        texto = conteudo.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="O arquivo não é texto. Envie o MEMORIA-<SIGLA>-v<versão>.md.",
        ) from None
    try:
        memoria = ler_memoria(texto)
    except MemoriaRecusadaError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from None
    return importar_memoria(supabase, memoria, texto, me.get("id"))
