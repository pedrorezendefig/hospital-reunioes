"""O manual entra no ar junto com a funcionalidade (issue #735).

Quem tira o `draft` das páginas não é gente: é o `/deploy ship`, logo depois do
bookkeeping, para cada PRD que subiu naquele deploy. Estes testes provam o que
o passo faz e, principalmente, o que ele **não** faz: página de PRD que ainda
não subiu continua invisível, e página que a publicação não conseguiria subir
não sai do draft, porque draft tirado sem publicação é página no repositório e
fora do ar.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import tirar_draft_manual  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
SCRIPT = RAIZ / "tools" / "tirar_draft_manual.py"

PAGINA = """---
title: Registrar uma manifestação
description: Uma frase.
prd: [{prds}]
draft: {draft}
papel: [Ouvidoria]{video}
---

## Quando usar
"""


def escrever(
    raiz: Path, caminho: str, prds: str, draft: str = "true", video: str = ""
) -> Path:
    arquivo = raiz / "src" / "content" / "docs" / caminho
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    arquivo.write_text(
        PAGINA.format(
            prds=prds, draft=draft, video=f"\nvideo: {video}" if video else ""
        ),
        encoding="utf-8",
    )
    return arquivo


def mp4(raiz: Path, modulo: str, slug: str) -> Path:
    """O MP4 renderizado, que não vem no clone e a publicação exige."""
    arquivo = raiz / "public" / "video" / modulo / f"{slug}.mp4"
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    arquivo.write_bytes(b"nao e um video de verdade")
    return arquivo


def caixa_de_ferramentas(
    node: str = "22.12.0", tem: tuple[str, ...] = ("corepack", "ffmpeg")
) -> str:
    """Uma pasta de PATH com o que a publicação exige, de mentira.

    O script confere a máquina antes de escrever, e a máquina de quem roda o
    teste não pode decidir o resultado.
    """
    pasta = Path(tempfile.mkdtemp())
    if node:
        (pasta / "node").write_text(f'#!/bin/sh\necho "v{node}"\n', encoding="utf-8")
        (pasta / "node").chmod(0o755)
    for binario in tem:
        (pasta / binario).write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        (pasta / binario).chmod(0o755)
    return str(pasta)


FERRAMENTAS_OK = caixa_de_ferramentas()


def rodar(
    raiz: Path, *args: str, path: str | None = None
) -> subprocess.CompletedProcess[str]:
    ambiente = dict(os.environ, PATH=path if path is not None else FERRAMENTAS_OK)
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--dir", str(raiz), *args],
        capture_output=True,
        text=True,
        env=ambiente,
    )


def test_pagina_do_prd_que_subiu_sai_do_draft(tmp_path):
    arquivo = escrever(tmp_path, "ouvidoria/registrar.md", "731")

    saida = rodar(tmp_path, "--prd", "731")

    assert saida.returncode == 0, saida.stderr
    assert "draft: false" in arquivo.read_text(encoding="utf-8")
    assert "ouvidoria/registrar.md" in saida.stdout


def test_pagina_de_outro_prd_fica_intacta(tmp_path):
    """O deploy de um PRD não pode publicar a tela que outro ainda não subiu."""
    arquivo = escrever(tmp_path, "pops/aprovar.md", "740")
    antes = arquivo.read_text(encoding="utf-8")

    saida = rodar(tmp_path, "--prd", "731")

    assert saida.returncode == 0, saida.stderr
    assert arquivo.read_text(encoding="utf-8") == antes


def test_sem_pagina_em_draft_o_passo_e_silencioso(tmp_path):
    """Critério de aceite da #735: sem draft, não faz nada e diz isso no log."""
    escrever(tmp_path, "ouvidoria/registrar.md", "731", draft="false")

    saida = rodar(tmp_path, "--prd", "731")

    assert saida.returncode == 0, saida.stderr
    assert "nenhuma página" in saida.stdout.lower()


def test_dry_run_diz_o_que_mudaria_sem_escrever(tmp_path):
    arquivo = escrever(tmp_path, "ouvidoria/registrar.md", "731")
    antes = arquivo.read_text(encoding="utf-8")

    saida = rodar(tmp_path, "--prd", "731", "--dry-run")

    assert saida.returncode == 0, saida.stderr
    assert "ouvidoria/registrar.md" in saida.stdout
    assert arquivo.read_text(encoding="utf-8") == antes


def test_comentario_na_linha_nao_engana_a_leitura(tmp_path):
    """O molde da `/manual` comenta a linha do `draft`, e o número do ADR mora
    no comentário do `prd`. Ler a linha crua publicaria a página errada."""
    pagina = tmp_path / "src" / "content" / "docs" / "ouvidoria" / "registrar.md"
    pagina.parent.mkdir(parents=True, exist_ok=True)
    pagina.write_text(
        "---\n"
        "title: Registrar\n"
        "prd: [731]                 # ADR 0057\n"
        "draft: true                # sai quando o PRD sobe para produção\n"
        "papel: [Ouvidoria]\n"
        "---\n\n## Quando usar\n",
        encoding="utf-8",
    )

    saida = rodar(tmp_path, "--prd", "57")
    assert "nenhuma página" in saida.stdout.lower(), "o 0057 do comentário virou PRD"

    rodar(tmp_path, "--prd", "731")
    texto = pagina.read_text(encoding="utf-8")
    assert "draft: false" in texto
    assert "sai quando o PRD sobe para produção" in texto


def test_pagina_de_varios_prds_sai_do_draft_uma_vez_so(tmp_path):
    """Página tocada por dois PRDs sobe quando os dois já subiram."""
    arquivo = escrever(tmp_path, "reunioes/criar-meta.md", "731, 740")

    saida = rodar(tmp_path, "--prd", "740", "--prd", "731")

    assert saida.returncode == 0, saida.stderr
    assert saida.stdout.count("reunioes/criar-meta.md") == 1
    assert "draft: false" in arquivo.read_text(encoding="utf-8")


def test_pagina_de_dois_prds_espera_os_dois_subirem(tmp_path):
    """Publicar no primeiro PRD poria no ar a tela do segundo, que não subiu."""
    arquivo = escrever(tmp_path, "reunioes/criar-meta.md", "731, 740")
    antes = arquivo.read_text(encoding="utf-8")

    saida = rodar(tmp_path, "--prd", "731")

    assert saida.returncode == 0, saida.stderr
    assert arquivo.read_text(encoding="utf-8") == antes


def test_pasta_sem_site_e_erro_de_uso(tmp_path):
    """Rodar na pasta errada não pode passar por 'nada em draft'."""
    saida = rodar(tmp_path / "vazio", "--prd", "731")

    assert saida.returncode == 1
    assert "src/content/docs" in saida.stderr


def test_draft_com_letra_maiuscula_nao_passa_por_publicado(tmp_path):
    """O frontmatter é lido em minúscula e escrito com a caixa que está lá."""
    pagina = tmp_path / "src" / "content" / "docs" / "ouvidoria" / "registrar.md"
    pagina.parent.mkdir(parents=True, exist_ok=True)
    pagina.write_text(
        "---\ntitle: Registrar\nprd: [731]\nDraft: true\npapel: [Ouvidoria]\n---\n",
        encoding="utf-8",
    )

    saida = rodar(tmp_path, "--prd", "731")

    assert saida.returncode == 0, saida.stderr
    assert "true" not in pagina.read_text(encoding="utf-8").lower()


def test_pagina_sem_linha_de_draft_nao_e_reescrita_em_silencio():
    """Seam do escritor: sem a linha, ninguém pode jurar que publicou."""
    assert tirar_draft_manual.sem_draft("---\ntitle: Registrar\n---\n") is None


def test_video_sem_mp4_nao_tira_o_draft(tmp_path):
    """O MP4 não vem no clone: sem ele, a publicação morre depois do commit."""
    arquivo = escrever(
        tmp_path, "ouvidoria/registrar.md", "731", video="registrar-pelo-formulario"
    )
    antes = arquivo.read_text(encoding="utf-8")

    saida = rodar(tmp_path, "--prd", "731")

    assert saida.returncode == 2
    assert arquivo.read_text(encoding="utf-8") == antes
    assert "registrar-pelo-formulario" in saida.stderr
    assert "video/ouvidoria/registrar-pelo-formulario" in saida.stderr


def test_video_com_mp4_renderizado_sai_do_draft(tmp_path):
    arquivo = escrever(
        tmp_path, "ouvidoria/registrar.md", "731", video="registrar-pelo-formulario"
    )
    mp4(tmp_path, "ouvidoria", "registrar-pelo-formulario")

    saida = rodar(tmp_path, "--prd", "731")

    assert saida.returncode == 0, saida.stderr
    assert "draft: false" in arquivo.read_text(encoding="utf-8")


def test_sem_ffmpeg_nao_tira_o_draft(tmp_path):
    """Publicar reencoda os vídeos: sem ffmpeg o site não sobe."""
    arquivo = escrever(tmp_path, "ouvidoria/registrar.md", "731")
    antes = arquivo.read_text(encoding="utf-8")

    saida = rodar(
        tmp_path, "--prd", "731", path=caixa_de_ferramentas(tem=("corepack",))
    )

    assert saida.returncode == 2
    assert arquivo.read_text(encoding="utf-8") == antes
    assert "ffmpeg" in saida.stderr


def test_node_velho_nao_tira_o_draft(tmp_path):
    """O site é Starlight: com Node velho o build morre depois do commit."""
    arquivo = escrever(tmp_path, "ouvidoria/registrar.md", "731")
    antes = arquivo.read_text(encoding="utf-8")

    saida = rodar(tmp_path, "--prd", "731", path=caixa_de_ferramentas(node="22.9.0"))

    assert saida.returncode == 2
    assert arquivo.read_text(encoding="utf-8") == antes
    assert "22.12" in saida.stderr
    assert "22.9.0" in saida.stderr


def test_nada_e_escrito_quando_uma_pagina_do_lote_trava(tmp_path):
    """Ou o PRD inteiro sai do draft, ou nada sai: meio caminho é o pior caso."""
    sem_video = escrever(tmp_path, "ouvidoria/registrar.md", "731")
    escrever(tmp_path, "ouvidoria/encaminhar.md", "731", video="encaminhar")
    antes = sem_video.read_text(encoding="utf-8")

    saida = rodar(tmp_path, "--prd", "731")

    assert saida.returncode == 2
    assert sem_video.read_text(encoding="utf-8") == antes
