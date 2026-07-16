#!/usr/bin/env python3
"""Lint das ADRs (docs/adr/*.md).

Garante que o status de cada decisão seja verdadeiro e navegável por um agente:
- toda ADR tem frontmatter com `status:`;
- o estado canônico (primeira palavra do status) pertence ao conjunto fechado;
- ponteiros de supersessão/emenda são bidirecionais (se A aponta B, B aponta A);
- referências apontam para ADRs que existem.

Sem dependências externas. Uso: python3 tools/lint_adr.py [--dir docs/adr]
Sai com código 1 se houver qualquer violação.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

STATES = {"proposed", "accepted", "superseded", "deprecated", "rejected"}
# ponteiro -> ponteiro inverso que a ADR alvo precisa declarar de volta
INVERSE = {
    "supersedes": "superseded_by",
    "superseded_by": "supersedes",
    "amends": "amended_by",
    "amended_by": "amends",
}


def parse(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    meta: dict[str, str] = {}
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if m:
        for line in m.group(1).splitlines():
            km = re.match(r"\s*([\w-]+):\s*(.+?)\s*$", line)
            if km:
                meta[km.group(1).lower()] = km.group(2).strip()
    nm = re.match(r"(\d+)", path.name)
    return {"num": nm.group(1) if nm else None, "meta": meta, "path": path}


def num4(v: str) -> str:
    """Normaliza '18' / '0018' para '0018' (compara pelo número da ADR)."""
    return v.strip().zfill(4)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="docs/adr")
    args = ap.parse_args()

    adr_dir = Path(args.dir)
    adrs = {parse(f)["num"]: parse(f) for f in sorted(adr_dir.glob("*.md"))}
    errors: list[str] = []

    for num, adr in adrs.items():
        meta, name = adr["meta"], adr["path"].name

        raw = meta.get("status")
        if not raw:
            errors.append(f"{name}: falta frontmatter com `status:`.")
            continue
        state = raw.split()[0].rstrip(",").lower()
        if state not in STATES:
            errors.append(
                f"{name}: status '{state}' fora do conjunto {sorted(STATES)}."
            )

        for field, inverse in INVERSE.items():
            if field not in meta:
                continue
            target = num4(meta[field])
            if target not in adrs:
                errors.append(f"{name}: {field} aponta para ADR {target}, que não existe.")
                continue
            back = adrs[target]["meta"].get(inverse)
            if back is None or num4(back) != num4(num):
                errors.append(
                    f"{name}: {field}: {target} sem o par `{inverse}: {num}` na ADR {target}."
                )

    if errors:
        print("Lint de ADR falhou:\n" + "\n".join(f"  - {e}" for e in errors), file=sys.stderr)
        return 1
    print(f"Lint de ADR OK ({len(adrs)} ADRs).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
