#!/usr/bin/env python3
"""fluxo.py: a configuração do fluxo neste Projeto (`.claude/fluxo.json`).

O pacote do fluxo é o mesmo em todo Projeto (fonte única no PedroOS, `skills/fluxo/`).
O que muda de um Projeto para outro mora num arquivo só, `.claude/fluxo.json`, que o
instalador do PedroOS grava a partir de `projetos/<nome>.json`. As regras que só um
Projeto tem ficam em
`.claude/fluxo-notas.md`, uma seção `## <skill>` por skill, e a lista de arquivos
sensíveis em `.claude/skills/onda-enxuta/revisao-sensivel.txt`: os dois vêm da
pasta `projetos/<nome>/` do PedroOS.

Uso:
    python3 fluxo.py                  # a configuração inteira, em JSON
    python3 fluxo.py <chave>          # um valor (texto puro; lista e objeto em JSON)
    python3 fluxo.py classe <arq...>  # "app" se algum arquivo está na pasta do app, senão "ferramenta"
    python3 fluxo.py classe --pr <N>  # o mesmo, com os arquivos do PR (gh pr diff --name-only)
    python3 fluxo.py notas <skill>    # a seção `## <skill>` do fluxo-notas.md (vazio se não houver)

Saída 0 com a resposta, 2 com o motivo no stderr (arquivo ausente, JSON quebrado,
contrato de outra versão, chave desconhecida).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

CONTRATO = 1
ARQUIVO = Path(".claude") / "fluxo.json"
NOTAS = Path(".claude") / "fluxo-notas.md"

# O que vale quando o Projeto não diz nada. `nome` e `app` não têm padrão: sem eles o
# fluxo não sabe o que é PR do app.
PADRAO: dict = {
    "slug": None,
    "leitor": "quem decide",
    "bloco": "Para quem decide",
    "humano": "o dono do Projeto",
    "ask": None,
    "designado_tira_da_fila": False,
    "dado_sensivel": "dado pessoal",
    "migrations": None,
    "testes": None,
    "teste_da_main": None,
    "varredura": None,
    "decisoes": {},
    "prd_do_leitor": None,
    "design": None,
    "aviso_celular": True,
    "protegidos": [],
}
OBRIGATORIAS = ("nome", "app")


class Erro(Exception):
    """O motivo, numa frase."""


def raiz(inicio: Path | None = None) -> Path:
    """A raiz do repositório em que o comando roda (o worktree, se for um)."""
    try:
        saida = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True,
                               encoding="utf-8", check=True, cwd=inicio).stdout.strip()
        return Path(saida)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return Path(__file__).resolve().parents[4]


def carregar(base: Path | None = None) -> dict:
    """A configuração do Projeto com os padrões preenchidos."""
    arq = (base or raiz()) / ARQUIVO
    if not arq.exists():
        raise Erro(f"{ARQUIVO} não existe: rode o instalador do PedroOS (scripts/instalar-skills.sh)")
    try:
        dado = json.loads(arq.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise Erro(f"{ARQUIVO} não é JSON válido ({e})") from e
    if dado.get("contrato") != CONTRATO:
        raise Erro(f"{ARQUIVO} tem contrato {dado.get('contrato')!r}; este pacote lê o {CONTRATO}")
    faltam = [c for c in OBRIGATORIAS if not dado.get(c)]
    if faltam:
        raise Erro(f"{ARQUIVO} sem {', '.join(faltam)}")
    cfg = {**PADRAO, **dado}
    if not cfg["app"].endswith("/"):
        cfg["app"] += "/"
    if not cfg["slug"]:
        cfg["slug"] = cfg["nome"].lower()
    return cfg


def classe(arquivos: list[str], cfg: dict) -> str:
    """"app" se algum arquivo está na pasta do app, "ferramenta" se nenhum está."""
    return "app" if any(a.replace("\\", "/").startswith(cfg["app"]) for a in arquivos) else "ferramenta"


def notas(skill: str, base: Path | None = None) -> str:
    """A seção `## <skill>` do fluxo-notas.md, sem o título; vazio se não houver."""
    arq = (base or raiz()) / NOTAS
    if not arq.exists():
        return ""
    linhas, dentro, cerca = [], False, False
    for linha in arq.read_text(encoding="utf-8").splitlines():
        if linha.lstrip().startswith("```"):
            cerca = not cerca  # título dentro de bloco de código é conteúdo, não seção
        elif linha.startswith("## ") and not cerca:
            dentro = linha[3:].strip() == skill
            continue
        if dentro:
            linhas.append(linha)
    return "\n".join(linhas).strip()


def _arquivos_do_pr(pr: str) -> list[str]:
    saida = subprocess.run(["gh", "pr", "diff", pr, "--name-only"], capture_output=True, text=True,
                           encoding="utf-8", check=True).stdout
    return [linha for linha in saida.splitlines() if linha.strip()]


def main(argv: list[str]) -> int:
    for fluxo in (sys.stdout, sys.stderr):
        fluxo.reconfigure(encoding="utf-8")
    try:
        if argv and argv[0] == "notas":
            if len(argv) != 2:
                raise Erro("uso: fluxo.py notas <skill>")
            texto = notas(argv[1])
            if texto:
                print(texto)
            return 0
        cfg = carregar()
        if not argv:
            print(json.dumps(cfg, ensure_ascii=False, indent=2))
            return 0
        if argv[0] == "classe":
            arquivos = _arquivos_do_pr(argv[2]) if argv[1:2] == ["--pr"] and len(argv) == 3 else argv[1:]
            print(classe(arquivos, cfg))
            return 0
        if len(argv) != 1 or argv[0] not in cfg:
            raise Erro(f"chave desconhecida: {' '.join(argv)}")
        valor = cfg[argv[0]]
        print(valor if isinstance(valor, str) else json.dumps(valor, ensure_ascii=False))
        return 0
    except (Erro, subprocess.CalledProcessError) as e:
        print(f"erro: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
