"""A Action pós-merge: snapshot e draft do Manual direto na `main` (issue #940).

ADR 0062, decisão 10: o rabo deixou de rodar o `snapshot.py` e o
`tirar_draft_manual.py` (#939), e quem roda os dois é um workflow no push da
`main`, que commita como `github-actions[bot]` pelo bypass do ruleset. Estes
testes amarram o contrato do workflow (evento, branch, autor, `[skip ci]`, o
filtro que impede a Action de acordar com o próprio commit) e rodam os passos
de shell dele de verdade, num repo git de brinquedo.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parent.parent
WORKFLOW = RAIZ / ".github" / "workflows" / "pos-merge.yml"


def workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def gatilhos() -> dict:
    # O PyYAML segue o YAML 1.1, em que `on` é booleano: a chave vira True.
    w = workflow()
    return w["on"] if "on" in w else w[True]


def test_dispara_no_push_da_main_e_nunca_em_pull_request():
    """O commit vai direto na `main` pelo bypass; em PR a Action escreveria na
    branch de outra pessoa, ou commitaria snapshot de código que não subiu."""
    on = gatilhos()
    assert on["push"]["branches"] == ["main"]
    assert "pull_request" not in on
    assert "pull_request_target" not in on
    assert workflow()["permissions"] == {"contents": "write"}


def casa(padrao: str, caminho: str) -> bool:
    """O glob do filtro de caminhos do GitHub: `**` atravessa pastas, `*` não."""
    regex = ""
    i = 0
    while i < len(padrao):
        if padrao.startswith("**", i):
            regex += ".*"
            i += 2
        elif padrao[i] == "*":
            regex += "[^/]*"
            i += 1
        else:
            regex += re.escape(padrao[i])
            i += 1
    return re.fullmatch(regex, caminho) is not None


def acorda(mudados: list[str]) -> bool:
    """Com `paths-ignore`, o push só não acorda a Action se todo caminho cair
    num padrão ignorado."""
    ignorados = gatilhos()["push"]["paths-ignore"]
    return any(not any(casa(p, c) for p in ignorados) for c in mudados)


def test_push_que_so_toca_snapshot_e_paginas_do_manual_nao_acorda_a_action():
    """É o que a própria Action escreve. Push do `GITHUB_TOKEN` já não dispara
    workflow; o filtro cobre quem rodar o snapshot à mão e empurrar."""
    assert not acorda(["docs/spec/snapshots/ROTAS.md", "docs/spec/snapshots/SCHEMA.md"])
    assert not acorda(["docs/ARQUITETURA.md"])
    assert not acorda(["docs/manual/src/content/docs/ouvidoria/manifestacoes/registrar.mdx"])
    assert not acorda(["docs/spec/snapshots/ROTAS.md", "docs/ARQUITETURA.md",
                       "docs/manual/src/content/docs/index.mdx"])


def test_merge_do_registro_e_de_codigo_acordam_a_action():
    """O gatilho que importa é o PR de registro do rabo: com o `history.json`
    na `main`, o draft sabe o que está em produção."""
    assert acorda(["docs/spec/deploy/history.json", "docs/spec/deploy/state.json"])
    assert acorda(["hospital-reunioes/backend/app/routers/atas.py"])
    assert acorda(["docs/spec/snapshots/ROTAS.md", "hospital-reunioes/supabase/migrations/115_x.sql"])
    assert acorda(["docs/manual/video/ouvidoria/registrar/index.html"])


# --------------------------------------------------- os passos de shell, rodados

def passo(trecho: str) -> dict:
    """O passo do job cujo nome contém o trecho."""
    passos = workflow()["jobs"]["pos-merge"]["steps"]
    achados = [p for p in passos if trecho in p.get("name", "")]
    assert len(achados) == 1, [p.get("name") for p in passos]
    return achados[0]


# Sem identidade nem config global: quem diz o autor do commit é o passo.
ENV_GIT = {
    **{k: v for k, v in os.environ.items() if not k.startswith(("GIT_AUTHOR_", "GIT_COMMITTER_"))},
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
}


def rodar(trecho: str, cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    """Roda o `run:` do passo como o GitHub Actions roda: `bash -e {0}`."""
    script = cwd.parent / "passo.sh"
    script.write_text(passo(trecho)["run"], encoding="utf-8")
    return subprocess.run(["bash", "-e", str(script)], cwd=cwd, env={**ENV_GIT, **(env or {})},
                          capture_output=True, text=True)


TIRAR_DRAFT_FALSO = """\
import os, sys
from pathlib import Path
Path("chamadas.txt").open("a").write(" ".join(sys.argv[1:]) + "\\n")
sys.exit(int(os.environ.get("SAIDA_DO_DRAFT", "0")))
"""


def arvore_do_draft(tmp_path: Path, prds: list[int]) -> Path:
    raiz = tmp_path / "repo"
    (raiz / "docs" / "spec" / "deploy").mkdir(parents=True)
    (raiz / "tools").mkdir()
    deploys = [{"app_version": "0.2.0", "prds": prds}, {"app_version": "0.1.0", "prds": [700]}]
    (raiz / "docs" / "spec" / "deploy" / "history.json").write_text(
        json.dumps({"schema_version": 1, "deploys": deploys}), encoding="utf-8")
    (raiz / "tools" / "tirar_draft_manual.py").write_text(TIRAR_DRAFT_FALSO, encoding="utf-8")
    return raiz


def chamadas(raiz: Path) -> list[str]:
    arq = raiz / "chamadas.txt"
    return arq.read_text(encoding="utf-8").splitlines() if arq.exists() else []


def test_draft_sai_para_os_prds_do_ultimo_deploy(tmp_path):
    raiz = arvore_do_draft(tmp_path, [963, 646])
    proc = rodar("Tirar do draft", raiz)
    assert proc.returncode == 0, proc.stderr
    assert chamadas(raiz) == ["--prd 963 --prd 646"]


def test_ultimo_deploy_sem_prd_nao_chama_o_tirar_draft(tmp_path):
    """PR avulso registra `prds: []`. Sem `--prd` o argparse sai com 2, e o
    passo não pode confundir isso com o bloqueio do MP4."""
    raiz = arvore_do_draft(tmp_path, [])
    proc = rodar("Tirar do draft", raiz)
    assert proc.returncode == 0, proc.stderr
    assert chamadas(raiz) == []


def test_bloqueio_do_mp4_avisa_e_nao_derruba_a_action(tmp_path):
    """Saída 2: o tirar-draft não escreveu nada (o MP4 do Vídeo de tarefa não
    vem no clone, issue #951). A página fica em draft e o snapshot segue."""
    raiz = arvore_do_draft(tmp_path, [963])
    proc = rodar("Tirar do draft", raiz, {"SAIDA_DO_DRAFT": "2"})
    assert proc.returncode == 0, proc.stderr
    assert "::warning::" in proc.stdout
    assert chamadas(raiz) == ["--prd 963"]


def test_pasta_errada_do_manual_derruba_a_action(tmp_path):
    raiz = arvore_do_draft(tmp_path, [963])
    proc = rodar("Tirar do draft", raiz, {"SAIDA_DO_DRAFT": "1"})
    assert proc.returncode == 1


SNAPSHOT_FALSO = """\
import sys
from pathlib import Path
Path("args.txt").write_text(" ".join(sys.argv[1:]))
"""


def test_snapshot_roda_sem_commitar_sozinho(tmp_path):
    """Sem `--no-commit` o `snapshot.py` commita por conta própria, com outra
    mensagem e sem `[skip ci]`; quem commita aqui é o passo do bot."""
    raiz = tmp_path / "repo"
    scripts = raiz / ".claude" / "skills" / "snapshot" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "snapshot.py").write_text(SNAPSHOT_FALSO, encoding="utf-8")
    proc = rodar("Snapshot", raiz)
    assert proc.returncode == 0, proc.stderr
    assert (raiz / "args.txt").read_text(encoding="utf-8").split() == ["--root", ".", "--no-commit"]


def test_backend_montado_com_o_mesmo_ambiente_do_ci():
    """O snapshot lê as rotas do app montado (`introspect_routes.py`, pelo
    `.venv` do backend). Sem o venv, ou sem as variáveis que o Settings exige,
    ele cai no parser AST e rebaixa o ROTAS.md (o modo parcial do macOS)."""
    ci = yaml.safe_load((RAIZ / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
    assert workflow()["jobs"]["pos-merge"]["env"] == ci["jobs"]["backend"]["env"]
    venv = passo("backend")
    assert venv["working-directory"] == "hospital-reunioes/backend"
    assert "uv sync --frozen" in venv["run"]


# O que a Action escreve, um caminho de cada filtro.
ESCRITOS = [
    "docs/spec/snapshots/ROTAS.md",
    "docs/ARQUITETURA.md",
    "docs/manual/src/content/docs/ouvidoria/index.mdx",
]


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=alguem", "-c", "user.email=alguem@example.com", *args],
        cwd=cwd, env=ENV_GIT, capture_output=True, text=True, check=True,
    ).stdout.strip()


def escrever(raiz: Path, caminho: str, texto: str) -> None:
    arq = raiz / caminho
    arq.parent.mkdir(parents=True, exist_ok=True)
    arq.write_text(texto, encoding="utf-8")


def main_com_runner(tmp_path: Path) -> tuple[Path, Path, Path]:
    """A `main` (repo bare), um clone de quem mergeia PR e o clone do runner."""
    origem = tmp_path / "origem.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origem))
    outro = tmp_path / "outro"
    git(tmp_path, "clone", "-q", str(origem), str(outro))
    for caminho in [*ESCRITOS, "hospital-reunioes/backend/uv.lock"]:
        escrever(outro, caminho, "antes\n")
    git(outro, "add", "-A")
    git(outro, "commit", "-q", "-m", "base")
    git(outro, "push", "-q", "origin", "HEAD:main")
    runner = tmp_path / "repo"
    git(tmp_path, "clone", "-q", "-b", "main", str(origem), str(runner))
    return origem, outro, runner


def test_commit_do_bot_com_skip_ci_so_do_que_a_action_escreve(tmp_path):
    origem, _, runner = main_com_runner(tmp_path)
    escrever(runner, "docs/spec/snapshots/ROTAS.md", "rota nova\n")
    escrever(runner, "docs/manual/src/content/docs/ouvidoria/index.mdx", "draft: false\n")
    escrever(runner, "hospital-reunioes/backend/uv.lock", "mexido pelo ambiente\n")
    escrever(runner, "lixo-do-runner.txt", "fora do git\n")

    proc = rodar("Commitar", runner)

    assert proc.returncode == 0, proc.stderr
    autor, email, assunto = git(origem, "log", "-1", "--format=%an|%ae|%s", "main").split("|")
    assert autor == "github-actions[bot]"
    assert email == "41898282+github-actions[bot]@users.noreply.github.com"
    assert "[skip ci]" in assunto
    arquivos = git(origem, "show", "--name-only", "--format=", "main").splitlines()
    assert sorted(arquivos) == ["docs/manual/src/content/docs/ouvidoria/index.mdx",
                                "docs/spec/snapshots/ROTAS.md"]
    assert not acorda(arquivos), "o commit do bot acordaria a própria Action"


def test_sem_diff_nao_commita(tmp_path):
    origem, _, runner = main_com_runner(tmp_path)
    antes = git(origem, "rev-parse", "main")
    escrever(runner, "hospital-reunioes/backend/uv.lock", "mexido pelo ambiente\n")

    proc = rodar("Commitar", runner)

    assert proc.returncode == 0, proc.stderr
    assert git(origem, "rev-parse", "main") == antes


def test_merge_que_entra_durante_a_action_nao_derruba_o_push(tmp_path):
    """Entre o checkout e o push outro PR pode entrar na `main`: sem rebase o
    push seria recusado (non_fast_forward no ruleset)."""
    origem, outro, runner = main_com_runner(tmp_path)
    escrever(outro, "hospital-reunioes/backend/app/novo.py", "x = 1\n")
    git(outro, "add", "-A")
    git(outro, "commit", "-q", "-m", "PR que entrou no meio")
    git(outro, "push", "-q", "origin", "HEAD:main")
    do_pr = git(outro, "rev-parse", "HEAD")
    escrever(runner, "docs/ARQUITETURA.md", "bloco AUTO novo\n")

    proc = rodar("Commitar", runner)

    assert proc.returncode == 0, proc.stderr
    assert git(origem, "rev-parse", "main~1") == do_pr
    assert git(origem, "log", "-1", "--format=%an", "main") == "github-actions[bot]"


def test_um_run_por_vez_e_o_draft_nao_se_perde_com_o_snapshot_vermelho():
    """Runs na fila partem da ponta da `main` (o commit do run anterior), não
    do commit do evento. O draft vem antes do backend e o commit roda mesmo
    com o snapshot vermelho: o próximo registro troca os PRDs do último
    deploy, e o draft que não entrou agora não entraria mais."""
    w = workflow()
    assert w["concurrency"]["cancel-in-progress"] is False
    passos = w["jobs"]["pos-merge"]["steps"]
    assert passos[0]["uses"].startswith("actions/checkout@") and passos[0]["with"]["ref"] == "main"
    ordem = [p.get("name") for p in passos]
    assert (ordem.index(passo("Tirar do draft")["name"])
            < ordem.index(passo("backend")["name"])
            < ordem.index(passo("Snapshot")["name"])
            < ordem.index(passo("Commitar")["name"]))
    assert passo("Commitar")["if"] == "${{ !cancelled() }}"


def test_estes_testes_rodam_quando_so_o_workflow_muda():
    """Os testes de `tools/` rodam no `manual.yml`, que só acorda pelos caminhos
    dele: PR que mexesse só no YAML entraria sem este contrato rodar."""
    manual = yaml.safe_load((RAIZ / ".github" / "workflows" / "manual.yml").read_text(encoding="utf-8"))
    on = manual["on"] if "on" in manual else manual[True]
    for evento in ("push", "pull_request"):
        assert ".github/workflows/pos-merge.yml" in on[evento]["paths"], evento
