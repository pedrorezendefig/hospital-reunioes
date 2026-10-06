"""Recusa issue que toca arquivo de outra em andamento, para o `/pegar-issue` (issue #970).

Sem parada humana até produção (ADR 0063), duas fatias que mexem no mesmo
arquivo não andam ao mesmo tempo: a segunda ganha a dependência nativa
"Bloqueada por" da primeira (ADR 0028) e o `/pegar-issue` não faz o claim. Ela
volta à fila sozinha quando a primeira fecha.

Os arquivos de uma issue são os caminhos que o corpo cita entre crases
(`ship/SKILL.md`, `ouvidoria_setor.py:102`); os de uma fatia em andamento somam
os do PR aberto que a fecha. Um caminho casa com outro quando é igual a ele ou
é o fim dele depois de uma barra: `ship/SKILL.md` casa com
`.claude/skills/ship/SKILL.md`, e `tdd/SKILL.md` não.

Uso:
  python3 arquivo_em_comum.py <N>   sem arquivo em comum: nada, saída 0
                                     com arquivo em comum: marca "Bloqueada por"
                                     em cada fatia, uma linha por fatia, saída 1
"""

from __future__ import annotations

import json
import re
import subprocess
import sys

CONSULTA = """
query($owner: String!, $repo: String!, $n: Int!, $q: String!) {
  repository(owner: $owner, name: $repo) { issue(number: $n) { body } }
  search(query: $q, type: ISSUE, first: 100) {
    nodes { ... on Issue { number databaseId body
      closedByPullRequestsReferences(first: 5) { nodes { files(first: 100) { nodes { path } } } }
    } }
  }
}
"""

# Entre crases, sem espaço, terminando em extensão que começa por letra, com o
# `:linha` opcional: `fechar_onda.py:466`, não `v0.163.3` nem `/ship`.
CITACAO = re.compile(r"`(?:\./)?([\w.\-/]+\.[A-Za-z]\w*)(?::\d+(?:-\d+)?)?`")


def gh(*args: str) -> str:
    return subprocess.run(
        ["gh", *args], capture_output=True, text=True, check=True
    ).stdout


def citados(corpo: str | None) -> set[str]:
    return set(CITACAO.findall(corpo or ""))


def arquivos_da_fatia(issue: dict) -> set[str]:
    prs = issue["closedByPullRequestsReferences"]["nodes"]
    return citados(issue["body"]) | {f["path"] for pr in prs for f in pr["files"]["nodes"]}


def casa(a: str, b: str) -> bool:
    return a == b or a.endswith("/" + b) or b.endswith("/" + a)


def em_comum(meus: set[str], dela: set[str]) -> list[str]:
    """Os caminhos da outra fatia que casam com algum dos meus."""
    return sorted(d for d in dela if any(casa(m, d) for m in meus))


def main(argv: list[str]) -> int:
    n = int(argv[0])
    repo = gh("repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner").strip()
    owner, nome = repo.split("/")
    dados = json.loads(gh(
        "api", "graphql", "-f", f"query={CONSULTA}",
        "-f", f"owner={owner}", "-f", f"repo={nome}", "-F", f"n={n}",
        "-f", f"q=repo:{repo} is:issue is:open label:in-progress",
    ))["data"]
    meus = citados(dados["repository"]["issue"]["body"])
    recusada = False
    for outra in dados["search"]["nodes"]:
        if outra["number"] == n:
            continue
        comuns = em_comum(meus, arquivos_da_fatia(outra))
        if not comuns:
            continue
        gh("api", "--method", "POST", f"repos/{repo}/issues/{n}/dependencies/blocked_by",
           "-F", f"issue_id={outra['databaseId']}")
        print(f"bloqueada por #{outra['number']}: arquivo em comum com a fatia em andamento "
              f"({', '.join(comuns)})")
        recusada = True
    return 1 if recusada else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
