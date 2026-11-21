"""As Rotinas e as Verificações (ADR 0098, decisão 9; issue #1874).

Quem vê e quem age sai do vínculo, como na Pendência (decisão 7): o
responsável marca os ciclos dele; o Facilitador da Reunião vê, marca pelo
responsável (quem não entra no app) e encerra; o Super admin vê e faz tudo,
fora das Reuniões do Núcleo que ele não alcança. Fora do vínculo, 404.

Realizada é um clique (a mesma rota do botão da Minha Fila); Não realizada e
o encerramento pedem anotação.
"""

from __future__ import annotations

import logging
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.dependencies import (
    get_current_user,
    get_participante_for_user,
    get_supabase_client,
    is_secretaria,
    is_super_admin,
    require_acesso_reunioes,
    reunioes_ocultas,
)
from app.services import rotina_service
from app.services.rotina_ciclo import NAO_REALIZADA, REALIZADA, VerificacaoRecusada

router = APIRouter(
    prefix="/rotinas",
    tags=["rotinas"],
    # Gate de contexto (ADR 0007): sem papel nas Reuniões -> 403 em todo o router.
    dependencies=[Depends(require_acesso_reunioes)],
)
logger = logging.getLogger(__name__)

RESPONSAVEL = "responsavel"
FACILITADOR = "facilitador"
SUPER_ADMIN = "super_admin"


class AnotacaoRequest(BaseModel):
    # O mesmo teto da anotação da Pendência (AcaoPendenciaRequest).
    anotacao: str | None = Field(default=None, max_length=5000)


class FrequenciaRequest(BaseModel):
    frequencia: str = Field(max_length=20)


class CicloEmAberto(BaseModel):
    inicio: date
    fim: date
    atrasado: bool


class VerificacaoResponse(BaseModel):
    ciclo_inicio: date
    ciclo_fim: date
    resultado: str
    anotacao: str | None = None
    atrasada: bool
    marcada_por_nome: str


class RotinaResponse(BaseModel):
    id: str
    id_reuniao: str
    reuniao_titulo: str | None = None
    descricao: str
    responsavel_id: str | None = None
    responsavel_nome: str
    frequencia: str | None = None
    comeca_em: date | None = None
    status: str
    encerrada_em: date | None = None
    anotacao_encerramento: str | None = None
    ciclos_em_aberto: list[CicloEmAberto]
    verificacoes: list[VerificacaoResponse]
    pode_marcar: bool
    pode_encerrar: bool
    # A Rotina que veio do fluxo contínuo espera o Facilitador (issue #1877).
    pode_escolher_frequencia: bool = False


async def _quem_pede(current_user: dict, supabase) -> dict | None:
    me = await get_participante_for_user(current_user, supabase)
    if is_secretaria(me):
        raise HTTPException(status_code=403, detail="Secretária não tem acesso a Rotinas")
    return me


def _reunioes(supabase, ids: list[str]) -> dict[str, dict]:
    if not ids:
        return {}
    linhas = (
        supabase.table("reunioes").select("id_reuniao, titulo, facilitador_id").in_("id_reuniao", ids).execute().data
    )
    return {r["id_reuniao"]: r for r in linhas or []}


def _papeis(rotina: dict, reuniao: dict | None, me: dict | None) -> set[str]:
    papeis: set[str] = set()
    if is_super_admin(me):
        papeis.add(SUPER_ADMIN)
    meu_id = (me or {}).get("id")
    if meu_id is not None:
        if rotina.get("responsavel_id") == meu_id:
            papeis.add(RESPONSAVEL)
        if reuniao and reuniao.get("facilitador_id") == meu_id:
            papeis.add(FACILITADOR)
    return papeis


def _autor(me: dict | None, current_user: dict) -> dict:
    return {
        "autor_id": (me or {}).get("id"),
        "autor_nome": (me or {}).get("nome_completo") or current_user.get("email") or "Sem nome",
    }


async def _rotina_e_papeis(id_rotina: UUID, current_user: dict, supabase) -> tuple[dict, dict | None, set[str]]:
    """A Rotina que quem pede alcança e os papéis dele nela. O Núcleo oculto e
    quem está fora do vínculo recebem 404, sem dizer que ela existe."""
    me = await _quem_pede(current_user, supabase)
    linhas = supabase.table("rotinas").select("*").eq("id", str(id_rotina)).execute().data
    if not linhas or linhas[0]["id_reuniao"] in set(reunioes_ocultas(supabase, me)):
        raise HTTPException(status_code=404, detail="Rotina não encontrada")
    rotina = linhas[0]
    papeis = _papeis(rotina, _reunioes(supabase, [rotina["id_reuniao"]]).get(rotina["id_reuniao"]), me)
    if not papeis:
        raise HTTPException(status_code=404, detail="Rotina não encontrada")
    return rotina, me, papeis


def _visiveis(supabase, me: dict | None) -> list[dict]:
    if not me:
        return []
    if is_super_admin(me):
        return supabase.table("rotinas").select("*").execute().data or []
    linhas = {
        r["id"]: r for r in supabase.table("rotinas").select("*").eq("responsavel_id", me["id"]).execute().data or []
    }
    facilitadas = [
        r["id_reuniao"]
        for r in supabase.table("reunioes").select("id_reuniao").eq("facilitador_id", me["id"]).execute().data or []
    ]
    if facilitadas:
        for r in supabase.table("rotinas").select("*").in_("id_reuniao", facilitadas).execute().data or []:
            linhas.setdefault(r["id"], r)
    return list(linhas.values())


@router.get("", response_model=list[RotinaResponse])
async def listar_rotinas(
    current_user: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    """As Rotinas de quem pede, com os ciclos em aberto e as Verificações."""
    me = await _quem_pede(current_user, supabase)
    ocultas = set(reunioes_ocultas(supabase, me))
    rotinas = [r for r in _visiveis(supabase, me) if r["id_reuniao"] not in ocultas]
    reunioes = _reunioes(supabase, sorted({r["id_reuniao"] for r in rotinas}))
    marcadas = rotina_service.verificacoes_de(supabase, [r["id"] for r in rotinas])
    hoje = rotina_service.hoje_em_brasilia()
    saida = []
    for rotina in rotinas:
        reuniao = reunioes.get(rotina["id_reuniao"])
        papeis = _papeis(rotina, reuniao, me)
        feitas = sorted(marcadas.get(rotina["id"], []), key=lambda v: str(v["ciclo_inicio"]), reverse=True)
        saida.append(
            {
                **rotina,
                "reuniao_titulo": (reuniao or {}).get("titulo"),
                "ciclos_em_aberto": [
                    {"inicio": c.inicio, "fim": c.fim, "atrasado": c.fim < hoje}
                    for c in rotina_service.ciclos_em_aberto(rotina, feitas, hoje)
                ],
                "verificacoes": feitas,
                "pode_marcar": bool(papeis),
                "pode_encerrar": rotina.get("status") == rotina_service.ATIVA
                and bool(papeis & {FACILITADOR, SUPER_ADMIN}),
                "pode_escolher_frequencia": rotina.get("status") == rotina_service.ATIVA
                and not rotina.get("frequencia")
                and bool(papeis & {FACILITADOR, SUPER_ADMIN}),
            }
        )
    saida.sort(key=lambda r: (r["status"] != rotina_service.ATIVA, r["descricao"].lower()))
    return saida


def _marcar(rotina: dict, inicio: date, resultado: str, anotacao: str | None, autor: dict, supabase) -> dict:
    try:
        return rotina_service.marcar(supabase, rotina, inicio, resultado, anotacao, **autor)
    except (VerificacaoRecusada, rotina_service.CicloInexistente) as recusa:
        raise HTTPException(status_code=422, detail=str(recusa)) from recusa
    except rotina_service.JaMarcada as recusa:
        raise HTTPException(status_code=409, detail=str(recusa)) from recusa


@router.post("/{id_rotina}/ciclos/{inicio}/realizada", status_code=201, response_model=VerificacaoResponse)
async def marcar_realizada(
    id_rotina: UUID,
    inicio: date,
    current_user: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    """Realizada é um clique, sem anotação."""
    rotina, me, _ = await _rotina_e_papeis(id_rotina, current_user, supabase)
    return _marcar(rotina, inicio, REALIZADA, None, _autor(me, current_user), supabase)


@router.post("/{id_rotina}/ciclos/{inicio}/nao-realizada", status_code=201, response_model=VerificacaoResponse)
async def marcar_nao_realizada(
    id_rotina: UUID,
    inicio: date,
    body: AnotacaoRequest,
    current_user: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    """Não realizada pede anotação."""
    rotina, me, _ = await _rotina_e_papeis(id_rotina, current_user, supabase)
    return _marcar(rotina, inicio, NAO_REALIZADA, body.anotacao, _autor(me, current_user), supabase)


@router.post("/{id_rotina}/manter")
async def manter_rotina(
    id_rotina: UUID,
    current_user: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    """A revisão de 90 dias (issue #1944): o Facilitador (ou o Super admin)
    mantém a Rotina com um clique. Encerrar continua pedindo anotação."""
    rotina, me, papeis = await _rotina_e_papeis(id_rotina, current_user, supabase)
    if not papeis & {FACILITADOR, SUPER_ADMIN}:
        raise HTTPException(status_code=403, detail="Só o Facilitador da Reunião revisa a Rotina")
    try:
        mantida = rotina_service.manter(supabase, rotina, **_autor(me, current_user))
    except rotina_service.JaEncerrada as recusa:
        raise HTTPException(status_code=409, detail=str(recusa)) from recusa
    return {"id": mantida.get("id", str(id_rotina)), "revisada_em": mantida.get("revisada_em")}


@router.post("/{id_rotina}/encerrar")
async def encerrar_rotina(
    id_rotina: UUID,
    body: AnotacaoRequest,
    current_user: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    """O Facilitador (ou o Super admin) encerra a qualquer momento, com anotação."""
    rotina, me, papeis = await _rotina_e_papeis(id_rotina, current_user, supabase)
    if not papeis & {FACILITADOR, SUPER_ADMIN}:
        raise HTTPException(status_code=403, detail="Só o Facilitador da Reunião encerra a Rotina")
    try:
        encerrada = rotina_service.encerrar(supabase, rotina, body.anotacao, **_autor(me, current_user))
    except VerificacaoRecusada as recusa:
        raise HTTPException(status_code=422, detail=str(recusa)) from recusa
    except rotina_service.JaEncerrada as recusa:
        raise HTTPException(status_code=409, detail=str(recusa)) from recusa
    logger.info("[Rotina] %s encerrada por %s", id_rotina, (me or {}).get("id"))
    return {"id": encerrada.get("id", str(id_rotina)), "status": encerrada.get("status")}


@router.post("/{id_rotina}/frequencia")
async def escolher_frequencia(
    id_rotina: UUID,
    body: FrequenciaRequest,
    current_user: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    """O Facilitador (ou o Super admin) escolhe a frequência da Rotina que veio
    do fluxo contínuo (issue #1877). Até lá, ela não tem ciclo."""
    rotina, me, papeis = await _rotina_e_papeis(id_rotina, current_user, supabase)
    if not papeis & {FACILITADOR, SUPER_ADMIN}:
        raise HTTPException(status_code=403, detail="Só o Facilitador da Reunião escolhe a frequência da Rotina")
    try:
        gravada = rotina_service.escolher_frequencia(supabase, rotina, body.frequencia)
    except VerificacaoRecusada as recusa:
        raise HTTPException(status_code=422, detail=str(recusa)) from recusa
    except rotina_service.JaTemFrequencia as recusa:
        raise HTTPException(status_code=409, detail=str(recusa)) from recusa
    logger.info("[Rotina] %s ganhou frequência %s por %s", id_rotina, body.frequencia, (me or {}).get("id"))
    return {
        "id": gravada.get("id", str(id_rotina)),
        "frequencia": gravada.get("frequencia"),
        "comeca_em": gravada.get("comeca_em"),
    }
