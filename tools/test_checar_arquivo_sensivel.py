"""Trava de arquivo sensível no PR (issue #1287, PRD #1282).

O repositório é público: PDF, planilha, dump ou `.env` que entra por engano
fica no histórico para sempre. A trava olha só o que o PR ADICIONA e recusa as
extensões de arquivo de dado fora das pastas que existem para isso (migration,
manual, comunicação, fixture de teste, materiais reais dos POPs). Os testes
montam um repositório `git` de verdade em `tmp_path`, com uma `main` de base e
uma branch por cima, e rodam o script como o CI roda.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SCRIPT = RAIZ / "tools" / "checar_arquivo_sensivel.py"

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


def escrever(repo: Path, caminho: str, conteudo: str = "x\n") -> None:
    arquivo = repo / caminho
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    arquivo.write_text(conteudo, encoding="utf-8")


def commitar(repo: Path, msg: str) -> None:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", msg)


def repo_com_base(tmp_path: Path) -> Path:
    """`main` com um README e um seed antigo; o teste segue na branch `feature`."""
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    escrever(repo, "README.md")
    escrever(repo, "hospital-reunioes/supabase/seed.sql", "select 1;\n")
    commitar(repo, "base")
    git(repo, "checkout", "-q", "-b", "feature")
    return repo


def rodar(repo: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--base", "main"],
        cwd=repo,
        env=ENV_GIT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def test_pr_que_adiciona_planilha_fora_das_pastas_liberadas_e_recusado(tmp_path):
    repo = repo_com_base(tmp_path)
    escrever(repo, "hospital-reunioes/backend/exportacao.xlsx")
    commitar(repo, "planilha")

    proc = rodar(repo)

    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "hospital-reunioes/backend/exportacao.xlsx" in proc.stdout


def test_cada_extensao_bloqueada_e_recusada(tmp_path):
    repo = repo_com_base(tmp_path)
    nomes = ["a.pdf", "a.doc", "a.docx", "a.csv", "a.xls", "a.xlsx", "a.sql", "a.dump",
             "a.bak", "a.sqlite", "a.db", "producao.env", ".env", "app/.env.local"]
    for nome in nomes:
        escrever(repo, f"tools/{nome}")
    commitar(repo, "tudo de uma vez")

    proc = rodar(repo)

    assert proc.returncode == 1
    for nome in nomes:
        assert f"tools/{nome}" in proc.stdout, nome


def test_extensao_em_maiuscula_tambem_e_recusada(tmp_path):
    repo = repo_com_base(tmp_path)
    escrever(repo, "docs/Contrato.PDF")
    commitar(repo, "maiuscula")

    proc = rodar(repo)

    assert proc.returncode == 1
    assert "docs/Contrato.PDF" in proc.stdout


def test_pastas_liberadas_passam(tmp_path):
    repo = repo_com_base(tmp_path)
    for caminho in [
        "hospital-reunioes/supabase/migrations/200_nova.sql",
        "docs/manual/public/guia.pdf",
        "docs/comunicacao/central/folheto.PDF",
        "hospital-reunioes/backend/tests/fixtures/contas_medicas/tabela.csv",
        "docs/pops/materiais-reais/pop.docx",
    ]:
        escrever(repo, caminho)
    commitar(repo, "liberadas")

    proc = rodar(repo)

    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_pasta_com_nome_parecido_com_a_liberada_nao_passa(tmp_path):
    repo = repo_com_base(tmp_path)
    escrever(repo, "docs/manual-antigo/guia.pdf")
    commitar(repo, "vizinha")

    assert rodar(repo).returncode == 1


def test_env_example_e_arquivo_comum_passam(tmp_path):
    repo = repo_com_base(tmp_path)
    escrever(repo, "hospital-reunioes/backend/.env.example")
    escrever(repo, "tools/script.py")
    commitar(repo, "comum")

    assert rodar(repo).returncode == 0


def test_editar_arquivo_que_ja_existe_na_base_nao_conta(tmp_path):
    repo = repo_com_base(tmp_path)
    escrever(repo, "hospital-reunioes/supabase/seed.sql", "select 2;\n")
    commitar(repo, "edita o seed")

    assert rodar(repo).returncode == 0


def test_renomear_para_fora_da_pasta_liberada_conta_como_adicionar(tmp_path):
    repo = repo_com_base(tmp_path)
    (repo / "tools").mkdir()
    git(repo, "mv", "hospital-reunioes/supabase/seed.sql", "tools/seed.sql")
    commitar(repo, "move o seed")

    proc = rodar(repo)

    assert proc.returncode == 1
    assert "tools/seed.sql" in proc.stdout
