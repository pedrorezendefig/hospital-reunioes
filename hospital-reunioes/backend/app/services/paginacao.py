"""Leitura integral do PostgREST, em páginas (issue #430).

O PostgREST aceita um teto de linhas por resposta (`PGRST_DB_MAX_ROWS`). Com ele
configurado, uma leitura sem `range` volta CORTADA no teto, com HTTP 200 e sem
nenhum aviso: a diferença aparece no número, nunca no erro. Numa métrica esse é
o pior modo de falha possível, porque tudo sai menor e continua com cara de
medido. É o mesmo corte que encolheria a listagem que alimenta os contadores do
painel.

`ler_tudo` tira o teto do caminho: pede a leitura em janelas e para quando a
janela volta vazia. O laço avança pelo tamanho do lote RECEBIDO, e não pelo
tamanho pedido, porque é exatamente quando o servidor devolve menos do que se
pediu que o teto está agindo: avançar pelo tamanho pedido pularia tudo o que ele
cortou.

Duas condições de quem chama, e as duas são de correção:

* a query precisa de ordenação por chave única, senão a página seguinte pode
  repetir ou pular linha (o PostgREST não garante ordem sem `order`);
* a query entra como FÁBRICA, não pronta: `range` acrescenta `offset`/`limit` aos
  parâmetros em vez de substituí-los, então um builder reaproveitado sairia da
  segunda página com dois offsets grudados.

A volta a mais (a página vazia que encerra o laço) é o preço de não saber o teto
do servidor: com o teto agindo, toda página volta menor que a pedida, e é só a
página vazia que distingue "acabou" de "foi cortado".

E porque o laço confia no servidor honrar o recorte, `MAX_PAGINAS` é a saída de
emergência para o caso de essa confiança ser quebrada no caminho.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

# Quantas linhas por ida ao banco. Abaixo de qualquer teto plausível o laço
# apenas dá mais voltas; acima dele, o próprio teto encurta a página e o laço
# continua correto: o tamanho aqui é desempenho, não correção.
PAGINA = 1000

# Teto de voltas. O laço confia no servidor honrar o `range`; se alguém no
# caminho descartar o recorte (um proxy, um cliente que ignore o offset), toda
# página volta igual e cheia, e o laço nunca acabaria, segurando memória
# crescente até derrubar o processo. O teto troca esse travamento silencioso
# por uma linha de log e uma resposta curta: continua errado, mas visível.
MAX_PAGINAS = 1000


def ler_paginado(consulta: Callable[[], Any], pagina: int = PAGINA) -> tuple[list[dict], bool]:
    """As linhas e se a leitura chegou ao fim sozinha.

    O segundo valor é `False` quando o laço desistiu no teto de voltas, e é a
    única forma de quem chama saber que o resultado saiu INCOMPLETO: o teto
    devolve linhas de menos com a mesma cara de uma leitura inteira, e uma
    contagem feita em cima delas mente sem denunciar nada. O log de erro
    continua, mas log não chega à tela de ninguém (issue #487).

    Quem só precisa das linhas usa `ler_tudo`."""
    linhas: list[dict] = []
    inicio = 0
    for _volta in range(MAX_PAGINAS):
        resposta = consulta().range(inicio, inicio + pagina - 1).execute()
        lote = resposta.data or []
        if not lote:
            return linhas, True
        linhas.extend(lote)
        inicio += len(lote)
    logger.error(
        "Leitura paginada parou no teto de %s páginas: o servidor não está honrando o recorte, "
        "e o resultado saiu incompleto",
        MAX_PAGINAS,
    )
    return linhas, False


def ler_tudo(consulta: Callable[[], Any], pagina: int = PAGINA) -> list[dict]:
    """Roda `consulta()` em páginas até esgotar e devolve todas as linhas.

    `consulta` é uma fábrica de query já filtrada e ORDENADA por chave única;
    esta função só acrescenta o recorte de cada página."""
    linhas, _completa = ler_paginado(consulta, pagina)
    return linhas
