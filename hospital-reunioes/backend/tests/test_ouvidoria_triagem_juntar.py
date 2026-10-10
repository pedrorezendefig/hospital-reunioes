"""Triagem de e-mail: juntar a caso existente, com sugestão de protocolo
(issue #651, PRD #646, ADR 0051 decisão 4).

A resposta ao acuse e a segunda mensagem sobre o mesmo protocolo são o gesto
mais comum de quem reclama por e-mail. Juntar põe o texto e os anexos na trilha
do caso como [Movimento], sem mudar estado, prazo nem T1. Se o assunto traz o
Protocolo de ouvidoria, o app sugere o caso; a escolha é sempre do ouvidor.

Os dublês são os da fatia de virar manifestação (#650).
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from test_ouvidoria_triagem_email import OUVIDOR, SECRETARIA, SUPER_ADMIN  # noqa: E402
from test_ouvidoria_triagem_virar_manifestacao import (  # noqa: E402
    _email_na_triagem,
    _reset_rate_limiter,  # noqa: F401 (fixture autouse)
    _segredo_configurado,  # noqa: F401 (fixture autouse)
)

CORPO = "Esperei três horas na recepção sem informação nenhuma."


def _caso(banco, **campos) -> dict:
    """Um caso que já existe, como o banco o guarda."""
    caso = {
        "id": "caso-12",
        "protocolo": "2026-0012",
        "status": "aguardando_area",
        "setor": "Recepção",
        "prazo_area_em": "2026-09-18T18:00:00+00:00",
        "validada_em": "2026-09-08T13:00:00+00:00",
        "validada_por": "P10",
        "anonimizada_em": None,
        "apagamento_pedido_em": None,
    } | campos
    banco.tabelas["ouvidoria_protocolos"].append(caso)
    return caso


def _juntar(cliente, email_id: str, caso_id: str):
    return cliente.post(f"/api/ouvidoria/triagem-email/{email_id}/juntada", json={"manifestacao_id": caso_id})


class TestJuntarGravaMovimentoSemMexerNoCaso:
    def test_juntar_cria_movimento_com_o_texto_do_email_e_o_caso_fica_igual(self, monkeypatch):
        cliente, banco, email_id = _email_na_triagem(monkeypatch)
        caso = _caso(banco)
        antes = dict(caso)

        r = _juntar(cliente, email_id, caso["id"])

        assert r.status_code == 200
        [movimento] = banco.tabelas["ouvidoria_movimentos"]
        assert movimento["manifestacao_id"] == caso["id"]
        # Não é transição: o estado novo é o mesmo de antes.
        assert movimento["estado_anterior"] == "aguardando_area"
        assert movimento["estado_novo"] == "aguardando_area"
        assert movimento["autor_id"] == OUVIDOR["id"]
        assert movimento["observacao"].startswith(
            "E-mail recebido de Joana da Silva <joana.silva@gmail.com> em 10/09/2026 11:02: "
            "Demora na recepção do ambulatório"
        )
        assert CORPO in movimento["observacao"]
        # Estado, prazo e T1 iguais antes e depois: o caso não foi tocado.
        assert banco.tabelas["ouvidoria_protocolos"][0] == antes


class TestOsAnexosVaoParaOCaso:
    def test_os_anexos_do_email_aparecem_como_anexos_do_caso(self, monkeypatch):
        cliente, banco, email_id = _email_na_triagem(monkeypatch)
        caso = _caso(banco)

        _juntar(cliente, email_id, caso["id"])

        anexos_do_caso = cliente.get(f"/api/ouvidoria/manifestacoes/{caso['id']}/anexos").json()["anexos"]
        assert [a["filename"] for a in anexos_do_caso] == ["laudo.pdf"]
        assert cliente.get(f"/api/ouvidoria/triagem-email/{email_id}").json()["anexos"] == []


class TestOItemJuntadoSaiDosPendentes:
    def test_item_juntado_aparece_decidido_ligado_ao_caso(self, monkeypatch):
        cliente, banco, email_id = _email_na_triagem(monkeypatch)
        caso = _caso(banco)

        _juntar(cliente, email_id, caso["id"])

        [linha] = cliente.get("/api/ouvidoria/triagem-email").json()["emails"]
        assert linha["estado"] == "juntado"
        assert linha["manifestacao_id"] == caso["id"]
        assert linha["decidido_por_nome"] == "Marta Ouvidora"

    def test_juntar_de_novo_recebe_409_e_nao_duplica_o_movimento(self, monkeypatch):
        cliente, banco, email_id = _email_na_triagem(monkeypatch)
        caso = _caso(banco)
        assert _juntar(cliente, email_id, caso["id"]).status_code == 200

        r = _juntar(cliente, email_id, caso["id"])

        assert r.status_code == 409
        assert len(banco.tabelas["ouvidoria_movimentos"]) == 1

    def test_movimento_que_nao_entra_devolve_o_email_aos_pendentes(self, monkeypatch):
        """Juntado sem movimento seria um e-mail que diz estar no caso e não
        está: a marca volta, e o ouvidor tenta de novo."""
        from postgrest.exceptions import APIError

        cliente, banco, email_id = _email_na_triagem(monkeypatch)
        caso = _caso(banco)
        original = banco.table

        def table(nome):
            tabela = original(nome)
            if nome == "ouvidoria_movimentos":

                def insert(_payload):
                    raise APIError({"code": "08006", "message": "conexão caiu"})

                tabela.insert = insert
            return tabela

        monkeypatch.setattr(banco, "table", table)

        r = _juntar(cliente, email_id, caso["id"])

        assert r.status_code == 503
        [item] = banco.tabelas["ouvidoria_emails_recebidos"]
        assert item["estado"] == "pendente"
        assert item["manifestacao_id"] is None
        assert item["decidido_em"] is None
        assert len(banco.tabelas["ouvidoria_emails_recebidos_anexos"]) == 1

    def test_decisao_concorrente_entre_a_conferencia_e_a_marca_nao_entra_na_trilha(self, monkeypatch):
        """Dois cliques (ou juntar numa aba e descartar na outra) passam juntos
        pela conferência de pendente: só o filtro no próprio update segura o
        segundo, e a trilha do caso, que é imutável, não ganha um movimento
        de um e-mail que já foi decidido."""
        from app.services import ouvidoria_triagem_email as triagem

        cliente, banco, email_id = _email_na_triagem(monkeypatch)
        caso = _caso(banco)
        conferir = triagem.estado_do_email

        def conferencia_que_perde_a_corrida(supabase, eid):
            estado = conferir(supabase, eid)
            # A outra aba descarta logo depois desta leitura.
            banco.tabelas["ouvidoria_emails_recebidos"][0] |= {"estado": "descartado", "decidido_em": "agora"}
            return estado

        monkeypatch.setattr(triagem, "estado_do_email", conferencia_que_perde_a_corrida)

        r = _juntar(cliente, email_id, caso["id"])

        assert r.status_code == 409
        assert banco.tabelas["ouvidoria_movimentos"] == []
        assert banco.tabelas["ouvidoria_emails_recebidos"][0]["estado"] == "descartado"


class TestQualCasoAceitaAJuntada:
    @pytest.mark.parametrize(
        "carimbo", [{"anonimizada_em": "2031-09-01T03:00:00+00:00"}, {"apagamento_pedido_em": "2026-09-20T10:00:00"}]
    )
    def test_caso_apagado_ou_em_apagamento_recusa_e_o_email_fica_pendente(self, monkeypatch, carimbo):
        cliente, banco, email_id = _email_na_triagem(monkeypatch)
        caso = _caso(banco, status="encerrado", **carimbo)

        r = _juntar(cliente, email_id, caso["id"])

        assert r.status_code == 409
        assert "apagado" in r.json()["detail"] or "apagamento" in r.json()["detail"]
        assert banco.tabelas["ouvidoria_movimentos"] == []
        assert banco.tabelas["ouvidoria_emails_recebidos"][0]["estado"] == "pendente"

    def test_caso_encerrado_aceita_e_continua_encerrado(self, monkeypatch):
        cliente, banco, email_id = _email_na_triagem(monkeypatch)
        caso = _caso(banco, status="encerrado", encerrada_em="2026-09-15T12:00:00+00:00")

        r = _juntar(cliente, email_id, caso["id"])

        assert r.status_code == 200
        [movimento] = banco.tabelas["ouvidoria_movimentos"]
        assert movimento["estado_anterior"] == movimento["estado_novo"] == "encerrado"
        assert banco.tabelas["ouvidoria_protocolos"][0]["status"] == "encerrado"

    def test_caso_inexistente_recebe_404(self, monkeypatch):
        cliente, banco, email_id = _email_na_triagem(monkeypatch)

        assert _juntar(cliente, email_id, "caso-que-nao-existe").status_code == 404
        assert banco.tabelas["ouvidoria_emails_recebidos"][0]["estado"] == "pendente"


def _com_assunto(monkeypatch, assunto: str, corpo: str = CORPO):
    from test_ouvidoria_triagem_email import _evento, _lido

    return _email_na_triagem(monkeypatch, evento=_evento(assunto=assunto), lido=_lido(texto=corpo, html=None))


def _sugestao(cliente, email_id: str, protocolo: str | None = None):
    sufixo = f"?protocolo={protocolo}" if protocolo is not None else ""
    return cliente.get(f"/api/ouvidoria/triagem-email/{email_id}/caso-para-juntar{sufixo}")


class TestASugestaoDeCaso:
    def test_assunto_com_o_protocolo_sugere_o_caso_com_o_resumo(self, monkeypatch):
        cliente, banco, email_id = _com_assunto(monkeypatch, "Re: Recebemos sua manifestação, protocolo 2026-0012")
        _caso(banco)

        r = _sugestao(cliente, email_id)

        assert r.status_code == 200
        assert r.json()["caso"] == {
            "id": "caso-12",
            "protocolo": "2026-0012",
            "status": "aguardando_area",
            "setor": "Recepção",
        }

    def test_assunto_sem_protocolo_devolve_vazio(self, monkeypatch):
        cliente, banco, email_id = _com_assunto(monkeypatch, "Demora na recepção do ambulatório")
        _caso(banco)

        assert _sugestao(cliente, email_id).json()["caso"] is None

    def test_protocolo_que_nao_existe_nao_sugere_nada(self, monkeypatch):
        cliente, banco, email_id = _com_assunto(monkeypatch, "Re: protocolo 2026-0999")
        _caso(banco)

        assert _sugestao(cliente, email_id).json()["caso"] is None

    def test_sem_protocolo_no_assunto_procura_nas_primeiras_linhas_do_corpo(self, monkeypatch):
        corpo = "Bom dia,\nsobre o meu protocolo 2026-0012, esqueci de dizer o leito.\nObrigada."
        cliente, banco, email_id = _com_assunto(monkeypatch, "Complemento", corpo=corpo)
        _caso(banco)

        assert _sugestao(cliente, email_id).json()["caso"]["protocolo"] == "2026-0012"

    def test_o_protocolo_digitado_devolve_o_resumo_daquele_caso(self, monkeypatch):
        """Antes de confirmar, a tela mostra o resumo do caso que o ouvidor
        digitou, que pode não ser o sugerido."""
        cliente, banco, email_id = _com_assunto(monkeypatch, "Re: protocolo 2026-0012")
        _caso(banco)
        _caso(banco, id="caso-30", protocolo="2026-0030", status="encerrado", setor="Faturamento")

        caso = _sugestao(cliente, email_id, protocolo="2026-0030").json()["caso"]

        assert caso == {"id": "caso-30", "protocolo": "2026-0030", "status": "encerrado", "setor": "Faturamento"}


class TestSoAOuvidoriaJunta:
    @pytest.mark.parametrize("participante", [SECRETARIA, SUPER_ADMIN, None])
    def test_perfil_sem_ouvidoria_recebe_403_e_nada_muda(self, monkeypatch, participante):
        cliente, banco, email_id = _email_na_triagem(monkeypatch, participante)
        caso = _caso(banco)

        assert _juntar(cliente, email_id, caso["id"]).status_code == 403
        assert _sugestao(cliente, email_id).status_code == 403
        assert banco.tabelas["ouvidoria_movimentos"] == []
        assert banco.tabelas["ouvidoria_emails_recebidos"][0]["estado"] == "pendente"


class TestAJuntadaEntraNoLogDeAcesso:
    def test_juntar_grava_o_acesso_com_o_email_e_o_caso(self, monkeypatch):
        cliente, banco, email_id = _email_na_triagem(monkeypatch)
        caso = _caso(banco)

        _juntar(cliente, email_id, caso["id"])

        [acesso] = [a for a in banco.tabelas["ouvidoria_acessos"] if a["acao"] == "juntar_email"]
        assert acesso["email_recebido_id"] == email_id
        assert acesso["manifestacao_id"] == caso["id"]
        assert acesso["ator_id"] == OUVIDOR["id"]


class TestOCorpoApareceNaLinhaDoTempo:
    def test_a_linha_do_tempo_do_caso_mostra_a_linha_padrao_e_o_corpo_do_email(self, monkeypatch):
        """O que o ouvidor lê no Dossiê é a linha do tempo, e não a tabela crua:
        o movimento sem mudança de estado tem a linha padronizada como
        descrição e o corpo do e-mail como texto (spec da #651, "e o corpo em
        texto")."""
        cliente, banco, email_id = _email_na_triagem(monkeypatch)
        caso = _caso(banco)
        _juntar(cliente, email_id, caso["id"])

        r = cliente.get(f"/api/ouvidoria/manifestacoes/{caso['id']}/movimentos")

        assert r.status_code == 200
        [evento] = r.json()["movimentos"]
        assert evento["descricao"] == (
            "E-mail recebido de Joana da Silva <joana.silva@gmail.com> em 10/09/2026 11:02: "
            "Demora na recepção do ambulatório"
        )
        assert evento["texto"] == CORPO


class TestFalhaNosAnexosDepoisDoMovimento:
    def test_falha_ao_mover_os_anexos_nao_vira_503_com_a_juntada_feita(self, monkeypatch, caplog):
        """O movimento já está na trilha imutável e o e-mail já está juntado:
        um 503 "tente de novo" aqui seria mentira, e a nova tentativa daria
        409. Como no virar manifestação (#650), o passo dos anexos nunca
        levanta, e o log leva só ids e o tipo da falha."""
        from postgrest.exceptions import APIError

        cliente, banco, email_id = _email_na_triagem(monkeypatch)
        caso = _caso(banco)
        original = banco.table
        falhou = []

        def table(nome):
            tabela = original(nome)
            if nome == "ouvidoria_emails_recebidos_anexos" and banco.tabelas["ouvidoria_movimentos"] and not falhou:
                select_original = tabela.select

                def select(*args, **kwargs):
                    falhou.append(True)
                    raise APIError({"code": "08006", "message": "conexão caiu", "details": "Failing row (Joana)"})

                tabela.select = select
                del select_original
            return tabela

        monkeypatch.setattr(banco, "table", table)

        r = _juntar(cliente, email_id, caso["id"])

        assert falhou, "o teste não chegou a quebrar a leitura dos anexos"
        assert r.status_code == 200
        assert len(banco.tabelas["ouvidoria_movimentos"]) == 1
        assert banco.tabelas["ouvidoria_emails_recebidos"][0]["estado"] == "juntado"
        assert email_id in caplog.text
        assert "APIError" in caplog.text
        assert "Joana" not in caplog.text


ARQUIVADO = {"status": "encerrado", "arquivada_em": "2026-09-20T10:00:00+00:00", "arquivada_por": "P10"}


class TestCasoArquivadoRecusaAJuntada:
    """O caso arquivado sai da fila e do contador de novidade: o e-mail juntado
    a ele sumiria sem ninguém ver. A recusa diz o caminho, desarquivar no
    Dossiê, e o arquivo só muda por ato explícito do ouvidor."""

    def test_juntar_a_caso_arquivado_recebe_409_e_nada_muda(self, monkeypatch):
        cliente, banco, email_id = _email_na_triagem(monkeypatch)
        caso = _caso(banco, **ARQUIVADO)

        r = _juntar(cliente, email_id, caso["id"])

        assert r.status_code == 409
        assert "arquivado" in r.json()["detail"]
        assert "Desarquive" in r.json()["detail"]
        assert banco.tabelas["ouvidoria_movimentos"] == []
        assert banco.tabelas["ouvidoria_emails_recebidos"][0]["estado"] == "pendente"
        assert banco.tabelas["ouvidoria_protocolos"][0]["arquivada_em"] == ARQUIVADO["arquivada_em"]

    def test_sugestao_de_caso_arquivado_recebe_409(self, monkeypatch):
        cliente, banco, email_id = _com_assunto(monkeypatch, "Re: protocolo 2026-0012")
        _caso(banco, **ARQUIVADO)

        r = _sugestao(cliente, email_id)

        assert r.status_code == 409
        assert "2026-0012" in r.json()["detail"]
        assert "arquivado" in r.json()["detail"]

    def test_protocolo_digitado_de_caso_arquivado_recebe_409(self, monkeypatch):
        cliente, banco, email_id = _com_assunto(monkeypatch, "Complemento")
        _caso(banco, **ARQUIVADO)

        r = _sugestao(cliente, email_id, protocolo="2026-0012")

        assert r.status_code == 409
        assert "arquivado" in r.json()["detail"]


class TestDepoisDeJuntarFicaSoOCabecalho:
    def test_o_corpo_sai_da_triagem_e_fica_so_no_caso(self, monkeypatch):
        """O texto entrou na trilha do caso, que a Retenção alcança. A cópia na
        triagem ficaria fora dela: depois de juntar, o item guarda só o
        cabeçalho, como no descarte (ADR 0051, decisão 5)."""
        cliente, banco, email_id = _email_na_triagem(monkeypatch)
        caso = _caso(banco)

        assert _juntar(cliente, email_id, caso["id"]).status_code == 200

        [item] = banco.tabelas["ouvidoria_emails_recebidos"]
        assert item["estado"] == "juntado"
        assert item["corpo_texto"] is None
        assert item["corpo_html"] is None
        assert item["cabecalhos"] == {}
        assert item["remetente_endereco"] == "joana.silva@gmail.com"
        assert item["assunto"] == "Demora na recepção do ambulatório"
        [movimento] = banco.tabelas["ouvidoria_movimentos"]
        assert CORPO in movimento["observacao"]
