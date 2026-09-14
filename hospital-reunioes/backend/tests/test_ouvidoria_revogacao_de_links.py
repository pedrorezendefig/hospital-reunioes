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

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.limiter import limiter  # noqa: E402
from app.services import ouvidoria_notificacoes, ouvidoria_setor_tokens  # noqa: E402

sys.path.insert(0, os.path.dirname(__file__))

from test_ouvidoria_portal_setor import (  # noqa: E402
    VALIDACAO,
    _acionar,
    _client,
    _responsavel,
)

MOTIVO = "Este caso é do Centro Médico: a recepção não agenda consulta de especialidade."

AREA_NOVA = "Centro Medico"
EMAIL_DA_AREA_NOVA = "helena@hsm.br"

# A frase que o responsável da área antiga lê ao abrir o link velho.
FRASE_DO_LINK_REVOGADO = "Este caso foi encaminhado a outra área; este link não vale mais"

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
        que FOI USADO, e o link revogado continua sem marca de uso. São duas
        verdades diferentes na trilha, e uma não pode virar a outra."""
        emails = _nunca_envia_email_de_verdade
        client, sb = _com_a_segunda_area(monkeypatch, emails)
        _cobrar(client)
        usado = _token_para(emails, "carlos@hsm.br")
        _devolver_e_reacionar(client, emails)

        resposta = client.get(f"/api/ouvidoria-setor/{usado}")
        assert resposta.status_code == 410
        assert "já foi usado" in resposta.json()["detail"]

        linhas = sb.tabelas["ouvidoria_setor_tokens"]
        revogados = [linha for linha in linhas if linha.get("revogado_em")]
        assert revogados, "nenhum link foi revogado"
        assert all(linha.get("usado_em") is None for linha in revogados)

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
