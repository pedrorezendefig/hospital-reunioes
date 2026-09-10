"""A Demanda vinculada relendo o GitHub (issue #678, PRD #673, ADR 0054).

Uma rotina, dois gatilhos. `sincronizar_demanda` le a issue, monta a foto,
compara com a guardada e, se mudou, grava o cache e a linha automatica da Etapa.
Quem a chama e o webhook (em segundos, pelo numero da issue do payload) e o job
de hora em hora (sobre o lote inteiro). O par webhook + reconciliacao e o mesmo
molde da ClickSign, e existe pelo mesmo motivo: o GitHub NAO reentrega webhook
que falhou, e sem a segunda passagem um container reiniciando na hora errada
congelaria o selo do card ate alguem mexer nele a mao.

Tres invariantes que valem pelos dois caminhos:

- **Foto igual nao escreve NADA.** Nem a linha do fio, nem o `UPDATE`, nem o
  carimbo da ultima sincronizacao. E o que faz a entrega repetida do GitHub e a
  passagem de hora em hora serem inofensivas: sem esta guarda, o fio do diretor
  ganharia uma linha por hora dizendo a mesma coisa.
- **Etapa igual nao grava linha.** Um degrau abaixo da guarda acima: editar o
  corpo da issue muda a foto sem mudar a Etapa, e o cache precisa acompanhar
  enquanto o fio fica calado.
- **Falha e de UMA Demanda.** No lote, o `except` e por linha e por qualquer
  causa (o GitHub fora do ar e o timeout do PostgREST chegam por portas
  diferentes), e o log guarda o identificador.

O I/O do GitHub e todo do `github_client`; a regra da Etapa e toda do
`tecnologia_vinculo`. Aqui mora so a costura entre os dois e o banco.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from app.services import github_client
from app.services.tecnologia import (
    ESTADOS_ABERTOS,
    TABELA_CONVERSAS,
    TABELA_DEMANDAS,
    linha_de_movimento,
)
from app.services.tecnologia_vinculo import (
    ETAPA_REGISTRADA,
    etapa_da_foto,
    foto_mudou,
    o_que_muda_da_foto,
    partes_da_foto,
    partes_para_o_diretor,
    texto_movimento_etapa,
)

logger = logging.getLogger(__name__)

# As acoes do evento `issues` que podem mexer na foto (issue #678).
#
# `opened` fica de fora porque uma issue recem-aberta nao tem Demanda vinculada
# ainda: o Vinculo nasce depois, e ja sincroniza na hora em que e criado. As
# demais acoes (`assigned`, `milestoned`, `pinned`) nao tocam em label, estado
# nem corpo, que sao os tres campos de que a Etapa e o "O que muda" vivem.
ACOES_DE_ISSUE = ("labeled", "unlabeled", "closed", "reopened", "edited")

# Quais Demandas o lote de hora em hora rele.
#
# A lista e a POSITIVA, e nao "tudo menos concluida e cancelada", porque no
# PostgREST um filtro de negacao sobre coluna com NULL descarta as linhas nulas
# em silencio. O teste amarra esta tupla ao complemento de `ESTADOS_FECHADOS`:
# um estado novo que ficasse de fora sumiria da reconciliacao sem erro nenhum.
ESTADOS_DA_RECONCILIACAO = ESTADOS_ABERTOS


def mudanca_da_foto(foto: dict[str, Any]) -> dict[str, Any]:
    """O cache da Demanda para esta foto: Etapa, partes, "O que muda" e carimbo.

    Um lugar so para o SHAPE do cache. Ele e escrito por tres caminhos (vincular,
    webhook e reconciliacao), e montar o dicionario a mao em cada um deles faria
    uma coluna nova nascer preenchida num caminho e parada nos outros dois. Foi
    o que quase aconteceu com o `o_que_muda` da issue #676, que entrou pelo
    `vincular`: sem esta funcao, o bloco que o diretor le congelaria no texto do
    dia do Vinculo e a edicao dele no GitHub nunca chegaria ao card.
    """
    entregues, total = partes_da_foto(foto)
    return {
        "etapa": etapa_da_foto(foto),
        "partes_entregues": entregues,
        "partes_total": total,
        # O texto que o diretor le, lido do GitHub e nunca digitado no app
        # (issue #676, ADR 0054, decisao 7). Em coluna propria, e nao so dentro
        # da foto, porque e dado de leitura da tela: a foto existe para a
        # sincronizacao seguinte saber se algo mudou.
        "o_que_muda": o_que_muda_da_foto(foto),
        "partes": partes_para_o_diretor(foto),
        "github_foto": foto,
        "github_sincronizado_em": datetime.now(UTC).isoformat(),
    }


def demanda_vinculada(supabase, numero: int) -> dict[str, Any] | None:
    """A Demanda que carrega este numero de issue, ou `None`.

    `None` e resposta, e nao erro: o repositorio tem centenas de issues e um
    punhado de Demandas vinculadas, entao a esmagadora maioria das entregas do
    webhook cai aqui e termina em 2xx sem escrever nada.
    """
    result = supabase.table(TABELA_DEMANDAS).select("*").eq("github_issue_numero", numero).execute()
    linhas = result.data or []
    return linhas[0] if linhas else None


def sincronizar_demanda(supabase, demanda: dict[str, Any]) -> bool:
    """Rele a issue vinculada e atualiza o cache da Demanda. `True` se mudou.

    NAO trata excecao: `GithubIndisponivelError` e `IssueNaoEncontradaError` sobem
    para quem chamou, porque o desfeito e diferente nos dois gatilhos. O webhook
    engole e responde 2xx (o GitHub nao reentrega, e insistir nao traria o evento
    de volta); o lote conta a falha e segue para a proxima Demanda.
    """
    numero = demanda.get("github_issue_numero")
    if not numero:
        return False
    numero = int(numero)

    dados = github_client.ler_issue(numero)
    foto = github_client.montar_foto(dados, github_client.ler_sub_issues(numero))
    if not foto_mudou(demanda.get("github_foto"), foto):
        return False

    demanda_id = str(demanda["id"])
    etapa_antes = demanda.get("etapa") or ETAPA_REGISTRADA
    mudanca = mudanca_da_foto(foto)
    supabase.table(TABELA_DEMANDAS).update(mudanca).eq("id", demanda_id).execute()

    if mudanca["etapa"] != etapa_antes:
        supabase.table(TABELA_CONVERSAS).insert(
            linha_de_movimento(
                demanda_id=demanda_id,
                campo="etapa",
                de=etapa_antes,
                para=mudanca["etapa"],
                texto=texto_movimento_etapa(
                    para=mudanca["etapa"],
                    entregues=mudanca["partes_entregues"],
                    total=mudanca["partes_total"],
                ),
            )
        ).execute()
    return True


def reconciliar_vinculos(supabase) -> dict[str, int]:
    """O lote de hora em hora: toda Demanda vinculada que ainda esta aberta.

    Existe porque o webhook e o unico caminho rapido, e ele e perdivel: o GitHub
    exige 2xx em 10 segundos e nao reentrega a entrega que falhou. Um deploy no
    momento errado, uma queda de rede ou um erro nosso somem com o evento, e sem
    esta passagem o card ficaria mentindo ate alguem reparar.

    Devolve `{"lidas", "mudadas", "falhas"}`, que e o que o log conta. Falha numa
    Demanda e contada e registrada com o identificador dela; o lote segue.
    """
    result = (
        supabase.table(TABELA_DEMANDAS)
        .select("*")
        .not_.is_("github_issue_numero", "null")
        .in_("estado", list(ESTADOS_DA_RECONCILIACAO))
        .execute()
    )
    demandas = result.data or []

    mudadas = 0
    falhas = 0
    for demanda in demandas:
        try:
            if sincronizar_demanda(supabase, demanda):
                mudadas += 1
        except Exception:
            # Qualquer causa, de proposito: `except GithubIndisponivelError`
            # deixaria o timeout do PostgREST subir cru e derrubar o lote na
            # metade, com as Demandas seguintes sem reconciliar e sem rastro.
            falhas += 1
            logger.warning(
                "[tecnologia] Falha ao reconciliar a Demanda %s (issue #%s)",
                demanda.get("id"),
                demanda.get("github_issue_numero"),
                exc_info=True,
            )

    if demandas:
        logger.info(
            "[tecnologia] Reconciliação do Vínculo: %s lida(s), %s mudada(s), %s falha(s).",
            len(demandas),
            mudadas,
            falhas,
        )
    return {"lidas": len(demandas), "mudadas": mudadas, "falhas": falhas}
