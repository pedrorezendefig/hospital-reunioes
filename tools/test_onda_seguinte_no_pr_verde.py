"""A onda seguinte começa no PR verde, com o deploy em paralelo (issue #999).

ADR 0064, decisão 6a: a sessão da `/onda-enxuta` lança a sessão da onda
seguinte assim que os PRs ficam verdes e limpos, e só depois roda o rabo, em
paralelo com os implementadores novos. A passagem sai com "em deploy" e a
versão esperada; fatia bloqueada por issue da onda em deploy espera a
bloqueadora fechar; a sessão encerra só depois de comentar o resultado do rabo
na onda. Skill é instrução que um agente segue: estes testes leem os textos.
"""

from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SKILLS = RAIZ / ".claude" / "skills"
ONDA = SKILLS / "onda-enxuta" / "SKILL.md"
PROMPTS = SKILLS / "onda-enxuta" / "references" / "prompts.md"


def ler(caminho: Path) -> str:
    return caminho.read_text(encoding="utf-8")


def secao(md: str, titulo: str, nivel: str = "##") -> str:
    """De um `<nivel> <titulo>` até o próximo título do mesmo nível."""
    achado = re.search(rf"^{nivel} {re.escape(titulo)}.*?(?=^{nivel} |\Z)", md, re.S | re.M)
    assert achado, f"seção ausente: {titulo}"
    return achado.group(0)


def passo(numero: int) -> str:
    """O `### <numero>. ` do Fluxo, até o próximo título de nível 2 ou 3."""
    achado = re.search(rf"^### {numero}\. .*?(?=^#{{2,3}} |\Z)", ler(ONDA), re.S | re.M)
    assert achado, f"passo ausente: {numero}"
    return achado.group(0)


def bloco_da_passagem() -> str:
    # o bloco tem um `## Passagem` dentro: a seção vai do título até o fim do arquivo
    passagem = ler(PROMPTS).split("\n## Passagem (prompt da próxima sessão)\n", 1)[1]
    return re.search(r"```\n(.*?)```", passagem, re.S).group(1)


# ------------------------------------------- a onda seguinte sai no PR verde


def test_a_sessao_lanca_a_onda_seguinte_e_so_depois_roda_o_rabo():
    resumo = next(li for li in ler(ONDA).splitlines() if li.startswith("**Uma sessão de fundo = uma onda.**"))
    # a ordem antiga: o rabo (fecha a onda), depois a passagem, depois o lançamento
    assert not re.search(r"(fecha a onda|rabo).*escreve a passagem.*lança", resumo), resumo
    assert re.search(
        r"PRs ficam verdes e limpos.*escreve a passagem e lança a sessão da onda seguinte"
        r".*roda o rabo.*em paralelo.*comenta o resultado na onda",
        resumo,
    ), resumo

    # no fluxo, o lançamento vem no passo 5, e o rabo de verdade só no 6
    lote = passo(5)
    assert "lancar_sessao.sh <nome>-onda<N+1>" in lote, lote
    assert "a linha `Em deploy`" in lote, lote
    rabo = next(li for li in passo(6).splitlines() if "fechar_onda.py --prs" in li)
    assert "--dry-run" not in rabo, rabo


def test_a_passagem_sai_com_o_que_esta_em_deploy_e_a_versao_esperada():
    bloco = bloco_da_passagem()
    assert re.search(
        r"^Em deploy: PRs #a #b \(issues #x #y\), versão esperada v<antiga> -> v<nova>", bloco, re.M
    ), bloco
    # nada do que só é verdade depois do rabo
    for depois_do_rabo in ("fechada em", "build ok", "health ok", "Está solta"):
        assert depois_do_rabo not in bloco, depois_do_rabo


def test_a_sessao_so_encerra_depois_de_comentar_o_resultado_do_rabo_na_onda():
    resultado = passo(7)
    assert "<!-- automacao -->" in resultado and "## Onda <nome> <N>" in resultado, resultado
    # a passagem já lançada registra o resultado quando o rabo termina
    assert "Rabo da onda <N>:" in resultado and "<nome>-onda<N+1>.md" in resultado, resultado
    assert re.search(r"[Ee]ncerre só depois", resultado), resultado
