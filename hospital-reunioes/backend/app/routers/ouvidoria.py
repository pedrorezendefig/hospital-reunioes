"""Painel de ouvidoria (issue #292, ADR 0031 decisão 3): a equipe do hospital
enxerga os protocolos registrados pela Ana e marca cada um como respondido.

Fluxo JWT (usuário logado), fora da API de serviço da Ana. Índice, não dossiê:
o painel expõe os mesmos campos da API da Ana e nada além deles; protocolo
nasce só pelo registro da Ana (não existe rota de criação aqui).
"""

import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from postgrest.exceptions import APIError
from pydantic import BaseModel
from supabase import Client

from app.dependencies import (
    get_current_user,
    get_participante_for_user,
    get_supabase_client,
    tem_acesso_reunioes,
)
from app.limiter import limiter
from app.routers.ana import _CAMPOS_PROTOCOLO, _CAMPOS_PROTOCOLO_TUPLA
from app.services.ouvidoria_estados import (
    DadosInsuficientesError,
    TransicaoInvalidaError,
    validar_transicao,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ouvidoria", tags=["ouvidoria"])


async def require_acesso_painel(
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
) -> dict:
    """Gate do painel: quem tem papel no contexto Reuniões (facilitador,
    secretária, super admin) mais quem tem papel na Ouvidoria. O ouvidor pode
    não participar de Reuniões nenhuma e ainda assim é o dono desta tela.

    Devolve o participante: a listagem decide o que mostrar pelo perfil."""
    me = await get_participante_for_user(current_user, supabase)
    if not me or not (tem_acesso_reunioes(me) or tem_perfil_ouvidoria(me)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito à equipe de Reuniões",
        )
    return me


@router.get("/protocolos")
@limiter.limit("60/minute")
async def listar_protocolos(
    request: Request,
    me: dict = Depends(require_acesso_painel),
    supabase=Depends(get_supabase_client),
):
    """Todos os protocolos, mais recentes primeiro, com prazo e status.

    Índice, não Dossiê: agora que a tabela guarda relato e identificação
    (ADR 0034), a resposta é fechada no índice campo a campo, e não no que o
    select devolveu."""
    # sigilo_reforcado entra no select mas não na resposta: é a coluna que
    # decide o filtro abaixo, e o índice segue fechado em _CAMPOS_PROTOCOLO.
    result = (
        supabase.table("ouvidoria_protocolos")
        .select(f"{_CAMPOS_PROTOCOLO}, sigilo_reforcado")
        .order("numero", desc=True)
        .execute()
    )
    linhas = result.data or []
    # Sigilo reforçado (RN-40): o resumo de uma denúncia já identifica quem
    # relatou, então a sigilosa não entra nem no índice de quem está fora da
    # Ouvidoria, super admin incluído.
    if not tem_perfil_ouvidoria(me):
        linhas = [row for row in linhas if not row.get("sigilo_reforcado")]
    return {"protocolos": [{campo: row.get(campo) for campo in _CAMPOS_PROTOCOLO_TUPLA} for row in linhas]}


# Dossiê completo (ADR 0034, decisão 1): o índice mais o que só ouvidor e
# diretoria executiva podem ler.
_CAMPOS_DOSSIE_TUPLA = _CAMPOS_PROTOCOLO_TUPLA + (
    "relato_integral",
    "manifestante_nome",
    "manifestante_contato",
    "manifestante_vinculo",
    "anonimo",
    "sigilo_reforcado",
    "dados_incompletos",
    "classificacao_ia",
    "desfecho",
    "desfecho_descricao",
)
_CAMPOS_DOSSIE = ", ".join(_CAMPOS_DOSSIE_TUPLA)

PERFIS_OUVIDORIA = ("ouvidor", "diretoria_executiva")


def tem_perfil_ouvidoria(participante: dict | None) -> bool:
    """Quem lê o Dossiê (ADR 0034, decisão 8): só os dois perfis do contexto
    Ouvidoria. Papel nas Reuniões, inclusive super admin, não concede."""
    return bool(participante) and participante.get("perfil_ouvidoria") in PERFIS_OUVIDORIA


async def require_perfil_ouvidoria(
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
) -> dict:
    """Gate do Dossiê. Devolve o participante para a rota decidir sobre sigilo
    e para registrar o log de acesso."""
    me = await get_participante_for_user(current_user, supabase)
    if not tem_perfil_ouvidoria(me):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito à Ouvidoria",
        )
    return me


def registrar_acesso(supabase, me: dict, manifestacao_id: str, acao: str) -> None:
    """Grava o log de acesso. Falha aqui não derruba a leitura: a trilha é
    importante, mas deixar o ouvidor sem o Dossiê por causa dela seria pior.
    O timestamp é do banco (`ocorrido_em` tem default now())."""
    try:
        supabase.table("ouvidoria_acessos").insert(
            {
                "manifestacao_id": manifestacao_id,
                "ator_id": me["id"],
                "ator_nome": me.get("nome_completo") or me["id"],
                "acao": acao,
            }
        ).execute()
    except APIError:
        logger.warning("Falha ao registrar acesso à manifestação %s", manifestacao_id)


@router.get("/manifestacoes/{manifestacao_id}")
@limiter.limit("60/minute")
async def abrir_manifestacao(
    request: Request,
    manifestacao_id: str,
    me: dict = Depends(require_perfil_ouvidoria),
    supabase=Depends(get_supabase_client),
):
    """Abre o Dossiê completo de uma manifestação."""
    try:
        result = supabase.table("ouvidoria_protocolos").select(_CAMPOS_DOSSIE).eq("id", manifestacao_id).execute()
    except APIError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Manifestação não encontrada") from exc
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Manifestação não encontrada")
    row = result.data[0]
    registrar_acesso(supabase, me, manifestacao_id, "abrir_dossie")
    return {campo: row.get(campo) for campo in _CAMPOS_DOSSIE_TUPLA}


class PedidoTransicao(BaseModel):
    """Pedido de mudança de estado. `desfecho` e `desfecho_descricao` só fazem
    sentido no encerramento, e lá são obrigatórios."""

    estado: Literal["em_classificacao", "aguardando_area", "respondido", "encerrado"]
    observacao: str | None = None
    desfecho: str | None = None
    desfecho_descricao: str | None = None


@router.post("/manifestacoes/{manifestacao_id}/transicoes")
@limiter.limit("60/minute")
async def transicionar_manifestacao(
    request: Request,
    manifestacao_id: str,
    pedido: PedidoTransicao,
    me: dict = Depends(require_perfil_ouvidoria),
    supabase=Depends(get_supabase_client),
):
    """Porta de entrada única da máquina de estados: valida a regra e grava o
    movimento na mesma transação (RPC `ouvidoria_transicionar`).

    A regra é checada aqui para devolver mensagem útil, e de novo no banco,
    para que contornar a API não contorne a máquina de estados."""
    atual = supabase.table("ouvidoria_protocolos").select("id, status").eq("id", manifestacao_id).execute()
    if not atual.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Manifestação não encontrada")

    try:
        validar_transicao(
            atual.data[0]["status"],
            pedido.estado,
            desfecho=pedido.desfecho,
            desfecho_descricao=pedido.desfecho_descricao,
        )
    except DadosInsuficientesError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    except TransicaoInvalidaError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    try:
        resultado = supabase.rpc(
            "ouvidoria_transicionar",
            {
                "p_manifestacao_id": manifestacao_id,
                "p_estado_novo": pedido.estado,
                "p_autor_id": me["id"],
                "p_autor_nome": me.get("nome_completo") or me["id"],
                "p_observacao": pedido.observacao,
                "p_desfecho": pedido.desfecho,
                "p_desfecho_descricao": pedido.desfecho_descricao,
            },
        ).execute()
    except APIError as exc:
        # A regra também vive no banco: se ele recusar, foi corrida com outra
        # transição, não erro de servidor.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Transição recusada") from exc

    row = resultado.data[0] if isinstance(resultado.data, list) else resultado.data
    registrar_acesso(supabase, me, manifestacao_id, "transicionar")
    return {campo: row.get(campo) for campo in _CAMPOS_DOSSIE_TUPLA}
