"""Check de um minuto das issues de quem pede, o `/minhas-issues` (issue #956).

A coleta (gh, git, status page) fica num canto; o que estes testes cobrem é o
miolo puro, `montar(dados)`, alimentado com dados normalizados de mentira. O
GitHub de verdade não entra no teste.
"""

from __future__ import annotations

import ast
import importlib.util
import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
SKILL = RAIZ / ".claude" / "skills" / "minhas-issues"
SCRIPT = SKILL / "scripts" / "minhas_issues.py"

_spec = importlib.util.spec_from_file_location("minhas_issues", SCRIPT)
mi = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mi)

EU = "pedrorezendefig"
AGORA = "2026-10-05T21:00:00Z"


def issue(n, titulo="t", labels=(), donos=(), autor=EU, parent=None, upd="2026-10-05T10:00:00Z"):
    return {
        "number": n,
        "title": titulo,
        "labels": list(labels),
        "assignees": list(donos),
        "author": autor,
        "createdAt": upd,
        "updatedAt": upd,
        "parent": parent,
    }


def pr(n, fecha, checks=("SUCCESS",), mss="CLEAN", vereditos=(), run_id=111):
    return {
        "number": n,
        "headRefName": f"chore/x-{fecha}",
        "mergeStateStatus": mss,
        "closes": [fecha],
        "checks": [{"name": f"c{i}", "conclusion": c, "run_id": run_id} for i, c in enumerate(checks)],
        "vereditos": list(vereditos),
    }


def dados(issues=(), prs=(), worktrees=(), componente="operational", cancelados=0, medianas=None):
    return {
        "login": EU,
        "agora": AGORA,
        "issues": list(issues),
        "prs": list(prs),
        "worktrees": list(worktrees),
        "actions": {"componente": componente, "cancelados_por_runner": cancelados},
        "medianas": medianas or {"fatia:P": 1.1, "fatia:M": 1.4, "fatia:G": 1.8, "todas": 1.4},
    }


# Quem é "meu": a regra do painel (ADR 0061, emenda de 05/10/2026)


def test_conta_atribuida_e_criada_sem_dono_e_deixa_fora_a_criada_que_outro_assumiu():
    abertas = [
        issue(941, donos=[EU]),
        issue(942),  # criada por mim, sem dono
        issue(650, donos=["lucassampaioc1"]),  # criada por mim, outro assumiu
        issue(700, autor="lucassampaioc1"),  # de outro, sem dono
        issue(701, autor="lucassampaioc1", donos=[EU]),  # de outro, atribuída a mim
    ]
    assert [i["number"] for i in mi.minhas(abertas, EU)] == [941, 942, 701]


# Semáforo, só Actions


@pytest.mark.parametrize(
    "componente,cancelados,cor",
    [
        pytest.param("operational", 0, "verde", id="verde"),
        pytest.param("degraded_performance", 0, "amarelo", id="amarelo-pela-status-page"),
        pytest.param("operational", 2, "amarelo", id="amarelo-por-runner-com-status-page-ok"),
        pytest.param("partial_outage", 0, "vermelho", id="vermelho-parcial"),
        pytest.param("major_outage", 5, "vermelho", id="vermelho-total"),
        pytest.param(None, 0, "amarelo", id="status-page-fora-do-ar"),
    ],
)
def test_semaforo(componente, cancelados, cor):
    assert mi.semaforo({"componente": componente, "cancelados_por_runner": cancelados})[0] == cor


def test_veredito_do_semaforo_diz_se_da_pra_desenvolver():
    linha = lambda c, n: mi.montar(dados(componente=c, cancelados=n)).splitlines()[0]  # noqa: E731
    assert "dá pra desenvolver: sim" in linha("operational", 0)
    assert "dá pra desenvolver: só até o PR" in linha("operational", 1)
    assert "dá pra desenvolver: só código local" in linha("major_outage", 0)


# Estado do PR


def test_cancelamento_e_falha_viram_motivos_distintos():
    assert mi.estado_pr(pr(1, 9, checks=("SUCCESS", "CANCELLED")))["motivo"] == "CI cancelado"
    assert mi.estado_pr(pr(1, 9, checks=("SUCCESS", "FAILURE")))["motivo"] == "CI vermelho"
    assert mi.estado_pr(pr(1, 9, checks=("SUCCESS", None)))["motivo"] == "CI rodando"
    assert mi.estado_pr(pr(1, 9, mss="DIRTY"))["motivo"] == "conflito com a main"


def test_pr_verde_e_limpo_e_nivel_1_e_must_fix_aberto_segura():
    limpo = "## Veredito da revisão\n\n**must-fix**\nNenhum.\n"
    sujo = "## Veredito da revisão\n\n**must-fix**\n1. `x.py` quebra.\n"
    assert mi.estado_pr(pr(1, 9, vereditos=[limpo]))["nivel"] == 1
    assert mi.estado_pr(pr(1, 9, vereditos=[limpo, sujo]))["motivo"] == "must-fix aberto"
    assert mi.estado_pr(pr(1, 9, vereditos=[sujo, limpo]))["nivel"] == 1


# Os 4 blocos


def cenario():
    return dados(
        issues=[
            issue(941, "Módulo de fases", ["in-progress", "fatia:G"], [EU], parent={"number": 938, "title": "PRD: Hospital OS"}),
            issue(939, "Rabo enxuto", ["in-progress", "fatia:M"], [EU], parent={"number": 938, "title": "PRD: Hospital OS"}),
            issue(955, "Runner reserva", ["in-progress"], [EU]),
            issue(938, "PRD: Hospital OS", ["ready-for-agent"], [EU]),
            issue(942, "Aba Issues", ["ready-for-agent", "fatia:G"], parent={"number": 938, "title": "PRD: Hospital OS"}),
            issue(926, "PR órfão", ["ready-for-agent", "priority:high", "fatia:P"], upd="2026-10-03T10:00:00Z"),
            issue(891, "Publicar o Manual", ["ready-for-human"], [EU], upd="2026-09-27T10:00:00Z"),
            issue(933, "Semáforo de deploy", ["needs-triage"]),
            issue(651, "Juntar a caso", ["ready-for-agent", "fatia:M"], parent={"number": 646, "title": "PRD: Ouvidoria e-mail"}, upd="2026-09-09T10:00:00Z"),
        ],
        prs=[
            pr(950, 941),
            pr(949, 939, checks=("SUCCESS", "CANCELLED"), mss="BLOCKED", run_id=37363765582),
        ],
        worktrees=[
            {"path": "/wt/a", "branch": "chore/ci-runner-reserva-955", "locked": True, "ahead": 1, "sem_remoto": True},
        ],
        componente="degraded_performance",
        cancelados=3,
    )


def blocos(texto: str) -> list[str]:
    return re.findall(r"^\*\*(\d\. [^*]+)\*\*", texto, flags=re.M)


def test_saida_tem_os_4_blocos_na_ordem_e_cabe_numa_tela():
    texto = mi.montar(cenario())
    assert texto.startswith("**Semáforo:**")
    assert [b.split(" ", 1)[1] for b in blocos(texto)] == ["Em andamento", "Na fila", "Plano"]
    assert len(texto.splitlines()) <= 40


def test_em_andamento_traz_pr_parado_e_trabalho_que_pode_se_perder():
    texto = mi.montar(cenario())
    andamento = texto.split("**2. Na fila**")[0]
    assert "| 941 |" in andamento and "#950" in andamento
    assert "| 939 |" in andamento and "CI cancelado" in andamento
    assert "| 955 |" in andamento and "1 commit só local, sem push" in andamento
    assert "worktree travado" in andamento


def test_fila_agrupa_por_prd_com_idade_e_deixa_needs_triage_na_contagem():
    fila = mi.montar(cenario()).split("**2. Na fila**")[1].split("**3. Plano**")[0]
    linhas = [l for l in fila.splitlines() if l.startswith("| PRD #") or l.startswith("| avulsa")]
    assert any(l.startswith("| PRD #938") and "938, 942" in l for l in linhas)
    assert any(l.startswith("| PRD #646") and "26 dias" in l for l in linhas)
    assert "needs-triage: #933" in fila and "/triage" in fila


def test_plano_segue_a_ordem_fixa_e_tem_comando_pronto():
    plano = mi.montar(cenario()).split("**3. Plano**")[1]
    passos = re.findall(r"^(\d)\. (.*)$", plano, flags=re.M)
    assert [p[0] for p in passos] == ["1", "2", "3"]
    assert "#950" in passos[0][1] and "espera o Actions" in passos[0][1]
    assert "push" in passos[1][1] and "#955" in passos[1][1]
    assert "#949" in passos[2][1]
    assert "fechar_onda.py --prs 950 --dry-run" in plano
    assert "git -C /wt/a push -u origin chore/ci-runner-reserva-955" in plano
    assert "gh run rerun 37363765582 --failed" in plano


def plano_de(d):
    return re.findall(r"^(\d)\. (.*)$", mi.montar(d).split("**3. Plano**")[1], flags=re.M)


def test_plano_desce_a_ordem_quando_os_niveis_de_cima_estao_vazios():
    d = dados(
        issues=[
            issue(926, "PR órfão", ["ready-for-agent", "priority:high", "fatia:P"]),
            issue(891, "Publicar o Manual", ["ready-for-human"], [EU]),
            issue(942, "Aba Issues", ["ready-for-agent", "fatia:G"], parent={"number": 938, "title": "PRD: Hospital OS"}),
            issue(941, "Fases", ["in-progress", "fatia:G"], ["lucassampaioc1"], parent={"number": 938, "title": "PRD: Hospital OS"}),
        ]
    )
    passos = plano_de(d)
    assert "/pegar-issue 926" in passos[0][1]
    assert "#891" in passos[1][1]
    assert "/montar-ondas-enxutas" in passos[2][1]


def test_onda_sugere_recorte_do_prd_que_ja_tem_fatia_andando():
    d = dados(
        issues=[
            issue(942, "Aba Issues", ["ready-for-agent", "fatia:G"], parent={"number": 938, "title": "PRD: Hospital OS"}),
            issue(941, "Fases", ["in-progress", "fatia:G"], [EU], parent={"number": 938, "title": "PRD: Hospital OS"}),
            issue(651, "Juntar", ["ready-for-agent", "fatia:M"], parent={"number": 646, "title": "PRD: Ouvidoria"}),
        ]
    )
    ondas = [p for p in plano_de(d) if "/montar-ondas-enxutas" in p[1]]
    assert ondas and "--exceto #938" in ondas[0][1]


def test_estimativa_vem_da_mediana_da_fatia_e_marca_mais_rapido_e_melhor():
    d = dados(
        issues=[
            issue(926, "PR órfão", ["ready-for-agent", "priority:high", "fatia:G"]),
            issue(891, "Publicar o Manual", ["ready-for-human"], [EU]),
            issue(651, "Juntar", ["ready-for-agent", "fatia:M"], parent={"number": 646, "title": "PRD: Ouvidoria"}),
        ],
        medianas={"fatia:P": 1.1, "fatia:M": 1.4, "fatia:G": 1.8, "todas": 1.4},
    )
    plano = mi.montar(d).split("**3. Plano**")[1]
    assert "~1,8 h" in plano
    assert "Melhor: passo 1." in plano
    assert "Mais rápido: passo 3." in plano


@pytest.mark.parametrize(
    "ahead,sem_remoto,onde,prox",
    [
        pytest.param(0, True, "worktree aberto, sem commit novo", "seguir no worktree", id="sem-commit"),
        pytest.param(2, False, "branch no remoto, sem PR", "`/ship`", id="pushado-sem-pr"),
    ],
)
def test_worktree_sem_pr_sempre_diz_onde_parou_e_o_proximo_passo(ahead, sem_remoto, onde, prox):
    d = dados(
        issues=[issue(956, "Skill", ["in-progress"], [EU])],
        worktrees=[{"path": "/wt/b", "branch": "chore/minhas-issues-956", "locked": True, "ahead": ahead, "sem_remoto": sem_remoto}],
    )
    linha = next(l for l in mi.montar(d).splitlines() if l.startswith("| 956 |"))
    assert onde in linha and prox in linha and "worktree travado" in linha


def test_quando_o_melhor_e_o_mais_rapido_coincidem_diz_numa_linha():
    plano = mi.montar(cenario()).split("**3. Plano**")[1]
    assert "O passo 1 é o melhor e o mais rápido." in plano


def test_medianas_por_fatia_saem_dos_prs_mergeados():
    mergeados = [
        {"horas": 1.0, "fatias": ["fatia:P"]},
        {"horas": 3.0, "fatias": ["fatia:P"]},
        {"horas": 2.0, "fatias": ["fatia:M"]},
        {"horas": 9.0, "fatias": []},
    ]
    assert mi.medianas(mergeados) == {"fatia:P": 2.0, "fatia:M": 2.0, "todas": 2.5}


# Só leitura


PROIBIDOS = {"push", "rerun", "merge", "edit", "comment", "close", "create", "delete",
             "checkout", "reset", "-X", "--method", "--add-label", "--add-assignee"}


def test_a_coleta_so_chama_gh_e_git_de_leitura():
    arvore = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    chamadas = [
        n for n in ast.walk(arvore)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in {"gh", "git"}
    ]
    assert chamadas, "a coleta não chama mais gh/git pelos helpers"
    for c in chamadas:
        literais = {a.value for a in c.args if isinstance(a, ast.Constant) and isinstance(a.value, str)}
        assert not literais & PROIBIDOS, f"linha {c.lineno}: {literais & PROIBIDOS}"
    assert "mutation" not in SCRIPT.read_text(encoding="utf-8")
    assert "subprocess" in SCRIPT.read_text(encoding="utf-8").split("def gh(")[0]


def test_o_subprocess_so_entra_pelos_helpers():
    arvore = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    for f in [n for n in arvore.body if isinstance(n, ast.FunctionDef) and n.name not in {"gh", "git"}]:
        usa = [
            n for n in ast.walk(f)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and isinstance(n.func.value, ast.Name) and n.func.value.id == "subprocess"
        ]
        assert not usa, f"{f.name} chama subprocess direto"


# A skill


def texto_skill() -> str:
    return (SKILL / "SKILL.md").read_text(encoding="utf-8")


def test_a_skill_roda_o_script_que_existe_e_aceita_login():
    achado = re.search(r"python3 (\S+/minhas_issues\.py)", texto_skill())
    assert achado and (RAIZ / achado.group(1)) == SCRIPT
    assert "@login" in texto_skill()


def test_a_skill_tem_os_gatilhos_e_entra_no_ask_pedro():
    cabeca = texto_skill().split("---", 2)[1]
    for g in ("minhas issues", "onde parei", "o que tem pra mim", "status do Actions"):
        assert g in cabeca
    assert "/minhas-issues" in (RAIZ / ".claude" / "skills" / "ask-pedro" / "SKILL.md").read_text(encoding="utf-8")


def test_o_texto_novo_nao_tem_travessao():
    travessoes = f"[{chr(0x2013)}{chr(0x2014)}]"
    for arquivo in (SCRIPT, SKILL / "SKILL.md", Path(__file__)):
        assert not re.search(travessoes, arquivo.read_text(encoding="utf-8")), arquivo
