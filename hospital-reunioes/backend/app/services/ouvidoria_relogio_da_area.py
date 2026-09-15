"""Parar (e destravar) o relógio da área quando o caso sai das mãos dela.

Extraído da rota de Devolução à Ouvidoria na issue #708, porque o
Redirecionamento pelo ouvidor (ADR 0055) faz exatamente a mesma coisa por outra
porta: as duas tiram o caso da área e o devolvem à fila do ouvidor, e as duas
precisam do mesmo par de escritas, na mesma ordem, com o mesmo desfazer. Manter
duas cópias significaria que o próximo ajuste no relógio (foi isso que a #607 e
a #623 corrigiram, uma por vez) valeria para uma porta e não para a outra.

Três funções, e a separação entre elas é regra, não arrumação:

- `estouro_a_carimbar` é PURA e é decidida ANTES de qualquer efeito. A devolução
  a chama antes de consumir o link de uso único, porque ler um timestamp com
  formato inesperado levanta `ValueError` cru, e um 500 depois do claim
  deixaria o responsável sem devolução e sem link para tentar de novo.
- `parar` escreve e DEIXA A FALHA SUBIR. Cada porta trata a falha do PostgREST
  de um jeito (o portal devolve o link e responde 503; o painel responde 500
  com a frase do ouvidor), e é esse tratamento que não pode ser compartilhado.
- `restaurar` é o desfazer, colado ao fazer: ele devolve o vencimento e, só
  quando a ida o escreveu, o carimbo do estouro.
"""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass, field

from httpx import HTTPError
from postgrest.exceptions import APIError

from app.services import ouvidoria_prorrogacao
from app.services.ouvidoria_prazos import estouro_consumado, ler_instante

logger = logging.getLogger(__name__)

# `APIError` só nasce DEPOIS que a resposta chega; timeout, conexão recusada e
# pool esgotado sobem como `HTTPError` do httpx, que herda de `Exception` e não
# de `OSError`. Sem os dois na tupla, a falha de rede escapa crua.
_FALHAS_DO_POSTGREST = (APIError, HTTPError)


@dataclass(frozen=True)
class RelogioParado:
    """O que a parada guardou para poder ser desfeita.

    `estado_de_origem` é o estado que o caso tinha quando foi LIDO, e é ele que
    filtra as duas escritas. Entre a leitura do caso e a parada há idas ao
    PostgREST, e a Ouvidoria pode ter pausado ou movido o caso no meio: parar às
    cegas tiraria o vencimento de um caso que já não é da área, a restauração
    depois não casaria linha (ela filtra pelo mesmo estado) e o caso voltaria
    para a fila com `prazo_area_em` nulo. A cobrança e o escalonamento filtram
    por `.lte("prazo_area_em", ...)`, que descarta nulo: o caso sairia das duas
    em silêncio."""

    estado_de_origem: str
    prazo_anterior: object
    carimbo_a_restaurar: dict
    # O par do `limpar_a_resposta`: as colunas do marco T2 com os valores que
    # elas tinham, e só quando a ida as escreveu. Vazio para quem não pediu a
    # limpeza, e é isso que mantém o rollback da Devolução à Ouvidoria com o
    # mesmo payload de sempre (issue #708).
    carimbo_da_resposta_a_restaurar: dict = field(default_factory=dict)


def estouro_a_carimbar(caso: dict, agora: dt.datetime) -> dt.datetime | None:
    """O estouro consumado a gravar antes de o relógio parar, ou None.

    Decidido ANTES de o vencimento ir para nulo, e é isso que o torna
    necessário: zerar `prazo_area_em` tira do indicador de cumprimento a única
    régua que ele tinha, e o atraso do ciclo que acabou sumiria junto
    (issue #374). Ciclo cumprido não carimba nada, e estouro já gravado não é
    reescrito: as duas regras moram em `estouro_consumado`, não aqui."""
    return estouro_consumado(
        ler_instante(caso.get("prazo_area_em")),
        ler_instante(caso.get("respondida_em")),
        agora,
        ler_instante(caso.get("area_estourou_em")),
    )


def parar(
    supabase,
    manifestacao_id: str,
    caso: dict,
    estourou: dt.datetime | None,
    *,
    limpar_a_resposta: bool = False,
) -> RelogioParado | None:
    """Zera o vencimento da área e os carimbos dos jobs de prazo, e grava o
    estouro consumado quando houver. Devolve o que o desfazer precisa, ou
    **None quando nenhuma linha casou**.

    Os carimbos dos jobs saem junto porque sem eles o caso despachado depois
    ficaria fora da véspera, da cobrança e da escada para sempre: cada job pula
    o degrau que já tem carimbo (issue #373).

    A coluna do estouro só entra no update quando há estouro a gravar. Escrever
    `None` nela seria escrita cega sobre um carimbo que esta requisição não
    decidiu apagar: a devolução por insuficiência grava o mesmo campo sem
    filtro de status, e o `None` daqui apagaria o carimbo dela na corrida.

    **`None` é recusa, não detalhe.** Nenhuma linha casada significa que o caso
    saiu do estado de origem entre a leitura e esta escrita, e quem chama TEM
    que parar aí. Até a issue #708 esse ramo não precisava de resposta: a RPC
    logo adiante recusava sozinha, porque `respondido -> em_classificacao` não
    existia no grafo. Com a aresta aberta, a RPC passa a aceitar, e seguir em
    frente mandaria para a Ouvidoria (pela devolução do portal) ou para a área
    nova (pelo redirecionamento) um caso cujo relógio nunca parou, carregando
    junto a resposta que a área acabou de dar.

    `limpar_a_resposta` é opt-in, e o padrão é não mexer no marco T2. Com ele, o
    update também apaga `respondida_em` e `respondida_por_nome`, que é o que o
    Redirecionamento a partir de `respondido` precisa: o ciclo daquela área
    acabou, e a área NOVA não pode nascer com a resposta da anterior no lugar da
    dela (`cumprimento_da_area` lê `respondida_em` como "a resposta do ciclo
    CORRENTE" e diria "cumprido" para sempre). É a mesma limpeza que a devolução
    por insuficiência e a reabertura por reincidência já fazem, pelo mesmo
    motivo escrito lá.

    `resposta_da_area` NÃO sai, como na devolução por insuficiência: o texto é a
    resposta corrente que o ouvidor relê, a trilha guarda a cópia imutável dele
    (uma por ciclo, issue #374) e o que mente é o MARCO, não o texto.

    Sem o opt-in o payload é byte a byte o de antes desta issue, e é isso que
    mantém a Devolução à Ouvidoria (rota pública, sem login) intocada.

    Levanta o erro do PostgREST para quem chamou: a resposta ao usuário é
    diferente em cada porta, e ela não mora aqui."""
    estado_de_origem = str(caso.get("status"))
    carimbo_do_estouro = {"area_estourou_em": estourou.isoformat()} if estourou else {}
    limpeza_da_resposta = {"respondida_em": None, "respondida_por_nome": None} if limpar_a_resposta else {}
    result = (
        supabase.table("ouvidoria_protocolos")
        .update(
            {"prazo_area_em": None}
            | carimbo_do_estouro
            | ouvidoria_prorrogacao.carimbos_a_zerar()
            | limpeza_da_resposta
        )
        .eq("id", manifestacao_id)
        .eq("status", estado_de_origem)
        .execute()
    )
    if not result.data:
        return None
    return RelogioParado(
        estado_de_origem=estado_de_origem,
        prazo_anterior=caso.get("prazo_area_em"),
        # O desfazer nasce colado no fazer: o rollback devolve a coluna ao valor
        # que ela tinha, mas só quando a ida a escreveu. Sem esse par, o
        # `except` de quem chama mandaria `None` para um caso cujo carimbo esta
        # requisição nunca tocou (issue #623).
        carimbo_a_restaurar={"area_estourou_em": caso.get("area_estourou_em")} if carimbo_do_estouro else {},
        carimbo_da_resposta_a_restaurar={
            "respondida_em": caso.get("respondida_em"),
            "respondida_por_nome": caso.get("respondida_por_nome"),
        }
        if limpeza_da_resposta
        else {},
    )


def restaurar(supabase, manifestacao_id: str, parado: RelogioParado) -> bool:
    """Devolve o vencimento da área quando a transição NÃO entrou, e só nesse
    caso. Devolve se restaurou de fato.

    O `ReadTimeout` não diz que o Postgres deixou de executar, e o filtro pelo
    estado de origem é o que separa os dois mundos, porque ele só casa enquanto
    a transição não passou. Restaurar às cegas devolveria prazo a um caso que já
    saiu da área, e a cobrança passaria a caçar uma área que não tem mais nada a
    fazer.

    Os carimbos dos jobs de prazo ficam zerados de propósito: a linha casada
    prova que o caso continua com a área, e um carimbo zerado a mais custa um
    aviso repetido, enquanto restaurá-lo errado custa a cobrança que não sai.

    O estouro consumado volta JUNTO com o vencimento porque os dois saíram
    juntos, e desfazer meio par é pior que não desfazer nada: o caso ficaria com
    o prazo de volta e o carimbo do estouro gravado, e `cumprimento_da_area` lê
    o carimbo antes de tudo. Uma prorrogação aprovada depois nunca mais
    conseguiria levar aquele caso a `cumprido` (issue #607).

    O marco T2 volta pela mesma regra do carimbo do estouro: só quando a ida o
    apagou. Sem esse par, o rollback do redirecionamento deixaria um caso
    `respondido` sem T2, que é o mesmo meio-desfazer que a issue #623
    corrigiu."""
    try:
        result = (
            supabase.table("ouvidoria_protocolos")
            .update(
                {"prazo_area_em": parado.prazo_anterior}
                | parado.carimbo_a_restaurar
                | parado.carimbo_da_resposta_a_restaurar
            )
            .eq("id", manifestacao_id)
            .eq("status", parado.estado_de_origem)
            .execute()
        )
    except _FALHAS_DO_POSTGREST:
        logger.warning("Falha ao restaurar o prazo da área da manifestação %s", manifestacao_id)
        return False
    return bool(result.data)
