"""O modelo e o custo da conversa no cabeçalho do chat (issue #1439, PRD #1436).

ADR 0079, decisão 6, que emenda a decisão 9 da ADR 0077: a resposta do chat,
ao abrir a conversa e em cada turno, traz o modelo da chamada mais recente (no
nome de exibição) e a soma em dólar das chamadas de IA gravadas daquela
Demanda. Uma chamada com tokens e custo zero é o preço ausente que o código já
grava: a soma vira nula, e a tela diz "custo não medido". Tudo pela ROTA, com o
modelo dublado no molde de `test_tecnologia_chat`.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from test_planejamento_demanda import _ia, _uso  # noqa: E402
from test_tecnologia_chat import CHAT, _cenario, _chamadas, _comecar, _turno  # noqa: E402

from app.config import settings  # noqa: E402
from app.limiter import limiter  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


@pytest.fixture(autouse=True)
def _integracao_configurada(monkeypatch):
    monkeypatch.setattr(settings, "github_integracao_token", "token-de-teste")
    monkeypatch.setattr(settings, "github_integracao_repo", "pedrorezendefig/hospital-reunioes")


def _chamada(demanda_id: str | None, *, custo: float, modelo: str = "claude-opus-5-5", criado_em: str, **kw) -> dict:
    return {
        "demanda_id": demanda_id,
        "passo": "pergunta",
        "modelo": modelo,
        "tokens_entrada": kw.get("entrada", 1000),
        "tokens_saida": kw.get("saida", 200),
        "tokens_cache": 0,
        "custo_usd": custo,
        "duracao_ms": 900,
        "sucesso": True,
        "criado_em": criado_em,
    }


def _conversa_com(monkeypatch, *chamadas_de) -> tuple:
    """Uma conversa guardada cujas chamadas gravadas são só as dadas."""
    client, sb, _ = _cenario(monkeypatch)
    demanda_id = _comecar(client, monkeypatch)
    _chamadas(sb).clear()
    _chamadas(sb).extend(c(demanda_id) for c in chamadas_de)
    return client, sb, demanda_id


class TestCustoAoAbrirAConversa:
    def test_duas_chamadas_com_preco_somam_o_custo_exato(self, monkeypatch):
        client, _, demanda_id = _conversa_com(
            monkeypatch,
            lambda d: _chamada(d, custo=1.234567, criado_em="2026-11-06T10:00:00Z"),
            lambda d: _chamada(d, custo=0.605433, criado_em="2026-11-06T10:05:00Z"),
        )

        custo = client.get(f"{CHAT}/{demanda_id}").json()["custo"]

        assert custo["custo_usd"] == 1.84
