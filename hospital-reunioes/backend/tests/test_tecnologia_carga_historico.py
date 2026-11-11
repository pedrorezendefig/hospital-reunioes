"""A carga do historico de entregas desde o primeiro deploy (issue #1555, PRD #1548, ADR 0084, decisao 8).

Uma seam so: `carregar`, chamada direto com o banco duble do webhook e o GitHub
falso (as issues fechadas, as sub-issues e o `history.json`). E a mesma funcao
que o comando de uma vez roda, local ou no container de producao.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from test_tecnologia_webhook_github import (  # noqa: E402
    REPO,
    _demanda,
    _GithubFalso,
    _SupabaseMock,
    _sem_github_de_verdade,  # noqa: F401 (fixture autouse: nenhuma chamada sai para a rede)
)

from app.services import email_service, github_client  # noqa: E402
from app.services.tecnologia_carga_historico import carregar  # noqa: E402
from app.services.tecnologia_vinculo import ETAPA_EM_PRODUCAO, ETAPA_ENTREGUE  # noqa: E402

PRODUTO = {"id": "prod-1", "nome": "App do Hospital", "ativo": True, "ordem": 1}

CORPO_DE_RAIZ = "## 👔 Para o diretor\n\n**O que muda:** o prazo aparece por setor.\n\n---\n\n## Problema\n\nX."


def _fechada(numero: int, *, fechada_em: str, labels=("type:feature", "area:backend"), corpo=CORPO_DE_RAIZ, **campos):
    """Uma issue fechada como concluida, como a lista de issues do GitHub a manda."""
    dados = {
        "number": numero,
        "title": f"Entrega antiga #{numero}",
        "html_url": f"https://github.com/{REPO}/issues/{numero}",
        "state": "closed",
        "state_reason": "completed",
        "closed_at": fechada_em,
        "labels": [{"name": nome} for nome in labels],
        "body": corpo,
        "user": {"login": "pedrorezendefig"},
        "parent_issue_url": None,
    }
    dados.update(campos)
    return dados


def _subida(at: str, versao: str, *, notas: str = "", prds=()) -> dict:
    """Uma entrada do `history.json`, so com o que a carga le."""
    return {"at": at, "app_version": versao, "notes": notas, "prds": list(prds), "result": "healthy"}


# O `history.json` falso, a mais nova primeiro, como o arquivo de verdade.
#
# - A #1600 e fechada pelo PR #1601 na v0.150.0 e de novo (reaberta) pelo PR
#   #1610 na v0.160.0: a primeira e a v0.150.0.
# - A #1700 e um PRD: o `prds` a cita na v0.151.0 e na v0.170.0, e nenhum PR a
#   fecha: a primeira e a v0.151.0.
# - A #1800 e citada pelo `prds` na v0.140.0 e fechada por PR na v0.155.0: a
#   primeira entrada que a cita, por qualquer das duas portas, e a v0.140.0.
HISTORICO = [
    _subida("2026-10-20T10:00:00-03:00", "0.170.0", notas="Onda: PR #1720 (issue #1721).", prds=[1700]),
    _subida("2026-10-10T10:00:00-03:00", "0.160.0", notas="Onda: PR #1610 (issue #1600)."),
    _subida("2026-10-05T10:00:00-03:00", "0.155.0", notas="PR avulso: PR #1801, issue #1800."),
    _subida("2026-10-02T10:00:00-03:00", "0.151.0", notas="Onda: PR #1710 (issue #1711).", prds=[1700]),
    _subida("2026-10-01T10:00:00-03:00", "0.150.0", notas="Onda: PR #1601 (issue #1600) e PR #1602 (sem issue)."),
    _subida("2026-09-20T10:00:00-03:00", "0.140.0", notas="Registro antigo, texto livre.", prds=[1800]),
]


class _Cenario:
    def __init__(self, monkeypatch, *, fechadas: list[dict], demandas=(), historico=HISTORICO, sub_issues=None):
        self.sb = _SupabaseMock(
            {
                "tecnologia_demandas": [dict(d) for d in demandas],
                "tecnologia_produtos": [dict(PRODUTO)],
                "participantes": [],
                "notificacoes": [],
            }
        )
        self.gh = _GithubFalso({issue["number"]: issue for issue in fechadas}, sub_issues=sub_issues)
        monkeypatch.setattr(github_client, "ler_issue", self.gh.ler_issue)
        monkeypatch.setattr(github_client, "ler_sub_issues", self.gh.ler_sub_issues)
        monkeypatch.setattr(github_client, "listar_issues_fechadas", lambda: [dict(i) for i in fechadas])
        monkeypatch.setattr(github_client, "ler_historico_de_deploys", lambda: [dict(e) for e in historico])

    @property
    def demandas(self) -> list[dict]:
        return self.sb.tabelas["tecnologia_demandas"]

    def demanda(self, numero: int) -> dict:
        (linha,) = [d for d in self.demandas if d.get("github_issue_numero") == numero]
        return linha


# ═══════════════════════════════════════════════════════════════════════════
# As datas e a versao batem com a primeira entrada certa
# ═══════════════════════════════════════════════════════════════════════════


class TestDatasDaPrimeiraSubida:
    def test_entrega_reaberta_fica_com_a_primeira_subida_que_a_fechou(self, monkeypatch):
        cenario = _Cenario(monkeypatch, fechadas=[_fechada(1600, fechada_em="2026-10-08T15:00:00Z")])

        carregar(cenario.sb, dry_run=False)

        demanda = cenario.demanda(1600)
        assert demanda["entregue_em"] == "2026-10-08T15:00:00Z"
        assert demanda["em_producao_em"] == "2026-10-01T10:00:00-03:00"
        assert demanda["versao_em_producao"] == "v0.150.0"
        assert demanda["etapa"] == ETAPA_EM_PRODUCAO
