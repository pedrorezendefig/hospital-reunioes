"""O PRD nasce com dono e o `/pegar-issue` avisa fatia de PRD alheio (issue #904).

ADR 0061, decisão 4: todo PRD tem como assignee quem fez o grilling, e pegar
fatia de PRD alheio não é proibido, mas se combina antes. O aviso e a fila com o
dono saem de `dono_do_prd.py`, que estes testes rodam como o agente roda, com um
`gh` de mentira no PATH: o GitHub de verdade não entra no teste.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
SKILLS = RAIZ / ".claude" / "skills"
SCRIPT = SKILLS / "pegar-issue" / "scripts" / "dono_do_prd.py"

QUEM_PEGA = "lucassampaioc1"


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
        "  repo) echo hsm/hospital-reunioes ;;\n"
        '  api) cat "$GH_RESPOSTA" ;;\n'
        "esac\n",
        encoding="utf-8",
    )
    gh.chmod(0o755)
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


def issue(parent: dict | None) -> dict:
    """A resposta do GraphQL para `/pegar-issue <N>`: quem pega e o pai da fatia."""
    return {
        "data": {
            "viewer": {"login": QUEM_PEGA},
            "repository": {"issue": {"number": 904, "parent": parent}},
        }
    }


def prd(numero: int, *donos: str) -> dict:
    return {
        "number": numero,
        "assignees": {"nodes": [{"login": d} for d in donos]},
    }


def test_fatia_de_prd_alheio_avisa_com_o_login_do_dono_e_nao_bloqueia(tmp_path):
    feito = rodar(tmp_path, issue(prd(902, "pedrorezendefig")), "904")

    assert feito.returncode == 0, feito.stderr
    assert feito.stdout.strip() == "fatia do PRD de @pedrorezendefig; combine antes"


@pytest.mark.parametrize(
    "parent",
    [
        pytest.param(prd(902, "pedrorezendefig", QUEM_PEGA), id="fatia-do-proprio-prd"),
        pytest.param(None, id="issue-avulsa"),
        pytest.param(prd(659), id="prd-sem-dono"),
    ],
)
def test_sem_aviso_quando_nao_ha_o_que_combinar(tmp_path, parent):
    feito = rodar(tmp_path, issue(parent), "904")

    assert feito.returncode == 0, feito.stderr
    assert feito.stdout == ""
