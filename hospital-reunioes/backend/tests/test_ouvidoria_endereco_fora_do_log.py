"""Quem tem o endereço omitido do log é decidido pelo PAPEL, não por lista
escrita à mão (issue #547, PRD #471, ADR 0042).

A guarda que tira o email pessoal do manifestante do log da aplicação nasceu
opt-in, ligada por uma tupla de gatilhos escrita à mão: caminho novo de envio ao
manifestante nascia VAZANDO até alguém lembrar de editar a tupla, e o custo do
esquecimento é dado pessoal em log de produção, em nível de erro.

O que precisa ficar provado aqui:

1. **gatilho novo ao manifestante já nasce protegido**, sem ninguém cadastrar
   nada em lugar nenhum;
2. **papel desconhecido, nulo, vazio ou com caixa diferente cai no lado
   seguro**. Na dúvida, não se imprime;
3. **vale no log de FALHA**, que é o que sai em ERROR e sobrevive a qualquer
   ajuste de verbosidade. Cobre a recusa do provedor nas tentativas de envio; o
   alerta ao admin técnico da TERCEIRA falha carrega o endereço no corpo do
   email e é buraco pré-existente, com follow-up próprio;
4. **o envio interno continua com o endereço no log**: ali o destinatário é do
   hospital e o endereço é o que responde "o email deste caso saiu?" quando
   alguém liga dizendo que não recebeu (issue #450).

Os testes de omissão são os que mais mentem, e de dois jeitos:

* **"o endereço não está no log" fica verde quando o email nem saiu.** Por isso
  todo teste daqui prova, na mesma passagem, que o envio ACONTECEU (o retorno do
  despacho) e que o log daquele envio foi capturado (o assunto está lá).
* **procurar a string exata fica verde em cima de vazamento derivado.** Trocar a
  omissão por um mascaramento em `_alvo_no_log` (`joana`, `joana (at)
  exemplo.com`, `joana%40exemplo.com`) passaria por uma varredura literal. Por
  isso o caminho de sucesso assere o MARCADOR (`(endereco omitido)`), que é
  positivo e cobre toda forma derivada de uma vez, e a varredura procura também
  a parte local e o domínio isolados, em caixa dobrada.
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
from app.services.ouvidoria_contato import (  # noqa: E402
    PAPEIS_INTERNOS,
    PAPEL_MANIFESTANTE,
    destinatario_e_o_manifestante,
)
from app.services.ouvidoria_responsaveis import PAPEIS as PAPEIS_DE_RESPONSAVEL  # noqa: E402

# O assunto real de uma notificação da Ouvidoria: ele carrega o protocolo, e é
# por isso que o endereço ao lado dele identificaria quem abriu o caso.
ASSUNTO = "Ouvidoria 2026-0007: assunto do caso"

# O que o `email_service` escreve no lugar do endereço. Asserir a PRESENÇA dele
# é mais forte do que asserir a ausência do endereço: qualquer troca da omissão
# por um mascaramento (a parte local sozinha, o arroba escrito por extenso, o
# url-encode) apaga este marcador e fica vermelha, enquanto passaria por uma
# varredura que só procura a string literal do endereço.
MARCADOR = "(endereco omitido)"

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


def _nao_aparece_no_log(email: str, caplog) -> None:
    """O endereço não sobrou no log, NEM EM PEDAÇOS.

    Procurar só a string exata deixa passar a forma derivada, que é justamente o
    que um refactor produz: `joana` (a parte local sozinha),
    `joana%40exemplo.com` (url-encode) e `JOANA@EXEMPLO.COM` (caixa) vazam a
    mesma pessoa e passariam por uma varredura literal."""
    registrado = caplog.text.casefold()
    local, _, dominio = email.partition("@")

    assert email.casefold() not in registrado
    assert local.casefold() not in registrado, "a parte local do endereço sobrou no log"
    assert dominio.casefold() not in registrado, "o domínio do endereço sobrou no log"


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
        assert MARCADOR in caplog.text, "O log não diz que omitiu: a omissão virou outra coisa"
        _nao_aparece_no_log("joana@exemplo.com", caplog)


class TestPapelQueNaoEDoHospitalCaiNoLadoSeguro:
    """Nulo, vazio, espaço em branco, caixa diferente e papel desconhecido são a
    mesma pergunta: sem saber que quem recebe é do hospital, não se imprime.

    O papel desconhecido é o caso que importa para amanhã. O retorno por
    WhatsApp (ADR 0042, decisão 3) gravado como `"manifestante_whatsapp"` seria a
    lista escrita à mão de volta, com outro nome, se a guarda perguntasse
    `papel == "manifestante"`."""

    @pytest.mark.parametrize(
        "papel",
        [None, "", "   ", "Manifestante", " manifestante ", "manifestante_whatsapp", "desconhecido"],
        ids=["nulo", "vazio", "espaco", "caixa", "com-espaco-em-volta", "gatilho-de-amanha", "desconhecido"],
    )
    def test_papel_que_nao_esta_na_lista_de_internos_omite_o_endereco(self, papel, sem_provedor, caplog):
        banco = _BancoFake([_caso(status="aguardando_area")])

        entregue = _despachar(
            banco,
            caplog,
            gatilho=ouvidoria_notificacoes.GATILHO_NOVA_DEMANDA,
            papel=papel,
            email="joana@exemplo.com",
        )

        assert entregue is True, "O envio nem aconteceu: o teste de omissão passaria vazio"
        assert MARCADOR in caplog.text, "O log não diz que omitiu: a omissão virou outra coisa"
        _nao_aparece_no_log("joana@exemplo.com", caplog)

    def test_omitir_o_do_manifestante_nao_leva_o_do_hospital_junto(self, sem_provedor, caplog):
        """As duas entregas correm na MESMA passagem de propósito: omitir tudo
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
        assert MARCADOR in caplog.text
        _nao_aparece_no_log("joana@exemplo.com", caplog)
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
        assert MARCADOR not in caplog.text, "O email do hospital não devia ter o endereço omitido"


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
        # O caminho de falha não tem marcador para asserir (`_falha_no_log`
        # devolve o TIPO da exceção, e é só isso que sobra), então aqui a
        # varredura por pedaço é a defesa: a mensagem do provedor carrega o
        # endereço inteiro, e qualquer sanitização parcial dela vazaria a parte
        # local ou o domínio.
        _nao_aparece_no_log(self.ENDERECO, caplog)
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


class TestPapeisInternos:
    """A allowlist é a única lista escrita à mão que sobrou, e ela existe do lado
    seguro: papel que falta nela perde o endereço no log, não o protege demais.
    Ainda assim ela não pode divergir de quem grava o campo, senão o titular do
    setor deixa de aparecer no log sem ninguém perceber."""

    def test_a_lista_cobre_os_papeis_do_responsavel_do_setor(self):
        """`titular`, `substituto` e `gestor` vêm de `ouvidoria_responsaveis`."""
        assert set(PAPEIS_DE_RESPONSAVEL) <= PAPEIS_INTERNOS

    def test_a_lista_cobre_os_perfis_do_modulo_da_ouvidoria(self):
        """`ouvidor` e `diretoria_executiva` são os `PERFIS_OUVIDORIA` do router,
        e `setor` é quem responde pelo portal tokenizado."""
        from app.routers.ouvidoria import PERFIS_OUVIDORIA

        assert set(PERFIS_OUVIDORIA) <= PAPEIS_INTERNOS
        assert "setor" in PAPEIS_INTERNOS

    def test_o_manifestante_nunca_entra_na_lista(self):
        assert PAPEL_MANIFESTANTE not in PAPEIS_INTERNOS

    @pytest.mark.parametrize("papel", sorted(PAPEIS_INTERNOS))
    def test_papel_interno_nao_e_tratado_como_manifestante(self, papel):
        assert destinatario_e_o_manifestante(papel) is False
