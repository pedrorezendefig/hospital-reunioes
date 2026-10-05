#!/usr/bin/env python3
"""Diz se o CI vermelho de um PR foi o GitHub sem runner e, se foi, pede o rerun (issue #953).

Num incidente do Actions o job fica 15 min na fila e o GitHub o cancela com a
anotacao "The job was not acquired by Runner of type hosted even after multiple
attempts", sem rodar nenhum passo. Isso nao e falha de codigo: nao chame o
corretor nem conte tentativa, repita o run.

Uso: python ci_sem_runner.py <PR>
Saida: exit 0 se TODO check vermelho foi cancelado sem runner (rerun pedido, ou
o run ainda esta andando): rode o `gh pr checks --watch` de novo. Exit 1 se ha
vermelho de codigo, ou nenhum vermelho: siga o fluxo normal. Exit 2 em erro.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from collections.abc import Callable

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SEM_RUNNER = "not acquired by Runner"
REPETICOES_MAX = 3  # cada rodada sem runner leva ~15 min de fila
VERDE_OU_PENDENTE = ("SUCCESS", "NEUTRAL", "SKIPPED", "")


def ids(check: dict) -> tuple[str, str] | None:
    """(run, job) do link do check; None em status externo."""
    m = re.search(r"/actions/runs/(\d+)/job/(\d+)", check.get("detailsUrl") or "")
    return (m.group(1), m.group(2)) if m else None


def runs_sem_runner(vermelhos: list[dict], anotacoes: Callable[[str], list[str]]) -> set[str]:
    """Runs a repetir quando todo check vermelho foi cancelado sem runner; vazio
    se algum vermelho e de codigo. `anotacoes(job)` devolve as mensagens do job."""
    runs = set()
    for check in vermelhos:
        par = ids(check)
        if (check.get("conclusion") or "").upper() != "CANCELLED" or not par:
            return set()
        if not any(SEM_RUNNER in m for m in anotacoes(par[1])):
            return set()
        runs.add(par[0])
    return runs


def _gh(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8", check=False)


def main() -> int:
    if len(sys.argv) != 2 or not sys.argv[1].isdigit():
        print("uso: python ci_sem_runner.py <PR>", file=sys.stderr)
        return 2
    pr = sys.argv[1]
    proc = _gh("pr", "view", pr, "--json", "statusCheckRollup")
    if proc.returncode != 0:
        print(f"erro ao consultar o PR #{pr}: {proc.stderr.strip()}", file=sys.stderr)
        return 2
    checks = json.loads(proc.stdout).get("statusCheckRollup") or []
    vermelhos = [c for c in checks
                 if (c.get("conclusion") or c.get("state") or "").upper() not in VERDE_OU_PENDENTE]

    def anotacoes(job: str) -> list[str]:
        p = _gh("api", f"repos/{{owner}}/{{repo}}/check-runs/{job}/annotations")
        return [a.get("message") or "" for a in json.loads(p.stdout or "[]")] if p.returncode == 0 else []

    runs = runs_sem_runner(vermelhos, anotacoes)
    if not runs:
        print(f"PR #{pr}: " + ("CI vermelho de codigo, siga o fluxo normal." if vermelhos
                                 else "nenhum check vermelho."))
        return 1
    for run in sorted(runs):
        p = _gh("run", "rerun", run, "--failed")
        estado = "rerun pedido" if p.returncode == 0 else f"rerun recusado ({p.stderr.strip()[:120]})"
        print(f"PR #{pr}: run {run} cancelado sem runner do GitHub (incidente do Actions, "
              f"githubstatus.com), {estado}. Nao e falha de codigo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
