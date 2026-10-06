"""O ruleset da `main` e o CI que ele exige (issue #910, ADR 0061 decisão 3).

O ruleset vive versionado em `.github/rulesets/main.json` e é aplicado à mão
pelo admin (`gh api`, no corpo do PR #910 e no `dev.md`). Ele exige os jobs do
`ci.yml` pelo nome: renomear um job sem mexer no ruleset deixa todo PR em
"Expected, waiting for status" para sempre. E workflow pulado por filtro de
caminho não reporta check nenhum, então o PR só de docs (o registro do
`fechar_onda.py`, ADR, skill) travaria do mesmo jeito. Estes testes amarram as
duas pontas: o nome de cada check e o CI que sempre reporta.

Desde a issue #966 o detector responde por pasta (backend, frontend,
ferramenta) e cada job pesado roda só com a parte dele. Os testes rodam o
script do detector num repo git de verdade e avaliam o `if:` de cada job com as
saídas dele, como o GitHub avalia: a pergunta é quais jobs rodam.
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


def test_ruleset_pr_obrigatorio_zero_aprovacoes_em_dia_com_a_base_sem_force_push_nem_delete():
    r = ruleset()
    assert r["target"] == "branch" and r["enforcement"] == "active"
    assert r["conditions"]["ref_name"]["include"] == ["refs/heads/main"]
    assert regra("pull_request")["parameters"]["required_approving_review_count"] == 0
    assert regra("required_status_checks")["parameters"]["strict_required_status_checks_policy"] is True
    regra("non_fast_forward")
    regra("deletion")


def test_bypass_so_do_github_actions_nenhuma_pessoa_nem_equipe():
    """A Action pós-merge commita snapshot e draft do Manual direto na `main`
    (issue #940, ADR 0062 decisão 10). O bypass é do GitHub Actions e de mais
    ninguém: pessoa, equipe, papel ou admin da organização continuam entrando
    por PR, admin inclusive (ADR 0061)."""
    assert ruleset()["bypass_actors"] == [
        {"actor_id": GITHUB_ACTIONS_APP, "actor_type": "Integration", "bypass_mode": "always"}
    ]


# ---------------------------------------------- CI que sempre reporta no PR

def test_pr_so_de_docs_tambem_dispara_o_ci():
    pr = gatilho("pull_request")
    assert "paths" not in pr, pr
    assert "branches: [main]" in pr


def test_jobs_obrigatorios_pulam_por_if_e_rodam_todos_se_o_detector_falhar():
    """Job pulado por `if` reporta sucesso, e é isso que libera o PR só de
    ferramenta. Se o detector falhar (sem saída nenhuma), os três rodam: pular
    o CI de um PR de código porque o detector quebrou passaria pelo ruleset sem
    teste nenhum. Workflow cancelado não roda nada."""
    assert len(jobs_obrigatorios()) == 3, sorted(jobs_obrigatorios())
    assert jobs_que_rodam("success", {"backend": "false", "frontend": "false", "ferramenta": "true"}) == set()
    assert jobs_que_rodam("failure", {}) == TUDO
    assert jobs_que_rodam("failure", {}, cancelado=True) == set()


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


def saidas_do_passo(proc: subprocess.CompletedProcess) -> dict[str, str]:
    return dict(li.split("=", 1) for li in proc.stdout.splitlines())


def repasse_do_job_mudancas() -> dict[str, str]:
    """saída do job `mudancas` -> saída do passo `diff` que ela repassa."""
    bloco = jobs_do_ci()["mudancas"]
    trecho = re.search(r"^    outputs:\n((?:      .*\n)+)", bloco, re.M).group(1)
    return dict(re.findall(r"^      (\w+): \$\{\{ steps\.diff\.outputs\.(\w+) \}\}$", trecho, re.M))


def avaliar_if(expr: str, resultado: str, saidas_job: dict[str, str], cancelado: bool = False) -> bool:
    """Avalia o `if:` de um job como o GitHub Actions avalia, no vocabulário
    que este CI usa: `!`, `&&`, `||`, `==`, `!=`, `cancelled()` e o resultado e
    as saídas do job `mudancas`. Saída que não existe vale '' no GitHub. Sem
    função de status no `if`, o GitHub soma um `success() &&` implícito, que
    pula o job quando o detector falha: é isso que o `!cancelled()` desliga."""
    corpo = re.fullmatch(r"\$\{\{ (.+) \}\}", expr.strip()).group(1)
    if not re.search(r"\b(success|failure|cancelled|always)\(\)", corpo):
        corpo = f"success() && ({corpo})"
    corpo = corpo.replace("success()", repr(resultado == "success" and not cancelado))
    corpo = corpo.replace("cancelled()", repr(cancelado))
    corpo = corpo.replace("needs.mudancas.result", repr(resultado))
    corpo = re.sub(r"needs\.mudancas\.outputs\.(\w+)", lambda m: repr(saidas_job.get(m.group(1), "")), corpo)
    corpo = corpo.replace("&&", " and ").replace("||", " or ")
    corpo = re.sub(r"!(?!=)", " not ", corpo)
    sobra = set(re.findall(r"[A-Za-z_.]+", re.sub(r"'[^']*'", "", corpo)))
    assert sobra <= {"True", "False", "and", "or", "not"}, f"if fora do vocabulário: {expr}"
    return eval(corpo, {"__builtins__": {}})


def jobs_que_rodam(resultado: str, saidas_passo: dict[str, str], cancelado: bool = False) -> set[str]:
    repasse = repasse_do_job_mudancas()
    saidas_job = {saida: saidas_passo.get(passo, "") for saida, passo in repasse.items()}
    rodam = set()
    for job, bloco in jobs_obrigatorios().items():
        se = re.search(r"^    if: (.+)$", bloco, re.M)
        assert se, f"{job} sem if: sem ele o job roda sempre e o detector não serve"
        if avaliar_if(se.group(1), resultado, saidas_job, cancelado):
            rodam.add(job)
    return rodam


TUDO = {"backend", "frontend-lint", "build"}
BACKEND = {"backend", "build"}
FRONTEND = {"frontend-lint", "build"}


@pytest.mark.parametrize("mudados, rodam, ferramenta", [
    (["docs/spec/deploy/history.json", "docs/spec/deploy/state.json", "docs/ARQUITETURA.md"], set(), "true"),
    (["docs/manual/src/content/docs/ouvidoria/index.mdx"], set(), "true"),
    ([".claude/skills/onda-enxuta/scripts/fechar_onda.py"], set(), "true"),
    (["docs/adr/0061-x.md", "tools/checar_migration_repetida.py"], set(), "true"),
    ([".github/rulesets/main.json"], set(), "true"),
    (["README.md"], set(), "true"),
    (["hospital-reunioes/README.md"], set(), "false"),
    (["hospital-reunioes/frontend/package.json"], FRONTEND, "false"),
    (["hospital-reunioes/backend/app/main.py"], BACKEND, "false"),
    (["hospital-reunioes/supabase/migrations/114_x.sql"], BACKEND, "false"),
    # Acento: com core.quotePath ligado (o padrão) o git devolve o caminho
    # entre aspas, e nenhum ^hospital-reunioes/ casaria.
    (["hospital-reunioes/backend/app/serviço.py"], BACKEND, "false"),
    (["hospital-reunioes/supabase/migrations/115_manifestação.sql"], BACKEND, "false"),
    (["hospital-reunioes/frontend/src/app/reunião/page.tsx"], FRONTEND, "false"),
    # Aspa no nome continua entre aspas mesmo sem quotePath: roda tudo.
    (['hospital-reunioes/backend/app/a"b.py'], TUDO, "true"),
    (["hospital-reunioes/backend/README.md", "hospital-reunioes/frontend/src/app/page.tsx"], TUDO, "false"),
    (["tools/x.py", "hospital-reunioes/frontend/package.json"], FRONTEND, "true"),
    ([".github/workflows/ci.yml"], TUDO, "true"),
    ([".github/workflows/manual.yml"], TUDO, "true"),
    ([], TUDO, "true"),
])
def test_cada_pasta_liga_so_os_jobs_dela(tmp_path, mudados, rodam, ferramenta):
    """A tabela do PRD #963 (decisão 4): backend roda com `backend/` ou
    `supabase/`, frontend com `frontend/`, docker build com qualquer um dos
    dois, `.github/workflows/` roda tudo. Ferramenta (fora de
    `hospital-reunioes/`, a mesma fronteira do rabo) não liga job nenhum daqui:
    os testes de `tools/` rodam no `manual.yml`."""
    proc = rodar_detector(tmp_path, mudados)
    assert proc.returncode == 0, proc.stderr
    saidas = saidas_do_passo(proc)
    assert jobs_que_rodam("success", saidas) == rodam, saidas
    assert saidas["ferramenta"] == ferramenta, saidas


@pytest.mark.parametrize("origem, destino, rodam", [
    ("hospital-reunioes/backend/app/main.py", "docs/main.py", BACKEND),
    # Cruza pastas: sem --no-renames só o destino (frontend) apareceria.
    ("hospital-reunioes/backend/app/x.py", "hospital-reunioes/frontend/src/x.py", TUDO),
])
def test_detector_ve_o_caminho_antigo_de_um_rename(tmp_path, origem, destino, rodam):
    """Num rename o `git diff --name-only` lista só o caminho novo: tirar código
    do backend pularia o job dele e o merge subiria sem teste."""
    proc = rodar_detector(tmp_path, [], renomeados=((origem, destino),))
    assert proc.returncode == 0, proc.stderr
    assert jobs_que_rodam("success", saidas_do_passo(proc)) == rodam


def test_detector_no_push_da_main_sempre_roda_tudo(tmp_path):
    proc = rodar_detector(tmp_path, ["docs/x.md"], evento="push")
    assert proc.returncode == 0, proc.stderr
    assert jobs_que_rodam("success", saidas_do_passo(proc)) == TUDO


def test_detector_que_nao_acha_a_base_falha_e_roda_tudo(tmp_path):
    proc = rodar_detector(tmp_path, ["hospital-reunioes/backend/app/main.py"], base="0" * 40)
    assert proc.returncode != 0
    assert jobs_que_rodam("failure", saidas_do_passo(proc)) == TUDO


def test_estes_testes_rodam_quando_tools_o_ci_ou_o_ruleset_mudam():
    """Os testes de `tools/` rodam no `manual.yml`, que só acorda pelos caminhos
    dele. O `ci.yml` pula PR só de ferramenta (issue #966): sem `tools/**` aqui,
    mudança em `tools/` entraria sem teste nenhum."""
    texto = MANUAL.read_text(encoding="utf-8")
    on = texto.split("\non:\n", 1)[1].split("\njobs:\n", 1)[0]
    for evento in ("push", "pull_request"):
        bloco = re.search(rf"^  {evento}:\n((?:    .*\n|\n)*)", on, re.M).group(1)
        assert "- 'tools/**'" in bloco, evento
        assert "- '.github/workflows/ci.yml'" in bloco, evento
        assert "- '.github/rulesets/**'" in bloco, evento
