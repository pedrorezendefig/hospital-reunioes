"""Carga da operadora em Contas médicas (issue #1119, PRD #1113, ADR 0070).

A gestão envia o arquivo de memória da operadora, cadastra os nomes de plano
que o MV imprime e os setores com a acomodação de cada um. Tudo pela rota de
verdade, atrás da permissão "regra contratual e tabelas".

As memórias de teste são sintéticas, no formato do MODELO-MEMORIA-OPERADORA.md
do diretor: as reais (ASSIM, Unimed) vivem em `local/contas-medicas/`, fora do
git, e entram em produção pela tela.

O dublê do banco guarda as restrições da migration 116 que a carga pode ferir:
uma versão vigente por operadora, nome do MV único sem diferença de
maiúscula, e os CHECKs de tipo, status, situação e acomodação. Violar uma
delas estoura como o PostgREST estouraria, para o teste não ficar verde sobre
um banco que aceitaria qualquer coisa.
"""

from __future__ import annotations

import os
import re
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from postgrest.exceptions import APIError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.dependencies import get_current_user, get_supabase_client  # noqa: E402
from app.limiter import limiter  # noqa: E402
from app.routers import contas_medicas_operadoras as operadoras_router  # noqa: E402

MIGRATION = Path(__file__).resolve().parents[2] / "supabase" / "migrations" / "116_contas_medicas_fundacao.sql"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "contas_medicas" / "memoria"

ROTA_MEMORIA = "/api/contas-medicas/operadoras/memoria"


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


def _memoria(nome: str) -> str:
    return (FIXTURES / nome).read_text(encoding="utf-8")


def _matriz_da_migration() -> list[dict[str, Any]]:
    sql = MIGRATION.read_text(encoding="utf-8")
    bloco = re.search(r"INSERT INTO cm_perfil_permissao\s*\([^)]*\)\s*VALUES(.*?);", sql, flags=re.DOTALL)
    assert bloco, "a migration 116 nao carrega a matriz"
    linhas = re.findall(r"\(\s*'(\w+)'\s*,\s*'(\w+)'\s*,\s*(true|false)\s*\)", bloco.group(1))
    return [{"perfil": p, "permissao": k, "ligada": v == "true"} for p, k, v in linhas]


# ═══════════════════════════════════════════════════════════════════════════
# O dublê do banco
# ═══════════════════════════════════════════════════════════════════════════

ACOMODACOES = {
    "CTI",
    "ENFERMARIA",
    "APARTAMENTO",
    "ISOLAMENTO",
    "CENTRO_CIRURGICO",
    "HOSPITAL_DIA",
    "PEDIATRIA",
    "UTI_PEDIATRICA",
    "UTI_NEONATAL",
}

# Os padrões de coluna da migration 116 que a carga deixa de mandar.
PADROES = {
    "cm_operadora": {"situacao": "SEM_MEMORIA"},
    "cm_memoria_versao": {"vigente": False, "parametros_json": {}},
    "cm_regra": {"status": "PENDENTE", "ativa": True},
}

# Os CHECKs da migration 116 (valor permitido por coluna; None = nulo aceito).
CHECKS = {
    ("cm_operadora", "situacao"): {"PRONTA", "PARCIAL", "SEM_MEMORIA"},
    ("cm_regra", "tipo"): {None, "CONTRATUAL", "OPERACIONAL"},
    ("cm_regra", "status"): {"VIGENTE", "PENDENTE"},
    ("cm_setor", "acomodacao"): {None, *ACOMODACOES},
}

NAO_NULOS = {
    "cm_operadora": ("sigla", "nome"),
    "cm_memoria_versao": ("operadora_id", "versao"),
    "cm_regra": ("operadora_id", "codigo", "texto"),
    "cm_operadora_plano": ("operadora_id", "nome_mv"),
    "cm_setor": ("nome_mv",),
}


def _erro(codigo: str, mensagem: str) -> APIError:
    return APIError({"code": codigo, "message": mensagem, "details": None, "hint": None})


class _Consulta:
    def __init__(self, banco: _Banco, tabela: str):
        self._banco = banco
        self._tabela = tabela
        self._filtros: list = []
        self._ordem: tuple[str, bool] | None = None
        self._operacao = "select"
        self._payload: Any = None

    def select(self, *_a, **_kw):
        return self

    def eq(self, coluna, valor):
        self._filtros.append(lambda linha: linha.get(coluna) == valor)
        return self

    def in_(self, coluna, valores):
        valores = list(valores)
        self._filtros.append(lambda linha: linha.get(coluna) in valores)
        return self

    def order(self, coluna, desc=False):
        self._ordem = (coluna, desc)
        return self

    def limit(self, _n):
        return self

    def insert(self, payload):
        self._operacao = "insert"
        self._payload = payload
        return self

    def update(self, payload):
        self._operacao = "update"
        self._payload = payload
        return self

    def _casam(self) -> list[dict]:
        return [linha for linha in self._banco.linhas(self._tabela) if all(f(linha) for f in self._filtros)]

    def execute(self):
        if self._operacao == "insert":
            novas = self._payload if isinstance(self._payload, list) else [self._payload]
            gravadas = [self._banco.inserir(self._tabela, dict(linha)) for linha in novas]
            return SimpleNamespace(data=[dict(g) for g in gravadas], count=len(gravadas))
        if self._operacao == "update":
            alvo = self._casam()
            for linha in alvo:
                self._banco.atualizar(self._tabela, linha, dict(self._payload))
            return SimpleNamespace(data=[dict(linha) for linha in alvo], count=len(alvo))
        casam = [dict(linha) for linha in self._casam()]
        if self._ordem:
            coluna, desc = self._ordem
            casam.sort(key=lambda linha: (linha.get(coluna) is None, linha.get(coluna)), reverse=desc)
        return SimpleNamespace(data=casam, count=len(casam))


class _Banco:
    def __init__(self, tabelas: dict[str, list[dict]] | None = None):
        self.tabelas: dict[str, list[dict]] = tabelas or {}

    def linhas(self, tabela: str) -> list[dict]:
        return self.tabelas.setdefault(tabela, [])

    def table(self, nome: str):
        return _Consulta(self, nome)

    def _validar(self, tabela: str, linha: dict, ignorar: dict | None = None) -> None:
        for coluna in NAO_NULOS.get(tabela, ()):
            if linha.get(coluna) is None:
                raise _erro("23502", f"null value in column {coluna} of relation {tabela}")
        for (t, coluna), permitidos in CHECKS.items():
            if t == tabela and coluna in linha and linha[coluna] not in permitidos:
                raise _erro("23514", f"new row for relation {tabela} violates check constraint ({coluna})")
        outras = [o for o in self.linhas(tabela) if o is not ignorar]
        if tabela == "cm_operadora" and any(o["sigla"] == linha["sigla"] for o in outras):
            raise _erro("23505", "duplicate key value violates unique constraint cm_operadora_sigla_key")
        if tabela in ("cm_operadora_plano", "cm_setor") and any(
            o["nome_mv"].lower() == linha["nome_mv"].lower() for o in outras
        ):
            raise _erro("23505", f"duplicate key value violates unique constraint idx_{tabela}_nome_mv")
        if tabela == "cm_memoria_versao" and linha.get("vigente"):
            if any(o["operadora_id"] == linha["operadora_id"] and o.get("vigente") for o in outras):
                raise _erro("23505", "duplicate key value violates unique constraint idx_cm_memoria_versao_vigente")

    def inserir(self, tabela: str, linha: dict) -> dict:
        completa = {**PADROES.get(tabela, {}), "id": str(uuid.uuid4()), **linha}
        self._validar(tabela, completa)
        self.linhas(tabela).append(completa)
        return completa

    def atualizar(self, tabela: str, linha: dict, mudancas: dict) -> None:
        self._validar(tabela, {**linha, **mudancas}, ignorar=linha)
        linha.update(mudancas)


def _pessoa(**campos) -> dict[str, Any]:
    base = {
        "id": "P1",
        "auth_user_id": "auth-p1",
        "nome_completo": "Pessoa de Teste",
        "email": "p1@hsm.test",
        "ativo": True,
        "is_super_admin": False,
        "access_profile": None,
        "perfil_pop": None,
        "perfil_ouvidoria": None,
        "perfil_contas_medicas": None,
    }
    return {**base, **campos}


GESTAO = _pessoa(perfil_contas_medicas="gestao_contas_medicas")
FATURISTA = _pessoa(perfil_contas_medicas="faturista")


def _cliente(pessoa: dict[str, Any], banco: _Banco | None = None) -> tuple[TestClient, _Banco]:
    banco = banco or _Banco()
    banco.tabelas["participantes"] = [pessoa]
    banco.tabelas["cm_perfil_permissao"] = _matriz_da_migration()
    app = FastAPI()
    app.state.limiter = limiter
    app.include_router(operadoras_router.router, prefix="/api")

    async def _usuario() -> dict[str, Any]:
        return {"id": pessoa["auth_user_id"], "email": pessoa["email"], "metadata": {}}

    app.dependency_overrides[get_current_user] = _usuario
    app.dependency_overrides[get_supabase_client] = lambda: banco
    return TestClient(app), banco


def _enviar_memoria(cliente: TestClient, texto: str, nome: str = "MEMORIA.md"):
    return cliente.post(ROTA_MEMORIA, files={"arquivo": (nome, texto.encode("utf-8"), "text/markdown")})


# ═══════════════════════════════════════════════════════════════════════════
# 1. Envio do arquivo de memória
# ═══════════════════════════════════════════════════════════════════════════


class TestEnvioDaMemoria:
    def test_memoria_de_duas_secoes_cria_a_operadora_a_versao_e_as_cinco_regras(self):
        cliente, banco = _cliente(GESTAO)

        resposta = _enviar_memoria(cliente, _memoria("MEMORIA-ALFA-v1.0.md"))

        assert resposta.status_code == 201, resposta.text
        corpo = resposta.json()
        assert corpo["operadora"] == "ALFA"
        assert corpo["versao"] == "1.0"
        assert corpo["regras"] == {"total": 5, "vigentes": 3, "pendentes": 2}
        assert corpo["parametros"]["diaria"]["hora_vencimento"] == "10:00"
        assert corpo["parametros"]["colunas_de_preco"]["CARIOCA"] == ["Alfa Max Qc", "Alfa Intermediário Qp"]

        [operadora] = banco.linhas("cm_operadora")
        assert (operadora["sigla"], operadora["nome"], operadora["situacao"]) == ("ALFA", "Alfa Saúde", "PARCIAL")
        [versao] = banco.linhas("cm_memoria_versao")
        assert versao["operadora_id"] == operadora["id"]
        assert versao["vigente"] is True
        assert versao["autor_id"] == "P1"
        regras = {r["codigo"]: r for r in banco.linhas("cm_regra")}
        assert sorted(regras) == ["ALFA-DIA-01", "ALFA-DIA-02", "ALFA-PRI-01", "ALFA-PRI-02", "ALFA-PRI-03"]
        assert all(r["memoria_versao_id"] == versao["id"] for r in regras.values())
        assert {k: (r["secao"], r["tipo"], r["origem"], r["status"]) for k, r in regras.items()} == {
            "ALFA-PRI-01": ("PRI", "OPERACIONAL", "PRÁTICA", "VIGENTE"),
            "ALFA-PRI-02": ("PRI", "OPERACIONAL", "PRÁTICA", "VIGENTE"),
            "ALFA-PRI-03": ("PRI", "CONTRATUAL", "CONTRATO", "PENDENTE"),
            "ALFA-DIA-01": ("DIA", "CONTRATUAL", "PRÁTICA", "VIGENTE"),
            "ALFA-DIA-02": ("DIA", "CONTRATUAL", "PRÁTICA", "PENDENTE"),
        }
        assert regras["ALFA-DIA-01"]["texto"] == (
            "A diária começa em qualquer horário, vence às 10h e é sempre integral."
        )
        assert regras["ALFA-DIA-01"]["validado_em"] == "2026-10-06"
        assert regras["ALFA-DIA-02"]["validado_em"] is None

    def test_quem_nao_tem_regra_contratual_e_tabelas_recebe_403_e_nada_e_gravado(self):
        """Mutante: tirar a permissão da rota. A faturista gravaria a memória."""
        cliente, banco = _cliente(FATURISTA)

        resposta = _enviar_memoria(cliente, _memoria("MEMORIA-ALFA-v1.0.md"))

        assert resposta.status_code == 403
        assert banco.linhas("cm_operadora") == []
        assert banco.linhas("cm_regra") == []
