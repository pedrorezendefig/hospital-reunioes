"""A fila de Validação de Contas médicas (issue #1142, PRD #1129, ADR 0070).

A diretoria e a gestão decidem por tema, não por conta: cada cartão é uma
regra pendente, um código bloqueado, as observações do time sobre uma regra ou
um termo proposto ao dicionário, com quantas contas e quanto dinheiro esperam
a decisão.

Os temas nascem onde as linhas nascem: a linha Validar no ponto único de
gravação do Guia (`processamento._gravar_guia`, por onde passam as linhas do
código e as da IA), o Bloqueado e o Não procede na marcação da faturista, a
observação na conclusão. Tudo pelas rotas de verdade, com o dublê do banco do
processamento e os CHECKs das migrations 116 e 118.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from postgrest.exceptions import APIError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from test_contas_medicas_processamento import _Banco, _Consulta, _matriz_da_migration, _pessoa  # noqa: E402

from app.dependencies import get_current_user, get_supabase_client  # noqa: E402
from app.limiter import limiter  # noqa: E402
from app.routers import contas_medicas_envio as envio_router  # noqa: E402
from app.routers import contas_medicas_guia as guia_router  # noqa: E402
from app.routers import contas_medicas_validacao as validacao_router  # noqa: E402
from app.services.contas_medicas import processamento  # noqa: E402
from app.services.contas_medicas.conferencia import Conferencia  # noqa: E402
from app.services.contas_medicas.guia import nota_de_entrada  # noqa: E402

MIGRATION_118 = Path(__file__).resolve().parents[2] / "supabase" / "migrations" / "118_contas_medicas_gestao.sql"
_SQL_118 = MIGRATION_118.read_text(encoding="utf-8")


def _lista_do_check(coluna: str) -> set[str]:
    bloco = re.search(
        rf"CREATE TABLE IF NOT EXISTS cm_validacao_tema \(.*?\b{coluna}\b[^\n]*CHECK \(([^\n]*)\)", _SQL_118, re.S
    )
    assert bloco, f"a migration 118 nao tem o CHECK de cm_validacao_tema.{coluna}"
    return set(re.findall(r"'(\w+)'", bloco.group(1)))


TIPOS_DE_TEMA = _lista_do_check("tipo")
ESTADOS_DE_TEMA = _lista_do_check("estado")


def test_o_duble_le_os_checks_da_migration_118():
    """Piso do detector: regex que parou de casar devolveria conjunto vazio."""
    assert TIPOS_DE_TEMA == {"REGRA_PENDENTE", "BLOQUEADO", "OBSERVACAO", "DICIONARIO"}
    assert ESTADOS_DE_TEMA == {"ABERTO", "DECIDIDO"}


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


# ═══════════════════════════════════════════════════════════════════════════
# O dublê: o banco do processamento, com paginação e os CHECKs da 118
# ═══════════════════════════════════════════════════════════════════════════


# Os DEFAULT da 118 (e da 116, no dicionário) que as rotas deixam o banco preencher.
PADROES_DA_118 = {
    "cm_validacao_tema": {"estado": "ABERTO", "leitura_ia": None, "decisao": None, "resposta": None},
    "cm_item_dicionario": {"origem": "GESTAO", "situacao": "PROPOSTO"},
}


class _ConsultaDaValidacao(_Consulta):
    def __init__(self, banco, nome):
        super().__init__(banco, nome)
        self._pagina: tuple[int, int] | None = None

    def range(self, inicio: int, fim: int):
        self._pagina = (inicio, fim)
        return self

    def _executar(self):
        if self._insert is not None and self._nome in PADROES_DA_118:
            novas = self._insert if isinstance(self._insert, list) else [self._insert]
            self._insert = [{**PADROES_DA_118[self._nome], **nova} for nova in novas]
        if self._nome == "cm_validacao_tema":
            escritas = self._insert if isinstance(self._insert, list) else [self._insert or self._update or {}]
            for linha in escritas:
                if linha.get("tipo", "REGRA_PENDENTE") not in TIPOS_DE_TEMA:
                    raise APIError({"message": "cm_validacao_tema_tipo_check", "code": "23514"})
                if linha.get("estado", "ABERTO") not in ESTADOS_DE_TEMA:
                    raise APIError({"message": "cm_validacao_tema_estado_check", "code": "23514"})
        resposta = super()._executar()
        if self._pagina is not None:
            inicio, fim = self._pagina
            resposta.data = resposta.data[inicio : fim + 1]
        return resposta


class _BancoDaValidacao(_Banco):
    def table(self, nome: str):
        return _ConsultaDaValidacao(self, nome)


FATURISTA = _pessoa("F1", "faturista")
GESTAO = _pessoa("G1", "gestao_contas_medicas")
COORDENADORA = _pessoa("K1", "coordenadora")
PESSOAS = {"faturista": FATURISTA, "gestao": GESTAO, "coordenadora": COORDENADORA}

REGRA_PENDENTE = "ALFA-PRI-03"
REGRA_VIGENTE = "ALFA-PRI-07"
TEXTO_PENDENTE = "Seringa de limpeza pronta é cobrada à parte."


def _regra(codigo: str, status: str, texto: str, tipo: str = "CONTRATUAL") -> dict[str, Any]:
    return {
        "id": f"rg-{codigo}",
        "operadora_id": "op-alfa",
        "memoria_versao_id": "mv-alfa",
        "codigo": codigo,
        "secao": codigo.split("-")[1],
        "texto": texto,
        "tipo": tipo,
        "origem": "PRÁTICA",
        "status": status,
        "ativa": True,
        "validado_por": None,
        "validado_em": None,
    }


def _atendimento(n: int) -> dict[str, Any]:
    return {
        "id": f"at-{n}",
        "numero_atendimento": f"3130{n}",
        "operadora_id": "op-alfa",
        "plano": "ALFA BASICO",
        "coluna_preco": "COMUM",
    }


def _conta(n: int, situacao: str) -> dict[str, Any]:
    return {
        "id": f"c-{n}",
        "atendimento_id": f"at-{n}",
        "numero_conta": f"4880{n}",
        "situacao": situacao,
        "faturista_id": "F1",
        "ordem_fila": n,
        "total_lancado": 1000.0,
        "tentativas": 1,
    }


def _cenario() -> _BancoDaValidacao:
    """Três contas da ALFA: duas na mão da faturista e uma já concluída."""
    return _BancoDaValidacao(
        {
            "participantes": list(PESSOAS.values()),
            "cm_perfil_permissao": _matriz_da_migration(),
            "cm_operadora": [{"id": "op-alfa", "sigla": "ALFA", "nome": "Alfa Saúde", "situacao": "PARCIAL"}],
            "cm_memoria_versao": [
                {
                    "id": "mv-alfa",
                    "operadora_id": "op-alfa",
                    "versao": "1.0",
                    "parametros_json": {"operadora": "ALFA"},
                    "vigente": True,
                }
            ],
            "cm_regra": [
                _regra(REGRA_PENDENTE, "PENDENTE", TEXTO_PENDENTE),
                _regra(REGRA_VIGENTE, "VIGENTE", "Medicamento prescrito e não lançado é incluído.", "OPERACIONAL"),
            ],
            "cm_atendimento": [_atendimento(1), _atendimento(2), _atendimento(3)],
            "cm_conta": [_conta(1, "EM_CORRECAO"), _conta(2, "A_FAZER"), _conta(3, "CONCLUIDA_COM_PENDENCIA")],
            "cm_guia_linha": [],
            "cm_observacao": [],
            "cm_item_dicionario": [],
            "cm_validacao_tema": [],
            "cm_validacao_tema_linha": [],
            "cm_regra_historico": [],
            "cm_registro": [],
            "cm_chamada_ia": [],
            "notificacoes": [],
        }
    )


def _cliente(banco: _Banco, quem: str = "gestao") -> TestClient:
    pessoa = PESSOAS[quem]
    app = FastAPI()
    app.state.limiter = limiter
    app.include_router(envio_router.router, prefix="/api")
    app.include_router(guia_router.router, prefix="/api")
    app.include_router(validacao_router.router, prefix="/api")

    async def _usuario() -> dict[str, Any]:
        return {"id": pessoa["auth_user_id"], "email": pessoa["email"], "metadata": {}}

    app.dependency_overrides[get_current_user] = _usuario
    app.dependency_overrides[get_supabase_client] = lambda: banco
    return TestClient(app)


def _linha_do_guia(acao: str, codigo: str, valor: float, regra: str | None, **campos) -> dict[str, Any]:
    """Uma linha como a conferência entrega ao `_gravar_guia`."""
    base = {
        "acao": acao,
        "data": "2026-10-03",
        "data_fim": "2026-10-03",
        "setor": "CTI ADULTO",
        "codigo": codigo,
        "descricao": f"ITEM {codigo}",
        "quantidade_lancada": 0.0,
        "quantidade_devida": 1.0,
        "preco_lancado": None,
        "preco_tabela": valor,
        "valor_diferenca": valor,
        "regra_codigo": regra,
        "motivo": f"Regra {regra} pendente. Prescrito e sem lançamento no dia.",
        "evidencia_pagina": 3,
        "evidencia_trecho": "Seringa pronta 10 ml",
        "nivel_evidencia": "PRESCRITO",
        "causa_raiz": "DISPENSACAO",
        "confianca": "ALTA",
        "origem": "CODIGO",
        "ordem": 1,
    }
    return {**base, **campos}


def _gravar(banco: _Banco, conta_id: str, *linhas: dict[str, Any]) -> list[dict]:
    """O ponto único de gravação das linhas do Guia, como o pipeline chama."""
    conferencia = Conferencia(linhas=tuple(linhas), descartadas=(), nota=nota_de_entrada(linhas, 1000))
    return processamento._gravar_guia(banco, conta_id, conferencia)


def _fila_de_validacao(banco: _Banco, quem: str = "gestao") -> dict:
    resposta = _cliente(banco, quem).get("/api/contas-medicas/validacao")
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


def _validar_em_tres_contas(banco: _Banco) -> None:
    _gravar(banco, "c-1", _linha_do_guia("VALIDAR", "70000010", 120.0, REGRA_PENDENTE))
    _gravar(banco, "c-2", _linha_do_guia("VALIDAR", "70000010", 80.0, REGRA_PENDENTE))
    _gravar(banco, "c-3", _linha_do_guia("VALIDAR", "70000010", 50.5, REGRA_PENDENTE))


# ═══════════════════════════════════════════════════════════════════════════
# 1. Regra pendente: um tema por regra e operadora
# ═══════════════════════════════════════════════════════════════════════════


class TestRegraPendente:
    def test_linhas_validar_de_tres_contas_pela_mesma_regra_viram_um_tema_com_as_tres_contas_e_o_rs_somado(self):
        banco = _cenario()

        _validar_em_tres_contas(banco)

        fila = _fila_de_validacao(banco)
        [tema] = fila["temas"]
        assert tema["tipo"] == "REGRA_PENDENTE"
        assert tema["regra_codigo"] == REGRA_PENDENTE
        assert tema["operadora"] == "ALFA"
        assert tema["contas"] == 3
        assert tema["valor"] == 250.5
        assert tema["regra"]["texto"] == TEXTO_PENDENTE
        assert tema["desde"]
