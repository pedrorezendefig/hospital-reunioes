"""O chat da Tecnologia com o Roteiro do bug, ponta a ponta (issue #1381, PRD #1380, ADR 0077).

A aba abre no chat do Assistente de Tecnologia: "bug ou melhoria?", dois botões
e um campo livre. A Demanda nasce no primeiro turno, o bug segue o Roteiro do
bug (no máximo cinco perguntas, uma por vez) e termina num resumo com "Criar o
card" e "Não bateu". Tudo pela ROTA, com o modelo e o GitHub dublados no molde
de `test_planejamento_demanda` e `test_tecnologia_vinculo`: nenhum teste chega
à Anthropic nem ao GitHub de verdade.
"""

from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from test_planejamento_demanda import _ia  # noqa: E402
from test_tecnologia_anexos import PNG, _StorageFake  # noqa: E402
from test_tecnologia_vinculo import BASE, DIRETOR, _montar  # noqa: E402

from app.config import settings  # noqa: E402
from app.limiter import limiter  # noqa: E402
from app.services import tecnologia_anexos  # noqa: E402

CHAT = f"{BASE}/chat"

PRODUTOS = [
    {"id": "prod-1", "nome": "Reuniões", "ativo": True, "ordem": 1, "dono_id": "P1"},
    {"id": "prod-2", "nome": "Ouvidoria", "ativo": True, "ordem": 2, "dono_id": "P1"},
]


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


@pytest.fixture(autouse=True)
def _llm_em_mock(monkeypatch):
    """O pytest carrega o `.env` real (chave de PROD): sem isto, o teste que
    esquecesse de dublar o modelo chamaria o provedor de verdade."""
    from app.services import ai_processor

    monkeypatch.setattr(ai_processor, "_llm_provider", lambda: "mock")
    yield


@pytest.fixture(autouse=True)
def _integracao_configurada(monkeypatch):
    monkeypatch.setattr(settings, "github_integracao_token", "token-de-teste")
    monkeypatch.setattr(settings, "github_integracao_repo", "pedrorezendefig/hospital-reunioes")


def _cenario(monkeypatch, *, logado=DIRETOR, **kw):
    client, sb, gh = _montar(logado=logado, monkeypatch=monkeypatch, **kw)
    sb.tabelas["tecnologia_produtos"] = [dict(p) for p in PRODUTOS]
    sb.storage = _StorageFake()
    return client, sb, gh


def _turno(**campos) -> str:
    """A resposta do modelo para um turno do chat, em JSON."""
    base = {
        "classificacao": "bug",
        "confirmada": True,
        "produto_id": "prod-2",
        "titulo": "Botão de responder some na Ouvidoria",
        "mensagem": "Onde isso aconteceu?",
        "fonte": None,
        "opcoes": [],
        "campos": {"onde": None, "o_que_aconteceu": None, "o_que_esperava": None, "como_repetir": None},
        "criterios": [],
        "pronto": False,
    }
    base.update(campos)
    return json.dumps(base, ensure_ascii=False)


def _demandas(sb) -> list[dict]:
    return sb.tabelas["tecnologia_demandas"]


def _conversas(sb) -> list[dict]:
    return sb.tabelas.setdefault("tecnologia_planejamentos", [])


def _chamadas(sb) -> list[dict]:
    return sb.tabelas.setdefault("tecnologia_chamadas_ia", [])


# ═══════════════════════════════════════════════════════════════════════════
# 1. O primeiro turno: a Demanda nasce
# ═══════════════════════════════════════════════════════════════════════════


class TestPrimeiroTurno:
    def test_o_botao_bug_faz_nascer_a_demanda_defeito_no_produto_do_agente(self, monkeypatch):
        client, sb, _ = _cenario(monkeypatch)
        _ia(monkeypatch, _turno())

        resposta = client.post(CHAT, json={"escolha": "bug"})

        assert resposta.status_code == 201, resposta.text
        [demanda] = _demandas(sb)
        assert demanda["tipo"] == "defeito"
        assert demanda["produto_id"] == "prod-2"
        assert demanda["titulo"] == "Botão de responder some na Ouvidoria"
        assert demanda["estado"] == "nova"
        assert demanda["autor_id"] == DIRETOR["id"]
        corpo = resposta.json()
        assert corpo["demanda_id"] == demanda["id"]
        assert corpo["estado"] == "em_andamento"
        assert [m["autor"] for m in corpo["mensagens"]] == ["ia", "diretor", "ia"]
        assert corpo["mensagens"][-1]["texto"] == "Onde isso aconteceu?"
        # A conversa fica guardada na Demanda, para não se perder.
        [conversa] = _conversas(sb)
        assert conversa["demanda_id"] == demanda["id"]
        assert len(conversa["mensagens"]) == 3


CONFIRMAR = ["Sim, é um bug", "Não, é uma melhoria"]


def _comecar(client, monkeypatch, **campos_do_modelo):
    """O primeiro turno pelo botão "Bug", e a Demanda que ele fez nascer."""
    _ia(monkeypatch, _turno(**campos_do_modelo))
    resposta = client.post(CHAT, json={"escolha": "bug"})
    assert resposta.status_code == 201, resposta.text
    return resposta.json()["demanda_id"]


class TestDescricaoLivre:
    def test_o_assistente_classifica_e_confirma_antes_de_seguir(self, monkeypatch):
        """O modelo já quer fechar o resumo, mas o diretor ainda não confirmou
        que é um bug: o roteiro não começa, e a pergunta de confirmação vem com
        os dois botões."""
        client, sb, _ = _cenario(monkeypatch)
        _ia(
            monkeypatch,
            _turno(
                confirmada=False,
                mensagem="Pelo que você contou, é um bug na Ouvidoria. É isso?",
                opcoes=CONFIRMAR,
                pronto=True,
                campos={"onde": "Ouvidoria", "o_que_aconteceu": "O botão sumiu"},
            ),
        )

        resposta = client.post(CHAT, json={"texto": "O botão de responder sumiu da Ouvidoria"})

        assert resposta.status_code == 201, resposta.text
        corpo = resposta.json()
        assert corpo["estado"] == "em_andamento"
        assert corpo["resumo"] is None
        assert corpo["mensagens"][-1]["opcoes"] == CONFIRMAR
        assert _demandas(sb)[0]["tipo"] == "defeito"

    def test_a_melhoria_classificada_faz_nascer_a_demanda_novo(self, monkeypatch):
        client, sb, _ = _cenario(monkeypatch)
        _ia(monkeypatch, _turno(classificacao="melhoria", confirmada=False, opcoes=["Sim", "Não"]))

        assert client.post(CHAT, json={"texto": "Queria um aviso quando a ata sair"}).status_code == 201

        assert _demandas(sb)[0]["tipo"] == "novo"

    def test_confirmado_o_bug_vem_a_primeira_pergunta_do_roteiro(self, monkeypatch):
        client, sb, _ = _cenario(monkeypatch)
        _ia(monkeypatch, _turno(confirmada=False, opcoes=CONFIRMAR))
        demanda_id = client.post(CHAT, json={"texto": "O botão sumiu"}).json()["demanda_id"]
        _ia(monkeypatch, _turno(confirmada=True, mensagem="Em que tela isso aconteceu?"))

        resposta = client.post(f"{CHAT}/{demanda_id}", json={"texto": "Sim, é um bug"})

        assert resposta.status_code == 200, resposta.text
        falas = resposta.json()["mensagens"]
        assert [f["texto"] for f in falas[-2:]] == ["Sim, é um bug", "Em que tela isso aconteceu?"]
        assert len(_conversas(sb)[0]["mensagens"]) == 5


class TestDuvidaRespondidaPeloKit:
    def test_a_duvida_respondida_diz_de_onde_veio_e_nao_cria_card(self, monkeypatch):
        client, sb, gh = _cenario(monkeypatch)
        _ia(
            monkeypatch,
            _turno(
                confirmada=False,
                fonte="Reuniões",
                mensagem="Pelo material da Vitta sobre Reuniões, a ata sai em PDF depois da assinatura. Resolveu?",
            ),
        )

        resposta = client.post(CHAT, json={"texto": "Como eu baixo a ata em PDF?"})

        assert resposta.status_code == 201, resposta.text
        corpo = resposta.json()
        assert corpo["mensagens"][-1]["fonte"] == "Reuniões"
        assert corpo["resumo"] is None
        # Sem resumo não há card: o botão "Criar o card" é recusado, e nada
        # chega ao GitHub.
        criar = client.post(f"{CHAT}/{corpo['demanda_id']}/criar-card")
        assert criar.status_code == 409
        assert gh.criadas == []
        assert _demandas(sb)[0].get("github_issue_numero") is None


@pytest.fixture
def _visao_dublada(monkeypatch):
    """A leitura do print fica de fora: o que se prova aqui é o que o app
    guarda, e não o que o modelo enxerga."""
    from app.services import assistente_tecnologia

    monkeypatch.setattr(assistente_tecnologia, "descrever_imagem", lambda **kw: "Tela da Ouvidoria sem o botão.")
    tecnologia_anexos.esquecer_prints()
    yield
    tecnologia_anexos.esquecer_prints()


def _print_lido(client) -> dict:
    resposta = client.post(
        f"{BASE}/assistente/descrever-imagem", files={"imagem": ("Captura de tela.png", PNG, "image/png")}
    )
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


@pytest.mark.usefixtures("_visao_dublada")
class TestPrintNoChat:
    def test_o_print_mandado_no_chat_vira_anexo_da_demanda_na_hora(self, monkeypatch):
        client, sb, _ = _cenario(monkeypatch)
        demanda_id = _comecar(client, monkeypatch, mensagem="Tem um print da tela?")
        lido = _print_lido(client)
        _ia(monkeypatch, _turno(mensagem="Obrigado. Como repetir o problema?"))

        resposta = client.post(
            f"{CHAT}/{demanda_id}", json={"texto": f"[print] {lido['texto']}", "prints": [lido["print_id"]]}
        )

        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["anexos"] == 1
        [anexo] = sb.tabelas["tecnologia_anexos"]
        assert anexo["demanda_id"] == demanda_id
        assert sb.storage.arquivos == {f"anexos-tecnologia/{anexo['storage_path']}": PNG}

    def test_o_print_do_primeiro_turno_vira_anexo_da_demanda_que_nasceu(self, monkeypatch):
        client, sb, _ = _cenario(monkeypatch)
        lido = _print_lido(client)
        _ia(monkeypatch, _turno())

        resposta = client.post(CHAT, json={"escolha": "bug", "texto": f"[print] {lido['texto']}", "prints": [lido["print_id"]]})

        assert resposta.status_code == 201, resposta.text
        [anexo] = sb.tabelas["tecnologia_anexos"]
        assert anexo["demanda_id"] == resposta.json()["demanda_id"]


# ═══════════════════════════════════════════════════════════════════════════
# 2. O Roteiro do bug e o resumo
# ═══════════════════════════════════════════════════════════════════════════

CAMPOS_RESPONDIDOS = {
    "onde": "Ouvidoria, no caso aberto",
    "o_que_aconteceu": "O botão Responder sumiu",
    "o_que_esperava": "Ver o botão Responder no caso",
    "como_repetir": None,
}
CRITERIOS = ["O botão Responder aparece no caso aberto da Ouvidoria"]


def _responder(client, monkeypatch, demanda_id: str, texto: str, **campos_do_modelo):
    _ia(monkeypatch, _turno(**campos_do_modelo))
    resposta = client.post(f"{CHAT}/{demanda_id}", json={"texto": texto})
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


def _ate_o_resumo(client, monkeypatch) -> str:
    """Um bug inteiro: a primeira pergunta e o resumo logo na resposta."""
    demanda_id = _comecar(client, monkeypatch)
    corpo = _responder(
        client,
        monkeypatch,
        demanda_id,
        "Na Ouvidoria, o botão Responder sumiu",
        pronto=True,
        mensagem="Montei o resumo. Confere?",
        campos=CAMPOS_RESPONDIDOS,
        criterios=CRITERIOS,
    )
    assert corpo["estado"] == "resumido"
    return demanda_id


class TestRoteiroDoBug:
    def test_o_roteiro_para_na_quinta_pergunta_e_monta_o_resumo(self, monkeypatch):
        """Respondidas as cinco, o modelo ainda quer perguntar: a sexta não
        sai, e o resumo nasce do que o diretor já disse."""
        client, _, _ = _cenario(monkeypatch)
        demanda_id = _comecar(client, monkeypatch, mensagem="Pergunta 1?")
        for n in range(2, 6):
            corpo = _responder(client, monkeypatch, demanda_id, f"Resposta {n - 1}", mensagem=f"Pergunta {n}?")
            assert corpo["estado"] == "em_andamento"

        corpo = _responder(
            client, monkeypatch, demanda_id, "Resposta 5", mensagem="Pergunta 6?", campos=CAMPOS_RESPONDIDOS
        )

        assert corpo["estado"] == "resumido"
        perguntas = [m["texto"] for m in corpo["mensagens"] if m["autor"] == "ia" and m["texto"].startswith("Pergunta")]
        assert perguntas == ["Pergunta 1?", "Pergunta 2?", "Pergunta 3?", "Pergunta 4?", "Pergunta 5?"]
        assert corpo["resumo"]["onde"] == "Ouvidoria, no caso aberto"
        # Rótulo sem resposta sai "não informado", e o critério vem do que ele esperava.
        assert corpo["resumo"]["como_repetir"] == "não informado"
        assert corpo["resumo"]["criterios"] == ["Ver o botão Responder no caso"]

    def test_o_resumo_traz_o_que_o_diretor_disse_e_os_criterios(self, monkeypatch):
        client, _, _ = _cenario(monkeypatch)

        demanda_id = _ate_o_resumo(client, monkeypatch)

        resumo = client.get(f"{CHAT}/{demanda_id}").json()["resumo"]
        assert resumo == {
            "titulo": "Botão de responder some na Ouvidoria",
            "onde": "Ouvidoria, no caso aberto",
            "o_que_aconteceu": "O botão Responder sumiu",
            "o_que_esperava": "Ver o botão Responder no caso",
            "como_repetir": "não informado",
            "criterios": CRITERIOS,
        }

    def test_com_o_resumo_na_tela_a_conversa_espera_o_clique(self, monkeypatch):
        client, _, _ = _cenario(monkeypatch)
        demanda_id = _ate_o_resumo(client, monkeypatch)

        resposta = client.post(f"{CHAT}/{demanda_id}", json={"texto": "mais uma coisa"})

        assert resposta.status_code == 409

