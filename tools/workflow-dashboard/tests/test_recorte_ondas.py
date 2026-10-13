"""Recorte das ondas (hr-ondas): os PRDs com onda viva ou com PR aberto, em três chamadas ao gh.

`gh` e `git` mockados em collect._run. O que se prova: a régua de fases é a mesma do OS
inteiro, a fatia ligada pelo corpo ("Pai: #N") entra, o PRD de um PR aberto entra sem sessão
viva (trabalho de um sócio, uma /pegar-issue à mão), e o custo é de três chamadas ao gh.
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


def _montar(monkeypatch, tmp_path, abertos=(), em_andamento=(), resposta=RESPOSTA):
    chamadas = []
    descoberta = {"data": {"repository": {"pullRequests": {"nodes": list(abertos)},
                                          "issues": {"nodes": list(em_andamento)}}}}

    def run(cmd, cwd, timeout=None):
        chamadas.append(cmd)
        if cmd[:3] == ["gh", "api", "graphql"] and "pullRequests(states:OPEN" in " ".join(cmd):
            return json.dumps(descoberta)
        if cmd[:3] == ["gh", "api", "graphql"]:
            return json.dumps(resposta)
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


def test_recorte_custa_tres_chamadas_ao_gh(monkeypatch, tmp_path):
    chamadas = _montar(monkeypatch, tmp_path)
    collect.collect_recorte(tmp_path, [10])
    gh = [c for c in chamadas if c[0] == "gh"]
    assert [c[:3] for c in gh] == [["gh", "api", "graphql"], ["gh", "api", "graphql"], ["gh", "pr", "list"]]
    assert "--state" in gh[2] and gh[2][gh[2].index("--state") + 1] == "open"


def test_prd_de_pr_aberto_entra_sem_sessao_viva(monkeypatch, tmp_path):
    pai_nativo = {"number": 70, "closingIssuesReferences": {"nodes": [{"number": 11, "body": "", "parent": {"number": 10}}]}}
    pai_no_corpo = {"number": 71, "closingIssuesReferences": {"nodes": [{"number": 13, "body": "Pai: #10", "parent": None}]}}
    solta = {"number": 72, "closingIssuesReferences": {"nodes": [{"number": 99, "body": "", "parent": None}]}}
    for pr in (pai_nativo, pai_no_corpo):
        chamadas = _montar(monkeypatch, tmp_path, abertos=[pr, solta])
        d = collect.collect_recorte(tmp_path, [])
        recorte = [c for c in chamadas if c[:3] == ["gh", "api", "graphql"]][1][-1]
        assert "p10:" in recorte and "p99:" not in recorte
        assert d["github"]["prds"] == [10] and d["fases"]["issues"][11]["fase"] == "pr_aberto"


def test_recorte_sem_prd_e_sem_pr_aberto_so_pergunta_os_prs_abertos(monkeypatch, tmp_path):
    chamadas = _montar(monkeypatch, tmp_path)
    d = collect.collect_recorte(tmp_path, [])
    gh = [c for c in chamadas if c[0] == "gh"]
    assert d["github"]["issues"] == [] and len(gh) == 1 and "pullRequests(states:OPEN" in " ".join(gh[0])


def test_issue_sem_prd_entra_pelo_pr_aberto_pelo_label_e_pela_fila_da_sessao(monkeypatch, tmp_path):
    """A #1191 (sem PRD pai, PR aberto, fila de uma sessão viva) sumia do painel: entra solta."""
    pr_da_solta = {"number": 72, "closingIssuesReferences": {"nodes": [{"number": 99, "body": "", "parent": None}]}}
    rotulada = {"number": 98, "body": "", "parent": None}
    resposta = {"data": {"repository": {
        "i97": {**_issue(97, "na fila da sessão"), "parent": None},
        "i98": {**_issue(98, "em andamento", labels=["in-progress"]), "parent": None},
        "i99": {**_issue(99, "fix solto", prs=[PR_ABERTO]), "parent": None},
        "i96": {**_issue(96, "fatia de um PRD fora do recorte"), "parent": {"number": 80}},
    }}}
    chamadas = _montar(monkeypatch, tmp_path, abertos=[pr_da_solta], em_andamento=[rotulada], resposta=resposta)
    d = collect.collect_recorte(tmp_path, [], soltas=[97, 96])
    gh = [c for c in chamadas if c[0] == "gh"]
    assert len(gh) == 3 and all(f"i{n}:" in gh[1][-1] for n in (96, 97, 98, 99))
    por_n = {i["number"]: i for i in d["github"]["issues"]}
    assert sorted(por_n) == [97, 98, 99] and d["github"]["prds"] == []
    assert not any(i["is_prd"] or i["parent"] for i in por_n.values())
    f = d["fases"]["issues"]
    assert f[99]["fase"] == "pr_aberto" and f[99]["pr"] == 50 and f[98]["fase"] == "em_andamento"
