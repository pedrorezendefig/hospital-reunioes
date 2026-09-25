#!/usr/bin/env python3
"""fechar_onda.py: integra uma onda da `/onda-enxuta` com UM push e UM build.

Uso:
    python fechar_onda.py --prs 850 851 852 --sessao onda-a-1 [--dry-run] [--sem-snapshot] [--raiz <repo>]

A ordem dos PRs e a ordem de merge. O script nunca toca na arvore principal
(ela pode estar suja): todo o trabalho acontece num worktree descartavel de
caminho curto (`~/wt-<sessao>`, por causa do MAX_PATH do Windows).

Sequencia (cada passo imprime no maximo uma linha; sucesso cabe em 10 linhas):
  1. pre-condicoes (gh, coolify, PRs abertos e verdes, origin/main buscado)
  2. semaforo de deploy (chave = nome da sessao, unica por construcao)
  3. worktree descartavel em origin/main
  4. merges locais `--no-ff` em ordem (um commit de merge por PR)
  5. bump semver pelo tipo dominante dos commits do lote (docs-only nao bumpa)
  6. bookkeeping no mesmo push: history.json, state.json, CHANGELOG.md,
     snapshot (best-effort, issue #844), draft do manual (ADR 0057)
  7. APP_VERSION no Coolify ANTES do push
  8. um push em origin/main
  9. monitorar o build de cada service (webhook), forcar se nao disparar
 10. health com version match
 11. limpeza (worktree, branches pr-*, worktrees de agente ja mergeados) e soltar o semaforo
 12. linha final

Commits produzidos no worktree (todos no mesmo push):
  - um commit de merge por PR: "<titulo do PR> (#N)"
  - `chore(release): bump vX.Y.Z (onda <sessao>: #a #b)`   (so quando ha bump)
  - `chore(deploy): registro da onda <sessao> (vX.Y.Z)`     (bookkeeping)
O campo `sha` do history.json e o sha do commit de bump (ou do ultimo merge,
quando nao houve bump): e o ultimo commit que muda codigo. O commit de
registro so muda docs/spec e vem depois, no mesmo push.

Codigos de saida:
  0  onda fechada, health verde
  1  pre-condicao falhou ou trava velha: nada foi tocado
  2  conflito de merge ou push rejeitado: worktree removido, semaforo solto, rode de novo depois de corrigir
  3  build falhou no Coolify: SEMAFORO FICA PRESO, rode `/deploy rollback` com a chave impressa
  4  health falhou (ou versao nao bate): SEMAFORO FICA PRESO, mesma instrucao do 3

`--dry-run`: executa 1, 3, 4 e calcula o 5 sem escrever; imprime o que faria
nos demais; nao pega semaforo, nao toca no Coolify, nao pusha.

Windows: `bash` do Git no PATH (para o semaforo.sh), `PYTHONUTF8=1` no snapshot.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

EXIT_PRECOND = 1
EXIT_MERGE = 2
EXIT_BUILD = 3
EXIT_HEALTH = 4

PACKAGE_JSON = "hospital-reunioes/frontend/package.json"
SEMAFORO = ".claude/skills/deploy/scripts/semaforo.sh"
SNAPSHOT = ".claude/skills/snapshot/scripts/snapshot.py"
TIRAR_DRAFT = "tools/tirar_draft_manual.py"
PUBLICAR_MANUAL = "docs/manual/publicar.sh"
SPEC = "docs/spec"
DOCS_ONLY_PREFIXES = ("docs/", ".claude/")
HISTORY_MAX = 50
BUILD_WAIT_WEBHOOK_S = 120
BUILD_POLL_S = 10
BUILD_TIMEOUT_S = 40 * 60
COAUTHOR = "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"

# Windows: "bash" nu no subprocess cai no System32 (WSL) antes do PATH.
BASH = shutil.which("bash") or "bash"

T0 = time.time()


# ----------------------------------------------------------------- utilidades

def falhar(msg: str, code: int) -> None:
    print(msg)
    sys.exit(code)


def run(cmd: list[str], cwd: Path | None = None, check: bool = True,
        timeout: int | None = 600, env: dict | None = None) -> subprocess.CompletedProcess:
    full_env = dict(os.environ)
    full_env.setdefault("PYTHONUTF8", "1")
    if env:
        full_env.update(env)
    proc = subprocess.run(cmd, cwd=str(cwd) if cwd else None, capture_output=True,
                          text=True, encoding="utf-8", errors="replace",
                          timeout=timeout, env=full_env)
    if check and proc.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)} -> {proc.returncode}: {(proc.stderr or proc.stdout).strip()[:400]}")
    return proc


def gh_json(args: list[str], cwd: Path | None = None):
    proc = run(["gh", *args], cwd=cwd)
    return json.loads(proc.stdout or "null")


def ler_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def escrever_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def agora_iso() -> str:
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


def dur(seg: float | int | None) -> str:
    if seg is None:
        return "?"
    seg = int(seg)
    return f"{seg // 60}m{seg % 60:02d}s"


def bash_path(p: Path) -> str:
    return str(p).replace("\\", "/")


# ------------------------------------------------------------- pre-condicoes

def checar_pre_condicoes(raiz: Path, prs: list[int], dry: bool) -> list[dict]:
    if run(["gh", "auth", "status"], check=False).returncode != 0:
        falhar("pre-condicao: `gh auth status` falhou.", EXIT_PRECOND)
    if not shutil.which("coolify"):
        if dry:
            print("aviso: `coolify` nao esta no PATH (o dry-run segue; o fechamento real precisa dele).")
        else:
            falhar("pre-condicao: `coolify` nao esta no PATH.", EXIT_PRECOND)
    if not shutil.which("bash"):
        falhar("pre-condicao: `bash` (Git Bash) nao esta no PATH; o semaforo precisa dele.", EXIT_PRECOND)
    run(["git", "fetch", "-q", "origin", "main"], cwd=raiz)

    infos = []
    problemas = []
    for n in prs:
        info = None
        for tentativa in range(6):
            info = gh_json(["pr", "view", str(n), "--json",
                            "number,state,mergeable,mergeStateStatus,statusCheckRollup,headRefName,"
                            "baseRefName,title,files,commits,url,closingIssuesReferences"], cwd=raiz)
            if info.get("mergeable") != "UNKNOWN":
                break
            time.sleep(5)
        info["docs_only"] = all(
            f["path"].startswith(DOCS_ONLY_PREFIXES) or f["path"].endswith(".md")
            for f in info.get("files") or []
        )
        if info.get("state") != "OPEN":
            problemas.append(f"#{n} esta {info.get('state')}")
        if info.get("baseRefName") not in (None, "main"):
            problemas.append(f"#{n} tem base {info.get('baseRefName')}, nao main")
        if info.get("mergeable") != "MERGEABLE":
            problemas.append(f"#{n} nao e MERGEABLE ({info.get('mergeable')}/{info.get('mergeStateStatus')})")
        checks = info.get("statusCheckRollup") or []
        ruins = [c for c in checks
                 if (c.get("conclusion") or c.get("state") or "").upper()
                 not in ("SUCCESS", "NEUTRAL", "SKIPPED")]
        if ruins:
            nomes = ", ".join((c.get("name") or c.get("context") or "?") for c in ruins[:4])
            problemas.append(f"#{n} com check nao verde: {nomes}")
        elif not checks and not info["docs_only"]:
            problemas.append(f"#{n} sem nenhum check e nao e docs-only")
        infos.append(info)
    if problemas:
        falhar("pre-condicao: " + "; ".join(problemas) + ".", EXIT_PRECOND)
    return infos


# ----------------------------------------------------------------- semaforo

def semaforo(raiz: Path, acao: str, chave: str, descricao: str = "") -> int:
    cmd = [BASH, bash_path(raiz / SEMAFORO), acao, chave]
    if descricao:
        cmd.append(descricao)
    proc = run(cmd, cwd=raiz, check=False, timeout=700)
    return proc.returncode


def pegar_semaforo(raiz: Path, chave: str, prs: list[int]) -> None:
    desc = f"onda-enxuta {chave}: PRs " + " ".join(f"#{p}" for p in prs)
    while True:
        rc = semaforo(raiz, "pegar", chave, desc)
        if rc == 0:
            return
        if rc == 3:
            print("semaforo: outra sessao esta deployando, esperando mais um ciclo.")
            continue
        if rc == 2:
            falhar("semaforo: trava velha (mais de 60 min). Confira `coolify app deployments list` e, "
                   "sem build rodando, `semaforo.sh soltar <chave-do-dono> --forcar`.", EXIT_PRECOND)
        falhar(f"semaforo: saida inesperada {rc}.", EXIT_PRECOND)


# ----------------------------------------------------------------- worktree

def criar_worktree(raiz: Path, sessao: str) -> Path:
    wt = Path.home() / f"wt-{sessao}"
    if wt.exists():
        run(["git", "worktree", "remove", "--force", str(wt)], cwd=raiz, check=False)
        shutil.rmtree(wt, ignore_errors=True)
    run(["git", "worktree", "prune"], cwd=raiz, check=False)
    run(["git", "worktree", "add", "--detach", str(wt), "origin/main"], cwd=raiz)
    return wt


def remover_worktree(raiz: Path, wt: Path | None, prs: list[int]) -> None:
    if wt and wt.exists():
        run(["git", "worktree", "remove", "--force", str(wt)], cwd=raiz, check=False)
        shutil.rmtree(wt, ignore_errors=True)
    run(["git", "worktree", "prune"], cwd=raiz, check=False)
    for n in prs:
        run(["git", "branch", "-D", f"pr-{n}"], cwd=raiz, check=False)


# ------------------------------------------------------------------- merges

def mergear(wt: Path, infos: list[dict]) -> list[str]:
    shas = []
    for info in infos:
        n = info["number"]
        run(["git", "fetch", "-q", "origin", f"pull/{n}/head:pr-{n}"], cwd=wt)
        titulo = info["title"].strip()
        msg = titulo if f"(#{n})" in titulo else f"{titulo} (#{n})"
        proc = run(["git", "merge", "--no-ff", f"pr-{n}", "-m", msg], cwd=wt, check=False)
        if proc.returncode != 0:
            conflitos = run(["git", "diff", "--name-only", "--diff-filter=U"], cwd=wt, check=False).stdout.split()
            run(["git", "merge", "--abort"], cwd=wt, check=False)
            raise MergeConflito(n, conflitos)
        shas.append(run(["git", "rev-parse", "--short=8", "HEAD"], cwd=wt).stdout.strip())
    return shas


class MergeConflito(Exception):
    def __init__(self, pr: int, arquivos: list[str]):
        super().__init__(pr)
        self.pr = pr
        self.arquivos = arquivos


# --------------------------------------------------------------------- bump

def tipo_de_bump(infos: list[dict]) -> str | None:
    if all(i["docs_only"] for i in infos):
        return None
    nivel = "patch"
    for info in infos:
        for c in info.get("commits") or []:
            head = (c.get("messageHeadline") or "").strip()
            body = c.get("messageBody") or ""
            if "BREAKING CHANGE" in body or re.match(r"^\w+(\([^)]*\))?!:", head):
                return "major"
            if re.match(r"^feat(\([^)]*\))?:", head):
                nivel = "minor"
        if re.match(r"^feat(\([^)]*\))?:", info["title"].strip()) and nivel == "patch":
            nivel = "minor"
    return nivel


def proxima_versao(atual: str, tipo: str) -> str:
    major, minor, patch = (int(x) for x in atual.split(".")[:3])
    if tipo == "major":
        return f"{major + 1}.0.0"
    if tipo == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def ler_versao(wt: Path) -> str:
    return ler_json(wt / PACKAGE_JSON)["version"]


def escrever_versao(wt: Path, nova: str) -> None:
    p = wt / PACKAGE_JSON
    txt = p.read_text(encoding="utf-8")
    novo, n = re.subn(r'("version"\s*:\s*")[^"]+(")', rf"\g<1>{nova}\g<2>", txt, count=1)
    if n != 1:
        raise RuntimeError("nao achei o campo version no package.json")
    p.write_text(novo, encoding="utf-8")


# -------------------------------------------------------------- bookkeeping

def prds_do_lote(raiz: Path, infos: list[dict]) -> list[int]:
    prds = set()
    for info in infos:
        for ref in info.get("closingIssuesReferences") or []:
            try:
                body = gh_json(["issue", "view", str(ref["number"]), "--json", "body"], cwd=raiz).get("body") or ""
            except Exception:
                continue
            m = re.search(r"^## Pai[^\n]*\n(?:.*\n)*?[^\n]*#(\d+)", body, re.M)
            if not m:
                m = re.search(r"^## Pai[^\n]*#(\d+)", body, re.M)
            if m:
                prds.add(int(m.group(1)))
    return sorted(prds)


def migrations_novas(wt: Path, base: str) -> list[str]:
    out = run(["git", "diff", "--name-only", "--diff-filter=A", f"{base}..HEAD", "--",
               "hospital-reunioes/supabase/migrations/"], cwd=wt, check=False).stdout.split()
    return [Path(p).name for p in out]


def humanizar(subject: str) -> str:
    s = re.sub(r"^\w+(\([^)]*\))?!?:\s*", "", subject)
    s = re.sub(r"\s*\(#\d+\)\s*$", "", s)
    return (s[:1].upper() + s[1:]) if s else subject


def escrever_registro(wt: Path, sessao: str, infos: list[dict], versao: str | None, versao_antiga: str,
                      sha_codigo: str, prds: list[int], migs: list[str], servicos: list[str],
                      duracoes: dict[str, int | None], healths: dict[str, dict], resultado: str,
                      houve_bump: bool) -> None:
    spec = wt / SPEC / "deploy"
    history = ler_json(spec / "history.json")
    state = ler_json(spec / "state.json")
    when = agora_iso()
    prs_txt = " ".join(f"#{i['number']}" for i in infos)
    subject = (f"Onda {sessao}: " + "; ".join(humanizar(i["title"]) for i in infos))[:200]
    entrada = {
        "at": when,
        "sha": sha_codigo,
        "app_version": versao,
        "subject": subject,
        "raw_subject": f"chore(deploy): registro da onda {sessao} ({prs_txt})",
        "scope": servicos,
        "prds": prds,
        "result": resultado,
        "duration_seconds": int(time.time() - T0),
        "services_touched": servicos,
        "env_changes": ([{"service": "backend", "action": "update", "keys": ["APP_VERSION"]}] if houve_bump else []),
        "migrations_applied": migs,
        "rollback_target_sha": None,
        "notes": f"onda-enxuta {sessao}: PRs {prs_txt}. Um push, um build. Registro no commit seguinte ao sha.",
    }
    deploys = history.setdefault("deploys", [])
    deploys.insert(0, entrada)
    del deploys[HISTORY_MAX:]
    escrever_json(spec / "history.json", history)

    state["updated_at"] = when
    state["updated_by"] = "onda-enxuta@fechar_onda"
    if versao:
        state["last_app_version"] = versao
    for svc in state.get("services") or []:
        if svc.get("id") in servicos:
            svc["last_deploy_sha"] = sha_codigo
            svc["last_deploy_at"] = when
            h = healths.get(svc["id"]) or {}
            svc["status"] = "healthy" if h.get("ok") else "warning"
            svc["last_health_check"] = {"at": when, "latency_ms": h.get("latency_ms"),
                                        "http_status": h.get("status"), "body_ok": bool(h.get("ok"))}
            svc["build_duration_seconds"] = duracoes.get(svc["id"])
    state["last_run"] = {"mode": "onda-enxuta", "sha": sha_codigo, "result": resultado,
                         "duration_seconds": int(time.time() - T0)}
    state.pop("next_actions", None)
    escrever_json(spec / "state.json", state)

    changelog = wt / SPEC / "CHANGELOG.md"
    txt = changelog.read_text(encoding="utf-8") if changelog.exists() else "# Changelog Hospital Reuniões\n\n---\n\n"
    autor = run(["git", "config", "user.name"], cwd=wt, check=False).stdout.strip() or "desconhecido"
    email = run(["git", "config", "user.email"], cwd=wt, check=False).stdout.strip() or "?"
    repo = (state.get("production") or {}).get("repo") or ""
    emoji = {"healthy": "🟢", "failed": "🔴", "rolled-back": "🟡"}.get(resultado, "⚪")
    cabec = f"## v{versao} - " if versao else f"## v{versao_antiga} (sem bump) - "
    entrada_md = "\n".join([
        f"{cabec}{when[:16].replace('T', ' ')} - {subject}",
        f"- Autor: {autor} <{email}>",
        f"- SHA: `{sha_codigo[:7]}`",
        f"- PRs: " + ", ".join(f"[#{i['number']}]({i['url']})" for i in infos),
        f"- Serviços: {', '.join(servicos) or 'nenhum'}",
        f"- Resultado: {emoji} {resultado} ({int(time.time() - T0)}s)",
        f"- Commit: https://github.com/{repo}/commit/{sha_codigo[:7]}",
        "",
    ])
    linhas = txt.split("\n")
    pos = next((i + 1 for i, ln in enumerate(linhas) if ln.strip() == "---"), None)
    if pos is None:
        txt = txt.rstrip() + "\n\n" + entrada_md
    else:
        while pos < len(linhas) and linhas[pos].strip() == "":
            pos += 1
        linhas.insert(pos, entrada_md)
        txt = "\n".join(linhas)
    changelog.write_text(txt, encoding="utf-8")


def rodar_snapshot(wt: Path) -> str:
    script = wt / SNAPSHOT
    if not script.exists():
        return "snapshot ausente"
    proc = run([sys.executable, str(script), "--no-commit", "--root", str(wt)], cwd=wt, check=False,
               timeout=600, env={"PYTHONUTF8": "1"})
    if proc.returncode == 0:
        return "snapshot ok"
    if proc.returncode == 4:
        return "snapshot parcial (sem venv, codigo 4)"
    return f"snapshot pulado (#844, codigo {proc.returncode})"


def tirar_draft_manual(wt: Path, prds: list[int]) -> tuple[str, bool]:
    """Devolve (linha, houve_pagina)."""
    script = wt / TIRAR_DRAFT
    if not prds or not script.exists():
        return ("manual: nenhum PRD no lote" if not prds else "manual: script ausente"), False
    args = []
    for p in prds:
        args += ["--prd", str(p)]
    proc = run([sys.executable, str(script), *args], cwd=wt, check=False, timeout=300, env={"PYTHONUTF8": "1"})
    saida = (proc.stdout or "").strip().replace("\n", " | ")[:200]
    if proc.returncode == 2:
        return f"manual: bloqueado, nada tocado ({saida})", False
    if proc.returncode != 0:
        return f"manual: script falhou ({proc.returncode})", False
    mudou = run(["git", "status", "--porcelain", "--", "docs/manual"], cwd=wt, check=False).stdout.strip()
    if mudou:
        return f"manual: paginas sairam do draft ({saida})", True
    return "manual: nenhuma pagina em draft", False


def commitar(wt: Path, msg: str, paths: list[str]) -> str:
    existentes = [p for p in paths if (wt / p).exists()]
    if existentes:
        run(["git", "add", "--", *existentes], cwd=wt)
    if not run(["git", "status", "--porcelain"], cwd=wt).stdout.strip():
        return run(["git", "rev-parse", "--short=8", "HEAD"], cwd=wt).stdout.strip()
    run(["git", "commit", "-q", "-m", msg, "-m", COAUTHOR], cwd=wt)
    return run(["git", "rev-parse", "--short=8", "HEAD"], cwd=wt).stdout.strip()


# ------------------------------------------------------------------ coolify

def coolify_json(args: list[str], timeout: int = 120):
    proc = run(["coolify", *args, "--format", "json"], check=False, timeout=timeout)
    if proc.returncode != 0:
        return None
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None


def setar_app_version(backend_uuid: str, versao: str) -> None:
    proc = run(["coolify", "app", "env", "update", backend_uuid, "APP_VERSION", "--value", versao], check=False)
    if proc.returncode != 0:
        run(["coolify", "app", "env", "create", backend_uuid, "--key", "APP_VERSION", "--value", versao])


def _lista(d):
    if isinstance(d, list):
        return d
    if isinstance(d, dict):
        for k in ("data", "deployments", "items"):
            if isinstance(d.get(k), list):
                return d[k]
    return []


def _campo(d: dict, *nomes, default=None):
    for n in nomes:
        if n in d and d[n] not in (None, ""):
            return d[n]
    return default


def _parse_ts(v) -> float | None:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def esperar_build(service: dict, desde: float, sha_push: str) -> tuple[str, int | None]:
    """Espera o deploy disparado pelo webhook. Devolve (status, duracao_s)."""
    uuid = service["uuid"]
    dep = None
    limite = time.time() + BUILD_WAIT_WEBHOOK_S
    forcado = False
    while dep is None:
        for d in _lista(coolify_json(["app", "deployments", "list", uuid])):
            criado = _parse_ts(_campo(d, "created_at", "createdAt"))
            commit = str(_campo(d, "commit", "git_commit_sha", default=""))
            if (criado and criado >= desde - 60) or (sha_push and commit.startswith(sha_push)):
                dep = d
                break
        if dep is None:
            if time.time() > limite and not forcado:
                run(["coolify", "deploy", "uuid", uuid], check=False)
                forcado = True
                limite = time.time() + BUILD_WAIT_WEBHOOK_S
            elif time.time() > limite:
                return "sem-deploy", None
            time.sleep(BUILD_POLL_S)
    dep_id = _campo(dep, "deployment_uuid", "uuid", "id")
    fim = time.time() + BUILD_TIMEOUT_S
    status = str(_campo(dep, "status", default="")).lower()
    while status not in ("finished", "failed", "cancelled") and time.time() < fim:
        time.sleep(BUILD_POLL_S)
        atual = coolify_json(["deploy", "get", str(dep_id)]) or {}
        if isinstance(atual, dict) and "data" in atual and isinstance(atual["data"], dict):
            atual = atual["data"]
        if atual:
            dep = atual
            status = str(_campo(dep, "status", default=status)).lower()
    ini = _parse_ts(_campo(dep, "started_at", "created_at"))
    fim_ts = _parse_ts(_campo(dep, "finished_at", "updated_at"))
    duracao = int(fim_ts - ini) if ini and fim_ts else None
    return status or "desconhecido", duracao


# ------------------------------------------------------------------- health

def checar_health(service: dict, versao_esperada: str | None) -> dict:
    hc = (service.get("deploy") or {}).get("health_check") or {}
    url = hc.get("url") or ((service.get("deploy") or {}).get("fqdn") or "") + (hc.get("path") or "/")
    if not url:
        return {"ok": True, "status": None, "latency_ms": None, "nota": "sem health"}
    resultado = {"ok": False, "status": None, "latency_ms": None}
    for tentativa in range(6):
        t = time.time()
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "fechar_onda"}), timeout=15) as r:
                body = r.read().decode("utf-8", "replace")
                resultado["status"] = r.status
        except urllib.error.HTTPError as e:
            resultado["status"] = e.code
            body = ""
        except Exception:
            body = ""
        resultado["latency_ms"] = int((time.time() - t) * 1000)
        ok = resultado["status"] == hc.get("expected_status", 200)
        regex = hc.get("expected_body_regex")
        if ok and regex and not re.search(regex, body.strip()):
            ok = False
        if ok and versao_esperada and regex:
            try:
                versao = json.loads(body).get("version")
            except Exception:
                versao = None
            resultado["versao"] = versao
            if versao != versao_esperada:
                ok = False
                resultado["nota"] = f"esperava v{versao_esperada}, /api/health devolveu v{versao}"
        resultado["ok"] = ok
        if ok:
            return resultado
        time.sleep(10)
    return resultado


# ------------------------------------------------------------------ limpeza

def limpar_worktrees_de_agente(raiz: Path) -> int:
    porcelain = run(["git", "worktree", "list", "--porcelain"], cwd=raiz, check=False).stdout
    merged = set(b.strip().lstrip("* ").strip() for b in
                 run(["git", "branch", "--merged", "origin/main"], cwd=raiz, check=False).stdout.splitlines())
    removidos = 0
    atual_path, atual_branch = None, None
    entradas = []
    for ln in porcelain.splitlines() + [""]:
        if ln.startswith("worktree "):
            atual_path = ln[9:].strip()
        elif ln.startswith("branch "):
            atual_branch = ln[7:].strip().replace("refs/heads/", "")
        elif ln == "":
            if atual_path:
                entradas.append((atual_path, atual_branch))
            atual_path, atual_branch = None, None
    for path, branch in entradas:
        if ".claude/worktrees/" not in path.replace("\\", "/") or not branch:
            continue
        if branch in merged and branch != "main":
            run(["git", "worktree", "remove", "--force", path], cwd=raiz, check=False)
            run(["git", "branch", "-d", branch], cwd=raiz, check=False)
            removidos += 1
    run(["git", "worktree", "prune"], cwd=raiz, check=False)
    return removidos


def conferir_prs_fechados(raiz: Path, infos: list[dict], sessao: str) -> None:
    for info in infos:
        n = info["number"]
        estado = gh_json(["pr", "view", str(n), "--json", "state"], cwd=raiz).get("state")
        if estado == "OPEN":
            run(["gh", "pr", "close", str(n), "--comment",
                 f"<!-- automacao -->\nIntegrado na main pela onda-enxuta {sessao} (merge local `--no-ff`, um push por onda)."],
                cwd=raiz, check=False)


# --------------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser(description="Fecha uma onda: um push, um build.")
    ap.add_argument("--prs", nargs="+", type=int, required=True, help="PRs na ordem de merge")
    ap.add_argument("--sessao", required=True, help="nome da sessao (chave do semaforo)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--sem-snapshot", action="store_true")
    ap.add_argument("--raiz", help="raiz do repositorio (default: git rev-parse)")
    args = ap.parse_args()

    if not re.fullmatch(r"[A-Za-z0-9._-]+", args.sessao):
        falhar("--sessao so aceita letras, numeros, ponto, hifen e underscore.", EXIT_PRECOND)
    raiz = Path(args.raiz).resolve() if args.raiz else Path(
        run(["git", "rev-parse", "--show-toplevel"]).stdout.strip()).resolve()
    projeto = ler_json(raiz / SPEC / "deploy" / "project.json")
    servicos_cfg = {s["id"]: s for s in projeto["services"]}
    backend = servicos_cfg.get("backend")

    infos = checar_pre_condicoes(raiz, args.prs, args.dry_run)
    prs_txt = " ".join(f"#{i['number']}" for i in infos)
    print(f"pre-condicoes ok: {prs_txt}" + (" (dry-run)" if args.dry_run else ""))

    wt = None
    semaforo_pego = False
    pushou = False
    try:
        if not args.dry_run:
            pegar_semaforo(raiz, args.sessao, args.prs)
            semaforo_pego = True
        wt = criar_worktree(raiz, args.sessao)
        base = run(["git", "rev-parse", "--short=8", "HEAD"], cwd=wt).stdout.strip()

        try:
            shas_merge = mergear(wt, infos)
        except MergeConflito as e:
            remover_worktree(raiz, wt, args.prs)
            wt = None
            if semaforo_pego:
                semaforo(raiz, "soltar", args.sessao)
            falhar(f"conflito no merge de #{e.pr} em: {', '.join(e.arquivos) or '?'}. "
                   f"Mande um corretor rebasear o PR sobre origin/main e rode de novo.", EXIT_MERGE)
        print(f"merges ok: {len(shas_merge)} PRs sobre {base}")

        versao_antiga = ler_versao(wt)
        tipo = tipo_de_bump(infos)
        versao_nova = proxima_versao(versao_antiga, tipo) if tipo else None
        docs_only = tipo is None
        arquivos = set()
        for i in infos:
            arquivos.update(f["path"] for f in i.get("files") or [])
        # supabase nao tem build: migration se aplica a mao no Studio (o deploy nao aplica SQL)
        servicos = [sid for sid, s in servicos_cfg.items()
                    if s.get("type") != "supabase" and any(re.match(tp.replace("**", ".*").replace("*", "[^/]*"), a)
                           for a in arquivos for tp in (s.get("diff_routing") or {}).get("trigger_paths") or [])]
        if not docs_only and not servicos:
            servicos = [sid for sid, s in servicos_cfg.items() if s.get("type") in ("nextjs", "fastapi", "node", "python", "generic")]
        prds = prds_do_lote(raiz, infos)
        migs = migrations_novas(wt, base)

        if args.dry_run:
            print(f"bump: v{versao_antiga} -> " + (f"v{versao_nova} ({tipo})" if tipo else "sem bump (lote docs-only)"))
            print(f"faria: registro (prds {prds or '[]'}, migrations {migs or '[]'}, services {servicos or '[]'}), "
                  + ("APP_VERSION no Coolify, " if versao_nova else "") + "um push, build, health, limpeza.")
            remover_worktree(raiz, wt, args.prs)
            wt = None
            print("dry-run terminou sem tocar em nada.")
            return 0

        sha_codigo = shas_merge[-1]
        if versao_nova:
            escrever_versao(wt, versao_nova)
            sha_codigo = commitar(wt, f"chore(release): bump v{versao_nova} (onda {args.sessao}: {prs_txt})", [PACKAGE_JSON])
            print(f"bump: v{versao_antiga} -> v{versao_nova} ({tipo}) em {sha_codigo}")
        else:
            print(f"bump: nenhum (lote docs-only), versao segue v{versao_antiga}")

        linha_snap = "snapshot pulado (--sem-snapshot)" if args.sem_snapshot else rodar_snapshot(wt)
        linha_manual, houve_pagina = tirar_draft_manual(wt, prds)
        # registro provisorio: resultado e health preenchidos como "pending" e corrigidos apos o deploy?
        # Nao: um push so. O registro nasce com o resultado esperado e, se o build ou o health
        # falharem, o codigo de saida 3/4 e a instrucao de rollback sao a fonte de verdade.
        escrever_registro(wt, args.sessao, infos, versao_nova, versao_antiga, sha_codigo, prds, migs,
                          servicos, {}, {}, "healthy", bool(versao_nova))
        commitar(wt, f"chore(deploy): registro da onda {args.sessao} (v{versao_nova or versao_antiga})",
                 [SPEC, "docs/manual", "docs/ARQUITETURA.md"])
        print(f"registro: history/state/CHANGELOG, {linha_snap}, {linha_manual}")

        if versao_nova and backend:
            setar_app_version(backend["uuid"], versao_nova)

        t_push = time.time()
        proc = run(["git", "push", "origin", "HEAD:main"], cwd=wt, check=False)
        if proc.returncode != 0:
            remover_worktree(raiz, wt, args.prs)
            wt = None
            semaforo(raiz, "soltar", args.sessao)
            falhar(f"push rejeitado ({(proc.stderr or '').strip()[:200]}). A main andou: rode de novo.", EXIT_MERGE)
        pushou = True
        sha_push = run(["git", "rev-parse", "HEAD"], cwd=wt).stdout.strip()
        print(f"push: {sha_push[:8]} em origin/main (um push, {len(infos)} PRs)")

        duracoes: dict[str, int | None] = {}
        falhas = []
        if not docs_only:
            for sid in servicos:
                status, d = esperar_build(servicos_cfg[sid], t_push, sha_push)
                duracoes[sid] = d
                if status != "finished":
                    falhas.append(f"{sid}: {status}")
        if falhas:
            print("build: " + "; ".join(falhas) + f". Semaforo preso na chave {args.sessao}: rode `/deploy rollback` com ela.")
            remover_worktree(raiz, wt, args.prs)
            wt = None
            return EXIT_BUILD
        print("build: " + (", ".join(f"{sid} {dur(duracoes.get(sid))}" for sid in servicos) if servicos else "nenhum (docs-only)"))

        healths = {}
        for sid in (servicos or [s for s in servicos_cfg if s != "supabase"]):
            healths[sid] = checar_health(servicos_cfg[sid], versao_nova if sid == "backend" else None)
        ruins = [f"{sid}: http {h.get('status')} {h.get('nota', '')}".strip() for sid, h in healths.items() if not h["ok"]]
        if ruins:
            print("health: " + "; ".join(ruins) + f". Semaforo preso na chave {args.sessao}: rode `/deploy rollback` com ela.")
            remover_worktree(raiz, wt, args.prs)
            wt = None
            return EXIT_HEALTH
        vm = " (version match)" if versao_nova else ""
        print(f"health: ok{vm}")

        if houve_pagina and (raiz / PUBLICAR_MANUAL).exists():
            pub = run([BASH, bash_path(wt / PUBLICAR_MANUAL)], cwd=wt, check=False, timeout=900)
            print("manual publicado" if pub.returncode == 0 else f"manual: publicar.sh falhou ({pub.returncode}); rode a mao depois")

        conferir_prs_fechados(raiz, infos, args.sessao)
        remover_worktree(raiz, wt, args.prs)
        wt = None
        n_wt = limpar_worktrees_de_agente(raiz)
        semaforo(raiz, "soltar", args.sessao)
        semaforo_pego = False
        builds = ", ".join(f"{sid} {dur(duracoes.get(sid))}" for sid in servicos) or "sem build"
        print(f"onda {args.sessao} fechada: v{versao_antiga} -> v{versao_nova or versao_antiga} · PRs {prs_txt} · "
              f"push {sha_push[:7]} · build {builds} · health ok{vm} · {n_wt} worktrees limpos · {dur(time.time() - T0)}")
        return 0
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        print(f"erro: {e}")
        if wt:
            remover_worktree(raiz, wt, args.prs)
        if pushou:
            print(f"o push ja aconteceu. Semaforo preso na chave {args.sessao}: confira o Coolify e o health, "
                  f"depois `semaforo.sh soltar {args.sessao}` ou `/deploy rollback`.")
            return EXIT_BUILD
        if semaforo_pego:
            semaforo(raiz, "soltar", args.sessao)
        return EXIT_MERGE


if __name__ == "__main__":
    sys.exit(main())
