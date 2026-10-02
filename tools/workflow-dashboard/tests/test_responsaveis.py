"""Testes do módulo responsaveis: o agrupamento por responsável do painel.

Comportamento externo apenas: issues, PRs, mapa PRD -> fatias e o history.json
(no shape do collect.py) entram, grupos por responsável saem. Sem rede, sem gh.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from responsaveis import agrupar_por_responsavel, ci_do_rollup, estado_do_pr  # noqa: E402

AGORA = datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)


def _issue(number, *, state="OPEN", labels=(), assignees=(), closed_at=None):
    """Issue no shape que o collect.py entrega ao módulo."""
    return {
        "number": number,
        "title": f"Fatia #{number}",
        "state": state,
        "labels": list(labels),
        "assignees": list(assignees),
        "closed_at": closed_at,
        "url": f"https://github.com/x/y/issues/{number}",
    }


def _agrupar(issues, prs=(), fatias_por_prd=None, history=()):
    return agrupar_por_responsavel(list(issues), list(prs), fatias_por_prd or {}, list(history), agora=AGORA)


def _numeros_por_grupo(resultado):
    return {g["responsavel"]: [i["number"] for i in g["itens"]] for g in resultado["grupos"]}


def test_issue_com_assignee_entra_no_grupo_dele():
    resultado = _agrupar([_issue(11, assignees=["ana"])])

    assert _numeros_por_grupo(resultado) == {"ana": [11]}


def test_fatia_sem_assignee_herda_o_dono_do_prd_pai():
    issues = [_issue(10, assignees=["bia"]), _issue(11), _issue(12, assignees=["ana"])]

    resultado = _agrupar(issues, fatias_por_prd={10: [11, 12]})

    grupos = _numeros_por_grupo(resultado)
    assert grupos["bia"] == [11, 10]
    assert grupos["ana"] == [12]


def test_sem_assignee_nem_dono_do_prd_cai_em_sem_responsavel_no_fim():
    issues = [_issue(10), _issue(11), _issue(20, assignees=["caio"]), _issue(30)]

    resultado = _agrupar(issues, fatias_por_prd={10: [11]})

    assert [g["responsavel"] for g in resultado["grupos"]] == ["caio", None]
    assert _numeros_por_grupo(resultado)[None] == [30, 11, 10]


def test_issue_com_dois_assignees_aparece_nos_dois_grupos():
    resultado = _agrupar([_issue(11, assignees=["bia", "ana"])])

    assert _numeros_por_grupo(resultado) == {"ana": [11], "bia": [11]}


def test_prd_com_dois_donos_leva_a_fatia_sem_assignee_aos_dois_grupos():
    issues = [_issue(10, assignees=["ana", "bia"]), _issue(11)]

    resultado = _agrupar(issues, fatias_por_prd={10: [11]})

    assert _numeros_por_grupo(resultado) == {"ana": [11, 10], "bia": [11, 10]}


def test_ordem_no_grupo_em_andamento_planejadas_demais_abertas_e_fechadas_recentes_primeiro():
    issues = [
        _issue(1, state="CLOSED", assignees=["ana"], closed_at="2026-09-20T10:00:00Z"),
        _issue(2, state="CLOSED", assignees=["ana"], closed_at="2026-09-01T10:00:00Z"),
        _issue(3, labels=["needs-triage"], assignees=["ana"]),
        _issue(4, labels=["ready-for-agent"], assignees=["ana"]),
        _issue(5, labels=["in-progress"], assignees=["ana"]),
        _issue(6, labels=["ready-for-human"], assignees=["ana"]),
        _issue(7, labels=["blocked"], assignees=["ana"]),
    ]

    itens = _agrupar(issues)["grupos"][0]["itens"]

    assert [(i["number"], i["secao"]) for i in itens] == [
        (5, "em_andamento"),
        (6, "planejada"),
        (4, "planejada"),
        (7, "aberta"),
        (3, "aberta"),
        (1, "fechada"),
        (2, "fechada"),
    ]


def _pr(number, *, closes, state="OPEN", merged_at=None, author="ana", ci=None, merge_state="UNKNOWN",
        updated_at="2026-10-01T12:00:00Z"):
    """PR no shape que o collect.py entrega ao módulo."""
    return {
        "number": number,
        "title": f"PR #{number}",
        "state": state,
        "merged_at": merged_at,
        "url": f"https://github.com/x/y/pull/{number}",
        "closes": list(closes),
        "author": author,
        "ci": ci,
        "merge_state": merge_state,
        "updated_at": updated_at,
    }


def test_em_andamento_traz_o_pr_aberto_que_a_fecha_com_ci_merge_e_dias_parado():
    issues = [_issue(5, labels=["in-progress"], assignees=["ana"])]
    prs = [
        _pr(40, closes=[5], state="MERGED", merged_at="2026-09-01T10:00:00Z", ci="sucesso", merge_state="CLEAN"),
        _pr(50, closes=[5], author="bia", ci="falha", merge_state="DIRTY", updated_at="2026-09-29T09:00:00Z"),
    ]

    item = _agrupar(issues, prs=prs)["grupos"][0]["itens"][0]

    assert item["pr"] == {
        "number": 50,
        "url": "https://github.com/x/y/pull/50",
        "author": "bia",
        "ci": "falha",
        "merge": "conflito",
        "dias_parado": 3,
    }


def test_issue_aberta_com_pr_aberto_conta_como_em_andamento_mesmo_sem_label():
    issues = [_issue(6, labels=["ready-for-agent"], assignees=["ana"]), _issue(7, assignees=["ana"])]

    itens = _agrupar(issues, prs=[_pr(60, closes=[6])])["grupos"][0]["itens"]

    assert [(i["number"], i["secao"], (i["pr"] or {}).get("number")) for i in itens] == [
        (6, "em_andamento", 60),
        (7, "aberta", None),
    ]


def _check(status="COMPLETED", conclusion="SUCCESS"):
    return {"__typename": "CheckRun", "name": "x", "status": status, "conclusion": conclusion}


def _contexto(state):
    return {"__typename": "StatusContext", "context": "x", "state": state}


@pytest.mark.parametrize(
    "rollup, esperado",
    [
        ([_check(), _check(conclusion="SKIPPED"), _contexto("SUCCESS")], "sucesso"),
        ([_check(), _check(conclusion="FAILURE")], "falha"),
        ([_check(), _contexto("ERROR")], "falha"),
        ([_check(status="IN_PROGRESS", conclusion=""), _check(conclusion="FAILURE")], "falha"),
        ([_check(), _check(status="IN_PROGRESS", conclusion="")], "pendente"),
        ([_check(), _check(status="QUEUED", conclusion=None)], "pendente"),
        ([_check(), _contexto("PENDING")], "pendente"),
        ([], None),
        (None, None),
    ],
)
def test_ci_do_rollup_resume_os_checks_em_sucesso_falha_ou_pendente(rollup, esperado):
    assert ci_do_rollup(rollup) == esperado


@pytest.mark.parametrize(
    "merge_state, esperado",
    [("CLEAN", "mergeavel"), ("BLOCKED", "mergeavel"), ("DIRTY", "conflito"), ("UNKNOWN", "desconhecido")],
)
def test_estado_do_pr_separa_mergeavel_de_conflito(merge_state, esperado):
    pr = _pr(70, closes=[7], merge_state=merge_state, updated_at="2026-10-02T11:00:00Z")

    estado = estado_do_pr(pr, AGORA)

    assert estado["merge"] == esperado
    assert estado["dias_parado"] == 0


def _deploy(at, versao, *, raw_subject="chore: x", notes=""):
    """Entrada do history.json (só os campos que importam aqui)."""
    return {"at": at, "app_version": versao, "raw_subject": raw_subject, "notes": notes, "result": "healthy"}


def _fechada_com_pr(number, pr, merged_at):
    issue = _issue(number, state="CLOSED", assignees=["ana"], closed_at=merged_at)
    return issue, _pr(pr, closes=[number], state="MERGED", merged_at=merged_at)


def _versoes(resultado):
    return {i["number"]: i["versao"] for g in resultado["grupos"] for i in g["itens"]}


def test_fechada_mostra_a_versao_do_deploy_do_pr_que_a_fechou():
    issue, pr = _fechada_com_pr(770, 894, "2026-09-28T14:00:00Z")
    history = [
        _deploy("2026-09-28T11:36:40-03:00", "0.156.6", raw_subject="fix(tecnologia): recuo (#894)"),
        _deploy("2026-09-27T20:00:13-03:00", "0.156.5", raw_subject="fix(backend): ia (#892)"),
    ]

    resultado = _agrupar([issue, _issue(9, assignees=["ana"])], prs=[pr], history=history)

    assert _versoes(resultado) == {770: "0.156.6", 9: None}


def test_fechada_sem_o_pr_no_history_fica_sem_versao():
    issue, pr = _fechada_com_pr(770, 894, "2026-09-28T14:00:00Z")
    history = [_deploy("2026-09-28T11:36:40-03:00", "0.156.5", raw_subject="fix(backend): ia (#892)")]

    assert _versoes(_agrupar([issue], prs=[pr], history=history)) == {770: None}


def test_mencao_ao_pr_em_deploy_anterior_ao_merge_nao_vira_versao():
    # Caso real do PR #751: o deploy 0.139.0 cita o PR nas notas como contexto,
    # horas antes do merge; quem levou o PR ao ar foi o 0.140.0.
    issue, pr = _fechada_com_pr(729, 751, "2026-09-17T03:25:31Z")
    history = [
        _deploy("2026-09-17T00:30:00-03:00", "0.140.0", raw_subject="feat(tecnologia): falar (#751)"),
        _deploy("2026-09-16T22:35:00-03:00", "0.139.0", raw_subject="feat(extracao): ler (#765)",
                notes="A issue #758 nasceu das revisoes do PR #751."),
    ]

    assert _versoes(_agrupar([issue], prs=[pr], history=history)) == {729: "0.140.0"}


def test_mencao_ao_pr_em_deploy_posterior_nao_troca_a_versao_em_que_subiu():
    # Caso real do PR #688: subiu no 0.127.0 e o 0.141.0 cita o PR nas notas.
    issue, pr = _fechada_com_pr(677, 688, "2026-09-10T20:00:00Z")
    history = [
        _deploy("2026-09-17T09:42:00-03:00", "0.141.0", raw_subject="feat: print (#771)",
                notes="Tres rodadas de correcao, como no PR #688."),
        _deploy("2026-09-10T18:28:00-03:00", "0.127.0", raw_subject="feat(tecnologia): botao (#688)"),
    ]

    assert _versoes(_agrupar([issue], prs=[pr], history=history)) == {677: "0.127.0"}


def test_registro_da_onda_com_varios_prs_da_versao_a_cada_um():
    a, pr_a = _fechada_com_pr(905, 911, "2026-10-02T10:00:00Z")
    b, pr_b = _fechada_com_pr(906, 912, "2026-10-02T10:05:00Z")
    history = [
        _deploy("2026-10-02T09:00:00-03:00", "0.157.0", raw_subject="chore(deploy): registro da onda s1 (#911 #912)",
                notes="onda-enxuta s1: PRs #911 #912. Um push, um build."),
    ]

    assert _versoes(_agrupar([a, b], prs=[pr_a, pr_b], history=history)) == {905: "0.157.0", 906: "0.157.0"}


# ---------- Coletor: o gh entra falso, nada de rede ----------

RAIZ = Path(__file__).resolve().parents[3]

PR_GH = {
    "number": 50,
    "title": "feat: x",
    "state": "OPEN",
    "mergedAt": None,
    "headRefName": "feat/x-11",
    "closingIssuesReferences": [{"number": 11}],
    "url": "https://github.com/x/y/pull/50",
    "author": {"login": "bia", "is_bot": False},
    "statusCheckRollup": [_check(), _check(conclusion="FAILURE")],
    "mergeStateStatus": "DIRTY",
    "updatedAt": "2026-09-29T09:00:00Z",
}

ISSUES_GH = [
    {"number": 10, "title": "PRD: esteira", "state": "OPEN", "labels": [], "createdAt": "2026-09-01T00:00:00Z",
     "closedAt": None, "assignees": [{"login": "ana"}], "body": "", "url": "https://github.com/x/y/issues/10"},
    {"number": 11, "title": "Fatia", "state": "OPEN", "labels": [{"name": "in-progress"}],
     "createdAt": "2026-09-02T00:00:00Z", "closedAt": None, "assignees": [], "body": "",
     "url": "https://github.com/x/y/issues/11"},
]


def _gh_falso(chamadas):
    import json

    def run(cmd, cwd, timeout=None):
        chamadas.append(cmd)
        if cmd[:3] == ["gh", "issue", "list"]:
            return "[]" if "--label" in cmd else json.dumps(ISSUES_GH)
        if cmd[:3] == ["gh", "pr", "list"]:
            return json.dumps([PR_GH])
        if cmd[:3] == ["gh", "api", "graphql"]:
            pagina = {"pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": []}
            if "subIssues" in cmd[4]:
                pagina["nodes"] = [{"number": 10, "subIssues": {"nodes": [{"number": 11}]}}]
            return json.dumps({"data": {"repository": {"issues": pagina}}})
        raise RuntimeError("offline no teste")

    return run


def test_coletor_traz_autor_ci_merge_e_updated_at_no_mesmo_gh_pr_list(monkeypatch):
    import collect

    chamadas = []
    monkeypatch.setattr(collect, "_run", _gh_falso(chamadas))

    prs = collect._gh_prs(RAIZ)

    assert len(chamadas) == 1
    assert chamadas[0][:3] == ["gh", "pr", "list"]
    assert prs[0]["author"] == "bia"
    assert prs[0]["ci"] == "falha"
    assert prs[0]["merge_state"] == "DIRTY"
    assert prs[0]["updated_at"] == "2026-09-29T09:00:00Z"


def test_api_data_entrega_os_grupos_sem_metrica_por_pessoa(monkeypatch):
    import collect

    chamadas = []
    monkeypatch.setattr(collect, "_run", _gh_falso(chamadas))

    data = collect.collect(RAIZ)

    assert sum(1 for c in chamadas if c[:3] == ["gh", "pr", "list"]) == 1
    grupos = data["responsaveis"]["grupos"]
    assert [g["responsavel"] for g in grupos] == ["ana"]
    assert [(i["number"], i["secao"]) for i in grupos[0]["itens"]] == [(11, "em_andamento"), (10, "aberta")]
    assert grupos[0]["itens"][0]["pr"]["ci"] == "falha"
    assert grupos[0]["itens"][0]["pr"]["merge"] == "conflito"
    # Só o agrupamento: nada de lead time nem volume por pessoa (ADR 0061, decisão 5).
    assert all(set(g) == {"responsavel", "itens"} for g in grupos)
    assert set(data["responsaveis"]) == {"grupos"}


def test_api_data_sem_gh_deixa_responsaveis_vazio(monkeypatch):
    import collect

    def sem_gh(cmd, cwd, timeout=None):
        raise FileNotFoundError("gh")

    monkeypatch.setattr(collect, "_run", sem_gh)

    assert collect.collect(RAIZ)["responsaveis"] is None
