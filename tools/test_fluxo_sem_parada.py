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
    for gate in ("Gate 1:", "Gate 1.5", "Gate 2:", "Gate 3 "):
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
    # o PR em conflito fica de fora e o lote segue (issue #989); o comportamento
    # está em tools/test_fechar_onda_pr_avulso.py
    assert 'print(f"de fora: conflito no merge de #{e.pr} em:' in ler(FECHAR_ONDA)


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


def test_o_montar_ondas_separa_por_dependencia_e_marca_bloqueada_por_no_mesmo_ponto():
    # ADR 0066: arquivo em comum não separa onda nem sessão; o mesmo ponto vira blocked_by
    agrupar = secao(texto("montar-ondas-enxutas"), "4. Reinventariar", "###")
    assert "dependencies/blocked_by" in agrupar and "Bloqueada por" in agrupar, agrupar
    assert "**Arquivo em comum, dentro da sessão ou entre sessões, não separa onda nem sessão.**" in agrupar
    assert "**Mesmo ponto é dependência**" in agrupar, agrupar
    assert "é aceitável" not in agrupar, "conflito entre sessões deixou de ser aceitável"


# ------------------------------------------- piso de revisão sem humano (revisão do PR #1004)

AGENTES = RAIZ / ".claude" / "agents"


def gate_do_ship(gate: str) -> str:
    return secao(secao(texto("ship"), "Passo 8 "), gate, "###")


def test_o_ship_avulso_revisa_com_os_agentes_e_o_sensivel_decide_o_gate_2():
    # ADR 0063, decisão 1: sem humano, o piso é hr-revisor e, em caminho
    # sensível, hr-revisor-seguranca; o /security-review lia o diff errado em worktree.
    # ADR 0064, decisão 4: quem decide o Gate 2 é só o sensivel.py (o pedido do
    # Gate 1 saiu); tools/test_revisao_so_must_fix.py cobre o gatilho novo.
    gate1 = gate_do_ship("Gate 1:")
    assert "hr-revisor" in gate1 and "VEREDITO: LIMPO" in gate1, gate1

    gate2 = gate_do_ship("Gate 2:")
    assert "sensivel.py" in gate2, gate2
    assert "hr-revisor-seguranca" in gate2 and "VEREDITO SEGURANCA: LIMPO" in gate2, gate2
    assert "Invoca a skill `security-review`" not in gate2, gate2

    cosmetico = secao(secao(texto("ship"), "Passo 8 "), "Passo 8.0", "###")
    assert "sensivel.py" in cosmetico, "diff cosmético em caminho sensível não pula o Gate 2"

    passo = passo_10_do_ship()
    assert "VEREDITO: LIMPO" in passo and "VEREDITO SEGURANCA: LIMPO" in passo, passo


def test_skip_review_e_hotfix_terminam_no_pr_sem_rodar_o_rabo():
    # ADR 0063, decisão 4: o rabo só roda com os gates verdes.
    ship = texto("ship")
    flags = secao(ship, "Flags de override", "###")
    for flag in ("--skip-review", "--hotfix"):
        linha = next(li for li in flags.splitlines() if li.startswith(f"- `{flag}`"))
        assert "sem o Passo 10" in linha, linha
    assert "Só o dono do repo usa" not in ship
    linha = next(li for li in passo_10_do_ship().splitlines() if "`--skip-review`" in li)
    assert "`--hotfix`" in linha and "não chega aqui" in linha, linha


def test_so_autor_de_dentro_do_repo_vale_como_spec_e_como_mapa():
    # repo público: comentário de conta externa não pode virar spec nem receita.
    teto = ("OWNER", "MEMBER", "COLLABORATOR")
    # o filtro tem que estar no comando que o agente roda, não só na prosa
    filtro = "select(" + " or ".join(f'.authorAssociation == "{t}"' for t in teto) + ")"

    ler_issue = secao(texto("pegar-issue"), "1. Ler a issue", "###")
    assert "--jq .author_association" in ler_issue and filtro in ler_issue, ler_issue
    assert all(t in ler_issue for t in teto) and "não pegue" in ler_issue, ler_issue

    onda = texto("onda-enxuta")
    fila = secao(onda, "1. Fila-alvo", "###")
    assert "author_association" in fila, fila
    mapa = next(li for li in onda.splitlines() if "## Mapa do terreno" in li and "startswith" in li)
    assert filtro in mapa, mapa

    for agente in ("hr-implementador", "hr-revisor"):
        entrada = secao(ler(AGENTES / f"{agente}.md"), "Entrada")
        assert re.search(r"--json comments --jq '\.comments\[\] \| " + re.escape(filtro), entrada), agente
    implementador = secao(ler(AGENTES / "hr-implementador.md"), "Entrada")
    assert re.search(r"o Mapa \(`gh issue view <PRD> --json comments --jq '[^`]*" + re.escape(filtro), implementador)


def test_fatia_de_manual_fica_fora_do_rabo_ate_o_ok_humano_no_draft():
    # ADR 0057, decisões 4 e 8; a ADR 0063 não as emendou.
    lote = secao(texto("onda-enxuta"), "5. Lote pronto", "###")
    manual = next(li for li in lote.splitlines() if li.startswith("Fatia de manual"))
    assert "fora do rabo" in manual and "PushNotification" in manual, manual
    assert "não segura o merge" not in lote, lote
    primeiro = next(li for li in fechamento_da_onda().splitlines() if li.startswith("1. "))
    assert "fatia de manual" in primeiro, primeiro
    assert "Fatia de manual" in passo_10_do_ship()
