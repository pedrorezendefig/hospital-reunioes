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

    def test_a_resposta_pela_opcao_entra_com_o_texto_da_opcao_e_vem_a_proxima_pergunta(self, monkeypatch):
        client, sb, _ = _cenario(monkeypatch)
        demanda_id = _abrir_pelo_botao(client, monkeypatch)["demanda_id"]
        _ia(monkeypatch, _pergunta(contexto="E quem confirma o retorno?", decisao_fechada="Só a recepção usa."))

        resposta = client.post(f"{CHAT}/{demanda_id}", json={"opcao": "A"})

        assert resposta.status_code == 200, resposta.text
        falas = resposta.json()["mensagens"]
        assert [f["texto"] for f in falas[-2:]] == ["Só a recepção.", "E quem confirma o retorno?"]
        assert falas[-2]["autor"] == "diretor"
        assert _conversas(sb)[0]["decisoes"] == ["Só a recepção usa."]

    def test_o_campo_livre_responde_a_pergunta(self, monkeypatch):
        client, sb, _ = _cenario(monkeypatch)
        demanda_id = _abrir_pelo_botao(client, monkeypatch)["demanda_id"]
        _ia(monkeypatch, _pergunta(contexto="E quem confirma o retorno?"))

        resposta = client.post(f"{CHAT}/{demanda_id}", json={"texto": "A recepção e o médico"})

        assert resposta.status_code == 200, resposta.text
        assert _conversas(sb)[0]["mensagens"][-2] == {
            "tipo": "resposta",
            "opcao": None,
            "texto": "A recepção e o médico",
        }

    def test_a_melhoria_contada_em_texto_ganha_a_primeira_pergunta_no_turno_seguinte(self, monkeypatch):
        """Confirmada a melhoria contada em texto livre, a tela pede o turno
        seguinte sem nada, e ele traz a primeira pergunta do planejamento, que
        parte do que o diretor já contou."""
        client, _, _ = _cenario(monkeypatch)
        _ia(monkeypatch, _turno(classificacao="melhoria", confirmada=False, opcoes=["Sim", "Não"]))
        demanda_id = client.post(CHAT, json={"texto": "Queria um aviso quando a ata sair"}).json()["demanda_id"]
        _ia(monkeypatch, _turno(classificacao="melhoria", confirmada=True, pronto=True, titulo="Aviso da ata"))
        assert client.post(f"{CHAT}/{demanda_id}", json={"texto": "Sim"}).json()["planejamento"] is True
        cliente = _ia(monkeypatch, _pergunta(contexto="O aviso vai para quem?"))

        resposta = client.post(f"{CHAT}/{demanda_id}", json={})

        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["mensagens"][-1]["texto"] == "O aviso vai para quem?"
        pedido = cliente.chamadas[0]["messages"][0]["content"]
        assert "Queria um aviso quando a ata sair" in pedido
        assert "Título: Aviso da ata" in pedido


# ═══════════════════════════════════════════════════════════════════════════
# 2. O teto de 12 perguntas e o "Fechar e resumir"
# ═══════════════════════════════════════════════════════════════════════════


def _pergunta_guardada(n: int) -> dict:
    return {
        "tipo": "pergunta",
        "contexto": f"Pergunta {n}?",
        "opcoes": [{"letra": "A", "texto": f"A{n}"}, {"letra": "B", "texto": f"B{n}"}],
        "recomendada": "A",
    }


def _com_perguntas(sb, perguntas: int, *, ultima_respondida: bool = True) -> None:
    """Troca o planejamento guardado por `perguntas` perguntas."""
    [conversa] = _conversas(sb)
    planejamento: list[dict] = []
    for n in range(1, perguntas + 1):
        planejamento.append(_pergunta_guardada(n))
        if n < perguntas or ultima_respondida:
            planejamento.append({"tipo": "resposta", "opcao": "A", "texto": f"A{n}"})
    conversa["mensagens"] = [*conversa["mensagens"][:2], *planejamento]


def _resumo_do_modelo(**campos) -> str:
    base = {
        "titulo": "Agenda de retorno na recepção",
        "decisoes": [{"pergunta": 1, "porque": "A recepção marca o retorno."}],
        "em_aberto": ["Quem confirma o retorno com o paciente."],
        "termos": ["Agenda de retorno: a marcação do retorno feita na saída."],
        "candidatas_a_adr": ["Só a recepção marca o retorno."],
    }
    base.update(campos)
    return json.dumps(base, ensure_ascii=False)


class TestTetoEFecharEResumir:
    def test_o_grill_para_na_decima_segunda_pergunta_mesmo_que_o_modelo_queira_mais(self, monkeypatch):
        client, sb, _ = _cenario(monkeypatch)
        demanda_id = _abrir_pelo_botao(client, monkeypatch)["demanda_id"]
        _com_perguntas(sb, 12, ultima_respondida=False)
        _ia(monkeypatch, _pergunta(contexto="Mais uma pergunta?"))

        resposta = client.post(f"{CHAT}/{demanda_id}", json={"opcao": "B"})

        assert resposta.status_code == 200, resposta.text
        corpo = resposta.json()
        assert corpo["estado"] == "encerrado"
        assert corpo["mensagens"][-1]["opcoes"] == []
        assert "Mais uma pergunta?" not in [f["texto"] for f in corpo["mensagens"]]
        # Encerrado, a conversa espera o resumo: outra resposta é recusada.
        assert client.post(f"{CHAT}/{demanda_id}", json={"texto": "e mais isto"}).status_code == 409

    def test_fechar_e_resumir_encerra_a_qualquer_momento_com_o_resumo(self, monkeypatch):
        client, sb, _ = _cenario(monkeypatch)
        demanda_id = _abrir_pelo_botao(client, monkeypatch)["demanda_id"]
        _com_perguntas(sb, 1)
        _ia(monkeypatch, _resumo_do_modelo())

        resposta = client.post(f"{CHAT}/{demanda_id}/resumo")

        assert resposta.status_code == 200, resposta.text
        corpo = resposta.json()
        assert corpo["estado"] == "resumido"
        assert corpo["resumo"] is None
        assert corpo["resumo_da_melhoria"]["decisoes"] == [
            {"pergunta": "Pergunta 1?", "escolha": "A1", "porque": "A recepção marca o retorno."}
        ]
        # O título provisório dá lugar ao do resumo.
        assert _demandas(sb)[0]["titulo"] == "Agenda de retorno na recepção"

    def test_fechar_e_resumir_e_so_da_melhoria(self, monkeypatch):
        client, _, _ = _cenario(monkeypatch)
        _ia(monkeypatch, _turno())
        demanda_id = client.post(CHAT, json={"escolha": "bug"}).json()["demanda_id"]

        assert client.post(f"{CHAT}/{demanda_id}/resumo").status_code == 409
