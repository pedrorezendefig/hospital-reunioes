"""A passada única do bloco "Para o desenvolvedor" (issue #1636, PRD #1632).

As Demandas abertas de hoje, da Origem "Pedido do diretor", ganham o bloco que
o card novo já traz (issue #1633). Um comando de uma vez só lista as Demandas
sem o bloco, pede as seis partes ao modelo pela conversa com o agente e pelo
corpo da issue, e insere a seção logo depois do bloco "Para o diretor".

Aqui: o comando inteiro, com o banco, o modelo e o GitHub de mentira. Nenhuma
chamada real a IA nem ao GitHub.
"""

from __future__ import annotations

import json
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from test_tecnologia_vinculo import _demanda, _SupabaseMock  # noqa: E402

from app.services import ai_processor, email_service, github_client  # noqa: E402
from scripts.oneshot import bloco_do_desenvolvedor_nas_demandas as passada_unica  # noqa: E402

PARTES = {
    "o_que_o_diretor_quer": "A recepção marca o retorno do paciente na saída.",
    "por_que_ele_pediu": "Hoje o retorno é anotado no papel e se perde.",
    "o_que_ja_ficou_decidido": "Só a recepção marca o retorno.",
    "onde_mexe_no_codigo": "A tela da recepção e o serviço de agenda.",
    "cuidados": "O aviso por WhatsApp tem limite diário.",
    "como_saber_que_acabou": "A recepção marca um retorno e ele aparece na agenda.",
}

# O bloco que a issue deve ganhar com as PARTES acima, escrito à mão.
BLOCO_ESPERADO = (
    "## 🛠️ Para o desenvolvedor\n"
    "\n"
    "**O que o diretor quer:** A recepção marca o retorno do paciente na saída.\n"
    "\n"
    "**Por que ele pediu:** Hoje o retorno é anotado no papel e se perde.\n"
    "\n"
    "**O que já ficou decidido com ele:** Só a recepção marca o retorno.\n"
    "\n"
    "**Onde mexe no código:** A tela da recepção e o serviço de agenda.\n"
    "\n"
    "**Cuidados:** O aviso por WhatsApp tem limite diário.\n"
    "\n"
    "**Como saber que acabou:** A recepção marca um retorno e ele aparece na agenda."
)

ANTES_DO_BLOCO = (
    "Agenda de retorno marcada na recepção.\n"
    "\n"
    "## 👔 Para o diretor\n"
    "\n"
    "**O que muda:** a recepção marca o retorno.\n"
    "\n"
    "- O paciente sai com a data.\n"
)
DEPOIS_DO_BLOCO = (
    "---\n"
    "\n"
    "## Decisões de negócio\n"
    "\n"
    "1. **Quem marca?**\n"
    "   Escolha: Só a recepção.\n"
    "\n"
    '<!-- demanda-vitta id="d-1" -->'
)
CORPO = ANTES_DO_BLOCO + "\n" + DEPOIS_DO_BLOCO


class _GithubDeMentira:
    """As issues por número, o registro do que foi regravado e o erro que uma
    issue deve dar."""

    def __init__(self, issues: dict[int, dict], *, erro_ao_gravar: dict[int, Exception] | None = None):
        self.issues = issues
        self.erro_ao_gravar = erro_ao_gravar or {}
        self.gravacoes: list[tuple[int, str]] = []

    def ler_issue(self, numero: int) -> dict:
        if numero not in self.issues:
            raise github_client.IssueNaoEncontradaError(str(numero))
        return dict(self.issues[numero])

    def regravar_corpo(self, numero: int, *, corpo: str) -> dict:
        if numero in self.erro_ao_gravar:
            raise self.erro_ao_gravar[numero]
        self.gravacoes.append((numero, corpo))
        self.issues[numero] = {**self.issues[numero], "body": corpo}
        return dict(self.issues[numero])


def _issue(numero: int, corpo: str = CORPO, estado: str = "open") -> dict:
    return {"number": numero, "state": estado, "body": corpo, "title": "Agenda de retorno"}


class _ModeloDeMentira:
    """A Anthropic de mentira: devolve as seis partes, ou um texto que não é
    JSON quando o pedido traz `quebra`."""

    def __init__(self, quebra: str | None = None):
        self.quebra = quebra
        self.pedidos: list[str] = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        conteudo = kwargs["messages"][0]["content"]
        self.pedidos.append(conteudo)
        texto = "não sei" if self.quebra and self.quebra in conteudo else json.dumps(PARTES, ensure_ascii=False)
        uso = SimpleNamespace(input_tokens=100, output_tokens=10, cache_read_input_tokens=0, cache_creation_input_tokens=0)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=texto)], stop_reason="end_turn", usage=uso)


@pytest.fixture
def modelo(monkeypatch) -> _ModeloDeMentira:
    cliente = _ModeloDeMentira()
    monkeypatch.setattr(ai_processor, "_llm_provider", lambda: "anthropic")
    monkeypatch.setattr(ai_processor, "_get_llm", lambda: (cliente, "modelo-do-resto-do-app"))
    return cliente


@pytest.fixture
def emails(monkeypatch) -> list:
    enviados: list = []
    monkeypatch.setattr(email_service, "_enviar_email", lambda *a, **kw: enviados.append((a, kw)))
    return enviados


def _github(monkeypatch, issues: dict[int, dict], **kw) -> _GithubDeMentira:
    gh = _GithubDeMentira(issues, **kw)
    monkeypatch.setattr(github_client, "integracao_configurada", lambda: True)
    monkeypatch.setattr(github_client, "ler_issue", gh.ler_issue)
    monkeypatch.setattr(github_client, "regravar_corpo", gh.regravar_corpo)
    return gh


def _banco(*demandas: dict) -> _SupabaseMock:
    return _SupabaseMock({"tecnologia_demandas": [dict(d) for d in demandas], "tecnologia_planejamentos": []})


def _do_diretor(did: str, numero: int | None, **campos) -> dict:
    return _demanda(did, origem="diretor", apagada_em=None, github_issue_numero=numero, **campos)


class TestAPassadaInsereUmaVez:
    def test_a_issue_ganha_o_bloco_uma_vez_e_rodar_de_novo_nao_duplica(self, monkeypatch, modelo, emails):
        gh = _github(monkeypatch, {42: _issue(42)})
        sb = _banco(_do_diretor("d-1", 42))

        passada_unica.passada(sb, aplicar=True, kit="")
        passada_unica.passada(sb, aplicar=True, kit="")

        assert len(gh.gravacoes) == 1
        assert gh.issues[42]["body"].count("Para o desenvolvedor") == 1
        assert len(modelo.pedidos) == 1
