"""O Início de quem pede (issue #1934, ADR 0104).

Todo mundo que entra no app tem Início, menos a Secretária, que continua na
tela dela e não vê Pendência (decisão 53 do diretor no PRD #1757): para ela a
rota recusa e não devolve dado nenhum.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import (
    barrar_desligado,
    get_current_user,
    get_participante_for_user,
    get_supabase_client,
    is_secretaria,
)
from app.services.inicio import Inicio, entregas, montar_inicio, quem_responde, registro_de_acesso
from app.services.inicio.regras import FUSO

router = APIRouter(prefix="/inicio", tags=["inicio"])


def agora_em_brasilia() -> datetime:
    return datetime.now(tz=FUSO)


@router.get("", response_model=Inicio)
async def get_inicio(
    current_user: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
) -> Inicio:
    me = await get_participante_for_user(current_user, supabase)
    barrar_desligado(me)
    if is_secretaria(me):
        raise HTTPException(status_code=403, detail="A Secretária não tem Início")
    agora = agora_em_brasilia()
    # O Registro de acesso (issue #1941): o dia em que a pessoa abriu o Início.
    if me:
        registro_de_acesso.marcar(supabase, me["id"], agora.astimezone(FUSO).date())
    return montar_inicio(supabase, me, agora)


@router.get("/quem-responde", response_model=quem_responde.QuemRespondeAVoce | None)
async def get_quem_responde(
    current_user: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
) -> quem_responde.QuemRespondeAVoce | None:
    """O bloco Quem responde a você (issue #1943), em pedido separado do resto
    do Início: a falha dele não derruba a Minha Fila. `null` para quem não
    acompanha ninguém, que não recebe o bloco."""
    me = await get_participante_for_user(current_user, supabase)
    barrar_desligado(me)
    if is_secretaria(me):
        raise HTTPException(status_code=403, detail="A Secretária não tem Início")
    return quem_responde.montar(supabase, me, agora_em_brasilia())


@router.get("/meus-numeros", response_model=entregas.MeusNumeros | None)
async def get_meus_numeros(
    current_user: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
) -> entregas.MeusNumeros | None:
    """Os próprios números de 90 dias e o que foi entregue nos últimos 7 dias
    (issue #1946), em pedido separado do resto do Início: a falha deles não
    derruba a Minha Fila. Só os de quem pede, nunca os de outra pessoa."""
    me = await get_participante_for_user(current_user, supabase)
    barrar_desligado(me)
    if is_secretaria(me):
        raise HTTPException(status_code=403, detail="A Secretária não tem Início")
    return entregas.meus_numeros(supabase, me, agora_em_brasilia())
