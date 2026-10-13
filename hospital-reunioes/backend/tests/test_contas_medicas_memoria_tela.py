"""A Memória da operadora por tela (issue #1140, PRD #1129, ADR 0070).

A memória de cada convênio passa a ser editada pela tela: editar regra
vigente, decidir regra pendente, "aplicar a todas as operadoras que têm esta
regra" e exportar o arquivo. Toda mudança cria uma versão nova de
`cm_memoria_versao`, com o texto Markdown gerado do banco, e guarda o texto
anterior em `cm_regra_historico`; a anterior deixa de ser a vigente e a conta
analisada com ela continua apontando para ela.

Tudo pela rota de verdade, com o dublê do banco da carga da operadora (os
CHECKs da migration 116 e a uma vigente por operadora).
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_contas_medicas_operadoras import (
    GESTAO,
    _Banco,
    _com_operadoras,
    _matriz_da_migration,
    _memoria,
    _pessoa,
)

from app.dependencies import get_current_user, get_supabase_client
from app.limiter import limiter
from app.routers import contas_medicas_memoria as memoria_router
from app.routers import contas_medicas_operadoras as operadoras_router
from app.services.contas_medicas.memoria import ler_memoria
from app.services.contas_medicas.memoria_texto import gerar_texto_memoria
from app.services.contas_medicas.operadoras import memoria_vigente

ROTA_MEMORIA = "/api/contas-medicas/operadoras/memoria"


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


def _cliente(pessoa: dict[str, Any], banco: _Banco | None = None, ligar: tuple[str, ...] = ()) -> tuple[TestClient, _Banco]:
    """O app com a carga e a Memória por tela. `ligar` liga permissões no
    perfil da pessoa, como a Habilitação faria."""
    banco = banco or _Banco()
    banco.tabelas["participantes"] = [pessoa]
    matriz = _matriz_da_migration()
    for linha in matriz:
        if linha["perfil"] == pessoa["perfil_contas_medicas"] and linha["permissao"] in ligar:
            linha["ligada"] = True
    banco.tabelas["cm_perfil_permissao"] = matriz
    app = FastAPI()
    app.state.limiter = limiter
    app.include_router(operadoras_router.router, prefix="/api")
    app.include_router(memoria_router.router, prefix="/api")

    async def _usuario() -> dict[str, Any]:
        return {"id": pessoa["auth_user_id"], "email": pessoa["email"], "metadata": {}}

    app.dependency_overrides[get_current_user] = _usuario
    app.dependency_overrides[get_supabase_client] = lambda: banco
    return TestClient(app), banco


def _importar(cliente: TestClient, nome: str = "MEMORIA-ALFA-v1.0.md") -> None:
    resposta = cliente.post(ROTA_MEMORIA, files={"arquivo": (nome, _memoria(nome).encode("utf-8"), "text/markdown")})
    assert resposta.status_code == 201, resposta.text


def _regra(sigla: str, codigo: str) -> str:
    return f"/api/contas-medicas/operadoras/{sigla}/regras/{codigo}"


def _operadora_id(banco: _Banco, sigla: str) -> str:
    return next(o["id"] for o in banco.linhas("cm_operadora") if o["sigla"] == sigla)


def _versoes(banco: _Banco, sigla: str) -> dict[str, bool]:
    oid = _operadora_id(banco, sigla)
    return {v["versao"]: v["vigente"] for v in banco.linhas("cm_memoria_versao") if v["operadora_id"] == oid}


def _versao(banco: _Banco, sigla: str, versao: str) -> dict:
    oid = _operadora_id(banco, sigla)
    return next(v for v in banco.linhas("cm_memoria_versao") if v["operadora_id"] == oid and v["versao"] == versao)


DIA_01_ANTES = "A diária começa em qualquer horário, vence às 10h e é sempre integral."
DIA_01_DEPOIS = "A diária começa em qualquer horário, vence às 12h e é sempre integral."


# ═══════════════════════════════════════════════════════════════════════════
# 1. Editar uma regra vigente
# ═══════════════════════════════════════════════════════════════════════════


class TestEditarRegra:
    def test_editar_cria_versao_nova_vigente_guarda_o_texto_anterior_e_a_memoria_vigente_le_o_novo(self):
        cliente, banco = _cliente(GESTAO)
        _importar(cliente)

        resposta = cliente.put(
            _regra("ALFA", "ALFA-DIA-01"),
            json={"texto": DIA_01_DEPOIS, "tipo": "CONTRATUAL", "origem": "PRÁTICA"},
        )

        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["versao"] == "1.1"
        assert _versoes(banco, "ALFA") == {"1.0": False, "1.1": True}
        nova = _versao(banco, "ALFA", "1.1")
        assert nova["autor_id"] == "P1"

        [historico] = banco.linhas("cm_regra_historico")
        regra_nova = next(r for r in banco.linhas("cm_regra") if r["id"] == historico["regra_id"])
        assert (regra_nova["codigo"], regra_nova["memoria_versao_id"]) == ("ALFA-DIA-01", nova["id"])
        assert historico["memoria_versao_id"] == nova["id"]
        assert historico["texto_anterior"] == DIA_01_ANTES
        assert historico["texto_novo"] == DIA_01_DEPOIS
        assert historico["autor_id"] == "P1"

        vigente = memoria_vigente(banco, _operadora_id(banco, "ALFA"))
        regras = {r["codigo"]: r for r in vigente["regras"]}
        assert len(regras) == 5, "a versão nova leva todas as regras, não só a editada"
        assert regras["ALFA-DIA-01"]["texto"] == DIA_01_DEPOIS
        assert regras["ALFA-DIA-01"]["status"] == "VIGENTE"

        # O texto da versão nova é o gerado do banco, já com a regra editada.
        lida = {r.codigo: r for r in ler_memoria(nova["texto_md"]).regras}
        assert lida["ALFA-DIA-01"].texto == DIA_01_DEPOIS
        assert (ler_memoria(nova["texto_md"]).versao, len(lida)) == ("1.1", 5)

        # A versão anterior fica como estava.
        antiga = {r.codigo: r for r in ler_memoria(gerar_texto_memoria(banco, _operadora_id(banco, "ALFA"), _versao(banco, "ALFA", "1.0")["id"])).regras}
        assert antiga["ALFA-DIA-01"].texto == DIA_01_ANTES
