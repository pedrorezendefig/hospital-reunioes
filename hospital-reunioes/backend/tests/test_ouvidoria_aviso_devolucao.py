"""Aviso à Ouvidoria quando a área devolve o caso (issue #599, PRD #598).

A fatia anterior (#600) fez a área devolver. Esta faz o ouvidor saber no mesmo
dia: a rota de devolver registra uma Notificação da Ouvidoria por pessoa com
Perfil da Ouvidoria, com o setor e o motivo no `detalhe`, e o email sai pelo
mesmo caminho do aviso de prorrogação solicitada.

Mesmo seam das fatias anteriores: HTTP no `TestClient`, com o fake do
PostgREST. O Resend nunca é chamado de verdade.
"""

from __future__ import annotations

import glob
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.limiter import limiter  # noqa: E402
from app.services import (  # noqa: E402
    ouvidoria_devolucao_a_ouvidoria,
    ouvidoria_notificacoes,
    ouvidoria_retencao,
)

sys.path.insert(0, os.path.dirname(__file__))

from test_ouvidoria_portal_setor import (  # noqa: E402
    _acionar,
    _client,
    _token_do_email,
)
from test_ouvidoria_retencao import (
    AGORA,  # noqa: E402
    _notificacao,  # noqa: E402
)
from test_ouvidoria_retencao import _SupabaseFake as _BancoDaRetencao  # noqa: E402

MOTIVO = "Este caso é do Centro Médico: a recepção não agenda consulta de especialidade."

MIGRATIONS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "supabase", "migrations")

OUVIDORIA = [
    {
        "id": "P10",
        "nome_completo": "Marta Ouvidora",
        "email": "marta@hsm.br",
        "perfil_ouvidoria": "ouvidor",
        "ativo": True,
    },
    {
        "id": "P11",
        "nome_completo": "Dr. Diretor",
        "email": "diretor@hsm.br",
        "perfil_ouvidoria": "diretoria_executiva",
        "ativo": True,
    },
    {
        "id": "P12",
        "nome_completo": "Ana Recepcao",
        "email": "ana@hsm.br",
        "perfil_ouvidoria": None,
        "ativo": True,
    },
]


def _migration_vigente_do_check_de_gatilhos() -> str:
    """A migration mais recente que redefine o CHECK de gatilhos. As migrations
    são numeradas, então a ordem alfabética é a cronológica."""
    candidatas = sorted(
        caminho
        for caminho in glob.glob(os.path.join(MIGRATIONS_DIR, "*.sql"))
        if "ouvidoria_notificacoes_gatilho_check" in open(caminho, encoding="utf-8").read()
    )
    assert candidatas, "Nenhuma migration define o CHECK de gatilhos das notificações"
    with open(candidatas[-1], encoding="utf-8") as f:
        return f.read()


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """O slowapi acumula contagem entre arquivos: sem isto, o 429 de outra
    suíte reaparece aqui como falha sem causa."""
    limiter._storage.reset()
    yield
    limiter._storage.reset()


@pytest.fixture(autouse=True)
def _nunca_envia_email_de_verdade(monkeypatch):
    """O pytest do backend carrega o `.env` real (Resend de produção)."""
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


def _portal_com_caso_na_area(monkeypatch, emails):
    """O caso já acionado, o token que chegou ao titular da Recepção e a
    Ouvidoria cadastrada para receber o aviso."""
    ja_enviados = len(emails)
    client, sb = _client(monkeypatch)
    _acionar(client)
    sb.tabelas["participantes"] = [dict(p) for p in OUVIDORIA]
    token = _token_do_email(emails[ja_enviados:])
    emails.clear()
    return client, sb, token


def _devolver(client, token, motivo: str = MOTIVO):
    return client.post(f"/api/ouvidoria-setor/{token}/devolver", json={"motivo": motivo})


def _avisos(sb) -> list[dict]:
    return [
        n
        for n in sb.tabelas["ouvidoria_notificacoes"]
        if n["gatilho"] == ouvidoria_notificacoes.GATILHO_DEVOLVIDO_A_OUVIDORIA
    ]


# =====================================================================
# 1. O gatilho no catálogo
# =====================================================================


class TestGatilhoNoCatalogo:
    def test_o_gatilho_entra_no_catalogo_e_no_check_vigente(self):
        """Critério: o gatilho entra nas listas do catálogo que os testes de
        cobertura já varrem. O CHECK vigente já o aceita desde a 098, e é por
        isso que esta fatia não traz migration."""
        assert ouvidoria_notificacoes.GATILHO_DEVOLVIDO_A_OUVIDORIA == "devolvido_a_ouvidoria"
        assert ouvidoria_notificacoes.GATILHO_DEVOLVIDO_A_OUVIDORIA in ouvidoria_notificacoes.GATILHOS
        assert f"'{ouvidoria_notificacoes.GATILHO_DEVOLVIDO_A_OUVIDORIA}'" in _migration_vigente_do_check_de_gatilhos()

    def test_o_gatilho_nao_abre_o_portal_do_setor_nem_cobra_a_area(self):
        """Quem recebe tem login no app, então o botão abre o Dossiê. Emitir
        link tokenizado aqui entregaria a porta de responder ao caso, com o
        relato integral, a quem já a tem pelo painel.

        E ele não é cobrança da área: o caso ACABOU de sair de
        `aguardando_area`, e a guarda de retenção que descarta cobrança de caso
        que andou engoliria justamente este aviso."""
        gatilho = ouvidoria_notificacoes.GATILHO_DEVOLVIDO_A_OUVIDORIA
        assert gatilho not in ouvidoria_notificacoes.GATILHOS_COM_PORTAL
        assert gatilho not in ouvidoria_notificacoes.GATILHOS_QUE_COBRAM_A_AREA


# =====================================================================
# 2. Quem é avisado
# =====================================================================


class TestQuemRecebeOAviso:
    def test_devolver_registra_um_aviso_por_pessoa_da_ouvidoria(self, monkeypatch, _nunca_envia_email_de_verdade):
        """Critério: uma notificação `devolvido_a_ouvidoria` por pessoa com
        Perfil da Ouvidoria, com setor e motivo no `detalhe`."""
        client, sb, token = _portal_com_caso_na_area(monkeypatch, _nunca_envia_email_de_verdade)

        assert _devolver(client, token).status_code == 200

        registradas = _avisos(sb)
        assert {n["destinatario_email"] for n in registradas} == {"marta@hsm.br", "diretor@hsm.br"}
        assert {n["papel_destinatario"] for n in registradas} == {"ouvidor", "diretoria_executiva"}
        for linha in registradas:
            assert linha["status"] == "enviada"
            assert "Recepcao" in linha["detalhe"], "o detalhe não diz qual área devolveu"
            assert MOTIVO in linha["detalhe"], "o detalhe não carrega o motivo escrito pela área"

    def test_o_detalhe_e_a_mesma_frase_da_trilha(self, monkeypatch, _nunca_envia_email_de_verdade):
        """O setor viaja CONGELADO na linha, e não é lido do caso na hora do
        envio: o reacionamento troca `setor` logo depois, e o reenvio do aviso
        meses adiante mostraria a área errada como a que devolveu."""
        client, sb, token = _portal_com_caso_na_area(monkeypatch, _nunca_envia_email_de_verdade)

        _devolver(client, token)

        observacao = sb.tabelas["ouvidoria_movimentos"][-1]["observacao"]
        assert _avisos(sb)[0]["detalhe"] == observacao

    def test_nem_a_area_que_devolveu_nem_o_manifestante_sao_avisados(self, monkeypatch, _nunca_envia_email_de_verdade):
        """Critério: nenhuma notificação nasce para o destinatário do link nem
        para o manifestante. Quem devolveu já sabe que devolveu, e a troca de
        área é ajuste interno (PRD #598, história 30)."""
        client, sb, token = _portal_com_caso_na_area(monkeypatch, _nunca_envia_email_de_verdade)

        _devolver(client, token)

        destinos = {n["destinatario_email"] for n in _avisos(sb)}
        assert "carlos@hsm.br" not in destinos, "o titular que devolveu recebeu aviso da própria devolução"
        assert "joana@exemplo.com" not in destinos, "o manifestante foi avisado de um ajuste interno"
        papeis = {n["papel_destinatario"] for n in sb.tabelas["ouvidoria_notificacoes"]}
        assert "manifestante" not in papeis

    def test_quem_saiu_do_hospital_nao_e_avisado(self, monkeypatch, _nunca_envia_email_de_verdade):
        """O desligamento é soft delete e não limpa `perfil_ouvidoria` (issue
        #403). O assunto deste email leva o protocolo e o corpo leva o setor.
        A ouvidora ATIVA recebe no mesmo cenário: a porta certa fica aberta."""
        client, sb, token = _portal_com_caso_na_area(monkeypatch, _nunca_envia_email_de_verdade)
        next(p for p in sb.tabelas["participantes"] if p["id"] == "P11")["ativo"] = False

        _devolver(client, token)

        assert {n["destinatario_email"] for n in _avisos(sb)} == {"marta@hsm.br"}

    def test_ouvidoria_sem_ninguem_cadastrado_nao_derruba_a_devolucao(self, monkeypatch, _nunca_envia_email_de_verdade):
        """O aviso é melhor esforço. Perder o caso devolvido porque não há a
        quem avisar deixaria a área presa a um caso que não é dela, e o link
        já foi consumido: não haveria segunda tentativa."""
        client, sb, token = _portal_com_caso_na_area(monkeypatch, _nunca_envia_email_de_verdade)
        sb.tabelas["participantes"] = []

        resposta = _devolver(client, token)

        assert resposta.status_code == 200, resposta.text
        assert next(m for m in sb.tabelas["ouvidoria_protocolos"] if m["id"] == "uuid-7")["status"] == (
            "em_classificacao"
        )
        assert _avisos(sb) == []


# =====================================================================
# 3. O email
# =====================================================================


class TestEmailDoAviso:
    def _email(self, emails, destinatario: str = "marta@hsm.br") -> dict:
        return next(e for e in emails if e["destinatario"] == destinatario)

    def test_o_email_mostra_protocolo_setor_motivo_e_o_link_do_dossie(self, monkeypatch, _nunca_envia_email_de_verdade):
        """Critério: protocolo, setor, motivo e link do Dossiê. O link é o do
        caso no app (quem recebe tem login), e não o do portal do setor."""
        client, sb, token = _portal_com_caso_na_area(monkeypatch, _nunca_envia_email_de_verdade)

        _devolver(client, token)

        protocolo = next(m for m in sb.tabelas["ouvidoria_protocolos"] if m["id"] == "uuid-7")["protocolo"]
        email = self._email(_nunca_envia_email_de_verdade)
        assert protocolo in email["assunto"]
        for corpo in (email["html"], email["texto"]):
            assert protocolo in corpo
            assert "Recepcao" in corpo
            assert MOTIVO in corpo
            assert f"http://app.test/ouvidoria/m/{protocolo}" in corpo
        assert "/ouvidoria-setor/" not in email["html"], "o aviso levou o link de responder pelo portal"

    def test_o_email_nao_carrega_o_relato_nem_a_identificacao_de_quem_manifestou(
        self, monkeypatch, _nunca_envia_email_de_verdade
    ):
        """Quem recebe já pode abrir o caso inteiro pelo Dossiê, então o email
        não precisa repetir o relato: um aviso operacional que carrega o texto
        cru do manifestante espalha por caixa de entrada o que o caso sigiloso
        e o caso anônimo existem para não espalhar.

        A régua é o marcador do que o email PROMETE mostrar (setor e motivo),
        e não só a ausência das strings: sem ela, um template que renderiza
        nada passaria verde nas duas linhas de baixo."""
        client, sb, token = _portal_com_caso_na_area(monkeypatch, _nunca_envia_email_de_verdade)
        caso = next(m for m in sb.tabelas["ouvidoria_protocolos"] if m["id"] == "uuid-7")
        caso["relato_integral"] = "Fiquei tres horas na fila e ninguem me atendeu, sou a Joana do leito 302."
        caso["manifestante_nome"] = "Joana da Silva"

        _devolver(client, token)

        email = self._email(_nunca_envia_email_de_verdade)
        for corpo in (email["html"], email["texto"]):
            assert MOTIVO in corpo, "o email perdeu o que ele existe para mostrar"
            assert "leito 302" not in corpo
            assert "Joana da Silva" not in corpo

    def test_o_aviso_e_reenviavel_pelo_dossie(self, monkeypatch, _nunca_envia_email_de_verdade):
        """Toda notificação da Ouvidoria tem botão de reenvio, e gatilho sem
        montador de email estoura no despacho (`_montar` levanta). O reenvio é
        onde isso apareceria em produção, depois do deploy."""
        client, sb, token = _portal_com_caso_na_area(monkeypatch, _nunca_envia_email_de_verdade)
        _devolver(client, token)
        aviso = _avisos(sb)[0]
        _nunca_envia_email_de_verdade.clear()

        resposta = client.post(f"/api/ouvidoria/manifestacoes/uuid-7/notificacoes/{aviso['id']}/reenviar")

        assert resposta.status_code == 201, resposta.text
        assert resposta.json()["entregue"] is True, "o gatilho chegou ao despacho sem montador de email"
        assert MOTIVO in self._email(_nunca_envia_email_de_verdade)["html"]

    def test_o_reenvio_depois_do_reacionamento_ainda_diz_quem_devolveu(
        self, monkeypatch, _nunca_envia_email_de_verdade
    ):
        """O ouvidor encaminha o caso devolvido para a área certa, e `setor` no
        caso passa a ser a NOVA. O aviso reenviado depois disso continua sendo
        sobre a devolução da Recepção: lido da coluna na hora do envio, ele
        acusaria de devolver justamente a área que recebeu o caso."""
        client, sb, token = _portal_com_caso_na_area(monkeypatch, _nunca_envia_email_de_verdade)
        _devolver(client, token)
        aviso = _avisos(sb)[0]
        next(m for m in sb.tabelas["ouvidoria_protocolos"] if m["id"] == "uuid-7")["setor"] = "Centro Medico"
        _nunca_envia_email_de_verdade.clear()

        client.post(f"/api/ouvidoria/manifestacoes/uuid-7/notificacoes/{aviso['id']}/reenviar")

        email = self._email(_nunca_envia_email_de_verdade)
        for corpo in (email["assunto"], email["html"], email["texto"]):
            assert "Recepcao" in corpo, "o aviso trocou de acusado quando o caso mudou de área"
            assert "Centro Medico" not in corpo

    def test_html_escrito_pela_area_sai_escapado(self, monkeypatch, _nunca_envia_email_de_verdade):
        """O motivo é texto livre de quem NÃO tem login: o responsável do setor
        chega pelo link do email. Ele vai parar na caixa de entrada da
        Diretoria, e uma tag viva ali viraria link ou imagem que o remetente
        escolheu, assinada pelo domínio do hospital."""
        client, sb, token = _portal_com_caso_na_area(monkeypatch, _nunca_envia_email_de_verdade)

        _devolver(client, token, '<a href="http://phishing.test">Clique aqui para responder</a>')

        html = self._email(_nunca_envia_email_de_verdade)["html"]
        assert "&lt;a href=" in html, "o motivo da área não foi escapado"
        assert '<a href="http://phishing.test"' not in html

    def test_o_email_nao_leva_travessao(self, monkeypatch, _nunca_envia_email_de_verdade):
        """ADR 0013: nem no texto da casa, nem no que a área escreveu. O motivo
        chega ao `detalhe` já peneirado pela rota, e a régua é o marcador que o
        sanitizador deixa, não a ausência do caractere."""
        client, sb, token = _portal_com_caso_na_area(monkeypatch, _nunca_envia_email_de_verdade)

        _devolver(client, token, "Não é da recepção — é do Centro Médico.")

        email = self._email(_nunca_envia_email_de_verdade)
        for corpo in (email["html"], email["texto"], email["assunto"]):
            assert "—" not in corpo and "–" not in corpo
        assert "recepção, é do Centro Médico." in email["html"]


# =====================================================================
# 4. A separação do setor e do motivo guardados juntos
# =====================================================================


class TestSetorEMotivoDoDetalhe:
    """O `detalhe` guarda a frase inteira da trilha, e o email a separa para
    mostrar o setor e o motivo em campos próprios."""

    def test_a_frase_da_trilha_volta_partida_em_setor_e_motivo(self):
        detalhe = ouvidoria_devolucao_a_ouvidoria.observacao_da_devolucao("Recepcao", MOTIVO)

        assert ouvidoria_devolucao_a_ouvidoria.setor_e_motivo(detalhe) == ("Recepcao", MOTIVO)

    def test_motivo_com_dois_pontos_nao_perde_pedaco(self):
        """O separador aparece dentro do próprio motivo o tempo todo: partir na
        ÚLTIMA ocorrência entregaria ao ouvidor meia frase."""
        motivo = "Não é nosso: quem agenda é o Centro Médico: a recepção só confirma presença."
        detalhe = ouvidoria_devolucao_a_ouvidoria.observacao_da_devolucao("Recepcao", motivo)

        assert ouvidoria_devolucao_a_ouvidoria.setor_e_motivo(detalhe) == ("Recepcao", motivo)

    def test_texto_sem_o_prefixo_vira_motivo_inteiro_sem_inventar_setor(self):
        """Linha antiga ou `detalhe` escrito por outro caminho não pode virar
        um setor inventado no email de quem despacha o caso."""
        assert ouvidoria_devolucao_a_ouvidoria.setor_e_motivo("Nao e do meu setor") == (None, "Nao e do meu setor")
        assert ouvidoria_devolucao_a_ouvidoria.setor_e_motivo(None) == (None, "")


# =====================================================================
# 5. A Retenção alcança o detalhe deste gatilho
# =====================================================================


class TestRetencaoAlcancaODetalhe:
    def test_a_anonimizacao_zera_o_detalhe_do_aviso_da_devolucao(self):
        """Critério: a Retenção alcança o `detalhe` desta notificação como das
        demais. O motivo escrito pela área pode nomear quem manifestou ("a
        senhora do leito 302 queria o Centro Médico"), e ele fica na linha
        amarrada ao mesmo `manifestacao_id`."""
        supabase = _BancoDaRetencao(
            notificacoes=[
                _notificacao(
                    1,
                    gatilho=ouvidoria_notificacoes.GATILHO_DEVOLVIDO_A_OUVIDORIA,
                    destinatario_nome="Marta Ouvidora",
                    destinatario_email="marta@hsm.br",
                    papel_destinatario="ouvidor",
                    detalhe=ouvidoria_devolucao_a_ouvidoria.observacao_da_devolucao(
                        "Recepcao", "A senhora do leito 302 queria o Centro Medico."
                    ),
                )
            ]
        )

        ouvidoria_retencao.anonimizar_encerradas_antigas(supabase, AGORA)

        assert supabase.tabelas["ouvidoria_notificacoes"][0]["detalhe"] is None
