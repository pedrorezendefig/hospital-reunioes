#!/usr/bin/env python3
"""medir_onda.py: a conta de tokens de uma onda da `/onda-enxuta`.

Uso:
    python medir_onda.py --onda N --issues 850,851 --prs 860,861 [--sessao <id ou prefixo>]
                         [--inicio <ISO>] [--fim <ISO>] [--saida <pasta>] [--projeto <cwd>]

Sem `--sessao`, le CLAUDE_CODE_SESSION_ID do ambiente (a sessao mede a si mesma).
`--prs 0` pula as consultas ao GitHub (rodadas de CI e de revisao).

Metodo (o mesmo das retros de setembro de 2026): agrega o campo `usage` dos
registros `assistant` do JSONL da sessao (`~/.claude/projects/<slug>/<sessao>.jsonl`)
e dos sub-agentes (`~/.claude/projects/<slug>/<sessao>/subagents/agent-*.jsonl`;
`tasks/*.output` so como reserva), deduplicado por id de mensagem com o MAXIMO de
cada campo (o streaming grava a mesma mensagem varias vezes, com saida parcial).
`--inicio`/`--fim` recortam a janela: numa sessao que atravessa varias ondas,
so conta o que caiu dentro dela.
Tokens (chave `tokens_equivalentes` no JSON, por compatibilidade) = soma BRUTA de
input + escrita de cache + leitura de cache + saida. Nao e o "eq" das retros de
setembro (custo dividido pelo preco do input); para comparar com elas use o custo.
Contexto maximo = maior (input + escrita + leitura) numa chamada.

Sub-agente sem transcript em lugar nenhum: o script usa o
`<subagent_tokens>` da task-notification que ficou no JSONL da sessao pai e marca
o agente como "estimado" (o numero da notificacao mistura tipos de token).

Saida: um JSON em `<saida>/<AAAA-MM-DD>-<sessao>-onda<N>.json` (default: pasta
`~/.claude/onda-enxuta/medicoes/`, fora do repositório) e ate 10 linhas no terminal.
Nao escreve em lugar nenhum do repositorio nem no GitHub.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Preco por milhao de tokens (USD), cache de 5 minutos. Conferido em 22/09/2026.
PRECOS = {
    "claude-opus-5-5": {"input": 4.0, "output": 20.0, "cache_write": 5.0, "cache_read": 0.20},
    "claude-opus-5":   {"input": 5.0, "output": 25.0, "cache_write": 6.25, "cache_read": 0.50},
    "claude-opus-4-8": {"input": 5.0, "output": 25.0, "cache_write": 6.25, "cache_read": 0.50},
    "claude-fable-5-1": {"input": 10.0, "output": 50.0, "cache_write": 12.50, "cache_read": 0.25},
    "claude-sonnet-5": {"input": 2.0, "output": 10.0, "cache_write": 2.50, "cache_read": 0.20},
}
PRECO_PADRAO = "claude-opus-5-5"

CHAVES = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens")

# Os prompts da onda-enxuta comecam com "[papel: <nome>]"; a lista abaixo e o
# fallback por palavra-chave para sessoes antigas (ordem importa).
PAPEIS = [
    ("revisor-seguranca", r"revisor de seguran[cç]a|security review"),
    ("auditor-prd", r"auditor|audit(a|e|oria)"),
    ("corretor", r"corretor|corrig[ai]|rebase"),
    ("implementador", r"implement|desenvolvimento|tdd|pr verde"),
    ("mapeador", r"mapa do terreno|mapeador"),
    ("revisor", r"revis[aã]o|revisor|review|ache problemas"),
]
AGENT_ID = re.compile(r"^a[0-9a-f]{16}$")


def slug_do_projeto(cwd: str) -> str:
    return re.sub(r"[:\\/]", "-", cwd)


def achar_pasta_projeto(cwd: str) -> Path | None:
    base = Path.home() / ".claude" / "projects"
    slug = slug_do_projeto(cwd)
    candidatos = [base / slug, base / (slug[:1].lower() + slug[1:]), base / (slug[:1].upper() + slug[1:])]
    for c in candidatos:
        if c.is_dir():
            return c
    for c in base.iterdir() if base.is_dir() else []:
        if c.is_dir() and c.name.lower() == slug.lower():
            return c
    return None


def achar_pasta_tasks(cwd: str, sessao_completa: str) -> Path | None:
    raiz = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")) / "Temp" / "claude"
    if not raiz.is_dir():
        raiz = Path("/tmp/claude")
    slug = slug_do_projeto(cwd)
    for pasta in [raiz / slug] + [p for p in raiz.iterdir() if p.is_dir() and p.name.lower() == slug.lower()] if raiz.is_dir() else []:
        t = pasta / sessao_completa / "tasks"
        if t.is_dir():
            return t
    return None


def agregar(path: Path, inicio: datetime | None = None, fim: datetime | None = None) -> dict:
    # Por id de mensagem, o MAXIMO de cada campo: o streaming regrava a mesma
    # mensagem com saida parcial, entao a primeira copia subconta a saida.
    por_id: dict[str, dict] = {}
    tools = Counter()
    primeiro_ts = None
    ultimo_ts = None
    primeiro_prompt = ""
    with open(path, encoding="utf-8", errors="replace") as fh:
        for linha in fh:
            try:
                d = json.loads(linha)
            except json.JSONDecodeError:
                continue
            if not isinstance(d, dict):
                continue
            t = d.get("type")
            m = d.get("message") or {}
            if t == "user" and not primeiro_prompt and isinstance(m, dict):
                c = m.get("content")
                if isinstance(c, str):
                    primeiro_prompt = c[:600]
                elif isinstance(c, list):
                    primeiro_prompt = " ".join(b.get("text", "") for b in c if isinstance(b, dict))[:600]
            ts = d.get("timestamp")
            quando = parse_iso(ts)
            if quando and ((inicio and quando < inicio) or (fim and quando > fim)):
                continue  # fora da janela da onda (sessao que atravessa varias ondas)
            if ts:
                primeiro_ts = primeiro_ts or ts
                ultimo_ts = ts
            if t != "assistant" or not isinstance(m, dict):
                continue
            for b in m.get("content") or []:
                if isinstance(b, dict) and b.get("type") == "tool_use":
                    tools[b.get("name")] += 1
            us = m.get("usage") or {}
            mid = m.get("id")
            if not us or not mid:
                continue
            reg = por_id.setdefault(mid, {"modelo": m.get("model") or "?", "pensamento": 0, **{k: 0 for k in CHAVES}})
            for k in CHAVES:
                reg[k] = max(reg[k], int(us.get(k) or 0))
            reg["pensamento"] = max(reg["pensamento"],
                                    int(((us.get("output_tokens_details") or {}).get("thinking_tokens")) or 0))
    u = Counter()
    modelos = Counter()
    for reg in por_id.values():
        modelos[reg["modelo"]] += 1
        for k in CHAVES:
            u[k] += reg[k]
    turnos = len(por_id)
    pensamento = sum(r["pensamento"] for r in por_id.values())
    ctx_max = max((sum(r[k] for k in CHAVES[:3]) for r in por_id.values()), default=0)
    return {
        "turnos": turnos, "tokens": dict(u), "contexto_max": ctx_max, "pensamento": pensamento,
        "ferramentas": dict(tools.most_common(6)), "modelos": dict(modelos),
        "primeiro_ts": primeiro_ts, "ultimo_ts": ultimo_ts, "primeiro_prompt": primeiro_prompt,
    }


def papel_de(nome_arquivo: str, prompt: str, e_sessao: bool) -> str:
    if e_sessao:
        return "orquestrador"
    texto = (prompt or "").lower()
    m = re.search(r"\[papel:\s*([a-z0-9-]+)\]", texto)
    if m:
        return m.group(1)
    for papel, rx in PAPEIS:
        if re.search(rx, texto):
            return papel
    return "sub-agente"


def equivalentes(tok: dict) -> int:
    return sum(int(tok.get(k) or 0) for k in CHAVES)


def custo(tok: dict, modelo: str) -> float:
    p = PRECOS.get(modelo) or PRECOS[PRECO_PADRAO]
    return (tok.get("input_tokens", 0) * p["input"] + tok.get("output_tokens", 0) * p["output"]
            + tok.get("cache_creation_input_tokens", 0) * p["cache_write"]
            + tok.get("cache_read_input_tokens", 0) * p["cache_read"]) / 1e6


def notificacoes_de_subagente(sessao_jsonl: Path) -> dict[str, int]:
    """task-id -> subagent_tokens (o maior visto), lido das task-notifications do pai."""
    achados: dict[str, int] = {}
    rx = re.compile(r"<task-id>([^<]+)</task-id>.*?<subagent_tokens>(\d+)</subagent_tokens>", re.S)
    with open(sessao_jsonl, encoding="utf-8", errors="replace") as fh:
        for linha in fh:
            if "subagent_tokens" not in linha:
                continue
            for tid, n in rx.findall(linha.replace("\\n", "\n")):
                achados[tid] = max(achados.get(tid, 0), int(n))
    return achados


def gh_json(args: list[str]):
    proc = subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        return None
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None


def rodadas_no_github(prs: list[int]) -> dict:
    out = {}
    for n in prs:
        info = gh_json(["pr", "view", str(n), "--json", "headRefName,comments"]) or {}
        ref = info.get("headRefName")
        runs = gh_json(["run", "list", "--branch", ref, "--limit", "30", "--json", "conclusion,createdAt"]) if ref else None
        runs = runs or []
        comentarios = info.get("comments") or []
        revisoes = sum(1 for c in comentarios
                       if (c.get("body") or "").lstrip().startswith("<!-- automacao -->")
                       and "eredito" in (c.get("body") or ""))
        out[str(n)] = {
            "branch": ref,
            "ci_rodadas": len(runs),
            "ci_falhas": sum(1 for r in runs if (r.get("conclusion") or "").lower() == "failure"),
            "revisoes": revisoes,
        }
    return out


def parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Conta de tokens de uma onda.")
    ap.add_argument("--onda", type=int, required=True)
    ap.add_argument("--issues", required=True, help="issues entregues, separadas por virgula")
    ap.add_argument("--prs", required=True, help="PRs da onda, separados por virgula; 0 pula o GitHub")
    ap.add_argument("--sessao", default=os.environ.get("CLAUDE_CODE_SESSION_ID"))
    ap.add_argument("--inicio")
    ap.add_argument("--fim")
    ap.add_argument("--saida")
    ap.add_argument("--projeto", default=os.getcwd(), help="cwd do projeto (para achar o slug)")
    ap.add_argument("--modelo", default=None, help="modelo para o preco quando o JSONL nao diz")
    args = ap.parse_args()

    if not args.sessao:
        print("sem --sessao e sem CLAUDE_CODE_SESSION_ID no ambiente.")
        return 1
    pasta = achar_pasta_projeto(args.projeto)
    if not pasta:
        print(f"nao achei a pasta do projeto em ~/.claude/projects para {args.projeto}")
        return 1
    jsonls = sorted(glob.glob(str(pasta / f"{args.sessao}*.jsonl")))
    if not jsonls:
        print(f"nenhum JSONL {args.sessao}* em {pasta}")
        return 1
    sessao_jsonl = Path(jsonls[0])
    sessao_id = sessao_jsonl.stem
    tasks = achar_pasta_tasks(args.projeto, sessao_id)
    janela_ini, janela_fim = parse_iso(args.inicio), parse_iso(args.fim)

    agentes = []
    principal = agregar(sessao_jsonl, janela_ini, janela_fim)
    principal.update({"arquivo": sessao_jsonl.name, "papel": "orquestrador", "estimado": False})
    agentes.append(principal)

    # Transcript de sub-agente: primeiro `<projeto>/<sessao>/subagents/agent-<id>.jsonl`
    # (onde o Claude Code grava hoje); `tasks/<id>.output` so quando nao vier vazio.
    transcritos: dict[str, Path] = {}
    for f in sorted(glob.glob(str(sessao_jsonl.with_suffix("") / "subagents" / "agent-*.jsonl"))):
        transcritos[Path(f).stem.removeprefix("agent-")] = Path(f)
    ids = set(transcritos)
    for out in glob.glob(str(tasks / "*.output")) if tasks else []:
        p = Path(out)
        if AGENT_ID.match(p.stem):  # o resto e saida de comando em background
            ids.add(p.stem)
            if p.stem not in transcritos and p.stat().st_size > 0:
                transcritos[p.stem] = p
    estimativas = notificacoes_de_subagente(sessao_jsonl)
    for tid in sorted(ids):
        p = transcritos.get(tid)
        if p is None:
            est = estimativas.get(tid)
            agentes.append({"arquivo": f"{tid} (sem transcript)", "papel": "sub-agente", "turnos": None,
                            "contexto_max": None, "pensamento": 0, "ferramentas": {}, "modelos": {},
                            "estimado": True, "tokens": {"cache_read_input_tokens": est or 0} if est else {}})
            continue
        a = agregar(p, janela_ini, janela_fim)
        if not a["turnos"]:
            continue  # sub-agente de outra onda da mesma sessao
        a.update({"arquivo": p.name, "papel": papel_de(p.name, a["primeiro_prompt"], False), "estimado": False})
        agentes.append(a)

    modelo_dominante = args.modelo or Counter(
        m for a in agentes for m, n in (a.get("modelos") or {}).items() if m in PRECOS for _ in range(n)
    ).most_common(1)
    if isinstance(modelo_dominante, list):
        modelo_dominante = modelo_dominante[0][0] if modelo_dominante else PRECO_PADRAO
    for a in agentes:
        tok = a.get("tokens") or {}
        a["equivalentes"] = equivalentes(tok)
        modelo_a = next(iter(a.get("modelos") or {}), modelo_dominante)
        a["custo_usd"] = round(custo(tok, modelo_a if modelo_a in PRECOS else modelo_dominante), 2)
        a.pop("primeiro_prompt", None)

    total = Counter()
    for a in agentes:
        for k, v in (a.get("tokens") or {}).items():
            total[k] += v
    tot_eq = sum(a["equivalentes"] for a in agentes)
    tot_custo = round(sum(a["custo_usd"] for a in agentes), 2)
    por_papel: dict[str, dict] = {}
    for a in agentes:
        pp = por_papel.setdefault(a["papel"], {"agentes": 0, "turnos": 0, "contexto_max": 0, "equivalentes": 0, "custo_usd": 0.0})
        pp["agentes"] += 1
        pp["turnos"] += a.get("turnos") or 0
        pp["contexto_max"] = max(pp["contexto_max"], a.get("contexto_max") or 0)
        pp["equivalentes"] += a["equivalentes"]
        pp["custo_usd"] = round(pp["custo_usd"] + a["custo_usd"], 2)

    issues = [int(x) for x in args.issues.split(",") if x.strip()]
    prs = [int(x) for x in args.prs.split(",") if x.strip() and x.strip() != "0"]
    inicio = parse_iso(args.inicio) or parse_iso(principal.get("primeiro_ts"))
    fim = parse_iso(args.fim) or parse_iso(principal.get("ultimo_ts")) or datetime.now(timezone.utc)
    minutos = round((fim - inicio).total_seconds() / 60) if inicio and fim else None
    github = rodadas_no_github(prs) if prs else {}

    resultado = {
        "sessao": sessao_id, "onda": args.onda, "medido_em": datetime.now().astimezone().replace(microsecond=0).isoformat(),
        "modelo_para_preco": modelo_dominante, "issues": issues, "prs": prs,
        "tokens": dict(total), "tokens_equivalentes": tot_eq,
        "tokens_equivalentes_por_issue": round(tot_eq / len(issues)) if issues else None,
        "custo_usd_api": tot_custo, "custo_usd_por_issue": round(tot_custo / len(issues), 2) if issues else None,
        "turnos": sum(a.get("turnos") or 0 for a in agentes), "agentes": len(agentes),
        "contexto_max": max((a.get("contexto_max") or 0) for a in agentes),
        "minutos": minutos, "inicio": inicio.isoformat() if inicio else None, "fim": fim.isoformat() if fim else None,
        "github": github, "por_papel": por_papel, "por_agente": agentes,
    }

    saida = Path(args.saida) if args.saida else Path.home() / ".claude" / "onda-enxuta" / "medicoes"
    saida.mkdir(parents=True, exist_ok=True)
    nome = f"{datetime.now():%Y-%m-%d}-{sessao_id[:8]}-onda{args.onda}.json"
    (saida / nome).write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")

    def m(n: int) -> str:
        return f"{n / 1e6:.1f}M" if n >= 1e6 else f"{n / 1e3:.0f}k"

    print(f"{'papel':18} {'ag':>3} {'turnos':>6} {'ctx max':>8} {'tokens':>10} {'US$':>7}")
    for papel, pp in sorted(por_papel.items(), key=lambda kv: -kv[1]["equivalentes"]):
        print(f"{papel:18} {pp['agentes']:>3} {pp['turnos']:>6} {m(pp['contexto_max']):>8} {m(pp['equivalentes']):>10} {pp['custo_usd']:>7.2f}")
    est = sum(1 for a in agentes if a.get("estimado"))
    print(f"total: {m(tot_eq)} tokens · {resultado['turnos']} turnos · {len(agentes)} agentes"
          + (f" ({est} estimados)" if est else "") + f" · US$ {tot_custo:.2f} a preco de API ({modelo_dominante})")
    print(f"por issue: {m(resultado['tokens_equivalentes_por_issue'] or 0)} tokens · US$ {resultado['custo_usd_por_issue'] or 0:.2f} · {len(issues)} issues")
    ci = sum(g["ci_rodadas"] for g in github.values())
    rev = sum(g["revisoes"] for g in github.values())
    print(f"parede: {minutos if minutos is not None else '?'} min · CI {ci} rodadas · revisao {rev} vereditos"
          + ("" if prs else " (GitHub pulado)"))
    print(f"gravado: {saida / nome}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
