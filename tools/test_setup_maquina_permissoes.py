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
from pathlib import Path

from test_setup_maquina_esteira import SEGREDO, linha, roda

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
    ALLOW[0]: "fechar_onda.py",
    ALLOW[1]: "minhas_issues.py",
    ALLOW[2]: "gh issue edit",
    ALLOW[3]: "gh issue comment",
    ALLOW[4]: "gh issue create",
    ALLOW[5]: "gh pr create",
    ALLOW[6]: "gh pr comment",
    DENY[0]: "git push --force",
    DENY[1]: "git push -f",
    DENY[2]: "gh api -X PUT",
    DENY[3]: "gh api --method PUT",
}


def settings(tmp_path: Path, allow=ALLOW, deny=DENY, ambiente=AMBIENTE, **extra) -> Path:
    arquivo = tmp_path / "settings.json"
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
