"""Testes do lint do cabeçalho das skills (tools/lint_skills.py), issue #807.

Cada teste monta uma pasta de skills mínima num diretório temporário e roda o
lint contra ela, como o CI faz. O último roda contra o `.claude/skills/` real.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

LINT = Path(__file__).resolve().parent / "lint_skills.py"


def _skill(raiz: Path, nome: str, conteudo: str) -> Path:
    pasta = raiz / nome
    pasta.mkdir(parents=True)
    arquivo = pasta / "SKILL.md"
    arquivo.write_bytes(conteudo.encode("utf-8"))
    return arquivo


def _rodar(pasta: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(LINT), "--dir", str(pasta)],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def test_skill_com_nome_e_descricao_passa(tmp_path: Path) -> None:
    _skill(
        tmp_path,
        "deploy",
        "---\nname: deploy\ndescription: 'Deploy via Coolify. Modos: ship, status.'\n---\n\n# Deploy\n",
    )

    resultado = _rodar(tmp_path)

    assert resultado.returncode == 0, resultado.stdout + resultado.stderr


def test_descricao_sem_aspas_com_dois_pontos_quebra_o_cabecalho(tmp_path: Path) -> None:
    # O mutante da issue #807: o `: ` no meio da descrição sem aspas vira uma
    # chave nova para o YAML, e o Claude Code descarta o cabeçalho em silêncio.
    _skill(tmp_path, "ok", "---\nname: ok\ndescription: 'Tudo certo.'\n---\n")
    _skill(
        tmp_path,
        "ship",
        "---\nname: ship\ndescription: Ciclo completo de uma mudança: branch, commit, PR.\n---\n",
    )

    resultado = _rodar(tmp_path)

    assert resultado.returncode == 1
    linhas = resultado.stdout.splitlines()
    assert len(linhas) == 1, resultado.stdout
    assert "ship" in linhas[0] and "SKILL.md" in linhas[0]


def test_skill_sem_nome_ou_sem_descricao_falha(tmp_path: Path) -> None:
    _skill(tmp_path, "sem-nome", "---\ndescription: 'Faz algo.'\n---\n")
    _skill(tmp_path, "sem-descricao", "---\nname: sem-descricao\n---\n")
    _skill(tmp_path, "descricao-vazia", "---\nname: descricao-vazia\ndescription:\n---\n")

    resultado = _rodar(tmp_path)

    assert resultado.returncode == 1
    linhas = resultado.stdout.splitlines()
    assert len(linhas) == 3, resultado.stdout
    assert any("sem-nome" in linha and "`name`" in linha for linha in linhas)
    assert any("sem-descricao" in linha and "`description`" in linha for linha in linhas)
    assert any("descricao-vazia" in linha and "`description`" in linha for linha in linhas)


def test_skill_sem_cabecalho_falha(tmp_path: Path) -> None:
    _skill(tmp_path, "solta", "# Solta\n\nSem cabeçalho nenhum.\n")

    resultado = _rodar(tmp_path)

    assert resultado.returncode == 1
    assert "solta" in resultado.stdout


def test_cabecalho_com_quebra_de_linha_do_windows_passa(tmp_path: Path) -> None:
    _skill(
        tmp_path,
        "windows",
        "---\r\nname: windows\r\ndescription: 'Salva no Windows: CRLF.'\r\n---\r\n\r\n# Windows\r\n",
    )

    resultado = _rodar(tmp_path)

    assert resultado.returncode == 0, resultado.stdout + resultado.stderr


def test_pasta_sem_nenhuma_skill_falha(tmp_path: Path) -> None:
    # Caminho errado no --dir não pode deixar o CI verde sobre varredura vazia.
    resultado = _rodar(tmp_path)

    assert resultado.returncode == 1
    assert "nenhum" in resultado.stdout.lower()


def test_todas_as_skills_do_repo_tem_cabecalho_valido() -> None:
    skills = Path(__file__).resolve().parent.parent / ".claude" / "skills"

    resultado = _rodar(skills)

    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
