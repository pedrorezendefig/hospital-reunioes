"""Rotas da Triagem de e-mail (ADR 0051, PRD #646, issues #648 a #651).

Só o Perfil da Ouvidoria entra: o gate é o mesmo do Dossiê
(`require_perfil_ouvidoria`), e Super admin fica de fora como lá. Todo acesso ao
conteúdo de um e-mail recebido entra no log de acesso da Ouvidoria.

O ouvidor lê a lista e o item. Das decisões, virar manifestação (#650) mora
aqui só como a pré-carga: quem cria o caso é o registro manual
(`POST /ouvidoria/manifestacoes` com o `email_recebido_id`). Descartar (#649)
é a rota `descarte`, e juntar a um caso que já existe (#651) são as rotas
`caso-para-juntar` (a sugestão e o resumo) e `juntada`, no fim deste arquivo.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from httpx import HTTPError
from postgrest.exceptions import APIError
from pydantic import BaseModel

from app.config import settings
from app.dependencies import get_supabase_client
from app.limiter import limiter
from app.routers.ouvidoria import (
    EXPIRACAO_URL_ANEXO_SEGUNDOS,
    barrar_caso_apagado,
    require_perfil_ouvidoria,
)
from app.services import ouvidoria_triagem_email as triagem
from app.services import storage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ouvidoria/triagem-email", tags=["ouvidoria-triagem-email"])


@router.get("")
@limiter.limit("60/minute")
async def listar_emails_recebidos(
    request: Request,
    me: dict = Depends(require_perfil_ouvidoria),
    supabase=Depends(get_supabase_client),
):
    """Os e-mails recebidos, pendentes primeiro, na ordem de chegada. Só o
    cabeçalho: o corpo sai quando o ouvidor abre o item."""
    return {"emails": triagem.listar(supabase)}


@router.get("/{email_id}")
@limiter.limit("60/minute")
async def ver_email_recebido(
    request: Request,
    email_id: str,
    me: dict = Depends(require_perfil_ouvidoria),
    supabase=Depends(get_supabase_client),
):
    """O item aberto: cabeçalho, corpo em texto e anexos. O HTML do e-mail fica
    guardado e não sai daqui (a tela desenha só o texto)."""
    item = triagem.carregar_item(supabase, email_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="E-mail não encontrado")
    triagem.registrar_acesso_ao_email(supabase, me, email_id, "ver_email_recebido")
    return item


@router.get("/{email_id}/pre-carga")
@limiter.limit("60/minute")
async def pre_carga_da_manifestacao(
    request: Request,
    email_id: str,
    me: dict = Depends(require_perfil_ouvidoria),
    supabase=Depends(get_supabase_client),
):
    """Os valores com que o modal "Nova manifestação" abre quando o e-mail vira
    manifestação (issue #650, ADR 0051 decisão 2). Quem cria o caso continua
    sendo o registro manual, com o `email_recebido_id` desta resposta."""
    item = triagem.carregar_item(supabase, email_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="E-mail não encontrado")
    if item["estado"] != triagem.PENDENTE:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=triagem.RECUSA_JA_DECIDIDO)
    triagem.registrar_acesso_ao_email(supabase, me, email_id, "pre_carga_manifestacao")
    return triagem.pre_carga(item)


@router.get("/{email_id}/anexos/{anexo_id}/url")
@limiter.limit("60/minute")
async def abrir_anexo_do_email(
    request: Request,
    email_id: str,
    anexo_id: str,
    me: dict = Depends(require_perfil_ouvidoria),
    supabase=Depends(get_supabase_client),
):
    """URL assinada, com expiração, para abrir o anexo do e-mail. O bucket é o
    privado da Ouvidoria: caminho público não existe."""
    anexo = triagem.caminho_do_anexo(supabase, email_id, anexo_id)
    if anexo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Anexo não encontrado")
    url = storage.signed_url(
        supabase,
        bucket=settings.supabase_storage_bucket_anexos_ouvidoria,
        path=anexo["storage_path"],
        expires_in=EXPIRACAO_URL_ANEXO_SEGUNDOS,
    )
    if url is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Não foi possível abrir o anexo agora. Tente de novo em instantes.",
        )
    triagem.registrar_acesso_ao_email(supabase, me, email_id, "abrir_anexo_email")
    return {"url": url, "filename": anexo["filename"], "expira_em_segundos": EXPIRACAO_URL_ANEXO_SEGUNDOS}


@router.post("/{email_id}/descarte")
@limiter.limit("60/minute")
async def descartar_email_recebido(
    request: Request,
    email_id: str,
    me: dict = Depends(require_perfil_ouvidoria),
    supabase=Depends(get_supabase_client),
):
    """Descarta o item: fica só o cabeçalho e quem descartou (issue #649, ADR
    0051 decisão 5). Sem motivo obrigatório, e idempotente."""
    try:
        desfecho = triagem.descartar(supabase, me, email_id, datetime.now(UTC))
    except (HTTPError, APIError, OSError) as exc:
        # Banco que não responde é "tente de novo", e não erro de servidor: a
        # mesma régua do registro manual (#650). O descarte é idempotente, e a
        # nova tentativa completa o que tiver ficado pela metade. Só o tipo vai
        # para o log: o `details` do `APIError` traz a linha, com o corpo.
        logger.warning("Falha ao descartar o e-mail recebido %s (%s)", email_id, type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Não foi possível descartar o e-mail agora. Tente de novo em instantes.",
        ) from None
    if desfecho == triagem.DESCARTE_SEM_ITEM:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="E-mail não encontrado")
    if desfecho == triagem.DESCARTE_RECUSADO:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Este e-mail já virou manifestação ou foi juntado a um caso, e não pode ser descartado",
        )
    triagem.registrar_acesso_ao_email(supabase, me, email_id, "descartar_email")
    if desfecho == triagem.DESCARTE_INCOMPLETO:
        # O item já está descartado e sem corpo, mas algum binário não saiu do
        # storage. 200 diria ao ouvidor que o anexo foi apagado; o descarte é
        # idempotente, e a nova tentativa termina o serviço.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="O e-mail foi descartado, mas algum anexo não saiu do armazenamento. Tente de novo em instantes.",
        )
    return triagem.carregar_item(supabase, email_id)


@router.get("/{email_id}/caso-para-juntar")
@limiter.limit("60/minute")
async def caso_para_juntar(
    request: Request,
    email_id: str,
    protocolo: str | None = None,
    me: dict = Depends(require_perfil_ouvidoria),
    supabase=Depends(get_supabase_client),
):
    """O caso a que o e-mail pode ser juntado, em resumo (protocolo, estado e
    setor). Sem `protocolo`, a sugestão tirada do assunto e do começo do corpo;
    com ele, o caso que o ouvidor digitou. `caso: null` quando não há."""
    item = triagem.carregar_item(supabase, email_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="E-mail não encontrado")
    try:
        caso = (
            triagem.resumo_do_caso(supabase, protocolo)
            if protocolo is not None
            else triagem.sugerir_caso(supabase, item)
        )
    except triagem.CasoArquivadoError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=triagem.recusa_de_caso_arquivado(exc.protocolo)
        ) from None
    except (HTTPError, APIError, OSError) as exc:
        logger.warning("Falha ao procurar o caso do e-mail recebido %s (%s)", email_id, type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Não foi possível procurar o caso agora. Tente de novo em instantes.",
        ) from None
    triagem.registrar_acesso_ao_email(
        supabase, me, email_id, "procurar_caso_para_juntar", manifestacao_id=caso["id"] if caso else None
    )
    return {"caso": caso}


class PedidoDeJuntada(BaseModel):
    """O caso a que o e-mail vai ser juntado: o id, que a tela tira do resumo
    que o ouvidor conferiu."""

    manifestacao_id: str


# O que a juntada lê do caso: o estado, para o movimento, e os carimbos que a
# guarda do caso apagado confere (`barrar_caso_apagado`).
_CAMPOS_DO_CASO_DA_JUNTADA = "id, protocolo, status, setor, anonimizada_em, apagamento_pedido_em, arquivada_em"


def _carregar_caso(supabase, manifestacao_id: str) -> dict | None:
    try:
        resultado = (
            supabase.table("ouvidoria_protocolos")
            .select(_CAMPOS_DO_CASO_DA_JUNTADA)
            .eq("id", manifestacao_id)
            .execute()
        )
    except APIError as exc:
        # Id que não é UUID (22P02) é caso que não existe; o resto é o banco.
        if getattr(exc, "code", None) == "22P02":
            return None
        raise
    return resultado.data[0] if resultado.data else None


@router.post("/{email_id}/juntada")
@limiter.limit("30/minute")
async def juntar_a_caso(
    request: Request,
    email_id: str,
    pedido: PedidoDeJuntada,
    me: dict = Depends(require_perfil_ouvidoria),
    supabase=Depends(get_supabase_client),
):
    """Junta o e-mail a um caso que já existe (issue #651, ADR 0051 decisão 4):
    o texto vira Movimento do caso e os anexos passam a ele, sem mudar estado,
    prazo nem T1."""
    try:
        estado = triagem.estado_do_email(supabase, email_id)
        caso = _carregar_caso(supabase, pedido.manifestacao_id)
        if estado is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="E-mail não encontrado")
        if estado != triagem.PENDENTE:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Este e-mail já foi decidido na triagem e não pode ser juntado a um caso",
            )
        if caso is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Manifestação não encontrada")
        # O caso cujo relato a retenção apagou não recebe texto novo: o que
        # voltar a ser trazido entra como manifestação nova (ADR 0047).
        barrar_caso_apagado(caso, "completado com um e-mail")
        # O caso arquivado está fora da fila e do contador de novidade: o
        # e-mail juntado a ele sumiria sem ninguém ver. Desarquivar é ato
        # explícito do ouvidor, no Dossiê.
        if caso.get("arquivada_em"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=triagem.recusa_de_caso_arquivado(caso.get("protocolo") or ""),
            )
        desfecho = triagem.juntar(supabase, me, email_id, caso, datetime.now(UTC))
    except (HTTPError, APIError, OSError) as exc:
        logger.warning("Falha ao juntar o e-mail recebido %s (%s)", email_id, type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Não foi possível juntar o e-mail agora. Tente de novo em instantes.",
        ) from None
    if desfecho == triagem.JUNTADA_RECUSADA:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Este e-mail já foi decidido na triagem e não pode ser juntado a um caso",
        )
    if desfecho == triagem.JUNTADA_FALHOU:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Não foi possível juntar o e-mail agora. Tente de novo em instantes.",
        )
    triagem.registrar_acesso_ao_email(supabase, me, email_id, "juntar_email", manifestacao_id=caso["id"])
    return triagem.carregar_item(supabase, email_id)
