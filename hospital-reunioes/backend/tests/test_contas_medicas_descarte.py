"""Descartar um envio em Contas médicas (issue #1338, PRD #1335).

Quem enviou, ou quem tem o Painel completo, tira da lista a conta em Erro ou
Aguardando arquivo: a conta sai do banco e os PDFs dela (e o texto extraído)
saem do bucket na hora. Tudo pela rota de verdade, com o dublê do banco e do
bucket da suíte do envio.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from test_contas_medicas_envio import (  # noqa: E402
    ROTA_ENVIO,
    _cenario,
    _cliente,
    _conta,
    _extrator_de_texto,  # noqa: F401 (fixture autouse do envio)
    _prontuario,
    _reset_rate_limiter,  # noqa: F401 (fixture autouse do envio)
)

from app.services.contas_medicas_retencao import chave_do_texto  # noqa: E402

BUCKET = "contas-medicas"


def _rota(conta_id: str) -> str:
    return f"/api/contas-medicas/contas/{conta_id}/descartar"


def _enviado(*arquivos, quem: str = "faturista", banco=None):
    banco = banco or _cenario()
    resposta = _cliente(quem, banco).post(ROTA_ENVIO, files=list(arquivos))
    assert resposta.status_code == 200, resposta.text
    return banco


def _chaves(banco) -> set[str]:
    return {chave for (bucket, chave) in banco.bucket if bucket == BUCKET}


def _em_erro(banco) -> dict:
    [conta] = banco.tabelas["cm_conta"]
    conta["situacao"] = "ERRO"
    conta["erro_motivo"] = "Não consegui ler a conta inteira"
    return conta


class TestDescartar:
    def test_quem_enviou_descarta_a_conta_em_erro_e_ela_some_do_banco_e_os_pdfs_do_bucket(self):
        banco = _enviado(_conta("31302", "48001"), _prontuario("31302"))
        conta = _em_erro(banco)
        chaves = [a["chave_bucket"] for a in banco.tabelas["cm_arquivo"]]
        assert len(chaves) == 2

        resposta = _cliente("faturista", banco).post(_rota(conta["id"]))

        assert resposta.status_code == 200, resposta.text
        assert banco.tabelas["cm_conta"] == []
        assert banco.tabelas["cm_arquivo"] == []
        for chave in chaves:
            assert chave not in _chaves(banco)
            assert chave_do_texto(chave) not in _chaves(banco)
