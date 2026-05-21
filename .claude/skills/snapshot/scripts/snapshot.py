#!/usr/bin/env python3
# snapshot.py — gera docs/spec/snapshots/*.md a partir do código fonte
# stdlib only. Self-contained. Idempotente.
#
# Uso:
#   python3 .claude/skills/snapshot/scripts/snapshot.py [--check] [--force]
#     [--diff <base>..HEAD] [--only ROTAS|ENTIDADES|SCHEMA|MIGRATIONS|INTEGRACOES]
#
# Saída: regenera 5 MDs auto-gerados (ROTAS, ENTIDADES, SCHEMA, MIGRATIONS,
# INTEGRACOES). FLUXOGRAMAS e ESTRUTURA são curados humano (script só alerta
# de gaps). Idempotente: se nada relevante mudou, exit 0 sem escrever.
#
# Invocado pelo /deploy ship no Passo 9.4 (pós-health verde).

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
import sys
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Constantes
TARGET_FILES = ["ROTAS", "ENTIDADES", "SCHEMA", "MIGRATIONS", "INTEGRACOES"]
CURATED_FILES = ["FLUXOGRAMAS", "ESTRUTURA"]  # script só alerta gaps, não regenera
TIMESTAMP_COMMENT = re.compile(r"<!--\s*last_update:[^>]*-->", re.IGNORECASE)


# ╔════════════════════════════════════════════════════════════════════╗
# ║ PARSER 1 — Routers FastAPI (AST)                                   ║
# ╚════════════════════════════════════════════════════════════════════╝

ROUTER_METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}
AUTH_DEPENDENCIES = {
    "get_current_user",
    "require_super_admin",
    "require_diretor",
    "require_coordenador",
}


def _ast_get_kwarg(call: ast.Call, name: str) -> Any:
    for kw in call.keywords:
        if kw.arg == name:
            return kw.value
    return None


def _ast_as_str(node: Any) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _detect_apirouter_assignments(tree: ast.Module) -> dict[str, dict]:
    """Retorna {variavel: {prefix, tags}} para cada APIRouter(...) no módulo."""
    routers: dict[str, dict] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not isinstance(node.value, ast.Call):
            continue
        call = node.value
        func_name = (
            call.func.id if isinstance(call.func, ast.Name)
            else call.func.attr if isinstance(call.func, ast.Attribute)
            else None
        )
        if func_name != "APIRouter":
            continue
        prefix = _ast_as_str(_ast_get_kwarg(call, "prefix")) or ""
        tags_node = _ast_get_kwarg(call, "tags")
        tags: list[str] = []
        if isinstance(tags_node, (ast.List, ast.Tuple)):
            for elt in tags_node.elts:
                t = _ast_as_str(elt)
                if t:
                    tags.append(t)
        for target in node.targets:
            if isinstance(target, ast.Name):
                routers[target.id] = {"prefix": prefix, "tags": tags}
    return routers


def _detect_route_decorator(dec: ast.expr) -> tuple[str | None, str | None, str | None]:
    """Detecta @router.METHOD("/path"). Retorna (router_var, method, path)."""
    if not isinstance(dec, ast.Call):
        return None, None, None
    if not isinstance(dec.func, ast.Attribute):
        return None, None, None
    method = dec.func.attr.lower()
    if method not in ROUTER_METHODS:
        return None, None, None
    if not isinstance(dec.func.value, ast.Name):
        return None, None, None
    router_var = dec.func.value.id
    if not dec.args:
        return None, None, None
    path = _ast_as_str(dec.args[0])
    if path is None:
        return None, None, None
    return router_var, method.upper(), path


def _detect_auth(func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Detecta se a função usa Depends(get_current_user) ou require_*."""
    src = ast.unparse(func.args) if hasattr(ast, "unparse") else ""
    return any(dep in src for dep in AUTH_DEPENDENCIES)


def _humanize_handler_name(name: str) -> str:
    parts = name.replace("_", " ").strip()
    return parts[:1].upper() + parts[1:] if parts else name


def _first_docstring_line(func: ast.FunctionDef | ast.AsyncFunctionDef) -> str | None:
    doc = ast.get_docstring(func)
    if not doc:
        return None
    return doc.strip().split("\n", 1)[0][:120]


def parse_routers(routers_dir: Path) -> list[dict]:
    """Lê app/routers/**/*.py via AST. Retorna lista de endpoints."""
    routes: list[dict] = []
    if not routers_dir.exists():
        return routes

    for py_file in sorted(routers_dir.rglob("*.py")):
        if py_file.name == "__init__.py":
            continue
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
        except SyntaxError:
            print(f"[snapshot] warning: sintaxe inválida em {py_file}", file=sys.stderr)
            continue

        routers_in_file = _detect_apirouter_assignments(tree)
        if not routers_in_file:
            continue

        for func in ast.walk(tree):
            if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for dec in func.decorator_list:
                router_var, method, path = _detect_route_decorator(dec)
                if not (router_var and method and path):
                    continue
                router_info = routers_in_file.get(router_var)
                if router_info is None:
                    continue
                full_path = (router_info["prefix"] or "") + path
                desc = _first_docstring_line(func) or _humanize_handler_name(func.name)
                routes.append({
                    "method": method,
                    "path": full_path,
                    "handler": func.name,
                    "desc": desc,
                    "auth": _detect_auth(func),
                    "router_file": str(py_file.relative_to(routers_dir.parent.parent)),
                    "router_stem": py_file.stem,
                    "tags": router_info["tags"],
                })

    routes.sort(key=lambda r: (r["router_stem"], r["path"], r["method"]))
    return routes


# ╔════════════════════════════════════════════════════════════════════╗
# ║ PARSER 2 — Migrations SQL (regex cumulativo)                       ║
# ╚════════════════════════════════════════════════════════════════════╝

SQL_CREATE_TABLE = re.compile(
    r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([a-zA-Z_][a-zA-Z0-9_]*)\s*\(([^;]+?)\)\s*;",
    re.IGNORECASE | re.DOTALL,
)
SQL_ALTER_ADD_COL = re.compile(
    r"ALTER\s+TABLE\s+([a-zA-Z_][a-zA-Z0-9_]*)\s+ADD\s+COLUMN\s+(?:IF\s+NOT\s+EXISTS\s+)?([^;]+?);",
    re.IGNORECASE,
)
SQL_ALTER_DROP_COL = re.compile(
    r"ALTER\s+TABLE\s+([a-zA-Z_][a-zA-Z0-9_]*)\s+DROP\s+COLUMN\s+(?:IF\s+EXISTS\s+)?([a-zA-Z_][a-zA-Z0-9_]*)",
    re.IGNORECASE,
)
SQL_DROP_TABLE = re.compile(
    r"DROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?([a-zA-Z_][a-zA-Z0-9_]*)",
    re.IGNORECASE,
)
SQL_CREATE_INDEX = re.compile(
    r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?([a-zA-Z_][a-zA-Z0-9_]*)\s+ON\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(([^)]+)\)",
    re.IGNORECASE,
)
SQL_REFERENCES = re.compile(
    r"REFERENCES\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\)",
    re.IGNORECASE,
)
SQL_FIRST_COMMENT = re.compile(r"^\s*--\s*(.+?)$", re.MULTILINE)


def _parse_column_def(text: str) -> dict | None:
    """Parse '<nome> <tipo> [constraints] [REFERENCES ...]'. Retorna dict ou None."""
    text = text.strip().rstrip(",").strip()
    if not text:
        return None
    # Skip table-level constraints
    if re.match(r"^(PRIMARY KEY|FOREIGN KEY|UNIQUE|CHECK|CONSTRAINT)\b", text, re.IGNORECASE):
        return None
    parts = text.split(None, 1)
    if len(parts) < 2:
        return None
    name = parts[0].strip('"`')
    rest = parts[1]
    # Extract type (first word, can include parens)
    type_match = re.match(r"^([a-zA-Z_][a-zA-Z0-9_]*(?:\([^)]+\))?(?:\s*\[\])?)", rest)
    col_type = type_match.group(1) if type_match else rest.split()[0]
    not_null = bool(re.search(r"\bNOT\s+NULL\b", rest, re.IGNORECASE))
    is_pk = bool(re.search(r"\bPRIMARY\s+KEY\b", rest, re.IGNORECASE))
    is_unique = bool(re.search(r"\bUNIQUE\b", rest, re.IGNORECASE))
    default_match = re.search(r"\bDEFAULT\s+([^,;]+?)(?:\s+(?:NOT\s+NULL|UNIQUE|REFERENCES|PRIMARY|CHECK)|\s*$)",
                              rest, re.IGNORECASE)
    default = default_match.group(1).strip() if default_match else None
    ref_match = SQL_REFERENCES.search(rest)
    fk_table = ref_match.group(1) if ref_match else None
    fk_column = ref_match.group(2) if ref_match else None
    return {
        "name": name,
        "type": col_type,
        "not_null": not_null,
        "is_pk": is_pk,
        "is_unique": is_unique,
        "default": default,
        "fk_table": fk_table,
        "fk_column": fk_column,
    }


def _split_table_body(body: str) -> list[str]:
    """Split table body by top-level commas (ignorando commas dentro de parens)."""
    parts = []
    depth = 0
    buf = []
    for ch in body:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    if buf:
        parts.append("".join(buf))
    return parts


_DECORATIVE_RE = re.compile(r"^[=\-*#~_\s]+$")
_MIGRATION_PREFIX_RE = re.compile(r"^migration\s+\d+[:\s\-]+", re.IGNORECASE)


def _migration_summary(content: str) -> str:
    """Pega 1ª linha de comentário '-- foo' real (pula decoração e 'Migration N:')."""
    for m in SQL_FIRST_COMMENT.finditer(content):
        line = m.group(1).strip()
        if not line:
            continue
        if _DECORATIVE_RE.match(line):
            continue
        # Strip "Migration NNN: " prefix
        line = _MIGRATION_PREFIX_RE.sub("", line)
        if line.lower().startswith("noqa"):
            continue
        if line:
            return line[:80]
    # Infer from first significant statement
    if SQL_CREATE_TABLE.search(content):
        names = SQL_CREATE_TABLE.findall(content)
        return f"criar tabela(s) {', '.join(n[0] for n in names)}"[:80]
    if SQL_ALTER_ADD_COL.search(content):
        return "alter table(s) — add column(s)"
    if SQL_DROP_TABLE.search(content):
        return "drop table(s)"
    return "—"


def parse_migrations(migrations_dir: Path) -> dict:
    """Reconstrói estado cumulativo das tabelas + history das migrations."""
    tables: dict[str, dict] = OrderedDict()
    history: list[dict] = []

    if not migrations_dir.exists():
        return {"tables": tables, "history": history}

    for sql_file in sorted(migrations_dir.glob("*.sql")):
        content = sql_file.read_text(encoding="utf-8")
        counts = {
            "create_table": len(SQL_CREATE_TABLE.findall(content)),
            "alter_table": len(SQL_ALTER_ADD_COL.findall(content)) + len(SQL_ALTER_DROP_COL.findall(content)),
            "create_index": len(SQL_CREATE_INDEX.findall(content)),
            "drop": len(SQL_DROP_TABLE.findall(content))
                    + len(re.findall(r"\bDROP\s+COLUMN\b", content, re.IGNORECASE)),
        }

        history.append({
            "file": sql_file.name,
            "summary": _migration_summary(content),
            "counts": counts,
            "order": _extract_order(sql_file.name),
        })

        # Apply CREATE TABLE
        for match in SQL_CREATE_TABLE.finditer(content):
            table_name = match.group(1)
            body = match.group(2)
            cols = []
            for part in _split_table_body(body):
                col = _parse_column_def(part)
                if col:
                    cols.append(col)
            tables[table_name] = {
                "columns": cols,
                "indexes": [],
                "first_seen": sql_file.name,
                "altered_in": [],
            }

        # Apply ALTER ADD COLUMN
        for match in SQL_ALTER_ADD_COL.finditer(content):
            table_name = match.group(1)
            col_text = match.group(2)
            col = _parse_column_def(col_text)
            if col and table_name in tables:
                # Replace if already exists, else append
                existing_idx = next((i for i, c in enumerate(tables[table_name]["columns"])
                                     if c["name"] == col["name"]), -1)
                if existing_idx >= 0:
                    tables[table_name]["columns"][existing_idx] = col
                else:
                    tables[table_name]["columns"].append(col)
                tables[table_name]["altered_in"].append(sql_file.name)

        # Apply ALTER DROP COLUMN
        for match in SQL_ALTER_DROP_COL.finditer(content):
            table_name = match.group(1)
            col_name = match.group(2)
            if table_name in tables:
                tables[table_name]["columns"] = [
                    c for c in tables[table_name]["columns"] if c["name"] != col_name
                ]
                tables[table_name]["altered_in"].append(sql_file.name)

        # Apply DROP TABLE
        for match in SQL_DROP_TABLE.finditer(content):
            tables.pop(match.group(1), None)

        # Apply CREATE INDEX
        for match in SQL_CREATE_INDEX.finditer(content):
            idx_name = match.group(1)
            table_name = match.group(2)
            cols = match.group(3).strip()
            if table_name in tables:
                tables[table_name]["indexes"].append({
                    "name": idx_name,
                    "cols": cols,
                    "file": sql_file.name,
                })

    return {"tables": tables, "history": history}


def _extract_order(filename: str) -> int:
    m = re.match(r"^(\d+)", filename)
    return int(m.group(1)) if m else 9999


# ╔════════════════════════════════════════════════════════════════════╗
# ║ GERADORES de MD                                                    ║
# ╚════════════════════════════════════════════════════════════════════╝

def _now_iso() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M%z")


def _auth_marker(auth: bool) -> str:
    return "✅" if auth else "❌"


def gen_rotas_md(routes: list[dict], project_name: str) -> str:
    """Gera ROTAS.md."""
    out = [
        "# ROTAS.md",
        "<!-- gerado automaticamente por /snapshot — não editar -->",
        f"<!-- last_update: {_now_iso()} -->",
        "",
        f"Endpoints HTTP expostos pelo backend FastAPI do {project_name}.",
        "",
    ]

    # Group by router stem
    by_router: OrderedDict[str, list[dict]] = OrderedDict()
    for r in routes:
        by_router.setdefault(r["router_stem"], []).append(r)

    for stem, items in by_router.items():
        tags = items[0]["tags"][0] if items[0]["tags"] else stem
        out.append(f"## {tags} (`{items[0]['router_file']}`)")
        out.append("")
        out.append("| Método | Rota | O que faz | Auth |")
        out.append("|--------|------|-----------|------|")
        for r in items:
            method = r["method"]
            path = r["path"]
            desc = r["desc"].replace("|", "\\|")
            auth = _auth_marker(r["auth"])
            out.append(f"| {method} | `{path}` | {desc} | {auth} |")
        out.append("")

    out.append("---")
    out.append("")
    total = len(routes)
    auth_count = sum(1 for r in routes if r["auth"])
    pct = (auth_count * 100 // total) if total else 0
    out.append(f"**Totais:** {total} endpoints em {len(by_router)} routers · {pct}% exigem auth.")
    out.append("")
    return "\n".join(out)


def gen_entidades_md(parsed: dict, project_name: str) -> str:
    """Gera ENTIDADES.md."""
    tables = parsed["tables"]
    out = [
        "# ENTIDADES.md",
        "<!-- gerado automaticamente por /snapshot — não editar -->",
        f"<!-- last_update: {_now_iso()} -->",
        "",
        f"Modelo de dados do {project_name}. Tabelas no Postgres (via Supabase).",
        "",
    ]

    for table_name, info in tables.items():
        out.append(f"## {table_name}")
        out.append("")
        first = info["first_seen"]
        altered = info["altered_in"]
        provenance = f"Origem: `{first}`"
        if altered:
            unique_alter = list(OrderedDict.fromkeys(altered))
            provenance += f" (alterada em: {', '.join(unique_alter)})"
        out.append(f"> {provenance}")
        out.append("")
        out.append("| Campo | Tipo | Constraints | Default | FK |")
        out.append("|-------|------|-------------|---------|-----|")
        for col in info["columns"]:
            constraints = []
            if col["is_pk"]:
                constraints.append("PK")
            if col["is_unique"]:
                constraints.append("UNIQUE")
            if col["not_null"]:
                constraints.append("NOT NULL")
            constraints_str = ", ".join(constraints) if constraints else "—"
            default_str = f"`{col['default']}`" if col["default"] else "—"
            fk_str = f"`{col['fk_table']}.{col['fk_column']}`" if col["fk_table"] else "—"
            out.append(f"| `{col['name']}` | `{col['type']}` | {constraints_str} | {default_str} | {fk_str} |")
        out.append("")
        if info["indexes"]:
            out.append("**Indexes:**")
            for idx in info["indexes"]:
                out.append(f"- `{idx['name']}` em `({idx['cols']})` (de `{idx['file']}`)")
            out.append("")

    out.append("---")
    out.append("")
    out.append(f"**Resumo:** {len(tables)} tabelas vivas.")
    out.append("")
    return "\n".join(out)


def gen_schema_md(parsed: dict, project_name: str) -> str:
    """Gera SCHEMA.md (Mermaid ER)."""
    tables = parsed["tables"]
    out = [
        "# SCHEMA.md",
        "<!-- gerado automaticamente por /snapshot — não editar -->",
        f"<!-- last_update: {_now_iso()} -->",
        "",
        f"Diagrama relacional do {project_name}. Renderiza nativo no GitHub.",
        "",
        "## Diagrama ER (Mermaid)",
        "",
        "```mermaid",
        "erDiagram",
    ]

    # FK edges
    edges: set[tuple[str, str, str]] = set()
    for table_name, info in tables.items():
        for col in info["columns"]:
            if col["fk_table"] and col["fk_table"] in tables:
                edges.add((col["fk_table"], table_name, col["name"]))

    for parent, child, col_name in sorted(edges):
        out.append(f'    {parent} ||--o{{ {child} : "{col_name}"')

    # Table boxes (compacto — só PK e algumas colunas)
    out.append("")
    for table_name, info in tables.items():
        out.append(f"    {table_name} {{")
        for col in info["columns"][:8]:  # max 8 cols pra não estourar diagram
            type_short = col["type"].split("(")[0]
            marker = "PK" if col["is_pk"] else "FK" if col["fk_table"] else ""
            out.append(f"        {type_short} {col['name']} {marker}".rstrip())
        if len(info["columns"]) > 8:
            out.append(f"        _ {len(info['columns']) - 8}_mais_colunas")
        out.append("    }")
    out.append("```")
    out.append("")

    # Indexes section
    out.append("## Indexes principais")
    out.append("")
    out.append("| Tabela | Index | Colunas | Origem |")
    out.append("|--------|-------|---------|--------|")
    for table_name, info in tables.items():
        for idx in info["indexes"]:
            out.append(f"| `{table_name}` | `{idx['name']}` | `{idx['cols']}` | `{idx['file']}` |")
    out.append("")
    out.append("---")
    out.append(f"**Resumo:** {len(tables)} tabelas · {len(edges)} relacionamentos FK detectados.")
    out.append("")
    return "\n".join(out)


def gen_migrations_md(parsed: dict, project_name: str) -> str:
    """Gera MIGRATIONS.md."""
    history = parsed["history"]
    out = [
        "# MIGRATIONS.md",
        "<!-- gerado automaticamente por /snapshot — não editar -->",
        f"<!-- last_update: {_now_iso()} -->",
        "",
        f"Ordem cronológica das migrations do Postgres do {project_name}.",
        "",
        "| # | Arquivo | Resumo | C | A | I | D |",
        "|---|---------|--------|---|---|---|---|",
    ]

    for h in history:
        c = h["counts"]
        out.append(
            f"| {h['order']} | `{h['file']}` | {h['summary']} | "
            f"{c['create_table']} | {c['alter_table']} | {c['create_index']} | {c['drop']} |"
        )

    out.append("")
    out.append("**Legenda:** C = CREATE TABLE · A = ALTER TABLE · I = CREATE INDEX · D = DROP.")
    out.append(f"**Total:** {len(history)} migrations.")
    out.append("")
    return "\n".join(out)


def gen_integracoes_md(project_json: dict, backend_root: Path, project_name: str) -> str:
    """Gera INTEGRACOES.md. Cruza project.json.integrations com grep no código."""
    integrations = project_json.get("project", {}).get("integrations", [])
    services = project_json.get("services", [])

    # Build map env_key → list of (key, purpose) for all backend env vars
    all_env_keys: dict[str, str] = {}
    for svc in services:
        for kind in ("runtime_required", "runtime_optional", "build_time"):
            for k in svc.get("env_keys", {}).get(kind, []):
                if isinstance(k, dict):
                    all_env_keys[k["name"]] = k.get("purpose", "")

    out = [
        "# INTEGRACOES.md",
        "<!-- gerado automaticamente por /snapshot — não editar -->",
        f"<!-- last_update: {_now_iso()} -->",
        "",
        f"Serviços externos usados pelo {project_name}. Secrets configurados no Coolify (não no git).",
        "",
    ]

    for integration in integrations:
        name = integration.get("name", "?")
        primary_key = integration.get("configured_via", "")
        note = integration.get("note", "")

        # Find related env vars (heurística: começam com prefix do nome ou contêm o nome)
        prefix_candidates = [
            primary_key.rsplit("_", 1)[0] if "_" in primary_key else primary_key,
            name.upper().replace(" ", "_"),
        ]
        related = []
        for var_name in all_env_keys:
            if var_name == primary_key:
                continue
            if any(var_name.startswith(p) for p in prefix_candidates if p):
                related.append(var_name)

        # grep no backend pra achar usos
        usages = _grep_first(backend_root, primary_key) if primary_key else []
        if not usages and name:
            usages = _grep_first(backend_root, name)

        out.append(f"## {name}")
        out.append(f"**Pra que serve:** {note}")
        if usages:
            usage_str = ", ".join(f"`{u}`" for u in usages[:3])
            out.append(f"**Onde aparece no código:** {usage_str}")
        if primary_key:
            out.append(f"**Secret/env primária:** `{primary_key}`")
        if related:
            related_sorted = sorted(set(related))
            out.append(f"**Variáveis relacionadas:** {', '.join(f'`{r}`' for r in related_sorted)}")
        out.append("")

    out.append("---")
    out.append(f"**Resumo:** {len(integrations)} integrações externas.")
    out.append("")
    return "\n".join(out)


# ╔════════════════════════════════════════════════════════════════════╗
# ║ HELPERS                                                            ║
# ╚════════════════════════════════════════════════════════════════════╝

def _grep_first(root: Path, pattern: str, max_results: int = 5) -> list[str]:
    """grep recursivo. Retorna paths relativos onde pattern aparece."""
    if not pattern or not root.exists():
        return []
    try:
        result = subprocess.run(
            ["grep", "-rln", "--include=*.py", pattern, str(root)],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode > 1:  # 0=found, 1=not found, 2+=error
            return []
        paths = [p for p in result.stdout.strip().splitlines() if p]
        relative = []
        for p in paths[:max_results]:
            try:
                relative.append(str(Path(p).relative_to(root.parent)))
            except ValueError:
                relative.append(p)
        return relative
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []


def strip_timestamp(text: str) -> str:
    """Remove o comment de last_update pra comparação idempotente."""
    return TIMESTAMP_COMMENT.sub("", text)


def has_changed(existing: str, generated: str) -> bool:
    return strip_timestamp(existing).strip() != strip_timestamp(generated).strip()


def detect_gaps(routes: list[dict], parsed: dict, snapshots_dir: Path) -> list[str]:
    """Detecta rotas/estados novos que não estão em FLUXOGRAMAS.md."""
    fluxogramas_path = snapshots_dir / "FLUXOGRAMAS.md"
    if not fluxogramas_path.exists():
        return ["FLUXOGRAMAS.md não existe — considere criar manualmente."]
    fluxos = fluxogramas_path.read_text(encoding="utf-8").lower()
    alerts: list[str] = []
    # Detect new state enum values (heurística: status_ata, status, etc.)
    for table_name, info in parsed["tables"].items():
        for col in info["columns"]:
            if "status" in col["name"].lower() and col["default"]:
                default_val = col["default"].strip("'\"").lower()
                if default_val and default_val not in fluxos and len(default_val) > 3:
                    alerts.append(
                        f"Estado novo `{default_val}` em `{table_name}.{col['name']}` "
                        f"sem fluxograma correspondente."
                    )
    return alerts[:10]  # cap em 10 alerts


# ╔════════════════════════════════════════════════════════════════════╗
# ║ MAIN                                                                ║
# ╚════════════════════════════════════════════════════════════════════╝

def _load_project_json(repo_root: Path) -> dict:
    path = repo_root / "docs" / "spec" / "deploy" / "project.json"
    if not path.exists():
        print(f"[snapshot] erro: {path} não existe. Rode `/deploy setup` primeiro.",
              file=sys.stderr)
        sys.exit(2)
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_paths(repo_root: Path, project_json: dict) -> dict:
    """Deriva paths críticos do project.json."""
    # Backend e migrations vêm de services[].build.base_directory e diff_routing
    backend_base = None
    supabase_base = None
    frontend_base = None
    for svc in project_json.get("services", []):
        bd = (svc.get("build", {}).get("base_directory") or "").strip("/")
        svc_type = svc.get("type", "")
        if svc_type == "fastapi" and bd:
            backend_base = repo_root / bd
        elif svc_type == "supabase":
            # Inferir do trigger_paths se base_directory for null
            triggers = svc.get("diff_routing", {}).get("trigger_paths", [])
            for t in triggers:
                stripped = t.rstrip("/*")
                if "supabase" in stripped:
                    supabase_base = repo_root / stripped
                    break
        elif svc_type == "nextjs" and bd:
            frontend_base = repo_root / bd

    migrations_path = (project_json.get("migrations", {}).get("dir") or "").strip("/")
    migrations_dir = repo_root / migrations_path if migrations_path else None

    return {
        "backend_app": (backend_base / "app") if backend_base else None,
        "routers": (backend_base / "app" / "routers") if backend_base else None,
        "frontend_src": (frontend_base / "src") if frontend_base else None,
        "supabase": supabase_base,
        "migrations": migrations_dir,
        "snapshots": repo_root / "docs" / "spec" / "snapshots",
    }


def _write_if_changed(path: Path, content: str, dry_run: bool, force: bool) -> bool:
    """Escreve `content` em `path` se diferente. Retorna True se mudou."""
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    changed = has_changed(existing, content) or force
    if changed and not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return changed


def cmd_default(args, paths: dict, project_json: dict) -> int:
    """Modo padrão: regenera 5 MDs auto-gerados se mudaram."""
    project_name = project_json.get("project", {}).get("name", "Projeto")
    repo_root = Path(args.root).resolve()

    # Parse
    routes = parse_routers(paths["routers"]) if paths["routers"] else []
    parsed = parse_migrations(paths["migrations"]) if paths["migrations"] else {"tables": {}, "history": []}

    # Generate
    generated = {
        "ROTAS": gen_rotas_md(routes, project_name),
        "ENTIDADES": gen_entidades_md(parsed, project_name),
        "SCHEMA": gen_schema_md(parsed, project_name),
        "MIGRATIONS": gen_migrations_md(parsed, project_name),
        "INTEGRACOES": gen_integracoes_md(project_json, paths["backend_app"] or repo_root, project_name),
    }

    only_filter = args.only.upper() if args.only else None
    if only_filter and only_filter not in TARGET_FILES:
        print(f"[snapshot] erro: --only deve ser um de {TARGET_FILES}", file=sys.stderr)
        return 2

    # Write
    changed_files = []
    for name in TARGET_FILES:
        if only_filter and name != only_filter:
            continue
        path = paths["snapshots"] / f"{name}.md"
        if _write_if_changed(path, generated[name], dry_run=args.check, force=args.force):
            changed_files.append(name)

    # Alerts
    alerts = detect_gaps(routes, parsed, paths["snapshots"])

    # Report
    if args.check:
        print("═══ /snapshot --check (dry-run) ═══")
    if changed_files:
        action = "mudariam" if args.check else "atualizados"
        print(f"Arquivos {action}:")
        for f in changed_files:
            print(f"  {f}.md")
    else:
        print("nenhuma mudança relevante desde último snapshot")
    if alerts:
        print("\nAlertas (FLUXOGRAMAS.md pode estar desatualizado):")
        for a in alerts:
            print(f"  ⚠ {a}")

    # Optional: commit if not dry-run, not --no-commit, and there are changes
    if not args.check and not args.no_commit and changed_files:
        _git_commit_snapshot(repo_root, changed_files)

    return 0


def _git_commit_snapshot(repo_root: Path, changed_files: list[str]) -> None:
    """Commit separado: chore(spec): atualizar snapshot pós deploy <sha7>."""
    try:
        sha = subprocess.check_output(
            ["git", "-C", str(repo_root), "rev-parse", "--short", "HEAD"],
            text=True,
        ).strip()
    except subprocess.CalledProcessError:
        sha = "unknown"

    files_str = "\n".join(f"- docs/spec/snapshots/{f}.md" for f in changed_files)
    msg = (
        f"chore(spec): atualizar snapshot pós deploy {sha}\n\n"
        f"Arquivos regenerados:\n{files_str}\n\n"
        f"Gerado automaticamente por /snapshot. Não dispara novo /deploy ship "
        f"(scope_map em project.json mapeia docs/spec/snapshots/** → spec)."
    )

    try:
        subprocess.check_call(
            ["git", "-C", str(repo_root), "add"]
            + [f"docs/spec/snapshots/{f}.md" for f in changed_files]
        )
        subprocess.check_call(
            ["git", "-C", str(repo_root), "commit", "-m", msg]
        )
        print(f"\ncommit criado: chore(spec): atualizar snapshot pós deploy {sha}")
    except subprocess.CalledProcessError as e:
        print(f"[snapshot] warning: commit falhou ({e}). Mudanças ficam no working tree.",
              file=sys.stderr)


def cmd_diff(args, paths: dict, project_json: dict) -> int:
    """Modo --diff <base>..HEAD: imprime markdown da mudança esperada."""
    project_name = project_json.get("project", {}).get("name", "Projeto")
    repo_root = Path(args.root).resolve()

    # Capture current state (working tree)
    routes_after = parse_routers(paths["routers"]) if paths["routers"] else []
    parsed_after = parse_migrations(paths["migrations"]) if paths["migrations"] else {"tables": {}, "history": []}

    # Capture base state via git worktree-ish trick: stash, checkout base, parse, restore
    # Simplified: parse files as they are in base ref using `git show`
    base_ref = args.diff.split("..")[0]

    routes_before = _parse_routers_from_ref(repo_root, base_ref, paths["routers"])
    parsed_before = _parse_migrations_from_ref(repo_root, base_ref, paths["migrations"])

    print("## 📊 Mudanças no snapshot\n")

    # Rotas diff
    paths_after = {(r["method"], r["path"]) for r in routes_after}
    paths_before = {(r["method"], r["path"]) for r in routes_before}
    new_routes = paths_after - paths_before
    removed_routes = paths_before - paths_after

    if new_routes or removed_routes:
        print("### Rotas")
        for method, path in sorted(new_routes):
            print(f"- ✨ Nova: `{method} {path}`")
        for method, path in sorted(removed_routes):
            print(f"- ❌ Removida: `{method} {path}`")
        print()

    # Entidades diff
    tables_after = set(parsed_after["tables"].keys())
    tables_before = set(parsed_before["tables"].keys())
    new_tables = tables_after - tables_before
    removed_tables = tables_before - tables_after

    if new_tables or removed_tables:
        print("### Entidades")
        for t in sorted(new_tables):
            print(f"- 🆕 Tabela nova: `{t}`")
        for t in sorted(removed_tables):
            print(f"- ❌ Tabela removida: `{t}`")
        print()

    # Migrations diff
    files_after = {h["file"] for h in parsed_after["history"]}
    files_before = {h["file"] for h in parsed_before["history"]}
    new_migrations = files_after - files_before
    if new_migrations:
        print("### Migrations")
        for f in sorted(new_migrations):
            summary = next((h["summary"] for h in parsed_after["history"] if h["file"] == f), "")
            print(f"- ➕ `{f}`: {summary}")
        print()

    if not (new_routes or removed_routes or new_tables or removed_tables or new_migrations):
        print("_(sem mudanças relevantes ao snapshot)_")

    return 0


def _parse_routers_from_ref(repo_root: Path, ref: str, routers_dir: Path | None) -> list[dict]:
    """Parsea routers como estavam no ref (snapshot do git)."""
    if not routers_dir:
        return []
    rel = str(routers_dir.relative_to(repo_root))
    try:
        files = subprocess.check_output(
            ["git", "-C", str(repo_root), "ls-tree", "-r", "--name-only", ref, rel],
            text=True,
        ).strip().splitlines()
    except subprocess.CalledProcessError:
        return []

    routes: list[dict] = []
    for f in files:
        if not f.endswith(".py") or f.endswith("__init__.py"):
            continue
        try:
            content = subprocess.check_output(
                ["git", "-C", str(repo_root), "show", f"{ref}:{f}"], text=True,
            )
            tree = ast.parse(content)
        except (subprocess.CalledProcessError, SyntaxError):
            continue

        routers_in_file = _detect_apirouter_assignments(tree)
        if not routers_in_file:
            continue
        for func in ast.walk(tree):
            if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for dec in func.decorator_list:
                router_var, method, path = _detect_route_decorator(dec)
                if not (router_var and method and path):
                    continue
                router_info = routers_in_file.get(router_var)
                if router_info is None:
                    continue
                full_path = (router_info["prefix"] or "") + path
                routes.append({
                    "method": method,
                    "path": full_path,
                })
    return routes


def _parse_migrations_from_ref(repo_root: Path, ref: str, migrations_dir: Path | None) -> dict:
    """Parsea migrations como estavam no ref."""
    if not migrations_dir:
        return {"tables": {}, "history": []}
    rel = str(migrations_dir.relative_to(repo_root))
    try:
        files = subprocess.check_output(
            ["git", "-C", str(repo_root), "ls-tree", "-r", "--name-only", ref, rel],
            text=True,
        ).strip().splitlines()
    except subprocess.CalledProcessError:
        return {"tables": {}, "history": []}

    tables: dict[str, dict] = OrderedDict()
    history: list[dict] = []
    for f in sorted(files):
        if not f.endswith(".sql"):
            continue
        try:
            content = subprocess.check_output(
                ["git", "-C", str(repo_root), "show", f"{ref}:{f}"], text=True,
            )
        except subprocess.CalledProcessError:
            continue

        # Apply same logic as parse_migrations (minimal)
        history.append({"file": Path(f).name, "summary": "", "counts": {}, "order": _extract_order(Path(f).name)})
        for match in SQL_CREATE_TABLE.finditer(content):
            tables[match.group(1)] = {"first_seen": Path(f).name}
        for match in SQL_DROP_TABLE.finditer(content):
            tables.pop(match.group(1), None)
    return {"tables": tables, "history": history}


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="snapshot",
        description="Regenera docs/spec/snapshots/*.md a partir do código fonte.",
    )
    parser.add_argument("--root", default=".", help="Raiz do repo (default: cwd)")
    parser.add_argument("--check", action="store_true", help="Dry-run: mostra o que mudaria sem escrever")
    parser.add_argument("--force", action="store_true", help="Regenera mesmo se nada mudou")
    parser.add_argument("--only", help="Regenera só 1 arquivo (ROTAS|ENTIDADES|SCHEMA|MIGRATIONS|INTEGRACOES)")
    parser.add_argument("--diff", metavar="RANGE", help="Markdown da mudança entre <base>..HEAD")
    parser.add_argument("--no-commit", action="store_true",
                        help="Não cria commit automático (default: commita chore(spec): ...)")
    args = parser.parse_args()

    repo_root = Path(args.root).resolve()
    if not (repo_root / ".git").exists() and not (repo_root / "docs" / "spec").exists():
        print(f"[snapshot] erro: {repo_root} não parece ser raiz do repo Hospital", file=sys.stderr)
        return 2

    project_json = _load_project_json(repo_root)
    paths = _resolve_paths(repo_root, project_json)

    if args.diff:
        return cmd_diff(args, paths, project_json)
    return cmd_default(args, paths, project_json)


if __name__ == "__main__":
    sys.exit(main())
