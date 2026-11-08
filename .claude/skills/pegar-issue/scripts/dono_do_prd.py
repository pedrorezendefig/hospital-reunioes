"""Dono do PRD de uma fatia, para o `/pegar-issue` (issue #904, decisão do fluxo).

O PRD nasce com dono: o `/to-prd` põe como assignee quem rodou. Pegar fatia de
PRD alheio não é proibido, mas se combina antes; este script dá o aviso, sem
bloquear o claim, e mostra o dono ao lado de cada fatia da fila.

Uso:
  python3 dono_do_prd.py <N>     imprime o aviso, ou nada se o card é de quem pega
                                 ou, sem dono, se a fatia é do próprio PRD, se o PRD
                                 não tem dono ou se a issue é avulsa
  python3 dono_do_prd.py --fila  imprime a fila ready-for-agent sem bloqueio, em
                                 tabela, com o PRD, o dono dele e quem está
                                 designado; com `designado_tira_da_fila`, só os
                                 cards de quem roda (o assignee é o dono do card)
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "onda-enxuta" / "scripts"))
import fluxo as config_do_fluxo  # noqa: E402


def _designado_tira_da_fila() -> bool:
    try:
        return bool(config_do_fluxo.carregar().get("designado_tira_da_fila"))
    except config_do_fluxo.Erro:
        return False


PAI = "parent { number assignees(first: 10) { nodes { login } } }"

CONSULTA_DA_ISSUE = f"""
query($owner: String!, $repo: String!, $n: Int!) {{
  viewer {{ login }}
  repository(owner: $owner, name: $repo) {{
    issue(number: $n) {{ number assignees(first: 10) {{ nodes {{ login }} }} {PAI} }}
  }}
}}
"""

# Busca avançada: na comum (`ISSUE`) o `-is:blocked` não filtra nada.
CONSULTA_DA_FILA = f"""
query($q: String!) {{
  search(query: $q, type: ISSUE_ADVANCED, first: 100) {{
    nodes {{ ... on Issue {{
      number title labels(first: 20) {{ nodes {{ name }} }}
      assignees(first: 10) {{ nodes {{ login }} }} {PAI}
    }} }}
  }}
}}
"""

FILTRO_DA_FILA = "is:issue is:open label:ready-for-agent -is:blocked"


def filtro_da_fila(designado_tira_da_fila: bool) -> str:
    """No Projeto em que o assignee e o dono do card (`designado_tira_da_fila` no fluxo.json), a fila e so a de quem roda."""
    return FILTRO_DA_FILA.replace(" -is:blocked", " assignee:@me -is:blocked") if designado_tira_da_fila else FILTRO_DA_FILA


def gh(*args: str) -> str:
    return subprocess.run(
        ["gh", *args], capture_output=True, text=True, encoding="utf-8", check=True
    ).stdout


def graphql(consulta: str, **variaveis: str | int) -> dict:
    campos = []
    for nome, valor in variaveis.items():
        campos += ["-F" if isinstance(valor, int) else "-f", f"{nome}={valor}"]
    return json.loads(gh("api", "graphql", "-f", f"query={consulta}", *campos))["data"]


def repositorio() -> str:
    return gh("repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner").strip()


def donos(issue: dict | None) -> list[str]:
    if not issue:
        return []
    return [a["login"] for a in (issue.get("assignees") or {}).get("nodes", [])]


def aviso(donos_do_card: list[str], donos_do_prd: list[str], login: str) -> str | None:
    """O aviso de uma linha, ou None quando não há o que combinar.

    O dono do card manda; sem dono no card, vale o dono do PRD.
    """
    if donos_do_card:
        if login in donos_do_card:
            return None
        return f"card de {', '.join('@' + d for d in donos_do_card)}; combine antes"
    if not donos_do_prd or login in donos_do_prd:
        return None
    return f"fatia do PRD de {', '.join('@' + d for d in donos_do_prd)}; combine antes"


def linha(issue: dict, com_designado: bool = True) -> str:
    labels = [
        n["name"] for n in issue["labels"]["nodes"] if n["name"] != "ready-for-agent"
    ]
    parent = issue["parent"]
    if parent:
        prd = f"#{parent['number']}"
        dono = ", ".join("@" + d for d in donos(parent)) or "sem dono"
    else:
        prd, dono = "avulsa", ""
    base = f"| {issue['number']} | {issue['title']} | {', '.join(labels)} | {prd} | {dono}"
    if not com_designado:
        return base + " |"
    designados = ", ".join("@" + d for d in donos(issue))
    return base + f" | {designados} |"


def tabela(issues: list[dict], com_designado: bool = True) -> str:
    """Onde o assignee e o dono (`designado_tira_da_fila`), a fila so tem card de quem roda: sem a coluna."""
    if com_designado:
        cabecalho = [
            "| # | título | labels | PRD | dono do PRD | designada a |",
            "|---|---|---|---|---|---|",
        ]
    else:
        cabecalho = ["| # | título | labels | PRD | dono do PRD |", "|---|---|---|---|---|"]
    return "\n".join(cabecalho + [linha(i, com_designado) for i in issues])


def main(argv: list[str]) -> int:
    if argv == ["--fila"]:
        so_os_meus = _designado_tira_da_fila()
        dados = graphql(CONSULTA_DA_FILA, q=f"repo:{repositorio()} {filtro_da_fila(so_os_meus)}")
        print(tabela(dados["search"]["nodes"], com_designado=not so_os_meus))
        return 0
    owner, repo = repositorio().split("/")
    dados = graphql(CONSULTA_DA_ISSUE, owner=owner, repo=repo, n=int(argv[0]))
    card = dados["repository"]["issue"]
    texto = aviso(donos(card), donos(card["parent"]), dados["viewer"]["login"])
    if texto:
        print(texto)
    return 0


if __name__ == "__main__":
    for fluxo in (sys.stdout, sys.stderr):  # Windows: o pipe sai em cp1252
        fluxo.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1:]))
