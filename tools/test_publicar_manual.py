"""Testes da montagem da publicação do Manual (docs/manual/publicar.sh).

O `--dry-run` monta a pasta que iria para a Vercel e para antes de publicar, e é
nela que os dois guardas do ADR 0057 vivem: reencodar cada vídeo para 720p
(decisão 6) e travar quando a pasta passa de 90 MB, que é o limite de 100 MB do
plano onde o site mora. Os testes montam a pasta de saída à mão e rodam o script
com `--pular-build`, sem Node e sem rede.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

PUBLICAR = Path(__file__).resolve().parents[1] / "docs" / "manual" / "publicar.sh"
sem_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg e ffprobe são pré-requisitos da publicação",
)


def publicar(
    saida: Path, videos: Path | None = None
) -> subprocess.CompletedProcess[str]:
    # A pasta dos masters é a do teste: o ~/Videos de quem roda não decide nada.
    pasta = videos if videos is not None else saida.parent / "sem-videos"
    return subprocess.run(
        ["bash", str(PUBLICAR), "--dry-run", "--pular-build", "--saida", str(saida)],
        capture_output=True,
        text=True,
        env=dict(os.environ, MANUAL_VIDEOS=str(pasta)),
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


def codec(arquivo: Path) -> str:
    saida = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=codec_name",
            "-of",
            "csv=p=0",
            str(arquivo),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return saida.stdout.strip()


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


def test_site_de_91_mb_trava(tmp_path):
    saida = tmp_path / "publicar"
    saida.mkdir()
    (saida / "index.html").write_text("<html></html>", encoding="utf-8")
    # Escrito de verdade, sem `truncate`: arquivo esparso ocupa zero bloco e a
    # trava (que mede o que o disco gasta, como o deploy) passaria batido.
    with open(saida / "gordo.bin", "wb") as arquivo:
        arquivo.write(b"\0" * 91 * 1024 * 1024)

    resultado = publicar(saida)
    assert resultado.returncode == 1
    # A mensagem do erro, e nao "90 MB" solto, que tambem sai na linha
    # informativa do caminho feliz: asserir nela deixaria passar um mutante que
    # apaga o aviso. A regra vem na recusa, no stderr.
    assert "passou do teto" in resultado.stderr
    assert "limite de 90 MB" in resultado.stderr


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


@sem_ffmpeg
def test_video_que_falta_na_montagem_vem_da_pasta_dos_masters(tmp_path):
    """O master mora fora do repositório (~/Videos/Hospital/Manual): é de lá
    que a publicação busca o MP4 que a montagem não trouxe."""
    saida = tmp_path / "publicar"
    saida.mkdir()
    videos = tmp_path / "masters"
    gravar_video(videos / "ouvidoria" / "registrar.mp4", 360)
    (saida / "index.html").write_text(
        '<video><source src="/video/ouvidoria/registrar.mp4"></video>', encoding="utf-8"
    )

    resultado = publicar(saida, videos)
    assert resultado.returncode == 0, resultado.stderr
    assert altura(saida / "video" / "ouvidoria" / "registrar.mp4") == 360


@sem_ffmpeg
def test_master_passa_por_cima_do_mp4_velho_da_montagem(tmp_path):
    """Re-render não pode ser desfeito em silêncio por uma cópia velha que já
    estava na montagem: quem vai ao ar é o master."""
    saida = tmp_path / "publicar"
    saida.mkdir()
    gravar_video(saida / "video" / "ouvidoria" / "registrar.mp4", 1080)
    videos = tmp_path / "masters"
    gravar_video(videos / "ouvidoria" / "registrar.mp4", 360)
    (saida / "index.html").write_text(
        '<video><source src="/video/ouvidoria/registrar.mp4"></video>', encoding="utf-8"
    )

    resultado = publicar(saida, videos)
    assert resultado.returncode == 0, resultado.stderr
    assert altura(saida / "video" / "ouvidoria" / "registrar.mp4") == 360


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


@sem_ffmpeg
def test_video_ganha_a_capa_do_primeiro_quadro(tmp_path):
    """A capa é o `poster` do <video>: sem ela, o leitor encara um retângulo
    preto até dar play, e quem lê no celular não dá play (ADR 0057, emenda de
    17/09/2026, decisão 2). Ela vai para o mesmo dist, então o `du` da trava de
    tamanho já a conta.
    """
    saida = tmp_path / "publicar"
    saida.mkdir()
    video = saida / "video" / "ouvidoria" / "registrar.mp4"
    gravar_video(video, 1080)
    (saida / "index.html").write_text(
        '<video poster="/video/ouvidoria/registrar.jpg">'
        '<source src="/video/ouvidoria/registrar.mp4"></video>',
        encoding="utf-8",
    )

    resultado = publicar(saida)
    assert resultado.returncode == 0, resultado.stderr
    capa = saida / "video" / "ouvidoria" / "registrar.jpg"
    assert capa.is_file()
    # JPEG de verdade, e da altura do vídeo já reencodado: gerar a capa antes do
    # reencode a deixaria em 1080, com um peso que a trava de tamanho conta e
    # ninguém pediu.
    assert codec(capa) == "mjpeg"
    assert altura(capa) == 720


@sem_ffmpeg
def test_video_sem_reencode_tambem_ganha_capa(tmp_path):
    """Vídeo que já é pequeno passa pelo mesmo caminho e sai com capa."""
    saida = tmp_path / "publicar"
    saida.mkdir()
    video = saida / "video" / "ouvidoria" / "curto.mp4"
    gravar_video(video, 360)
    (saida / "index.html").write_text(
        '<video><source src="/video/ouvidoria/curto.mp4"></video>', encoding="utf-8"
    )

    resultado = publicar(saida)
    assert resultado.returncode == 0, resultado.stderr
    assert codec(saida / "video" / "ouvidoria" / "curto.jpg") == "mjpeg"


def audio(video: Path) -> tuple[str, int]:
    """Codec e taxa (bits por segundo) da faixa de áudio."""
    saida = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=codec_name,bit_rate",
            "-of",
            "csv=p=0",
            str(video),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    nome, taxa = saida.stdout.strip().split(",")
    return nome, int(taxa)


@sem_ffmpeg
def test_video_narrado_sai_com_audio_aac_de_64_kbps(tmp_path):
    """O Vídeo de visão geral tem narração (ADR 0076): a voz vai junto, em AAC
    de 64 kbps, que basta para fala e pesa metade do que pesava a 128."""
    saida = tmp_path / "publicar"
    video = saida / "video" / "pops" / "visao-geral.mp4"
    video.parent.mkdir(parents=True)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=640x360:rate=12:duration=4",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=4",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            str(video),
        ],
        capture_output=True,
        check=True,
    )
    pagina_com_videos(saida, ["/video/pops/visao-geral.mp4"])

    resultado = publicar(saida)
    assert resultado.returncode == 0, resultado.stderr
    nome, taxa = audio(video)
    assert nome == "aac"
    # O AAC do ffmpeg oscila em volta do alvo; a 96 kbps de antes passaria de 80.
    assert 48_000 <= taxa <= 72_000, taxa


# --- Orçamento de vídeo (ADR 0076, que emenda a 0072) ------------------------
#
# Depois do reencode 720p, três travas: a soma dos MP4 até 60 MB, no máximo um
# vídeo por módulo e nenhum vídeo acima de 10 MB. O vídeo de ruído é o único que
# o reencode não encolhe: cada quadro pesa uns 200 KB em 720p, então o tamanho
# sai do número de quadros. Como o x264 do CI pode ser outro, cada teste confere
# depois da publicação que o vídeo montado tem mesmo o tamanho que o caso pede.

MB = 1024 * 1024
MODULOS = [
    "primeiros-passos",
    "reunioes",
    "ouvidoria",
    "pops",
    "contas-medicas",
    "admin",
    "tecnologia",
]


def gravar_ruido(destino: Path, quadros: int) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "nullsrc=s=1280x720:rate=30,geq=lum='random(1)*255':cb=128:cr=128",
            "-frames:v",
            str(quadros),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "28",
            "-pix_fmt",
            "yuv420p",
            str(destino),
        ],
        capture_output=True,
        check=True,
    )


def pagina_com_videos(saida: Path, caminhos: list[str]) -> None:
    (saida / "index.html").write_text(
        "".join(
            f'<video poster="{c[:-4]}.jpg"><source src="{c}"></video>' for c in caminhos
        ),
        encoding="utf-8",
    )


def mp4_montados(saida: Path) -> list[int]:
    return [v.stat().st_size for v in (saida / "video").rglob("*.mp4")]


@sem_ffmpeg
def test_soma_de_61_mb_trava(tmp_path):
    """Oito vídeos de uns 8 MB, um por pasta: cada um cabe, a soma não.

    Oito pastas e não os seis módulos com vídeo: seis vídeos passariam de 60 MB
    só com uns 10 MB cada, colados na trava de cada vídeo, e o x264 do CI que
    gerasse um quadro mais pesado faria o teste cair pela trava errada.
    """
    saida = tmp_path / "publicar"
    caminhos = [f"/video/modulo-{n}/visao-geral.mp4" for n in range(1, 9)]
    for caminho in caminhos:
        gravar_ruido(saida / caminho.lstrip("/"), 36)
    pagina_com_videos(saida, caminhos)

    resultado = publicar(saida)
    tamanhos = mp4_montados(saida)
    assert max(tamanhos) <= 10 * MB and sum(tamanhos) > 60 * MB, tamanhos
    assert resultado.returncode == 1
    assert "soma dos vídeos" in resultado.stderr
    assert "60 MB" in resultado.stderr


@sem_ffmpeg
def test_dois_videos_no_mesmo_modulo_travam(tmp_path):
    saida = tmp_path / "publicar"
    caminhos = ["/video/ouvidoria/visao-geral.mp4", "/video/ouvidoria/outro.mp4"]
    for caminho in caminhos:
        gravar_video(saida / caminho.lstrip("/"), 360)
    pagina_com_videos(saida, caminhos)

    resultado = publicar(saida)
    assert resultado.returncode == 1
    assert "mais de um vídeo no módulo" in resultado.stderr
    assert "/video/ouvidoria/outro.mp4" in resultado.stderr


@sem_ffmpeg
def test_video_de_11_mb_trava(tmp_path):
    """O Vídeo de visão geral narrado cabe em 10 MB depois do reencode."""
    saida = tmp_path / "publicar"
    caminho = "/video/pops/visao-geral.mp4"
    gravar_ruido(saida / caminho.lstrip("/"), 50)
    pagina_com_videos(saida, [caminho])

    resultado = publicar(saida)
    assert mp4_montados(saida)[0] > 10 * MB, mp4_montados(saida)
    assert resultado.returncode == 1
    assert "acima de 10 MB" in resultado.stderr
    assert caminho in resultado.stderr


@sem_ffmpeg
def test_seis_videos_pequenos_um_por_modulo_passam(tmp_path):
    """O plano do PRD #1365: seis Vídeos de visão geral, o Admin sem vídeo."""
    saida = tmp_path / "publicar"
    caminhos = [f"/video/{m}/visao-geral.mp4" for m in MODULOS if m != "admin"]
    for caminho in caminhos:
        gravar_video(saida / caminho.lstrip("/"), 360)
    pagina_com_videos(saida, caminhos)

    resultado = publicar(saida)
    assert resultado.returncode == 0, resultado.stderr
    assert "nada publicado" in resultado.stdout


@sem_ffmpeg
def test_o_mesmo_video_em_duas_paginas_conta_uma_vez(tmp_path):
    """A página inicial mostra o vídeo de Primeiros passos: é o mesmo arquivo."""
    saida = tmp_path / "publicar"
    caminho = "/video/primeiros-passos/conheca-a-plataforma.mp4"
    gravar_video(saida / caminho.lstrip("/"), 360)
    pagina_com_videos(saida, [caminho])
    abertura = saida / "primeiros-passos" / "index.html"
    abertura.parent.mkdir()
    abertura.write_text(
        f'<video><source src="{caminho}"></video>', encoding="utf-8"
    )

    resultado = publicar(saida)
    assert resultado.returncode == 0, resultado.stderr
