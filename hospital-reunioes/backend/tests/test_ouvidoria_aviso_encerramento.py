"""Aviso de encerramento ao manifestante (issue #494, PRD #471, ADR 0042).

A segunda e última ponta do ADR 0042. A #493 fez o hospital dizer "chegou"; esta
faz o hospital dizer "no que deu". Sem ela, encerrar o caso no sistema não era
encerrar para o paciente (RN-80): a fila do ouvidor esvaziava e a pessoa que
reclamou continuava esperando.

Quatro coisas precisam ficar provadas aqui, e três delas são furos que a revisão
independente da #493 encontrou no caminho irmão:

1. **O aviso sai na transição de encerramento**, com protocolo, o desfecho em
   linguagem simples que o ouvidor escreveu e o canal para voltar. Anônimo ou
   contato sem email é encerrado sem disparo, com marcação própria (RN-81);
2. **o corpo do email não carrega texto de quem manifestou.** O contato do canal
   aberto não tem confirmação de posse: quem manda o formulário escolhe o
   destinatário, e com o nome no corpo escolheria junto o texto de um email
   assinado pelo domínio do hospital;
3. **o endereço do manifestante não aparece no log**, nem quando o envio dá
   certo nem quando o provedor recusa. A ligação é opt-in por uma tupla escrita
   à mão (`GATILHOS_DO_MANIFESTANTE`), então o gatilho novo nasce vazando se
   ninguém a acrescentar. Estes testes são a trava;
4. **falhar o aviso não desfaz o encerramento.** O ato do ouvidor já aconteceu e
   já está na trilha imutável; perder o email é ruim, perder o ato é pior.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import glob
import inspect
import logging
import os
import sys

import pytest
from fastapi import BackgroundTasks
from postgrest.exceptions import APIError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Os dublês de banco e o cliente HTTP das fatias irmãs. Reaproveitados de
# propósito: o aviso de encerramento é o gêmeo do acuse, e um segundo fake com
# regras próprias faria os dois caminhos divergirem sem ninguém notar.
from test_ouvidoria_acuse_recebimento import _BancoFake  # noqa: E402
from test_ouvidoria_aguardando_manifestante import (  # noqa: E402
    _client,
    _manifestacao,
    _SupabaseFake,
    _transicionar,
)

from app.limiter import limiter  # noqa: E402
from app.middleware.request_context import JsonFormatter  # noqa: E402
from app.services import (  # noqa: E402
    email_service,
    ouvidoria_encerramento,
    ouvidoria_marcos,
    ouvidoria_notificacoes,
)
from app.services.ouvidoria_contato import destinatario_do_caso  # noqa: E402
from app.services.ouvidoria_estados import (  # noqa: E402
    entra_no_indicador_de_resposta_conclusiva,
)

MIGRATIONS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "supabase", "migrations")
MIGRATION_AVISO = "096_ouvidoria_aviso_encerramento.sql"

# Sábado, 3h20 da manhã. O encerramento não tem janela comercial nenhuma: ele
# sai quando o ouvidor clica.
ENCERRADO_EM = dt.datetime(2026, 9, 5, 3, 20, tzinfo=dt.UTC)

# O que o ouvidor escreveu PARA QUEM MANIFESTOU (RN-64). É este texto que vai no
# email, e não `procedente`, que é código de sistema.
DESFECHO_EM_LINGUAGEM_SIMPLES = (
    "Confirmamos a demora que voce relatou na recepcao do plantao noturno. "
    "A escala do setor foi reforcada a partir desta semana."
)


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """O storage do slowapi é global por IP e acumula 429 entre arquivos."""
    limiter._storage.reset()
    yield
    limiter._storage.reset()


@pytest.fixture(autouse=True)
def _nunca_chega_no_provedor_de_verdade(monkeypatch):
    """O pytest do backend carrega o .env REAL, com a chave do Resend de
    produção. Sem esta rede, um teste que esquecesse de mockar mandaria email
    de verdade para o endereço da fixture. Desconfigurar os dois provedores põe
    o `email_service` no modo mock, que é o caminho de log mais falante e o que
    os testes de log deste arquivo querem observar."""
    monkeypatch.setattr(email_service, "_resend_configurado", lambda: False)
    monkeypatch.setattr(email_service, "_smtp_configurado", lambda: False)


@pytest.fixture
def emails(monkeypatch) -> list[tuple]:
    """Toda saída de email do módulo passa por `_enviar_email`. Quem pede esta
    fixture inspeciona o que foi montado; quem não pede cai no modo mock da
    rede acima."""
    enviados: list[tuple] = []

    def _fake(destinatario, assunto, html, texto=None, **_kwargs):
        enviados.append((destinatario, assunto, html, texto))
        return True

    monkeypatch.setattr(ouvidoria_notificacoes, "_enviar_email", _fake)
    return enviados


def _ddl(nome: str = MIGRATION_AVISO) -> str:
    with open(os.path.join(MIGRATIONS_DIR, nome), encoding="utf-8") as f:
        return f.read()


def _migration_vigente_do_check_de_gatilhos() -> str:
    """A migration mais recente que redefine o CHECK de gatilhos. As migrations
    são numeradas, então a ordem alfabética é a cronológica."""
    candidatas = sorted(
        os.path.basename(caminho)
        for caminho in glob.glob(os.path.join(MIGRATIONS_DIR, "*.sql"))
        if "ouvidoria_notificacoes_gatilho_check" in open(caminho, encoding="utf-8").read()
    )
    assert candidatas, "Nenhuma migration define o CHECK de gatilhos das notificações"
    return candidatas[-1]


def _caso(**overrides) -> dict:
    caso = {
        "id": "uuid-7",
        "protocolo": "2026-0007",
        "manifestante_nome": "Joana da Silva",
        "manifestante_contato": "joana@exemplo.com",
        "anonimo": False,
        "status": "encerrado",
    }
    caso.update(overrides)
    return caso


def _avisar(banco, caso, agora=ENCERRADO_EM, *, desfecho=DESFECHO_EM_LINGUAGEM_SIMPLES, despachar=True):
    """Chama o aviso e (por padrão) roda o que ele agendou para depois da
    resposta. Devolve o desfecho da função e as tarefas de fundo."""
    tarefas = BackgroundTasks()
    resultado = ouvidoria_encerramento.avisar_encerramento(banco, caso, desfecho, agora, tarefas)
    if despachar:
        asyncio.run(tarefas())
    return resultado, tarefas


# =====================================================================
# 1. O gatilho novo no catálogo
# =====================================================================


class TestGatilhoNoCatalogo:
    def test_o_gatilho_entra_no_check_vigente(self):
        """A migration mais nova é a que vale, e ela recria a lista INTEIRA:
        esquecer um gatilho antigo ali derruba o registro dele em produção."""
        assert _migration_vigente_do_check_de_gatilhos() == MIGRATION_AVISO
        ddl = _ddl()
        for gatilho in ouvidoria_notificacoes.GATILHOS:
            assert f"'{gatilho}'" in ddl, f"O CHECK vigente não cobre o gatilho {gatilho}"

    def test_a_troca_do_check_vai_numa_transacao(self):
        """Roda à mão em produção: a tabela não pode ficar sem constraint se a
        segunda metade falhar."""
        ddl = _ddl()
        assert "BEGIN;" in ddl and "COMMIT;" in ddl
        assert "DROP CONSTRAINT IF EXISTS ouvidoria_notificacoes_gatilho_check" in ddl

    def test_os_carimbos_do_caso_sao_reaplicaveis(self):
        ddl = _ddl()
        assert "ADD COLUMN IF NOT EXISTS encerramento_avisado_em" in ddl
        assert "ADD COLUMN IF NOT EXISTS encerramento_sem_contato_em" in ddl

    def test_o_gatilho_e_do_manifestante(self):
        """A trava do furo 2 da revisão da #493, na forma mais direta: a tupla
        que liga as duas defesas de privacidade é escrita à mão, e o gatilho
        novo nasce FORA dela."""
        assert (
            ouvidoria_notificacoes.GATILHO_ENCERRAMENTO_MANIFESTANTE in ouvidoria_notificacoes.GATILHOS_DO_MANIFESTANTE
        )

    def test_o_gatilho_nao_cobra_a_area_nem_abre_o_portal(self):
        """Ele fala com quem está FORA do hospital: link do portal do setor ali
        entregaria a porta de responder ao caso a quem reclamou dele."""
        gatilho = ouvidoria_notificacoes.GATILHO_ENCERRAMENTO_MANIFESTANTE
        assert gatilho not in ouvidoria_notificacoes.GATILHOS_COM_PORTAL
        assert gatilho not in ouvidoria_notificacoes.GATILHOS_QUE_COBRAM_A_AREA


# =====================================================================
# 2. O disparo na transição de encerramento
# =====================================================================


class TestAvisoNoEncerramento:
    def test_caso_com_email_gera_o_registro_e_envia(self, emails):
        banco = _BancoFake([_caso()])

        _avisar(banco, _caso())

        assert len(banco.notificacoes) == 1
        registro = banco.notificacoes[0]
        assert registro["gatilho"] == ouvidoria_notificacoes.GATILHO_ENCERRAMENTO_MANIFESTANTE
        assert registro["destinatario_email"] == "joana@exemplo.com"
        assert registro["papel_destinatario"] == ouvidoria_encerramento.PAPEL_MANIFESTANTE
        assert len(emails) == 1
        destinatario, assunto, html, texto = emails[0]
        assert destinatario == "joana@exemplo.com"
        assert "2026-0007" in assunto
        assert "2026-0007" in texto and "2026-0007" in html

    def test_o_desfecho_vai_em_linguagem_simples_e_nao_em_codigo(self, emails):
        """Critério de aceite: o que a pessoa lê é o texto que o ouvidor
        escreveu para ela, nunca `procedente`."""
        banco = _BancoFake([_caso()])

        _avisar(banco, _caso())

        _destinatario, assunto, html, texto = emails[0]
        assert "escala do setor foi reforcada" in texto
        assert "escala do setor foi reforcada" in html
        for codigo in ("procedente", "improcedente", "sem_condicoes_de_apuracao", "sem_retorno_do_manifestante"):
            assert codigo not in texto
            assert codigo not in assunto

    def test_o_email_diz_como_voltar(self, emails):
        """RN-80 pede o canal para reabrir: sem ele o email é um aviso de porta
        fechada."""
        banco = _BancoFake([_caso()])

        _avisar(banco, _caso())

        _destinatario, _assunto, html, texto = emails[0]
        assert "/manifestacao" in texto and "/manifestacao" in html

    def test_o_caso_fica_carimbado(self, emails):
        banco = _BancoFake([_caso()])

        _avisar(banco, _caso())

        assert banco.casos[0]["encerramento_avisado_em"] == ENCERRADO_EM.isoformat()
        assert banco.casos[0].get("encerramento_sem_contato_em") is None

    def test_anonimo_nao_recebe_e_fica_marcado(self, emails):
        """O anônimo do canal aberto, que é o caso real: o formulário guarda o
        que a pessoa digitou no campo de contato mesmo quando ela marca
        anônimo, e o pedido de anonimato tem que vencer esse dado.

        A fixture traz o email de propósito. Com `manifestante_contato=None` o
        teste ficava em VÁCUO: `email_utilizavel(None)` já devolve None
        sozinho, e a guarda do anonimato nunca era exercitada."""
        anonimo = _caso(anonimo=True, manifestante_nome=None, manifestante_contato="joana@exemplo.com")
        banco = _BancoFake([anonimo])

        assert _avisar(banco, anonimo)[0] == ouvidoria_encerramento.SEM_CONTATO
        assert banco.notificacoes == []
        assert emails == []
        assert banco.casos[0]["encerramento_sem_contato_em"] == ENCERRADO_EM.isoformat()

    def test_caso_sem_contato_nenhum_tambem_fica_marcado(self, emails):
        """O outro lado: nem anônimo nem contato. É o registro de balcão em que
        ninguém anotou como retornar."""
        sem_nada = _caso(manifestante_nome=None, manifestante_contato=None)
        banco = _BancoFake([sem_nada])

        assert _avisar(banco, sem_nada)[0] == ouvidoria_encerramento.SEM_CONTATO
        assert banco.casos[0]["encerramento_sem_contato_em"] == ENCERRADO_EM.isoformat()

    def test_anonimo_com_email_no_contato_continua_sem_aviso(self, emails):
        """O pedido de anonimato vence o dado que sobrou no corpo do registro:
        a tela prometeu que não haveria identificação."""
        anonimo = _caso(anonimo=True, manifestante_contato="joana@exemplo.com")
        banco = _BancoFake([anonimo])

        _avisar(banco, anonimo)

        assert banco.notificacoes == []
        assert emails == []
        assert banco.casos[0]["encerramento_sem_contato_em"] == ENCERRADO_EM.isoformat()

    def test_contato_sem_email_fica_marcado(self, emails):
        so_telefone = _caso(manifestante_contato="(21) 99999-0000")
        banco = _BancoFake([so_telefone])

        _avisar(banco, so_telefone)

        assert banco.notificacoes == []
        assert banco.casos[0]["encerramento_sem_contato_em"] == ENCERRADO_EM.isoformat()
        assert banco.casos[0].get("encerramento_avisado_em") is None

    def test_a_regra_de_destinatario_e_a_mesma_do_acuse(self):
        """Uma regra só para o mesmo campo: duas fariam um caso receber o acuse
        e não receber o desfecho, ou entrar no denominador de um indicador e
        sair do outro."""
        assert ouvidoria_encerramento.destinatario_do_aviso is destinatario_do_caso

    def test_falha_do_registro_nao_carimba_nem_sobe(self, emails):
        banco = _BancoFake([_caso()])
        banco.insert_quebra["ouvidoria_notificacoes"] = APIError(
            {"code": "23514", "message": "violates check constraint"}
        )

        assert _avisar(banco, _caso())[0] == ouvidoria_encerramento.FALHOU
        assert emails == []
        assert banco.casos[0].get("encerramento_avisado_em") is None

    def test_desfecho_em_branco_nao_gera_aviso_mudo(self, emails):
        """Encerrar sem descrição não passa pela máquina de estados. Se passar
        por algum caminho novo, o email não sai dizendo apenas "encerramos"."""
        banco = _BancoFake([_caso()])

        assert _avisar(banco, _caso(), desfecho="   ")[0] == ouvidoria_encerramento.SEM_DESFECHO
        assert banco.notificacoes == []
        assert emails == []


# =====================================================================
# 3. O corpo do email não carrega texto de fora (furo 1 da revisão da #493)
# =====================================================================


class TestOEmailNaoCarregaTextoDoManifestante:
    def test_o_montador_recebe_protocolo_e_desfecho_e_nada_mais(self):
        """A assinatura é a defesa: passar a manifestação inteira deixaria a
        porta encostada para o dia em que alguém quiser "ajudar a pessoa a
        reconhecer o caso" com o relato dela no corpo."""
        parametros = list(inspect.signature(ouvidoria_notificacoes.montar_encerramento_manifestante).parameters)
        assert parametros == ["protocolo", "desfecho"]

    def test_nome_de_quem_manifestou_nao_entra_no_corpo(self, emails):
        injecao = "Joana\n\nATENCAO: sua conta sera bloqueada, acesse hospital-falso.example"
        banco = _BancoFake([_caso(manifestante_nome=injecao)])

        _avisar(banco, _caso(manifestante_nome=injecao))

        _destinatario, assunto, html, texto = emails[0]
        assert "hospital-falso" not in html
        assert "hospital-falso" not in texto
        assert "hospital-falso" not in assunto
        assert "Joana" not in texto

    def test_o_relato_de_quem_manifestou_nunca_chega_ao_email(self, emails):
        relato = "Cheguei as 8h com minha mae e so fomos atendidos as 10h30."
        banco = _BancoFake([_caso(relato_integral=relato, resumo=relato)])

        _avisar(banco, _caso(relato_integral=relato, resumo=relato))

        _destinatario, _assunto, html, texto = emails[0]
        assert "minha mae" not in html and "minha mae" not in texto

    def test_a_linha_da_fila_guarda_o_nome_para_o_ouvidor(self, emails):
        """O nome sai do CORPO, não do registro: a linha vive atrás do gate do
        Dossiê, e sem ela a fila do ouvidor mostraria um destinatário anônimo."""
        banco = _BancoFake([_caso()])

        _avisar(banco, _caso())

        assert banco.notificacoes[0]["destinatario_nome"] == "Joana da Silva"

    def test_caso_sem_nome_nao_grava_linha_em_branco(self, emails):
        banco = _BancoFake([_caso(manifestante_nome=None)])

        _avisar(banco, _caso(manifestante_nome=None))

        assert banco.notificacoes[0]["destinatario_nome"] == ouvidoria_notificacoes.MANIFESTANTE_SEM_NOME

    def test_o_travessao_nao_chega_ao_manifestante(self, emails):
        """Regra da casa: travessão é marca de texto gerado por IA, e o desfecho
        é campo livre digitado por gente que pode colar de qualquer lugar."""
        banco = _BancoFake([_caso()])

        _avisar(banco, _caso(), desfecho="A demora existiu — e a escala foi reforcada.")

        _destinatario, _assunto, html, texto = emails[0]
        assert "—" not in texto and "—" not in html
        assert "–" not in texto and "–" not in html


# =====================================================================
# 4. O endereço fora do log (furo 2 da revisão da #493)
# =====================================================================


class TestEnderecoForaDoLog:
    """Furo 2 da revisão da #493, no caminho novo. O app roda em INFO, e o log
    casava endereço pessoal com o assunto, que carrega o protocolo: quem tem
    acesso ao log do Coolify e nenhum perfil no módulo passaria a saber quem
    abriu cada caso.

    Os testes rodam o caminho INTEIRO, do serviço até o `email_service`, e sem
    provedor configurado, que é o modo de log mais falante que existe e o que
    acontece em produção quando a chave do Resend é rotacionada para vazio.
    Espiar o argumento da chamada provaria a fiação; o que precisa ficar provado
    é o que sobra escrito."""

    def test_o_endereco_nao_chega_ao_log_no_caminho_de_sucesso(self, caplog):
        banco = _BancoFake([_caso()])

        with caplog.at_level(logging.DEBUG):
            _avisar(banco, _caso())

        assert "joana@exemplo.com" not in caplog.text
        # O assunto fica: é o que responde "o email deste caso saiu?", e é
        # também a prova de que o teste olhou o log certo.
        assert "2026-0007" in caplog.text, "O teste não chegou ao log do envio"

    def test_email_interno_continua_com_o_endereco_no_log(self, caplog):
        """A contraprova, montada com as outras portas abertas: a omissão vale
        para quem escreve para FORA. Sem ela, o teste acima passaria com o log
        inteiro mudo. O acionamento do setor segue como estava, porque ali o
        endereço no log é o que responde a quem liga dizendo que não recebeu."""
        banco = _BancoFake([_caso(status="aguardando_area")])
        banco.tabelas["ouvidoria_notificacoes"].append(
            {
                "id": "n-1",
                "manifestacao_id": "uuid-7",
                "gatilho": ouvidoria_notificacoes.GATILHO_NOVA_DEMANDA,
                "destinatario_nome": "Carlos Titular",
                "destinatario_email": "joana@exemplo.com",
                "status": ouvidoria_notificacoes.AGENDADA,
                "tentativas": 0,
            }
        )

        with caplog.at_level(logging.DEBUG):
            ouvidoria_notificacoes.despachar(banco, banco.notificacoes[0], ENCERRADO_EM, frozenset())

        assert "joana@exemplo.com" in caplog.text


class TestEnderecoForaDoLogQuandoOEnvioFALHA:
    """A outra metade do furo 2, e a mais fácil de esquecer: a exceção formatada
    do provedor CARREGA o endereço que a mensagem tentou alcançar. Sai em ERROR,
    então sobrevive a qualquer subida de nível de log, e dispara com contato
    digitado errado, que é rotina num formulário público de texto livre."""

    ENDERECO = "joana.silva@gmial.com"

    @pytest.fixture
    def _resend_que_recusa(self, monkeypatch):
        monkeypatch.setattr(email_service, "_resend_configurado", lambda: True)
        monkeypatch.setattr(email_service.settings, "resend_api_key", "chave-de-teste", raising=False)

        def _recusa(_payload):
            raise RuntimeError(f"invalid recipient: {self.ENDERECO}")

        monkeypatch.setattr(email_service.resend.Emails, "send", staticmethod(_recusa))

    def test_a_recusa_do_provedor_nao_deixa_o_endereco_no_log(self, _resend_que_recusa, caplog):
        banco = _BancoFake([_caso(manifestante_contato=self.ENDERECO)])

        with caplog.at_level(logging.DEBUG):
            _avisar(banco, _caso(manifestante_contato=self.ENDERECO))

        assert self.ENDERECO not in caplog.text
        assert "gmial" not in caplog.text
        # O tipo da exceção fica: é o que separa provedor fora do ar de endereço
        # recusado, e é o mínimo para alguém investigar.
        assert "Erro ao enviar email via" in caplog.text

    def test_email_interno_mantem_a_mensagem_do_provedor(self, _resend_que_recusa, caplog):
        """Com as outras portas abertas: fora do caminho do manifestante, a
        mensagem do provedor é o que diz por que o email do setor não saiu."""
        with caplog.at_level(logging.DEBUG):
            email_service._enviar_email("carlos@hsm.br", "Ouvidoria: nova demanda", "<p>html</p>", "texto")

        assert self.ENDERECO in caplog.text, "O log interno perdeu a mensagem do provedor"


def _log_como_sai_em_producao(caplog) -> str:
    """O que o container realmente imprime.

    `caplog.text` usa o formatador do pytest, que NÃO serializa `exc_info`: um
    teste montado sobre ele passa verde com `logger.exception` no caminho, e foi
    exatamente esse o furo 3 da revisão da #493. O formatador da casa serializa
    (`JsonFormatter.format`: `payload["exc"] = self.formatException(...)`), então
    é ele que precisa ser a régua."""
    formatador = JsonFormatter()
    return "\n".join(formatador.format(registro) for registro in caplog.records)


class TestFalhaNaoSerializaOCaso:
    """Furo 3 da revisão da #493: `logger.exception` serializa o traceback, e o
    `details` do Postgres em violação de constraint é "Failing row contains
    (...)", ou seja, nome, contato e relato de quem manifestou no log."""

    ERRO_COM_A_LINHA = APIError(
        {
            "code": "23514",
            "message": "new row violates check constraint",
            "details": (
                "Failing row contains (uuid-7, 2026-0007, Joana da Silva, joana@exemplo.com, "
                "RELATO: fui maltratada no plantao)"
            ),
        }
    )

    def test_a_falha_do_carimbo_nao_imprime_o_caso(self, emails, caplog):
        banco = _BancoFake([_caso()])
        banco.update_quebra["ouvidoria_protocolos"] = self.ERRO_COM_A_LINHA

        with caplog.at_level(logging.INFO):
            _avisar(banco, _caso())

        registrado = _log_como_sai_em_producao(caplog)
        assert "Failing row" not in registrado
        assert "joana@exemplo.com" not in registrado
        assert "Joana da Silva" not in registrado
        assert "uuid-7" in registrado, "A falha sumiu do log: ninguém saberia que o carimbo não foi"

    def test_a_falha_do_registro_nao_imprime_o_caso(self, emails, caplog):
        banco = _BancoFake([_caso()])
        banco.insert_quebra["ouvidoria_notificacoes"] = self.ERRO_COM_A_LINHA

        with caplog.at_level(logging.INFO):
            _avisar(banco, _caso())

        registrado = _log_como_sai_em_producao(caplog)
        assert "Failing row" not in registrado
        assert "Joana da Silva" not in registrado

    def test_a_falha_que_sobe_ate_a_guarda_de_cima_nao_imprime_o_caso(self, emails, caplog, monkeypatch):
        """A guarda EXTERNA de `avisar_encerramento`, que é onde o
        `logger.exception` estava na #493. Ela só é exercitada por um erro que
        escapa das guardas internas, e `registrar` levantando é o caminho mais
        curto até lá."""
        banco = _BancoFake([_caso()])

        def _explode(*_a, **_kw):
            raise self.ERRO_COM_A_LINHA

        monkeypatch.setattr(ouvidoria_encerramento.ouvidoria_notificacoes, "registrar", _explode)

        with caplog.at_level(logging.INFO):
            assert _avisar(banco, _caso())[0] == ouvidoria_encerramento.FALHOU

        registrado = _log_como_sai_em_producao(caplog)
        assert "Failing row" not in registrado
        assert "joana@exemplo.com" not in registrado
        assert "Joana da Silva" not in registrado
        assert "uuid-7" in registrado, "A falha sumiu do log: ninguém saberia que o aviso não saiu"

    def test_a_falha_do_despacho_nao_imprime_o_caso(self, caplog, monkeypatch):
        banco = _BancoFake([_caso()])

        def _explode(*_a, **_kw):
            raise self.ERRO_COM_A_LINHA

        monkeypatch.setattr(ouvidoria_notificacoes, "despachar_agora_se_puder", _explode)

        with caplog.at_level(logging.INFO):
            _avisar(banco, _caso())

        registrado = _log_como_sai_em_producao(caplog)
        assert "Failing row" not in registrado
        assert "joana@exemplo.com" not in registrado
        assert "uuid-7" in registrado


class TestOEnvioSaiDaRequisicao:
    """Furo 4 da revisão da #493: a chamada ao provedor é síncrona, com timeout
    de 30 segundos, e o backend sobe com um event loop só."""

    def test_nada_e_enviado_antes_de_a_resposta_sair(self, emails):
        banco = _BancoFake([_caso()])

        resultado, tarefas = _avisar(banco, _caso(), despachar=False)

        assert resultado == ouvidoria_encerramento.REGISTRADO
        assert len(banco.notificacoes) == 1, "O registro precisa acontecer DENTRO da requisição"
        assert emails == [], "O provedor foi chamado dentro da requisição"
        assert tarefas.tasks, "Nada ficou agendado para depois da resposta"

        asyncio.run(tarefas())
        assert len(emails) == 1


# =====================================================================
# 5. A tela não afirma entrega sem a entrega
# =====================================================================


class TestSituacaoNaTela:
    """Precedente da #373 e da #493: o carimbo diz que o aviso foi GERADO, e
    quem sabe se o email chegou é o status da linha da notificação."""

    def _caso_avisado(self):
        return {"encerramento_avisado_em": "2026-09-05T03:20:00+00:00"}

    def test_entregue_e_o_unico_que_afirma_envio(self):
        aviso = ouvidoria_marcos.aviso_do_encerramento(self._caso_avisado(), "enviada")
        assert aviso["situacao"] == ouvidoria_marcos.AVISO_ENVIADO

    def test_envio_que_falhou_nao_afirma_envio(self):
        aviso = ouvidoria_marcos.aviso_do_encerramento(self._caso_avisado(), "falha")
        assert aviso["situacao"] == ouvidoria_marcos.AVISO_FALHA_NO_ENVIO
        assert aviso["nota"]

    @pytest.mark.parametrize("status", ["agendada", "enviando", None])
    def test_o_que_ainda_nao_saiu_fica_em_envio(self, status):
        aviso = ouvidoria_marcos.aviso_do_encerramento(self._caso_avisado(), status)
        assert aviso["situacao"] == ouvidoria_marcos.AVISO_EM_ENVIO

    def test_caso_sem_canal_mostra_a_marcacao_propria(self):
        aviso = ouvidoria_marcos.aviso_do_encerramento(
            {"encerramento_sem_contato_em": "2026-09-05T03:20:00+00:00"}, None
        )
        assert aviso["situacao"] == ouvidoria_marcos.AVISO_SEM_CONTATO
        assert aviso["em"] == "2026-09-05T03:20:00+00:00"

    def test_caso_antigo_fica_pendente_sem_inventar_data(self):
        aviso = ouvidoria_marcos.aviso_do_encerramento({}, None)
        assert aviso["situacao"] == ouvidoria_marcos.AVISO_PENDENTE
        assert aviso["em"] is None

    def test_notificacao_sem_carimbo_nao_vira_caso_antigo(self):
        """O carimbo tem guarda própria e engole a própria falha: concluir
        "pendente" ali diria, de um caso encerrado hoje, que ele é anterior ao
        aviso automático."""
        aviso = ouvidoria_marcos.aviso_do_encerramento({}, "enviada")
        assert aviso["situacao"] == ouvidoria_marcos.AVISO_ENVIADO

    def test_a_leitura_le_a_ultima_tentativa(self, emails):
        """O reenvio manual pelo painel cria outra linha: o que vale é a última
        tentativa, não a primeira."""
        banco = _BancoFake([_caso()])
        banco.tabelas["ouvidoria_notificacoes"] = [
            {
                "manifestacao_id": "uuid-7",
                "gatilho": ouvidoria_notificacoes.GATILHO_ENCERRAMENTO_MANIFESTANTE,
                "status": "falha",
                "criada_em": "2026-09-05T03:20:00+00:00",
            },
            {
                "manifestacao_id": "uuid-7",
                "gatilho": ouvidoria_notificacoes.GATILHO_ENCERRAMENTO_MANIFESTANTE,
                "status": "enviada",
                "criada_em": "2026-09-05T09:00:00+00:00",
            },
        ]

        assert ouvidoria_encerramento.status_do_envio(banco, "uuid-7") == ("enviada", True)

    def test_a_leitura_nao_confunde_o_aviso_com_o_acuse(self, emails):
        """Os dois gatilhos do manifestante moram na mesma tabela e no mesmo
        caso: ler sem filtrar o gatilho faria o acuse entregue responder pelo
        aviso que nunca saiu."""
        banco = _BancoFake([_caso()])
        banco.tabelas["ouvidoria_notificacoes"] = [
            {
                "manifestacao_id": "uuid-7",
                "gatilho": ouvidoria_notificacoes.GATILHO_ACUSAR_RECEBIMENTO,
                "status": "enviada",
                "criada_em": "2026-09-05T09:00:00+00:00",
            },
        ]

        assert ouvidoria_encerramento.status_do_envio(banco, "uuid-7") == (None, True)

    def test_leitura_que_falhou_chega_marcada(self, emails):
        banco = _BancoFake([_caso()])
        banco.leitura_quebra["ouvidoria_notificacoes"] = APIError({"code": "PGRST", "message": "fora do ar"})

        assert ouvidoria_encerramento.status_do_envio(banco, "uuid-7") == (None, False)


# =====================================================================
# 6. O indicador de resposta conclusiva (RN-81)
# =====================================================================


class TestIndicadorDeRespostaConclusiva:
    def test_caso_sem_canal_sai_do_denominador(self):
        assert not entra_no_indicador_de_resposta_conclusiva(
            {"encerramento_sem_contato_em": "2026-09-05T03:20:00+00:00"}
        )

    def test_caso_avisado_conta(self):
        assert entra_no_indicador_de_resposta_conclusiva({"encerramento_avisado_em": "2026-09-05T03:20:00+00:00"})

    def test_caso_sem_marcacao_nenhuma_conta(self):
        """Caso aberto, ou anterior a esta fatia: só a marcação tira alguém do
        denominador. Presumir o contrário esconderia do indicador todo caso que
        o hospital simplesmente deixou de avisar."""
        assert entra_no_indicador_de_resposta_conclusiva({})


# =====================================================================
# 7. O seam HTTP: a transição de encerramento
# =====================================================================


ENCERRAMENTO = {
    "estado": "encerrado",
    "desfecho": "procedente",
    "desfecho_descricao": DESFECHO_EM_LINGUAGEM_SIMPLES,
}


def _encerrar(client, **overrides):
    corpo = dict(ENCERRAMENTO)
    corpo.update(overrides)
    return _transicionar(client, **corpo)


class TestTransicaoDeEncerramento:
    def test_encerrar_dispara_o_aviso(self, monkeypatch):
        sb = _SupabaseFake([_manifestacao(manifestante_contato="joana@exemplo.com")])
        client, sb = _client(monkeypatch, supabase=sb)

        resposta = _encerrar(client)

        assert resposta.status_code == 200
        avisos = [
            n
            for n in sb.tabelas["ouvidoria_notificacoes"]
            if n["gatilho"] == ouvidoria_notificacoes.GATILHO_ENCERRAMENTO_MANIFESTANTE
        ]
        assert len(avisos) == 1
        assert avisos[0]["destinatario_email"] == "joana@exemplo.com"
        assert sb.tabelas["ouvidoria_protocolos"][0]["encerramento_avisado_em"] is not None

    def test_o_dossie_devolve_a_situacao_do_aviso(self, monkeypatch):
        sb = _SupabaseFake([_manifestacao(manifestante_contato="joana@exemplo.com")])
        client, sb = _client(monkeypatch, supabase=sb)

        corpo = _encerrar(client).json()

        assert corpo["aviso_encerramento"]["situacao"] in {
            ouvidoria_marcos.AVISO_ENVIADO,
            ouvidoria_marcos.AVISO_EM_ENVIO,
        }
        assert corpo["conta_no_indicador_de_resposta_conclusiva"] is True

    def test_encerrar_anonimo_nao_avisa_e_marca(self, monkeypatch):
        """O contato traz email de propósito: é o que o formulário público
        grava quando a pessoa preenche o campo E marca anônimo. Com o contato
        nulo, este teste passava sem nunca exercitar a precedência do
        anonimato, porque `email_utilizavel(None)` já devolve None sozinho."""
        sb = _SupabaseFake(
            [_manifestacao(anonimo=True, manifestante_contato="joana@exemplo.com", manifestante_nome=None)]
        )
        client, sb = _client(monkeypatch, supabase=sb)

        corpo = _encerrar(client).json()

        assert sb.tabelas["ouvidoria_notificacoes"] == []
        assert sb.tabelas["ouvidoria_protocolos"][0]["encerramento_sem_contato_em"] is not None
        assert corpo["aviso_encerramento"]["situacao"] == ouvidoria_marcos.AVISO_SEM_CONTATO
        assert corpo["conta_no_indicador_de_resposta_conclusiva"] is False

    def test_encerrar_contato_sem_email_nao_avisa_e_marca(self, monkeypatch):
        """O terceiro cenário do critério de aceite, e o mais comum dos dois
        que não recebem: a pessoa deixou telefone, não email. Não é anônima, o
        nome está lá, e mesmo assim não há para onde mandar o desfecho."""
        sb = _SupabaseFake([_manifestacao(manifestante_contato="(21) 99999-0000")])
        client, sb = _client(monkeypatch, supabase=sb)

        corpo = _encerrar(client).json()

        assert sb.tabelas["ouvidoria_notificacoes"] == []
        assert sb.tabelas["ouvidoria_protocolos"][0]["encerramento_sem_contato_em"] is not None
        assert sb.tabelas["ouvidoria_protocolos"][0].get("encerramento_avisado_em") is None
        assert corpo["aviso_encerramento"]["situacao"] == ouvidoria_marcos.AVISO_SEM_CONTATO
        assert corpo["conta_no_indicador_de_resposta_conclusiva"] is False

    def test_encerrar_nao_emite_token_do_portal_do_setor(self, monkeypatch):
        """O efeito, e não a tupla (`GATILHOS_COM_PORTAL`).

        `test_o_gatilho_nao_cobra_a_area_nem_abre_o_portal` afirma a lista, e
        lista afirmada não diz o que acontece quando o gatilho entra nela por
        engano. O que acontece é isto: `_link_tokenizado` emite um token REAL
        do portal do setor, amarrado ao email do destinatário, e o destinatário
        aqui é quem reclamou do caso. O hospital entregaria a porta de responder
        à própria manifestação para o manifestante, por email."""
        sb = _SupabaseFake([_manifestacao(manifestante_contato="joana@exemplo.com")])
        client, sb = _client(monkeypatch, supabase=sb)

        _encerrar(client)

        assert sb.tabelas["ouvidoria_setor_tokens"] == []

    def test_transicao_que_nao_encerra_nao_passa_pelo_aviso(self, monkeypatch, caplog):
        """A porta é a transição de ENCERRAMENTO. Pausar o caso ou devolvê-lo à
        área não é desfecho, e mandar o email ali diria à pessoa que acabou.

        A prova não pode ser só "nenhuma notificação saiu": fora do
        encerramento o desfecho é sempre nulo, então o aviso chamado no lugar
        errado cairia calado no ramo do desfecho vazio e o teste passaria com o
        gatilho pendurado em toda transição do módulo. O que denuncia é o rastro
        que esse ramo deixa: um ERROR de encerramento sem descrição a cada pausa
        e a cada devolução."""
        sb = _SupabaseFake([_manifestacao(status="aguardando_area", manifestante_contato="joana@exemplo.com")])
        client, sb = _client(monkeypatch, supabase=sb)

        with caplog.at_level(logging.INFO):
            resposta = _transicionar(
                client,
                estado="aguardando_manifestante",
                observacao="Falta o telefone para confirmar a data do atendimento.",
            )

        assert resposta.status_code == 200
        assert [
            n
            for n in sb.tabelas["ouvidoria_notificacoes"]
            if n["gatilho"] == ouvidoria_notificacoes.GATILHO_ENCERRAMENTO_MANIFESTANTE
        ] == []
        assert "sem descrição do desfecho" not in _log_como_sai_em_producao(caplog)

    def test_falha_do_aviso_nao_derruba_o_encerramento(self, monkeypatch):
        """O ato do ouvidor já está na trilha imutável quando o email é tentado.
        Perder o aviso é ruim; desfazer o encerramento é pior."""
        sb = _SupabaseFake([_manifestacao(manifestante_contato="joana@exemplo.com")])
        client, sb = _client(monkeypatch, supabase=sb)

        def _explode(*_a, **_kw):
            raise APIError({"code": "PGRST", "message": "banco fora do ar"})

        monkeypatch.setattr(ouvidoria_encerramento.ouvidoria_notificacoes, "registrar", _explode)

        resposta = _encerrar(client)

        assert resposta.status_code == 200
        assert sb.tabelas["ouvidoria_protocolos"][0]["status"] == "encerrado"
        assert sb.tabelas["ouvidoria_protocolos"][0]["encerrada_em"] is not None
