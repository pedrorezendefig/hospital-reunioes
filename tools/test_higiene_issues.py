"""A Action de higiene só fecha o PRD pela última fatia concluída (PR #1577).

O "Atualizar o card" da aba Tecnologia (issue #1558) fecha as partes não
começadas como `not_planned`, com o token do Pedro, e devolve a raiz para
`needs-triage`. Esse fechamento dispara a Action (a anti-recursão do GitHub só
vale para o `GITHUB_TOKEN`); se ela fechasse a raiz como concluída, o card iria
para Entregue em vez de Em análise. Os testes rodam o script do job `higiene`
de verdade, no node, com o cliente do GitHub falso.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parent.parent
WORKFLOW = RAIZ / ".github" / "workflows" / "higiene-issues.yml"

HARNESS = """
const chamadas = [];
const issue = %(issue)s;
const parent = %(parent)s;
const context = { repo: { owner: 'o', repo: 'r' }, payload: { issue } };
const core = { info: () => {} };
const github = {
  graphql: async () => ({ repository: { issue: { parent } } }),
  rest: { issues: {
    removeLabel: async (a) => { chamadas.push(['removeLabel', a.issue_number, a.name]); },
    createComment: async (a) => { chamadas.push(['createComment', a.issue_number]); },
    update: async (a) => { chamadas.push(['update', a.issue_number, a.state, a.state_reason]); },
  } },
};
(async () => {
%(script)s
})().then(() => console.log(JSON.stringify(chamadas)));
"""


def script_da_higiene() -> str:
    w = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return w["jobs"]["higiene"]["steps"][0]["with"]["script"]


def rodar(tmp_path: Path, *, state_reason: str) -> list[list]:
    issue = {"number": 20, "state_reason": state_reason, "labels": [{"name": "ready-for-agent"}]}
    parent = {
        "number": 10,
        "state": "OPEN",
        "labels": {"nodes": [{"name": "needs-triage"}]},
        "subIssues": {"totalCount": 2, "nodes": [{"state": "CLOSED"}, {"state": "CLOSED"}]},
    }
    arquivo = tmp_path / "higiene.js"
    arquivo.write_text(
        HARNESS % {"issue": json.dumps(issue), "parent": json.dumps(parent), "script": script_da_higiene()},
        encoding="utf-8",
    )
    node = shutil.which("node")
    assert node, "o teste roda o script da Action no node"
    saida = subprocess.run([node, str(arquivo)], capture_output=True, text=True, check=True)
    return json.loads(saida.stdout)


def test_ultima_fatia_concluida_fecha_o_prd(tmp_path):
    chamadas = rodar(tmp_path, state_reason="completed")
    assert ["createComment", 10] in chamadas
    assert ["update", 10, "closed", "completed"] in chamadas


def test_ultima_fatia_nao_planejada_deixa_o_prd_aberto(tmp_path):
    chamadas = rodar(tmp_path, state_reason="not_planned")
    # A fatia que fechou ainda perde as labels de estado.
    assert ["removeLabel", 20, "ready-for-agent"] in chamadas
    # O PRD não é tocado: nem comentário, nem fechamento, nem label.
    assert [c for c in chamadas if c[1] == 10] == []
