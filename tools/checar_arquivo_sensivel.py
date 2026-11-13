#!/usr/bin/env python3
"""Recusa arquivo de dado que o PR adiciona fora das pastas liberadas (issue #1287).

O repositório é público: PDF, planilha, dump ou `.env` que entra por engano
fica no histórico para sempre. Esta guarda compara a branch com a base (por
padrão `origin/main`) e sai com código 1 nomeando cada arquivo ADICIONADO com
extensão bloqueada fora das pastas que existem para isso. A extensão é
comparada em minúscula (`.PDF` também trava). Renomear conta como adicionar no
caminho novo; editar arquivo que a base já tem não conta.

As pastas liberadas também têm trava (issue #1653): na pasta das tabelas de
preço de Contas médicas, um arquivo com o nome de uma operadora real no
caminho é recusado (a fixture usa operadora inventada, ALFA, BETA, GAMA), e os
POPs reais do Centro Cirúrgico não entram mais em `docs/pops/`: vivem em
`local/`, fora do git.

Roda no CI de todo pull request. Só usa `git`.

Uso: python3 tools/checar_arquivo_sensivel.py [--base origin/main] [--head HEAD]
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import PurePosixPath

EXTENSOES = {
    ".pdf", ".doc", ".docx", ".csv", ".xls", ".xlsx", ".sql",
    ".dump", ".bak", ".sqlite", ".db", ".env",
}

PASTAS_LIBERADAS = (
    "hospital-reunioes/supabase/migrations/",
    "docs/comunicacao/",
    "hospital-reunioes/backend/tests/fixtures/",
)

PASTA_DAS_TABELAS = "hospital-reunioes/backend/tests/fixtures/contas_medicas/tabelas/"

# Operadoras reais com contrato carregado em Contas médicas: o nome delas no
# caminho de uma tabela de preço indica arquivo de contrato real.
OPERADORAS_REAIS = {"assim", "leve", "unimed"}


def tabela_de_operadora_real(caminho: str) -> bool:
    if not caminho.startswith(PASTA_DAS_TABELAS):
        return False
    palavras = re.split(r"[^a-z0-9]+", caminho[len(PASTA_DAS_TABELAS):].lower())
    return not OPERADORAS_REAIS.isdisjoint(palavras)


def bloqueado(caminho: str) -> bool:
    if tabela_de_operadora_real(caminho):
        return True
    if caminho.startswith(PASTAS_LIBERADAS):
        return False
    nome = PurePosixPath(caminho).name.lower()
    # `.env` puro e `.env.local` não têm sufixo `.env` para o pathlib; o
    # `.env.example` é o modelo sem valor que o repositório versiona.
    if nome == ".env" or (nome.startswith(".env.") and nome != ".env.example"):
        return True
    return PurePosixPath(nome).suffix in EXTENSOES


def adicionados(base: str, head: str) -> list[str]:
    proc = subprocess.run(
        ["git", "-c", "core.quotePath=false", "diff", "--name-only", "--no-renames",
         "--diff-filter=A", f"{base}...{head}"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git diff: {proc.stderr.strip()}")
    return proc.stdout.splitlines()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", default="origin/main", help="referência da base (default: origin/main)")
    ap.add_argument("--head", default="HEAD", help="referência da branch (default: HEAD)")
    args = ap.parse_args(argv)
    achados = [c for c in adicionados(args.base, args.head) if bloqueado(c)]
    if achados:
        for caminho in achados:
            print(f"arquivo sensível adicionado: {caminho}")
        print(
            "O repositório é público e não aceita dado real. Tire o arquivo do PR;"
            " se for fixture sintética, ponha numa pasta liberada ("
            + ", ".join(PASTAS_LIBERADAS)
            + "), com operadora inventada (ALFA, BETA, GAMA) no nome da tabela de preço."
            " O dado real vai para local/, fora do git."
        )
        return 1
    print(f"arquivos: nenhum arquivo sensível adicionado contra {args.base}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
