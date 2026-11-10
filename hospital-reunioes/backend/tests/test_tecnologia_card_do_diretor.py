"""O card do diretor é reconhecível no GitHub (issue #1532, PRD #1529, ADR 0083, decisões 4 e 9).

Toda issue que o "Criar o card" da aba Tecnologia cria, bug ou melhoria, nasce
com a label `origem:diretor`, uma frase de resumo escrita pelo agente na
primeira linha do corpo e o link para a Demanda no app. A frase passa pela
peneira pública (ADR 0060) e a entrevista fica no app. É desses três dados que
o Hospital OS tira o selo, o Aviso e o Resumo da manhã (pedrorezendefig/os#289).
Tudo pela ROTA, com o modelo e o GitHub dublados no molde de `test_tecnologia_chat`.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from test_planejamento_demanda import _ia  # noqa: E402
from test_tecnologia_chat import (  # noqa: E402
    CAMPOS_RESPONDIDOS,
    CHAT,
    CPF,
    CRITERIOS,
    NOME,
    _cenario,
    _comecar,
    _conversas,
    _integracao_configurada,  # noqa: F401
    _llm_em_mock,  # noqa: F401
    _reset_rate_limiter,  # noqa: F401
    _turno,
)
from test_tecnologia_chat_melhoria import (  # noqa: E402
    _abrir_pelo_botao,
    _com_perguntas,
    _resumo_do_modelo,
)

from app.config import settings  # noqa: E402
from app.services.tecnologia_vinculo import LABEL_ORIGEM_DIRETOR, bloco_para_o_diretor  # noqa: E402

TRIAGE_LABELS = Path(__file__).resolve().parents[3] / "docs" / "agents" / "triage-labels.md"

FRASE_DO_BUG = "O botão Responder sumiu do caso aberto na Ouvidoria."
FRASE_DA_MELHORIA = "A recepção passa a marcar o retorno do paciente na saída."


def _card_do_bug(client, monkeypatch, *, frase: str | None = FRASE_DO_BUG, fala: str = "Na Ouvidoria") -> dict:
    """Um bug do primeiro turno ao Criar o card; devolve a issue pedida ao GitHub."""
    demanda_id = _comecar(client, monkeypatch)
    extra = {"frase": frase} if frase is not None else {}
    _ia(
        monkeypatch,
        _turno(
            pronto=True, mensagem="Montei o resumo. Confere?", campos=CAMPOS_RESPONDIDOS, criterios=CRITERIOS, **extra
        ),
    )
    assert client.post(f"{CHAT}/{demanda_id}", json={"texto": fala}).status_code == 200
    assert client.post(f"{CHAT}/{demanda_id}/criar-card").status_code == 200
    return {"demanda_id": demanda_id}


def _card_da_melhoria(client, sb, monkeypatch, *, frase: str | None = FRASE_DA_MELHORIA) -> dict:
    """Uma melhoria do botão ao Criar o card; devolve o id da Demanda."""
    demanda_id = _abrir_pelo_botao(client, monkeypatch)["demanda_id"]
    _com_perguntas(sb, 1)
    extra = {"frase": frase} if frase is not None else {}
    _ia(monkeypatch, _resumo_do_modelo(**extra))
    assert client.post(f"{CHAT}/{demanda_id}/resumo").status_code == 200
    assert client.post(f"{CHAT}/{demanda_id}/criar-card").status_code == 200
    return {"demanda_id": demanda_id}


def _primeira_linha(corpo: str) -> str:
    return next(linha for linha in corpo.splitlines() if linha.strip())


class TestLabelDeOrigem:
    def test_a_issue_do_bug_nasce_com_a_label_de_origem_do_diretor(self, monkeypatch):
        client, _, gh = _cenario(monkeypatch)

        _card_do_bug(client, monkeypatch)

        [issue] = gh.criadas
        assert sorted(issue["labels"]) == ["origem:diretor", "ready-for-agent", "type:fix"]

    def test_a_issue_da_melhoria_nasce_com_a_label_de_origem_do_diretor(self, monkeypatch):
        client, sb, gh = _cenario(monkeypatch)

        _card_da_melhoria(client, sb, monkeypatch)

        [issue] = gh.criadas
        assert sorted(issue["labels"]) == ["needs-triage", "origem:diretor", "type:feature"]


class TestFraseDeResumo:
    def test_a_frase_do_agente_e_a_primeira_linha_do_corpo_do_bug(self, monkeypatch):
        client, _, gh = _cenario(monkeypatch)

        _card_do_bug(client, monkeypatch)

        assert _primeira_linha(gh.criadas[0]["corpo"]) == FRASE_DO_BUG

    def test_a_frase_do_agente_e_a_primeira_linha_do_corpo_da_melhoria(self, monkeypatch):
        client, sb, gh = _cenario(monkeypatch)

        _card_da_melhoria(client, sb, monkeypatch)

        assert _primeira_linha(gh.criadas[0]["corpo"]) == FRASE_DA_MELHORIA

    def test_o_bloco_para_o_diretor_continua_igual_com_a_frase_acima(self, monkeypatch):
        """A frase fica acima do cabeçalho: o bloco que volta para a tela do
        diretor não ganha nada (nada muda na tela dele)."""
        client, _, gh = _cenario(monkeypatch)

        _card_do_bug(client, monkeypatch)

        bloco = bloco_para_o_diretor(gh.criadas[0]["corpo"])
        assert bloco.startswith("**O que muda:** Ver o botão Responder no caso")
        assert FRASE_DO_BUG not in bloco

    # O resumo guardado antes desta versão não tem frase: o card nasce com o
    # título no lugar dela, que é o que o OS também faria.
    def test_sem_frase_do_agente_a_primeira_linha_do_bug_e_o_titulo(self, monkeypatch):
        client, _, gh = _cenario(monkeypatch)

        _card_do_bug(client, monkeypatch, frase=None)

        assert _primeira_linha(gh.criadas[0]["corpo"]) == "Botão de responder some na Ouvidoria"

    def test_sem_frase_do_agente_a_primeira_linha_da_melhoria_e_o_titulo(self, monkeypatch):
        client, sb, gh = _cenario(monkeypatch)

        _card_da_melhoria(client, sb, monkeypatch, frase=None)

        assert _primeira_linha(gh.criadas[0]["corpo"]) == "Agenda de retorno na recepção"


class TestLinkDaDemanda:
    @pytest.mark.parametrize("tipo", ["bug", "melhoria"])
    def test_o_corpo_leva_o_link_para_a_demanda_no_app(self, monkeypatch, tipo):
        monkeypatch.setattr(settings, "frontend_url", "https://app.hsm.exemplo")
        client, sb, gh = _cenario(monkeypatch)

        card = _card_do_bug(client, monkeypatch) if tipo == "bug" else _card_da_melhoria(client, sb, monkeypatch)

        link = f"https://app.hsm.exemplo/admin/tecnologia?demanda={card['demanda_id']}"
        assert f"Abrir a Demanda: {link}" in gh.criadas[0]["corpo"].splitlines()


class TestPeneiraNaFrase:
    @pytest.mark.parametrize("tipo", ["bug", "melhoria"])
    def test_o_dado_pessoal_dito_na_conversa_nao_aparece_na_frase(self, monkeypatch, tipo):
        """O modelo repete na frase o nome e o CPF que o diretor transcreveu:
        a peneira pública troca os dois por marcador antes do GitHub."""
        client, sb, gh = _cenario(monkeypatch)
        frase = f"A ficha de {NOME}, CPF {CPF}, não abre na Ouvidoria."

        if tipo == "bug":
            _card_do_bug(client, monkeypatch, frase=frase)
        else:
            _card_da_melhoria(client, sb, monkeypatch, frase=frase)

        primeira = _primeira_linha(gh.criadas[0]["corpo"])
        assert primeira == "A ficha de [NOME], CPF [CPF], não abre na Ouvidoria."
        for dado in (CPF, "maria", "ferreira"):
            assert dado not in gh.criadas[0]["corpo"].lower(), dado


FALA_DA_ENTREVISTA = "Lembrei agora que isso começou depois da reunião de terça com o pessoal da recepção"
PERGUNTA_DA_ENTREVISTA = "Quando você reparou que o botão sumiu pela primeira vez?"


class TestSemEntrevista:
    def test_o_corpo_do_bug_nao_traz_as_falas_da_conversa(self, monkeypatch):
        """A entrevista fica no app (ADR 0083, decisão 4): nem a pergunta do
        agente nem a fala do diretor vão para a issue, só o resumo e o link."""
        client, _, gh = _cenario(monkeypatch)
        demanda_id = _comecar(client, monkeypatch, mensagem=PERGUNTA_DA_ENTREVISTA)
        _ia(
            monkeypatch,
            _turno(pronto=True, mensagem="Montei o resumo.", campos=CAMPOS_RESPONDIDOS, criterios=CRITERIOS),
        )
        assert client.post(f"{CHAT}/{demanda_id}", json={"texto": FALA_DA_ENTREVISTA}).status_code == 200

        assert client.post(f"{CHAT}/{demanda_id}/criar-card").status_code == 200

        corpo = gh.criadas[0]["corpo"]
        for trecho in (PERGUNTA_DA_ENTREVISTA, FALA_DA_ENTREVISTA, "reunião de terça", "Montei o resumo"):
            assert trecho not in corpo, trecho

    def test_o_corpo_da_melhoria_nao_traz_a_fala_que_nao_decidiu_nada(self, monkeypatch):
        """No PRD entram as decisões que o diretor conferiu no resumo; a fala
        solta da entrevista, que não virou decisão, fica no app."""
        client, sb, gh = _cenario(monkeypatch)
        demanda_id = _abrir_pelo_botao(client, monkeypatch, contexto=PERGUNTA_DA_ENTREVISTA)["demanda_id"]
        [conversa] = _conversas(sb)
        conversa["mensagens"] = [
            *conversa["mensagens"],
            {"tipo": "resposta", "opcao": None, "texto": FALA_DA_ENTREVISTA},
        ]
        _ia(monkeypatch, _resumo_do_modelo(decisoes=[], frase=FRASE_DA_MELHORIA))
        assert client.post(f"{CHAT}/{demanda_id}/resumo").status_code == 200

        assert client.post(f"{CHAT}/{demanda_id}/criar-card").status_code == 200

        corpo = gh.criadas[0]["corpo"]
        for trecho in (PERGUNTA_DA_ENTREVISTA, FALA_DA_ENTREVISTA, "reunião de terça"):
            assert trecho not in corpo, trecho


class TestLabelNoRepositorio:
    def test_a_label_de_origem_esta_registrada_nas_labels_de_triagem(self):
        assert f"| `{LABEL_ORIGEM_DIRETOR}` |" in TRIAGE_LABELS.read_text(encoding="utf-8")
