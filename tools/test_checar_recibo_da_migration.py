"""Guarda do recibo da migration (issue #969).

Toda migration nova termina gravando o próprio número em `migracoes_aplicadas`,
e a subida só mergeia depois que o `/api/health` devolve esse número. Migration
sem o recibo, ou com o número de outra, faria a subida esperar 24 h por um número
que nunca chega. Estes testes montam um repositório `git` de verdade em
`tmp_path` e rodam a guarda por subprocess, como o CI roda. Cada mutante mexe
em uma coisa só da migration certa.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import checar_recibo_da_migration  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
SCRIPT = RAIZ / "tools" / "checar_recibo_da_migration.py"
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

CORPO = "CREATE TABLE triagem (id int);\nALTER TABLE triagem ENABLE ROW LEVEL SECURITY;\n"
RECIBO_115 = "INSERT INTO migracoes_aplicadas (numero) VALUES (115) ON CONFLICT (numero) DO NOTHING;\n"
CERTA = CORPO + "\n-- recibo: a subida espera este numero no /api/health\n" + RECIBO_115
NOVA = "115_triagem.sql"


def git(repo: Path, *args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=repo, env=ENV_GIT, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


def escrever(repo: Path, nome: str, sql: str) -> None:
    arquivo = repo / PASTA / nome
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    arquivo.write_text(sql, encoding="utf-8")


def commitar(repo: Path, msg: str) -> None:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", msg)


def repo_com_base(tmp_path: Path) -> Path:
    """`main` com migrations antigas sem recibo (o recibo nasce na 114); o teste
    continua numa branch `feature` por cima."""
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    escrever(repo, "113_comentarios.sql", "COMMENT ON TABLE x IS 'y';\n")
    escrever(repo, "114_migracoes_aplicadas.sql", "select 1;\n" + RECIBO_115.replace("115", "114"))
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


def com_migration(tmp_path: Path, sql: str) -> subprocess.CompletedProcess:
    repo = repo_com_base(tmp_path)
    escrever(repo, NOVA, sql)
    commitar(repo, "migration nova")
    return rodar(repo)


def test_migration_nova_com_o_recibo_no_fim_passa(tmp_path):
    proc = com_migration(tmp_path, CERTA)

    assert proc.returncode == 0, proc.stdout + proc.stderr


MUTANTES = {
    "sem-o-insert": CORPO,
    "numero-de-outra-migration": CERTA.replace("VALUES (115)", "VALUES (114)"),
    "insert-no-meio": RECIBO_115 + CORPO,
    "outra-tabela": CERTA.replace("migracoes_aplicadas", "migracoes"),
    "insert-comentado": CORPO + "-- " + RECIBO_115,
}


@pytest.mark.parametrize("sql", MUTANTES.values(), ids=MUTANTES.keys())
def test_mutante_da_migration_certa_reprova_nomeando_o_arquivo_e_o_insert(tmp_path, sql):
    proc = com_migration(tmp_path, sql)

    assert proc.returncode == 1, proc.stdout
    assert NOVA in proc.stdout
    # a mensagem traz o insert exato que falta, com o número do arquivo
    assert "INSERT INTO migracoes_aplicadas (numero) VALUES (115) ON CONFLICT (numero) DO NOTHING;" in proc.stdout
    assert "—" not in proc.stdout and "–" not in proc.stdout  # ADR 0013


@pytest.mark.parametrize(
    "sql",
    [
        CERTA.replace("ON CONFLICT (numero) DO NOTHING", ""),
        CERTA.lower(),
        CERTA + "\n\n-- fim\n/* nada depois */\n",
        CORPO + "insert into public.migracoes_aplicadas(numero)\n  values (115)\n  on conflict do nothing",
    ],
    ids=["sem-on-conflict", "minusculo", "comentario-depois", "quebrado-em-linhas-sem-ponto-e-virgula"],
)
def test_variacao_de_escrita_do_recibo_passa(tmp_path, sql):
    proc = com_migration(tmp_path, sql)

    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_editar_migration_antiga_sem_recibo_passa(tmp_path):
    repo = repo_com_base(tmp_path)
    escrever(repo, "113_comentarios.sql", "COMMENT ON TABLE x IS 'z';\n")
    commitar(repo, "edita a 113")

    proc = rodar(repo)

    assert proc.returncode == 0, proc.stdout


def test_renomear_migration_antiga_sem_recibo_passa(tmp_path):
    repo = repo_com_base(tmp_path)
    git(repo, "mv", f"{PASTA}/113_comentarios.sql", f"{PASTA}/113_comentarios_da_tabela.sql")
    commitar(repo, "renomeia a 113")

    proc = rodar(repo)

    assert proc.returncode == 0, proc.stdout


def test_branch_empilhada_sobre_squash_nao_cobra_a_migration_que_a_base_ja_tem(tmp_path):
    """A branch traz de novo o commit original de uma migration que a base já
    tem (entrou por squash); ela não é nova."""
    repo = repo_com_base(tmp_path)
    escrever(repo, "112_antiga.sql", "select 1;\n")
    commitar(repo, "PR de baixo")
    git(repo, "checkout", "-q", "main")
    escrever(repo, "112_antiga.sql", "select 1;\n")
    commitar(repo, "squash do PR de baixo")
    git(repo, "checkout", "-q", "feature")

    proc = rodar(repo)

    assert proc.returncode == 0, proc.stdout


def test_roda_da_pasta_do_backend_como_no_ci(tmp_path):
    repo = repo_com_base(tmp_path)
    escrever(repo, NOVA, CORPO)
    commitar(repo, "migration sem recibo")
    backend = repo / "hospital-reunioes" / "backend"
    backend.mkdir(parents=True)

    proc = rodar(backend)

    assert proc.returncode == 1 and NOVA in proc.stdout


def test_a_migration_114_do_repositorio_grava_o_proprio_numero():
    """A primeira migration com recibo é a que cria a tabela."""
    [arquivo] = (RAIZ / PASTA).glob("114_*.sql")

    sql = arquivo.read_text(encoding="utf-8")

    assert checar_recibo_da_migration.numero_do_recibo(sql) == 114
    assert re.search(r"ALTER TABLE migracoes_aplicadas ENABLE ROW LEVEL SECURITY;", sql)


def test_ci_roda_a_guarda_no_job_do_backend_em_pull_request():
    ci = (RAIZ / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    passo = re.search(
        r"- name: Migration com recibo\n(?:\s+#[^\n]*\n)*"
        r"\s+if: github\.event_name == 'pull_request'\n"
        r"\s+run: python \.\./\.\./tools/checar_recibo_da_migration\.py --base origin/main\n",
        ci,
    )
    assert passo, "o passo da guarda do recibo sumiu do ci.yml"
    # no mesmo job da guarda de número repetido, que roda em hospital-reunioes/backend
    repetida = ci.index("tools/checar_migration_repetida.py")
    proximo_job = re.compile(r"\n  [a-z_-]+:\n").search(ci, repetida)
    assert proximo_job, "o job do backend deveria vir antes de outro job"
    assert repetida < passo.start() < proximo_job.start()
