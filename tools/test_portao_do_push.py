"""Portão do push: as guardas de migration do CI rodam antes do push.

Monta um clone `git` de verdade com um remoto em `tmp_path`, copia o portão e
as guardas para ele e roda o portão como o `pre-push` roda, com a linha do push
na entrada padrão. O `uv` do PATH é trocado por um que chama este Python, porque
o runner das ferramentas não tem `uv`.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
PASTA = "hospital-reunioes/supabase/migrations"
ZERO = "0" * 40
RECIBO = "INSERT INTO migracoes_aplicadas (numero) VALUES ({n}) ON CONFLICT (numero) DO NOTHING;\n"
ENV_GIT = {
    **os.environ,
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "teste",
    "GIT_AUTHOR_EMAIL": "teste@example.com",
    "GIT_COMMITTER_NAME": "teste",
    "GIT_COMMITTER_EMAIL": "teste@example.com",
}


def git(repo: Path, *args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=repo, env=ENV_GIT, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


@pytest.fixture
def clone(tmp_path: Path) -> Path:
    remoto = tmp_path / "remoto.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(remoto))
    repo = tmp_path / "clone"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    git(repo, "remote", "add", "origin", str(remoto))
    for nome in ("portao_do_push.sh", "checar_migration_repetida.py", "checar_recibo_da_migration.py"):
        destino = repo / "tools" / nome
        destino.parent.mkdir(exist_ok=True)
        shutil.copy(RAIZ / "tools" / nome, destino)
    (repo / PASTA).mkdir(parents=True)
    (repo / PASTA / "136_antiga.sql").write_text("SELECT 1;\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "base")
    git(repo, "push", "-q", "origin", "main")
    git(repo, "checkout", "-q", "-b", "feat/x")
    return repo


@pytest.fixture
def env(tmp_path: Path) -> dict[str, str]:
    """`uv run --no-project --python 3.12 python ARGS` vira `<este python> ARGS`."""
    bin_falso = tmp_path / "bin"
    bin_falso.mkdir()
    uv = bin_falso / "uv"
    uv.write_text(f'#!/bin/sh\nshift 5\nexec "{sys.executable}" "$@"\n', encoding="utf-8")
    uv.chmod(uv.stat().st_mode | stat.S_IEXEC)
    return {**ENV_GIT, "PATH": f"{bin_falso}{os.pathsep}{os.environ['PATH']}"}


def migration(repo: Path, nome: str, sql: str) -> str:
    (repo / PASTA / nome).write_text(sql, encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", nome)
    return git(repo, "rev-parse", "HEAD")


def portao(repo: Path, env: dict[str, str], linha: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "tools/portao_do_push.sh"],
        cwd=repo,
        env=env,
        input=linha + "\n",
        capture_output=True,
        text=True,
    )


def test_migration_sem_recibo_para_o_push(clone: Path, env: dict[str, str]):
    sha = migration(clone, "137_nova.sql", "CREATE TABLE t (id int);\n")

    proc = portao(clone, env, f"refs/heads/feat/x {sha} refs/heads/feat/x {ZERO}")

    assert proc.returncode == 1
    assert "137_nova.sql precisa terminar com" in proc.stdout
    assert "migration com recibo" in proc.stdout


def test_migration_com_numero_da_base_para_o_push(clone: Path, env: dict[str, str]):
    sha = migration(clone, "136_repetida.sql", "SELECT 1;\n" + RECIBO.format(n=136))

    proc = portao(clone, env, f"refs/heads/feat/x {sha} refs/heads/feat/x {ZERO}")

    assert proc.returncode == 1
    assert "migration com número repetido" in proc.stdout


def test_migration_certa_passa(clone: Path, env: dict[str, str]):
    sha = migration(clone, "137_nova.sql", "CREATE TABLE t (id int);\n" + RECIBO.format(n=137))

    proc = portao(clone, env, f"refs/heads/feat/x {sha} refs/heads/feat/x {ZERO}")

    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_push_sem_migration_nem_backend_nao_confere_nada(clone: Path, env: dict[str, str]):
    (clone / "README.md").write_text("oi\n", encoding="utf-8")
    git(clone, "add", "-A")
    git(clone, "commit", "-q", "-m", "doc")
    sha = git(clone, "rev-parse", "HEAD")

    proc = portao(clone, env, f"refs/heads/feat/x {sha} refs/heads/feat/x {ZERO}")

    assert proc.returncode == 0
    assert proc.stdout == ""


@pytest.mark.parametrize(
    "remoto",
    ["refs/tags/v1.0.0", "refs/heads/main"],
    ids=["tag da subida", "main"],
)
def test_tag_e_main_nao_passam_pelo_portao(clone: Path, env: dict[str, str], remoto: str):
    sha = migration(clone, "137_nova.sql", "CREATE TABLE t (id int);\n")

    proc = portao(clone, env, f"refs/heads/feat/x {sha} {remoto} {ZERO}")

    assert proc.returncode == 0


def test_apagar_branch_remota_nao_passa_pelo_portao(clone: Path, env: dict[str, str]):
    proc = portao(clone, env, f"(delete) {ZERO} refs/heads/feat/x {ZERO}")

    assert proc.returncode == 0
