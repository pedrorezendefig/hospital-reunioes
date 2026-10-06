"""Revisor só de must-fix, uma rodada de correção, segurança por PRD (issue #988, ADR 0064).

Decisão 1: o veredito tem uma lista, must-fix (bug que o teste não pega, teste
vácuo, spec não cumprida, segredo, regressão de permissão), e uma rodada de
correção; a segunda revisão com must-fix tira a fatia da onda. Decisão 4: o
`hr-revisor-seguranca` só roda em rota sem login ou migration, uma vez, em
esforço high e sem ninguém esperar por ele; o resto da segurança é a lente do
`hr-auditor-prd` sobre o diff acumulado do PRD. Prompt é instrução que um
agente segue: estes testes leem os textos.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
SKILLS = RAIZ / ".claude" / "skills"
AGENTES = RAIZ / ".claude" / "agents"

TEXTOS_DA_REVISAO = [
    AGENTES / "hr-revisor.md",
    AGENTES / "hr-revisor-seguranca.md",
    AGENTES / "hr-corretor.md",
    AGENTES / "hr-corretor-max.md",
    SKILLS / "onda-enxuta" / "SKILL.md",
    SKILLS / "onda-enxuta" / "references" / "prompts.md",
    SKILLS / "ship" / "SKILL.md",
]

# O que a ADR 0064 tirou do veredito.
FORA_DO_VEREDITO = re.compile(
    r"should[- ]fix|\bnits?\b|observa[çc][õo]es|issue futura|PEDE_REVISOR_SEGURANCA", re.I
)


def ler(caminho: Path) -> str:
    return caminho.read_text(encoding="utf-8")


def secao(md: str, titulo: str, nivel: str = "##") -> str:
    """De um `<nivel> <titulo>` até o próximo título do mesmo nível."""
    achado = re.search(rf"^{nivel} {re.escape(titulo)}.*?(?=^{nivel} |\Z)", md, re.S | re.M)
    assert achado, f"seção ausente: {titulo}"
    return achado.group(0)


# ------------------------------------------- decisão 1: só must-fix

@pytest.mark.parametrize("caminho", TEXTOS_DA_REVISAO, ids=lambda p: str(p.relative_to(RAIZ)))
def test_nenhum_texto_da_revisao_pede_should_fix_nit_ou_observacao(caminho):
    achados = [
        f"{n}: {li.strip()[:140]}"
        for n, li in enumerate(ler(caminho).splitlines(), 1)
        if FORA_DO_VEREDITO.search(li)
    ]
    assert achados == [], "\n".join(achados)


def test_o_veredito_do_revisor_tem_uma_lista_so_de_must_fix():
    veredito = secao(ler(AGENTES / "hr-revisor.md"), "Veredito")
    assert "uma lista só" in veredito, veredito
    for categoria in (
        "bug que o teste não pega",
        "teste vácuo",
        "spec não cumprida",
        "segredo",
        "regressão de permissão",
    ):
        assert categoria in veredito, categoria
    assert "`VEREDITO: LIMPO`" in veredito and "`VEREDITO: MUST-FIX (n)`" in veredito, veredito


# ------------------------------------------- decisão 1: uma rodada de correção na onda

ONDA = SKILLS / "onda-enxuta" / "SKILL.md"


def passo_4_da_onda() -> str:
    return secao(ler(ONDA), "4. Por PR", "###")


def item(trecho: str, inicio: str) -> str:
    itens = [li for li in trecho.splitlines() if li.startswith(inicio)]
    assert len(itens) == 1, f"um item começando por {inicio!r}: {itens}"
    return itens[0]


def test_a_onda_corrige_uma_vez_e_a_segunda_revisao_com_must_fix_tira_a_fatia():
    assert not re.search(r"\b(2|duas|dois) rodadas", ler(ONDA), re.I)
    veredito = item(passo_4_da_onda(), "- **Veredito do `hr-revisor`**")
    assert "**Uma rodada de correção**" in veredito, veredito
    assert "rodada 2 com must-fix é baixa na hora" in veredito, veredito
    assert "--add-label ready-for-human" in veredito and "o que ficou" in veredito, veredito
    assert "o lote segue sem ela" in veredito, veredito


# ------------------------------------------- decisão 4: segurança por PRD

def test_a_onda_dispara_a_seguranca_uma_vez_e_ninguem_espera_por_ela():
    assert "e de segurança, se havia" not in ler(ONDA)
    passo = passo_4_da_onda()
    assert "**uma vez só**" in item(passo, "3. Dispare `hr-revisor`")

    veredito = item(passo, "- **Veredito do `hr-revisor`**")
    assert "sem esperar o veredito de segurança" in veredito, veredito
    assert "rodada 2 só do `hr-revisor`" in veredito, veredito

    seguranca = item(passo, "- **Veredito de segurança**")
    assert "não roda de novo depois da correção" in seguranca, seguranca
    assert "`hr-corretor`" in seguranca and "mesmo teto de 3 tentativas" in seguranca, seguranca

    papel = item(ler(ONDA), "| `hr-revisor-seguranca` |")
    assert papel.startswith("| `hr-revisor-seguranca` | high |"), papel
    assert "rota sem login" in papel and "migration" in papel, papel


def test_o_revisor_de_seguranca_roda_em_high_so_em_rota_sem_login_e_migration():
    frente = ler(AGENTES / "hr-revisor-seguranca.md").split("---")[1]
    assert re.search(r"^effort: high$", frente, re.M), frente
    descricao = item(frente, "description:")
    assert "rota sem login" in descricao and "migration" in descricao, descricao
    assert not re.search(r"rota nova|middleware|\benv\b|workflows|revisor padrão", descricao), descricao


LISTA_SENSIVEL = SKILLS / "onda-enxuta" / "revisao-sensivel.txt"


def _globs_sensiveis() -> list[str]:
    linhas = (li.strip() for li in ler(LISTA_SENSIVEL).splitlines())
    return [li for li in linhas if li and not li.startswith("#")]


def _casa(caminho: str) -> bool:
    import importlib.util

    spec = importlib.util.spec_from_file_location("sensivel", SKILLS / "onda-enxuta" / "scripts" / "sensivel.py")
    sensivel = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sensivel)
    return any(sensivel.casa(caminho, g.lstrip("+")) for g in _globs_sensiveis())


@pytest.mark.parametrize(
    "caminho",
    [
        "hospital-reunioes/supabase/migrations/115_qualquer.sql",
        "hospital-reunioes/backend/app/routers/ouvidoria_publica.py",
        "hospital-reunioes/backend/app/routers/webhooks.py",
        "hospital-reunioes/backend/app/services/ouvidoria_triagem_email.py",
        "hospital-reunioes/backend/app/routers/aceite.py",
    ],
)
def test_a_seguranca_por_pr_dispara_em_rota_sem_login_e_migration(caminho):
    assert _casa(caminho), caminho


@pytest.mark.parametrize(
    "caminho",
    [
        "hospital-reunioes/backend/app/routers/reunioes.py",
        "hospital-reunioes/backend/app/middleware/auth.py",
        "hospital-reunioes/backend/app/config.py",
        "hospital-reunioes/backend/app/dependencies.py",
        "hospital-reunioes/backend/.env.example",
        ".github/workflows/ci.yml",
        ".claude/agents/hr-revisor-seguranca.md",
        ".claude/skills/ship/SKILL.md",
    ],
)
def test_rota_com_login_middleware_env_workflow_e_o_fluxo_de_revisao_sairam_do_gatilho(caminho):
    assert not _casa(caminho), caminho


def test_rota_nova_saiu_do_gatilho():
    # o prefixo "+" disparava quando o PR criava um router qualquer
    assert [g for g in _globs_sensiveis() if g.startswith("+")] == []


def gate_do_ship(gate: str) -> str:
    return secao(secao(ler(SKILLS / "ship" / "SKILL.md"), "Passo 8 "), gate, "###")


def test_o_ship_dispara_a_seguranca_uma_vez_sem_esperar_e_o_spec_x_diff_so_traz_must_fix():
    gate1 = gate_do_ship("Gate 1:")
    assert "sem esperar o Gate 2" in gate1 and "só must-fix" in gate1, gate1

    gate15 = gate_do_ship("Gate 1.5")
    assert "só o que impede o merge" in gate15, gate15
    assert "scope creep" not in gate15.lower() and "sem travar" not in gate15, gate15

    gate2 = gate_do_ship("Gate 2:")
    assert gate2.splitlines()[0].endswith("(rota sem login ou migration)"), gate2.splitlines()[0]
    assert "**uma vez só**" in gate2 and "Ninguém espera por ele" in gate2, gate2
    assert "não roda de novo" in gate2, gate2
    assert "nova rodada do `hr-revisor-seguranca`" not in gate2, gate2


@pytest.mark.parametrize(
    "caminho",
    [ONDA, SKILLS / "ship" / "SKILL.md", RAIZ / "docs" / "onboarding" / "dev.md"],
    ids=lambda p: str(p.relative_to(RAIZ)),
)
def test_o_gatilho_de_seguranca_e_rota_sem_login_ou_migration_nos_textos_do_fluxo(caminho):
    linhas = [li for li in ler(caminho).splitlines() if "caminho sensível" in li]
    assert linhas == [], linhas


def test_o_auditor_do_prd_passa_a_lente_de_seguranca_no_diff_acumulado():
    auditor = ler(AGENTES / "hr-auditor-prd.md")
    lente = secao(auditor, "Segurança do diff acumulado")
    assert "uma rodada" in lente.lower(), lente
    # os PRs vêm de todas as sub-issues do PRD, não só das desta sessão
    prs = item(lente, "1. ")
    assert "issues/<PRD>/sub_issues --jq" in prs and "closedByPullRequestsReferences" in prs, prs
    assert "gh pr diff <PR>" in prs, prs
    assert "gh issue create" in lente and "must-fix" in lente, lente
    assert "`ready-for-agent`" in lente and "`ready-for-human` se for grave" in lente, lente
    assert "Segurança: MUST-FIX (n)" in secao(auditor, "Veredito"), "o comentário do PRD conta os achados"

    prompts = ler(SKILLS / "onda-enxuta" / "references" / "prompts.md")
    disparo = item(prompts, "PRD #<PRD>. Versão em produção")
    assert "lente de segurança no diff acumulado" in disparo, disparo
    papel = item(ler(ONDA), "| `hr-auditor-prd` |")
    assert "lente de segurança" in papel, papel
