"""Guarda de migration com número repetido (issue #903).

Duas sessões em paralelo podem escolher o mesmo próximo número de migration, e
o erro só aparecia depois de publicado. Estes testes montam um repositório
`git` de verdade em `tmp_path`, com uma `main` de base e uma branch por cima, e
provam o que a guarda recusa e, principalmente, o que ela deixa passar: branch
sem migration, número inédito, renomear ou editar migration que já existe.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import checar_migration_repetida  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
SCRIPT = RAIZ / "tools" / "checar_migration_repetida.py"
PASTA = "hospital-reunioes/supabase/migrations"

# Repositório isolado da configuração da máquina: assinatura de commit, nome
# do branch padrão e afins não podem mudar o resultado do teste.
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
    proc = subprocess.run(
        ["git", *args], cwd=repo, env=ENV_GIT, capture_output=True, text=True
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


def escrever(repo: Path, nome: str, sql: str = "select 1;\n") -> None:
    arquivo = repo / PASTA / nome
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    arquivo.write_text(sql, encoding="utf-8")


def commitar(repo: Path, msg: str) -> None:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", msg)


def repo_com_base(tmp_path: Path) -> Path:
    """`main` com 110 e 111; o teste continua numa branch `feature` por cima."""
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    escrever(repo, "110_ouvidoria_paciente_do_caso.sql")
    escrever(repo, "111_tecnologia_produto_central_de_comando.sql")
    commitar(repo, "base")
    git(repo, "checkout", "-q", "-b", "feature")
    return repo


def rodar(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--base", "main", *args],
        cwd=repo,
        env=ENV_GIT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def test_numero_repetido_falha_nomeando_o_numero_e_os_dois_arquivos(tmp_path):
    repo = repo_com_base(tmp_path)
    escrever(repo, "111_ouvidoria_triagem_email.sql")
    commitar(repo, "migration nova com numero ja usado")

    proc = rodar(repo)

    assert proc.returncode != 0
    saida = proc.stdout + proc.stderr
    assert "111" in saida
    assert "111_tecnologia_produto_central_de_comando.sql" in saida
    assert "111_ouvidoria_triagem_email.sql" in saida


def test_branch_sem_migration_nova_passa(tmp_path):
    repo = repo_com_base(tmp_path)
    (repo / "README.md").write_text("só código\n", encoding="utf-8")
    commitar(repo, "sem migration")

    proc = rodar(repo)

    assert proc.returncode == 0, proc.stdout
    assert checar_migration_repetida.colisoes(repo, "main") == []


def test_branch_com_numero_inedito_passa(tmp_path):
    repo = repo_com_base(tmp_path)
    escrever(repo, "112_ouvidoria_triagem_email.sql")
    commitar(repo, "migration nova com numero livre")

    proc = rodar(repo)

    assert proc.returncode == 0, proc.stdout
    assert checar_migration_repetida.colisoes(repo, "main") == []


def test_branch_que_so_renomeia_migration_existente_passa(tmp_path):
    repo = repo_com_base(tmp_path)
    git(
        repo,
        "mv",
        f"{PASTA}/111_tecnologia_produto_central_de_comando.sql",
        f"{PASTA}/111_tecnologia_central_de_comando.sql",
    )
    commitar(repo, "renomeia a 111")

    proc = rodar(repo)

    assert proc.returncode == 0, proc.stdout


def test_branch_que_so_edita_migration_existente_passa(tmp_path):
    repo = repo_com_base(tmp_path)
    escrever(
        repo,
        "111_tecnologia_produto_central_de_comando.sql",
        "select 1;\nselect 2;\n",
    )
    commitar(repo, "edita a 111")

    proc = rodar(repo)

    assert proc.returncode == 0, proc.stdout


def test_branch_empilhada_sobre_pr_que_entrou_por_squash_passa(tmp_path):
    """A branch traz de novo o commit original da 112 que a base já tem."""
    repo = repo_com_base(tmp_path)
    escrever(repo, "112_ouvidoria_triagem_email.sql")
    commitar(repo, "PR de baixo cria a 112")
    git(repo, "checkout", "-q", "main")
    escrever(repo, "112_ouvidoria_triagem_email.sql")
    commitar(repo, "squash do PR de baixo")
    git(repo, "checkout", "-q", "feature")

    proc = rodar(repo)

    assert proc.returncode == 0, proc.stdout
