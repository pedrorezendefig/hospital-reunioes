"""A fila de Validação de Contas médicas (issue #1142, PRD #1129, ADR 0070).

As rotas da tela `/contas-medicas/validacao`: os temas abertos e as decisões
de cada um. Toda rota passa pelo gate "decidir na validação". Mexer na memória
(Validar regra, Editar a regra) pede também a permissão do tipo da regra, que
o serviço da memória confere antes de gravar.

Router próprio, com o mesmo prefixo do módulo, para a tela andar sem disputar
o arquivo das outras telas.
"""

from __future__ import annotations

import re
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from app.dependencies import get_supabase_client, require_permissao_cm
from app.limiter import limiter
from app.services.ai_processor import chamar_ia_fora_do_loop
from app.services.contas_medicas import validacao_decidida
from app.services.contas_medicas.ia import ErroDaIA
from app.services.contas_medicas.memoria_edicao import (
    MudancaRecusadaError,
    RegraNaoEncontradaError,
    SemPermissaoNaRegraError,
)
from app.services.contas_medicas.validacao import (
    DecisaoRecusadaError,
    TemaNaoEncontradoError,
    csv_do_cadastro,
    decidir_tema,
    fila_de_validacao,
    leitura_da_observacao,
    tema_enviado_ao_cadastro,
)
from app.services.contas_medicas.validacao_decidida import aprovar_lote

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


class TemaDoLote(BaseModel):
    """Um cartão do lote e a recomendação que ele mostrava."""

    id: UUID
    decisao: str = Field(max_length=40)
    recomendado_em: str = Field(max_length=64)


class Lote(BaseModel):
    """Os temas que a tela mostrava com a recomendação do Auditor."""

    temas: list[TemaDoLote] = Field(max_length=500)


@router.post("/validacao/lote")
@limiter.limit("30/minute")
async def aprovar_o_lote(
    request: Request,
    corpo: Lote,
    me: dict = Depends(_PODE_DECIDIR),
    supabase=Depends(get_supabase_client),
) -> dict:
    """ "Aprovar o lote" (#1491): cada tema aberto com recomendação recebe a
    decisão do Auditor pelo caminho do cartão, se ainda for a que a tela
    mostrou. Devolve os decididos, os que recusaram, com o motivo, e os
    enviados ao cadastro, para baixar a lista."""
    vistos = [{"id": str(t.id), "decisao": t.decisao, "recomendado_em": t.recomendado_em} for t in corpo.temas]
    return aprovar_lote(supabase, vistos, me)


@router.get("/validacao/recomendacao")
@limiter.limit("60/minute")
async def ver_pedido_de_recomendacao(
    request: Request,
    me: dict = Depends(_PODE_DECIDIR),
    supabase=Depends(get_supabase_client),
) -> dict:
    """O que o botão "Pedir recomendação ao Auditor" mostra antes do clique
    (ADR 0082): temas sem recomendação, provas, custo estimado e se já roda."""
    return validacao_decidida.pedido_de_recomendacao(supabase)


@router.post("/validacao/recomendacao", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("10/minute")
async def pedir_recomendacao(
    request: Request,
    tarefas: BackgroundTasks,
    me: dict = Depends(_PODE_DECIDIR),
    supabase=Depends(get_supabase_client),
) -> dict:
    """O clique no botão (ADR 0082, issue #1523): o Auditor recomenda, em
    segundo plano, todos os temas abertos sem recomendação. Um pedido por vez;
    sem tema a recomendar, nada roda."""
    if not validacao_decidida.reservar():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="O Auditor já está recomendando a fila. Espere terminar."
        )
    try:
        pedido = validacao_decidida.pedido_de_recomendacao(supabase)
    except Exception:
        # O banco que cai aqui não pode deixar o botão preso no "recomendando".
        validacao_decidida.liberar()
        raise
    if not pedido["temas"]:
        validacao_decidida.liberar()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Nenhum tema aguarda recomendação.")
    tarefas.add_task(validacao_decidida.recomendar_e_liberar, supabase)
    return {**pedido, "em_andamento": True}


@router.post("/validacao/temas/{tema_id}/leitura")
@limiter.limit("30/minute")
async def ler_observacao(
    request: Request,
    tema_id: UUID,
    me: dict = Depends(_PODE_DECIDIR),
    supabase=Depends(get_supabase_client),
) -> dict:
    """A leitura da IA sobre as observações do tema: a guardada ou, na falta,
    uma chamada curta, que fica guardada no tema."""
    try:
        leitura = await chamar_ia_fora_do_loop(leitura_da_observacao, supabase, str(tema_id))
    except TemaNaoEncontradoError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from None
    except DecisaoRecusadaError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from None
    except ErroDaIA:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Tente de novo em alguns minutos"
        ) from None
    return {"leitura_ia": leitura}


@router.post("/validacao/temas/{tema_id}/cadastro")
@limiter.limit("30/minute")
async def enviar_ao_cadastro(
    request: Request,
    tema_id: UUID,
    me: dict = Depends(_PODE_DECIDIR),
    supabase=Depends(get_supabase_client),
) -> Response:
    """ "Enviar ao cadastro": fecha o tema do código bloqueado e devolve a lista
    em CSV, para o cadastro e a consultoria do MV."""
    try:
        tema = decidir_tema(supabase, str(tema_id), {"decisao": "ENVIAR_AO_CADASTRO"}, me)
    except TemaNaoEncontradoError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from None
    except DecisaoRecusadaError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from None
    return _lista_do_cadastro(supabase, tema)


@router.get("/validacao/temas/{tema_id}/cadastro")
@limiter.limit("30/minute")
async def baixar_lista_do_cadastro(
    request: Request,
    tema_id: UUID,
    me: dict = Depends(_PODE_DECIDIR),
    supabase=Depends(get_supabase_client),
) -> Response:
    """A lista do tema já enviado ao cadastro, de novo: o aprovado no lote."""
    try:
        tema = tema_enviado_ao_cadastro(supabase, str(tema_id))
    except TemaNaoEncontradoError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from None
    except DecisaoRecusadaError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from None
    return _lista_do_cadastro(supabase, tema)


def _lista_do_cadastro(supabase, tema: dict) -> Response:
    nome = f"cadastro-{re.sub(r'[^0-9A-Za-z.-]', '', tema.get('codigo_item') or '') or 'bloqueado'}.csv"
    return Response(
        content="﻿" + csv_do_cadastro(supabase, tema["id"]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )
