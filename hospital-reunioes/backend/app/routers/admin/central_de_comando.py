"""Router /admin/central-de-comando: a Central de Comando (ADR 0058, PRD #809).

**Só Super admin, em TODA rota.** O `require_super_admin` mora no próprio
router, e não em cada endpoint: rota acrescentada por uma fatia seguinte já
nasce atrás do gate, sem depender de alguém lembrar. A sidebar só esconde a
seção, e esconder não é proteger (ADR 0050, decisão 2); o `layout.tsx` da seção
no front é a outra metade (ADR 0058, decisão 1).

**Stateless.** Nenhuma tabela, nada gravado: cada número é lido da fonte na
hora. O cache com frescor de 1 hora e o Atualizar agora chegam na #815.

**Honestidade da resposta**, o contrato que as telas consomem:

- 200: a fonte respondeu. Zero é zero de verdade, porque a fonte disse zero.
- 502: a fonte falhou (timeout, 5xx, acesso recusado, resposta ilegível).
- 503: falta configurar a fonte no backend. Nunca zero, nunca lista vazia.

Telas, uma rota por tela, cada uma devolvendo o payload inteiro dela:

- GET /admin/central-de-comando/visao-geral?periodo=7d|28d|90d   (issue #814)

Os provedores são síncronos (`httpx.Client`, padrão da casa) e rodam em thread
pelo `_do_google`, que é também quem traduz a falha em resposta HTTP. A fatia
do Instagram ganha o seu par, no mesmo molde.
"""

from __future__ import annotations

import anyio.to_thread
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.dependencies import require_super_admin
from app.limiter import limiter
from app.services.central_de_comando import provedor_google
from app.services.central_de_comando import visao_geral as tela_visao_geral
from app.services.central_de_comando.periodo import PERIODO_PADRAO, Periodo

router = APIRouter(
    prefix="/admin/central-de-comando",
    tags=["admin", "central-de-comando"],
    dependencies=[Depends(require_super_admin)],
)


async def _do_google(funcao, *args):
    """Roda uma leitura que depende do Google e traduz a falha em HTTP honesto."""
    try:
        return await anyio.to_thread.run_sync(funcao, *args)
    except provedor_google.GoogleNaoConfiguradoError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except provedor_google.GoogleError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


# ─── Visão Geral (issue #814) ────────────────────────────────────────────────


@router.get("/visao-geral")
@limiter.limit("30/minute")
async def visao_geral(request: Request, periodo: Periodo = Query(PERIODO_PADRAO)):
    """A Visão Geral no período: os Visitantes, o anterior e a variação.

    Período fora de 7, 28 e 90 dias é 422 aqui: quem é leniente com o que se
    digita no endereço é a tela, que cai no padrão de 28 dias.
    """
    return await _do_google(tela_visao_geral.montar, periodo)
