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
- GET /admin/central-de-comando/dados-do-google?periodo=7d|28d|90d   (issue #817)
- GET /admin/central-de-comando/instagram?periodo=7d|28d   (issue #819)

E uma rota só de Atualizar agora, para toda tela do registro de `telas.py`, a
Visão Geral e a lente de cada Objetivo (`tela=objetivos/{id}`, issue #861):

- POST /admin/central-de-comando/atualizar-agora?tela=...&periodo=...  (#815)

Os provedores são síncronos (`httpx.Client`, padrão da casa) e rodam em thread
pelo `_do_fonte`, que é também quem traduz a falha em resposta HTTP, uma
tradução só para o Google e o Instagram. O Ao vivo não passa pelo cache.
"""

from __future__ import annotations

from functools import partial

import anyio.to_thread
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.dependencies import require_super_admin
from app.limiter import limiter
from app.services.central_de_comando import objetivos, provedor_google, provedor_instagram, telas
from app.services.central_de_comando import visao_geral as visao_geral_service
from app.services.central_de_comando.periodo import PERIODO_PADRAO, Periodo

# As telas compostas de vários blocos, cada bloco com a sua chave de cache e a
# sua degradação (issue #821). Não passam pelo `telas.ler` de chave única: a
# leitura delas já é honesta por bloco e nunca levanta por falha de fonte, então
# não precisam do `_do_fonte`. O Atualizar agora as reconhece pelo nome.
LEITORES_COMPOSTOS = {"visao-geral": visao_geral_service.ler}

# A lente de um Objetivo entra no Atualizar agora como `tela=objetivos/{id}`, o
# mesmo caminho da leitura dela (issue #861). A lente não está no registro de
# `telas.py`: o montador dela lê os provedores direto, então forçar a chave da
# lente é ir às fontes que ela usa. Objetivo sem lente ou período que ela não
# tem é 422 dentro do `ler_lente`, sem ir à fonte.
PREFIXO_DA_LENTE = "objetivos/"

router = APIRouter(
    prefix="/admin/central-de-comando",
    tags=["admin", "central-de-comando"],
    dependencies=[Depends(require_super_admin)],
)


async def _do_fonte(funcao, *args):
    """Roda uma leitura que depende de uma fonte externa (Google ou Instagram) e
    traduz a falha em HTTP honesto.

    Envolve a tela inteira: uma falha da fonte sem número guardado (o cache já
    devolveu o último valor bom quando havia) vira 502 ou 503 do payload todo, e
    não de um bloco só. Vale até a #821, que passa a usar status por bloco. O
    pedido de tela que o registro recusa (`telas.ler`) vira 422.

    Uma tradução só para as duas fontes: o Atualizar agora é genérico e serve
    qualquer tela do registro, então a falha do Instagram precisa virar HTTP
    aqui como a do Google. O token vencido do Instagram é subclasse de
    `InstagramError` e cai no 502 quando não há número guardado.
    """
    try:
        return await anyio.to_thread.run_sync(funcao, *args)
    except telas.PedidoDeTelaInvalidoError as exc:
        # Tela fora do registro ou período que ela não tem: recusado antes de
        # qualquer busca, dentro do `telas.ler`.
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    except (provedor_google.GoogleNaoConfiguradoError, provedor_instagram.InstagramNaoConfiguradoError) as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except (provedor_google.GoogleError, provedor_instagram.InstagramError) as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


# ─── Visão Geral (issue #814) ────────────────────────────────────────────────


@router.get("/visao-geral")
@limiter.limit("30/minute")
async def visao_geral(request: Request, periodo: Periodo = Query(PERIODO_PADRAO)):
    """A Visão Geral no período, por bloco (issue #821): o número-manchete e o
    contexto dele, o Instagram num relance e os Objetivos em foco, cada bloco com
    o seu `estado`, mais o frescor combinado. Dentro da hora, cada bloco sai do
    cache sem ir à fonte.

    Responde 200 mesmo com uma fonte fora: o erro mora no bloco (`sem-dado` ou
    `nao-configurado`), nunca derruba a tela. Período fora de 7, 28 e 90 dias é
    422 aqui: quem é leniente com o que se digita no endereço é a tela.
    """
    return await anyio.to_thread.run_sync(visao_geral_service.ler, periodo)


# ─── Dados do Google (issue #817) ────────────────────────────────────────────


@router.get("/dados-do-google")
@limiter.limit("30/minute")
async def dados_do_google(request: Request, periodo: Periodo = Query(PERIODO_PADRAO)):
    """Dados do Google no período: os Visitantes por dia e as Visitas por
    dispositivo, com o frescor. Dentro da hora, sai do cache sem ir ao Google;
    o Atualizar agora é o da rota genérica, com `tela=dados-do-google`.

    No mesmo payload, e na mesma chave de cache (#818): as Áreas do site, a
    Origem do público e os Contatos gerados.

    Período fora de 7, 28 e 90 dias é 422, como na Visão Geral.
    """
    return await _do_fonte(telas.ler, "dados-do-google", periodo)


# ─── Instagram (issue #819) ──────────────────────────────────────────────────


@router.get("/instagram")
@limiter.limit("30/minute")
async def instagram(request: Request, periodo: Periodo = Query(PERIODO_PADRAO)):
    """A tela do Instagram no período: Seguidores e crescimento, Alcance,
    Visualizações, o bloco de engajamento e as Principais publicações, com o
    frescor. Dentro da hora, sai do cache sem ir ao Instagram; o Atualizar agora
    é o da rota genérica, com `tela=instagram`.

    Só 7 e 28 dias: a Graph API limita os insights a 30 dias por chamada, então
    o registro (`telas.py`) recusa 90 dias com 422, e não o busca. Token vencido
    com número guardado é 200 com o último valor bom e o aviso de renovação no
    frescor; sem número guardado, 502. Sem credencial, 503.
    """
    return await _do_fonte(telas.ler, "instagram", periodo)


# ─── Objetivos (issue #820) ──────────────────────────────────────────────────


@router.get("/objetivos")
@limiter.limit("30/minute")
async def objetivos_galeria(request: Request):
    """A galeria dos Objetivos: os seis do catálogo, com o número de hoje (28
    dias) dos quatro com montador e os dois em construção sem número nem destino
    navegável. Dentro da hora, sai do cache sem ir às fontes.

    É tudo ou nada como as outras telas até a #821: uma fonte fora sem número
    guardado é 502 (ou 503, sem credencial) para a galeria inteira.
    """
    return await _do_fonte(objetivos.ler_galeria)


@router.get("/objetivos/{identificador}")
@limiter.limit("30/minute")
async def objetivo_lente(request: Request, identificador: str, periodo: Periodo = Query(PERIODO_PADRAO)):
    """A lente de um Objetivo: os números dele no período, as sugestões (cada uma
    com o porquê) e o frescor.

    Identificador que não é de um Objetivo com lente (inexistente, ou em
    construção sem destino navegável) é 404. Período que a lente não tem (90 dias
    no Instagram) é 422, sem ir à fonte.
    """
    if not objetivos.tem_lente(identificador):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"A Central não tem o Objetivo {identificador!r}.",
        )
    return await _do_fonte(objetivos.ler_lente, identificador, periodo)


# ─── Ao vivo (issue #816) ────────────────────────────────────────────────────

# O único número em tempo real da Central, e o único que NÃO passa pelo cache:
# leitura direta da fonte de tempo real do Google a cada consulta, porque cache
# de 1 hora mataria o "agora". Cada consulta é uma ida garantida ao
# runRealtimeReport da GA4, que gasta cota de tempo real; por isso o teto é o da
# rota irmã de ida garantida (o Atualizar agora, também 5/minute), e não o das
# telas de leitura cacheadas. A tela consulta a cada 30 segundos e ao voltar o
# foco (ADR 0050, decisão 9), cerca de 2 por minuto, então 5/minute cobre o uso
# legítimo com folga. Como todo limite da casa, conta por endereço.
LIMITE_DO_AO_VIVO = "5/minute"


@router.get("/ao-vivo")
@limiter.limit(LIMITE_DO_AO_VIVO)
async def ao_vivo(request: Request):
    """Quantas pessoas estão no Site agora, direto da fonte de tempo real do
    Google, sem passar pelo cache.

    Não é tela do registro de `telas.py`: nunca é guardado e não tem Atualizar
    agora. Fonte fora é 502 e falta de configuração é 503, pelo mesmo
    `_do_fonte` das telas de tendência; nunca um zero inventado.
    """
    return {"pessoas": await _do_fonte(provedor_google.pessoas_no_site_agora)}


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

    A Visão Geral (e qualquer tela composta) renova todos os seus blocos pela
    leitura própria dela, que já é honesta por bloco: não passa pelo `_do_fonte`.

    A lente de um Objetivo (`tela=objetivos/{id}`, issue #861) renova a leitura
    dela, dentro deste mesmo limite de taxa.
    """
    leitor_composto = LEITORES_COMPOSTOS.get(tela)
    if leitor_composto is not None:
        return await anyio.to_thread.run_sync(partial(leitor_composto, periodo, forcar=True))
    if tela.startswith(PREFIXO_DA_LENTE):
        identificador = tela.removeprefix(PREFIXO_DA_LENTE)
        return await _do_fonte(partial(objetivos.ler_lente, identificador, periodo, forcar=True))
    return await _do_fonte(partial(telas.ler, tela, periodo, forcar=True))
