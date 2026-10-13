"""O Passo B de Contas médicas: a comparação com a memória e a conferência das
linhas da IA (issue #1135, PRD #1128, ADR 0070).

A IA compara os eventos do prontuário com a conta, aplicando a memória da
operadora, e devolve linhas do Guia sem valor em reais. Nenhuma delas chega à
faturista sem as conferências do código: regra existe, regra vigente, evidência
na página, código na tabela, teto recalculado, sem repetir o que o código já
apontou e dentro do período.

Tudo pelo caminho de verdade, com os dublês do processamento (#1124): a rota de
envio, o job da fila, o adaptador de IA com o transporte HTTP trocado e a rota
do Guia. O provedor responde pelo schema pedido: o Passo A devolve eventos, o
Passo B devolve as linhas que cada teste escolhe.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from openai import OpenAI
from test_contas_medicas_processamento import (
    EVENTOS_DA_IA,
    PARAMETROS,
    PASSO_B,
    _Banco,
    _cenario,
    _conta,
    _enviar,
    _Extrator,
    _guia,
    _item_de_tabela,
    _linhas_do_guia,
    _OpenRouter,
    _prontuario,
    _regra,
    _rodar_o_job,
)

from app.limiter import limiter
from app.services.contas_medicas import envio as envio_service
from app.services.contas_medicas import ia, processamento


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


# A página 2 do prontuário sintético (admissão no CTI) diz isto, palavra por palavra.
TRECHO_DA_ADMISSAO = "Chegou com acesso venoso periférico em membro superior esquerdo"


# O teto da fralda no CTI. O par sintético tem 4 diárias de CTI pagas (de 02/10
# 22:40 à alta em 06/10 15:20; o guia do código retira a 5ª lançada a mais do
# pacote): a devida é 4 × 6 = 24.
TETO_DA_FRALDA = {"codigo": "70000050", "cti": 6}
DEVIDA_DA_FRALDA = 24


def _cenario_do_passo_b() -> _Banco:
    """O par sintético do processamento, com as regras de insumo (uma
    pendente), o teto da fralda e a tabela de materiais dos itens da IA."""
    banco = _cenario()
    pendente = {**_regra("ALFA-INS-05"), "status": "PENDENTE"}
    banco.tabelas["cm_regra"] += [_regra("ALFA-INS-03"), _regra("ALFA-INS-04"), pendente]
    (versao,) = banco.tabelas["cm_memoria_versao"]
    versao["parametros_json"] = {**PARAMETROS, "tetos_por_dia": {"fralda": TETO_DA_FRALDA}}
    banco.tabelas["cm_tabela_preco_item"] += [
        _item_de_tabela("it-equipo", "tb-mat", "70000002", "EQUIPO MACROGOTAS", {"comum": 12.5, "carioca": 13.0}, {}),
        _item_de_tabela("it-curativo", "tb-mat", "70000003", "CURATIVO HIDROCOLOIDE", {"comum": 5.0}, {}),
        _item_de_tabela("it-cateter", "tb-mat", "70000004", "CATETER NASAL", {"comum": 3.0}, {}),
        _item_de_tabela("it-fralda", "tb-mat", "70000050", "FRALDA GERIATRICA", {"comum": 2.0}, {}),
    ]
    return banco


def _linha_da_ia(**campos: Any) -> dict[str, Any]:
    """Uma linha no formato do Anexo B: a boa, com o que o teste trocar."""
    return {
        "acao": "INCLUIR",
        "data": "2026-10-03",
        "data_fim": "2026-10-03",
        "setor": "CTI ADULTO",
        "codigo": "70000002",
        "descricao": "EQUIPO MACROGOTAS",
        "quantidade_lancada": 0,
        "quantidade_devida": 1,
        "regra_id": "ALFA-INS-03",
        "motivo": "Acesso venoso periférico na admissão e sem equipo na conta.",
        "evidencia": {"pagina": 2, "trecho": TRECHO_DA_ADMISSAO},
        "nivel_evidencia": "REGISTRADO",
        "causa_raiz": "DISPENSACAO",
        "confianca": "ALTA",
        **campos,
    }


def _analisar(banco: _Banco, openrouter, *linhas: dict[str, Any]) -> tuple[dict, list[dict]]:
    """Envia o par, roda a fila com o Passo B respondendo `linhas` e devolve a
    conta gravada e as linhas do Guia pela rota."""
    openrouter.comparacao = {"linhas": list(linhas), "resumo": "Conta comparada com a memória."}
    _enviar(banco, _conta(), _prontuario())
    _rodar_o_job(banco)
    (conta,) = banco.tabelas["cm_conta"]
    assert conta["situacao"] == "A_FAZER", conta.get("erro_motivo")
    return conta, _linhas_do_guia(_guia(banco, conta["id"]))


class TestConferenciaDasLinhasDaIA:
    def test_a_linha_boa_entra_no_guia_com_origem_ia_e_o_valor_pela_tabela(self, openrouter):
        _, linhas = _analisar(_cenario_do_passo_b(), openrouter, _linha_da_ia())

        (equipo,) = [linha for linha in linhas if linha["codigo"] == "70000002"]
        assert (equipo["origem"], equipo["acao"], equipo["regra_codigo"]) == ("IA", "INCLUIR", "ALFA-INS-03")
        assert (equipo["preco_tabela"], equipo["valor_diferenca"], equipo["confianca"]) == (12.5, 12.5, "ALTA")
        assert {linha["origem"] for linha in linhas if linha["codigo"] != "70000002"} == {"CODIGO"}

    def test_cada_defeito_da_ia_recebe_a_conferencia_do_codigo(self, openrouter):
        banco = _cenario_do_passo_b()
        conta, linhas = _analisar(
            banco,
            openrouter,
            _linha_da_ia(),
            _linha_da_ia(codigo="70000005", descricao="LUVA DE PROCEDIMENTO", regra_id="ALFA-INS-99"),
            _linha_da_ia(
                codigo="70000003", descricao="CURATIVO HIDROCOLOIDE", quantidade_devida=2, regra_id="ALFA-INS-05"
            ),
            _linha_da_ia(
                codigo="70000004",
                descricao="CATETER NASAL",
                evidencia={"pagina": 2, "trecho": "Paciente recebeu curativo de hidrocoloide no sacro"},
            ),
            _linha_da_ia(codigo="70000077", descricao="SERINGA 20ML"),
            _linha_da_ia(
                codigo="70000050",
                descricao="FRALDA GERIATRICA",
                data_fim="2026-10-05",
                quantidade_devida=10,
                regra_id="ALFA-INS-04",
                nivel_evidencia="POR_REGRA",
            ),
            _linha_da_ia(
                codigo="98005497",
                descricao="PACOTE COLECISTECTOMIA",
                data="2026-10-04",
                data_fim="2026-10-04",
                setor=None,
                regra_id="ALFA-PAC-03",
            ),
            _linha_da_ia(data="2026-10-09", data_fim="2026-10-09"),
        )
        da_ia = {linha["codigo"]: linha for linha in linhas if linha["origem"] == "IA"}

        # A boa entra; a do período errado não, mesmo com o mesmo código.
        assert [linha["data"] for linha in linhas if linha["codigo"] == "70000002"] == ["2026-10-03"]
        assert da_ia["70000002"]["acao"] == "INCLUIR"
        # Regra que a memória não tem: a linha cai.
        assert "70000005" not in {linha["codigo"] for linha in linhas}
        # Regra pendente: Validar, nunca ordem.
        assert da_ia["70000003"]["acao"] == "VALIDAR"
        assert da_ia["70000003"]["motivo"].startswith("Regra ALFA-INS-05 pendente.")
        # Evidência que não está na página nem na vizinha: confiança baixa (a tela mostra "conferir evidência").
        assert (da_ia["70000004"]["confianca"], da_ia["70000002"]["confianca"]) == ("BAIXA", "ALTA")
        # Código fora da tabela: sem preço de tabela, "não conferido".
        seringa = da_ia["70000077"]
        assert (seringa["preco_tabela"], seringa["valor_diferenca"], seringa["nao_conferido"]) == (None, None, True)
        assert da_ia["70000002"]["nao_conferido"] is False
        # Teto: a quantidade é a do código, diárias pagas × teto, e o valor vem dela.
        fralda = da_ia["70000050"]
        assert (fralda["quantidade_devida"], fralda["valor_diferenca"]) == (DEVIDA_DA_FRALDA, DEVIDA_DA_FRALDA * 2.0)
        # A mesma linha que o código já gerou: fica uma, a do código.
        pacotes = [linha for linha in linhas if linha["codigo"] == "98005497"]
        assert [(p["origem"], p["data"]) for p in pacotes] == [("CODIGO", "2026-10-04")]
        # O que caiu fica registrado na conta, com o motivo.
        motivos = {d["linha"]["codigo"]: d["motivo"] for d in banco.conta(conta["id"])["faltantes"]["descartadas_ia"]}
        assert motivos["70000005"] == "A regra ALFA-INS-99 não existe na memória."
        assert motivos["70000002"] == "Data fora do período da conta."

    def test_sem_preco_na_tabela_vale_o_unitario_da_conta_e_codigo_nulo_tenta_o_dicionario(self, openrouter):
        _, linhas = _analisar(
            _cenario_do_passo_b(),
            openrouter,
            # O Clexane não está na tabela da operadora; a conta lançou a 45,00.
            _linha_da_ia(
                acao="AJUSTAR_QUANTIDADE",
                codigo="90030001",
                descricao="CLEXANE 40MG/0,4ML SER PREENCH",
                quantidade_lancada=1,
                quantidade_devida=2,
            ),
            # Retirar tira o que foi lançado, pelo preço lançado (agulha a 0,17).
            _linha_da_ia(
                acao="RETIRAR",
                codigo="70000001",
                descricao="AGULHA HIPODERMICA 40X12",
                quantidade_lancada=10,
                quantidade_devida=0,
            ),
            # Sem código: o dicionário do hospital liga Clexane ao código da conta.
            _linha_da_ia(
                codigo=None,
                descricao="CLEXANE SERINGA",
                data="2026-10-04",
                data_fim="2026-10-04",
                acao="AJUSTAR_QUANTIDADE",
                quantidade_lancada=1,
                quantidade_devida=2,
            ),
            # Sem código e sem par no dicionário nem na conta.
            _linha_da_ia(codigo=None, descricao="BOLSA COLETORA DE URINA"),
        )
        da_ia = [linha for linha in linhas if linha["origem"] == "IA"]

        clexane, clexane_sem_codigo = sorted(
            (linha for linha in da_ia if linha["codigo"] == "90030001"), key=lambda linha: linha["data"]
        )
        assert (clexane["preco_lancado"], clexane["preco_tabela"], clexane["valor_diferenca"]) == (45.0, None, 45.0)
        assert clexane["motivo"].endswith("Valor pelo preço da conta, não conferido.")
        assert clexane["nao_conferido"] is True
        assert (clexane_sem_codigo["data"], clexane_sem_codigo["valor_diferenca"]) == ("2026-10-04", 45.0)
        (agulha,) = [linha for linha in da_ia if linha["codigo"] == "70000001"]
        assert (agulha["acao"], agulha["valor_diferenca"], agulha["nao_conferido"]) == ("RETIRAR", -1.7, False)
        (bolsa,) = [linha for linha in da_ia if linha["descricao"] == "BOLSA COLETORA DE URINA"]
        assert (bolsa["codigo"], bolsa["valor_diferenca"], bolsa["nao_conferido"]) == (None, None, True)
        assert bolsa["motivo"].endswith("Sem código.")


def _prescricao_da_ia(data: str, item: str) -> dict[str, Any]:
    return {
        "data": data,
        "setor": "CTI ADULTO",
        "item": item,
        "via": "EV",
        "doses_no_dia": 1,
        "se_necessario": False,
        "indicio_de_uso": None,
        "suspenso": False,
        "diluente": None,
        "em_bomba": False,
        "pagina": 3,
        "trecho": item,
    }


def _terapia_da_ia(inicio: str, fim: str | None, descricao: str) -> dict[str, Any]:
    return {
        "tipo": "OXIGENIO",
        "descricao": descricao,
        "setor": "CTI ADULTO",
        "inicio": inicio,
        "fim": fim,
        "pagina": 2,
        "trecho": descricao,
    }


class TestEntradaDoPassoB:
    def test_a_entrada_leva_a_memoria_em_cache_os_eventos_do_periodo_os_itens_e_as_linhas_do_codigo(self, openrouter):
        # A conta vai de 02/10 a 06/10: a margem é 01/10 e 07/10.
        openrouter.eventos = {
            **EVENTOS_DA_IA,
            "prescricoes": [
                _prescricao_da_ia("2026-09-20", "DIPIRONA FORA ANTES"),
                _prescricao_da_ia("2026-10-01", "DIPIRONA NA MARGEM DE ANTES"),
                _prescricao_da_ia("2026-10-04", "DIPIRONA NO PERIODO"),
                _prescricao_da_ia("2026-10-07", "DIPIRONA NA MARGEM DE DEPOIS"),
                _prescricao_da_ia("2026-10-08", "DIPIRONA FORA DEPOIS"),
            ],
            "terapias": [
                _terapia_da_ia("2026-09-15T08:00", "2026-09-25T08:00", "OXIGENIO DA INTERNACAO ANTERIOR"),
                _terapia_da_ia("2026-09-28T08:00", None, "OXIGENIO QUE SEGUE EM CURSO"),
            ],
        }

        _analisar(_cenario_do_passo_b(), openrouter)

        (corpo,) = [c for c in openrouter.corpos if c["response_format"]["json_schema"]["name"] == PASSO_B]
        memoria, eventos, conta, calculos = corpo["messages"][1]["content"]
        assert memoria["cache_control"] == {"type": "ephemeral"}
        assert "# MEMÓRIA DA OPERADORA: Alfa Saúde" in memoria["text"]
        assert "| ALFA-INS-05 | Regra sintética ALFA-INS-05. | CONTRATUAL | PRÁTICA | PENDENTE |" in memoria["text"]
        assert all("cache_control" not in bloco for bloco in (eventos, conta, calculos))

        assert eventos["text"].startswith("EVENTOS\n")
        for dentro in ("NA MARGEM DE ANTES", "NO PERIODO", "NA MARGEM DE DEPOIS", "QUE SEGUE EM CURSO"):
            assert dentro in eventos["text"], dentro
        for fora in ("FORA ANTES", "FORA DEPOIS", "INTERNACAO ANTERIOR"):
            assert fora not in eventos["text"], fora

        assert conta["text"].startswith("CONTA\n")
        assert "70000001 | AGULHA HIPODERMICA 40X12 | 10 | UN" in conta["text"]
        assert "0,17" not in conta["text"] and "0.17" not in conta["text"], "o preço lançado não vai para a IA"

        assert calculos["text"].startswith("CÁLCULOS\n")
        linhas_do_codigo = json.loads(calculos["text"].removeprefix("CÁLCULOS\n"))["linhas_do_codigo"]
        assert {
            "acao": "INCLUIR",
            "codigo": "98005497",
            "descricao": "PACOTE COLECISTECTOMIA",
            "data": "2026-10-04",
            "data_fim": None,
        } in linhas_do_codigo
