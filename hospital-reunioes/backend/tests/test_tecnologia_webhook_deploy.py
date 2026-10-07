"""O webhook de deploy: a Etapa Em produção (issue #1065, PRD #1056, ADR 0069).

A Action pós-merge chama `POST /webhooks/deploy` depois do registro da subida,
com a versão, a data e os PRs do lote (cada um com as issues que fecha). O app
marca Em produção as Demandas vinculadas a essas issues, escreve a linha
automática "Em produção na vX.Y.Z" e, quando a issue fechou por PR, devolve a
Demanda a quem pediu (ADR 0069, decisões 4 e 5).

Os dublês são os do webhook do GitHub (`test_tecnologia_webhook_github`): o
mesmo Supabase em memória, o mesmo GitHub falso e as mesmas travas autouse
contra rede e e-mail de verdade, importadas para valerem aqui também.

O segredo usado aqui é um valor FALSO deste arquivo. O de produção mora no
Coolify e nos secrets do repositório, e não entra em teste, log, commit nem
corpo de PR.
"""

from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from test_tecnologia_webhook_github import (  # noqa: E402
    _assinar,
    _demanda,
    _demandas,
    _entregue,
    _fio,
    _foto_guardada,
    _GithubFalso,
    _montar,
    _pessoa,
    _reset_rate_limiter,  # noqa: F401  (autouse)
    _segredo_configurado,  # noqa: F401  (autouse)
    _sem_email_de_verdade,  # noqa: F401  (autouse)
    _sem_github_de_verdade,  # noqa: F401  (autouse)
    _sem_pr_aberto,  # noqa: F401  (autouse)
)

from app.config import settings  # noqa: E402
from app.services import github_client  # noqa: E402
from app.services.tecnologia_vinculo import (  # noqa: E402
    ETAPA_EM_DESENVOLVIMENTO,
    ETAPA_EM_PRODUCAO,
    ETAPA_ENTREGUE,
)

ROTA = "/api/webhooks/deploy"

# Valor de mentira, deste arquivo.
SEGREDO_DO_DEPLOY = "segredo-falso-do-deploy-1065"

DATA_DA_SUBIDA = "2026-10-07T18:00:00-03:00"


@pytest.fixture(autouse=True)
def _segredo_do_deploy_configurado(monkeypatch):
    """O segredo de pé, como estará no Coolify. Quem prova o 503 é o teste que
    o APAGA, e não a ausência dele por acidente."""
    monkeypatch.setattr(settings, "tecnologia_deploy_webhook_secret", SEGREDO_DO_DEPLOY)


def _corpo_do_deploy(versao: str = "0.169.0", prs: list[dict] | None = None, data: str = DATA_DA_SUBIDA) -> bytes:
    """O corpo CRU que a Action manda: versão, data e os PRs do lote."""
    if prs is None:
        prs = [{"numero": 1100, "fecha": [673]}]
    return json.dumps({"versao": versao, "data": data, "prs": prs}, indent=2).encode("utf-8")


def _avisar(cliente, corpo: bytes, *, assinatura: str | None = "auto"):
    cabecalhos = {"Content-Type": "application/json"}
    if assinatura == "auto":
        assinatura = _assinar(corpo, segredo=SEGREDO_DO_DEPLOY)
    if assinatura is not None:
        cabecalhos["X-Hub-Signature-256"] = assinatura
    return cliente.post(ROTA, content=corpo, headers=cabecalhos)


def _entregue_por_pr(gh: _GithubFalso, numero: int, did: str, *, pr: int = 1100, **campos) -> dict:
    """A Demanda cuja issue o merge fechou: Etapa Entregue e o `fechada_por_pr`
    que o webhook `pull_request` gravou na foto (issue #1064)."""
    foto = {**_foto_guardada(gh, numero), "fechada_por_pr": pr}
    base = {"etapa": ETAPA_ENTREGUE, "github_foto": foto, "github_issue_numero": numero}
    return _demanda(did, **{**base, **campos})


class TestOWebhookMarcaEmProducao:
    def test_marca_em_producao_so_as_demandas_que_o_lote_fechou(self, monkeypatch):
        """Critério de aceite: a Demanda da issue que o PR do lote fechou ganha
        Em produção com a versão e a data; a outra, também Entregue, fica."""
        gh = _GithubFalso({673: _entregue(673), 674: _entregue(674)})
        cliente, sb, _ = _montar(
            demandas=[_entregue_por_pr(gh, 673, "D1"), _entregue_por_pr(gh, 674, "D2", pr=1101)],
            participantes=[_pessoa()],
            github=gh,
            monkeypatch=monkeypatch,
        )

        resposta = _avisar(cliente, _corpo_do_deploy())

        assert resposta.status_code == 200
        d1, d2 = _demandas(sb)
        assert (d1["etapa"], d1["versao_em_producao"], d1["entregue_em"]) == (
            ETAPA_EM_PRODUCAO,
            "v0.169.0",
            DATA_DA_SUBIDA,
        )
        assert d2["etapa"] == ETAPA_ENTREGUE
        assert d2.get("versao_em_producao") is None
        assert gh.leituras == [], "o webhook de deploy não relê o GitHub"

    def test_a_linha_em_producao_entra_na_conversa_e_nao_e_espelhada(self, monkeypatch):
        """Critério de aceite: "Em produção na v0.169.0" no fio do diretor, como
        linha automática (sem autor), e nada publicado na issue."""
        publicados: list = []
        monkeypatch.setattr(github_client, "criar_comentario", lambda *a, **kw: publicados.append(a) or 1)
        gh = _GithubFalso({673: _entregue(673)})
        cliente, sb, _ = _montar(
            demandas=[_entregue_por_pr(gh, 673, "D1")],
            participantes=[_pessoa()],
            github=gh,
            monkeypatch=monkeypatch,
        )

        resposta = _avisar(cliente, _corpo_do_deploy())

        assert resposta.json() == {"recebido": True, "versao": "v0.169.0", "marcadas": 1, "falhas": 0}
        linha = _fio(sb)[0]
        assert linha["texto"] == "Em produção na v0.169.0"
        assert (linha["linha"], linha["autor_id"]) == ("movimento", None)
        assert (linha["movimento_campo"], linha["movimento_de"], linha["movimento_para"]) == (
            "etapa",
            ETAPA_ENTREGUE,
            ETAPA_EM_PRODUCAO,
        )
        assert publicados == [], "a linha automática não vira comentário na issue"
