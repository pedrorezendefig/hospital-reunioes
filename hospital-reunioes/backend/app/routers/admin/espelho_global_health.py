"""Router /admin/espelho-global-health: Espelho da Global Health (ADR 0038).

Janela somente leitura sobre a agenda online da Global Health, na tela Dados
do Atendimento. O navegador fala com o app; o app fala com a Global Health.
O token da integração nunca sai do backend.

Caminho paralelo às tabelas curadas: nada é gravado (espelho, não cópia),
nenhum endpoint escreve, e a resposta é sempre a da chamada de agora.

Autorização: a mesma leitura da tela (qualquer participante de Reuniões
autenticado). Rate limit no padrão dos routers admin.

Honestidade da resposta, o contrato que a tela consome:
- 200 com `data` cheio: a Global Health respondeu.
- 200 com `data` vazio e `motivo_vazio`: respondeu, e não há nada publicado.
- 502: a Global Health falhou (timeout, 5xx, rede). Nunca lista vazia.
- 503: falta `GH_TOKEN_HOMOLOG` no backend. Nunca lista vazia.
"""

from __future__ import annotations

import anyio.to_thread
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.dependencies import require_participante_reunioes
from app.limiter import limiter
from app.services import global_health_service as global_health

router = APIRouter(prefix="/admin/espelho-global-health", tags=["admin", "espelho-global-health"])

_MOTIVO_SEM_ESPECIALIDADE = "Nenhuma especialidade publicada na agenda da Global Health."

_MOTIVO_BUSCA_SEM_RESULTADO = "Nenhuma especialidade publicada na agenda da Global Health com esse termo no nome."

# Cada bloco vazio diz por que está vazio e onde agir (ADR 0038, decisão 7).
# O particular é uma linha da própria lista: lista vazia quer dizer que nem
# ele está publicado, então prometer que "só o particular atende" seria dizer
# mais do que a resposta da GH sustenta.
_MOTIVO_SEM_CONVENIO = (
    "Nenhum convênio publicado para esta especialidade na agenda da Global Health. "
    "A cobertura ainda não foi liberada no Painel de Controle da GH."
)

_MOTIVO_SEM_PROFISSIONAL = (
    "Nenhum profissional com o botão ligado no Painel de Controle da Global Health para esta especialidade."
)

_MOTIVO_SEM_PLANO = "Nenhum plano publicado para este convênio nesta especialidade."

_ERRO_SEM_TOKEN = (
    "Espelho da Global Health não configurado: falta GH_TOKEN_HOMOLOG no backend. "
    "Fale com o super admin antes de concluir que não há nada publicado."
)


async def _chamar(funcao, *args):
    """Chama um elo do service e traduz a falha em resposta HTTP honesta.

    O service é síncrono (httpx.Client, padrão da casa): roda em thread para
    não segurar o event loop enquanto a Global Health pensa.
    """
    try:
        return await anyio.to_thread.run_sync(funcao, *args)
    except global_health.GlobalHealthNaoConfiguradaError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_ERRO_SEM_TOKEN,
        ) from exc
    except global_health.GlobalHealthError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc


@router.get("/especialidades")
@limiter.limit("30/minute")
async def listar_especialidades(
    request: Request,
    pesquisa: str | None = Query(None, max_length=100),
    _me: dict = Depends(require_participante_reunioes),
):
    """Elo 1: especialidades publicadas na agenda, ao vivo.

    `motivo_vazio` só vem preenchido quando a Global Health respondeu de fato
    e não havia nada a mostrar. O motivo distingue os dois vazios: agenda sem
    nada publicado, ou busca que não achou. Dizer "nada publicado" quando o
    filtro é que não casou seria mentira para quem consome a rota.
    """
    itens = await _chamar(global_health.listar_especialidades, pesquisa)
    if itens:
        motivo_vazio = None
    elif pesquisa:
        motivo_vazio = _MOTIVO_BUSCA_SEM_RESULTADO
    else:
        motivo_vazio = _MOTIVO_SEM_ESPECIALIDADE
    return {"data": itens, "total": len(itens), "motivo_vazio": motivo_vazio}


def _resposta(itens: list[dict], motivo_vazio: str) -> dict:
    """Envelope comum dos elos: o motivo só aparece quando não veio nada."""
    return {"data": itens, "total": len(itens), "motivo_vazio": motivo_vazio if not itens else None}


@router.get("/especialidades/{especialidade_id}/convenios")
@limiter.limit("30/minute")
async def listar_convenios(
    request: Request,
    especialidade_id: int,
    _me: dict = Depends(require_participante_reunioes),
):
    """Elo 2a: convênios aceitos na especialidade escolhida.

    O id vem do elo anterior na tela (não existe campo para digitar id); o
    tipo `int` no caminho recusa qualquer outra coisa aqui, sem gastar uma
    chamada na Global Health.
    """
    itens = await _chamar(global_health.listar_convenios, especialidade_id)
    return _resposta(itens, _MOTIVO_SEM_CONVENIO)


@router.get("/especialidades/{especialidade_id}/profissionais")
@limiter.limit("30/minute")
async def listar_profissionais(
    request: Request,
    especialidade_id: int,
    _me: dict = Depends(require_participante_reunioes),
):
    """Elo 2b: profissionais disponíveis na especialidade escolhida."""
    itens = await _chamar(global_health.listar_profissionais, especialidade_id)
    return _resposta(itens, _MOTIVO_SEM_PROFISSIONAL)


@router.get("/especialidades/{especialidade_id}/convenios/{convenio_id}/planos")
@limiter.limit("30/minute")
async def listar_planos(
    request: Request,
    especialidade_id: int,
    convenio_id: int,
    _me: dict = Depends(require_participante_reunioes),
):
    """Elo 3: planos do convênio, dentro da especialidade escolhida.

    Os dois ids ficam no caminho porque ambos vêm dos elos anteriores: a
    cadeia da agenda está desenhada na própria URL.
    """
    itens = await _chamar(global_health.listar_planos, convenio_id, especialidade_id)
    return _resposta(itens, _MOTIVO_SEM_PLANO)
