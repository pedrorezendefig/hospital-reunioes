"""A Conferência da coordenação de Contas médicas (issue #1143, PRD #1129, adendo v1.1).

A gestão cadastra os cenários (o procedimento que dispara e os insumos a
conferir) escrevendo em linguagem comum: a IA preenche os campos e a pessoa
confere os códigos contra a tabela. O Passo C roda depois do Passo A: a IA diz
em que data e setor cada cenário ativo da operadora ocorreu, o código confere a
evidência e, quando falta insumo na conta, cria o lembrete com o valor pela
tabela. A coordenadora marca Incluído ou Não se aplica. A faturista não vê
cenário nem lembrete, e o guia, a nota e a produção dela não mudam.

Tudo pelo caminho de verdade, com os dublês do processamento (#1124): a rota de
envio, o job da fila, o adaptador de IA com o transporte HTTP trocado e as
rotas da tela. O provedor responde pelo schema pedido.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from openai import OpenAI
from test_contas_medicas_processamento import (
    PESSOAS,
    _Banco,
    _cenario,
    _Consulta,
    _conta,
    _enviar,
    _Extrator,
    _item_de_tabela,
    _OpenRouter,
    _pessoa,
    _prontuario,
    _rodar_o_job,
)

from app.dependencies import get_current_user, get_supabase_client
from app.limiter import limiter
from app.routers import contas_medicas_coordenacao as coordenacao_router
from app.routers import contas_medicas_envio as envio_router
from app.routers import contas_medicas_guia as guia_router
from app.routers import contas_medicas_painel as painel_router
from app.services.contas_medicas import envio as envio_service
from app.services.contas_medicas import ia, processamento

ROTA = "/api/contas-medicas/coordenacao"

# O schema que o cadastro pede à IA.
PROPOSTA = "CenarioProposto"


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


@pytest.fixture(autouse=True)
def _extrator(monkeypatch) -> _Extrator:
    duble = _Extrator()
    monkeypatch.setattr(envio_service, "extrair_paginas", duble)
    monkeypatch.setattr(processamento, "extrair_paginas", duble)
    return duble


@pytest.fixture(autouse=True)
def openrouter(monkeypatch) -> _OpenRouter:
    """O provedor do teste na fronteira HTTP: nada chega ao OpenRouter."""
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


# ═══════════════════════════════════════════════════════════════════════════
# O dublê do banco: o do processamento, com o recorte das leituras paginadas
# ═══════════════════════════════════════════════════════════════════════════


class _ConsultaComRecorte(_Consulta):
    def range(self, inicio, fim):
        self._recorte = (inicio, fim)
        return self

    def _executar(self):
        resposta = super()._executar()
        recorte = getattr(self, "_recorte", None)
        if recorte is not None:
            resposta.data = resposta.data[recorte[0] : recorte[1] + 1]
        return resposta


class _BancoDaCoordenacao(_Banco):
    def table(self, nome: str):
        return _ConsultaComRecorte(self, nome)


QUEM = {
    **PESSOAS,
    "coordenadora": _pessoa("CO", "coordenadora"),
    "diretoria": _pessoa("DM", "diretoria_medica"),
}


def _banco() -> _BancoDaCoordenacao:
    """O par sintético do processamento (operadora ALFA, agulha 70000001 na
    tabela de materiais e lançada na conta em 03/10), com a coordenadora e a
    diretoria."""
    banco = _BancoDaCoordenacao(_cenario().tabelas)
    banco.tabelas["participantes"] = list(QUEM.values())
    return banco


def _cliente(banco: _Banco, quem: str) -> TestClient:
    pessoa = QUEM[quem]
    app = FastAPI()
    app.state.limiter = limiter
    for router in (coordenacao_router, envio_router, guia_router, painel_router):
        app.include_router(router.router, prefix="/api")

    async def _usuario() -> dict[str, Any]:
        return {"id": pessoa["auth_user_id"], "email": pessoa["email"], "metadata": {}}

    app.dependency_overrides[get_current_user] = _usuario
    app.dependency_overrides[get_supabase_client] = lambda: banco
    return TestClient(app)


# ═══════════════════════════════════════════════════════════════════════════
# 1. O cadastro do cenário
# ═══════════════════════════════════════════════════════════════════════════

TEXTO_DO_CENARIO = (
    "Sondagem vesical ou cirurgia com lidocaína gel: conferir lidocaína gel, a agulha e o coletor de urina, um de cada."
)

PROPOSTA_DA_IA = {
    "nome": "Lidocaína gel em sondagem ou cirurgia",
    "operadora": None,
    "gatilho_texto": "Cateterismo vesical, ou cirurgia em que foi usada lidocaína gel",
    "orientacao": "Confira se a lidocaína gel e o coletor foram lançados no dia.",
    "insumos": [
        {"codigo": "70000001", "descricao": "AGULHA HIPODERMICA", "quantidade": 1},
        {"codigo": "79999999", "descricao": "COLETOR DE URINA", "quantidade": 1},
    ],
}


def _cenario_enviado(**campos: Any) -> dict[str, Any]:
    return {
        "nome": "Lidocaína gel em sondagem ou cirurgia",
        "operadora_sigla": None,
        "gatilho_texto": "Cateterismo vesical, ou cirurgia em que foi usada lidocaína gel",
        "orientacao": "Confira se a lidocaína gel e o coletor foram lançados no dia.",
        "ativo": True,
        "insumos": [
            {"codigo": "70000001", "descricao": "AGULHA HIPODERMICA", "quantidade": 1},
            {"codigo": "79999999", "descricao": "COLETOR DE URINA", "quantidade": 1},
        ],
        **campos,
    }


class TestCadastroDoCenario:
    def test_a_ia_preenche_os_campos_e_o_codigo_que_nao_esta_na_tabela_e_apontado(self, openrouter):
        openrouter.respostas[PROPOSTA] = PROPOSTA_DA_IA
        banco = _banco()

        resposta = _cliente(banco, "gestao").post(f"{ROTA}/cenarios/proposta", json={"texto": TEXTO_DO_CENARIO})

        assert resposta.status_code == 200, resposta.text
        corpo = resposta.json()
        assert corpo["campos"]["nome"] == "Lidocaína gel em sondagem ou cirurgia"
        assert corpo["campos"]["gatilho_texto"] == "Cateterismo vesical, ou cirurgia em que foi usada lidocaína gel"
        assert [(i["codigo"], i["na_tabela"]) for i in corpo["campos"]["insumos"]] == [
            ("70000001", True),
            ("79999999", False),
        ]
        assert corpo["codigos_fora_da_tabela"] == ["79999999"]
        # O texto da pessoa foi para a IA; nada foi gravado antes de ela conferir.
        (pedido,) = [c for c in openrouter.corpos if c["response_format"]["json_schema"]["name"] == PROPOSTA]
        assert TEXTO_DO_CENARIO in json.dumps(pedido["messages"], ensure_ascii=False)
        assert banco.tabelas.get("cm_cenario", []) == []

    def test_salvar_cria_o_cen_001_com_os_insumos_e_o_autor_e_aponta_o_codigo_fora_da_tabela(self):
        banco = _banco()

        resposta = _cliente(banco, "gestao").post(f"{ROTA}/cenarios", json=_cenario_enviado())

        assert resposta.status_code == 201, resposta.text
        assert resposta.json()["codigos_fora_da_tabela"] == ["79999999"]
        (cenario,) = banco.tabelas["cm_cenario"]
        assert (cenario["codigo"], cenario["autor_id"], cenario["ativo"], cenario["operadora_id"]) == (
            "CEN-001",
            "G1",
            True,
            None,
        )
        insumos = sorted((i["codigo"], i["quantidade"]) for i in banco.tabelas["cm_cenario_item"])
        assert insumos == [("70000001", 1), ("79999999", 1)]
        # A criação fica no registro, com quem e quando.
        (registro,) = [r for r in banco.tabelas["cm_registro"] if r["entidade"] == "cm_cenario"]
        assert (registro["autor_id"], registro["entidade_id"], registro["antes_json"]) == ("G1", cenario["id"], None)

        # O segundo é o CEN-002, na lista de quem cadastra.
        _cliente(banco, "gestao").post(f"{ROTA}/cenarios", json=_cenario_enviado(nome="Outro cenário"))
        lista = _cliente(banco, "gestao").get(f"{ROTA}/cenarios").json()["cenarios"]
        assert [c["codigo"] for c in lista] == ["CEN-001", "CEN-002"]

    @pytest.mark.parametrize("quem", ["coordenadora", "faturista"])
    def test_sem_incluir_regra_operacional_nao_cadastra_nem_pede_a_ia(self, quem, openrouter):
        openrouter.respostas[PROPOSTA] = PROPOSTA_DA_IA
        banco = _banco()
        cliente = _cliente(banco, quem)

        assert cliente.post(f"{ROTA}/cenarios", json=_cenario_enviado()).status_code == 403
        assert cliente.post(f"{ROTA}/cenarios/proposta", json={"texto": TEXTO_DO_CENARIO}).status_code == 403
        assert banco.tabelas.get("cm_cenario", []) == []
        assert openrouter.requisicoes == 0


# ═══════════════════════════════════════════════════════════════════════════
# 2. O Passo C no pipeline
# ═══════════════════════════════════════════════════════════════════════════

PASSO_C = "OcorrenciasDosCenarios"

# A página 2 do prontuário sintético (admissão no CTI) diz isto, palavra por palavra.
TRECHO_DA_ADMISSAO = "Chegou com acesso venoso periférico em membro superior esquerdo"
# E não diz isto em página nenhuma.
TRECHO_INVENTADO = "Sondagem vesical de demora com lidocaína gel e coletor fechado"


def _cenario_no_banco(banco: _Banco, codigo: str, insumos: list[tuple[str, str, float]], **campos: Any) -> dict:
    cenario = {
        "id": f"cn-{codigo}",
        "codigo": codigo,
        "nome": f"Cenário {codigo}",
        "operadora_id": None,
        "gatilho_texto": f"Quando o {codigo} acontece",
        "orientacao": f"Orientação do {codigo}",
        "ativo": True,
        "autor_id": "G1",
        "criado_em": "2026-10-01T10:00:00+00:00",
        **campos,
    }
    banco.tabelas.setdefault("cm_cenario", []).append(cenario)
    banco.tabelas.setdefault("cm_cenario_item", []).extend(
        {"id": f"ci-{codigo}-{n}", "cenario_id": cenario["id"], "codigo": c, "descricao": d, "quantidade": q}
        for n, (c, d, q) in enumerate(insumos)
    )
    return cenario


def _ocorrencia(cenario: str, trecho: str = TRECHO_DA_ADMISSAO, data: str = "2026-10-03") -> dict[str, Any]:
    return {"cenario_id": cenario, "data": data, "setor": "CTI ADULTO", "evidencia": {"pagina": 2, "trecho": trecho}}


def _banco_com_cenarios() -> _BancoDaCoordenacao:
    """Três cenários ativos que valem para todas as operadoras, um inativo e um
    de outra operadora. A conta 48811 lança a agulha (70000001) em 03/10 e não
    lança o equipo (70000002), que a tabela de materiais da ALFA dá a 12,50."""
    banco = _banco()
    banco.tabelas["cm_tabela_preco_item"].append(
        _item_de_tabela("it-equipo", "tb-mat", "70000002", "EQUIPO MACROGOTAS", {"comum": 12.5, "carioca": 13.0}, {})
    )
    banco.tabelas["cm_operadora"].append({"id": "op-beta", "sigla": "BETA", "nome": "Beta Saúde", "situacao": "PRONTA"})
    _cenario_no_banco(
        banco,
        "CEN-001",
        [("70000001", "AGULHA HIPODERMICA", 10), ("70000002", "EQUIPO MACROGOTAS", 2)],
        nome="Sondagem vesical com equipo",
    )
    _cenario_no_banco(banco, "CEN-002", [("70000001", "AGULHA HIPODERMICA", 1)], nome="Só a agulha")
    _cenario_no_banco(banco, "CEN-003", [("70000002", "EQUIPO MACROGOTAS", 1)], nome="Evidência inventada")
    _cenario_no_banco(banco, "CEN-004", [("70000002", "EQUIPO", 1)], nome="Desligado", ativo=False)
    _cenario_no_banco(banco, "CEN-005", [("70000002", "EQUIPO", 1)], nome="Só da Beta", operadora_id="op-beta")
    return banco


def _analisar(banco: _Banco, openrouter: _OpenRouter, *ocorrencias: dict[str, Any]) -> dict:
    openrouter.respostas[PASSO_C] = {"ocorrencias": list(ocorrencias)}
    _enviar(banco, _conta(), _prontuario())
    _rodar_o_job(banco)
    (conta,) = banco.tabelas["cm_conta"]
    assert conta["situacao"] == "A_FAZER", conta.get("erro_motivo")
    return conta


def _conferencia(banco: _Banco, quem: str = "coordenadora") -> dict:
    resposta = _cliente(banco, quem).get(ROTA)
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


def _lembretes_por_cenario(corpo: dict) -> dict[str, dict]:
    return {lembrete["cenario"]["codigo"]: lembrete for conta in corpo["contas"] for lembrete in conta["lembretes"]}


class TestPassoC:
    def test_so_o_insumo_que_falta_vira_lembrete_com_o_valor_da_tabela(self, openrouter):
        banco = _banco_com_cenarios()

        _analisar(
            banco, openrouter, _ocorrencia("CEN-001"), _ocorrencia("CEN-002"), _ocorrencia("CEN-003", TRECHO_INVENTADO)
        )

        corpo = _conferencia(banco)
        lembretes = _lembretes_por_cenario(corpo)
        # A agulha já está na conta no período: o CEN-002 não vira lembrete, e
        # no CEN-001 só o equipo falta, 2 a R$ 12,50 pela tabela da ALFA.
        assert set(lembretes) == {"CEN-001", "CEN-003"}
        sondagem = lembretes["CEN-001"]
        assert [(i["codigo"], i["quantidade"], i["preco_tabela"], i["valor"]) for i in sondagem["insumos"]] == [
            ("70000002", 2, 12.5, 25.0)
        ]
        assert (sondagem["data"], sondagem["setor"], sondagem["evidencia_pagina"]) == ("2026-10-03", "CTI ADULTO", 2)
        assert sondagem["evidencia_trecho"] == TRECHO_DA_ADMISSAO
        assert sondagem["etiquetas"] == []
        # O trecho que não está na página citada nem na vizinha: lembrete com a etiqueta.
        assert lembretes["CEN-003"]["etiquetas"] == ["conferir evidência"]
        # Os três números do topo e a conta com o atendimento e a operadora.
        assert corpo["numeros"] == {"lembretes_abertos": 2, "contas_com_lembrete": 1, "valor_a_conferir": 37.5}
        (conta,) = corpo["contas"]
        assert (conta["numero_atendimento"], conta["operadora"], conta["situacao"]) == ("31245", "ALFA", "A_FAZER")

    def test_a_ia_recebe_so_os_cenarios_ativos_da_operadora_e_nada_disso_entra_no_passo_b(self, openrouter):
        banco = _banco_com_cenarios()

        _analisar(banco, openrouter)

        (pedido,) = [c for c in openrouter.corpos if c["response_format"]["json_schema"]["name"] == PASSO_C]
        enviado = json.dumps(pedido["messages"], ensure_ascii=False)
        assert all(codigo in enviado for codigo in ("CEN-001", "CEN-002", "CEN-003"))
        assert "CEN-004" not in enviado and "CEN-005" not in enviado
        # O Passo C vem depois do Passo A, e o Passo B não recebe cenário nenhum.
        formatos = openrouter.formatos
        assert formatos.index("EventosDoProntuario") < formatos.index(PASSO_C)
        (comparacao,) = [
            c for c in openrouter.corpos if c["response_format"]["json_schema"]["name"] == "LinhasDaComparacao"
        ]
        assert "CEN-" not in json.dumps(comparacao["messages"], ensure_ascii=False)

    def test_sem_cenario_ativo_a_ia_nao_e_chamada(self, openrouter):
        banco = _banco()

        _analisar(banco, openrouter)

        assert PASSO_C not in openrouter.formatos

    def test_a_ia_fora_do_ar_no_passo_c_nao_derruba_a_conta_da_faturista(self, openrouter):
        banco = _banco_com_cenarios()
        openrouter.fora_do_formato_em = {PASSO_C}

        conta = _analisar(banco, openrouter, _ocorrencia("CEN-001"))

        assert conta["situacao"] == "A_FAZER"
        assert banco.tabelas.get("cm_lembrete", []) == []


# ═══════════════════════════════════════════════════════════════════════════
# 3. A faturista não vê cenário nem lembrete
# ═══════════════════════════════════════════════════════════════════════════

UM_UUID = "00000000-0000-4000-8000-000000000001"


def _chaves(valor: Any) -> set[str]:
    """Todas as chaves de um JSON, em qualquer profundidade."""
    if isinstance(valor, dict):
        return set(valor) | {chave for filho in valor.values() for chave in _chaves(filho)}
    if isinstance(valor, list):
        return {chave for filho in valor for chave in _chaves(filho)}
    return set()


class TestFaturistaNaoVe:
    def test_as_rotas_de_cenario_e_de_lembrete_devolvem_403_sem_dado_nenhum(self, openrouter):
        banco = _banco_com_cenarios()
        _analisar(banco, openrouter, _ocorrencia("CEN-001"))
        (lembrete,) = banco.tabelas["cm_lembrete"]
        cliente = _cliente(banco, "faturista")

        respostas = [
            cliente.get(ROTA),
            cliente.get(f"{ROTA}/cenarios"),
            cliente.post(f"{ROTA}/cenarios/proposta", json={"texto": TEXTO_DO_CENARIO}),
            cliente.post(f"{ROTA}/cenarios", json=_cenario_enviado()),
            cliente.put(f"{ROTA}/cenarios/{UM_UUID}", json=_cenario_enviado()),
            cliente.post(f"{ROTA}/lembretes/{lembrete['id']}/marcacao", json={"estado": "INCLUIDO"}),
        ]

        assert [r.status_code for r in respostas] == [403] * 6
        for resposta in respostas:
            assert "CEN-" not in resposta.text and "Sondagem" not in resposta.text
        assert banco.tabelas["cm_lembrete"][0]["estado"] == "ABERTO"

    def test_o_guia_da_conta_com_lembrete_nao_traz_nenhum_campo_de_cenario(self, openrouter):
        banco = _banco_com_cenarios()
        conta = _analisar(banco, openrouter, _ocorrencia("CEN-001"), _ocorrencia("CEN-003", TRECHO_INVENTADO))
        assert len(banco.tabelas["cm_lembrete"]) == 2, "a conta precisa ter lembrete para o teste valer"

        resposta = _cliente(banco, "faturista").get(f"/api/contas-medicas/contas/{conta['id']}/guia")

        assert resposta.status_code == 200, resposta.text
        assert not {c for c in _chaves(resposta.json()) if "cenario" in c or "lembrete" in c or "coordena" in c}
        for vestigio in ("CEN-001", "CEN-003", "Sondagem vesical com equipo", "Orientação do CEN", "Quando o CEN"):
            assert vestigio not in resposta.text
        # O tempo das etapas vai para a conta dela: são as etapas de antes do Passo C.
        assert set(banco.conta(conta["id"])["faltantes"]["tempos_por_etapa_s"]) == {
            "texto_da_conta",
            "leitura_da_conta",
            "texto_do_prontuario",
            "leitura_do_prontuario",
            "dicionario",
            "conferencia",
            "passo_a",
            "conferencia_com_eventos",
            "passo_b",
            "gravacao",
            "total",
        }


# ═══════════════════════════════════════════════════════════════════════════
# 4. Incluído e Não se aplica
# ═══════════════════════════════════════════════════════════════════════════


class TestMarcacao:
    def test_incluido_e_nao_se_aplica_mudam_o_estado_com_autor_data_e_observacao(self, openrouter):
        banco = _banco_com_cenarios()
        _analisar(banco, openrouter, _ocorrencia("CEN-001"), _ocorrencia("CEN-003", TRECHO_INVENTADO))
        lembretes = _lembretes_por_cenario(_conferencia(banco))
        cliente = _cliente(banco, "coordenadora")

        incluido = cliente.post(
            f"{ROTA}/lembretes/{lembretes['CEN-001']['id']}/marcacao",
            json={"estado": "INCLUIDO", "observacao": "Equipo lançado no MV."},
        )
        nao_se_aplica = cliente.post(
            f"{ROTA}/lembretes/{lembretes['CEN-003']['id']}/marcacao", json={"estado": "NAO_SE_APLICA"}
        )

        assert (incluido.status_code, nao_se_aplica.status_code) == (200, 200), incluido.text
        por_id = {lembrete["id"]: lembrete for lembrete in banco.tabelas["cm_lembrete"]}
        sondagem, inventado = por_id[lembretes["CEN-001"]["id"]], por_id[lembretes["CEN-003"]["id"]]
        assert (sondagem["estado"], sondagem["marcado_por"], sondagem["observacao"]) == (
            "INCLUIDO",
            "CO",
            "Equipo lançado no MV.",
        )
        # Sem observação, a etiqueta da evidência que o lembrete aberto guardava sai.
        assert (inventado["estado"], inventado["marcado_por"], inventado["observacao"]) == ("NAO_SE_APLICA", "CO", None)
        assert sondagem["marcado_em"] and inventado["marcado_em"]
        # Marcados, saem da lista dos abertos; marcar de novo é conflito.
        assert _conferencia(banco)["numeros"] == {
            "lembretes_abertos": 0,
            "contas_com_lembrete": 0,
            "valor_a_conferir": 0,
        }
        de_novo = cliente.post(
            f"{ROTA}/lembretes/{lembretes['CEN-001']['id']}/marcacao", json={"estado": "NAO_SE_APLICA"}
        )
        assert de_novo.status_code == 409
        assert por_id[lembretes["CEN-001"]["id"]]["estado"] == "INCLUIDO"


KIT = Path(__file__).resolve().parents[1] / "app" / "conhecimento" / "contas-medicas.md"
