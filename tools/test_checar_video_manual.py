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


# Composição no Estilo do manual (issue #1230): cor e fonte pelos tokens, e o
# timeline termina com a âncora que preenche o slot inteiro.
CORPO_NO_ESTILO = """<body>
<div id="main" data-composition-id="main" data-start="0" data-width="1920" data-height="1080" data-duration="42">
  <section id="c-tarefa" class="clip" data-start="0" data-duration="42" data-track-index="1"
    style="background: var(--video-palco); font-family: var(--font-app)"></section>
</div>
<script>
window.__timelines = window.__timelines || {};
const tl = gsap.timeline({ paused: true });
tl.fromTo("#c-tarefa", { opacity: 0 }, { opacity: 1, duration: 0.4 }, 0);
tl.to({}, { duration: 42 }, 0);
window.__timelines["main"] = tl;
</script>
</body>"""


def composicao(carimbo: dict | None, corpo: str = CORPO_NO_ESTILO) -> str:
    miolo = ""
    if carimbo is not None:
        miolo = (
            '<script type="application/json" id="manual-video-meta">'
            + json.dumps(carimbo, ensure_ascii=False)
            + "</script>"
        )
    return (
        f'<html><head>{miolo}<link rel="stylesheet" href="tokens.css" /></head>'
        f"{corpo}</html>"
    )


def montar(
    raiz: Path,
    *,
    com_composicao: bool = True,
    carimbo: dict | None = CARIMBO,
    mp4_versionado: bool = False,
    corpo: str = CORPO_NO_ESTILO,
    com_verify: bool = True,
) -> Path:
    conteudo = raiz / "src" / "content" / "docs" / "ouvidoria"
    conteudo.mkdir(parents=True)
    (conteudo / "registrar-manifestacao-pelo-formulario.md").write_text(
        PAGINA_COM_VIDEO, encoding="utf-8"
    )
    pasta = raiz / "video" / "ouvidoria" / "registrar-manifestacao-pelo-formulario"
    if com_composicao:
        pasta.mkdir(parents=True)
        (pasta / "index.html").write_text(composicao(carimbo, corpo), encoding="utf-8")
        if com_verify:
            (pasta / "VERIFY.md").write_text(
                "# VERIFY\n\nStrips de cada corte conferidas.\n", encoding="utf-8"
            )
    if mp4_versionado:
        pasta.mkdir(parents=True, exist_ok=True)
        (pasta / "registrar-manifestacao-pelo-formulario.mp4").write_bytes(b"x")
    return pasta


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


# Os gates do Estilo do manual (emenda de 13/10/2026 à ADR 0057, issue #1230).
# Cada teste quebra uma coisa só na composição em ordem e espera um problema.


def test_video_sem_verify_trava(tmp_path):
    """Sem VERIFY.md ninguém sabe o que foi conferido antes do OK humano."""
    montar(tmp_path, com_verify=False)
    problemas = checar_video_manual.checar(tmp_path)
    assert len(problemas) == 1
    assert "VERIFY.md" in problemas[0]


def test_cor_em_hex_fixo_trava(tmp_path):
    """Hex na composição é cor que não acompanha o app quando o globals.css muda."""
    montar(
        tmp_path,
        corpo=CORPO_NO_ESTILO.replace("var(--video-palco)", "#EEF1F6"),
    )
    problemas = checar_video_manual.checar(tmp_path)
    assert len(problemas) == 1
    assert "#EEF1F6" in problemas[0]


def test_hex_dentro_do_timeline_tambem_trava(tmp_path):
    """A cor que o GSAP pinta no meio do vídeo é tão fixa quanto a do CSS."""
    montar(
        tmp_path,
        corpo=CORPO_NO_ESTILO.replace(
            "{ opacity: 1, duration: 0.4 }", '{ opacity: 1, color: "#2b2e7e", duration: 0.4 }'
        ),
    )
    problemas = checar_video_manual.checar(tmp_path)
    assert len(problemas) == 1
    assert "#2b2e7e" in problemas[0]


def test_seletor_de_id_nao_e_cor(tmp_path):
    """`#c-tarefa` e `&#233;` têm cerquilha e não são cor."""
    montar(tmp_path, corpo=CORPO_NO_ESTILO.replace("<section", "<p>&#233;</p><section"))
    assert checar_video_manual.checar(tmp_path) == []


def test_fonte_fora_dos_tokens_trava(tmp_path):
    montar(
        tmp_path,
        corpo=CORPO_NO_ESTILO.replace("font-family: var(--font-app)", "font-family: Arial"),
    )
    problemas = checar_video_manual.checar(tmp_path)
    assert len(problemas) == 1
    assert "Arial" in problemas[0]


def test_timeline_mais_curto_que_o_slot_trava(tmp_path):
    """O kit viu quadro preto quando o timeline acaba antes do `data-duration`."""
    montar(
        tmp_path,
        corpo=CORPO_NO_ESTILO.replace("tl.to({}, { duration: 42 }, 0);", "tl.to({}, { duration: 30 }, 0);"),
    )
    problemas = checar_video_manual.checar(tmp_path)
    assert len(problemas) == 1
    assert "timeline" in problemas[0]
    assert "42" in problemas[0]


def test_timeline_sem_a_ancora_do_slot_trava(tmp_path):
    montar(
        tmp_path,
        corpo=CORPO_NO_ESTILO.replace("tl.to({}, { duration: 42 }, 0);\n", ""),
    )
    problemas = checar_video_manual.checar(tmp_path)
    assert len(problemas) == 1
    assert "timeline" in problemas[0]


CARD_MONTADO = """<!doctype html>
<html><head><link rel="stylesheet" href="tokens.css" /></head><body>
<div id="legenda-de-passo" data-composition-id="legenda-de-passo" data-start="0" data-width="1920" data-height="1080" data-duration="60">
  <div class="placa" style="background: var(--video-legenda-fundo)"></div>
</div>
<script>
window.__timelines = window.__timelines || {};
const tl = gsap.timeline({ paused: true });
tl.to({}, { duration: DURACAO }, 0);
window.__timelines["legenda-de-passo"] = tl;
</script>
</body></html>
"""

HOST_DA_LEGENDA = (
    '<div id="slot-legenda" data-composition-id="legenda-de-passo"'
    ' data-composition-src="compositions/legenda-de-passo.html"'
    ' data-start="4" data-duration="8" data-track-index="3"'
    ' data-width="1920" data-height="1080"></div>\n</div>'
)


def montar_com_card(tmp_path: Path, duracao_do_card: int) -> None:
    pasta = montar(tmp_path, corpo=CORPO_NO_ESTILO.replace("\n</div>", "\n" + HOST_DA_LEGENDA, 1))
    (pasta / "compositions").mkdir()
    (pasta / "compositions" / "legenda-de-passo.html").write_text(
        CARD_MONTADO.replace("DURACAO", str(duracao_do_card)), encoding="utf-8"
    )


def test_card_montado_que_preenche_o_slot_passa(tmp_path):
    montar_com_card(tmp_path, 60)
    assert checar_video_manual.checar(tmp_path) == []


def test_card_montado_com_timeline_mais_curto_que_o_slot_trava(tmp_path):
    montar_com_card(tmp_path, 4)
    problemas = checar_video_manual.checar(tmp_path)
    assert len(problemas) == 1
    assert "legenda-de-passo" in problemas[0]


def test_card_com_hex_dentro_da_composicao_do_video_trava(tmp_path):
    """O card copiado para compositions/ é parte do vídeo e segue os mesmos gates."""
    montar_com_card(tmp_path, 60)
    card = (
        tmp_path
        / "video"
        / "ouvidoria"
        / "registrar-manifestacao-pelo-formulario"
        / "compositions"
        / "legenda-de-passo.html"
    )
    card.write_text(
        card.read_text(encoding="utf-8").replace("var(--video-legenda-fundo)", "#1A1C4E"),
        encoding="utf-8",
    )
    problemas = checar_video_manual.checar(tmp_path)
    assert len(problemas) == 1
    assert "#1A1C4E" in problemas[0]


ANTIGA = "<body><div style=\"color:#2B2E7E;font-family:'HP Simplified'\"></div></body>"


def test_composicao_pendente_de_rerender_fica_fora_dos_gates_novos(tmp_path):
    """Os vídeos de antes do estilo saem da lista quando a campanha os refaz."""
    montar(tmp_path, corpo=ANTIGA, com_verify=False)
    estilo = tmp_path / "video" / "_estilo"
    estilo.mkdir()
    (estilo / "pendentes-de-rerender.txt").write_text(
        "# vídeos de antes do Estilo do manual\nouvidoria/registrar-manifestacao-pelo-formulario\n",
        encoding="utf-8",
    )
    assert checar_video_manual.checar(tmp_path) == []


def test_composicao_antiga_fora_da_lista_de_pendentes_trava(tmp_path):
    montar(tmp_path, corpo=ANTIGA, com_verify=False)
    problemas = checar_video_manual.checar(tmp_path)
    assert any("VERIFY.md" in p for p in problemas)
    assert any("#2B2E7E" in p for p in problemas)


def test_pasta_do_estilo_nao_e_composicao_orfa(tmp_path):
    """`video/_estilo/` guarda os cards e as fichas: não é módulo nem vídeo."""
    montar(tmp_path)
    card = tmp_path / "video" / "_estilo" / "cards" / "legenda-de-passo"
    card.mkdir(parents=True)
    (card / "index.html").write_text(CARD_MONTADO.replace("DURACAO", "60"), encoding="utf-8")
    (tmp_path / "video" / "_estilo" / "references").mkdir()
    assert checar_video_manual.checar(tmp_path) == []


def test_card_do_estilo_com_hex_trava(tmp_path):
    """O card da biblioteca vira cópia em todo vídeo: o erro dele se espalha."""
    montar(tmp_path)
    card = tmp_path / "video" / "_estilo" / "cards" / "legenda-de-passo"
    card.mkdir(parents=True)
    (card / "index.html").write_text(
        CARD_MONTADO.replace("DURACAO", "60").replace("var(--video-legenda-fundo)", "#1A1C4E"),
        encoding="utf-8",
    )
    problemas = checar_video_manual.checar(tmp_path)
    assert len(problemas) == 1
    assert "_estilo/cards/legenda-de-passo" in problemas[0]
