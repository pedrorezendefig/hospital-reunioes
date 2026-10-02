"""Dono do PRD de uma fatia, para o `/pegar-issue` (issue #904, ADR 0061).

O PRD nasce com dono: o `/to-prd` põe como assignee quem rodou. Pegar fatia de
PRD alheio não é proibido, mas se combina antes; este script dá o aviso, sem
bloquear o claim.

Uso:
  python3 dono_do_prd.py <N>   imprime o aviso, ou nada se a fatia é do próprio
                               PRD, se o PRD não tem dono ou se a issue é avulsa
"""

from __future__ import annotations

import json
import subprocess
import sys

CONSULTA_DA_ISSUE = """
query($owner: String!, $repo: String!, $n: Int!) {
  viewer { login }
  repository(owner: $owner, name: $repo) {
    issue(number: $n) {
      number
      parent { number assignees(first: 10) { nodes { login } } }
    }
  }
}
"""


def gh(*args: str) -> str:
    return subprocess.run(
        ["gh", *args], capture_output=True, text=True, check=True
    ).stdout


def graphql(consulta: str, **variaveis: str) -> dict:
    campos = []
    for nome, valor in variaveis.items():
        campos += ["-F" if nome == "n" else "-f", f"{nome}={valor}"]
    return json.loads(gh("api", "graphql", "-f", f"query={consulta}", *campos))["data"]


def donos(parent: dict | None) -> list[str]:
    if not parent:
        return []
    return [a["login"] for a in parent["assignees"]["nodes"]]


def aviso(donos_do_prd: list[str], login: str) -> str | None:
    """O aviso de uma linha, ou None quando não há o que combinar."""
    if not donos_do_prd or login in donos_do_prd:
        return None
    return f"fatia do PRD de {', '.join('@' + d for d in donos_do_prd)}; combine antes"


def main(argv: list[str]) -> int:
    owner, repo = gh(
        "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"
    ).strip().split("/")
    dados = graphql(CONSULTA_DA_ISSUE, owner=owner, repo=repo, n=argv[0])
    parent = dados["repository"]["issue"]["parent"]
    texto = aviso(donos(parent), dados["viewer"]["login"])
    if texto:
        print(texto)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
