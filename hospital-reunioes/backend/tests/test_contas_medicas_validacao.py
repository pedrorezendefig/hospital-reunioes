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

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from openai import OpenAI
from postgrest.exceptions import APIError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from test_contas_medicas_processamento import _Banco, _Consulta, _matriz_da_migration, _pessoa  # noqa: E402

from app.dependencies import get_current_user, get_supabase_client  # noqa: E402
from app.limiter import limiter  # noqa: E402
from app.routers import contas_medicas_envio as envio_router  # noqa: E402
from app.routers import contas_medicas_guia as guia_router  # noqa: E402
from app.routers import contas_medicas_validacao as validacao_router  # noqa: E402
from app.services.contas_medicas import ia, processamento  # noqa: E402
from app.services.contas_medicas.conferencia import Conferencia  # noqa: E402
from app.services.contas_medicas.dicionario import casar, dicionario_do_banco  # noqa: E402
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
TEXTO_VIGENTE = "Medicamento prescrito e não lançado é incluído."


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


def _conta_id(n: int) -> str:
    """A rota do Guia pede UUID no caminho."""
    return f"00000000-0000-4000-8000-00000000000{n}"


C1, C2, C3 = _conta_id(1), _conta_id(2), _conta_id(3)


def _conta(n: int, situacao: str) -> dict[str, Any]:
    return {
        "id": _conta_id(n),
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
                _regra(REGRA_VIGENTE, "VIGENTE", TEXTO_VIGENTE, "OPERACIONAL"),
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


def _decidir(banco: _Banco, tema_id: str, corpo: dict, quem: str = "gestao"):
    return _cliente(banco, quem).post(f"/api/contas-medicas/validacao/temas/{tema_id}/decisao", json=corpo)


def _linha(banco: _Banco, linha_id: str) -> dict:
    return next(linha for linha in banco.tabelas["cm_guia_linha"] if linha["id"] == linha_id)


def _guia(banco: _Banco, conta_id: str, quem: str = "faturista") -> dict:
    resposta = _cliente(banco, quem).get(f"/api/contas-medicas/contas/{conta_id}/guia")
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


def _linhas_do_guia(guia: dict) -> list[dict]:
    return [linha for grupo in guia["grupos"] for linha in grupo["linhas"]]


def _validar_em_tres_contas(banco: _Banco) -> None:
    _gravar(banco, C1, _linha_do_guia("VALIDAR", "70000010", 120.0, REGRA_PENDENTE))
    _gravar(banco, C2, _linha_do_guia("VALIDAR", "70000010", 80.0, REGRA_PENDENTE))
    _gravar(banco, C3, _linha_do_guia("VALIDAR", "70000010", 50.5, REGRA_PENDENTE))


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

    def test_validar_regra_torna_vigente_em_versao_nova_decide_as_tres_linhas_e_a_concluida_volta_em_retorno(self):
        banco = _cenario()
        _validar_em_tres_contas(banco)
        # A conta concluída tem outra linha, já feita: ela não volta.
        _gravar(
            banco,
            C3,
            _linha_do_guia("VALIDAR", "70000010", 50.5, REGRA_PENDENTE),
            _linha_do_guia("INCLUIR", "90030001", 45.0, REGRA_VIGENTE),
        )
        feita = next(linha for linha in banco.tabelas["cm_guia_linha"] if linha["codigo"] == "90030001")
        feita["estado"] = "FEITO"
        [tema] = _fila_de_validacao(banco)["temas"]

        resposta = _decidir(banco, tema["id"], {"decisao": "VALIDAR_REGRA", "texto": TEXTO_PENDENTE})

        assert resposta.status_code == 200, resposta.text
        # A regra vigente, numa versão nova da memória.
        vigente = next(v for v in banco.tabelas["cm_memoria_versao"] if v["vigente"])
        assert vigente["versao"] == "1.1"
        regra = next(
            r
            for r in banco.tabelas["cm_regra"]
            if r["memoria_versao_id"] == vigente["id"] and r["codigo"] == REGRA_PENDENTE
        )
        assert (regra["status"], regra["validado_por"]) == ("VIGENTE", "G1")
        # As três linhas Decidida, com a ação que a regra manda (incluir).
        decididas = [linha for linha in banco.tabelas["cm_guia_linha"] if linha["codigo"] == "70000010"]
        assert sorted(linha["conta_id"] for linha in decididas) == [C1, C2, C3]
        assert {(linha["estado"], linha["acao"]) for linha in decididas} == {("DECIDIDA", "INCLUIR")}
        # A decisão grava quem e quando, e o tema sai da fila.
        gravado = next(t for t in banco.tabelas["cm_validacao_tema"] if t["id"] == tema["id"])
        assert (gravado["estado"], gravado["decisao"], gravado["decidido_por"]) == ("DECIDIDO", "VALIDAR_REGRA", "G1")
        assert gravado["decidido_em"]
        assert _fila_de_validacao(banco)["temas"] == []
        # Só a concluída vai para Retorno; as outras seguem com a faturista.
        assert {c["id"]: c["situacao"] for c in banco.tabelas["cm_conta"]} == {
            C1: "EM_CORRECAO",
            C2: "A_FAZER",
            C3: "RETORNO",
        }
        # A concluída aparece na fila da faturista, e o Guia dela traz só a linha decidida.
        fila = _cliente(banco, "faturista").get("/api/contas-medicas/fila").json()
        assert (C3, "RETORNO") in {(c["id"], c["situacao"]) for c in fila["fila"]}
        linhas = _linhas_do_guia(_guia(banco, C3))
        assert [(linha["codigo"], linha["acao"], linha["estado"]) for linha in linhas] == [
            ("70000010", "INCLUIR", "DECIDIDA")
        ]

    def test_linha_decidida_e_pendencia_da_faturista_ate_ela_marcar_no_retorno(self):
        banco = _cenario()
        _validar_em_tres_contas(banco)
        [tema] = _fila_de_validacao(banco)["temas"]
        assert _decidir(banco, tema["id"], {"decisao": "VALIDAR_REGRA"}).status_code == 200
        faturista = _cliente(banco, "faturista")

        sem_marcar = faturista.post(f"/api/contas-medicas/contas/{C3}/guia/concluir", json={})
        assert sem_marcar.json()["situacao"] == "CONCLUIDA_COM_PENDENCIA"

        banco.conta(C3)["situacao"] = "RETORNO"
        [linha] = _linhas_do_guia(_guia(banco, C3))
        assert _guia(banco, C3)["numeros"]["itens_sem_marcacao"] == 1
        feito = faturista.post(
            f"/api/contas-medicas/contas/{C3}/guia/linhas/{linha['id']}/marcacao", json={"estado": "FEITO"}
        )
        assert feito.status_code == 200, feito.text
        concluida = faturista.post(f"/api/contas-medicas/contas/{C3}/guia/concluir", json={})
        assert concluida.json()["situacao"] == "CONCLUIDA"

    def test_regra_vigente_validada_sem_texto_novo_nao_cria_versao_e_linha_sem_diferenca_e_descartada(self):
        """A linha Validar de regra já vigente (o caso ambíguo) e a que não diz
        o que corrigir (a diária que não fecha): Decidida sem ação, sem Retorno."""
        banco = _cenario()
        _gravar(
            banco,
            C3,
            _linha_do_guia(
                "VALIDAR",
                None,
                300.0,
                REGRA_VIGENTE,
                quantidade_lancada=None,
                quantidade_devida=None,
                preco_tabela=None,
                descricao="Diária",
            ),
        )
        [tema] = _fila_de_validacao(banco)["temas"]
        assert _guia(banco, C3)["numeros"]["valor_em_validacao"] == 300.0

        assert _decidir(banco, tema["id"], {"decisao": "VALIDAR_REGRA"}).status_code == 200

        assert [v["versao"] for v in banco.tabelas["cm_memoria_versao"]] == ["1.0"]
        [linha] = banco.tabelas["cm_guia_linha"]
        assert (linha["acao"], linha["estado"]) == ("VALIDAR", "DECIDIDA")
        assert banco.conta(C3)["situacao"] == "CONCLUIDA_COM_PENDENCIA"
        assert _guia(banco, C3)["numeros"]["valor_em_validacao"] == 0

    def test_deixar_pendente_fecha_o_tema_sem_mexer_na_memoria_nem_nas_linhas(self):
        banco = _cenario()
        _validar_em_tres_contas(banco)
        [tema] = _fila_de_validacao(banco)["temas"]

        assert _decidir(banco, tema["id"], {"decisao": "DEIXAR_PENDENTE"}).status_code == 200

        assert [v["versao"] for v in banco.tabelas["cm_memoria_versao"]] == ["1.0"]
        assert {(linha["acao"], linha["estado"]) for linha in banco.tabelas["cm_guia_linha"]} == {("VALIDAR", "ABERTA")}
        assert _fila_de_validacao(banco)["temas"] == []
        assert _decidir(banco, tema["id"], {"decisao": "VALIDAR_REGRA"}).status_code == 409


# ═══════════════════════════════════════════════════════════════════════════
# 2. Bloqueado: um tema por código, e a lista para o cadastro
# ═══════════════════════════════════════════════════════════════════════════

CATETER = "70000020"


def _marcar(banco: _Banco, conta_id: str, linha_id: str, corpo: dict):
    resposta = _cliente(banco, "faturista").post(
        f"/api/contas-medicas/contas/{conta_id}/guia/linhas/{linha_id}/marcacao", json=corpo
    )
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


def _bloquear_em_duas_contas(banco: _Banco) -> list[dict]:
    linhas = []
    for conta_id in (C1, C2):
        [linha] = _gravar(
            banco,
            conta_id,
            _linha_do_guia("INCLUIR", CATETER, 33.0, REGRA_VIGENTE, descricao="CATETER VENOSO CENTRAL DUPLO"),
        )
        linhas.append(_marcar(banco, conta_id, linha["id"], {"estado": "BLOQUEADO"}))
    return linhas


def _tema_no_banco(banco: _Banco, tema_id: str) -> dict:
    return next(t for t in banco.tabelas["cm_validacao_tema"] if t["id"] == tema_id)


class TestBloqueado:
    def test_bloqueado_em_duas_contas_pelo_mesmo_codigo_vira_um_tema_e_enviar_ao_cadastro_gera_o_csv(self):
        banco = _cenario()
        _bloquear_em_duas_contas(banco)

        [tema] = _fila_de_validacao(banco)["temas"]
        assert (tema["tipo"], tema["codigo_item"], tema["contas"], tema["valor"]) == ("BLOQUEADO", CATETER, 2, 66.0)
        assert tema["operadora"] == "ALFA"

        resposta = _cliente(banco).post(f"/api/contas-medicas/validacao/temas/{tema['id']}/cadastro")

        assert resposta.status_code == 200, resposta.text
        assert resposta.headers["content-type"].startswith("text/csv")
        assert "attachment" in resposta.headers["content-disposition"]
        linhas = resposta.content.decode("utf-8-sig").splitlines()
        assert linhas == [
            "Código;Descrição;Operadora;Coluna;Preço de tabela;Contas afetadas",
            f"{CATETER};CATETER VENOSO CENTRAL DUPLO;ALFA;COMUM;33,00;31301 (48801), 31302 (48802)",
        ]
        gravado = _tema_no_banco(banco, tema["id"])
        assert (gravado["estado"], gravado["decisao"], gravado["decidido_por"]) == (
            "DECIDIDO",
            "ENVIAR_AO_CADASTRO",
            "G1",
        )
        assert _fila_de_validacao(banco)["temas"] == []

    def test_descartar_fecha_o_tema_sem_csv(self):
        banco = _cenario()
        _bloquear_em_duas_contas(banco)
        [tema] = _fila_de_validacao(banco)["temas"]

        resposta = _decidir(banco, tema["id"], {"decisao": "DESCARTAR"})

        assert resposta.status_code == 200, resposta.text
        assert resposta.headers["content-type"].startswith("application/json")
        assert _tema_no_banco(banco, tema["id"])["decisao"] == "DESCARTAR"
        assert _cliente(banco).post(f"/api/contas-medicas/validacao/temas/{tema['id']}/cadastro").status_code == 409

    def test_desfazer_o_bloqueado_tira_a_linha_do_tema(self):
        banco = _cenario()
        primeira, _segunda = _bloquear_em_duas_contas(banco)

        desfeita = _cliente(banco, "faturista").delete(
            f"/api/contas-medicas/contas/{C1}/guia/linhas/{primeira['id']}/marcacao"
        )

        assert desfeita.status_code == 200, desfeita.text
        [tema] = _fila_de_validacao(banco)["temas"]
        assert (tema["contas"], tema["valor"]) == (1, 33.0)


# ═══════════════════════════════════════════════════════════════════════════
# 3. Observação do time: um tema por regra citada, com a leitura da IA
# ═══════════════════════════════════════════════════════════════════════════

LEITURA = {
    "cobre": False,
    "sugestao": "EDITAR",
    "leitura": "A regra não trata do Clexane dentro do pacote da ALFA.",
}


class _OpenRouter:
    """O provedor do teste, na fronteira HTTP: devolve a leitura no formato
    pedido, guarda o que recebeu e conta as requisições."""

    def __init__(self):
        self.corpos: list[dict] = []
        self.leitura = LEITURA

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.corpos.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "id": "gen",
                "object": "chat.completion",
                "created": 1,
                "model": "m",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": json.dumps(self.leitura)},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15, "cost": 0.001},
            },
        )

    def texto_enviado(self, i: int = 0) -> str:
        return json.dumps(self.corpos[i]["messages"], ensure_ascii=False)


@pytest.fixture
def provedor(monkeypatch) -> _OpenRouter:
    duble = _OpenRouter()
    monkeypatch.setattr(
        ia,
        "_cliente",
        lambda: OpenAI(
            api_key="chave-de-teste",
            base_url="https://openrouter.ai/api/v1",
            http_client=httpx.Client(transport=httpx.MockTransport(duble)),
            max_retries=0,
        ),
    )
    monkeypatch.setattr(ia, "_esperar", lambda _segundos: None)
    return duble


def _nao_procede(banco: _Banco, conta_id: str, texto: str) -> dict:
    [linha] = _gravar(banco, conta_id, _linha_do_guia("INCLUIR", "90030001", 45.0, REGRA_VIGENTE))
    return _marcar(banco, conta_id, linha["id"], {"estado": "NAO_PROCEDE", "motivo": "REGRA_E_OUTRA", "texto": texto})


def _ler(banco: _Banco, tema_id: str):
    return _cliente(banco).post(f"/api/contas-medicas/validacao/temas/{tema_id}/leitura")


class TestObservacao:
    def test_nao_procede_vira_tema_da_regra_a_leitura_da_ia_e_uma_so_e_a_resposta_aparece_no_guia(self, provedor):
        banco = _cenario()
        _nao_procede(banco, C1, "Na ALFA o Clexane vem dentro do pacote")

        [tema] = _fila_de_validacao(banco)["temas"]
        assert (tema["tipo"], tema["regra_codigo"], tema["operadora"], tema["contas"]) == (
            "OBSERVACAO",
            REGRA_VIGENTE,
            "ALFA",
            1,
        )
        assert tema["observacoes"] == ["A regra é outra: Na ALFA o Clexane vem dentro do pacote"]
        assert tema["leitura_ia"] is None

        primeira, segunda = _ler(banco, tema["id"]), _ler(banco, tema["id"])

        assert primeira.status_code == 200, primeira.text
        esperada = (
            "A regra atual não cobre o caso. A regra não trata do Clexane dentro do pacote da ALFA."
            " Sugestão: editar a regra."
        )
        assert primeira.json()["leitura_ia"] == segunda.json()["leitura_ia"] == esperada
        assert len(provedor.corpos) == 1, "a leitura fica guardada no tema: uma chamada por observação"
        assert TEXTO_VIGENTE in provedor.texto_enviado() and "Clexane vem dentro do pacote" in provedor.texto_enviado()
        assert _fila_de_validacao(banco)["temas"][0]["leitura_ia"] == esperada
        [chamada] = banco.tabelas["cm_chamada_ia"]
        assert chamada["passo"] == "OBSERVACAO"

        resposta = _decidir(
            banco, tema["id"], {"decisao": "RESPONDER", "texto": "Confirmado com a ALFA: vem no pacote."}
        )

        assert resposta.status_code == 200, resposta.text
        assert _tema_no_banco(banco, tema["id"])["resposta"] == "Confirmado com a ALFA: vem no pacote."
        [recado] = _guia(banco, C1)["respostas"]
        assert recado["resposta"] == "Confirmado com a ALFA: vem no pacote."
        assert recado["regra_codigo"] == REGRA_VIGENTE
        assert _guia(banco, C2)["respostas"] == []

    def test_observacao_nova_no_tema_pede_leitura_nova(self, provedor):
        banco = _cenario()
        _nao_procede(banco, C1, "Na ALFA o Clexane vem dentro do pacote")
        [tema] = _fila_de_validacao(banco)["temas"]
        assert _ler(banco, tema["id"]).status_code == 200

        _nao_procede(banco, C2, "Mesma coisa na conta de outubro")

        [tema] = _fila_de_validacao(banco)["temas"]
        assert (tema["contas"], tema["leitura_ia"]) == (2, None)
        assert _ler(banco, tema["id"]).status_code == 200
        assert len(provedor.corpos) == 2

    def test_observacao_da_conclusao_entra_no_tema_da_regra_que_ela_cita(self):
        banco = _cenario()
        banco.conta(C1)["situacao"] = "EM_CORRECAO"

        concluida = _cliente(banco, "faturista").post(
            f"/api/contas-medicas/contas/{C1}/guia/concluir",
            json={"observacao": f"A {REGRA_VIGENTE} não vale para o Clexane da ALFA."},
        )

        assert concluida.status_code == 200, concluida.text
        [tema] = _fila_de_validacao(banco)["temas"]
        assert (tema["tipo"], tema["regra_codigo"], tema["contas"]) == ("OBSERVACAO", REGRA_VIGENTE, 1)
        assert tema["observacoes"] == [f"A {REGRA_VIGENTE} não vale para o Clexane da ALFA."]

    def test_manter_a_regra_fecha_o_tema_e_editar_a_regra_grava_versao_nova(self):
        banco = _cenario()
        _nao_procede(banco, C1, "Na ALFA o Clexane vem dentro do pacote")
        [tema] = _fila_de_validacao(banco)["temas"]

        editada = _decidir(banco, tema["id"], {"decisao": "EDITAR_REGRA", "texto": TEXTO_VIGENTE + " Fora de pacote."})

        assert editada.status_code == 200, editada.text
        vigente = next(v for v in banco.tabelas["cm_memoria_versao"] if v["vigente"])
        regra = next(
            r
            for r in banco.tabelas["cm_regra"]
            if r["memoria_versao_id"] == vigente["id"] and r["codigo"] == REGRA_VIGENTE
        )
        assert (vigente["versao"], regra["texto"]) == ("1.1", TEXTO_VIGENTE + " Fora de pacote.")
        assert _tema_no_banco(banco, tema["id"])["decisao"] == "EDITAR_REGRA"

        _nao_procede(banco, C2, "Outra observação")
        [outro] = _fila_de_validacao(banco)["temas"]
        assert _decidir(banco, outro["id"], {"decisao": "MANTER_REGRA"}).status_code == 200
        assert _tema_no_banco(banco, outro["id"])["decisao"] == "MANTER_REGRA"
        assert [v["versao"] for v in banco.tabelas["cm_memoria_versao"] if v["vigente"]] == ["1.1"]


# ═══════════════════════════════════════════════════════════════════════════
# 4. Dicionário: a Validação confirma ou rejeita o termo que a IA propôs
# ═══════════════════════════════════════════════════════════════════════════

# O item da conta seguinte: a marca não lembra o termo, só o dicionário liga.
POSIFLUSH = {"codigo": "70000010", "descricao": "POSIFLUSH SF 0,9% 10ML"}
PRESCRITO = "Seringa pronta de soro 10 ml"


def _proposta_da_ia(banco: _Banco) -> None:
    banco.tabelas["cm_item_dicionario"].append(
        {
            "id": "dc-ia",
            "termo": "SERINGA PRONTA",
            "codigo_conta": POSIFLUSH["codigo"],
            "descricao_conta": POSIFLUSH["descricao"],
            "origem": "IA",
            "situacao": "PROPOSTO",
        }
    )


class TestDicionario:
    def test_proposta_da_ia_confirmada_passa_a_casar_na_conta_seguinte(self):
        banco = _cenario()
        _proposta_da_ia(banco)

        [tema] = _fila_de_validacao(banco)["temas"]
        assert tema["tipo"] == "DICIONARIO"
        assert tema["dicionario"] == {
            "termo": "SERINGA PRONTA",
            "codigo_conta": POSIFLUSH["codigo"],
            "descricao_conta": POSIFLUSH["descricao"],
        }

        resposta = _decidir(banco, tema["id"], {"decisao": "CONFIRMAR"})

        assert resposta.status_code == 200, resposta.text
        [termo] = banco.tabelas["cm_item_dicionario"]
        assert termo["situacao"] == "CONFIRMADO"
        casamento = casar(PRESCRITO, [POSIFLUSH], dicionario_do_banco(banco))
        assert (casamento.como, casamento.itens) == ("DICIONARIO", [POSIFLUSH])
        assert _fila_de_validacao(banco)["temas"] == []

    def test_proposta_rejeitada_nao_casa_e_nao_volta_para_a_fila(self):
        banco = _cenario()
        _proposta_da_ia(banco)
        [tema] = _fila_de_validacao(banco)["temas"]

        assert _decidir(banco, tema["id"], {"decisao": "REJEITAR"}).status_code == 200

        # Como a rejeição pela tela Operadoras (issue #1135): o termo fica
        # decidido e sem código, para a IA não ser perguntada de novo.
        [termo] = banco.tabelas["cm_item_dicionario"]
        assert (termo["situacao"], termo["codigo_conta"], termo["autor_id"]) == ("CONFIRMADO", None, "G1")
        assert casar(PRESCRITO, [POSIFLUSH], dicionario_do_banco(banco)).como == "NENHUM"
        assert _fila_de_validacao(banco)["temas"] == []

    def test_termo_da_carga_da_gestao_casa_como_antes(self):
        """A carga do dicionário grava PROPOSTO quando o CSV não diz CONFIRMADO,
        e esses termos sempre casaram: só a proposta da IA vai para a Validação."""
        banco = _cenario()
        banco.tabelas["cm_item_dicionario"].append(
            {
                "id": "dc-g",
                "termo": "SERINGA PRONTA",
                "codigo_conta": "70000010",
                "origem": "GESTAO",
                "situacao": "PROPOSTO",
            }
        )

        assert casar(PRESCRITO, [POSIFLUSH], dicionario_do_banco(banco)).como == "DICIONARIO"
        assert _fila_de_validacao(banco)["temas"] == []


# ═══════════════════════════════════════════════════════════════════════════
# 5. A fila inteira: a ordem e os três números do topo
# ═══════════════════════════════════════════════════════════════════════════


def _os_quatro_tipos(banco: _Banco) -> None:
    """Regra pendente em 3 contas (R$ 250,50), cateter bloqueado em 2 (R$ 66),
    Não procede em 1 (R$ 45) e uma proposta de dicionário (sem R$)."""
    validar = {C1: 120.0, C2: 80.0, C3: 50.5}
    for conta_id, valor in validar.items():
        linhas = [_linha_do_guia("VALIDAR", "70000010", valor, REGRA_PENDENTE)]
        if conta_id != C3:
            linhas.append(_linha_do_guia("INCLUIR", CATETER, 33.0, REGRA_VIGENTE, descricao="CATETER"))
        if conta_id == C2:
            linhas.append(_linha_do_guia("INCLUIR", "90030001", 45.0, REGRA_VIGENTE, descricao="CLEXANE"))
        _gravar(banco, conta_id, *linhas)
    for linha in list(banco.tabelas["cm_guia_linha"]):
        if linha["codigo"] == CATETER:
            _marcar(banco, linha["conta_id"], linha["id"], {"estado": "BLOQUEADO"})
        elif linha["codigo"] == "90030001":
            _marcar(banco, linha["conta_id"], linha["id"], {"estado": "NAO_PROCEDE", "motivo": "SEM_EVIDENCIA"})
    _proposta_da_ia(banco)


class TestAFila:
    def test_temas_do_maior_rs_em_jogo_para_o_menor_e_os_numeros_do_topo_batem(self):
        banco = _cenario()
        _os_quatro_tipos(banco)

        fila = _fila_de_validacao(banco)

        assert [(t["tipo"], t["valor"], t["contas"]) for t in fila["temas"]] == [
            ("REGRA_PENDENTE", 250.5, 3),
            ("BLOQUEADO", 66.0, 2),
            ("OBSERVACAO", 45.0, 1),
            ("DICIONARIO", 0.0, 0),
        ]
        assert fila["numeros"] == {"aguardando_decisao": 4, "contas_afetadas": 3, "valor_em_jogo": 361.5}

    @pytest.mark.parametrize("quem", ["faturista", "coordenadora"])
    def test_quem_nao_decide_na_validacao_recebe_403_em_toda_rota(self, quem):
        banco = _cenario()
        _os_quatro_tipos(banco)
        temas = {t["tipo"]: t["id"] for t in _fila_de_validacao(banco)["temas"]}
        cliente = _cliente(banco, quem)

        respostas = [
            cliente.get("/api/contas-medicas/validacao"),
            cliente.post(
                f"/api/contas-medicas/validacao/temas/{temas['REGRA_PENDENTE']}/decisao",
                json={"decisao": "VALIDAR_REGRA"},
            ),
            cliente.post(f"/api/contas-medicas/validacao/temas/{temas['BLOQUEADO']}/cadastro"),
            cliente.post(f"/api/contas-medicas/validacao/temas/{temas['OBSERVACAO']}/leitura"),
        ]

        assert [r.status_code for r in respostas] == [403, 403, 403, 403]
        assert {t["estado"] for t in banco.tabelas["cm_validacao_tema"]} == {"ABERTO"}


# ═══════════════════════════════════════════════════════════════════════════
# 6. O texto do Produto no Kit de conhecimento
# ═══════════════════════════════════════════════════════════════════════════

RAIZ_DO_APP = Path(__file__).resolve().parents[2]
KIT = RAIZ_DO_APP / "backend" / "app" / "conhecimento" / "contas-medicas.md"


def _secao(titulo: str) -> str:
    return KIT.read_text(encoding="utf-8").split(f"## {titulo}")[1].split("\n## ")[0]


class TestOKitDescreveAValidacao:
    """O Assistente de Tecnologia responde Demanda com este texto: sem a fila
    nele, a pergunta "por que a conta concluída voltou para mim?" fica sem
    resposta."""

    def test_a_secao_da_validacao_descreve_a_fila_as_decisoes_e_o_retorno(self):
        validacao = _secao("A Validação")

        for trecho in (
            "decidir na validação",
            "aguardando decisão",
            "contas afetadas",
            "R$ em jogo",
            "Validar regra",
            "Deixar pendente",
            "Enviar ao cadastro",
            "Descartar",
            "Manter a regra",
            "Editar a regra",
            "Responder ao time",
            "dicionário",
            "Retorno",
            "versão nova",
            "quem decide é a pessoa",
        ):
            assert trecho in validacao, trecho

    def test_o_que_ja_esta_no_ar_inclui_a_validacao(self):
        assert "a fila de Validação" in _secao("O que já está no ar")


# ═══════════════════════════════════════════════════════════════════════════
# 7. Tipografia
# ═══════════════════════════════════════════════════════════════════════════

ARQUIVOS_DA_FATIA = [
    RAIZ_DO_APP / "backend/app/services/contas_medicas/validacao.py",
    RAIZ_DO_APP / "backend/app/routers/contas_medicas_validacao.py",
    RAIZ_DO_APP / "backend/app/prompts/contas_medicas_observacao.md",
    KIT,
    RAIZ_DO_APP / "frontend/src/app/contas-medicas/validacao/page.tsx",
    RAIZ_DO_APP / "frontend/src/components/contas-medicas/CartaoDeTema.tsx",
    RAIZ_DO_APP / "frontend/src/components/contas-medicas/LinkParaValidacao.tsx",
    RAIZ_DO_APP / "frontend/src/lib/contas-medicas/validacao.ts",
    Path(__file__),
]


@pytest.mark.parametrize("arquivo", ARQUIVOS_DA_FATIA, ids=lambda a: a.name)
def test_sem_travessao_nem_meia_risca(arquivo):
    texto = arquivo.read_text(encoding="utf-8")
    assert chr(0x2014) not in texto
    assert chr(0x2013) not in texto


def test_a_leitura_da_ia_sai_sem_travessao(provedor):
    """O texto da IA vai para a tela: o sanitizador troca o travessão que vier."""
    provedor.leitura = {**LEITURA, "leitura": f"A regra {chr(0x2014)} como está {chr(0x2013)} não trata do caso."}
    banco = _cenario()
    _nao_procede(banco, C1, "Na ALFA o Clexane vem dentro do pacote")
    [tema] = _fila_de_validacao(banco)["temas"]

    leitura = _ler(banco, tema["id"]).json()["leitura_ia"]

    assert chr(0x2014) not in leitura and chr(0x2013) not in leitura
    assert "A regra, como está, não trata do caso." in leitura
