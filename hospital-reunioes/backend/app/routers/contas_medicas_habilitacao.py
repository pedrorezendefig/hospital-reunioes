"""A Habilitação de Contas médicas (issue #1139, PRD #1129, ADR 0070).

As rotas da tela `/contas-medicas/habilitacao`: a matriz perfil x permissão,
editável célula a célula, e a busca de pessoa com a atribuição ou a retirada
do perfil do módulo. Tudo atrás da permissão "habilitar pessoas"; cada mudança
grava `cm_registro` com autor, data, antes e depois.

Router próprio, com o mesmo prefixo do módulo, para a Habilitação andar sem
disputar o arquivo das outras telas.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from pydantic import BaseModel

from app.dependencies import get_supabase_client, require_permissao_cm
from app.limiter import limiter
from app.services.contas_medicas.habilitacao import (
    PessoaNaoEncontradaError,
    buscar_pessoas,
    ler_matriz,
    mudar_perfil,
    mudar_permissao,
)

router = APIRouter(prefix="/contas-medicas", tags=["contas-medicas"])

_PODE_HABILITAR = require_permissao_cm("habilitar_pessoas")

# Os valores dos CHECKs das migrations 116 e 121, na ordem da spec.
Perfil = Literal[
    "faturista",
    "coordenadora",
    "gestao_contas_medicas",
    "diretoria_medica",
    "diretoria_executiva",
    "credenciamento",
    "apoio_faturamento",
]
Permissao = Literal[
    "enviar_contas",
    "enviar_corrigir_contas",
    "decidir_validacao",
    "incluir_regra_operacional",
    "regra_contratual_tabelas",
    "contratos_avisos",
    "painel_completo",
    "habilitar_pessoas",
    "conferencia_coordenacao",
]


class CelulaDaMatriz(BaseModel):
    perfil: Perfil
    permissao: Permissao
    ligada: bool


class PerfilDaPessoa(BaseModel):
    """`perfil` nulo tira a pessoa do módulo."""

    perfil: Perfil | None


@router.get("/habilitacao")
@limiter.limit("60/minute")
async def matriz(
    request: Request,
    _me: dict = Depends(_PODE_HABILITAR),
    supabase=Depends(get_supabase_client),
) -> dict:
    """A matriz perfil x permissão como o guard a lê agora."""
    return ler_matriz(supabase)


@router.put("/habilitacao/matriz")
@limiter.limit("60/minute")
async def mudar_celula(
    request: Request,
    corpo: CelulaDaMatriz,
    me: dict = Depends(_PODE_HABILITAR),
    supabase=Depends(get_supabase_client),
) -> dict:
    """Liga ou desliga uma permissão de um perfil; vale na próxima requisição."""
    return mudar_permissao(supabase, corpo.perfil, corpo.permissao, corpo.ligada, me.get("id"))


@router.get("/habilitacao/pessoas")
@limiter.limit("60/minute")
async def pessoas(
    request: Request,
    busca: str | None = Query(default=None, max_length=100),
    _me: dict = Depends(_PODE_HABILITAR),
    supabase=Depends(get_supabase_client),
) -> dict:
    """Sem busca, quem tem perfil no módulo; com busca, as pessoas pelo nome."""
    return {"pessoas": buscar_pessoas(supabase, busca)}


@router.put("/habilitacao/pessoas/{participante_id}")
@limiter.limit("60/minute")
async def mudar_perfil_da_pessoa(
    request: Request,
    corpo: PerfilDaPessoa,
    participante_id: str = Path(..., max_length=10),
    me: dict = Depends(_PODE_HABILITAR),
    supabase=Depends(get_supabase_client),
) -> dict:
    """Dá, troca ou tira o perfil de Contas médicas de uma pessoa."""
    try:
        return mudar_perfil(supabase, participante_id, corpo.perfil, me.get("id"))
    except PessoaNaoEncontradaError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pessoa não encontrada.") from None
