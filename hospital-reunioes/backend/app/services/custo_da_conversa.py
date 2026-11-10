"""O modelo e o custo da conversa da aba Tecnologia (issue #1439, ADR 0079, decisao 6).

Soma as chamadas de IA gravadas da Demanda em `tecnologia_chamadas_ia`: as
perguntas, o resumo e as rodadas de leitura do codigo. O modelo e o da chamada
mais recente, no nome de exibicao ("Opus 5.5").

Custo nulo quer dizer "nao medido", e sai em dois casos em que somar o que esta
gravado daria um valor menor que o de verdade, com cara de exato:

- alguma chamada com tokens gravou custo zero, que e o sinal do modelo sem
  preco na tabela (`PRECO_POR_MILHAO`);
- a Demanda tem print. A leitura do print (`assistente_tecnologia.descrever_imagem`)
  chama a IA antes de a Demanda receber o print e nao grava a chamada em lugar
  nenhum, entao o custo dela nao esta na tabela (revisao do PR #1443). O print
  apagado pelo cron tambem conta: a leitura aconteceu do mesmo jeito.

O documento nao entra nessa conta (issue #1520): ele e lido pelo extrator, sem
IA, e os turnos que o levam ao agente sao chamadas gravadas como as outras.
"""

from __future__ import annotations

import re

from app.services import tecnologia_anexos
from app.services.planejamento_demanda import TABELA_CHAMADAS_IA

_ID_DO_MODELO = re.compile(r"^claude-([a-z]+)-(\d+)-(\d+)$")


def nome_de_exibicao(modelo: str) -> str:
    """`claude-opus-5-5` vira `Opus 5.5`; o que nao segue o padrao fica como veio."""
    casou = _ID_DO_MODELO.match(modelo or "")
    if not casou:
        return modelo
    familia, maior, menor = casou.groups()
    return f"{familia.capitalize()} {maior}.{menor}"


def _sem_preco(chamada: dict) -> bool:
    tokens = (chamada.get("tokens_entrada") or 0) + (chamada.get("tokens_saida") or 0)
    return tokens > 0 and float(chamada.get("custo_usd") or 0) == 0


def da_demanda(supabase, demanda_id: str) -> dict | None:
    """`{"modelo", "custo_usd"}` da conversa, ou nulo quando nao houve chamada."""
    result = (
        supabase.table(TABELA_CHAMADAS_IA)
        .select("modelo, tokens_entrada, tokens_saida, custo_usd, criado_em")
        .eq("demanda_id", str(demanda_id))
        .order("criado_em")
        .execute()
    )
    chamadas = list(result.data or [])
    if not chamadas:
        return None
    tem_print = any(not tecnologia_anexos.e_documento(linha) for linha in tecnologia_anexos.ler(supabase, demanda_id))
    if any(_sem_preco(c) for c in chamadas) or tem_print:
        custo = None
    else:
        custo = round(sum(float(c.get("custo_usd") or 0) for c in chamadas), 6)
    return {"modelo": nome_de_exibicao(chamadas[-1].get("modelo") or ""), "custo_usd": custo}
