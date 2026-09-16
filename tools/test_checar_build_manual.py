"""Testes do conferidor do build do Manual (tools/checar_build_manual.py).

Cada teste monta um par (conteúdo, dist) num diretório temporário: uma página
publicada e uma página `draft: true`. O conferidor tem que provar as duas
coisas que o ADR 0057 promete ao usuário: o que está em draft não vira página
nem entra na busca, e o que está publicado entra nas duas.
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


def montar(raiz: Path, *, draft_no_dist: bool = False, draft_na_busca: bool = False):
    conteudo = raiz / "src" / "content" / "docs"
    (conteudo / "primeiros-passos").mkdir(parents=True)
    (conteudo / "ouvidoria").mkdir(parents=True)
    (conteudo / "primeiros-passos" / "entrar-na-plataforma.md").write_text(
        PUBLICADA, encoding="utf-8"
    )
    (conteudo / "ouvidoria" / "index.md").write_text(RASCUNHO, encoding="utf-8")

    dist = raiz / "dist"
    pagina = dist / "primeiros-passos" / "entrar-na-plataforma"
    pagina.mkdir(parents=True)
    (pagina / "index.html").write_text("<html></html>", encoding="utf-8")
    urls = ["/primeiros-passos/entrar-na-plataforma/"]

    if draft_no_dist:
        (dist / "ouvidoria").mkdir(parents=True)
        (dist / "ouvidoria" / "index.html").write_text("<html></html>", encoding="utf-8")
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
    assert len(problemas) == 1
    assert "entrar-na-plataforma" in problemas[0]


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
