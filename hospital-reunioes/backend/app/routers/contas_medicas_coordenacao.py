"""A Conferência da coordenação de Contas médicas (issue #1143, PRD #1129, adendo v1.1).

As rotas da tela `/contas-medicas/coordenacao`: os lembretes abertos por conta
e a marcação (Incluído ou Não se aplica), e a aba Cenários (lista, proposta da
IA, novo e editar).

Toda rota pede "conferência da coordenação": nenhum dado de cenário ou de
lembrete sai para quem não tem (a faturista recebe 403). Os cenários pedem
também "incluir regra operacional": a coordenadora confere os lembretes, mas
quem cadastra é a gestão e a diretoria.

Router próprio, com o mesmo prefixo do módulo, para a tela andar sem disputar
o arquivo das outras.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.dependencies import get_supabase_client, require_permissao_cm
from app.limiter import limiter
from app.services.ai_processor import chamar_ia_fora_do_loop
from app.services.contas_medicas.coordenacao import (
    CenarioNaoEncontradoError,
    editar_cenario,
    lembretes_abertos,
    listar_cenarios,
    novo_cenario,
    propor_cenario,
)

router = APIRouter(prefix="/contas-medicas", tags=["contas-medicas"])

PERMISSAO = "conferencia_coordenacao"
PERMISSAO_DE_CADASTRAR = "incluir_regra_operacional"
_PODE_VER = require_permissao_cm(PERMISSAO)


class InsumoDoCenario(BaseModel):
    codigo: str = Field(..., min_length=1, max_length=40)
    descricao: str | None = Field(default=None, max_length=300)
    quantidade: float = Field(default=1, gt=0, le=100_000)


class CenarioConferido(BaseModel):
    """O cenário como a pessoa conferiu e salva."""

    nome: str = Field(..., min_length=1, max_length=200)
    operadora_sigla: str | None = Field(default=None, max_length=40)
    gatilho_texto: str = Field(..., min_length=1, max_length=2000)
    orientacao: str | None = Field(default=None, max_length=2000)
    ativo: bool = True
    insumos: list[InsumoDoCenario] = Field(..., min_length=1, max_length=50)


class TextoDoCenario(BaseModel):
    texto: str = Field(..., min_length=1, max_length=4000)


def _pode_cadastrar(me: dict) -> bool:
    return PERMISSAO_DE_CADASTRAR in me["permissoes_cm"]


def _barrar_quem_nao_cadastra(me: dict) -> None:
    if not _pode_cadastrar(me):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Quem cadastra cenário é quem tem a permissão de incluir regra operacional.",
        )


def _campos(corpo: CenarioConferido) -> dict:
    campos = corpo.model_dump()
    if not campos["nome"].strip() or not campos["gatilho_texto"].strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="O cenário precisa de nome e de gatilho."
        )
    if any(not insumo["codigo"].strip() for insumo in campos["insumos"]):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Todo insumo precisa do código da conta."
        )
    return campos


@router.get("/coordenacao")
@limiter.limit("60/minute")
async def conferencia_da_coordenacao(
    request: Request,
    me: dict = Depends(_PODE_VER),
    supabase=Depends(get_supabase_client),
) -> dict:
    """Os três números e os lembretes abertos por conta, o mais antigo
    primeiro. `pode_cadastrar` diz à tela se mostra a aba Cenários."""
    return {**await run_in_threadpool(lembretes_abertos, supabase), "pode_cadastrar": _pode_cadastrar(me)}


@router.get("/coordenacao/cenarios")
@limiter.limit("60/minute")
async def cenarios(
    request: Request,
    me: dict = Depends(_PODE_VER),
    supabase=Depends(get_supabase_client),
) -> dict:
    """Todos os cenários, ativos e inativos, para quem cadastra."""
    _barrar_quem_nao_cadastra(me)
    return {"cenarios": await run_in_threadpool(listar_cenarios, supabase)}


@router.post("/coordenacao/cenarios/proposta")
@limiter.limit("20/minute")
async def proposta_de_cenario(
    request: Request,
    corpo: TextoDoCenario,
    me: dict = Depends(_PODE_VER),
    supabase=Depends(get_supabase_client),
) -> dict:
    """Os campos que a IA lê do texto da pessoa, com os códigos conferidos
    contra a tabela. Nada é gravado antes de ela salvar."""
    _barrar_quem_nao_cadastra(me)
    return await chamar_ia_fora_do_loop(propor_cenario, supabase, corpo.texto)


@router.post("/coordenacao/cenarios", status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
async def criar_cenario(
    request: Request,
    corpo: CenarioConferido,
    me: dict = Depends(_PODE_VER),
    supabase=Depends(get_supabase_client),
) -> dict:
    """Grava o cenário com o próximo código CEN-NNN, o autor e a data."""
    _barrar_quem_nao_cadastra(me)
    return await run_in_threadpool(novo_cenario, supabase, _campos(corpo), me.get("id"))


@router.put("/coordenacao/cenarios/{cenario_id}")
@limiter.limit("30/minute")
async def mudar_cenario(
    request: Request,
    cenario_id: UUID,
    corpo: CenarioConferido,
    me: dict = Depends(_PODE_VER),
    supabase=Depends(get_supabase_client),
) -> dict:
    """Edita, ativa ou desativa o cenário, com o antes e o depois no registro."""
    _barrar_quem_nao_cadastra(me)
    try:
        return await run_in_threadpool(editar_cenario, supabase, str(cenario_id), _campos(corpo), me.get("id"))
    except CenarioNaoEncontradoError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from None
