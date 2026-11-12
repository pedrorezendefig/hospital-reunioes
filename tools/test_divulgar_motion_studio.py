"""O vídeo da Demonstração sai do Motion studio, sem Remotion (issue #1616).

A receita do `/divulgar` é texto que um agente segue: estes testes leem o `SKILL.md`
como o agente lê. O portão de entrega (`gate-video.sh`) roda com `ffprobe` e `ffmpeg`
falsos no PATH, para provar o fps que ele aceita sem precisar de um MP4 de verdade.
"""

from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SKILL = RAIZ / ".claude" / "skills" / "divulgar" / "SKILL.md"


def _texto() -> str:
    return SKILL.read_text(encoding="utf-8")


def test_receita_nao_cita_remotion_nem_a_skill_motion_arquivada():
    texto = _texto()
    assert not re.search(r"remotion", texto, re.IGNORECASE)
    # A skill antiga aparece como `motion` entre crases ou pelo caminho dela.
    assert "`motion`" not in texto
    assert "skills/motion/" not in texto
    assert not re.search(r"skill motion(?![\w-])", texto)
