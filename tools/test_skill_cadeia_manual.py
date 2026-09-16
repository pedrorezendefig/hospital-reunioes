"""A cadeia de skills combina com o Manual que existe de verdade (issue #735).

O `/to-prd`, o `/to-issues`, a `/onda` e o `/deploy` passaram a falar do Manual,
e nenhum deles executa nada aqui: são instruções que um agente vai seguir num
terminal, meses depois. Seção renomeada, modo que não existe, script de `tools/`
com outro nome: tudo isso só apareceria lá, no meio de um deploy. Estes testes
leem as skills e provam aqui que o que elas mandam fazer existe.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SKILLS = RAIZ / ".claude" / "skills"

# Teto da descrição de skill (ADR 0044, decisão 5): acima disso o carregador
# corta e o roteamento passa a decidir por meia frase.
TETO_DA_DESCRICAO = 200

# As skills que a #735 fez conhecerem o Manual.
CADEIA = ["to-prd", "to-issues", "onda", "deploy", "setup-maquina", "ask-pedro"]

# O nome da seção do PRD é contrato entre três skills: o `/to-prd` escreve, o
# `/to-issues` decide se cria a Fatia de manual e a `/manual` lê para saber que
# páginas escrever. Renomear em um lugar só quebra os outros dois em silêncio.
SECAO_DO_PRD = "Manual: páginas que nascem ou mudam"


def texto(skill: str) -> str:
    return (SKILLS / skill / "SKILL.md").read_text(encoding="utf-8")


def descricao(skill: str) -> str:
    return re.search(r"^description: (.+)$", texto(skill), re.M).group(1)


def test_toda_descricao_da_cadeia_cabe_no_teto():
    grandes = {
        s: len(descricao(s)) for s in CADEIA if len(descricao(s)) > TETO_DA_DESCRICAO
    }
    assert grandes == {}


def test_a_secao_do_prd_tem_o_mesmo_nome_nas_tres_skills():
    assert f"## {SECAO_DO_PRD}" in texto("to-prd"), "o template do PRD gera a seção"
    assert SECAO_DO_PRD in texto("to-issues"), "o /to-issues lê a seção para decidir"
    receita = (SKILLS / "manual" / "references" / "prd-e-novidades.md").read_text(
        encoding="utf-8"
    )
    assert SECAO_DO_PRD in receita, (
        "a /manual #PRD lê a seção para saber o que escrever"
    )


def modos_da_manual() -> set[str]:
    """Os modos da tabela "Três modos" da `/manual`, como ela os declara."""
    return {
        m.group(1)
        for m in re.finditer(r"^\| `/manual ([^`]+)` \|", texto("manual"), re.M)
    }


def moldes(citacao: str) -> set[str]:
    """Um modo por alternativa, sem os sinais de molde.

    A cadeia cita ora um modo (`/manual #<PRD>`), ora a sintaxe inteira
    (`/manual <módulo | #PRD | publicar>`). O que importa é que cada alternativa
    seja um modo que a `/manual` declara.
    """
    return {
        re.sub(r"#\S+", "#PRD", parte.strip("<> ").strip())
        for parte in citacao.split("|")
    }


def test_a_cadeia_so_manda_rodar_modo_que_a_manual_tem():
    citados = set()
    for skill in CADEIA:
        for achado in re.finditer(r"`/manual ([^`]+)`", texto(skill)):
            citados |= moldes(achado.group(1))
    assert citados, "alguma skill da cadeia precisa dizer que modo da /manual roda"
    declarados = {m for modo in modos_da_manual() for m in moldes(modo)}
    assert citados <= declarados


def linhas_de_manual(skill: str) -> list[str]:
    return [li for li in texto(skill).splitlines() if "manual" in li.lower()]


def test_todo_caminho_de_manual_que_a_cadeia_cita_existe():
    """Script renomeado em `tools/` não pode sobreviver colado numa skill."""
    citados: set[str] = set()
    for skill in CADEIA:
        citados |= {
            m.group(1)
            for m in re.finditer(r"((?:tools|docs/manual)/[\w./-]+)", texto(skill))
        }
    concretos = sorted(c.rstrip("./") for c in citados)
    # Piso de sanidade: sem ele, reescrever o texto de um jeito que a regex não
    # reconhece deixaria este teste verde sobre lista vazia.
    assert len(concretos) >= 3, concretos
    assert [c for c in concretos if not (RAIZ / c).exists()] == []


def test_o_deploy_chama_o_tirar_draft_com_opcao_que_existe():
    """Opção inventada só falharia no meio de um deploy, depois do merge."""
    ajuda = subprocess.run(
        [sys.executable, str(RAIZ / "tools" / "tirar_draft_manual.py"), "--help"],
        capture_output=True,
        text=True,
    ).stdout
    opcoes = set()
    for linha in linhas_de_manual("deploy"):
        if "tirar_draft_manual.py" in linha:
            opcoes |= set(re.findall(r"(--[a-z-]+)", linha))
    assert opcoes, "o Passo 9.6 precisa mostrar como se chama o script"
    assert [o for o in opcoes if o not in ajuda] == []


def test_o_deploy_registra_o_prd_de_cada_deploy_no_history():
    """Sem o campo, o passo do manual e o inventário voltam a garimpar prosa."""
    assert '"prds"' in texto("deploy")


def test_o_comentario_da_fatia_de_manual_nao_para_a_onda():
    """`revisor-comentou` é falso positivo quando o próprio agente comenta."""
    linha = next(li for li in linhas_de_manual("onda") if "Fatia de manual" in li)
    assert "<!-- automacao -->" in linha
    assert "draft" in linha, "o checkpoint cita o draft do vídeo a aprovar"
