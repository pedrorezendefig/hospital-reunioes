"""O PRD nasce com dono e o `/pegar-issue` avisa fatia de PRD alheio (issue #904).

ADR 0061, decisão 4: todo PRD tem como assignee quem fez o grilling, e pegar
fatia de PRD alheio não é proibido, mas se combina antes. O aviso e a fila com o
dono saem de `dono_do_prd.py`, que estes testes rodam como o agente roda, com um
`gh` de mentira no PATH: o GitHub de verdade não entra no teste.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
SKILLS = RAIZ / ".claude" / "skills"
SCRIPT = SKILLS / "pegar-issue" / "scripts" / "dono_do_prd.py"

QUEM_PEGA = "lucassampaioc1"


def texto(skill: str) -> str:
    return (SKILLS / skill / "SKILL.md").read_text(encoding="utf-8")


def criacoes(skill: str) -> list[str]:
    """Cada `gh issue create` que a skill manda rodar (com título, não a menção)."""
    achadas = re.findall(r"gh issue create --title[^\n`]*", texto(skill))
    assert achadas, f"o /{skill} não manda mais rodar gh issue create --title"
    return achadas


def test_o_prd_nasce_com_o_assignee_de_quem_rodou_o_to_prd():
    assert all("--assignee @me" in c for c in criacoes("to-prd"))


def test_o_to_issues_nao_atribui_fatia():
    assert not any("--assignee" in c for c in criacoes("to-issues"))


def test_o_pegar_issue_roda_o_script_que_existe():
    chamadas = dict(
        (modo, caminho)
        for caminho, modo in re.findall(
            r"python3 (\S+/dono_do_prd\.py) (<N>|--fila)", texto("pegar-issue")
        )
    )
    assert set(chamadas) == {"<N>", "--fila"}
    assert all((RAIZ / caminho) == SCRIPT for caminho in chamadas.values())


def test_o_aviso_vem_antes_do_claim_e_a_fila_sem_argumento_mostra_o_dono():
    sem_argumento, com_argumento = texto("pegar-issue").split("## Com argumento", 1)
    assert "dono_do_prd.py --fila" in sem_argumento
    claim = com_argumento.index("gh issue edit <N> --remove-label ready-for-agent")
    assert com_argumento.index("dono_do_prd.py <N>") < claim


def test_o_texto_novo_nao_tem_travessao():
    travessoes = f"[{chr(0x2013)}{chr(0x2014)}]"
    assert not re.search(travessoes, SCRIPT.read_text(encoding="utf-8"))


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


def fila(*issues: dict) -> dict:
    return {"data": {"search": {"nodes": list(issues)}}}


def fatia(numero: int, titulo: str, labels: list[str], parent: dict | None) -> dict:
    return {
        "number": numero,
        "title": titulo,
        "labels": {"nodes": [{"name": n} for n in ["ready-for-agent", *labels]]},
        "parent": parent,
    }


def test_a_fila_mostra_o_dono_do_prd_ao_lado_de_cada_fatia(tmp_path):
    resposta = fila(
        fatia(907, "Esteira: rabo único", ["type:chore"], prd(902, "pedrorezendefig")),
        fatia(888, "Tecnologia: menção viva", ["type:fix"], None),
        fatia(664, "Fatia de PRD sem dono", [], prd(659)),
    )

    feito = rodar(tmp_path, resposta, "--fila")

    assert feito.returncode == 0, feito.stderr
    linhas = feito.stdout.splitlines()
    assert linhas[0] == "| # | título | labels | PRD | dono do PRD |"
    assert linhas[2:] == [
        "| 907 | Esteira: rabo único | type:chore | #902 | @pedrorezendefig |",
        "| 888 | Tecnologia: menção viva | type:fix | avulsa |  |",
        "| 664 | Fatia de PRD sem dono |  | #659 | sem dono |",
    ]


def test_a_fila_continua_so_com_pronta_sem_dono_e_desbloqueada(tmp_path):
    """O `-is:blocked` só vale na busca avançada; na comum volta a fatia bloqueada."""
    rodar(tmp_path, fila(), "--fila")

    chamada = (tmp_path / "gh.log").read_text(encoding="utf-8")
    assert "ISSUE_ADVANCED" in chamada
    assert (
        "q=repo:hsm/hospital-reunioes is:issue is:open label:ready-for-agent "
        "no:assignee -is:blocked"
    ) in chamada
