"""O CI no runner próprio do Mac do Pedro (issue #1599).

Os minutos grátis do GitHub Actions de novembro de 2026 acabaram e a conta não
tem cartão: todo job em `ubuntu-latest` ficou na fila. Os jobs sem Docker
passaram para o runner `pedro-mac`, de graça; só os que montam imagem ficam no
GitHub. Estes testes varrem todos os workflows e amarram as regras do runner
pessoal: o rótulo certo, nenhuma ação de terceiro nele, nenhum `setup-python` ou
`setup-node` (que no Mac não funcionam ou só gastam tempo), trava contra PR de
fork e rodada velha cancelada por commit novo.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

RAIZ = Path(__file__).resolve().parent.parent
WORKFLOWS = sorted((RAIZ / ".github" / "workflows").glob("*.yml"))
MAC = ["self-hosted", "pedro-mac"]
TRAVA_DE_FORK = "github.event.pull_request.head.repo.full_name == github.repository"
# Os jobs que montam imagem Docker: ficam no GitHub, gastando os minutos grátis.
DOCKER = {("ci.yml", "build"), ("imagem-backend.yml", "publicar")}
# O único job do Mac que roda em fork é nenhum; este reprova o PR de fork no GitHub.
RECUSA_DE_FORK = ("ci.yml", "fork-sem-mac")


def carregar(arquivo: Path) -> dict:
    return yaml.safe_load(arquivo.read_text(encoding="utf-8"))


def gatilhos(workflow: dict) -> dict:
    # o PyYAML lê a chave `on:` como o booleano True
    return workflow["on"] if "on" in workflow else workflow[True]


def jobs() -> list[tuple[str, str, dict, dict]]:
    return [(arq.name, nome, job, carregar(arq))
            for arq in WORKFLOWS for nome, job in carregar(arq)["jobs"].items()]


def jobs_do_mac() -> list[tuple[str, str, dict, dict]]:
    return [j for j in jobs() if j[2]["runs-on"] == MAC]


def test_todo_job_roda_no_mac_menos_o_docker_e_a_recusa_de_fork():
    for arquivo, nome, job, _ in jobs():
        if (arquivo, nome) in DOCKER or (arquivo, nome) == RECUSA_DE_FORK:
            assert job["runs-on"] == "ubuntu-latest", (arquivo, nome)
        else:
            assert job["runs-on"] == MAC, (arquivo, nome)


def test_os_jobs_de_docker_sao_os_que_usam_acao_de_docker():
    """Quem monta imagem é quem chama `docker/*`: um job novo de Docker que
    caísse no Mac apareceria aqui."""
    com_docker = {(arquivo, nome) for arquivo, nome, job, _ in jobs()
                  if any(p.get("uses", "").startswith("docker/") for p in job.get("steps", []))}
    assert com_docker == DOCKER


@pytest.mark.parametrize("arquivo, nome, job", [(a, n, j) for a, n, j, _ in jobs_do_mac()])
def test_job_do_mac_so_usa_acao_do_github_e_nenhum_setup(arquivo, nome, job):
    for passo in job.get("steps", []):
        uso = passo.get("uses", "")
        if not uso:
            continue
        assert uso.startswith("actions/"), (arquivo, nome, uso)
        assert not uso.startswith(("actions/setup-python@", "actions/setup-node@")), (arquivo, nome, uso)
        run = passo.get("run", "")
        assert "pip install" not in run, (arquivo, nome)


@pytest.mark.parametrize("arquivo, nome, job, workflow", jobs_do_mac())
def test_job_do_mac_com_pull_request_trava_o_fork(arquivo, nome, job, workflow):
    if "pull_request" not in gatilhos(workflow):
        return
    assert TRAVA_DE_FORK in job.get("if", ""), (arquivo, nome)


def test_job_do_mac_nao_roda_com_pull_request_target():
    """`pull_request_target` roda com os segredos do repositório e o código de
    quem abriu o PR: no runner pessoal, nunca."""
    for arquivo in WORKFLOWS:
        assert "pull_request_target" not in gatilhos(carregar(arquivo)), arquivo.name


@pytest.mark.parametrize("arquivo", [a for a in WORKFLOWS if "pull_request" in gatilhos(carregar(a))],
                         ids=lambda a: a.name)
def test_workflow_de_pr_cancela_a_rodada_anterior_da_mesma_branch(arquivo):
    """Commit novo no PR cancela a rodada velha; o push na main tem um grupo
    por commit e nunca cancela outro."""
    concorrencia = carregar(arquivo).get("concurrency")
    assert concorrencia, arquivo.name
    assert concorrencia["cancel-in-progress"] is True
    assert concorrencia["group"] == "${{ github.workflow }}-${{ github.event.pull_request.number || github.sha }}"


def test_build_so_roda_com_o_que_entra_na_imagem():
    ci = carregar(RAIZ / ".github" / "workflows" / "ci.yml")
    assert "needs.mudancas.outputs.imagem == 'true'" in ci["jobs"]["build"]["if"]
    assert "outputs.backend" not in ci["jobs"]["build"]["if"]
    assert "outputs.frontend" not in ci["jobs"]["build"]["if"]


def test_doc_do_fluxo_diz_que_o_ci_depende_do_mac_ligado():
    claude = (RAIZ / "CLAUDE.md").read_text(encoding="utf-8")
    assert "pedro-mac" in claude and "Mac do Pedro" in claude
