"""Revisão com o código de hoje, a conversa (issue #1557, PRD #1548, ADR 0084, decisão 3).

Um card de melhoria Em análise ou Planejada, sem parte em desenvolvimento,
ganha o botão "Revisar com o código de hoje", para o autor e o Desenvolvedor.
O diálogo mostra antes a estimativa em dólar, e a IA só roda com a
confirmação (ADR 0082). Confirmada, a mesma conversa volta a em andamento com a
marca da revisão, e o primeiro turno é o Retrato de hoje (Já existe, com a
versão; Mudou desde o card; Continua em aberto), lido dos comentários da
issue-raiz e das subidas do `history.json` desde a data do card. Cada item de
Já existe vira o "isso atende?" e só sai do pedido com o sim. Cada turno grava
quem respondeu.

Tudo pela ROTA, com o modelo e o GitHub dublados no molde de
`test_tecnologia_documento_vivo` e `test_tecnologia_apagar_a_demanda`.
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
from test_tecnologia_vinculo import BASE, DIRETOR, PEDRO, _demanda, _GithubFalso, _issue, _pessoa  # noqa: E402

from app.services import github_client  # noqa: E402
from app.services.conhecimento import CONHECIMENTO_DIR  # noqa: E402
from app.services.tecnologia_vinculo import (  # noqa: E402
    ETAPA_EM_ANALISE,
    ETAPA_EM_DESENVOLVIMENTO,
    ETAPA_PLANEJADA,
)

CHAT = f"{BASE}/chat"
DEMANDA = "d-1"
REVISAO = f"{CHAT}/{DEMANDA}/revisao"
OUTRO_DIRETOR = _pessoa("P3", "Outro Diretor")

# A conversa da melhoria que virou card: a abertura, o que o diretor contou, a
# passagem ao planejamento, uma pergunta respondida e o encerramento.
CONVERSA_ENVIADA = [
    {"tipo": "ia", "texto": "Isso é um bug ou uma melhoria?", "fonte": None, "opcoes": ["Bug", "Melhoria"]},
    {"tipo": "diretor", "texto": "Melhoria"},
    {"tipo": "diretor", "texto": "Quero marcar o retorno do paciente na saída."},
    {
        "tipo": "ia",
        "texto": "Vamos planejar.",
        "fonte": None,
        "opcoes": [],
        "classificacao": "melhoria",
        "planejar": True,
    },
    {
        "tipo": "pergunta",
        "contexto": "Quem marca o retorno?",
        "opcoes": [{"letra": "A", "texto": "Só a recepção."}, {"letra": "B", "texto": "A enfermagem."}],
        "recomendada": "A",
    },
    {"tipo": "resposta", "opcao": "A", "texto": "Só a recepção."},
    {"tipo": "encerrou", "contexto": "Já tenho o que preciso."},
]

RESUMO_ENVIADO = {
    "decisoes": [{"pergunta": "Quem marca o retorno?", "escolha": "Só a recepção.", "porque": "É quem atende."}],
    "em_aberto": ["Quem confirma o retorno com o paciente."],
    "termos": [],
    "candidatas_a_adr": [],
}

# O card nasceu em 01/10; a subida de 20/09 é de antes dele e não entra.
ISSUE_DO_CARD = {
    **_issue(900, corpo="## Para o diretor\n\n**O que muda:** A recepção marca o retorno."),
    "created_at": "2026-10-01T12:00:00Z",
}
HISTORICO = [
    {
        "at": "2026-10-20T10:00:00-03:00",
        "app_version": "0.245.0",
        "subject": "Onda agenda: retorno marcado na saída",
        "prds": [1400],
    },
    {
        "at": "2026-09-20T10:00:00-03:00",
        "app_version": "0.230.0",
        "subject": "Onda velha: tela de cadastro antiga",
        "prds": [1300],
    },
]
COMENTARIOS = [
    {"autor": "pedrorezendefig", "corpo": "Combinado por fora: a enfermagem também vê o retorno.", "criado_em": "x"}
]

ITEM_QUE_JA_EXISTE = "A recepção já marca o retorno na saída do paciente."


def _retrato(**campos) -> str:
    base = {
        "ja_existe": [{"item": ITEM_QUE_JA_EXISTE, "versao": "v0.245.0"}],
        "mudou": ["A enfermagem também vê o retorno, combinado na issue."],
        "em_aberto": ["Quem confirma o retorno com o paciente."],
    }
    base.update(campos)
    return json.dumps(base, ensure_ascii=False)


def _card(etapa: str = ETAPA_EM_ANALISE, **campos) -> dict:
    base = {
        "autor_id": DIRETOR["id"],
        "responsavel_id": PEDRO["id"],
        "github_issue_numero": 900,
        "etapa": etapa,
        "tipo": "novo",
        "titulo": "Retorno marcado na saída",
        "descricao": "Quero marcar o retorno do paciente na saída.",
    }
    return _demanda(DEMANDA, **{**base, **campos})


def _montar_revisao(monkeypatch, *, logado=DIRETOR, demanda: dict | None = None, estado: str = "enviado"):
    client, sb, gh = _cenario(
        monkeypatch,
        logado=logado,
        participantes=[PEDRO, DIRETOR, OUTRO_DIRETOR],
        demandas=[demanda or _card()],
        github=_GithubFalso({900: ISSUE_DO_CARD}),
    )
    sb.tabelas["tecnologia_planejamentos"] = [
        {
            "id": "p-1",
            "demanda_id": DEMANDA,
            "estado": estado,
            "mensagens": [dict(m) for m in CONVERSA_ENVIADA],
            "decisoes": [],
            "resumo": dict(RESUMO_ENVIADO),
            "atualizado_em": "2026-10-01T12:00:00Z",
        }
    ]
    monkeypatch.setattr(github_client, "ler_historico_de_deploys", lambda: [dict(h) for h in HISTORICO])
    monkeypatch.setattr(github_client, "ler_comentarios", lambda numero: [dict(c) for c in COMENTARIOS], raising=False)
    return client, sb, gh


def _na_lista(client) -> dict:
    [demanda] = [d for d in client.get(f"{CHAT}?filtro=todas").json() if d["id"] == DEMANDA]
    return demanda


def _revisar(client, monkeypatch, retrato: str | None = None):
    cliente = _ia(monkeypatch, retrato or _retrato())
    resposta = client.post(REVISAO, json={"confirmado": True})
    return resposta, cliente


# ═══════════════════════════════════════════════════════════════════════════
# 1. Quem vê o botão
# ═══════════════════════════════════════════════════════════════════════════


class TestQuemVeOBotao:
    @pytest.mark.parametrize("etapa", [ETAPA_EM_ANALISE, ETAPA_PLANEJADA])
    def test_o_autor_ve_o_botao_no_card_em_analise_ou_planejada(self, monkeypatch, etapa):
        client, _, _ = _montar_revisao(monkeypatch, demanda=_card(etapa))

        assert _na_lista(client)["pode_revisar"] is True

    def test_o_desenvolvedor_ve_o_botao_no_card_de_outro_autor(self, monkeypatch):
        client, _, _ = _montar_revisao(monkeypatch, logado=PEDRO)

        assert _na_lista(client)["pode_revisar"] is True

    def test_card_em_desenvolvimento_nao_tem_o_botao_e_a_rota_recusa(self, monkeypatch):
        client, _, _ = _montar_revisao(monkeypatch, demanda=_card(ETAPA_EM_DESENVOLVIMENTO))

        assert _na_lista(client)["pode_revisar"] is False
        assert client.get(REVISAO).status_code == 409

    def test_card_planejado_com_uma_parte_em_desenvolvimento_nao_tem_o_botao(self, monkeypatch):
        partes = [
            {"numero": 901, "o_que_muda": "A tela", "situacao": ETAPA_EM_DESENVOLVIMENTO},
            {"numero": 902, "o_que_muda": "O aviso", "situacao": ETAPA_PLANEJADA},
        ]
        client, _, _ = _montar_revisao(monkeypatch, demanda=_card(ETAPA_PLANEJADA, partes=partes))

        assert _na_lista(client)["pode_revisar"] is False
        _ia(monkeypatch, _retrato())
        assert client.post(REVISAO, json={"confirmado": True}).status_code == 409

    def test_outro_diretor_nao_revisa_o_card_que_nao_e_dele(self, monkeypatch):
        """No card da Vitta todo diretor vê, mas revisar é do autor e do Desenvolvedor."""
        client, _, _ = _montar_revisao(monkeypatch, logado=OUTRO_DIRETOR, demanda=_card(origem="vitta"))

        assert _na_lista(client)["pode_revisar"] is False
        assert client.get(REVISAO).status_code in (403, 409)

    def test_o_bug_nao_tem_o_botao(self, monkeypatch):
        client, _, _ = _montar_revisao(monkeypatch, demanda=_card(tipo="defeito"))

        assert _na_lista(client)["pode_revisar"] is False


# ═══════════════════════════════════════════════════════════════════════════
# 2. Sem confirmação, nenhuma IA
# ═══════════════════════════════════════════════════════════════════════════


class TestSemConfirmacaoNenhumaIA:
    def test_a_estimativa_sai_em_dolar_pelo_preco_do_modelo_sem_chamar_a_ia(self, monkeypatch):
        client, sb, _ = _montar_revisao(monkeypatch)
        cliente = _ia(monkeypatch, _retrato())

        resposta = client.get(REVISAO)

        assert resposta.status_code == 200, resposta.text
        corpo = resposta.json()
        assert corpo["modelo"] == "Opus 5.5"
        assert 0 < corpo["minimo_usd"] < corpo["maximo_usd"]
        assert cliente.chamadas == []
        assert _conversas(sb)[0]["estado"] == "enviado"

    def test_a_estimativa_cresce_com_o_tamanho_da_conversa(self, monkeypatch):
        client, sb, _ = _montar_revisao(monkeypatch)
        curta = client.get(REVISAO).json()["minimo_usd"]
        _conversas(sb)[0]["mensagens"][2]["texto"] = "Quero marcar o retorno. " * 2000

        assert client.get(REVISAO).json()["minimo_usd"] > curta

    def test_sem_a_confirmacao_a_rota_recusa_e_nao_chama_a_ia(self, monkeypatch):
        client, sb, _ = _montar_revisao(monkeypatch)
        cliente = _ia(monkeypatch, _retrato())

        resposta = client.post(REVISAO, json={})

        assert resposta.status_code == 422
        assert cliente.chamadas == []
        conversa = _conversas(sb)[0]
        assert conversa["estado"] == "enviado"
        assert conversa.get("revisao_iniciada_em") is None


# ═══════════════════════════════════════════════════════════════════════════
# 3. O Retrato de hoje
# ═══════════════════════════════════════════════════════════════════════════


class TestORetratoDeHoje:
    def test_confirmada_a_revisao_o_retrato_sai_com_os_tres_blocos_e_a_versao(self, monkeypatch):
        client, _, _ = _montar_revisao(monkeypatch)

        resposta, _ = _revisar(client, monkeypatch)

        assert resposta.status_code == 200, resposta.text
        [retrato] = [f for f in resposta.json()["mensagens"] if f.get("retrato")]
        assert retrato["autor"] == "ia"
        assert retrato["retrato"] == {
            "ja_existe": [{"item": ITEM_QUE_JA_EXISTE, "versao": "v0.245.0"}],
            "mudou": ["A enfermagem também vê o retorno, combinado na issue."],
            "em_aberto": ["Quem confirma o retorno com o paciente."],
        }

    def test_o_agente_le_os_comentarios_e_so_as_subidas_desde_a_data_do_card(self, monkeypatch):
        client, _, _ = _montar_revisao(monkeypatch)

        _, cliente = _revisar(client, monkeypatch)

        [chamada] = cliente.chamadas
        pedido = chamada["messages"][0]["content"]
        assert "PEDIDO: RETRATO DE HOJE" in pedido
        assert "v0.245.0" in pedido and "Onda agenda: retorno marcado na saída" in pedido
        assert "v0.230.0" not in pedido
        assert "Combinado por fora: a enfermagem também vê o retorno." in pedido
        assert "**O que muda:** A recepção marca o retorno." in pedido

    def test_a_conversa_volta_a_em_andamento_com_a_marca_da_revisao(self, monkeypatch):
        client, sb, _ = _montar_revisao(monkeypatch, logado=PEDRO)
        monkeypatch.setattr("app.config.settings.app_version", "0.250.0")

        resposta, _ = _revisar(client, monkeypatch)

        assert resposta.json()["estado"] == "em_andamento"
        conversa = _conversas(sb)[0]
        assert conversa["estado"] == "em_andamento"
        assert conversa["revisao_por"] == PEDRO["id"]
        assert conversa["revisao_versao_base"] == "v0.250.0"
        assert conversa["revisao_iniciada_em"]
        # A mesma conversa: o que já estava fica, e o retrato entra depois.
        assert conversa["mensagens"][: len(CONVERSA_ENVIADA)] == CONVERSA_ENVIADA

    def test_item_de_ja_existe_sem_versao_derruba_o_retrato(self, monkeypatch):
        client, sb, _ = _montar_revisao(monkeypatch)

        resposta, _ = _revisar(client, monkeypatch, _retrato(ja_existe=[{"item": ITEM_QUE_JA_EXISTE, "versao": ""}]))

        assert resposta.status_code == 502
        assert _conversas(sb)[0]["estado"] == "enviado"


# ═══════════════════════════════════════════════════════════════════════════
# 4. "Isso atende?"
# ═══════════════════════════════════════════════════════════════════════════


class TestIssoAtende:
    def test_cada_item_de_ja_existe_vira_a_pergunta_isso_atende(self, monkeypatch):
        client, _, _ = _montar_revisao(monkeypatch)

        resposta, _ = _revisar(client, monkeypatch)

        pergunta = resposta.json()["mensagens"][-1]
        assert pergunta["autor"] == "ia"
        assert pergunta["texto"] == f"Isso atende? Já existe desde a v0.245.0: {ITEM_QUE_JA_EXISTE}"
        assert pergunta["opcoes"] == ["Atende, pode sair do pedido.", "Não atende, continua no pedido."]

    def test_com_o_atende_o_item_sai_do_pedido(self, monkeypatch):
        client, _, _ = _montar_revisao(monkeypatch)
        _revisar(client, monkeypatch)
        cliente = _ia(monkeypatch, _pergunta(contexto="E quem confirma o retorno?"))

        resposta = client.post(f"{CHAT}/{DEMANDA}", json={"opcao": "A"})

        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["revisao"]["saiu"] == [ITEM_QUE_JA_EXISTE]
        assert resposta.json()["revisao"]["continua"] == []
        pedido = cliente.chamadas[0]["messages"][0]["content"]
        assert f"Saiu do pedido (o diretor disse que já atende):\n- {ITEM_QUE_JA_EXISTE}" in pedido

    def test_com_o_nao_atende_o_item_continua_no_pedido(self, monkeypatch):
        client, _, _ = _montar_revisao(monkeypatch)
        _revisar(client, monkeypatch)
        cliente = _ia(monkeypatch, _pergunta(contexto="E quem confirma o retorno?"))

        resposta = client.post(f"{CHAT}/{DEMANDA}", json={"opcao": "B"})

        assert resposta.json()["revisao"]["continua"] == [ITEM_QUE_JA_EXISTE]
        assert resposta.json()["revisao"]["saiu"] == []
        pedido = cliente.chamadas[0]["messages"][0]["content"]
        assert f"Continua no pedido (o diretor disse que não atende):\n- {ITEM_QUE_JA_EXISTE}" in pedido

    def test_com_dois_itens_a_segunda_pergunta_vem_sem_chamar_a_ia(self, monkeypatch):
        client, _, _ = _montar_revisao(monkeypatch)
        outro = "O médico já vê o retorno marcado."
        _revisar(
            client,
            monkeypatch,
            _retrato(
                ja_existe=[{"item": ITEM_QUE_JA_EXISTE, "versao": "v0.245.0"}, {"item": outro, "versao": "v0.246.0"}]
            ),
        )
        cliente = _ia(monkeypatch, _pergunta())

        resposta = client.post(f"{CHAT}/{DEMANDA}", json={"opcao": "A"})

        assert cliente.chamadas == []
        assert resposta.json()["mensagens"][-1]["texto"] == f"Isso atende? Já existe desde a v0.246.0: {outro}"


# ═══════════════════════════════════════════════════════════════════════════
# 5. Quem respondeu cada turno
# ═══════════════════════════════════════════════════════════════════════════


class TestQuemRespondeu:
    def test_cada_turno_grava_quem_respondeu_e_a_tela_mostra_o_nome(self, monkeypatch):
        client, sb, _ = _montar_revisao(monkeypatch, logado=PEDRO)
        _revisar(client, monkeypatch)
        _ia(monkeypatch, _pergunta())

        resposta = client.post(f"{CHAT}/{DEMANDA}", json={"opcao": "B"})

        gravada = [m for m in _conversas(sb)[0]["mensagens"] if m.get("tipo") == "resposta"][-1]
        assert gravada["respondido_por"] == PEDRO["id"]
        falas_de_gente = [f for f in resposta.json()["mensagens"] if f["autor"] == "diretor"]
        assert falas_de_gente[-1]["respondido_por"] == "Pedro Vitta"


# ═══════════════════════════════════════════════════════════════════════════
# 6. O kit de conhecimento
# ═══════════════════════════════════════════════════════════════════════════


class TestOKitDizARevisao:
    def test_o_texto_da_tecnologia_no_kit_diz_a_revisao_com_o_codigo_de_hoje(self):
        texto = (CONHECIMENTO_DIR / "tecnologia.md").read_text(encoding="utf-8")

        secao = texto.split("## Revisar com o código de hoje", 1)[1].split("\n## ", 1)[0]
        for trecho in (
            "Revisar com o código de hoje",
            "Em análise ou Planejada",
            "quanto a revisão deve custar",
            "Retrato de hoje",
            "Já existe",
            "Mudou desde o card",
            "Continua em aberto",
            "isso atende?",
            "o nome de quem respondeu",
        ):
            assert trecho in secao, trecho
