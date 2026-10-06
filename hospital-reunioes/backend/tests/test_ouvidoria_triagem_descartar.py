"""Triagem de e-mail: descartar guarda só o cabeçalho (issue #649, PRD #646,
ADR 0051 decisão 5).

Spam, newsletter e resposta interna não são manifestação, e o corpo de um
e-mail pode trazer nome, CPF e leito sem uso nenhum. Descartar fica com o que
responde "sumiu o e-mail de fulano, quem descartou?": remetente, assunto,
data, quem descartou e quando. Corpo, cabeçalhos técnicos e anexos (linha e
binário) saem. Item descartado não é manifestação, então o ADR 0047 não o
alcança; já o e-mail que virou caso ou foi juntado a um não se descarta.

Os dublês são os da fatia de virar manifestação (#650), que já trazem o
`delete` e o storage com `remove`.
"""

from __future__ import annotations

import os
import sys

import httpx
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from test_ouvidoria_triagem_email import OUVIDOR, SECRETARIA, SUPER_ADMIN  # noqa: E402
from test_ouvidoria_triagem_virar_manifestacao import (  # noqa: E402
    _email_na_triagem,
    _reset_rate_limiter,  # noqa: F401 (fixture autouse)
    _segredo_configurado,  # noqa: F401 (fixture autouse)
)

from app.config import settings  # noqa: E402

BUCKET = settings.supabase_storage_bucket_anexos_ouvidoria


def _descartar(cliente, email_id: str):
    return cliente.post(f"/api/ouvidoria/triagem-email/{email_id}/descarte")


class TestDescartarGuardaSoOCabecalho:
    def test_descartar_deixa_so_o_cabecalho_e_quem_descartou(self, monkeypatch):
        cliente, banco, email_id = _email_na_triagem(monkeypatch)
        [anexo] = banco.tabelas["ouvidoria_emails_recebidos_anexos"]
        caminho = f"{BUCKET}/{anexo['storage_path']}"
        assert caminho in banco.storage.arquivos

        r = _descartar(cliente, email_id)

        assert r.status_code == 200
        [item] = banco.tabelas["ouvidoria_emails_recebidos"]
        assert item["estado"] == "descartado"
        assert item["remetente_endereco"] == "joana.silva@gmail.com"
        assert item["remetente_nome"] == "Joana da Silva"
        assert item["assunto"] == "Demora na recepção do ambulatório"
        assert item["recebido_em"] == "2026-09-10T14:02:10.000Z"
        assert item["decidido_por"] == OUVIDOR["id"]
        assert item["decidido_por_nome"] == "Marta Ouvidora"
        assert item["decidido_em"] is not None
        # O conteúdo sai. Se o corpo ficar gravado, este teste fica vermelho.
        assert item["corpo_texto"] is None
        assert item["corpo_html"] is None
        assert item["cabecalhos"] == {}
        assert banco.tabelas["ouvidoria_emails_recebidos_anexos"] == []
        assert caminho not in banco.storage.arquivos

    def test_descartar_duas_vezes_nao_da_erro_e_nao_muda_nada(self, monkeypatch):
        cliente, banco, email_id = _email_na_triagem(monkeypatch)
        assert _descartar(cliente, email_id).status_code == 200
        depois_do_primeiro = dict(banco.tabelas["ouvidoria_emails_recebidos"][0])

        r = _descartar(cliente, email_id)

        assert r.status_code == 200
        # Quem descartou e quando continuam os do primeiro descarte.
        assert banco.tabelas["ouvidoria_emails_recebidos"][0] == depois_do_primeiro

    def test_binario_recusado_responde_503_e_o_descarte_seguinte_termina(self, monkeypatch):
        """O storage recusou o binário no primeiro descarte: a linha do anexo
        fica, e a resposta é "tente de novo" (503), e não 200, porque 200
        diria ao ouvidor que o anexo foi apagado. O descarte seguinte termina
        o serviço."""
        cliente, banco, email_id = _email_na_triagem(monkeypatch)
        [anexo] = banco.tabelas["ouvidoria_emails_recebidos_anexos"]
        caminho = f"{BUCKET}/{anexo['storage_path']}"
        remover = banco.storage.from_(BUCKET).__class__.remove
        monkeypatch.setattr(banco.storage.from_(BUCKET).__class__, "remove", lambda self, paths: [])

        r = _descartar(cliente, email_id)
        assert r.status_code == 503
        assert "Tente de novo" in r.json()["detail"]
        assert len(banco.tabelas["ouvidoria_emails_recebidos_anexos"]) == 1
        assert caminho in banco.storage.arquivos

        monkeypatch.setattr(banco.storage.from_(BUCKET).__class__, "remove", remover)
        assert _descartar(cliente, email_id).status_code == 200

        assert banco.tabelas["ouvidoria_emails_recebidos_anexos"] == []
        assert caminho not in banco.storage.arquivos


class TestOQueNaoSeDescarta:
    @pytest.mark.parametrize("estado", ["virou_manifestacao", "juntado"])
    def test_email_que_e_parte_de_um_caso_recusa_o_descarte_e_guarda_o_corpo(self, monkeypatch, estado):
        """O conteúdo do e-mail que virou caso, ou foi juntado a um, é parte
        do caso, e o caso não se apaga (ADR 0047)."""
        cliente, banco, email_id = _email_na_triagem(monkeypatch)
        banco.tabelas["ouvidoria_emails_recebidos"][0] |= {
            "estado": estado,
            "decidido_em": "2026-09-11T10:00:00",
            "manifestacao_id": "caso-7",
        }

        r = _descartar(cliente, email_id)

        assert r.status_code == 409
        [item] = banco.tabelas["ouvidoria_emails_recebidos"]
        assert item["estado"] == estado
        assert item["corpo_texto"] == "Esperei três horas na recepção sem informação nenhuma."
        assert len(banco.tabelas["ouvidoria_emails_recebidos_anexos"]) == 1

    def test_email_inexistente_recebe_404(self, monkeypatch):
        cliente, _, _ = _email_na_triagem(monkeypatch)

        assert _descartar(cliente, "nao-existe").status_code == 404


class TestSoAOuvidoriaDescarta:
    @pytest.mark.parametrize("participante", [SECRETARIA, SUPER_ADMIN, None])
    def test_perfil_sem_ouvidoria_recebe_403_e_o_email_fica_inteiro(self, monkeypatch, participante):
        cliente, banco, email_id = _email_na_triagem(monkeypatch, participante)

        assert _descartar(cliente, email_id).status_code == 403
        [item] = banco.tabelas["ouvidoria_emails_recebidos"]
        assert item["estado"] == "pendente"
        assert item["corpo_texto"] is not None
        assert len(banco.tabelas["ouvidoria_emails_recebidos_anexos"]) == 1


class TestODescarteEntraNoLogDeAcesso:
    def test_o_descarte_grava_o_acesso_com_o_email_como_alvo(self, monkeypatch):
        cliente, banco, email_id = _email_na_triagem(monkeypatch)

        _descartar(cliente, email_id)

        [acesso] = [a for a in banco.tabelas["ouvidoria_acessos"] if a["acao"] == "descartar_email"]
        assert acesso["email_recebido_id"] == email_id
        assert acesso["ator_id"] == OUVIDOR["id"]
        assert acesso["ator_nome"] == "Marta Ouvidora"
        assert "manifestacao_id" not in acesso


class TestODescartadoNaTriagem:
    def test_descartado_aparece_decidido_na_lista_e_abre_so_com_o_cabecalho(self, monkeypatch):
        cliente, _, email_id = _email_na_triagem(monkeypatch)
        _descartar(cliente, email_id)

        [linha] = cliente.get("/api/ouvidoria/triagem-email").json()["emails"]
        assert linha["estado"] == "descartado"
        assert linha["decidido_por_nome"] == "Marta Ouvidora"
        assert linha["quantidade_de_anexos"] == 0

        item = cliente.get(f"/api/ouvidoria/triagem-email/{email_id}").json()
        assert item["remetente_endereco"] == "joana.silva@gmail.com"
        assert item["assunto"] == "Demora na recepção do ambulatório"
        assert item["corpo_texto"] is None
        assert item["anexos"] == []
        assert item["cabecalhos"] == {}
        assert item["destinatarios"] == []


class TestFalhaDoBancoNoDescarte:
    def test_banco_fora_do_ar_responde_503_e_nada_e_apagado(self, monkeypatch):
        """A mesma régua do registro manual (#650): banco que não responde é
        "tente de novo", e não erro de servidor."""
        cliente, banco, email_id = _email_na_triagem(monkeypatch)
        banco.leitura_quebra["ouvidoria_emails_recebidos"] = httpx.ConnectError("sem rota até o banco")

        r = _descartar(cliente, email_id)

        assert r.status_code == 503
        assert "Tente de novo" in r.json()["detail"]
        assert banco.tabelas["ouvidoria_emails_recebidos"][0]["corpo_texto"] is not None
        assert len(banco.tabelas["ouvidoria_emails_recebidos_anexos"]) == 1


class TestAReentregaNaoDesfazODescarte:
    def test_descarte_no_meio_da_reentrega_nao_ganha_corpo_nem_anexo_de_volta(self, monkeypatch):
        """A reentrega de um item incompleto confere o estado uma vez, antes de
        ler o Resend e baixar os anexos, que é o trecho lento. O ouvidor que
        descarta nessa janela não pode ver o corpo e os anexos voltarem: o
        descarte promete que fica só o cabeçalho (ADR 0051, decisão 5)."""
        from datetime import UTC, datetime

        from test_ouvidoria_triagem_email import _entregar, _evento, _lido
        from test_ouvidoria_triagem_virar_manifestacao import _client

        from app.services import email_service
        from app.services import ouvidoria_triagem_email as triagem

        cliente, banco, resend = _client(monkeypatch)
        # Primeira entrega: o Resend não devolve o corpo, e o item fica
        # pendente e incompleto. O 503 é o webhook pedindo a reentrega.
        assert _entregar(cliente, _evento()).status_code == 503
        [item] = banco.tabelas["ouvidoria_emails_recebidos"]
        assert item["incompleto"] is True

        def ler_com_descarte_no_meio(email_id):
            # A leitura lenta do Resend, com o ouvidor descartando no meio.
            assert triagem.descartar(banco, OUVIDOR, item["id"], datetime.now(UTC)) == triagem.DESCARTE_FEITO
            return _lido()

        monkeypatch.setattr(email_service, "ler_email_recebido", ler_com_descarte_no_meio)
        _entregar(cliente, _evento())

        [item] = banco.tabelas["ouvidoria_emails_recebidos"]
        assert item["estado"] == "descartado"
        assert item["corpo_texto"] is None
        assert item["corpo_html"] is None
        assert item["cabecalhos"] == {}
        assert banco.tabelas["ouvidoria_emails_recebidos_anexos"] == []
        assert not any(caminho.startswith(f"{BUCKET}/") for caminho in banco.storage.arquivos)
