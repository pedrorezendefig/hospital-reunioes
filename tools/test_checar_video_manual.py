"""Testes do conferidor do vídeo do Manual (tools/checar_video_manual.py).

Cada teste monta um manual mínimo num diretório temporário: a abertura de um
módulo que declara `video` e a composição correspondente. O conferidor prova o
que o ADR 0057 (decisão 3) promete e a issue #736 cobra: todo vídeo que uma
página exibe tem composição versionada com carimbo de geração, e o MP4, que é
regerável, não mora na árvore versionada. Desde a issue #1260 o vídeo é o de
visão geral, um por módulo, na abertura: Página de tarefa não exibe vídeo.
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
title: Ouvidoria
prd: [731]
draft: true
video: visao-geral
---

A Ouvidoria recebe a manifestação e a leva até o setor.
"""

TAREFA = """---
title: Registrar uma manifestação pelo formulário
prd: [731]
draft: true
papel: [Sem login]
---

Escreva o seu relato e clique em **Enviar manifestação**.
"""

CARIMBO = {
    "modulo": "ouvidoria",
    "slug": "visao-geral",
    "pagina": "ouvidoria/index.md",
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
    (conteudo / "index.md").write_text(PAGINA_COM_VIDEO, encoding="utf-8")
    (conteudo / "registrar-manifestacao-pelo-formulario.md").write_text(
        TAREFA, encoding="utf-8"
    )
    pasta = raiz / "video" / "ouvidoria" / "visao-geral"
    if com_composicao:
        pasta.mkdir(parents=True)
        (pasta / "index.html").write_text(composicao(carimbo, corpo), encoding="utf-8")
        if com_verify:
            (pasta / "VERIFY.md").write_text(
                "# VERIFY\n\nStrips de cada corte conferidas.\n", encoding="utf-8"
            )
    if mp4_versionado:
        pasta.mkdir(parents=True, exist_ok=True)
        (pasta / "visao-geral.mp4").write_bytes(b"x")
    return pasta


def test_abertura_com_composicao_e_carimbo_passa(tmp_path):
    montar(tmp_path)
    assert checar_video_manual.checar(tmp_path) == []


def test_abertura_com_video_sem_composicao_trava(tmp_path):
    montar(tmp_path, com_composicao=False)
    problemas = checar_video_manual.checar(tmp_path)
    assert len(problemas) == 1
    assert "não tem composição" in problemas[0]
    assert "video/ouvidoria/visao-geral/index.html" in problemas[0]


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
    (rendido / "visao-geral.mp4").write_bytes(b"x")
    assert checar_video_manual.checar(tmp_path) == []


def test_mp4_em_renders_passa(tmp_path):
    """`renders/` é onde o HyperFrames larga o MP4 sozinho, e é git-ignored."""
    montar(tmp_path)
    sobra = (
        tmp_path
        / "video"
        / "ouvidoria"
        / "visao-geral"
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


def test_abertura_sem_video_passa(tmp_path):
    """Módulo ainda sem Vídeo de visão geral publica sem ele (o Admin nem tem)."""
    montar(tmp_path, com_composicao=False)
    abertura = tmp_path / "src" / "content" / "docs" / "ouvidoria" / "index.md"
    abertura.write_text(
        PAGINA_COM_VIDEO.replace("video: visao-geral\n", ""), encoding="utf-8"
    )
    assert checar_video_manual.checar(tmp_path) == []


def test_pagina_de_tarefa_sem_video_nao_e_acusada(tmp_path):
    """O Vídeo de tarefa saiu do Manual: a tarefa sem vídeo é o normal."""
    montar(tmp_path)
    problemas = checar_video_manual.checar(tmp_path)
    assert not any("registrar-manifestacao-pelo-formulario" in p for p in problemas)
    assert problemas == []


def test_pagina_de_tarefa_com_video_trava(tmp_path):
    """O tema só desenha vídeo na abertura: o campo na tarefa sumiria calado."""
    montar(tmp_path)
    tarefa = (
        tmp_path
        / "src"
        / "content"
        / "docs"
        / "ouvidoria"
        / "registrar-manifestacao-pelo-formulario.md"
    )
    tarefa.write_text(
        TAREFA.replace("papel:", "video: registrar\npapel:"), encoding="utf-8"
    )
    problemas = checar_video_manual.checar(tmp_path)
    assert len(problemas) == 1
    assert "registrar-manifestacao-pelo-formulario.md" in problemas[0]
    assert "abertura" in problemas[0]


HOME = """---
title: Manual da plataforma
template: splash
video: conheca-a-plataforma
---
"""

ABERTURA_PP = """---
title: Primeiros passos
video: conheca-a-plataforma
---
"""

CARIMBO_PP = {
    **CARIMBO,
    "modulo": "primeiros-passos",
    "slug": "conheca-a-plataforma",
    "pagina": "primeiros-passos/index.md",
}


def montar_conheca_a_plataforma(raiz: Path, *, com_composicao: bool = True) -> None:
    """A página inicial e a abertura de Primeiros passos mostram o mesmo vídeo."""
    montar(raiz)
    conteudo = raiz / "src" / "content" / "docs"
    (conteudo / "index.mdx").write_text(HOME, encoding="utf-8")
    (conteudo / "primeiros-passos").mkdir()
    (conteudo / "primeiros-passos" / "index.md").write_text(
        ABERTURA_PP, encoding="utf-8"
    )
    if com_composicao:
        pasta = raiz / "video" / "primeiros-passos" / "conheca-a-plataforma"
        pasta.mkdir(parents=True)
        (pasta / "index.html").write_text(composicao(CARIMBO_PP), encoding="utf-8")
        (pasta / "VERIFY.md").write_text("# VERIFY\n", encoding="utf-8")


def test_pagina_inicial_usa_o_video_de_primeiros_passos(tmp_path):
    montar_conheca_a_plataforma(tmp_path)
    assert checar_video_manual.checar(tmp_path) == []


def test_pagina_inicial_com_video_sem_composicao_trava(tmp_path):
    montar(tmp_path)
    (tmp_path / "src" / "content" / "docs" / "index.mdx").write_text(
        HOME, encoding="utf-8"
    )
    problemas = checar_video_manual.checar(tmp_path)
    assert len(problemas) == 1
    assert "video/primeiros-passos/conheca-a-plataforma/index.html" in problemas[0]


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
    assert "Conferidor do vídeo do Manual falhou" in resultado.stderr


def test_manual_em_ordem_sai_com_codigo_0(tmp_path):
    montar(tmp_path)
    resultado = rodar(tmp_path)
    assert resultado.returncode == 0, resultado.stderr


# Os gates do Estilo do manual (emenda de 13/10/2026 à ADR 0057, issue #1230).
# Cada teste quebra uma coisa só na composição em ordem e espera um problema.


def test_video_sem_verify_trava(tmp_path):
    """Sem VERIFY.md ninguém sabe o que foi conferido antes do render final."""
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
            "{ opacity: 1, duration: 0.4 }",
            '{ opacity: 1, color: "#2b2e7e", duration: 0.4 }',
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
        corpo=CORPO_NO_ESTILO.replace(
            "font-family: var(--font-app)", "font-family: Arial"
        ),
    )
    problemas = checar_video_manual.checar(tmp_path)
    assert len(problemas) == 1
    assert "Arial" in problemas[0]


def test_timeline_mais_curto_que_o_slot_trava(tmp_path):
    """O kit viu quadro preto quando o timeline acaba antes do `data-duration`."""
    montar(
        tmp_path,
        corpo=CORPO_NO_ESTILO.replace(
            "tl.to({}, { duration: 42 }, 0);", "tl.to({}, { duration: 30 }, 0);"
        ),
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
    pasta = montar(
        tmp_path, corpo=CORPO_NO_ESTILO.replace("\n</div>", "\n" + HOST_DA_LEGENDA, 1)
    )
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
        / "visao-geral"
        / "compositions"
        / "legenda-de-passo.html"
    )
    card.write_text(
        card.read_text(encoding="utf-8").replace(
            "var(--video-legenda-fundo)", "#1A1C4E"
        ),
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
        "# vídeos de antes do Estilo do manual\nouvidoria/visao-geral\n",
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
    (card / "index.html").write_text(
        CARD_MONTADO.replace("DURACAO", "60"), encoding="utf-8"
    )
    (tmp_path / "video" / "_estilo" / "references").mkdir()
    assert checar_video_manual.checar(tmp_path) == []


def test_card_do_estilo_com_hex_trava(tmp_path):
    """O card da biblioteca vira cópia em todo vídeo: o erro dele se espalha."""
    montar(tmp_path)
    card = tmp_path / "video" / "_estilo" / "cards" / "legenda-de-passo"
    card.mkdir(parents=True)
    (card / "index.html").write_text(
        CARD_MONTADO.replace("DURACAO", "60").replace(
            "var(--video-legenda-fundo)", "#1A1C4E"
        ),
        encoding="utf-8",
    )
    problemas = checar_video_manual.checar(tmp_path)
    assert len(problemas) == 1
    assert "_estilo/cards/legenda-de-passo" in problemas[0]


# A réplica da tela e os cards dividem a mesma página depois de montados: uma
# regra de classe da raiz pega também o elemento do card que tem a mesma
# classe. No piloto (issue #1231), o `.tela` da réplica jogou o nome da tela do
# lower-third para cima do lugar, e o `.cartao` deformou o callout; o `check`
# do HyperFrames acusa só a sobreposição de texto, sem dizer de onde ela vem.
def montar_com_estilo_na_raiz(tmp_path: Path, estilo: str) -> None:
    montar_com_card(tmp_path, 60)
    pasta = tmp_path / "video" / "ouvidoria" / "visao-geral"
    raiz = pasta / "index.html"
    raiz.write_text(
        raiz.read_text(encoding="utf-8").replace(
            "</head>", f"<style>{estilo}</style></head>"
        ),
        encoding="utf-8",
    )


def test_classe_da_replica_com_o_nome_de_uma_classe_do_card_trava(tmp_path):
    montar_com_estilo_na_raiz(tmp_path, ".placa { position: absolute; top: 0; }")
    problemas = checar_video_manual.checar(tmp_path)
    assert len(problemas) == 1
    assert ".placa" in problemas[0]
    assert "compositions/legenda-de-passo.html" in problemas[0]


def test_classe_da_replica_com_nome_proprio_passa(tmp_path):
    montar_com_estilo_na_raiz(
        tmp_path,
        "@font-face { src: url('assets/fonts/x.ttf'); } .ap-placa { opacity: .5; }",
    )
    assert checar_video_manual.checar(tmp_path) == []
