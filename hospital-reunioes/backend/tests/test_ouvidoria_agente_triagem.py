"""O agente de triagem da Ouvidoria (issue #1624, PRD #1527, ADR 0087).

Logo depois da chegada de toda manifestação e de toda avaliação com
comentário, o relato pseudonimizado vai ao modelo, uma vez, e o agente devolve
o assunto de uma linha, o apontamento ao Núcleo de Segurança do Paciente com
as duas justificativas e, na avaliação, a marca Para revisar com o motivo. Só
sugere: nunca grava tipo, gravidade, sigilo nem área. Se falhar, ou se o teto
de 300 chamadas por dia acabou, o caso entra normal, sem assunto e sem alerta.

Os testes sobem a rota real com o banco falso do formulário público e o
cliente da Anthropic simulado (`ClienteFalso`): nada chega à IA de verdade.
"""

from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from anthropic_apoio import ClienteFalso  # noqa: E402
from test_ouvidoria_avaliacao import CODIGO, ROTA_AVALIACAO, _BancoComAvaliacoes, _QueryComAvaliacoes  # noqa: E402
from test_ouvidoria_formulario_publico import _make_app  # noqa: E402

from app.dependencies import get_supabase_client  # noqa: E402
from app.limiter import limiter  # noqa: E402
from app.services import ouvidoria_agente_triagem  # noqa: E402

ROTA_MANIFESTACAO = "/api/ouvidoria/publico/manifestacoes"

RELATO_DE_QUEDA = (
    "Minha mãe Maria Aparecida Souza caiu do leito no quarto 204 na madrugada de ontem "
    "porque a grade estava abaixada, e ninguém veio quando apertamos a campainha. "
    "Meu CPF é 123.456.789-09."
)

RESPOSTA_COM_NUCLEO = json.dumps(
    {
        "assunto": "Queda do leito com grade abaixada na internação",
        "nsp_sugerido": True,
        "nsp_justificativa_simples": "Relata queda do paciente do leito, um incidente com a assistência.",
        "nsp_justificativa_tecnica": "Queda do leito; internação, quarto 204; madrugada; dano potencial.",
    }
)


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


class _Banco(_BancoComAvaliacoes):
    """O banco do formulário público e da avaliação, mais o update do caso e a
    reserva da cota diária do agente (a função da migration 143)."""

    def __init__(self, *, cota_livre: bool = True, **kwargs):
        super().__init__(**kwargs)
        self.cota_livre = cota_livre
        self.reservas = 0
        self.updates_do_caso: list[dict] = []

    def reservar(self, nome: str, params: dict):
        assert nome == "ouvidoria_agente_reservar_chamada"
        assert params == {"p_teto": 300}
        self.reservas += 1
        return [{"reservada": self.cota_livre}]


class _QueryDoAgente(_QueryComAvaliacoes):
    def execute(self):
        if self._tabela == "ouvidoria_protocolos" and self._pending_update is not None:
            self._banco.updates_do_caso.append(dict(self._pending_update))
            alvo = [r for r in self._banco.rows if all(r.get(c) == v for c, v in self._filters.items())]
            for linha in alvo:
                linha.update(self._pending_update)
            return type("R", (), {"data": [dict(r) for r in alvo]})()
        return super().execute()


def _app(banco: _Banco | None = None):
    banco = banco or _Banco()
    client, _ = _make_app(banco)

    class _Supabase:
        def table(self, name: str):
            return _QueryDoAgente(banco, name)

        def rpc(self, nome: str, params: dict):
            return type("Rpc", (), {"execute": lambda _self: type("R", (), {"data": banco.reservar(nome, params)})()})()

    client.app.dependency_overrides[get_supabase_client] = _Supabase
    return client, banco


@pytest.fixture
def modelo(monkeypatch):
    """O cliente da Anthropic simulado. O teste troca `modelo.texto` para mudar
    o que o agente responde."""
    cliente = ClienteFalso(RESPOSTA_COM_NUCLEO)
    monkeypatch.setattr(ouvidoria_agente_triagem, "_cliente", lambda: cliente)
    return cliente


def _enviar(client, relato: str = RELATO_DE_QUEDA):
    return client.post(ROTA_MANIFESTACAO, json={"relato": relato, "sobre": "mim"})


def _texto_enviado(cliente: ClienteFalso) -> str:
    (chamada,) = cliente.chamadas
    return json.dumps(chamada["messages"], ensure_ascii=False) + (chamada.get("system") or "")


class TestAChegadaGravaAssuntoENucleo:
    """Critério 1: com o cliente simulado, a chegada grava o assunto e, quando
    for o caso, a sugestão do Núcleo com as duas justificativas."""

    def test_a_manifestacao_publica_chega_com_assunto_e_apontamento_ao_nucleo(self, modelo):
        client, banco = _app()

        r = _enviar(client)

        assert r.status_code == 201
        caso = banco.rows[0]
        assert caso["assunto"] == "Queda do leito com grade abaixada na internação"
        assert caso["nsp_sugerido"] is True
        assert caso["nsp_justificativa_simples"] == (
            "Relata queda do paciente do leito, um incidente com a assistência."
        )
        assert caso["nsp_justificativa_tecnica"] == (
            "Queda do leito; internação, quarto 204; madrugada; dano potencial."
        )
        assert modelo.chamadas[0]["model"] == "claude-sonnet-5-5"
