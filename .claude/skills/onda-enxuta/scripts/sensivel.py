#!/usr/bin/env python3
"""Cruza os arquivos de um PR com a lista revisao-sensivel.txt da skill e varre o head.

Uso: python sensivel.py <PR> [--lista <arquivo>]
Saída: um arquivo sensível por linha (com o glob ou o motivo que casou). Exit 0
se houver algum, 1 se não houver, 2 em qualquer erro (falha fechada: Python
abaixo do 3.12, `gh`, `git` ou a varredura que quebra). Globs com prefixo "+" só casam
quando o PR criou o arquivo (status "added" na API do GitHub).

Além da lista, a varredura (ADR 0064, decisão 4): router de backend tocado pelo
PR com rota cuja cadeia de Depends não chega a get_current_user, lido no head
do PR, e arquivo do frontend tocado que é route handler (route.ts) ou server
action ("use server"). Rota nova com login segue fora.
"""
from __future__ import annotations

import argparse
import ast
import fnmatch
import io
import json
import re
import subprocess
import sys
import tarfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

RAIZ = Path(__file__).resolve().parents[4]
APP = "hospital-reunioes/backend/app"
FRONT = "hospital-reunioes/frontend/src"
METODOS_DE_ROTA = {"get", "post", "put", "patch", "delete", "head", "options", "api_route", "websocket"}
# Rota sem login que não precisa do revisor de segurança por PR (caminho relativo a APP).
FORA_DA_LISTA = {"routers/health.py"}
USE_SERVER = re.compile(r"""^\s*['"]use server['"]""", re.M)


def casa(caminho: str, glob: str) -> bool:
    caminho = caminho.replace("\\", "/")
    if "**" in glob:
        # fnmatch trata * como qualquer coisa inclusive /, então ** e * viram o mesmo
        return fnmatch.fnmatch(caminho, glob.replace("**", "*"))
    if "/" not in glob:
        return fnmatch.fnmatch(Path(caminho).name, glob)
    # um * só não cruza diretório
    partes_c, partes_g = caminho.split("/"), glob.split("/")
    if len(partes_c) != len(partes_g):
        return False
    return all(fnmatch.fnmatch(c, g) for c, g in zip(partes_c, partes_g))


def ler_globs(lista: Path) -> list[tuple[str, bool]]:
    globs = []
    for linha in Path(lista).read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#"):
            continue
        globs.append((linha.lstrip("+"), linha.startswith("+")))
    return globs


def _alvo_do_depends(no: ast.AST) -> str | None:
    """`Depends(x)`, `Depends(fabrica(...))` ou `Depends(mod.x)` devolve o nome de x."""
    if not isinstance(no, ast.Call) or not no.args:
        return None
    if getattr(no.func, "id", getattr(no.func, "attr", None)) not in ("Depends", "Security"):
        return None
    alvo = no.args[0].func if isinstance(no.args[0], ast.Call) else no.args[0]
    return getattr(alvo, "id", getattr(alvo, "attr", None))


def depends(no: ast.AST) -> set[str]:
    return {nome for nome in map(_alvo_do_depends, ast.walk(no)) if nome}


def rotas_sem_login(fontes: dict[str, str]) -> dict[str, list[str]]:
    """Fontes do app (caminho relativo a app/ -> código). Router -> rotas sem login."""
    arvores = {caminho: ast.parse(codigo) for caminho, codigo in fontes.items() if caminho.endswith(".py")}
    grafo: dict[str, set[str]] = {}
    for arvore in arvores.values():
        for no in ast.walk(arvore):
            if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)):
                grafo.setdefault(no.name, set()).update(depends(no))
    com_login, cresceu = {"get_current_user"}, True
    while cresceu:
        novos = {nome for nome, alvos in grafo.items() if alvos & com_login} - com_login
        com_login |= novos
        cresceu = bool(novos)

    achados = {}
    for caminho in sorted(c for c in arvores if c.startswith("routers/")):
        arvore = arvores[caminho]
        do_router = set()
        for no in arvore.body:
            if isinstance(no, ast.Assign) and getattr(getattr(no.value, "func", None), "id", None) == "APIRouter":
                do_router |= depends(no.value)
        abertas = []
        for no in ast.walk(arvore):
            if not isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            rota = [d for d in no.decorator_list if getattr(getattr(d, "func", None), "attr", None) in METODOS_DE_ROTA]
            if rota and not (do_router | depends(no.args) | set().union(*map(depends, rota))) & com_login:
                abertas.append(no.name)
        if abertas:
            achados[caminho] = abertas
    return achados


def porta_do_front(nome: str, codigo: str) -> bool:
    """Route handler do Next ou server action: código do servidor chamável sem login."""
    return Path(nome).stem == "route" or bool(USE_SERVER.search(codigo))


def fontes_do_commit(ref: str, caminhos: list[str], raiz: Path = RAIZ) -> dict[str, str]:
    """Texto dos arquivos sob `caminhos` no commit `ref` (caminho a partir da raiz do repo)."""
    tar = subprocess.run(["git", "-C", str(raiz), "archive", "--format=tar", ref, "--", *caminhos],
                         capture_output=True, check=True).stdout
    fontes = {}
    with tarfile.open(fileobj=io.BytesIO(tar)) as arquivo:
        for membro in arquivo.getmembers():
            if membro.isfile() and membro.name.endswith((".py", ".ts", ".tsx", ".js", ".jsx")):
                fontes[membro.name] = arquivo.extractfile(membro).read().decode("utf-8", errors="replace")
    return fontes


def sensiveis(arquivos: list[dict], globs: list[tuple[str, bool]], fontes_do_head) -> list[tuple[str, str]]:
    """Arquivos do PR que pedem o revisor de segurança: pela lista e pela varredura do head.

    `fontes_do_head(caminhos)` devolve {caminho a partir da raiz: código} no head do PR;
    só é chamada quando o PR toca router do backend ou código do frontend.
    """
    achados, a_varrer = [], []
    for f in arquivos:
        nome, status = f["filename"], f.get("status", "")
        casou = next(((g, so_novo) for g, so_novo in globs if (not so_novo or status == "added") and casa(nome, g)), None)
        if casou:
            achados.append((nome, ("+" if casou[1] else "") + casou[0]))
        elif status != "removed" and (
            (nome.startswith(f"{APP}/routers/") and nome.endswith(".py"))
            or (nome.startswith(f"{FRONT}/") and nome.endswith((".ts", ".tsx", ".js", ".jsx")))
        ):
            a_varrer.append(nome)
    if not a_varrer:
        return achados

    backend = [n for n in a_varrer if n.startswith(APP)]
    frontend = [n for n in a_varrer if n.startswith(FRONT)]
    fontes = fontes_do_head(([APP] if backend else []) + frontend)
    abertas = rotas_sem_login({c[len(APP) + 1:]: v for c, v in fontes.items() if c.startswith(f"{APP}/")})
    for nome in a_varrer:
        relativo = nome[len(APP) + 1:]
        if nome in backend and relativo in abertas and relativo not in FORA_DA_LISTA:
            achados.append((nome, "rota sem login no head: " + ", ".join(abertas[relativo])))
        elif nome in frontend and porta_do_front(nome, fontes.get(nome, "")):
            achados.append((nome, "route handler ou server action no head"))
    ordem = {f["filename"]: i for i, f in enumerate(arquivos)}
    return sorted(achados, key=lambda a: ordem[a[0]])


def main() -> int:
    if sys.version_info < (3, 12):
        print(f"sensivel.py exige Python 3.12 ou mais novo (este é {sys.version.split()[0]})", file=sys.stderr)
        return 2
    ap = argparse.ArgumentParser()
    ap.add_argument("pr", type=int)
    ap.add_argument("--lista", default=str(Path(__file__).resolve().parent.parent / "revisao-sensivel.txt"))
    args = ap.parse_args()

    def gh(*argumentos: str) -> str:
        return subprocess.run(["gh", *argumentos], capture_output=True, text=True, check=True,
                              encoding="utf-8").stdout

    try:
        globs = ler_globs(Path(args.lista))
        repo = gh("repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner").strip()
        saida = gh("api", f"repos/{repo}/pulls/{args.pr}/files", "--paginate")
        head = gh("api", f"repos/{repo}/pulls/{args.pr}", "--jq", ".head.sha").strip()
        arquivos = json.loads(saida)

        def fontes_do_head(caminhos: list[str]) -> dict[str, str]:
            subprocess.run(["git", "-C", str(RAIZ), "fetch", "--quiet", "--no-write-fetch-head", "origin", head],
                           capture_output=True, text=True, check=True)
            return fontes_do_commit(head, caminhos)

        achados = sensiveis(arquivos, globs, fontes_do_head)
    except subprocess.CalledProcessError as e:
        erro = e.stderr.decode() if isinstance(e.stderr, bytes) else e.stderr
        print(f"erro ao consultar o PR #{args.pr}: {(erro or '').strip()}", file=sys.stderr)
        return 2
    except Exception as e:  # falha fechada: erro na varredura não vira "não sensível"
        print(f"varredura do PR #{args.pr} falhou: {type(e).__name__}: {e}", file=sys.stderr)
        return 2

    for nome, motivo in achados:
        print(f"{nome}\t({motivo})")
    return 0 if achados else 1


if __name__ == "__main__":
    sys.exit(main())
