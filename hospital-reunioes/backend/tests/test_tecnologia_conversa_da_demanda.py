"""A Conversa da Demanda, com menção e aviso no sino (issue #1537, PRD #1529, ADR 0083, decisão 8).

A troca de mensagens entre o diretor e os Desenvolvedores dentro de uma
Demanda: tabela própria, separada da conversa com o agente, e que nunca vai
para o GitHub. Escreve e lê quem vê a Demanda (o `pode_ver`, a mesma regra da
lista). Menção é por nome, no formato dos comentários de Pendência
("@Nome Completo"). O aviso sai pelo sino:

- menção avisa o mencionado;
- sem menção, a mensagem do autor da Demanda avisa o Responsável, e a do
  Desenvolvedor avisa o autor;
- ninguém é avisado da própria mensagem.

Tudo pela ROTA, no molde de `test_tecnologia_desenvolvedor`.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from test_tecnologia_vinculo import BASE, DIRETOR, PEDRO, _demanda, _montar, _pessoa  # noqa: E402

from app.limiter import limiter  # noqa: E402

# Outro Desenvolvedor da Vitta e outra pessoa da diretoria (Super admin sem
# login do GitHub, que não vê a Demanda do DIRETOR).
LUCAS = _pessoa("P4", "Lucas Sampaio", github_login="lucas-vitta")
OUTRO_DIRETOR = _pessoa("P3", "Outro Diretor")

DEMANDA = "d-1"
CONVERSA = f"{BASE}/chat/{DEMANDA}/conversa"


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


def _demanda_do_diretor(**campos) -> dict:
    """A Demanda do DIRETOR, já com card, de que o PEDRO é o Responsável."""
    base = {"autor_id": DIRETOR["id"], "responsavel_id": PEDRO["id"], "github_issue_numero": 900}
    base.update(campos)
    return _demanda(DEMANDA, titulo="O relatório some", **base)


def _cenario(monkeypatch, *, logado: dict, demanda: dict | None = None, sb=None):
    client, sb, _ = _montar(
        logado=logado,
        participantes=[PEDRO, DIRETOR, OUTRO_DIRETOR, LUCAS],
        demandas=[demanda or _demanda_do_diretor()],
        supabase=sb,
        monkeypatch=monkeypatch,
    )
    return client, sb


def _avisos(sb) -> list[tuple[str, str]]:
    """(destinatário, referência) de cada aviso do sino gravado."""
    return [(n["destinatario_id"], n["referencia_id"]) for n in sb.tabelas.get("notificacoes", [])]


# ═══════════════════════════════════════════════════════════════════════════
# 1. Quem escreve e lê
# ═══════════════════════════════════════════════════════════════════════════


class TestQuemEscreveELe:
    def test_o_autor_e_o_desenvolvedor_escrevem_e_leem_a_conversa(self, monkeypatch):
        diretor, sb = _cenario(monkeypatch, logado=DIRETOR)
        pedro, _ = _cenario(monkeypatch, logado=PEDRO, sb=sb)

        assert diretor.post(CONVERSA, json={"texto": "O relatório sumiu de novo hoje."}).status_code == 201
        assert pedro.post(CONVERSA, json={"texto": "Vi aqui, olho amanhã cedo."}).status_code == 201

        for client in (diretor, pedro):
            resposta = client.get(CONVERSA)
            assert resposta.status_code == 200, resposta.text
            assert [(m["autor"], m["texto"]) for m in resposta.json()["mensagens"]] == [
                ("Diretor do Hospital", "O relatório sumiu de novo hoje."),
                ("Pedro Vitta", "Vi aqui, olho amanhã cedo."),
            ]
