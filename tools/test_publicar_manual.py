"""Testes da montagem da publicação do Manual (docs/manual/publicar.sh).

O `--dry-run` monta a pasta que iria para a Vercel e para antes de publicar, e é
nela que os dois guardas do ADR 0057 vivem: reencodar cada vídeo para 720p
(decisão 6) e travar quando a pasta passa de 90 MB, que é o limite de 100 MB do
plano onde o site mora. Os testes montam a pasta de saída à mão e rodam o script
com `--pular-build`, sem Node e sem rede.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

PUBLICAR = Path(__file__).resolve().parents[1] / "docs" / "manual" / "publicar.sh"
sem_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg e ffprobe são pré-requisitos da publicação",
)


def publicar(saida: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(PUBLICAR), "--dry-run", "--pular-build", "--saida", str(saida)],
        capture_output=True,
        text=True,
    )


def altura(video: Path) -> int:
    saida = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=height",
            "-of",
            "csv=p=0",
            str(video),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return int(saida.stdout.strip())


def gravar_video(destino: Path, altura_em_pixels: int) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"testsrc=size={altura_em_pixels * 16 // 9}x{altura_em_pixels}:rate=12:duration=1",
            "-pix_fmt",
            "yuv420p",
            str(destino),
        ],
        capture_output=True,
        check=True,
    )


def test_saida_acima_de_90_mb_trava(tmp_path):
    saida = tmp_path / "publicar"
    saida.mkdir()
    (saida / "index.html").write_text("<html></html>", encoding="utf-8")
    # Escrito de verdade, sem `truncate`: arquivo esparso ocupa zero bloco e a
    # trava (que mede o que o disco gasta, como o deploy) passaria batido.
    with open(saida / "gordo.bin", "wb") as arquivo:
        arquivo.write(b"\0" * 95 * 1024 * 1024)

    resultado = publicar(saida)
    assert resultado.returncode == 1
    # A mensagem do erro, e nao "90 MB", que tambem sai na linha informativa do
    # caminho feliz: asserir nela deixaria passar um mutante que apaga o aviso.
    assert "passou do teto" in resultado.stdout + resultado.stderr


def test_saida_logo_acima_do_teto_trava(tmp_path):
    """90,5 MB: medir em MB arredondado leria 90 e deixaria publicar."""
    saida = tmp_path / "publicar"
    saida.mkdir()
    (saida / "index.html").write_text("<html></html>", encoding="utf-8")
    with open(saida / "quase.bin", "wb") as arquivo:
        arquivo.write(b"\0" * ((90 * 1024 + 512) * 1024))

    resultado = publicar(saida)
    assert resultado.returncode == 1
    assert "passou do teto" in resultado.stdout + resultado.stderr


def test_saida_abaixo_do_teto_passa(tmp_path):
    saida = tmp_path / "publicar"
    saida.mkdir()
    (saida / "index.html").write_text("<html></html>", encoding="utf-8")
    with open(saida / "magro.bin", "wb") as arquivo:
        arquivo.write(b"\0" * 2 * 1024 * 1024)

    resultado = publicar(saida)
    assert resultado.returncode == 0, resultado.stderr
    assert "nada publicado" in resultado.stdout


@sem_ffmpeg
def test_video_grande_sai_em_720p(tmp_path):
    saida = tmp_path / "publicar"
    saida.mkdir()
    video = saida / "video" / "ouvidoria" / "registrar.mp4"
    gravar_video(video, 1080)
    (saida / "index.html").write_text(
        '<video><source src="/video/ouvidoria/registrar.mp4"></video>', encoding="utf-8"
    )

    resultado = publicar(saida)
    assert resultado.returncode == 0, resultado.stderr
    assert altura(video) == 720


@sem_ffmpeg
def test_video_ja_pequeno_nao_cresce(tmp_path):
    saida = tmp_path / "publicar"
    saida.mkdir()
    video = saida / "video" / "ouvidoria" / "curto.mp4"
    gravar_video(video, 360)
    (saida / "index.html").write_text(
        '<video><source src="/video/ouvidoria/curto.mp4"></video>', encoding="utf-8"
    )

    resultado = publicar(saida)
    assert resultado.returncode == 0, resultado.stderr
    assert altura(video) == 360


def test_video_que_a_pagina_usa_e_nao_existe_trava(tmp_path):
    """Sem esta trava, a página sobe com o quadro do vídeo quebrado."""
    saida = tmp_path / "publicar"
    saida.mkdir()
    (saida / "index.html").write_text(
        '<video><source src="/video/ouvidoria/sumido.mp4"></video>', encoding="utf-8"
    )

    resultado = publicar(saida)
    assert resultado.returncode == 1
    assert "sumido.mp4" in resultado.stdout + resultado.stderr


def test_video_apontando_para_fora_da_publicacao_trava(tmp_path):
    """O `src` vem do HTML: sem a recusa, o reencode gravaria fora da pasta."""
    saida = tmp_path / "publicar"
    saida.mkdir()
    (saida / "index.html").write_text(
        '<video><source src="../../fora.mp4"></video>', encoding="utf-8"
    )

    resultado = publicar(saida)
    assert resultado.returncode == 1
    assert "para fora da publicação" in resultado.stdout + resultado.stderr


def test_pular_build_nao_publica_mesmo_sem_dry_run(tmp_path):
    """Sem lint, build e conferidor, o script monta e para: não sobe nada."""
    saida = tmp_path / "publicar"
    saida.mkdir()
    (saida / "index.html").write_text("<html></html>", encoding="utf-8")

    resultado = subprocess.run(
        ["bash", str(PUBLICAR), "--pular-build", "--saida", str(saida)],
        capture_output=True,
        text=True,
    )
    assert resultado.returncode == 0, resultado.stderr
    assert "nada publicado" in resultado.stdout
