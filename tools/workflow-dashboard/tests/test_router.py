"""Router de hash do Hospital OS (issue #944, ADR 0062, decisão 8).

Aba, item aberto e filtros vivem no hash (`#issues/930`, `#prs/930`,
`#producao/v0.161.0`, `#issues?resp=...&fase=...`); abrir o painel com o hash
restaura o estado. Chips de issue, PR e versão navegam dentro do painel; o
GitHub fica no `↗` de cada card.

O router.js e o app.js rodam de verdade no Node: o app.js com um DOM mínimo de
mentira, um `location`/`history` que guardam o hash e os ouvintes de `window`
registrados para o teste disparar o `hashchange`, o ⟳ e a recoleta de 60 s.
"""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

DASH = Path(__file__).resolve().parents[1]
STATIC = DASH / "static"
APP_JS = (STATIC / "app.js").read_text(encoding="utf-8")
ROUTER = STATIC / "router.js"

com_node = pytest.mark.skipif(not shutil.which("node"), reason="node ausente")


def _node(tmp_path, prog):
    arq = tmp_path / "harness.mjs"
    arq.write_text(prog, encoding="utf-8")
    out = subprocess.run(
        ["node", str(arq)], capture_output=True, text=True, check=False, env={**os.environ, "TZ": "UTC"}
    )
    assert out.returncode == 0, out.stderr
    linha = [x for x in out.stdout.splitlines() if x.startswith("@@")][-1]
    return json.loads(linha[2:])


def _router(tmp_path, expr):
    """Avalia `expr` com as funções do router.js importadas."""
    prog = f"import * as R from '{ROUTER.as_uri()}';\nconsole.log('@@' + JSON.stringify({expr}));\n"
    return _node(tmp_path, prog)


# ---------- o router lê e monta o hash ----------


@com_node
def test_hash_vira_aba_item_e_filtros(tmp_path):
    rotas = _router(
        tmp_path,
        "['#issues/930?resp=lucassampaioc1&fase=pr_aberto', '#prs/930', '#producao/v0.161.0', '#mapa', '']"
        ".map(R.lerHash)",
    )
    assert rotas == [
        {"aba": "issues", "item": "930", "filtros": {"resp": "lucassampaioc1", "fase": "pr_aberto"}},
        {"aba": "prs", "item": "930", "filtros": {}},
        {"aba": "producao", "item": "v0.161.0", "filtros": {}},
        {"aba": "mapa", "item": None, "filtros": {}},
        {"aba": "issues", "item": None, "filtros": {}},
    ]
