"""O Responsável acompanha a troca de dono no GitHub (issue #1534, PRD #1529, ADR 0083, decisão 6).

Depois do card criado, o Responsável é derivado do GitHub, como a Etapa: a
troca de assignee na issue vinculada chega pelo webhook e grava na Demanda o
usuário cujo login do GitHub corresponde. Assignee sem usuário no app aparece
pelo login. O app não tem rota nem botão para trocar o Responsável.

O webhook vai pela ROTA de verdade, com a assinatura e os dublês de
`test_tecnologia_webhook_github`.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from test_tecnologia_webhook_github import (  # noqa: E402
    _corpo,
    _demanda,
    _demandas,
    _entregar,
    _GithubFalso,
    _issue,
    _ja_sincronizada,
    _montar,
    _pr_do_app,  # noqa: F401
    _reset_rate_limiter,  # noqa: F401
    _segredo_configurado,  # noqa: F401
    _sem_github_de_verdade,  # noqa: F401
    _sem_pr_aberto,  # noqa: F401
)

from app.services import tecnologia_sincronizacao  # noqa: E402


def _pessoa(pid: str, nome: str, login: str | None) -> dict:
    return {"id": pid, "nome_completo": nome, "github_login": login, "ativo": True}


PEDRO = _pessoa("P1", "Pedro Rezende", "pedrorezendefig")
RIB = _pessoa("P4", "Pedro Rib", "pedrorib")
DIRETOR = _pessoa("P2", "Diretor", None)


def _issue_designada(numero: int, *logins: str) -> dict:
    dados = _issue(numero, labels=["needs-triage"])
    dados["assignees"] = [{"login": login} for login in logins]
    dados["assignee"] = dados["assignees"][0] if logins else None
    return dados


def _vinculada_ao_pedro(numero: int = 673) -> tuple[_GithubFalso, dict]:
    """A Demanda como o "Criar o card" a deixou: designada ao Pedro, que é o
    Responsável."""
    gh = _GithubFalso({numero: _issue_designada(numero, "PedroRezendeFig")})
    demanda = _ja_sincronizada(gh, numero, responsavel_id=PEDRO["id"])
    return gh, demanda


class TestATrocaDeAssignee:
    @pytest.mark.parametrize("acao", ["assigned", "unassigned"])
    def test_a_troca_de_dono_no_github_troca_o_responsavel_da_demanda(self, monkeypatch, acao):
        gh, demanda = _vinculada_ao_pedro()
        client, sb, _ = _montar(demandas=[demanda], participantes=[PEDRO, RIB, DIRETOR], github=gh, monkeypatch=monkeypatch)
        gh.issues[673] = _issue_designada(673, "pedrorib")

        resposta = _entregar(client, _corpo(673, acao=acao))

        assert resposta.status_code == 200, resposta.text
        assert resposta.json() == {"recebido": True, "sincronizada": True}
        assert _demandas(sb)[0]["responsavel_id"] == RIB["id"]
