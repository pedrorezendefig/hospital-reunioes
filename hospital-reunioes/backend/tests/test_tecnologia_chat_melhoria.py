"""O caminho da melhoria dentro do chat (issue #1383, PRD #1380, ADR 0077, decisão 4).

Escolhida a melhoria, o chat segue o Planejamento da Demanda: uma pergunta por
vez, contexto curto, duas opções com a recomendada marcada, campo livre, teto de
12 perguntas e "Fechar e resumir" a qualquer altura. O resumo traz o que ficou
em aberto, e "Criar o card" cria o PRD do diretor. Tudo pela ROTA, com o modelo
e o GitHub dublados no molde de `test_tecnologia_chat`.
"""

from __future__ import annotations

import json
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from test_planejamento_demanda import _encerrou, _ia, _pergunta  # noqa: E402
from test_tecnologia_chat import (  # noqa: E402
    _reset_rate_limiter,  # noqa: F401
    _cenario,
    _chamadas,
    _conversas,
    _demandas,
    _integracao_configurada,  # noqa: F401
    _llm_em_mock,  # noqa: F401
    _turno,
)
from test_tecnologia_vinculo import BASE  # noqa: E402

from app.services.tecnologia_vinculo import bloco_para_o_diretor  # noqa: E402

CHAT = f"{BASE}/chat"


def _abrir_pelo_botao(client, monkeypatch, **campos) -> dict:
    _ia(monkeypatch, _pergunta(**campos))
    resposta = client.post(CHAT, json={"escolha": "melhoria"})
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


# ═══════════════════════════════════════════════════════════════════════════
# 1. Escolher "melhoria" abre o grill
# ═══════════════════════════════════════════════════════════════════════════


class TestEscolherMelhoriaAbreOGrill:
    def test_o_botao_melhoria_abre_a_primeira_pergunta_com_duas_opcoes_e_a_recomendada(self, monkeypatch):
        client, sb, _ = _cenario(monkeypatch)

        corpo = _abrir_pelo_botao(
            client,
            monkeypatch,
            contexto="Preciso entender o problema. Ele acontece na recepção?",
            opcao_a="Sim, na recepção.",
            opcao_b="Não, na enfermagem.",
            recomendada="B",
        )

        [demanda] = _demandas(sb)
        assert demanda["tipo"] == "novo"
        assert corpo["planejamento"] is True
        assert corpo["estado"] == "em_andamento"
        ultima = corpo["mensagens"][-1]
        assert ultima["autor"] == "ia"
        assert ultima["texto"] == "Preciso entender o problema. Ele acontece na recepção?"
        assert ultima["opcoes"] == ["Sim, na recepção.", "Não, na enfermagem."]
        assert ultima["recomendada"] == "B"
        # A conversa fica guardada na Demanda, como a do bug.
        [conversa] = _conversas(sb)
        assert conversa["mensagens"][-1]["tipo"] == "pergunta"

    def test_o_custo_da_primeira_pergunta_fica_na_demanda_que_nasceu(self, monkeypatch):
        client, sb, _ = _cenario(monkeypatch)

        _abrir_pelo_botao(client, monkeypatch)

        [chamada] = _chamadas(sb)
        assert chamada["demanda_id"] == _demandas(sb)[0]["id"]
