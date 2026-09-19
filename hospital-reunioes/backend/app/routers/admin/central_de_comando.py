"""Router /admin/central-de-comando: a Central de Comando (ADR 0058, PRD #809).

**Só Super admin, em TODA rota.** O `require_super_admin` mora no próprio
router, e não em cada endpoint: rota acrescentada por uma fatia seguinte já
nasce atrás do gate, sem depender de alguém lembrar. A sidebar só esconde a
seção, e esconder não é proteger (ADR 0050, decisão 2); o `layout.tsx` da seção
no front é a outra metade (ADR 0058, decisão 1).

**Stateless.** Nenhuma tabela, nada gravado no banco. Cada tela passa pelo
cache com frescor de 1 hora, em memória do processo (`services/central_de_comando/
cache.py` e `telas.py`, issue #815), e todo payload de tela traz o `frescor`: de
quando são os números e se a última atualização falhou.

**Honestidade da resposta**, o contrato que as telas consomem:

- 200: a fonte respondeu, agora ou há menos de 1 hora. Zero é zero de verdade,
  porque a fonte disse zero. Também é 200 o último valor bom: a fonte caiu,
  mas havia número guardado, e o `frescor` diz que a atualização falhou e por
  quê. A tela nunca zera por causa de uma falha.
- 502: a fonte falhou e não há número guardado para mostrar.
- 503: falta configurar a fonte no backend. Nunca zero, nunca lista vazia.

Telas, uma rota por tela, cada uma devolvendo o payload inteiro dela:

- GET /admin/central-de-comando/visao-geral?periodo=7d|28d|90d   (issue #814)

E uma rota só de Atualizar agora, para toda tela do registro de `telas.py`:

- POST /admin/central-de-comando/atualizar-agora?tela=...&periodo=...  (#815)

Os provedores são síncronos (`httpx.Client`, padrão da casa) e rodam em thread
pelo `_do_google`, que é também quem traduz a falha em resposta HTTP. A fatia
do Instagram ganha o seu par, no mesmo molde. O Ao vivo não passa pelo cache.
"""

from __future__ import annotations

from functools import partial

import anyio.to_thread
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.dependencies import require_super_admin
from app.limiter import limiter
from app.services.central_de_comando import provedor_google, telas
from app.services.central_de_comando.periodo import PERIODO_PADRAO, Periodo

router = APIRouter(
    prefix="/admin/central-de-comando",
    tags=["admin", "central-de-comando"],
    dependencies=[Depends(require_super_admin)],
)


async def _do_google(funcao, *args):
    """Roda uma leitura que depende do Google e traduz a falha em HTTP honesto.

    Envolve a tela inteira: uma falha do Google sem número guardado (o cache
    já devolveu o último valor bom quando havia) vira 502 ou 503 do payload
    todo, e não de um bloco só. Vale até a #821, que passa a usar status por
    bloco. O pedido de tela que o registro recusa (`telas.ler`) vira 422.
    """
    try:
        return await anyio.to_thread.run_sync(funcao, *args)
    except telas.PedidoDeTelaInvalidoError as exc:
        # Tela fora do registro ou período que ela não tem: recusado antes de
        # qualquer busca, dentro do `telas.ler`.
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    except provedor_google.GoogleNaoConfiguradoError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except provedor_google.GoogleError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


# ─── Visão Geral (issue #814) ────────────────────────────────────────────────


@router.get("/visao-geral")
@limiter.limit("30/minute")
async def visao_geral(request: Request, periodo: Periodo = Query(PERIODO_PADRAO)):
    """A Visão Geral no período: os Visitantes, o anterior, a variação e o
    frescor. Dentro da hora, sai do cache sem ir ao Google.

    Período fora de 7, 28 e 90 dias é 422 aqui: quem é leniente com o que se
    digita no endereço é a tela, que cai no padrão de 28 dias.
    """
    return await _do_google(telas.ler, "visao-geral", periodo)


# ─── Atualizar agora (issue #815) ────────────────────────────────────────────

# Cada Atualizar agora é uma ida garantida ao Google, que tem cota por
# propriedade e por hora. Cinco por minuto sobram para quem clica e acabam com
# o botão como porta de abuso. Por endereço, e não por pessoa, porque é assim
# que o `limiter` do app conta em todo lugar. A renovação automática da tela
# aberta usa esta mesma rota, uma vez por hora.
LIMITE_DO_ATUALIZAR_AGORA = "5/minute"


@router.post("/atualizar-agora")
@limiter.limit(LIMITE_DO_ATUALIZAR_AGORA)
async def atualizar_agora(request: Request, tela: str = Query(...), periodo: Periodo = Query(PERIODO_PADRAO)):
    """Força a renovação da tela pedida, no período pedido, e devolve o
    payload novo, com o carimbo novo.

    Vai à fonte mesmo com o número dentro da hora. Se a fonte falhar, devolve
    o último valor bom marcado (200), ou 502 se não houver nenhum guardado.
    Tela fora do registro de `telas.py` (o Ao vivo, por exemplo) ou período que
    a tela não tem é 422, sem ir à fonte: quem recusa é o próprio `telas.ler`.
    """
    return await _do_google(partial(telas.ler, tela, periodo, forcar=True))
