"""O fluxo automático não pode parar na máquina de quem roda (ADR 0063, issue #964).

O modo auto do Claude Code ignora regra ampla de interpretador (`Bash(python3:*)`)
e não lê `autoMode` do settings do projeto. Então cada pessoa precisa, no próprio
`~/.claude/settings.json`, do allow específico do rabo, da `/minhas-issues` e da
escrituração em issue e PR, do deny de force push e de mudança no ruleset, e do
`autoMode.environment` descrevendo o repositório, o Coolify e a Vercel. O
`/setup-maquina` confere e diz o que falta e por quê; nunca grava o arquivo e
nunca imprime nada dele (o bloco `env` guarda token).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from test_setup_maquina_esteira import SCRIPT, SEGREDO, linha, roda

# A referência é o settings da máquina do Pedro em 05/10/2026 (PRD #963, decisão 10).
ALLOW = [
    "Bash(python3 .claude/skills/onda-enxuta/scripts/fechar_onda.py:*)",
    "Bash(python3 .claude/skills/minhas-issues/scripts/minhas_issues.py:*)",
    "Bash(gh issue edit:*)",
    "Bash(gh issue comment:*)",
    "Bash(gh issue create:*)",
    "Bash(gh pr create:*)",
    "Bash(gh pr comment:*)",
]
DENY = [
    "Bash(git push --force:*)",
    "Bash(git push -f:*)",
    "Bash(gh api -X PUT repos/pedrorezendefig/hospital-reunioes/rulesets:*)",
    "Bash(gh api --method PUT repos/pedrorezendefig/hospital-reunioes/rulesets:*)",
]
AMBIENTE = [
    "**Source control**: the trusted repo (pedrorezendefig/hospital-reunioes) and its origin",
    "**CI/CD deploy targets**: Coolify (coolify.exemplo.test), driven by fechar_onda.py",
    "**Trusted internal domains**: manual-hsm.vercel.app (Vercel)",
]
# Como cada regra aparece no rótulo da linha do diagnóstico.
ROTULOS = {
    ALLOW[0]: "allow fechar_onda.py",
    ALLOW[1]: "allow minhas_issues.py",
    ALLOW[2]: "allow gh issue edit",
    ALLOW[3]: "allow gh issue comment",
    ALLOW[4]: "allow gh issue create",
    ALLOW[5]: "allow gh pr create",
    ALLOW[6]: "allow gh pr comment",
    DENY[0]: "deny git push --force",
    DENY[1]: "deny git push -f",
    DENY[2]: "deny gh api -X PUT",
    DENY[3]: "deny gh api --method PUT",
}


def settings(pasta: Path, allow=ALLOW, deny=DENY, ambiente=AMBIENTE, **extra) -> Path:
    pasta.mkdir(parents=True, exist_ok=True)
    arquivo = pasta / "settings.json"
    dados = {
        "permissions": {"allow": list(allow), "deny": list(deny)},
        "autoMode": {"environment": list(ambiente), "allow": [], "soft_deny": []},
        **extra,
    }
    arquivo.write_text(json.dumps(dados, indent=2), encoding="utf-8")
    return arquivo


def confere(tmp_path: Path, arquivo: Path) -> str:
    return roda(tmp_path, f'checa_permissoes_claude "{arquivo}"')


def faltas(saida: str) -> list[str]:
    return [li for li in saida.splitlines() if li.startswith("FALTA")]


def test_settings_completo_passa_regra_por_regra(tmp_path):
    saida = confere(tmp_path, settings(tmp_path))
    assert faltas(saida) == [], saida
    for regra, rotulo in ROTULOS.items():
        assert linha(saida, rotulo).startswith("OK"), regra
    for item in ("repositório", "Coolify", "Vercel"):
        assert linha(saida, f"autoMode.environment: {item}").startswith("OK")


def test_settings_incompleto_aponta_cada_regra_que_falta_e_o_conserto(tmp_path):
    arquivo = settings(
        tmp_path,
        allow=[r for r in ALLOW if "fechar_onda" not in r and "gh pr comment" not in r],
        deny=[r for r in DENY if r != "Bash(git push -f:*)"],
        ambiente=[a for a in AMBIENTE if "Vercel" not in a],
    )
    saida = confere(tmp_path, arquivo)
    assert len(faltas(saida)) == 4, saida

    rabo = linha(saida, "allow fechar_onda.py")
    assert rabo.startswith("FALTA")
    assert ALLOW[0] in rabo and "permissions.allow" in rabo, "diz a regra exata e onde pôr"
    assert "~/.claude/settings.json" in rabo, "o arquivo é o do usuário, não o do projeto"

    comentario = linha(saida, "allow gh pr comment")
    assert comentario.startswith("FALTA") and ALLOW[6] in comentario

    force = linha(saida, "deny git push -f")
    assert force.startswith("FALTA")
    assert DENY[1] in force and "permissions.deny" in force

    vercel = linha(saida, "autoMode.environment: Vercel")
    assert vercel.startswith("FALTA")
    assert "não lê autoMode do settings do projeto" in vercel, "diz por que tem de ser no do usuário"

    assert linha(saida, "allow gh issue edit").startswith("OK")
    assert linha(saida, "deny git push --force").startswith("OK")
    assert linha(saida, "autoMode.environment: Coolify").startswith("OK")


def test_regra_ampla_de_interpretador_nao_substitui_a_especifica(tmp_path):
    amplas = ["Bash(python3:*)", "Bash(python3 *)"] + ALLOW[2:]
    saida = confere(tmp_path, settings(tmp_path, allow=amplas))
    for rotulo in ("allow fechar_onda.py", "allow minhas_issues.py"):
        li = linha(saida, rotulo)
        assert li.startswith("FALTA")
        assert "regra ampla de interpretador" in li, "diz por que a ampla não basta"


def test_regra_na_forma_com_espaco_tambem_vale(tmp_path):
    """O Claude Code aceita `Bash(cmd:*)` e `Bash(cmd *)`; a máquina do Pedro tem as duas."""
    com_espaco = [r.replace(":*)", " *)") for r in ALLOW]
    saida = confere(tmp_path, settings(tmp_path, allow=com_espaco))
    assert faltas(saida) == [], saida


def test_settings_sem_autoMode_e_sem_permissoes_acusa_tudo(tmp_path):
    arquivo = tmp_path / "settings.json"
    arquivo.write_text(json.dumps({"model": "opus"}), encoding="utf-8")
    assert len(faltas(confere(tmp_path, arquivo))) == len(ROTULOS) + 3


def test_settings_que_nao_existe_acusa_tudo(tmp_path):
    saida = confere(tmp_path, tmp_path / "nao-existe.json")
    assert len(faltas(saida)) == len(ROTULOS) + 3, saida


# ------------------------------------------------- segredo e escrita


def test_nao_imprime_valor_do_env_nem_grava_o_arquivo(tmp_path):
    """O token falso fica no `env`, onde o settings de verdade guarda chave."""
    arquivo = settings(
        tmp_path,
        allow=ALLOW[1:],
        ambiente=AMBIENTE[:1],
        env={"COOLIFY_ACCESS_TOKEN": SEGREDO, "GITHUB_PERSONAL_ACCESS_TOKEN": SEGREDO},
    )
    antes = arquivo.read_bytes()
    saida = confere(tmp_path, arquivo)
    assert len(faltas(saida)) == 3, saida
    assert SEGREDO not in saida
    assert arquivo.read_bytes() == antes, "nunca grava a configuração sozinho"
    assert list((tmp_path / "casa").iterdir()) == [], "nada gravado na casa nem na pasta"


# ------------------------------------------------- o script inteiro


def roda_script(tmp_path: Path, nivel: str) -> str:
    """O `diagnostico.sh` de verdade, numa cópia mínima do repo e com HOME falso."""
    repo = tmp_path / "repo"
    pasta_script = repo / ".claude" / "skills" / "setup-maquina" / "scripts"
    pasta_script.mkdir(parents=True, exist_ok=True)
    shutil.copy(SCRIPT, pasta_script / "diagnostico.sh")
    (pasta_script.parent / "references").mkdir(exist_ok=True)
    (pasta_script.parent / "references" / "plugins.txt").write_text("", encoding="utf-8")
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    pasta = tmp_path / "bin"
    pasta.mkdir(exist_ok=True)
    if not (pasta / "jq").exists():
        (pasta / "jq").symlink_to(shutil.which("jq"))
    r = subprocess.run(
        ["bash", str(pasta_script / "diagnostico.sh"), "--nivel", nivel],
        cwd=tmp_path / "casa",
        env={"PATH": f"{pasta}:/usr/bin:/bin", "HOME": str(tmp_path / "casa")},
        capture_output=True,
        text=True,
        timeout=120,
    )
    return r.stdout + r.stderr


def test_o_script_confere_o_settings_do_usuario_no_nivel_2(tmp_path):
    (tmp_path / "casa" / ".claude").mkdir(parents=True)
    settings(tmp_path / "casa" / ".claude", env={"COOLIFY_ACCESS_TOKEN": SEGREDO})
    saida = roda_script(tmp_path, "2")
    for rotulo in ROTULOS.values():
        assert linha(saida, rotulo).split()[0] == "OK", saida
    assert linha(saida, "autoMode.environment: Vercel").split()[0] == "OK", saida
    assert SEGREDO not in saida


def test_settings_do_projeto_nao_conta(tmp_path):
    """O modo auto não lê `autoMode` do projeto: só o arquivo do usuário vale."""
    (tmp_path / "casa").mkdir()
    settings(tmp_path / "repo" / ".claude")
    saida = roda_script(tmp_path, "2")
    assert linha(saida, "allow fechar_onda.py").split()[0] == "FALTA", saida
    assert linha(saida, "autoMode.environment: Coolify").split()[0] == "FALTA", saida


def test_o_nivel_1_nao_confere_as_permissoes(tmp_path):
    (tmp_path / "casa").mkdir()
    assert "allow fechar_onda.py" not in roda_script(tmp_path, "1")
