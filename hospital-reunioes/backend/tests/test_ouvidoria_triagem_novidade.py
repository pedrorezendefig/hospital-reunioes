"""Triagem de e-mail: e-mail pendente acende a novidade do menu (issue #652,
PRD #646, ADR 0051 decisão 3).

Sem resposta automática na chegada, a contrapartida é a triagem diária: o
contador de novidades do menu soma os e-mails recebidos que esperam decisão
aos casos com novidade, e cada decisão baixa a soma. O e-mail parado há mais
de 90 dias aparece marcado como atrasado na lista; nada é descartado sozinho.

Os dublês são os da fatia de virar manifestação (#650), com o que esta fatia
acrescenta: a RPC do último movimento por caso, que o contador lê.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from test_ouvidoria_triagem_email import _entregar, _evento, _lido  # noqa: E402
from test_ouvidoria_triagem_virar_manifestacao import (  # noqa: E402
    _BancoDaFatia,
    _client,
    _reset_rate_limiter,  # noqa: F401 (fixture autouse)
    _segredo_configurado,  # noqa: F401 (fixture autouse)
)


class _RespostaDaRpc:
    """A RPC do último movimento por caso, sem movimento nenhum: o caso que
    nunca foi visto tem novidade só pelo carimbo nulo."""

    def __init__(self, linhas):
        self.linhas = linhas

    def order(self, *_a, **_kw):
        return self

    def range(self, inicio, fim):
        self.linhas = self.linhas[inicio : fim + 1]
        return self

    def execute(self):
        return type("R", (), {"data": list(self.linhas)})()


def _rpc(self, _nome, _params=None):
    return _RespostaDaRpc([])


def _is_(self, coluna, valor):
    """O `is null` do PostgREST: o contador ignora o caso arquivado."""
    assert valor == "null"
    return self.eq(coluna, None)


@pytest.fixture(autouse=True)
def _rpc_do_ultimo_movimento(monkeypatch):
    from test_ouvidoria_triagem_virar_manifestacao import _TabelaDaFatia

    monkeypatch.setattr(_BancoDaFatia, "rpc", _rpc, raising=False)
    monkeypatch.setattr(_TabelaDaFatia, "is_", _is_, raising=False)


def _com_emails(monkeypatch, quantos: int, *, recebido_em: str = "2026-09-10T14:02:10.000Z"):
    """Um cliente com `quantos` e-mails pendentes na triagem."""
    cliente, banco, resend = _client(monkeypatch)
    for i in range(quantos):
        evento = _evento(f"em_{i:04d}")
        evento["data"]["created_at"] = recebido_em
        resend.respostas[evento["data"]["email_id"]] = _lido()
        assert _entregar(cliente, evento).status_code == 200
    return cliente, banco


def _caso_com_novidade(banco, numero: int = 7) -> dict:
    """Um caso que a Ouvidoria nunca viu: o carimbo nulo é novidade."""
    caso = {
        "id": f"caso-{numero}",
        "numero": numero,
        "protocolo": f"2026-{numero:04d}",
        "status": "em_classificacao",
        "vista_pela_ouvidoria_em": None,
        "arquivada_em": None,
    }
    banco.tabelas["ouvidoria_protocolos"].append(caso)
    return caso


def _contador(cliente):
    return cliente.get("/api/ouvidoria/novidades")


class TestOEmailPendenteSomaNaNovidade:
    def test_dois_emails_pendentes_e_um_caso_com_novidade_somam_tres(self, monkeypatch):
        cliente, banco = _com_emails(monkeypatch, 2)
        _caso_com_novidade(banco)

        r = _contador(cliente)

        assert r.status_code == 200
        assert r.json() == {"total": 3, "degradado": []}

    @pytest.mark.parametrize("decisao", ["descarte", "juntada"])
    def test_decidir_um_email_baixa_a_contagem_em_um(self, monkeypatch, decisao):
        cliente, banco = _com_emails(monkeypatch, 2)
        caso = _caso_com_novidade(banco)
        email_id = banco.tabelas["ouvidoria_emails_recebidos"][0]["id"]
        assert _contador(cliente).json()["total"] == 3

        if decisao == "descarte":
            r = cliente.post(f"/api/ouvidoria/triagem-email/{email_id}/descarte")
        else:
            caso |= {"setor": "Recepção", "anonimizada_em": None, "apagamento_pedido_em": None}
            r = cliente.post(f"/api/ouvidoria/triagem-email/{email_id}/juntada", json={"manifestacao_id": caso["id"]})

        assert r.status_code == 200
        assert _contador(cliente).json()["total"] == 2


class TestQuemNaoEDaOuvidoria:
    def test_perfil_sem_ouvidoria_continua_recebendo_403(self, monkeypatch):
        from test_ouvidoria_triagem_email import SECRETARIA

        cliente, banco, _ = _client(monkeypatch, SECRETARIA)

        assert _contador(cliente).status_code == 403


class TestLeituraDosEmailsQueFalha:
    def test_falha_ao_ler_os_emails_nao_vira_um_total_menor(self, monkeypatch):
        """Contador que não carregou não é contador zerado (issue #487): sem os
        e-mails, o total sai `None`, e a falha viaja nomeada."""
        import httpx

        cliente, banco = _com_emails(monkeypatch, 2)
        _caso_com_novidade(banco)
        banco.leitura_quebra["ouvidoria_emails_recebidos"] = httpx.ConnectError("sem rota até o banco")

        assert _contador(cliente).json() == {"total": None, "degradado": ["e-mails"]}


def _dias_atras(dias: int) -> str:
    from datetime import UTC, datetime, timedelta

    return (datetime.now(UTC) - timedelta(days=dias)).isoformat()


class TestOEmailParadoFicaAtrasado:
    def test_pendente_ha_mais_de_90_dias_vem_atrasado_e_o_novo_nao(self, monkeypatch):
        cliente, banco = _com_emails(monkeypatch, 1, recebido_em=_dias_atras(91))
        evento = _evento("em_novo")
        evento["data"]["created_at"] = _dias_atras(2)
        # O dublê do Resend é o mesmo do `_client`: o e-mail novo também chega.
        from app.services import email_service

        email_service.ler_email_recebido.respostas["em_novo"] = _lido()
        assert _entregar(cliente, evento).status_code == 200

        linhas = {linha["id"]: linha for linha in cliente.get("/api/ouvidoria/triagem-email").json()["emails"]}
        antigo, novo = banco.tabelas["ouvidoria_emails_recebidos"]

        assert linhas[antigo["id"]]["atrasado"] is True
        assert linhas[novo["id"]]["atrasado"] is False

    def test_o_decidido_nao_fica_atrasado_mesmo_antigo(self, monkeypatch):
        """Atrasado é e-mail PARADO: o que já foi decidido não espera nada.
        E nada é descartado sozinho: o pendente antigo continua pendente."""
        cliente, banco = _com_emails(monkeypatch, 2, recebido_em=_dias_atras(120))
        decidido, parado = banco.tabelas["ouvidoria_emails_recebidos"]
        assert cliente.post(f"/api/ouvidoria/triagem-email/{decidido['id']}/descarte").status_code == 200

        linhas = {linha["id"]: linha for linha in cliente.get("/api/ouvidoria/triagem-email").json()["emails"]}

        assert linhas[decidido["id"]]["atrasado"] is False
        assert linhas[parado["id"]]["atrasado"] is True
        assert linhas[parado["id"]]["estado"] == "pendente"
