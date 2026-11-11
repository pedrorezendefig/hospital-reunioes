"""O documento vivo do planejamento (issue #1553, PRD #1548, ADR 0084, decisão 7).

No Planejamento da Demanda, cada turno do agente devolve também o rascunho do
documento do card (a frase e os tópicos), guardado em
`tecnologia_planejamentos.documento` e mostrado ao lado do chat. O card criado
sai com o bloco "Para o diretor" no formato fixo: uma frase de "O que muda" e
no máximo cinco tópicos. O bug segue o Roteiro do bug, sem documento vivo.

Tudo pela ROTA, com o modelo e o GitHub dublados no molde de
`test_tecnologia_chat_melhoria`.
"""

from __future__ import annotations

import os
import re
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
from test_tecnologia_chat_melhoria import CHAT, _abrir_pelo_botao, _ate_o_resumo  # noqa: E402

SETE_TOPICOS = [f"Tópico {n} do pedido." for n in range(1, 8)]


class TestCadaTurnoGravaORascunho:
    def test_o_turno_da_melhoria_grava_o_documento_e_a_tela_o_recebe(self, monkeypatch):
        client, sb, _ = _cenario(monkeypatch)
        demanda_id = _abrir_pelo_botao(client, monkeypatch)["demanda_id"]
        _ia(
            monkeypatch,
            _pergunta(
                contexto="E quem confirma o retorno?",
                documento={
                    "frase": "A recepção marca o retorno do paciente na saída.",
                    "topicos": ["Só a recepção usa a agenda.", "O médico vê o retorno marcado."],
                },
            ),
        )

        resposta = client.post(f"{CHAT}/{demanda_id}", json={"opcao": "A"})

        assert resposta.status_code == 200, resposta.text
        esperado = {
            "frase": "A recepção marca o retorno do paciente na saída.",
            "topicos": ["Só a recepção usa a agenda.", "O médico vê o retorno marcado."],
        }
        assert _conversas(sb)[0]["documento"] == esperado
        assert resposta.json()["documento"] == esperado
        assert client.get(f"{CHAT}/{demanda_id}").json()["documento"] == esperado

    def test_o_turno_sem_rascunho_deixa_o_documento_de_antes(self, monkeypatch):
        client, sb, _ = _cenario(monkeypatch)
        demanda_id = _abrir_pelo_botao(client, monkeypatch)["demanda_id"]
        _ia(monkeypatch, _pergunta(documento={"frase": "A recepção marca o retorno.", "topicos": []}))
        client.post(f"{CHAT}/{demanda_id}", json={"opcao": "A"})
        _ia(monkeypatch, _pergunta(contexto="E quem confirma?"))

        resposta = client.post(f"{CHAT}/{demanda_id}", json={"opcao": "B"})

        assert resposta.json()["documento"] == {"frase": "A recepção marca o retorno.", "topicos": []}

    def test_o_rascunho_guarda_no_maximo_cinco_topicos_numa_linha_cada(self, monkeypatch):
        client, sb, _ = _cenario(monkeypatch)
        demanda_id = _abrir_pelo_botao(client, monkeypatch)["demanda_id"]
        _ia(
            monkeypatch,
            _pergunta(documento={"frase": "A recepção\nmarca o retorno.", "topicos": ["Linha\num.", *SETE_TOPICOS]}),
        )

        client.post(f"{CHAT}/{demanda_id}", json={"opcao": "A"})

        assert _conversas(sb)[0]["documento"] == {
            "frase": "A recepção marca o retorno.",
            "topicos": ["Linha um.", *SETE_TOPICOS[:4]],
        }
