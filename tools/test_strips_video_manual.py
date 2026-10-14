"""Testes do gate de strips do Vídeo de tarefa (tools/strips_video_manual.py).

O `hyperframes check` olha o vídeo em nove instantes espalhados e não vê o que
acontece no corte: um quadro preto de 33 ms entre duas telas, uma legenda que
fica um instante sem a placa. O gate pega o MP4 e os cortes da composição, tira
dez quadros de cada lado de cada corte e reprova o que o olho humano veria
(emenda de 13/10/2026 à ADR 0057, issue #1230).

Os MP4 de fixture saem do ffmpeg na hora, com cor chapada: o teste sabe
exatamente qual quadro está preto e onde está a placa.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

GATE = Path(__file__).resolve().parent / "strips_video_manual.py"

# Duas cenas de 1 s: o corte é em 1.0 s, o quadro 30 a 30 fps.
COMPOSICAO = """<!doctype html>
<html><body>
<div id="main" data-composition-id="main" data-start="0" data-width="1920" data-height="1080" data-duration="2">
  <section id="c-a" class="clip" data-start="0" data-duration="1" data-track-index="1"></section>
  <section id="c-b" class="clip" data-start="1" data-duration="1" data-track-index="1"></section>
</div>
</body></html>
"""

TOKENS = """:root {
  --color-primary-dark: #1A1C4E;
  --video-legenda-fundo: var(--color-primary-dark);
  --video-legenda-esquerda: 160px;
  --video-legenda-topo: 904px;
  --video-legenda-largura: 1600px;
  --video-legenda-altura: 128px;
}
"""


def mp4(destino: Path, *filtros: str) -> Path:
    """Dois segundos de tela clara a 30 fps, com os filtros pedidos por cima."""
    cadeia = ",".join(("color=c=0xEEF1F6:s=320x180:r=30:d=2", *filtros))
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            cadeia,
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(destino),
        ],
        check=True,
    )
    return destino


QUADRO_PRETO_NO_CORTE = "drawbox=x=0:y=0:w=iw:h=ih:color=black:t=fill:enable='eq(n,30)'"


def rodar(tmp_path: Path, video: Path, composicao: str = COMPOSICAO):
    (tmp_path / "index.html").write_text(composicao, encoding="utf-8")
    (tmp_path / "tokens.css").write_text(TOKENS, encoding="utf-8")
    return subprocess.run(
        [
            sys.executable,
            str(GATE),
            "--mp4",
            str(video),
            "--composicao",
            str(tmp_path / "index.html"),
            "--tokens",
            str(tmp_path / "tokens.css"),
            "--saida",
            str(tmp_path / "strips"),
        ],
        capture_output=True,
        text=True,
    )


def test_quadro_preto_no_corte_reprova(tmp_path):
    video = mp4(tmp_path / "com-preto.mp4", QUADRO_PRETO_NO_CORTE)
    resultado = rodar(tmp_path, video)
    assert resultado.returncode == 1, resultado.stdout
    assert "quadro preto" in resultado.stderr
    assert "1.00s" in resultado.stderr


def test_o_mesmo_video_sem_o_quadro_preto_passa(tmp_path):
    video = mp4(tmp_path / "limpo.mp4")
    resultado = rodar(tmp_path, video)
    assert resultado.returncode == 0, resultado.stderr
    strips = sorted((tmp_path / "strips").glob("*.png"))
    assert [s.name for s in strips] == ["corte-01-1.00s.png"]


# A mesma composição com um card de legenda de passo montado de 0.5 s a 2 s.
COM_LEGENDA = COMPOSICAO.replace(
    "</div>\n</body>",
    '  <div id="slot-legenda" data-composition-id="legenda-de-passo"'
    ' data-composition-src="compositions/legenda-de-passo.html"'
    ' data-start="0.5" data-duration="1.5" data-track-index="3"'
    ' data-width="1920" data-height="1080"></div>\n</div>\n</body>',
)
# A placa no retângulo dos tokens, no quadro de 320x180 (1920x1080 dividido por 6).
PLACA = "drawbox=x=26:y=150:w=268:h=22:color=0x1A1C4E:t=fill"


def test_legenda_que_perde_a_placa_no_corte_reprova(tmp_path):
    video = mp4(tmp_path / "sem-placa.mp4", PLACA + ":enable='not(between(n,30,32))'")
    resultado = rodar(tmp_path, video, COM_LEGENDA)
    assert resultado.returncode == 1, resultado.stdout
    assert "legenda sem fundo em 1.00s" in resultado.stderr


def test_legenda_com_a_placa_o_tempo_todo_passa(tmp_path):
    video = mp4(tmp_path / "com-placa.mp4", PLACA)
    resultado = rodar(tmp_path, video, COM_LEGENDA)
    assert resultado.returncode == 0, resultado.stderr
