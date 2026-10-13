"""A Memória da operadora por tela (issue #1140, PRD #1129, ADR 0070).

As rotas da tela `/contas-medicas/operadoras/[sigla]`: editar uma regra
vigente e decidir uma pendente, cada mudança numa versão nova da memória.
O gate da rota é ter o eixo de Contas médicas; a permissão de verdade depende
do tipo da regra (operacional ou contratual) e é conferida no serviço, antes
de gravar qualquer coisa.

Router próprio, com o mesmo prefixo do módulo, para a tela andar sem disputar
o arquivo da carga da operadora.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.dependencies import get_supabase_client, require_permissao_cm
from app.limiter import limiter
from app.services.contas_medicas.memoria_edicao import (
    PERMISSOES_DA_TELA,
    MudancaRecusadaError,
    RegraNaoEncontradaError,
    SemPermissaoNaRegraError,
    ler_memoria_da_operadora,
    mudar_regra,
)

router = APIRouter(prefix="/contas-medicas", tags=["contas-medicas"])


class RegraDecidida(BaseModel):
    """O texto, o tipo e a origem como a regra fica."""

    texto: str = Field(..., max_length=4000)
    tipo: Literal["CONTRATUAL", "OPERACIONAL"] | None = None
    origem: str | None = Field(default=None, max_length=200)


class RegraEditada(RegraDecidida):
    """Com `aplicar_a_todas`, a regra do Modelo HSM muda em cada operadora que a tem."""

    aplicar_a_todas: bool = False


def _gravar_mudanca(supabase, me: dict, sigla: str, codigo: str, corpo: RegraDecidida, *, decidir: bool) -> dict:
    try:
        return mudar_regra(
            supabase,
            sigla,
            codigo,
            texto=corpo.texto,
            tipo=corpo.tipo,
            origem=corpo.origem,
            decidir=decidir,
            autor_id=me.get("id"),
            permissoes=me.get("permissoes_cm") or [],
            aplicar_a_todas=getattr(corpo, "aplicar_a_todas", False),
        )
    except RegraNaoEncontradaError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from None
    except SemPermissaoNaRegraError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from None
    except MudancaRecusadaError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from None


@router.get("/operadoras/{sigla}")
@limiter.limit("60/minute")
async def memoria_da_operadora(
    request: Request,
    sigla: str,
    me: dict = Depends(require_permissao_cm()),
    supabase=Depends(get_supabase_client),
) -> dict:
    """A memória da operadora para a tela: cabeçalho, regras, tabelas e histórico de versões.

    Abre para quem muda regra de algum tipo; `permissoes` diz de quais, para a
    tela mostrar Editar e Decidir só onde a pessoa pode.
    """
    permissoes = [p for p in PERMISSOES_DA_TELA if p in (me.get("permissoes_cm") or [])]
    if not permissoes:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sem permissão para a memória das operadoras")
    memoria = ler_memoria_da_operadora(supabase, sigla)
    if memoria is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Operadora não cadastrada")
    return {**memoria, "permissoes": permissoes}


@router.put("/operadoras/{sigla}/regras/{codigo}")
@limiter.limit("30/minute")
async def editar_regra(
    request: Request,
    sigla: str,
    codigo: str,
    corpo: RegraEditada,
    me: dict = Depends(require_permissao_cm()),
    supabase=Depends(get_supabase_client),
) -> dict:
    """Edita a regra vigente: versão nova da memória, com o texto anterior guardado."""
    return _gravar_mudanca(supabase, me, sigla, codigo, corpo, decidir=False)


@router.post("/operadoras/{sigla}/regras/{codigo}/decisao")
@limiter.limit("30/minute")
async def decidir_regra(
    request: Request,
    sigla: str,
    codigo: str,
    corpo: RegraDecidida,
    me: dict = Depends(require_permissao_cm()),
    supabase=Depends(get_supabase_client),
) -> dict:
    """Decide a regra pendente: vira vigente, com quem validou e a data, numa versão nova."""
    return _gravar_mudanca(supabase, me, sigla, codigo, corpo, decidir=True)
