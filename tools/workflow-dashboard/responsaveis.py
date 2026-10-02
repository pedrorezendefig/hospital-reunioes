"""Agrupamento por responsável da aba Issues do painel (ADR 0061, decisão 5).

Função pura: issues, PRs, mapa PRD -> fatias e o history.json (no shape do
collect.py) entram, grupos por responsável saem. O front só desenha.
"""

from __future__ import annotations

from datetime import datetime, timezone

SECOES = ("em_andamento", "planejada", "aberta", "fechada")
# Mesma régua da Etapa "Planejada" do app (tecnologia_vinculo.LABELS_PLANEJADA).
LABELS_PLANEJADA = ("ready-for-agent", "ready-for-human")


def agrupar_por_responsavel(
    issues: list[dict],
    prs: list[dict],
    fatias_por_prd: dict[int, list[int]],
    history: list[dict],
    agora: datetime | None = None,
) -> dict:
    por_numero = {i["number"]: i for i in issues}
    prds_da_fatia: dict[int, list[int]] = {}
    for prd, fatias in fatias_por_prd.items():
        for n in fatias:
            prds_da_fatia.setdefault(n, []).append(prd)

    grupos: dict[str | None, list[dict]] = {}
    for i in sorted(issues, key=_ordem):
        item = {"number": i["number"], "secao": _secao(i)}
        for quem in _responsaveis(i, prds_da_fatia, por_numero):
            grupos.setdefault(quem, []).append(item)
    # Pessoas em ordem alfabética; "sem responsável" (None) sempre por último.
    ordem = sorted(grupos, key=lambda quem: (quem is None, quem or ""))
    return {"grupos": [{"responsavel": quem, "itens": grupos[quem]} for quem in ordem]}


def _secao(issue: dict) -> str:
    if issue["state"] != "OPEN":
        return "fechada"
    if "in-progress" in issue["labels"]:
        return "em_andamento"
    if set(issue["labels"]) & set(LABELS_PLANEJADA):
        return "planejada"
    return "aberta"


def _ordem(issue: dict) -> tuple:
    """Seção na ordem de SECOES; abertas da mais nova para a mais antiga, fechadas pela data de fechamento."""
    secao = _secao(issue)
    if secao == "fechada":
        fechada = _parse_dt(issue.get("closed_at"))
        return (SECOES.index(secao), -fechada.timestamp() if fechada else 0.0, -issue["number"])
    return (SECOES.index(secao), 0.0, -issue["number"])


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _responsaveis(issue: dict, prds_da_fatia: dict[int, list[int]], por_numero: dict[int, dict]) -> list:
    """Assignees da issue; senão os do PRD pai; senão [None] ("sem responsável")."""
    if issue["assignees"]:
        return sorted(set(issue["assignees"]))
    donos = {
        quem
        for prd in prds_da_fatia.get(issue["number"], [])
        for quem in (por_numero.get(prd) or {}).get("assignees", [])
    }
    return sorted(donos) or [None]
