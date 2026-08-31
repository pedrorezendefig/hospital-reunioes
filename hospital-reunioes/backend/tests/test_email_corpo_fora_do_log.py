"""O corpo do email no log do modo mock (issue #450, ADR 0039 decisão 7).

Sem `RESEND_API_KEY` e sem SMTP, `_enviar_email` cai no modo mock: nada sai da
máquina e a mensagem é gravada no log da aplicação. No desenvolvimento local
isso é o desenho, e é o único jeito de ver o email que se acabou de escrever.

O que este arquivo tranca é a outra ponta: **o modo mock não é exclusividade do
desenvolvimento**. Basta a chave do Resend ser rotacionada para vazio e
produção inteira cai nele. Aí os doze construtores de notificação da Ouvidoria
despejam protocolo e `extrato_para_o_setor` no log do container, e quem tem
acesso ao log do Coolify passa a ler conteúdo de caso da Ouvidoria sem ter
perfil nenhum no módulo: o gate de acesso do Dossiê deixa de valer para aquele
trecho.

O sinal de operação (para quem ia, com que assunto, com que anexo) continua no
log nos dois ambientes. Quem investiga um email que não saiu precisa dele, e
ele não carrega conteúdo de caso.

Nenhum teste aqui toca provedor de email real: o modo mock é justamente o que
se está exercitando, e ele não abre socket nenhum.
"""

from __future__ import annotations

import logging
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services import email_service  # noqa: E402

DESTINATARIO = "carlos.titular@hsm.br"
# Um assunto no molde dos emails do caso, e de propósito SEM o protocolo: o que
# se está medindo é o corpo, e um assunto que carregasse o protocolo faria a
# asserção de ausência acusar o campo errado.
ASSUNTO = "Ouvidoria: nova demanda para o seu setor"
# O corpo no molde do pior caso real: protocolo mais o extrato escrito pelo
# ouvidor, que é o que o ADR 0039 deixa sair para o setor.
CORPO = (
    "Protocolo 2026-0042, Recepcao.\n"
    "Extrato para o setor: paciente relata espera de duas horas e quinze minutos "
    "sem informacao sobre a fila.\n"
    "Prazo para responder: 20/08/2026.\n"
)
TRECHO_DO_RELATO = "espera de duas horas e quinze minutos"
PROTOCOLO = "2026-0042"

ANEXOS = [("relatorio-ouvidoria-quinzenal-2026-08-01.pdf", b"%PDF-1.4 fake")]


@pytest.fixture(autouse=True)
def _modo_mock(monkeypatch):
    """Nem Resend nem SMTP: é o modo mock que se está testando."""
    monkeypatch.setattr(email_service.settings, "resend_api_key", "")
    monkeypatch.setattr(email_service.settings, "smtp_user", "")


def _enviar(caplog) -> tuple[bool, str]:
    """Manda um email pelo modo mock e devolve o que foi para o log."""
    with caplog.at_level(logging.WARNING, logger="app.services.email_service"):
        enviado = email_service._enviar_email(
            destinatario=DESTINATARIO,
            assunto=ASSUNTO,
            html_content=f"<p>{CORPO}</p>",
            texto_fallback=CORPO,
            anexos=ANEXOS,
        )
    return enviado, "\n".join(registro.getMessage() for registro in caplog.records)


@pytest.mark.parametrize("ambiente", ["production", "staging", ""])
def test_fora_de_desenvolvimento_o_corpo_do_email_nao_vai_para_o_log(monkeypatch, caplog, ambiente):
    """CA: fora de desenvolvimento, o corpo do email não aparece no log.

    Os três ambientes juntos porque a regra não é "não é production", é "só em
    development": um `!=` no lugar do `==` deixaria homologação despejando o
    relato no log, e ela roda com dado de verdade nesta casa."""
    monkeypatch.setattr(email_service.settings, "environment", ambiente)

    enviado, log = _enviar(caplog)

    assert enviado is True, "o modo mock continua devolvendo o que sempre devolveu"
    assert TRECHO_DO_RELATO not in log
    assert PROTOCOLO not in log
    assert CORPO not in log


def test_fora_de_desenvolvimento_o_log_diz_que_omitiu_o_corpo(monkeypatch, caplog):
    """Um log que cala sem dizer que calou manda o desenvolvedor procurar bug
    onde não há: ele vê "[MOCK EMAIL]" sem corpo e conclui que o corpo veio
    vazio do construtor."""
    monkeypatch.setattr(email_service.settings, "environment", "production")

    _, log = _enviar(caplog)

    assert "corpo omitido" in log.lower()


def test_fora_de_desenvolvimento_o_sinal_de_operacao_continua_no_log(monkeypatch, caplog):
    """CA: destinatário e assunto continuam no log.

    É o que responde "o email deste caso saiu?" quando alguém liga reclamando
    que não recebeu, e nada disso é conteúdo de manifestação: o endereço é de
    gente do hospital (ADR 0039, decisão 5) e o assunto não carrega relato."""
    monkeypatch.setattr(email_service.settings, "environment", "production")

    _, log = _enviar(caplog)

    assert DESTINATARIO in log
    assert ASSUNTO in log
    # O anexo entra por nome e tamanho, que é o que já ia: o PDF em si nunca
    # foi para o log.
    assert ANEXOS[0][0] in log


def test_em_desenvolvimento_o_corpo_continua_no_log(monkeypatch, caplog):
    """A privacidade não pode custar o fluxo local: sem provedor configurado, o
    log é o único lugar em que o desenvolvedor lê o email que acabou de
    escrever."""
    monkeypatch.setattr(email_service.settings, "environment", "development")

    _, log = _enviar(caplog)

    assert TRECHO_DO_RELATO in log
    assert DESTINATARIO in log
    assert ASSUNTO in log


def test_o_transporte_real_nao_passa_pelo_modo_mock(monkeypatch, caplog):
    """A guarda de ambiente é do modo mock, e só dele: com Resend configurado
    nada é impresso aqui, nem em produção nem em desenvolvimento."""
    monkeypatch.setattr(email_service.settings, "environment", "production")
    monkeypatch.setattr(email_service.settings, "resend_api_key", "re_chave_de_teste")
    enviados: list[dict] = []
    monkeypatch.setattr(
        email_service,
        "_enviar_via_resend",
        lambda *args, **kwargs: enviados.append({"args": args}) is None,
    )

    with caplog.at_level(logging.WARNING, logger="app.services.email_service"):
        email_service._enviar_email(DESTINATARIO, ASSUNTO, "<p>x</p>", CORPO)

    assert len(enviados) == 1
    assert "[MOCK EMAIL]" not in "\n".join(r.getMessage() for r in caplog.records)
