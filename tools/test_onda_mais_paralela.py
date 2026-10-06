"""Ondas mais paralelas, mapa uma vez por PRD, teto de mutantes, esforço por tamanho (issue #995).

ADR 0064, decisão 5: (a) o `/to-issues` fatia para paralelismo real, com a onda
separada só por dependência e não por arquivo de costura (emenda da ADR 0066),
G que não bloqueia ninguém vira duas M, e as
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
ONDA = SKILLS / "onda-enxuta" / "SKILL.md"
PROMPTS = SKILLS / "onda-enxuta" / "references" / "prompts.md"
MONTAR = SKILLS / "montar-ondas-enxutas" / "SKILL.md"
ADR_0066 = RAIZ / "docs" / "adr" / "0066-ondas-por-dependencia-nao-por-arquivo.md"


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


def test_o_to_issues_separa_onda_por_dependencia_e_nao_por_arquivo_de_costura():
    # ADR 0066: arquivo em comum não separa onda; o mesmo ponto de registro é dependência
    regra = regra_do_paralelismo()
    assert "fatias da mesma onda não compartilham arquivo de costura" not in regra, regra
    assert "Fatias que só compartilham o arquivo andam na mesma onda" in regra, regra
    assert MESMO_PONTO in regra and "`blocked_by`" in regra, regra
    for costura in ("main.py", "config.py", "AdminSidebar.tsx", "fechar_onda.py"):
        assert f"`{costura}`" in regra, costura
    # confere o arquivo compartilhado antes de propor a divisão, não depois
    assert "antes de propor a divisão" in regra and "Mapa do terreno" in regra, regra
    assert "git grep" in regra, regra


# Revisão do PR #1021: o mesmo texto e o mesmo exemplo de "mesmo ponto" nos três lugares,
# senão a fatia que acrescenta a própria linha no arquivo de costura sai paralela de um
# e em série do outro.
MESMO_PONTO = (
    "mesmo ponto é a mesma entrada: as duas fatias editam a mesma rota, o mesmo item de menu "
    "ou a mesma função, ou uma usa o que a outra cria. Cada fatia acrescentar a própria linha "
    "de `include_router` no `main.py` ou o próprio item no `AdminSidebar.tsx` não é mesmo "
    "ponto: as duas rodam juntas, e o rabo PR a PR resolve o conflito de texto."
)
EXEMPLO_MESMO_PONTO = (
    "Exemplo: as fatias 1 e 2 criam as rotas `/pops` e `/ouvidoria`, cada uma com o próprio "
    "`include_router` no `main.py`, e andam na mesma onda; a fatia 3 muda a rota `/pops` que "
    "a 1 cria e anda depois da 1, com o `blocked_by` dela."
)


def test_mesmo_ponto_tem_o_mesmo_texto_e_o_mesmo_exemplo_nos_tres_lugares():
    lugares = {
        "to-issues": regra_do_paralelismo(),
        "montar-ondas": secao(ler(MONTAR), "4. Reinventariar", "###"),
        "ADR 0066": secao(ler(ADR_0066), "Decisão"),
    }
    for nome, texto in lugares.items():
        plano = " ".join(texto.split())
        assert MESMO_PONTO in plano, nome
        assert EXEMPLO_MESMO_PONTO in plano, nome
        assert "lista de rotas do `main.py`" not in plano, nome


def test_a_varredura_de_modulo_ganha_blocked_by_de_cada_issue_do_modulo():
    # sem bloqueio nativo, a /onda-enxuta puxa a varredura na onda 1 (passo 1)
    agrupar = secao(ler(MONTAR), "4. Reinventariar", "###")
    varredura = next(f for f in re.split(r"(?<=\.) ", agrupar) if f.startswith("Varredura de módulo"))
    assert "`blocked_by` nativo de cada issue aberta que muda aquele módulo" in varredura, varredura


def test_o_to_issues_divide_a_fatia_g_que_nao_bloqueia_ninguem_em_duas_m():
    assert "fatia G que não bloqueia ninguém vira duas M" in regra_do_paralelismo()


def test_o_to_issues_lista_as_ondas_previstas_ao_usuario_e_no_prd():
    md = ler(TO_ISSUES)
    quiz = secao(md, "4. Quiz the user", "###")
    assert "**ondas previstas**" in quiz and "a dependência que a segura" in quiz, quiz
    assert "Arquivo de costura em comum não é motivo de onda" in quiz, quiz

    publicar = secao(md, "5. Publish the issues", "###")
    # o PRD leva o agrupamento com os números reais, no corpo
    bloco = next(b for b in re.findall(r"```bash\n(.*?)```", publicar, re.S) if "Ondas previstas" in b)
    assert "## Ondas previstas" in bloco and 'gh issue edit "$PRD" --body-file' in bloco, bloco
    assert "- Onda 2: #<c>, depois da #<a>" in bloco and "divide" not in bloco, bloco
    assert "Não feche nem edite o corpo" not in publicar, publicar


# ------------------------------------------- (b) Mapa do terreno uma vez por PRD


def test_o_mapa_do_terreno_e_feito_uma_vez_por_prd_e_so_refeito_se_a_estrutura_mudou():
    mapa = secao(ler(ONDA), "2. Mapa do terreno", "###")
    assert "anterior ao último PR mergeado" not in mapa, mapa
    assert "Sem Mapa: dispare `hr-mapeador`" in mapa, mapa
    assert "só `Estrutura mudou: sim` daquele PRD dispara o `hr-mapeador` de novo" in mapa, mapa

    papel = next(li for li in ler(ONDA).splitlines() if li.startswith("| `hr-mapeador` |"))
    assert "1 vez por PRD" in papel and "`Estrutura mudou: sim`" in papel, papel


def test_a_passagem_leva_o_mergeado_na_onda_anterior_e_se_a_estrutura_mudou():
    # o bloco tem um `## Passagem` dentro: a seção vai do título até o fim do arquivo
    passagem = ler(PROMPTS).split("\n## Passagem (prompt da próxima sessão)\n", 1)[1]
    bloco = re.search(r"```\n(.*?)```", passagem, re.S).group(1)
    assert re.search(r"^Mergeado na onda anterior: PRD #<X>: PRs #a #b\.$", bloco, re.M), bloco
    assert re.search(r"^Estrutura mudou: PRD #<X>: <sim\|não>\.$", bloco, re.M), bloco

    # a regra do sim/não é por arquivo apagado ou renomeado, lida da API do PR
    regra = next(li for li in passagem.splitlines() if li.startswith("`Estrutura mudou`"))
    assert "pulls/<PR>/files" in regra and "--paginate" in regra, regra
    assert '.status == "removed" or .status == "renamed"' in regra, regra


def test_a_onda_puxa_toda_issue_desbloqueada_e_a_passagem_leva_a_dependencia():
    # ADR 0066: a onda é a fila desbloqueada, não a lista da onda prevista
    fila = secao(ler(ONDA), "1. Fila-alvo", "###")
    assert "**a onda é toda issue da fila fixa já desbloqueada** (`blocked_by` todo fechado)" in fila, fila
    assert "mesmo que a passagem a tenha posto numa onda posterior" in fila, fila

    relatorio = secao(ler(ONDA), "7. Relatório da onda", "###")
    assert '("#945, depois da #944")' in relatorio, relatorio
    assert "número de issues da fila desbloqueadas quando você a escreve, com teto 3" in relatorio, relatorio

    passagem = ler(PROMPTS).split("\n## Passagem (prompt da próxima sessão)\n", 1)[1]
    bloco = re.search(r"```\n(.*?)```", passagem, re.S).group(1)
    assert re.search(r"^- Onda <N\+2>: #f, depois da #e$", bloco, re.M), bloco
    assert "Ordem obrigatória" not in bloco, bloco
    assert "número de issues da fila desbloqueadas quando você escreve a passagem, com teto 3" in passagem


def test_o_implementador_recebe_o_mapa_e_o_mergeado_na_onda_anterior():
    prompt = secao(ler(PROMPTS), "hr-implementador")
    assert "Mapa do terreno: <URL do comentário>." in prompt, prompt
    assert '"Mergeado na onda anterior: PRs #a #b."' in prompt, prompt

    entrada = secao(ler(AGENTES / "hr-implementador.md"), "Entrada")
    linha = next(li for li in entrada.splitlines() if "Mergeado na onda anterior" in li)
    assert "depois do Mapa" in linha and "origin/main" in linha, linha


# ------------------------------------------- (c) teto de mutantes

TETO = "um mutante por critério de aceite, não por teste"


def test_o_teto_de_um_mutante_por_criterio_vale_no_implementador_no_tdd_e_no_revisor():
    passo_4 = next(
        li for li in secao(ler(AGENTES / "hr-implementador.md"), "Ciclo").splitlines() if li.startswith("4. ")
    )
    tdd = next(li for li in ler(SKILLS / "tdd" / "SKILL.md").splitlines() if li.startswith("> **Prova por mutação"))
    lente_1 = next(li for li in secao(ler(AGENTES / "hr-revisor.md"), "Lentes").splitlines() if li.startswith("1. "))

    for nome, texto in (("hr-implementador", passo_4), ("/tdd", tdd), ("hr-revisor", lente_1)):
        assert TETO in texto, nome
    # quem escreve o teto escreve a regra inteira: uma coisa só por mutante, e o detector
    for nome, texto in (("hr-implementador", passo_4), ("/tdd", tdd)):
        assert "mexe em uma coisa só" in texto and "detector" in texto, nome
    assert "não peça mutante além do teto" in lente_1, lente_1


# ------------------------------------------- (d) esforço do implementador pelo tamanho da fatia
# O disparo da ferramenta Agent não aceita esforço por chamada: o esforço vive no
# frontmatter, e o par de agentes é o precedente do `hr-corretor` / `hr-corretor-max`.


def frente(agente: str) -> str:
    return ler(AGENTES / f"{agente}.md").split("---", 2)[1]


def corpo(agente: str) -> str:
    return ler(AGENTES / f"{agente}.md").split("---", 2)[2]


def test_o_implementador_roda_em_high_na_fatia_p_e_m_e_em_xhigh_na_g():
    assert re.search(r"^effort: high$", frente("hr-implementador"), re.M)
    assert re.search(r"^effort: xhigh$", frente("hr-implementador-xhigh"), re.M)

    onda = ler(ONDA)
    lote = secao(onda, "3. Lote: implementadores em paralelo", "###")
    disparo = next(li for li in lote.splitlines() if li.startswith("Dispare os"))
    assert "`fatia:G` no `hr-implementador-xhigh` (`xhigh`)" in disparo, disparo
    assert "`fatia:P`, `fatia:M` ou sem label no `hr-implementador` (`high`)" in disparo, disparo

    papel = next(li for li in onda.splitlines() if li.startswith("| `hr-implementador` "))
    assert papel.startswith("| `hr-implementador` / `hr-implementador-xhigh` | high / xhigh |"), papel


def test_o_implementador_xhigh_tem_o_mesmo_contrato_do_implementador():
    assert corpo("hr-implementador-xhigh") == corpo("hr-implementador")

    def campos(agente: str) -> dict[str, str]:
        return dict(li.split(": ", 1) for li in frente(agente).strip().splitlines())

    base, g = campos("hr-implementador"), campos("hr-implementador-xhigh")
    assert base.keys() == g.keys()
    assert {k for k in base if base[k] != g[k]} == {"name", "description", "effort"}
    assert g["name"] == "hr-implementador-xhigh"
