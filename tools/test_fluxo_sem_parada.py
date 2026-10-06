"""Da issue à produção sem parada humana, fora a migration (issue #970, ADR 0063).

O `/pegar-issue` encadeia `/tdd`, `/ship` e o rabo; o `/ship` roda o rabo com os
gates verdes; a `/onda-enxuta` fecha a onda sem checkpoint. Conflito no rabo
chama o `hr-corretor` com a `/resolver-conflitos` e conta tentativa. Skill é
instrução que um agente segue: um "vai" esquecido num canto para o fluxo inteiro
esperando uma mensagem que ninguém vai mandar. Estes testes leem os textos.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
SKILLS = RAIZ / ".claude" / "skills"
FECHAR_ONDA = SKILLS / "onda-enxuta" / "scripts" / "fechar_onda.py"

TEXTOS_DO_FLUXO = [
    SKILLS / "pegar-issue" / "SKILL.md",
    SKILLS / "tdd" / "SKILL.md",
    SKILLS / "ship" / "SKILL.md",
    SKILLS / "onda-enxuta" / "SKILL.md",
    SKILLS / "onda-enxuta" / "references" / "prompts.md",
    SKILLS / "montar-ondas-enxutas" / "SKILL.md",
    SKILLS / "ask-pedro" / "SKILL.md",
    RAIZ / "CLAUDE.md",
    RAIZ / "docs" / "onboarding" / "dev.md",
]

# Cada forma com que o fluxo antigo esperava o humano antes do rabo.
PARADA = re.compile(
    r"vai #|[\"“`]vai[\"”`]|claude attach|checkpoint|depois do (seu )?OK|OK explícito"
    r"|decisão humana|citando os PR|imprime o comando do rabo|para no PR verde"
    r"|o `?/ship`? termina aqui|para o autor rodar|pedir confirmação|perguntar se incluir"
    r"|aprovação explícita|gate humano do merge",
    re.I,
)


def ler(caminho: Path) -> str:
    return caminho.read_text(encoding="utf-8")


def texto(skill: str) -> str:
    return ler(SKILLS / skill / "SKILL.md")


def secao(md: str, titulo: str, nivel: str = "##") -> str:
    """De um `<nivel> <titulo>` até o próximo título do mesmo nível."""
    achado = re.search(rf"^{nivel} {re.escape(titulo)}.*?(?=^{nivel} |\Z)", md, re.S | re.M)
    assert achado, f"seção ausente: {titulo}"
    return achado.group(0)


def codigo_do_rabo(nome: str) -> str:
    return re.search(rf"^{nome} = (\d+)$", ler(FECHAR_ONDA), re.M).group(1)


def item_da_saida(trecho: str, codigo: str) -> str:
    itens = [li for li in trecho.splitlines() if f"Saída `{codigo}`" in li]
    assert len(itens) == 1, f"um item para a saída {codigo}: {itens}"
    return itens[0]


def passo_10_do_ship() -> str:
    return secao(texto("ship"), "Passo 10")


def fechamento_da_onda() -> str:
    return secao(texto("onda-enxuta"), "6. Fechamento da onda", "###")


# ------------------------------------------- nenhuma parada antes do rabo

@pytest.mark.parametrize("caminho", TEXTOS_DO_FLUXO, ids=lambda p: str(p.relative_to(RAIZ)))
def test_nenhum_texto_do_fluxo_pede_vai_numero_de_pr_ou_confirmacao(caminho):
    paradas = [
        f"{n}: {li.strip()[:140]}"
        for n, li in enumerate(ler(caminho).splitlines(), 1)
        if PARADA.search(li)
    ]
    assert paradas == [], "\n".join(paradas)


def test_o_ship_roda_o_rabo_sozinho_com_os_gates_verdes():
    passo = passo_10_do_ship()
    assert re.search(r"^## Passo 10: Rodar o rabo", passo, re.M), passo.splitlines()[0]
    bloco = re.search(r"```bash\n(.*?)```", passo, re.S).group(1)
    assert "fechar_onda.py --prs" in bloco and "--dry-run" not in bloco, bloco
    assert "sem esperar mensagem" in passo and "em segundo plano" in passo
    # o implementador da onda não roda o rabo: quem roda é o fechamento da onda
    assert "hr-implementador" in passo and "fechamento da onda" in passo


def test_gate_reprovado_no_ship_chama_o_corretor_em_vez_de_parar():
    gates = secao(texto("ship"), "Passo 8 ")
    for gate in ("Gate 1 ", "Gate 1.5", "Gate 2 ", "Gate 3 "):
        corpo = secao(gates, gate, "###")
        assert "hr-corretor" in corpo, gate
        assert not re.search(r"parar \(sem aprovar|reportar logs .*parar", corpo), gate


def test_a_onda_fecha_com_os_prs_verdes_e_limpos_num_rabo_so():
    onda = texto("onda-enxuta")
    assert not re.search(r"^### \d\. Checkpoint", onda, re.M)
    assert re.search(r"^### 6\. Fechamento da onda$", onda, re.M)
    primeiro = next(li for li in fechamento_da_onda().splitlines() if li.startswith("1. "))
    assert "LIMPO" in primeiro and "rabo só" in primeiro, primeiro


def test_o_pegar_issue_encadeia_tdd_ship_e_rabo_sem_perguntar():
    pegar = texto("pegar-issue")
    passo = secao(pegar, "8. Carregar contexto", "###")
    assert passo.index("/tdd") < passo.index("/ship"), passo
    assert "Não espere mensagem" in passo, passo
    assert "fechar_onda.py --prs" in secao(pegar, "Fechar o loop")


def test_o_tdd_chama_o_ship_sem_esperar_mensagem():
    cadencia = next(li for li in texto("tdd").splitlines() if "Cadência de verificação" in li)
    assert "`/ship`" in cadencia and "sem esperar mensagem" in cadencia, cadencia


@pytest.mark.parametrize(
    "caminho",
    [SKILLS / "ask-pedro" / "SKILL.md", RAIZ / "CLAUDE.md", RAIZ / "docs" / "onboarding" / "dev.md"],
    ids=lambda p: str(p.relative_to(RAIZ)),
)
def test_router_claude_md_e_onboarding_descrevem_o_fluxo_novo(caminho):
    linhas = [li for li in ler(caminho).splitlines() if "ADR 0063" in li]
    assert any("migration" in li and re.search(r"sem parada|sozinho", li) for li in linhas), linhas


# ------------------------------------------- conflito resolvido por agente

def test_o_rabo_imprime_a_linha_de_conflito_que_as_skills_procuram():
    assert 'falhar(f"conflito no merge de #{e.pr} em:' in ler(FECHAR_ONDA)


@pytest.mark.parametrize("skill", ["ship", "onda-enxuta"])
def test_conflito_no_rabo_chama_o_corretor_conta_tentativa_e_baixa_na_terceira(skill):
    trecho = passo_10_do_ship() if skill == "ship" else fechamento_da_onda()
    item = item_da_saida(trecho, codigo_do_rabo("EXIT_MERGE"))

    assert "`conflito no merge de #" in item, "a skill distingue o conflito pela linha do rabo: " + item
    assert "hr-corretor" in item and "motivo `conflito`" in item and "resolver-conflitos" in item, item
    assert "gh pr checks" in item, "o CI roda sobre o código combinado antes de tentar de novo: " + item
    assert "conta uma tentativa" in item and "terceira" in item, item
    assert "ready-for-human" in item and "diagnóstico" in item and "PushNotification" in item, item


def test_o_prompt_do_corretor_de_conflito_cita_a_skill_e_a_tentativa():
    prompts = ler(SKILLS / "onda-enxuta" / "references" / "prompts.md")
    conflito = next(li for li in prompts.splitlines() if li.startswith("<conflito:"))
    assert "resolver-conflitos" in conflito and "Tentativa <k> de 3" in conflito, conflito


def test_o_montar_ondas_nao_poe_arquivo_em_comum_em_paralelo_e_marca_bloqueada_por():
    agrupar = secao(texto("montar-ondas-enxutas"), "4. Reinventariar", "###")
    assert "dependencies/blocked_by" in agrupar and "Bloqueada por" in agrupar, agrupar
    assert "é aceitável" not in agrupar, "conflito entre sessões deixou de ser aceitável"
