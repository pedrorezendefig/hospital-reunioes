"""A issue-raiz que o terminal publica nasce com `type:` e `area:` (issue #1706).

O espelho da Tecnologia (`tecnologia_espelho.decidir`, ADR 0084, decisão 4) só
cria a Demanda de uma raiz do app que já chega no `issues.opened` com uma label
de tipo e uma `area:` do app. O `/to-prd` publicava o PRD só com
`ready-for-agent`, e o PRD aberto pelo terminal nunca virava card. Estes testes
leem o `gh issue create` de cada skill como o agente lê e conferem as labels
contra as constantes do próprio espelho, lidas do código-fonte (o backend não
roda no job de ferramentas).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
SKILLS = RAIZ / ".claude" / "skills"
ESPELHO = RAIZ / "hospital-reunioes" / "backend" / "app" / "services" / "tecnologia_espelho.py"


def constante_do_espelho(nome: str) -> set[str]:
    """O valor literal de `TIPO_DA_LABEL` (as chaves) ou `AREAS_DO_APP`."""
    arvore = ast.parse(ESPELHO.read_text(encoding="utf-8"))
    for no in arvore.body:
        alvo = no.target if isinstance(no, ast.AnnAssign) else (no.targets[0] if isinstance(no, ast.Assign) else None)
        if isinstance(alvo, ast.Name) and alvo.id == nome:
            valor = no.value
            if isinstance(valor, ast.Dict):
                return {ast.literal_eval(k) for k in valor.keys}
            if isinstance(valor, ast.Call):  # frozenset({...})
                return set(ast.literal_eval(valor.args[0]))
    raise AssertionError(f"{nome} não encontrada em {ESPELHO}")


def secao(skill: str, titulo: str) -> str:
    texto = (SKILLS / skill / "SKILL.md").read_text(encoding="utf-8")
    m = re.search(rf"^(#+) {re.escape(titulo)}\s*$", texto, re.MULTILINE)
    assert m, f"/{skill}: seção '{titulo}' não encontrada"
    nivel = len(m.group(1))
    resto = texto[m.end() :]
    fim = re.search(rf"^#{{1,{nivel}}} ", resto, re.MULTILINE)
    return resto[: fim.start()] if fim else resto


def labels_do_create(trecho: str, *, avulsa: bool = False) -> list[str]:
    """As labels do `gh issue create` do trecho; `avulsa` pega o da fatia sem Pai."""
    comandos = [li for li in trecho.splitlines() if "gh issue create" in li and "--label" in li]
    if avulsa:
        comandos = [li for li in comandos if "avulsa" in li.lower() or "Pai: Nenhum" in li]
    assert comandos, "nenhum `gh issue create` com --label no trecho"
    return re.findall(r'--label\s+"?([^"\s)]+)"?', comandos[0])


def opcoes(labels: list[str], prefixo: str) -> set[str]:
    """`type:<feature|fix>` vira {"type:feature", "type:fix"}."""
    saida: set[str] = set()
    for label in labels:
        if not label.startswith(prefixo):
            continue
        m = re.fullmatch(rf"{re.escape(prefixo)}<([^>]+)>", label)
        nomes = m.group(1).split("|") if m else [label[len(prefixo) :]]
        saida |= {f"{prefixo}{n.strip()}" for n in nomes}
    return saida


CASOS = [
    pytest.param("to-prd", "Process", False, id="prd-do-to-prd"),
    pytest.param("to-issues", "5. Publish the issues", True, id="fatia-avulsa-do-to-issues"),
]


@pytest.mark.parametrize(("skill", "titulo", "avulsa"), CASOS)
def test_raiz_publicada_pelo_terminal_sai_com_type_e_area(skill: str, titulo: str, avulsa: bool) -> None:
    labels = labels_do_create(secao(skill, titulo), avulsa=avulsa)

    assert "ready-for-agent" in labels, labels
    assert opcoes(labels, "type:"), f"/{skill}: o gh issue create não põe type: ({labels})"
    assert opcoes(labels, "area:"), f"/{skill}: o gh issue create não põe area: ({labels})"


@pytest.mark.parametrize(("skill", "titulo", "avulsa"), CASOS)
def test_raiz_do_app_tem_as_labels_que_o_espelho_le_no_opened(skill: str, titulo: str, avulsa: bool) -> None:
    trecho = secao(skill, titulo)
    tipos = opcoes(labels_do_create(trecho, avulsa=avulsa), "type:")

    assert tipos & constante_do_espelho("TIPO_DA_LABEL"), (
        f"/{skill}: nenhum type: do comando ({sorted(tipos)}) faz o espelho criar a Demanda"
    )
    areas_do_app = constante_do_espelho("AREAS_DO_APP")
    assert areas_do_app == {"area:backend", "area:frontend", "area:supabase"}
    linha_do_app = [li for li in trecho.splitlines() if "app:" in li.lower() and "area:" in li]
    assert linha_do_app, f"/{skill}: a skill não diz quais area: são do app"
    citadas = set(re.findall(r"area:[a-z]+", linha_do_app[0]))
    assert areas_do_app <= citadas, f"/{skill}: faltam {sorted(areas_do_app - citadas)} na lista do app"
