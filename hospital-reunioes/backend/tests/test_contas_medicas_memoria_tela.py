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

    def test_permissao_segue_o_tipo_da_regra_e_a_recusa_nao_grava_nada(self):
        """A coordenadora com "incluir regra operacional" ligada (e sem "regra
        contratual e tabelas") muda a regra operacional e recebe 403 na
        contratual; trocar o tipo de operacional para contratual também pede a
        contratual. Quem só tem a contratual recebe 403 na operacional."""
        banco = _Banco()
        gestao, _ = _cliente(GESTAO, banco)
        _importar(gestao)
        coordenadora, _ = _cliente(
            _pessoa(perfil_contas_medicas="coordenadora"), banco, ligar=("incluir_regra_operacional",)
        )
        pri_01 = {"texto": "Identificar pelo número do atendimento.", "tipo": "OPERACIONAL", "origem": "PRÁTICA"}

        contratual = coordenadora.put(
            _regra("ALFA", "ALFA-DIA-01"), json={"texto": DIA_01_DEPOIS, "tipo": "CONTRATUAL", "origem": "PRÁTICA"}
        )
        virou_contratual = coordenadora.put(_regra("ALFA", "ALFA-PRI-01"), json={**pri_01, "tipo": "CONTRATUAL"})
        virou_operacional = coordenadora.put(
            _regra("ALFA", "ALFA-DIA-01"), json={"texto": DIA_01_DEPOIS, "tipo": "OPERACIONAL", "origem": "PRÁTICA"}
        )

        assert (contratual.status_code, virou_contratual.status_code, virou_operacional.status_code) == (403, 403, 403)
        assert _versoes(banco, "ALFA") == {"1.0": True}
        assert banco.linhas("cm_regra_historico") == []

        assert coordenadora.put(_regra("ALFA", "ALFA-PRI-01"), json=pri_01).status_code == 200
        assert _versoes(banco, "ALFA") == {"1.0": False, "1.1": True}

        so_contratual, _ = _cliente(
            _pessoa(perfil_contas_medicas="credenciamento"), banco, ligar=("regra_contratual_tabelas",)
        )
        assert so_contratual.put(_regra("ALFA", "ALFA-PRI-01"), json=pri_01).status_code == 403
        assert _versoes(banco, "ALFA") == {"1.0": False, "1.1": True}

    def test_faturista_recebe_403_e_regra_que_nao_existe_e_404(self):
        banco = _Banco()
        gestao, _ = _cliente(GESTAO, banco)
        _importar(gestao)
        faturista, _ = _cliente(_pessoa(perfil_contas_medicas="faturista"), banco)
        corpo = {"texto": DIA_01_DEPOIS, "tipo": "CONTRATUAL", "origem": "PRÁTICA"}

        assert faturista.put(_regra("ALFA", "ALFA-DIA-01"), json=corpo).status_code == 403
        gestao, _ = _cliente(GESTAO, banco)
        assert gestao.put(_regra("ALFA", "ALFA-DIA-99"), json=corpo).status_code == 404
        assert gestao.put(_regra("ZETA", "ZETA-DIA-01"), json=corpo).status_code == 404
        assert _versoes(banco, "ALFA") == {"1.0": True}


# ═══════════════════════════════════════════════════════════════════════════
# 2. Decidir uma regra pendente
# ═══════════════════════════════════════════════════════════════════════════

DIA_02_ANTES = "Transferência de setor antes das 10h: gera ou não diária extra no setor de origem."
DIA_02_DECIDIDA = "Transferência de setor antes das 10h não gera diária extra no setor de origem."


class TestDecidirPendente:
    def test_decidir_torna_a_regra_vigente_com_validador_e_data_e_a_conta_antiga_fica_na_versao_antiga(self):
        cliente, banco = _cliente(GESTAO)
        _importar(cliente)
        antiga = _versao(banco, "ALFA", "1.0")
        banco.tabelas["cm_conta"] = [{"id": "conta-1", "memoria_versao_id": antiga["id"], "situacao": "A_FAZER"}]

        resposta = cliente.post(
            _regra("ALFA", "ALFA-DIA-02") + "/decisao",
            json={"texto": DIA_02_DECIDIDA, "tipo": "CONTRATUAL", "origem": "PRÁTICA"},
        )

        assert resposta.status_code == 200, resposta.text
        assert _versoes(banco, "ALFA") == {"1.0": False, "1.1": True}
        regras = {r["codigo"]: r for r in banco.linhas("cm_regra") if r["memoria_versao_id"] == _versao(banco, "ALFA", "1.1")["id"]}
        decidida = regras["ALFA-DIA-02"]
        assert (decidida["status"], decidida["texto"], decidida["validado_por"]) == ("VIGENTE", DIA_02_DECIDIDA, "P1")
        assert decidida["validado_em"][:10] == datetime.now(UTC).date().isoformat()
        assert regras["ALFA-PRI-03"]["status"] == "PENDENTE", "só a decidida muda"
        [historico] = banco.linhas("cm_regra_historico")
        assert (historico["texto_anterior"], historico["texto_novo"]) == (DIA_02_ANTES, DIA_02_DECIDIDA)

        # A conta analisada antes continua na versão antiga, e a versão antiga
        # continua dizendo o que dizia: a regra ainda pendente, com o texto de antes.
        [conta] = banco.linhas("cm_conta")
        assert conta["memoria_versao_id"] == antiga["id"]
        da_conta = {r.codigo: r for r in ler_memoria(gerar_texto_memoria(banco, antiga["operadora_id"], antiga["id"])).regras}
        assert (da_conta["ALFA-DIA-02"].status, da_conta["ALFA-DIA-02"].texto) == ("PENDENTE", DIA_02_ANTES)

    def test_decidir_regra_vigente_ou_editar_pendente_e_recusado_sem_versao_nova(self):
        cliente, banco = _cliente(GESTAO)
        _importar(cliente)
        corpo = {"texto": DIA_02_DECIDIDA, "tipo": "CONTRATUAL", "origem": "PRÁTICA"}

        assert cliente.post(_regra("ALFA", "ALFA-DIA-01") + "/decisao", json=corpo).status_code == 409
        assert cliente.put(_regra("ALFA", "ALFA-DIA-02"), json=corpo).status_code == 409
        assert _versoes(banco, "ALFA") == {"1.0": True}


# ═══════════════════════════════════════════════════════════════════════════
# 3. "Aplicar a todas as operadoras que têm esta regra"
# ═══════════════════════════════════════════════════════════════════════════

PRI_01_NOVA = "Identificar sempre pelo número do atendimento e pela data de entrada, nunca pelo número da conta."


def _com_modelo(banco: _Banco, codigo: str, modelo_id: str) -> None:
    """A regra que veio do Modelo HSM: a carga ainda não lê `modelo_id` do arquivo."""
    for regra in banco.linhas("cm_regra"):
        if regra["codigo"] == codigo:
            regra["modelo_id"] = modelo_id


class TestAplicarATodas:
    def test_diretriz_geral_gera_uma_versao_em_cada_operadora_com_o_mesmo_modelo_e_nenhuma_nas_outras(self):
        cliente, banco = _cliente(GESTAO)
        for arquivo in ("MEMORIA-ALFA-v1.0.md", "MEMORIA-BETA-v1.0.md", "MEMORIA-GAMA-v2.0.md"):
            _importar(cliente, arquivo)
        _com_modelo(banco, "ALFA-PRI-01", "HSM-PRI-01")
        _com_modelo(banco, "GAMA-PRI-01", "HSM-PRI-01")
        _com_modelo(banco, "BETA-INS-00", "HSM-INS-00")

        resposta = cliente.put(
            _regra("ALFA", "ALFA-PRI-01"),
            json={"texto": PRI_01_NOVA, "tipo": "OPERACIONAL", "origem": "PRÁTICA", "aplicar_a_todas": True},
        )

        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["outras_operadoras"] == [{"operadora": "GAMA", "versao": "2.1"}]
        assert _versoes(banco, "ALFA") == {"1.0": False, "1.1": True}
        assert _versoes(banco, "GAMA") == {"2.0": False, "2.1": True}
        assert _versoes(banco, "BETA") == {"1.0": True}

        gama = {r["codigo"]: r for r in memoria_vigente(banco, _operadora_id(banco, "GAMA"))["regras"]}
        assert gama["GAMA-PRI-01"]["texto"] == PRI_01_NOVA
        assert len(gama) == 4, "a versão da GAMA leva as regras dela, e não as da ALFA"
        assert gama["GAMA-DIA-01"]["texto"] == "A diária vence às 10h e é sempre integral."
        assert {h["texto_novo"] for h in banco.linhas("cm_regra_historico")} == {PRI_01_NOVA}
        assert len(banco.linhas("cm_regra_historico")) == 2

    def test_sem_aplicar_a_todas_so_a_operadora_editada_muda(self):
        cliente, banco = _cliente(GESTAO)
        for arquivo in ("MEMORIA-ALFA-v1.0.md", "MEMORIA-GAMA-v2.0.md"):
            _importar(cliente, arquivo)
        _com_modelo(banco, "ALFA-PRI-01", "HSM-PRI-01")
        _com_modelo(banco, "GAMA-PRI-01", "HSM-PRI-01")

        resposta = cliente.put(
            _regra("ALFA", "ALFA-PRI-01"), json={"texto": PRI_01_NOVA, "tipo": "OPERACIONAL", "origem": "PRÁTICA"}
        )

        assert resposta.json()["outras_operadoras"] == []
        assert _versoes(banco, "GAMA") == {"2.0": True}
