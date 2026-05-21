"""Prepend de entrada em docs/spec/CHANGELOG.md ao final do /deploy ship.

Lê estado do último deploy de docs/spec/deploy/state.json e history.json,
captura autor via git config, e insere entrada no topo do CHANGELOG (após
o separador "---" do header). Idempotente: se a entrada já existe (mesma
combinação SHA+result), não duplica.
"""

import json
import os
import subprocess as sp
from datetime import datetime
from pathlib import Path


def main() -> int:
    repo = os.environ.get("REPO_ROOT")
    if not repo:
        try:
            repo = sp.run(
                ["git", "rev-parse", "--show-toplevel"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
        except Exception:
            print("Não foi possível descobrir REPO_ROOT. Pulando CHANGELOG.")
            return 1

    bp = Path(repo) / "docs" / "spec"
    changelog = bp / "CHANGELOG.md"
    state_path = bp / "deploy" / "state.json"
    history_path = bp / "deploy" / "history.json"

    if not state_path.exists() or not history_path.exists():
        print("state.json ou history.json ausente. Pulando.")
        return 0

    state = json.loads(state_path.read_text())
    history = json.loads(history_path.read_text())

    deploys = history.get("deploys") if isinstance(history, dict) else history
    if not deploys:
        print("Sem deploys em history.json. Pulando.")
        return 0
    last_history = deploys[0]

    sha = (last_history.get("sha") or "")[:7] or "unknown"
    subject = last_history.get("subject") or last_history.get("raw_subject") or "(sem subject)"
    result = last_history.get("result", "unknown")
    duration = last_history.get("duration_seconds", 0)
    services = ", ".join(last_history.get("services_touched", [])) or "—"

    result_emoji = {
        "healthy": "🟢",
        "failed": "🔴",
        "build-failed": "🔴",
        "rolled-back": "🟡",
        "rollback-manual": "🟡",
        "migration-failed": "🔴",
    }.get(result, "⚪")

    at_iso = last_history.get("at") or state.get("updated_at") or datetime.now().isoformat()
    try:
        at_human = datetime.fromisoformat(at_iso.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M")
    except Exception:
        at_human = at_iso[:16]

    author_name = (
        sp.run(["git", "config", "user.name"], capture_output=True, text=True).stdout.strip()
        or "desconhecido"
    )
    author_email = (
        sp.run(["git", "config", "user.email"], capture_output=True, text=True).stdout.strip()
        or "?"
    )

    chronicle_link = "—"
    for ch_path in sorted(
        bp.glob(f"chronicles/*-{sha}-*.md"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    ):
        chronicle_link = f"[chronicles/{ch_path.name}](chronicles/{ch_path.name})"
        break

    entry_lines = [
        f"## {at_human} — {subject}",
        f"- Autor: {author_name} <{author_email}>",
        f"- SHA: `{sha}`",
        f"- Serviços: {services}",
        f"- Resultado: {result_emoji} {result} ({duration}s)",
        f"- Detalhe: {chronicle_link}",
        "",
    ]
    entry = "\n".join(entry_lines)

    if not changelog.exists():
        changelog.parent.mkdir(parents=True, exist_ok=True)
        header = (
            "# Changelog Hospital Reuniões\n\n"
            "Cronologia de deploys em ordem reversa (mais recente no topo).\n"
            "Prepended pelo /deploy ship ao final do ciclo.\n\n"
            "---\n\n"
        )
        changelog.write_text(header + entry)
        print(f"CHANGELOG criado: {sha} — {subject[:60]}")
        return 0

    content = changelog.read_text()

    # Idempotência: se essa entrada exata (mesmo SHA+result+at) já existe no topo, pula
    if f"SHA: `{sha}`" in content and result_emoji in content and at_human in content:
        # Verifica se é nas primeiras ~20 linhas (topo)
        head_preview = "\n".join(content.split("\n")[:20])
        if f"SHA: `{sha}`" in head_preview:
            print(f"CHANGELOG já tem entrada {sha} no topo. Idempotente, pula.")
            return 0

    lines = content.split("\n")
    insert_at = None
    for i, ln in enumerate(lines):
        if ln.strip() == "---":
            insert_at = i + 1
            break

    if insert_at is None:
        new_content = content.rstrip() + "\n\n" + entry
    else:
        # Pula linhas em branco depois do "---"
        while insert_at < len(lines) and lines[insert_at].strip() == "":
            insert_at += 1
        lines.insert(insert_at, entry)
        new_content = "\n".join(lines)

    changelog.write_text(new_content)
    print(f"CHANGELOG atualizado: {sha} — {subject[:60]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
