"""O CI que o GitHub cancelou por falta de runner não é falha de código (issue #953).

Num incidente do Actions o job fica 15 min na fila e sai `CANCELLED` com a
anotação "The job was not acquired by Runner of type hosted even after multiple
attempts", sem rodar nenhum passo. O `ci_sem_runner.py` separa esse caso do
vermelho de verdade para a esteira repetir o run em vez de corrigir código certo.
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SCRIPTS = RAIZ / ".claude" / "skills" / "onda-enxuta" / "scripts"

ANOTACAO = "The job was not acquired by Runner of type hosted even after multiple attempts"


def carregar():
    sys.path.insert(0, str(SCRIPTS))
    try:
        sys.modules.pop("ci_sem_runner", None)
        import ci_sem_runner
    finally:
        sys.path.remove(str(SCRIPTS))
    return ci_sem_runner


def check(nome: str, conclusao: str, run: str, job: str) -> dict:
    return {"__typename": "CheckRun", "name": nome, "status": "COMPLETED", "conclusion": conclusao,
            "workflowName": "CI",
            "detailsUrl": f"https://github.com/dono/repo/actions/runs/{run}/job/{job}"}


def anotacoes(por_job: dict[str, list[str]]):
    return lambda job: por_job.get(job, [])


def test_todo_vermelho_cancelado_sem_runner_devolve_os_runs_a_repetir():
    m = carregar()
    vermelhos = [check("Backend", "CANCELLED", "10", "1"), check("Docker", "CANCELLED", "10", "2"),
                 check("Lint skills", "CANCELLED", "20", "3")]
    por_job = {"1": [ANOTACAO], "2": ["aviso do ubuntu-latest", ANOTACAO], "3": [ANOTACAO]}

    assert m.runs_sem_runner(vermelhos, anotacoes(por_job)) == {"10", "20"}


def test_um_vermelho_de_codigo_no_meio_faz_o_lote_inteiro_ser_vermelho():
    m = carregar()
    vermelhos = [check("Backend", "FAILURE", "10", "1"), check("Docker", "CANCELLED", "10", "2")]
    por_job = {"1": [ANOTACAO], "2": [ANOTACAO]}

    assert m.runs_sem_runner(vermelhos, anotacoes(por_job)) == set()


def test_cancelamento_sem_a_anotacao_do_runner_continua_vermelho():
    # cancelado por concorrência, à mão ou por timeout: não é incidente do Actions
    m = carregar()
    vermelhos = [check("Backend", "CANCELLED", "10", "1")]

    assert m.runs_sem_runner(vermelhos, anotacoes({"1": ["The operation was canceled."]})) == set()


def test_check_sem_link_de_job_continua_vermelho():
    # status externo (sem /actions/runs/<run>/job/<job>) não tem como ser repetido
    m = carregar()
    externo = {"__typename": "StatusContext", "context": "vercel", "state": "ERROR"}

    assert m.runs_sem_runner([externo], anotacoes({})) == set()


def test_sem_vermelho_nao_ha_o_que_repetir():
    assert carregar().runs_sem_runner([], anotacoes({})) == set()
