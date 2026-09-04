"""O corpo do email no log do modo mock (issue #450, ADR 0039 decisão 7).

Sem `RESEND_API_KEY` e sem SMTP, `_enviar_email` cai no modo mock: nada sai da
máquina e a mensagem é gravada no log da aplicação. No desenvolvimento local
isso é o desenho, e é o único jeito de ver o email que se acabou de escrever.

O que este arquivo tranca é a outra ponta: **o modo mock não é exclusividade do
desenvolvimento**. Basta a chave do Resend ser rotacionada para vazio e produção
inteira cai nele. Aí os doze construtores de notificação da Ouvidoria despejam o
`extrato_para_o_setor` no log do container, e quem tem acesso ao log do Coolify
passa a ler o relato de um caso da Ouvidoria sem ter perfil nenhum no módulo: o
gate de acesso do Dossiê deixa de valer para aquele trecho.

O que sai do log é o RELATO, que é o conteúdo. O que FICA é destinatário,
assunto e anexos, porque é o que responde "o email deste caso saiu?" quando
alguém liga dizendo que não recebeu, e a issue #450 decidiu manter os dois. Isso
não os torna dado neutro: os assuntos reais dos construtores carregam protocolo,
setor e estado do caso, e `test_o_assunto_real_de_construtor_ainda_deixa_indice`
mostra exatamente o que sobra. O residual é pendência humana na decisão 7 do
ADR 0039, e não é resolvido aqui.

A guarda é o ambiente, e ela é **fail-closed** nas duas pontas: o default de
`ENVIRONMENT` é o ambiente mais restrito (a variável sumir não abre o log) e
valor desconhecido faz o app recusar subir (um `prodution` digitado errado não
vira "não é production, então imprime"). `TestAmbienteFailClosed` cobre as duas.

Nenhum teste aqui toca provedor de email real: o modo mock é justamente o que se
está exercitando, e ele não abre socket nenhum.
"""

from __future__ import annotations

import logging
import os
import sys

import pytest
from pydantic import ValidationError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.config import AMBIENTES_CONHECIDOS, Settings  # noqa: E402
from app.services import email_service  # noqa: E402

DESTINATARIO = "carlos.titular@hsm.br"
# Um assunto no molde dos emails do caso, e de propósito SEM o protocolo: o que
# se está medindo é o corpo, e um assunto que carregasse o protocolo faria a
# asserção de ausência acusar o campo errado. O assunto REAL, com protocolo,
# entra no teste que mede o residual.
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

# Os ambientes conhecidos, escritos como LITERAL de propósito. Derivar a lista
# de `AMBIENTES_CONHECIDOS` daria teste vácuo: tirar um ambiente da constante
# encolheria a parametrização junto e nenhum teste ficaria vermelho.
AMBIENTES_ESPERADOS = {"development", "ci", "staging", "production"}
# Os de verdade em que o modo mock pode acontecer sem ser desenvolvimento.
AMBIENTES_QUE_OMITEM = ["production", "staging", "ci"]


@pytest.fixture(autouse=True)
def _modo_mock(monkeypatch):
    """Nem Resend nem SMTP: é o modo mock que se está testando."""
    monkeypatch.setattr(email_service.settings, "resend_api_key", "")
    monkeypatch.setattr(email_service.settings, "smtp_user", "")


def _enviar(caplog, assunto: str = ASSUNTO) -> tuple[bool, str]:
    """Manda um email pelo modo mock e devolve o que foi para o log."""
    with caplog.at_level(logging.WARNING, logger="app.services.email_service"):
        enviado = email_service._enviar_email(
            destinatario=DESTINATARIO,
            assunto=assunto,
            html_content=f"<p>{CORPO}</p>",
            texto_fallback=CORPO,
            anexos=ANEXOS,
        )
    return enviado, "\n".join(registro.getMessage() for registro in caplog.records)


@pytest.mark.parametrize("ambiente", AMBIENTES_QUE_OMITEM)
def test_fora_de_desenvolvimento_o_corpo_do_email_nao_vai_para_o_log(monkeypatch, caplog, ambiente):
    """CA: fora de desenvolvimento, o corpo do email não aparece no log.

    Todos os ambientes conhecidos juntos porque a regra não é "não é
    production", é "só em development": um `!=` no lugar do `==` deixaria
    homologação despejando o relato no log, e ela roda com dado de verdade nesta
    casa."""
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


def test_fora_de_desenvolvimento_o_destinatario_continua_no_log(monkeypatch, caplog):
    """CA: o destinatário continua no log. É metade do "o email deste caso
    saiu?", e o endereço é de gente do hospital (ADR 0039, decisão 5)."""
    monkeypatch.setattr(email_service.settings, "environment", "production")

    _, log = _enviar(caplog)

    assert DESTINATARIO in log


def test_fora_de_desenvolvimento_o_assunto_continua_no_log(monkeypatch, caplog):
    """CA: o assunto continua no log. É a outra metade: sem ele, o log diz que
    algum email saiu para o Carlos, e não QUAL."""
    monkeypatch.setattr(email_service.settings, "environment", "production")

    _, log = _enviar(caplog)

    assert ASSUNTO in log


def test_fora_de_desenvolvimento_o_anexo_continua_no_log(monkeypatch, caplog):
    """O anexo entra por nome e tamanho, que é o que já ia: o PDF em si nunca
    foi para o log."""
    monkeypatch.setattr(email_service.settings, "environment", "production")

    _, log = _enviar(caplog)

    assert ANEXOS[0][0] in log
    assert f"{len(ANEXOS[0][1])} bytes" in log


def test_o_assunto_real_de_construtor_ainda_deixa_indice(monkeypatch, caplog):
    """O que SOBRA no log, medido no assunto que o app gera de verdade.

    Os testes acima usam um assunto sintético para medir o corpo sem
    interferência. Este mede o residual com a forma real de
    `ouvidoria_notificacoes.montar_critico_imediato`: protocolo, setor e estado
    do caso viajam no assunto, então quem lê o log do Coolify sem perfil no
    módulo ainda monta um índice de casos com cronologia.

    Ele existe para a afirmação do PR não ser mais forte do que a verdade: o
    ganho desta issue é o RELATO fora do log, não o anonimato do log. Manter
    destinatário e assunto foi decidido na issue #450; truncar o protocolo ou
    aceitar o residual é pendência humana na decisão 7 do ADR 0039.

    Se um dia o assunto do log for truncado, é este teste que muda, e a mudança
    aparece como mudança de decisão, não como ajuste de asserção solta."""
    monkeypatch.setattr(email_service.settings, "environment", "production")
    assunto_real = f"Ouvidoria {PROTOCOLO}: caso CRITICO validado no setor Recepcao"

    _, log = _enviar(caplog, assunto=assunto_real)

    # O relato continua fora, que é o que a issue veio fechar.
    assert TRECHO_DO_RELATO not in log
    # E isto é o residual, medido em vez de negado.
    assert PROTOCOLO in log
    assert "Recepcao" in log
    assert "CRITICO" in log


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


class TestAmbienteFailClosed:
    """A guarda do log só vale se o sinal de ambiente for confiável nas duas
    pontas (issue #450).

    O modo mock só acontece quando alguém mexeu nas env vars do Coolify
    (`RESEND_API_KEY` vazia). A mesma mão que apaga uma pode apagar `ENVIRONMENT`
    ou digitá-la errado, e nos dois casos a defesa não pode se abrir sozinha.
    Contrato de deploy (`project.json`) segura hoje, mas contrato de deploy não é
    defesa do código."""

    @pytest.fixture(autouse=True)
    def _sem_environment_no_processo(self, monkeypatch):
        """Algum import da suíte despeja o `.env` da máquina em `os.environ` para a
        sessão inteira de teste (o `app.config` lê `hospital-reunioes/.env`, e
        scripts de operação chamam `load_dotenv`). Sem limpar, "ENVIRONMENT
        ausente" nunca seria ausente aqui: o teste do default mediria o `.env` do
        desenvolvedor em vez do código, passaria sozinho e falharia na suíte
        inteira. Antes de remover esta fixture, prove que nada mais carrega o
        `.env` no import."""
        monkeypatch.delenv("ENVIRONMENT", raising=False)

    def _settings(self, **campos) -> Settings:
        """Um Settings mínimo, sem ler o `.env` da máquina. ClickSign fora do
        sandbox e `debug` desligado porque em produção o próprio Settings recusa
        os dois, e o que se está medindo aqui é outra coisa."""
        return Settings(
            _env_file=None,
            supabase_url="http://localhost:54321",
            supabase_service_role_key="dummy",
            clicksign_base_url="https://app.clicksign.com",
            debug=False,
            **campos,
        )

    def test_ambiente_ausente_cai_no_mais_restrito(self):
        """`ENVIRONMENT` sumir do ambiente do container (remoção, renome,
        processo que não herda env) não pode abrir o log. O default é o ambiente
        mais restrito, então a ausência FECHA."""
        assert self._settings().environment == "production"

    def test_o_ambiente_do_default_omite_o_corpo(self, monkeypatch, caplog):
        """O default e a guarda do log lidos juntos: é este teste que liga uma
        coisa na outra, e sem ele o default poderia mudar sem ninguém notar que a
        defesa mudou de lado."""
        monkeypatch.setattr(email_service.settings, "environment", self._settings().environment)

        _, log = _enviar(caplog)

        assert TRECHO_DO_RELATO not in log

    @pytest.mark.parametrize("valor", ["prodution", "prod", "PRODUCTION", "", "local", "homolog"])
    def test_ambiente_desconhecido_recusa_subir(self, valor):
        """Um valor digitado errado no Coolify não pode virar "não é production,
        então tudo bem": as duas validações de produção do Settings (ClickSign
        sandbox e DEBUG) só apertam quando o valor é EXATAMENTE "production", e
        um typo as desligaria em silêncio junto com a guarda do log."""
        with pytest.raises(ValidationError, match="não é um ambiente conhecido"):
            self._settings(environment=valor)

    def test_a_lista_de_ambientes_conhecidos_e_exatamente_esta(self):
        """A lista, comparada com um literal.

        `ci` está nela porque é o valor que o workflow do GitHub Actions passa
        para o job de backend: tirá-lo faz o import do app levantar antes do
        primeiro teste, e o vermelho tem que aparecer AQUI, não no Actions.
        `staging` está porque homologação roda com dado de verdade nesta casa e
        não pode ser tratada como ambiente desconhecido."""
        assert AMBIENTES_CONHECIDOS == AMBIENTES_ESPERADOS

    @pytest.mark.parametrize("valor", sorted(AMBIENTES_ESPERADOS))
    def test_os_ambientes_conhecidos_sobem(self, valor):
        """A recusa não pode pegar quem é de casa."""
        assert self._settings(environment=valor).environment == valor
