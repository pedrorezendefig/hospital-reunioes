#!/usr/bin/env python3
"""A conferência do lote: os PRs verdes de uma onda cabem juntos na main?

Na subida, o conflito aparece depois que um PR irmão da mesma onda entra na
main: o seguinte não cabe mais, fica de fora, e a onda paga outro corretor,
outro CI e outra subida. Aqui a mesma conta é feita antes, em memória (`git
merge-tree`), sem tocar em branch, PR nem working tree: a origin/main recebe
cada PR na ordem dada, que é a da subida. O PR que não cabe sai numa linha
`conflito:` com os arquivos e a base em que o corretor rebaseia, que é a
branch do irmão. Rebaseado sobre o irmão, ele entra na mesma subida, logo
depois dele.

Uso: python conferir_lote.py --prs <a> <b> [<c> ...]
Saída: exit 0 com `lote sem conflito` se todos cabem. Exit 1 com uma linha por
PR que não cabe:
  conflito: #B bate em #A em: <arquivos>. Base do corretor: origin/<branch do A>.
  conflito: #B bate na main em: <arquivos>. Base do corretor: origin/main.
  conflito: #C bate em #A #B em: <arquivos>. Sem base única: ...
A base é o irmão em que o PR bate; batendo em mais de um, é o último deles se
ele já carrega os outros (foi rebaseado sobre eles), senão não há base e o PR
segue o caminho do conflito na subida. O PR que não cabe fica fora da conta
dos seguintes: corrija uma linha e rode de novo. Exit 2 em erro do gh ou do git.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def git(raiz: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(["git", *args], cwd=str(raiz), capture_output=True, text=True, encoding="utf-8",
                          errors="replace")
    if check and proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} -> {proc.returncode}: {proc.stderr.strip()[:300]}")
    return proc


def juntar(raiz: Path, a: str, b: str) -> tuple[str | None, list[str]]:
    """Junta `b` em `a` em memória. Devolve (árvore, []) se cabe e (None, arquivos) se bate."""
    proc = git(raiz, "merge-tree", "--write-tree", "--name-only", "--no-messages", a, b, check=False)
    linhas = proc.stdout.splitlines()
    if proc.returncode == 0:
        return linhas[0], []
    if proc.returncode == 1:
        return None, sorted(x for x in linhas[1:] if x)
    raise RuntimeError(f"git merge-tree {a} {b} -> {proc.returncode}: {proc.stderr.strip()[:300]}")


def contem(raiz: Path, dentro: str, de: str) -> bool:
    return git(raiz, "merge-base", "--is-ancestor", dentro, de, check=False).returncode == 0


def conferir(raiz: Path, main: str, prs: list[dict]) -> list[str]:
    """As linhas `conflito:` do lote, na ordem dos PRs; vazia se todos cabem.
    Cada PR é {"number", "branch", "head"}."""
    linhas = []
    pilha = git(raiz, "rev-parse", main).stdout.strip()  # a main com os PRs que couberam até aqui
    dentro: list[dict] = []
    for pr in prs:
        arvore, arquivos = juntar(raiz, pilha, pr["head"])
        if arvore:
            pilha = git(raiz, "-c", "user.name=conferir_lote", "-c", "user.email=conferir_lote@local",
                        "commit-tree", arvore, "-p", pilha, "-p", pr["head"], "-m",
                        f"lote com o #{pr['number']}").stdout.strip()
            dentro.append(pr)
            continue
        na_main = juntar(raiz, main, pr["head"])[1]
        if na_main:
            linhas.append(f"conflito: #{pr['number']} bate na main em: {', '.join(na_main)}. "
                          "Base do corretor: origin/main.")
            continue
        batidos = [d for d in dentro if juntar(raiz, d["head"], pr["head"])[1]]
        ultimo = batidos[-1] if batidos else None
        em = " ".join(f"#{d['number']}" for d in batidos) or "o lote"
        if ultimo and all(contem(raiz, d["head"], ultimo["head"]) for d in batidos[:-1]):
            fim = f"Base do corretor: origin/{ultimo['branch']}."
        else:
            fim = "Sem base única: entra por último na subida e segue o caminho do conflito na subida."
        linhas.append(f"conflito: #{pr['number']} bate em {em} em: {', '.join(arquivos)}. {fim}")
    return linhas


def prs_do_github(raiz: Path, numeros: list[int]) -> list[dict]:
    """Busca a main e a branch de cada PR e devolve os PRs com o head que veio."""
    git(raiz, "fetch", "-q", "origin", "main")
    prs = []
    for n in numeros:
        proc = subprocess.run(["gh", "pr", "view", str(n), "--json", "headRefName"], cwd=str(raiz),
                              capture_output=True, text=True, encoding="utf-8", errors="replace")
        if proc.returncode != 0:
            raise RuntimeError(f"gh pr view {n} -> {proc.returncode}: {proc.stderr.strip()[:300]}")
        branch = json.loads(proc.stdout)["headRefName"]
        git(raiz, "fetch", "-q", "origin", f"+refs/heads/{branch}:refs/remotes/origin/{branch}")
        prs.append({"number": n, "branch": branch,
                    "head": git(raiz, "rev-parse", f"origin/{branch}").stdout.strip()})
    return prs


def main() -> int:
    ap = argparse.ArgumentParser(description="Confere se os PRs de um lote cabem juntos na main.")
    ap.add_argument("--prs", nargs="+", type=int, required=True, help="PRs na ordem da subida")
    args = ap.parse_args()
    try:
        raiz = Path(subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True,
                                   check=True).stdout.strip())
        linhas = conferir(raiz, "origin/main", prs_do_github(raiz, args.prs))
    except (RuntimeError, subprocess.CalledProcessError, KeyError, ValueError) as e:
        print(f"erro: {e}", file=sys.stderr)
        return 2
    if not linhas:
        print("lote sem conflito: " + " ".join(f"#{n}" for n in args.prs) + " cabem juntos na main.")
        return 0
    print("\n".join(linhas))
    return 1


if __name__ == "__main__":
    sys.exit(main())
