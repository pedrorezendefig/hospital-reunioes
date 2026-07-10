#!/usr/bin/env python3
"""Coleta tudo que o workflow produz (gh + docs/spec + git) num dict único.

Usado pelo serve.py; executável solo para debug:
  python3 collect.py          # resumo com contagens
  python3 collect.py --json   # dump completo
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from plano import bloqueios_do_corpo, montar_plano

GH_TIMEOUT = 20

ISSUE_FIELDS = "number,title,state,labels,createdAt,closedAt,assignees,body,url"
PR_FIELDS = "number,title,state,mergedAt,headRefName,closingIssuesReferences,url"

SNAPSHOT_ORDER = ["ROTAS", "ENTIDADES", "SCHEMA", "MIGRATIONS", "INTEGRACOES", "ESTRUTURA", "FLUXOGRAMAS"]

CLAIMS_QUERY = """
query($owner:String!,$name:String!){
  repository(owner:$owner,name:$name){
    issues(first:100,states:[CLOSED],labels:["fatia:P","fatia:M","fatia:G"],
           orderBy:{field:UPDATED_AT,direction:DESC}){
      nodes{
        number
        timelineItems(itemTypes:[ASSIGNED_EVENT],first:1){
          nodes{ ... on AssignedEvent { createdAt } }
        }
      }
    }
  }
}
"""

SUBISSUES_QUERY = """
query($owner:String!,$name:String!,$after:String){
  repository(owner:$owner,name:$name){
    issues(first:100,states:[OPEN,CLOSED],orderBy:{field:CREATED_AT,direction:DESC},after:$after){
      pageInfo{ hasNextPage endCursor }
      nodes{ number subIssues(first:50){ nodes{ number } } }
    }
  }
}
"""


def _run(cmd: list[str], cwd: Path, timeout: int = GH_TIMEOUT) -> str:
    p = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout)
    if p.returncode != 0:
        msg = (p.stderr or p.stdout).strip() or f"exit {p.returncode}"
        raise RuntimeError(msg[:400])
    return p.stdout


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _read_text(path: Path):
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return None


def _spec_json_fresh(root: Path, rel: str):
    """Lê um JSON de spec da origin/main, com fallback na working tree.

    Os ships rodam em worktrees paralelos e empurram direto pra origin/main —
    a working tree local fica velha e pode até ter staging sujo de outra
    sessão. O estado fresco pós-ship vive no remoto.
    """
    try:
        return json.loads(_run(["git", "show", f"origin/main:{rel}"], root))
    except Exception:
        return _read_json(root / rel)


def _spec_text_fresh(root: Path, rel: str):
    """Variante texto de _spec_json_fresh — mesma regra (origin/main → fallback local)."""
    try:
        return _run(["git", "show", f"origin/main:{rel}"], root)
    except Exception:
        return _read_text(root / rel)


# ---------- GitHub ----------

def _gh_issues(root: Path) -> list[dict]:
    items = json.loads(_run(["gh", "issue", "list", "--state", "all", "--limit", "200",
                             "--json", ISSUE_FIELDS], root))
    issues = []
    for it in items:
        body = it.get("body") or ""
        blocked = bloqueios_do_corpo(body)
        criteria = re.findall(r"^\s*[-*] \[([ xX])\]", body, re.M)
        parent = None
        m = re.search(r"(?mi)^.{0,20}pai[^#\n]{0,40}#(\d+)", body)
        if m:
            parent = int(m.group(1))
        issues.append({
            "number": it["number"],
            "title": it["title"],
            "state": it["state"],
            "labels": [l["name"] for l in it.get("labels") or []],
            "created_at": it.get("createdAt"),
            "closed_at": it.get("closedAt"),
            "assignees": [a.get("login") for a in it.get("assignees") or []],
            "url": it.get("url"),
            "body": body,
            "blocked_by": sorted(set(blocked)),
            "parent": parent,
            "criteria": {"done": sum(1 for c in criteria if c.strip()), "total": len(criteria)},
        })
    return issues


def _gh_prs(root: Path) -> list[dict]:
    items = json.loads(_run(["gh", "pr", "list", "--state", "all", "--limit", "200",
                             "--json", PR_FIELDS], root))
    return [{
        "number": it["number"],
        "title": it["title"],
        "state": it["state"],
        "merged_at": it.get("mergedAt"),
        "head_ref": it.get("headRefName"),
        "url": it.get("url"),
        "closes": [r["number"] for r in it.get("closingIssuesReferences") or []],
    } for it in items]


def _gh_subissues(root: Path, slug: str) -> dict[int, list[int]]:
    """Mapa PRD -> fatias via API nativa de sub-issues (GraphQL).

    Do mais recente pro mais antigo, paginando até esgotar (sem orderBy
    o GitHub devolve as mais ANTIGAS primeiro e PRDs novos fora da 1ª
    página apareciam sem fatias no painel; teto fixo de páginas traria
    o mesmo sintoma de volta quando o repo crescer).
    """
    owner, name = slug.split("/", 1)
    rel: dict[int, list[int]] = {}
    cursor = None
    while True:
        cmd = ["gh", "api", "graphql", "-f", f"query={SUBISSUES_QUERY}",
               "-F", f"owner={owner}", "-F", f"name={name}"]
        if cursor:
            cmd += ["-F", f"after={cursor}"]
        page = json.loads(_run(cmd, root))["data"]["repository"]["issues"]
        for node in page["nodes"]:
            subs = [s["number"] for s in node["subIssues"]["nodes"]]
            if subs:
                rel[node["number"]] = sorted(subs)
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]
    return rel


def _enrich_claims(root: Path, slug: str, issues: list[dict]) -> None:
    """claimed_at nas fechadas com label fatia:* — base do lead time real do Plano.

    Uma única chamada GraphQL em lote (1º evento assigned por issue), independente
    de quantas fechadas existam. Falha degrada para "sem claim" (lead time cai no
    fallback abertura→fechamento) sem envenenar coletas futuras.
    """
    try:
        owner, name = slug.split("/", 1)
        raw = _run(["gh", "api", "graphql", "-f", f"query={CLAIMS_QUERY}",
                    "-F", f"owner={owner}", "-F", f"name={name}"], root)
        nodes = json.loads(raw)["data"]["repository"]["issues"]["nodes"]
        claims = {}
        for node in nodes:
            items = node["timelineItems"]["nodes"]
            if items and items[0].get("createdAt"):
                claims[node["number"]] = items[0]["createdAt"]
    except Exception:
        return
    for i in issues:
        if i["number"] in claims:
            i["claimed_at"] = claims[i["number"]]


def issue_detail(root: Path, number: int) -> dict:
    """Comentários de uma issue (lazy, só no drill-down)."""
    try:
        raw = _run(["gh", "issue", "view", str(number), "--json", "number,comments"], root)
        data = json.loads(raw)
        return {"number": number, "error": None, "comments": [{
            "author": (c.get("author") or {}).get("login"),
            "created_at": c.get("createdAt"),
            "body_md": c.get("body") or "",
        } for c in data.get("comments") or []]}
    except Exception as e:
        return {"number": number, "error": str(e), "comments": []}


# ---------- Correlação issue -> PR -> deploy ----------

def _correlate(history: list[dict], issues: list[dict], prs: list[dict]) -> None:
    issues_by = {i["number"]: i for i in issues}
    prs_by = {p["number"]: p for p in prs}

    for d in history:
        notes = d.get("notes") or ""
        found = {int(n) for n in re.findall(r"\(#(\d+)\)", d.get("raw_subject") or "")}
        found |= {int(n) for n in re.findall(r"PRs? #(\d+)", notes)}
        issue_direct = {int(n) for n in re.findall(r"(?:[Ii]ssues? |Closes )#(\d+)", notes)}

        pr_nums, issue_nums = set(), set()
        for n in found:
            if n in prs_by:
                pr_nums.add(n)
            elif n in issues_by:
                issue_nums.add(n)
        issue_nums |= issue_direct & issues_by.keys()
        for pn in pr_nums:
            issue_nums |= set(prs_by[pn]["closes"]) & issues_by.keys()

        d["pr_numbers"] = sorted(pr_nums)
        d["issue_numbers"] = sorted(issue_nums)

    for i in issues:
        i["prs"] = [{"number": p["number"], "state": p["state"], "merged_at": p["merged_at"],
                     "url": p["url"]} for p in prs if i["number"] in p["closes"]]
        i["deploys"] = [{"app_version": d.get("app_version"), "sha": d.get("sha"),
                         "at": d.get("at"), "result": d.get("result")}
                        for d in history if i["number"] in d.get("issue_numbers", [])]


# ---------- Arquivos do repo ----------

def _parse_changelog(text: str | None) -> list[dict]:
    if not text:
        return []
    entries, cur = [], None
    for line in text.splitlines():
        if line.startswith("## "):
            if cur:
                entries.append(cur)
            header = line[3:].strip()
            version = date = time_ = None
            title = header
            m = re.match(r"v(\d+\.\d+\.\d+)\s*[—\-–]+\s*(\d{4}-\d{2}-\d{2})\s*[—\-–]+\s*(.*)", header)
            if m:
                version, date, title = m.groups()
            else:
                m = re.match(r"(\d{4}-\d{2}-\d{2})[ T]?(\d{2}:\d{2})?\s*[—\-–]+\s*(.*)", header)
                if m:
                    date, time_, title = m.groups()
            cur = {"version": version, "date": date, "time": time_, "title": title.strip(),
                   "sha": None, "pr": None, "issue": None, "body_md": ""}
        elif cur is not None:
            cur["body_md"] += line + "\n"
    if cur:
        entries.append(cur)
    for e in entries:
        body = e["body_md"]
        m = re.search(r"(?:SHA|Commit):\s*`?([0-9a-f]{7,40})`?", body) or \
            re.search(r"/commit/([0-9a-f]{7,40})", body)
        e["sha"] = m.group(1)[:7] if m else None
        m = re.search(r"/pull/(\d+)", body)
        e["pr"] = int(m.group(1)) if m else None
        m = re.search(r"/issues/(\d+)", body)
        e["issue"] = int(m.group(1)) if m else None
        e["body_md"] = body.strip()
    return entries


def _parse_adrs(root: Path) -> list[dict]:
    out = []
    for f in sorted((root / "docs" / "adr").glob("*.md")):
        text = _read_text(f) or ""
        meta, body = {}, text
        m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
        if m:
            for line in m.group(1).splitlines():
                km = re.match(r"\s*([\w-]+):\s*(.+?)\s*$", line)
                if km:
                    meta[km.group(1).lower()] = km.group(2).strip()
            body = text[m.end():]
        # Estado canônico = primeira palavra do status (o resto, se houver, é legenda).
        raw = meta.get("status", "")
        state = raw.split()[0].rstrip(",").lower() if raw else ""
        tm = re.search(r"(?m)^# (.+)$", body)
        title = tm.group(1).strip() if tm else f.stem
        nm = re.match(r"(\d+)", f.name)
        out.append({
            "number": int(nm.group(1)) if nm else None,
            "slug": f.stem,
            "title": title,
            "status": state or "?",
            "supersedes": meta.get("supersedes"),
            "superseded_by": meta.get("superseded_by"),
            "amends": meta.get("amends"),
            "amended_by": meta.get("amended_by"),
            "body_md": re.sub(r"(?m)^# .+\n", "", body, count=1).strip(),
            "file": str(f.relative_to(root)),
        })
    return out


def _snapshots(root: Path) -> list[dict]:
    docs = []
    for f in (root / "docs" / "spec" / "snapshots").glob("*.md"):
        text = _read_text(f) or ""
        docs.append({
            "name": f.stem,
            "generated_at": datetime.fromtimestamp(f.stat().st_mtime).astimezone().isoformat(timespec="seconds"),
            "lines": text.count("\n") + 1,
            "body_md": text,
        })
    docs.sort(key=lambda d: SNAPSHOT_ORDER.index(d["name"]) if d["name"] in SNAPSHOT_ORDER else 99)
    return docs


def _git_info(root: Path) -> dict:
    info = {"branch": None, "dirty": None, "commits": []}
    try:
        info["branch"] = _run(["git", "branch", "--show-current"], root).strip()
        info["dirty"] = len([l for l in _run(["git", "status", "--porcelain"], root).splitlines() if l.strip()])
        for line in _run(["git", "log", "--oneline", "-15"], root).splitlines():
            sha, _, subject = line.partition(" ")
            info["commits"].append({"sha": sha, "subject": subject})
    except Exception as e:
        info["error"] = str(e)
    info["on_main"] = info["branch"] == "main"
    info["stale_hint"] = bool(info["branch"] and info["branch"] != "main") or bool(info["dirty"])
    return info


def _gh_failure(e: Exception) -> tuple[str, str]:
    """Classifica a falha do gh numa mensagem amigável para o painel."""
    if isinstance(e, FileNotFoundError):
        return "missing", "gh não encontrado — instale o GitHub CLI (cli.github.com) e rode `gh auth login`."
    msg = str(e).lower()
    if any(t in msg for t in ("auth", "logged in", "not logged", "gh auth login")):
        return "unauth", "gh não autenticado — rode `gh auth login` e clique em ⟳ para recarregar."
    return "other", str(e)


def _state_public(st: dict | None) -> dict | None:
    """Tira do payload o que a UI não usa e não deve trafegar (secrets/env_vars)."""
    if not st:
        return st
    return {k: v for k, v in st.items() if k not in ("secrets", "env_vars")}


def _project_light(pj: dict | None) -> dict | None:
    if not pj:
        return None
    proj = pj.get("project") or {}
    return {
        "name": proj.get("name"),
        "description": proj.get("description"),
        "stack": proj.get("stack"),
        "services": [{"id": s.get("id"), "fqdn": (s.get("deploy") or {}).get("fqdn")}
                     for s in pj.get("services") or []],
    }


def _montar_plano_seguro(github: dict):
    """Plano com a mesma degradação do resto do payload.

    gh indisponível → None (a UI distingue "sem dados" de "sem PRD ativo");
    erro inesperado no módulo → estrutura vazia com o erro, sem derrubar /api/data.
    """
    if github["error"]:
        return None
    try:
        return montar_plano(github["issues"])
    except Exception as e:
        return {"levas": [], "tempos_tipicos": {}, "erro": str(e)[:300]}


# ---------- Montagem ----------

def collect(root: Path) -> dict:
    spec = root / "docs" / "spec"
    try:  # tolera offline — segue com o que a working tree tiver
        _run(["git", "fetch", "origin", "main", "--quiet"], root, timeout=15)
    except Exception:
        pass
    state = _spec_json_fresh(root, "docs/spec/deploy/state.json")
    history_doc = _spec_json_fresh(root, "docs/spec/deploy/history.json") or {}
    history = history_doc.get("deploys") or []
    project = _project_light(_read_json(spec / "deploy" / "project.json"))

    slug = ((state or {}).get("production") or {}).get("repo") or "pedrorezendefig/hospital-reunioes"

    github = {"error": None, "error_kind": None, "issues": [], "prs": [], "prds": []}
    try:
        issues = _gh_issues(root)
        prs = _gh_prs(root)
        try:
            rel = _gh_subissues(root, slug)
        except Exception:
            rel = {}
        issues_by = {i["number"]: i for i in issues}
        for parent, subs in rel.items():
            for s in subs:
                if s in issues_by:
                    issues_by[s]["parent"] = parent
        children: dict[int, list[int]] = {}
        for i in issues:
            if i["parent"] and i["parent"] in issues_by:
                children.setdefault(i["parent"], []).append(i["number"])
        prds = set(children) | {i["number"] for i in issues if i["title"].upper().startswith("PRD")}
        for i in issues:
            i["children"] = sorted(children.get(i["number"], []))
            i["is_prd"] = i["number"] in prds
        _correlate(history, issues, prs)
        _enrich_claims(root, slug, issues)
        github.update(issues=issues, prs=prs, prds=sorted(prds))
    except Exception as e:
        kind, friendly = _gh_failure(e)
        github["error"] = friendly
        github["error_kind"] = kind
        for d in history:
            d.setdefault("pr_numbers", [])
            d.setdefault("issue_numbers", [])

    return {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "repo_slug": slug,
        "repo_url": f"https://github.com/{slug}",
        "github": github,
        "plano": _montar_plano_seguro(github),
        "state": _state_public(state),
        "history": history,
        "project": project,
        "changelog": _parse_changelog(_spec_text_fresh(root, "docs/spec/CHANGELOG.md")),
        "versioning_md": _read_text(spec / "VERSIONING.md"),
        "adrs": _parse_adrs(root),
        "context_md": _read_text(root / "CONTEXT.md"),
        "snapshots": _snapshots(root),
        "git": _git_info(root),
    }


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[2]
    data = collect(root)
    if "--json" in sys.argv:
        json.dump(data, sys.stdout, ensure_ascii=False, indent=2)
        sys.exit(0)
    gh = data["github"]
    print(f"repo        {data['repo_slug']}")
    print(f"gh error    {gh['error']}")
    print(f"issues      {len(gh['issues'])}  (abertas {sum(1 for i in gh['issues'] if i['state'] == 'OPEN')})")
    print(f"prs         {len(gh['prs'])}")
    print(f"prds        {gh['prds']}")
    print(f"deploys     {len(data['history'])}")
    print(f"changelog   {len(data['changelog'])} entradas")
    print(f"adrs        {len(data['adrs'])}")
    print(f"snapshots   {[s['name'] for s in data['snapshots']]}")
    print(f"git         branch={data['git'].get('branch')} dirty={data['git'].get('dirty')}")
    for i in gh["issues"]:
        if i["number"] == 49:
            print(f"#49 sample  parent={i['parent']} prs={[p['number'] for p in i['prs']]} "
                  f"deploys={[d['app_version'] for d in i['deploys']]} criteria={i['criteria']}")
