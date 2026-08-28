"""Exceção não tratada não conta o que houve por dentro (issue #375, item 8).

O handler global respondia `{"detail": "TipoDoErro: mensagem"}` para qualquer
exceção que escapasse. O texto de uma exceção do PostgREST, do httpx ou de um
bug de código carrega nome de tabela, de coluna e caminho interno, e desde a
fatia do canal aberto existe POST público sem credencial chegando nesse
handler. A decisão 2 da issue vale para o app inteiro, não só para a porta
pública: o cliente lê uma frase genérica e o texto real vai só para o log.
"""

from __future__ import annotations

import logging
import os
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.main import DETALHE_ERRO_GENERICO, app  # noqa: E402

SEGREDO = 'relation "ouvidoria_protocolos" does not exist'


@app.get("/api/_teste_excecao_nao_tratada")
async def _rota_que_estoura():  # pragma: no cover - existe só para o teste
    raise RuntimeError(SEGREDO)


class TestExcecaoNaoTratada:
    def test_o_cliente_nao_recebe_o_texto_da_excecao(self):
        client = TestClient(app, raise_server_exceptions=False)

        resposta = client.get("/api/_teste_excecao_nao_tratada")

        assert resposta.status_code == 500
        corpo = resposta.json()
        assert corpo["detail"] == DETALHE_ERRO_GENERICO
        # Nem o texto, nem o tipo da exceção: os dois contam da estrutura.
        assert SEGREDO not in resposta.text
        assert "RuntimeError" not in resposta.text

    def test_o_texto_real_vai_para_o_log(self, caplog):
        """Genérico para o cliente não pode virar cego para quem opera: o
        rastro tem que continuar existindo em algum lugar."""
        client = TestClient(app, raise_server_exceptions=False)

        with caplog.at_level(logging.ERROR):
            client.get("/api/_teste_excecao_nao_tratada")

        assert SEGREDO in caplog.text
