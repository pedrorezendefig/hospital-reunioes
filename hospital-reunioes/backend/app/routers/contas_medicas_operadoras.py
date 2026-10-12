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

import re
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile, status
from pydantic import BaseModel, Field

from app.dependencies import get_supabase_client, require_permissao_cm
from app.limiter import limiter
from app.services.contas_medicas.memoria import MemoriaRecusadaError, ler_memoria
from app.services.contas_medicas.operadoras import (
    CadastroRecusadoError,
    cadastrar_plano,
    cadastrar_setor,
    importar_memoria,
    listar_planos,
    listar_setores,
    texto_da_memoria_vigente,
)

router = APIRouter(prefix="/contas-medicas", tags=["contas-medicas"])

PERMISSAO = "regra_contratual_tabelas"


class PlanoNovo(BaseModel):
    nome_mv: str = Field(..., max_length=200)
    operadora: str = Field(..., max_length=40)
    coluna_preco: str | None = Field(default=None, max_length=40)


# As acomodações do CHECK de `cm_setor` (migration 116).
Acomodacao = Literal[
    "CTI",
    "ENFERMARIA",
    "APARTAMENTO",
    "ISOLAMENTO",
    "CENTRO_CIRURGICO",
    "HOSPITAL_DIA",
    "PEDIATRIA",
    "UTI_PEDIATRICA",
    "UTI_NEONATAL",
]


class SetorNovo(BaseModel):
    nome_mv: str = Field(..., max_length=200)
    acomodacao: Acomodacao


def _recusa(exc: CadastroRecusadoError) -> HTTPException:
    codigo = status.HTTP_409_CONFLICT if exc.conflito else status.HTTP_422_UNPROCESSABLE_CONTENT
    return HTTPException(status_code=codigo, detail=str(exc))


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


@router.get("/operadoras/{sigla}/memoria")
@limiter.limit("60/minute")
async def exportar_memoria(
    request: Request,
    sigla: str,
    _me: dict = Depends(require_permissao_cm(PERMISSAO)),
    supabase=Depends(get_supabase_client),
) -> Response:
    """A memória vigente como foi enviada, cabeçalho inteiro, para baixar."""
    vigente = texto_da_memoria_vigente(supabase, sigla)
    if vigente is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Operadora sem memória carregada")
    versao, texto = vigente
    # Sigla e versão vêm de quem enviou: só o que cabe num nome de arquivo.
    nome = re.sub(r"[^A-Za-z0-9._-]", "", f"MEMORIA-{sigla.strip().upper()}-v{versao}.md")
    return Response(
        content=texto,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )


@router.get("/planos")
@limiter.limit("60/minute")
async def planos(
    request: Request,
    _me: dict = Depends(require_permissao_cm(PERMISSAO)),
    supabase=Depends(get_supabase_client),
) -> dict:
    """Os nomes de plano que o MV imprime, cada um com a operadora e a coluna de preço."""
    return {"planos": listar_planos(supabase)}


@router.post("/planos", status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
async def novo_plano(
    request: Request,
    plano: PlanoNovo,
    _me: dict = Depends(require_permissao_cm(PERMISSAO)),
    supabase=Depends(get_supabase_client),
) -> dict:
    """Cadastra um nome de plano do MV. Sem cadastro, a conta desse plano é recusada no envio."""
    try:
        return cadastrar_plano(supabase, plano.nome_mv, plano.operadora, plano.coluna_preco)
    except CadastroRecusadoError as exc:
        raise _recusa(exc) from None


@router.get("/setores")
@limiter.limit("60/minute")
async def setores(
    request: Request,
    _me: dict = Depends(require_permissao_cm(PERMISSAO)),
    supabase=Depends(get_supabase_client),
) -> dict:
    """Os setores como o MV imprime, cada um com a acomodação."""
    return {"setores": listar_setores(supabase)}


@router.post("/setores", status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
async def novo_setor(
    request: Request,
    setor: SetorNovo,
    _me: dict = Depends(require_permissao_cm(PERMISSAO)),
    supabase=Depends(get_supabase_client),
) -> dict:
    """Cadastra um setor do MV com a acomodação, que decide a diária e o teto por dia."""
    try:
        return cadastrar_setor(supabase, setor.nome_mv, setor.acomodacao)
    except CadastroRecusadoError as exc:
        raise _recusa(exc) from None
