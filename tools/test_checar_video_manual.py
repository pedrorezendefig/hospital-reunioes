"""Testes do conferidor do Vídeo de tarefa (tools/checar_video_manual.py).

Cada teste monta um manual mínimo num diretório temporário: uma Página de
tarefa que declara `video` e a composição correspondente. O conferidor prova o
que o ADR 0057 (decisão 3) promete e a issue #736 cobra: todo vídeo que uma
página exibe tem composição versionada com carimbo de geração, e o MP4, que é
regerável, não mora na árvore versionada.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import checar_video_manual  # noqa: E402

CONFERIDOR = Path(__file__).resolve().parent / "checar_video_manual.py"

PAGINA_COM_VIDEO = """---
title: Registrar uma manifestação pelo formulário
prd: [731]
draft: true
papel: [Sem login]
video: registrar-manifestacao-pelo-formulario
---

Escreva o seu relato e clique em **Enviar manifestação**.
"""

CARIMBO = {
    "modulo": "ouvidoria",
    "slug": "registrar-manifestacao-pelo-formulario",
    "pagina": "ouvidoria/registrar-manifestacao-pelo-formulario.md",
    "app_version": "0.136.0",
    "gerado_em": "2026-09-16T10:00:00-03:00",
}


def composicao(carimbo: dict | None) -> str:
    miolo = ""
    if carimbo is not None:
        miolo = (
            '<script type="application/json" id="manual-video-meta">'
            + json.dumps(carimbo, ensure_ascii=False)
            + "</script>"
        )
    return f"<html><head>{miolo}</head><body></body></html>"


def montar(
    raiz: Path,
    *,
    com_composicao: bool = True,
    carimbo: dict | None = CARIMBO,
    mp4_versionado: bool = False,
) -> None:
    conteudo = raiz / "src" / "content" / "docs" / "ouvidoria"
    conteudo.mkdir(parents=True)
    (conteudo / "registrar-manifestacao-pelo-formulario.md").write_text(
        PAGINA_COM_VIDEO, encoding="utf-8"
    )
    pasta = raiz / "video" / "ouvidoria" / "registrar-manifestacao-pelo-formulario"
    if com_composicao:
        pasta.mkdir(parents=True)
        (pasta / "index.html").write_text(composicao(carimbo), encoding="utf-8")
    if mp4_versionado:
        pasta.mkdir(parents=True, exist_ok=True)
        (pasta / "registrar-manifestacao-pelo-formulario.mp4").write_bytes(b"x")


def test_pagina_com_composicao_e_carimbo_passa(tmp_path):
    montar(tmp_path)
    assert checar_video_manual.checar(tmp_path) == []


def test_pagina_que_exibe_video_sem_composicao_trava(tmp_path):
    montar(tmp_path, com_composicao=False)
    problemas = checar_video_manual.checar(tmp_path)
    assert len(problemas) == 1
    assert "não tem composição" in problemas[0]


def test_composicao_sem_carimbo_de_geracao_trava(tmp_path):
    montar(tmp_path, carimbo=None)
    problemas = checar_video_manual.checar(tmp_path)
    assert len(problemas) == 1
    assert "carimbo de geração" in problemas[0]


def test_carimbo_sem_a_versao_do_app_trava(tmp_path):
    """O carimbo diz que tela o vídeo retrata: campo pela metade não serve."""
    montar(tmp_path, carimbo={**CARIMBO, "app_version": ""})
    problemas = checar_video_manual.checar(tmp_path)
    assert len(problemas) == 1
    assert "app_version" in problemas[0]


def test_carimbo_de_outra_pagina_trava(tmp_path):
    """Copiar pasta de composição pronta traz o carimbo do vídeo antigo junto."""
    montar(
        tmp_path,
        carimbo={
            **CARIMBO,
            "modulo": "pops",
            "slug": "aprovar-pop",
            "pagina": "pops/aprovar-pop.md",
        },
    )
    problemas = checar_video_manual.checar(tmp_path)
    assert len(problemas) == 1
    assert "aprovar-pop" in problemas[0]


def test_mp4_dentro_da_composicao_trava(tmp_path):
    """O MP4 é regerável e pesa: renderizar dentro da fonte incha o repositório."""
    montar(tmp_path, mp4_versionado=True)
    problemas = checar_video_manual.checar(tmp_path)
    assert len(problemas) == 1
    assert ".mp4" in problemas[0]


def test_mp4_fora_da_pasta_de_video_trava(tmp_path):
    """A árvore versionada inteira é sem MP4, não só docs/manual/video."""
    montar(tmp_path)
    (tmp_path / "src" / "assets" / "ouvidoria").mkdir(parents=True)
    (tmp_path / "src" / "assets" / "ouvidoria" / "tour.mp4").write_bytes(b"x")
    problemas = checar_video_manual.checar(tmp_path)
    assert len(problemas) == 1
    assert "tour.mp4" in problemas[0]


def test_mp4_renderizado_em_public_video_passa(tmp_path):
    """`public/video/` é o destino do render e está fora do git pelo .gitignore."""
    montar(tmp_path)
    rendido = tmp_path / "public" / "video" / "ouvidoria"
    rendido.mkdir(parents=True)
    (rendido / "registrar-manifestacao-pelo-formulario.mp4").write_bytes(b"x")
    assert checar_video_manual.checar(tmp_path) == []


def test_mp4_em_renders_passa(tmp_path):
    """`renders/` é onde o HyperFrames larga o MP4 sozinho, e é git-ignored."""
    montar(tmp_path)
    sobra = (
        tmp_path
        / "video"
        / "ouvidoria"
        / "registrar-manifestacao-pelo-formulario"
        / "renders"
    )
    sobra.mkdir(parents=True)
    (sobra / "main.mp4").write_bytes(b"x")
    assert checar_video_manual.checar(tmp_path) == []


def test_composicao_que_pagina_nenhuma_exibe_trava(tmp_path):
    """Vídeo órfão some do manual sem ninguém notar e ninguém sabe se ainda vale."""
    montar(tmp_path)
    orfa = tmp_path / "video" / "ouvidoria" / "consultar-protocolo"
    orfa.mkdir(parents=True)
    (orfa / "index.html").write_text(composicao(CARIMBO), encoding="utf-8")
    problemas = checar_video_manual.checar(tmp_path)
    assert len(problemas) == 1
    assert "consultar-protocolo" in problemas[0]


def test_pagina_sem_video_passa(tmp_path):
    """Frontmatter sem `video` é o aviso "vídeo em produção", não um erro."""
    montar(tmp_path, com_composicao=False)
    pagina = (
        tmp_path
        / "src"
        / "content"
        / "docs"
        / "ouvidoria"
        / "registrar-manifestacao-pelo-formulario.md"
    )
    pagina.write_text(
        PAGINA_COM_VIDEO.replace("video: registrar-manifestacao-pelo-formulario\n", ""),
        encoding="utf-8",
    )
    assert checar_video_manual.checar(tmp_path) == []


def rodar(raiz: Path) -> subprocess.CompletedProcess[str]:
    """O conferidor como o CI chama: o que trava o merge é o código de saída."""
    return subprocess.run(
        [sys.executable, str(CONFERIDOR), "--dir", str(raiz)],
        capture_output=True,
        text=True,
    )


def test_video_sem_composicao_sai_com_codigo_1(tmp_path):
    montar(tmp_path, com_composicao=False)
    resultado = rodar(tmp_path)
    assert resultado.returncode == 1
    assert "Conferidor do Vídeo de tarefa falhou" in resultado.stderr


def test_manual_em_ordem_sai_com_codigo_0(tmp_path):
    montar(tmp_path)
    resultado = rodar(tmp_path)
    assert resultado.returncode == 0, resultado.stderr
