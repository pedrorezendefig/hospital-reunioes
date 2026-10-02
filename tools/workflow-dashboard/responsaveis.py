"""Agrupamento por responsável da aba Issues do painel (ADR 0061, decisão 5).

Função pura: issues, PRs, mapa PRD -> fatias e o history.json (no shape do
collect.py) entram, grupos por responsável saem. O front só desenha.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

SECOES = ("em_andamento", "planejada", "aberta", "fechada")
# Mesma régua da Etapa "Planejada" do app (tecnologia_vinculo.LABELS_PLANEJADA).
LABELS_PLANEJADA = ("ready-for-agent", "ready-for-human")
# Conclusões de CheckRun que não reprovam; qualquer outra (FAILURE, CANCELLED, TIMED_OUT...) é falha.
CONCLUSOES_OK = ("SUCCESS", "NEUTRAL", "SKIPPED")


def agrupar_por_responsavel(
    issues: list[dict],
    prs: list[dict],
    fatias_por_prd: dict[int, list[int]],
    history: list[dict],
    agora: datetime | None = None,
) -> dict:
    agora = agora or datetime.now(timezone.utc)
    por_numero = {i["number"]: i for i in issues}
    prds_da_fatia: dict[int, list[int]] = {}
    for prd, fatias in fatias_por_prd.items():
        for n in fatias:
            prds_da_fatia.setdefault(n, []).append(prd)
    pr_aberto = _pr_aberto_por_issue(prs)
    versao_da_issue = _versao_por_issue(prs, history)

    itens = []
    for i in issues:
        aberta = i["state"] == "OPEN"
        pr = pr_aberto.get(i["number"]) if aberta else None
        item = {
            "number": i["number"],
            "secao": _secao(i, pr),
            "pr": estado_do_pr(pr, agora) if pr else None,
            "versao": None if aberta else versao_da_issue.get(i["number"]),
        }
        itens.append((_ordem(i, item["secao"]), item, i))

    grupos: dict[str | None, list[dict]] = {}
    for _, item, i in sorted(itens, key=lambda t: t[0]):
        for quem in _responsaveis(i, prds_da_fatia, por_numero):
            grupos.setdefault(quem, []).append(item)
    # Pessoas em ordem alfabética; "sem responsável" (None) sempre por último.
    ordem = sorted(grupos, key=lambda quem: (quem is None, quem or ""))
    return {"grupos": [{"responsavel": quem, "itens": grupos[quem]} for quem in ordem]}


def estado_do_pr(pr: dict, agora: datetime) -> dict:
    """O que o card mostra do PR: CI, mergeável ou conflito e há quantos dias está parado."""
    atualizado = _parse_dt(pr.get("updated_at"))
    return {
        "number": pr["number"],
        "url": pr.get("url"),
        "author": pr.get("author"),
        "ci": pr.get("ci"),
        "merge": _mergeabilidade(pr.get("merge_state")),
        "dias_parado": (agora - atualizado).days if atualizado else None,
    }


def ci_do_rollup(rollup: list[dict] | None) -> str | None:
    """statusCheckRollup do gh resumido em "sucesso", "falha" ou "pendente".

    Falha vence pendente (um check vermelho já reprova o PR); sem nenhum check
    (PR só de docs cai no paths-ignore do CI) devolve None.
    """
    estados = set()
    for c in rollup or []:
        if c.get("__typename") == "StatusContext":
            estado = c.get("state")
            estados.add("sucesso" if estado == "SUCCESS" else "falha" if estado in ("FAILURE", "ERROR") else "pendente")
        elif c.get("status") != "COMPLETED":
            estados.add("pendente")
        else:
            estados.add("sucesso" if c.get("conclusion") in CONCLUSOES_OK else "falha")
    for estado in ("falha", "pendente", "sucesso"):
        if estado in estados:
            return estado
    return None


def _mergeabilidade(merge_state: str | None) -> str:
    """mergeStateStatus do GitHub em três valores.

    DIRTY é conflito. UNKNOWN (o GitHub calcula sob demanda e a primeira
    leitura vem sem resposta) e DRAFT (esconde o conflito) ficam desconhecidos.
    O resto (CLEAN, BLOCKED, BEHIND, UNSTABLE, HAS_HOOKS) não tem conflito.
    """
    if merge_state == "DIRTY":
        return "conflito"
    if merge_state in (None, "UNKNOWN", "DRAFT"):
        return "desconhecido"
    return "mergeavel"


def _versao_por_issue(prs: list[dict], history: list[dict]) -> dict[int, str]:
    """Versão em que cada issue subiu: a do deploy do PR mergeado mais recente que a fecha."""
    versao_do_pr = _versao_por_pr(prs, history)
    versoes: dict[int, str] = {}
    for p in sorted(prs, key=lambda p: p.get("merged_at") or ""):
        if p["number"] in versao_do_pr:
            for n in p["closes"]:
                versoes[n] = versao_do_pr[p["number"]]
    return versoes


def _versao_por_pr(prs: list[dict], history: list[dict]) -> dict[int, str]:
    """Primeiro deploy, a partir do merge, que cita o PR.

    As notas citam PRs como contexto, antes e depois de eles subirem (#751 aparece
    no 0.139.0, horas antes do merge; #688 reaparece no 0.141.0). Deploy anterior ao
    merge não pode ter levado o PR; entre os posteriores, vale o primeiro.
    """
    mergeado_em = {p["number"]: _parse_dt(p.get("merged_at")) for p in prs if p.get("merged_at")}
    deploys = sorted(
        ((at, d) for d in history if d.get("app_version") and (at := _parse_dt(d.get("at")))),
        key=lambda t: t[0],
    )
    versoes: dict[int, str] = {}
    for at, d in deploys:
        for n in _prs_citados(d):
            if n in mergeado_em and n not in versoes and (mergeado_em[n] is None or at >= mergeado_em[n]):
                versoes[n] = d["app_version"]
    return versoes


def _prs_citados(deploy: dict) -> set[int]:
    """Números citados no registro do deploy, no formato que o /ship e o fechar_onda escrevem.

    raw_subject: "(#894)" do squash ou "(#911 #912)" do registro da onda.
    notes: "PR #894", "PRs #911 #912".
    """
    nums: set[int] = set()
    for grupo in re.findall(r"\((#\d+(?:[\s,]+#\d+)*)\)", deploy.get("raw_subject") or ""):
        nums |= {int(n) for n in re.findall(r"#(\d+)", grupo)}
    for grupo in re.findall(r"PRs? (#\d+(?:(?:,\s*|\s+e\s+|\s+)#\d+)*)", deploy.get("notes") or ""):
        nums |= {int(n) for n in re.findall(r"#(\d+)", grupo)}
    return nums


def _pr_aberto_por_issue(prs: list[dict]) -> dict[int, dict]:
    """PR aberto que fecha cada issue; havendo mais de um, o atualizado por último."""
    abertos = sorted((p for p in prs if p["state"] == "OPEN"), key=lambda p: p.get("updated_at") or "")
    return {n: p for p in abertos for n in p["closes"]}


def _secao(issue: dict, pr_aberto: dict | None) -> str:
    if issue["state"] != "OPEN":
        return "fechada"
    if "in-progress" in issue["labels"] or pr_aberto:
        return "em_andamento"
    if set(issue["labels"]) & set(LABELS_PLANEJADA):
        return "planejada"
    return "aberta"


def _ordem(issue: dict, secao: str) -> tuple:
    """Seção na ordem de SECOES; abertas da mais nova para a mais antiga, fechadas pela data de fechamento."""
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
