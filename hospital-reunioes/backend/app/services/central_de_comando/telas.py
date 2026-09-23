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
  sem rota nova. A rota de leitura dela chama `ler(nome, periodo)` pelo
  `_do_google` do router, que traduz a recusa do pedido em 422;
- a recusa de período que a tela não tem, conferida aqui dentro do `ler`.

**Fica de fora, de propósito, o Ao vivo**: é o único número em tempo real da
Central e nunca é guardado, então não é tela deste registro e não tem o que
forçar no Atualizar agora.

Até a #821, a tela é tudo ou nada (`visao_geral.py`): o `montar` sobe a falha
de qualquer bloco e a tela inteira cai para o último valor bom, ou para o erro
se não houver nenhum guardado.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial

from app.services.central_de_comando import dados_do_google as tela_dados_do_google
from app.services.central_de_comando import instagram as tela_instagram
from app.services.central_de_comando import provedor_google, provedor_instagram
from app.services.central_de_comando.cache import cache_da_central
from app.services.central_de_comando.periodo import PERIODOS, Periodo


class PedidoDeTelaInvalidoError(ValueError):
    """A tela não está no registro, ou não tem o período pedido. A rota traduz
    em 422, e nada é buscado nem guardado. A mensagem diz qual dos dois."""


@dataclass(frozen=True)
class Tela:
    """Uma tela da Central para o cache.

    - `montar`: o payload inteiro da tela no período, lido da fonte.
    - `falhas`: as exceções que querem dizer "a fonte falhou". Com número
      guardado, elas viram o último valor bom; as outras sobem sempre (a
      configuração que falta é 503, nunca um número velho). **A mensagem
      dessas exceções vai para a tela** (o `motivo` do frescor, num 200) e
      fica guardada no cache por até 1 hora: só entra exceção de frase fixa e
      segura, sem URL, token, corpo da fonte ou detalhe interno. A
      `GoogleError` do provedor é assim; a exceção crua do `httpx` não é (o
      texto dela traz a URL inteira).
    - `periodos`: os períodos que a tela tem. O Instagram só tem 7 e 28 dias.
    - `fontes`: de onde vêm os números (`"google"`, `"instagram"`). O Atualizar
      agora da tela vence as outras telas da mesma fonte e período (#858).
    """

    montar: Callable[[Periodo], dict]
    falhas: tuple[type[Exception], ...]
    periodos: tuple[Periodo, ...] = PERIODOS
    fontes: tuple[str, ...] = ()

    def fontes_no(self, periodo: Periodo) -> set[tuple[str, Periodo]]:
        """As fontes da tela no período, como o cache as compara."""
        return {(fonte, periodo) for fonte in self.fontes}


TELAS: dict[str, Tela] = {
    # A Visão Geral saiu daqui na #821: virou tela COMPOSTA, um bloco por chave
    # de cache, cada bloco degradando sozinho (`visao_geral.ler`). Não cabe no
    # registro de chave única, que é tudo ou nada. O Atualizar agora dela é
    # despachado à parte no router (`LEITORES_COMPOSTOS`).
    # Dados do Google (#817): os blocos da #818 entram no mesmo `montar`, na
    # mesma chave, e o Atualizar agora renova todos juntos.
    "dados-do-google": Tela(
        montar=tela_dados_do_google.montar,
        falhas=(provedor_google.GoogleError,),
        periodos=PERIODOS,
        fontes=("google",),
    ),
    # Instagram (#819): só 7 e 28 dias (a Graph API limita insights a 30 dias).
    # `InstagramError` cobre a falha da fonte, e o token vencido
    # (`InstagramTokenExpiradoError`) é subclasse dela, então também vira último
    # valor bom; o "não configurado" fica de fora e é sempre 503.
    "instagram": Tela(
        montar=tela_instagram.montar,
        falhas=(provedor_instagram.InstagramError,),
        periodos=("7d", "28d"),
        fontes=("instagram",),
    ),
}


def _tela_do_pedido(nome: str, periodo: Periodo) -> Tela:
    """A tela do registro, se ela existe e tem o período; senão, recusa."""
    tela = TELAS.get(nome)
    if tela is None:
        raise PedidoDeTelaInvalidoError(f"A Central não tem a tela {nome!r}.")
    if periodo not in tela.periodos:
        raise PedidoDeTelaInvalidoError(f"A tela {nome} não tem o período {periodo}.")
    return tela


def ler(nome: str, periodo: Periodo, *, forcar: bool = False) -> dict:
    """O payload da tela no período, com o `frescor` dele.

    Dentro da hora, sai do cache sem ir à fonte; `forcar` é o Atualizar agora.
    A fonte fora com número guardado devolve o último valor bom, marcado; sem
    número guardado, a falha sobe para a rota traduzir (502 ou 503).

    Tela fora do registro ou período que a tela não tem levanta
    `PedidoDeTelaInvalidoError` antes de qualquer busca (422 na rota): a regra
    mora aqui, e não em cada rota, para nenhuma tela guardar período que não
    tem por uma rota esquecer de conferir.

    O payload sai do cache em cópia funda: ele é o mesmo para todo Super admin
    por até 1 hora, e quem mexer no que recebeu não mexe no guardado.
    """
    tela = _tela_do_pedido(nome, periodo)
    leitura = cache_da_central.ler(
        (nome, periodo),
        partial(tela.montar, periodo),
        forcar=forcar,
        falhas=tela.falhas,
        fontes=tela.fontes_no(periodo),
    )
    return {**copy.deepcopy(leitura.valor), "frescor": leitura.frescor.como_dict()}
