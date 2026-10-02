"""Dono do PRD de uma fatia, para o `/pegar-issue` (issue #904, ADR 0061).

O PRD nasce com dono: o `/to-prd` põe como assignee quem rodou. Pegar fatia de
PRD alheio não é proibido, mas se combina antes; este script dá o aviso, sem
bloquear o claim, e mostra o dono ao lado de cada fatia da fila.

Uso:
  python3 dono_do_prd.py <N>     imprime o aviso, ou nada se a fatia é do próprio
                                 PRD, se o PRD não tem dono ou se a issue é avulsa
  python3 dono_do_prd.py --fila  imprime a fila ready-for-agent sem dono e sem
                                 bloqueio, em tabela, com o PRD e o dono dele
"""

from __future__ import annotations

import json
import subprocess
import sys

PAI = "parent { number assignees(first: 10) { nodes { login } } }"

CONSULTA_DA_ISSUE = f"""
query($owner: String!, $repo: String!, $n: Int!) {{
  viewer {{ login }}
  repository(owner: $owner, name: $repo) {{ issue(number: $n) {{ number {PAI} }} }}
}}
"""

# Busca avançada: na comum (`ISSUE`) o `-is:blocked` não filtra nada.
CONSULTA_DA_FILA = f"""
query($q: String!) {{
  search(query: $q, type: ISSUE_ADVANCED, first: 100) {{
    nodes {{ ... on Issue {{ number title labels(first: 20) {{ nodes {{ name }} }} {PAI} }} }}
  }}
}}
"""

FILTRO_DA_FILA = "is:issue is:open label:ready-for-agent no:assignee -is:blocked"


def gh(*args: str) -> str:
    return subprocess.run(
        ["gh", *args], capture_output=True, text=True, check=True
    ).stdout


def graphql(consulta: str, **variaveis: str | int) -> dict:
    campos = []
    for nome, valor in variaveis.items():
        campos += ["-F" if isinstance(valor, int) else "-f", f"{nome}={valor}"]
    return json.loads(gh("api", "graphql", "-f", f"query={consulta}", *campos))["data"]


def repositorio() -> str:
    return gh("repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner").strip()


def donos(parent: dict | None) -> list[str]:
    if not parent:
        return []
    return [a["login"] for a in parent["assignees"]["nodes"]]


def aviso(donos_do_prd: list[str], login: str) -> str | None:
    """O aviso de uma linha, ou None quando não há o que combinar."""
    if not donos_do_prd or login in donos_do_prd:
        return None
    return f"fatia do PRD de {', '.join('@' + d for d in donos_do_prd)}; combine antes"


def linha(issue: dict) -> str:
    labels = [
        n["name"] for n in issue["labels"]["nodes"] if n["name"] != "ready-for-agent"
    ]
    parent = issue["parent"]
    if parent:
        prd = f"#{parent['number']}"
        dono = ", ".join("@" + d for d in donos(parent)) or "sem dono"
    else:
        prd, dono = "avulsa", ""
    return f"| {issue['number']} | {issue['title']} | {', '.join(labels)} | {prd} | {dono} |"


def tabela(issues: list[dict]) -> str:
    cabecalho = ["| # | título | labels | PRD | dono do PRD |", "|---|---|---|---|---|"]
    return "\n".join(cabecalho + [linha(i) for i in issues])


def main(argv: list[str]) -> int:
    if argv == ["--fila"]:
        dados = graphql(CONSULTA_DA_FILA, q=f"repo:{repositorio()} {FILTRO_DA_FILA}")
        print(tabela(dados["search"]["nodes"]))
        return 0
    owner, repo = repositorio().split("/")
    dados = graphql(CONSULTA_DA_ISSUE, owner=owner, repo=repo, n=int(argv[0]))
    texto = aviso(donos(dados["repository"]["issue"]["parent"]), dados["viewer"]["login"])
    if texto:
        print(texto)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
