"""Testes do gerador dos tokens do Estilo do manual (tools/gerar_tokens_video.py).

O `tokens.css` dos Vídeos de tarefa sai do `globals.css` do frontend e nunca é
escrito à mão (emenda de 13/10/2026 à ADR 0057, issue #1230). O que o gerador
promete: a cor que o app mostra é a cor que o vídeo usa, e mudar uma no app
muda a outra na próxima geração.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

GERADOR = Path(__file__).resolve().parent / "gerar_tokens_video.py"

GLOBALS = """@import "tailwindcss";

@font-face {
  font-family: "HP Simplified";
  src: url("/fonts/HPSimplified_Rg.ttf") format("truetype");
  font-weight: 400;
  font-style: normal;
}

:root {
  --color-primary: #2B2E7E;       /* Navy (Logo) */
  --color-bg: #ffffff;
  --color-text: #1E293B;
}

@theme {
  --color-primary: var(--color-primary);
  --radius-lg: 4px;
}

body {
  font-family: "HP Simplified", system-ui, -apple-system, sans-serif;
}
"""

TEMA_TAILWIND = """@theme default {
  --font-mono: ui-monospace, SFMono-Regular, Menlo, monospace;
  --color-slate-500: oklch(55.4% 0.046 257.417);
  --color-white: #fff;
  --spacing: 0.25rem;
}
"""


def gerar(
    tmp_path: Path, globals_css: str
) -> tuple[subprocess.CompletedProcess[str], Path]:
    """O gerador como a receita manda rodar: lê arquivos, grava o tokens.css."""
    (tmp_path / "globals.css").write_text(globals_css, encoding="utf-8")
    (tmp_path / "theme.css").write_text(TEMA_TAILWIND, encoding="utf-8")
    saida = tmp_path / "_estilo" / "tokens.css"
    resultado = subprocess.run(
        [
            sys.executable,
            str(GERADOR),
            "--globals",
            str(tmp_path / "globals.css"),
            "--tema",
            str(tmp_path / "theme.css"),
            "--saida",
            str(saida),
        ],
        capture_output=True,
        text=True,
    )
    return resultado, saida


def test_mudar_a_cor_no_globals_muda_o_token(tmp_path):
    resultado, saida = gerar(tmp_path, GLOBALS)
    assert resultado.returncode == 0, resultado.stderr
    assert "--color-primary: #2B2E7E;" in saida.read_text(encoding="utf-8")

    resultado, saida = gerar(
        tmp_path,
        GLOBALS.replace("--color-primary: #2B2E7E;", "--color-primary: #7A1F3D;"),
    )
    assert resultado.returncode == 0, resultado.stderr
    tokens = saida.read_text(encoding="utf-8")
    assert "--color-primary: #7A1F3D;" in tokens
    assert "#2B2E7E" not in tokens


def test_paleta_que_o_app_herda_do_tailwind_vira_token(tmp_path):
    """A tela usa `text-slate-500` mais do que os tokens próprios: a réplica precisa dela."""
    resultado, saida = gerar(tmp_path, GLOBALS)
    assert resultado.returncode == 0, resultado.stderr
    tokens = saida.read_text(encoding="utf-8")
    assert "--color-slate-500: oklch(55.4% 0.046 257.417);" in tokens
    assert "--font-mono: ui-monospace, SFMono-Regular, Menlo, monospace;" in tokens
    assert (
        '--font-app: "HP Simplified", system-ui, -apple-system, sans-serif;' in tokens
    )
    assert 'src: url("assets/fonts/HPSimplified_Rg.ttf")' in tokens


def test_sem_o_tema_do_tailwind_o_gerador_para_em_vez_de_gerar_pela_metade(tmp_path):
    (tmp_path / "globals.css").write_text(GLOBALS, encoding="utf-8")
    saida = tmp_path / "tokens.css"
    resultado = subprocess.run(
        [
            sys.executable,
            str(GERADOR),
            "--globals",
            str(tmp_path / "globals.css"),
            "--tema",
            str(tmp_path / "nao-existe.css"),
            "--saida",
            str(saida),
        ],
        capture_output=True,
        text=True,
    )
    assert resultado.returncode == 1
    assert "theme.css" in resultado.stderr
    assert not saida.exists()
