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
