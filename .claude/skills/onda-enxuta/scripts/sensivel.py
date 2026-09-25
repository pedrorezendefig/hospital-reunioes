#!/usr/bin/env python3
"""Cruza os arquivos de um PR com a lista revisao-sensivel.txt da skill.

Uso: python sensivel.py <PR> [--lista <arquivo>]
Saída: um arquivo sensível por linha (com o glob que casou). Exit 0 se houver
algum, 1 se não houver, 2 em erro. Globs com prefixo "+" só casam quando o PR
criou o arquivo (status "added" na API do GitHub).
"""
import argparse
import fnmatch
import json
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")


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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pr", type=int)
    ap.add_argument("--lista", default=str(Path(__file__).resolve().parent.parent / "revisao-sensivel.txt"))
    args = ap.parse_args()

    globs = []
    for linha in Path(args.lista).read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#"):
            continue
        so_novo = linha.startswith("+")
        globs.append((linha.lstrip("+"), so_novo))

    try:
        repo = subprocess.run(["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"],
                              capture_output=True, text=True, check=True, encoding="utf-8").stdout.strip()
        saida = subprocess.run(["gh", "api", f"repos/{repo}/pulls/{args.pr}/files", "--paginate"],
                               capture_output=True, text=True, check=True, encoding="utf-8").stdout
    except subprocess.CalledProcessError as e:
        print(f"erro ao consultar o PR #{args.pr}: {e.stderr.strip()}", file=sys.stderr)
        return 2
    arquivos = json.loads(saida)

    achados = []
    for f in arquivos:
        nome, status = f["filename"], f.get("status", "")
        for glob, so_novo in globs:
            if so_novo and status != "added":
                continue
            if casa(nome, glob):
                achados.append((nome, ("+" if so_novo else "") + glob))
                break

    for nome, glob in achados:
        print(f"{nome}\t({glob})")
    return 0 if achados else 1


if __name__ == "__main__":
    sys.exit(main())
