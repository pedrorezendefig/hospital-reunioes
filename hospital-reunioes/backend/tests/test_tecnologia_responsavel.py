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
            {"id": "P5", "nome": "Lucas Sampaio"},
            {"id": "P4", "nome": "Pedro Rib"},
            {"id": "P1", "nome": "Pedro Vitta"},
        ]


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
