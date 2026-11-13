#!/usr/bin/env python3
"""/pendencias: o que está parado em cada repositório de ~/PedroDev, só leitura.

Para cada clone git de ~/PedroDev mostra:
  - branch atual e a branch principal (origin/HEAD, senão main)
  - mudanças pendentes (git status), com o diffstat e a idade do arquivo mais novo
  - commits locais que não subiram (à frente do upstream ou da principal)
  - commits da principal que faltam aqui (atrás)
  - outras branches locais com commits fora da principal
  - PR aberto da branch atual (gh), com estado do merge e dos checks
  - conflito? se juntar o que está aqui (commits e arquivos mexidos) com a principal dá conflito, simulado sem mexer em nada
  - velha? sim quando a mudança mais antiga tem mais de 7 dias ou a principal recebeu commits depois dela

Uso:
  pendencias.py [Pasta ...] [--sem-fetch] [--todos]
    Pasta        só essas pastas de ~/PedroDev (padrão: todas)
    --sem-fetch  não roda git fetch (mais rápido, ahead/behind pode estar velho)
    --todos      mostra também os repositórios limpos
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

RAIZ = Path(os.environ.get("PEDRODEV") or Path.home() / "PedroDev")
EM_USO_MIN = 15  # arquivo mexido há menos que isso: pode ser de uma sessão aberta
MAX_ARQUIVOS = 25
VELHA_DIAS = 7


def rodar(pasta: Path, *args: str, timeout: int = 30, env: dict | None = None) -> str | None:
    try:
        r = subprocess.run(args, cwd=pasta, capture_output=True, text=True, timeout=timeout, env=env)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout.rstrip() if r.returncode == 0 else None


def git(pasta: Path, *args: str, timeout: int = 30, env: dict | None = None) -> str | None:
    return rodar(pasta, "git", *args, timeout=timeout, env=env)


def conflito(pasta: Path, principal: str, status: list[str]) -> list[str] | None:
    """Os arquivos que dariam conflito ao juntar o que está aqui com a principal. None: não deu para simular.

    Os arquivos rastreados entram por um índice temporário (cópia do real) e um commit solto, que nenhuma branch
    aponta; o `git merge-tree --write-tree` junta esse commit com a principal sem tocar em arquivo, índice ou branch.
    Arquivo novo não entra no commit (seria gravar no .git todo arquivo solto, até vídeo): ele só conta quando a
    principal já tem o mesmo caminho com outro conteúdo.
    """
    alvo = "HEAD"
    if any(not l.startswith("??") for l in status):
        real = git(pasta, "rev-parse", "--git-path", "index")
        if not real:
            return None
        with tempfile.TemporaryDirectory() as d:
            indice = Path(d) / "index"
            try:
                shutil.copyfile(pasta / real, indice)
            except OSError:
                return None
            env = {**os.environ, "GIT_INDEX_FILE": str(indice), "GIT_AUTHOR_NAME": "pendencias",
                   "GIT_AUTHOR_EMAIL": "pendencias@local", "GIT_COMMITTER_NAME": "pendencias",
                   "GIT_COMMITTER_EMAIL": "pendencias@local"}
            arvore = git(pasta, "add", "-u", env=env) is not None and git(pasta, "write-tree", env=env)
            alvo = arvore and git(pasta, "commit-tree", arvore, "-p", "HEAD", "-m", "pendencias", env=env)
        if not alvo:
            return None

    try:
        r = subprocess.run(["git", "merge-tree", "--write-tree", "--name-only", "--no-messages", principal, alvo],
                           cwd=pasta, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode not in (0, 1):
        return None
    arquivos: list[str] = []
    for l in r.stdout.split("\n")[1:]:
        if not l:
            break
        if l not in arquivos:
            arquivos.append(l)

    novos = [l[3:].strip('"') for l in status if l.startswith("??")]
    if novos:
        na_principal = {}
        for l in (git(pasta, "ls-tree", "-r", principal, "--", *novos) or "").split("\n"):
            if "\t" in l:
                info, caminho = l.split("\t", 1)
                na_principal[caminho] = info.split()[2]
        if na_principal:
            caminhos = list(na_principal)
            aqui = (git(pasta, "hash-object", "--", *caminhos) or "").split("\n")
            arquivos += [c for c, h in zip(caminhos, aqui) if h != na_principal[c] and c not in arquivos]
    return arquivos


def idade(segundos: float) -> str:
    m = int(segundos // 60)
    if m < 60:
        return f"{m} min"
    h = m // 60
    return f"{h} h" if h < 48 else f"{h // 24} dias"


def ler(pasta: Path, fetch: bool) -> dict:
    if fetch:
        git(pasta, "fetch", "--quiet", "--prune", "origin", timeout=60)
    principal = (git(pasta, "symbolic-ref", "--short", "refs/remotes/origin/HEAD") or "origin/main")
    if git(pasta, "rev-parse", "--verify", "--quiet", principal) is None:
        principal = "main" if git(pasta, "rev-parse", "--verify", "--quiet", "main") else None
    branch = git(pasta, "branch", "--show-current") or "(HEAD solto)"
    status = [l for l in (git(pasta, "status", "--porcelain", "--untracked-files=all") or "").split("\n") if l]

    mais_novo = mais_velho = None
    for l in status:
        arq = pasta / l[3:].split(" -> ")[-1].strip('"')
        try:
            t = arq.stat().st_mtime
            mais_novo = t if mais_novo is None else max(mais_novo, t)
            mais_velho = t if mais_velho is None else min(mais_velho, t)
        except OSError:
            pass

    upstream = git(pasta, "rev-parse", "--abbrev-ref", "@{u}")
    base_subida = upstream or principal
    nao_subiram = (git(pasta, "log", "--oneline", f"{base_subida}..HEAD") or "").split("\n") if base_subida else []
    atras = (git(pasta, "rev-list", "--count", f"HEAD..{principal}") or "0") if principal else "0"
    a_frente_principal = (git(pasta, "log", "--oneline", f"{principal}..HEAD") or "").split("\n") if principal else []

    # Velha?: o começo da mudança é o arquivo mexido mais antigo ou o commit mais antigo fora da principal.
    inicios = [mais_velho] if mais_velho else []
    if principal:
        inicios += [int(t) for t in (git(pasta, "log", "--format=%ct", f"{principal}..HEAD") or "").split()]
    inicio = min(inicios) if inicios else None
    principal_depois = 0
    if inicio and principal:
        n = git(pasta, "rev-list", "--count", f"--since=@{int(inicio)}", principal) or "0"
        principal_depois = int(n) if n.isdigit() else 0

    # Worktree divide as branches com o clone principal: a lista sai só lá.
    worktree = (git(pasta, "rev-parse", "--git-dir") or "") != (git(pasta, "rev-parse", "--git-common-dir") or "")
    outras, sumidas = [], 0
    if principal and not worktree:
        fora = set((git(pasta, "branch", "--format=%(refname:short)", "--no-merged", principal) or "").split("\n"))
        refs = git(pasta, "for-each-ref", "--sort=-committerdate", "refs/heads",
                   "--format=%(refname:short)\x1f%(upstream:track)\x1f%(committerdate:relative)\x1f%(subject)") or ""
        for l in refs.split("\n"):
            b, track, quando, assunto = (l.split("\x1f") + ["", "", "", ""])[:4]
            if not b or b == branch or b not in fora:
                continue
            if track == "[gone]":  # remoto apagado: quase sempre PR já mergeado (squash)
                sumidas += 1
                continue
            n = git(pasta, "rev-list", "--count", f"{principal}..{b}") or "?"
            outras.append(f"{b}: {n} commits, {quando}: {assunto}")

    pr = None
    nome_principal = (principal or "main").split("/")[-1]
    if branch != nome_principal and branch != "(HEAD solto)":
        saida = rodar(pasta, "gh", "pr", "list", "--head", branch, "--state", "open",
                      "--json", "number,title,mergeable,mergeStateStatus,isDraft,url", timeout=30)
        if saida:
            lista = json.loads(saida)
            pr = lista[0] if lista else None

    a_frente_principal = [c for c in a_frente_principal if c]
    briga = conflito(pasta, principal, status) if principal and (status or a_frente_principal) else None

    return {
        "pasta": pasta.name,
        "branch": branch,
        "principal": principal,
        "status": status,
        "diffstat": (git(pasta, "diff", "HEAD", "--shortstat") or "").strip(),
        "idade": time.time() - mais_novo if mais_novo else None,
        "inicio": inicio,
        "principal_depois": principal_depois,
        "upstream": upstream,
        "nao_subiram": [c for c in nao_subiram if c],
        "a_frente_principal": a_frente_principal,
        "atras": int(atras) if atras.isdigit() else 0,
        "outras": outras,
        "sumidas": sumidas,
        "pr": pr,
        "conflito": briga,
    }


def velha(r: dict) -> str | None:
    if r["inicio"] is None:
        return None
    d = int((time.time() - r["inicio"]) // 86400)
    texto = "1 dia" if d == 1 else f"{d} dias"
    andou = r["principal_depois"]
    if andou:
        texto += f", a principal recebeu {andou} commits depois"
    return f"velha? {'sim' if d > VELHA_DIAS or andou else 'não'} ({texto})"


def texto_conflito(arquivos: list[str] | None) -> str:
    if arquivos is None:
        return "conflito? não deu para simular"
    if not arquivos:
        return "conflito? não"
    n = len(arquivos)
    return (f"conflito? sim, {n} {'arquivo' if n == 1 else 'arquivos'}: {', '.join(arquivos[:5])}"
            + (f" e mais {n - 5}" if n > 5 else ""))


def tem_algo(r: dict) -> bool:
    return bool(r["status"] or r["nao_subiram"] or r["a_frente_principal"] or r["outras"] or r["sumidas"] or r["pr"])


def imprimir(r: dict) -> list[str]:
    s = [f"## {r['pasta']}  (~/PedroDev/{r['pasta']})",
         f"branch: {r['branch']}  ·  principal: {r['principal'] or '?'}"
         + (f"  ·  {r['atras']} commits atrás da principal" if r["atras"] else "")]
    if r["status"]:
        em_uso = r["idade"] is not None and r["idade"] < EM_USO_MIN * 60
        s.append(f"pendentes: {len(r['status'])} arquivos  ·  {r['diffstat'] or 'só arquivos novos'}"
                 + (f"  ·  mais novo há {idade(r['idade'])}" if r["idade"] is not None else "")
                 + ("  ·  ATENÇÃO: pode ser de sessão aberta" if em_uso else ""))
        if len(r["status"]) <= MAX_ARQUIVOS:
            s += [f"  {l}" for l in r["status"]]
        else:  # muitos arquivos: mexidos um a um, os novos agrupados por pasta
            mexidos = [l for l in r["status"] if not l.startswith("??")]
            s += [f"  {l}" for l in mexidos[:MAX_ARQUIVOS]]
            grupos: dict[str, int] = {}
            for l in r["status"]:
                if l.startswith("??"):
                    partes = l[3:].strip('"').split("/")
                    chave = "/".join(partes[:2]) + "/" if len(partes) > 2 else partes[0] + ("/" if len(partes) == 2 else "")
                    grupos[chave] = grupos.get(chave, 0) + 1
            s += [f"  ?? {k}  ({n} arquivos novos)" for k, n in sorted(grupos.items(), key=lambda x: -x[1])[:15]]
    if r["nao_subiram"]:
        s.append(f"commits que não subiram ({'upstream ' + r['upstream'] if r['upstream'] else 'sem upstream'}): {len(r['nao_subiram'])}")
        s += [f"  {c}" for c in r["nao_subiram"][:10]]
    if r["a_frente_principal"] and r["a_frente_principal"] != r["nao_subiram"]:
        s.append(f"commits da branch fora da principal: {len(r['a_frente_principal'])}")
        s += [f"  {c}" for c in r["a_frente_principal"][:10]]
    v = velha(r)
    if v and (r["status"] or r["a_frente_principal"]):
        s.append(v)
    if r["principal"] and (r["status"] or r["a_frente_principal"]):
        s.append(texto_conflito(r["conflito"]))
    if r["pr"]:
        p = r["pr"]
        s.append(f"PR aberto: #{p['number']} {p['title']}  ·  mergeable={p['mergeable']}  ·  "
                 f"estado={p['mergeStateStatus']}{'  ·  rascunho' if p['isDraft'] else ''}  ·  {p['url']}")
    if r["outras"]:
        s.append(f"outras branches locais fora da principal (remoto vivo): {len(r['outras'])}, as mais novas:")
        s += [f"  {o}" for o in r["outras"][:8]]
    if r["sumidas"]:
        s.append(f"branches locais com o remoto apagado (provável PR já mergeado): {r['sumidas']}")
    return s


def main() -> None:
    args = sys.argv[1:]
    fetch = "--sem-fetch" not in args
    todos = "--todos" in args
    nomes = [a for a in args if not a.startswith("--")]
    pastas = sorted(p for p in RAIZ.iterdir() if (p / ".git").exists() and (not nomes or p.name in nomes))
    faltam = [n for n in nomes if not (RAIZ / n / ".git").exists()]

    with ThreadPoolExecutor(max_workers=8) as ex:
        resultados = list(ex.map(lambda p: ler(p, fetch), pastas))

    com = [r for r in resultados if tem_algo(r)]
    limpos = [r["pasta"] for r in resultados if not tem_algo(r)]
    saida = [f"# Pendências: {len(com)} de {len(resultados)} repositórios com algo parado"]
    for r in (resultados if todos else com):
        saida += [""] + imprimir(r)
    if limpos and not todos:
        saida += ["", f"Limpos: {', '.join(limpos)}"]
    if faltam:
        saida += [f"Não achei em ~/PedroDev: {', '.join(faltam)}"]
    print("\n".join(saida))


if __name__ == "__main__":
    main()
