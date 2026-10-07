"""O slug da pasta de projeto do `medir_onda.py` (issue #900).

O Claude Code nomeia `~/.claude/projects/<slug>` trocando todo caractere que não
é letra ou dígito ASCII por hífen. Os nomes esperados abaixo foram copiados de
pastas reais de `~/.claude/projects` (e o de Windows, da pasta citada na issue):
o espaço, o til, o ponto e o sublinhado viram hífen.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
SCRIPT = RAIZ / ".claude" / "skills" / "onda-enxuta" / "scripts" / "medir_onda.py"


def _carregar():
    spec = importlib.util.spec_from_file_location("medir_onda", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


medir_onda = _carregar()


@pytest.mark.parametrize(
    ("cwd", "pasta_real"),
    [
        (
            "/Users/pedrorezende/Library/Mobile Documents/iCloud~md~obsidian/Documents",
            "-Users-pedrorezende-Library-Mobile-Documents-iCloud-md-obsidian-Documents",
        ),
        (
            r"C:\Users\lucas\Documents\PROJETOS VITTA\APP Hospital\hospital-reunioes",
            "C--Users-lucas-Documents-PROJETOS-VITTA-APP-Hospital-hospital-reunioes",
        ),
        (
            "/Users/pedrorezende/PedroDev/Hospital/.claude/worktrees/agent-a02144276960ddd00",
            "-Users-pedrorezende-PedroDev-Hospital--claude-worktrees-agent-a02144276960ddd00",
        ),
        (
            "/Users/pedrorezende/PedroDev/Vertex_Analyzer",
            "-Users-pedrorezende-PedroDev-Vertex-Analyzer",
        ),
    ],
)
def test_slug_casa_com_a_pasta_que_o_claude_code_cria(cwd, pasta_real):
    assert medir_onda.slug_do_projeto(cwd) == pasta_real


def test_acha_pastas_de_projeto_e_tasks_com_dois_espacos_no_caminho(tmp_path, monkeypatch):
    cwd = r"C:\Users\lucas\Documents\PROJETOS VITTA\APP Hospital\hospital-reunioes"
    pasta = "C--Users-lucas-Documents-PROJETOS-VITTA-APP-Hospital-hospital-reunioes"
    sessao = "827ab7e3-0000-0000-0000-000000000000"

    home = tmp_path / "home"
    projeto = home / ".claude" / "projects" / pasta
    projeto.mkdir(parents=True)
    local = tmp_path / "AppData" / "Local"
    tasks = local / "Temp" / "claude" / pasta / sessao / "tasks"
    tasks.mkdir(parents=True)

    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("LOCALAPPDATA", str(local))

    assert medir_onda.achar_pasta_projeto(cwd) == projeto
    assert medir_onda.achar_pasta_tasks(cwd, sessao) == tasks
