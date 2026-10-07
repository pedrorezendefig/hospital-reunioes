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
    _corpo,
    _corpo_pr,
    _demanda,
    _demandas,
    _entregar,
    _entregue,
    _fio,
    _foto_guardada,
    _GithubFalso,
    _issue,
    _montar,
    _pessoa,
    _reset_rate_limiter,  # noqa: F401  (autouse)
    _segredo_configurado,  # noqa: F401  (autouse)
    _sem_email_de_verdade,  # noqa: F401  (autouse)
    _sem_github_de_verdade,  # noqa: F401  (autouse)
    _sem_pr_aberto,  # noqa: F401  (autouse)
)

from app.config import settings  # noqa: E402
from app.services import github_client, tecnologia_sincronizacao  # noqa: E402
from app.services.tecnologia import RECADO_DA_ENTREGA  # noqa: E402
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


def _quem_tem_o_card(sb) -> tuple[str, str]:
    demanda = _demandas(sb)[0]
    return demanda["estado"], demanda["responsavel_id"]


class TestADevolucaoEsperaAProducao:
    """O gatilho da devolução a quem pediu (ADR 0069, decisão 5): Em produção
    quando a issue fechou por PR, Entregue quando fechou sem PR. Nunca as duas.

    Pelas DUAS rotas de verdade, na ordem em que os eventos chegam: o merge pelo
    webhook do GitHub, depois o aviso da subida pelo webhook de deploy.
    """

    def _em_desenvolvimento_com_pr(self, monkeypatch):
        gh = _GithubFalso({673: _issue(673, labels=("in-progress",))})
        foto = {**_foto_guardada(gh, 673), "prs_abertos": [1100]}
        demanda = _demanda(
            "D1",
            github_issue_numero=673,
            etapa=ETAPA_EM_DESENVOLVIMENTO,
            github_foto=foto,
            estado="em_andamento",
            autor_id="P1",
            responsavel_id="P2",
        )
        cliente, sb, _ = _montar(
            demandas=[demanda],
            participantes=[_pessoa("P1")],
            produtos=[{"id": "prod-1", "nome": "Prontuário"}],
            github=gh,
            monkeypatch=monkeypatch,
        )
        gh.issues[673] = _entregue(673)
        return cliente, sb

    def test_fechada_por_pr_volta_a_quem_pediu_so_em_producao(self, monkeypatch, _sem_email_de_verdade):
        """Critério de aceite: o merge leva a Entregue e o card fica com a Vitta;
        a subida leva a Em produção e só então o card volta para quem pediu
        (Aguardando, Responsável o autor, e-mail de atribuição)."""
        cliente, sb = self._em_desenvolvimento_com_pr(monkeypatch)

        _entregar(cliente, _corpo_pr(acao="closed", merged=True), evento="pull_request")

        assert _demandas(sb)[0]["etapa"] == ETAPA_ENTREGUE
        assert _quem_tem_o_card(sb) == ("em_andamento", "P2"), "o merge não devolve: o código ainda não está no ar"
        assert _sem_email_de_verdade == []

        _avisar(cliente, _corpo_do_deploy())

        assert _demandas(sb)[0]["etapa"] == ETAPA_EM_PRODUCAO
        assert _quem_tem_o_card(sb) == ("aguardando", "P1")
        assert [(aviso["destinatario_id"], aviso["trecho"]) for aviso in _sem_email_de_verdade] == [
            ("P1", RECADO_DA_ENTREGA)
        ]
        assert _sem_email_de_verdade[0]["demanda"]["produto_nome"] == "Prontuário"

    def test_o_fechamento_que_chega_antes_do_merge_tambem_espera_a_producao(self, monkeypatch, _sem_email_de_verdade):
        """No merge, `issues.closed` pode chegar ANTES do `pull_request.closed`:
        a foto ainda diz "PR aberto" e não tem `fechada_por_pr`. O PR a caminho
        já diz que o fechamento é por PR, e a devolução espera a subida."""
        cliente, sb = self._em_desenvolvimento_com_pr(monkeypatch)

        _entregar(cliente, _corpo(acao="closed"))
        _entregar(cliente, _corpo_pr(acao="closed", merged=True), evento="pull_request")

        assert _demandas(sb)[0]["etapa"] == ETAPA_ENTREGUE
        assert _quem_tem_o_card(sb) == ("em_andamento", "P2")
        assert _sem_email_de_verdade == []

        _avisar(cliente, _corpo_do_deploy())

        assert _quem_tem_o_card(sb) == ("aguardando", "P1")
        assert len(_sem_email_de_verdade) == 1

    def test_fechada_sem_pr_volta_em_entregue_e_nao_de_novo_em_producao(self, monkeypatch, _sem_email_de_verdade):
        """Critério de aceite: a issue fechada à mão (decisão, consultoria)
        devolve em Entregue, como hoje. Se uma subida a listar depois, a
        Demanda ganha Em produção sem ser devolvida outra vez."""
        gh = _GithubFalso({673: _issue(673, labels=("in-progress",))})
        cliente, sb, _ = _montar(
            demandas=[
                _demanda(
                    "D1",
                    github_issue_numero=673,
                    etapa=ETAPA_EM_DESENVOLVIMENTO,
                    github_foto=_foto_guardada(gh, 673),
                    estado="em_andamento",
                    autor_id="P1",
                    responsavel_id="P2",
                )
            ],
            participantes=[_pessoa("P1")],
            github=gh,
            monkeypatch=monkeypatch,
        )
        gh.issues[673] = _entregue(673)

        _entregar(cliente, _corpo(acao="closed"))

        assert _demandas(sb)[0]["etapa"] == ETAPA_ENTREGUE
        assert _quem_tem_o_card(sb) == ("aguardando", "P1")
        assert len(_sem_email_de_verdade) == 1

        # O diretor conferiu e passou a bola adiante; a subida chega depois.
        _demandas(sb)[0].update(estado="em_andamento", responsavel_id="P2")
        _avisar(cliente, _corpo_do_deploy())

        assert _demandas(sb)[0]["etapa"] == ETAPA_EM_PRODUCAO
        assert _quem_tem_o_card(sb) == ("em_andamento", "P2"), "devolvida duas vezes"
        assert len(_sem_email_de_verdade) == 1


class TestAMesmaVersaoNaoRegrava:
    def test_a_mesma_versao_duas_vezes_nao_grava_nem_avisa_de_novo(self, monkeypatch, _sem_email_de_verdade):
        """Critério de aceite: a Action reexecutada (ou o aviso repetido) não
        escreve nada na segunda vez: nem a Demanda, nem o fio, nem o e-mail."""
        gh = _GithubFalso({673: _entregue(673)})
        cliente, sb, _ = _montar(
            demandas=[_entregue_por_pr(gh, 673, "D1", responsavel_id="P2")],
            participantes=[_pessoa("P1")],
            github=gh,
            monkeypatch=monkeypatch,
        )
        _avisar(cliente, _corpo_do_deploy())
        depois_da_primeira = dict(_demandas(sb)[0])
        linhas = len(_fio(sb))
        assert len(_sem_email_de_verdade) == 1, "o piso: a primeira chamada devolveu"

        resposta = _avisar(cliente, _corpo_do_deploy())

        assert resposta.json()["marcadas"] == 0
        assert _demandas(sb)[0] == depois_da_primeira
        assert len(_fio(sb)) == linhas
        assert len(_sem_email_de_verdade) == 1

    def test_a_releitura_da_issue_depois_da_subida_mantem_em_producao(self, monkeypatch):
        """A reconciliação de hora em hora relê a issue, que segue fechada: a
        Etapa fica Em produção, sem linha nova. Sem isto, a passagem seguinte
        derivaria Entregue da foto e o selo voltaria para trás."""
        gh = _GithubFalso({673: _entregue(673)})
        cliente, sb, _ = _montar(
            demandas=[_entregue_por_pr(gh, 673, "D1")],
            participantes=[_pessoa("P1")],
            github=gh,
            monkeypatch=monkeypatch,
        )
        _avisar(cliente, _corpo_do_deploy())
        linhas = len(_fio(sb))

        tecnologia_sincronizacao.reconciliar_vinculos(sb)

        assert _demandas(sb)[0]["etapa"] == ETAPA_EM_PRODUCAO
        assert len(_fio(sb)) == linhas

    def test_a_issue_reaberta_sai_de_em_producao_e_o_novo_fechamento_espera_a_subida(self, monkeypatch):
        """O diretor pediu ajuste: a issue reabre e a Etapa volta a andar. O
        fechamento seguinte é Entregue, e não Em produção com a versão velha."""
        gh = _GithubFalso({673: _entregue(673)})
        cliente, sb, _ = _montar(
            demandas=[_entregue_por_pr(gh, 673, "D1")],
            participantes=[_pessoa("P1")],
            github=gh,
            monkeypatch=monkeypatch,
        )
        _avisar(cliente, _corpo_do_deploy())

        gh.issues[673] = _issue(673, labels=("in-progress",))
        _entregar(cliente, _corpo(acao="reopened"))
        assert _demandas(sb)[0]["etapa"] == ETAPA_EM_DESENVOLVIMENTO

        gh.issues[673] = _entregue(673)
        _entregar(cliente, _corpo(acao="closed"))
        assert _demandas(sb)[0]["etapa"] == ETAPA_ENTREGUE

        _avisar(cliente, _corpo_do_deploy("0.170.0"))
        demanda = _demandas(sb)[0]
        assert (demanda["etapa"], demanda["versao_em_producao"]) == (ETAPA_EM_PRODUCAO, "v0.170.0")


class TestAPortaDoDeploy:
    @pytest.mark.parametrize(
        "assinatura",
        (None, "sha256=" + "0" * 64, "outro-segredo", "github"),
        ids=("sem_assinatura", "assinatura_errada", "outro_segredo", "segredo_do_webhook_do_github"),
    )
    def test_assinatura_invalida_e_recusada_sem_gravar(self, assinatura, monkeypatch):
        """Critério de aceite: 401 antes de qualquer leitura ou escrita. O
        segredo do webhook do GitHub não abre esta porta: são dois segredos."""
        gh = _GithubFalso({673: _entregue(673)})
        cliente, sb, _ = _montar(demandas=[_entregue_por_pr(gh, 673, "D1")], github=gh, monkeypatch=monkeypatch)
        corpo = _corpo_do_deploy()
        if assinatura == "outro-segredo":
            assinatura = _assinar(corpo, segredo="outro-segredo")
        elif assinatura == "github":
            assinatura = _assinar(corpo)

        resposta = _avisar(cliente, corpo, assinatura=assinatura)

        assert resposta.status_code == 401
        assert _demandas(sb)[0]["etapa"] == ETAPA_ENTREGUE
        assert _fio(sb) == []

    def test_sem_o_segredo_configurado_responde_503(self, monkeypatch):
        """Critério de aceite: até o passo humano, a porta fica fechada e diz
        que está indisponível, e não que a assinatura falhou. A assinatura com
        segredo vazio é a tentativa que uma porta aberta aceitaria."""
        monkeypatch.setattr(settings, "tecnologia_deploy_webhook_secret", "")
        gh = _GithubFalso({673: _entregue(673)})
        cliente, sb, _ = _montar(demandas=[_entregue_por_pr(gh, 673, "D1")], github=gh, monkeypatch=monkeypatch)
        corpo = _corpo_do_deploy()

        resposta = _avisar(cliente, corpo, assinatura=_assinar(corpo, segredo=""))

        assert resposta.status_code == 503
        assert _demandas(sb)[0]["etapa"] == ETAPA_ENTREGUE

    @pytest.mark.parametrize(
        "corpo",
        (
            {"versao": "latest", "data": DATA_DA_SUBIDA, "prs": []},
            {"versao": "0.169.0", "data": "ontem", "prs": []},
            {"versao": "0.169.0", "data": "2026-10-07T18:00:00", "prs": []},
            {"versao": "0.169.0", "data": DATA_DA_SUBIDA, "prs": [{"numero": 1100, "fecha": ["673"]}]},
            {"versao": "0.169.0", "data": DATA_DA_SUBIDA, "prs": [{"numero": True, "fecha": [673]}]},
            {"versao": "0.169.0", "data": DATA_DA_SUBIDA},
        ),
        ids=("versao", "data", "data_sem_fuso", "issue_em_texto", "pr_booleano", "sem_prs"),
    )
    def test_aviso_fora_do_formato_e_recusado_com_422(self, corpo, monkeypatch):
        gh = _GithubFalso({673: _entregue(673)})
        cliente, sb, _ = _montar(demandas=[_entregue_por_pr(gh, 673, "D1")], github=gh, monkeypatch=monkeypatch)

        resposta = _avisar(cliente, json.dumps(corpo).encode("utf-8"))

        assert resposta.status_code == 422
        assert _demandas(sb)[0]["etapa"] == ETAPA_ENTREGUE
