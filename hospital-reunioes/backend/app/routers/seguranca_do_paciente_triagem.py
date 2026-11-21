"""A tela de triagem do Núcleo (issue #1992, PRD #1979, ADR 0095 e 0107).

- `GET /nsp/triagem`: a fila, da mais antiga para a mais nova;
- `GET /nsp/triagem/{id}`: a tela de um caso, com a sugestão e o que o
  sistema calcula;
- `GET /nsp/triagem/{id}/contexto`: o cálculo de novo, para a categoria e a
  faixa que a pessoa escolheu ao ajustar;
- `POST /nsp/triagem/{id}`: confirmar (sem classificação, vale a sugestão) ou
  ajustar (com a classificação da pessoa);
- `GET` e `PUT /nsp/configuracao/cortes-de-frequencia`: os cortes da matriz
  de prioridade, na Configuração do módulo.

A triagem é da Presidência e do Acesso pleno (o recurso `triagem`); os cortes,
de quem alcança a configuração.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from postgrest.exceptions import APIError
from pydantic import BaseModel, Field
from supabase import Client

from app.dependencies import get_supabase_client, require_recurso_nsp
from app.services import limite_sem_ip, ouvidoria_nucleo
from app.services.seguranca_do_paciente import anexos, notificacoes, triagem

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/nsp", tags=["seguranca-do-paciente"])

FALHA_DE_LEITURA = "Não foi possível abrir a triagem agora. Tente de novo em instantes."
FALHA_DE_GRAVACAO = "Não foi possível gravar a triagem agora. Tente de novo em instantes."


def _indisponivel(erro: Exception, mensagem: str) -> HTTPException:
    logger.error("Falha na triagem do Núcleo: %s", type(erro).__name__)
    return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=mensagem)


@router.get("/triagem")
@limite_sem_ip.limitar("60/minute")
async def fila_de_triagem(
    request: Request,
    _: dict = Depends(require_recurso_nsp("triagem")),
    supabase: Client = Depends(get_supabase_client),
) -> dict:
    """A fila de triagem: sem relato e sem quem notificou."""
    try:
        return {"fila": triagem.fila(supabase)}
    except (APIError, httpx.HTTPError) as erro:
        raise _indisponivel(erro, FALHA_DE_LEITURA) from erro


@router.get("/triagem/{notificacao_id}")
@limite_sem_ip.limitar("60/minute")
async def tela_de_triagem(
    request: Request,
    notificacao_id: UUID,
    me: dict = Depends(require_recurso_nsp("triagem")),
    supabase: Client = Depends(get_supabase_client),
) -> dict:
    """A tela única: o caso, com os anexos, a sugestão (ou nenhuma) e o que o
    sistema calcula. Abrir a triagem do caso que veio da Ouvidoria marca o
    Recebido do Núcleo lá (ADR 0107, decisão 7)."""
    com_identidade = "identidade_notificante" in me["recursos_nsp"]
    try:
        tela = triagem.abrir(supabase, str(notificacao_id), com_identidade=com_identidade)
        if tela is not None:
            tela["caso"]["anexos"] = anexos.anexos_dos_casos(supabase, [str(notificacao_id)]).get(
                str(notificacao_id), []
            )
    except (APIError, httpx.HTTPError) as erro:
        raise _indisponivel(erro, FALHA_DE_LEITURA) from erro
    if tela is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Caso não encontrado.")
    if tela["caso"].get("origem") == notificacoes.ORIGEM_OUVIDORIA:
        _marcar_o_recebido_na_ouvidoria(supabase, str(notificacao_id), me)
    return tela


@router.get("/triagem/{notificacao_id}/contexto")
@limite_sem_ip.limitar("120/minute")
async def contexto_da_triagem(
    request: Request,
    notificacao_id: UUID,
    categoria: str | None = None,
    faixa: str | None = None,
    _: dict = Depends(require_recurso_nsp("triagem")),
    supabase: Client = Depends(get_supabase_client),
) -> dict:
    """A recorrência, os casos parecidos, a frequência e a prioridade para a
    categoria e a faixa que a pessoa escolheu ao ajustar."""
    try:
        calculo = triagem.contexto_do_caso(supabase, str(notificacao_id), categoria, faixa)
    except (APIError, httpx.HTTPError) as erro:
        raise _indisponivel(erro, FALHA_DE_LEITURA) from erro
    if calculo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Caso não encontrado.")
    return calculo


class Classificacao(BaseModel):
    """A classificação da pessoa. Quem confere as regras é o serviço, com as
    mesmas listas do agente; a faixa sai do cálculo, e não daqui."""

    assunto: str | None = Field(default=None, max_length=1000)
    natureza: str | None = None
    grau_de_dano: str | None = None
    categoria: str | None = None
    incidente: str | None = Field(default=None, max_length=1000)
    evento_situacao: str | None = None
    evento_item: int | None = None
    evento_motivo: str | None = Field(default=None, max_length=2000)
    iras: bool | None = None
    risco_de_imagem: bool | None = None
    protocolo_basico: str | None = None
    canais: list[str] = Field(default_factory=list, max_length=6)
    motivo_do_encaminhamento: str | None = Field(default=None, max_length=2000)


class Decisao(BaseModel):
    """Sem `classificacao`, confirma a sugestão como veio; com ela, ajusta.
    `conferidos` são os campos que a pessoa marcou na revisão campo a campo."""

    classificacao: Classificacao | None = None
    conferidos: list[str] = Field(default_factory=list, max_length=len(triagem.CAMPOS_DA_CONFERENCIA))


@router.post("/triagem/{notificacao_id}", status_code=status.HTTP_201_CREATED)
@limite_sem_ip.limitar("60/minute")
async def decidir_a_triagem(
    request: Request,
    notificacao_id: UUID,
    decisao: Decisao,
    me: dict = Depends(require_recurso_nsp("triagem")),
    supabase: Client = Depends(get_supabase_client),
) -> dict:
    """Confirmar ou ajustar. Grava a linha da pessoa ao lado da sugestão e leva
    o caso a Classificada, ou a Em análise agregada na faixa E e na D sem dano."""
    try:
        return triagem.decidir(
            supabase,
            str(notificacao_id),
            autor_id=str(me["id"]),
            classificacao=decisao.classificacao.model_dump() if decisao.classificacao else None,
            conferidos=decisao.conferidos,
        )
    except triagem.CasoNaoEncontradoError as erro:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(erro)) from erro
    except triagem.JaConfirmadaError as erro:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(erro)) from erro
    except triagem.TriagemRecusadaError as erro:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(erro)) from erro
    except (APIError, httpx.HTTPError) as erro:
        raise _indisponivel(erro, FALHA_DE_GRAVACAO) from erro


class CortesDeFrequencia(BaseModel):
    """Quantas ocorrências anteriores da mesma categoria no mesmo setor, na
    janela, fazem cada frequência da matriz de prioridade."""

    janela_meses: int = Field(..., ge=0, le=600)
    incomum_a_partir: int = Field(..., ge=0, le=1000)
    ocasional_a_partir: int = Field(..., ge=0, le=1000)
    frequente_a_partir: int = Field(..., ge=0, le=1000)


@router.get("/configuracao/cortes-de-frequencia")
@limite_sem_ip.limitar("60/minute")
async def ler_cortes_de_frequencia(
    request: Request,
    _: dict = Depends(require_recurso_nsp("configuracao")),
    supabase: Client = Depends(get_supabase_client),
) -> dict:
    try:
        return triagem.cortes_de_frequencia(supabase)
    except httpx.HTTPError as erro:
        raise _indisponivel(erro, FALHA_DE_LEITURA) from erro


@router.put("/configuracao/cortes-de-frequencia")
@limite_sem_ip.limitar("30/minute")
async def gravar_cortes_de_frequencia(
    request: Request,
    cortes: CortesDeFrequencia,
    me: dict = Depends(require_recurso_nsp("configuracao")),
    supabase: Client = Depends(get_supabase_client),
) -> dict:
    """Os cortes novos valem para o que for calculado daqui para a frente."""
    try:
        return triagem.salvar_cortes_de_frequencia(supabase, cortes.model_dump(), autor_id=str(me["id"]))
    except triagem.ClassificacaoInvalidaError as erro:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(erro)) from erro
    except (APIError, httpx.HTTPError) as erro:
        raise _indisponivel(erro, "Não foi possível gravar os cortes agora. Tente de novo em instantes.") from erro


def agora_utc() -> datetime:
    return datetime.now(UTC)


def _marcar_o_recebido_na_ouvidoria(supabase, caso_id: str, me: dict) -> None:
    """Melhor esforço, como na tela do caso: o Recebido que não gravou volta
    no próximo abrir."""
    try:
        manifestacao_id = notificacoes.manifestacao_do_caso(supabase, caso_id)
        if manifestacao_id:
            ouvidoria_nucleo.receber_pelo_modulo(supabase, manifestacao_id, me, agora_utc())
    except (APIError, httpx.HTTPError) as erro:
        logger.error("Falha ao marcar o Recebido do Núcleo na Ouvidoria: %s", type(erro).__name__)
