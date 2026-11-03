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

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from test_planejamento_demanda import _ia, _pergunta  # noqa: E402
from test_tecnologia_chat import (  # noqa: E402
    _cenario,
    _chamadas,
    _conversas,
    _demandas,
    _integracao_configurada,  # noqa: F401
    _llm_em_mock,  # noqa: F401
    _reset_rate_limiter,  # noqa: F401
    _turno,
)
from test_tecnologia_vinculo import _CRIAR_ISSUE_DE_VERDADE, BASE, _TransporteGithub  # noqa: E402

from app.config import settings  # noqa: E402
from app.services import github_client  # noqa: E402
from app.services.conhecimento import CONHECIMENTO_DIR  # noqa: E402
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


# ═══════════════════════════════════════════════════════════════════════════
# 3. O resumo traz o que ficou em aberto, e o "Não bateu" volta à conversa
# ═══════════════════════════════════════════════════════════════════════════


def _ate_o_resumo(client, sb, monkeypatch, **campos_do_resumo) -> str:
    demanda_id = _abrir_pelo_botao(client, monkeypatch)["demanda_id"]
    _com_perguntas(sb, 1)
    _ia(monkeypatch, _resumo_do_modelo(**campos_do_resumo))
    resposta = client.post(f"{CHAT}/{demanda_id}/resumo")
    assert resposta.status_code == 200, resposta.text
    return demanda_id


class TestResumoDaMelhoria:
    def test_o_resumo_traz_o_que_ficou_em_aberto(self, monkeypatch):
        client, sb, _ = _cenario(monkeypatch)
        demanda_id = _ate_o_resumo(client, sb, monkeypatch)

        resumo = client.get(f"{CHAT}/{demanda_id}").json()["resumo_da_melhoria"]

        assert resumo["em_aberto"] == ["Quem confirma o retorno com o paciente."]

    def test_o_que_nao_foi_perguntado_nunca_vira_decisao(self, monkeypatch):
        """O modelo aponta uma decisão para a pergunta 2, que não houve: ela
        some do resumo. O que não foi perguntado só cabe em "ficou em aberto"."""
        client, sb, _ = _cenario(monkeypatch)
        demanda_id = _ate_o_resumo(
            client,
            sb,
            monkeypatch,
            decisoes=[{"pergunta": 1, "porque": "Dito."}, {"pergunta": 2, "porque": "Inventado."}],
        )

        resumo = client.get(f"{CHAT}/{demanda_id}").json()["resumo_da_melhoria"]

        assert [d["porque"] for d in resumo["decisoes"]] == ["Dito."]

    def test_nao_bateu_volta_ao_planejamento_e_a_ia_retoma_dali(self, monkeypatch):
        client, sb, gh = _cenario(monkeypatch)
        demanda_id = _ate_o_resumo(client, sb, monkeypatch)

        voltou = client.post(f"{CHAT}/{demanda_id}/nao-bateu", json={"texto": "A enfermagem também marca."})
        assert voltou.status_code == 200, voltou.text
        assert voltou.json()["estado"] == "em_andamento"
        cliente = _ia(monkeypatch, _pergunta(contexto="A enfermagem marca em que momento?"))

        retomou = client.post(f"{CHAT}/{demanda_id}", json={})

        assert retomou.status_code == 200, retomou.text
        assert retomou.json()["mensagens"][-1]["texto"] == "A enfermagem marca em que momento?"
        assert "A enfermagem também marca." in cliente.chamadas[0]["messages"][0]["content"]
        assert gh.criadas == []


# ═══════════════════════════════════════════════════════════════════════════
# 4. "Criar o card" cria o PRD do diretor
# ═══════════════════════════════════════════════════════════════════════════


class TestCriarOCardDaMelhoria:
    def test_criar_o_card_cria_o_prd_do_diretor_para_a_triagem(self, monkeypatch):
        client, sb, gh = _cenario(monkeypatch)
        demanda_id = _ate_o_resumo(client, sb, monkeypatch)

        resposta = client.post(f"{CHAT}/{demanda_id}/criar-card")

        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["estado"] == "enviado"
        [issue] = gh.criadas
        assert sorted(issue["labels"]) == ["needs-triage", "type:feature"]
        assert issue["titulo"] == "Agenda de retorno na recepção"
        cabecalhos = re.findall(r"^## (.+)$", issue["corpo"], re.MULTILINE)
        assert cabecalhos == [
            "👔 Para o diretor",
            "Problema",
            "Solução",
            "Histórias de usuário",
            "Decisões de negócio",
            "Decisões de implementação",
            "Decisões de teste",
            "Ficou em aberto",
            "Para o glossário",
            "Origem",
        ]
        assert _demandas(sb)[0]["github_issue_numero"] is not None

    def test_o_glossario_traz_os_termos_e_as_decisoes_candidatas_a_adr(self, monkeypatch):
        client, sb, gh = _cenario(monkeypatch)
        demanda_id = _ate_o_resumo(client, sb, monkeypatch)

        client.post(f"{CHAT}/{demanda_id}/criar-card")

        glossario = gh.criadas[0]["corpo"].split("## Para o glossário", 1)[1].split("\n## ", 1)[0]
        assert "Agenda de retorno: a marcação do retorno feita na saída." in glossario
        assert "Só a recepção marca o retorno." in glossario

    def test_o_bloco_para_o_diretor_nao_tem_numero_de_issue(self, monkeypatch):
        client, sb, gh = _cenario(monkeypatch)
        demanda_id = _abrir_pelo_botao(client, monkeypatch)["demanda_id"]
        [conversa] = _conversas(sb)
        conversa["mensagens"] = [
            *conversa["mensagens"][:2],
            _pergunta_guardada(1),
            {"tipo": "resposta", "opcao": None, "texto": "Igual ao pedido #1380, mas na recepção"},
        ]
        _ia(monkeypatch, _resumo_do_modelo(titulo="Retorno como no #1380"))
        assert client.post(f"{CHAT}/{demanda_id}/resumo").status_code == 200

        client.post(f"{CHAT}/{demanda_id}/criar-card")

        bloco = bloco_para_o_diretor(gh.criadas[0]["corpo"])
        assert "1380" in bloco
        assert re.search(r"#\d", bloco) is None

    def test_o_card_do_bug_continua_sem_glossario(self, monkeypatch):
        client, _, gh = _cenario(monkeypatch)
        _ia(monkeypatch, _turno(pronto=True, mensagem="Montei o resumo."))
        demanda_id = client.post(CHAT, json={"escolha": "bug"}).json()["demanda_id"]
        _ia(monkeypatch, _turno(pronto=True, mensagem="Montei o resumo."))
        client.post(f"{CHAT}/{demanda_id}", json={"texto": "Na Ouvidoria"})

        assert client.post(f"{CHAT}/{demanda_id}/criar-card").status_code == 200

        assert "Para o glossário" not in gh.criadas[0]["corpo"]
        assert "type:fix" in gh.criadas[0]["labels"]


# ═══════════════════════════════════════════════════════════════════════════
# 5. O Kit de conhecimento
# ═══════════════════════════════════════════════════════════════════════════


class TestOPrdNasceDesignadoAoDono:
    """O PRD do diretor nasce designado ao dono da empresa, que redistribui
    (issue #1349): antes provado pela rota "enviar" da tela antiga."""

    def test_a_issue_nasce_atribuida_ao_dono(self, monkeypatch):
        monkeypatch.setattr(settings, "github_login_dono", "dono-da-vitta")
        client, sb, gh = _cenario(monkeypatch)
        demanda_id = _ate_o_resumo(client, sb, monkeypatch)

        assert client.post(f"{CHAT}/{demanda_id}/criar-card").status_code == 200

        assert gh.criadas[0]["assignees"] == ["dono-da-vitta"]

    def test_o_dono_padrao_e_o_pedro(self):
        assert type(settings).model_fields["github_login_dono"].default == "pedrorezendefig"

    def test_o_assignee_que_o_github_recusa_ainda_vincula(self, monkeypatch):
        """O assignee e conveniencia: login que o GitHub recusa nao pode virar
        "GitHub indisponivel" no botao (must-fix da revisao do PR #1050). O
        caminho inteiro, com o `criar_issue` de verdade e so a rede falsa."""
        monkeypatch.setattr(settings, "github_login_dono", "login-recusado")
        client, sb, _ = _cenario(monkeypatch)
        demanda_id = _ate_o_resumo(client, sb, monkeypatch)
        monkeypatch.setattr(github_client, "criar_issue", _CRIAR_ISSUE_DE_VERDADE)
        transporte = _TransporteGithub(status_da_designacao=422, numero=902)
        monkeypatch.setattr(github_client.httpx, "request", transporte)

        resposta = client.post(f"{CHAT}/{demanda_id}/criar-card")

        assert resposta.status_code == 200, resposta.text
        assert _demandas(sb)[0]["github_issue_numero"] == 902
        assert transporte.chamadas[1][2] == {"assignees": ["login-recusado"]}


class TestKitDaTecnologia:
    def test_o_texto_da_tecnologia_no_kit_diz_o_caminho_da_melhoria_no_chat(self):
        """O kit e a lingua em que o Assistente fala com o diretor: sem o
        caminho novo escrito, ele mandaria o diretor a um botao que saiu."""
        texto = (CONHECIMENTO_DIR / "tecnologia.md").read_text(encoding="utf-8")

        secao = texto.split("## A conversa com o Assistente", 1)[1].split("\n## ", 1)[0]
        for trecho in ("no máximo 12 perguntas", "**Fechar e resumir**", "ficou em aberto", "recomendada"):
            assert trecho in secao, trecho
        assert "Planejar com a IA" not in texto
