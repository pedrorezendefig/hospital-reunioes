"""Designação falhou fica registrada na Demanda, com "Designar de novo" (issue #1536, PRD #1529, ADR 0083, decisão 7).

O envio ganha o terceiro resultado: a issue nasceu e a designação ao
Responsável não. A Demanda fica vinculada e guarda o estado; só o
Desenvolvedor o vê, com "Designar de novo", que pede ao GitHub só a
designação. Envio falhado e designação falhada avisam cada Desenvolvedor no
sino.

Tudo pela ROTA, com o modelo e o GitHub dublados no molde de `test_tecnologia_chat`.
"""

from __future__ import annotations

import os
import sys

import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from test_tecnologia_chat import (  # noqa: E402
    CHAT,
    _ate_o_resumo,
    _cenario,
    _demandas,
    _integracao_configurada,  # noqa: F401
    _llm_em_mock,  # noqa: F401
    _reset_rate_limiter,  # noqa: F401
)
from test_tecnologia_vinculo import DIRETOR, PEDRO, _issue, _montar, _pessoa  # noqa: E402

from app.services import github_client  # noqa: E402

CRIAR_O_CARD_DE_VERDADE = github_client.criar_issue
URL_DO_REPO = "https://api.github.com/repos/pedrorezendefig/hospital-reunioes"

# Outro Desenvolvedor da Vitta, para o aviso chegar a cada um.
LUCAS = _pessoa("P4", "Lucas Sampaio", github_login="lucas-vitta")


class _GithubDeVerdadeNaRede:
    """O cliente do GitHub roda inteiro; só o `httpx.request` é falso.

    O POST cria a issue 900. O PATCH que designa responde
    `status_da_designacao`; no 200, devolve a issue com o login pedido em
    `assignees`, como o GitHub devolve, salvo `ignora_o_login`, que imita o
    GitHub que responde 200 e deixa a issue sem ninguém.
    """

    def __init__(self, *, status_da_designacao: int = 200, ignora_o_login: bool = False):
        self.status_da_designacao = status_da_designacao
        self.ignora_o_login = ignora_o_login
        self.chamadas: list[tuple[str, str, dict | None]] = []

    def __call__(self, metodo, url, *, headers, json, timeout):
        self.chamadas.append((metodo, url, json))
        pedido = httpx.Request(metodo, url)
        if metodo == "POST":
            return httpx.Response(201, json={**_issue(900), "title": json["title"]}, request=pedido)
        if self.status_da_designacao != 200:
            return httpx.Response(
                self.status_da_designacao,
                json={"message": "Validation Failed", "errors": [{"field": "assignees"}]},
                request=pedido,
            )
        logins = [] if self.ignora_o_login else json["assignees"]
        return httpx.Response(
            200, json={**_issue(900), "assignees": [{"login": login} for login in logins]}, request=pedido
        )


def _na_rede(monkeypatch, rede: _GithubDeVerdadeNaRede) -> _GithubDeVerdadeNaRede:
    monkeypatch.setattr(github_client, "criar_issue", CRIAR_O_CARD_DE_VERDADE)
    monkeypatch.setattr(github_client.httpx, "request", rede)
    return rede


def _como(logado: dict, sb, gh, monkeypatch):
    if all(p["id"] != logado["id"] for p in sb.tabelas["participantes"]):
        sb.tabelas["participantes"].append(dict(logado))
    client, _, _ = _montar(logado=logado, supabase=sb, github=gh, monkeypatch=monkeypatch)
    return client


def _linha(lista: list[dict], demanda_id: str) -> dict:
    return next(d for d in lista if d["id"] == demanda_id)


# ═══════════════════════════════════════════════════════════════════════════
# 1. A designação que falha fica registrada
# ═══════════════════════════════════════════════════════════════════════════


class TestADesignacaoQueFalhaFicaRegistrada:
    def test_issue_criada_com_a_designacao_recusada_grava_o_estado_e_vincula(self, monkeypatch):
        client, sb, _ = _cenario(monkeypatch)
        demanda_id = _ate_o_resumo(client, monkeypatch)
        _na_rede(monkeypatch, _GithubDeVerdadeNaRede(status_da_designacao=422))

        resposta = client.post(f"{CHAT}/{demanda_id}/criar-card")

        assert resposta.status_code == 200, resposta.text
        demanda = _demandas(sb)[0]
        assert demanda["github_issue_numero"] == 900
        assert demanda["envio_estado"] == "designacao_falhou"
        assert "pedrorezendefig" in demanda["envio_motivo"]

    def test_o_github_que_responde_200_sem_o_login_tambem_e_designacao_falhada(self, monkeypatch):
        client, sb, _ = _cenario(monkeypatch)
        demanda_id = _ate_o_resumo(client, monkeypatch)
        _na_rede(monkeypatch, _GithubDeVerdadeNaRede(ignora_o_login=True))

        assert client.post(f"{CHAT}/{demanda_id}/criar-card").status_code == 200

        assert _demandas(sb)[0]["envio_estado"] == "designacao_falhou"

    def test_a_designacao_que_pega_nao_deixa_estado(self, monkeypatch):
        client, sb, _ = _cenario(monkeypatch)
        demanda_id = _ate_o_resumo(client, monkeypatch)
        _na_rede(monkeypatch, _GithubDeVerdadeNaRede())

        assert client.post(f"{CHAT}/{demanda_id}/criar-card").status_code == 200

        assert _demandas(sb)[0]["github_issue_numero"] == 900
        assert _demandas(sb)[0]["envio_estado"] is None


def _demanda_com_designacao_falhada(monkeypatch):
    """O diretor cria o card; a issue 900 nasce e o GitHub recusa o Responsável."""
    client, sb, gh = _cenario(monkeypatch, participantes=[PEDRO, DIRETOR, LUCAS])
    demanda_id = _ate_o_resumo(client, monkeypatch)
    rede = _na_rede(monkeypatch, _GithubDeVerdadeNaRede(status_da_designacao=422))
    assert client.post(f"{CHAT}/{demanda_id}/criar-card").status_code == 200
    return client, sb, gh, demanda_id, rede


# ═══════════════════════════════════════════════════════════════════════════
# 2. Quem vê
# ═══════════════════════════════════════════════════════════════════════════


class TestQuemVe:
    def test_o_desenvolvedor_ve_a_designacao_falhada_e_o_motivo(self, monkeypatch):
        _, sb, gh, demanda_id, _ = _demanda_com_designacao_falhada(monkeypatch)
        pedro = _como(PEDRO, sb, gh, monkeypatch)

        linha = _linha(pedro.get(f"{CHAT}?filtro=todas").json(), demanda_id)

        assert linha["designacao_falhou"] is True
        assert "pedrorezendefig" in linha["envio_motivo"]

    def test_o_diretor_nao_ve_a_designacao_falhada(self, monkeypatch):
        diretor, _, _, demanda_id, _ = _demanda_com_designacao_falhada(monkeypatch)

        linha = _linha(diretor.get(CHAT).json(), demanda_id)

        assert linha["designacao_falhou"] is False
        assert linha["envio_motivo"] is None
        assert linha["envio_falhou"] is False


# ═══════════════════════════════════════════════════════════════════════════
# 3. Designar de novo
# ═══════════════════════════════════════════════════════════════════════════


def _designar_de_novo(client, demanda_id: str):
    return client.post(f"{CHAT}/{demanda_id}/designar-de-novo")


class TestDesignarDeNovo:
    def test_pede_so_a_designacao_com_o_login_do_responsavel_e_limpa_o_estado(self, monkeypatch):
        client, sb, gh = _cenario(monkeypatch, participantes=[PEDRO, DIRETOR, LUCAS])
        demanda_id = _ate_o_resumo(client, monkeypatch)
        rede = _na_rede(monkeypatch, _GithubDeVerdadeNaRede(status_da_designacao=422))
        assert client.post(f"{CHAT}/{demanda_id}/criar-card", json={"responsavel_id": "P4"}).status_code == 200
        rede.status_da_designacao = 200
        rede.chamadas.clear()
        pedro = _como(PEDRO, sb, gh, monkeypatch)

        resposta = _designar_de_novo(pedro, demanda_id)

        assert resposta.status_code == 200, resposta.text
        assert rede.chamadas == [("PATCH", f"{URL_DO_REPO}/issues/900", {"assignees": ["lucas-vitta"]})]
        demanda = _demandas(sb)[0]
        assert demanda["envio_estado"] is None
        assert demanda["envio_motivo"] is None
        assert demanda["github_issue_numero"] == 900
        assert resposta.json()["designacao_falhou"] is False

    def test_o_diretor_nao_designa_de_novo(self, monkeypatch):
        diretor, sb, _, demanda_id, rede = _demanda_com_designacao_falhada(monkeypatch)
        rede.chamadas.clear()

        assert _designar_de_novo(diretor, demanda_id).status_code == 404

        assert rede.chamadas == []
        assert _demandas(sb)[0]["envio_estado"] == "designacao_falhou"

    def test_a_designacao_que_falha_de_novo_continua_no_estado(self, monkeypatch):
        _, sb, gh, demanda_id, rede = _demanda_com_designacao_falhada(monkeypatch)
        rede.status_da_designacao = 503
        pedro = _como(PEDRO, sb, gh, monkeypatch)

        assert _designar_de_novo(pedro, demanda_id).status_code == 502

        assert _demandas(sb)[0]["envio_estado"] == "designacao_falhou"
        assert _demandas(sb)[0]["envio_motivo"] == "GitHub respondeu 503"

    def test_demanda_sem_designacao_falhada_nao_chama_o_github(self, monkeypatch):
        client, sb, gh = _cenario(monkeypatch)
        demanda_id = _ate_o_resumo(client, monkeypatch)
        rede = _na_rede(monkeypatch, _GithubDeVerdadeNaRede())
        assert client.post(f"{CHAT}/{demanda_id}/criar-card").status_code == 200
        rede.chamadas.clear()

        assert _designar_de_novo(_como(PEDRO, sb, gh, monkeypatch), demanda_id).status_code == 409
        assert rede.chamadas == []
