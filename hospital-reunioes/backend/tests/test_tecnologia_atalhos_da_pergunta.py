"""Os atalhos "Não sei agora, siga" e "Explica melhor" na pergunta (issue #1595, PRD #1591).

Cada atalho é uma fala fixa do diretor, que vai pelo mesmo caminho do texto
livre. O prompt diz o que fazer com cada uma, e nenhuma das duas fecha
decisão: nem no turno, nem no resumo.

Tudo pela ROTA, com o modelo dublado no molde de
`test_tecnologia_pergunta_em_cartao`.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from test_planejamento_demanda import _ia, _pergunta  # noqa: E402
from test_tecnologia_chat import (  # noqa: E402
    _cenario,
    _conversas,
    _integracao_configurada,  # noqa: F401
    _llm_em_mock,  # noqa: F401
    _reset_rate_limiter,  # noqa: F401
)
from test_tecnologia_chat_melhoria import CHAT, _abrir_pelo_botao, _resumo_do_modelo  # noqa: E402

from app.services.conhecimento import CONHECIMENTO_DIR  # noqa: E402
from app.services.prompt_loader import load_prompt  # noqa: E402

NAO_SEI = "Não sei agora, siga"
EXPLICA = "Explica melhor"
ATALHOS = pytest.mark.parametrize("atalho", [NAO_SEI, EXPLICA], ids=["nao-sei", "explica"])


def _clicar_no_atalho(client, monkeypatch, atalho: str, **do_modelo):
    """Abre a melhoria na primeira pergunta e manda o atalho como o botão manda."""
    demanda_id = _abrir_pelo_botao(client, monkeypatch)["demanda_id"]
    cliente = _ia(monkeypatch, _pergunta(contexto="E quem confirma o retorno?", **do_modelo))
    resposta = client.post(f"{CHAT}/{demanda_id}", json={"texto": atalho, "prints": []})
    assert resposta.status_code == 200, resposta.text
    return demanda_id, cliente, resposta.json()


class TestOAtalhoChegaComoRespostaDoDiretor:
    @ATALHOS
    def test_o_atalho_chega_ao_modelo_como_resposta_do_diretor(self, monkeypatch, atalho):
        client, sb, _ = _cenario(monkeypatch)

        _, cliente, corpo = _clicar_no_atalho(client, monkeypatch, atalho)

        pedido = cliente.chamadas[0]["messages"][0]["content"]
        assert pedido.endswith(f"(recomendada: A)\nDiretor: {atalho}")
        guardada = _conversas(sb)[0]["mensagens"][-2]
        assert (guardada["tipo"], guardada["opcao"], guardada["texto"]) == ("resposta", None, atalho)
        assert corpo["mensagens"][-2]["autor"] == "diretor"
        assert corpo["mensagens"][-2]["texto"] == atalho


class TestOAtalhoNaoFechaDecisao:
    @ATALHOS
    def test_depois_do_atalho_a_decisao_do_turno_fica_nula(self, monkeypatch, atalho):
        """Mesmo que o modelo escreva uma decisão, a fala fixa não decidiu nada."""
        client, sb, _ = _cenario(monkeypatch)

        _clicar_no_atalho(client, monkeypatch, atalho, decisao_fechada="Só a recepção usa.")

        assert _conversas(sb)[0]["decisoes"] == []

    def test_a_resposta_de_verdade_continua_fechando_a_decisao(self, monkeypatch):
        """O detector não é cego: a mesma rota com texto livre de verdade guarda a decisão."""
        client, sb, _ = _cenario(monkeypatch)

        _clicar_no_atalho(client, monkeypatch, "Só a recepção.", decisao_fechada="Só a recepção usa.")

        assert _conversas(sb)[0]["decisoes"] == ["Só a recepção usa."]

    @ATALHOS
    def test_o_resumo_nao_lista_decisao_para_a_pergunta_do_atalho(self, monkeypatch, atalho):
        client, _, _ = _cenario(monkeypatch)
        demanda_id, _, _ = _clicar_no_atalho(client, monkeypatch, atalho)
        client.post(f"{CHAT}/{demanda_id}", json={"opcao": "B"})
        _ia(
            monkeypatch,
            _resumo_do_modelo(
                decisoes=[
                    {"pergunta": 1, "porque": "Inventada sobre o atalho."},
                    {"pergunta": 2, "porque": "O diretor escolheu."},
                ]
            ),
        )

        resposta = client.post(f"{CHAT}/{demanda_id}/resumo")

        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["resumo_da_melhoria"]["decisoes"] == [
            {
                "pergunta": "E quem confirma o retorno?",
                "escolha": "A recepção e a enfermagem.",
                "porque": "O diretor escolheu.",
            }
        ]


class TestOPromptTemARegraDeCadaAtalho:
    def test_o_prompt_diz_o_que_fazer_com_cada_atalho(self):
        prompt = load_prompt("planejamento_demanda_system")

        secao = prompt.split("## Os atalhos do diretor", 1)[1].split("\n## ", 1)[0]
        nao_sei = next(linha for linha in secao.splitlines() if f'"{NAO_SEI}"' in linha)
        explica = next(linha for linha in secao.splitlines() if f'"{EXPLICA}"' in linha)
        assert "próxima lacuna" in nao_sei
        assert "mesma pergunta com outras palavras" in explica
        for linha in (nao_sei, explica):
            assert "`decisao_fechada` é `null`" in linha


class TestOKitDizOsAtalhos:
    def test_o_texto_da_tecnologia_no_kit_diz_os_dois_atalhos(self):
        texto = (CONHECIMENTO_DIR / "tecnologia.md").read_text(encoding="utf-8")

        for titulo in ("## A conversa com o Assistente", "## O Planejamento da Demanda"):
            secao = texto.split(titulo, 1)[1].split("\n## ", 1)[0]
            for trecho in (f"**{NAO_SEI}**", f"**{EXPLICA}**", "não conta como decisão"):
                assert trecho in secao, (titulo, trecho)
