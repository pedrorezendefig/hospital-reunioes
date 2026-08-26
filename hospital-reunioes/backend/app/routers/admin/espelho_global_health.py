"""Router /admin/espelho-global-health — Espelho da Global Health (ADR 0038).

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
    e não havia nada publicado.
    """
    itens = await _chamar(global_health.listar_especialidades, pesquisa)
    return {
        "data": itens,
        "total": len(itens),
        "motivo_vazio": None if itens else _MOTIVO_SEM_ESPECIALIDADE,
    }
