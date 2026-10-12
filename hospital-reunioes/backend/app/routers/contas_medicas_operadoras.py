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
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile, status
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.dependencies import get_supabase_client, require_permissao_cm
from app.limiter import limiter
from app.services.contas_medicas.dicionario import DicionarioRecusadoError, importar_dicionario, ler_dicionario
from app.services.contas_medicas.memoria import MemoriaRecusadaError, ler_memoria
from app.services.contas_medicas.operadoras import (
    CadastroRecusadoError,
    cadastrar_plano,
    cadastrar_setor,
    importar_memoria,
    listar_operadoras,
    listar_planos,
    listar_setores,
    texto_da_memoria_vigente,
)
from app.services.contas_medicas.tabelas import TabelaRecusadaError, importar_tabela, ler_tabela

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

# A LPM de materiais da Unimed, a maior tabela, tem 6 MB.
TETO_DO_CSV = 20 * 1024 * 1024

# As categorias que recebem tabela por envio. HONORARIO existe na migration
# 116 e fica "não carregada": a CBHPM não chegou.
CategoriaDeTabela = Literal["MATERIAL", "MEDICAMENTO", "DIARIA_TAXA", "PACOTE"]


def _422(detalhe: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=detalhe)


async def _texto_do_csv(arquivo: UploadFile) -> str:
    conteudo = await arquivo.read(TETO_DO_CSV + 1)
    if len(conteudo) > TETO_DO_CSV:
        raise _422("O arquivo passa de 20 MB, grande demais para uma tabela.")
    try:
        return conteudo.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise _422("O arquivo não é um CSV em UTF-8.") from None


@router.get("/operadoras")
@limiter.limit("60/minute")
async def operadoras(
    request: Request,
    _me: dict = Depends(require_permissao_cm(PERMISSAO)),
    supabase=Depends(get_supabase_client),
) -> dict:
    """As operadoras com a situação, a versão da memória, as regras e as tabelas carregadas."""
    return {"operadoras": listar_operadoras(supabase)}


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


@router.post("/operadoras/{sigla}/tabelas", status_code=status.HTTP_201_CREATED)
@limiter.limit("20/minute")
async def enviar_tabela(
    request: Request,
    sigla: str,
    categoria: CategoriaDeTabela = Form(...),
    vigencia_inicio: date = Form(...),
    vigencia_fim: date | None = Form(default=None),
    versao: str | None = Form(default=None, max_length=200),
    arquivo: UploadFile = File(...),
    me: dict = Depends(require_permissao_cm(PERMISSAO)),
    supabase=Depends(get_supabase_client),
) -> dict:
    """Carrega o CSV como uma versão nova da tabela da categoria, ao lado das anteriores."""
    sigla = sigla.strip().upper()
    if vigencia_fim and vigencia_fim < vigencia_inicio:
        raise _422("O fim da vigência é anterior ao início.")
    operadoras = supabase.table("cm_operadora").select("id").eq("sigla", sigla).execute().data or []
    if not operadoras:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"A operadora {sigla} não está cadastrada")
    texto = await _texto_do_csv(arquivo)
    try:
        tabela = ler_tabela(texto)
    except TabelaRecusadaError as exc:
        raise _422(str(exc)) from None
    # A LPM tem dezenas de milhares de itens: a gravação sai do laço de eventos.
    resumo = await run_in_threadpool(
        importar_tabela,
        supabase,
        operadoras[0]["id"],
        categoria,
        tabela,
        vigencia_inicio=vigencia_inicio,
        vigencia_fim=vigencia_fim,
        versao=(versao or "").strip() or None,
        arquivo_nome=arquivo.filename or f"{sigla}-{categoria}.csv",
        autor_id=me.get("id"),
    )
    return {"operadora": sigla, **resumo}


@router.post("/dicionario", status_code=status.HTTP_201_CREATED)
@limiter.limit("20/minute")
async def enviar_dicionario(
    request: Request,
    arquivo: UploadFile = File(...),
    me: dict = Depends(require_permissao_cm(PERMISSAO)),
    supabase=Depends(get_supabase_client),
) -> dict:
    """Carrega o dicionário de itens do hospital: termo atualizado ou novo, um por sinônimo."""
    texto = await _texto_do_csv(arquivo)
    try:
        termos = ler_dicionario(texto)
    except DicionarioRecusadoError as exc:
        raise _422(str(exc)) from None
    return await run_in_threadpool(importar_dicionario, supabase, termos, me.get("id"))


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
