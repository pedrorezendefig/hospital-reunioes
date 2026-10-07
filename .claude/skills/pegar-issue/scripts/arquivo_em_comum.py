"""Avisa, sem bloquear, a issue que toca arquivo de outra em andamento, para o `/pegar-issue`.

Nasceu no #970 recusando o claim (ADR 0068). Pela ADR 0068, arquivo em comum
não separa fatias: o único separador é a dependência, que quem fatia escreve
como `blocked_by` nativo (ADR 0068), e o conflito de texto se resolve no rabo
PR a PR. Por isso o script só imprime um aviso de uma linha com os arquivos que
coincidem, não grava dependência e não impede o claim.

Os arquivos de uma issue são os caminhos que o corpo cita entre crases
(`ship/SKILL.md`, `ouvidoria_setor.py:102`); os de uma fatia em andamento somam
os do PR aberto que a fecha. Um caminho casa com outro quando é igual a ele ou
é o fim dele depois de uma barra: `ship/SKILL.md` casa com
`.claude/skills/ship/SKILL.md`, e `tdd/SKILL.md` não.

Uso:
  python3 arquivo_em_comum.py <N>   sem arquivo em comum: nada
                                     com arquivo em comum: uma linha de aviso
                                     sempre saída 0
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
    nodes { ... on Issue { number body
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
    coincidencias = []
    for outra in dados["search"]["nodes"]:
        if outra["number"] == n:
            continue
        comuns = em_comum(meus, arquivos_da_fatia(outra))
        if comuns:
            coincidencias.append(f"#{outra['number']} ({', '.join(comuns)})")
    if coincidencias:
        print("aviso, sem bloqueio (ADR 0068): arquivo em comum com fatia em andamento: "
              + "; ".join(coincidencias))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
