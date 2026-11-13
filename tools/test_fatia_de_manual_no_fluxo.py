"""A fatia de manual volta ao fluxo, sem vídeo (issue #1728, ADR 0094, decisão 6).

O `/to-prd` pede a seção "Manual: páginas que mudam" em todo PRD com tela, e o
`/to-issues` cria, a partir dela, a fatia que atualiza o Markdown da página do
módulo, com os prints do roteiro do `playwright-cli` contra o seed e o bloco
`fluxograma` quando o processo muda. O vídeo, que fez a ADR 0078 tirar a fatia,
não volta. O teste lê o `SKILL.md` como o agente lê: o trecho certo de cada
skill, não o arquivo inteiro.
"""

from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SKILLS = RAIZ / ".claude" / "skills"
MANUAL = RAIZ / "hospital-reunioes" / "frontend" / "public" / "manual"


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


def template_do_prd() -> str:
    m = re.search(r"<prd-template>(.*?)</prd-template>", ler("to-prd"), re.DOTALL)
    assert m, "/to-prd sem <prd-template>"
    return m.group(1)


def test_prd_com_tela_traz_a_secao_do_manual_no_template() -> None:
    manual = secao(template_do_prd(), "Manual: páginas que mudam")

    assert "Nenhuma" in manual, "o PRD sem tela precisa de um jeito de dizer que não muda página"
    assert "/to-issues" in manual, "a seção não diz que é dela que sai a fatia de manual"


def test_to_issues_cria_a_fatia_de_manual_pela_secao_do_prd() -> None:
    fatia = secao(ler("to-issues"), "A fatia de manual (todo PRD com tela)")

    assert "Manual: páginas que mudam" in fatia, "a fatia não lê a seção do PRD"
    for item in ("pagina.md", "`playwright-cli`", "seed", "`fluxograma`", "roteiro"):
        assert item in fatia, f"a fatia de manual não pede {item}"
    assert "blocked_by" in fatia or "bloqueada" in fatia.lower(), "a fatia não espera as telas prontas"


def test_a_pasta_citada_pela_fatia_e_a_do_manual_no_app() -> None:
    fatia = secao(ler("to-issues"), "A fatia de manual (todo PRD com tela)")
    pasta = MANUAL.relative_to(RAIZ).as_posix()

    assert pasta in fatia, f"a fatia não diz onde mora a página ({pasta})"
    assert any(MANUAL.glob("*/pagina.md")), "a pasta citada não tem página nenhuma"


def test_fatia_de_manual_nao_pede_video() -> None:
    fatia = secao(ler("to-issues"), "A fatia de manual (todo PRD com tela)")
    manual = secao(template_do_prd(), "Manual: páginas que mudam")

    for nome, trecho in (("to-issues", fatia), ("to-prd", manual)):
        frases = [f for f in re.split(r"(?<=[.:])\s+", trecho) if re.search(r"v[íi]deo|mp4", f, re.IGNORECASE)]
        assert frases, f"/{nome}: a skill não diz que a fatia é sem vídeo"
        assert all(re.search(r"\bsem v[íi]deo\b|\bnão tem v[íi]deo\b", f, re.IGNORECASE) for f in frases), (
            f"/{nome}: frase que pede vídeo: {frases}"
        )


def test_ask_pedro_cita_a_fatia_de_manual() -> None:
    especificar = [li for li in ler("ask-pedro").splitlines() if li.startswith("2. **Especificar**")]

    assert especificar, "/ask-pedro sem o passo Especificar"
    assert "fatia de manual" in especificar[0].lower(), especificar[0]
