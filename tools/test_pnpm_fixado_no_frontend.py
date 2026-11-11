"""O pnpm do frontend fixado num major só (issue #1312).

O PR semanal do Dependabot (#1300) chegou com `ERR_PNPM_LOCKFILE_CONFIG_MISMATCH`:
sem o campo `packageManager`, o Dependabot regenerou o lockfile com o pnpm 11,
que não lê mais o bloco `pnpm` do `package.json` e jogou fora a seção
`overrides`. O CI e o Dockerfile instalam com o pnpm 9 e travam na instalação.
Estes testes amarram o mesmo major nos quatro lugares e o lockfile em dia com
os overrides. Desde a issue #1599 o CI roda no Mac e pega o pnpm pelo corepack,
que lê o próprio `packageManager`.
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
    passos = ci["jobs"]["frontend-lint"]["steps"]
    # O corepack instala a versão exata do `packageManager`; nenhuma ação fixa outra.
    assert not [p for p in passos if "pnpm/action-setup" in p.get("uses", "")]
    corepack = [p for p in passos if "corepack enable pnpm" in p.get("run", "")]
    assert len(corepack) == 1
    instalar = [p for p in passos if p.get("run", "").startswith("pnpm install")]
    assert passos.index(corepack[0]) < passos.index(instalar[0])

    dockerfile = (FRONTEND / "Dockerfile").read_text(encoding="utf-8")
    preparos = re.findall(r"corepack prepare pnpm@(\d+)", dockerfile)
    assert preparos and set(preparos) == {major}


def test_lockfile_tem_os_mesmos_overrides_do_package_json():
    lock = yaml.safe_load((FRONTEND / "pnpm-lock.yaml").read_text(encoding="utf-8"))
    assert lock.get("overrides") == package_json()["pnpm"]["overrides"]


def test_a_guarda_roda_quando_o_pnpm_do_frontend_muda():
    """Os testes de `tools/` rodam no `ferramentas.yml`: o PR que mexe só no
    `package.json`, no Dockerfile ou no lockfile do frontend também precisa
    acordá-los, senão a guarda fica verde sobre nada."""
    manual = yaml.safe_load((RAIZ / ".github" / "workflows" / "ferramentas.yml").read_text(encoding="utf-8"))
    on = manual["on"] if "on" in manual else manual[True]
    for evento in ("push", "pull_request"):
        for arquivo in ("package.json", "Dockerfile", "pnpm-lock.yaml"):
            assert f"hospital-reunioes/frontend/{arquivo}" in on[evento]["paths"], (evento, arquivo)
