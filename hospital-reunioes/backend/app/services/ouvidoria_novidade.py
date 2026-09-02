"""Novidade na fila da Ouvidoria (issue #484, PRD #470, RN-66).

Um caso tem novidade quando a última movimentação da trilha é mais recente que
o carimbo de visto da Ouvidoria, ou quando o carimbo é nulo. Nada disso é
guardado: o carimbo mora no protocolo (`vista_pela_ouvidoria_em`, migration
092) e o outro lado da comparação é derivado da trilha na hora da leitura.

A leitura da trilha é uma só para a fila inteira, e falha nela não pode
derrubar a fila: sem o ponto o ouvidor ainda trabalha; sem a lista, não.
"""

from __future__ import annotations

import datetime as dt
import logging

from httpx import HTTPError
from postgrest.exceptions import APIError

logger = logging.getLogger(__name__)

# A função de agregação da migration 092: um par (caso, instante) por caso com
# pelo menos um movimento na trilha.
RPC_ULTIMO_MOVIMENTO = "ouvidoria_ultimo_movimento"


def _instante(bruto) -> dt.datetime | None:
    """O timestamp que o PostgREST devolve como texto, ou None quando vazio."""
    return dt.datetime.fromisoformat(str(bruto)) if bruto else None


def ultimo_movimento_por_caso(supabase) -> dict[str, dt.datetime]:
    """O instante da última movimentação de cada caso, por id.

    Devolve o mapa vazio quando a trilha não responde: a fila continua de pé,
    sem novidade nenhuma. `HTTPError` entra junto de `APIError` porque timeout
    e queda de conexão do PostgREST sobem crus, sem virar `APIError`.
    """
    try:
        resposta = supabase.rpc(RPC_ULTIMO_MOVIMENTO, {}).execute()
    except (APIError, HTTPError):
        logger.warning("Falha ao derivar a última movimentação dos casos: a fila sai sem marcador de novidade")
        return {}
    mapa: dict[str, dt.datetime] = {}
    for linha in resposta.data or []:
        quando = _instante(linha.get("ultimo_movimento_em"))
        if quando is not None:
            mapa[str(linha.get("manifestacao_id"))] = quando
    return mapa


def tem_novidade(vista_em, ultimo_movimento_em: dt.datetime | None) -> bool:
    """A regra do ponto (RN-66).

    Carimbo nulo é novidade mesmo sem nenhum movimento na trilha: é o estado em
    que todo caso já existente entra na migration, e ninguém pode afirmar que a
    Ouvidoria o leu.

    O empate cai do lado de "já vi": quem abriu o caso no mesmo instante do
    movimento leu o movimento. Do outro lado o ponto nunca apagaria nos casos
    em que a própria abertura coincide com o último movimento gravado.
    """
    vista = _instante(vista_em)
    if vista is None:
        return True
    if ultimo_movimento_em is None:
        return False
    return ultimo_movimento_em > vista
