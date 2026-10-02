"""O ruleset da `main` e o CI que ele exige (issue #910, ADR 0061 decisão 3).

O ruleset vive versionado em `.github/rulesets/main.json` e é aplicado à mão
pelo admin (`gh api`, no corpo do PR #910 e no `dev.md`). Ele exige os jobs do
`ci.yml` pelo nome: renomear um job sem mexer no ruleset deixa todo PR em
"Expected, waiting for status" para sempre. E workflow pulado por filtro de
caminho não reporta check nenhum, então o PR só de docs (o registro do
`fechar_onda.py`, ADR, skill) travaria do mesmo jeito. Estes testes amarram as
duas pontas: o nome de cada check e o CI que sempre reporta.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
CI = RAIZ / ".github" / "workflows" / "ci.yml"
MANUAL = RAIZ / ".github" / "workflows" / "manual.yml"
RULESET = RAIZ / ".github" / "rulesets" / "main.json"
GITHUB_ACTIONS_APP = 15368  # integration_id do GitHub Actions

ENV_GIT = {
    **os.environ,
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "teste",
    "GIT_AUTHOR_EMAIL": "teste@example.com",
    "GIT_COMMITTER_NAME": "teste",
    "GIT_COMMITTER_EMAIL": "teste@example.com",
}


def ruleset() -> dict:
    return json.loads(RULESET.read_text(encoding="utf-8"))


def regra(tipo: str) -> dict:
    achadas = [r for r in ruleset()["rules"] if r["type"] == tipo]
    assert len(achadas) == 1, f"regra {tipo}: {achadas}"
    return achadas[0]


def jobs_do_ci() -> dict[str, str]:
    """id do job -> bloco de texto dele (o YAML do CI é simples o bastante)."""
    texto = CI.read_text(encoding="utf-8")
    corpo = texto.split("\njobs:\n", 1)[1]
    partes = re.split(r"^  ([\w-]+):\n", corpo, flags=re.M)
    return dict(zip(partes[1::2], partes[2::2]))


def nome(bloco: str) -> str:
    return re.search(r"^    name: (.+)$", bloco, re.M).group(1).strip()


def jobs_obrigatorios() -> dict[str, str]:
    return {j: b for j, b in jobs_do_ci().items() if re.search(r"^    needs: mudancas$", b, re.M)}


def gatilho(evento: str) -> str:
    texto = CI.read_text(encoding="utf-8")
    on = texto.split("\non:\n", 1)[1].split("\njobs:\n", 1)[0]
    return re.search(rf"^  {evento}:\n((?:    .*\n|\n)*)", on + "\n", re.M).group(1)


# ------------------------------------------------------------------ ruleset

def test_ruleset_exige_os_tres_jobs_do_ci_pelo_nome_vindos_do_github_actions():
    obrigatorios = jobs_obrigatorios()
    assert sorted(obrigatorios) == ["backend", "build", "frontend-lint"]
    checks = regra("required_status_checks")["parameters"]["required_status_checks"]
    assert sorted(c["context"] for c in checks) == sorted(nome(b) for b in obrigatorios.values())
    assert {c.get("integration_id") for c in checks} == {GITHUB_ACTIONS_APP}


def test_ruleset_pr_obrigatorio_zero_aprovacoes_em_dia_com_a_base_sem_force_push_delete_nem_bypass():
    r = ruleset()
    assert r["target"] == "branch" and r["enforcement"] == "active"
    assert r["conditions"]["ref_name"]["include"] == ["refs/heads/main"]
    assert r["bypass_actors"] == [], "sem bypass, nem para admin"
    assert regra("pull_request")["parameters"]["required_approving_review_count"] == 0
    assert regra("required_status_checks")["parameters"]["strict_required_status_checks_policy"] is True
    regra("non_fast_forward")
    regra("deletion")


# ---------------------------------------------- CI que sempre reporta no PR

def test_pr_so_de_docs_tambem_dispara_o_ci():
    pr = gatilho("pull_request")
    assert "paths" not in pr, pr
    assert "branches: [main]" in pr


def test_jobs_obrigatorios_pulam_por_if_e_rodam_se_o_detector_falhar():
    """Job pulado por `if` reporta sucesso, e é isso que libera o PR só de docs.
    Se o detector falhar, os jobs rodam: pular o CI de um PR de código porque o
    detector quebrou passaria pelo ruleset sem teste nenhum."""
    obrigatorios = jobs_obrigatorios()
    assert len(obrigatorios) == 3, sorted(obrigatorios)
    for job, bloco in obrigatorios.items():
        se = re.search(r"^    if: (.+)$", bloco, re.M)
        assert se, f"{job} sem if"
        expr = se.group(1)
        assert "!cancelled()" in expr, (job, expr)
        assert "needs.mudancas.result != 'success'" in expr, (job, expr)
        assert "needs.mudancas.outputs.codigo == 'true'" in expr, (job, expr)


def passo_do_detector() -> tuple[str, dict[str, str]]:
    """O script do passo `diff` do job `mudancas` e o env dele, como estão no YAML."""
    bloco = jobs_do_ci()["mudancas"]
    passo = bloco.split("        id: diff\n", 1)[1]
    env = dict(re.findall(r"^          (\w+): \$\{\{ (.+?) \}\}$", passo.split("        run: |\n", 1)[0], re.M))
    linhas = passo.split("        run: |\n", 1)[1].splitlines()
    script = []
    for li in linhas:
        if li and not li.startswith("          "):
            break
        script.append(li[10:])
    return "\n".join(script) + "\n", env


def rodar_detector(tmp_path: Path, mudados: list[str], evento: str = "pull_request",
                   base: str | None = None,
                   renomeados: tuple[tuple[str, str], ...] = ()) -> subprocess.CompletedProcess:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, env=ENV_GIT, check=True)
    (repo / "base.txt").write_text("base\n", encoding="utf-8")
    for origem, _ in renomeados:
        arq = repo / origem
        arq.parent.mkdir(parents=True, exist_ok=True)
        arq.write_text("conteudo igual, para o git ver o rename\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, env=ENV_GIT, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=repo, env=ENV_GIT, check=True)
    sha_base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True,
                              text=True, check=True).stdout.strip()
    for caminho in mudados:
        arq = repo / caminho
        arq.parent.mkdir(parents=True, exist_ok=True)
        arq.write_text("mudou\n", encoding="utf-8")
    for origem, destino in renomeados:
        (repo / destino).parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "mv", origem, destino], cwd=repo, env=ENV_GIT, check=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, env=ENV_GIT, check=True)
    subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", "pr"], cwd=repo, env=ENV_GIT, check=True)
    sha_head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True,
                              text=True, check=True).stdout.strip()
    script, env_yaml = passo_do_detector()
    valores = {
        "github.event_name": evento,
        "github.event.pull_request.base.sha": base if base is not None else sha_base,
        "github.event.pull_request.head.sha": sha_head,
    }
    saida = tmp_path / "github_output"
    saida.write_text("", encoding="utf-8")
    env = {**ENV_GIT, "GITHUB_OUTPUT": str(saida), **{k: valores[v] for k, v in env_yaml.items()}}
    (tmp_path / "passo.sh").write_text(script, encoding="utf-8")
    # o shell padrão do GitHub Actions no Linux: bash -e {0}
    proc = subprocess.run(["bash", "-e", str(tmp_path / "passo.sh")], cwd=repo, env=env,
                          capture_output=True, text=True)
    proc.stdout = saida.read_text(encoding="utf-8")
    return proc


@pytest.mark.parametrize("mudados, codigo", [
    (["docs/spec/deploy/history.json", "docs/spec/CHANGELOG.md", "docs/ARQUITETURA.md"], "false"),
    (["docs/manual/src/content/docs/ouvidoria/index.mdx"], "false"),
    ([".claude/skills/onda-enxuta/scripts/fechar_onda.py"], "false"),
    (["README.md", "hospital-reunioes/README.md"], "false"),
    (["hospital-reunioes/frontend/package.json"], "true"),
    ([".github/workflows/ci.yml"], "true"),
    (["docs/adr/0061-x.md", "tools/checar_migration_repetida.py"], "true"),
    ([], "true"),
])
def test_detector_classifica_como_o_paths_ignore_do_push(tmp_path, mudados, codigo):
    proc = rodar_detector(tmp_path, mudados)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == f"codigo={codigo}\n"


@pytest.mark.parametrize("origem, destino", [
    ("hospital-reunioes/backend/app/main.py", "docs/main.py"),
    ("hospital-reunioes/backend/app/main.py", "hospital-reunioes/backend/app/main.md"),
])
def test_detector_ve_o_caminho_antigo_de_um_rename(tmp_path, origem, destino):
    """Num rename o `git diff --name-only` lista só o caminho novo: mover código
    para docs/ pularia os três checks obrigatórios e o merge subiria sem teste."""
    proc = rodar_detector(tmp_path, [], renomeados=((origem, destino),))
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "codigo=true\n"


def test_detector_no_push_da_main_sempre_roda(tmp_path):
    proc = rodar_detector(tmp_path, ["docs/x.md"], evento="push")
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "codigo=true\n"


def test_detector_que_nao_acha_a_base_falha_em_vez_de_pular(tmp_path):
    proc = rodar_detector(tmp_path, ["hospital-reunioes/backend/app/main.py"], base="0" * 40)
    assert proc.returncode != 0
    assert "codigo=false" not in proc.stdout


def test_estes_testes_rodam_quando_o_ci_ou_o_ruleset_mudam():
    """Os testes de `tools/` rodam no `manual.yml`, que só acorda pelos caminhos dele."""
    texto = MANUAL.read_text(encoding="utf-8")
    on = texto.split("\non:\n", 1)[1].split("\njobs:\n", 1)[0]
    for evento in ("push", "pull_request"):
        bloco = re.search(rf"^  {evento}:\n((?:    .*\n|\n)*)", on, re.M).group(1)
        assert "- '.github/workflows/ci.yml'" in bloco, evento
        assert "- '.github/rulesets/**'" in bloco, evento
