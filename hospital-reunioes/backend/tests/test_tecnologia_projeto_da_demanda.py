"""O Projeto na Demanda: Aplicativo do Hospital e Ana (issue #1713, PRD #1710,
ADR 0093, decisoes 2, 3 e 6).

A issue #50 da Ana e a #50 do Hospital sao Demandas diferentes: a chave do
Vinculo passa a ser projeto mais numero da issue. Os cenarios aqui poem as duas
lado a lado, com o MESMO numero, e olham qual delas cada caminho toca.

Os dubles sao os do webhook do GitHub (`test_tecnologia_webhook_github`), com
um GitHub falso que responde por projeto: a leitura que vai ao repositorio
errado aparece em `leituras`, e a issue que nao existe naquele repositorio
estoura.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from test_tecnologia_webhook_github import (  # noqa: E402
    REPO,
    _corpo,
    _demanda,
    _demandas,
    _entregar,
    _entregue,
    _issue,
    _montar,
    _pr_do_app,  # noqa: F401  (autouse)
    _reset_rate_limiter,  # noqa: F401  (autouse)
    _segredo_configurado,  # noqa: F401  (autouse)
    _sem_github_de_verdade,  # noqa: F401  (autouse)
    _sem_pr_aberto,  # noqa: F401  (autouse)
)

from app.config import settings  # noqa: E402
from app.services import github_client  # noqa: E402
from app.services.tecnologia_vinculo import (  # noqa: E402
    ETAPA_EM_ANALISE,
    ETAPA_EM_DESENVOLVIMENTO,
    ETAPA_ENTREGUE,
)

REPO_ANA = "pedrorezendefig/programa-ana"

HOSPITAL = "hospital"
ANA = "ana"


@pytest.fixture(autouse=True)
def _ana_configurada(monkeypatch):
    """O repositorio da Ana de pe, como estara no Coolify depois da tarefa
    humana #1717. Quem prova a Ana desligada e o teste que APAGA a variavel."""
    monkeypatch.setattr(settings, "github_integracao_repo_ana", REPO_ANA)


class _GithubDosDoisProjetos:
    """O GitHub com um repositorio por Projeto: a issue e achada por (projeto,
    numero), e cada leitura fica registrada com o projeto que a pediu."""

    def __init__(self, issues: dict[tuple[str, int], dict]):
        self.issues = issues
        self.leituras: list[tuple[str, int]] = []

    def ler_issue(self, numero: int, *, projeto: str) -> dict:
        self.leituras.append((projeto, numero))
        if (projeto, numero) not in self.issues:
            raise github_client.IssueNaoEncontradaError(f"{projeto}#{numero}")
        return self.issues[(projeto, numero)]

    def ler_sub_issues(self, numero: int, *, projeto: str) -> list[dict]:
        return []


def _montar_dois(monkeypatch, demandas: list[dict], gh: _GithubDosDoisProjetos):
    cliente, sb, _ = _montar(demandas=demandas, monkeypatch=monkeypatch)
    monkeypatch.setattr(github_client, "ler_issue", gh.ler_issue)
    monkeypatch.setattr(github_client, "ler_sub_issues", gh.ler_sub_issues)
    return cliente, sb


def _por_id(sb) -> dict[str, dict]:
    return {d["id"]: d for d in _demandas(sb)}


# A issue #50 dos dois lados, cada uma levando a uma Etapa diferente: a do
# Hospital em desenvolvimento, a da Ana entregue. A Etapa que cada Demanda
# ganha diz de qual repositorio ela foi lida.
ISSUES_50 = {
    (HOSPITAL, 50): _issue(50, labels=("in-progress",)),
    (ANA, 50): {**_entregue(50), "html_url": f"https://github.com/{REPO_ANA}/issues/50"},
}


def _as_duas_demandas_50(*, ana_primeiro: bool) -> list[dict]:
    """A Demanda da Ana e a do Hospital, as duas na issue #50 e Em analise.
    A ordem conta: quem achasse a Demanda so pelo numero pegaria a primeira."""
    hospital = _demanda("DH", projeto=HOSPITAL, github_issue_numero=50, etapa=ETAPA_EM_ANALISE)
    ana = _demanda("DA", projeto=ANA, github_issue_numero=50, etapa=ETAPA_EM_ANALISE)
    return [ana, hospital] if ana_primeiro else [hospital, ana]


class TestOWebhookDoGithubPorProjeto:
    def test_evento_da_ana_na_issue_50_mexe_so_na_demanda_da_ana(self, monkeypatch):
        """Criterio de aceite: o evento do repositorio da Ana le a issue la e
        move so a Demanda da Ana; a do Hospital, com o mesmo numero, fica."""
        gh = _GithubDosDoisProjetos(ISSUES_50)
        cliente, sb = _montar_dois(monkeypatch, _as_duas_demandas_50(ana_primeiro=False), gh)

        resposta = _entregar(cliente, _corpo(50, repo=REPO_ANA))

        assert resposta.status_code == 200
        assert resposta.json()["sincronizada"] is True
        assert gh.leituras == [(ANA, 50)]
        demandas = _por_id(sb)
        assert demandas["DA"]["etapa"] == ETAPA_ENTREGUE
        assert demandas["DH"]["etapa"] == ETAPA_EM_ANALISE

    def test_evento_do_hospital_na_issue_50_mexe_so_na_demanda_do_hospital(self, monkeypatch):
        gh = _GithubDosDoisProjetos(ISSUES_50)
        cliente, sb = _montar_dois(monkeypatch, _as_duas_demandas_50(ana_primeiro=True), gh)

        resposta = _entregar(cliente, _corpo(50, repo=REPO))

        assert resposta.status_code == 200
        assert resposta.json()["sincronizada"] is True
        assert gh.leituras == [(HOSPITAL, 50)]
        demandas = _por_id(sb)
        assert demandas["DH"]["etapa"] == ETAPA_EM_DESENVOLVIMENTO
        assert demandas["DA"]["etapa"] == ETAPA_EM_ANALISE
