"""A pergunta do planejamento em cartão (issue #1592, PRD #1591).

O turno da IA no Planejamento da Demanda devolve, além de contexto, opções e
recomendada, quatro textos opcionais: o título da pergunta, o "na prática" de
cada opção e o porquê da recomendada. A mensagem gravada os leva, a conversa
que o modelo relê e o pedido do resumo os incluem, e a tela os recebe no
`cartao` da fala. Nenhum turno é recusado pela falta deles.

Tudo pela ROTA, com o modelo e o GitHub dublados no molde de
`test_tecnologia_documento_vivo`.
"""

from __future__ import annotations

import json
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

CAMPOS_DO_CARTAO = {
    "titulo_pergunta": "Quem marca o retorno do paciente?",
    "na_pratica_a": "A recepção marca o retorno na saída do paciente.",
    "na_pratica_b": "O médico marca o retorno ainda no consultório.",
    "porque": "A recepção já agenda as consultas do hospital hoje.",
}

CARTAO_NA_TELA = {
    "titulo": "Quem marca o retorno do paciente?",
    "na_pratica_a": "A recepção marca o retorno na saída do paciente.",
    "na_pratica_b": "O médico marca o retorno ainda no consultório.",
    "porque": "A recepção já agenda as consultas do hospital hoje.",
}

# A pergunta como ela era gravada antes desta fatia: sem nenhum campo novo.
PERGUNTA_DE_HOJE = {
    "tipo": "pergunta",
    "contexto": "Preciso saber quem vai usar a tela nova.",
    "opcoes": [
        {"letra": "A", "texto": "Só a recepção."},
        {"letra": "B", "texto": "A recepção e a enfermagem."},
    ],
    "recomendada": "A",
}


class TestOTurnoGravaOsQuatroTextos:
    def test_o_turno_com_titulo_na_pratica_e_porque_grava_os_quatro_textos_na_pergunta(self, monkeypatch):
        client, sb, _ = _cenario(monkeypatch)

        corpo = _abrir_pelo_botao(client, monkeypatch, **CAMPOS_DO_CARTAO)

        pergunta = _conversas(sb)[0]["mensagens"][-1]
        assert pergunta == {**PERGUNTA_DE_HOJE, **CAMPOS_DO_CARTAO}
        assert corpo["mensagens"][-1]["cartao"] == CARTAO_NA_TELA
        assert client.get(f"{CHAT}/{corpo['demanda_id']}").json()["mensagens"][-1]["cartao"] == CARTAO_NA_TELA

    def test_os_textos_do_cartao_saem_numa_linha_e_sem_travessao(self, monkeypatch):
        client, sb, _ = _cenario(monkeypatch)

        _abrir_pelo_botao(
            client,
            monkeypatch,
            titulo_pergunta="Quem marca\no retorno?",
            porque="A recepção \u2014 que já agenda \u2014 marca.",
        )

        pergunta = _conversas(sb)[0]["mensagens"][-1]
        assert pergunta["titulo_pergunta"] == "Quem marca o retorno?"
        assert pergunta["porque"] == "A recepção, que já agenda, marca."


class TestOTurnoSemOsCamposNovos:
    @pytest.mark.parametrize(
        "campos",
        [
            {},
            {"titulo_pergunta": None, "na_pratica_a": None, "na_pratica_b": "   ", "porque": ""},
        ],
        ids=["ausentes", "nulos-ou-vazios"],
    )
    def test_o_turno_sem_os_campos_novos_grava_a_pergunta_como_hoje(self, monkeypatch, campos):
        client, sb, _ = _cenario(monkeypatch)

        corpo = _abrir_pelo_botao(client, monkeypatch, **campos)

        assert _conversas(sb)[0]["mensagens"][-1] == PERGUNTA_DE_HOJE
        fala = corpo["mensagens"][-1]
        assert fala["texto"] == PERGUNTA_DE_HOJE["contexto"]
        assert fala["opcoes"] == ["Só a recepção.", "A recepção e a enfermagem."]
        assert fala["cartao"] is None

    def test_so_o_porque_vem_e_o_cartao_leva_so_ele(self, monkeypatch):
        client, sb, _ = _cenario(monkeypatch)

        corpo = _abrir_pelo_botao(client, monkeypatch, porque="A recepção já agenda.")

        assert _conversas(sb)[0]["mensagens"][-1] == {**PERGUNTA_DE_HOJE, "porque": "A recepção já agenda."}
        assert corpo["mensagens"][-1]["cartao"] == {
            "titulo": None,
            "na_pratica_a": None,
            "na_pratica_b": None,
            "porque": "A recepção já agenda.",
        }


# ─── A regra de tamanho do prompt, conferida por amostra ─────────────────────

LIMITE_DO_TITULO = 8
LIMITE_DO_CONTEXTO = 25
LIMITE_DA_OPCAO = 12


def _palavras(texto: str | None) -> int:
    return len((texto or "").split())


def _fora_da_regra(resposta: dict) -> list[str]:
    """O que uma resposta de pergunta fere da regra que o prompt pede: título
    curto em forma de pergunta, contexto de uma frase curta, opções curtas, o
    "na prática" de cada opção e o porquê da recomendada."""
    falhas = []
    titulo = resposta.get("titulo_pergunta") or ""
    if not titulo.strip() or _palavras(titulo) > LIMITE_DO_TITULO or not titulo.rstrip().endswith("?"):
        falhas.append("titulo_pergunta")
    if _palavras(resposta.get("contexto")) > LIMITE_DO_CONTEXTO:
        falhas.append("contexto")
    for campo in ("opcao_a", "opcao_b"):
        if not (resposta.get(campo) or "").strip() or _palavras(resposta.get(campo)) > LIMITE_DA_OPCAO:
            falhas.append(campo)
    for campo in ("na_pratica_a", "na_pratica_b", "porque"):
        if not (resposta.get(campo) or "").strip():
            falhas.append(campo)
    return falhas


def _exemplos_de_pergunta_do_prompt(prompt: str) -> list[dict]:
    """As respostas de exemplo de pergunta que o prompt mostra ao modelo."""
    formato = prompt.split("## Formato de resposta", 1)[1]
    return [
        json.loads(linha)
        for linha in formato.splitlines()
        if linha.startswith("{") and json.loads(linha).get("encerrou") is False
    ]


class TestOPromptPedeOTamanhoEOPorque:
    def test_o_prompt_pede_os_limites_de_tamanho_e_o_porque_da_recomendada(self):
        prompt = load_prompt("planejamento_demanda_system")

        secao = prompt.split("## Como perguntar", 1)[1].split("\n## ", 1)[0]
        for trecho in (
            "`titulo_pergunta`",
            "até 8 palavras",
            "em forma de pergunta",
            "uma frase só, de até 25 palavras",
            "até 12 palavras",
            "`na_pratica_a`",
            "`na_pratica_b`",
            "`porque`",
        ):
            assert trecho in secao, trecho

    def test_a_resposta_de_exemplo_do_prompt_cumpre_a_regra(self):
        exemplos = _exemplos_de_pergunta_do_prompt(load_prompt("planejamento_demanda_system"))

        assert exemplos, "o prompt não mostra nenhuma resposta de exemplo de pergunta"
        for exemplo in exemplos:
            assert _fora_da_regra(exemplo) == [], exemplo

    def test_a_regra_pega_a_resposta_fora_do_tamanho_e_sem_o_porque(self):
        """O detector não é cego: a amostra longa e sem o porquê é apontada
        campo a campo."""
        longa = {
            "titulo_pergunta": "Quem é que vai marcar o retorno do paciente na saída?",
            "contexto": " ".join(["palavra"] * 26),
            "opcao_a": " ".join(["palavra"] * 13),
            "opcao_b": "Só a recepção.",
            "na_pratica_a": "A recepção marca.",
            "na_pratica_b": "O médico marca.",
            "porque": None,
        }

        assert _fora_da_regra(longa) == ["titulo_pergunta", "contexto", "opcao_a", "porque"]


# ─── A conversa que o modelo relê e o resumo ─────────────────────────────────


class TestOModeloReleOCartao:
    def test_a_conversa_que_o_modelo_rele_traz_titulo_na_pratica_e_porque(self, monkeypatch):
        client, _, _ = _cenario(monkeypatch)
        demanda_id = _abrir_pelo_botao(client, monkeypatch, **CAMPOS_DO_CARTAO)["demanda_id"]
        cliente = _ia(monkeypatch, _pergunta(contexto="E quem confirma o retorno?"))

        assert client.post(f"{CHAT}/{demanda_id}", json={"opcao": "A"}).status_code == 200

        pedido = cliente.chamadas[0]["messages"][0]["content"]
        assert "Título da pergunta: Quem marca o retorno do paciente?" in pedido
        assert "Na prática: A recepção marca o retorno na saída do paciente." in pedido
        assert "Na prática: O médico marca o retorno ainda no consultório." in pedido
        assert "Por que recomendo a A: A recepção já agenda as consultas do hospital hoje." in pedido

    def test_o_pedido_do_resumo_traz_titulo_na_pratica_e_porque(self, monkeypatch):
        client, _, _ = _cenario(monkeypatch)
        demanda_id = _abrir_pelo_botao(client, monkeypatch, **CAMPOS_DO_CARTAO)["demanda_id"]
        _ia(monkeypatch, _pergunta(contexto="E quem confirma o retorno?"))
        client.post(f"{CHAT}/{demanda_id}", json={"opcao": "A"})
        cliente = _ia(monkeypatch, _resumo_do_modelo())

        assert client.post(f"{CHAT}/{demanda_id}/resumo").status_code == 200

        pedido = cliente.chamadas[0]["messages"][0]["content"]
        assert pedido.startswith("PEDIDO: RESUMO")
        assert "Título da pergunta: Quem marca o retorno do paciente?" in pedido
        assert "Na prática: A recepção marca o retorno na saída do paciente." in pedido
        assert "Na prática: O médico marca o retorno ainda no consultório." in pedido
        assert "Por que recomendo a A: A recepção já agenda as consultas do hospital hoje." in pedido

    def test_a_pergunta_sem_os_campos_novos_volta_ao_modelo_como_hoje(self, monkeypatch):
        client, _, _ = _cenario(monkeypatch)
        demanda_id = _abrir_pelo_botao(client, monkeypatch)["demanda_id"]
        cliente = _ia(monkeypatch, _pergunta(contexto="E quem confirma o retorno?"))

        client.post(f"{CHAT}/{demanda_id}", json={"opcao": "A"})

        pedido = cliente.chamadas[0]["messages"][0]["content"]
        assert (
            "IA: Preciso saber quem vai usar a tela nova.\n"
            "    A) Só a recepção.\n"
            "    B) A recepção e a enfermagem.\n"
            "    (recomendada: A)\n"
            "Diretor: escolheu A) Só a recepção."
        ) in pedido
        assert "Título da pergunta" not in pedido
        assert "Na prática" not in pedido


# ─── O kit ───────────────────────────────────────────────────────────────────


class TestOKitDizOCartao:
    def test_o_texto_da_tecnologia_no_kit_diz_que_a_pergunta_chega_em_cartao(self):
        """O kit é a língua em que o Assistente fala com o diretor: sem o cartão
        escrito, ele descreveria a pergunta do jeito de antes."""
        texto = (CONHECIMENTO_DIR / "tecnologia.md").read_text(encoding="utf-8")

        for titulo in ("## A conversa com o Assistente", "## O Planejamento da Demanda"):
            secao = texto.split(titulo, 1)[1].split("\n## ", 1)[0]
            for trecho in ("num cartão", "**Na prática**", "o porquê da recomendada"):
                assert trecho in secao, (titulo, trecho)
            assert "uma ou duas frases de contexto" not in secao, titulo
