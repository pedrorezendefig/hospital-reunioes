"""O portão único do lado do Comitê do Canal de Conduta (ADR 0097, decisão 4).

Toda rota do Comitê depende de `portao_da_lista`, de `portao_do_caso`, de
`portao_da_acao`, na tela inicial, de `portao_da_tela_inicial` ou, nas
configurações do módulo, de `portao_da_coordenacao`, e
`tests/test_conduta_varredura.py` reprova a rota do módulo que não dependa.
A tela Membros, que não mostra caso, tem os dois portões dela:
`portao_dos_membros` (ler) e `portao_do_cadastro` (incluir e encerrar).

Na ordem: a chave de cifra (sem ela, 503 e nada é lido nem gravado), a pessoa
logada e não desligada, a designação dela (`acesso`) e, no caso, a leitura
gravada na trilha antes de o caso sair. Se a trilha não grava, o caso não sai.

Toda recusa é a mesma recusa, com o mesmo texto: caso que não existe e caso
fechado para a pessoa não se distinguem. O super admin não passa por cima.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

import httpx
from fastapi import Depends, HTTPException, status
from postgrest.exceptions import APIError
from supabase import Client

from app.dependencies import barrar_desligado, get_current_user, get_participante_for_user, get_supabase_client
from app.services.conduta import cifra, membros, trilha
from app.services.conduta.acesso import (
    PessoaNoComite,
    caso_se_a_pessoa_abre,
    casos_da_pessoa,
    hoje_em_sao_paulo,
    pessoa_no_comite,
)

logger = logging.getLogger(__name__)

RECUSA = "Sem acesso a este conteúdo do Canal de Conduta"
INDISPONIVEL = "O Canal de Conduta está indisponível no momento"


@dataclass(frozen=True)
class NoComite:
    """Quem pediu e os casos que abre, só com os metadados."""

    autor_id: str
    pessoa: PessoaNoComite
    casos: list[dict]
    # No Comitê hoje, sem o Termo de Confidencialidade e Posse assinado.
    termo_pendente: bool = False


@dataclass(frozen=True)
class CasoAberto:
    """O caso que a pessoa abre, ainda cifrado, e as atribuições dela nele."""

    autor_id: str
    pessoa: PessoaNoComite
    caso: dict
    atribuicoes: list[dict]


def _recusar() -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=RECUSA)


def _indisponivel() -> HTTPException:
    return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=INDISPONIVEL)


async def _logado(current_user: dict, supabase) -> tuple[dict, PessoaNoComite]:
    me = await get_participante_for_user(current_user, supabase)
    barrar_desligado(me)
    if not me:
        raise _recusar()
    return me, pessoa_no_comite(supabase, me["id"])


async def _pessoa(current_user: dict, supabase) -> tuple[dict, PessoaNoComite]:
    if not cifra.chave_configurada():
        raise _indisponivel()
    return await _logado(current_user, supabase)


async def portao_da_coordenacao(
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
) -> dict:
    """A pessoa logada, se ela é a coordenação vigente do Comitê (issue #1826).
    As configurações não levam conteúdo de caso, então a chave de cifra não
    entra aqui. O super admin não passa por cima."""
    me, pessoa = await _logado(current_user, supabase)
    if pessoa.papel != "coordenacao":
        raise _recusar()
    return me


async def portao_da_lista(
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
) -> NoComite:
    """Os casos que a pessoa abre, só com os metadados. 403 a quem não tem
    designação nenhuma no Canal."""
    me, pessoa = await _pessoa(current_user, supabase)
    casos = casos_da_pessoa(supabase, pessoa)
    if casos is None:
        raise _recusar()
    return NoComite(autor_id=me["id"], pessoa=pessoa, casos=casos)


async def portao_da_tela_inicial(
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
) -> NoComite:
    """MINHA VEZ: o portão da lista e, além dele, o membro do Comitê ainda
    sem o Termo assinado (issue #1823; especificação, 3.4). Ele vê a tela
    inicial vazia, com o Termo pendente, e não abre caso nenhum."""
    me, pessoa = await _pessoa(current_user, supabase)
    casos = casos_da_pessoa(supabase, pessoa)
    # Quem tem Participação vigente e não assinou. O apurador, sem
    # Participação, não tem este Termo.
    termo_pendente = pessoa.papel is not None and not pessoa.termo_valido
    if casos is None and not termo_pendente:
        raise _recusar()
    return NoComite(autor_id=me["id"], pessoa=pessoa, casos=casos or [], termo_pendente=termo_pendente)


async def _caso_aberto(caso_id: UUID, current_user: dict, supabase) -> CasoAberto:
    me, pessoa = await _pessoa(current_user, supabase)
    aberto = caso_se_a_pessoa_abre(supabase, pessoa, str(caso_id))
    if aberto is None:
        raise _recusar()
    caso, atribuicoes = aberto
    return CasoAberto(autor_id=me["id"], pessoa=pessoa, caso=caso, atribuicoes=atribuicoes)


async def portao_do_caso(
    caso_id: UUID,
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
) -> CasoAberto:
    """O caso inteiro, ainda cifrado, depois de gravada a leitura na trilha."""
    aberto = await _caso_aberto(caso_id, current_user, supabase)
    try:
        trilha.registrar(supabase, aberto.caso["id"], aberto.autor_id, "leitura", "abriu o caso")
    except (APIError, httpx.HTTPError) as erro:
        logger.error("Leitura de caso do Canal de Conduta sem registro na trilha; o caso não sai: %s", erro)
        raise _indisponivel() from erro
    return aberto


async def portao_da_acao(
    caso_id: UUID,
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
) -> CasoAberto:
    """O caso em que a pessoa vai agir. A mesma autorização do `portao_do_caso`;
    a linha da trilha é a da própria ação, gravada por quem age, e sem ela a
    ação não vale."""
    return await _caso_aberto(caso_id, current_user, supabase)


async def _quem_esta_logado(current_user: dict, supabase) -> dict:
    me = await get_participante_for_user(current_user, supabase)
    barrar_desligado(me)
    if not me:
        raise _recusar()
    return me


async def portao_dos_membros(
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
) -> dict:
    """A tela Membros: quem está no Comitê hoje e quem tem o perfil de
    cadastro. Devolve a pessoa com `pode_cadastrar`. O super admin sem um dos
    dois recebe a mesma recusa."""
    me = await _quem_esta_logado(current_user, supabase)
    if not membros.ve_os_membros(supabase, me, hoje_em_sao_paulo()):
        raise _recusar()
    return {**me, "pode_cadastrar": me.get("perfil_conduta") == membros.PERFIL_DE_CADASTRO}


async def portao_do_cadastro(
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
) -> dict:
    """Incluir e encerrar membro: só com o perfil de cadastro do módulo
    (ADR 0097, decisão 3). O super admin não herda o perfil."""
    me = await _quem_esta_logado(current_user, supabase)
    if me.get("perfil_conduta") != membros.PERFIL_DE_CADASTRO:
        raise _recusar()
    return me
