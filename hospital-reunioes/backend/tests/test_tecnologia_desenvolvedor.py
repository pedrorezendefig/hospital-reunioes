"""O Desenvolvedor vê as Demandas de todos, com a entrevista inteira (issue #1531, PRD #1529, ADR 0083).

Desenvolvedor é o Super admin com login do GitHub no cadastro (ADR 0083,
decisão 2): não é perfil novo. A regra de quem vê uma Demanda é uma só, usada
pela lista e pela leitura da conversa: o autor vê as dele, o Desenvolvedor vê
todas. O diretor (Super admin sem login do GitHub) segue vendo só as dele, sem
número nem link da issue.

Tudo pela ROTA, no molde de `test_tecnologia_chat`: o modelo e o GitHub ficam
dublados.
"""

from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from test_tecnologia_anexos import PNG  # noqa: E402
from test_tecnologia_chat import CHAT, _cenario, _comecar  # noqa: E402
from test_tecnologia_vinculo import BASE, DIRETOR, PEDRO, _demanda, _montar, _pessoa  # noqa: E402

from app.config import settings  # noqa: E402
from app.limiter import limiter  # noqa: E402
from app.services import ai_processor, tecnologia_anexos  # noqa: E402
from app.services.conhecimento import CONHECIMENTO_DIR  # noqa: E402

# Outra pessoa da diretoria: Super admin, sem login do GitHub.
OUTRO_DIRETOR = _pessoa("P3", "Outro Diretor")

TODAS = f"{CHAT}?filtro=todas"


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


@pytest.fixture(autouse=True)
def _llm_em_mock(monkeypatch):
    monkeypatch.setattr(ai_processor, "_llm_provider", lambda: "mock")
    yield


@pytest.fixture(autouse=True)
def _integracao_configurada(monkeypatch):
    monkeypatch.setattr(settings, "github_integracao_token", "token-de-teste")
    monkeypatch.setattr(settings, "github_integracao_repo", "pedrorezendefig/hospital-reunioes")


def _demandas_de_dois_autores() -> list[dict]:
    return [
        _demanda(
            "d-diretor", titulo="O relatório some", autor_id=DIRETOR["id"], criado_em="2026-11-01T10:00:00Z", numero=41
        ),
        _demanda(
            "d-pedro", titulo="Pedido da Vitta", autor_id=PEDRO["id"], criado_em="2026-11-02T10:00:00Z", numero=42
        ),
        _demanda(
            "d-outro",
            numero=7,
            titulo="O botão sumiu",
            autor_id=OUTRO_DIRETOR["id"],
            criado_em="2026-10-15T10:00:00Z",
            github_issue_numero=912,
            github_foto={"numero": 912, "url": "https://github.com/pedrorezendefig/hospital-reunioes/issues/912"},
            etapa="em_desenvolvimento",
        ),
    ]


def _participantes() -> list[dict]:
    return [PEDRO, DIRETOR, OUTRO_DIRETOR]


def _conversa_do_diretor_com_print(monkeypatch):
    """O diretor conversa com o agente e manda um print; devolve o banco e o id."""
    client, sb, _ = _cenario(monkeypatch, logado=DIRETOR, participantes=_participantes())
    demanda_id = _comecar(client, monkeypatch, mensagem="Onde isso aconteceu?")
    demanda = next(d for d in sb.tabelas["tecnologia_demandas"] if d["id"] == demanda_id)
    tecnologia_anexos.anexar(sb, demanda=demanda, nome="tela.png", conteudo=PNG, quem_id=DIRETOR["id"])
    return sb, demanda_id


def _como(logado: dict, sb, monkeypatch):
    client, _, _ = _montar(logado=logado, supabase=sb, monkeypatch=monkeypatch)
    return client


# ═══════════════════════════════════════════════════════════════════════════
# 1. A lista
# ═══════════════════════════════════════════════════════════════════════════


class TestListaDoDesenvolvedor:
    def test_o_desenvolvedor_lista_as_demandas_de_todos_com_o_autor_em_cada_linha(self, monkeypatch):
        client, _, _ = _cenario(
            monkeypatch, logado=PEDRO, participantes=_participantes(), demandas=_demandas_de_dois_autores()
        )

        resposta = client.get(TODAS)

        assert resposta.status_code == 200, resposta.text
        assert [(d["titulo"], d["autor"]) for d in resposta.json()] == [
            ("Pedido da Vitta", "Pedro Vitta"),
            ("O relatório some", "Diretor do Hospital"),
            ("O botão sumiu", "Outro Diretor"),
        ]

    def test_sem_o_filtro_a_lista_do_desenvolvedor_traz_so_as_dele(self, monkeypatch):
        client, _, _ = _cenario(
            monkeypatch, logado=PEDRO, participantes=_participantes(), demandas=_demandas_de_dois_autores()
        )

        assert [d["titulo"] for d in client.get(CHAT).json()] == ["Pedido da Vitta"]

    def test_so_a_demanda_do_proprio_desenvolvedor_sai_como_minha_na_lista_de_todas(self, monkeypatch):
        """`minha` é o que faz a tela abrir a Demanda de outro autor no
        Acompanhamento, com os Anexos e sem a caixa de responder."""
        client, _, _ = _cenario(
            monkeypatch, logado=PEDRO, participantes=_participantes(), demandas=_demandas_de_dois_autores()
        )

        por_id = {d["id"]: d["minha"] for d in client.get(TODAS).json()}

        assert por_id == {"d-pedro": True, "d-diretor": False, "d-outro": False}

    def test_super_admin_sem_login_do_github_lista_so_as_proprias_mesmo_pedindo_todas(self, monkeypatch):
        client, _, _ = _cenario(
            monkeypatch, logado=DIRETOR, participantes=_participantes(), demandas=_demandas_de_dois_autores()
        )

        resposta = client.get(TODAS)

        assert resposta.status_code == 200, resposta.text
        assert [d["titulo"] for d in resposta.json()] == ["O relatório some"]

    def test_o_desenvolvedor_ve_o_numero_e_o_link_da_issue_na_demanda_com_card(self, monkeypatch):
        client, _, _ = _cenario(
            monkeypatch, logado=PEDRO, participantes=_participantes(), demandas=_demandas_de_dois_autores()
        )

        por_id = {d["id"]: d for d in client.get(TODAS).json()}

        assert por_id["d-outro"]["issue_numero"] == 912
        assert por_id["d-outro"]["issue_url"] == "https://github.com/pedrorezendefig/hospital-reunioes/issues/912"
        assert por_id["d-diretor"]["issue_numero"] is None
        assert por_id["d-diretor"]["issue_url"] is None

    def test_a_lista_entregue_ao_diretor_nao_traz_numero_nem_link_da_issue(self, monkeypatch):
        client, _, _ = _cenario(
            monkeypatch, logado=OUTRO_DIRETOR, participantes=_participantes(), demandas=_demandas_de_dois_autores()
        )

        [item] = client.get(TODAS).json()

        assert item["id"] == "d-outro"
        assert item["tem_vinculo"] is True
        assert "github.com" not in json.dumps(item)
        assert "912" not in json.dumps(item)

    def test_o_diretor_ve_o_numero_da_demanda_na_lista_sem_o_numero_da_issue(self, monkeypatch):
        """O Número da Demanda (issue #1585) é de todo mundo que vê a Demanda;
        o da issue continua só do Desenvolvedor (ADR 0054, decisão 9)."""
        client, _, _ = _cenario(
            monkeypatch, logado=OUTRO_DIRETOR, participantes=_participantes(), demandas=_demandas_de_dois_autores()
        )

        [item] = client.get(TODAS).json()

        assert item["numero"] == 7
        assert item["issue_numero"] is None

    def test_o_desenvolvedor_ve_o_numero_da_demanda_e_o_da_issue_lado_a_lado(self, monkeypatch):
        client, _, _ = _cenario(
            monkeypatch, logado=PEDRO, participantes=_participantes(), demandas=_demandas_de_dois_autores()
        )

        por_id = {d["id"]: (d["numero"], d["issue_numero"]) for d in client.get(TODAS).json()}

        assert por_id == {"d-pedro": (42, None), "d-diretor": (41, None), "d-outro": (7, 912)}


# ═══════════════════════════════════════════════════════════════════════════
# 2. Quem sou na aba
# ═══════════════════════════════════════════════════════════════════════════


class TestQuemSou:
    """A tela pergunta ao servidor se quem está logado é Desenvolvedor, e só
    então mostra o filtro "Todas": a regra fica num lugar só, no backend."""

    def test_o_super_admin_com_login_do_github_e_desenvolvedor(self, monkeypatch):
        client, _, _ = _cenario(monkeypatch, logado=PEDRO)

        assert client.get(f"{BASE}/eu").json() == {"desenvolvedor": True}

    def test_o_super_admin_sem_login_do_github_nao_e(self, monkeypatch):
        client, _, _ = _cenario(monkeypatch, logado=DIRETOR)

        assert client.get(f"{BASE}/eu").json() == {"desenvolvedor": False}


# ═══════════════════════════════════════════════════════════════════════════
# 3. A leitura de uma conversa
# ═══════════════════════════════════════════════════════════════════════════


class TestLeituraDaConversa:
    def test_o_desenvolvedor_abre_a_demanda_de_outro_autor_e_le_a_entrevista_e_os_anexos(self, monkeypatch):
        sb, demanda_id = _conversa_do_diretor_com_print(monkeypatch)

        resposta = _como(PEDRO, sb, monkeypatch).get(f"{CHAT}/{demanda_id}")

        assert resposta.status_code == 200, resposta.text
        conversa = resposta.json()
        assert [(f["autor"], f["texto"]) for f in conversa["mensagens"]][-1] == ("ia", "Onde isso aconteceu?")
        assert any(f["autor"] == "diretor" for f in conversa["mensagens"])
        [anexo] = conversa["anexos_da_demanda"]
        assert anexo["nome"] == "tela.png"
        assert anexo["url"].startswith("https://storage.local/")

    def test_super_admin_sem_login_do_github_recebe_recusa_ao_abrir_a_de_outro_autor(self, monkeypatch):
        sb, demanda_id = _conversa_do_diretor_com_print(monkeypatch)

        resposta = _como(OUTRO_DIRETOR, sb, monkeypatch).get(f"{CHAT}/{demanda_id}")

        assert resposta.status_code == 404, resposta.text
        assert "mensagens" not in resposta.text

    def test_o_autor_le_a_propria_conversa_sem_a_lista_dos_anexos(self, monkeypatch):
        sb, demanda_id = _conversa_do_diretor_com_print(monkeypatch)

        resposta = _como(DIRETOR, sb, monkeypatch).get(f"{CHAT}/{demanda_id}")

        assert resposta.status_code == 200, resposta.text
        conversa = resposta.json()
        assert conversa["anexos"] == 1
        assert conversa["anexos_da_demanda"] == []
        assert "storage.local" not in resposta.text

    @pytest.mark.parametrize("logado", [DIRETOR, PEDRO], ids=["autor", "desenvolvedor"])
    def test_o_detalhe_da_demanda_traz_o_numero_da_demanda(self, monkeypatch, logado):
        """O número vem do banco no insert (issue #1585); aqui o banco falso
        não tem a sequence, e o teste o grava como o default gravaria."""
        sb, demanda_id = _conversa_do_diretor_com_print(monkeypatch)
        next(d for d in sb.tabelas["tecnologia_demandas"] if d["id"] == demanda_id)["numero"] = 42

        resposta = _como(logado, sb, monkeypatch).get(f"{CHAT}/{demanda_id}")

        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["numero"] == 42


# ═══════════════════════════════════════════════════════════════════════════
# 4. O Kit de conhecimento
# ═══════════════════════════════════════════════════════════════════════════


class TestKit:
    def test_o_kit_diz_que_o_desenvolvedor_ve_as_demandas_de_todos(self):
        """O Assistente fala com o diretor pela língua do Kit: sem a regra
        escrita, ele diria que ninguém da Vitta lê a conversa."""
        texto = (CONHECIMENTO_DIR / "tecnologia.md").read_text(encoding="utf-8")

        secao = texto.split("## Quem vê", 1)[1].split("\n## ", 1)[0]
        for trecho in ("Desenvolvedor", "login do GitHub", "Demandas de todos", "as próprias conversas", "Todas"):
            assert trecho in secao, trecho
