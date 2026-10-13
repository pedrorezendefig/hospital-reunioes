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
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from openai import OpenAI
from test_contas_medicas_processamento import (
    AGORA,
    EVENTOS_DA_IA,
    PARAMETROS,
    PASSO_B,
    PESSOAS,
    _arquivo_do_envio,
    _Banco,
    _cenario,
    _conta,
    _enviar,
    _Extrator,
    _guia,
    _item_de_tabela,
    _linhas_do_guia,
    _OpenRouter,
    _paginas_do_prontuario,
    _prontuario,
    _regra,
    _rodar_o_job,
)

from app.dependencies import get_current_user, get_supabase_client
from app.limiter import limiter
from app.routers import contas_medicas_operadoras as operadoras_router
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


# O teto da fralda no CTI. O par sintético tem 4 diárias de CTI pagas, de 02/10
# a 05/10 (de 02/10 22:40 à alta em 06/10 15:20; o guia do código retira a 5ª
# lançada a mais do pacote): 6 fraldas por diária paga.
TETO_DA_FRALDA = {"codigo": "70000050", "cti": 6}


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
        # Teto: a quantidade é a do código, diárias pagas do período da linha
        # (03, 04 e 05/10) × 6, e o valor vem dela (fralda a 2,00 na tabela).
        fralda = da_ia["70000050"]
        assert (fralda["quantidade_devida"], fralda["valor_diferenca"]) == (18, 36.0)
        # A mesma linha que o código já gerou: fica uma, a do código.
        pacotes = [linha for linha in linhas if linha["codigo"] == "98005497"]
        assert [(p["origem"], p["data"]) for p in pacotes] == [("CODIGO", "2026-10-04")]
        # O que caiu fica registrado na conta, com o motivo.
        motivos = {d["linha"]["codigo"]: d["motivo"] for d in banco.conta(conta["id"])["faltantes"]["descartadas_ia"]}
        assert motivos["70000005"] == "A regra ALFA-INS-99 não existe na memória."
        assert motivos["70000002"] == "Data fora do período da conta."

    def test_o_teto_da_linha_e_o_das_diarias_pagas_no_periodo_dela(self, openrouter):
        def fralda(data: str, data_fim: str) -> dict[str, Any]:
            return _linha_da_ia(
                codigo="70000050",
                descricao="FRALDA GERIATRICA",
                data=data,
                data_fim=data_fim,
                quantidade_devida=30,
                regra_id="ALFA-INS-04",
            )

        # Dois períodos que não se cruzam: 02 e 03/10 (2 diárias) e 04 a 06/10
        # (04 e 05/10 pagas; a alta do dia 06 não é diária). Juntas, as 24 da
        # conta inteira, nunca o dobro.
        _, linhas = _analisar(
            _cenario_do_passo_b(), openrouter, fralda("2026-10-02", "2026-10-03"), fralda("2026-10-04", "2026-10-06")
        )
        fraldas = sorted((linha["data"], linha["quantidade_devida"]) for linha in linhas if linha["origem"] == "IA")
        assert fraldas == [("2026-10-02", 12), ("2026-10-04", 12)]

    def test_a_linha_de_um_dia_so_tem_o_teto_de_uma_diaria(self, openrouter):
        _, linhas = _analisar(
            _cenario_do_passo_b(),
            openrouter,
            _linha_da_ia(
                codigo="70000050", descricao="FRALDA GERIATRICA", quantidade_devida=30, regra_id="ALFA-INS-04"
            ),
        )
        (fralda,) = [linha for linha in linhas if linha["origem"] == "IA"]
        assert (fralda["quantidade_devida"], fralda["valor_diferenca"]) == (6, 12.0)
        assert fralda["motivo"].endswith("Teto pelo código: 6 para 1 diária paga no período.")

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

    def test_o_motivo_com_os_acrescimos_do_codigo_fica_em_ate_140_caracteres(self, openrouter):
        # O motivo da IA já no limite (140), numa linha de regra pendente e sem
        # código: o código acrescenta o "pendente" na frente e o "Sem código." no fim.
        motivo_da_ia = ("Bolsa coletora de urina registrada na evolução de enfermagem, " * 3)[:140]
        _, linhas = _analisar(
            _cenario_do_passo_b(),
            openrouter,
            _linha_da_ia(codigo=None, descricao="BOLSA COLETORA DE URINA", regra_id="ALFA-INS-05", motivo=motivo_da_ia),
        )

        (bolsa,) = [linha for linha in linhas if linha["origem"] == "IA"]
        assert len(bolsa["motivo"]) == 140
        # Quem perde é o texto da IA, com reticências; o que o código conferiu fica inteiro.
        assert bolsa["motivo"].startswith("Regra ALFA-INS-05 pendente. Bolsa coletora de urina registrada")
        assert bolsa["motivo"].endswith("… Sem código.")


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


PROPOSTAS = "PropostasDoDicionario"
# O genérico do Clexane, com a mesma largura do nome que ele substitui: a
# prescrição do MV é lida por coluna.
ENOXAPARINA = "ENOXAPARINA 40MG/0,4ML SER"
ENOXA_ID, ROCU_ID = "00000000-0000-4000-8000-000000000001", "00000000-0000-4000-8000-000000000002"


def _prontuario_com_enoxaparina():
    paginas = [p.replace("CLEXANE 40MG/0,4ML SER PREENCH", f"{ENOXAPARINA:<30}") for p in _paginas_do_prontuario()]
    return _arquivo_do_envio("prontuario.pdf", "\f".join(paginas))


def _cliente_da_carga(banco: _Banco, quem: str) -> TestClient:
    pessoa = PESSOAS[quem]
    app = FastAPI()
    app.state.limiter = limiter
    app.include_router(operadoras_router.router, prefix="/api")

    async def _usuario() -> dict[str, Any]:
        return {"id": pessoa["auth_user_id"], "email": pessoa["email"], "metadata": {}}

    app.dependency_overrides[get_current_user] = _usuario
    app.dependency_overrides[get_supabase_client] = lambda: banco
    return TestClient(app)


def _lancado_sem_mencao_do_clexane(banco: _Banco) -> list[str]:
    """As contas em que o Clexane saiu "lançado sem menção": a conferência que
    não teve o termo da enoxaparina no dicionário."""
    return [
        conta["numero_conta"]
        for conta in banco.tabelas["cm_conta"]
        for linha in _linhas_do_guia(_guia(banco, conta["id"]))
        if linha["codigo"] == "90030001" and linha["motivo"].startswith("Lançado sem nenhuma menção")
    ]


class TestDicionarioPelaIA:
    def test_termo_sem_par_vai_uma_vez_a_ia_e_entra_proposto(self, openrouter):
        """A prescrição diz enoxaparina e a conta lança Clexane: nem o
        dicionário, nem a marca, nem a concentração ligam os dois. A IA
        recebe o termo e os medicamentos da conta e propõe o código. A segunda
        parcial do atendimento tem o mesmo termo e não pergunta de novo."""
        openrouter.respostas[PROPOSTAS] = {"propostas": [{"termo": ENOXAPARINA, "codigo": "90030001"}]}
        banco = _cenario_do_passo_b()
        _enviar(banco, _conta("48811", 2, 3), _conta("48812", 4, 6), _prontuario_com_enoxaparina())

        assert _rodar_o_job(banco) == 2

        assert [c["situacao"] for c in banco.tabelas["cm_conta"]] == ["A_FAZER", "A_FAZER"]
        assert openrouter.formatos.count(PROPOSTAS) == 1
        (corpo,) = [c for c in openrouter.corpos if c["response_format"]["json_schema"]["name"] == PROPOSTAS]
        pergunta = corpo["messages"][1]["content"][0]["text"]
        assert ENOXAPARINA in pergunta
        assert "90030001 | CLEXANE 40MG/0,4ML SER PREENCH" in pergunta
        (proposta,) = [t for t in banco.tabelas["cm_item_dicionario"] if t["termo"] == ENOXAPARINA]
        assert {k: proposta[k] for k in ("codigo_conta", "situacao", "origem")} == {
            "codigo_conta": "90030001",
            "situacao": "PROPOSTO",
            "origem": "IA",
        }
        assert [c["passo"] for c in banco.tabelas["cm_chamada_ia"]].count("DICIONARIO") == 1

    def test_duas_parciais_em_vagas_paralelas_perguntam_o_termo_uma_vez(self, openrouter):
        """As duas vagas pegam as parciais do envio juntas. A barreira segura a
        primeira na chamada do dicionário até a outra chegar lá: sem a trava do
        atendimento, as duas leram o dicionário sem o termo e as duas perguntam.
        Com a trava, a barreira estoura, a primeira segue sozinha e a segunda lê
        o dicionário já com a proposta."""
        openrouter.respostas[PROPOSTAS] = {"propostas": [{"termo": ENOXAPARINA, "codigo": "90030001"}]}
        banco = _cenario_do_passo_b()
        _enviar(banco, _conta("48811", 2, 3), _conta("48812", 4, 6), _prontuario_com_enoxaparina())
        as_duas_na_ia = threading.Barrier(2, timeout=1)

        def esperar_a_outra_vaga(formato: str) -> None:
            if formato == PROPOSTAS:
                try:
                    as_duas_na_ia.wait()
                except threading.BrokenBarrierError:
                    pass

        openrouter.antes_de_responder = esperar_a_outra_vaga
        vagas = ThreadPoolExecutor(max_workers=2)
        try:
            assert processamento.alimentar_fila(banco, AGORA, executor=vagas) == 2
        finally:
            vagas.shutdown(wait=True)

        assert [c["situacao"] for c in banco.tabelas["cm_conta"]] == ["A_FAZER", "A_FAZER"]
        assert openrouter.formatos.count(PROPOSTAS) == 1
        assert _lancado_sem_mencao_do_clexane(banco) == []

    def test_o_termo_que_outra_parcial_gravou_antes_vale_nesta_conta(self, openrouter):
        """Entre a leitura do dicionário e a gravação, outra parcial (outro
        processo, fora da trava) grava o mesmo termo: o insert bate no índice
        único, e a conta é conferida com o dicionário relido, não sem o termo."""
        openrouter.respostas[PROPOSTAS] = {"propostas": [{"termo": ENOXAPARINA, "codigo": "90030001"}]}
        banco = _cenario_do_passo_b()
        _enviar(banco, _conta(), _prontuario_com_enoxaparina())

        def a_outra_parcial_grava_antes(formato: str) -> None:
            if formato == PROPOSTAS:
                banco.table("cm_item_dicionario").insert(
                    {
                        "termo": ENOXAPARINA,
                        "codigo_conta": "90030001",
                        "descricao_conta": "CLEXANE 40MG/0,4ML SER PREENCH",
                        "situacao": "PROPOSTO",
                        "origem": "IA",
                    }
                ).execute()

        openrouter.antes_de_responder = a_outra_parcial_grava_antes
        _rodar_o_job(banco)

        (conta,) = banco.tabelas["cm_conta"]
        assert conta["situacao"] == "A_FAZER", conta.get("erro_motivo")
        assert [t["termo"] for t in banco.tabelas["cm_item_dicionario"]].count(ENOXAPARINA) == 1
        assert _lancado_sem_mencao_do_clexane(banco) == []

    def test_termo_que_a_ia_nao_soube_ligar_fica_sem_codigo_e_nao_volta_a_ia(self, openrouter):
        # Código fora da lista da conta é chute: vale como sem par.
        openrouter.respostas[PROPOSTAS] = {"propostas": [{"termo": ENOXAPARINA, "codigo": "99999999"}]}
        banco = _cenario_do_passo_b()
        _enviar(banco, _conta("48811", 2, 3), _conta("48812", 4, 6), _prontuario_com_enoxaparina())

        assert _rodar_o_job(banco) == 2

        assert openrouter.formatos.count(PROPOSTAS) == 1
        (termo,) = [t for t in banco.tabelas["cm_item_dicionario"] if t["termo"] == ENOXAPARINA]
        assert (termo["codigo_conta"], termo["situacao"]) == (None, "PROPOSTO")

    def test_a_gestao_confirma_e_rejeita_a_proposta_pela_rota_e_a_faturista_nao(self, openrouter):
        banco = _cenario_do_passo_b()
        da_ia = {"situacao": "PROPOSTO", "origem": "IA"}
        banco.tabelas["cm_item_dicionario"] += [
            {"id": ENOXA_ID, "termo": ENOXAPARINA, "codigo_conta": "90030001", **da_ia},
            {"id": ROCU_ID, "termo": "ROCURONIO 10MG/ML", "codigo_conta": "90040001", **da_ia},
        ]
        gestao, faturista = _cliente_da_carga(banco, "gestao"), _cliente_da_carga(banco, "faturista")
        rota = "/api/contas-medicas/dicionario/propostas"

        assert faturista.get(rota).status_code == 403
        assert faturista.post(f"{rota}/{ENOXA_ID}/confirmar").status_code == 403
        lista = gestao.get(rota)
        assert lista.status_code == 200, lista.text
        assert [(p["termo"], p["codigo_conta"]) for p in lista.json()["propostas"]] == [
            (ENOXAPARINA, "90030001"),
            ("ROCURONIO 10MG/ML", "90040001"),
        ]

        assert gestao.post(f"{rota}/{ENOXA_ID}/confirmar").status_code == 200
        assert gestao.post(f"{rota}/{ROCU_ID}/rejeitar").status_code == 200

        termos = {t["id"]: t for t in banco.tabelas["cm_item_dicionario"]}
        decisao = [(t["situacao"], t["codigo_conta"], t["autor_id"]) for t in (termos[ENOXA_ID], termos[ROCU_ID])]
        # Rejeitada: o termo fica sem código, para a IA não ser perguntada de novo.
        assert decisao == [("CONFIRMADO", "90030001", "G1"), ("CONFIRMADO", None, "G1")]
        assert gestao.get(rota).json()["propostas"] == []
        assert gestao.post(f"{rota}/{ENOXA_ID}/confirmar").status_code == 409


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


# ═══════════════════════════════════════════════════════════════════════════
# O kit de conhecimento e a tipografia
# ═══════════════════════════════════════════════════════════════════════════

TRAVESSAO, MEIA_RISCA = chr(0x2014), chr(0x2013)
RAIZ_DO_APP = Path(__file__).resolve().parents[2]
KIT_DO_PRODUTO = RAIZ_DO_APP / "backend/app/conhecimento/contas-medicas.md"
ARQUIVOS_DA_FATIA = [
    RAIZ_DO_APP / "backend/app/services/contas_medicas/passo_b.py",
    RAIZ_DO_APP / "backend/app/services/contas_medicas/dicionario_ia.py",
    RAIZ_DO_APP / "backend/app/services/contas_medicas/processamento.py",
    RAIZ_DO_APP / "backend/app/services/contas_medicas/conferencia.py",
    RAIZ_DO_APP / "backend/app/routers/contas_medicas_operadoras.py",
    RAIZ_DO_APP / "backend/app/prompts/contas_medicas_dicionario.md",
    RAIZ_DO_APP / "frontend/src/components/contas-medicas/PropostasDoDicionario.tsx",
    KIT_DO_PRODUTO,
    Path(__file__),
]


def test_o_kit_diz_o_que_a_ia_compara_e_o_que_o_codigo_confere():
    texto = " ".join(KIT_DO_PRODUTO.read_text(encoding="utf-8").split()).casefold()

    # O que a IA compara, e com o quê.
    for trecho in (
        "compara o que aconteceu com a paciente com o que foi lançado na conta, aplicando as regras do convênio",
        "a memória inteira da operadora",
        "os fatos do prontuário no período da conta, com um dia a mais de cada lado",
        "acessórios de cada medicação",
        "insumos por tempo de cada terapia",
        "o bloco do centro cirúrgico",
    ):
        assert trecho.casefold() in texto, trecho
    # As seis conferências do código, e o que acontece quando cada uma falha.
    for trecho in (
        "seis conferências do código",
        "a regra citada existe na memória",
        "regra pendente vira Validar",
        "o trecho citado está na página do prontuário ou na vizinha",
        "o código existe na tabela da operadora",
        "o teto por dia é recalculado pelo código",
        "a linha está dentro do período da conta",
        "Propostas da IA para o dicionário",
    ):
        assert trecho.casefold() in texto, trecho


@pytest.mark.parametrize("arquivo", ARQUIVOS_DA_FATIA, ids=lambda a: a.name)
def test_sem_travessao_nem_meia_risca_nos_arquivos(arquivo):
    texto = arquivo.read_text(encoding="utf-8")
    assert TRAVESSAO not in texto
    assert MEIA_RISCA not in texto


def test_o_texto_que_a_ia_escreveu_na_linha_sai_sem_travessao_nem_meia_risca(openrouter):
    banco = _cenario_do_passo_b()

    _, linhas = _analisar(
        banco,
        openrouter,
        _linha_da_ia(motivo=f"Acesso venoso {TRAVESSAO} sem equipo na conta."),
        _linha_da_ia(regra_id="ALFA-INS-99", motivo=f"Luva {MEIA_RISCA} sem regra."),
    )

    (equipo,) = [linha for linha in linhas if linha["origem"] == "IA"]
    assert equipo["motivo"] == "Acesso venoso, sem equipo na conta."
    gravado = json.dumps(banco.tabelas["cm_conta"][0]["faltantes"], ensure_ascii=False)
    assert TRAVESSAO not in gravado and MEIA_RISCA not in gravado
