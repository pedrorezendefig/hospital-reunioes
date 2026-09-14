"""Revogação dos links da área antiga no acionamento (issue #707, PRD #706, ADR 0055).

Todo acionamento que sai de `em_classificacao` derruba os links vivos do caso
antes de emitir o link novo. Sem isso, depois de uma Devolução à Ouvidoria e do
reacionamento em OUTRA área, o link do acionamento anterior e cada link de
cobrança da área antiga continuam abrindo o portal, e a área errada responde
pelo caso da área certa.

Cobre os critérios de aceite da #707 pelo mesmo seam das fatias anteriores do
portal do setor: HTTP no `TestClient`, com o fake do PostgREST. O Resend nunca
é chamado de verdade.
"""

from __future__ import annotations

import datetime as dt
import os
import re
import sys

import httpx
import pytest
from postgrest.exceptions import APIError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.limiter import limiter  # noqa: E402
from app.services import ouvidoria_notificacoes, ouvidoria_setor_tokens  # noqa: E402

sys.path.insert(0, os.path.dirname(__file__))

from test_ouvidoria_portal_setor import (  # noqa: E402
    VALIDACAO,
    _acionar,
    _client,
    _Falha,
    _responsavel,
)

MOTIVO = "Este caso é do Centro Médico: a recepção não agenda consulta de especialidade."

AREA_NOVA = "Centro Medico"
EMAIL_DA_AREA_NOVA = "helena@hsm.br"

# A frase que o responsável da área antiga lê ao abrir o link velho.
FRASE_DO_LINK_REVOGADO = "Este caso foi encaminhado a outra área; este link não vale mais"

# Um instante qualquer depois do reacionamento dos testes deste arquivo, e o
# instante em que a cobrança retida pela janela comercial foi agendada (antes).
DEPOIS_DA_REVOGACAO = dt.datetime(2026, 8, 25, 18, 0, tzinfo=dt.UTC)
QUANDO_A_JANELA_ABRE = dt.datetime(2026, 8, 25, 16, 0, tzinfo=dt.UTC)

MIGRATIONS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "supabase", "migrations")
MIGRATION = "106_ouvidoria_token_do_setor_revogado.sql"


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """O slowapi acumula contagem entre arquivos: sem isto, o 429 de outra
    suíte reaparece aqui como falha sem causa."""
    limiter._storage.reset()
    yield
    limiter._storage.reset()


@pytest.fixture(autouse=True)
def _nunca_envia_email_de_verdade(monkeypatch):
    """O pytest do backend carrega o `.env` real (Resend de produção). Mesma
    trava do arquivo do portal do setor, no mesmo ponto único."""
    enviados: list[dict] = []

    def _fake(destinatario, assunto, html_content, texto_fallback):
        enviados.append({"destinatario": destinatario, "assunto": assunto, "texto": texto_fallback})
        return True

    monkeypatch.setattr(ouvidoria_notificacoes, "_enviar_email", _fake)
    return enviados


def _token_para(emails: list[dict], destinatario: str) -> str:
    """O token do ÚLTIMO email que saiu para aquele endereço, que é o link que
    a pessoa tem na caixa de entrada agora."""
    email = next(e for e in reversed(emails) if e["destinatario"] == destinatario)
    achado = re.search(r"http://app\.test/ouvidoria-setor/([A-Za-z0-9_-]+)", email["texto"])
    assert achado, f"O email não tem link tokenizado: {email['texto']}"
    return achado.group(1)


def _cobrar(client) -> None:
    resposta = client.post("/api/ouvidoria/manifestacoes/uuid-7/cobrar-setor")
    assert resposta.status_code == 201, resposta.text


def _com_a_segunda_area(monkeypatch, emails):
    """O caso acionado na Recepção, com a segunda área já cadastrada e pronta
    para receber o reacionamento."""
    client, sb = _client(monkeypatch)
    sb.tabelas["setores"].append({"id": "s2", "nome": AREA_NOVA, "ativo": True})
    sb.tabelas["ouvidoria_setor_responsaveis"].append(
        _responsavel(setor=AREA_NOVA, nome="Helena Titular", email=EMAIL_DA_AREA_NOVA, id="resp-centro")
    )
    _acionar(client)
    return client, sb


def _devolver_e_reacionar(client, emails) -> None:
    """O caminho que já existe hoje: a área devolve pelo link da última
    cobrança, e o ouvidor reaciona em outra área."""
    devolucao = client.post(
        f"/api/ouvidoria-setor/{_token_para(emails, 'carlos@hsm.br')}/devolver",
        json={"motivo": MOTIVO},
    )
    assert devolucao.status_code == 200, devolucao.text
    reacionamento = client.post(
        "/api/ouvidoria/manifestacoes/uuid-7/validar",
        json=VALIDACAO | {"setor": AREA_NOVA},
    )
    assert reacionamento.status_code == 200, reacionamento.text


class TestMigration:
    """Critério 1: a migration só acrescenta a coluna."""

    def test_a_coluna_nasce_na_tabela_de_tokens_e_nada_mais_muda(self):
        with open(os.path.join(MIGRATIONS_DIR, MIGRATION), encoding="utf-8") as f:
            ddl = f.read()
        assert "ALTER TABLE ouvidoria_setor_tokens" in ddl
        assert "ADD COLUMN IF NOT EXISTS revogado_em TIMESTAMPTZ" in ddl
        assert "CREATE TABLE" not in ddl, "a fatia não cria tabela, então não há RLS nova a ligar"
        assert "DROP" not in ddl


class TestLinksDaAreaAntiga:
    """Critério 2: o reacionamento em outra área derruba o que sobrou da antiga."""

    def test_acionamento_e_cobranca_da_area_antiga_param_de_valer(self, monkeypatch, _nunca_envia_email_de_verdade):
        emails = _nunca_envia_email_de_verdade
        client, _sb = _com_a_segunda_area(monkeypatch, emails)
        acionamento = _token_para(emails, "carlos@hsm.br")
        _cobrar(client)
        cobranca = _token_para(emails, "carlos@hsm.br")
        _cobrar(client)
        assert acionamento != cobranca

        _devolver_e_reacionar(client, emails)

        for velho, rotulo in ((acionamento, "acionamento"), (cobranca, "cobrança")):
            resposta = client.get(f"/api/ouvidoria-setor/{velho}")
            assert resposta.status_code == 410, f"o link de {rotulo} continuou abrindo o caso: {resposta.text}"
            assert resposta.json()["detail"] == FRASE_DO_LINK_REVOGADO
        assert "2026-0007" not in client.get(f"/api/ouvidoria-setor/{acionamento}").text

    def test_o_link_da_area_nova_funciona(self, monkeypatch, _nunca_envia_email_de_verdade):
        """A outra metade do critério, e a prova de que a revogação vem ANTES da
        emissão: invertida a ordem, o link recém-emitido nasce revogado."""
        emails = _nunca_envia_email_de_verdade
        client, _sb = _com_a_segunda_area(monkeypatch, emails)
        _cobrar(client)
        _devolver_e_reacionar(client, emails)

        resposta = client.get(f"/api/ouvidoria-setor/{_token_para(emails, EMAIL_DA_AREA_NOVA)}")
        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["setor"] == AREA_NOVA
        assert resposta.json()["aceita_resposta"] is True

    def test_a_revogacao_nao_toca_a_marca_de_uso(self, monkeypatch, _nunca_envia_email_de_verdade):
        """Critério 3: o link que a área consumiu para devolver continua dizendo
        que FOI USADO. São duas verdades diferentes na trilha, e uma não pode
        virar a outra: o carimbo de uso que estava lá continua igual depois da
        revogação, e quem o abre lê que usou, não que o caso mudou de área."""
        emails = _nunca_envia_email_de_verdade
        client, sb = _com_a_segunda_area(monkeypatch, emails)
        _cobrar(client)
        usado = _token_para(emails, "carlos@hsm.br")

        devolucao = client.post(f"/api/ouvidoria-setor/{usado}/devolver", json={"motivo": MOTIVO})
        assert devolucao.status_code == 200, devolucao.text
        linha = next(t for t in sb.tabelas["ouvidoria_setor_tokens"] if t.get("usado_em"))
        carimbo_de_uso = linha["usado_em"]

        reacionamento = client.post(
            "/api/ouvidoria/manifestacoes/uuid-7/validar",
            json=VALIDACAO | {"setor": AREA_NOVA},
        )
        assert reacionamento.status_code == 200, reacionamento.text

        assert linha["usado_em"] == carimbo_de_uso, "a revogação reescreveu a marca de uso"
        resposta = client.get(f"/api/ouvidoria-setor/{usado}")
        assert resposta.status_code == 410
        assert "já foi usado" in resposta.json()["detail"]

    def test_o_link_com_claim_em_voo_tambem_e_revogado(self, monkeypatch, _nunca_envia_email_de_verdade):
        """A corrida entre o portal e o reacionamento, pelas duas pontas.

        O token com claim em voo tem `usado_em` preenchido. Se a revogação o
        pulasse, uma falha depois do claim soltaria o carimbo e devolveria à
        área ANTIGA um link vivo. E o claim que entra DEPOIS da revogação não
        pode gravar a resposta da área que já saiu do caso."""
        emails = _nunca_envia_email_de_verdade
        client, sb = _com_a_segunda_area(monkeypatch, emails)
        em_voo = _token_para(emails, "carlos@hsm.br")
        vinculo = sb.tabelas["ouvidoria_setor_tokens"][0]
        vinculo["usado_em"] = "2026-08-25T16:59:00+00:00"

        _cobrar(client)
        _devolver_e_reacionar(client, emails)

        assert vinculo.get("revogado_em"), "o token com claim em voo escapou da revogação"
        # A ponta do rollback: soltar o claim não ressuscita o link derrubado.
        ouvidoria_setor_tokens.devolver(sb, vinculo, "2026-08-25T16:59:00+00:00")
        assert vinculo["usado_em"] == "2026-08-25T16:59:00+00:00"
        assert client.get(f"/api/ouvidoria-setor/{em_voo}").status_code == 410

        # A outra ponta: o claim que chega depois da revogação não passa.
        vinculo["usado_em"] = None
        assert ouvidoria_setor_tokens.consumir(sb, vinculo, DEPOIS_DA_REVOGACAO) is False
        assert vinculo["usado_em"] is None

    def test_o_link_vencido_continua_dizendo_que_venceu(self, monkeypatch, _nunca_envia_email_de_verdade):
        """Critério 3, outra metade: a revogação não reescreve a recusa de quem
        já tinha vencido por conta do calendário."""
        emails = _nunca_envia_email_de_verdade
        client, sb = _com_a_segunda_area(monkeypatch, emails)
        vencido = _token_para(emails, "carlos@hsm.br")
        sb.tabelas["ouvidoria_setor_tokens"][0]["expira_em"] = "2026-08-01T00:00:00+00:00"
        _cobrar(client)
        _devolver_e_reacionar(client, emails)

        resposta = client.get(f"/api/ouvidoria-setor/{vencido}")
        assert resposta.status_code == 410
        assert "expirou" in resposta.json()["detail"]

    def test_o_link_de_outro_caso_nao_e_derrubado(self, monkeypatch, _nunca_envia_email_de_verdade):
        """A revogação é do caso que está sendo acionado, e de mais nenhum: o
        titular que responde por outro protocolo não perde o link dele."""
        emails = _nunca_envia_email_de_verdade
        client, sb = _com_a_segunda_area(monkeypatch, emails)
        de_outro_caso = ouvidoria_setor_tokens.emitir(
            sb,
            manifestacao_id="uuid-8",
            destinatario_nome="Carlos Titular",
            destinatario_email="carlos@hsm.br",
        )
        _cobrar(client)
        _devolver_e_reacionar(client, emails)

        linha = next(t for t in sb.tabelas["ouvidoria_setor_tokens"] if t["manifestacao_id"] == "uuid-8")
        assert linha.get("revogado_em") is None
        assert de_outro_caso


class TestAcionamentoSemLinkVivo:
    """Critério 4: revogar zero links é no-op, e o primeiro despacho do caso é
    exatamente esse cenário."""

    def test_o_primeiro_acionamento_segue_igual(self, monkeypatch, _nunca_envia_email_de_verdade):
        emails = _nunca_envia_email_de_verdade
        client, sb = _client(monkeypatch)
        assert sb.tabelas["ouvidoria_setor_tokens"] == []

        _acionar(client)

        resposta = client.get(f"/api/ouvidoria-setor/{_token_para(emails, 'carlos@hsm.br')}")
        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["aceita_resposta"] is True
        assert [t for t in sb.tabelas["ouvidoria_setor_tokens"] if t.get("revogado_em")] == []


def _links_vivos_de(sb, email: str) -> list[dict]:
    """Os tokens do caso que ainda abrem o portal para aquele endereço."""
    return [
        t
        for t in sb.tabelas["ouvidoria_setor_tokens"]
        if t["destinatario_email"] == email and not t.get("revogado_em") and not t.get("usado_em")
    ]


class TestFabricaDeLinks:
    """A revogação derruba os links que EXISTEM. Esta classe cobre a outra
    metade: nenhum link NOVO nasce para a área que saiu do caso.

    Três portas emitem depois do reacionamento, e as três passam pelo
    `despachar`: a cobrança retida pela janela comercial, a decisão de
    prorrogação (que nem guarda de status tem) e o reenvio manual pelo painel.
    """

    def _cobranca_retida(self, sb, quando: dt.datetime) -> dict:
        """A cobrança que o job registrou para a área ANTIGA e que ficou
        `agendada` esperando a janela comercial abrir."""
        registro = ouvidoria_notificacoes.registrar(
            sb,
            manifestacao_id="uuid-7",
            gatilho=ouvidoria_notificacoes.GATILHO_PRAZO_ROMPIDO,
            destinatario_nome="Carlos Titular",
            destinatario_email="carlos@hsm.br",
            papel_destinatario="titular",
            enviar_a_partir_de=quando,
        )
        assert registro is not None
        return registro

    def test_cobranca_agendada_nao_acorda_para_a_area_antiga(self, monkeypatch, _nunca_envia_email_de_verdade):
        emails = _nunca_envia_email_de_verdade
        client, sb = _com_a_segunda_area(monkeypatch, emails)
        cobranca = self._cobranca_retida(sb, QUANDO_A_JANELA_ABRE)
        _cobrar(client)
        _devolver_e_reacionar(client, emails)
        ja_enviados = len(emails)

        ouvidoria_notificacoes.despachar_pendentes(sb, DEPOIS_DA_REVOGACAO, frozenset())

        assert [e for e in emails[ja_enviados:] if e["destinatario"] == "carlos@hsm.br"] == []
        assert _links_vivos_de(sb, "carlos@hsm.br") == [], "nasceu link novo para a área que saiu do caso"
        linha = next(n for n in sb.tabelas["ouvidoria_notificacoes"] if n["id"] == cobranca["id"])
        assert linha["status"] == ouvidoria_notificacoes.FALHA
        assert linha["ultimo_erro"] == ouvidoria_notificacoes.LINK_FORA_DA_AREA

    def test_prorrogacao_decidida_nao_emite_para_a_area_antiga(self, monkeypatch, _nunca_envia_email_de_verdade):
        """O pior dos três: este gatilho está fora dos que cobram a área, então
        a guarda de status não o alcança, e o caso volta a `aguardando_area`
        pela área nova sem que nada pergunte de quem é o email."""
        emails = _nunca_envia_email_de_verdade
        client, sb = _com_a_segunda_area(monkeypatch, emails)
        _cobrar(client)
        _devolver_e_reacionar(client, emails)
        ja_enviados = len(emails)

        decisao = ouvidoria_notificacoes.registrar(
            sb,
            manifestacao_id="uuid-7",
            gatilho=ouvidoria_notificacoes.GATILHO_PRORROGACAO_DECIDIDA,
            destinatario_nome="Carlos Titular",
            destinatario_email="carlos@hsm.br",
            papel_destinatario="titular",
            enviar_a_partir_de=DEPOIS_DA_REVOGACAO,
        )
        entregue = ouvidoria_notificacoes.despachar(sb, decisao, DEPOIS_DA_REVOGACAO, frozenset())

        assert entregue is False
        assert [e for e in emails[ja_enviados:] if e["destinatario"] == "carlos@hsm.br"] == []
        assert _links_vivos_de(sb, "carlos@hsm.br") == []

    def test_reenvio_manual_da_notificacao_antiga_nao_emite_link(self, monkeypatch, _nunca_envia_email_de_verdade):
        """O botão de reenvio continua na tela ao lado do acionamento da área
        antiga, e copia o destinatário da linha velha."""
        emails = _nunca_envia_email_de_verdade
        client, sb = _com_a_segunda_area(monkeypatch, emails)
        acionamento_antigo = sb.tabelas["ouvidoria_notificacoes"][0]["id"]
        _devolver_e_reacionar(client, emails)
        ja_enviados = len(emails)

        resposta = client.post(f"/api/ouvidoria/manifestacoes/uuid-7/notificacoes/{acionamento_antigo}/reenviar")

        assert resposta.status_code == 201, resposta.text
        assert resposta.json()["entregue"] is False
        assert [e for e in emails[ja_enviados:] if e["destinatario"] == "carlos@hsm.br"] == []
        assert _links_vivos_de(sb, "carlos@hsm.br") == []

    def test_quem_responde_pelo_setor_continua_recebendo(self, monkeypatch, _nunca_envia_email_de_verdade):
        """A contraprova, e a razão de a guarda não poder virar indisponibilidade.

        Nos MESMOS dois caminhos (cobrança retida e reenvio manual), o
        destinatário vigente do setor que está com o caso recebe o email e o
        link novo. Sem este teste, trocar a guarda por uma recusa cega passaria
        despercebido: os três testes acima ficariam verdes com a fila inteira
        parada."""
        emails = _nunca_envia_email_de_verdade
        client, sb = _com_a_segunda_area(monkeypatch, emails)
        _devolver_e_reacionar(client, emails)
        acionamento_novo = sb.tabelas["ouvidoria_notificacoes"][-1]["id"]
        ja_enviados = len(emails)

        self._cobranca_retida(sb, QUANDO_A_JANELA_ABRE)
        ouvidoria_notificacoes.registrar(
            sb,
            manifestacao_id="uuid-7",
            gatilho=ouvidoria_notificacoes.GATILHO_PRAZO_ROMPIDO,
            destinatario_nome="Helena Titular",
            destinatario_email=EMAIL_DA_AREA_NOVA,
            papel_destinatario="titular",
            enviar_a_partir_de=QUANDO_A_JANELA_ABRE,
        )
        ouvidoria_notificacoes.despachar_pendentes(sb, DEPOIS_DA_REVOGACAO, frozenset())

        cobrados = [e["destinatario"] for e in emails[ja_enviados:]]
        assert cobrados == [EMAIL_DA_AREA_NOVA], "a cobrança da área que está com o caso não saiu"
        assert len(_links_vivos_de(sb, EMAIL_DA_AREA_NOVA)) == 2

        reenvio = client.post(f"/api/ouvidoria/manifestacoes/uuid-7/notificacoes/{acionamento_novo}/reenviar")
        assert reenvio.status_code == 201, reenvio.text
        assert reenvio.json()["entregue"] is True
        assert client.get(f"/api/ouvidoria-setor/{_token_para(emails, EMAIL_DA_AREA_NOVA)}").status_code == 200


class TestFalhaDeRedeNaRevogacao:
    """A falha do PostgREST tem duas formas, e só uma delas é `APIError`."""

    @pytest.mark.parametrize(
        "falha",
        [
            pytest.param(httpx.ReadTimeout("o banco não respondeu no tempo"), id="read-timeout"),
            pytest.param(httpx.ConnectError("conexão recusada"), id="connect-error"),
            pytest.param(APIError({"message": "indisponivel", "code": "PGRST000"}), id="api-error"),
        ],
    )
    def test_o_ouvidor_le_o_que_aconteceu_em_vez_do_500_mudo(self, monkeypatch, _nunca_envia_email_de_verdade, falha):
        """Timeout e conexão recusada nascem antes de existir resposta HTTP, e
        por isso não são `APIError`: fora da tupla do `except` elas escapam,
        viram 500 genérico, e a frase deste bloco (a única coisa que ele
        entrega) não chega a quem despachou. A segunda tentativa do ouvidor
        ainda esbarra em "Este caso já está com a área", porque o caso
        transicionou antes da revogação."""
        client, sb = _client(monkeypatch)
        sb.falhas_por_operacao[("ouvidoria_setor_tokens", "update")] = _Falha(falha)

        resposta = client.post("/api/ouvidoria/manifestacoes/uuid-7/validar", json=VALIDACAO)

        assert resposta.status_code == 500, resposta.text
        assert "links da área anterior não foram derrubados" in resposta.json()["detail"]
        assert "Confira a manifestação no painel." in resposta.json()["detail"]
