"""A imagem do backend construída no CI e publicada no GHCR (issue #1001, ADR 0064 decisão 6c).

Três pontas que só se encontram em produção: o `ci.yml` publica a imagem com a
tag do sha do head do PR, o `imagem-backend.yml` dá a ela a tag do squash (o
rabo o dispara e acha o run pelo sha no título) e o `project.json` diz ao rabo
que o backend está em modo imagem, qual imagem e qual workflow. Um nome de
imagem diferente numa delas, ou um run-name sem o sha, só apareceria no
primeiro deploy. Estes testes leem os YAML e o JSON como dado e rodam o script
do retag com um `docker` falso.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml

RAIZ = Path(__file__).resolve().parent.parent
WORKFLOWS = RAIZ / ".github" / "workflows"
CI = WORKFLOWS / "ci.yml"
MANUAL = WORKFLOWS / "manual.yml"
PROJECT = RAIZ / "docs" / "spec" / "deploy" / "project.json"
SKILL_DEPLOY = RAIZ / ".claude" / "skills" / "deploy"

SHA = "a" * 40
HEAD_SEM_IMAGEM = "b" * 40
HEAD_COM_IMAGEM = "c" * 40


def servico(sid: str) -> dict:
    return next(s for s in json.loads(PROJECT.read_text(encoding="utf-8"))["services"] if s["id"] == sid)


def backend() -> dict:
    return servico("backend")


def workflow(caminho: Path) -> dict:
    dado = yaml.safe_load(caminho.read_text(encoding="utf-8"))
    dado["on"] = dado.pop(True, dado.get("on"))  # o YAML 1.1 lê a chave `on` como True
    return dado


def publicador() -> dict:
    return workflow(WORKFLOWS / backend()["build"]["publish_workflow"])


def passo(passos: list[dict], nome: str) -> dict:
    achados = [p for p in passos if p.get("name") == nome]
    assert len(achados) == 1, (nome, [p.get("name") for p in passos])
    return achados[0]


def job_build() -> dict:
    return workflow(CI)["jobs"]["build"]


# ------------------------------------------------------------- project.json

def test_backend_esta_em_modo_imagem_no_project_json_e_o_frontend_segue_no_git():
    build = backend()["build"]
    assert build["build_pack"] == "dockerimage"
    assert build["image"] == "ghcr.io/pedrorezendefig/hospital-reunioes-backend"
    assert (WORKFLOWS / build["publish_workflow"]).exists()
    # a pasta que o rabo compara entre head e squash é o contexto do build no CI
    contexto = passo(job_build()["steps"], "Build backend image")["with"]["context"]
    assert build["base_directory"].strip("/") == contexto
    assert servico("frontend")["build"]["build_pack"] == "dockerfile"  # a #1002


# ------------------------------------------------------------------- ci.yml

def test_ci_publica_a_imagem_do_backend_com_o_sha_do_head_em_todo_pr_do_repositorio():
    job = job_build()
    imagem = backend()["build"]["image"]
    assert job["name"] == "Docker Build (sanity)"  # check exigido pelo ruleset
    assert job["permissions"] == {"contents": "read", "packages": "write"}
    assert workflow(CI)["permissions"] == {"contents": "read"}, "packages: write só no job que publica"
    assert job["env"]["IMAGEM_BACKEND"] == imagem
    publica = job["env"]["PUBLICA"]
    assert "github.event_name == 'pull_request'" in publica
    assert "github.event.pull_request.head.repo.full_name == github.repository" in publica, \
        "PR de fork não tem token que escreva no GHCR"
    # a tag é o sha do head, e o código construído é o do head (não o merge com a main)
    head = "${{ github.event.pull_request.head.sha || github.sha }}"
    assert passo(job["steps"], "Checkout do head")["with"]["ref"] == head
    login = passo(job["steps"], "Login no GHCR")
    assert login["with"]["registry"] == "ghcr.io"
    assert login["with"]["password"] == "${{ secrets.GITHUB_TOKEN }}"
    back = passo(job["steps"], "Build backend image")["with"]
    assert back["push"] == "${{ env.PUBLICA == 'true' }}"
    assert back["tags"] == "${{ env.IMAGEM_BACKEND }}:" + head
    assert back["cache-from"] == "type=registry,ref=${{ env.IMAGEM_BACKEND }}:buildcache"
    assert "type=registry,ref={0}:buildcache,mode=max" in back["cache-to"]
    assert "env.PUBLICA == 'true'" in back["cache-to"]


def test_ci_nao_publica_a_imagem_do_frontend_construida_com_valores_falsos():
    front = passo(job_build()["steps"], "Build frontend image")["with"]
    assert front["push"] is False
    assert "NEXT_PUBLIC_SUPABASE_ANON_KEY=dummy-anon-key-for-ci" in front["build-args"]


# ------------------------------------------------------ imagem-backend.yml

def test_workflow_de_imagem_e_o_contrato_que_o_rabo_dispara():
    wf = publicador()
    entradas = wf["on"]["workflow_dispatch"]["inputs"]
    assert entradas["sha"]["required"] is True
    assert entradas["origens"]["required"] is False
    # o rabo acha o run do disparo pelo sha no título
    assert "${{ inputs.sha }}" in wf["run-name"]
    assert wf["permissions"] == {"contents": "read", "packages": "write"}
    [job] = wf["jobs"].values()
    assert job["env"]["IMAGEM_BACKEND"] == backend()["build"]["image"]
    # entrada vai por env, nunca interpolada no shell (injeção de script)
    for p in job["steps"]:
        assert "${{ inputs." not in str(p.get("run", "")), p.get("name")


def test_build_de_reserva_constroi_o_squash_e_publica_sha_e_latest():
    [job] = publicador()["jobs"].values()
    checkout = passo(job["steps"], "Checkout do squash")
    assert checkout["with"]["ref"] == "${{ inputs.sha }}"
    assert checkout["if"] == "steps.retag.outputs.feito != 'true'"
    build = passo(job["steps"], "Build do squash (nenhum head serviu)")
    assert build["if"] == "steps.retag.outputs.feito != 'true'"
    assert build["with"]["context"] == backend()["build"]["base_directory"].strip("/")
    assert build["with"]["push"] is True
    assert build["with"]["tags"].strip().splitlines() == ["${{ env.IMAGEM_BACKEND }}:${{ inputs.sha }}",
                                             "${{ env.IMAGEM_BACKEND }}:latest"]


def rodar_retag(tmp_path: Path, sha: str, origens: str, existentes: set[str]) -> tuple[int, list[str], str]:
    """Roda o `run` do passo de retag com um `docker` falso que anota cada
    chamada e só acha no GHCR as tags de `existentes`."""
    [job] = publicador()["jobs"].values()
    script = passo(job["steps"], "Retag da imagem de um head (sem build)")["run"]
    imagem = backend()["build"]["image"]
    bin_falso = tmp_path / "bin"
    bin_falso.mkdir()
    log = tmp_path / "docker.log"
    docker = bin_falso / "docker"
    docker.write_text(
        "#!/bin/sh\n"
        f'echo "$*" >> {log}\n'
        'if [ "$1 $2 $3" = "buildx imagetools inspect" ]; then\n'
        '  case " $EXISTENTES " in *" $4 "*) exit 0 ;; esac\n'
        "  exit 1\n"
        "fi\n"
        "exit 0\n",
        encoding="utf-8",
    )
    docker.chmod(0o755)
    saida = tmp_path / "github_output"
    saida.write_text("", encoding="utf-8")
    env = {**os.environ, "PATH": f"{bin_falso}{os.pathsep}{os.environ['PATH']}",
           "IMAGEM_BACKEND": imagem, "SHA": sha, "ORIGENS": origens, "GITHUB_OUTPUT": str(saida),
           "EXISTENTES": " ".join(f"{imagem}:{t}" for t in existentes)}
    proc = subprocess.run(["bash", "-e", "-c", script], env=env, capture_output=True, text=True)
    chamadas = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    return proc.returncode, chamadas, saida.read_text(encoding="utf-8")


def test_retag_usa_a_primeira_origem_que_existe_no_ghcr_e_da_a_ela_o_sha_e_latest(tmp_path):
    imagem = backend()["build"]["image"]

    codigo, chamadas, saida = rodar_retag(tmp_path, SHA, f"{HEAD_SEM_IMAGEM} {HEAD_COM_IMAGEM}",
                                          {HEAD_COM_IMAGEM})

    assert codigo == 0
    assert chamadas[-1] == (f"buildx imagetools create -t {imagem}:{SHA} -t {imagem}:latest "
                            f"{imagem}:{HEAD_COM_IMAGEM}")
    assert [c for c in chamadas if "create" in c] == [chamadas[-1]]
    assert "feito=true" in saida.splitlines()


@pytest.mark.parametrize("origens", ["", HEAD_SEM_IMAGEM], ids=["sem-origem", "origem-sem-imagem"])
def test_sem_origem_no_ghcr_o_retag_cede_a_vez_ao_build(tmp_path, origens):
    codigo, chamadas, saida = rodar_retag(tmp_path, SHA, origens, set())

    assert codigo == 0
    assert [c for c in chamadas if "create" in c] == []
    assert "feito=false" in saida.splitlines()


@pytest.mark.parametrize("sha, origens", [("main", ""), (SHA, "x; rm -rf /"), (SHA[:12], "")],
                         ids=["ref-de-branch", "origem-que-nao-e-sha", "sha-curto"])
def test_retag_recusa_entrada_que_nao_e_sha_completo(tmp_path, sha, origens):
    codigo, chamadas, _ = rodar_retag(tmp_path, sha, origens, {"main"})

    assert codigo != 0
    assert chamadas == []


# --------------------------------------------------------- texto e gatilho

def test_tools_rodam_quando_o_workflow_de_imagem_muda():
    """Os testes de `tools/` rodam no `manual.yml`, que só acorda pelos caminhos dele."""
    on = workflow(MANUAL)["on"]
    caminho = f".github/workflows/{backend()['build']['publish_workflow']}"
    for evento in ("push", "pull_request"):
        assert caminho in on[evento]["paths"], evento


def test_deploy_rollback_de_app_em_modo_imagem_e_por_tag():
    rollback = (SKILL_DEPLOY / "references" / "modo-rollback.md").read_text(encoding="utf-8")
    skill = (SKILL_DEPLOY / "SKILL.md").read_text(encoding="utf-8")
    for texto in (rollback, skill):
        assert "coolify app update <uuid> --docker-tag <SHA-alvo>" in texto
        assert "dockerimage" in texto
    assert "! coolify deploy uuid <uuid>" in rollback
    esquema = (SKILL_DEPLOY / "references" / "project-schema.md").read_text(encoding="utf-8")
    for campo in ('"dockerimage"', '"image"', '"publish_workflow"'):
        assert campo in esquema, campo
