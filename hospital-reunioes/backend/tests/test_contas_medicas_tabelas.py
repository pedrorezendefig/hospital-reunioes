"""Tabelas de preço, busca de preço e dicionário de itens (issue #1120, PRD #1113, ADR 0070).

A gestão envia, pela tela Operadoras, o CSV de cada tabela de preço com a
categoria e a vigência, e o dicionário de itens do hospital. A busca
`preco(operadora, categoria, código, data, coluna)` devolve o valor da versão
vigente na data, `NAO_CONFERIDO` quando não há como conferir, ou `PACOTE`.

As fixtures são sintéticas, com o cabeçalho de cada formato e só as linhas que
a conferência da carga do diretor pede (spec v1.0, item 21.2; pacote da
Unimed, item 3; memória da Leve): os CSVs reais vivem em
`local/contas-medicas/`, fora do git. O dublê do banco é o da carga da
operadora, com os CHECKs da migration 116.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_contas_medicas_operadoras import (
    FATURISTA,
    GESTAO,
    _Banco,
    _cliente,
    _com_operadoras,
    _enviar_memoria,
)

from app.limiter import limiter
from app.services.contas_medicas.tabelas import NAO_CONFERIDO, PACOTE, preco

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "contas_medicas" / "tabelas"

DIA = date(2026, 10, 5)


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


def _rota(sigla: str) -> str:
    return f"/api/contas-medicas/operadoras/{sigla}/tabelas"


def _enviar_tabela(
    cliente: TestClient,
    sigla: str,
    categoria: str,
    arquivo: str,
    *,
    inicio: str = "2026-05-01",
    fim: str | None = None,
    texto: str | None = None,
):
    conteudo = texto if texto is not None else (FIXTURES / arquivo).read_text(encoding="utf-8")
    dados = {"categoria": categoria, "vigencia_inicio": inicio}
    if fim:
        dados["vigencia_fim"] = fim
    return cliente.post(
        _rota(sigla), data=dados, files={"arquivo": (arquivo, conteudo.encode("utf-8"), "text/csv")}
    )


def _id(banco: _Banco, sigla: str) -> str:
    return next(o["id"] for o in banco.linhas("cm_operadora") if o["sigla"] == sigla)


# ═══════════════════════════════════════════════════════════════════════════
# 1. O envio do CSV, formato reconhecido pelo cabeçalho
# ═══════════════════════════════════════════════════════════════════════════


class TestEnvioDaTabela:
    def test_csv_de_materiais_com_duas_colunas_cria_a_tabela_os_itens_e_devolve_a_contagem(self):
        cliente, banco = _cliente(GESTAO, _com_operadoras("ASSIM"))

        resposta = _enviar_tabela(cliente, "ASSIM", "MATERIAL", "assim-materiais.csv")

        assert resposta.status_code == 201, resposta.text
        corpo = resposta.json()
        assert (corpo["operadora"], corpo["categoria"], corpo["itens"]) == ("ASSIM", "MATERIAL", 5)
        [tabela] = banco.linhas("cm_tabela_preco")
        assert (tabela["vigencia_inicio"], tabela["vigencia_fim"]) == ("2026-05-01", None)
        assert tabela["arquivo_nome"] == "assim-materiais.csv"
        assert tabela["autor_id"] == "P1"
        assert len(banco.linhas("cm_tabela_preco_item")) == 5
        [ligacao] = banco.linhas("cm_operadora_tabela")
        assert (ligacao["operadora_id"], ligacao["categoria"], ligacao["tabela_id"]) == (
            "op-ASSIM",
            "MATERIAL",
            tabela["id"],
        )
        assert preco(banco, "op-ASSIM", "MATERIAL", "70802726", DIA, "CARIOCA") == Decimal("0.38")
        assert preco(banco, "op-ASSIM", "MATERIAL", "70802726", DIA, "COMUM") == Decimal("0.44")
