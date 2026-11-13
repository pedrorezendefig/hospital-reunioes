"""Gerador de migration (Portão do push).

A migration nasce com o próximo número livre e com o recibo da issue #969, e a
guarda do CI aceita o arquivo como ele sai do gerador.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import checar_recibo_da_migration  # noqa: E402
import nova_migration  # noqa: E402

PASTA = "hospital-reunioes/supabase/migrations"
ENV_GIT = {
    **os.environ,
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "teste",
    "GIT_AUTHOR_EMAIL": "teste@example.com",
    "GIT_COMMITTER_NAME": "teste",
    "GIT_COMMITTER_EMAIL": "teste@example.com",
}


def git(repo: Path, *args: str) -> None:
    proc = subprocess.run(["git", *args], cwd=repo, env=ENV_GIT, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-q", "-b", "main")
    pasta = tmp_path / PASTA
    pasta.mkdir(parents=True)
    (pasta / "136_antiga.sql").write_text("SELECT 1;\n", encoding="utf-8")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "base")
    return tmp_path


def test_o_numero_e_um_a_mais_que_o_maior_da_pasta(repo: Path):
    arquivo = nova_migration.criar(repo, "ouvidoria_nota", base="main")

    assert arquivo.name == "137_ouvidoria_nota.sql"


def test_o_numero_pula_o_que_a_base_ja_tem_e_a_pasta_local_nao(repo: Path):
    git(repo, "checkout", "-q", "-b", "outra")
    (repo / PASTA / "137_de_outra_sessao.sql").write_text("SELECT 1;\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "outra sessão")
    git(repo, "checkout", "-q", "main")

    arquivo = nova_migration.criar(repo, "minha", base="outra")

    assert arquivo.name == "138_minha.sql"


def test_o_arquivo_nasce_com_o_recibo_que_a_guarda_do_ci_aceita(repo: Path):
    arquivo = nova_migration.criar(repo, "com_recibo", base="main")

    sql = arquivo.read_text(encoding="utf-8")
    assert checar_recibo_da_migration.numero_do_recibo(sql) == 137


def test_corpo_escrito_acima_do_recibo_continua_aceito(repo: Path):
    arquivo = nova_migration.criar(repo, "com_corpo", base="main")
    sql = arquivo.read_text(encoding="utf-8").replace(
        "\n\n\n", "\nCREATE TABLE t (id int);\n\n", 1
    )

    assert checar_recibo_da_migration.numero_do_recibo(sql) == 137


@pytest.mark.parametrize("slug", ["Com Maiuscula", "com-hifen", "", "_solto"])
def test_slug_fora_do_padrao_e_recusado(repo: Path, slug: str):
    with pytest.raises(ValueError):
        nova_migration.criar(repo, slug, base="main")
