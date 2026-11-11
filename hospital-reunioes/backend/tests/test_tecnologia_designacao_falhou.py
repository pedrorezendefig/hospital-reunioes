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
