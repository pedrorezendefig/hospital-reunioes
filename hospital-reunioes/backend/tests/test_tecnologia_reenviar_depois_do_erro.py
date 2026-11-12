"""Reenviar depois do aviso de erro destrava a conversa (issue #1582).

O caso do diretor: a melhoria passa ao planejamento, a tela pede a primeira
pergunta e a IA falha (502, "Tente de novo em instantes"). A conversa fica
guardada sem pergunta no fim. Ele escreve de novo no campo e manda: a fala
tem que chegar ao modelo e a pergunta tem que voltar, com tudo o que ele ja
tinha contado. Antes, a rota recusava o texto ("Ainda não há pergunta para
responder") a cada reenvio, e a conversa nao saia do lugar.

Nada aqui tenta de novo sozinho (ADR 0082): cada chamada ao modelo e um envio
da pessoa.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from test_planejamento_demanda import _ia, _pergunta  # noqa: E402
from test_tecnologia_chat import (  # noqa: E402
    _cenario,
    _conversas,
    _integracao_configurada,  # noqa: F401
    _llm_em_mock,  # noqa: F401
    _reset_rate_limiter,  # noqa: F401
    _turno,
)
from test_tecnologia_vinculo import BASE  # noqa: E402

CHAT = f"{BASE}/chat"

CONTOU = "Quero que o substituto responda a manifestação no lugar do titular"
REENVIO = "Quando o titular está de férias, o substituto responde"


def _primeira_pergunta_falhou(client, monkeypatch) -> str:
    """A melhoria contada em texto passa ao planejamento, e a primeira
    pergunta falha no provedor: o aviso vermelho que o diretor viu."""
    _ia(monkeypatch, _turno(classificacao="melhoria", confirmada=False, opcoes=["Sim", "Não"]))
    demanda_id = client.post(CHAT, json={"texto": CONTOU}).json()["demanda_id"]
    _ia(monkeypatch, _turno(classificacao="melhoria", confirmada=True, pronto=True, titulo="Substituto na Ouvidoria"))
    assert client.post(f"{CHAT}/{demanda_id}", json={"texto": "Sim"}).json()["planejamento"] is True
    _ia(monkeypatch, RuntimeError("provedor fora do ar"))
    assert client.post(f"{CHAT}/{demanda_id}", json={}).status_code == 502
    return demanda_id


class TestReenviarDepoisDoErro:
    def test_reenviar_o_texto_depois_do_aviso_de_erro_faz_o_assistente_responder(self, monkeypatch):
        client, _, _ = _cenario(monkeypatch)
        demanda_id = _primeira_pergunta_falhou(client, monkeypatch)
        _ia(monkeypatch, _pergunta(contexto="O substituto responde só nas férias do titular?"))

        resposta = client.post(f"{CHAT}/{demanda_id}", json={"texto": REENVIO})

        assert resposta.status_code == 200, resposta.text
        falas = resposta.json()["mensagens"]
        assert [(f["autor"], f["texto"]) for f in falas[-2:]] == [
            ("diretor", REENVIO),
            ("ia", "O substituto responde só nas férias do titular?"),
        ]

    def test_a_conversa_segue_de_onde_parou_com_o_que_o_diretor_ja_contou(self, monkeypatch):
        client, sb, _ = _cenario(monkeypatch)
        demanda_id = _primeira_pergunta_falhou(client, monkeypatch)
        antes = [dict(m) for m in _conversas(sb)[0]["mensagens"]]
        cliente = _ia(monkeypatch, _pergunta(contexto="O substituto responde só nas férias do titular?"))

        client.post(f"{CHAT}/{demanda_id}", json={"texto": REENVIO})

        # A conversa guardada so cresceu: o que havia continua igual, na mesma ordem.
        assert _conversas(sb)[0]["mensagens"][: len(antes)] == antes
        # E o modelo leu o que o diretor contou antes do erro e o que reenviou.
        pedido = cliente.chamadas[0]["messages"][0]["content"]
        assert CONTOU in pedido
        assert f"Diretor: {REENVIO}" in pedido
