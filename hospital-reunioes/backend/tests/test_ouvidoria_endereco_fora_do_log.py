"""Quem tem o endereço omitido do log é decidido pelo PAPEL, não por lista
escrita à mão (issue #547, PRD #471, ADR 0042).

A guarda que tira o email pessoal do manifestante do log da aplicação nasceu
opt-in, ligada por uma tupla de gatilhos escrita à mão: caminho novo de envio ao
manifestante nascia VAZANDO até alguém lembrar de editar a tupla, e o custo do
esquecimento é dado pessoal em log de produção, em nível de erro.

O que precisa ficar provado aqui:

1. **gatilho novo ao manifestante já nasce protegido**, sem ninguém cadastrar
   nada em lugar nenhum;
2. **papel nulo cai no lado seguro**: linha antiga, gravada antes da coluna ter
   dono, omite o endereço. Na dúvida, não se imprime;
3. **vale no log de FALHA**, que é o que sai em ERROR e sobrevive a qualquer
   ajuste de verbosidade;
4. **o envio interno continua com o endereço no log**: ali o destinatário é do
   hospital e o endereço é o que responde "o email deste caso saiu?" quando
   alguém liga dizendo que não recebeu (issue #450).

Os testes de omissão são os que mais mentem: "o endereço não está no log" fica
verde quando o email nem saiu. Por isso todo teste daqui prova, na mesma
passagem, que o envio ACONTECEU (o retorno do despacho) e que o log daquele
envio foi mesmo capturado (o assunto, que carrega o protocolo, está lá).
"""

from __future__ import annotations

import inspect
import logging
import os
import smtplib
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# O dublê de banco da fatia que criou a guarda. Reaproveitado de propósito: um
# segundo fake com regras próprias faria os dois caminhos divergirem.
from test_ouvidoria_acuse_recebimento import SABADO_DE_MADRUGADA, _BancoFake, _caso  # noqa: E402

from app.services import (  # noqa: E402
    email_service,
    ouvidoria_acuse,
    ouvidoria_encerramento,
    ouvidoria_notificacoes,
    ouvidoria_retencao,
)
from app.services.ouvidoria_contato import PAPEL_MANIFESTANTE  # noqa: E402

# O assunto real de uma notificação da Ouvidoria: ele carrega o protocolo, e é
# por isso que o endereço ao lado dele identificaria quem abriu o caso.
ASSUNTO = "Ouvidoria 2026-0007: assunto do caso"

# Um gatilho que NÃO existe em lista nenhuma do módulo. É o gatilho de amanhã
# (o transporte por WhatsApp do ADR 0042, o retorno da decisão 3): se a proteção
# dependesse de cadastro, ele nasceria vazando.
GATILHO_QUE_AINDA_NAO_EXISTE = "retorno_ao_manifestante_de_amanha"


@pytest.fixture
def sem_provedor(monkeypatch):
    """Sem Resend e sem SMTP o envio cai no modo mock, que é o caminho de log
    mais falante que existe. Nenhum teste deste arquivo encosta em provedor de
    verdade."""
    monkeypatch.setattr(email_service, "_resend_configurado", lambda: False)
    monkeypatch.setattr(email_service, "_smtp_configurado", lambda: False)
    monkeypatch.setattr(
        ouvidoria_notificacoes,
        "_montar",
        lambda *_a, **_kw: (ASSUNTO, "<p>html</p>", "texto"),
    )
    return monkeypatch


def _despachar(banco, caplog, *, gatilho, papel, email) -> bool:
    """Põe uma notificação na fila e a entrega. Devolve se o envio saiu."""
    linha = {
        "id": f"n-{len(banco.notificacoes) + 1}",
        "manifestacao_id": "uuid-7",
        "gatilho": gatilho,
        "destinatario_nome": "Quem recebe",
        "destinatario_email": email,
        "papel_destinatario": papel,
        "status": ouvidoria_notificacoes.AGENDADA,
        "tentativas": 0,
    }
    banco.notificacoes.append(linha)
    with caplog.at_level(logging.DEBUG):
        return ouvidoria_notificacoes.despachar(banco, linha, SABADO_DE_MADRUGADA, frozenset())


class TestGatilhoNovoNasceProtegido:
    def test_gatilho_fora_de_qualquer_lista_ja_omite_o_endereco(self, sem_provedor, caplog):
        """O critério de aceite da issue: um retorno NOVO ao manifestante,
        criado sem tocar em lista nenhuma, já sai com o endereço fora do log."""
        banco = _BancoFake([_caso()])

        entregue = _despachar(
            banco,
            caplog,
            gatilho=GATILHO_QUE_AINDA_NAO_EXISTE,
            papel=PAPEL_MANIFESTANTE,
            email="joana@exemplo.com",
        )

        assert entregue is True, "O envio nem aconteceu: o teste de omissão passaria vazio"
        assert ASSUNTO in caplog.text, "O log deste envio não foi capturado: a varredura está cega"
        assert "joana@exemplo.com" not in caplog.text


class TestPapelNuloCaiNoLadoSeguro:
    def test_linha_sem_papel_omite_o_endereco_e_nao_leva_a_do_hospital_junto(self, sem_provedor, caplog):
        """A coluna é anulável e há linha antiga sem papel. Sem saber quem
        recebe, o app assume o manifestante e não imprime o endereço.

        As duas entregas correm na MESMA passagem de propósito: omitir tudo
        também seria bug, e o endereço interno ao lado prova que o que sumiu foi
        só o da linha sem papel, e não o log inteiro."""
        banco = _BancoFake([_caso(status="aguardando_area")])

        sem_papel = _despachar(
            banco,
            caplog,
            gatilho=ouvidoria_notificacoes.GATILHO_NOVA_DEMANDA,
            papel=None,
            email="joana@exemplo.com",
        )
        com_papel = _despachar(
            banco,
            caplog,
            gatilho=ouvidoria_notificacoes.GATILHO_NOVA_DEMANDA,
            papel="titular",
            email="carlos@hsm.br",
        )

        assert sem_papel is True and com_papel is True, "Sem envio, a omissão não prova nada"
        assert "joana@exemplo.com" not in caplog.text
        assert "carlos@hsm.br" in caplog.text, "Omitir TODOS os endereços não é o lado seguro, é outro bug"


class TestDestinatarioInternoMantemOEndereco:
    def test_o_email_do_setor_continua_com_o_endereco_no_log(self, sem_provedor, caplog):
        """A troca vale para quem escreve para FORA. Com papel do hospital o
        endereço fica: é ele que responde "o email deste caso saiu?" quando o
        setor liga dizendo que não recebeu (issue #450)."""
        banco = _BancoFake([_caso(status="aguardando_area")])

        entregue = _despachar(
            banco,
            caplog,
            gatilho=ouvidoria_notificacoes.GATILHO_NOVA_DEMANDA,
            papel="titular",
            email="carlos@hsm.br",
        )

        assert entregue is True
        assert "carlos@hsm.br" in caplog.text


class TestOLogDeFalhaTambem:
    """O caminho de ERRO é o que mais vaza e o mais fácil de esquecer: a exceção
    formatada do provedor CARREGA o endereço que a mensagem tentou alcançar, sai
    em ERROR (então sobrevive a qualquer subida de nível) e dispara com contato
    digitado errado, que é rotina num formulário público."""

    ENDERECO = "joana.silva@gmial.com"

    @pytest.fixture
    def smtp_que_recusa(self, monkeypatch):
        monkeypatch.setattr(email_service, "_resend_configurado", lambda: False)
        monkeypatch.setattr(email_service, "_smtp_configurado", lambda: True)
        monkeypatch.setattr(
            ouvidoria_notificacoes,
            "_montar",
            lambda *_a, **_kw: (ASSUNTO, "<p>html</p>", "texto"),
        )

        class _SMTPQueRecusa:
            def __init__(self, *_a, **_kw):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *_a):
                return False

            def starttls(self):
                pass

            def login(self, *_a):
                pass

            def send_message(self, msg):
                # O erro real de destinatário recusado:
                # `SMTPRecipientsRefused.__str__` é o dicionário dos recusados,
                # com o endereço dentro.
                raise smtplib.SMTPRecipientsRefused({msg["To"]: (550, b"5.1.1 User unknown")})

        monkeypatch.setattr(email_service.smtplib, "SMTP", _SMTPQueRecusa)
        return monkeypatch

    def test_a_recusa_do_provedor_nao_deixa_o_endereco_do_manifestante_no_log(self, smtp_que_recusa, caplog):
        banco = _BancoFake([_caso(status="aguardando_area")])

        do_manifestante = _despachar(
            banco,
            caplog,
            gatilho=GATILHO_QUE_AINDA_NAO_EXISTE,
            papel=PAPEL_MANIFESTANTE,
            email=self.ENDERECO,
        )
        do_setor = _despachar(
            banco,
            caplog,
            gatilho=ouvidoria_notificacoes.GATILHO_NOVA_DEMANDA,
            papel="titular",
            email="carlos@hsm.br",
        )

        assert do_manifestante is False and do_setor is False, "Sem recusa não há log de falha para inspecionar"
        assert "Erro ao enviar email via" in caplog.text, "O log de falha não foi capturado: a varredura está cega"
        assert self.ENDERECO not in caplog.text
        assert "gmial" not in caplog.text
        # Fora do caminho do manifestante a mensagem do provedor é o que diz por
        # que o email do setor não saiu, e o app inteiro depende dela.
        assert "carlos@hsm.br" in caplog.text


class TestConstanteUnicaDoPapel:
    """O literal `"manifestante"` estava copiado em três módulos. Como ele agora
    decide o que vai para o log, uma cópia divergente deixaria de proteger um
    caminho sem que nada na tela mudasse."""

    @pytest.mark.parametrize(
        "modulo",
        [ouvidoria_acuse, ouvidoria_encerramento, ouvidoria_retencao],
        ids=["acuse", "encerramento", "retencao"],
    )
    def test_o_consumidor_importa_o_papel_em_vez_de_reescreve_lo(self, modulo):
        fonte = inspect.getsource(modulo)

        assert 'PAPEL_MANIFESTANTE = "manifestante"' not in fonte, "O literal voltou a ser reescrito neste módulo"
        assert "from app.services.ouvidoria_contato import" in fonte
        assert modulo.PAPEL_MANIFESTANTE == PAPEL_MANIFESTANTE
