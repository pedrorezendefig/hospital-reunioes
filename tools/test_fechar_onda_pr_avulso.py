"""O `fechar_onda.py` como rabo único de um PR avulso (issue #907, ADR 0061).

O `/ship` passou a parar no PR verde, e quem faz merge, bump, `APP_VERSION`,
push, build, health e registro de um PR só é o mesmo script da onda. Estes
testes montam um repositório `git` de verdade em `tmp_path` (uma `main` de base,
o PR em `refs/pull/<n>/head` num remoto nu, como no GitHub) e rodam o `main()`
do script contra ele. Fica de fora só o que sai da máquina: o `gh` responde por
um dublê, o `coolify` é um executável falso no PATH que anota cada chamada, e o
build e o health devolvem verde sem rede.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
SCRIPTS = RAIZ / ".claude" / "skills" / "onda-enxuta" / "scripts"
MIGRATIONS = "hospital-reunioes/supabase/migrations"

TRAVESSAO = "—"
MEIA_RISCA = "–"

ENV_GIT = {
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "teste",
    "GIT_AUTHOR_EMAIL": "teste@example.com",
    "GIT_COMMITTER_NAME": "teste",
    "GIT_COMMITTER_EMAIL": "teste@example.com",
}


def git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=repo,
        env={**os.environ, **ENV_GIT},
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


def escrever(repo: Path, caminho: str, texto: str) -> None:
    arquivo = repo / caminho
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    arquivo.write_text(texto, encoding="utf-8")


def json_txt(dado) -> str:
    return json.dumps(dado, ensure_ascii=False, indent=2) + "\n"


PROJECT = {
    "services": [
        {
            "id": "backend",
            "type": "fastapi",
            "uuid": "uuid-backend",
            "diff_routing": {"trigger_paths": ["hospital-reunioes/backend/**"]},
            "deploy": {"health_check": {"url": "https://exemplo.invalid/api/health"}},
        },
        {
            "id": "frontend",
            "type": "nextjs",
            "uuid": "uuid-frontend",
            "diff_routing": {"trigger_paths": ["hospital-reunioes/frontend/**"]},
            "deploy": {"health_check": {"url": "https://exemplo.invalid/"}},
        },
    ]
}

CHANGELOG = (
    "# Changelog Hospital Reuniões\n\n---\n\n"
    "## v0.10.0 - 2026-10-01 10:00 - Entrada anterior\n- SHA: `abc1234`\n"
)


class Cenario:
    """O remoto, o clone em que o script roda e o que os dublês anotaram."""

    def __init__(self, tmp_path: Path, numero: int, titulo: str, issue: int | None,
                 arquivos: dict[str, str], corpo: str = ""):
        self.numero = numero
        self.issue = issue
        repo = tmp_path / "repo"
        repo.mkdir()
        git(repo, "init", "-q", "-b", "main")
        escrever(repo, "hospital-reunioes/frontend/package.json",
                 '{\n  "name": "frontend",\n  "version": "0.10.0"\n}\n')
        escrever(repo, "hospital-reunioes/backend/app/prazo.py", "PRAZO = 10\n")
        escrever(repo, f"{MIGRATIONS}/111_base.sql", "select 1;\n")
        escrever(repo, "docs/spec/deploy/project.json", json_txt(PROJECT))
        escrever(repo, "docs/spec/deploy/state.json", json_txt({
            "production": {"repo": "dono/repo"},
            "services": [{"id": "backend"}, {"id": "frontend"}],
        }))
        escrever(repo, "docs/spec/deploy/history.json", json_txt({"deploys": []}))
        escrever(repo, "docs/spec/CHANGELOG.md", CHANGELOG)
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "base")
        git(repo, "checkout", "-q", "-b", "feature")
        for caminho, texto in arquivos.items():
            escrever(repo, caminho, texto)
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", titulo)
        self.remoto = tmp_path / "remoto.git"
        git(tmp_path, "init", "-q", "--bare", "-b", "main", str(self.remoto))
        git(repo, "push", "-q", str(self.remoto), "main", f"feature:refs/pull/{numero}/head")
        self.clone = tmp_path / "clone"
        git(tmp_path, "clone", "-q", str(self.remoto), str(self.clone))
        self.base = self.main_remota()
        self.pr = {
            "number": numero,
            "state": "OPEN",
            "mergeable": "MERGEABLE",
            "mergeStateStatus": "CLEAN",
            "statusCheckRollup": [{"name": "Backend", "conclusion": "SUCCESS"}],
            "headRefName": "feature",
            "baseRefName": "main",
            "title": titulo,
            "files": [{"path": p} for p in arquivos],
            "commits": [{"messageHeadline": titulo, "messageBody": ""}],
            "url": f"https://github.com/dono/repo/pull/{numero}",
            "closingIssuesReferences": [{"number": issue}] if issue else [],
            "body": corpo,
        }
        self.gh_chamadas: list[list[str]] = []
        self.builds: list[str] = []
        self.healths: list[tuple[str, str | None]] = []
        self.semaforo: list[tuple[str, str]] = []
        bin_falso = tmp_path / "bin"
        bin_falso.mkdir()
        self.log_coolify = tmp_path / "coolify.log"
        coolify = bin_falso / "coolify"
        coolify.write_text(
            "#!/bin/sh\n"
            f'echo "$* | main=$(git --git-dir={self.remoto} rev-parse main)" >> {self.log_coolify}\n',
            encoding="utf-8",
        )
        coolify.chmod(0o755)
        self.path = f"{bin_falso}{os.pathsep}{os.environ.get('PATH', '')}"
        self.home = tmp_path / "home"
        self.home.mkdir()

    def main_remota(self) -> str:
        return git(self.remoto, "rev-parse", "main")

    def na_main(self, caminho: str) -> str:
        return git(self.remoto, "show", f"main:{caminho}")

    def coolify(self) -> list[str]:
        if not self.log_coolify.exists():
            return []
        return self.log_coolify.read_text(encoding="utf-8").splitlines()


def carregar_fechar_onda():
    sys.path.insert(0, str(SCRIPTS))
    try:
        sys.modules.pop("fechar_onda", None)
        import fechar_onda
    finally:
        sys.path.remove(str(SCRIPTS))
    return fechar_onda


def preparar(fo, monkeypatch, c: Cenario) -> None:
    for k, v in ENV_GIT.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("PATH", c.path)
    monkeypatch.setenv("HOME", str(c.home))

    def gh_json(args, cwd=None):
        c.gh_chamadas.append(list(args))
        if args[:2] == ["pr", "view"]:
            return dict(c.pr)
        if args[:2] == ["issue", "view"]:
            return {"body": "## Pai\n\n`#902`, PRD da esteira.\n"}
        raise AssertionError(f"gh inesperado: {args}")

    run_real = fo.run

    def run(cmd, *args, **kwargs):
        if cmd[0] == "gh":
            c.gh_chamadas.append(list(cmd[1:]))
            return subprocess.CompletedProcess(cmd, 0, "", "")
        return run_real(cmd, *args, **kwargs)

    def semaforo(raiz, acao, chave, descricao=""):
        c.semaforo.append((acao, chave))
        return 0

    def esperar_build(service, desde, sha_push):
        c.builds.append(service["id"])
        return "finished", 42

    def checar_health(service, versao_esperada):
        c.healths.append((service["id"], versao_esperada))
        return {"ok": True, "status": 200, "latency_ms": 5}

    monkeypatch.setattr(fo, "gh_json", gh_json)
    monkeypatch.setattr(fo, "run", run)
    monkeypatch.setattr(fo, "semaforo", semaforo)
    monkeypatch.setattr(fo, "esperar_build", esperar_build)
    monkeypatch.setattr(fo, "checar_health", checar_health)


def rodar_main(fo, monkeypatch, c: Cenario, *extra: str) -> int:
    monkeypatch.setattr(sys, "argv", ["fechar_onda.py", "--prs", str(c.numero),
                                      "--raiz", str(c.clone), *extra])
    return fo.main()


TITULO_COM_TRAVESSAO = f"fix(ouvidoria): prazo do caso {TRAVESSAO} conta dias uteis"


def pr_de_codigo(tmp_path: Path, **kw) -> Cenario:
    return Cenario(tmp_path, 7, kw.pop("titulo", TITULO_COM_TRAVESSAO), kw.pop("issue", 5),
                   {"hospital-reunioes/backend/app/prazo.py": "PRAZO = 15\n"}, **kw)


# ------------------------------------------------------------ PR avulso inteiro

def test_um_pr_so_sem_sessao_faz_merge_bump_app_version_push_build_health_e_registro(
    tmp_path, monkeypatch
):
    fo = carregar_fechar_onda()
    c = pr_de_codigo(tmp_path)
    preparar(fo, monkeypatch, c)

    assert rodar_main(fo, monkeypatch, c) == 0

    # merge: o commit do PR está na main remota, num commit de merge com o número
    assert git(c.remoto, "merge-base", "--is-ancestor", "refs/pull/7/head", "main") == ""
    assuntos = git(c.remoto, "log", "--format=%s", f"{c.base}..main").splitlines()
    assert any(a.endswith("(#7)") for a in assuntos), assuntos
    # bump: patch, pelo tipo do commit
    assert json.loads(c.na_main("hospital-reunioes/frontend/package.json"))["version"] == "0.10.1"
    # APP_VERSION no Coolify, ANTES do push (a main remota ainda era a base)
    assert c.coolify() == [
        f"app env update uuid-backend APP_VERSION --value 0.10.1 | main={c.base}"
    ]
    # build e health só do serviço tocado, com conferência de versão
    assert c.builds == ["backend"]
    assert ("backend", "0.10.1") in c.healths
    # semáforo pego e solto com a chave derivada do PR
    assert c.semaforo == [("pegar", "pr-7"), ("soltar", "pr-7")]
    # registro no mesmo push
    entrada = json.loads(c.na_main("docs/spec/deploy/history.json"))["deploys"][0]
    assert entrada["app_version"] == "0.10.1"
    assert entrada["prds"] == [902]


def sem_a_palavra_onda(texto: str) -> bool:
    # `fechar_onda` é nome de arquivo, não a palavra: `_` é letra para o `\b`.
    return re.search(r"\bonda\b", texto, re.I) is None


def test_registro_do_pr_avulso_nomeia_pr_e_issue_sem_onda_e_sem_travessao(
    tmp_path, monkeypatch
):
    fo = carregar_fechar_onda()
    c = pr_de_codigo(tmp_path)
    preparar(fo, monkeypatch, c)

    assert rodar_main(fo, monkeypatch, c) == 0

    entrada = json.loads(c.na_main("docs/spec/deploy/history.json"))["deploys"][0]
    for campo in ("subject", "raw_subject", "notes"):
        assert sem_a_palavra_onda(entrada[campo]), (campo, entrada[campo])
    assert "PR #7" in entrada["subject"] and "issue #5" in entrada["subject"], entrada["subject"]
    assert TRAVESSAO not in entrada["subject"] and MEIA_RISCA not in entrada["subject"]
    # contrato do painel (`tools/workflow-dashboard/collect.py`, `_correlate`)
    assert re.search(r"\(#7\)", entrada["raw_subject"]), entrada["raw_subject"]
    assert re.search(r"PRs? #7\b", entrada["notes"]), entrada["notes"]
    assert re.search(r"(?:[Ii]ssues? |Closes )#5\b", entrada["notes"]), entrada["notes"]

    titulo = next(li for li in c.na_main("docs/spec/CHANGELOG.md").splitlines()
                  if li.startswith("## "))
    assert titulo.startswith("## v0.10.1 - "), titulo
    assert "PR #7" in titulo and "issue #5" in titulo, titulo
    assert sem_a_palavra_onda(titulo), titulo
    assert TRAVESSAO not in titulo and MEIA_RISCA not in titulo, titulo
    assert "Prazo do caso, conta dias uteis" in titulo, titulo


def test_dry_run_do_pr_avulso_imprime_o_plano_com_pr_issue_e_tipo_de_bump(
    tmp_path, monkeypatch, capsys
):
    fo = carregar_fechar_onda()
    c = pr_de_codigo(tmp_path, titulo="feat(ouvidoria): prazo em dias uteis")
    preparar(fo, monkeypatch, c)

    assert rodar_main(fo, monkeypatch, c, "--dry-run") == 0

    plano = [li for li in capsys.readouterr().out.splitlines() if li.startswith("plano:")]
    assert len(plano) == 1, plano
    assert "PR #7" in plano[0] and "issue #5" in plano[0], plano[0]
    assert "minor" in plano[0] and "v0.10.0 -> v0.11.0" in plano[0], plano[0]
    # nada sai da máquina
    assert c.main_remota() == c.base
    assert c.coolify() == []
    assert c.semaforo == []
    assert c.builds == []
