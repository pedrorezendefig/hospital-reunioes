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
from test_tecnologia_vinculo import DIRETOR, PEDRO, _montar, _pessoa  # noqa: E402
from test_tecnologia_webhook_github import _SupabaseMock as _SupabaseDoCron  # noqa: E402

from app.routers.admin.tecnologia import MOTIVO_CHAT_TERMINOU  # noqa: E402
from app.services import github_client, tecnologia_sincronizacao  # noqa: E402
from app.services.conhecimento import CONHECIMENTO_DIR  # noqa: E402
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
    if all(p["id"] != logado["id"] for p in sb.tabelas["participantes"]):
        sb.tabelas["participantes"].append(dict(logado))
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

        resposta = pedro.get(f"{CHAT}?filtro=todas&envio_falhou=true")

        assert resposta.status_code == 200, resposta.text
        assert [d["id"] for d in resposta.json()] == [falhou_id]
        assert {falhou_id, criada_id, conversa_id} <= {d["id"] for d in pedro.get(f"{CHAT}?filtro=todas").json()}


# ═══════════════════════════════════════════════════════════════════════════
# 3. Reenviar
# ═══════════════════════════════════════════════════════════════════════════


def _reenviar(client, demanda_id: str):
    return client.post(f"{CHAT}/{demanda_id}/reenviar")


class TestReenviar:
    @pytest.mark.parametrize("quem", ["diretor", "desenvolvedor"])
    def test_reenviar_cria_a_issue_e_limpa_o_estado(self, monkeypatch, quem):
        diretor, sb, gh, demanda_id = _demanda_com_envio_falhou(monkeypatch)
        client = diretor if quem == "diretor" else _como(PEDRO, sb, gh, monkeypatch)

        resposta = _reenviar(client, demanda_id)

        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["estado"] == "enviado"
        assert len(gh.criadas) == 1
        demanda = _demandas(sb)[0]
        assert demanda["github_issue_numero"] == 900
        assert demanda["envio_estado"] is None
        assert demanda["envio_motivo"] is None
        assert _linha(diretor.get(CHAT).json(), demanda_id)["envio_falhou"] is False

    def test_reenviar_mantem_o_responsavel_escolhido_no_criar_o_card(self, monkeypatch):
        lucas = _pessoa("P5", "Lucas Sampaio", github_login="lucas")
        client, sb, gh = _cenario(monkeypatch, participantes=[PEDRO, DIRETOR, lucas])
        demanda_id = _ate_o_resumo(client, monkeypatch)
        _falha_no_github(gh)
        assert client.post(f"{CHAT}/{demanda_id}/criar-card", json={"responsavel_id": "P5"}).status_code == 502
        gh.erro_ao_criar = None

        assert _reenviar(client, demanda_id).status_code == 200

        assert gh.criadas[0]["assignees"] == ["lucas"]
        assert _demandas(sb)[0]["responsavel_id"] == "P5"

    def test_reenviar_que_falha_de_novo_continua_em_envio_falhou(self, monkeypatch):
        client, sb, gh, demanda_id = _demanda_com_envio_falhou(monkeypatch)
        gh.erro_ao_criar = github_client.GithubIndisponivelError("GitHub respondeu 503")

        assert _reenviar(client, demanda_id).status_code == 502

        assert _demandas(sb)[0]["envio_estado"] == "falhou"
        assert _demandas(sb)[0]["envio_motivo"] == "GitHub respondeu 503"

    def test_reenviar_demanda_que_ja_tem_issue_vinculada_nao_cria_a_segunda(self, monkeypatch):
        client, sb, gh, demanda_id = _demanda_com_envio_falhou(monkeypatch)
        # A issue foi vinculada por outro caminho depois da falha.
        _demandas(sb)[0]["github_issue_numero"] = 777

        resposta = _reenviar(client, demanda_id)

        assert resposta.status_code == 409
        assert resposta.json()["detail"] == MOTIVO_CHAT_TERMINOU
        assert gh.criadas == []
        assert _demandas(sb)[0]["github_issue_numero"] == 777

    def test_reenviar_demanda_sem_envio_falhou_nao_cria_issue(self, monkeypatch):
        """Reenviar e para o envio que falhou; o primeiro envio e o Criar o card."""
        client, _, gh = _cenario(monkeypatch)
        demanda_id = _ate_o_resumo(client, monkeypatch)

        assert _reenviar(client, demanda_id).status_code == 409
        assert gh.criadas == []

    def test_quem_nao_ve_a_demanda_nao_reenvia(self, monkeypatch):
        _, sb, gh, demanda_id = _demanda_com_envio_falhou(monkeypatch)
        outro_diretor = _pessoa("P3", "Outro Diretor")

        resposta = _reenviar(_como(outro_diretor, sb, gh, monkeypatch), demanda_id)

        assert resposta.status_code == 404
        assert gh.criadas == []


# ═══════════════════════════════════════════════════════════════════════════
# 4. O cron não reenvia
# ═══════════════════════════════════════════════════════════════════════════


class TestOCronNaoReenvia:
    def test_a_reconciliacao_de_hora_em_hora_nao_reenvia_a_demanda_com_envio_falhou(self, monkeypatch):
        """O cron le pelo dublê do webhook, que conhece o `.not_` da consulta
        dele; o `criar_issue` segue dublado pelo cenário, e é ele que conta."""
        _, sb, gh, _ = _demanda_com_envio_falhou(monkeypatch)
        banco_do_cron = _SupabaseDoCron({"tecnologia_demandas": _demandas(sb)})

        lidas = tecnologia_sincronizacao.reconciliar_vinculos(banco_do_cron)

        assert lidas == {"lidas": 0, "mudadas": 0, "falhas": 0}
        assert gh.criadas == []
        assert _demandas(sb)[0]["envio_estado"] == "falhou"
        assert _demandas(sb)[0].get("github_issue_numero") is None


# ═══════════════════════════════════════════════════════════════════════════
# 5. O Kit
# ═══════════════════════════════════════════════════════════════════════════


def _secao(titulo: str) -> str:
    texto = (CONHECIMENTO_DIR / "tecnologia.md").read_text(encoding="utf-8")
    return texto.split(f"## {titulo}", 1)[1].split("\n## ", 1)[0]


class TestKit:
    def test_o_kit_diz_ao_diretor_que_o_envio_falhado_fica_na_lista_com_reenviar(self):
        """O Kit é a língua do Assistente: sem isto, ele diria ao diretor que o
        card que falhou se perdeu e que é preciso refazer a conversa."""
        secao = _secao("A conversa com o Assistente")
        for trecho in ("Envio falhou", "Reenviar", "não precisa refazer", "não reenvia sozinho"):
            assert trecho in secao, trecho

    def test_o_kit_diz_que_o_desenvolvedor_ve_o_motivo_e_tem_o_filtro(self):
        secao = _secao("Quem vê")
        for trecho in ("**Envio falhou**", "o motivo da falha"):
            assert trecho in secao, trecho
