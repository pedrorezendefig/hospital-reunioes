"""Apagar a Demanda (issue #1549, PRD #1548, ADR 0084, decisao 2).

A Demanda que nao vale mais sai do app e vira lapide: a linha fica, com
`apagada_em` e `apagada_por`, para o webhook reconhecer a issue e nao recria-la.
Quem pode apagar e a regra pura `tecnologia.recusa_de_apagar`; aqui mora o que
o Apagar faz.

O card criado fecha antes no GitHub: as partes abertas e depois a issue-raiz,
como nao planejadas, cada uma com o comentario de motivo. A issue nunca e
apagada (o token so tem Issues: write, e o historico das decisoes fica). Se o
GitHub falha, a excecao sobe antes de qualquer escrita no app.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.services import github_client
from app.services.tecnologia import TABELA_DEMANDAS

# A primeira linha marca o comentario como do agente (o /onda-enxuta nao o le
# como comentario de revisor). O repositorio e publico: sem nome de ninguem.
COMENTARIO_DO_APAGAR = (
    "<!-- automacao -->\n"
    "O card foi apagado na aba Tecnologia do app. A issue fecha como não planejada "
    "e fica aqui para o histórico das decisões."
)


def _fechar_no_github(numero: int) -> None:
    """As partes abertas e depois a raiz. A raiz por ultimo: fechada antes, o
    webhook dela levaria a Etapa a Nao sera feita, e um Apagar repetido depois
    de uma falha no meio daria 409."""
    abertas = [
        parte["number"]
        for parte in github_client.ler_sub_issues(numero)
        if isinstance(parte, dict) and parte.get("state") == "open" and isinstance(parte.get("number"), int)
    ]
    for parte in abertas:
        github_client.fechar_como_nao_planejada(parte, comentario=COMENTARIO_DO_APAGAR)
    github_client.fechar_como_nao_planejada(numero, comentario=COMENTARIO_DO_APAGAR)


def apagar(supabase, demanda: dict[str, Any], *, ator: dict[str, Any]) -> None:
    """Faz da Demanda uma lapide. Recebe as guardas da rota ja passadas.

    Levanta `GithubIndisponivelError` ou `GithubNaoConfiguradoError` quando o
    card nao fechou no GitHub, e nesse caso nada mudou no app.
    """
    numero = demanda.get("github_issue_numero")
    if numero:
        _fechar_no_github(int(numero))
    supabase.table(TABELA_DEMANDAS).update(
        {"apagada_em": datetime.now(UTC).isoformat(), "apagada_por": ator["id"]}
    ).eq("id", str(demanda["id"])).execute()
