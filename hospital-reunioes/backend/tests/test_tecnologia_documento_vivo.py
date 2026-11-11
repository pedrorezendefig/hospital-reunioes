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
    _demandas,
    _integracao_configurada,  # noqa: F401
    _llm_em_mock,  # noqa: F401
    _reset_rate_limiter,  # noqa: F401
    _turno,
)
from test_tecnologia_chat_melhoria import (  # noqa: E402
    CHAT,
    _abrir_pelo_botao,
    _ate_o_resumo,
    _pergunta_guardada,
    _resumo_do_modelo,
)

from app.services.tecnologia_vinculo import bloco_para_o_diretor  # noqa: E402

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


def _linhas_do_bloco(corpo: str) -> list[str]:
    return [linha for linha in (bloco_para_o_diretor(corpo) or "").splitlines() if linha.strip()]


class TestOCardSaiNoFormatoFixo:
    def test_o_card_leva_a_frase_e_os_topicos_do_documento(self, monkeypatch):
        client, sb, gh = _cenario(monkeypatch)
        demanda_id = _ate_o_resumo(client, sb, monkeypatch)
        _conversas(sb)[0]["documento"] = {
            "frase": "A recepção marca o retorno do paciente na saída.",
            "topicos": ["Só a recepção usa a agenda.", "O médico vê o retorno marcado."],
        }

        assert client.post(f"{CHAT}/{demanda_id}/criar-card").status_code == 200

        assert _linhas_do_bloco(gh.criadas[0]["corpo"]) == [
            "**O que muda:** A recepção marca o retorno do paciente na saída.",
            "**O que você precisa saber:**",
            "- Só a recepção usa a agenda.",
            "- O médico vê o retorno marcado.",
        ]

    def test_o_documento_com_sete_topicos_sai_com_cinco(self, monkeypatch):
        client, sb, gh = _cenario(monkeypatch)
        demanda_id = _ate_o_resumo(client, sb, monkeypatch)
        _conversas(sb)[0]["documento"] = {"frase": "A recepção marca o retorno.", "topicos": SETE_TOPICOS}

        client.post(f"{CHAT}/{demanda_id}/criar-card")

        linhas = _linhas_do_bloco(gh.criadas[0]["corpo"])
        assert [linha for linha in linhas if linha.startswith("- ")] == [f"- {t}" for t in SETE_TOPICOS[:5]]

    def test_sem_documento_o_bloco_sai_com_a_frase_do_resumo_e_ate_cinco_topicos(self, monkeypatch):
        """A conversa de antes desta fatia não tem rascunho: o bloco sai no
        formato fixo mesmo assim, com a frase do resumo no lugar da descrição
        inteira e só cinco das decisões."""
        client, sb, gh = _cenario(monkeypatch)
        demanda_id = _abrir_pelo_botao(client, monkeypatch)["demanda_id"]
        [conversa] = _conversas(sb)
        planejamento: list[dict] = []
        for n in range(1, 8):
            planejamento += [_pergunta_guardada(n), {"tipo": "resposta", "opcao": "A", "texto": f"A{n}"}]
        conversa["mensagens"] = [*conversa["mensagens"][:2], *planejamento]
        _ia(
            monkeypatch,
            _resumo_do_modelo(
                frase="A recepção passa a marcar o retorno na saída.",
                decisoes=[{"pergunta": n, "porque": "Pelo pedido."} for n in range(1, 8)],
            ),
        )
        assert client.post(f"{CHAT}/{demanda_id}/resumo").status_code == 200
        _demandas(sb)[0]["descricao"] = "Primeira frase longa do pedido. Segunda frase.\n\nTerceira."

        client.post(f"{CHAT}/{demanda_id}/criar-card")

        linhas = _linhas_do_bloco(gh.criadas[0]["corpo"])
        assert linhas[0] == "**O que muda:** A recepção passa a marcar o retorno na saída."
        assert len([linha for linha in linhas if linha.startswith("- ")]) == 5
