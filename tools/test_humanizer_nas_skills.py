"""As skills de texto para fora mandam passar pelo humanizer (issue #1220, ADR 0071).

Decisões 1 e 2 da ADR 0071: toda skill que grava ou publica texto que o
hospital lê chama a skill global `humanizer` em modo embutido no ponto em que o
texto sai, e a voz é a do canal (a amostra aprovada manda no tom). O teste lê o
`SKILL.md` como o agente lê: procura o passo dentro da seção em que o texto é
escrito, não em qualquer lugar do arquivo.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
SKILLS = RAIZ / ".claude" / "skills"

# Skills cujo texto vai para leitor de fora (ADR 0071, decisão 1). Quem cria
# skill nova que escreve para o hospital entra aqui junto com o passo.
TEXTO_PARA_FORA = {
    "manual",
    "divulgar",
    "mensagem-prd",
    "to-prd",
    "to-issues",
    "ship",
    "ask-pedro",
    "montar-manual",
}


def ler(skill: str) -> str:
    return (SKILLS / skill / "SKILL.md").read_text(encoding="utf-8")


def secao(texto: str, titulo: str) -> str:
    """O trecho do título até o próximo título de nível igual ou maior."""
    m = re.search(rf"^(#+) {re.escape(titulo)}\s*$", texto, re.MULTILINE)
    assert m, f"seção '{titulo}' não encontrada"
    nivel = len(m.group(1))
    resto = texto[m.end() :]
    fim = re.search(rf"^#{{1,{nivel}}} ", resto, re.MULTILINE)
    return resto[: fim.start()] if fim else resto


def passos_do_humanizer(trecho: str) -> list[str]:
    """Os parágrafos (ou itens de lista) do trecho que citam o humanizer."""
    blocos = re.split(r"\n\s*\n|\n(?=\s*(?:[-*]|\d+\.) )", trecho)
    return [b for b in blocos if "humanizer" in b]


@pytest.mark.parametrize(
    ("skill", "titulo"),
    [
        ("manual", "A régua de linguagem"),
        ("divulgar", "Passo 1: o vídeo"),
        ("divulgar", "Passo 2: a página"),
        ("mensagem-prd", "Fluxo"),
        ("to-prd", "Process"),
        ("to-issues", "5. Publish the issues"),
    ],
)
def test_skill_de_texto_para_fora_passa_o_texto_pelo_humanizer_onde_ele_e_gravado(
    skill: str, titulo: str
) -> None:
    passos = passos_do_humanizer(secao(ler(skill), titulo))

    assert passos, (
        f"/{skill}: a seção '{titulo}' não manda passar o texto pelo humanizer"
    )
    passo = passos[0]
    assert "modo embutido" in passo, f"/{skill}: o passo não cita o modo embutido"
    assert "ADR 0071" in passo, f"/{skill}: o passo não cita a ADR 0071"
    assert "amostra" in passo, (
        f"/{skill}: o passo não diz qual amostra de voz manda no tom"
    )


def test_manual_passa_pelo_humanizer_antes_do_lint() -> None:
    regua = secao(ler("manual"), "A régua de linguagem")

    passo = passos_do_humanizer(regua)[0]
    assert "antes" in passo and "lint_manual.py" in passo, passo


def test_ask_pedro_cita_a_adr_0071_na_regua_de_texto() -> None:
    texto = ler("ask-pedro")

    linhas = [li for li in texto.splitlines() if "ADR 0071" in li]
    assert linhas, "o /ask-pedro não cita a ADR 0071"
    assert any("humanizer" in li and "texto para fora" in li for li in linhas), linhas


def test_skill_de_texto_interno_nao_ganha_passo_de_humanizer() -> None:
    com_humanizer = {
        p.parent.name
        for p in SKILLS.glob("*/SKILL.md")
        if "humanizer" in p.read_text(encoding="utf-8")
    }

    intrusas = com_humanizer - TEXTO_PARA_FORA
    assert not intrusas, (
        f"{sorted(intrusas)} citam o humanizer sem escrever texto para fora; "
        "comentário de código e nota de scratchpad não passam por ele (ADR 0071)"
    )
