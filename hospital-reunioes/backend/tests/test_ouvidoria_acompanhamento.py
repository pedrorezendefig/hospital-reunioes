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
