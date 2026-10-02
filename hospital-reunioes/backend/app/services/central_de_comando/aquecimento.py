"""O aquecimento do cache da Central no boot do backend (issue #867, ADR 0059).

O cache da Central mora na memória do processo e começa vazio a cada deploy
(`cache.py`). Sem aquecer, a primeira abertura de cada tela depois do deploy ia
à fonte na hora: 0,1 a 0,6 s com o cache cheio contra até 29 s na galeria dos
Objetivos com ele vazio (conferência de 23/09 na #858).

Aqui mora a única rodada de aquecimento: logo depois do boot, uma vez por
processo, ela lê cada chave que a primeira abertura de cada tela pede, no
**período padrão** (`PERIODO_PADRAO`). Decisão do dono na triagem da #867: nada
agendado, nada renovando o dia todo, nenhum outro período. A troca de período e
a abertura depois de horas sem ninguém olhando continuam indo à fonte.

- **Pelas leituras das rotas.** A rodada chama as mesmas funções que as rotas
  chamam (`visao_geral.ler`, `telas.ler`, `ler_galeria`, `ler_lente`), pela
  leitura comum do cache, sem `forcar`: a chave aquecida é a que a rota lê, e a
  rodada não vence as vizinhas como o Atualizar agora vence. A lista sai dos
  registros (`TELAS`, os períodos de cada lente), então tela ou Objetivo novo
  entra sozinho. A tela composta (a Visão Geral) é a única escrita à mão; o
  teste confere que toda tela composta do Atualizar agora está na rodada.
- **Numa thread, nunca no event loop.** O backend é um processo só e atende o
  app inteiro (reuniões, atas, POPs, Ouvidoria). As leituras da Central são
  síncronas e esperam a fonte por dezenas de segundos: no event loop, travariam
  o app todo, e não só a Central, e poderiam reprovar o health check do deploy.
  O `lifespan` dispara a thread e segue, sem esperar. Uma tela lida no meio da
  rodada espera a ida que já está no ar, sem abrir outra (uma ida por chave,
  #858). A thread é `daemon`: o desligamento do processo não espera uma fonte
  lenta.
- **Falha não derruba nada.** Falha da fonte, credencial ausente ou defeito numa
  chave vai para o log, e a rodada segue para a próxima. A tela se comporta
  como antes: a primeira leitura tenta de novo, respeitando a espera depois de
  falha do cache. Sem credencial nenhuma (CI, localhost sem `.env`), o
  provedor recusa antes de qualquer rede, e o log ganha uma linha só, o resumo.
- **Desligável.** `CENTRAL_AQUECER_NO_BOOT=false` e um restart desligam a
  rodada, sem deploy de código. A suíte de testes roda com ela desligada
  (`tests/conftest.py`).

O Ao vivo fica de fora: não passa pelo cache.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from functools import partial

from app.config import settings
from app.services.central_de_comando import objetivos, provedor_google, provedor_instagram, telas, visao_geral
from app.services.central_de_comando.objetivos.montador import PERIODOS_POR_OBJETIVO
from app.services.central_de_comando.periodo import PERIODO_PADRAO

logger = logging.getLogger(__name__)

# Uma leitura da rodada: o nome da tela (o mesmo do `tela=` do Atualizar agora)
# e a leitura dela, pronta para chamar.
Leitura = tuple[str, Callable[[], dict]]

# As telas compostas, lidas por bloco (#821): a falha mora no `estado` de cada
# bloco, e a leitura não levanta. A rodada olha os blocos delas para o log.
_COMPOSTAS = frozenset({"visao-geral"})

# Falta a credencial: não é falha, é a Central sem aquela fonte. Vai só no resumo.
_NAO_CONFIGURADO: tuple[type[Exception], ...] = (
    provedor_google.GoogleNaoConfiguradoError,
    provedor_instagram.InstagramNaoConfiguradoError,
)
# A fonte caiu. A frase destas exceções é fixa e segura (`cache.py`), então vai
# para o log como está.
_FALHA_DA_FONTE: tuple[type[Exception], ...] = (provedor_google.GoogleError, provedor_instagram.InstagramError)


def leituras_do_boot() -> list[Leitura]:
    """As leituras da rodada, na ordem do menu: a Visão Geral, as telas do
    registro, a galeria dos Objetivos e a lente de cada Objetivo navegável.
    Todas no período padrão; tela ou lente que não o tem fica de fora."""
    periodo = PERIODO_PADRAO
    leituras: list[Leitura] = [("visao-geral", partial(visao_geral.ler, periodo))]
    leituras += [
        (nome, partial(telas.ler, nome, periodo)) for nome, tela in telas.TELAS.items() if periodo in tela.periodos
    ]
    # A galeria só tem um período, o de hoje, que é o padrão.
    leituras.append(("objetivos", objetivos.ler_galeria))
    leituras += [
        (f"objetivos/{identificador}", partial(objetivos.ler_lente, identificador, periodo))
        for identificador, periodos_da_lente in PERIODOS_POR_OBJETIVO.items()
        if periodo in periodos_da_lente
    ]
    return leituras


def aquecer() -> None:
    """A rodada: lê cada leitura uma vez, em sequência, e fecha com uma linha de
    resumo no log. Nunca levanta: a falha de uma leitura vai para o log, e a
    rodada segue. Em sequência, e não em paralelo, para não somar a rajada do
    boot às leituras de quem abrir a Central nesse meio tempo."""
    inicio = time.monotonic()
    aquecidas = sem_credencial = com_falha = 0
    for nome, ler in leituras_do_boot():
        try:
            payload = ler()
        except _NAO_CONFIGURADO:
            sem_credencial += 1
            continue
        except _FALHA_DA_FONTE as exc:
            com_falha += 1
            logger.warning("Aquecimento da Central: %s ficou sem número, a fonte falhou (%s).", nome, exc)
            continue
        except Exception:
            com_falha += 1
            logger.exception("Aquecimento da Central: %s ficou sem número, erro inesperado.", nome)
            continue
        if nome not in _COMPOSTAS:
            aquecidas += 1
            continue
        for bloco, estado, motivo in _blocos(payload):
            if estado == "ok":
                aquecidas += 1
            elif estado == "nao-configurado":
                sem_credencial += 1
            else:
                com_falha += 1
                logger.warning(
                    "Aquecimento da Central: %s, bloco %s, ficou sem número, a fonte falhou (%s).",
                    nome,
                    bloco,
                    motivo,
                )
    logger.info(
        "Aquecimento da Central em %.1f s: %d aquecidas, %d sem credencial, %d com falha.",
        time.monotonic() - inicio,
        aquecidas,
        sem_credencial,
        com_falha,
    )


def _blocos(payload: dict) -> list[tuple[str, str, str | None]]:
    """Os blocos de fonte de uma tela composta: o nome, o `estado` e o motivo."""
    return [
        (bloco, valor["estado"], valor.get("motivo"))
        for bloco, valor in payload.items()
        if isinstance(valor, dict) and "estado" in valor
    ]


def disparar() -> threading.Thread | None:
    """Dispara a rodada numa thread própria e volta na hora, sem esperar. É o que
    o `lifespan` chama, uma vez por processo. Com o aquecimento desligado
    (`CENTRAL_AQUECER_NO_BOOT=false`), não dispara nada e devolve `None`."""
    if not settings.central_aquecer_no_boot:
        logger.info("Aquecimento da Central desligado (CENTRAL_AQUECER_NO_BOOT=false).")
        return None
    rodada = threading.Thread(target=aquecer, name="aquecimento-da-central", daemon=True)
    rodada.start()
    return rodada
