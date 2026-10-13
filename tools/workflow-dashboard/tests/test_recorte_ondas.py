"""Recorte das ondas (hr-ondas): só os PRDs com onda viva, numa consulta GraphQL e uma lista de PRs abertos.

`gh` e `git` mockados em collect._run. O que se prova: a régua de fases é a mesma do OS
inteiro, a fatia ligada pelo corpo ("Pai: #N") entra, e o custo é de duas chamadas ao gh.
"""

import json
import sys
from pathlib import Path

DASH = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DASH))

import collect  # noqa: E402


def _issue(n, titulo, estado="OPEN", labels=(), body="", bloqueios=(), prs=()):
    return {
        "number": n, "title": titulo, "state": estado, "createdAt": "2026-10-12T10:00:00Z", "closedAt": None,
        "url": f"https://github.com/o/r/issues/{n}", "body": body,
        "labels": {"nodes": [{"name": lb} for lb in labels]}, "assignees": {"nodes": []},
        "author": {"login": "pedro"}, "blockedBy": {"nodes": [{"number": b} for b in bloqueios]},
        "closedByPullRequestsReferences": {"nodes": list(prs)},
    }


PR_ABERTO = {"number": 50, "title": "fatia 11", "state": "OPEN", "mergedAt": None, "headRefName": "feat/x-11",
             "url": "u", "createdAt": "2026-10-12T11:00:00Z", "closedAt": None, "isDraft": False,
             "author": {"login": "pedro"}}
RESPOSTA = {"data": {
    "repository": {"p10": {
        **_issue(10, "PRD: Contas"),
        "subIssues": {"nodes": [
            _issue(11, "fatia 11", labels=["in-progress"], prs=[PR_ABERTO]),
            _issue(12, "fatia 12", labels=["ready-for-agent"], bloqueios=[11]),
        ]},
    }},
    "s10": {"nodes": [
        _issue(13, "pendência humana", labels=["ready-for-human"], body="Pai: #10\n\nimport na virada"),
        _issue(14, "cita o PRD sem ser filha", body="ver o #10"),
    ]},
}}
ABERTOS = [{"number": 50, "statusCheckRollup": [{"__typename": "CheckRun", "name": "ci", "status": "COMPLETED",
            "conclusion": "FAILURE", "startedAt": "2026-10-12T11:01:00Z", "completedAt": "2026-10-12T11:05:00Z"}],
            "mergeStateStatus": "BLOCKED", "reviews": [], "comments": []}]


def _montar(monkeypatch, tmp_path):
    chamadas = []

    def run(cmd, cwd, timeout=None):
        chamadas.append(cmd)
        if cmd[:3] == ["gh", "api", "graphql"]:
            return json.dumps(RESPOSTA)
        if cmd[:3] == ["gh", "pr", "list"]:
            return json.dumps(ABERTOS)
        if cmd[:2] == ["git", "ls-remote"]:
            return ""
        if cmd[:2] == ["git", "log"]:
            return ""
        raise AssertionError(f"chamada inesperada: {cmd}")

    monkeypatch.setattr(collect, "_run", run)
    monkeypatch.setattr(collect, "_spec_json_fresh", lambda root, rel: {"repo": "o/r"} if "state" in rel else {})
    return chamadas


def test_recorte_traz_o_prd_vivo_com_fases_e_a_filha_pelo_corpo(monkeypatch, tmp_path):
    _montar(monkeypatch, tmp_path)
    d = collect.collect_recorte(tmp_path, [10])
    por_n = {i["number"]: i for i in d["github"]["issues"]}
    assert sorted(por_n) == [10, 11, 12, 13]
    assert por_n[10]["is_prd"] and por_n[13]["parent"] == 10 and por_n[12]["blocked_by"] == [11]
    f = d["fases"]["issues"]
    assert f[11]["fase"] == "pr_aberto" and f[11]["pr"] == 50 and f[11]["sinal"]["ci"] == "vermelho"
    assert f[12]["fase"] == "bloqueada" and f[13]["fase"] == "humana"
    assert d["fases"]["ondas"][10] == [[11, 13], [12]]


def test_recorte_custa_duas_chamadas_ao_gh(monkeypatch, tmp_path):
    chamadas = _montar(monkeypatch, tmp_path)
    collect.collect_recorte(tmp_path, [10])
    gh = [c for c in chamadas if c[0] == "gh"]
    assert [c[:3] for c in gh] == [["gh", "api", "graphql"], ["gh", "pr", "list"]]
    assert "--state" in gh[1] and gh[1][gh[1].index("--state") + 1] == "open"


def test_recorte_sem_prd_nao_chama_o_github(monkeypatch, tmp_path):
    chamadas = _montar(monkeypatch, tmp_path)
    d = collect.collect_recorte(tmp_path, [])
    assert d["github"]["issues"] == [] and not [c for c in chamadas if c[0] == "gh"]
