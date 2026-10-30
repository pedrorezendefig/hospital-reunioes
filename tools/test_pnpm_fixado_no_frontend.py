"""O pnpm do frontend fixado num major só (issue #1312).

O PR semanal do Dependabot (#1300) chegou com `ERR_PNPM_LOCKFILE_CONFIG_MISMATCH`:
sem o campo `packageManager`, o Dependabot regenerou o lockfile com o pnpm 11,
que não lê mais o bloco `pnpm` do `package.json` e jogou fora a seção
`overrides`. O CI e o Dockerfile instalam com o pnpm 9 e travam na instalação.
Estes testes amarram o mesmo major nos quatro lugares e o lockfile em dia com
os overrides.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parent.parent
FRONTEND = RAIZ / "hospital-reunioes" / "frontend"


def package_json() -> dict:
    return json.loads((FRONTEND / "package.json").read_text(encoding="utf-8"))


def major_do_package_manager() -> str:
    valor = package_json().get("packageManager", "")
    achado = re.fullmatch(r"pnpm@(\d+)\.\d+\.\d+", valor)
    assert achado, f"packageManager precisa ser pnpm@X.Y.Z, veio {valor!r}"
    return achado.group(1)


def test_package_manager_fixa_o_mesmo_pnpm_do_ci_e_do_dockerfile():
    major = major_do_package_manager()

    ci = yaml.safe_load((RAIZ / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
    setup = [p for p in ci["jobs"]["frontend-lint"]["steps"] if "pnpm/action-setup" in p.get("uses", "")]
    assert len(setup) == 1
    assert str(setup[0]["with"]["version"]) == major

    dockerfile = (FRONTEND / "Dockerfile").read_text(encoding="utf-8")
    preparos = re.findall(r"corepack prepare pnpm@(\d+)", dockerfile)
    assert preparos and set(preparos) == {major}


def test_lockfile_tem_os_mesmos_overrides_do_package_json():
    lock = yaml.safe_load((FRONTEND / "pnpm-lock.yaml").read_text(encoding="utf-8"))
    assert lock.get("overrides") == package_json()["pnpm"]["overrides"]
