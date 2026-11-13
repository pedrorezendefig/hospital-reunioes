"""O Refino da Demanda do diretor no terminal (PRD #240 do PedroOS, os#606).

O "Criar o card" da aba Tecnologia cria a issue da Demanda (ADR 0077): a
melhoria já nasce com o PRD inteiro, "Decisões de implementação" inclusive, e o
bug nasce com o Roteiro do bug. O `/grill-with-docs #N` lê a issue pelo
`prd_do_diretor.py ler`, faz o Refino (Leitura, Veredito e, na melhoria,
Escolhas) e grava o resultado na mesma issue pelo `prd_do_diretor.py
completar`: a seção do Refino, as perguntas abertas para o diretor, a linha
"O que muda" do bloco trocada pelo Veredito e a marca de Refino. É o miolo puro
do script que estes testes cobrem: o GitHub não entra.

Os casos do card novo, do bug e da linha de comando seguem o
`tests/test_prd_do_diretor.py` do PedroOS, onde o script nasce
(`projetos/hospital/`). O card antigo (sem "Decisões de implementação", o
formato do ADR 0075) continua coberto.
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
SCRIPT = RAIZ / ".claude" / "skills" / "to-prd" / "scripts" / "prd_do_diretor.py"

_spec = importlib.util.spec_from_file_location("prd_do_diretor", SCRIPT)
pd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pd)

MARCA_DA_DEMANDA = '<!-- demanda-vitta id="d-1" -->'

BLOCO = """## 👔 Para o diretor

**O que muda:** o ouvidor vê o prazo de cada caso na fila.

**O que você precisa saber:**
- só o ouvidor vê o prazo
- Ficou em aberto: 2 pontos, que a Vitta pergunta depois.

---
"""

# o card antigo: a metade de negócio do PRD, sem as seções técnicas (ADR 0075)
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

"""
    + MARCA_DA_DEMANDA
)

# o card novo da melhoria, no formato do tecnologia_vinculo.py (ADR 0077, decisão 7)
MELHORIA = f"""Relatório de ocorrências por setor.

## 👔 Para o diretor

**O que muda:** Sim, é uma melhoria

**O que você precisa saber:**
- O relatório sai por setor.

---

## Problema

O diretor não vê as ocorrências por setor.

## Decisões de negócio

1. **Por qual setor?**
   Escolha: todos
   Por quê: visão geral

## Decisões de implementação

- O relatório lê a tabela de ocorrências.

## Decisões de teste

- Teste do endpoint do relatório.

## Ficou em aberto

- Se o relatório conta fim de semana.

## Para o glossário

Termos:
- Nenhum termo novo.

## Origem

Planejado com a IA na aba Tecnologia.
Abrir a Demanda: https://app.exemplo/tecnologia/d-1

{MARCA_DA_DEMANDA}"""

BUG = f"""O botão de salvar some.

## 👔 Para o diretor

**O que muda:** O botão de salvar aparece.

**O que você precisa saber:**
- Bug relatado pelo diretor na aba Tecnologia, em Reuniões.

---

## O bug

- **Onde:** tela da Ata
- **O que aconteceu:** o botão sumiu
- **O que esperava:** o botão na tela
- **Como repetir:** abrir uma Ata

## Critérios de aceite

- [ ] O botão de salvar aparece na Ata.

## Origem

Relatado na conversa com o Assistente de Tecnologia.
Abrir a Demanda: https://app.exemplo/tecnologia/d-2

{MARCA_DA_DEMANDA}"""

REFINO = """## Refino

### Leitura

O diretor quer ver as ocorrências separadas por setor ("quero ver por setor").

### Veredito

Viável com mudança: a tabela de ocorrências não guarda o setor (backend/app/models/ocorrencia.py:12).

### Escolhas

1. O setor entra como coluna nova na tabela.

## O que muda

Dá para fazer: o relatório passa a separar as ocorrências por setor.
"""

PERGUNTAS = """
## Perguntas para o diretor

- O relatório conta o fim de semana?
- Quem mais pode ver o relatório?
"""

# as seções técnicas que o arquivo do Refino traz quando o card é antigo
TECNICAS = """## Decisões de implementação

- O prazo sai do serviço da fila, contado em dias corridos.

## Decisões de teste

- Rota da fila via TestClient, no molde do teste da Ouvidoria.

"""

PAINEL = "https://claude.ai/artifacts/abc"
VEREDITO = "**O que muda:** Dá para fazer: o relatório passa a separar as ocorrências por setor."


# Ler: o que o /grill-with-docs #N recebe


def test_reconhece_a_demanda_pelo_marcador_e_o_tipo_pela_secao():
    assert pd.ler(CORPO)["demanda"] is True and pd.ler(CORPO)["tipo"] == "melhoria"
    assert pd.ler(BUG)["tipo"] == "bug"
    so_marcador = CORPO.replace("## Ficou em aberto", "## Detalhes")
    assert pd.ler(so_marcador)["demanda"] is True and pd.ler(so_marcador)["tipo"] is None
    sem_marcador = CORPO.split("<!--")[0]
    assert pd.ler(sem_marcador)["demanda"] is False
    # o card novo já nasce com as seções técnicas; o que diz que o Refino passou é a marca
    assert pd.ler(MELHORIA)["completo"] is True and pd.ler(CORPO)["completo"] is False
    assert pd.ler(MELHORIA)["refinada"] is False
    assert pd.ler(MELHORIA + "\n<!-- refino -->")["refinada"] is True


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
    # card antigo: o roteiro avisa que o arquivo do Refino traz as seções técnicas
    assert "card antigo" in abertas


def test_grill_de_issue_comum_avisa_que_nao_e_demanda():
    assert pd.roteiro_do_grill("## Problema\n\nqualquer coisa") == pd.NAO_E_DEMANDA


def test_o_card_novo_nao_e_recusado_e_o_roteiro_comeca_pelo_que_o_diretor_decidiu():
    roteiro = pd.roteiro_do_grill(MELHORIA)
    assert pd.TITULO_TOMADAS in roteiro
    assert "- Se o relatório conta fim de semana." in roteiro
    assert "card antigo" not in roteiro


def test_o_bug_tem_o_roteiro_curto_e_o_card_refinado_mostra_as_perguntas_abertas():
    assert "Refino curto" in pd.roteiro_do_grill(BUG)
    refinado, _ = pd.completar(MELHORIA, REFINO + PERGUNTAS)
    roteiro = pd.roteiro_do_grill(refinado)
    assert "já foi refinada" in roteiro
    assert "- O relatório conta o fim de semana?" in roteiro


# Completar: o Refino gravado na mesma issue


def test_completar_preserva_o_bloco_para_o_diretor_e_o_resto_do_corpo():
    novo, _ = pd.completar(MELHORIA, REFINO)
    # até a Origem, o corpo fica byte a byte, menos a linha "O que muda", que vira o Veredito
    antes, depois = MELHORIA.split("## Origem")
    assert novo.split("## Refino")[0] == antes.replace("**O que muda:** Sim, é uma melhoria", VEREDITO)
    assert novo.endswith("## Origem" + depois + "\n<!-- refino -->")
    assert len(pd.CABECALHO_DO_DIRETOR.findall(novo)) == 1


def test_o_que_muda_do_bloco_do_diretor_vira_o_veredito_em_palavras_simples():
    novo, _ = pd.completar(MELHORIA, REFINO)
    bloco = novo.split("---")[0]
    assert VEREDITO in bloco
    assert "Sim, é uma melhoria" not in novo
    assert "**O que você precisa saber:**\n- O relatório sai por setor.\n" in bloco


def test_completar_poe_as_secoes_tecnicas_e_o_refino_antes_da_origem():
    novo, _ = pd.completar(CORPO, TECNICAS + REFINO)
    assert novo.index("## Ficou em aberto") < novo.index("## Decisões de implementação")
    assert novo.index("## Decisões de teste") < novo.index("## Refino") < novo.index("## Origem")
    assert novo.rstrip().endswith(f"{MARCA_DA_DEMANDA}\n<!-- refino -->")


def test_card_novo_com_decisoes_de_implementacao_ganha_o_refino_e_a_marca():
    novo, perguntas = pd.completar(MELHORIA, REFINO)
    assert perguntas == []
    assert "## Refino\n\n### Leitura" in novo
    assert "Viável com mudança: a tabela de ocorrências" in novo
    assert novo.index("## Refino") < novo.index("## Origem")
    assert novo.rstrip().endswith(f"{MARCA_DA_DEMANDA}\n<!-- refino -->")
    # as seções técnicas que o app escreveu ficam como estavam
    assert novo.count("## Decisões de implementação") == 1
    assert "- O relatório lê a tabela de ocorrências." in novo
    assert "## Perguntas para o diretor" not in novo


def test_card_com_perguntas_abertas_grava_a_lista_e_o_link_do_painel():
    novo, perguntas = pd.completar(MELHORIA, REFINO + PERGUNTAS, painel=PAINEL)
    assert perguntas == ["O relatório conta o fim de semana?", "Quem mais pode ver o relatório?"]
    secao = novo.split("## Perguntas para o diretor")[1].split("## Origem")[0]
    assert "- O relatório conta o fim de semana?\n- Quem mais pode ver o relatório?" in secao
    assert f"Painel do Refino: {PAINEL}" in novo
    assert novo.rstrip().endswith(f"<!-- refino: {PAINEL} -->")


def test_card_ja_refinado_troca_o_refino_sem_repetir_secao_nem_marca():
    primeiro, _ = pd.completar(MELHORIA, REFINO + PERGUNTAS, painel=PAINEL)
    segundo_refino = REFINO.replace("Viável com mudança", "Viável").replace("Dá para fazer:", "Dá para fazer agora:")
    segundo, perguntas = pd.completar(primeiro, segundo_refino)
    assert perguntas == []
    assert segundo.count("## Refino") == 1
    assert "## Perguntas para o diretor" not in segundo
    assert "Viável com mudança" not in segundo
    assert segundo.count("<!-- refino") == 1
    # sem --painel no segundo Refino, o link do primeiro continua
    assert segundo.rstrip().endswith(f"<!-- refino: {PAINEL} -->")
    assert "**O que muda:** Dá para fazer agora:" in segundo


def test_bug_do_diretor_tambem_ganha_o_refino():
    refino_do_bug = REFINO.replace("### Escolhas\n\n1. O setor entra como coluna nova na tabela.\n", "")
    novo, _ = pd.completar(BUG, refino_do_bug)
    assert "## Refino" in novo
    assert novo.index("## Critérios de aceite") < novo.index("## Refino")
    assert novo.rstrip().endswith("<!-- refino -->")


@pytest.mark.parametrize(
    ("corpo", "refino", "painel", "motivo"),
    [
        ("## Problema\n\nx", REFINO, None, "não é Demanda do diretor"),
        (MELHORIA, REFINO.split("## O que muda")[0], None, "## O que muda"),
        (MELHORIA, "## O que muda\n\nDá para fazer.\n", None, "## Refino"),
        (MELHORIA, BLOCO + REFINO, None, "Para o diretor"),
        (MELHORIA, REFINO, "http://claude.ai/artifacts/abc", "https"),
        # card antigo sem as seções técnicas no arquivo
        (CORPO, REFINO, None, "Decisões de implementação"),
        # card novo: o arquivo não repete as seções que o app escreveu
        (MELHORIA, TECNICAS + REFINO, None, "já tem Decisões de implementação"),
    ],
)
def test_completar_recusa_o_que_quebraria_a_issue(corpo, refino, painel, motivo):
    with pytest.raises(ValueError, match=motivo):
        pd.completar(corpo, refino, painel)


def test_pergunta_aberta_mantem_a_triagem_e_a_lista_vazia_libera_para_o_agente():
    assert pd.labels_do_refino(["needs-triage", "type:feature"], ["Conta o fim de semana?"]) == {"add": [], "remove": []}
    assert pd.labels_do_refino(["needs-triage"], []) == {"add": ["ready-for-agent"], "remove": ["needs-triage"]}
    # o bug que já estava na Fila volta à Triagem enquanto o diretor não responde
    assert pd.labels_do_refino(["ready-for-agent", "type:fix"], ["O print é da Ata nova?"]) == {
        "add": ["needs-triage"],
        "remove": ["ready-for-agent"],
    }
    assert pd.labels_do_refino(["ready-for-agent"], []) == {"add": [], "remove": []}


# A linha de comando, com o `gh` dublado


def rodar_completar(tmp_path, corpo, labels, refino, *extra):
    chamadas = []

    def gh_falso(*args):
        chamadas.append(args)
        if args[:2] == ("issue", "view"):
            return json.dumps({"body": corpo, "labels": [{"name": l} for l in labels], "title": "Relatório por setor"})
        if args[:2] == ("issue", "edit"):
            arquivo = args[args.index("--body-file") + 1]
            chamadas.append(("corpo", Path(arquivo).read_text(encoding="utf-8")))
        return ""

    arquivo = tmp_path / "refino.md"
    arquivo.write_text(refino, encoding="utf-8")
    codigo = pd.main(["completar", "1400", str(arquivo), *extra], gh=gh_falso)
    return codigo, chamadas


def test_cli_completar_edita_a_mesma_issue_e_troca_a_triagem(tmp_path, capsys):
    codigo, chamadas = rodar_completar(tmp_path, MELHORIA, ["needs-triage"], REFINO)
    assert codigo == 0

    edicoes = [c for c in chamadas if c[:2] == ("issue", "edit")]
    assert len(edicoes) == 1 and edicoes[0][2] == "1400"
    assert edicoes[0][edicoes[0].index("--add-label") + 1] == "ready-for-agent"
    assert edicoes[0][edicoes[0].index("--remove-label") + 1] == "needs-triage"
    assert not any(c[:2] == ("issue", "create") for c in chamadas)
    corpo_gravado = next(c[1] for c in chamadas if c[0] == "corpo")
    assert corpo_gravado.startswith("Relatório de ocorrências por setor.\n\n## 👔 Para o diretor")
    assert "## Refino" in corpo_gravado and corpo_gravado.endswith("<!-- refino -->")
    assert "Qualquer coisa me chama" not in capsys.readouterr().out


def test_cli_com_perguntas_fica_em_triagem_e_imprime_a_mensagem_para_o_diretor(tmp_path, capsys):
    codigo, chamadas = rodar_completar(tmp_path, MELHORIA, ["needs-triage"], REFINO + PERGUNTAS, "--painel", PAINEL)
    assert codigo == 0
    edicao = next(c for c in chamadas if c[:2] == ("issue", "edit"))
    assert edicao[:3] == ("issue", "edit", "1400")
    assert "--add-label" not in edicao and "--remove-label" not in edicao
    assert f"<!-- refino: {PAINEL} -->" in next(c[1] for c in chamadas if c[0] == "corpo")
    saida = capsys.readouterr().out
    assert '"Relatório por setor"' in saida
    assert "1. O relatório conta o fim de semana?\n2. Quem mais pode ver o relatório?" in saida


def test_cli_arquivo_recusado_nao_edita_a_issue(tmp_path):
    codigo, chamadas = rodar_completar(tmp_path, MELHORIA, ["needs-triage"], "## Refino\n\nsó a leitura\n")
    assert codigo == 1
    assert not [c for c in chamadas if c[:2] == ("issue", "edit")]


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
    trecho = secao_da_skill("grill-with-docs", "Refino da Demanda (`/grill-with-docs #N`)", NOTAS)
    assert "prd_do_diretor.py ler" in trecho
    assert "não repergunte" in trecho
    assert "Ficou em aberto" in trecho
    # o Refino grava na mesma issue, com o texto passado pelo humanizer, e segue para o /to-issues
    assert "prd_do_diretor.py completar" in trecho
    assert "humanizer" in trecho
    assert "/to-issues #N" in trecho


def test_to_prd_completa_a_issue_do_diretor_em_vez_de_criar_outra():
    trecho = secao_da_skill("to-prd", "to-prd", NOTAS)
    assert "prd_do_diretor.py completar" in trecho
    assert "Não crie issue" in trecho
    assert "Para o diretor" in trecho


def test_ask_pedro_descreve_o_caminho_do_prd_do_diretor_ate_o_to_issues():
    trecho = secao_da_skill("ask-pedro", "PRD do diretor (planejado no app)")
    ordem = ["Planejar com a IA", "/minhas-issues", "/grill-with-docs #N", "/to-prd", "/to-issues"]
    posicoes = [trecho.find(passo) for passo in ordem]
    assert -1 not in posicoes, dict(zip(ordem, posicoes))
    assert posicoes == sorted(posicoes)


def test_to_prd_limita_o_bloco_a_uma_frase_e_ate_cinco_topicos():
    """Formato fixo do bloco (ADR 0084, decisão 7, issue #1553): o mesmo do
    PRD do diretor, que o Documento do card lê em Em uma frase e O que muda."""
    texto = (RAIZ / ".claude" / "skills" / "to-prd" / "SKILL.md").read_text(encoding="utf-8")
    regra = texto.split("**Todo PRD abre com o bloco", 1)[1].split("**Humanizer", 1)[0]
    assert "uma frase só" in regra
    assert "no máximo cinco tópicos curtos" in regra
    modelo = texto.split("<prd-template>", 1)[1].split("---", 1)[0]
    assert "No máximo cinco tópicos curtos" in modelo
