"""O `fechar_onda.py` como rabo único de um PR avulso (issues #907 e #910, ADR 0061).

O `/ship` passou a parar no PR verde, e quem faz merge, bump, `APP_VERSION`,
build, health e registro de um PR só é o mesmo script da onda. Estes testes
montam um repositório `git` de verdade em `tmp_path` (uma `main` de base, o PR
na branch `feature` e em `refs/pull/<n>/head` num remoto nu, como no GitHub) e
rodam o `main()` do script contra ele.

A `main` do remoto está sob o ruleset (issue #910): um hook `pre-receive` recusa
todo push nela, como o GitHub recusa com `GH013`. Ela só anda pelo dublê do
GitHub, que faz o squash pela API do jeito que o repositório permite: exige o
`sha` do head, o CI verde e o merge sem conflito com a main, sem exigir a branch
em dia com a base (ADR 0064, decisão 2), e apaga a branch depois.
Fica de fora só o que sai da máquina: o `coolify` é um executável falso no PATH
que anota cada chamada, e o build e o health devolvem verde sem rede.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shlex
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

# O backend em modo imagem (issue #1001): o Coolify roda a imagem que o CI
# publicou no GHCR, sem build e sem webhook.
PROJECT_IMAGEM = {
    "services": [
        {
            **PROJECT["services"][0],
            "build": {"build_pack": "dockerimage", "base_directory": "/hospital-reunioes/backend",
                      "image": "ghcr.io/dono/repo-backend", "publish_workflow": "imagem-backend.yml"},
        },
        PROJECT["services"][1],
    ]
}

def digest_de(semente: str) -> str:
    return "sha256:" + hashlib.sha256(semente.encode()).hexdigest()


DIGEST_FORJADO = digest_de("imagem de um run de outra branch")


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
                 versao_em_producao: str = "0.10.0", project: dict | None = None,
                 sha_no_ar: str | None = None, digest_no_ar: str | None = None):
        self.numero = numero
        self.issue = issue
        self.log_scripts = tmp_path / "scripts-chamados.log"
        repo = self.repo = tmp_path / "repo"
        repo.mkdir()
        git(repo, "init", "-q", "-b", "main")
        escrever(repo, "hospital-reunioes/frontend/package.json",
                 '{\n  "name": "frontend",\n  "version": "0.10.0"\n}\n')
        escrever(repo, "hospital-reunioes/backend/app/prazo.py", "PRAZO = 10\n")
        escrever(repo, f"{MIGRATIONS}/111_base.sql", "select 1;\n")
        escrever(repo, "docs/spec/deploy/project.json", json_txt(project or PROJECT))
        escrever(repo, "docs/spec/deploy/state.json", json_txt({
            "last_app_version": versao_em_producao,
            "production": {"repo": "dono/repo"},
            "services": [{"id": "backend", **({"last_deploy_sha": sha_no_ar} if sha_no_ar else {}),
                          **({"last_deploy_digest": digest_no_ar} if digest_no_ar else {})},
                         {"id": "frontend"}],
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
        # o ruleset de antes da ADR 0064 (decisão 2) ainda aplicado no GitHub:
        # o merge de branch atrás da base é recusado
        self.ruleset_antigo = False
        self.sem_checks = False  # o CI nunca rodou: nenhum check no PR
        self.bloqueadoras: dict[int, list[dict]] = {}  # issue -> o `blocked_by` dela (issue #999)
        # quantas rodadas do CI do head que o rabo empurra o GitHub cancela por
        # falta de runner (#953)
        self.sem_runner = 0
        self.anotacao_do_cancelamento = SEM_RUNNER
        self.merges: list[dict] = []
        self.gh_chamadas: list[list[str]] = []
        self.builds: list[str] = []
        self.esperados: list[str] = []  # sha do squash cujo deploy o rabo esperou
        self.healths: list[tuple[str, str | None]] = []
        # versões em que o /api/health do backend responde 500 (issue #968)
        self.health_ruim_em: set[str | None] = set()
        self.rollbacks: list[str] = []  # apps cujo deploy de rollback o rabo esperou
        self.semaforo: list[tuple[str, str]] = []
        self.cancelamentos: list[str] = []
        self.tags: list[tuple[str, str]] = []  # (ref, sha) criados pela API
        # o workflow que publica a imagem no GHCR (issue #1001): os `-f` de cada
        # disparo e quantas chamadas ao Coolify (fora as leituras) vieram antes dele
        self.publicacoes: list[dict] = []
        self.publicacao_falha = False
        # o GHCR (revisão do PR #1016): tag -> digest para o qual ela aponta agora;
        # os artefatos `digest-backend` de cada run (id -> digest); os runs do
        # workflow da imagem de antes deste rabo; os heads cujo CI não guardou digest
        self.ghcr: dict[str, str] = {}
        self.artefatos: dict[str, str] = {}
        self.runs_anteriores: list[dict] = []
        self.ci_sem_digest: set[str] = set()
        self.tag_sobrescrita = False  # um run de outra branch troca a tag do squash depois do workflow
        if sha_no_ar and digest_no_ar:
            self.ghcr[sha_no_ar] = digest_no_ar
        self.deploys_novos: list[str] = []  # apps cujo deploy novo (sem webhook) o rabo esperou
        # a Action pós-merge que grava o registro (ADR 0064, decisão 6b): cada
        # disparo, a conclusão de cada run (success sem nada dito; "pendente"
        # fica na fila) e o commit que o bot empurrou na main
        self.tmp = tmp_path
        self.registros: list[dict] = []
        self.action_do_registro: list[str] = []
        self.commits_do_bot: list[str] = []
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
        # o que o `coolify app rollback images` devolve por app (issue #968)
        self.dir_coolify = tmp_path / "coolify-dados"
        self.dir_coolify.mkdir()
        coolify = bin_falso / "coolify"
        coolify.write_text(
            "#!/bin/sh\n"
            f"main=$(git --git-dir={self.remoto} rev-parse main)\n"
            f'echo "$* | main=$main" >> {self.log_coolify}\n'
            'if [ "$1 $2" = "app get" ]; then\n'
            f'  [ -f "{self.dir_coolify}/app-$3.json" ] && cat "{self.dir_coolify}/app-$3.json"\n'
            "  exit 0\n"
            "fi\n"
            'case "$1 $2 $3" in\n'
            '  "app rollback images")\n'
            f'    [ -f "{self.dir_coolify}/imagens-$4.json" ] && cat "{self.dir_coolify}/imagens-$4.json" ;;\n'
            '  "app rollback run")\n'
            f'    [ -f "{self.dir_coolify}/rollback-recusado" ] && exit 1 ;;\n'
            "esac\n"
            "exit 0\n",
            encoding="utf-8",
        )
        coolify.chmod(0o755)
        # o `coolify app get` de cada app diz o build pack que o Coolify roda de verdade
        for s in (project or PROJECT)["services"]:
            build = s.get("build") or {}
            self.build_pack_no_coolify(s["uuid"], build.get("build_pack", "dockerfile"), build.get("image"))
        self.path = f"{bin_falso}{os.pathsep}{os.environ.get('PATH', '')}"
        self.home = tmp_path / "home"
        self.home.mkdir()

    def outro_pr(self, numero: int, titulo: str, issue: int, arquivos: dict[str, str]) -> dict:
        """Mais um PR do lote, numa branch própria a partir da base."""
        branch = f"feature-{numero}"
        git(self.repo, "checkout", "-q", "-b", branch, "main")
        for caminho, texto in arquivos.items():
            escrever(self.repo, caminho, texto)
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", titulo)
        git(self.repo, "push", "-q", str(self.remoto), branch, f"{branch}:refs/pull/{numero}/head")
        self.prs[numero] = {
            **self.pr,
            "number": numero,
            "headRefName": branch,
            "headRefOid": git(self.remoto, "rev-parse", branch),
            "title": titulo,
            "files": [{"path": p} for p in arquivos],
            "commits": [{"messageHeadline": titulo, "messageBody": ""}],
            "url": f"https://github.com/dono/repo/pull/{numero}",
            "closingIssuesReferences": [{"number": issue}],
        }
        return self.prs[numero]

    def imagens_no_coolify(self, uuid: str, no_ar: str | None, revertidas: tuple[str, ...] = ()) -> None:
        """Lista do `coolify app rollback images`, no formato real (conferido em
        06/10/2026), como o rabo a le ANTES do merge: a imagem no ar e, mais novas
        que ela, as que um rollback anterior tirou do ar."""
        imagens = [{"created_at": f"2026-10-06 0{5 - i}:00:00 +0000 UTC", "is_current": False, "tag": tag}
                   for i, tag in enumerate(revertidas)]
        if no_ar:
            imagens.append({"created_at": "2026-10-05 22:00:00 +0000 UTC", "is_current": True, "tag": no_ar})
        (self.dir_coolify / f"imagens-{uuid}.json").write_text(
            json.dumps({"current": no_ar, "images": imagens}), encoding="utf-8")

    def build_pack_no_coolify(self, uuid: str, build_pack: str, imagem: str | None = None) -> None:
        dado = {"uuid": uuid, "build_pack": build_pack, "status": "running:healthy"}
        if imagem:
            dado["docker_registry_image_name"] = imagem
        (self.dir_coolify / f"app-{uuid}.json").write_text(json.dumps(dado), encoding="utf-8")

    def recusar_rollback(self) -> None:
        (self.dir_coolify / "rollback-recusado").write_text("", encoding="utf-8")

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

    def coolify_sem_leituras(self) -> list[str]:
        return [li for li in self.coolify() if not li.startswith(("app deployments list", "app get "))]

    def disparar_workflow(self, cmd: list[str]) -> None:
        """`gh workflow run <arquivo> --ref main -f k=v ...`, como o GitHub: o run
        nasce com o run-name do workflow, que leva o sha. Como o workflow: a
        primeira origem `<head>@<digest>` ganha a tag do squash com o mesmo
        digest; sem origem, o build publica um digest novo. O digest vai para o
        artefato do run."""
        campos = dict(cmd[i + 1].split("=", 1) for i, a in enumerate(cmd) if a == "-f")
        ref = cmd[cmd.index("--ref") + 1] if "--ref" in cmd else None
        self.publicacoes.append({"workflow": cmd[3], "ref": ref, **campos,
                                 "coolify_antes": len(self.coolify_sem_leituras())})
        if self.publicacao_falha:
            return
        origens = campos["origens"].split()
        digest = origens[0].split("@", 1)[1] if origens else digest_de(f"build-{campos['sha']}")
        self.artefatos[str(900 + len(self.publicacoes) - 1)] = digest
        self.ghcr[campos["sha"]] = DIGEST_FORJADO if self.tag_sobrescrita else digest

    def imagem_publicada_antes(self, sha: str, digest: str) -> None:
        """Um run do workflow da imagem de antes deste rabo (o passo 2 do PR #1016)."""
        run_id = 800 + len(self.runs_anteriores)
        self.runs_anteriores.append({"databaseId": run_id, "displayTitle": f"Imagem do backend {sha}",
                                     "status": "completed", "conclusion": "success"})
        self.artefatos[str(run_id)] = digest
        self.ghcr[sha] = digest

    def runs_do_workflow(self) -> list[dict]:
        return [{"databaseId": 900 + i, "displayTitle": f"Imagem do backend {p['sha']}",
                 "status": "completed", "conclusion": "failure" if self.publicacao_falha else "success"}
                for i, p in reversed(list(enumerate(self.publicacoes)))] + self.runs_anteriores

    def disparar_registro(self, cmd: list[str]) -> None:
        """`gh workflow run pos-merge.yml --ref main -F registro=@<arquivo>`, como a
        Action: o `gerar` roda o `tools/aplicar_registro.py` de verdade num checkout
        da ponta da main, e o `commitar` empurra o commit do bot pela deploy key,
        que o ruleset deixa passar (aqui, o lado do servidor, sem o hook)."""
        nome, _, valor = cmd[cmd.index("-F") + 1].partition("=")
        assert nome == "registro" and valor.startswith("@"), cmd
        texto = Path(valor[1:]).read_text(encoding="utf-8")
        conclusao = self.action_do_registro.pop(0) if self.action_do_registro else "success"
        self.registros.append({"ref": cmd[cmd.index("--ref") + 1], "registro": json.loads(texto),
                               "conclusao": conclusao, "healths": list(self.healths)})
        if conclusao != "success":
            return
        checkout = self.tmp / f"action-{len(self.registros)}"
        git(self.tmp, "clone", "-q", str(self.remoto), str(checkout))
        proc = subprocess.run([sys.executable, str(RAIZ / "tools" / "aplicar_registro.py")], cwd=checkout,
                              env={**os.environ, "REGISTRO": texto}, capture_output=True, text=True)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        git(checkout, "add", "-A")
        git(checkout, "commit", "-q", "-m", "chore(spec): registro, snapshot e draft do Manual pós-merge [skip ci]")
        self.avancar_main(checkout)
        self.commits_do_bot.append(self.main_remota())

    def runs_do_registro(self) -> list[dict]:
        return [{"databaseId": 700 + i, "status": "queued" if r["conclusao"] == "pendente" else "completed",
                 "conclusion": None if r["conclusao"] == "pendente" else r["conclusao"]}
                for i, r in reversed(list(enumerate(self.registros)))]

    def runs_do_ci(self, head: str) -> list[dict]:
        """O CI verde do PR no `head`, que publicou a imagem e guardou o digest."""
        run_id = f"ci-{head}"
        if head not in self.ci_sem_digest:
            self.artefatos[run_id] = digest_de(head)
        return [{"databaseId": run_id}]

    def baixar_artefato(self, cmd: list[str]) -> int:
        """`gh run download <id> -n <nome> -D <dir>`: grava `<dir>/digest`."""
        nome, destino = cmd[cmd.index("-n") + 1], Path(cmd[cmd.index("-D") + 1])
        if nome != "digest-backend" or cmd[3] not in self.artefatos:
            return 1
        (destino / "digest").write_text(self.artefatos[cmd[3]] + "\n", encoding="utf-8")
        return 0

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

    def _atras(self, head: str) -> bool:
        return subprocess.run(["git", "merge-base", "--is-ancestor", "main", head],
                              cwd=self.remoto).returncode != 0

    def _arvore_do_squash(self, head: str) -> str | None:
        """A árvore do squash de `head` sobre a main como o GitHub monta, um
        merge de três vias; None se conflita."""
        proc = subprocess.run(["git", "merge-tree", "--write-tree", "main", head],
                              cwd=self.remoto, capture_output=True, text=True, check=False)
        return proc.stdout.split()[0] if proc.returncode == 0 else None

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
        # sem a exigência de em dia com a base o GitHub ainda pode dizer BEHIND,
        # e o merge passa assim mesmo
        pr["mergeStateStatus"] = ("DIRTY" if self._arvore_do_squash(head) is None
                                  else "BEHIND" if self._atras(head) else "CLEAN")
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
        que o repositório permite), recusa head que mudou, CI vermelho e conflito
        com a main, e apaga a branch do PR depois do merge. Branch atrás da base
        entra (ADR 0064, decisão 2), salvo com o ruleset antigo ainda aplicado."""
        pr = self.prs[n]
        head = self._tip(pr["headRefName"])
        if campos.get("merge_method") != "squash":
            raise RuntimeError("gh api -> 405: Merge commits are not allowed on this repository.")
        if campos.get("sha") != head:
            raise RuntimeError("gh api -> 409: Head branch was modified. Review and try the merge again.")
        if self.ruleset_antigo and self._atras(head):
            raise RuntimeError("gh api -> 405: Head branch is not up to date with the base branch.")
        if head in self.ci_vermelho:
            raise RuntimeError("gh api -> 405: Required status check is failing.")
        arvore = self._arvore_do_squash(head)
        if arvore is None:
            raise RuntimeError("gh api -> 405: Pull Request is not mergeable")
        antes = self.main_remota()
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
        bloqueio = re.fullmatch(r"repos/\{owner\}/\{repo\}/issues/(\d+)/dependencies/blocked_by", args[-1])
        if args[:1] == ["api"] and len(args) == 2 and bloqueio:
            return c.bloqueadoras.get(int(bloqueio.group(1)), [])
        if args[:2] == ["pr", "view"]:
            # como o gh de verdade: só os campos pedidos no --json
            return c.ver_pr(int(args[2]), args[args.index("--json") + 1].split(","))
        if args[:2] == ["issue", "view"]:
            return {"body": "## Pai\n\n`#902`, PRD da esteira.\n"}
        if args[:2] == ["run", "list"]:
            wf = args[args.index("--workflow") + 1]
            if wf == "ci.yml":
                assert args[args.index("--event") + 1] == "pull_request", args
                assert args[args.index("--status") + 1] == "success", args
                return c.runs_do_ci(args[args.index("--commit") + 1])
            # um run disparado de outra branch roda outro workflow: só os da main valem
            assert args[args.index("--branch") + 1] == "main", args
            if wf == "pos-merge.yml":
                assert args[args.index("--event") + 1] == "workflow_dispatch", args
                return c.runs_do_registro()
            return c.runs_do_workflow()
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
            if cmd[1:4] == ["workflow", "run", "pos-merge.yml"]:
                c.disparar_registro(cmd)
            elif cmd[1:3] == ["workflow", "run"]:
                c.disparar_workflow(cmd)
            if cmd[1:3] == ["run", "download"]:
                return subprocess.CompletedProcess(cmd, c.baixar_artefato(cmd), "", "")
            return subprocess.CompletedProcess(cmd, 0, "", "")
        return run_real(cmd, *args, **kwargs)

    def semaforo(raiz, acao, chave, descricao=""):
        c.semaforo.append((acao, chave))
        return 0

    def esperar_build(service, desde, sha_push, ignorar=()):
        c.builds.append(service["id"])
        c.esperados.append(sha_push)
        return "finished", 42

    def checar_health(service, versao_esperada):
        c.healths.append((service["id"], versao_esperada))
        if service["id"] == "backend" and versao_esperada in c.health_ruim_em:
            return {"ok": False, "status": 500, "latency_ms": 5,
                    "corpo": '{"detail":"relation \\"prazos\\" does not exist"}'}
        return {"ok": True, "status": 200, "latency_ms": 5}

    def esperar_rollback(service, antes):
        c.rollbacks.append(service["id"])
        return "finished"

    def esperar_deploy_novo(service, antes):
        c.deploys_novos.append(service["id"])
        return "finished"

    def cancelar_build_do_registro(servicos_cfg, sha):
        c.cancelamentos.append(sha)
        return []

    monkeypatch.setattr(fo, "gh_json", gh_json)
    monkeypatch.setattr(fo, "run", run)
    monkeypatch.setattr(fo, "semaforo", semaforo)
    monkeypatch.setattr(fo, "esperar_build", esperar_build)
    monkeypatch.setattr(fo, "checar_health", checar_health)
    monkeypatch.setattr(fo, "esperar_rollback", esperar_rollback)
    monkeypatch.setattr(fo, "esperar_deploy_novo", esperar_deploy_novo)
    monkeypatch.setattr(fo, "cancelar_build_do_registro", cancelar_build_do_registro)
    monkeypatch.setattr(fo, "IMAGEM_POLL_S", 0)
    monkeypatch.setattr(fo, "digest_no_ghcr", lambda imagem, tag: c.ghcr.get(tag))


def rodar_main(fo, monkeypatch, c: Cenario, *extra: str) -> int:
    monkeypatch.setattr(sys, "argv", ["fechar_onda.py", "--prs", str(c.numero),
                                      "--raiz", str(c.clone), *extra])
    return fo.main()


def rodar_onda(fo, monkeypatch, c: Cenario, prs: list[int], *extra: str) -> int:
    monkeypatch.setattr(sys, "argv", ["fechar_onda.py", "--prs", *map(str, prs), "--sessao", "onda-x",
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
        f"app rollback images uuid-backend --format json | main={c.base}",
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


def test_registro_vai_pela_action_na_main_depois_do_health_sem_pr_de_registro(
    tmp_path, monkeypatch, capsys
):
    """ADR 0064, decisão 6b: o rabo termina no health e dispara a Action
    pós-merge na `main` com o registro; quem grava os dois JSONs é o bot, pela
    deploy key. O rabo só sai depois de ver a entrada no `history.json` da
    `main`, e cancela o build que o webhook do Coolify dispara para o commit do
    bot (issue #851)."""
    fo = carregar_fechar_onda()
    c = pr_de_codigo(tmp_path)
    preparar(fo, monkeypatch, c)

    assert rodar_main(fo, monkeypatch, c) == 0

    # nenhum PR além do do autor: o único merge é o do código
    assert [m["pr"] for m in c.merges] == [7]
    assert [a for a in c.gh_chamadas if a[:4] == ["api", "-X", "POST", "repos/{owner}/{repo}/pulls"]] == []
    # um disparo, na main, depois do health verde
    [disparo] = c.registros
    assert disparo["ref"] == "main" and disparo["healths"] == [("backend", "0.10.1")]
    codigo, bot = c.merges[0]["main"], c.commits_do_bot[0]
    assert disparo["registro"]["entrada"]["sha"] == codigo
    assert c.main_remota() == bot and git(c.remoto, "rev-parse", f"{bot}^") == codigo
    entrada = json.loads(c.na_main("docs/spec/deploy/history.json"))["deploys"][0]
    assert entrada == disparo["registro"]["entrada"]
    assert json.loads(c.na_main("docs/spec/deploy/state.json"))["last_run"]["sha"] == codigo
    # o commit do bot é push na main: o build que o webhook dispara é cancelado
    assert c.cancelamentos == [bot]
    [registro] = linhas_com(capsys.readouterr().out, "registro:")
    assert "Action pos-merge" in registro and bot[:8] in registro, registro
    # o arquivo do registro é de quem dispara à mão; com o registro na main, sai
    assert list(c.home.glob("registro-*")) == []


def comando_do_registro(saida: str) -> list[str]:
    [linha] = linhas_com(saida, "registro:")
    return shlex.split(linha[linha.index("`") + 1:linha.rindex("`")])


@pytest.mark.parametrize("conclusao", ["failure", "pendente"], ids=["run-vermelho", "sem-fim"])
def test_action_que_nao_confirma_sai_com_5_e_imprime_o_disparo_a_mao(tmp_path, monkeypatch, capsys, conclusao):
    """Produção está certa: o rabo solta o semáforo e diz como disparar a
    Action à mão com o mesmo registro, que fica num arquivo."""
    fo = carregar_fechar_onda()
    c = pr_de_codigo(tmp_path)
    preparar(fo, monkeypatch, c)
    monkeypatch.setattr(fo, "REGISTRO_POLL_S", 0)
    monkeypatch.setattr(fo, "REGISTRO_TIMEOUT_S", 0)
    c.action_do_registro = [conclusao]

    assert rodar_main(fo, monkeypatch, c) == fo.EXIT_REGISTRO

    assert [m["pr"] for m in c.merges] == [7] and c.main_remota() == c.merges[0]["main"]
    assert c.builds == ["backend"] and c.cancelamentos == []
    assert c.semaforo == [("pegar", "pr-7"), ("soltar", "pr-7")]
    cmd = comando_do_registro(capsys.readouterr().out)
    assert cmd[:5] == ["gh", "workflow", "run", "pos-merge.yml", "--ref"], cmd
    # o comando impresso grava o mesmo registro
    c.disparar_registro(cmd)
    entrada = json.loads(c.na_main("docs/spec/deploy/history.json"))["deploys"][0]
    assert entrada == c.registros[0]["registro"]["entrada"] and entrada["sha"] == c.merges[0]["main"]


def test_run_do_registro_cancelado_na_fila_e_disparado_de_novo(tmp_path, monkeypatch):
    """Um push que chega com o disparo na fila do grupo `pos-merge` cancela o
    disparo: o rabo dispara de novo, e a entrada entra uma vez."""
    fo = carregar_fechar_onda()
    c = pr_de_codigo(tmp_path)
    preparar(fo, monkeypatch, c)
    monkeypatch.setattr(fo, "REGISTRO_POLL_S", 0)
    c.action_do_registro = ["cancelled"]

    assert rodar_main(fo, monkeypatch, c) == 0

    assert [r["conclusao"] for r in c.registros] == ["cancelled", "success"]
    deploys = json.loads(c.na_main("docs/spec/deploy/history.json"))["deploys"]
    assert [d["sha"] for d in deploys] == [c.merges[0]["main"]]


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
    codigo, registro = c.merges[0]["main"], c.commits_do_bot[0]
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


def pr_atras_da_main(tmp_path: Path) -> Cenario:
    """A main andou depois do CI do PR, por outro PR em outro arquivo."""
    c = pr_de_codigo(tmp_path)
    repo = tmp_path / "repo"
    git(repo, "checkout", "-q", "main")
    escrever(repo, "hospital-reunioes/backend/app/outro.py", "OUTRO = 1\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "fix: outro PR que entrou antes")
    c.avancar_main(repo)
    return c


def test_pr_atras_da_main_entra_no_head_verde_sem_trazer_a_main_nem_ci_novo(
    tmp_path, monkeypatch, capsys
):
    """ADR 0064, decisão 2: o ruleset não exige a branch em dia com a base. O
    head com que o PR chegou, o do CI verde, é o que entra: nada de merge da
    main na branch, push ou CI de novo. O squash da API junta a main que andou."""
    fo = carregar_fechar_onda()
    c = pr_atras_da_main(tmp_path)
    main_antes = c.main_remota()
    preparar(fo, monkeypatch, c)

    assert rodar_main(fo, monkeypatch, c) == 0

    entrega = c.merges[0]
    assert entrega["pr"] == 7 and entrega["head"] == c.head_do_pr
    codigo = entrega["main"]
    assert git(c.remoto, "rev-parse", f"{codigo}^") == main_antes
    assert git(c.remoto, "show", f"{codigo}:hospital-reunioes/backend/app/outro.py") == "OUTRO = 1"
    assert git(c.remoto, "show", f"{codigo}:hospital-reunioes/backend/app/prazo.py") == "PRAZO = 15"
    [merge] = linhas_com(capsys.readouterr().out, "merge: PR #7")
    assert "main trazida" not in merge, merge


# O PR do lote entra no head que já estava verde (ADR 0064, decisão 2), e o
# registro vai pela Action (decisão 6b): o único head que o rabo empurra e cujo
# CI ele espera é o do PR `revert/<chave>`, depois de um rollback.

def revert_depois_do_rollback(tmp_path: Path) -> Cenario:
    c = pr_atras_da_main(tmp_path)
    c.imagens_no_coolify("uuid-backend", IMAGEM_ANTERIOR)
    c.health_ruim_em.add("0.10.1")
    return c


def test_ci_cancelado_sem_runner_e_repetido_e_o_pr_entra_quando_fica_verde(
    tmp_path, monkeypatch
):
    fo = carregar_fechar_onda()
    c = revert_depois_do_rollback(tmp_path)
    preparar(fo, monkeypatch, c)
    monkeypatch.setattr(fo, "CHECKS_POLL_S", 0)
    c.sem_runner = 2

    assert rodar_main(fo, monkeypatch, c) == fo.EXIT_ROLLBACK

    assert c.gh_chamadas.count(["run", "rerun", "555", "--failed"]) == 2
    assert [m["branch"] for m in c.merges] == ["feature", "revert/pr-7"]


def test_sem_runner_esgotado_no_revert_sai_com_4_e_aponta_o_incidente_nao_o_codigo(
    tmp_path, monkeypatch, capsys
):
    fo = carregar_fechar_onda()
    c = revert_depois_do_rollback(tmp_path)
    preparar(fo, monkeypatch, c)
    monkeypatch.setattr(fo, "CHECKS_POLL_S", 0)
    c.sem_runner = 99

    assert rodar_main(fo, monkeypatch, c) == fo.EXIT_HEALTH

    assert c.gh_chamadas.count(["run", "rerun", "555", "--failed"]) == 3
    assert [m["pr"] for m in c.merges] == [7]
    saida = capsys.readouterr().out
    assert "githubstatus.com" in saida and "CI vermelho" not in saida


def test_cancelamento_que_nao_e_falta_de_runner_continua_ci_vermelho_sem_rerun(
    tmp_path, monkeypatch, capsys
):
    fo = carregar_fechar_onda()
    c = revert_depois_do_rollback(tmp_path)
    preparar(fo, monkeypatch, c)
    monkeypatch.setattr(fo, "CHECKS_POLL_S", 0)
    c.sem_runner = 99
    c.anotacao_do_cancelamento = "The operation was canceled."

    assert rodar_main(fo, monkeypatch, c) == fo.EXIT_HEALTH

    assert ["run", "rerun", "555", "--failed"] not in c.gh_chamadas
    assert "CI vermelho" in capsys.readouterr().out


def test_ruleset_antigo_deixa_o_pr_atras_de_fora_e_a_rodada_seguinte_sai_na_mesma_versao(
    tmp_path, monkeypatch, capsys
):
    """Até o admin aplicar o ruleset novo (ADR 0064, decisão 2), o GitHub recusa
    a branch atrás da base: o PR fica de fora com a causa, na hora, sem a main
    empurrada na branch. Sem commit de versão, nada fica na branch para a
    rodada seguinte contar de novo: ela parte do mesmo state.json e a primeira
    não criou tag."""
    fo = carregar_fechar_onda()
    c = pr_atras_da_main(tmp_path)
    preparar(fo, monkeypatch, c)
    monkeypatch.setattr(fo, "CHECKS_POLL_S", 0)
    monkeypatch.setattr(fo, "CHECKS_TIMEOUT_S", 1)
    c.ruleset_antigo = True

    assert rodar_main(fo, monkeypatch, c) == fo.EXIT_MERGE

    assert c.merges == [] and c.tags == [] and c._tip("feature") == c.head_do_pr
    [fora] = linhas_com(capsys.readouterr().out, "de fora:")
    assert "PR #7" in fora and "not up to date with the base branch" in fora, fora
    c.ruleset_antigo = False  # o admin aplicou o .github/rulesets/main.json

    assert rodar_main(fo, monkeypatch, c) == 0

    assert c.merges[0]["head"] == c.head_do_pr
    assert c.tags == [("refs/tags/v0.10.1", c.merges[0]["main"])]
    app_version = [li for li in c.coolify() if " APP_VERSION " in li]
    assert app_version and all("--value 0.10.1 " in li for li in app_version), c.coolify()


# ------------------------------------------ onda PR a PR (#989, ADR 0064)

def onda_de_dois(tmp_path: Path) -> Cenario:
    """O PR #7 (issue #5) e o PR #8 (issue #6), em arquivos diferentes do backend."""
    c = pr_de_codigo(tmp_path)
    c.outro_pr(8, "fix(ouvidoria): limite de anexos por caso", 6,
               {"hospital-reunioes/backend/app/limite.py": "LIMITE = 3\n"})
    return c


def test_onda_mergeia_pr_a_pr_em_ordem_com_um_build_so(tmp_path, monkeypatch):
    """ADR 0064, decisão 3: cada PR entra pela API no próprio número, em ordem,
    como o avulso. O webhook do Coolify dispara um deploy por merge: o do squash
    intermediário é cancelado e só o do último roda."""
    fo = carregar_fechar_onda()
    c = onda_de_dois(tmp_path)
    preparar(fo, monkeypatch, c)

    assert rodar_onda(fo, monkeypatch, c, [7, 8]) == 0

    assert c.pushes_na_main() == []
    primeiro, segundo = c.merges
    assert (primeiro["pr"], primeiro["branch"]) == (7, "feature")
    assert (segundo["pr"], segundo["branch"]) == (8, "feature-8")
    # em ordem, um squash por PR no próprio número
    assert git(c.remoto, "rev-parse", f"{segundo['main']}^") == primeiro["main"]
    assert git(c.remoto, "log", "-1", "--format=%s", primeiro["main"]).endswith("(#7)")
    assert git(c.remoto, "log", "-1", "--format=%s", segundo["main"]).endswith("(#8)")
    assert git(c.remoto, "show", f"{segundo['main']}:hospital-reunioes/backend/app/prazo.py") == "PRAZO = 15"
    assert git(c.remoto, "show", f"{segundo['main']}:hospital-reunioes/backend/app/limite.py") == "LIMITE = 3"
    # os PRs do lote fecham como mergeados, sem `gh pr close`
    assert c.prs[7]["state"] == c.prs[8]["state"] == "MERGED"
    assert [a for a in c.gh_chamadas if a[:2] == ["pr", "close"]] == []
    # APP_VERSION nos dois apps antes do primeiro merge: a main remota ainda era a base
    assert c.coolify() == [f"app rollback images uuid-backend --format json | main={c.base}",
                           f"app env update uuid-backend APP_VERSION --value 0.10.1 | main={c.base}",
                           f"app env update uuid-frontend APP_VERSION --value 0.10.1 | main={c.base}"]
    # um deploy cancelado (o do squash do #7, além do commit do bot), um esperado (o do #8)
    assert c.cancelamentos == [primeiro["main"], c.commits_do_bot[0]]
    assert c.esperados == [segundo["main"]]
    assert c.tags == [("refs/tags/v0.10.1", segundo["main"])]


def test_segundo_pr_com_merge_recusado_fica_de_fora_e_o_primeiro_sobe_com_saida_2(
    tmp_path, monkeypatch, capsys
):
    """Só o PR que não mergeia fica de fora: o que entrou sobe inteiro (build,
    health e registro), sem cancelar o build dele, e a saída é 2."""
    fo = carregar_fechar_onda()
    c = onda_de_dois(tmp_path)
    preparar(fo, monkeypatch, c)
    mergear = c.mergear_pela_api

    def recusar_o_8(n, campos):
        if n == 8:
            raise RuntimeError("gh api -> 405: Pull Request is not mergeable")
        return mergear(n, campos)

    c.mergear_pela_api = recusar_o_8

    assert rodar_onda(fo, monkeypatch, c, [7, 8]) == fo.EXIT_MERGE

    [primeiro] = c.merges
    assert primeiro["pr"] == 7 and len(c.registros) == 1, c.merges
    assert c.main_remota() == c.commits_do_bot[0]
    assert c.prs[8]["state"] == "OPEN"
    # o build e o health do que entrou: o squash do #7 é o último, e o deploy dele roda
    assert c.esperados == [primeiro["main"]] and c.builds == ["backend"]
    assert c.healths == [("backend", "0.10.1")]
    assert c.cancelamentos == [c.commits_do_bot[0]]
    assert c.tags == [("refs/tags/v0.10.1", primeiro["main"])]
    assert c.semaforo == [("pegar", "onda-x"), ("soltar", "onda-x")]
    entrada = json.loads(c.na_main("docs/spec/deploy/history.json"))["deploys"][0]
    assert entrada["sha"] == primeiro["main"] and "#8" not in entrada["notes"], entrada
    saida = capsys.readouterr().out
    fora = [li for li in saida.splitlines() if li.startswith("de fora:")]
    assert len(fora) == 1 and "PR #8" in fora[0] and "405" in fora[0], fora
    fechou = saida.strip().splitlines()[-1]
    assert fechou.startswith("onda onda-x fechada sem #8") and "PRs #7 " in fechou, fechou


def test_falha_inesperada_do_gh_no_segundo_pr_fica_de_fora_e_o_primeiro_sobe(
    tmp_path, monkeypatch, capsys
):
    """Depois do primeiro squash, uma falha que não é conflito nem entrega
    recusada (um 502 do `gh` no polling do CI do 2º PR) não pode virar saída 3
    com o semáforo preso: o PR fica de fora com a causa e o que entrou segue
    para build, health e registro (revisão do PR #1013)."""
    fo = carregar_fechar_onda()
    c = onda_de_dois(tmp_path)
    preparar(fo, monkeypatch, c)
    gh_json = fo.gh_json

    def gh_502_no_8(args, cwd=None):
        if args[:3] == ["pr", "view", "8"] and c.prs[7]["state"] == "MERGED":
            raise RuntimeError("gh pr view 8 -> HTTP 502: Bad Gateway")
        return gh_json(args, cwd)

    monkeypatch.setattr(fo, "gh_json", gh_502_no_8)

    assert rodar_onda(fo, monkeypatch, c, [7, 8]) == fo.EXIT_MERGE

    [primeiro] = c.merges
    assert primeiro["pr"] == 7 and len(c.registros) == 1, c.merges
    assert c.prs[8]["state"] == "OPEN"
    assert c.esperados == [primeiro["main"]] and c.healths == [("backend", "0.10.1")]
    assert c.semaforo == [("pegar", "onda-x"), ("soltar", "onda-x")]
    saida = capsys.readouterr().out
    fora = [li for li in saida.splitlines() if li.startswith("de fora:")]
    assert len(fora) == 1 and "PR #8" in fora[0] and "502" in fora[0], fora
    assert "rollback" not in saida, saida


def test_history_da_onda_lista_os_prs_e_as_issues_do_lote(tmp_path, monkeypatch):
    fo = carregar_fechar_onda()
    c = onda_de_dois(tmp_path)
    preparar(fo, monkeypatch, c)

    assert rodar_onda(fo, monkeypatch, c, [7, 8]) == 0

    entrada = json.loads(c.na_main("docs/spec/deploy/history.json"))["deploys"][0]
    # o commit que foi para produção é o squash do último PR
    assert entrada["sha"] == c.merges[1]["main"] and entrada["app_version"] == "0.10.1"
    assert entrada["subject"].startswith("Onda onda-x: "), entrada["subject"]
    assert "Limite de anexos por caso" in entrada["subject"], entrada["subject"]
    # contrato do painel (`tools/workflow-dashboard/collect.py`, `_correlate`): cada
    # PR e cada issue do lote achados nas notas
    assert {int(n) for n in re.findall(r"PRs? #(\d+)", entrada["notes"])} == {7, 8}, entrada["notes"]
    assert {int(n) for n in re.findall(r"(?:[Ii]ssues? |Closes )#(\d+)", entrada["notes"])} == {5, 6}, entrada["notes"]
    state = json.loads(c.na_main("docs/spec/deploy/state.json"))
    assert state["last_run"]["sha"] == c.merges[1]["main"]


def test_dry_run_da_onda_lista_um_merge_por_pr_sem_branch_de_lote(tmp_path, monkeypatch, capsys):
    fo = carregar_fechar_onda()
    c = onda_de_dois(tmp_path)
    preparar(fo, monkeypatch, c)

    assert rodar_onda(fo, monkeypatch, c, [7, 8], "--dry-run") == 0

    saida = capsys.readouterr().out
    [faria] = linhas_com(saida, "faria:")
    assert re.findall(r"merge pela API do PR #(\d+)", faria) == ["7", "8"], faria
    assert "tag v0.10.1 no squash do ultimo" in faria and "um build" in faria, faria
    assert "registro pela Action pos-merge" in faria and "PR so de docs" not in faria, faria
    assert "onda/" not in saida and "entrega" not in saida.lower(), saida
    # nada sai da máquina
    assert c.main_remota() == c.base and c.coolify() == [] and c.semaforo == []
    assert [a for a in c.gh_chamadas if a[:3] in (["api", "-X", "POST"], ["api", "-X", "PUT"])] == []
    assert c._tip("feature-8") == c.prs[8]["headRefOid"]


def test_segundo_pr_em_conflito_com_o_primeiro_imprime_a_linha_que_chama_o_corretor(
    tmp_path, monkeypatch, capsys
):
    """O #8 mexe no mesmo arquivo que o #7: depois do squash do #7, a main não
    entra na branch do #8. A `/onda-enxuta` e o `/ship` distinguem o conflito
    pela linha `conflito no merge de #N em: <arquivos>`."""
    fo = carregar_fechar_onda()
    c = pr_de_codigo(tmp_path)
    c.outro_pr(8, "fix(ouvidoria): prazo de vinte dias", 6, {"hospital-reunioes/backend/app/prazo.py": "PRAZO = 20\n"})
    preparar(fo, monkeypatch, c)

    assert rodar_onda(fo, monkeypatch, c, [7, 8]) == fo.EXIT_MERGE

    assert [m["pr"] for m in c.merges] == [7] and len(c.registros) == 1, c.merges
    assert c.na_main("hospital-reunioes/backend/app/prazo.py") == "PRAZO = 15"
    # nada foi empurrado na branch do #8: o corretor rebaseia a partir dela
    assert c._tip("feature-8") == c.prs[8]["headRefOid"] and c.prs[8]["state"] == "OPEN"
    conflito = [li for li in capsys.readouterr().out.splitlines() if "conflito no merge de #8 em:" in li]
    assert len(conflito) == 1 and "hospital-reunioes/backend/app/prazo.py" in conflito[0], conflito


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


def test_esperar_build_ignora_o_deploy_cancelado_do_squash_intermediario(monkeypatch):
    """Os merges da onda saem segundos um depois do outro: o deploy do squash
    intermediário, já cancelado, cai na janela de horário do último. O rabo
    espera o do último, nunca o cancelado."""
    fo = carregar_fechar_onda()
    intermediario, ultimo = "a" * 40, "b" * 40
    agora = fo.datetime.now(fo.timezone.utc).isoformat()
    cancelado = {"deployment_uuid": "d-intermediario", "commit": intermediario, "status": "cancelled",
                 "created_at": agora}
    rodando = {"deployment_uuid": "d-ultimo", "commit": ultimo, "status": "in_progress", "created_at": agora}
    listas = iter([[cancelado], [rodando, cancelado]])
    pedidos = []

    def coolify_json(args, timeout=120):
        pedidos.append(args)
        if args[:3] == ["app", "deployments", "list"]:
            return next(listas)
        return {"deployment_uuid": args[2], "status": "finished"}

    monkeypatch.setattr(fo, "coolify_json", coolify_json)
    monkeypatch.setattr(fo, "BUILD_POLL_S", 0)
    monkeypatch.setattr(fo, "run", lambda cmd, **kw: pytest.fail(f"comando inesperado: {cmd}"))

    status, _ = fo.esperar_build(PROJECT["services"][0], fo.time.time(), ultimo, (intermediario,))

    assert status == "finished"
    assert pedidos[-1] == ["deploy", "get", "d-ultimo"], pedidos


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


def test_dry_run_de_app_mostra_a_versao_nova_sem_commit_de_bump(tmp_path, monkeypatch, capsys):
    """Issue #967: a versão nova vai para o APP_VERSION dos dois apps e para a
    tag do squash; nenhum commit de versão na branch, nenhum package.json."""
    fo = carregar_fechar_onda()
    c = pr_de_codigo(tmp_path)
    preparar(fo, monkeypatch, c)

    assert rodar_main(fo, monkeypatch, c, "--dry-run") == 0

    saida = capsys.readouterr().out
    plano = next(li for li in saida.splitlines() if li.startswith("plano:"))
    assert "v0.10.0 -> v0.10.1" in plano, plano
    faria = next(li for li in saida.splitlines() if li.startswith("faria:"))
    assert "APP_VERSION v0.10.1 no backend e no frontend" in faria, faria
    assert "tag v0.10.1" in faria, faria
    for proibido in ("chore(release)", "commit", "package.json"):
        assert proibido not in saida, (proibido, saida)
    assert c.coolify() == [] and c.tags == []


def test_tag_que_falha_nao_para_o_deploy_e_diz_como_criar_depois(tmp_path, monkeypatch, capsys):
    """A tag é conferência da próxima versão, não deploy: o merge já aconteceu,
    e o build e o health seguem."""
    fo = carregar_fechar_onda()
    c = pr_de_codigo(tmp_path)
    preparar(fo, monkeypatch, c)

    def criar_ref_fora_do_ar(campos):
        raise RuntimeError("gh api -> 502: Bad Gateway")

    c.criar_ref = criar_ref_fora_do_ar

    assert rodar_main(fo, monkeypatch, c) == 0

    assert c.builds == ["backend"] and len(c.merges) == 1 and len(c.commits_do_bot) == 1
    saida = capsys.readouterr().out
    assert "tag v0.10.1 falhou" in saida, saida
    assert f"ref=refs/tags/v0.10.1 -f sha={c.merges[0]['main']}" in saida, saida


@pytest.mark.parametrize("tags, de, para", [
    ([], "0.20.4", "0.20.5"),
    (["v0.20.1", "v0.9.30"], "0.20.4", "0.20.5"),
    (["v0.20.4", "v0.20.6"], "0.20.6", "0.20.7"),
], ids=["sem-tag", "tag-atras-do-state", "tag-a-frente-do-state"])
def test_versao_de_partida_vem_do_state_json_conferida_pela_tag(
    tmp_path, monkeypatch, capsys, tags, de, para
):
    """O package.json fica congelado (0.10.0 no cenário) e não conta. Tag à
    frente do state.json é um rabo que etiquetou e não registrou: vale a tag,
    para a versão não se repetir."""
    fo = carregar_fechar_onda()
    c = pr_de_codigo(tmp_path, versao_em_producao="0.20.4")
    for tag in tags:
        git(c.remoto, "tag", tag, c.base)
    preparar(fo, monkeypatch, c)

    assert rodar_main(fo, monkeypatch, c, "--dry-run") == 0

    saida = capsys.readouterr().out
    plano = next(li for li in saida.splitlines() if li.startswith("plano:"))
    assert f"v{de} -> v{para}" in plano, plano
    assert ("maior tag" in saida) == (de != "0.20.4"), saida


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
    # nenhum PR aberto pelo rabo: nem de registro, nem um que embrulhe a onda
    abertos = [a for a in c.gh_chamadas if a[:4] == ["api", "-X", "POST", "repos/{owner}/{repo}/pulls"]]
    assert abertos == [], abertos
    assert c.merges[0]["pr"] == 7
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
    assert c.coolify() == [f"app rollback images uuid-frontend --format json | main={c.base}",
                           f"app env update uuid-backend APP_VERSION --value 0.11.0 | main={c.base}",
                           f"app env update uuid-frontend APP_VERSION --value 0.11.0 | main={c.base}"]
    assert c.tags == [("refs/tags/v0.11.0", c.merges[0]["main"])]
    assert c.builds == ["frontend"]
    assert [m["pr"] for m in c.merges] == [7] and len(c.commits_do_bot) == 1
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


def falhar_na_limpeza(fo, monkeypatch, c: Cenario) -> None:
    def limpar(raiz, entregues=None):
        raise RuntimeError("git worktree remove -> 128: permission denied")

    monkeypatch.setattr(fo, "limpar_worktrees_de_agente", limpar)


@pytest.mark.parametrize("falha", [falhar_no_cancelamento, falhar_na_limpeza],
                         ids=["coolify-timeout", "limpeza"])
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


# ---------------------------------------------- rollback automático (#968)

IMAGEM_ANTERIOR = "cab8930958d1f89545d688418f37745936cc576f"
IMAGEM_MAIS_VELHA = "9428a0263e43d81cbbe32891fee5a1af9f5879a2"
# a imagem de um merge ruim que um rollback anterior tirou do ar: segue na
# lista do Coolify, mais nova que a do ar
IMAGEM_REVERTIDA = "be11c0de5a1d0b9a2e3f4c5d6e7f8a9b0c1d2e3f"


def coolify_sem_leitura_de_deploys(c: Cenario) -> list[str]:
    return [li for li in c.coolify() if not li.startswith("app deployments list")]


def test_health_ruim_volta_a_imagem_anterior_e_o_app_version_antigo_e_sai_com_rollback_feito(
    tmp_path, monkeypatch, capsys
):
    """O backend da v0.10.1 responde 500: o rabo volta o app do lote à imagem
    que estava no ar ANTES do merge (lida antes dele, não a mais nova da lista:
    a de um rollback anterior é mais nova e tem defeito), devolve o APP_VERSION
    v0.10.0 aos dois apps ANTES de subir a imagem (o backend o lê no start do
    container), confere o health de novo, agora na versão antiga, e solta o
    semáforo."""
    fo = carregar_fechar_onda()
    c = pr_de_codigo(tmp_path)
    c.imagens_no_coolify("uuid-backend", IMAGEM_ANTERIOR, revertidas=(IMAGEM_REVERTIDA,))
    c.health_ruim_em.add("0.10.1")
    preparar(fo, monkeypatch, c)

    assert rodar_main(fo, monkeypatch, c) == fo.EXIT_ROLLBACK

    merge = c.merges[0]["main"]
    assert coolify_sem_leitura_de_deploys(c) == [
        f"app rollback images uuid-backend --format json | main={c.base}",
        f"app env update uuid-backend APP_VERSION --value 0.10.1 | main={c.base}",
        f"app env update uuid-frontend APP_VERSION --value 0.10.1 | main={c.base}",
        f"app env update uuid-backend APP_VERSION --value 0.10.0 | main={merge}",
        f"app env update uuid-frontend APP_VERSION --value 0.10.0 | main={merge}",
        f"app rollback run uuid-backend --commit {IMAGEM_ANTERIOR} | main={merge}",
    ]
    # o frontend não estava no lote: a imagem dele não muda
    assert c.rollbacks == ["backend"]
    assert c.healths == [("backend", "0.10.1"), ("backend", "0.10.0")]
    assert c.semaforo == [("pegar", "pr-7"), ("soltar", "pr-7")]
    # sem registro: o próprio rabo mergeia o revert antes de soltar a trava (issue #999)
    assert [m["branch"] for m in c.merges] == ["feature", "revert/pr-7"], c.merges
    saida = capsys.readouterr().out
    health = next(li for li in saida.splitlines() if li.startswith("health:"))
    assert "http 500" in health and 'relation \\"prazos\\" does not exist' in health, health
    rollback = next(li for li in saida.splitlines() if li.startswith("rollback:"))
    for trecho in (merge[:8], "PR #7", "issue #5", "v0.10.0", "semaforo solto"):
        assert trecho in rollback, (trecho, rollback)
    assert "Semaforo preso" not in saida, saida


def sem_imagem_anterior(c: Cenario) -> None:
    c.imagens_no_coolify("uuid-backend", None)


def coolify_recusa_o_rollback(c: Cenario) -> None:
    c.imagens_no_coolify("uuid-backend", IMAGEM_ANTERIOR)
    c.recusar_rollback()


def health_segue_ruim_na_versao_antiga(c: Cenario) -> None:
    c.imagens_no_coolify("uuid-backend", IMAGEM_ANTERIOR)
    c.health_ruim_em.add("0.10.0")


@pytest.mark.parametrize("falha", [sem_imagem_anterior, coolify_recusa_o_rollback,
                                   health_segue_ruim_na_versao_antiga],
                         ids=["sem-imagem", "coolify-recusa", "health-segue-ruim"])
def test_rollback_que_falha_sai_com_4_e_o_semaforo_fica_preso(tmp_path, monkeypatch, capsys, falha):
    fo = carregar_fechar_onda()
    c = pr_de_codigo(tmp_path)
    c.health_ruim_em.add("0.10.1")
    falha(c)
    preparar(fo, monkeypatch, c)

    assert rodar_main(fo, monkeypatch, c) == fo.EXIT_HEALTH == 4

    # presa e marcada parada: o rabo seguinte sai com 8 na hora (issue #999)
    assert c.semaforo == [("pegar", "pr-7"), ("parar", "pr-7")]
    assert [m["pr"] for m in c.merges] == [7]
    saida = capsys.readouterr().out
    rollback = next(li for li in saida.splitlines() if li.startswith("rollback:"))
    assert "falhou" in rollback and "Semaforo preso na chave pr-7" in rollback, rollback
    assert "/deploy rollback" in rollback, rollback


def test_sem_imagem_anterior_o_rabo_nao_mexe_no_app_version_nem_sobe_imagem(tmp_path, monkeypatch):
    """Sem para onde voltar, o APP_VERSION novo continua batendo com a imagem no ar."""
    fo = carregar_fechar_onda()
    c = pr_de_codigo(tmp_path)
    c.health_ruim_em.add("0.10.1")
    sem_imagem_anterior(c)
    preparar(fo, monkeypatch, c)

    assert rodar_main(fo, monkeypatch, c) == fo.EXIT_HEALTH

    assert not [li for li in c.coolify() if "--value 0.10.0" in li or "rollback run" in li], c.coolify()
    assert c.rollbacks == []


def imagem(tag: str, criada: str, no_ar: bool = False) -> dict:
    return {"created_at": f"2026-10-06 {criada} +0000 UTC", "is_current": no_ar, "tag": tag}


@pytest.mark.parametrize("dado, esperada", [
    # depois de um rollback, a imagem ruim que ele tirou do ar segue na lista,
    # mais nova que a do ar: vale a `current`, nunca a mais nova
    ({"current": IMAGEM_ANTERIOR,
      "images": [imagem(IMAGEM_REVERTIDA, "04:26:37"), imagem(IMAGEM_ANTERIOR, "02:10:00", True),
                 imagem(IMAGEM_MAIS_VELHA, "00:37:08")]}, IMAGEM_ANTERIOR),
    ({"current": None, "images": []}, None),
    (None, None),  # o Coolify não respondeu
], ids=["revertida-mais-nova", "sem-imagem", "coolify-fora"])
def test_imagem_no_ar_e_a_current_do_coolify_e_nao_a_mais_nova(monkeypatch, dado, esperada):
    fo = carregar_fechar_onda()
    pedidos = []

    def coolify_json(args, timeout=120):
        pedidos.append(args)
        return dado

    monkeypatch.setattr(fo, "coolify_json", coolify_json)

    assert fo.imagem_no_ar("uuid-backend") == esperada
    assert pedidos == [["app", "rollback", "images", "uuid-backend"]]


def test_esperar_rollback_acompanha_o_deploy_novo_e_nao_o_antigo_do_mesmo_commit(monkeypatch):
    """O deploy que pôs a imagem anterior no ar da primeira vez tem o mesmo
    commit do rollback: casar por commit acharia o antigo, já `finished`."""
    fo = carregar_fechar_onda()
    antigo = {"deployment_uuid": "d-antigo", "commit": IMAGEM_ANTERIOR, "status": "finished"}
    novo = {"deployment_uuid": "d-rollback", "commit": IMAGEM_ANTERIOR, "status": "in_progress"}
    listas = iter([[antigo], [novo, antigo]])
    pedidos = []

    def coolify_json(args, timeout=120):
        pedidos.append(args)
        if args[:3] == ["app", "deployments", "list"]:
            return next(listas)
        return {"deployment_uuid": args[2], "status": "finished"}

    monkeypatch.setattr(fo, "coolify_json", coolify_json)
    monkeypatch.setattr(fo, "BUILD_POLL_S", 0)
    monkeypatch.setattr(fo, "run", lambda cmd, **kw: pytest.fail(f"comando inesperado: {cmd}"))

    assert fo.esperar_rollback(PROJECT["services"][0], {"d-antigo"}) == "finished"
    assert pedidos[-1] == ["deploy", "get", "d-rollback"], pedidos


def test_esperar_rollback_sem_deploy_novo_desiste_sem_forcar_build(monkeypatch):
    """`coolify deploy uuid` rebuildaria a main, que ainda tem o defeito."""
    fo = carregar_fechar_onda()
    chamadas = []
    monkeypatch.setattr(fo, "coolify_json", lambda args, timeout=120: [{"deployment_uuid": "d-antigo"}])
    monkeypatch.setattr(fo, "BUILD_WAIT_WEBHOOK_S", 0)
    monkeypatch.setattr(fo, "BUILD_POLL_S", 0)
    monkeypatch.setattr(fo, "run", lambda cmd, **kw: chamadas.append(cmd))

    assert fo.esperar_rollback(PROJECT["services"][0], {"d-antigo"}) == "sem-deploy"
    assert chamadas == []


def test_health_ruim_guarda_o_que_o_health_respondeu(monkeypatch):
    """O corpo da resposta vai na linha do rabo e, dali, no comentário da issue reaberta."""
    fo = carregar_fechar_onda()

    def urlopen(req, timeout):
        raise fo.urllib.error.HTTPError(req.full_url, 500, "Internal Server Error", {},
                                        io.BytesIO(b'{"detail":\n  "db fora do ar"}'))

    monkeypatch.setattr(fo.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(fo.time, "sleep", lambda s: None)

    h = fo.checar_health(PROJECT["services"][0], "0.10.1")

    assert h["ok"] is False and h["status"] == 500
    assert h["corpo"] == '{"detail": "db fora do ar"}'
    assert fo.linha_de_health(h) == 'http 500 {"detail": "db fora do ar"}'


# --------------------------- migration com recibo: o rabo espera o número (#969)

SQL_COM_RECIBO = (
    "create table triagem (id int);\n"
    "alter table triagem enable row level security;\n"
    "insert into migracoes_aplicadas (numero) values (112) on conflict (numero) do nothing;\n"
)
SHA_COM_RECIBO = hashlib.sha256(SQL_COM_RECIBO.encode("utf-8")).hexdigest()
HORA = 60 * 60


class Relogio:
    """O relógio do rabo: `sleep` só anda o ponteiro, e 24 h passam num instante."""

    def __init__(self):
        import time as _time

        self.agora = _time.time()
        self.inicio = self.agora

    def time(self) -> float:
        return self.agora

    def sleep(self, s: float) -> None:
        self.agora += s


class _Resposta:
    def __init__(self, corpo: str, status: int = 200):
        self.status = status
        self._corpo = corpo.encode("utf-8")

    def read(self) -> bytes:
        return self._corpo

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class HealthDoBackend:
    """O `/api/health` de produção visto pelo rabo. `coladas` diz, em segundos
    desde o início, quando o Pedro colou cada migration no Studio; antes de
    todas, o banco tem só a 111. `sem_campo`: o backend no ar é anterior ao
    #969 e não informa o número."""

    def __init__(self, relogio: Relogio, coladas: dict[int, float] | None = None, sem_campo: bool = False):
        self.relogio = relogio
        self.coladas = coladas or {}
        self.sem_campo = sem_campo
        self.leituras: list[tuple[float, str]] = []

    def __call__(self, req, timeout):
        self.leituras.append((self.relogio.agora, req.full_url))
        corpo = {"status": "healthy", "db": "healthy", "app": "Hospital", "version": "0.10.0"}
        if not self.sem_campo:
            passou = self.relogio.agora - self.relogio.inicio
            corpo["migracao"] = max([111] + [n for n, quando in self.coladas.items() if passou >= quando])
        return _Resposta(json.dumps(corpo, separators=(",", ":")))


def pr_com_migration_com_recibo(tmp_path: Path, *outras: str) -> Cenario:
    arquivos = {f"{MIGRATIONS}/112_triagem.sql": SQL_COM_RECIBO}
    arquivos.update({f"{MIGRATIONS}/{nome}": SQL_COM_RECIBO.replace("(112)", f"({nome[:3]})")
                     for nome in outras})
    shas = [hashlib.sha256(sql.encode("utf-8")).hexdigest() for sql in arquivos.values()]
    arquivos["hospital-reunioes/backend/app/prazo.py"] = "PRAZO = 15\n"
    return Cenario(tmp_path, 8, "feat(ouvidoria): triagem", 6, arquivos,
                   corpo="## Migrations (conferência por hash)\n\n" + "\n".join(shas) + "\n")


def preparar_com_relogio(fo, monkeypatch, c: Cenario, health: HealthDoBackend) -> list[float]:
    """`preparar` com o relógio controlado e o health falso do backend; devolve
    os instantes em que o rabo pegou o semáforo."""
    preparar(fo, monkeypatch, c)
    monkeypatch.setattr(fo, "time", health.relogio)
    monkeypatch.setattr(fo.urllib.request, "urlopen", health)
    pegou_em: list[float] = []
    semaforo_do_preparar = fo.semaforo

    def semaforo(raiz, acao, chave, descricao=""):
        if acao == "pegar":
            pegou_em.append(health.relogio.agora)
        return semaforo_do_preparar(raiz, acao, chave, descricao)

    monkeypatch.setattr(fo, "semaforo", semaforo)
    return pegou_em


def linhas_com(saida: str, prefixo: str) -> list[str]:
    return [li for li in saida.splitlines() if li.startswith(prefixo)]


def test_rabo_espera_a_migration_aparecer_no_health_e_so_entao_pega_o_semaforo_e_mergeia(
    tmp_path, monkeypatch, capsys
):
    fo = carregar_fechar_onda()
    c = pr_com_migration_com_recibo(tmp_path)
    relogio = Relogio()
    health = HealthDoBackend(relogio, coladas={112: 3 * HORA})
    pegou_em = preparar_com_relogio(fo, monkeypatch, c, health)

    assert rodar_main(fo, monkeypatch, c) == 0

    # o merge saiu, como em qualquer PR de app
    assert [m["pr"] for m in c.merges] == [8]  # o registro vai pela Action, sem PR
    assert c.semaforo == [("pegar", "pr-8"), ("soltar", "pr-8")]
    # mas só depois de o /api/health do backend devolver a 112: o semáforo
    # (e com ele o APP_VERSION e o merge) não ficou preso durante a espera
    assert {url for _, url in health.leituras} == {"https://exemplo.invalid/api/health"}
    assert relogio.inicio + 3 * HORA <= pegou_em[0] <= relogio.inicio + 3 * HORA + fo.MIGRACAO_POLL_S
    saida = capsys.readouterr().out
    # o humano recebe o caminho clicável do arquivo, com o SQL do head do PR
    [cole] = linhas_com(saida, "migration: cole no Studio")
    caminho = re.search(r"(\S+112_triagem\.sql):1\b", cole)
    assert caminho, cole
    assert Path(caminho.group(1)).read_text(encoding="utf-8") == SQL_COM_RECIBO
    assert SHA_COM_RECIBO[:12] in cole and "3 linhas" in cole, cole
    assert linhas_com(saida, "migration: 112 aplicada"), saida
    assert "vencida" not in saida, saida


def test_lote_com_duas_migrations_espera_a_maior(tmp_path, monkeypatch, capsys):
    fo = carregar_fechar_onda()
    c = pr_com_migration_com_recibo(tmp_path, "113_triagem_anexos.sql")
    relogio = Relogio()
    health = HealthDoBackend(relogio, coladas={112: 1 * HORA, 113: 5 * HORA})
    pegou_em = preparar_com_relogio(fo, monkeypatch, c, health)

    assert rodar_main(fo, monkeypatch, c) == 0

    assert relogio.inicio + 5 * HORA <= pegou_em[0] <= relogio.inicio + 5 * HORA + fo.MIGRACAO_POLL_S
    saida = capsys.readouterr().out
    assert len(linhas_com(saida, "migration: cole no Studio")) == 2, saida
    assert linhas_com(saida, "migration: 113 aplicada"), saida


def test_migration_que_nao_aparece_em_24_h_vence_com_codigo_proprio_sem_merge(
    tmp_path, monkeypatch, capsys
):
    fo = carregar_fechar_onda()
    c = pr_com_migration_com_recibo(tmp_path)
    relogio = Relogio()
    health = HealthDoBackend(relogio)  # o Pedro nunca cola a 112
    preparar_com_relogio(fo, monkeypatch, c, health)

    assert rodar_main(fo, monkeypatch, c) == fo.EXIT_MIGRACAO == 7

    # vence no teto, nem antes nem um dia depois
    esperou = relogio.agora - relogio.inicio
    assert 24 * HORA <= esperou <= 24 * HORA + fo.MIGRACAO_POLL_S, esperou
    # nada entrou na main, nada no Coolify, semáforo livre e o PR devolvido aberto
    assert c.merges == [] and c.main_remota() == c.base
    assert c.coolify() == []
    assert c.semaforo == []
    assert c.prs[8]["state"] == "OPEN"
    saida = capsys.readouterr().out
    [vencida] = linhas_com(saida, "migration: vencida")
    for trecho in ("112", "24 h", "111", "#8", "Nada entrou na main"):
        assert trecho in vencida, (trecho, vencida)
    assert TRAVESSAO not in saida and MEIA_RISCA not in saida, saida


def test_push_no_pr_da_onda_durante_a_espera_nao_entra_na_main(tmp_path, monkeypatch, capsys):
    """Revisão de segurança do PR #996: na espera, alguém empurra outro SQL no PR
    do lote. O SQL colado (do head conferido) deixa de ser o que entraria na
    main, e o rabo para sem merge, como o avulso já parava."""
    fo = carregar_fechar_onda()
    c = pr_com_migration_com_recibo(tmp_path)
    relogio = Relogio()
    health = HealthDoBackend(relogio, coladas={112: 3 * HORA})
    preparar_com_relogio(fo, monkeypatch, c, health)
    repo = tmp_path / "repo"
    ler_health = health.__call__

    def health_com_push_na_primeira_hora(req, timeout):
        if relogio.agora - relogio.inicio >= HORA and c._tip("feature") == c.head_do_pr:
            git(repo, "checkout", "-q", "feature")
            escrever(repo, f"{MIGRATIONS}/112_triagem.sql", SQL_COM_RECIBO + "drop policy x on y;\n")
            git(repo, "commit", "-q", "-am", "outro SQL")
            git(repo, "push", "-q", str(c.remoto), "feature", "feature:refs/pull/8/head")
        return ler_health(req, timeout)

    monkeypatch.setattr(fo.urllib.request, "urlopen", health_com_push_na_primeira_hora)

    assert rodar_main(fo, monkeypatch, c, "--sessao", "onda-x") == fo.EXIT_MERGE

    assert c._tip("feature") != c.head_do_pr  # o push aconteceu
    assert c.merges == [] and c.main_remota() == c.base and c.coolify() == []
    assert c.semaforo == [("pegar", "onda-x"), ("soltar", "onda-x")]
    saida = capsys.readouterr().out
    assert "#8 andou depois das pre-condicoes" in saida, saida


def test_health_de_backend_anterior_ao_recibo_nao_prende_o_rabo(tmp_path, monkeypatch, capsys):
    """O deploy do próprio #969: o backend no ar ainda não informa o número, e a
    114 foi colada no Studio pelo fluxo antigo. O rabo avisa e segue sem esperar."""
    fo = carregar_fechar_onda()
    c = pr_com_migration_com_recibo(tmp_path)
    health = HealthDoBackend(Relogio(), sem_campo=True)
    preparar_com_relogio(fo, monkeypatch, c, health)

    assert rodar_main(fo, monkeypatch, c) == 0

    assert len(health.leituras) == 1
    assert [m["pr"] for m in c.merges] == [8]  # o registro vai pela Action, sem PR
    [aviso] = linhas_com(capsys.readouterr().out, "migration: o /api/health")
    assert "112" in aviso and "nao informa" in aviso, aviso


def test_pr_sem_migration_nao_consulta_o_health_antes_do_merge(tmp_path, monkeypatch):
    fo = carregar_fechar_onda()
    c = pr_de_codigo(tmp_path)
    health = HealthDoBackend(Relogio())
    preparar_com_relogio(fo, monkeypatch, c, health)

    assert rodar_main(fo, monkeypatch, c) == 0

    assert health.leituras == []


def test_dry_run_com_migration_diz_que_esperaria_sem_consultar_o_health(tmp_path, monkeypatch, capsys):
    fo = carregar_fechar_onda()
    c = pr_com_migration_com_recibo(tmp_path)
    health = HealthDoBackend(Relogio())
    preparar_com_relogio(fo, monkeypatch, c, health)

    assert rodar_main(fo, monkeypatch, c, "--dry-run") == 0

    assert health.leituras == []
    [faria] = linhas_com(capsys.readouterr().out, "faria:")
    assert "esperar a 112 no /api/health (teto 24 h)" in faria, faria


CORPO_DEGRADADO = b'{"status":"degraded","db":"degraded","app":"a","version":"1","migracao":113}'


@pytest.mark.parametrize("resposta, esperado", [
    (_Resposta('{"status":"healthy","db":"healthy","app":"a","version":"1","migracao":114}'), 114),
    ("503", 113),  # banco degradado: o 503 ainda traz o número
    (_Resposta('{"status":"healthy","db":"healthy","app":"a","version":"1","migracao":null}'), None),
    (_Resposta('{"status":"healthy","db":"healthy","app":"a","version":"1"}'), "sem-campo"),
    # resposta que não é o health (proxy, rota errada): não vale como backend antigo
    (_Resposta('{"detail":"Not Found"}', 404), None),
    (_Resposta("<html>Bad Gateway</html>", 502), None),
    ("fora-do-ar", None),
], ids=["numero", "503-com-numero", "tabela-vazia", "backend-antigo", "outra-rota", "nao-json", "fora-do-ar"])
def test_migracao_no_health_le_o_numero_do_corpo(monkeypatch, resposta, esperado):
    fo = carregar_fechar_onda()

    def urlopen(req, timeout):
        if resposta == "fora-do-ar":
            raise fo.urllib.error.URLError("connection refused")
        if resposta == "503":
            raise fo.urllib.error.HTTPError(req.full_url, 503, "Service Unavailable", {},
                                            io.BytesIO(CORPO_DEGRADADO))
        return resposta

    monkeypatch.setattr(fo.urllib.request, "urlopen", urlopen)

    lido = fo.migracao_no_health("https://exemplo.invalid/api/health")

    assert lido == (fo.SEM_CAMPO if esperado == "sem-campo" else esperado)


# ------------------------------------- imagem do backend no GHCR (#1001)

def test_backend_em_modo_imagem_sobe_a_imagem_do_head_retagueada_para_o_squash_sem_build(
    tmp_path, monkeypatch, capsys
):
    """ADR 0064, decisão 6c: o CI publicou a imagem do head do PR no GHCR. Depois
    do merge o rabo dispara o workflow que dá a ela a tag do squash (retag, a
    origem é o head) e só então aponta o Coolify para essa tag e dispara o
    deploy, que só puxa e reinicia: nenhum build do webhook é esperado."""
    fo = carregar_fechar_onda()
    c = pr_de_codigo(tmp_path, project=PROJECT_IMAGEM)
    preparar(fo, monkeypatch, c)

    assert rodar_main(fo, monkeypatch, c) == 0

    squash = c.merges[0]["main"]
    [publicacao] = c.publicacoes
    assert (publicacao["workflow"], publicacao["ref"]) == ("imagem-backend.yml", "main")
    # a origem vai pelo digest que o CI do head guardou: a tag `:<head>` é mutável
    assert (publicacao["sha"], publicacao["origens"]) == (squash, f"{c.head_do_pr}@{digest_de(c.head_do_pr)}")
    # antes da imagem publicada, o Coolify só recebeu o APP_VERSION
    assert publicacao["coolify_antes"] == 2
    assert c.coolify_sem_leituras() == [
        f"app env update uuid-backend APP_VERSION --value 0.10.1 | main={c.base}",
        f"app env update uuid-frontend APP_VERSION --value 0.10.1 | main={c.base}",
        f"app update uuid-backend --docker-tag {squash} | main={squash}",
        f"deploy uuid uuid-backend | main={squash}",
    ]
    assert c.builds == [] and c.deploys_novos == ["backend"]
    assert c.healths == [("backend", "0.10.1")]
    entrada = json.loads(c.na_main("docs/spec/deploy/history.json"))["deploys"][0]
    assert entrada["sha"] == squash and entrada["result"] == "healthy"
    # o state.json guarda o digest do que foi para o ar: é o que o próximo rollback confere
    back = next(s for s in json.loads(c.na_main("docs/spec/deploy/state.json"))["services"] if s["id"] == "backend")
    assert (back["last_deploy_sha"], back["last_deploy_digest"]) == (squash, digest_de(c.head_do_pr))
    # o Coolify confirmou o modo imagem: nenhum aviso de troca pendente
    assert linhas_com(capsys.readouterr().out, "aviso:") == []


def test_onda_em_modo_imagem_so_retagueia_head_com_a_mesma_pasta_do_backend_do_squash(
    tmp_path, monkeypatch
):
    """O #8, só de docs, entra depois do #7 no head com que chegou, sem a main
    (ADR 0064, decisão 2): a imagem do head dele não tem o backend do #7. Só o
    head do #7 tem o backend do squash final, e é a única origem que o workflow
    pode retaguear."""
    fo = carregar_fechar_onda()
    c = pr_de_codigo(tmp_path, project=PROJECT_IMAGEM)
    c.outro_pr(8, "docs(ouvidoria): prazo explicado", 6, {"docs/ouvidoria/prazo.md": "Quinze dias.\n"})
    preparar(fo, monkeypatch, c)

    assert rodar_onda(fo, monkeypatch, c, [7, 8]) == 0

    primeiro, segundo = c.merges
    assert [(p["sha"], p["origens"]) for p in c.publicacoes] == [
        (segundo["main"], f"{primeiro['head']}@{digest_de(primeiro['head'])}")]
    assert segundo["head"] not in c.publicacoes[0]["origens"]
    assert c.coolify_sem_leituras()[-2:] == [
        f"app update uuid-backend --docker-tag {segundo['main']} | main={segundo['main']}",
        f"deploy uuid uuid-backend | main={segundo['main']}",
    ]
    assert c.builds == []


def test_frontend_no_lote_segue_o_build_do_webhook_e_o_backend_vai_por_imagem(tmp_path, monkeypatch):
    """Só o backend está em modo imagem (o frontend é a #1002): o frontend do
    lote continua esperando o build que o webhook disparou."""
    fo = carregar_fechar_onda()
    c = Cenario(tmp_path, 7, "fix: prazo e rotulo", 5,
                {"hospital-reunioes/backend/app/prazo.py": "PRAZO = 15\n",
                 "hospital-reunioes/frontend/src/rotulo.ts": "export const R = 1\n"},
                project=PROJECT_IMAGEM)
    preparar(fo, monkeypatch, c)

    assert rodar_main(fo, monkeypatch, c) == 0

    squash = c.merges[0]["main"]
    assert c.builds == ["frontend"] and c.esperados == [squash]
    assert c.deploys_novos == ["backend"] and [p["sha"] for p in c.publicacoes] == [squash]


def test_imagem_que_nao_sai_do_workflow_para_com_3_sem_trocar_a_tag_no_coolify(
    tmp_path, monkeypatch, capsys
):
    """O run do workflow terminou vermelho: o Coolify nunca recebe a tag de uma
    imagem que não existe, e o rabo sai como um build que falhou."""
    fo = carregar_fechar_onda()
    c = pr_de_codigo(tmp_path, project=PROJECT_IMAGEM)
    c.publicacao_falha = True
    preparar(fo, monkeypatch, c)

    assert rodar_main(fo, monkeypatch, c) == fo.EXIT_BUILD

    assert [li for li in c.coolify_sem_leituras() if "--docker-tag" in li or li.startswith("deploy ")] == []
    assert c.deploys_novos == [] and c.healths == []
    assert c.semaforo == [("pegar", "pr-7"), ("parar", "pr-7")]
    [build] = linhas_com(capsys.readouterr().out, "build:")
    assert "backend" in build and "failure" in build and "Semaforo preso na chave pr-7" in build, build


def test_app_em_modo_imagem_fica_fora_do_cancelamento_do_webhook(monkeypatch):
    """Sem webhook, nenhum deploy do commit do registro aparece no backend em
    modo imagem: esperar por ele gastaria a janela inteira a cada squash."""
    fo = carregar_fechar_onda()
    sha = "a" * 40
    pedidos = []

    def coolify_json(args, timeout=120):
        pedidos.append(args[3])
        return [{"deployment_uuid": "d-registro", "commit": sha, "status": "queued"}]

    monkeypatch.setattr(fo, "coolify_json", coolify_json)
    monkeypatch.setattr(fo, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, "", ""))
    servicos = {s["id"]: s for s in PROJECT_IMAGEM["services"]}

    assert fo.cancelar_build_do_registro(servicos, sha) == ["frontend"]
    assert pedidos == ["uuid-frontend"]


def test_rollback_em_modo_imagem_volta_a_tag_do_ultimo_deploy_sem_build(tmp_path, monkeypatch):
    """O health da v0.10.1 falhou: o backend volta à tag que estava no ar, o sha
    do último deploy dele no state.json (o CLI do Coolify não devolve a tag
    configurada), pelo mesmo caminho do deploy: troca a tag e puxa. Nada de
    `rollback run --commit`, que é de imagem construída do git."""
    fo = carregar_fechar_onda()
    c = pr_de_codigo(tmp_path, project=PROJECT_IMAGEM, sha_no_ar=IMAGEM_ANTERIOR,
                     digest_no_ar=DIGEST_ANTERIOR)
    c.health_ruim_em.add("0.10.1")
    preparar(fo, monkeypatch, c)

    assert rodar_main(fo, monkeypatch, c) == fo.EXIT_ROLLBACK

    squash = c.merges[0]["main"]
    assert c.coolify_sem_leituras() == [
        f"app env update uuid-backend APP_VERSION --value 0.10.1 | main={c.base}",
        f"app env update uuid-frontend APP_VERSION --value 0.10.1 | main={c.base}",
        f"app update uuid-backend --docker-tag {squash} | main={squash}",
        f"deploy uuid uuid-backend | main={squash}",
        f"app env update uuid-backend APP_VERSION --value 0.10.0 | main={squash}",
        f"app env update uuid-frontend APP_VERSION --value 0.10.0 | main={squash}",
        f"app update uuid-backend --docker-tag {IMAGEM_ANTERIOR} | main={squash}",
        f"deploy uuid uuid-backend | main={squash}",
    ]
    assert c.rollbacks == ["backend"]
    assert c.healths == [("backend", "0.10.1"), ("backend", "0.10.0")]
    assert c.semaforo == [("pegar", "pr-7"), ("soltar", "pr-7")]


def test_backend_que_o_coolify_ainda_constroi_do_git_segue_pelo_webhook_com_aviso(
    tmp_path, monkeypatch, capsys
):
    """O project.json já diz modo imagem, mas a troca no Coolify é pela tela e
    ainda não foi feita: trocar a tag de um app do git dispararia um segundo
    build, e o rollback por tag reconstruiria a main com o defeito. O rabo
    confere o build pack no Coolify antes do primeiro merge e segue pelo
    webhook, avisando."""
    fo = carregar_fechar_onda()
    c = pr_de_codigo(tmp_path, project=PROJECT_IMAGEM)
    c.build_pack_no_coolify("uuid-backend", "dockerfile")
    c.imagens_no_coolify("uuid-backend", IMAGEM_ANTERIOR)
    preparar(fo, monkeypatch, c)

    assert rodar_main(fo, monkeypatch, c) == 0

    assert c.publicacoes == [] and c.deploys_novos == []
    assert c.builds == ["backend"] and c.esperados == [c.merges[0]["main"]]
    assert not [li for li in c.coolify() if "--docker-tag" in li], c.coolify()
    [aviso] = linhas_com(capsys.readouterr().out, "aviso:")
    assert "backend" in aviso and "Coolify" in aviso and "webhook" in aviso, aviso


@pytest.mark.parametrize("resposta", [
    "",  # o CLI nao respondeu nada (timeout, saida vazia)
    "Coolify CLI v1.2\nnao e json",
    json.dumps({"uuid": "uuid-backend", "status": "running:healthy"}),  # sem o campo
], ids=["vazio", "nao-json", "sem-build-pack"])
def test_leitura_do_build_pack_que_falha_para_antes_do_primeiro_merge(
    tmp_path, monkeypatch, capsys, resposta
):
    """Revisão do PR #1016: sem saber o build pack, o rabo não pode cair no
    webhook. Depois da troca na tela o app não tem webhook, o deploy forçado
    repuxaria a tag velha, o health passaria pelo APP_VERSION do runtime e o
    registro gravaria healthy com um sha que nem existe no GHCR. Só um build
    pack lido e diferente de dockerimage rebaixa; leitura que falha para antes
    do primeiro merge, sem tocar no Coolify, e solta o semáforo."""
    fo = carregar_fechar_onda()
    c = pr_de_codigo(tmp_path, project=PROJECT_IMAGEM)
    (c.dir_coolify / "app-uuid-backend.json").write_text(resposta, encoding="utf-8")
    preparar(fo, monkeypatch, c)

    assert rodar_main(fo, monkeypatch, c) == fo.EXIT_MERGE

    assert c.merges == [] and c.pushes_na_main() == []
    assert c.coolify_sem_leituras() == [] and c.publicacoes == [] and c.builds == []
    assert c.semaforo == [("pegar", "pr-7"), ("soltar", "pr-7")]
    saida = capsys.readouterr().out
    assert linhas_com(saida, "aviso:") == []
    [erro] = linhas_com(saida, "erro:")
    assert "backend" in erro and "build pack" in erro and "nada entrou" in erro, erro


def test_build_pack_dentro_de_data_vale_como_modo_imagem(tmp_path, monkeypatch, capsys):
    """O CLI pode embrulhar a resposta em `data`, como no `deploy get`: o build
    pack lido ali é o real."""
    fo = carregar_fechar_onda()
    c = pr_de_codigo(tmp_path, project=PROJECT_IMAGEM)
    (c.dir_coolify / "app-uuid-backend.json").write_text(
        json.dumps({"data": {"uuid": "uuid-backend", "build_pack": "dockerimage",
                             "docker_registry_image_name": "ghcr.io/dono/repo-backend"}}), encoding="utf-8")
    preparar(fo, monkeypatch, c)

    assert rodar_main(fo, monkeypatch, c) == 0

    assert c.builds == [] and c.deploys_novos == ["backend"]
    assert linhas_com(capsys.readouterr().out, "aviso:") == []


def test_dry_run_em_modo_imagem_diz_que_o_backend_vai_por_imagem_sem_disparar_nada(
    tmp_path, monkeypatch, capsys
):
    fo = carregar_fechar_onda()
    c = pr_de_codigo(tmp_path, project=PROJECT_IMAGEM)
    preparar(fo, monkeypatch, c)

    assert rodar_main(fo, monkeypatch, c, "--dry-run") == 0

    [faria] = linhas_com(capsys.readouterr().out, "faria:")
    assert "backend: imagem do GHCR com a tag do squash, sem build" in faria, faria
    assert c.publicacoes == [] and c.coolify() == [] and c.semaforo == []


def test_rollback_em_modo_imagem_sem_deploy_anterior_no_state_sai_com_4(tmp_path, monkeypatch):
    fo = carregar_fechar_onda()
    c = pr_de_codigo(tmp_path, project=PROJECT_IMAGEM)
    c.health_ruim_em.add("0.10.1")
    preparar(fo, monkeypatch, c)

    assert rodar_main(fo, monkeypatch, c) == fo.EXIT_HEALTH

    assert [li for li in c.coolify_sem_leituras() if "--value 0.10.0" in li or "rollback" in li] == []
    assert c.rollbacks == [] and c.semaforo == [("pegar", "pr-7"), ("parar", "pr-7")]


# ------------------------- digest de ponta a ponta (revisão do PR #1016)

DIGEST_ANTERIOR = digest_de("imagem que estava no ar")


def test_tag_do_squash_sobrescrita_depois_do_workflow_nao_vai_para_o_ar(tmp_path, monkeypatch, capsys):
    """Um run com `packages: write` de outra branch troca a tag `:<squash>` depois
    que o workflow a publicou: no GHCR ela já não aponta para o digest que o run
    guardou, e o Coolify não recebe a tag."""
    fo = carregar_fechar_onda()
    c = pr_de_codigo(tmp_path, project=PROJECT_IMAGEM)
    c.tag_sobrescrita = True
    preparar(fo, monkeypatch, c)

    assert rodar_main(fo, monkeypatch, c) == fo.EXIT_BUILD

    assert [li for li in c.coolify_sem_leituras() if "--docker-tag" in li or li.startswith("deploy ")] == []
    assert c.deploys_novos == [] and c.healths == []
    [build] = linhas_com(capsys.readouterr().out, "build:")
    assert DIGEST_FORJADO in build and digest_de(c.head_do_pr) in build, build


def test_head_cujo_ci_nao_guardou_digest_nao_vira_origem_e_o_workflow_constroi(tmp_path, monkeypatch):
    """Sem o digest do CI, a tag `:<head>` não prova nada: o head não vai como
    origem, o workflow constrói do squash, e o digest do build é o que vai para
    o ar e para o state.json."""
    fo = carregar_fechar_onda()
    c = pr_de_codigo(tmp_path, project=PROJECT_IMAGEM)
    c.ci_sem_digest.add(c.head_do_pr)
    preparar(fo, monkeypatch, c)

    assert rodar_main(fo, monkeypatch, c) == 0

    squash = c.merges[0]["main"]
    assert [(p["sha"], p["origens"]) for p in c.publicacoes] == [(squash, "")]
    assert c.deploys_novos == ["backend"]
    back = next(s for s in json.loads(c.na_main("docs/spec/deploy/state.json"))["services"] if s["id"] == "backend")
    assert back["last_deploy_digest"] == digest_de(f"build-{squash}")


def test_rollback_em_modo_imagem_com_a_tag_anterior_sobrescrita_nao_mexe_em_nada(tmp_path, monkeypatch, capsys):
    """A tag do último deploy (pública no state.json) foi sobrescrita no GHCR: o
    rollback a poria no ar. Ele confere o digest antes de tocar em qualquer app,
    nem o APP_VERSION volta, e sai com 4 para o humano."""
    fo = carregar_fechar_onda()
    c = pr_de_codigo(tmp_path, project=PROJECT_IMAGEM, sha_no_ar=IMAGEM_ANTERIOR,
                     digest_no_ar=DIGEST_ANTERIOR)
    c.ghcr[IMAGEM_ANTERIOR] = DIGEST_FORJADO
    c.health_ruim_em.add("0.10.1")
    preparar(fo, monkeypatch, c)

    assert rodar_main(fo, monkeypatch, c) == fo.EXIT_HEALTH

    squash = c.merges[0]["main"]
    assert c.coolify_sem_leituras()[2:] == [
        f"app update uuid-backend --docker-tag {squash} | main={squash}",
        f"deploy uuid uuid-backend | main={squash}",
    ]
    assert c.rollbacks == [] and c.semaforo == [("pegar", "pr-7"), ("parar", "pr-7")]
    [rollback] = linhas_com(capsys.readouterr().out, "rollback:")
    assert DIGEST_FORJADO in rollback and DIGEST_ANTERIOR in rollback, rollback


def test_rollback_do_primeiro_deploy_por_imagem_le_o_digest_do_run_que_publicou_a_tag(tmp_path, monkeypatch):
    """O state.json ainda não tem digest (a imagem no ar veio do passo 2, o run
    manual do workflow): o rabo o lê do artefato daquele run, na main, e volta."""
    fo = carregar_fechar_onda()
    c = pr_de_codigo(tmp_path, project=PROJECT_IMAGEM, sha_no_ar=IMAGEM_ANTERIOR)
    c.imagem_publicada_antes(IMAGEM_ANTERIOR, DIGEST_ANTERIOR)
    c.health_ruim_em.add("0.10.1")
    preparar(fo, monkeypatch, c)

    assert rodar_main(fo, monkeypatch, c) == fo.EXIT_ROLLBACK

    squash = c.merges[0]["main"]
    assert c.coolify_sem_leituras()[-2:] == [
        f"app update uuid-backend --docker-tag {IMAGEM_ANTERIOR} | main={squash}",
        f"deploy uuid uuid-backend | main={squash}",
    ]
    assert c.rollbacks == ["backend"]


@pytest.mark.parametrize("nome", ["ghcr.io/dono-sem-fig/repo-backend", None], ids=["outro-namespace", "sem-nome"])
def test_coolify_que_puxa_de_outra_imagem_para_antes_do_primeiro_merge(tmp_path, monkeypatch, capsys, nome):
    """Revisão do PR #1016: no passo 3, `pedrorezende` sem o `fig` faria o Coolify
    puxar de outro namespace, onde as tags pedidas são previsíveis. O nome lido
    no `coolify app get` tem que ser o `build.image` do project.json; diferente,
    ou não lido, nada entra na main."""
    fo = carregar_fechar_onda()
    c = pr_de_codigo(tmp_path, project=PROJECT_IMAGEM)
    c.build_pack_no_coolify("uuid-backend", "dockerimage", nome)
    preparar(fo, monkeypatch, c)

    assert rodar_main(fo, monkeypatch, c) == fo.EXIT_MERGE

    assert c.merges == [] and c.coolify_sem_leituras() == [] and c.publicacoes == []
    assert c.semaforo == [("pegar", "pr-7"), ("soltar", "pr-7")]
    [erro] = linhas_com(capsys.readouterr().out, "erro:")
    assert "ghcr.io/dono/repo-backend" in erro and "nada entrou" in erro, erro


class RespostaFalsa(io.BytesIO):
    def __init__(self, corpo: bytes = b"", headers: dict | None = None):
        super().__init__(corpo)
        self.headers = headers or {}


def test_digest_no_ghcr_le_o_digest_da_tag_sem_login_e_none_quando_nao_le(monkeypatch):
    """O `imagetools inspect` sem docker: token anônimo de pull e HEAD no
    manifesto, pedindo também o índice multi-arquitetura (o digest que o
    build-push-action devolve é o dele)."""
    fo = carregar_fechar_onda()
    pedidos = []

    def urlopen(pedido, timeout=None):
        pedidos.append(pedido)
        if isinstance(pedido, str):
            return RespostaFalsa(json.dumps({"token": "anonimo"}).encode())
        return RespostaFalsa(headers={"Docker-Content-Digest": DIGEST_ANTERIOR})

    monkeypatch.setattr(fo.urllib.request, "urlopen", urlopen)

    assert fo.digest_no_ghcr("ghcr.io/dono/repo-backend", IMAGEM_ANTERIOR) == DIGEST_ANTERIOR
    token, head = pedidos
    assert token == "https://ghcr.io/token?scope=repository:dono/repo-backend:pull"
    assert (head.get_method(), head.full_url) == (
        "HEAD", f"https://ghcr.io/v2/dono/repo-backend/manifests/{IMAGEM_ANTERIOR}")
    assert head.get_header("Authorization") == "Bearer anonimo"
    assert "application/vnd.oci.image.index.v1+json" in head.get_header("Accept")

    def recusa(pedido, timeout=None):
        raise fo.urllib.error.HTTPError("https://ghcr.io", 401, "unauthorized", {}, None)

    monkeypatch.setattr(fo.urllib.request, "urlopen", recusa)
    assert fo.digest_no_ghcr("ghcr.io/dono/repo-backend", IMAGEM_ANTERIOR) is None
