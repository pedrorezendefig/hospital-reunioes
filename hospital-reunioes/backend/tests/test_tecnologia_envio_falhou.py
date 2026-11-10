"""Envio falhou fica registrado na Demanda, com "Reenviar" (issue #1535, PRD #1529, ADR 0083, decisão 7).

O "Criar o card" que não chega ao GitHub grava na Demanda o estado "Envio
falhou" e o motivo. A lista mostra o selo para o autor e para o Desenvolvedor;
os dois têm "Reenviar", que passa pela mesma porta do "Criar o card". O motivo
técnico só sai para o Desenvolvedor, que ganha o filtro "Envio falhou". O cron
de reconciliação nunca reenvia.

Tudo pela ROTA, com o modelo e o GitHub dublados no molde de `test_tecnologia_chat`.
"""

from __future__ import annotations

import os
import sys

import httpx
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from test_tecnologia_chat import (  # noqa: E402
    CHAT,
    _ate_o_resumo,
    _cenario,
    _conversas,
    _demandas,
    _integracao_configurada,  # noqa: F401
    _llm_em_mock,  # noqa: F401
    _reset_rate_limiter,  # noqa: F401
)
from test_tecnologia_vinculo import DIRETOR, PEDRO, _montar  # noqa: E402

from app.services import github_client  # noqa: E402
from app.services.tecnologia_vinculo import MOTIVO_GITHUB_INDISPONIVEL  # noqa: E402

CRIAR_O_CARD_DE_VERDADE = github_client.criar_issue


def _falha_no_github(gh) -> None:
    gh.erro_ao_criar = github_client.GithubIndisponivelError("GitHub respondeu 502")


def _demanda_com_envio_falhou(monkeypatch):
    """O diretor chega ao resumo, clica em Criar o card e o GitHub falha."""
    client, sb, gh = _cenario(monkeypatch, participantes=[PEDRO, DIRETOR])
    demanda_id = _ate_o_resumo(client, monkeypatch)
    _falha_no_github(gh)
    assert client.post(f"{CHAT}/{demanda_id}/criar-card").status_code == 502
    gh.erro_ao_criar = None
    return client, sb, gh, demanda_id


def _como(logado: dict, sb, gh, monkeypatch):
    client, _, _ = _montar(logado=logado, supabase=sb, github=gh, monkeypatch=monkeypatch)
    return client


# ═══════════════════════════════════════════════════════════════════════════
# 1. A falha fica registrada
# ═══════════════════════════════════════════════════════════════════════════


class TestAFalhaFicaRegistrada:
    def test_falha_do_github_grava_envio_falhou_e_o_motivo_na_demanda(self, monkeypatch):
        client, sb, gh = _cenario(monkeypatch)
        demanda_id = _ate_o_resumo(client, monkeypatch)
        _falha_no_github(gh)

        resposta = client.post(f"{CHAT}/{demanda_id}/criar-card")

        assert resposta.status_code == 502
        assert resposta.json()["detail"] == MOTIVO_GITHUB_INDISPONIVEL
        demanda = _demandas(sb)[0]
        assert demanda["envio_estado"] == "falhou"
        assert demanda["envio_motivo"] == "GitHub respondeu 502"
        assert demanda.get("github_issue_numero") is None
        assert _conversas(sb)[0]["estado"] == "resumido"

    def test_timeout_de_rede_dentro_da_chamada_tambem_grava_envio_falhou(self, monkeypatch):
        """A falha nasce DENTRO do cliente do GitHub, no `httpx`, e não num
        dublê do cliente: é o caminho do timeout de verdade."""
        client, sb, _ = _cenario(monkeypatch)
        demanda_id = _ate_o_resumo(client, monkeypatch)
        monkeypatch.setattr(github_client, "criar_issue", CRIAR_O_CARD_DE_VERDADE)

        def _timeout(*_a, **_kw):
            raise httpx.ReadTimeout("o GitHub não respondeu em 10 s")

        monkeypatch.setattr(github_client.httpx, "request", _timeout)

        assert client.post(f"{CHAT}/{demanda_id}/criar-card").status_code == 502

        demanda = _demandas(sb)[0]
        assert demanda["envio_estado"] == "falhou"
        assert "o GitHub não respondeu em 10 s" in demanda["envio_motivo"]


# ═══════════════════════════════════════════════════════════════════════════
# 2. A lista
# ═══════════════════════════════════════════════════════════════════════════


def _linha(lista: list[dict], demanda_id: str) -> dict:
    return next(d for d in lista if d["id"] == demanda_id)


class TestALista:
    def test_o_autor_ve_o_selo_envio_falhou_na_lista(self, monkeypatch):
        client, _, _, demanda_id = _demanda_com_envio_falhou(monkeypatch)

        assert _linha(client.get(CHAT).json(), demanda_id)["envio_falhou"] is True

    def test_o_desenvolvedor_ve_o_selo_envio_falhou_na_lista_de_todas(self, monkeypatch):
        _, sb, gh, demanda_id = _demanda_com_envio_falhou(monkeypatch)
        pedro = _como(PEDRO, sb, gh, monkeypatch)

        assert _linha(pedro.get(f"{CHAT}?filtro=todas").json(), demanda_id)["envio_falhou"] is True

    def test_a_demanda_que_criou_o_card_nao_tem_o_selo(self, monkeypatch):
        client, _, _ = _cenario(monkeypatch)
        demanda_id = _ate_o_resumo(client, monkeypatch)
        assert client.post(f"{CHAT}/{demanda_id}/criar-card").status_code == 200

        assert _linha(client.get(CHAT).json(), demanda_id)["envio_falhou"] is False

    def test_o_desenvolvedor_ve_o_motivo_e_o_diretor_nao(self, monkeypatch):
        diretor, sb, gh, demanda_id = _demanda_com_envio_falhou(monkeypatch)
        pedro = _como(PEDRO, sb, gh, monkeypatch)

        assert _linha(pedro.get(f"{CHAT}?filtro=todas").json(), demanda_id)["envio_motivo"] == "GitHub respondeu 502"
        assert _linha(diretor.get(CHAT).json(), demanda_id)["envio_motivo"] is None

    def test_o_filtro_envio_falhou_lista_so_as_demandas_nesse_estado(self, monkeypatch):
        diretor, sb, gh, falhou_id = _demanda_com_envio_falhou(monkeypatch)
        criada_id = _ate_o_resumo(diretor, monkeypatch)
        assert diretor.post(f"{CHAT}/{criada_id}/criar-card").status_code == 200
        conversa_id = _ate_o_resumo(diretor, monkeypatch)
        pedro = _como(PEDRO, sb, gh, monkeypatch)

        resposta = pedro.get(f"{CHAT}?filtro=envio_falhou")

        assert resposta.status_code == 200, resposta.text
        assert [d["id"] for d in resposta.json()] == [falhou_id]
        assert {falhou_id, criada_id, conversa_id} <= {d["id"] for d in pedro.get(f"{CHAT}?filtro=todas").json()}
