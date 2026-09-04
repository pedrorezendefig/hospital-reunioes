"""O corpo do aviso ao admin técnico no log (issue #466, o resto da #450).

A #450 fechou o modo mock do `email_service`: lá o corpo só ia ao log quando a
chave do provedor estava vazia. Aqui a porta é mais larga, e não depende de
configuração nenhuma: `avisar_admins_tecnicos` grava o `texto` do aviso no log
em QUALQUER ambiente, nos dois caminhos em que o alerta não chega a ninguém.

E o `texto` é o corpo do email. Conforme quem chama, ele carrega:

- protocolo, setor e degrau de cada caso travado na rodada de escalonamento;
- `manifestacao_id`, gatilho, email do destinatário e o último erro do provedor;
- `manifestacao_id` e o nome do gestor, no alerta de setor sem titular.

Pior: o segundo `logger.error` dispara EXATAMENTE quando o provedor de email
está fora do ar, que é o vizinho do cenário da #450. No incidente em que o email
cai, esta porta despejava no log justamente o que a #450 quis proteger. Quem tem
acesso ao log do Coolify, sem perfil nenhum na Ouvidoria, lia protocolo, setor,
gravidade e cronologia de caso.

A guarda é a mesma do `email_service`: o corpo só entra no log quando
`ENVIRONMENT=development`. O `fail-closed` do sinal de ambiente (default no mais
restrito, valor desconhecido recusa subir) já é trancado em
`test_email_corpo_fora_do_log.py::TestAmbienteFailClosed` e não se repete aqui.

O que FICA fora de desenvolvimento é o sinal de operação, porque o valor deste
log é diagnosticar um alerta que NÃO saiu: que ele não saiu, o assunto (que é
onde vive a contagem de casos travados) e o `request_id`, que o `JsonFormatter`
carimba sozinho.

Residual conhecido e aceito: o assunto das notificações de caso segue no log com
protocolo e setor, porque a #450 decidiu manter destinatário e assunto. Está na
decisão 7 do ADR 0039, para decisão humana, e não se resolve aqui.

Nenhum teste toca provedor de email: `_enviar_email` é espionado em todos.
"""

from __future__ import annotations

import datetime as dt
import logging
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.middleware.request_context import JsonFormatter, request_id_var  # noqa: E402
from app.routers import ouvidoria as router_ouvidoria  # noqa: E402
from app.services import ouvidoria_escalonamento, ouvidoria_notificacoes  # noqa: E402

LOGGER = "app.services.ouvidoria_notificacoes"

# Os ambientes de verdade em que o aviso pode sair sem ser desenvolvimento.
# Homologação entra porque roda com dado de verdade nesta casa, e a regra é "só
# em development", não "não é production".
AMBIENTES_QUE_OMITEM = ["production", "staging", "ci"]

ADMIN_TECNICO = {"id": "P03", "nome_completo": "Pedro Admin", "email": "pedro@hsm.br"}

AGORA = dt.datetime(2026, 8, 20, 10, 0, tzinfo=dt.UTC)
SEM_FERIADOS: frozenset[dt.date] = frozenset()


class _SupabaseFake:
    """Só o suficiente para `avisar_admins_tecnicos` ler os super admins.

    `admins` vazio é o primeiro caminho de log (ninguém a quem alertar); com
    admin, quem manda no segundo caminho é o `_enviar_email` espionado."""

    def __init__(self, admins: list[dict]):
        self._admins = admins
        self.data = admins

    def table(self, _nome: str):
        return self

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, *_args, **_kwargs):
        return self

    def execute(self):
        return self


@pytest.fixture
def correio_mudo(monkeypatch) -> list[dict]:
    """O provedor fora do ar, que é o cenário deste log. Devolve o que teria
    saído, para os testes poderem conferir que o corpo segue chegando ao EMAIL
    mesmo quando não chega ao log."""
    tentados: list[dict] = []

    def _espiao(destinatario, assunto, html, texto):
        tentados.append({"destinatario": destinatario, "assunto": assunto, "texto": texto})
        return False

    monkeypatch.setattr(ouvidoria_notificacoes, "_enviar_email", _espiao)
    return tentados


def _no_ambiente(monkeypatch, ambiente: str) -> None:
    monkeypatch.setattr(ouvidoria_notificacoes.settings, "environment", ambiente)


def _log_de(caplog) -> str:
    return "\n".join(registro.getMessage() for registro in caplog.records)


# ═══════════════════════════════════════════════════════════════════════════
# Os três chamadores, exercitados de verdade
# ═══════════════════════════════════════════════════════════════════════════
#
# Cada um monta o corpo com o texto REAL do app, e não com uma imitação: um
# construtor que passasse a vazar um campo novo tem que aparecer aqui.

PROTOCOLO = "2026-0042"
SETOR = "Recepcao"
DEGRAU = "titular"
MANIFESTACAO_ID = "9f1c0b6e-0000-4000-8000-000000000042"
EMAIL_DO_CASO = "carlos.titular@hsm.br"
ERRO_DO_PROVEDOR = "Resend recusou: dominio nao verificado"
GESTOR = "Marina Gestora"


def _chamador_cadastro_incompleto(supabase) -> None:
    """A rodada de escalonamento que travou por cadastro incompleto: o corpo
    lista protocolo, setor e degrau de CADA caso da rodada."""
    travados = [
        ({"id": "c1", "protocolo": PROTOCOLO, "setor": SETOR}, DEGRAU),
        ({"id": "c2", "protocolo": "2026-0043", "setor": "Farmacia"}, "gestor"),
        ({"id": "c3", "protocolo": "2026-0044", "setor": "Enfermagem"}, "diretoria"),
    ]
    ouvidoria_escalonamento._alertar_cadastro_incompleto(supabase, travados)


def _chamador_notificacao_falhou(supabase) -> None:
    """A notificação que falhou nas três tentativas: o corpo carrega o id da
    manifestação, o email de quem receberia e a mensagem do provedor."""
    ouvidoria_notificacoes.alertar_admin_tecnico(
        supabase,
        {
            "id": "n1",
            "manifestacao_id": MANIFESTACAO_ID,
            "gatilho": "prazo_area_rompido",
            "destinatario_email": EMAIL_DO_CASO,
            # Notificação INTERNA: com o papel do hospital o alerta segue com
            # destinatário e erro no corpo. Sem papel a linha é tratada como
            # do manifestante e os dois saem (issue #572).
            "papel_destinatario": "titular",
            "ultimo_erro": ERRO_DO_PROVEDOR,
        },
    )


def _chamador_setor_sem_titular(supabase, monkeypatch) -> None:
    """Setor sem titular e sem Diretoria ativa: o corpo carrega o id da
    manifestação e o nome do gestor a quem o caso subiu."""
    monkeypatch.setattr(ouvidoria_notificacoes, "carregar_diretoria_executiva", lambda _s: [])
    router_ouvidoria.alertar_diretoria_sem_titular(
        supabase,
        manifestacao_id=MANIFESTACAO_ID,
        gestor_nome=GESTOR,
        gravidade="CRITICA",
        agora=AGORA,
        feriados=SEM_FERIADOS,
    )


# (nome, função que dispara, o que NÃO pode sobrar no log fora de dev)
CHAMADORES = [
    (
        "cadastro_incompleto",
        _chamador_cadastro_incompleto,
        [PROTOCOLO, SETOR, DEGRAU, "2026-0043", "Farmacia"],
    ),
    (
        "notificacao_falhou",
        _chamador_notificacao_falhou,
        [MANIFESTACAO_ID, EMAIL_DO_CASO, ERRO_DO_PROVEDOR],
    ),
    (
        "setor_sem_titular",
        _chamador_setor_sem_titular,
        [MANIFESTACAO_ID, GESTOR],
    ),
]


def _disparar(nome_ou_funcao, supabase, monkeypatch) -> None:
    if nome_ou_funcao is _chamador_setor_sem_titular:
        nome_ou_funcao(supabase, monkeypatch)
    else:
        nome_ou_funcao(supabase)


# ═══════════════════════════════════════════════════════════════════════════
# Caminho 1: não há super admin a quem alertar
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("ambiente", AMBIENTES_QUE_OMITEM)
@pytest.mark.parametrize("nome,chamador,vazamentos", CHAMADORES, ids=[c[0] for c in CHAMADORES])
def test_sem_super_admin_o_corpo_nao_vai_para_o_log(
    monkeypatch, caplog, correio_mudo, ambiente, nome, chamador, vazamentos
):
    """CA: fora de desenvolvimento, o corpo do aviso não aparece no log, para
    cada um dos três chamadores.

    Este é o caminho do cadastro do PRÓPRIO app incompleto (nenhum super admin
    ativo com email). Ele imprimia o corpo inteiro sem nem tentar enviar."""
    _no_ambiente(monkeypatch, ambiente)
    supabase = _SupabaseFake([])

    with caplog.at_level(logging.INFO, logger=LOGGER):
        _disparar(chamador, supabase, monkeypatch)

    log = _log_de(caplog)
    assert log, "o log de que o alerta não chegou a ninguém não pode sumir junto com o corpo"
    for vazamento in vazamentos:
        assert vazamento not in log, f"{vazamento!r} vazou no log em {ambiente}"


# ═══════════════════════════════════════════════════════════════════════════
# Caminho 2: havia a quem alertar, e o provedor de email não entregou
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("ambiente", AMBIENTES_QUE_OMITEM)
@pytest.mark.parametrize("nome,chamador,vazamentos", CHAMADORES, ids=[c[0] for c in CHAMADORES])
def test_alerta_que_nao_saiu_nao_leva_o_corpo_para_o_log(
    monkeypatch, caplog, correio_mudo, ambiente, nome, chamador, vazamentos
):
    """CA: o mesmo para o segundo caminho, e é o mais grave.

    Ele dispara justamente quando o provedor de email está fora do ar, que é o
    incidente vizinho ao da #450: era ali que o log recebia o conteúdo do caso
    que a #450 tinha acabado de proteger."""
    _no_ambiente(monkeypatch, ambiente)
    supabase = _SupabaseFake([ADMIN_TECNICO])

    with caplog.at_level(logging.INFO, logger=LOGGER):
        _disparar(chamador, supabase, monkeypatch)

    assert correio_mudo, "o teste precisa passar pelo caminho do envio recusado"
    log = _log_de(caplog)
    for vazamento in vazamentos:
        assert vazamento not in log, f"{vazamento!r} vazou no log em {ambiente}"


def test_o_corpo_continua_indo_para_o_email_mesmo_omitido_no_log(monkeypatch, caplog, correio_mudo):
    """A guarda é do LOG, e só dele: o admin técnico continua recebendo o aviso
    completo, senão a issue trocaria um furo de privacidade por um alerta
    inútil."""
    _no_ambiente(monkeypatch, "production")

    with caplog.at_level(logging.INFO, logger=LOGGER):
        _chamador_cadastro_incompleto(_SupabaseFake([ADMIN_TECNICO]))

    assert PROTOCOLO in correio_mudo[0]["texto"]
    assert SETOR in correio_mudo[0]["texto"]


# ═══════════════════════════════════════════════════════════════════════════
# O sinal que precisa sobrar
# ═══════════════════════════════════════════════════════════════════════════


def test_o_log_continua_dizendo_que_o_alerta_nao_saiu(monkeypatch, caplog, correio_mudo):
    """CA: o log fora de desenvolvimento mantém sinal acionável.

    O valor deste log é diagnosticar um alerta que NÃO saiu. Se ele calasse
    junto com o corpo, o incidente de email caído ficaria sem rastro nenhum,
    que é o oposto do que a função documenta."""
    _no_ambiente(monkeypatch, "production")

    with caplog.at_level(logging.INFO, logger=LOGGER):
        _chamador_cadastro_incompleto(_SupabaseFake([ADMIN_TECNICO]))

    assert "não saiu" in _log_de(caplog)


def test_o_log_continua_dizendo_que_nao_ha_super_admin(monkeypatch, caplog, correio_mudo):
    """A outra metade: o caminho sem destinatário tem ação diferente (cadastrar
    um super admin ativo com email), e o log tem que distinguir os dois."""
    _no_ambiente(monkeypatch, "production")

    with caplog.at_level(logging.INFO, logger=LOGGER):
        _chamador_cadastro_incompleto(_SupabaseFake([]))

    assert "Sem super admin" in _log_de(caplog)


def test_o_log_diz_que_omitiu_o_corpo(monkeypatch, caplog, correio_mudo):
    """Um log que cala sem dizer que calou manda o operador procurar bug onde
    não há: ele vê o aviso sem corpo e conclui que o construtor gerou vazio."""
    _no_ambiente(monkeypatch, "production")

    with caplog.at_level(logging.INFO, logger=LOGGER):
        _chamador_cadastro_incompleto(_SupabaseFake([ADMIN_TECNICO]))

    assert "corpo omitido" in _log_de(caplog).lower()


def test_o_assunto_fica_e_com_ele_a_contagem_de_casos(monkeypatch, caplog, correio_mudo):
    """CA: quantos casos.

    A contagem não é um campo novo: ela já viaja no assunto do alerta de
    cadastro (`{quantos} caso(s) travado(s)`), e é o assunto que passa a entrar
    no log no lugar do corpo. Sem ele, o operador lê "um alerta não saiu" e não
    sabe se era um caso ou trinta.

    Os assuntos dos quatro chamadores de aviso operacional são neutros (não
    carregam protocolo nem relato), diferente dos assuntos das notificações de
    caso, cujo residual está medido em `test_email_corpo_fora_do_log.py`."""
    _no_ambiente(monkeypatch, "production")

    with caplog.at_level(logging.INFO, logger=LOGGER):
        _chamador_cadastro_incompleto(_SupabaseFake([ADMIN_TECNICO]))

    log = _log_de(caplog)
    assert ouvidoria_escalonamento.ALERTA_CADASTRO_ASSUNTO.format(quantos=3) in log
    assert "3 caso(s)" in log


def test_o_request_id_continua_na_linha_do_log(monkeypatch, caplog, correio_mudo):
    """CA: o `request_id`.

    Ele não é escrito na mensagem: quem o carimba é o `JsonFormatter` do
    middleware, a partir do contextvar do request. Este teste formata o
    LogRecord de verdade com ele, porque a garantia só vale ponta a ponta: uma
    mensagem que perdesse o corpo mas fosse emitida fora do logger configurado
    ficaria sem o `request_id` e o operador não teria como cruzar a linha com o
    resto do incidente."""
    _no_ambiente(monkeypatch, "production")
    token = request_id_var.set("req-466-abc")
    try:
        with caplog.at_level(logging.INFO, logger=LOGGER):
            _chamador_cadastro_incompleto(_SupabaseFake([ADMIN_TECNICO]))
        linhas = [JsonFormatter().format(registro) for registro in caplog.records]
    finally:
        request_id_var.reset(token)

    assert linhas, "sem linha de log não há o que cruzar"
    assert all('"request_id": "req-466-abc"' in linha for linha in linhas)
    assert all(PROTOCOLO not in linha for linha in linhas)


# ═══════════════════════════════════════════════════════════════════════════
# Desenvolvimento não perde o diagnóstico
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("nome,chamador,vazamentos", CHAMADORES, ids=[c[0] for c in CHAMADORES])
def test_em_desenvolvimento_o_corpo_continua_no_log(monkeypatch, caplog, correio_mudo, nome, chamador, vazamentos):
    """CA: em desenvolvimento o corpo continua.

    Sem provedor configurado na máquina do desenvolvedor, o log é o único lugar
    em que se lê o aviso que se acabou de escrever."""
    _no_ambiente(monkeypatch, "development")
    supabase = _SupabaseFake([ADMIN_TECNICO])

    with caplog.at_level(logging.INFO, logger=LOGGER):
        _disparar(chamador, supabase, monkeypatch)

    log = _log_de(caplog)
    for esperado in vazamentos:
        assert esperado in log, f"{esperado!r} sumiu do log em desenvolvimento"


def test_em_desenvolvimento_o_corpo_continua_no_caminho_sem_super_admin(monkeypatch, caplog, correio_mudo):
    """Os dois caminhos, porque são duas linhas de log distintas e uma guarda
    só num deles deixaria a outra aberta (ou muda)."""
    _no_ambiente(monkeypatch, "development")

    with caplog.at_level(logging.INFO, logger=LOGGER):
        _chamador_cadastro_incompleto(_SupabaseFake([]))

    assert PROTOCOLO in _log_de(caplog)


def test_o_aviso_entregue_nao_imprime_corpo_em_ambiente_nenhum(monkeypatch, caplog):
    """O caminho saudável não tem log de corpo para guardar, nem em
    desenvolvimento: quando o email sai, o email é o sinal, e o log fica no
    INFO com a contagem (issue #373). A guarda nova não podia inventar
    impressão onde não havia."""
    _no_ambiente(monkeypatch, "development")
    monkeypatch.setattr(ouvidoria_notificacoes, "_enviar_email", lambda *args, **kwargs: True)

    with caplog.at_level(logging.INFO, logger=LOGGER):
        _chamador_cadastro_incompleto(_SupabaseFake([ADMIN_TECNICO]))

    log = _log_de(caplog)
    assert PROTOCOLO not in log
    assert "entregue a 1 destinatário(s)" in log
