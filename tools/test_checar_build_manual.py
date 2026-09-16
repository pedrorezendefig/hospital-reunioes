"""Testes do conferidor do build do Manual (tools/checar_build_manual.py).

Cada teste monta um par (conteúdo, dist) num diretório temporário: uma página
publicada, uma página publicada dentro da subpasta `como-funciona/` e uma
página `draft: true`. O conferidor tem que provar o que o site promete ao
usuário: o que está em draft não vira página nem entra na busca, o que está
publicado entra nas duas, o ícone que o HTML declara existe no dist, e nenhum
grupo da sidebar mostra o nome cru da pasta.

O HTML do dist é escrito à mão aqui, com a forma que o Starlight gera: um
`<link rel=...icon...>` no head e o rótulo do grupo num `<span>`. É o que o
conferidor lê, então é o que o teste precisa imitar.
"""

from __future__ import annotations

import gzip
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import checar_build_manual  # noqa: E402

CONFERIDOR = Path(__file__).resolve().parent / "checar_build_manual.py"

PUBLICADA = """---
title: Entrar na plataforma
prd: [731]
draft: false
papel: [Todo mundo]
---

Clique em **Entrar**.
"""

RASCUNHO = """---
title: Ouvidoria
prd: [731]
draft: true
---

Ainda em produção.
"""

DENTRO_DA_SUBPASTA = """---
title: O que é a plataforma
prd: [731]
draft: false
papel: [Todo mundo]
---

Um lugar só para reunião, meta e POP.
"""


def html_pagina(*, rotulo: str = "Como funciona", icone: str | None = "/favicon.png") -> str:
    """O HTML como o Starlight gera: ícone no head, rótulo do grupo na sidebar."""
    link = (
        f'<link rel="shortcut icon" href="{icone}" type="image/png"/>'
        if icone is not None
        else ""
    )
    return (
        f"<html><head>{link}</head><body><nav>"
        f'<span class="group-label"><span class="large">{rotulo}</span></span>'
        "</nav></body></html>"
    )


def montar(
    raiz: Path,
    *,
    draft_no_dist: bool = False,
    draft_na_busca: bool = False,
    icone: str | None = "/favicon.png",
    icone_no_dist: bool = True,
    rotulo: str = "Como funciona",
):
    conteudo = raiz / "src" / "content" / "docs"
    (conteudo / "primeiros-passos" / "como-funciona").mkdir(parents=True)
    (conteudo / "ouvidoria").mkdir(parents=True)
    (conteudo / "primeiros-passos" / "entrar-na-plataforma.md").write_text(
        PUBLICADA, encoding="utf-8"
    )
    (conteudo / "primeiros-passos" / "como-funciona" / "o-que-e.md").write_text(
        DENTRO_DA_SUBPASTA, encoding="utf-8"
    )
    (conteudo / "ouvidoria" / "index.md").write_text(RASCUNHO, encoding="utf-8")

    dist = raiz / "dist"
    html = html_pagina(rotulo=rotulo, icone=icone)
    urls = []
    for caminho, url in (
        (
            dist / "primeiros-passos" / "entrar-na-plataforma",
            "/primeiros-passos/entrar-na-plataforma/",
        ),
        (
            dist / "primeiros-passos" / "como-funciona" / "o-que-e",
            "/primeiros-passos/como-funciona/o-que-e/",
        ),
    ):
        caminho.mkdir(parents=True)
        (caminho / "index.html").write_text(html, encoding="utf-8")
        urls.append(url)

    if icone is not None and icone_no_dist and icone.startswith("/"):
        alvo = dist / icone.lstrip("/")
        alvo.parent.mkdir(parents=True, exist_ok=True)
        alvo.write_bytes(b"\x89PNG\r\n\x1a\n")

    if draft_no_dist:
        (dist / "ouvidoria").mkdir(parents=True)
        (dist / "ouvidoria" / "index.html").write_text(html, encoding="utf-8")
    if draft_na_busca:
        urls.append("/ouvidoria/")

    fragmentos = dist / "pagefind" / "fragment"
    fragmentos.mkdir(parents=True)
    for i, url in enumerate(urls):
        corpo = b"pagefind_dcd" + json.dumps({"url": url, "content": "x"}).encode()
        (fragmentos / f"pt-br_{i}.pf_fragment").write_bytes(gzip.compress(corpo))
    return dist


def test_draft_fora_do_dist_e_da_busca_passa(tmp_path):
    montar(tmp_path)
    assert checar_build_manual.checar(tmp_path) == []


def test_draft_que_virou_pagina_trava(tmp_path):
    montar(tmp_path, draft_no_dist=True)
    problemas = checar_build_manual.checar(tmp_path)
    assert len(problemas) == 1
    # "ouvidoria" sai nas duas mensagens de draft e no caminho do arquivo.
    assert "virou página em dist" in problemas[0]


def test_draft_que_entrou_na_busca_trava(tmp_path):
    montar(tmp_path, draft_na_busca=True)
    problemas = checar_build_manual.checar(tmp_path)
    assert len(problemas) == 1
    assert "busca" in problemas[0]


def test_busca_sem_a_pagina_publicada_trava(tmp_path):
    """Piso de sanidade: sem isto, um dist vazio passaria como 'nenhum draft'."""
    dist = montar(tmp_path)
    for fragmento in (dist / "pagefind" / "fragment").glob("*.pf_fragment"):
        fragmento.unlink()
    problemas = checar_build_manual.checar(tmp_path)
    assert len(problemas) == 2
    assert any("entrar-na-plataforma" in p for p in problemas)
    assert any("o-que-e" in p for p in problemas)


def rodar(raiz: Path) -> subprocess.CompletedProcess[str]:
    """O conferidor como o CI chama: o que trava o merge é o código de saída."""
    return subprocess.run(
        [sys.executable, str(CONFERIDOR), "--dir", str(raiz)],
        capture_output=True,
        text=True,
    )


def test_draft_no_ar_sai_com_codigo_1(tmp_path):
    montar(tmp_path, draft_no_dist=True)
    resultado = rodar(tmp_path)
    assert resultado.returncode == 1
    assert "Conferidor do build do Manual falhou" in resultado.stderr


def test_build_correto_sai_com_codigo_0(tmp_path):
    montar(tmp_path)
    resultado = rodar(tmp_path)
    assert resultado.returncode == 0, resultado.stderr


def test_sem_dist_sai_com_codigo_1(tmp_path):
    """Sem build, o conferidor não pode dizer que está tudo certo."""
    (tmp_path / "src" / "content" / "docs").mkdir(parents=True)
    resultado = rodar(tmp_path)
    assert resultado.returncode == 1
    assert "dist" in resultado.stderr


# --- Ícone declarado no HTML x arquivo no dist -------------------------------
#
# O site pediu `/favicon.svg` por meses sem ele existir no dist, e o build
# ficava verde. Quem fica vermelho agora é o conferidor.


def test_icone_declarado_sem_arquivo_no_dist_trava(tmp_path):
    montar(tmp_path, icone_no_dist=False)
    problemas = checar_build_manual.checar(tmp_path)
    assert len(problemas) == 1
    assert "/favicon.png" in problemas[0]
    assert "não existe em dist" in problemas[0]


def test_icone_de_qualquer_rel_e_extensao_vale(tmp_path):
    """Trocar de ícone amanhã não pode quebrar o conferidor por motivo errado."""
    montar(tmp_path, icone="/icone-do-hospital.svg")
    assert checar_build_manual.checar(tmp_path) == []

    outra = tmp_path / "outra"
    montar(outra, icone="/icone-do-hospital.svg", icone_no_dist=False)
    problemas = checar_build_manual.checar(outra)
    assert len(problemas) == 1
    assert "/icone-do-hospital.svg" in problemas[0]


def test_icone_em_url_externa_nao_e_cobrado_no_dist(tmp_path):
    """Ícone hospedado fora não tem arquivo no dist, e isso não é erro."""
    montar(tmp_path, icone="https://exemplo.test/icone.png", icone_no_dist=False)
    assert checar_build_manual.checar(tmp_path) == []


def test_html_sem_nenhum_icone_trava(tmp_path):
    """Vácuo: zero ícone achado é varredura quebrada, não site sem ícone.

    Sem este piso, um regex que parasse de casar deixaria a checagem verde
    sobre nada, que é exatamente o pecado que este conferidor existe para
    tirar do CI.
    """
    montar(tmp_path, icone=None)
    problemas = checar_build_manual.checar(tmp_path)
    assert len(problemas) == 1
    assert "nenhuma página do dist declarou ícone" in problemas[0]


def test_extrair_icone_ignora_link_que_nao_e_icone():
    """`rel="stylesheet"` e `rel="canonical"` não são ícone."""
    html = (
        '<link rel="stylesheet" href="/estilo.css"/>'
        '<link rel="canonical" href="/pagina/"/>'
        '<link rel="apple-touch-icon" href="/toque.png"/>'
    )
    assert checar_build_manual.icones_declarados(html) == {"/toque.png"}


# --- Rótulo cru de pasta na sidebar ------------------------------------------
#
# O `autogenerate` do Starlight rotula o grupo com o nome do diretório, e quem
# conserta é o route middleware do `astro.config.mjs`. Apagar aquela linha
# devolvia `como-funciona` para a tela com o build verde.


def test_rotulo_cru_da_pasta_na_sidebar_trava(tmp_path):
    montar(tmp_path, rotulo="como-funciona")
    problemas = checar_build_manual.checar(tmp_path)
    assert len(problemas) == 1
    assert "como-funciona" in problemas[0]
    assert "rotulos-da-sidebar" in problemas[0]


def test_uma_linha_por_pasta_e_nao_uma_por_pagina(tmp_path):
    """A sidebar sai em toda página: 2 páginas erradas, 1 linha de erro."""
    dist = montar(tmp_path, rotulo="como-funciona")
    assert len(list(dist.rglob("*.html"))) == 2
    problemas = checar_build_manual.checar(tmp_path)
    assert len(problemas) == 1
    assert "2 página(s)" in problemas[0]


def test_rotulo_escrito_por_gente_passa(tmp_path):
    montar(tmp_path, rotulo="Como funciona")
    assert checar_build_manual.checar(tmp_path) == []


def test_so_subpasta_vira_grupo_autogerado(tmp_path):
    """O módulo (`primeiros-passos/`) tem rótulo escrito à mão no astro.config
    e o nome dele aparece em link e breadcrumb do HTML. Cobrar o nome do módulo
    aqui encheria o conferidor de falso positivo."""
    montar(tmp_path)
    assert checar_build_manual.pastas_que_viram_grupo(
        tmp_path / "src" / "content" / "docs"
    ) == {"como-funciona"}


# --- O que o CI lê: o código de saída ----------------------------------------


def test_icone_ausente_sai_com_codigo_1(tmp_path):
    montar(tmp_path, icone_no_dist=False)
    resultado = rodar(tmp_path)
    assert resultado.returncode == 1
    assert "Conferidor do build do Manual falhou" in resultado.stderr


def test_rotulo_cru_sai_com_codigo_1(tmp_path):
    montar(tmp_path, rotulo="como-funciona")
    resultado = rodar(tmp_path)
    assert resultado.returncode == 1
    assert "Conferidor do build do Manual falhou" in resultado.stderr
