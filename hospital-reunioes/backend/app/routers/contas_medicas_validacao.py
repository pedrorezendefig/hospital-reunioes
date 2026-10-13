"""A fila de Validação de Contas médicas (issue #1142, PRD #1129, ADR 0070).

As rotas da tela `/contas-medicas/validacao`: os temas abertos e as decisões
de cada um. Toda rota passa pelo gate "decidir na validação". Mexer na memória
(Validar regra, Editar a regra) pede também a permissão do tipo da regra, que
o serviço da memória confere antes de gravar.

Router próprio, com o mesmo prefixo do módulo, para a tela andar sem disputar
o arquivo das outras telas.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.dependencies import get_supabase_client, require_permissao_cm
from app.limiter import limiter
from app.services.contas_medicas.memoria_edicao import (
    MudancaRecusadaError,
    RegraNaoEncontradaError,
    SemPermissaoNaRegraError,
)
from app.services.contas_medicas.validacao import (
    DecisaoRecusadaError,
    TemaNaoEncontradoError,
    decidir_tema,
    fila_de_validacao,
)

router = APIRouter(prefix="/contas-medicas", tags=["contas-medicas"])

_PODE_DECIDIR = require_permissao_cm("decidir_validacao")


@router.get("/validacao")
@limiter.limit("60/minute")
async def ver_fila_de_validacao(
    request: Request,
    me: dict = Depends(_PODE_DECIDIR),
    supabase=Depends(get_supabase_client),
) -> dict:
    """Os temas abertos, do maior R$ em jogo para o menor, e os três números do topo."""
    return fila_de_validacao(supabase)


class Decisao(BaseModel):
    """A decisão do cartão. `texto` é a regra como fica (Validar regra, Editar a
    regra) ou a resposta ao time; `tipo` e `origem`, quando a regra muda."""

    decisao: Literal[
        "VALIDAR_REGRA",
        "DEIXAR_PENDENTE",
        "DESCARTAR",
        "MANTER_REGRA",
        "EDITAR_REGRA",
        "RESPONDER",
        "CONFIRMAR",
        "REJEITAR",
    ]
    texto: str | None = Field(default=None, max_length=4000)
    tipo: Literal["CONTRATUAL", "OPERACIONAL"] | None = None
    origem: str | None = Field(default=None, max_length=200)


@router.post("/validacao/temas/{tema_id}/decisao")
@limiter.limit("60/minute")
async def decidir(
    request: Request,
    tema_id: UUID,
    corpo: Decisao,
    me: dict = Depends(_PODE_DECIDIR),
    supabase=Depends(get_supabase_client),
) -> dict:
    """Decide o tema: grava quem decidiu e quando, e o tema sai da fila."""
    try:
        return decidir_tema(supabase, str(tema_id), corpo.model_dump(), me)
    except (TemaNaoEncontradoError, RegraNaoEncontradaError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from None
    except SemPermissaoNaRegraError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from None
    except (DecisaoRecusadaError, MudancaRecusadaError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from None
