"""Check de um minuto das issues abertas de quem pede, o `/minhas-issues` (issue #956).

Só leitura: consulta gh, git e a status page do GitHub e imprime 4 blocos
(semáforo, em andamento, na fila, plano). Toda ação sai como comando pronto;
nada é executado aqui.

Uso:
  python3 minhas_issues.py            login do `gh api user`
  python3 minhas_issues.py @login     fila de outra pessoa

"Minha" segue a regra do filtro de responsável do Hospital OS (issue #1039):
atribuída à pessoa; sem ninguém atribuído, quem criou.
"""

from __future__ import annotations

import json
import re
import statistics
import subprocess
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

STATUS_PAGE = "https://www.githubstatus.com/api/v2/components.json"
SEM_RUNNER = "not acquired by Runner"
JANELA_DIAS = 45
SUBIDA = "python3 .claude/skills/onda-enxuta/scripts/fechar_onda.py"
TRIAGEM = ("ready-for-agent", "ready-for-human", "needs-triage", "needs-info")

VEREDITO = {
    "verde": "dá pra desenvolver: sim",
    "amarelo": "dá pra desenvolver: só até o PR (a subida espera)",
    "vermelho": "dá pra desenvolver: só código local (não abra onda)",
}


# Miolo puro


def minhas(issues: list[dict], login: str) -> list[dict]:
    return [
        i for i in issues
        if login in i["assignees"] or (not i["assignees"] and i["author"] == login)
    ]


def cancelados_por_runner(runs: list[dict]) -> int:
    """Jobs cancelados porque o runner não pegou. O run costuma sair failure, não cancelled."""
    return sum(
        1
        for r in runs if r["conclusion"] not in ("success", "skipped")
        for j in r["jobs"] if j["conclusion"] == "cancelled" and any(SEM_RUNNER in a for a in j["anotacoes"])
    )


def semaforo(actions: dict) -> tuple[str, str]:
    comp, cancelados = actions["componente"], actions["cancelados_por_runner"]
    if comp in ("partial_outage", "major_outage"):
        cor = "vermelho"
    elif comp != "operational" or cancelados or cancelados is None:
        cor = "amarelo"
    else:
        cor = "verde"
    partes = [f"Actions {comp or 'sem resposta da status page'}"]
    if cancelados is None:
        partes.append("sem leitura dos runs")
    elif cancelados:
        partes.append(f"{cancelados} job{'s' if cancelados > 1 else ''} cancelado{'s' if cancelados > 1 else ''} por falta de runner")
    return cor, " · ".join(partes)


def _must_fix_aberto(veredito: str) -> bool:
    final = re.search(r"VEREDITO:\s*(\S+)", veredito)
    if final:
        return final.group(1).upper().startswith("MUST-FIX")
    achado = re.search(r"\*\*must-fix\*\*(.*?)(?=\n\s*\*\*|\Z)", veredito, re.S)
    if not achado:
        return False
    corpo = re.sub(r"^\s*(\([^)]*\))?\s*:?", "", achado.group(1))
    palavras = re.sub(r"(?m)^\s*(?:[-*]|\d+\.)\s*", "", corpo).split()
    return bool(palavras) and not palavras[0].lower().startswith("nenhum")


def estado_pr(pr: dict) -> dict:
    conclusoes = [c["conclusion"] for c in pr["checks"]]
    if any(c in ("FAILURE", "TIMED_OUT", "ACTION_REQUIRED", "STARTUP_FAILURE", "ERROR") for c in conclusoes):
        motivo = "CI vermelho"
    elif "CANCELLED" in conclusoes:
        motivo = "CI cancelado"
    elif any(c is None for c in conclusoes):
        motivo = "CI rodando"
    elif pr["mergeStateStatus"] in ("DIRTY", "BEHIND"):
        motivo = "conflito com a main"
    elif pr["vereditos"] and _must_fix_aberto(pr["vereditos"][-1]):
        motivo = "must-fix aberto"
    elif pr["mergeStateStatus"] == "CLEAN":
        return {"nivel": 1, "motivo": "verde, esperando a subida"}
    else:
        motivo = "sem revisão" if not pr["vereditos"] else f"merge {pr['mergeStateStatus']}"
    return {"nivel": 3, "motivo": motivo}


def _comando_pr(pr: dict, motivo: str) -> list[str]:
    runs = sorted({c["run_id"] for c in pr["checks"] if c["conclusion"] in ("CANCELLED", "FAILURE", "TIMED_OUT", "ERROR") and c["run_id"]})
    if motivo == "CI cancelado":
        return [f"`gh run rerun {r} --failed`" for r in runs] or ["rodar o CI de novo"]
    if motivo == "CI vermelho":
        return [f"`gh run view {r} --log-failed`" for r in runs] or ["ver o CI"]
    return [{
        "CI rodando": "esperar o CI",
        "conflito com a main": "`/resolver-conflitos`",
        "must-fix aberto": f"corrigir o must-fix do PR #{pr['number']}",
        "sem revisão": f"`/code-review {pr['number']}`",
    }.get(motivo, f"ver o PR #{pr['number']}")]


def medianas(mergeados: list[dict]) -> dict:
    por: dict[str, list[float]] = {}
    for m in mergeados:
        por.setdefault("todas", []).append(m["horas"])
        for f in m["fatias"]:
            por.setdefault(f, []).append(m["horas"])
    return {k: statistics.median(v) for k, v in por.items()}


def _horas(h: float) -> str:
    return f"~{h:.1f} h".replace(".", ",")


def _quando(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _fatia(i: dict) -> str | None:
    return next((l for l in i["labels"] if l.startswith("fatia:")), None)


def _curto(s: str, n: int = 38) -> str:
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def montar(d: dict) -> str:
    cor, detalhe = semaforo(d["actions"])
    agora = _quando(d["agora"])
    mias = minhas(d["issues"], d["login"])
    numeros = {i["number"] for i in mias}
    pr_de = {n: p for p in d["prs"] for n in p["closes"] if n in numeros}
    wt_de = {}
    for w in d["worktrees"]:
        achado = re.search(r"-(\d+)$", w["branch"] or "")
        if achado and int(achado.group(1)) in numeros:
            wt_de[int(achado.group(1))] = w
    mediana = lambda i: d["medianas"].get(_fatia(i) or "todas", d["medianas"].get("todas", 0))  # noqa: E731

    andamento, fila = [], []
    for i in sorted(mias, key=lambda i: -i["number"]):
        if i["number"] in pr_de or i["number"] in wt_de or "in-progress" in i["labels"]:
            andamento.append(i)
        else:
            fila.append(i)

    # passos: (nivel, texto, comando, horas ou None)
    passos: dict[int, list] = {}
    linhas_and = []
    for i in andamento:
        n, pr, wt = i["number"], pr_de.get(i["number"]), wt_de.get(i["number"])
        onde, prox = [], []
        if pr:
            e = estado_pr(pr)
            onde.append(e["motivo"])
            if e["nivel"] == 1:
                prox = [f"`{SUBIDA} --prs {pr['number']} --dry-run`"]
            else:
                prox = _comando_pr(pr, e["motivo"])
            passos.setdefault(e["nivel"], []).append((f"#{pr['number']}", prox))
        if wt and wt["nao_pushados"]:
            k = wt["nao_pushados"]
            onde.insert(0, f"{k} commit{'s' if k > 1 else ''} só local, sem push")
            prox = [f"`git -C {wt['path']} push -u origin {wt['branch']}`"]
            passos.setdefault(2, []).append((f"#{n}", prox))
        elif wt and not pr and wt["ahead"]:
            onde.append("branch no remoto, sem PR")
            prox = ["`/ship`"]
            passos.setdefault(3, []).append((f"#{n}", prox))
        elif wt and not pr:
            onde.append("worktree aberto, sem commit novo")
            prox = [f"seguir no worktree `{wt['path']}`"]
        if wt and wt["locked"]:
            onde.append("worktree travado")
        if not onde:
            onde.append("claim sem PR nem worktree nesta máquina")
            prox = ["retomar (`/tdd`) ou devolver ao pool"]
            passos.setdefault(3, []).append((f"#{n}", prox))
        pr_txt = f"#{pr['number']} {pr['mergeStateStatus']}" if pr else "sem PR"
        linhas_and.append(f"| {n} | {_curto(i['title'])} | {pr_txt} | {'; '.join(onde)} | {' ; '.join(prox)} |")

    triagem = [i for i in fila if "needs-triage" in i["labels"] or "needs-info" in i["labels"]]
    grupos: dict[str, list[dict]] = {}
    for i in fila:
        if i in triagem:
            continue
        if i["parent"]:
            chave = f"PRD #{i['parent']['number']} {_curto(i['parent']['title'], 30)}"
        elif i["title"].startswith("PRD"):
            chave = f"PRD #{i['number']} {_curto(i['title'], 30)}"
        else:
            estado = next((l for l in i["labels"] if l in TRIAGEM), "sem label")
            chave = f"avulsa · {estado}"
        grupos.setdefault(chave, []).append(i)
    linhas_fila = []
    for chave, its in sorted(grupos.items()):
        labels = {}
        for i in its:
            l = next((x for x in i["labels"] if x in TRIAGEM), "sem label")
            labels[l] = labels.get(l, 0) + 1
        dias = min((agora - _quando(i["updatedAt"])).days for i in its)
        nums = ", ".join(str(i["number"]) for i in sorted(its, key=lambda i: i["number"]))
        lab = " · ".join(f"{k} {v}" for k, v in labels.items())
        linhas_fila.append(f"| {chave} | {nums} | {lab} | parada há {dias} dia{'s' if dias != 1 else ''} |")

    # níveis 4 a 6, a partir da fila
    agente = [i for i in fila if "ready-for-agent" in i["labels"] and i not in triagem and not i["title"].startswith("PRD")]
    for i in [i for i in agente if "priority:high" in i["labels"]]:
        passos.setdefault(4, []).append((f"#{i['number']}", [f"`/pegar-issue {i['number']}` ({_horas(mediana(i))})"], mediana(i)))
    for i in [i for i in fila if "ready-for-human" in i["labels"]]:
        passos.setdefault(5, []).append((f"#{i['number']}", [f"tarefa sua: {_curto(i['title'], 50)}"]))
    resto = [i for i in agente if "priority:high" not in i["labels"]]
    if resto:
        andando = sorted({i["parent"]["number"] for i in andamento if i["parent"]})
        recorte = "".join(f" --exceto #{p}" for p in andando)
        horas = sum(mediana(i) for i in resto)
        passos.setdefault(6, []).append(
            (f"{len(resto)} na fila de agente", [f"`/montar-ondas-enxutas{recorte}` ({_horas(horas)} de PR somados)"], horas)
        )

    titulos = {
        1: "Fechar o que está verde",
        2: "Salvar trabalho que pode se perder",
        3: "Destravar PR parado",
        4: "Prioridade alta na fila",
        5: "Tarefa humana",
        6: "Fila de agente em ondas",
    }
    plano, estimativas = [], []
    for nivel in sorted(passos)[:3]:
        itens = passos[nivel]
        alvo = ", ".join(x[0] for x in itens)
        cmds = [c for x in itens for c in x[1]]
        precisa_ci = any("gh run" in c or "fechar_onda" in c for c in cmds)
        extra = " (espera o Actions)" if precisa_ci and cor != "verde" else ""
        estimativas.append(0.0 if nivel <= 3 else None if nivel == 5 else sum(x[2] for x in itens))
        plano.append(f"{len(estimativas)}. {titulos[nivel]} {alvo}{extra}:")
        plano += [f"   - {c}" for c in cmds]

    saida = [
        f"**Semáforo:** {cor} · {detalhe} · {VEREDITO[cor]}",
        "",
        f"**{d['login']}**: {len(mias)} abertas ({len(andamento)} em andamento, {len(fila)} na fila)",
        "",
        "**1. Em andamento**",
        "",
    ]
    if linhas_and:
        saida += ["| # | tema | PR | onde parou | próximo passo |", "|---|---|---|---|---|", *linhas_and]
    else:
        saida.append("nada em andamento")
    saida += ["", "**2. Na fila**", ""]
    if linhas_fila:
        saida += ["| grupo | issues | label | parada |", "|---|---|---|---|", *linhas_fila]
    for rotulo in ("needs-triage", "needs-info"):
        dessa = [i for i in triagem if rotulo in i["labels"]]
        if dessa:
            saida.append(f"{rotulo}: {', '.join('#' + str(i['number']) for i in dessa)} (`/triage`)")
    saida += ["", "**3. Plano**", ""]
    saida += plano or ["nada a fazer"]
    validas = [(h, k) for k, h in enumerate(estimativas) if h is not None]
    if validas:
        rapido = min(validas)[1] + 1
        saida.append("")
        saida.append(
            "O passo 1 é o melhor e o mais rápido." if rapido == 1
            else f"Melhor: passo 1. Mais rápido: passo {rapido}."
        )
    return "\n".join(saida)


# Coleta (só leitura)


def gh(*args: str) -> str:
    return subprocess.run(["gh", *args], capture_output=True, text=True, check=True).stdout


def git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout


CONSULTA_ISSUES = """
query($q: String!) {
  search(query: $q, type: ISSUE, first: 100) {
    nodes { ... on Issue {
      number title createdAt updatedAt author { login }
      assignees(first: 10) { nodes { login } }
      labels(first: 20) { nodes { name } }
      parent { number title }
    } }
  }
}
"""

CONSULTA_MERGEADOS = """
query($q: String!, $endCursor: String) {
  search(query: $q, type: ISSUE, first: 100, after: $endCursor) {
    pageInfo { hasNextPage endCursor }
    nodes { ... on PullRequest {
      createdAt mergedAt
      closingIssuesReferences(first: 5) { nodes { labels(first: 20) { nodes { name } } } }
    } }
  }
}
"""


def _jsons(texto: str) -> list:
    """O `gh api --paginate` emite um JSON por página, colados."""
    dec, i, saida = json.JSONDecoder(), 0, []
    while i < len(texto):
        while i < len(texto) and texto[i].isspace():
            i += 1
        if i < len(texto):
            obj, i = dec.raw_decode(texto, i)
            saida.append(obj)
    return saida


def _issues(repo: str, filtro: str) -> list[dict]:
    resp = json.loads(gh("api", "graphql", "-f", f"query={CONSULTA_ISSUES}", "-f", f"q=repo:{repo} is:issue is:open {filtro}"))
    return [
        {
            "number": n["number"],
            "title": n["title"],
            "labels": [l["name"] for l in n["labels"]["nodes"]],
            "assignees": [a["login"] for a in n["assignees"]["nodes"]],
            "author": (n["author"] or {}).get("login"),
            "createdAt": n["createdAt"],
            "updatedAt": n["updatedAt"],
            "parent": n["parent"],
        }
        for n in resp["data"]["search"]["nodes"]
    ]


def _prs() -> list[dict]:
    brutos = json.loads(gh(
        "pr", "list", "--state", "open", "--limit", "100", "--json",
        "number,headRefName,mergeStateStatus,statusCheckRollup,closingIssuesReferences,comments",
    ))
    prs = []
    for p in brutos:
        checks = []
        for c in p["statusCheckRollup"]:
            run = re.search(r"/runs/(\d+)", c.get("detailsUrl") or "")
            checks.append({
                "name": c.get("name") or c.get("context"),
                "conclusion": c.get("conclusion") or (c.get("state") if c.get("state") not in ("PENDING", "EXPECTED") else None) or None,
                "run_id": int(run.group(1)) if run else None,
            })
        prs.append({
            "number": p["number"],
            "headRefName": p["headRefName"],
            "mergeStateStatus": p["mergeStateStatus"],
            "closes": [r["number"] for r in p["closingIssuesReferences"]],
            "checks": checks,
            "vereditos": [c["body"] for c in p["comments"] if "Veredito da revisão" in c["body"]],
        })
    return prs


def _actions(repo: str) -> dict:
    try:
        with urllib.request.urlopen(STATUS_PAGE, timeout=5) as r:
            comps = json.load(r)["components"]
        componente = next((c["status"] for c in comps if c["name"] == "Actions"), None)
    except Exception:
        componente = None
    try:
        runs = json.loads(gh("run", "list", "--limit", "10", "--json", "databaseId,conclusion"))
        for run in runs:
            run["jobs"] = []
            if run["conclusion"] in ("success", "skipped", "", None):
                continue
            for job in json.loads(gh("run", "view", str(run["databaseId"]), "--json", "jobs"))["jobs"]:
                notas = []
                if job["conclusion"] == "cancelled":
                    resp = gh("api", f"repos/{repo}/check-runs/{job['databaseId']}/annotations")
                    notas = [n.get("message") or "" for n in json.loads(resp)]
                run["jobs"].append({"conclusion": job["conclusion"], "anotacoes": notas})
        cancelados = cancelados_por_runner(runs)
    except (subprocess.CalledProcessError, json.JSONDecodeError, KeyError):
        cancelados = None  # sem leitura dos runs: o semáforo fica amarelo
    return {"componente": componente, "cancelados_por_runner": cancelados}


def _mergeados(repo: str, agora: datetime) -> list[dict]:
    desde = (agora - timedelta(days=JANELA_DIAS)).date().isoformat()
    paginas = _jsons(gh(
        "api", "graphql", "--paginate", "-f", f"query={CONSULTA_MERGEADOS}",
        "-f", f"q=repo:{repo} is:pr is:merged merged:>={desde}",
    ))
    saida = []
    for pag in paginas:
        for n in pag["data"]["search"]["nodes"]:
            fatias = [l["name"] for ref in n["closingIssuesReferences"]["nodes"] for l in ref["labels"]["nodes"] if l["name"].startswith("fatia:")]
            if not n["closingIssuesReferences"]["nodes"]:
                continue  # PR de registro de deploy (histórico, não existe mais desde a Action pós-merge), sem issue
            horas = (_quando(n["mergedAt"]) - _quando(n["createdAt"])).total_seconds() / 3600
            saida.append({"horas": horas, "fatias": fatias})
    return saida


def _worktrees() -> list[dict]:
    remotas = {l.split("refs/heads/", 1)[1] for l in git("ls-remote", "--heads", "origin").splitlines() if "refs/heads/" in l}
    saida, atual = [], {}
    for linha in git("worktree", "list", "--porcelain").splitlines() + [""]:
        if linha.startswith("worktree "):
            atual = {"path": linha.split(" ", 1)[1], "branch": None, "locked": False}
        elif linha.startswith("branch "):
            atual["branch"] = linha.split("refs/heads/", 1)[-1]
        elif linha.startswith("locked"):
            atual["locked"] = True
        elif not linha and atual:
            if atual["branch"]:
                sem_remoto = atual["branch"] not in remotas
                base = "origin/main" if sem_remoto else f"origin/{atual['branch']}"
                try:
                    ahead = int(git("-C", atual["path"], "rev-list", "--count", "origin/main..HEAD").strip())
                    nao_pushados = int(git("-C", atual["path"], "rev-list", "--count", f"{base}..HEAD").strip())
                except subprocess.CalledProcessError:
                    ahead = nao_pushados = 0
                saida.append({**atual, "ahead": ahead, "sem_remoto": sem_remoto, "nao_pushados": nao_pushados})
            atual = {}
    return saida


def coletar(login: str | None) -> dict:
    login = login or gh("api", "user", "-q", ".login").strip()
    repo = gh("repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner").strip()
    agora = datetime.now(timezone.utc)
    vistas, issues = set(), []
    for filtro in (f"assignee:{login}", f"author:{login} no:assignee"):
        for i in _issues(repo, filtro):
            if i["number"] not in vistas:
                vistas.add(i["number"])
                issues.append(i)
    return {
        "login": login,
        "agora": agora.isoformat(),
        "issues": issues,
        "prs": _prs(),
        "worktrees": _worktrees(),
        "actions": _actions(repo),
        "medianas": medianas(_mergeados(repo, agora)),
    }


if __name__ == "__main__":
    alvo = sys.argv[1].lstrip("@") if len(sys.argv) > 1 else None
    try:
        print(montar(coletar(alvo)))
    except subprocess.CalledProcessError as erro:
        motivo = (erro.stderr or "").strip().splitlines()
        sys.exit(f"falha ao consultar o GitHub ({' '.join(erro.cmd[:3])}): {motivo[0] if motivo else erro}")
