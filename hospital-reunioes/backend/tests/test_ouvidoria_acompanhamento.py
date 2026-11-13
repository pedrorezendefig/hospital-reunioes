"""Código e página de acompanhamento (issue #1623, PRD #1527, ADR 0086 decisão 7).

O manifestante anônimo recebe, junto com o protocolo, um código mostrado uma
vez só; o banco guarda só o hash. Na página pública `/acompanhar` ele informa
protocolo e código (anônimo) ou protocolo e o telefone ou e-mail que deixou
(identificado) e vê só o estado em linguagem simples, a data da última
movimentação e a resposta institucional (seção 4.3 do anexo da Demanda).

Os testes sobem a rota real com o mesmo banco falso do formulário público.
"""

from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from test_ouvidoria_formulario_publico import _make_app  # noqa: E402

from app.limiter import limiter  # noqa: E402

ROTA_ENVIO = "/api/ouvidoria/publico/manifestacoes"
ROTA_ACOMPANHAR = "/api/ouvidoria/publico/acompanhamento"


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


def _guiada(**overrides) -> dict:
    payload = {
        "anonimo": False,
        "sobre": "mim",
        "data_ocorrencia": "2026-11-10",
        "periodo": "tarde",
        "local_informado": "Emergência adulta",
        "relato": "Esperei duas horas na emergência sem nenhuma informação.",
        "expectativa": "resposta",
        "nome": "Maria Souza",
        "contato": "maria@exemplo.com",
        "telefone": "(21) 99999-0000",
    }
    payload.update(overrides)
    return {chave: valor for chave, valor in payload.items() if valor is not None}


def _anonima(client) -> dict:
    r = client.post(ROTA_ENVIO, json=_guiada(anonimo=True))
    assert r.status_code == 201, r.text
    return r.json()


class TestOCodigoDoAnonimo:
    def test_o_anonimo_ve_o_codigo_e_entra_com_ele_na_pagina(self):
        client, _ = _make_app()

        recibo = _anonima(client)

        codigo = recibo["codigo_acompanhamento"]
        assert len(codigo.replace("-", "")) >= 10
        r = client.post(ROTA_ACOMPANHAR, json={"protocolo": recibo["protocolo"], "codigo": codigo})
        assert r.status_code == 200, r.text
        assert r.json()["estado"] == "Recebida"

    def test_o_banco_guarda_so_o_hash_do_codigo(self):
        client, banco = _make_app()

        codigo = _anonima(client)["codigo_acompanhamento"]

        gravado = banco.inserts[0]
        assert gravado["codigo_acompanhamento_hash"]
        # Em nenhuma coluna, com ou sem o hífen, e em nenhuma caixa.
        bruto = json.dumps(gravado, ensure_ascii=False).upper()
        assert codigo.upper() not in bruto
        assert codigo.replace("-", "").upper() not in bruto

    def test_o_codigo_nao_volta_depois_da_confirmacao(self):
        client, _ = _make_app()
        recibo = _anonima(client)
        codigo = recibo["codigo_acompanhamento"]

        r = client.post(ROTA_ACOMPANHAR, json={"protocolo": recibo["protocolo"], "codigo": codigo})

        assert codigo not in r.text
        assert codigo.replace("-", "") not in r.text

    def test_cada_anonimo_ganha_um_codigo_diferente(self):
        client, _ = _make_app()

        codigos = {_anonima(client)["codigo_acompanhamento"] for _ in range(3)}

        assert len(codigos) == 3

    def test_o_codigo_digitado_sem_hifen_e_em_minuscula_tambem_entra(self):
        client, _ = _make_app()
        recibo = _anonima(client)
        digitado = recibo["codigo_acompanhamento"].replace("-", "").lower()

        r = client.post(ROTA_ACOMPANHAR, json={"protocolo": recibo["protocolo"], "codigo": f" {digitado} "})

        assert r.status_code == 200, r.text

    def test_quem_se_identifica_nao_recebe_codigo(self):
        client, banco = _make_app()

        r = client.post(ROTA_ENVIO, json=_guiada())

        assert r.status_code == 201, r.text
        assert "codigo_acompanhamento" not in r.json()
        assert banco.inserts[0].get("codigo_acompanhamento_hash") is None


class TestARecusaEUmaSo:
    def test_codigo_errado_devolve_o_mesmo_erro_de_protocolo_inexistente(self):
        client, _ = _make_app()
        recibo = _anonima(client)

        errado = client.post(ROTA_ACOMPANHAR, json={"protocolo": recibo["protocolo"], "codigo": "AAAAA-AAAAA"})
        inexistente = client.post(ROTA_ACOMPANHAR, json={"protocolo": "2026-9999", "codigo": "AAAAA-AAAAA"})

        assert errado.status_code == 404
        assert (errado.status_code, errado.json()) == (inexistente.status_code, inexistente.json())

    def test_contato_no_lugar_do_codigo_do_anonimo_e_a_mesma_recusa(self):
        client, _ = _make_app()
        recibo = _anonima(client)

        r = client.post(ROTA_ACOMPANHAR, json={"protocolo": recibo["protocolo"], "contato": "maria@exemplo.com"})
        inexistente = client.post(ROTA_ACOMPANHAR, json={"protocolo": "2026-9999", "contato": "maria@exemplo.com"})

        assert (r.status_code, r.json()) == (inexistente.status_code, inexistente.json())


def _caso_identificado(client, banco, **no_banco) -> str:
    r = client.post(ROTA_ENVIO, json=_guiada())
    assert r.status_code == 201, r.text
    banco.rows[-1].update(no_banco)
    return r.json()["protocolo"]


class TestOIdentificadoEntraPeloContato:
    @pytest.mark.parametrize(
        "contato", ["maria@exemplo.com", "  Maria@Exemplo.COM ", "21999990000", "+55 21 99999-0000"]
    )
    def test_entra_com_o_telefone_ou_o_email_cadastrado(self, contato):
        client, banco = _make_app()
        protocolo = _caso_identificado(client, banco)

        r = client.post(ROTA_ACOMPANHAR, json={"protocolo": protocolo, "contato": contato})

        assert r.status_code == 200, r.text
        assert r.json()["protocolo"] == protocolo

    @pytest.mark.parametrize("contato", ["outra@exemplo.com", "21988887777", "99990000", ""])
    def test_contato_que_nao_confere_e_a_mesma_recusa(self, contato):
        client, banco = _make_app()
        protocolo = _caso_identificado(client, banco)

        r = client.post(ROTA_ACOMPANHAR, json={"protocolo": protocolo, "contato": contato})
        inexistente = client.post(ROTA_ACOMPANHAR, json={"protocolo": "2026-9999", "contato": contato})

        assert r.status_code == 404
        assert r.json() == inexistente.json()

    def test_o_caso_de_antes_com_o_telefone_no_contato_tambem_entra(self):
        client, banco = _make_app()
        protocolo = _caso_identificado(client, banco, manifestante_contato="(21) 97777-1111", manifestante_telefone=None)

        r = client.post(ROTA_ACOMPANHAR, json={"protocolo": protocolo, "contato": "21977771111"})

        assert r.status_code == 200, r.text

    def test_codigo_qualquer_nao_abre_o_caso_identificado(self):
        client, banco = _make_app()
        protocolo = _caso_identificado(client, banco)

        r = client.post(ROTA_ACOMPANHAR, json={"protocolo": protocolo, "codigo": "AAAAA-AAAAA"})

        assert r.status_code == 404


# O que o caso guarda e a página nunca pode mostrar.
_INTERNOS = {
    "setor": "Farmácia Central",
    "canal_setor": "Recepção Principal",
    "responsavel_nome": "Joana Responsável",
    "nota_ouvidoria": "Anotação interna do ouvidor",
    "extrato_para_o_setor": "Extrato que só a área lê",
    "resumo": "Resumo da fila interna",
}


class TestAPaginaMostraSoOEstadoAUltimaMovimentacaoEAResposta:
    def test_a_resposta_nunca_carrega_setor_responsavel_nem_anotacao(self):
        client, banco = _make_app()
        protocolo = _caso_identificado(
            client,
            banco,
            status="encerrado",
            desfecho_descricao="Conversamos com a equipe e reforçamos o atendimento.",
            **_INTERNOS,
        )
        banco.movimentos.append(
            {
                "manifestacao_id": banco.rows[-1]["id"],
                "ocorrido_em": "2026-11-12T15:00:00+00:00",
                "autor_nome": "Joana Responsável",
                "observacao": "Anotação interna na trilha",
            }
        )

        r = client.post(ROTA_ACOMPANHAR, json={"protocolo": protocolo, "contato": "maria@exemplo.com"})

        assert r.status_code == 200, r.text
        assert set(r.json()) == {"protocolo", "estado", "ultima_movimentacao", "resposta"}
        for valor in [*_INTERNOS.values(), "Anotação interna na trilha", "Maria Souza"]:
            assert valor not in r.text, valor

    def test_o_caso_encerrado_mostra_a_resposta_institucional(self):
        client, banco = _make_app()
        protocolo = _caso_identificado(client, banco, status="encerrado", desfecho_descricao="Reforçamos o atendimento.")

        r = client.post(ROTA_ACOMPANHAR, json={"protocolo": protocolo, "contato": "maria@exemplo.com"})

        assert r.json()["estado"] == "Encerrada"
        assert r.json()["resposta"] == "Reforçamos o atendimento."

    def test_o_elogio_encerrado_responde_que_foi_entregue(self):
        client, banco = _make_app()
        protocolo = _caso_identificado(
            client, banco, status="encerrado", tipo_manifestacao="elogio", desfecho_descricao="Nota interna"
        )

        r = client.post(ROTA_ACOMPANHAR, json={"protocolo": protocolo, "contato": "maria@exemplo.com"})

        assert r.json()["resposta"] == "Seu elogio foi entregue à equipe."

    @pytest.mark.parametrize(
        "status,estado",
        [
            ("em_classificacao", "Recebida"),
            ("aguardando_area", "Em análise"),
            ("aguardando_manifestante", "Em análise"),
            ("respondido", "Respondida"),
        ],
    )
    def test_o_estado_em_linguagem_simples_e_sem_resposta_antes_de_encerrar(self, status, estado):
        client, banco = _make_app()
        protocolo = _caso_identificado(client, banco, status=status, desfecho_descricao="Rascunho que não vale")

        r = client.post(ROTA_ACOMPANHAR, json={"protocolo": protocolo, "contato": "maria@exemplo.com"})

        assert r.json()["estado"] == estado
        assert r.json()["resposta"] is None

    def test_a_data_e_a_da_ultima_movimentacao(self):
        client, banco = _make_app()
        protocolo = _caso_identificado(client, banco)
        caso_id = banco.rows[-1]["id"]
        banco.movimentos[:] = [
            {"manifestacao_id": caso_id, "ocorrido_em": "2026-11-10T12:00:00+00:00"},
            {"manifestacao_id": caso_id, "ocorrido_em": "2026-11-12T09:30:00+00:00"},
            {"manifestacao_id": caso_id, "ocorrido_em": "2026-11-11T08:00:00+00:00"},
            {"manifestacao_id": "outro-caso", "ocorrido_em": "2026-11-13T08:00:00+00:00"},
        ]

        r = client.post(ROTA_ACOMPANHAR, json={"protocolo": protocolo, "contato": "maria@exemplo.com"})

        assert r.json()["ultima_movimentacao"] == "2026-11-12T09:30:00+00:00"


class TestOLimiteDeTentativas:
    def test_tentativas_demais_sao_barradas(self):
        client, _ = _make_app()

        respostas = [
            client.post(ROTA_ACOMPANHAR, json={"protocolo": "2026-9999", "codigo": f"AAAAA-AAAA{n}"}).status_code
            for n in range(2, 8)
        ]

        assert respostas[:5] == [404] * 5
        assert respostas[5] == 429
