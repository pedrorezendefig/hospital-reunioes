"""O Painel de Contas médicas (issue #1137, PRD #1128, ADR 0070).

A diretoria lê a nota média de entrada de cada semana, onde o R$ apontado
nasce (causa-raiz), os dez itens que mais faltam, a produção de cada faturista,
o R$ incluído por nível de evidência e o custo de IA. A faturista vê só a
própria linha de produção.

O cenário tem 2 semanas, 2 operadoras e 2 faturistas. Os esperados vêm das
definições do glossário (`docs/contas-medicas/CONTEXT.md`) e da spec do
diretor (item 15), somados à mão a partir das linhas semeadas.
"""

from __future__ import annotations

import os
import re
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.dependencies import get_current_user, get_supabase_client  # noqa: E402
from app.limiter import limiter  # noqa: E402
from app.routers import contas_medicas_painel as painel_router  # noqa: E402

MIGRATION_116 = Path(__file__).resolve().parents[2] / "supabase" / "migrations" / "116_contas_medicas_fundacao.sql"

ROTA = "/api/contas-medicas/painel"

# A semana escolhida vai de segunda 05/10 a domingo 11/10/2026; a anterior,
# de 28/09 a 04/10.
SEMANA = "2026-10-05"
SEMANA_ANTERIOR = "2026-09-28"


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


# ═══════════════════════════════════════════════════════════════════════════
# O dublê do banco
# ═══════════════════════════════════════════════════════════════════════════


def _instante(valor: str) -> datetime:
    return datetime.fromisoformat(valor)


class _Consulta:
    """O pedaço do cliente do Supabase que o Painel usa."""

    def __init__(self, banco: _Banco, nome: str):
        self._banco = banco
        self._nome = nome
        self._filtros: list = []
        self._ordem: list[tuple[str, bool]] = []
        self._recorte: tuple[int, int] | None = None
        self._limite: int | None = None

    def select(self, *_a, **_kw):
        return self

    def eq(self, coluna, valor):
        self._filtros.append(lambda linha: linha.get(coluna) == valor)
        return self

    def in_(self, coluna, valores):
        valores = list(valores)
        self._banco.maior_in = max(self._banco.maior_in, len(valores))
        self._filtros.append(lambda linha: linha.get(coluna) in valores)
        return self

    def gte(self, coluna, valor):
        self._filtros.append(lambda linha: linha.get(coluna) is not None and _instante(linha[coluna]) >= _instante(valor))
        return self

    def lt(self, coluna, valor):
        self._filtros.append(lambda linha: linha.get(coluna) is not None and _instante(linha[coluna]) < _instante(valor))
        return self

    def order(self, coluna, desc=False):
        self._ordem.append((coluna, desc))
        return self

    def range(self, inicio, fim):
        self._recorte = (inicio, fim)
        return self

    def limit(self, n):
        self._limite = n
        return self

    def execute(self):
        casam = [linha for linha in self._banco.tabelas.get(self._nome, []) if all(f(linha) for f in self._filtros)]
        for coluna, desc in reversed(self._ordem):
            casam.sort(key=lambda linha, c=coluna: (linha.get(c) is None, str(linha.get(c) or "")), reverse=desc)
        if self._recorte is not None:
            casam = casam[self._recorte[0] : self._recorte[1] + 1]
        if self._limite is not None:
            casam = casam[: self._limite]
        return SimpleNamespace(data=[dict(linha) for linha in casam])


class _Banco:
    def __init__(self, tabelas: dict[str, list[dict]]):
        self.tabelas = tabelas
        self.maior_in = 0

    def table(self, nome: str):
        return _Consulta(self, nome)


def _matriz_da_migration() -> list[dict[str, Any]]:
    """A matriz perfil x permissão como a migration 116 grava."""
    sql = MIGRATION_116.read_text(encoding="utf-8")
    bloco = re.search(r"INSERT INTO cm_perfil_permissao\s*\([^)]*\)\s*VALUES(.*?);", sql, flags=re.DOTALL)
    assert bloco, "a migration 116 nao carrega a matriz"
    linhas = re.findall(r"\(\s*'(\w+)'\s*,\s*'(\w+)'\s*,\s*(true|false)\s*\)", bloco.group(1))
    return [{"perfil": p, "permissao": k, "ligada": v == "true"} for p, k, v in linhas]


def _pessoa(pid: str, perfil: str | None, nome: str, **campos) -> dict[str, Any]:
    base = {
        "id": pid,
        "auth_user_id": f"auth-{pid}",
        "nome_completo": nome,
        "email": f"{pid.lower()}@hsm.test",
        "ativo": True,
        "is_externo": False,
        "is_super_admin": False,
        "access_profile": None,
        "perfil_pop": None,
        "perfil_ouvidoria": None,
        "perfil_contas_medicas": perfil,
        "github_login": None,
    }
    return {**base, **campos}


PESSOAS = {
    "ana": _pessoa("F1", "faturista", "Ana Faturista"),
    "bia": _pessoa("F2", "faturista", "Bia Faturista"),
    "coordenadora": _pessoa("CO", "coordenadora", "Carla Coordenadora"),
    "sem_eixo": _pessoa("RG", None, "Rui Sem Eixo", access_profile="regular"),
}


# ═══════════════════════════════════════════════════════════════════════════
# O cenário: 2 semanas, 2 operadoras, 2 faturistas
# ═══════════════════════════════════════════════════════════════════════════

ASSIM = "aaaaaaaa-0000-0000-0000-000000000001"
UNIMED = "aaaaaaaa-0000-0000-0000-000000000002"


def _conta(cid, atendimento, faturista, situacao, nota, concluida_em, custo) -> dict:
    return {
        "id": cid,
        "atendimento_id": atendimento,
        "faturista_id": faturista,
        "situacao": situacao,
        "nota_entrada": nota,
        "concluida_em": concluida_em,
        "custo_usd": custo,
    }


def _contas() -> list[dict]:
    return [
        # Semana escolhida (05/10 a 11/10)
        _conta("C1", "at-1", "F1", "CONCLUIDA", 80, "2026-10-06T14:00:00+00:00", 0.40),
        _conta("C2", "at-3", "F1", "CONCLUIDA_COM_PENDENCIA", 60, "2026-10-08T15:00:00+00:00", 0.20),
        _conta("C3", "at-2", "F2", "CONCLUIDA", 70, "2026-10-09T18:00:00+00:00", 0.60),
        # Semana anterior (28/09 a 04/10)
        _conta("C4", "at-4", "F2", "CONCLUIDA", 50, "2026-09-29T13:00:00+00:00", 0.30),
        _conta("C5", "at-2", "F1", "CONCLUIDA", 94, "2026-10-01T12:00:00+00:00", 0.10),
        # Concluída e enviada de novo: voltou para a fila e não conta mais.
        _conta("C6", "at-5", "F1", "NA_FILA", 10, "2026-10-07T12:00:00+00:00", 9.00),
    ]


def _atendimentos() -> list[dict]:
    return [
        {"id": "at-1", "operadora_id": ASSIM},
        {"id": "at-2", "operadora_id": ASSIM},
        {"id": "at-3", "operadora_id": UNIMED},
        {"id": "at-4", "operadora_id": UNIMED},
        {"id": "at-5", "operadora_id": ASSIM},
    ]


def _l(lid, conta, acao, codigo, descricao, valor, estado, causa, nivel, preco_tabela=1.0) -> dict:
    return {
        "id": lid,
        "conta_id": conta,
        "acao": acao,
        "codigo": codigo,
        "descricao": descricao,
        "valor_diferenca": valor,
        "preco_tabela": preco_tabela,
        "estado": estado,
        "causa_raiz": causa,
        "nivel_evidencia": nivel,
    }


def _linhas() -> list[dict]:
    return [
        # C1 (ASSIM, Ana)
        _l("L01", "C1", "INCLUIR", "M100", "Luva", 100.00, "FEITO", "DISPENSACAO", "REGISTRADO"),
        _l("L02", "C1", "INCLUIR", "M200", "Lanceta", 40.00, "FEITO", "DISPENSACAO", "PRESCRITO"),
        _l("L03", "C1", "RETIRAR", "T300", "Senha", -30.00, "FEITO", "LANCAMENTO_MANUAL", "REGISTRADO", None),
        _l("L04", "C1", "INCLUIR", "M300", "Fita", 20.00, "NAO_PROCEDE", "REGISTRO_ASSISTENCIAL", "POR_REGRA"),
        _l("L05", "C1", "VALIDAR", "X100", "Pacote", 500.00, "EM_VALIDACAO", "REGRA_AUTOMATICA", "POR_REGRA"),
        # C2 (UNIMED, Ana)
        _l("L06", "C2", "INCLUIR", "M100", "Luva", 60.00, "FEITO", "DISPENSACAO", "PRESCRITO_SN"),
        _l("L07", "C2", "CORRIGIR_PRECO", "P100", "Agulha", 15.00, "ABERTA", "CADASTRO_PRECO", "POR_REGRA"),
        _l("L08", "C2", "INCLUIR", "M400", "Seringa", 25.00, "BLOQUEADO", "CADASTRO_PRECO", "POR_REGRA", None),
        # C3 (ASSIM, Bia)
        _l("L09", "C3", "INCLUIR", "M100", "Luva", 50.00, "FEITO", "REGRA_AUTOMATICA", "POR_REGRA"),
        _l("L10", "C3", "INCLUIR", "M200", "Lanceta", 10.00, "NAO_PROCEDE", "DISPENSACAO", "PRESCRITO"),
        _l("L11", "C3", "AJUSTAR_QUANTIDADE", "Q100", "Fralda", -20.00, "FEITO", "LANCAMENTO_MANUAL", "REGISTRADO"),
        # C4 (UNIMED, Bia), semana anterior
        _l("L12", "C4", "INCLUIR", "M500", "Gaze", 70.00, "FEITO", "DISPENSACAO", "REGISTRADO"),
        # C5 (ASSIM, Ana), semana anterior
        _l("L13", "C5", "INCLUIR", "M100", "Luva", 30.00, "FEITO", "REGRA_AUTOMATICA", "PRESCRITO"),
        # C6, de volta na fila: nada dela entra
        _l("L14", "C6", "INCLUIR", "M100", "Luva", 999.00, "FEITO", "DISPENSACAO", "REGISTRADO"),
    ]


def _cenario(contas: list[dict] | None = None, linhas: list[dict] | None = None) -> _Banco:
    return _Banco(
        {
            "participantes": list(PESSOAS.values()),
            "cm_perfil_permissao": _matriz_da_migration(),
            "cm_operadora": [
                {"id": UNIMED, "sigla": "UNIMED", "nome": "Unimed"},
                {"id": ASSIM, "sigla": "ASSIM", "nome": "ASSIM Saúde"},
            ],
            "cm_atendimento": _atendimentos(),
            "cm_conta": _contas() if contas is None else contas,
            "cm_guia_linha": _linhas() if linhas is None else linhas,
        }
    )


def _cliente(quem: str, banco: _Banco) -> TestClient:
    pessoa = PESSOAS[quem]
    app = FastAPI()
    app.state.limiter = limiter
    app.include_router(painel_router.router, prefix="/api")

    async def _usuario() -> dict[str, Any]:
        return {"id": pessoa["auth_user_id"], "email": pessoa["email"], "metadata": {}}

    app.dependency_overrides[get_current_user] = _usuario
    app.dependency_overrides[get_supabase_client] = lambda: banco
    return TestClient(app)


def _painel(quem: str = "coordenadora", banco: _Banco | None = None, **filtros) -> dict:
    resposta = _cliente(quem, banco or _cenario()).get(ROTA, params={"semana": SEMANA, **filtros})
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


# ═══════════════════════════════════════════════════════════════════════════
# 1. Cada agregado, asserido pelo valor
# ═══════════════════════════════════════════════════════════════════════════


class TestOsCartoesDoTopo:
    def test_nota_media_de_entrada_da_semana_com_a_semana_anterior_ao_lado(self):
        painel = _painel()

        assert painel["semana"] == {"inicio": "2026-10-05", "fim": "2026-10-11"}
        # (80 + 60 + 70) / 3 e (50 + 94) / 2; a C6, de volta na fila, fica fora.
        assert painel["nota_media"] == {"semana": 70.0, "anterior": 72.0}
