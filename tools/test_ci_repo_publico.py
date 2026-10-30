"""As travas de repositório público no CI (issue #1287, PRD #1282).

O repositório é público, e o que entra no histórico fica lá. Estes testes
amarram as travas que vivem em arquivo de configuração e que nenhum outro teste
exercita: o gitleaks só nos commits do PR, a trava de arquivo sensível no CI,
toda action presa ao SHA de um commit, o Dependabot dos três ecossistemas e o
`SECURITY.md` na raiz.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parent.parent
WORKFLOWS = RAIZ / ".github" / "workflows"
CI = WORKFLOWS / "ci.yml"


def ci() -> dict:
    return yaml.safe_load(CI.read_text(encoding="utf-8"))


def passos(job: str) -> list[dict]:
    return ci()["jobs"][job]["steps"]


def runs(job: str) -> str:
    return "\n".join(p.get("run", "") for p in passos(job))


# ------------------------------------------------------------- SHA fixo

RE_USES = re.compile(r"^\s*(?:-\s+)?uses:\s*(\S+)(.*)$")
RE_FIXO = re.compile(r"^[\w.-]+/[\w./-]+@[0-9a-f]{40}$")


def test_toda_action_dos_workflows_esta_presa_ao_sha_com_a_tag_em_comentario():
    usos = []
    for arquivo in sorted(WORKFLOWS.glob("*.yml")):
        for n, linha in enumerate(arquivo.read_text(encoding="utf-8").splitlines(), 1):
            m = RE_USES.match(linha)
            if m:
                usos.append((f"{arquivo.name}:{n}", m.group(1), m.group(2)))
    assert len(usos) >= 30, usos  # piso de sanidade: a varredura achou os workflows
    soltas = [u for u in usos if not RE_FIXO.match(u[1]) or not re.search(r"#\s*v\d", u[2])]
    assert soltas == []


# --------------------------------------------------------------- gitleaks

def test_gitleaks_roda_no_pr_so_nos_commits_dele_e_falha_em_achado():
    job = ci()["jobs"]["gitleaks"]
    assert job["if"] == "github.event_name == 'pull_request'"
    checkout = passos("gitleaks")[0]
    assert checkout["uses"].startswith("actions/checkout@")
    assert checkout["with"]["fetch-depth"] == 0
    script = runs("gitleaks")
    assert '--log-opts="$BASE_SHA..$HEAD_SHA"' in script
    assert "--config .gitleaks.toml" in script
    assert "--exit-code 1" in script
    # o binário baixado é conferido pelo sha256 antes de rodar
    assert "sha256sum -c" in script


def test_allowlist_do_gitleaks_cobre_os_fixtures_conhecidos_e_so_eles():
    config = tomllib.loads((RAIZ / ".gitleaks.toml").read_text(encoding="utf-8"))
    assert config["extend"]["useDefault"] is True
    padroes = [p for a in config["allowlists"] for p in a["paths"]]
    testes = RAIZ / "hospital-reunioes" / "backend" / "tests"
    for fixture in ["test_contas_medicas_conta.py", "test_central_de_comando_visao_geral.py",
                    "test_token_fora_do_log.py"]:
        caminho = f"hospital-reunioes/backend/tests/{fixture}"
        assert (testes / fixture).exists(), fixture
        assert any(re.search(p, caminho) for p in padroes), fixture
    # o resto do backend continua varrido
    assert not any(re.search(p, "hospital-reunioes/backend/app/config.py") for p in padroes)
    assert not any(re.search(p, "hospital-reunioes/backend/tests/test_reunioes.py") for p in padroes)


# ---------------------------------------------------- arquivo sensível

def test_trava_de_arquivo_sensivel_roda_no_pr_contra_a_base():
    job = ci()["jobs"]["arquivo-sensivel"]
    assert job["if"] == "github.event_name == 'pull_request'"
    assert passos("arquivo-sensivel")[0]["with"]["fetch-depth"] == 0
    assert 'python3 tools/checar_arquivo_sensivel.py --base "$BASE_SHA" --head "$HEAD_SHA"' in runs(
        "arquivo-sensivel"
    )


def test_snippet_com_emails_reais_saiu_do_repositorio():
    assert not (RAIZ / "hospital-reunioes" / "supabase" / "snippets" / "diagnostico-emails.sql").exists()


# ------------------------------------------------------------ Dependabot

def test_dependabot_semanal_e_agrupado_nos_tres_ecossistemas():
    config = yaml.safe_load((RAIZ / ".github" / "dependabot.yml").read_text(encoding="utf-8"))
    assert config["version"] == 2
    por_eco = {u["package-ecosystem"]: u for u in config["updates"]}
    assert por_eco["npm"]["directory"] == "/hospital-reunioes/frontend"
    assert por_eco["uv"]["directory"] == "/hospital-reunioes/backend"
    assert por_eco["github-actions"]["directory"] == "/"
    assert (RAIZ / "hospital-reunioes" / "frontend" / "package.json").exists()
    assert (RAIZ / "hospital-reunioes" / "backend" / "uv.lock").exists()
    for eco, u in por_eco.items():
        assert u["schedule"]["interval"] == "weekly", eco
        assert any(g.get("patterns") == ["*"] for g in u["groups"].values()), eco


# ------------------------------------------------------------- SECURITY

def test_security_md_na_raiz_diz_como_reportar_e_que_nao_aceita_dado_real():
    texto = (RAIZ / "SECURITY.md").read_text(encoding="utf-8")
    assert "Report a vulnerability" in texto
    assert "dado real" in texto
