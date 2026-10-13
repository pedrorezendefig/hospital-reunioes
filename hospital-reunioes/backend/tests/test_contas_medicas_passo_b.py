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


class TestNotaComAsLinhasDaIA:
    def test_a_nota_de_entrada_muda_com_a_linha_da_ia_e_o_rs_em_validacao_soma_a_linha_validar(self, openrouter):
        """Sem a IA, o par sintético dá nota 17: R$ 5.500,30 apontados de R$
        6.592,00 devidos (o teste do pipeline do processamento). A IA inclui
        10 equipos a R$ 12,50 (R$ 125,00) e propõe 2 curativos a R$ 5,00 por
        regra pendente (R$ 10,00 em validação): 5.625,30 de 6.717,00 dá 16."""
        banco = _cenario_do_passo_b()
        conta, _ = _analisar(
            banco,
            openrouter,
            _linha_da_ia(quantidade_devida=10),
            _linha_da_ia(
                codigo="70000003", descricao="CURATIVO HIDROCOLOIDE", quantidade_devida=2, regra_id="ALFA-INS-05"
            ),
        )

        gravada = banco.conta(conta["id"])
        assert (gravada["nota_bruta"], gravada["valor_apontado"], gravada["valor_em_validacao"]) == (16, 5625.30, 10.0)
        numeros = _guia(banco, conta["id"])["numeros"]
        assert (numeros["nota_entrada"], numeros["valor_em_validacao"]) == (16, 10.0)


class TestFalhaDaIA:
    def test_a_ia_fora_do_ar_deixa_erro_com_a_frase_guarda_as_linhas_do_codigo_e_o_reprocesso_funciona(
        self, openrouter
    ):
        openrouter.fora_do_formato_em = {PASSO_B}
        banco = _cenario_do_passo_b()
        _enviar(banco, _conta(), _prontuario())

        _rodar_o_job(banco)

        (conta,) = banco.tabelas["cm_conta"]
        # As três tentativas são do adaptador; a conta não volta para a fila.
        assert openrouter.formatos.count(PASSO_B) == 3
        assert (conta["situacao"], conta["erro_motivo"], conta["tentativas"]) == (
            "ERRO",
            "Tente de novo em alguns minutos",
            1,
        )
        # O que o código achou (agulha, diária, pacote e Clexane) ficou no Guia.
        guardadas = [linha for linha in banco.tabelas["cm_guia_linha"] if linha["conta_id"] == conta["id"]]
        assert sorted((linha["origem"], linha["codigo"]) for linha in guardadas) == [
            ("CODIGO", "60001038"),
            ("CODIGO", "70000001"),
            ("CODIGO", "90030001"),
            ("CODIGO", "98005497"),
        ]

        # A IA voltou e a faturista manda a conta de novo pelo botão da conta em Erro.
        openrouter.fora_do_formato_em = set()
        openrouter.comparacao = {"linhas": [_linha_da_ia()], "resumo": "Conta comparada com a memória."}
        _enviar(banco, _conta())
        _rodar_o_job(banco)

        assert (banco.conta(conta["id"])["situacao"], banco.conta(conta["id"])["erro_motivo"]) == ("A_FAZER", None)
        linhas = _linhas_do_guia(_guia(banco, conta["id"]))
        assert sorted((linha["origem"], linha["codigo"]) for linha in linhas) == [
            ("CODIGO", "60001038"),
            ("CODIGO", "70000001"),
            ("CODIGO", "90030001"),
            ("CODIGO", "98005497"),
            ("IA", "70000002"),
        ]


class TestCustoDoPassoB:
    def test_a_chamada_do_passo_b_fica_gravada_com_os_tokens_de_cache_e_o_custo(self, openrouter):
        openrouter.uso = {
            "prompt_tokens": 2500,
            "completion_tokens": 300,
            "total_tokens": 2800,
            "prompt_tokens_details": {"cached_tokens": 2000},
            "cost": 0.0123,
        }
        banco = _cenario_do_passo_b()

        conta, _ = _analisar(banco, openrouter)

        (chamada,) = [c for c in banco.tabelas["cm_chamada_ia"] if c["passo"] == "B"]
        campos = ("conta_id", "atendimento_id", "tokens_entrada", "tokens_saida", "tokens_cache", "custo_usd")
        assert {campo: chamada[campo] for campo in (*campos, "sucesso")} == {
            "conta_id": conta["id"],
            "atendimento_id": conta["atendimento_id"],
            "tokens_entrada": 2500,
            "tokens_saida": 300,
            "tokens_cache": 2000,
            "custo_usd": 0.0123,
            "sucesso": True,
        }
        assert chamada["modelo"].startswith("anthropic/")


class TestCausaRaiz:
    def test_a_causa_raiz_da_ia_e_sobreposta_nos_casos_obvios(self, openrouter):
        banco = _cenario_do_passo_b()
        banco.tabelas["cm_regra"].append(_regra("ALFA-PRC-05"))
        # O MV não deixou lançar o curativo em outra conta: falta de cadastro.
        banco.tabelas["cm_guia_linha"].append(
            {"id": "gl-outra", "conta_id": "outra", "acao": "INCLUIR", "codigo": "70000003", "estado": "BLOQUEADO"}
        )

        _, linhas = _analisar(
            banco,
            openrouter,
            # Diária, mesmo que a IA diga lançamento manual: Regra automática.
            _linha_da_ia(
                acao="VALIDAR",
                codigo="60001038",
                descricao="DIARIA DE UTI ADULTO",
                data="2026-10-05",
                data_fim="2026-10-05",
                regra_id="ALFA-DIA-01",
                causa_raiz="LANCAMENTO_MANUAL",
            ),
            # Regra de preço: Cadastro e preço.
            _linha_da_ia(regra_id="ALFA-PRC-05", causa_raiz="DISPENSACAO"),
            # Item que o MV bloqueou: Cadastro e preço.
            _linha_da_ia(codigo="70000003", descricao="CURATIVO HIDROCOLOIDE", causa_raiz="DISPENSACAO"),
            # O resto fica como a IA disse.
            _linha_da_ia(codigo="70000004", descricao="CATETER NASAL", causa_raiz="REGISTRO_ASSISTENCIAL"),
        )

        causas = {linha["codigo"]: linha["causa_raiz"] for linha in linhas if linha["origem"] == "IA"}
        assert causas == {
            "60001038": "REGRA_AUTOMATICA",
            "70000002": "CADASTRO_PRECO",
            "70000003": "CADASTRO_PRECO",
            "70000004": "REGISTRO_ASSISTENCIAL",
        }


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
