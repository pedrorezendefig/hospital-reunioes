"""A receita do Vídeo de visão geral em Remotion (ADR 0076, issue #1366).

O vídeo do módulo passa a ser narrado e feito pela skill global `motion`, e
todo PRD que muda página do módulo o refaz. O teste lê o texto que o agente lê:
a receita da `/manual` nomeia a ferramenta e as peças que o
`checar_video_manual.py` cobra, diz os mesmos tetos que o `publicar.sh` trava,
e a `/to-issues` escreve o pedido de vídeo na Fatia de manual.
"""

from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SKILLS = RAIZ / ".claude" / "skills"
RECEITA = SKILLS / "manual" / "references" / "video-de-visao-geral.md"
PUBLICAR = RAIZ / "docs" / "manual" / "publicar.sh"


def texto_corrido(caminho: Path) -> str:
    """O arquivo sem negrito e sem quebra de linha: a frase como se lê."""
    return " ".join(caminho.read_text(encoding="utf-8").replace("**", "").split())


def teto(nome: str) -> int:
    achado = re.search(
        rf"^{nome}=(\d+)$", PUBLICAR.read_text(encoding="utf-8"), re.MULTILINE
    )
    assert achado, f"{nome} sumiu do publicar.sh"
    return int(achado.group(1))


def secao(texto: str, titulo: str) -> str:
    """O trecho do título até o próximo título de nível igual ou maior."""
    m = re.search(rf"^(#+) {re.escape(titulo)}\s*$", texto, re.MULTILINE)
    assert m, f"seção '{titulo}' não encontrada"
    resto = texto[m.end() :]
    fim = re.search(rf"^#{{1,{len(m.group(1))}}} ", resto, re.MULTILINE)
    return resto[: fim.start()] if fim else resto


def test_receita_faz_o_video_em_remotion_com_as_pecas_que_o_conferidor_cobra():
    receita = texto_corrido(RECEITA)
    assert "Remotion pela skill global `motion`" in receita
    for peca in ("roteiro.md", "cena/", "meta.json", "prds_cobertos", "VERIFY.md"):
        assert f"`{peca}`" in receita, peca


def test_receita_diz_os_tetos_que_o_publicar_trava():
    receita = texto_corrido(RECEITA)
    assert f"até {teto('TETO_VIDEO_MB')} MB por vídeo" in receita
    assert f"até {teto('TETO_SOMA_VIDEOS_MB')} MB somando" in receita
    assert f"o site inteiro até {teto('TETO_MB')} MB" in receita


def test_manual_manda_para_a_receita_nova():
    manual = texto_corrido(SKILLS / "manual" / "SKILL.md")
    assert "Remotion pela skill global `motion`" in manual
    assert "references/video-de-visao-geral.md" in manual


def test_to_issues_pede_o_video_do_modulo_na_fatia_de_manual():
    fatia = secao(
        (SKILLS / "to-issues" / "SKILL.md").read_text(encoding="utf-8"),
        "A Fatia de manual (todo PRD com tela)",
    )
    assert '"Refazer o vídeo do módulo `<modulo>`"' in fatia
    assert "segue válido porque" in fatia
    assert "prds_cobertos" in fatia
    # A regra antiga, de refazer só quando o caminho principal muda, saiu.
    assert "caminho principal" not in fatia
