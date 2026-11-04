"""O PRD do diretor no terminal (issue #1350, ADR 0075, decisão 1).

O "sim" do Planejamento da Demanda cria a issue com a metade de negócio do PRD.
O `/grill-with-docs #N` lê essa issue e pergunta só o técnico; o `/to-prd`
completa a mesma issue. Os dois passam pelo `prd_do_diretor.py` da skill
`to-prd`, e é o miolo puro dele que estes testes cobrem: o GitHub não entra.

O corpo de exemplo segue o formato do `corpo_do_prd_do_diretor` do backend
(bloco "Para o diretor", Decisões de negócio numeradas, "Ficou em aberto",
Origem e o marcador da Demanda no fim).
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
SCRIPT = RAIZ / ".claude" / "skills" / "to-prd" / "scripts" / "prd_do_diretor.py"

_spec = importlib.util.spec_from_file_location("prd_do_diretor", SCRIPT)
pd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pd)

BLOCO = """## 👔 Para o diretor

**O que muda:** o ouvidor vê o prazo de cada caso na fila.

**O que você precisa saber:**
- só o ouvidor vê o prazo
- Ficou em aberto: 2 pontos, que a Vitta pergunta depois.

---
"""

CORPO = (
    BLOCO
    + """
## Problema

o ouvidor vê o prazo de cada caso na fila.

## Solução

Prazo na fila, do jeito que o diretor decidiu no planejamento com a IA, na aba Tecnologia.

## Histórias de usuário

1. Como quem pediu a Demanda, quero Prazo na fila, para resolver o problema acima.
2. Como quem pediu a Demanda, quero que valha o que decidi: só o ouvidor vê o prazo

## Decisões de negócio

1. **Quem vê o prazo?**
   Escolha: só o ouvidor vê o prazo
   Por quê: a fila é dele

2. **O prazo aparece em vermelho quando vence?**
   Escolha: sim, em vermelho no dia
   Por quê: é o que o ouvidor olha primeiro

## Ficou em aberto

- Se o prazo conta fim de semana.
- O que acontece com caso reaberto.

## Origem

Planejado com a IA na aba Tecnologia do aplicativo do hospital e mandado para o desenvolvimento pelo sim dado no resumo.
Abrir a Demanda: https://app.exemplo/tecnologia?demanda=d-1

<!-- demanda-vitta id="d-1" -->"""
)

SECOES = """## Decisões de implementação

- O prazo sai do serviço da fila, contado em dias corridos.

## Decisões de teste

- Rota da fila via TestClient, no molde do teste da Ouvidoria.

## Manual: páginas que nascem ou mudam

Nenhuma: este PRD não muda tela
"""


# Ler: o que o /grill-with-docs #N recebe


def test_reconhece_o_prd_do_diretor_pelo_marcador_e_pelo_ficou_em_aberto():
    assert pd.ler(CORPO)["prd_do_diretor"] is True
    so_marcador = CORPO.replace("## Ficou em aberto", "## Detalhes")
    assert pd.ler(so_marcador)["prd_do_diretor"] is False
    sem_marcador = CORPO.split("<!--")[0]
    assert pd.ler(sem_marcador)["prd_do_diretor"] is False


def test_grill_lista_as_decisoes_do_diretor_como_tomadas_e_abre_pelo_que_ficou_em_aberto():
    roteiro = pd.roteiro_do_grill(CORPO)
    tomadas, abertas = roteiro.split(pd.TITULO_EM_ABERTO)
    assert pd.TITULO_TOMADAS in tomadas
    # As duas decisões do diretor estão do lado das tomadas, com a escolha dele.
    assert "Quem vê o prazo?" in tomadas and "só o ouvidor vê o prazo" in tomadas
    assert "O prazo aparece em vermelho quando vence?" in tomadas and "sim, em vermelho no dia" in tomadas
    # O que ficou em aberto vira as primeiras perguntas, e nenhuma decisão do diretor volta como pergunta.
    assert "Se o prazo conta fim de semana." in abertas and "O que acontece com caso reaberto." in abertas
    assert "Quem vê o prazo?" not in abertas and "em vermelho" not in abertas


def test_grill_de_issue_comum_avisa_que_nao_e_prd_do_diretor():
    assert pd.roteiro_do_grill("## Problema\n\nqualquer coisa") == pd.NAO_E_PRD_DO_DIRETOR


# Completar: o que o /to-prd faz na mesma issue


def test_completar_preserva_o_bloco_para_o_diretor_e_o_resto_do_corpo():
    novo = pd.completar(CORPO, SECOES)
    assert novo.startswith(BLOCO)
    antes, depois = CORPO.split("## Origem")
    assert novo.startswith(antes)
    assert novo.endswith("## Origem" + depois)
    assert novo.count(pd.CABECALHO_DO_BLOCO) == 1


def test_completar_poe_as_secoes_tecnicas_antes_da_origem():
    novo = pd.completar(CORPO, SECOES)
    assert novo.index("## Ficou em aberto") < novo.index("## Decisões de implementação")
    assert novo.index("## Decisões de teste") < novo.index("## Origem")
    assert novo.rstrip().endswith('<!-- demanda-vitta id="d-1" -->')


@pytest.mark.parametrize(
    ("corpo", "secoes", "motivo"),
    [
        ("## Problema\n\nx", SECOES, "não é PRD do diretor"),
        (CORPO, "## Decisões de implementação\n\n- x\n", "Decisões de teste"),
        (CORPO, "## Decisões de teste\n\n- x\n", "Decisões de implementação"),
        (CORPO, BLOCO + SECOES, "Para o diretor"),
        (pd.completar(CORPO, SECOES), SECOES, "já tem"),
    ],
)
def test_completar_recusa_o_que_quebraria_a_issue(corpo, secoes, motivo):
    with pytest.raises(ValueError, match=motivo):
        pd.completar(corpo, secoes)


def test_cli_completar_edita_a_mesma_issue_e_troca_a_triagem(tmp_path):
    chamadas = []

    def gh_falso(*args):
        chamadas.append(args)
        if args[:2] == ("issue", "view"):
            return CORPO
        if args[:2] == ("issue", "edit"):
            arquivo = args[args.index("--body-file") + 1]
            chamadas.append(("corpo", Path(arquivo).read_text(encoding="utf-8")))
        return ""

    secoes = tmp_path / "secoes.md"
    secoes.write_text(SECOES, encoding="utf-8")
    assert pd.main(["completar", "1400", str(secoes)], gh=gh_falso) == 0

    edicoes = [c for c in chamadas if c[:2] == ("issue", "edit")]
    assert len(edicoes) == 1 and edicoes[0][2] == "1400"
    assert "--remove-label" in edicoes[0] and "needs-triage" in edicoes[0]
    assert "--add-label" in edicoes[0] and "ready-for-agent" in edicoes[0]
    assert not any(c[:2] == ("issue", "create") for c in chamadas)
    corpo_gravado = next(c[1] for c in chamadas if c[0] == "corpo")
    assert corpo_gravado.startswith(BLOCO) and "## Decisões de implementação" in corpo_gravado


# As skills: o agente só segue o caminho se o SKILL.md disser onde ele passa


SKILLS = RAIZ / ".claude" / "skills"
# As regras só do Hospital nas skills do fluxo moram nas notas, uma seção `## <skill>` cada
NOTAS = RAIZ / ".claude" / "fluxo-notas.md"


def secao_da_skill(skill: str, titulo: str, arquivo: Path | None = None) -> str:
    texto = (arquivo or SKILLS / skill / "SKILL.md").read_text(encoding="utf-8")
    m = re.search(rf"^(#+) {re.escape(titulo)}\s*$", texto, re.MULTILINE)
    assert m, f"{skill}: seção '{titulo}' não encontrada"
    resto = texto[m.end() :]
    fim = re.search(rf"^#{{1,{len(m.group(1))}}} ", resto, re.MULTILINE)
    return resto[: fim.start()] if fim else resto


def test_grill_with_docs_le_o_prd_do_diretor_e_nao_repergunta_o_negocio():
    trecho = secao_da_skill("grill-with-docs", "PRD do diretor (`/grill-with-docs #N`)", NOTAS)
    assert "prd_do_diretor.py ler" in trecho
    assert "não repergunte" in trecho
    assert "Ficou em aberto" in trecho
    assert "/to-prd" in trecho


def test_to_prd_completa_a_issue_do_diretor_em_vez_de_criar_outra():
    trecho = secao_da_skill("to-prd", "PRD do diretor: completar a mesma issue", NOTAS)
    assert "prd_do_diretor.py completar" in trecho
    assert "sem `gh issue create`" in trecho
    assert "Para o diretor" in trecho
    assert "humanizer" in trecho


def test_ask_pedro_descreve_o_caminho_do_prd_do_diretor_ate_o_to_issues():
    trecho = secao_da_skill("ask-pedro", "PRD do diretor (planejado no app)")
    ordem = ["Planejar com a IA", "/minhas-issues", "/grill-with-docs #N", "/to-prd", "/to-issues"]
    posicoes = [trecho.find(passo) for passo in ordem]
    assert -1 not in posicoes, dict(zip(ordem, posicoes))
    assert posicoes == sorted(posicoes)
