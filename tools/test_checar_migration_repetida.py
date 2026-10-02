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


def test_roda_da_pasta_do_backend_sobre_o_merge_do_pr_como_no_ci(tmp_path):
    """O job do backend roda em `hospital-reunioes/backend` e o checkout do PR
    é o commit de merge que o GitHub monta sobre a base."""
    repo = repo_com_base(tmp_path)
    escrever(repo, "111_ouvidoria_triagem_email.sql")
    commitar(repo, "migration nova com numero ja usado")
    git(repo, "checkout", "-q", "--detach", "main")
    git(repo, "merge", "-q", "--no-ff", "feature", "-m", "merge do PR")
    backend = repo / "hospital-reunioes" / "backend"
    backend.mkdir(parents=True)

    proc = rodar(backend)

    assert proc.returncode != 0
    assert "111_ouvidoria_triagem_email.sql" in proc.stdout


# --------------------------------------------- segundo tempo: fechar_onda.py

def carregar_fechar_onda():
    scripts = RAIZ / ".claude" / "skills" / "onda-enxuta" / "scripts"
    sys.path.insert(0, str(scripts))
    try:
        import fechar_onda
    finally:
        sys.path.remove(str(scripts))
    return fechar_onda


def origem_com_pr(tmp_path: Path, numero: int, migration: str) -> Path:
    """Remoto com a `main` de base e o PR em `refs/pull/<n>/head`, como no
    GitHub; devolve o clone em que o `fechar_onda.py` roda."""
    repo = repo_com_base(tmp_path)
    escrever(repo, migration)
    commitar(repo, "migration do PR")
    remoto = tmp_path / "remoto.git"
    git(tmp_path, "init", "-q", "--bare", str(remoto))
    git(repo, "push", "-q", str(remoto), "main", f"feature:refs/pull/{numero}/head")
    clone = tmp_path / "clone"
    git(tmp_path, "clone", "-q", str(remoto), str(clone))
    git(clone, "fetch", "-q", "origin", "main")
    return clone


def pre_condicoes(fechar_onda, monkeypatch, clone: Path, numero: int) -> None:
    """Roda as pré-condições de verdade (git contra o remoto local) com o `gh`
    respondendo que o PR está aberto, verde e mergeável."""
    run_real = fechar_onda.run

    def run_sem_gh(cmd, *args, **kwargs):
        if cmd[0] == "gh":
            return subprocess.CompletedProcess(cmd, 0, "", "")
        return run_real(cmd, *args, **kwargs)

    pr_verde = {
        "number": numero,
        "state": "OPEN",
        "baseRefName": "main",
        "mergeable": "MERGEABLE",
        "statusCheckRollup": [{"name": "Backend", "conclusion": "SUCCESS"}],
        "files": [{"path": f"{PASTA}/x.sql"}],
    }
    monkeypatch.setattr(fechar_onda, "run", run_sem_gh)
    monkeypatch.setattr(fechar_onda, "gh_json", lambda *a, **k: dict(pr_verde))
    fechar_onda.checar_pre_condicoes(clone, [numero], dry=True)


def test_fechar_onda_para_nas_pre_condicoes_com_a_mesma_mensagem_do_ci(
    tmp_path, monkeypatch, capsys
):
    fechar_onda = carregar_fechar_onda()
    clone = origem_com_pr(tmp_path, 7, "111_ouvidoria_triagem_email.sql")
    ci = rodar(tmp_path / "repo")

    try:
        pre_condicoes(fechar_onda, monkeypatch, clone, 7)
    except SystemExit as e:
        assert e.code == fechar_onda.EXIT_PRECOND
    else:
        raise AssertionError("o fechar_onda.py seguiu com número repetido")

    saida = capsys.readouterr().out
    assert "#7" in saida
    assert "111_tecnologia_produto_central_de_comando.sql" in saida
    assert "111_ouvidoria_triagem_email.sql" in saida
    assert ci.returncode != 0
    assert ci.stdout.strip() in saida


def test_fechar_onda_segue_com_numero_inedito(tmp_path, monkeypatch):
    fechar_onda = carregar_fechar_onda()
    clone = origem_com_pr(tmp_path, 8, "112_ouvidoria_triagem_email.sql")

    pre_condicoes(fechar_onda, monkeypatch, clone, 8)
