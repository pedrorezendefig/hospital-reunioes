"""Ondas mais paralelas, mapa uma vez por PRD, teto de mutantes, esforço por tamanho (issue #995).

ADR 0064, decisão 5: (a) o `/to-issues` fatia para paralelismo real, sem arquivo
de costura em comum na mesma onda, G que não bloqueia ninguém vira duas M, e as
ondas previstas na lista e no PRD; (b) o Mapa do terreno é feito uma vez por PRD
e a passagem leva o que a onda anterior mergeou e se a estrutura mudou; (c) um
mutante por critério de aceite, não por teste; (d) implementador em `high` na
fatia P e M e `xhigh` só na G. Skill e agente são instrução que um agente segue:
estes testes leem os textos.
"""

from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SKILLS = RAIZ / ".claude" / "skills"
AGENTES = RAIZ / ".claude" / "agents"
TO_ISSUES = SKILLS / "to-issues" / "SKILL.md"


def ler(caminho: Path) -> str:
    return caminho.read_text(encoding="utf-8")


def secao(md: str, titulo: str, nivel: str = "##") -> str:
    """De um `<nivel> <titulo>` até o próximo título do mesmo nível."""
    achado = re.search(rf"^{nivel} {re.escape(titulo)}.*?(?=^{nivel} |\Z)", md, re.S | re.M)
    assert achado, f"seção ausente: {titulo}"
    return achado.group(0)


# ------------------------------------------- (a) /to-issues fatia para paralelismo real


def regra_do_paralelismo() -> str:
    rascunho = secao(ler(TO_ISSUES), "3. Draft vertical slices", "###")
    return secao(rascunho, "Paralelismo real", "####")


def test_o_to_issues_nao_poe_arquivo_de_costura_em_comum_na_mesma_onda():
    regra = regra_do_paralelismo()
    assert "fatias da mesma onda não compartilham arquivo de costura" in regra, regra
    for costura in ("main.py", "config.py", "AdminSidebar.tsx", "fechar_onda.py"):
        assert f"`{costura}`" in regra, costura
    # confere o arquivo compartilhado antes de propor a divisão, não depois
    assert "antes de propor a divisão" in regra and "Mapa do terreno" in regra, regra
    assert "git grep" in regra, regra


def test_o_to_issues_divide_a_fatia_g_que_nao_bloqueia_ninguem_em_duas_m():
    assert "fatia G que não bloqueia ninguém vira duas M" in regra_do_paralelismo()


def test_o_to_issues_lista_as_ondas_previstas_ao_usuario_e_no_prd():
    md = ler(TO_ISSUES)
    quiz = secao(md, "4. Quiz the user", "###")
    assert "**ondas previstas**" in quiz and "arquivo de costura" in quiz, quiz

    publicar = secao(md, "5. Publish the issues", "###")
    # o PRD leva o agrupamento com os números reais, no corpo
    bloco = next(b for b in re.findall(r"```bash\n(.*?)```", publicar, re.S) if "Ondas previstas" in b)
    assert "## Ondas previstas" in bloco and 'gh issue edit "$PRD" --body-file' in bloco, bloco
    assert "Não feche nem edite o corpo" not in publicar, publicar
