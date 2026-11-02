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
