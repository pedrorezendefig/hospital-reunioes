"""As telas da Central de Comando, lidas pelo cache com frescor (issue #815).

O backend devolve um payload por tela (PRD #809, "Telas agregadas"), e é o
payload INTEIRO da tela que vai para o cache, numa chave por tela e período: os
blocos de uma tela nascem e envelhecem juntos, e o carimbo de frescor é um só.

**O registro (`TELAS`) é o ponto de extensão das fatias seguintes.** Uma tela
nova (Dados do Google na #817, com os blocos da #818 no mesmo payload) entra
aqui com o `montar` dela e o que conta como falha da fonte, e ganha de graça:

- o cache de 1 hora por período e o último valor bom quando a fonte cai;
- o `frescor` no payload, que a barra de frescor da tela desenha;
- o Atualizar agora, pela rota genérica `POST /atualizar-agora?tela=...`,
  sem rota nova. A rota de leitura dela chama `ler(nome, periodo)`.

**Fica de fora, de propósito, o Ao vivo**: é o único número em tempo real da
Central e nunca é guardado, então não é tela deste registro e não tem o que
forçar no Atualizar agora.

Até a #821, a tela é tudo ou nada (`visao_geral.py`): o `montar` sobe a falha
de qualquer bloco e a tela inteira cai para o último valor bom, ou para o erro
se não houver nenhum guardado.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import partial

from app.services.central_de_comando import provedor_google
from app.services.central_de_comando import visao_geral as tela_visao_geral
from app.services.central_de_comando.cache import cache_da_central
from app.services.central_de_comando.periodo import PERIODOS, Periodo


@dataclass(frozen=True)
class Tela:
    """Uma tela da Central para o cache.

    - `montar`: o payload inteiro da tela no período, lido da fonte.
    - `falhas`: as exceções que querem dizer "a fonte falhou". Com número
      guardado, elas viram o último valor bom; as outras sobem sempre (a
      configuração que falta é 503, nunca um número velho).
    - `periodos`: os períodos que a tela tem. O Instagram só tem 7 e 28 dias.
    """

    montar: Callable[[Periodo], dict]
    falhas: tuple[type[Exception], ...]
    periodos: tuple[Periodo, ...] = PERIODOS


TELAS: dict[str, Tela] = {
    "visao-geral": Tela(montar=tela_visao_geral.montar, falhas=(provedor_google.GoogleError,)),
}


def motivo_da_recusa(nome: str, periodo: Periodo) -> str | None:
    """Por que o pedido não serve, ou `None` quando serve: a tela tem de estar
    no registro e ter o período pedido."""
    tela = TELAS.get(nome)
    if tela is None:
        return f"A Central não tem a tela {nome!r} para atualizar."
    if periodo not in tela.periodos:
        return f"A tela {nome} não tem o período {periodo}."
    return None


def ler(nome: str, periodo: Periodo, *, forcar: bool = False) -> dict:
    """O payload da tela no período, com o `frescor` dele.

    Dentro da hora, sai do cache sem ir à fonte; `forcar` é o Atualizar agora.
    A fonte fora com número guardado devolve o último valor bom, marcado; sem
    número guardado, a falha sobe para a rota traduzir (502 ou 503).
    """
    tela = TELAS[nome]
    leitura = cache_da_central.ler(
        (nome, periodo),
        partial(tela.montar, periodo),
        forcar=forcar,
        falhas=tela.falhas,
    )
    return {**leitura.valor, "frescor": leitura.frescor.como_dict()}
