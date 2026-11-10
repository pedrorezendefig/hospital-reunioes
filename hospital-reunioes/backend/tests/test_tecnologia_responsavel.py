"""O diretor escolhe o Responsável antes de "Criar o card" (issue #1533, PRD #1529, ADR 0083, decisão 5).

No resumo, "Quem cuida disto?" lista os Desenvolvedores (o Super admin com
login do GitHub no cadastro). O escolhido vira o Responsável da Demanda e o
assignee da issue; sem escolha, bug e melhoria nascem designados ao login do
dono que já está na configuração. A lista mostra o Responsável em cada linha e
o Desenvolvedor ganha o filtro "Para mim".

Tudo pela ROTA, com o modelo e o GitHub dublados no molde de `test_tecnologia_chat`.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from test_tecnologia_chat import (  # noqa: E402
    CHAT,
    _ate_o_resumo,
    _cenario,
    _demandas,
    _integracao_configurada,  # noqa: F401
    _llm_em_mock,  # noqa: F401
    _reset_rate_limiter,  # noqa: F401
)
from test_tecnologia_chat_melhoria import _ate_o_resumo as _ate_o_resumo_da_melhoria  # noqa: E402
from test_tecnologia_vinculo import BASE, DIRETOR, PEDRO, _demanda, _pessoa  # noqa: E402

from app.config import settings  # noqa: E402
from app.services.conhecimento import CONHECIMENTO_DIR  # noqa: E402

RIB = _pessoa("P4", "Pedro Rib", github_login="pedrorib")
LUCAS = _pessoa("P5", "Lucas Sampaio", github_login="lucas-sampaio")
# Tem login do GitHub, mas não é Super admin: não é Desenvolvedor.
ANALISTA = _pessoa("P6", "Analista de TI", github_login="analista-ti", access_profile="facilitador")

DESENVOLVEDORES = f"{BASE}/desenvolvedores"


def _participantes() -> list[dict]:
    return [PEDRO, DIRETOR, RIB, LUCAS, ANALISTA]


@pytest.fixture(autouse=True)
def _dono_na_configuracao(monkeypatch):
    monkeypatch.setattr(settings, "github_login_dono", "pedrorezendefig")


def _resumo(client, sb, monkeypatch, tipo: str) -> str:
    if tipo == "bug":
        return _ate_o_resumo(client, monkeypatch)
    return _ate_o_resumo_da_melhoria(client, sb, monkeypatch)


# ═══════════════════════════════════════════════════════════════════════════
# 1. O seletor "Quem cuida disto?"
# ═══════════════════════════════════════════════════════════════════════════


class TestSeletor:
    def test_o_seletor_lista_exatamente_os_super_admins_com_login_do_github(self, monkeypatch):
        client, _, _ = _cenario(monkeypatch, participantes=_participantes())

        resposta = client.get(DESENVOLVEDORES)

        assert resposta.status_code == 200, resposta.text
        assert resposta.json() == [
            {"id": "P5", "nome": "Lucas Sampaio", "padrao": False},
            {"id": "P4", "nome": "Pedro Rib", "padrao": False},
            {"id": "P1", "nome": "Pedro Vitta", "padrao": True},
        ]

    def test_o_padrao_e_quem_tem_o_login_do_dono_da_configuracao(self, monkeypatch):
        """A tela diz para quem vai o card sem escolha: o dono, pelo nome."""
        monkeypatch.setattr(settings, "github_login_dono", "Lucas-Sampaio")
        client, _, _ = _cenario(monkeypatch, participantes=_participantes())

        padrao = [d["nome"] for d in client.get(DESENVOLVEDORES).json() if d["padrao"]]

        assert padrao == ["Lucas Sampaio"]


# ═══════════════════════════════════════════════════════════════════════════
# 2. O assignee pedido ao GitHub
# ═══════════════════════════════════════════════════════════════════════════


class TestAssignee:
    @pytest.mark.parametrize("tipo", ["bug", "melhoria"])
    def test_com_responsavel_escolhido_o_assignee_e_o_login_dele(self, monkeypatch, tipo):
        client, sb, gh = _cenario(monkeypatch, participantes=_participantes())
        demanda_id = _resumo(client, sb, monkeypatch, tipo)

        resposta = client.post(f"{CHAT}/{demanda_id}/criar-card", json={"responsavel_id": "P5"})

        assert resposta.status_code == 200, resposta.text
        assert gh.criadas[0]["assignees"] == ["lucas-sampaio"]
        assert _demandas(sb)[0]["responsavel_id"] == "P5"

    @pytest.mark.parametrize("tipo", ["bug", "melhoria"])
    def test_sem_escolha_o_assignee_e_o_login_do_dono_e_o_card_nasce_sem_erro(self, monkeypatch, tipo):
        monkeypatch.setattr(settings, "github_login_dono", "lucas-sampaio")
        client, sb, gh = _cenario(monkeypatch, participantes=_participantes())
        demanda_id = _resumo(client, sb, monkeypatch, tipo)

        resposta = client.post(f"{CHAT}/{demanda_id}/criar-card")

        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["estado"] == "enviado"
        assert gh.criadas[0]["assignees"] == ["lucas-sampaio"]
        assert _demandas(sb)[0]["github_issue_numero"] == 900
        assert _demandas(sb)[0]["responsavel_id"] == "P5"

    def test_escolha_vazia_conta_como_sem_escolha(self, monkeypatch):
        client, sb, gh = _cenario(monkeypatch, participantes=_participantes())
        demanda_id = _resumo(client, sb, monkeypatch, "bug")

        resposta = client.post(f"{CHAT}/{demanda_id}/criar-card", json={"responsavel_id": None})

        assert resposta.status_code == 200, resposta.text
        assert gh.criadas[0]["assignees"] == ["pedrorezendefig"]

    @pytest.mark.parametrize("fora_da_lista", ["P2", "P6", "nao-existe"])
    def test_quem_nao_e_desenvolvedor_nao_vira_responsavel(self, monkeypatch, fora_da_lista):
        client, sb, gh = _cenario(monkeypatch, participantes=_participantes())
        demanda_id = _resumo(client, sb, monkeypatch, "bug")

        resposta = client.post(f"{CHAT}/{demanda_id}/criar-card", json={"responsavel_id": fora_da_lista})

        assert resposta.status_code == 422, resposta.text
        assert gh.criadas == []
        assert _demandas(sb)[0].get("github_issue_numero") is None


# ═══════════════════════════════════════════════════════════════════════════
# 3. As labels de sempre
# ═══════════════════════════════════════════════════════════════════════════


class TestLabels:
    @pytest.mark.parametrize(
        ("tipo", "labels"),
        [
            ("bug", ["origem:diretor", "ready-for-agent", "type:fix"]),
            ("melhoria", ["needs-triage", "origem:diretor", "type:feature"]),
        ],
    )
    def test_com_responsavel_o_bug_nasce_pronto_e_a_melhoria_na_triagem(self, monkeypatch, tipo, labels):
        client, sb, gh = _cenario(monkeypatch, participantes=_participantes())
        demanda_id = _resumo(client, sb, monkeypatch, tipo)

        assert client.post(f"{CHAT}/{demanda_id}/criar-card", json={"responsavel_id": "P4"}).status_code == 200

        assert sorted(gh.criadas[0]["labels"]) == labels
        assert gh.criadas[0]["assignees"] == ["pedrorib"]


# ═══════════════════════════════════════════════════════════════════════════
# 4. A lista
# ═══════════════════════════════════════════════════════════════════════════


def _demandas_com_responsavel() -> list[dict]:
    return [
        _demanda(
            "d-rib",
            titulo="O relatório some",
            autor_id=DIRETOR["id"],
            responsavel_id=RIB["id"],
            github_issue_numero=910,
            etapa="em_analise",
            criado_em="2026-11-03T10:00:00Z",
        ),
        _demanda(
            "d-pedro",
            titulo="Agenda de retorno",
            autor_id=DIRETOR["id"],
            responsavel_id=PEDRO["id"],
            github_issue_numero=911,
            etapa="em_analise",
            criado_em="2026-11-02T10:00:00Z",
        ),
        # Conversa sem card, de antes desta versão: o Responsável que o
        # Produto punha no nascimento não conta, porque ninguém escolheu.
        _demanda(
            "d-registrada",
            titulo="Conversa no meio",
            autor_id=DIRETOR["id"],
            responsavel_id=PEDRO["id"],
            criado_em="2026-11-01T10:00:00Z",
        ),
    ]


class TestLista:
    @pytest.mark.parametrize("logado", [DIRETOR, PEDRO], ids=["diretor", "desenvolvedor"])
    def test_o_responsavel_aparece_em_cada_linha(self, monkeypatch, logado):
        client, _, _ = _cenario(
            monkeypatch, logado=logado, participantes=_participantes(), demandas=_demandas_com_responsavel()
        )

        resposta = client.get(f"{CHAT}?filtro=todas")

        assert resposta.status_code == 200, resposta.text
        assert [(d["id"], d["responsavel"]) for d in resposta.json()] == [
            ("d-rib", "Pedro Rib"),
            ("d-pedro", "Pedro Vitta"),
            ("d-registrada", None),
        ]

    def test_para_mim_mostra_so_as_demandas_de_que_o_desenvolvedor_e_responsavel(self, monkeypatch):
        client, _, _ = _cenario(
            monkeypatch, logado=PEDRO, participantes=_participantes(), demandas=_demandas_com_responsavel()
        )

        resposta = client.get(f"{CHAT}?filtro=para_mim")

        assert resposta.status_code == 200, resposta.text
        assert [d["id"] for d in resposta.json()] == ["d-pedro"]


# ═══════════════════════════════════════════════════════════════════════════
# 5. O Kit de conhecimento
# ═══════════════════════════════════════════════════════════════════════════


class TestKit:
    def test_o_kit_diz_o_comportamento_novo_do_responsavel(self):
        """O Assistente fala com o diretor pela língua do Kit: sem a regra
        escrita, ele diria que o card vai sempre para o Pedro."""
        texto = (CONHECIMENTO_DIR / "tecnologia.md").read_text(encoding="utf-8")
        decidido = texto.split("## O que já foi decidido", 1)[1]
        quem_ve = texto.split("## Quem vê", 1)[1].split("\n## ", 1)[0]

        for trecho in ("Quem cuida disto?", "Pedro Rezende", "Pedro Rib", "Lucas Sampaio", "opcional"):
            assert trecho in texto, trecho
        assert "Quem cuida disto?" in decidido
        for trecho in ("Para mim", "Responsável"):
            assert trecho in quem_ve, trecho
        assert "chega primeiro ao Pedro" not in texto
