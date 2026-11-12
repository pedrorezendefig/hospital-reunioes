"""O vídeo da Demonstração sai do Motion studio, sem Remotion (issue #1616).

A receita do `/divulgar` é texto que um agente segue: estes testes leem o `SKILL.md`
como o agente lê. O portão de entrega (`gate-video.sh`) roda com `ffprobe` e `ffmpeg`
falsos no PATH, para provar o fps que ele aceita sem precisar de um MP4 de verdade.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
SKILL = RAIZ / ".claude" / "skills" / "divulgar" / "SKILL.md"
GATE = RAIZ / ".claude" / "skills" / "divulgar" / "scripts" / "gate-video.sh"


def _texto() -> str:
    return SKILL.read_text(encoding="utf-8")


def test_receita_nao_cita_remotion_nem_a_skill_motion_arquivada():
    texto = _texto()
    assert not re.search(r"remotion", texto, re.IGNORECASE)
    # A skill antiga aparece como `motion` entre crases ou pelo caminho dela.
    assert "`motion`" not in texto
    assert "skills/motion/" not in texto
    assert not re.search(r"skill motion(?![\w-])", texto)


def _passo_1() -> str:
    texto = _texto()
    return texto[texto.index("## Passo 1: o vídeo") : texto.index("## Passo 2: a página")]


def test_passo_1_carrega_a_skill_motion_studio_e_renderiza_pelo_estudio():
    passo = _passo_1()
    assert "carregue a skill `motion-studio`" in passo
    assert "node render.mjs films/<pasta> --final" in passo


def test_passo_1_para_na_lista_de_tomadas_antes_do_codigo_e_na_folha_antes_do_render():
    passo = _passo_1()
    parada_1 = passo.index("**PARADA 1:**")
    parada_2 = passo.index("**PARADA 2:**")
    codigo = passo.index("### 6. Código do filme")
    render_final = passo.index("node render.mjs films/<pasta> --final")
    assert "lista" in passo[parada_1 : parada_1 + 80]
    assert "folha de quadros" in passo[parada_2 : parada_2 + 80]
    assert parada_1 < codigo < parada_2 < render_final


def _portao(tmp_path: Path, fps: str) -> str:
    """Roda o gate-video.sh com um ffprobe que responde `fps` e devolve a prova 1 da saída."""
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    (bin_ / "ffprobe").write_text(f'#!/bin/sh\necho "{fps},{fps},"\n', encoding="utf-8")
    (bin_ / "ffmpeg").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    for b in bin_.iterdir():
        b.chmod(0o755)
    video = tmp_path / "filme.mp4"
    video.write_bytes(b"")
    saida = subprocess.run(
        ["bash", str(GATE), str(video)],
        capture_output=True,
        text=True,
        env={"PATH": f"{bin_}:/usr/bin:/bin", "PYTHON": "/bin/false"},
    ).stdout
    return saida[saida.index("== 1.") : saida.index("== 2.")]


@pytest.mark.parametrize("fps, aprovado", [("60/1", True), ("30/1", False)])
def test_portao_aceita_o_render_final_do_estudio_a_60_fps(tmp_path, fps, aprovado):
    prova = _portao(tmp_path, fps)
    assert ("REPROVADO" not in prova) is aprovado
