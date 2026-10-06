"""O `/pegar-issue` avisa, sem bloquear, a issue que toca arquivo de outra em andamento.

Nasceu no #970 recusando o claim e gravando "Bloqueada por" (ADR 0063). A ADR
0066 tirou o arquivo como separador: o único separador é a dependência, escrita
como `blocked_by` por quem fatia, e o conflito de texto se resolve no rabo PR a
PR. Agora `arquivo_em_comum.py` só imprime um aviso de uma linha com os arquivos
que coincidem, sai 0 e não grava dependência nenhuma. Estes testes o rodam como
o agente roda, com um `gh` de mentira no PATH.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SKILL = RAIZ / ".claude" / "skills" / "pegar-issue" / "SKILL.md"
SCRIPT = RAIZ / ".claude" / "skills" / "pegar-issue" / "scripts" / "arquivo_em_comum.py"

REPO = "hsm/hospital-reunioes"


def rodar(tmp_path: Path, resposta: dict, *args: str) -> subprocess.CompletedProcess:
    """Roda o script com um `gh` falso que devolve `resposta` ao GraphQL."""
    falso = tmp_path / "bin"
    falso.mkdir(exist_ok=True)
    (tmp_path / "resposta.json").write_text(json.dumps(resposta), encoding="utf-8")
    gh = falso / "gh"
    gh.write_text(
        "#!/bin/sh\n"
        'printf "%s\\n" "$*" >> "$GH_LOG"\n'
        'case "$1" in\n'
        f"  repo) echo {REPO} ;;\n"
        '  api) case "$*" in *graphql*) cat "$GH_RESPOSTA" ;; *) echo "{}" ;; esac ;;\n'
        "esac\n",
        encoding="utf-8",
    )
    gh.chmod(0o755)
    (tmp_path / "gh.log").write_text("", encoding="utf-8")
    ambiente = dict(
        os.environ,
        PATH=f"{falso}:{os.environ['PATH']}",
        GH_LOG=str(tmp_path / "gh.log"),
        GH_RESPOSTA=str(tmp_path / "resposta.json"),
    )
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        env=ambiente,
    )


def em_andamento(numero: int, id_: int, corpo: str = "", *prs: list[str]) -> dict:
    return {
        "number": numero,
        "databaseId": id_,
        "body": corpo,
        "closedByPullRequestsReferences": {
            "nodes": [{"files": {"nodes": [{"path": p} for p in arquivos]}} for arquivos in prs]
        },
    }


def resposta(corpo_da_candidata: str, *andamento: dict) -> dict:
    return {
        "data": {
            "repository": {"issue": {"body": corpo_da_candidata}},
            "search": {"nodes": list(andamento)},
        }
    }


def bloqueios(tmp_path: Path) -> list[str]:
    log = (tmp_path / "gh.log").read_text(encoding="utf-8").splitlines()
    return [li for li in log if "dependencies/blocked_by" in li]


def test_arquivo_do_pr_de_outra_em_andamento_avisa_sem_bloquear(tmp_path):
    feito = rodar(
        tmp_path,
        resposta(
            "Mexe no Passo 10 de `.claude/skills/ship/SKILL.md`.",
            em_andamento(988, 5001, "", [".claude/agents/hr-revisor.md", ".claude/skills/ship/SKILL.md"]),
        ),
        "970",
    )

    assert feito.returncode == 0, feito.stderr
    assert feito.stdout == (
        "aviso, sem bloqueio (ADR 0066): arquivo em comum com fatia em andamento: "
        "#988 (.claude/skills/ship/SKILL.md)\n"
    )
    assert bloqueios(tmp_path) == []


def test_citacao_curta_com_linha_casa_com_o_caminho_inteiro_do_corpo_da_outra(tmp_path):
    """Ainda sem PR, a fatia em andamento só tem o que o corpo dela cita."""
    feito = rodar(
        tmp_path,
        resposta(
            "O `raise` em `fechar_onda.py:466` vira código próprio.",
            em_andamento(989, 5002, "Reescreve `.claude/skills/onda-enxuta/scripts/fechar_onda.py`."),
        ),
        "970",
    )

    assert feito.returncode == 0, feito.stderr
    assert "#989 (.claude/skills/onda-enxuta/scripts/fechar_onda.py)" in feito.stdout
    assert bloqueios(tmp_path) == []


def test_sem_arquivo_em_comum_pega_sem_marcar_nada(tmp_path):
    feito = rodar(
        tmp_path,
        resposta(
            "Mexe em `.claude/skills/ship/SKILL.md` e em `tools/test_skill_ship_rabo.py`.",
            em_andamento(990, 5003, "Muda `.github/rulesets/main.json`.", ["tools/test_ruleset_main.py"]),
        ),
        "970",
    )

    assert feito.returncode == 0, feito.stderr
    assert feito.stdout == ""
    assert bloqueios(tmp_path) == []


def test_mesmo_nome_em_pasta_diferente_nao_e_o_mesmo_arquivo(tmp_path):
    feito = rodar(
        tmp_path,
        resposta(
            "Mexe em `.claude/skills/ship/SKILL.md`.",
            em_andamento(995, 5004, "", [".claude/skills/tdd/SKILL.md"]),
        ),
        "970",
    )

    assert feito.returncode == 0, feito.stdout
    assert feito.stdout == ""
    assert bloqueios(tmp_path) == []


def test_a_propria_issue_ja_em_andamento_nao_se_bloqueia(tmp_path):
    feito = rodar(
        tmp_path,
        resposta(
            "Mexe em `CLAUDE.md`.",
            em_andamento(970, 5005, "Mexe em `CLAUDE.md`."),
        ),
        "970",
    )

    assert feito.returncode == 0, feito.stdout
    assert feito.stdout == ""
    assert bloqueios(tmp_path) == []


def test_todas_as_fatias_com_arquivo_em_comum_cabem_num_aviso_de_uma_linha(tmp_path):
    feito = rodar(
        tmp_path,
        resposta(
            "Mexe em `CLAUDE.md` e em `docs/onboarding/dev.md`.",
            em_andamento(988, 5001, "Atualiza o `CLAUDE.md`."),
            em_andamento(990, 5003, "", ["docs/onboarding/dev.md"]),
            em_andamento(995, 5004, "Só `.claude/skills/to-issues/SKILL.md`."),
        ),
        "970",
    )

    assert feito.returncode == 0, feito.stderr
    assert feito.stdout == (
        "aviso, sem bloqueio (ADR 0066): arquivo em comum com fatia em andamento: "
        "#988 (CLAUDE.md); #990 (docs/onboarding/dev.md)\n"
    )
    assert bloqueios(tmp_path) == []


def test_a_busca_e_so_das_abertas_em_andamento_do_repositorio(tmp_path):
    rodar(tmp_path, resposta("Mexe em `CLAUDE.md`."), "970")

    chamada = (tmp_path / "gh.log").read_text(encoding="utf-8")
    assert f"q=repo:{REPO} is:issue is:open label:in-progress" in chamada
    assert "n=970" in chamada


def test_o_pegar_issue_roda_o_aviso_antes_do_claim_e_segue_sem_bloquear():
    com_argumento = SKILL.read_text(encoding="utf-8").split("## Com argumento", 1)[1]
    chamada = re.search(r"python3 (\S+/arquivo_em_comum\.py) <N>", com_argumento)
    assert chamada, "o /pegar-issue roda o script com o número da issue"
    assert RAIZ / chamada.group(1) == SCRIPT
    claim = com_argumento.index("gh issue edit <N> --remove-label ready-for-agent")
    assert chamada.start() < claim
    passo = com_argumento[chamada.start():com_argumento.index("### 4.")]
    assert "ADR 0066" in passo, passo
    assert re.search(r"\*\*siga para o claim\*\*", passo), passo
    assert "não pegue" not in passo and "Bloqueada por" not in passo, passo


def test_o_script_novo_nao_tem_travessao():
    travessoes = f"[{chr(0x2013)}{chr(0x2014)}]"
    assert not re.search(travessoes, SCRIPT.read_text(encoding="utf-8"))
