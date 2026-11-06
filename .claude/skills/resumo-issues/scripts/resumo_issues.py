"""Resumo das issues abertas por pessoa, agrupadas pelo PRD, o `/resumo-issues`.

Só leitura. A coleta (uma consulta GraphQL) fica em `coletar`; o miolo puro é
`montar(issues)`, que os testes alimentam com dados de mentira.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys

APELIDOS = {"pedrorezendefig": "Pedro", "pedroribbe": "Rib", "lucassampaioc1": "Lucas"}
SEM_DONO = "Sem responsável"
RE_O_QUE_MUDA = re.compile(r"\*\*O que muda:\*\*\s*(.+)")
LARGURA = 110
RE_CONTROLE = re.compile(r"[\x00-\x1f\x7f]")


def limpo(t: str) -> str:
    """Texto de issue é de terceiros: sem caracteres de controle nem quebra de linha."""
    return RE_CONTROLE.sub(" ", t).strip()


def nome(login: str) -> str:
    return APELIDOS.get(login, login)


def eh_prd(i: dict) -> bool:
    return i["title"].startswith("PRD")


def o_que_muda(i: dict) -> str | None:
    """A linha "O que muda" do bloco Para o diretor, cortada em LARGURA."""
    m = RE_O_QUE_MUDA.search(i.get("body") or "")
    if not m:
        return None
    texto = limpo(m.group(1))
    return texto if len(texto) <= LARGURA else texto[: LARGURA - 3].rstrip() + "..."


def _titulo_prd(t: str) -> str:
    t = re.sub(r"^PRD:\s*", "", limpo(t))
    return t if len(t) <= 80 else t[:77].rstrip() + "..."


def montar(issues: list[dict], projeto: str = "Projeto") -> str:
    pais = {i["parent"]["number"] for i in issues if i.get("parent")}
    pessoas: dict[str, list[dict]] = {}
    for i in issues:
        for dono in i["assignees"] or [None]:
            pessoas.setdefault(nome(dono) if dono else SEM_DONO, []).append(i)

    # Pessoas com mais cards primeiro; quem não tem dono vai por último.
    ordem = sorted(pessoas, key=lambda p: (p == SEM_DONO, -len(pessoas[p]), p))
    linhas = [f"{projeto}: {len(issues)} abertas", ""]
    for p in ordem:
        cards = pessoas[p]
        linhas.append(f"{p} ({len(cards)})")
        grupos: dict[int | None, list[dict]] = {}
        titulos: dict[int, str] = {}
        for i in cards:
            if i.get("parent"):
                chave = i["parent"]["number"]
                titulos[chave] = i["parent"]["title"]
            elif eh_prd(i) or i["number"] in pais:
                chave = i["number"]
                titulos[chave] = i["title"]
            else:
                chave = None
            grupos.setdefault(chave, []).append(i)
        for chave in sorted(grupos, key=lambda k: (k is None, -(k or 0))):
            if chave is None:
                linhas.append("  Avulsas")
            else:
                linhas.append(f"  PRD #{chave} {_titulo_prd(titulos[chave])}")
            for i in sorted(grupos[chave], key=lambda x: x["number"]):
                titulo = "(o PRD)" if i["number"] == chave else limpo(i["title"])
                linhas.append(f"    #{i['number']} {titulo}")
                muda = o_que_muda(i)
                if muda and muda != limpo(i["title"]):
                    linhas.append(f"      muda: {muda}")
        linhas.append("")
    return "\n".join(linhas).rstrip() + "\n"


CONSULTA = """
query($q: String!) {
  search(query: $q, type: ISSUE, first: 100) {
    issueCount
    nodes { ... on Issue {
      number title body
      assignees(first: 10) { nodes { login } }
      parent { number title }
    } }
  }
}
"""


def nome_do_projeto(repo: str) -> str:
    """O `nome` do .claude/fluxo.json que o instalador gera; sem ele, o nome do repo."""
    try:
        raiz = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True).stdout.strip()
        with open(f"{raiz}/.claude/fluxo.json", encoding="utf-8") as f:
            return json.load(f)["nome"]
    except (OSError, subprocess.CalledProcessError, KeyError, ValueError):
        return repo.split("/")[-1]


def coletar() -> tuple[list[dict], str]:
    repo = subprocess.run(
        ["gh", "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"],
        capture_output=True, text=True, encoding="utf-8", check=True,
    ).stdout.strip()
    saida = subprocess.run(
        ["gh", "api", "graphql", "-f", f"query={CONSULTA}", "-f", f"q=repo:{repo} is:issue is:open"],
        capture_output=True, text=True, encoding="utf-8", check=True,
    ).stdout
    busca = json.loads(saida)["data"]["search"]
    if busca["issueCount"] > 100:
        print(f"Aviso: {busca['issueCount']} abertas, o resumo mostra só as 100 mais recentes.", file=sys.stderr)
    issues = [
        {
            "number": n["number"],
            "title": n["title"],
            "body": n["body"],
            "assignees": [a["login"] for a in n["assignees"]["nodes"]],
            "parent": n["parent"],
        }
        for n in busca["nodes"]
    ]
    return issues, nome_do_projeto(repo)


if __name__ == "__main__":
    issues, projeto = coletar()
    print(montar(issues, projeto), end="")
