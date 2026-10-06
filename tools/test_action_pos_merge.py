"""A Action pós-merge: snapshot e draft do Manual direto na `main` (issue #940).

ADR 0062, decisão 10: o rabo deixou de rodar o `snapshot.py` e o
`tirar_draft_manual.py` (#939), e quem roda os dois é um workflow no push da
`main`, que commita como `github-actions[bot]` pelo bypass do ruleset. Estes
testes amarram o contrato do workflow (evento, branch, autor, `[skip ci]`, o
filtro que impede a Action de acordar com o próprio commit) e rodam os passos
de shell dele de verdade, num repo git de brinquedo.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parent.parent
WORKFLOW = RAIZ / ".github" / "workflows" / "pos-merge.yml"


def workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def gatilhos() -> dict:
    # O PyYAML segue o YAML 1.1, em que `on` é booleano: a chave vira True.
    w = workflow()
    return w["on"] if "on" in w else w[True]


def test_dispara_no_push_da_main_e_nunca_em_pull_request():
    """O commit vai direto na `main` pelo bypass; em PR a Action escreveria na
    branch de outra pessoa, ou commitaria snapshot de código que não subiu."""
    on = gatilhos()
    assert on["push"]["branches"] == ["main"]
    assert "pull_request" not in on
    assert "pull_request_target" not in on
    assert workflow()["permissions"] == {"contents": "write"}


def casa(padrao: str, caminho: str) -> bool:
    """O glob do filtro de caminhos do GitHub: `**` atravessa pastas, `*` não."""
    regex = ""
    i = 0
    while i < len(padrao):
        if padrao.startswith("**", i):
            regex += ".*"
            i += 2
        elif padrao[i] == "*":
            regex += "[^/]*"
            i += 1
        else:
            regex += re.escape(padrao[i])
            i += 1
    return re.fullmatch(regex, caminho) is not None


def acorda(mudados: list[str]) -> bool:
    """Com `paths-ignore`, o push só não acorda a Action se todo caminho cair
    num padrão ignorado."""
    ignorados = gatilhos()["push"]["paths-ignore"]
    return any(not any(casa(p, c) for p in ignorados) for c in mudados)


def test_push_que_so_toca_snapshot_e_paginas_do_manual_nao_acorda_a_action():
    """É o que a própria Action escreve. Push do `GITHUB_TOKEN` já não dispara
    workflow; o filtro cobre quem rodar o snapshot à mão e empurrar."""
    assert not acorda(["docs/spec/snapshots/ROTAS.md", "docs/spec/snapshots/SCHEMA.md"])
    assert not acorda(["docs/ARQUITETURA.md"])
    assert not acorda(["docs/manual/src/content/docs/ouvidoria/manifestacoes/registrar.mdx"])
    assert not acorda(["docs/spec/snapshots/ROTAS.md", "docs/ARQUITETURA.md",
                       "docs/manual/src/content/docs/index.mdx"])


def test_merge_do_registro_e_de_codigo_acordam_a_action():
    """O gatilho que importa é o PR de registro do rabo: com o `history.json`
    na `main`, o draft sabe o que está em produção."""
    assert acorda(["docs/spec/deploy/history.json", "docs/spec/deploy/state.json"])
    assert acorda(["hospital-reunioes/backend/app/routers/atas.py"])
    assert acorda(["docs/spec/snapshots/ROTAS.md", "hospital-reunioes/supabase/migrations/115_x.sql"])
    assert acorda(["docs/manual/video/ouvidoria/registrar/index.html"])
