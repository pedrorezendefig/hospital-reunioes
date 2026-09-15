"""Aviso à área antiga no redirecionamento (issue #709, PRD #706, ADR 0055).

A fatia anterior (#708) fez o caso sair de uma área e entrar em outra numa
requisição só. Esta faz a área que PERDEU o caso saber disso: email curto, com o
protocolo e a frase de encaminhado, sem motivo, sem o nome da área nova e sem
link nenhum.

Duas coisas deste arquivo merecem ser lidas antes do resto:

1. `TestAGuardaDoDespacharNaoAlcancaOAviso` é o teste que a fatia existe para
   ter. A guarda que a issue #707 pôs no `despachar` só deixa emitir para quem
   PERTENCE ao cadastro do setor ATUAL do caso, e o destinatário deste aviso é,
   por definição, alguém que já não pertence. A guarda não o alcança porque ela
   só pergunta por quem VAI receber link, e este aviso não recebe link nenhum.
   O teste exercita o job de verdade, sem monkeypatch na guarda, e traz a
   contraprova ao lado: no MESMO banco, no MESMO instante, a cobrança da área
   antiga é descartada e o acionamento da área nova sai.
2. As asserções do email são do MARCADOR positivo, não da ausência: o que mata o
   mutante que lê o `setor` do caso (e entrega à área antiga o nome da área
   nova) é afirmar que o email diz "Recepcao", não procurar por "Centro Medico".

Mesmo seam da #708: HTTP no `TestClient`, sobre o fake do PostgREST da fatia da
validação. O Resend nunca é chamado de verdade.
"""

from __future__ import annotations

import datetime as dt
import glob
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services import (  # noqa: E402
    ouvidoria_notificacoes,
    ouvidoria_redirecionamento,
)

sys.path.insert(0, os.path.dirname(__file__))

from test_ouvidoria_redirecionamento import (  # noqa: E402
    EMAIL_DA_RECEPCAO,
    EMAIL_DO_SETOR_NOVO,
    MIGRATIONS_DIR,
    MOTIVO,
    REDIRECIONAMENTO,
    SETOR_NOVO,
    _banco,
    _caso,
    _com_o_caso_na_recepcao,
    _notificacoes,
    _redirecionar,
)
from test_ouvidoria_validacao_acionamento import EXTRATO, _manifestacao  # noqa: E402

GATILHO = ouvidoria_notificacoes.GATILHO_REDIRECIONAMENTO_AREA
PROTOCOLO = "2026-0007"
SETOR_ANTIGO = "Recepcao"

# 22h30 de quarta em Brasília, o dia seguinte ao acionamento inicial. Fora do
# expediente de propósito: é a única forma de ver a janela comercial agir, e é o
# cenário em que a notificação fica na fila para o job levar.
REDIRECIONADO_DE_MADRUGADA = dt.datetime(2026, 8, 27, 1, 30, tzinfo=dt.UTC)
# 8h de quinta em Brasília: o expediente abrindo, quando o job varre a fila.
ABERTURA_SEGUINTE = dt.datetime(2026, 8, 27, 11, 0, tzinfo=dt.UTC)


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """O slowapi acumula contagem entre arquivos: sem isto, o 429 de outra
    suíte reaparece aqui como falha sem causa."""
    from app.limiter import limiter

    limiter._storage.reset()
    yield
    limiter._storage.reset()


@pytest.fixture(autouse=True)
def _nunca_envia_email_de_verdade(monkeypatch):
    """O pytest do backend carrega o `.env` real (Resend de produção). Todo
    teste deste arquivo passa pelo mock, mesmo os que não olham o email."""
    enviados: list[dict] = []

    def _fake(destinatario, assunto, html_content, texto_fallback):
        enviados.append(
            {
                "destinatario": destinatario,
                "assunto": assunto,
                "html": html_content,
                "texto": texto_fallback,
            }
        )
        return True

    monkeypatch.setattr(ouvidoria_notificacoes, "_enviar_email", _fake)
    return enviados


def _avisos(supabase) -> list[dict]:
    return _notificacoes(supabase, GATILHO)


def _emails_para(enviados, destinatario: str) -> list[dict]:
    return [e for e in enviados if e["destinatario"] == destinatario]


def _de_madrugada(monkeypatch, emails, **kwargs):
    """O caso na Recepção, com o relógio parado numa quarta às 22h30.

    O redirecionamento feito aqui deixa TODA notificação da leva na fila, que é
    o que permite ver a janela comercial e chamar o job à mão."""
    from app.routers import ouvidoria as ouvidoria_router

    client, supabase = _com_o_caso_na_recepcao(monkeypatch, emails, **kwargs)
    monkeypatch.setattr(ouvidoria_router, "agora_utc", lambda: REDIRECIONADO_DE_MADRUGADA)
    return client, supabase


# =====================================================================
# 1. O gatilho no catálogo
# =====================================================================


class TestGatilhoNoCatalogo:
    def test_o_gatilho_entra_no_catalogo(self):
        assert GATILHO == "redirecionamento_area"
        assert GATILHO in ouvidoria_notificacoes.GATILHOS

    def test_o_gatilho_nao_leva_link_e_nao_cobra_a_area(self):
        """Terceiro critério de aceite, e a decisão que sustenta a fatia.

        Fora de `GATILHOS_COM_PORTAL` porque a área antiga PERDEU o acesso: a
        issue #707 derrubou os links dela na mesma requisição, e emitir um token
        aqui reabriria o buraco que a fatia anterior fechou.

        Fora de `GATILHOS_QUE_COBRAM_A_AREA` porque o aviso não pede resposta e
        o caso já está em `aguardando_area` com OUTRA área quando o email sai: na
        tupla, a guarda de status descartaria o aviso em toda vez que o
        redirecionamento desse certo."""
        assert GATILHO not in ouvidoria_notificacoes.GATILHOS_COM_PORTAL
        assert GATILHO not in ouvidoria_notificacoes.GATILHOS_QUE_COBRAM_A_AREA


# =====================================================================
# 2. A guarda do despachar (issue #707) e o aviso
# =====================================================================


class TestAGuardaDoDespacharNaoAlcancaOAviso:
    """O nó desta fatia, exercitado pelo job de verdade.

    A guarda `responde_pelo_setor_do_caso` só roda para gatilho de
    `GATILHOS_COM_PORTAL`, e marca `falha` TERMINAL (o job só relê `agendada`,
    a tentativa não é incrementada e ninguém é alertado). O aviso à área antiga
    sairia em silêncio da fila se entrasse naquela tupla."""

    def test_o_aviso_sai_para_quem_ja_nao_responde_pelo_setor_do_caso(self, monkeypatch, _nunca_envia_email_de_verdade):
        """O caso está com o Centro Medico e o aviso vai para o titular da
        Recepção, que não está no cadastro do Centro Medico. Ele sai."""
        client, supabase = _de_madrugada(monkeypatch, _nunca_envia_email_de_verdade)
        assert _redirecionar(client).status_code == 201
        assert _caso(supabase)["setor"] == SETOR_NOVO
        aviso = _avisos(supabase)[0]
        assert aviso["status"] == "agendada", "o aviso precisa estar na fila para o job levá-lo"
        assert aviso["destinatario_email"] == EMAIL_DA_RECEPCAO
        assert EMAIL_DA_RECEPCAO not in {
            r["email"] for r in supabase.tabelas["ouvidoria_setor_responsaveis"] if r["setor"] == SETOR_NOVO
        }, "o cenário perdeu a premissa: o destinatário não pode pertencer ao setor novo"

        ouvidoria_notificacoes.despachar_pendentes(supabase, ABERTURA_SEGUINTE, frozenset())

        entregue = next(n for n in _avisos(supabase) if n["id"] == aviso["id"])
        assert entregue["status"] == "enviada", entregue.get("ultimo_erro")
        assert entregue.get("ultimo_erro") is None
        assert _emails_para(_nunca_envia_email_de_verdade, EMAIL_DA_RECEPCAO), "a área antiga não foi avisada"

    def test_contraprova_a_guarda_esta_viva_e_quem_tem_direito_continua_recebendo(
        self, monkeypatch, _nunca_envia_email_de_verdade
    ):
        """Sem esta contraprova, o teste acima passaria verde com a guarda
        trocada por `True`, ou sem guarda nenhuma.

        No MESMO banco e no MESMO instante, três notificações e três destinos
        diferentes:

        - a cobrança retida da área ANTIGA (gatilho com portal, destinatário
          fora do cadastro do setor do caso) é descartada com a frase da #707;
        - o acionamento da área NOVA (gatilho com portal, destinatário dentro do
          cadastro) sai;
        - o aviso à área antiga sai, embora o destinatário dele seja o MESMO da
          cobrança descartada. A diferença é só o gatilho."""
        client, supabase = _de_madrugada(monkeypatch, _nunca_envia_email_de_verdade)
        assert _redirecionar(client).status_code == 201
        cobranca_da_area_antiga = ouvidoria_notificacoes.registrar(
            supabase,
            manifestacao_id="uuid-7",
            gatilho=ouvidoria_notificacoes.GATILHO_PRAZO_ROMPIDO,
            destinatario_nome="Carlos Titular",
            destinatario_email=EMAIL_DA_RECEPCAO,
            papel_destinatario="titular",
            enviar_a_partir_de=REDIRECIONADO_DE_MADRUGADA,
        )

        ouvidoria_notificacoes.despachar_pendentes(supabase, ABERTURA_SEGUINTE, frozenset())

        descartada = next(
            n for n in supabase.tabelas["ouvidoria_notificacoes"] if n["id"] == cobranca_da_area_antiga["id"]
        )
        assert descartada["status"] == "falha"
        assert descartada["ultimo_erro"] == ouvidoria_notificacoes.LINK_FORA_DA_AREA
        acionamento = _notificacoes(supabase, ouvidoria_notificacoes.GATILHO_NOVA_DEMANDA)[-1]
        assert acionamento["destinatario_email"] == EMAIL_DO_SETOR_NOVO
        assert acionamento["status"] == "enviada", "a área que TEM direito de responder deixou de ser acionada"
        assert _avisos(supabase)[0]["status"] == "enviada"

    def test_o_aviso_sai_mesmo_com_o_caso_ja_fora_de_aguardando_area(self, monkeypatch, _nunca_envia_email_de_verdade):
        """A outra guarda do `despachar`, a de status, também não alcança o
        aviso, e isso precisa de prova de comportamento e não só da tupla.

        Retido pela janela comercial, o aviso acorda num caso que a área NOVA já
        respondeu de madrugada. Ele sai assim mesmo: ele não cobra ninguém, ele
        libera. Em `GATILHOS_QUE_COBRAM_A_AREA` a guarda o descartaria com
        `falha` TERMINAL, e a área antiga continuaria apurando um caso que já não
        é dela."""
        client, supabase = _de_madrugada(monkeypatch, _nunca_envia_email_de_verdade)
        assert _redirecionar(client).status_code == 201
        _caso(supabase)["status"] = "respondido"

        ouvidoria_notificacoes.despachar_pendentes(supabase, ABERTURA_SEGUINTE, frozenset())

        aviso = _avisos(supabase)[0]
        assert aviso["status"] == "enviada", aviso.get("ultimo_erro")
        assert _emails_para(_nunca_envia_email_de_verdade, EMAIL_DA_RECEPCAO)


# =====================================================================
# 3. A notificação que nasce no redirecionamento
# =====================================================================


class TestOAvisoNasceNoRedirecionamento:
    def test_redirecionar_registra_o_aviso_alem_do_acionamento_da_area_nova(
        self, monkeypatch, _nunca_envia_email_de_verdade
    ):
        """Primeiro critério de aceite: nasce o `redirecionamento_area` para o
        destinatário do último acionamento da área antiga, ALÉM da
        `nova_demanda` da área nova."""
        client, supabase = _com_o_caso_na_recepcao(monkeypatch, _nunca_envia_email_de_verdade)

        assert _redirecionar(client).status_code == 201

        avisos = _avisos(supabase)
        assert len(avisos) == 1
        assert avisos[0]["destinatario_email"] == EMAIL_DA_RECEPCAO
        assert avisos[0]["destinatario_nome"] == "Carlos Titular"
        assert avisos[0]["papel_destinatario"] == "titular"
        assert (
            _notificacoes(supabase, ouvidoria_notificacoes.GATILHO_NOVA_DEMANDA)[-1]["destinatario_email"]
            == EMAIL_DO_SETOR_NOVO
        )

    def test_o_destinatario_e_o_da_area_antiga_e_nao_o_da_nova(self, monkeypatch, _nunca_envia_email_de_verdade):
        """O acionamento da área nova registra a `nova_demanda` DELA na mesma
        requisição. Lido depois disso, "o último acionamento" já seria o do
        Centro Medico, e o aviso de que a demanda saiu iria para quem acabou de
        recebê-la."""
        client, supabase = _com_o_caso_na_recepcao(monkeypatch, _nunca_envia_email_de_verdade)

        _redirecionar(client)

        assert _avisos(supabase)[0]["destinatario_email"] == EMAIL_DA_RECEPCAO

    def test_o_detalhe_guarda_so_o_protocolo_e_o_setor_antigo(self, monkeypatch, _nunca_envia_email_de_verdade):
        """Quinto critério de aceite. O setor fica CONGELADO no ato: o
        acionamento sobrescreve `setor` no caso na mesma requisição, e o reenvio
        meses adiante leria a área nova."""
        client, supabase = _com_o_caso_na_recepcao(monkeypatch, _nunca_envia_email_de_verdade)

        _redirecionar(client)

        detalhe = _avisos(supabase)[0]["detalhe"]
        assert ouvidoria_redirecionamento.protocolo_e_setor(detalhe) == (PROTOCOLO, SETOR_ANTIGO)
        assert MOTIVO not in detalhe, "o motivo do ouvidor vazou para o registro do aviso"
        assert SETOR_NOVO not in detalhe

    def test_o_aviso_nasce_depois_do_acionamento_da_area_nova(self, monkeypatch, _nunca_envia_email_de_verdade):
        """O aviso só é verdade quando a área nova de fato recebeu o caso: se o
        acionamento falha, a área antiga continua sendo a área do caso."""
        client, supabase = _com_o_caso_na_recepcao(monkeypatch, _nunca_envia_email_de_verdade)

        _redirecionar(client)

        gatilhos = [n["gatilho"] for n in supabase.tabelas["ouvidoria_notificacoes"]]
        assert gatilhos[-2:] == [ouvidoria_notificacoes.GATILHO_NOVA_DEMANDA, GATILHO]

    def test_acionamento_recusado_nao_avisa_a_area_antiga(self, monkeypatch, _nunca_envia_email_de_verdade):
        """Contraprova da ordem: o redirecionamento para uma área sem
        responsável é recusado ANTES de qualquer escrita, e a área antiga não
        pode receber um aviso de que perdeu um caso que continua com ela."""
        supabase = _banco()
        supabase.tabelas["setores"].append({"id": "s3", "nome": "Farmacia", "ativo": True})
        client, supabase = _com_o_caso_na_recepcao(monkeypatch, _nunca_envia_email_de_verdade, supabase=supabase)

        resposta = _redirecionar(client, {**REDIRECIONAMENTO, "setor": "Farmacia"})

        assert resposta.status_code == 409
        assert _avisos(supabase) == []
        assert _caso(supabase)["setor"] == SETOR_ANTIGO

    def test_o_redirecionamento_nao_cai_quando_o_aviso_nao_tem_a_quem_ir(
        self, monkeypatch, _nunca_envia_email_de_verdade
    ):
        """Guarda-corpo que não vira indisponibilidade: caso sem acionamento
        anterior registrado (linha antiga, ou limpa pela Retenção) continua
        sendo redirecionado. O aviso é cortesia à área que perdeu o caso, não
        condição do ato."""
        client, supabase = _com_o_caso_na_recepcao(monkeypatch, _nunca_envia_email_de_verdade)
        supabase.tabelas["ouvidoria_notificacoes"].clear()

        resposta = _redirecionar(client)

        assert resposta.status_code == 201, resposta.text
        assert _caso(supabase)["setor"] == SETOR_NOVO
        assert _avisos(supabase) == []


# =====================================================================
# 4. O email
# =====================================================================


class TestOEmailDoAviso:
    def _email_da_area_antiga(self, monkeypatch, emails) -> dict:
        client, _supabase = _com_o_caso_na_recepcao(monkeypatch, emails)
        assert _redirecionar(client).status_code == 201
        entregues = _emails_para(emails, EMAIL_DA_RECEPCAO)
        assert len(entregues) == 1, "a área antiga recebeu zero ou mais de um email"
        return entregues[0]

    def test_o_email_diz_o_protocolo_e_a_frase_de_encaminhado(self, monkeypatch, _nunca_envia_email_de_verdade):
        """Segundo critério de aceite, pelo marcador positivo."""
        email = self._email_da_area_antiga(monkeypatch, _nunca_envia_email_de_verdade)

        assert email["assunto"] == f"Ouvidoria {PROTOCOLO}: a demanda foi encaminhada a outra area"
        assert PROTOCOLO in email["html"]
        assert PROTOCOLO in email["texto"]
        assert "encaminhou esta manifestação a outra área" in email["html"]
        assert "Não é preciso responder" in email["html"]
        assert "Nao e preciso responder" in email["texto"]

    def test_o_email_nomeia_a_area_antiga_e_nao_a_nova(self, monkeypatch, _nunca_envia_email_de_verdade):
        """O marcador que mata o mutante que lê `setor` do caso: na hora em que
        o email é montado, aquela coluna já vale Centro Medico."""
        email = self._email_da_area_antiga(monkeypatch, _nunca_envia_email_de_verdade)

        assert f"Setor: <strong>{SETOR_ANTIGO}</strong>" in email["html"]
        assert f"do setor {SETOR_ANTIGO}" in email["texto"]
        assert SETOR_NOVO not in email["html"]
        assert SETOR_NOVO not in email["texto"]

    def test_o_email_nao_leva_link_nenhum(self, monkeypatch, _nunca_envia_email_de_verdade):
        """Segundo critério, e a razão de existir da fatia anterior: a área
        antiga perdeu o acesso ao caso (issue #707). Um link aqui reabriria o
        buraco na fatia seguinte.

        A asserção é estrutural (nenhuma âncora no HTML), e não a busca por uma
        URL específica: assim ela pega também o botão que aponte para o app, que
        o aviso da Devolução à Ouvidoria tem e este não pode ter."""
        email = self._email_da_area_antiga(monkeypatch, _nunca_envia_email_de_verdade)

        assert "href" not in email["html"].lower()
        assert "<a " not in email["html"].lower()
        assert "http" not in email["texto"]
        assert "ouvidoria-setor" not in email["html"]
        assert "Os links que você recebeu para responder este caso não valem mais" in email["html"]

    def test_o_email_nao_leva_motivo_extrato_nem_relato(self, monkeypatch, _nunca_envia_email_de_verdade):
        """O ADR 0055, decisão 4: sem motivo. E, como todo email do módulo, sem
        o que quem manifestou escreveu (RN-79)."""
        email = self._email_da_area_antiga(monkeypatch, _nunca_envia_email_de_verdade)

        for proibido in (MOTIVO, EXTRATO, _manifestacao()["relato_integral"], _manifestacao()["manifestante_nome"]):
            assert proibido not in email["html"]
            assert proibido not in email["texto"]

    def test_o_email_nao_afirma_prazo_nem_gravidade(self, monkeypatch, _nunca_envia_email_de_verdade):
        """O relógio da área acabou de parar, e a faixa de gravidade diz com que
        pressa agir num email cuja mensagem é que não há o que fazer."""
        email = self._email_da_area_antiga(monkeypatch, _nunca_envia_email_de_verdade)

        assert "Prazo" not in email["html"]
        assert "MÉDIO" not in email["html"]

    @pytest.mark.parametrize("campo", ["assunto", "html", "texto"])
    def test_sem_travessao_nem_meia_risca(self, monkeypatch, _nunca_envia_email_de_verdade, campo):
        """ADR 0013, e o grep do CI nos templates. O email é texto que o time
        LÊ."""
        email = self._email_da_area_antiga(monkeypatch, _nunca_envia_email_de_verdade)

        assert chr(0x2014) not in email[campo]
        assert chr(0x2013) not in email[campo]

    def test_detalhe_ilegivel_nao_vira_email_generico(self):
        """Sem protocolo o aviso não diz a que caso se refere. A linha fica em
        falha, com o motivo visível no Dossiê (issue #707), em vez de um email
        mudo na caixa de quem já não responde pelo caso."""
        with pytest.raises(ValueError):
            ouvidoria_notificacoes.montar_redirecionamento_area("Carlos Titular", "texto de outro caminho")


# =====================================================================
# 5. Janela comercial e reenvio
# =====================================================================


class TestJanelaComercialEReenvio:
    def test_o_aviso_espera_o_expediente_mesmo_no_caso_critico(self, monkeypatch, _nunca_envia_email_de_verdade):
        """Quarto critério: o aviso entra na janela comercial como as demais não
        críticas.

        O caso crítico é a única forma de VER a diferença: no mesmo
        redirecionamento, o acionamento da área nova sai às 22h30 (o crítico não
        espera o expediente) e o aviso à área antiga fica na fila até as 8h. Sem
        esta separação, o mutante que passa a gravidade do caso para
        `quando_enviar` acordaria de madrugada, por um caso grave, exatamente a
        pessoa que não tem mais nada a fazer por ele."""
        client, supabase = _de_madrugada(monkeypatch, _nunca_envia_email_de_verdade)

        resposta = _redirecionar(client, {**REDIRECIONAMENTO, "gravidade": "critico"})

        assert resposta.status_code == 201, resposta.text
        acionamento = _notificacoes(supabase, ouvidoria_notificacoes.GATILHO_NOVA_DEMANDA)[-1]
        assert acionamento["status"] == "enviada", "o crítico da área nova deixou de sair na hora"
        aviso = _avisos(supabase)[0]
        assert aviso["status"] == "agendada"
        assert aviso["enviar_a_partir_de"].startswith("2026-08-27T08:00")
        assert _emails_para(_nunca_envia_email_de_verdade, EMAIL_DA_RECEPCAO) == []

    def test_o_aviso_sai_na_hora_dentro_do_expediente(self, monkeypatch, _nunca_envia_email_de_verdade):
        """Contraprova da janela: no expediente, a área antiga é avisada no ato,
        e não fica na fila."""
        client, supabase = _com_o_caso_na_recepcao(monkeypatch, _nunca_envia_email_de_verdade)

        _redirecionar(client)

        assert _avisos(supabase)[0]["status"] == "enviada"

    def test_o_aviso_e_reenviavel_pela_rota_de_reenvio(self, monkeypatch, _nunca_envia_email_de_verdade):
        """Quarto critério: reenviável pela rota que já existe, com o MESMO
        `detalhe`. É ele que carrega o setor congelado, e sem a cópia o reenvio
        mandaria um email sem protocolo."""
        client, supabase = _com_o_caso_na_recepcao(monkeypatch, _nunca_envia_email_de_verdade)
        _redirecionar(client)
        original = _avisos(supabase)[0]
        _nunca_envia_email_de_verdade.clear()

        resposta = client.post(f"/api/ouvidoria/manifestacoes/uuid-7/notificacoes/{original['id']}/reenviar")

        assert resposta.status_code == 201, resposta.text
        assert resposta.json()["entregue"] is True
        copia = next(n for n in _avisos(supabase) if n["id"] != original["id"])
        assert copia["detalhe"] == original["detalhe"]
        assert copia["destinatario_email"] == EMAIL_DA_RECEPCAO
        reenviado = _emails_para(_nunca_envia_email_de_verdade, EMAIL_DA_RECEPCAO)
        assert len(reenviado) == 1
        assert PROTOCOLO in reenviado[0]["assunto"]
        assert SETOR_NOVO not in reenviado[0]["html"], "o reenvio leu o setor do caso, que já é o da área nova"


# =====================================================================
# 6. O CHECK de gatilhos no banco
# =====================================================================


def _migration_vigente_do_check_de_gatilhos() -> str:
    """A migration mais recente que redefine o CHECK de gatilhos. As migrations
    são numeradas, então a ordem alfabética é a cronológica.

    Mesmo helper (e mesma razão) do arquivo do aviso da Devolução à Ouvidoria:
    número fixo aqui faria a próxima fatia que acrescentar um gatilho derrubar o
    teste sem ter quebrado nada."""
    candidatas = sorted(
        caminho
        for caminho in glob.glob(os.path.join(MIGRATIONS_DIR, "*.sql"))
        if "ouvidoria_notificacoes_gatilho_check" in open(caminho, encoding="utf-8").read()
    )
    assert candidatas, "Nenhuma migration define o CHECK de gatilhos das notificações"
    with open(candidatas[-1], encoding="utf-8") as f:
        return f.read()


class TestOCheckDeGatilhosAceitaOAviso:
    """A coluna `gatilho` tem CHECK de lista fechada. Sem o gatilho novo lá
    dentro, o INSERT volta 23514, `registrar` engole a exceção e devolve None, e
    a área antiga nunca é avisada, em produção, em silêncio. O fake do PostgREST
    não aplica CHECK, então é esta leitura do arquivo que segura a regra."""

    def test_o_gatilho_entra_no_check_vigente(self):
        """A lista INTEIRA já é cobrada por três testes antigos (o do acuse, o
        do aviso de encerramento e o da Devolução à Ouvidoria varrem
        `GATILHOS`). O que falta aqui é o CHECK ser aplicado dentro de uma
        transação: ele roda à mão em produção, e a tabela não pode ficar sem
        constraint se a segunda metade falhar."""
        ddl = _migration_vigente_do_check_de_gatilhos()
        assert f"'{GATILHO}'" in ddl
        assert "BEGIN;" in ddl and "COMMIT;" in ddl
