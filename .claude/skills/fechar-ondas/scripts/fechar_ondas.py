#!/usr/bin/env python3
"""fechar_ondas.py: a parte mecânica da /fechar-ondas (issue #533).

Lê as Ondas de todos os Projetos em ${PEDROOS_ONDAS:-~/.pedroos/ondas}, pega as que quebraram (`erro`) ou
esperam o Pedro (`pronto-para-voce`) e confere cada uma no GitHub pelo `gh`:

- O que se confere é o que a pendência espera: o campo `espera` da Onda (issue #532). Sem ele, a Onda
  que espera o Pedro fica como está, porque a pendência dela pode ser fora do GitHub (migration para
  aplicar, mensagem para o diretor) mesmo com as issues e os PRs fechados. Só a quebrada sem `espera`
  cai para as issues e os PRs da Onda, e ainda precisa da main verde (o último run do Actions na main).
- Onda com tudo o que confere fechado (issue CLOSED, PR MERGED ou CLOSED) já acabou. A quebrada também
  precisa da main verde, para uma quebra de verdade não sumir. O script grava o `resolvido` com o
  `estado_onda.py` da pasta do Projeto (o campo `pasta` do arquivo): antes, a issue em `baixa` que ele
  viu fechada sai pelo `mergeadas`, senão o `resolvido` a deixa esperando.
- Onda sem nada para conferir, com algo aberto, ou que o GitHub não deixou ler, fica como está.

Imprime a tabela Onda por Onda (o que diz, a verdade hoje, o que o script fez) e a lista do que ficou.
Saída 0. Uso: python3 fechar_ondas.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

PARADAS = ("erro", "pronto-para-voce")
ESTADO_ONDA = Path(".claude") / "skills" / "onda-enxuta" / "scripts" / "estado_onda.py"
FECHADO = {"issue": ("CLOSED",), "pr": ("MERGED", "CLOSED")}


def pasta_base() -> Path:
    return Path(os.environ.get("PEDROOS_ONDAS") or Path.home() / ".pedroos" / "ondas")


def gh(*args: str) -> str | None:
    """O que o `gh` imprime, sem espaços nas pontas, ou None se ele falhar."""
    try:
        r = subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8", timeout=30, check=True)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None
    return r.stdout.strip()


def paradas() -> list[dict]:
    base = pasta_base()
    ondas = []
    for arq in sorted(base.glob("*/*.json")) if base.is_dir() else []:
        try:
            o = json.loads(arq.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if o.get("estado") in PARADAS:
            ondas.append(o)
    return ondas


def alvos(o: dict) -> list[tuple[str, str, int]]:
    """O que conferir no GitHub: o campo `espera`. Sem ele, só a quebrada cai para as issues e os PRs da Onda;
    a que espera o Pedro devolve nada, porque a pendência dela pode estar fora do GitHub."""
    repo = o.get("repo") or ""
    espera = o.get("espera") or []
    if espera:
        vistos = [(e.get("tipo"), e.get("repo") or repo, e.get("numero")) for e in espera if isinstance(e, dict)]
    elif o.get("estado") == "erro":
        issues = o.get("issues") or []
        vistos = [("issue", repo, i["numero"]) for i in issues] + [("pr", repo, i["pr"]) for i in issues if i.get("pr")]
    else:
        vistos = []
    return [a for k, a in enumerate(vistos) if a not in vistos[:k] and a[0] in FECHADO and isinstance(a[2], int)]


def rotulo(tipo: str, repo: str, numero: int, o: dict) -> str:
    nome = f"PR #{numero}" if tipo == "pr" else f"#{numero}"
    return nome if repo == o.get("repo") else f"{repo}{nome.removeprefix('PR ')}"


def juntar(nomes: list[str]) -> str:
    return nomes[0] if len(nomes) == 1 else f"{', '.join(nomes[:-1])} e {nomes[-1]}"


def o_que_diz(o: dict) -> str:
    """O texto da última pendência (erro ou pronto-para-voce) depois do último resolvido."""
    texto = "sem evento"
    for e in sorted(o.get("eventos") or [], key=lambda e: e.get("em") or ""):
        if e.get("tipo") == "resolvido":
            texto = "sem evento"
        elif e.get("tipo") in PARADAS:
            texto = e.get("texto") or e["tipo"]
    return texto.replace("|", "/").replace("\n", " ")[:120]


def conferir(o: dict) -> tuple[bool, str]:
    """(já acabou, a verdade hoje)."""
    lista = alvos(o)
    if not lista:
        return False, "nada para conferir no GitHub: a pendência é fora dele"
    abertos, sem_leitura = [], []
    for tipo, repo, numero in lista:
        estado = gh(tipo, "view", str(numero), "--repo", repo, "--json", "state", "--jq", ".state")
        if estado is None:
            sem_leitura.append(rotulo(tipo, repo, numero, o))
        elif estado not in FECHADO[tipo]:
            abertos.append(f"{rotulo(tipo, repo, numero, o)} aberto")
    if sem_leitura:
        return False, f"não consegui ler {juntar(sem_leitura)} no GitHub"
    if abertos:
        return False, juntar(abertos)
    fechados = f"{juntar([rotulo(*a, o) for a in lista])} fechados no GitHub"
    if o["estado"] == "erro":
        ci = gh("run", "list", "--repo", o.get("repo") or "", "--branch", "main", "--limit", "1", "--json", "conclusion", "--jq", ".[0].conclusion")
        if ci != "success":
            return False, f"{fechados}, mas a main não está verde ({ci or 'sem leitura'})"
    return True, fechados


def resolver(o: dict, texto: str) -> str:
    pasta = Path(o.get("pasta") or "")
    script = pasta / ESTADO_ONDA
    if not o.get("pasta") or not script.is_file():
        return "acabou, mas está sem a pasta do Projeto neste Mac"
    alvo = ["--sessao", o["sessao"], "--onda", str(o["onda"])]
    vistas = {(repo, numero) for tipo, repo, numero in alvos(o) if tipo == "issue"}
    baixa = [str(i["numero"]) for i in o.get("issues") or [] if i.get("status") == "baixa" and (o.get("repo") or "", i["numero"]) in vistas]
    comandos = ([["mergeadas", "--issues", *baixa, "--texto", "fechar-ondas"]] if baixa else []) + [["resolvido", *alvo, "--texto", f"fechar-ondas: {texto}"]]
    for args in comandos:
        r = subprocess.run([sys.executable, str(script), *args], cwd=pasta, capture_output=True, text=True, encoding="utf-8")
        if r.returncode != 0:
            return f"o estado_onda.py {args[0]} falhou: {(r.stderr.strip() or 'sem motivo').splitlines()[0]}"
    return "resolvido gravado"


def main() -> int:
    for f in (sys.stdout, sys.stderr):
        f.reconfigure(encoding="utf-8")
    ondas = paradas()
    if not ondas:
        print("Nenhuma Onda quebrou nem espera você agora.")
        return 0
    print("| Onda | Estado | O que diz | A verdade hoje | O que fiz |")
    print("|---|---|---|---|---|")
    ficaram = []
    for o in ondas:
        chave = f"{o.get('slug')}/{o.get('id')}"
        acabou, verdade = conferir(o)
        feito = resolver(o, verdade) if acabou else "nada: é real"
        print(f"| {chave} | {'quebrou' if o['estado'] == 'erro' else 'espera você'} | {o_que_diz(o)} | {verdade} | {feito} |")
        if feito != "resolvido gravado":
            ficaram.append(f"- {chave}: {verdade}")
    print()
    print(f"Ficaram {len(ficaram)} de {len(ondas)} Ondas:" if ficaram else f"As {len(ondas)} Ondas já tinham acabado; nenhuma ficou.")
    for linha in ficaram:
        print(linha)
    return 0


if __name__ == "__main__":
    sys.exit(main())
