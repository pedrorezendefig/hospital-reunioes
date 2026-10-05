"""Testes do módulo fases: a régua de nove fases da issue e as seis do PR (ADR 0062).

Comportamento externo apenas: issues, PRs, deploys do history.json e branches
remotas (no shape do collect.py) entram; fase por issue, fase por PR, timeline,
ondas por PRD e contagens do funil saem. Sem rede, sem gh, sem filesystem.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fases import montar_fases, timeline_da_issue, vereditos_dos_comentarios  # noqa: E402

AGORA = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)


def _issue(
    number,
    *,
    state="OPEN",
    labels=(),
    assignees=(),
    author="ana",
    blocked_by=(),
    children=(),
    is_prd=False,
    created_at="2026-10-01T10:00:00Z",
    closed_at=None,
):
    """Issue no shape que o collect.py entrega ao módulo."""
    return {
        "number": number,
        "title": f"Fatia #{number}",
        "state": state,
        "labels": list(labels),
        "assignees": list(assignees),
        "author": author,
        "blocked_by": sorted(blocked_by),
        "children": sorted(children),
        "is_prd": is_prd,
        "created_at": created_at,
        "closed_at": closed_at,
    }


def _pr(
    number,
    closes,
    *,
    state="OPEN",
    created_at="2026-10-03T10:00:00Z",
    closed_at=None,
    merged_at=None,
    head_ref=None,
    author="bia",
    checks=(),
    merge_state=None,
    reviews=(),
    vereditos=(),
):
    """PR no shape que o collect.py entrega (checks e veredito só nos abertos)."""
    return {
        "number": number,
        "title": f"PR #{number}",
        "state": state,
        "created_at": created_at,
        "closed_at": closed_at,
        "merged_at": merged_at,
        "head_ref": head_ref or f"feat/x-{closes[0] if closes else number}",
        "author": author,
        "is_draft": False,
        "url": f"https://github.com/x/y/pull/{number}",
        "closes": list(closes),
        "checks": list(checks),
        "merge_state": merge_state,
        "reviews": list(reviews),
        "comentarios": len(vereditos),
        "vereditos": list(vereditos),
    }


def _check(conclusao="SUCCESS", *, status="COMPLETED", inicio="2026-10-03T10:05:00Z", fim="2026-10-03T10:20:00Z"):
    return {
        "nome": "CI",
        "status": status,
        "conclusao": conclusao,
        "inicio": inicio,
        "fim": fim if status == "COMPLETED" else None,
    }


def _deploy(versao, at, texto, duracao=None):
    """Deploy no shape do history.json; o texto cita PRs e issues como o rabo escreve."""
    return {
        "app_version": versao,
        "at": at,
        "result": "healthy",
        "subject": texto,
        "raw_subject": "chore(deploy): registro",
        "notes": "",
        "duration_seconds": duracao,
    }


def _merged(number, closes, merged_at="2026-10-04T10:00:00Z"):
    return _pr(number, closes, state="MERGED", merged_at=merged_at, closed_at=merged_at)


def _fase(issue, *, outras=(), prs=(), deploys=(), branches=()):
    fases = montar_fases([issue, *outras], list(prs), list(deploys), list(branches), agora=AGORA)
    return fases["issues"][issue["number"]]


# ---------- fase da issue: um caso positivo por fase ----------


def test_needs_triage_fica_em_triagem():
    assert _fase(_issue(1, labels=["needs-triage"]))["fase"] == "triagem"


def test_ready_for_agent_sem_dono_e_sem_bloqueio_fica_na_fila():
    assert _fase(_issue(2, labels=["ready-for-agent"]))["fase"] == "fila"


def test_issue_com_claim_fica_em_andamento():
    issue = _issue(3, labels=["in-progress"], assignees=["bia"])
    assert _fase(issue)["fase"] == "em_andamento"


def test_bloqueadora_aberta_deixa_a_issue_bloqueada():
    issue = _issue(4, labels=["ready-for-agent"], blocked_by=[5])
    assert _fase(issue, outras=[_issue(5, labels=["ready-for-agent"])])["fase"] == "bloqueada"


def test_ready_for_human_fica_na_fase_humana():
    assert _fase(_issue(6, labels=["ready-for-human"]))["fase"] == "humana"


def test_fechada_sem_pr_fica_encerrada_sem_pr():
    issue = _issue(7, state="CLOSED", labels=["wontfix"], closed_at="2026-10-02T10:00:00Z")
    assert _fase(issue)["fase"] == "encerrada_sem_pr"


def test_pr_aberto_que_fecha_a_issue_poe_a_issue_em_pr_aberto():
    issue = _issue(8, labels=["in-progress"], assignees=["bia"])
    fase = _fase(issue, prs=[_pr(108, [8])])
    assert fase["fase"] == "pr_aberto"
    assert fase["pr"] == 108


def test_pr_mergeado_com_versao_no_history_poe_a_issue_em_producao():
    issue = _issue(9, state="CLOSED", closed_at="2026-10-04T10:00:00Z")
    deploys = [_deploy("0.162.0", "2026-10-04T10:20:00-03:00", "PR #109, issue #9: algo")]
    fase = _fase(issue, prs=[_merged(109, [9])], deploys=deploys)
    assert fase["fase"] == "em_producao"
    assert fase["versao"] == "0.162.0"
    assert fase["em_producao_em"] == "2026-10-04T10:20:00-03:00"


def test_mergeada_sem_versao_no_history_fica_mergeada():
    issue = _issue(10, state="CLOSED", closed_at="2026-10-04T10:00:00Z")
    outro = [_deploy("0.161.0", "2026-10-03T09:00:00-03:00", "PR #50, issue #40: antes do merge")]
    fase = _fase(issue, prs=[_merged(110, [10])], deploys=outro)
    assert fase["fase"] == "mergeada"
    assert fase["versao"] is None


def test_issue_aberta_sem_label_de_triagem_cai_em_triagem():
    assert _fase(_issue(11, labels=["type:fix"]))["fase"] == "triagem"


# ---------- precedência: cada fase vence a de baixo que também vale ----------

DEPLOY_DO_120 = _deploy("0.162.0", "2026-10-04T12:00:00-03:00", "PR #120, issue #20")


def test_ready_for_human_vence_tudo():
    issue = _issue(
        20,
        state="CLOSED",
        labels=["ready-for-human", "in-progress", "ready-for-agent"],
        assignees=["bia"],
        blocked_by=[21],
    )
    prs = [_merged(120, [20]), _pr(121, [20])]
    fase = _fase(issue, outras=[_issue(21)], prs=prs, deploys=[DEPLOY_DO_120], branches=["feat/x-20"])
    assert fase["fase"] == "humana"


def test_encerrada_sem_pr_vence_pr_aberto_e_claim():
    issue = _issue(22, state="CLOSED", labels=["in-progress"], assignees=["bia"])
    assert _fase(issue, prs=[_pr(122, [22])])["fase"] == "encerrada_sem_pr"


def test_em_producao_vence_pr_aberto_de_issue_reaberta():
    issue = _issue(20, labels=["in-progress"], assignees=["bia"])
    fase = _fase(issue, prs=[_merged(120, [20]), _pr(121, [20])], deploys=[DEPLOY_DO_120])
    assert fase["fase"] == "em_producao"


def test_mergeada_vence_pr_aberto():
    issue = _issue(23, labels=["in-progress"], assignees=["bia"])
    assert _fase(issue, prs=[_merged(123, [23]), _pr(124, [23])])["fase"] == "mergeada"


def test_pr_aberto_vence_bloqueio():
    issue = _issue(24, labels=["in-progress"], assignees=["bia"], blocked_by=[25])
    assert _fase(issue, outras=[_issue(25)], prs=[_pr(125, [24])])["fase"] == "pr_aberto"


def test_bloqueada_vence_claim():
    issue = _issue(26, labels=["in-progress"], assignees=["bia"], blocked_by=[27])
    assert _fase(issue, outras=[_issue(27)])["fase"] == "bloqueada"


def test_em_andamento_vence_fila():
    issue = _issue(28, labels=["ready-for-agent"], assignees=["bia"])
    assert _fase(issue)["fase"] == "em_andamento"


def test_fila_vence_triagem():
    assert _fase(_issue(29, labels=["ready-for-agent", "needs-info"]))["fase"] == "fila"


# ---------- casos obrigatórios da issue #941 ----------


def test_bloqueadora_fechada_nao_bloqueia():
    issue = _issue(30, labels=["ready-for-agent"], blocked_by=[31])
    fechada = _issue(31, state="CLOSED", closed_at="2026-10-02T10:00:00Z")
    assert _fase(issue, outras=[fechada])["fase"] == "fila"


def test_pr_fechado_sem_merge_seguido_de_pr_novo_marca_tentativa_anterior():
    issue = _issue(32, labels=["in-progress"], assignees=["bia"])
    velho = _pr(132, [32], state="CLOSED", created_at="2026-10-02T10:00:00Z", closed_at="2026-10-02T15:00:00Z")
    novo = _pr(133, [32], created_at="2026-10-03T10:00:00Z")
    fase = _fase(issue, prs=[novo, velho])
    assert fase["fase"] == "pr_aberto"
    assert fase["pr"] == 133
    assert fase["tentativas"] == [132]
    assert fase["sinal"]["tentativa_anterior"] is True


def test_branch_remota_com_o_numero_e_sem_pr_marca_branch_criada():
    issue = _issue(33, labels=["in-progress"], assignees=["bia"])
    fase = _fase(issue, branches=["main", "feat/fases-do-painel-33", "feat/outra-133"])
    assert fase["fase"] == "em_andamento"
    assert fase["sub"] == "branch_criada"
    assert fase["branch"] == "feat/fases-do-painel-33"


def test_branch_de_outro_numero_com_o_mesmo_final_nao_conta():
    issue = _issue(34, labels=["in-progress"], assignees=["bia"])
    fase = _fase(issue, branches=["feat/outra-134", "feat/x34"])
    assert fase["sub"] is None
    assert fase["branch"] is None


def test_branch_que_ja_tem_pr_nao_marca_branch_criada():
    issue = _issue(35, labels=["in-progress"], assignees=["bia"])
    fechado = _pr(135, [35], state="CLOSED", closed_at="2026-10-02T15:00:00Z", head_ref="feat/x-35")
    fase = _fase(issue, prs=[fechado], branches=["feat/x-35"])
    assert fase["fase"] == "em_andamento"
    assert fase["sub"] is None


def test_merge_anterior_ao_historico_conta_como_em_producao_sem_versao():
    # history.json guardou só os 50 últimos deploys até a #939: o merge antigo já subiu
    issue = _issue(36, state="CLOSED", closed_at="2026-01-01T10:00:00Z")
    deploys = [_deploy("0.135.0", "2026-09-15T18:32:00-03:00", "PR #800")]
    fase = _fase(issue, prs=[_merged(136, [36], merged_at="2026-01-01T10:00:00Z")], deploys=deploys)
    assert fase["fase"] == "em_producao"
    assert fase["versao"] is None


# ---------- veredito dos agentes revisores ----------

MARCADOR = "<!-- automacao -->\n"


def _comentario(corpo, em="2026-10-04T10:00:00Z"):
    return {"author": "pedro", "created_at": em, "body": corpo}


def test_veredito_so_conta_no_comentario_com_marcador_de_automacao():
    comentarios = [
        _comentario("Achei bom.\nVEREDITO: LIMPO"),
        _comentario(
            MARCADOR + "## Veredito da revisão\n\n**must-fix**\n- nada\n\nVEREDITO: LIMPO", em="2026-10-04T11:00:00Z"
        ),
        _comentario(
            MARCADOR + "## Veredito de segurança\n\nVEREDITO SEGURANCA: MUST-FIX (2)", em="2026-10-04T12:00:00Z"
        ),
        _comentario(MARCADOR + "Corretor: os dois must-fix fechados.", em="2026-10-04T13:00:00Z"),
    ]
    assert vereditos_dos_comentarios(comentarios) == [
        {"tipo": "revisao", "valor": "limpo", "em": "2026-10-04T11:00:00Z"},
        {"tipo": "seguranca", "valor": "must_fix", "em": "2026-10-04T12:00:00Z"},
    ]


# ---------- fase do PR ----------


def _fase_pr(pr, *, deploys=()):
    return montar_fases([], [pr], list(deploys), [], agora=AGORA)["prs"][pr["number"]]


def _limpo(em="2026-10-06T12:00:00Z", tipo="revisao"):
    return {"tipo": tipo, "valor": "limpo", "em": em}


def _must_fix(em="2026-10-06T12:00:00Z", tipo="revisao"):
    return {"tipo": tipo, "valor": "must_fix", "em": em}


def test_pr_sem_check_fica_aberto_sem_ci_desde_a_abertura():
    fase = _fase_pr(_pr(200, [1], created_at="2026-10-03T10:00:00Z"))
    assert fase["fase"] == "aberto_sem_ci"
    assert fase["desde"] == "2026-10-03T10:00:00Z"
    assert fase["dias_na_coluna"] == 7


def test_ci_rodando_ainda_e_aberto_sem_ci():
    checks = [_check(), _check(None, status="IN_PROGRESS", inicio="2026-10-08T12:00:00Z")]
    fase = _fase_pr(_pr(201, [1], checks=checks))
    assert fase["fase"] == "aberto_sem_ci"
    assert fase["ci"] == "pendente"


def test_check_vermelho_poe_o_pr_em_ci_vermelho_desde_a_falha():
    checks = [_check(), _check("FAILURE", fim="2026-10-05T12:00:00Z")]
    fase = _fase_pr(_pr(202, [1], checks=checks, vereditos=[_limpo()]))
    assert fase["fase"] == "ci_vermelho"
    assert fase["desde"] == "2026-10-05T12:00:00Z"
    assert fase["dias_na_coluna"] == 5


def test_ci_verde_sem_veredito_espera_o_revisor_desde_o_fim_do_ci():
    checks = [_check(fim="2026-10-04T12:00:00Z"), _check(fim="2026-10-08T12:00:00Z")]
    fase = _fase_pr(_pr(203, [1], checks=checks))
    assert fase["fase"] == "esperando_revisor"
    assert fase["ci"] == "verde"
    assert fase["desde"] == "2026-10-08T12:00:00Z"
    assert fase["dias_na_coluna"] == 2


def test_ci_verde_e_veredito_limpo_fica_verde_esperando_merge_desde_o_veredito():
    pr = _pr(204, [1], checks=[_check(fim="2026-10-04T12:00:00Z")], vereditos=[_limpo("2026-10-09T12:00:00Z")])
    fase = _fase_pr(pr)
    assert fase["fase"] == "verde_esperando_merge"
    assert fase["veredito"] == "limpo"
    assert fase["desde"] == "2026-10-09T12:00:00Z"
    assert fase["dias_na_coluna"] == 1


def test_must_fix_depois_do_limpo_volta_a_esperar_o_revisor():
    vereditos = [_limpo("2026-10-05T12:00:00Z"), _must_fix("2026-10-06T12:00:00Z")]
    fase = _fase_pr(_pr(205, [1], checks=[_check()], vereditos=vereditos))
    assert fase["fase"] == "esperando_revisor"
    assert fase["veredito"] == "must_fix"


def test_limpo_da_rodada_seguinte_libera_o_merge():
    vereditos = [_must_fix("2026-10-05T12:00:00Z"), _limpo("2026-10-06T12:00:00Z")]
    assert _fase_pr(_pr(206, [1], checks=[_check()], vereditos=vereditos))["fase"] == "verde_esperando_merge"


def test_must_fix_de_seguranca_segura_o_merge_mesmo_com_revisao_limpa():
    vereditos = [_limpo("2026-10-06T12:00:00Z"), _must_fix("2026-10-05T12:00:00Z", tipo="seguranca")]
    assert _fase_pr(_pr(207, [1], checks=[_check()], vereditos=vereditos))["fase"] == "esperando_revisor"


def test_review_aprovado_no_github_conta_como_veredito_limpo():
    reviews = [{"autor": "rib", "estado": "APPROVED", "em": "2026-10-07T12:00:00Z"}]
    assert _fase_pr(_pr(208, [1], checks=[_check()], reviews=reviews))["fase"] == "verde_esperando_merge"


def test_conflito_e_sinal_e_nao_muda_a_coluna():
    fase = _fase_pr(_pr(209, [1], checks=[_check()], merge_state="DIRTY"))
    assert fase["fase"] == "esperando_revisor"
    assert fase["conflito"] is True
    assert _fase_pr(_pr(210, [1], checks=[_check()], merge_state="BEHIND"))["conflito"] is False


def test_pr_mergeado_sem_deploy_fica_mergeado_sem_deploy_desde_o_merge():
    fase = _fase_pr(_merged(211, [1], merged_at="2026-10-08T12:00:00Z"))
    assert fase["fase"] == "mergeado_sem_deploy"
    assert fase["desde"] == "2026-10-08T12:00:00Z"
    assert fase["dias_na_coluna"] == 2


def test_pr_citado_num_deploy_de_onda_fica_em_producao_com_a_versao_e_a_data():
    deploys = [
        _deploy("0.157.0", "2026-10-09T12:00:00-03:00", "onda-b: PRs #212 #213 #214"),
        _deploy("0.156.0", "2026-10-08T12:00:00-03:00", "PR #99"),
    ]
    fase = _fase_pr(_merged(213, [1], merged_at="2026-10-08T15:00:00Z"), deploys=deploys)
    assert fase["fase"] == "em_producao"
    assert fase["versao"] == "0.157.0"
    assert fase["desde"] == "2026-10-09T12:00:00-03:00"
    assert fase["dias_na_coluna"] == 0


def test_deploy_que_cita_a_issue_do_pr_poe_o_pr_em_producao():
    # o /ship antigo escrevia o número da issue no título: "Objetivos com galeria (#820)"
    deploys = [_deploy("0.151.0", "2026-09-19T20:10:13-03:00", "feat(central): Objetivos (#820)")]
    fase = _fase_pr(_merged(840, [820], merged_at="2026-09-19T22:00:00Z"), deploys=deploys)
    assert fase["fase"] == "em_producao"
    assert fase["versao"] == "0.151.0"


def test_deploy_anterior_ao_merge_que_cita_a_issue_nao_conta():
    # issue reaberta: a versão antiga citou a issue, o PR novo ainda não subiu
    deploys = [
        _deploy("0.150.0", "2026-09-18T12:00:00-03:00", "PR #830, issue #820"),
        _deploy("0.140.0", "2026-09-01T12:00:00-03:00", "PR #700"),
    ]
    fase = _fase_pr(_merged(841, [820], merged_at="2026-09-20T12:00:00Z"), deploys=deploys)
    assert fase["fase"] == "mergeado_sem_deploy"


def test_pr_que_nenhum_deploy_cita_sobe_no_primeiro_build_depois_do_merge():
    # PR de registro do rabo e PR só de docs não ganham deploy próprio: o seguinte sobe a main com eles
    deploys = [
        _deploy("0.162.0", "2026-10-06T12:00:00Z", "PR #300", duracao=900),
        _deploy("0.161.3", "2026-10-05T18:41:18Z", "PR #896"),
    ]
    fase = _fase_pr(_merged(948, [], merged_at="2026-10-05T18:41:56Z"), deploys=deploys)
    assert fase["fase"] == "em_producao"
    assert fase["versao"] == "0.162.0"


def test_pr_mergeado_durante_o_build_de_outro_deploy_nao_entra_nele():
    # o build de 15 min começou 11:45; o merge das 11:50 fica para o próximo deploy
    deploys = [
        _deploy("0.162.0", "2026-10-06T12:00:00Z", "PR #300", duracao=900),
        _deploy("0.161.0", "2026-10-01T12:00:00Z", "PR #200", duracao=900),
    ]
    fase = _fase_pr(_merged(301, [], merged_at="2026-10-06T11:50:00Z"), deploys=deploys)
    assert fase["fase"] == "mergeado_sem_deploy"


def test_deploy_que_nao_ficou_saudavel_nao_poe_o_pr_em_producao():
    falhou = {**_deploy("0.163.0", "2026-10-09T12:00:00Z", "PR #216"), "result": "rolled_back"}
    fase = _fase_pr(_merged(216, [1], merged_at="2026-10-09T11:00:00Z"), deploys=[falhou])
    assert fase["fase"] == "mergeado_sem_deploy"


def test_pr_fechado_sem_merge_vira_tentativa_desde_o_fechamento():
    fase = _fase_pr(_pr(215, [1], state="CLOSED", closed_at="2026-10-07T12:00:00Z"))
    assert fase["fase"] == "fechado_sem_merge"
    assert fase["desde"] == "2026-10-07T12:00:00Z"
    assert fase["dias_na_coluna"] == 3


def test_issue_em_pr_aberto_traz_o_sinal_do_pr():
    issue = _issue(40, labels=["in-progress"], assignees=["bia"])
    pr = _pr(140, [40], checks=[_check("FAILURE")], merge_state="DIRTY")
    sinal = _fase(issue, prs=[pr])["sinal"]
    assert sinal == {"ci": "vermelho", "veredito": None, "conflito": True, "tentativa_anterior": False}


# ---------- ondas por PRD ----------


def _ondas(issues):
    return montar_fases(issues, [], [], [], agora=AGORA)["ondas"]


def test_fatias_sem_dependencia_ficam_na_mesma_coluna_e_dependencia_aberta_empurra():
    issues = [
        _issue(50, is_prd=True, children=[51, 52, 53, 54]),
        _issue(51),
        _issue(52),
        _issue(53, blocked_by=[51]),
        _issue(54, blocked_by=[53, 52]),
    ]
    assert _ondas(issues) == {50: [[51, 52], [53], [54]]}


def test_bloqueadora_fechada_nao_empurra_a_fatia_para_a_coluna_seguinte():
    issues = [
        _issue(60, is_prd=True, children=[61, 62]),
        _issue(61, state="CLOSED", closed_at="2026-10-02T10:00:00Z"),
        _issue(62, blocked_by=[61]),
    ]
    assert _ondas(issues) == {60: [[61, 62]]}


def test_bloqueio_de_fora_do_prd_nao_cria_coluna():
    issues = [_issue(70, is_prd=True, children=[71]), _issue(71, blocked_by=[99]), _issue(99)]
    assert _ondas(issues) == {70: [[71]]}


def test_ciclo_de_dependencia_degrada_numa_coluna_com_o_que_sobrou():
    issues = [
        _issue(80, is_prd=True, children=[81, 82, 83]),
        _issue(81),
        _issue(82, blocked_by=[83]),
        _issue(83, blocked_by=[82]),
    ]
    assert _ondas(issues) == {80: [[81], [82, 83]]}


# ---------- funil ----------


def test_funil_conta_as_nove_fases_no_total_e_por_responsavel():
    issues = [
        _issue(90, labels=["needs-triage"], author="ana"),
        _issue(91, labels=["ready-for-agent"], author="ana"),
        _issue(92, labels=["in-progress"], assignees=["bia", "caio"], author="ana"),
        _issue(93, labels=["ready-for-human"], assignees=["bia"]),
        _issue(94, labels=["ready-for-agent"], author=None),
    ]
    funil = montar_fases(issues, [], [], [], agora=AGORA)["funil"]
    assert list(funil["total"]) == [
        "triagem",
        "fila",
        "bloqueada",
        "em_andamento",
        "pr_aberto",
        "mergeada",
        "em_producao",
        "humana",
        "encerrada_sem_pr",
    ]
    assert funil["total"]["fila"] == 2
    assert funil["total"]["em_andamento"] == 1
    assert funil["total"]["humana"] == 1
    assert funil["total"]["pr_aberto"] == 0
    # responsável é quem assumiu; sem assignee, quem criou (emenda de 05/10 da ADR 0061)
    assert funil["por_responsavel"]["bia"]["em_andamento"] == 1
    assert funil["por_responsavel"]["bia"]["humana"] == 1
    assert funil["por_responsavel"]["caio"]["em_andamento"] == 1
    assert funil["por_responsavel"]["ana"]["triagem"] == 1
    assert funil["por_responsavel"]["ana"]["fila"] == 1
    assert funil["por_responsavel"]["ana"]["em_andamento"] == 0
    # "(sem)" é a fila sem claim, o mesmo valor do filtro "ninguém assumiu" da aba Issues
    assert funil["por_responsavel"]["(sem)"]["fila"] == 2
    assert funil["por_responsavel"]["(sem)"]["triagem"] == 1


# ---------- timeline normalizada ----------


def _pr_da_linha(
    number,
    state,
    created_at,
    *,
    closed_at=None,
    merged_at=None,
    ci_vermelho=0,
    ci_vermelho_em=None,
    vereditos=(),
    head_ref=None,
):
    """PR no shape que o coletor tira da consulta de timeline (GraphQL)."""
    return {
        "number": number,
        "state": state,
        "created_at": created_at,
        "closed_at": closed_at,
        "merged_at": merged_at,
        "head_ref": head_ref or f"feat/x-{number}",
        "ci_vermelho": ci_vermelho,
        "ci_vermelho_em": ci_vermelho_em,
        "vereditos": list(vereditos),
    }


def test_timeline_conta_a_historia_da_issue_em_ordem():
    issue = _issue(300, state="CLOSED", created_at="2026-10-01T10:00:00Z", closed_at="2026-10-05T10:00:00Z")
    linha = {
        "eventos": [
            {"tipo": "designada", "em": "2026-10-01T11:00:00Z", "quem": "bia"},
            {"tipo": "fechada", "em": "2026-10-05T10:00:00Z"},
        ],
        "prs": [
            _pr_da_linha(
                302,
                "MERGED",
                "2026-10-03T10:00:00Z",
                merged_at="2026-10-05T10:00:00Z",
                closed_at="2026-10-05T10:00:00Z",
                vereditos=[_must_fix("2026-10-04T10:00:00Z"), _limpo("2026-10-04T18:00:00Z")],
            ),
            _pr_da_linha(
                301,
                "CLOSED",
                "2026-10-02T10:00:00Z",
                closed_at="2026-10-02T20:00:00Z",
                ci_vermelho=2,
                ci_vermelho_em="2026-10-02T15:00:00Z",
            ),
        ],
    }
    deploys = [_deploy("0.170.0", "2026-10-05T09:00:00-03:00", "PR #302, issue #300")]
    tl = montar_fases([issue], [], deploys, [], timelines={300: linha}, agora=AGORA)["timelines"][300]
    assert [e["tipo"] for e in tl] == [
        "criada",
        "designada",
        "pr_aberto",
        "ci_vermelho",
        "pr_fechado",
        "novo_pr",
        "revisor_comentou",
        "revisor_comentou",
        "mergeado",
        "fechada",
        "em_producao",
    ]
    assert tl[1]["quem"] == "bia"
    assert tl[3] == {"tipo": "ci_vermelho", "em": "2026-10-02T15:00:00Z", "pr": 301, "vezes": 2}
    assert tl[5]["pr"] == 302
    assert (tl[6]["veredito"], tl[7]["veredito"]) == ("must_fix", "limpo")
    assert tl[-1] == {"tipo": "em_producao", "em": "2026-10-05T09:00:00-03:00", "pr": 302, "versao": "0.170.0"}


def test_timeline_poe_a_versao_depois_do_merge_mesmo_com_registro_segundos_antes():
    # onda antiga: o registro do deploy (20:01:37) saiu 4 s antes do merge do PR #925 (20:01:41)
    issue = _issue(910, state="CLOSED", created_at="2026-10-02T17:39:40Z")
    pr = _pr_da_linha(925, "MERGED", "2026-10-02T22:31:21Z", merged_at="2026-10-02T23:01:41Z")
    deploys = [_deploy("0.158.6", "2026-10-02T20:01:37-03:00", "onda-a: PRs #925")]
    linha = {"eventos": [{"tipo": "fechada", "em": "2026-10-02T23:01:42Z"}], "prs": [pr]}
    tl = timeline_da_issue(issue, linha, deploys)
    assert [e["tipo"] for e in tl] == ["criada", "pr_aberto", "mergeado", "em_producao", "fechada"]
    assert tl[3]["em"] == "2026-10-02T20:01:37-03:00"  # a hora registrada não muda, só a ordem


def test_timeline_termina_na_branch_quando_ela_ainda_nao_virou_pr():
    issue = _issue(310, labels=["in-progress"], assignees=["bia"])
    linha = {"eventos": [{"tipo": "designada", "em": "2026-10-01T11:00:00Z", "quem": "bia"}], "prs": []}
    tl = montar_fases([issue], [], [], ["feat/fases-310"], timelines={310: linha}, agora=AGORA)["timelines"][310]
    assert [e["tipo"] for e in tl] == ["criada", "designada", "branch"]
    assert tl[-1] == {"tipo": "branch", "em": None, "branch": "feat/fases-310"}


def test_timeline_so_sai_para_as_issues_que_vieram_com_linha():
    fases = montar_fases(
        [_issue(320), _issue(321)], [], [], [], timelines={320: {"eventos": [], "prs": []}}, agora=AGORA
    )
    assert list(fases["timelines"]) == [320]
