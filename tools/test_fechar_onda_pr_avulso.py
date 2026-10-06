"""O `fechar_onda.py` como rabo único de um PR avulso (issues #907 e #910, ADR 0061).

O `/ship` passou a parar no PR verde, e quem faz merge, bump, `APP_VERSION`,
build, health e registro de um PR só é o mesmo script da onda. Estes testes
montam um repositório `git` de verdade em `tmp_path` (uma `main` de base, o PR
na branch `feature` e em `refs/pull/<n>/head` num remoto nu, como no GitHub) e
rodam o `main()` do script contra ele.

A `main` do remoto está sob o ruleset (issue #910): um hook `pre-receive` recusa
todo push nela, como o GitHub recusa com `GH013`. Ela só anda pelo dublê do
GitHub, que faz o squash pela API do jeito que o repositório permite: exige o
`sha` do head, a branch em dia com a base e o CI verde, e apaga a branch depois.
Fica de fora só o que sai da máquina: o `coolify` é um executável falso no PATH
que anota cada chamada, e o build e o health devolvem verde sem rede.
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

TRAVESSAO = "\u2014"
MEIA_RISCA = "\u2013"
SEM_RUNNER = "The job was not acquired by Runner of type hosted even after multiple attempts"

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

def script_falso(log: Path, nome: str, alvo: str) -> str:
    """O snapshot e o tirar-draft do Manual moram no repo, mas saíram do rabo para
    a Action do push da main (ADR 0062, decisão 10). O falso anota quem o chamou
    e suja a árvore como o de verdade sujaria."""
    return (
        "import pathlib, sys\n"
        f"with open({str(log)!r}, 'a', encoding='utf-8') as f:\n"
        f"    f.write({nome!r} + ' ' + ' '.join(sys.argv[1:]) + '\\n')\n"
        f"alvo = pathlib.Path({alvo!r})\n"
        "alvo.parent.mkdir(parents=True, exist_ok=True)\n"
        "alvo.write_text('gerado\\n', encoding='utf-8')\n"
    )


class Cenario:
    """O remoto, o clone em que o script roda e o que os dublês anotaram."""

    def __init__(self, tmp_path: Path, numero: int, titulo: str, issue: int | None,
                 arquivos: dict[str, str], corpo: str = "", deploys: list[dict] | None = None,
                 versao_em_producao: str = "0.10.0"):
        self.numero = numero
        self.issue = issue
        self.log_scripts = tmp_path / "scripts-chamados.log"
        repo = tmp_path / "repo"
        repo.mkdir()
        git(repo, "init", "-q", "-b", "main")
        escrever(repo, "hospital-reunioes/frontend/package.json",
                 '{\n  "name": "frontend",\n  "version": "0.10.0"\n}\n')
        escrever(repo, "hospital-reunioes/backend/app/prazo.py", "PRAZO = 10\n")
        escrever(repo, f"{MIGRATIONS}/111_base.sql", "select 1;\n")
        escrever(repo, "docs/spec/deploy/project.json", json_txt(PROJECT))
        escrever(repo, "docs/spec/deploy/state.json", json_txt({
            "last_app_version": versao_em_producao,
            "production": {"repo": "dono/repo"},
            "services": [{"id": "backend"}, {"id": "frontend"}],
        }))
        escrever(repo, "docs/spec/deploy/history.json", json_txt({"deploys": deploys or []}))
        escrever(repo, ".claude/skills/snapshot/scripts/snapshot.py",
                 script_falso(self.log_scripts, "snapshot", "docs/spec/snapshots/ROTAS.md"))
        escrever(repo, "tools/tirar_draft_manual.py",
                 script_falso(self.log_scripts, "tirar_draft", "docs/manual/pagina.mdx"))
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "base")
        git(repo, "checkout", "-q", "-b", "feature")
        for caminho, texto in arquivos.items():
            escrever(repo, caminho, texto)
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", titulo)
        self.remoto = tmp_path / "remoto.git"
        git(tmp_path, "init", "-q", "--bare", "-b", "main", str(self.remoto))
        git(repo, "push", "-q", str(self.remoto), "main", "feature",
            f"feature:refs/pull/{numero}/head")
        self.clone = tmp_path / "clone"
        git(tmp_path, "clone", "-q", str(self.remoto), str(self.clone))
        self.base = self.main_remota()
        self.head_do_pr = git(self.remoto, "rev-parse", "feature")
        self.pr = {
            "number": numero,
            "state": "OPEN",
            "mergeable": "MERGEABLE",
            "headRefName": "feature",
            "headRefOid": self.head_do_pr,
            "isCrossRepository": False,
            "baseRefName": "main",
            "title": titulo,
            "files": [{"path": p} for p in arquivos],
            "commits": [{"messageHeadline": titulo, "messageBody": ""}],
            "url": f"https://github.com/dono/repo/pull/{numero}",
            "closingIssuesReferences": [{"number": issue}] if issue else [],
            "body": corpo,
        }
        # PRs que o GitHub conhece: o do autor e os que o script abrir pela API
        self.prs: dict[int, dict] = {numero: self.pr}
        self.ci_vermelho: set[str] = set()  # heads em que o CI falha
        self.sem_checks = False  # o CI nunca rodou: nenhum check no PR
        # quantas rodadas do CI do head que o rabo empurra o GitHub cancela por
        # falta de runner (#953)
        self.sem_runner = 0
        self.anotacao_do_cancelamento = SEM_RUNNER
        self.merges: list[dict] = []
        self.gh_chamadas: list[list[str]] = []
        self.builds: list[str] = []
        self.healths: list[tuple[str, str | None]] = []
        self.semaforo: list[tuple[str, str]] = []
        self.cancelamentos: list[str] = []
        self.tags: list[tuple[str, str]] = []  # (ref, sha) criados pela API
        self.log_push_main = tmp_path / "push-na-main.log"
        hook = self.remoto / "hooks" / "pre-receive"
        hook.write_text(
            "#!/bin/sh\n"
            "while read velho novo ref; do\n"
            '  if [ "$ref" = "refs/heads/main" ]; then\n'
            f'    echo "$ref" >> {self.log_push_main}\n'
            '    echo "GH013: Repository rule violations found for refs/heads/main." >&2\n'
            "    exit 1\n"
            "  fi\n"
            "done\n",
            encoding="utf-8",
        )
        hook.chmod(0o755)
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

    def scripts_chamados(self) -> list[str]:
        if not self.log_scripts.exists():
            return []
        return self.log_scripts.read_text(encoding="utf-8").splitlines()

    def coolify(self) -> list[str]:
        if not self.log_coolify.exists():
            return []
        return self.log_coolify.read_text(encoding="utf-8").splitlines()

    def pushes_na_main(self) -> list[str]:
        if not self.log_push_main.exists():
            return []
        return self.log_push_main.read_text(encoding="utf-8").splitlines()

    def avancar_main(self, repo: Path, ref: str = "main") -> None:
        """Outro PR entrou na main pela API: o lado do servidor não passa pelo hook."""
        git(repo, "push", "-q", str(self.remoto), f"{ref}:refs/heads/entrou-por-outro-pr")
        git(self.remoto, "update-ref", "refs/heads/main", "refs/heads/entrou-por-outro-pr")
        git(self.remoto, "update-ref", "-d", "refs/heads/entrou-por-outro-pr")

    # ------------------------------------------------------- dublê do GitHub

    def _tip(self, branch: str) -> str | None:
        proc = subprocess.run(["git", "rev-parse", "--verify", "-q", f"refs/heads/{branch}"],
                              cwd=self.remoto, capture_output=True, text=True)
        return proc.stdout.strip() or None

    def _em_dia(self, head: str) -> bool:
        return subprocess.run(["git", "merge-base", "--is-ancestor", "main", head],
                              cwd=self.remoto).returncode == 0

    def ver_pr(self, n: int, campos: list[str]) -> dict:
        pr = dict(self.prs[n])
        head = self._tip(pr["headRefName"]) or pr.get("headRefOid")
        pr["headRefOid"] = head
        pr["statusCheckRollup"] = [{"name": "Backend Lint, Format & Tests", "status": "COMPLETED",
                                    "conclusion": "FAILURE" if head in self.ci_vermelho else "SUCCESS"}]
        if head != self.head_do_pr and self.sem_runner:
            pr["statusCheckRollup"] = [{"name": "Backend Lint, Format & Tests", "status": "COMPLETED",
                                        "conclusion": "CANCELLED", "workflowName": "CI",
                                        "detailsUrl": "https://github.com/dono/repo/actions/runs/555/job/9"}]
        if self.sem_checks:
            pr["statusCheckRollup"] = []
        pr["mergeStateStatus"] = "CLEAN" if self._em_dia(head) else "BEHIND"
        return {k: v for k, v in pr.items() if k in campos}

    def abrir_pr(self, campos: dict) -> dict:
        if any(p["headRefName"] == campos["head"] and p["state"] == "OPEN" for p in self.prs.values()):
            raise RuntimeError(f"gh api -> 422: A pull request already exists for {campos['head']}.")
        n = 100 + len(self.prs)
        self.prs[n] = {"number": n, "state": "OPEN", "mergeable": "MERGEABLE",
                       "headRefName": campos["head"], "baseRefName": campos["base"],
                       "title": campos["title"], "body": campos["body"],
                       "url": f"https://github.com/dono/repo/pull/{n}"}
        return {"number": n, "html_url": self.prs[n]["url"]}

    def criar_ref(self, campos: dict) -> dict:
        """POST /git/refs como o GitHub: recusa ref que já existe e sha que o
        repositório não tem (o squash só existe depois do merge)."""
        ref, sha = campos["ref"], campos["sha"]
        if subprocess.run(["git", "rev-parse", "--verify", "-q", ref], cwd=self.remoto,
                          capture_output=True).returncode == 0:
            raise RuntimeError("gh api -> 422: Reference already exists")
        if subprocess.run(["git", "cat-file", "-e", f"{sha}^{{commit}}"], cwd=self.remoto,
                          capture_output=True).returncode != 0:
            raise RuntimeError("gh api -> 422: Object does not exist")
        git(self.remoto, "update-ref", ref, sha)
        self.tags.append((ref, sha))
        return {"ref": ref, "object": {"sha": sha}}

    def mergear_pela_api(self, n: int, campos: dict) -> dict:
        """PUT /pulls/N/merge como o GitHub com o ruleset: squash (o único método
        que o repositório permite), recusa head que mudou, branch atrás da base e
        CI vermelho, e apaga a branch do PR depois do merge."""
        pr = self.prs[n]
        head = self._tip(pr["headRefName"])
        if campos.get("merge_method") != "squash":
            raise RuntimeError("gh api -> 405: Merge commits are not allowed on this repository.")
        if campos.get("sha") != head:
            raise RuntimeError("gh api -> 409: Head branch was modified. Review and try the merge again.")
        if not self._em_dia(head):
            raise RuntimeError("gh api -> 405: Head branch is not up to date with the base branch.")
        if head in self.ci_vermelho:
            raise RuntimeError("gh api -> 405: Required status check is failing.")
        antes = self.main_remota()
        arvore = git(self.remoto, "rev-parse", f"{head}^{{tree}}")
        novo = git(self.remoto, "commit-tree", arvore, "-p", antes, "-m", campos["commit_title"])
        git(self.remoto, "update-ref", "refs/heads/main", novo, antes)
        git(self.remoto, "update-ref", "-d", f"refs/heads/{pr['headRefName']}")
        pr["state"] = "MERGED"
        pr["headRefOid"] = head
        self.merges.append({"pr": n, "head": head, "main": novo, "titulo": campos["commit_title"],
                            "corpo": pr.get("body", ""), "branch": pr["headRefName"]})
        return {"sha": novo, "merged": True}


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
            # como o gh de verdade: só os campos pedidos no --json
            return c.ver_pr(int(args[2]), args[args.index("--json") + 1].split(","))
        if args[:2] == ["issue", "view"]:
            return {"body": "## Pai\n\n`#902`, PRD da esteira.\n"}
        if args == ["api", "repos/{owner}/{repo}/check-runs/9/annotations"]:
            return [{"annotation_level": "notice", "message": "The ubuntu-latest label will migrate"},
                    {"annotation_level": "failure", "message": c.anotacao_do_cancelamento}]
        if args[:3] in (["api", "-X", "POST"], ["api", "-X", "PUT"]):
            campos = dict(a.split("=", 1) for a in args[5::2])
            assert args[4::2] == ["-f"] * len(campos), args
            if args[2] == "POST" and args[3] == "repos/{owner}/{repo}/pulls":
                return c.abrir_pr(campos)
            if args[2] == "POST" and args[3] == "repos/{owner}/{repo}/git/refs":
                return c.criar_ref(campos)
            m = re.fullmatch(r"repos/\{owner\}/\{repo\}/pulls/(\d+)/merge", args[3])
            if args[2] == "PUT" and m:
                return c.mergear_pela_api(int(m.group(1)), campos)
        raise AssertionError(f"gh inesperado: {args}")

    run_real = fo.run

    def run(cmd, *args, **kwargs):
        if cmd[0] == "gh":
            c.gh_chamadas.append(list(cmd[1:]))
            if cmd[1:3] == ["pr", "close"]:
                c.prs[int(cmd[3])]["state"] = "CLOSED"
                branch = c.prs[int(cmd[3])]["headRefName"]
                if "--delete-branch" in cmd and c._tip(branch):
                    git(c.remoto, "update-ref", "-d", f"refs/heads/{branch}")
            if cmd[1:] == ["run", "rerun", "555", "--failed"]:
                c.sem_runner -= 1
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

    def cancelar_build_do_registro(servicos_cfg, sha):
        c.cancelamentos.append(sha)
        return []

    monkeypatch.setattr(fo, "gh_json", gh_json)
    monkeypatch.setattr(fo, "run", run)
    monkeypatch.setattr(fo, "semaforo", semaforo)
    monkeypatch.setattr(fo, "esperar_build", esperar_build)
    monkeypatch.setattr(fo, "checar_health", checar_health)
    monkeypatch.setattr(fo, "cancelar_build_do_registro", cancelar_build_do_registro)


def rodar_main(fo, monkeypatch, c: Cenario, *extra: str) -> int:
    monkeypatch.setattr(sys, "argv", ["fechar_onda.py", "--prs", str(c.numero),
                                      "--raiz", str(c.clone), *extra])
    return fo.main()


TITULO_COM_TRAVESSAO = f"fix(ouvidoria): prazo do caso {TRAVESSAO} conta dias uteis"


def pr_de_codigo(tmp_path: Path, **kw) -> Cenario:
    return Cenario(tmp_path, 7, kw.pop("titulo", TITULO_COM_TRAVESSAO), kw.pop("issue", 5),
                   {"hospital-reunioes/backend/app/prazo.py": "PRAZO = 15\n"}, **kw)


# ------------------------------------------------------------ PR avulso inteiro

def test_um_pr_so_sem_sessao_faz_merge_bump_app_version_build_health_e_registro(
    tmp_path, monkeypatch
):
    fo = carregar_fechar_onda()
    c = pr_de_codigo(tmp_path)
    preparar(fo, monkeypatch, c)

    assert rodar_main(fo, monkeypatch, c) == 0

    # o código do PR chegou à main, num squash com o número do PR
    codigo = c.merges[0]["main"]
    assert git(c.remoto, "show", f"{codigo}:hospital-reunioes/backend/app/prazo.py") == "PRAZO = 15"
    assert git(c.remoto, "log", "-1", "--format=%s", codigo).endswith("(#7)")
    # versão nova: patch, pelo tipo do commit, sem commit de bump (issue #967):
    # o package.json do frontend fica congelado
    assert json.loads(c.na_main("hospital-reunioes/frontend/package.json"))["version"] == "0.10.0"
    # APP_VERSION no backend E no frontend do Coolify, ANTES do merge (a main
    # remota ainda era a base)
    assert c.coolify() == [
        f"app env update uuid-backend APP_VERSION --value 0.10.1 | main={c.base}",
        f"app env update uuid-frontend APP_VERSION --value 0.10.1 | main={c.base}",
    ]
    # a tag da versão, DEPOIS do merge: no squash que foi para a main
    assert c.tags == [("refs/tags/v0.10.1", codigo)]
    # build e health só do serviço tocado, com conferência de versão
    assert c.builds == ["backend"]
    assert ("backend", "0.10.1") in c.healths
    # semáforo pego e solto com a chave derivada do PR
    assert c.semaforo == [("pegar", "pr-7"), ("soltar", "pr-7")]
    # registro aponta o commit de código que foi para produção
    entrada = json.loads(c.na_main("docs/spec/deploy/history.json"))["deploys"][0]
    assert entrada["app_version"] == "0.10.1"
    assert entrada["prds"] == [902]
    assert entrada["sha"] == codigo


# ------------------------------------------------ main sob o ruleset (#910)

def test_main_protegida_o_pr_entra_pela_api_sem_commit_na_branch_dele(tmp_path, monkeypatch):
    fo = carregar_fechar_onda()
    c = pr_de_codigo(tmp_path)
    preparar(fo, monkeypatch, c)

    assert rodar_main(fo, monkeypatch, c) == 0

    # ninguém tentou empurrar na main: o ruleset recusaria
    assert c.pushes_na_main() == []
    # o primeiro merge é o do próprio PR, no head com que ele chegou: a versão
    # não é commitada (issue #967), e o CI verde do PR já vale
    entrega = c.merges[0]
    assert entrega["pr"] == 7 and entrega["branch"] == "feature"
    assert entrega["head"] == c.head_do_pr
    # o PR fechou como mergeado, sem `gh pr close`
    assert c.prs[7]["state"] == "MERGED"
    assert [a for a in c.gh_chamadas if a[:2] == ["pr", "close"]] == []


def test_registro_sobe_depois_do_health_num_pr_so_de_docs_e_o_build_dele_e_cancelado(
    tmp_path, monkeypatch
):
    fo = carregar_fechar_onda()
    c = pr_de_codigo(tmp_path)
    preparar(fo, monkeypatch, c)
    healths_no_merge_do_registro = []
    mergear = c.mergear_pela_api

    def mergear_anotando(n, campos):
        healths_no_merge_do_registro.append(list(c.healths))
        return mergear(n, campos)

    c.mergear_pela_api = mergear_anotando

    assert rodar_main(fo, monkeypatch, c) == 0

    assert [m["pr"] for m in c.merges] == [7, 101]
    registro = c.merges[1]
    assert registro["branch"].startswith("registro/"), registro["branch"]
    # depois do health verde, não antes
    assert healths_no_merge_do_registro[1] == [("backend", "0.10.1")]
    # só docs: o CI pula os jobs pesados e o PR não espera build
    mudados = git(c.remoto, "diff", "--name-only", c.merges[0]["main"], registro["main"]).splitlines()
    assert mudados and all(m.startswith("docs/") for m in mudados), mudados
    assert "docs/spec/deploy/history.json" in mudados
    assert registro["titulo"].startswith("chore(deploy): registro do PR #7 (v0.10.1)"), registro["titulo"]
    # o push do registro na main dispara o webhook do Coolify: o script cancela esse build
    assert c.cancelamentos == [registro["main"]]
    assert c.main_remota() == registro["main"]


@pytest.mark.parametrize("extra", [(), ("--sessao", "onda-x")], ids=["avulso", "onda"])
def test_registro_leva_so_history_e_state_sem_snapshot_nem_draft_do_manual(
    tmp_path, monkeypatch, extra
):
    """ADR 0062, decisões 9 e 10: o rabo grava só a verdade do deploy. Snapshot e
    draft do Manual são da Action do push da main, em nenhum caminho do rabo."""
    fo = carregar_fechar_onda()
    c = pr_de_codigo(tmp_path)
    preparar(fo, monkeypatch, c)

    assert rodar_main(fo, monkeypatch, c, *extra) == 0

    assert c.scripts_chamados() == []
    codigo, registro = c.merges[0]["main"], c.merges[1]["main"]
    mudados = git(c.remoto, "diff", "--name-only", codigo, registro).splitlines()
    assert mudados == ["docs/spec/deploy/history.json", "docs/spec/deploy/state.json"], mudados


def test_history_guarda_todos_os_deploys_sem_teto(tmp_path, monkeypatch):
    """ADR 0062, decisão 9: o `history.json` é a timeline inteira, sem o teto de 50."""
    fo = carregar_fechar_onda()
    antigos = [{"app_version": f"0.9.{n}", "sha": f"{n:040x}"} for n in range(60, 0, -1)]
    c = pr_de_codigo(tmp_path, deploys=antigos)
    preparar(fo, monkeypatch, c)

    assert rodar_main(fo, monkeypatch, c) == 0

    deploys = json.loads(c.na_main("docs/spec/deploy/history.json"))["deploys"]
    assert len(deploys) == 61, len(deploys)
    assert deploys[0]["app_version"] == "0.10.1"
    assert deploys[1:] == antigos, "nenhum deploy antigo some nem muda de ordem"
    assert deploys[-1]["app_version"] == "0.9.1"


def test_sem_snapshot_saiu_da_cli_e_da_docstring(tmp_path, monkeypatch, capsys):
    """Sem snapshot no rabo, a opção que o pulava não tem o que pular."""
    fo = carregar_fechar_onda()
    c = pr_de_codigo(tmp_path)
    preparar(fo, monkeypatch, c)

    with pytest.raises(SystemExit) as e:
        rodar_main(fo, monkeypatch, c, "--sem-snapshot")

    assert e.value.code == 2  # argparse: opção desconhecida
    assert "--sem-snapshot" in capsys.readouterr().err
    assert c.gh_chamadas == [] and c.semaforo == []
    assert "sem-snapshot" not in fo.__doc__


def pr_atras_da_main(tmp_path: Path) -> Cenario:
    """A main andou depois do CI do PR: o rabo traz a main por merge e empurra
    um head novo na branch do PR, que roda o CI de novo."""
    c = pr_de_codigo(tmp_path)
    repo = tmp_path / "repo"
    git(repo, "checkout", "-q", "main")
    escrever(repo, "hospital-reunioes/backend/app/outro.py", "OUTRO = 1\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "fix: outro PR que entrou antes")
    c.avancar_main(repo)
    return c


def test_pr_atras_da_main_recebe_a_main_antes_do_merge(tmp_path, monkeypatch):
    """O ruleset exige a branch em dia com a base: a main andou depois do CI do
    PR, e o script traz a main para a branch antes do merge."""
    fo = carregar_fechar_onda()
    c = pr_atras_da_main(tmp_path)
    main_antes = c.main_remota()
    preparar(fo, monkeypatch, c)

    assert rodar_main(fo, monkeypatch, c) == 0

    codigo = c.merges[0]["main"]
    assert git(c.remoto, "rev-parse", f"{codigo}^") == main_antes
    assert git(c.remoto, "show", f"{codigo}:hospital-reunioes/backend/app/outro.py") == "OUTRO = 1"
    assert git(c.remoto, "show", f"{codigo}:hospital-reunioes/backend/app/prazo.py") == "PRAZO = 15"


def test_ci_vermelho_depois_de_trazer_a_main_para_sem_merge_e_sem_app_version(
    tmp_path, monkeypatch, capsys
):
    fo = carregar_fechar_onda()
    c = pr_atras_da_main(tmp_path)
    main_antes = c.main_remota()
    preparar(fo, monkeypatch, c)
    ver = c.ver_pr

    def ver_com_ci_vermelho_no_head_novo(n, campos):
        info = ver(n, campos)
        if info.get("headRefOid") and info["headRefOid"] != c.head_do_pr:
            c.ci_vermelho.add(info["headRefOid"])
            info = ver(n, campos)
        return info

    c.ver_pr = ver_com_ci_vermelho_no_head_novo

    assert rodar_main(fo, monkeypatch, c) == fo.EXIT_MERGE

    assert c.merges == [] and c.main_remota() == main_antes
    assert c.coolify() == [] and c.tags == []
    assert c.semaforo == [("pegar", "pr-7"), ("soltar", "pr-7")]
    assert "#7" in capsys.readouterr().out


def test_ci_cancelado_sem_runner_e_repetido_e_o_pr_entra_quando_fica_verde(
    tmp_path, monkeypatch
):
    fo = carregar_fechar_onda()
    c = pr_atras_da_main(tmp_path)
    preparar(fo, monkeypatch, c)
    monkeypatch.setattr(fo, "CHECKS_POLL_S", 0)
    c.sem_runner = 2

    assert rodar_main(fo, monkeypatch, c) == 0

    assert c.gh_chamadas.count(["run", "rerun", "555", "--failed"]) == 2
    assert len(c.merges) == 2  # o código e o registro


def test_sem_runner_esgotado_para_sem_merge_e_aponta_o_incidente_nao_o_codigo(
    tmp_path, monkeypatch, capsys
):
    fo = carregar_fechar_onda()
    c = pr_atras_da_main(tmp_path)
    preparar(fo, monkeypatch, c)
    monkeypatch.setattr(fo, "CHECKS_POLL_S", 0)
    c.sem_runner = 99

    assert rodar_main(fo, monkeypatch, c) == fo.EXIT_MERGE

    assert c.gh_chamadas.count(["run", "rerun", "555", "--failed"]) == 3
    assert c.merges == [] and c.coolify() == []
    saida = capsys.readouterr().out
    assert "githubstatus.com" in saida and "CI vermelho" not in saida


def test_cancelamento_que_nao_e_falta_de_runner_continua_ci_vermelho_sem_rerun(
    tmp_path, monkeypatch, capsys
):
    fo = carregar_fechar_onda()
    c = pr_atras_da_main(tmp_path)
    preparar(fo, monkeypatch, c)
    monkeypatch.setattr(fo, "CHECKS_POLL_S", 0)
    c.sem_runner = 99
    c.anotacao_do_cancelamento = "The operation was canceled."

    assert rodar_main(fo, monkeypatch, c) == fo.EXIT_MERGE

    assert ["run", "rerun", "555", "--failed"] not in c.gh_chamadas
    assert "CI vermelho" in capsys.readouterr().out


def test_registro_que_nao_entra_sai_com_5_semaforo_solto_e_producao_intacta(
    tmp_path, monkeypatch, capsys
):
    fo = carregar_fechar_onda()
    c = pr_de_codigo(tmp_path)
    preparar(fo, monkeypatch, c)
    ver = c.ver_pr

    def ver_com_ci_vermelho_no_registro(n, campos):
        if c.prs[n]["headRefName"].startswith("registro/"):
            c.ci_vermelho.add(c._tip(c.prs[n]["headRefName"]))
        return ver(n, campos)

    c.ver_pr = ver_com_ci_vermelho_no_registro

    assert rodar_main(fo, monkeypatch, c) == fo.EXIT_REGISTRO

    assert [m["pr"] for m in c.merges] == [7]
    assert c.main_remota() == c.merges[0]["main"]
    assert c.builds == ["backend"] and c.cancelamentos == []
    assert c.semaforo == [("pegar", "pr-7"), ("soltar", "pr-7")]
    assert "#101" in capsys.readouterr().out


def test_rodada_seguinte_a_um_ci_vermelho_sai_na_mesma_versao_sem_pular(
    tmp_path, monkeypatch
):
    """Sem commit de versão, nada fica na branch para a rodada seguinte contar
    de novo: ela parte do mesmo state.json e a primeira não criou tag."""
    fo = carregar_fechar_onda()
    c = pr_atras_da_main(tmp_path)
    preparar(fo, monkeypatch, c)
    ver = c.ver_pr
    vermelho = {"ligado": True}

    def ver_com_ci_vermelho_na_primeira(n, campos):
        info = ver(n, campos)
        if vermelho["ligado"] and info.get("headRefOid") and info["headRefOid"] != c.head_do_pr:
            c.ci_vermelho.add(info["headRefOid"])
            info = ver(n, campos)
        return info

    c.ver_pr = ver_com_ci_vermelho_na_primeira
    assert rodar_main(fo, monkeypatch, c) == fo.EXIT_MERGE
    head_com_a_main = git(c.remoto, "rev-parse", "feature")
    # o CI ficou verde depois (flaky corrigido); o PR segue com a main trazida
    vermelho["ligado"] = False
    c.ci_vermelho.clear()
    c.pr["headRefOid"] = head_com_a_main

    assert rodar_main(fo, monkeypatch, c) == 0

    assert c.merges[0]["head"] == head_com_a_main
    assert c.tags == [("refs/tags/v0.10.1", c.merges[0]["main"])]
    assert all("--value 0.10.1 " in li for li in c.coolify()), c.coolify()


def test_onda_entra_por_um_pr_de_entrega_que_fecha_as_issues_do_lote(tmp_path, monkeypatch):
    fo = carregar_fechar_onda()
    c = pr_de_codigo(tmp_path)
    preparar(fo, monkeypatch, c)

    assert rodar_main(fo, monkeypatch, c, "--sessao", "onda-x") == 0

    assert c.pushes_na_main() == []
    entrega = c.merges[0]
    assert entrega["branch"] == "onda/onda-x" and entrega["pr"] != 7
    assert re.search(r"^Closes #5$", entrega["corpo"], re.M), entrega["corpo"]
    # o PR do lote fecha apontando o PR de entrega
    fechar = [a for a in c.gh_chamadas if a[:3] == ["pr", "close", "7"]]
    assert len(fechar) == 1 and f"#{entrega['pr']}" in " ".join(fechar[0]), fechar
    assert git(c.remoto, "show", f"{entrega['main']}:hospital-reunioes/backend/app/prazo.py") == "PRAZO = 15"
    assert c.builds == ["backend"]
    # APP_VERSION nos dois apps antes do merge da entrega, tag no squash dela
    assert c.coolify() == [f"app env update uuid-backend APP_VERSION --value 0.10.1 | main={c.base}",
                           f"app env update uuid-frontend APP_VERSION --value 0.10.1 | main={c.base}"]
    assert c.tags == [("refs/tags/v0.10.1", entrega["main"])]


def test_onda_com_ci_vermelho_fecha_o_pr_de_entrega_e_a_rodada_seguinte_entra(
    tmp_path, monkeypatch, capsys
):
    """CI vermelho no PR de entrega: o PR fecha e a branch `onda/<sessao>` some,
    senão a rodada seguinte trava no push (non-fast-forward) e no 422 do PR."""
    fo = carregar_fechar_onda()
    c = pr_de_codigo(tmp_path)
    preparar(fo, monkeypatch, c)
    ver = c.ver_pr
    vermelho = {"ligado": True}

    def ver_com_ci_vermelho_na_entrega(n, campos):
        if vermelho["ligado"] and c.prs[n]["headRefName"] == "onda/onda-x":
            c.ci_vermelho.add(c._tip("onda/onda-x"))
        return ver(n, campos)

    c.ver_pr = ver_com_ci_vermelho_na_entrega

    assert rodar_main(fo, monkeypatch, c, "--sessao", "onda-x") == fo.EXIT_MERGE

    entrega = next(n for n, p in c.prs.items() if p["headRefName"] == "onda/onda-x")
    fechar = [a for a in c.gh_chamadas if a[:3] == ["pr", "close", str(entrega)]]
    assert len(fechar) == 1 and "--delete-branch" in fechar[0], fechar
    assert c.prs[entrega]["state"] == "CLOSED" and c._tip("onda/onda-x") is None
    assert c.merges == [] and c.main_remota() == c.base and c.coolify() == []
    assert c.semaforo == [("pegar", "onda-x"), ("soltar", "onda-x")]
    assert f"#{entrega}" in capsys.readouterr().out

    vermelho["ligado"] = False
    c.ci_vermelho.clear()
    assert rodar_main(fo, monkeypatch, c, "--sessao", "onda-x") == 0

    assert c.merges[0]["branch"] == "onda/onda-x" and c.merges[0]["pr"] != entrega
    assert c.na_main("hospital-reunioes/backend/app/prazo.py") == "PRAZO = 15"


def test_limpeza_remove_o_worktree_de_agente_da_branch_entregue_por_squash(tmp_path, monkeypatch):
    """Com squash, a branch do PR não vira ancestral da main e o `--merged` não a
    acha; o worktree do agente nessa branch, no head que entrou, sai assim mesmo."""
    fo = carregar_fechar_onda()
    c = pr_de_codigo(tmp_path)
    git(c.clone, "fetch", "-q", "origin", "refs/pull/7/head:feature")
    agente = c.clone / ".claude" / "worktrees" / "agente"
    git(c.clone, "worktree", "add", "-q", str(agente), "feature")
    preparar(fo, monkeypatch, c)

    assert rodar_main(fo, monkeypatch, c) == 0

    assert not agente.exists()
    assert "feature" not in git(c.clone, "branch", "--list", "feature")


def test_cancelar_build_do_registro_so_cancela_o_deploy_do_commit_do_registro(monkeypatch):
    fo = carregar_fechar_onda()
    sha = "a" * 40
    listas = {
        "uuid-backend": [
            {"deployment_uuid": "d-codigo", "commit": "b" * 40, "status": "in_progress"},
            {"deployment_uuid": "d-registro", "commit": sha, "status": "queued"},
        ],
        "uuid-frontend": [{"deployment_uuid": "d-pronto", "commit": sha, "status": "finished"}],
    }
    chamadas = []
    monkeypatch.setattr(fo, "coolify_json", lambda args, timeout=120: listas[args[3]])
    monkeypatch.setattr(fo, "run", lambda cmd, **kw: chamadas.append(cmd)
                        or subprocess.CompletedProcess(cmd, 0, "", ""))
    servicos = {s["id"]: s for s in PROJECT["services"]}
    servicos["supabase"] = {"id": "supabase", "type": "supabase"}

    assert fo.cancelar_build_do_registro(servicos, sha) == ["backend"]
    assert chamadas == [["coolify", "deploy", "cancel", "d-registro", "--force"]]


def test_cancelar_build_do_registro_sem_deploy_na_janela_nao_cancela_nada(monkeypatch):
    fo = carregar_fechar_onda()
    chamadas = []
    monkeypatch.setattr(fo, "REGISTRO_JANELA_S", 0)
    monkeypatch.setattr(fo, "coolify_json", lambda args, timeout=120: [])
    monkeypatch.setattr(fo, "run", lambda cmd, **kw: chamadas.append(cmd))

    assert fo.cancelar_build_do_registro({s["id"]: s for s in PROJECT["services"]}, "a" * 40) == []
    assert chamadas == []


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
    assert "Prazo do caso, conta dias uteis" in entrada["subject"], entrada["subject"]
    # contrato do painel (`tools/workflow-dashboard/collect.py`, `_correlate`)
    assert re.search(r"\(#7\)", entrada["raw_subject"]), entrada["raw_subject"]
    assert re.search(r"PRs? #7\b", entrada["notes"]), entrada["notes"]
    assert re.search(r"(?:[Ii]ssues? |Closes )#5\b", entrada["notes"]), entrada["notes"]


def test_com_sessao_o_registro_continua_sendo_da_onda(tmp_path, monkeypatch):
    fo = carregar_fechar_onda()
    c = pr_de_codigo(tmp_path)
    preparar(fo, monkeypatch, c)

    assert rodar_main(fo, monkeypatch, c, "--sessao", "onda-x") == 0

    entrada = json.loads(c.na_main("docs/spec/deploy/history.json"))["deploys"][0]
    assert entrada["subject"].startswith("Onda onda-x: "), entrada["subject"]
    assert TRAVESSAO not in entrada["subject"], entrada["subject"]
    assert c.semaforo == [("pegar", "onda-x"), ("soltar", "onda-x")]


def test_mais_de_um_pr_sem_sessao_para_antes_de_tudo(tmp_path, monkeypatch):
    fo = carregar_fechar_onda()
    c = pr_de_codigo(tmp_path)
    preparar(fo, monkeypatch, c)
    monkeypatch.setattr(sys, "argv", ["fechar_onda.py", "--prs", "7", "8", "--raiz", str(c.clone)])

    with pytest.raises(SystemExit) as e:
        fo.main()

    assert e.value.code == fo.EXIT_PRECOND
    assert c.gh_chamadas == [] and c.semaforo == []


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


# ----------------------------------- classe do lote: app ou ferramenta (#965)

def pr_de_ferramenta(tmp_path: Path, **kw) -> Cenario:
    """PR que não toca `hospital-reunioes/`: script do time e skill. Título `feat`
    de propósito, que num PR de app daria bump minor."""
    return Cenario(tmp_path, 7, kw.pop("titulo", "feat(tools): painel conta PRs por PRD"), kw.pop("issue", 5),
                   kw.pop("arquivos", {"tools/painel.py": "PRDS = 1\n",
                                       ".claude/skills/painel/SKILL.md": "# painel\n"}), **kw)


def test_dry_run_de_pr_so_de_tools_diz_ferramenta_so_merge(tmp_path, monkeypatch, capsys):
    fo = carregar_fechar_onda()
    c = pr_de_ferramenta(tmp_path, arquivos={"tools/painel.py": "PRDS = 1\n"})
    preparar(fo, monkeypatch, c)

    assert rodar_main(fo, monkeypatch, c, "--dry-run") == 0

    plano = [li for li in capsys.readouterr().out.splitlines() if li.startswith("plano:")]
    assert len(plano) == 1, plano
    assert "ferramenta: só merge" in plano[0], plano[0]
    assert "PR #7" in plano[0] and "bump" not in plano[0] and "->" not in plano[0], plano[0]
    assert c.main_remota() == c.base and c.coolify() == [] and c.semaforo == []


@pytest.mark.parametrize("extra", [(), ("--sessao", "onda-x")], ids=["avulso", "onda"])
def test_fechamento_de_ferramenta_so_faz_merge_sem_coolify_nem_registro(
    tmp_path, monkeypatch, capsys, extra
):
    fo = carregar_fechar_onda()
    c = pr_de_ferramenta(tmp_path)
    history_antes = c.na_main("docs/spec/deploy/history.json")
    preparar(fo, monkeypatch, c)

    assert rodar_main(fo, monkeypatch, c, *extra) == 0

    # um merge só, o do código, pela API
    assert len(c.merges) == 1, c.merges
    codigo = c.merges[0]["main"]
    assert c.main_remota() == codigo
    assert git(c.remoto, "show", f"{codigo}:tools/painel.py") == "PRDS = 1"
    # sem bump: a versão do app é a da base
    assert json.loads(c.na_main("hospital-reunioes/frontend/package.json"))["version"] == "0.10.0"
    assert "chore(release)" not in git(c.remoto, "log", "--format=%s", f"{c.base}..{c.merges[0]['head']}")
    # coolify falso sem nenhuma chamada: nem APP_VERSION, nem deploy forçado;
    # e sem versão nova, sem tag
    assert c.coolify() == [] and c.tags == []
    assert c.builds == [] and c.healths == []
    # nenhum PR de registro: o único POST de PR é o de entrega da onda
    abertos = [a for a in c.gh_chamadas if a[:4] == ["api", "-X", "POST", "repos/{owner}/{repo}/pulls"]]
    assert len(abertos) == (0 if not extra else 1), abertos
    assert not any("head=registro/" in " ".join(a) for a in abertos), abertos
    assert c.na_main("docs/spec/deploy/history.json") == history_antes
    # o build que o webhook disparar para o merge é cancelado, como o do registro
    assert c.cancelamentos == [codigo]
    assert c.semaforo[-1][0] == "soltar"
    assert "ferramenta" in capsys.readouterr().out


def test_pr_misto_de_ferramenta_e_frontend_segue_o_fluxo_de_app(tmp_path, monkeypatch, capsys):
    fo = carregar_fechar_onda()
    c = pr_de_ferramenta(tmp_path, arquivos={
        "tools/painel.py": "PRDS = 1\n",
        "hospital-reunioes/frontend/src/painel.ts": "export const PRDS = 1;\n",
    })
    preparar(fo, monkeypatch, c)

    assert rodar_main(fo, monkeypatch, c, "--dry-run") == 0
    plano = next(li for li in capsys.readouterr().out.splitlines() if li.startswith("plano:"))
    assert "app: bump minor v0.10.0 -> v0.11.0" in plano and "ferramenta" not in plano, plano

    assert rodar_main(fo, monkeypatch, c) == 0

    # o fluxo de app: versão nova sem commit, APP_VERSION nos dois apps antes do
    # merge, tag, build, health e registro
    assert json.loads(c.na_main("hospital-reunioes/frontend/package.json"))["version"] == "0.10.0"
    assert c.coolify() == [f"app env update uuid-backend APP_VERSION --value 0.11.0 | main={c.base}",
                           f"app env update uuid-frontend APP_VERSION --value 0.11.0 | main={c.base}"]
    assert c.tags == [("refs/tags/v0.11.0", c.merges[0]["main"])]
    assert c.builds == ["frontend"]
    assert [m["pr"] for m in c.merges] == [7, 101] and c.merges[1]["branch"].startswith("registro/")
    entrada = json.loads(c.na_main("docs/spec/deploy/history.json"))["deploys"][0]
    assert entrada["app_version"] == "0.11.0" and entrada["sha"] == c.merges[0]["main"]


def test_mover_codigo_do_app_para_tools_conta_como_app(tmp_path, monkeypatch, capsys):
    """O `files` do gh mostra um rename só pelo caminho novo. Sem olhar o caminho
    antigo, tirar código de `hospital-reunioes/` passaria por ferramenta, e a
    produção ficaria com o arquivo que a main já não tem."""
    fo = carregar_fechar_onda()
    c = pr_de_ferramenta(tmp_path, titulo="chore(tools): prazo vira script do time",
                         arquivos={"tools/prazo.py": "PRAZO = 10\n"})
    repo = tmp_path / "repo"
    git(repo, "rm", "-q", "hospital-reunioes/backend/app/prazo.py")
    git(repo, "commit", "-q", "-m", "chore(tools): tira o prazo do backend")
    git(repo, "push", "-q", str(c.remoto), "feature", "feature:refs/pull/7/head")
    c.head_do_pr = c.pr["headRefOid"] = git(c.remoto, "rev-parse", "feature")
    assert c.pr["files"] == [{"path": "tools/prazo.py"}]
    preparar(fo, monkeypatch, c)

    assert rodar_main(fo, monkeypatch, c, "--dry-run") == 0

    plano = next(li for li in capsys.readouterr().out.splitlines() if li.startswith("plano:"))
    assert "app: bump patch v0.10.0 -> v0.10.1" in plano, plano


def test_docstring_explica_as_duas_classes_sem_docs_only_e_sem_travessao():
    fo = carregar_fechar_onda()
    doc = " ".join(fo.__doc__.split())

    assert "docs-only" not in doc
    assert re.search(r'"app" se algum (arquivo )?esta em `hospital-reunioes/`', doc), doc
    assert re.search(r'"ferramenta" se nenhum esta', doc), doc
    assert "misto" in doc
    fonte = (SCRIPTS / "fechar_onda.py").read_text(encoding="utf-8")
    assert TRAVESSAO not in fonte and MEIA_RISCA not in fonte


@pytest.mark.parametrize("de", [pr_de_codigo, pr_de_ferramenta], ids=["app", "ferramenta"])
def test_pr_sem_nenhum_check_para_nas_pre_condicoes_seja_app_ou_ferramenta(
    tmp_path, monkeypatch, capsys, de
):
    """O ruleset exige os checks do CI e o `esperar_checks` so aceita lista nao
    vazia: PR de ferramenta sem check esperaria os 40 min e falharia. Parar
    antes, sem classificar pelo `files` do gh, que nao ve o caminho antigo de um
    rename."""
    fo = carregar_fechar_onda()
    c = de(tmp_path)
    c.sem_checks = True
    monkeypatch.setattr(fo, "CHECKS_POLL_S", 0)
    monkeypatch.setattr(fo, "CHECKS_TIMEOUT_S", 0)

    saida = parar_nas_pre_condicoes(fo, monkeypatch, c, capsys)

    assert "#7 sem nenhum check" in saida, saida
    assert c.merges == []


def falhar_no_cancelamento(fo, monkeypatch, c: Cenario) -> None:
    def cancelar(servicos_cfg, sha):
        raise subprocess.TimeoutExpired(["coolify", "deploy", "cancel"], 30)

    monkeypatch.setattr(fo, "cancelar_build_do_registro", cancelar)


def falhar_no_gh_depois_do_merge(fo, monkeypatch, c: Cenario) -> None:
    ver = c.ver_pr

    def ver_que_cai_no_estado(n, campos):
        if campos == ["state"]:
            raise RuntimeError("gh pr view -> 502 Bad Gateway")
        return ver(n, campos)

    c.ver_pr = ver_que_cai_no_estado


@pytest.mark.parametrize("falha", [falhar_no_cancelamento, falhar_no_gh_depois_do_merge],
                         ids=["coolify-timeout", "gh-pr-view"])
def test_ferramenta_que_falha_depois_do_merge_solta_o_semaforo_e_diz_producao_intacta(
    tmp_path, monkeypatch, capsys, falha
):
    fo = carregar_fechar_onda()
    c = pr_de_ferramenta(tmp_path)
    preparar(fo, monkeypatch, c)
    falha(fo, monkeypatch, c)

    assert rodar_main(fo, monkeypatch, c) == fo.EXIT_REGISTRO

    assert [m["pr"] for m in c.merges] == [7] and c.main_remota() == c.merges[0]["main"]
    assert c.semaforo == [("pegar", "pr-7"), ("soltar", "pr-7")]
    saida = capsys.readouterr().out
    assert "merge feito, producao intacta" in saida, saida
    assert "rollback" not in saida and "Semaforo preso" not in saida, saida


# ------------------------------------------- sha256 da migration no corpo do PR

SQL_DO_ARQUIVO = "create table triagem (id int);\n"
SHA_DO_ARQUIVO = hashlib.sha256(SQL_DO_ARQUIVO.encode("utf-8")).hexdigest()
SHA_VELHO = hashlib.sha256(b"create table triagem ();\n").hexdigest()


def pr_com_migration(tmp_path: Path, corpo: str) -> Cenario:
    return Cenario(tmp_path, 8, "feat(ouvidoria): triagem", 6, {
        f"{MIGRATIONS}/112_triagem.sql": SQL_DO_ARQUIVO,
        "hospital-reunioes/backend/app/prazo.py": "PRAZO = 15\n",
    }, corpo=corpo)


def corpo_com_hash(sha: str) -> str:
    return (
        "## Migration 112 (conferência por hash)\n\n"
        f"`sha256` do arquivo `{MIGRATIONS}/112_triagem.sql`:\n\n```\n{sha}\n```\n"
    )


def parar_nas_pre_condicoes(fo, monkeypatch, c: Cenario, capsys) -> str:
    preparar(fo, monkeypatch, c)
    with pytest.raises(SystemExit) as e:
        rodar_main(fo, monkeypatch, c)
    assert e.value.code == fo.EXIT_PRECOND
    # parou antes de tocar em qualquer coisa
    assert c.semaforo == [] and c.coolify() == [] and c.main_remota() == c.base
    return capsys.readouterr().out


def test_hash_do_corpo_diferente_do_arquivo_para_nas_pre_condicoes(
    tmp_path, monkeypatch, capsys
):
    fo = carregar_fechar_onda()
    c = pr_com_migration(tmp_path, corpo_com_hash(SHA_VELHO))

    saida = parar_nas_pre_condicoes(fo, monkeypatch, c, capsys)

    assert "#8" in saida and "112_triagem.sql" in saida, saida
    assert SHA_DO_ARQUIVO in saida and SHA_VELHO in saida, saida


def test_corpo_sem_hash_da_migration_para_e_diz_o_hash_do_arquivo(
    tmp_path, monkeypatch, capsys
):
    fo = carregar_fechar_onda()
    c = pr_com_migration(tmp_path, "## O que mudou\n\nTabela nova.\n")

    saida = parar_nas_pre_condicoes(fo, monkeypatch, c, capsys)

    assert "112_triagem.sql" in saida and SHA_DO_ARQUIVO in saida, saida


def test_hash_do_corpo_igual_ao_arquivo_segue(tmp_path, monkeypatch, capsys):
    fo = carregar_fechar_onda()
    c = pr_com_migration(tmp_path, corpo_com_hash(SHA_DO_ARQUIVO.upper()))
    preparar(fo, monkeypatch, c)

    assert rodar_main(fo, monkeypatch, c, "--dry-run") == 0
    assert "112_triagem.sql" in capsys.readouterr().out


def test_migration_que_a_main_ja_tem_por_squash_nao_pede_hash(tmp_path, monkeypatch):
    """PR empilhado sobre outro que entrou por squash traz de novo a migration
    que a main já tem: ela não é nova, e o corpo deste PR não precisa do hash."""
    fo = carregar_fechar_onda()
    c = pr_com_migration(tmp_path, "## O que mudou\n\nSó o prazo.\n")
    repo = tmp_path / "repo"
    git(repo, "checkout", "-q", "main")
    escrever(repo, f"{MIGRATIONS}/112_triagem.sql", SQL_DO_ARQUIVO)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "squash do PR de baixo")
    c.avancar_main(repo)
    preparar(fo, monkeypatch, c)

    assert rodar_main(fo, monkeypatch, c, "--dry-run") == 0


def test_pr_sem_migration_nova_nao_pede_hash(tmp_path, monkeypatch):
    fo = carregar_fechar_onda()
    c = pr_de_codigo(tmp_path, corpo="")
    preparar(fo, monkeypatch, c)

    assert rodar_main(fo, monkeypatch, c, "--dry-run") == 0


# ------------------------------------- rabo rodado de dentro do próprio worktree

def test_rabo_rodado_do_worktree_do_autor_nao_remove_o_proprio_checkout(
    tmp_path, monkeypatch
):
    """O autor roda o rabo do próprio checkout, um worktree em `.claude/worktrees/`
    na branch do PR. Depois do push essa branch está na main, mas a limpeza não
    pode remover o worktree de onde o script roda: o arquivo sujo sumiria e o
    `git` seguinte, com `cwd` apagado, viraria um exit 3 falso depois do deploy
    verde."""
    fo = carregar_fechar_onda()
    c = pr_de_codigo(tmp_path)
    git(c.clone, "fetch", "-q", "origin", "refs/pull/7/head:feature")
    autor = c.clone / ".claude" / "worktrees" / "autor"
    git(c.clone, "worktree", "add", "-q", str(autor), "feature")
    escrever(autor, "rascunho.txt", "trabalho nao commitado\n")
    preparar(fo, monkeypatch, c)
    monkeypatch.chdir(autor)
    monkeypatch.setattr(sys, "argv", ["fechar_onda.py", "--prs", "7"])

    assert fo.main() == 0

    assert (autor / "rascunho.txt").read_text(encoding="utf-8") == "trabalho nao commitado\n"
    lista = git(c.clone, "worktree", "list", "--porcelain")
    assert f"worktree {autor.resolve()}" in lista, lista
    assert c.semaforo == [("pegar", "pr-7"), ("soltar", "pr-7")]
