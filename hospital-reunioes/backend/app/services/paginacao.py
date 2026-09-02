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

E porque o laço confia no servidor honrar o recorte, `MAX_LINHAS` é a saída de
emergência para o caso de essa confiança ser quebrada no caminho.

O teto tem DUAS causas possíveis, e o código não consegue distinguir uma da
outra: ou o servidor parou de honrar o recorte (e o laço giraria para sempre),
ou a tabela passou legitimamente de `MAX_LINHAS` linhas. O laço sai pelo mesmo
lugar nos dois casos, porque nunca chegou a ver a página vazia. Por isso o log e
a exceção nomeiam as duas, em vez de afirmar a que não se sabe: mandar quem for
investigar caçar um bug de PostgREST que não existe é pior que não avisar.

O teto operacional que sai daí é uma decisão aceita (issue #448): a partir de
100.000 linhas em qualquer tabela lida por aqui, a leitura passa a ser
declarada incompleta. Nenhum cadastro da Ouvidoria chega perto disso hoje, e as
duas leituras que podem crescer sem limite pela porta pública, a fila de casos e
o calendário do painel, usam `ler_paginado` e CARIMBAM a incompletude na
resposta em vez de derrubar a tela. Passar do teto degrada, não nega serviço.

O recorte é por OFFSET, e isso é uma escolha, não um descuido: com escrita
acontecendo entre uma página e a seguinte, o offset pode repetir ou pular linha.
Keyset (cursor pela chave de ordenação) fecha essa janela, e foi avaliado e
RECUSADO na issue #448: o furo custa uma linha a mais ou a menos numa listagem
administrativa, enquanto a troca mexe na assinatura de `ler_tudo` (o cursor
precisa entrar na query, e cada chamada tem chave de ordenação diferente) e nas
quatorze chamadas do módulo. Preço alto para um sintoma que ninguém relatou. Se
aparecer contagem que não bate entre duas leituras próximas, é aqui que se olha.
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

# Teto de LINHAS acumuladas. O laço confia no servidor honrar o `range`; se
# alguém no caminho descartar o recorte (um proxy, um cliente que ignore o
# offset), toda página volta igual e cheia, e o laço nunca acabaria, segurando
# memória crescente até derrubar o processo. O teto troca esse travamento
# silencioso por um aviso.
#
# Conta linhas, e não páginas, porque é a linha que ocupa memória: um teto de
# mil PÁGINAS com página de mil linhas deixa juntar um milhão de dicionários
# antes de ser consultado, e o processo cai por falta de memória antes de
# chegar ao aviso, que é o caso exato para o qual o guarda-corpo existe (issue
# #448). Em linhas, o mesmo teto vale para qualquer tamanho de página.
#
# O valor é uma decisão aceita, não um número solto, e mexer nele nos dois
# sentidos custa caro (há teste de guarda na faixa, com o motivo escrito):
#
# * subir demais devolve o defeito da #448, porque volta a caber mais memória
#   do que o processo aguenta antes de o guarda-corpo agir;
# * baixar demais transforma cadastro legítimo em leitura declarada incompleta,
#   e aí o aviso vira ruído permanente que todo mundo aprende a ignorar.
#
# 100.000 fica uma ordem de grandeza acima de qualquer leitura plausível do
# módulo hoje (o cadastro maior é a fila de manifestações, na casa dos
# milhares) e ainda é um volume que o processo aguenta segurar para conseguir
# reclamar.
MAX_LINHAS = 100_000

# O que o log e a exceção dizem quando o teto age. As duas causas aparecem
# porque o código não sabe qual delas foi: o laço sai pelo mesmo lugar sem
# nunca ter visto a página vazia. Afirmar só a segunda mandaria quem for
# investigar caçar um bug de PostgREST que pode não existir.
_AS_DUAS_CAUSAS = "ou a tabela passou do teto, ou o servidor não está honrando o recorte das páginas"


class LeituraIncompletaError(RuntimeError):
    """A leitura parou no teto e as linhas que voltaram são MENOS do que a
    tabela tem.

    É erro, não aviso, porque a alternativa é devolver a resposta curta com a
    mesma cara de uma leitura inteira: quem chama contaria em cima dela sem ter
    como desconfiar. Herda de `RuntimeError` de propósito, fora da família de
    falhas de infraestrutura (`HTTPError`, `APIError`, `OSError`, `ValueError`)
    que o módulo da Ouvidoria engole para não derrubar a tela: um `except` que
    existe para tolerar banco fora do ar não pode transformar resultado
    incompleto em silêncio.

    Quem tem onde carimbar a incompletude na própria resposta não deve chegar
    aqui: usa `ler_paginado` e degrada. Esta exceção é o último recurso de quem
    devolve linhas e mais nada."""


def ler_paginado(consulta: Callable[[], Any], pagina: int = PAGINA, *, rotulo: str) -> tuple[list[dict], bool]:
    """As linhas e se a leitura chegou ao fim sozinha.

    O segundo valor é `False` quando o laço desistiu no teto de linhas, e é a
    única forma de quem chama saber que o resultado saiu INCOMPLETO: o teto
    devolve linhas de menos com a mesma cara de uma leitura inteira, e uma
    contagem feita em cima delas mente sem denunciar nada. O log de erro
    continua, mas log não chega à tela de ninguém (issue #487).

    Esta porta é para quem tem onde CARIMBAR a falha na própria resposta. Quem
    não tem usa `ler_tudo`, que levanta.

    `rotulo` é o nome da leitura no log, e é obrigatório de propósito: são
    quatorze chamadas em oito tabelas, e um aviso de teto que não diz QUAL
    leitura estourou não serve para nada no incidente. Sem default, chamada
    nova não nasce anônima."""
    linhas: list[dict] = []
    inicio = 0
    while len(linhas) < MAX_LINHAS:
        resposta = consulta().range(inicio, inicio + pagina - 1).execute()
        lote = resposta.data or []
        if not lote:
            return linhas, True
        linhas.extend(lote)
        inicio += len(lote)
    logger.error(
        "A leitura de %s parou no teto de %s linhas e saiu incompleta: %s",
        rotulo,
        MAX_LINHAS,
        _AS_DUAS_CAUSAS,
    )
    return linhas, False


def ler_tudo(consulta: Callable[[], Any], pagina: int = PAGINA, *, rotulo: str) -> list[dict]:
    """Roda `consulta()` em páginas até esgotar e devolve todas as linhas.

    `consulta` é uma fábrica de query já filtrada e ORDENADA por chave única;
    esta função só acrescenta o recorte de cada página. `rotulo` nomeia a
    leitura no aviso, como em `ler_paginado`.

    Levanta `LeituraIncompletaError` quando o teto age. Devolver as linhas
    juntadas até ali seria entregar uma resposta curta indistinguível da
    inteira, que é o modo de falha que a paginação veio consertar, só que por
    outra porta."""
    linhas, completa = ler_paginado(consulta, pagina, rotulo=rotulo)
    if not completa:
        raise LeituraIncompletaError(
            f"A leitura de {rotulo} parou no teto de {MAX_LINHAS} linhas e saiu incompleta: {_AS_DUAS_CAUSAS}"
        )
    return linhas
