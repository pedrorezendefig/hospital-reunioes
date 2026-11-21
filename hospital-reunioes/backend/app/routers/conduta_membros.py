"""Canal de Conduta, a tela Membros do Comitê (issue #1822, PRD #1786, ADR 0097).

"Quem compõe o Comitê e até quando." Lê quem está no Comitê hoje e quem tem
o perfil de cadastro (`portao_dos_membros`); inclui e encerra só quem tem o
perfil (`portao_do_cadastro`). O super admin sem o perfil recebe 403.

Nada se apaga: encerrar termina a vigência no dia e a linha fica, para a
composição de qualquer data passada. Não existe rota DELETE, e o banco recusa
apagar Participação (migration 150). Toda inclusão e saída grava o registro
do módulo e avisa os membros vigentes (`membros.mudanca_no_comite`).

Incluir gera o Termo de Confidencialidade e Posse e o envia à ClickSign
(issue #1823, `assinaturas`). Falha no Termo não desfaz a inclusão: vira
`aviso_termo` na resposta, e a linha tem o reenvio e o "Reconsultar status".
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
from supabase import Client

from app.dependencies import get_supabase_client
from app.limiter import limiter
from app.services.conduta import assinaturas, membros
from app.services.conduta.acesso import hoje_em_sao_paulo
from app.services.conduta.portao import portao_do_cadastro, portao_dos_membros

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/comite-de-conduta/membros", tags=["canal-de-conduta"])

Cadeira = Literal["coordenacao", "segundo_leitor", "membro", "suplente"]


class MembroNovo(BaseModel):
    participante_id: str = Field(min_length=1, max_length=10)
    papel: Cadeira
    e_diretor: bool = False
    vigencia_inicio: date
    # Sem fim, o mandato de dois anos.
    vigencia_fim: date | None = None


class Encerramento(BaseModel):
    # Sem data, encerra hoje.
    data: date | None = None


def _comite_id(supabase) -> str:
    comite_id = membros.id_do_comite(supabase)
    if not comite_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="O Comitê ainda não foi criado")
    return comite_id


@router.get("")
@limiter.limit("60/minute")
async def listar_membros(
    request: Request,
    data: date | None = Query(default=None, description="Sem data, todas; com data, quem valia naquele dia."),
    me: dict = Depends(portao_dos_membros),
    supabase: Client = Depends(get_supabase_client),
) -> dict:
    lista = membros.participacoes(supabase, _comite_id(supabase))
    if data is not None:
        lista = [p for p in lista if membros.vigente_em(p, data)]
    return {
        "data": data.isoformat() if data else None,
        "pode_cadastrar": me["pode_cadastrar"],
        "membros": membros.linhas_da_tela(supabase, lista, hoje_em_sao_paulo()),
    }


@router.get("/registro")
@limiter.limit("60/minute")
async def registro_do_comite(
    request: Request,
    _: dict = Depends(portao_dos_membros),
    supabase: Client = Depends(get_supabase_client),
) -> dict:
    """Quem entrou, saiu, ganhou ou perdeu o perfil de cadastro, por quem e quando."""
    return {"registro": membros.registro(supabase)}


@router.get("/pessoas")
@limiter.limit("60/minute")
async def pessoas_para_o_cadastro(
    request: Request,
    _: dict = Depends(portao_do_cadastro),
    supabase: Client = Depends(get_supabase_client),
) -> dict:
    """As pessoas ativas do cadastro, só id e nome."""
    linhas = (
        supabase.table("participantes")
        .select("id, nome_completo")
        .eq("ativo", True)
        .order("nome_completo")
        .execute()
        .data
    ) or []
    return {"pessoas": [{"id": x["id"], "nome": x["nome_completo"]} for x in linhas]}


@router.post("", status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
async def incluir_membro(
    request: Request,
    body: MembroNovo,
    tarefas: BackgroundTasks,
    me: dict = Depends(portao_do_cadastro),
    supabase: Client = Depends(get_supabase_client),
) -> dict:
    comite_id = _comite_id(supabase)
    fim = body.vigencia_fim or membros.fim_do_mandato(body.vigencia_inicio)
    if fim < body.vigencia_inicio:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="O fim da vigência não pode ser antes do início",
        )
    nome = membros.nomes(supabase, [body.participante_id]).get(body.participante_id)
    if nome is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pessoa não encontrada no cadastro")
    abertas = (
        supabase.table("participacoes")
        .select("id")
        .eq("colegiado_id", comite_id)
        .eq("participante_id", body.participante_id)
        .is_("encerrada_em", "null")
        .execute()
        .data
    ) or []
    if abertas:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Esta pessoa já tem uma participação aberta no Comitê. Encerre a atual antes.",
        )
    nova = (
        supabase.table("participacoes")
        .insert(
            {
                "colegiado_id": comite_id,
                "participante_id": body.participante_id,
                "papel": body.papel,
                "e_diretor": body.e_diretor,
                "vigencia_inicio": body.vigencia_inicio.isoformat(),
                "vigencia_fim": fim.isoformat(),
            }
        )
        .execute()
        .data
    )[0]
    hoje = hoje_em_sao_paulo()
    cadeira = membros.CADEIRAS[body.papel]
    avisados = membros.mudanca_no_comite(
        supabase,
        acao="inclusao",
        participante_id=body.participante_id,
        participacao_id=nova["id"],
        autor_id=me["id"],
        detalhe=f"{cadeira}, de {membros.data_br(body.vigencia_inicio)} a {membros.data_br(fim)}",
        mensagem=(
            f"{nome} entrou no Comitê como {cadeira}, "
            f"de {membros.data_br(body.vigencia_inicio)} a {membros.data_br(fim)}."
        ),
        hoje=hoje,
    )
    tarefas.add_task(membros.enviar_emails, supabase, avisados)
    aviso = await run_in_threadpool(_enviar_termo, assinaturas.enviar_termo_de_posse, supabase, nova)
    linha = membros.linhas_da_tela(supabase, [membros.participacao(supabase, comite_id, nova["id"])], hoje)[0]
    return {**linha, "aviso_termo": aviso}


def _enviar_termo(enviar, supabase, participacao: dict) -> str | None:
    """Gera e envia o Termo. A inclusão já está gravada: a falha vira aviso."""
    try:
        return enviar(supabase, participacao).get("erro")
    except assinaturas.TermoNaoGeradoError as erro:
        return str(erro)
    except Exception:  # noqa: BLE001 (a inclusão não se desfaz por falha do Termo)
        logger.exception("Termo de Confidencialidade e Posse da Participação %s não gerado", participacao.get("id"))
        return "O Termo não foi gerado agora. Use Reenviar o Termo na linha do membro."


def _participacao_aberta(supabase, participacao_id: str) -> tuple[str, dict]:
    comite_id = _comite_id(supabase)
    atual = membros.participacao(supabase, comite_id, participacao_id)
    if not atual:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Participação não encontrada")
    return comite_id, atual


@router.post("/{participacao_id}/termo/reconsultar")
@limiter.limit("30/minute")
async def reconsultar_termo(
    request: Request,
    participacao_id: str,
    _: dict = Depends(portao_do_cadastro),
    supabase: Client = Depends(get_supabase_client),
) -> dict:
    """Pergunta à ClickSign e aplica o mesmo tratamento do webhook."""
    comite_id, _ = _participacao_aberta(supabase, participacao_id)
    ultima = assinaturas.ultima_do_membro(supabase, participacao_id)
    if not ultima or not ultima.get("envelope_id"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Este membro ainda não tem Termo enviado. Use Reenviar o Termo.",
        )
    try:
        await run_in_threadpool(assinaturas.reconsultar, supabase, ultima)
    except assinaturas.AssinaturaIndisponivelError as erro:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="A assinatura eletrônica não respondeu. Tente de novo em instantes.",
        ) from erro
    hoje = hoje_em_sao_paulo()
    return membros.linhas_da_tela(supabase, [membros.participacao(supabase, comite_id, participacao_id)], hoje)[0]


@router.post("/{participacao_id}/termo/reenviar")
@limiter.limit("10/minute")
async def reenviar_termo(
    request: Request,
    participacao_id: str,
    _: dict = Depends(portao_do_cadastro),
    supabase: Client = Depends(get_supabase_client),
) -> dict:
    """Cancela o envio aberto e manda outro Termo, com outro identificador."""
    comite_id, atual = _participacao_aberta(supabase, participacao_id)
    if atual.get("termo_assinado_em"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Este membro já assinou o Termo")
    if atual.get("encerrada_em"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Esta participação já foi encerrada")
    aviso = await run_in_threadpool(_enviar_termo, assinaturas.reenviar_termo_de_posse, supabase, atual)
    hoje = hoje_em_sao_paulo()
    linha = membros.linhas_da_tela(supabase, [membros.participacao(supabase, comite_id, participacao_id)], hoje)[0]
    return {**linha, "aviso_termo": aviso}


@router.post("/{participacao_id}/encerrar")
@limiter.limit("30/minute")
async def encerrar_membro(
    request: Request,
    participacao_id: str,
    body: Encerramento,
    tarefas: BackgroundTasks,
    me: dict = Depends(portao_do_cadastro),
    supabase: Client = Depends(get_supabase_client),
) -> dict:
    """Encerra sem apagar: a vigência termina no dia (inclusive) e a linha
    fica para o histórico e para a composição das datas em que valia."""
    comite_id = _comite_id(supabase)
    atual = membros.participacao(supabase, comite_id, participacao_id)
    if not atual:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Participação não encontrada")
    if atual.get("encerrada_em"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Esta participação já foi encerrada")
    hoje = hoje_em_sao_paulo()
    dia = body.data or hoje
    inicio = str(atual["vigencia_inicio"])[:10]
    # Antes do início, encerrar desfaz a inclusão: a Participação que ainda
    # não começou nunca vale. O fim fica no início (o banco não deixa o fim
    # antes dele) e o `encerrada_em` antes do início tira o primeiro dia.
    desfeita = dia.isoformat() < inicio
    if desfeita and hoje.isoformat() >= inicio:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="O encerramento não pode ser antes do início da vigência",
        )
    novo_fim = inicio if desfeita else min(dia.isoformat(), str(atual["vigencia_fim"])[:10])
    supabase.table("participacoes").update({"encerrada_em": dia.isoformat(), "vigencia_fim": novo_fim}).eq(
        "id", participacao_id
    ).eq("colegiado_id", comite_id).execute()
    nome = membros.nomes(supabase, [atual["participante_id"]]).get(atual["participante_id"]) or "Um membro"
    cadeira = membros.CADEIRAS.get(atual["papel"], atual["papel"])
    avisados = membros.mudanca_no_comite(
        supabase,
        acao="encerramento",
        participante_id=atual["participante_id"],
        participacao_id=participacao_id,
        autor_id=me["id"],
        detalhe=(
            f"{cadeira}, inclusão desfeita em {membros.data_br(dia)}, antes do início em {membros.data_br(inicio)}"
            if desfeita
            else f"{cadeira}, encerrada em {membros.data_br(dia)}"
        ),
        mensagem=(
            f"{nome} não vai mais entrar no Comitê ({cadeira}). A inclusão foi desfeita antes do início."
            if desfeita
            else f"{nome} saiu do Comitê ({cadeira}) em {membros.data_br(dia)}."
        ),
        hoje=hoje,
    )
    tarefas.add_task(membros.enviar_emails, supabase, avisados)
    return membros.linhas_da_tela(supabase, [membros.participacao(supabase, comite_id, participacao_id)], hoje)[0]
