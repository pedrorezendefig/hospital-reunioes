"""A conversa da Operadora com o Auditor e o lote de propostas (issue #1490, PRD #1484, ADR 0081).

Quem tem "Regra contratual e tabelas" fala com o Auditor na Memória da
operadora. O texto vira um lote de propostas tipadas (Regra nova, Regra
alterada, parâmetro), cada uma com o motivo, os conflitos com as Regras que
existem e a Prova da regra. O "ok" aplica o lote numa versão nova só da
Memória; "corrige o item N" refaz só aquele item. A conversa fica guardada,
ligada à versão que gerou, e nunca entra no prompt do Passo A nem do Passo B.

Tudo pela rota de verdade, com o dublê do banco da carga da operadora e o
provedor da IA dublado no transporte HTTP (o adaptador roda inteiro). O
provedor responde pelo schema pedido.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import httpx2
import pytest
from anthropic_apoio import cliente_por_transporte, mensagem, nome_do_schema, nomear_schemas
from test_contas_medicas_memoria_tela import DIA_01_ANTES, DIA_01_DEPOIS, _importar, _versoes
from test_contas_medicas_operadoras import FATURISTA, GESTAO
from test_contas_medicas_prova_da_regra import _linha_do_guia, _semear
from test_contas_medicas_regra_nova import _cliente as _cliente_da_memoria

from app.limiter import limiter
from app.routers import contas_medicas_conversa as conversa_router
from app.services.contas_medicas import ia


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


ROTA = "/api/contas-medicas/operadoras/ALFA/conversa"


def _cliente(pessoa: dict[str, Any], ligar: tuple[str, ...] = ()):
    """O app da Memória da operadora com a conversa."""
    cliente, banco = _cliente_da_memoria(pessoa, ligar=ligar)
    cliente.app.include_router(conversa_router.router, prefix="/api")
    return cliente, banco


DIA_03 = "Transferência de setor antes das 12h não gera diária extra no setor de origem."
DIA_02 = "Transferência de setor antes das 10h: gera ou não diária extra no setor de origem."
PEDIDO = "Na ALFA a transferência antes do meio-dia não gera diária extra, e a diária vence ao meio-dia."


def _proposta(**campos: Any) -> dict[str, Any]:
    """Um item no formato da IA: a regra nova da transferência, com o que o teste trocar."""
    return {
        "tipo": "REGRA_NOVA",
        "regra_codigo": "",
        "secao": "DIA",
        "texto": DIA_03,
        "tipo_regra": "CONTRATUAL",
        "origem": "PRÁTICA",
        "parametro": "",
        "valor_json": "",
        "motivo": "A transferência antes do meio-dia deixa de gerar diária extra na origem.",
        "conflitos": [],
        **campos,
    }


LOTE = {
    "resposta": "Entendi três mudanças. Confira a prova de cada regra e responda ok.",
    "propostas": [
        # ALFA-DIA-99 não existe: a IA inventou, e o lote não repassa.
        _proposta(
            conflitos=[
                {"codigo": "ALFA-DIA-02", "resolucao": "SUBSTITUIR"},
                {"codigo": "ALFA-DIA-99", "resolucao": "JUNTAR"},
            ]
        ),
        _proposta(
            tipo="REGRA_ALTERADA",
            regra_codigo="ALFA-DIA-01",
            texto=DIA_01_DEPOIS,
            motivo="A diária passa a vencer ao meio-dia.",
        ),
        _proposta(
            tipo="PARAMETRO",
            texto="",
            parametro="diaria.hora_vencimento",
            valor_json='"12:00"',
            motivo="O cabeçalho acompanha o vencimento novo.",
        ),
    ],
}


class _Provedor:
    """A Anthropic do teste: responde pelo schema pedido. O Passo B da prova
    responde pela Conta do pedido (o código do item dela na tabela CONTA)."""

    def __init__(self, nomes: dict[str, str]):
        self.nomes = nomes
        self.pedidos: list[tuple[str, str]] = []
        # O modelo de cada pedido, com o formato: a prova vai no do passo B.
        self.modelos: list[tuple[str, str]] = []
        self.lote: dict = LOTE
        self.correcao: dict | None = None
        self.por_codigo: dict[str, list[dict]] = {}
        # Ligado, o Passo B da prova não responde: a prova falha inteira.
        self.prova_falha = False

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        corpo = json.loads(request.content)
        formato = nome_do_schema(self.nomes, corpo)
        texto = "\n".join(bloco["text"] for m in corpo["messages"] for bloco in m["content"])
        self.pedidos.append((formato, texto))
        self.modelos.append((formato, corpo["model"]))
        if formato == "LinhasDaComparacao" and self.prova_falha:
            return httpx2.Response(400, json={"type": "error", "error": {"type": "invalid_request_error"}})
        if formato == "LinhasDaComparacao":
            codigo = re.search(r"\bM\d{3}\b", texto.split("CONTA\n", 1)[1]).group(0)
            resposta = {"linhas": self.por_codigo.get(codigo, []), "resumo": "Comparada."}
        elif formato == "ItemCorrigido":
            resposta = self.correcao
        else:
            resposta = self.lote
        return httpx2.Response(200, json=mensagem(json.dumps(resposta)))

    def da_prova(self) -> list[str]:
        return [texto for formato, texto in self.pedidos if formato == "LinhasDaComparacao"]


@pytest.fixture
def provedor(monkeypatch) -> _Provedor:
    duble = _Provedor(nomear_schemas(monkeypatch))
    monkeypatch.setattr(ia, "_cliente", lambda: cliente_por_transporte(duble))
    monkeypatch.setattr(ia, "_esperar", lambda _segundos: None)
    return duble


@pytest.fixture
def cenario(provedor):
    """A ALFA com a memória 1.0 e doze Contas concluídas para a prova."""
    cliente, banco = _cliente(GESTAO)
    _importar(cliente)
    _importar(cliente, "MEMORIA-BETA-v1.0.md")
    _semear(banco)
    return cliente, banco, provedor


def _item(corpo: dict, numero: int) -> dict:
    return next(i for i in corpo["lote"]["itens"] if i["numero"] == numero)


# ═══════════════════════════════════════════════════════════════════════════
# 1. O texto vira um lote com a proposta, os conflitos e a prova
# ═══════════════════════════════════════════════════════════════════════════


class TestOTextoViraLote:
    def test_enviar_um_texto_de_regra_devolve_o_lote_com_proposta_conflitos_e_prova(self, cenario):
        cliente, banco, provedor = cenario
        # A regra nova tira uma Linha Feito da c12.
        banco.tabelas["cm_guia_linha"] = [_linha_do_guia("c12", "M012", "2026-10-12", 2.0, estado="FEITO")]

        resposta = cliente.post(ROTA, json={"texto": PEDIDO})

        assert resposta.status_code == 200, resposta.text
        corpo = resposta.json()
        assert [(i["numero"], i["tipo"]) for i in corpo["lote"]["itens"]] == [
            (1, "REGRA_NOVA"),
            (2, "REGRA_ALTERADA"),
            (3, "PARAMETRO"),
        ]

        nova = _item(corpo, 1)
        assert nova["proposta"] == {"secao": "DIA", "texto": DIA_03, "tipo": "CONTRATUAL", "origem": "PRÁTICA"}
        assert nova["motivo"] == LOTE["propostas"][0]["motivo"]
        # O texto da regra em conflito vem da memória, e o ID inventado fica de fora.
        assert nova["conflitos"] == [{"codigo": "ALFA-DIA-02", "texto": DIA_02, "resolucao": "SUBSTITUIR"}]
        assert (nova["prova"]["contas"], nova["prova"]["mudaria"], nova["prova"]["feitas_que_sumiriam"]) == (
            10,
            True,
            1,
        )

        alterada = _item(corpo, 2)
        assert alterada["regra_codigo"] == "ALFA-DIA-01"
        assert (alterada["proposta"]["texto_anterior"], alterada["proposta"]["texto"]) == (DIA_01_ANTES, DIA_01_DEPOIS)
        assert alterada["prova"]["contas"] == 10

        parametro = _item(corpo, 3)
        assert parametro["proposta"] == {"chave": "diaria.hora_vencimento", "antes": "10:00", "depois": "12:00"}
        assert parametro["prova"] is None

        # As falas ficam na conversa; a Memória não muda antes do ok.
        assert [(m["autor"], m["texto"]) for m in corpo["mensagens"]] == [
            ("PESSOA", PEDIDO),
            ("AUDITOR", LOTE["resposta"]),
        ]
        assert _versoes(banco, "ALFA") == {"1.0": True}
        # Uma chamada da conversa e dez da prova por regra.
        assert sorted(c["passo"] for c in banco.linhas("cm_chamada_ia")) == ["CONVERSA"] + ["PROVA"] * 20

    def test_a_prova_da_conversa_roda_no_modelo_do_passo_b_e_nao_no_da_validacao(self, cenario, monkeypatch):
        """Issue #1523: só a recomendação da Validação vai para o modelo da
        Validação; a Prova pedida na conversa segue no do passo B."""
        from app.config import settings

        cliente, banco, provedor = cenario
        monkeypatch.setattr(settings, "cm_ia_modelo_passo_b", "claude-opus-5-5")
        monkeypatch.setattr(settings, "cm_ia_modelo_validacao", "claude-sonnet-5-5")

        assert cliente.post(ROTA, json={"texto": PEDIDO}).status_code == 200

        da_prova = [modelo for formato, modelo in provedor.modelos if formato == "LinhasDaComparacao"]
        assert da_prova == ["claude-opus-5-5"] * 20
        assert {c["modelo"] for c in banco.linhas("cm_chamada_ia") if c["passo"] == "PROVA"} == {"claude-opus-5-5"}

    def test_a_prova_da_regra_alterada_troca_o_texto_da_antiga_na_memoria_candidata(self, cenario):
        cliente, _banco, provedor = cenario
        provedor.lote = {**LOTE, "propostas": [LOTE["propostas"][1]]}

        assert cliente.post(ROTA, json={"texto": PEDIDO}).status_code == 200

        pedido = provedor.da_prova()[0]
        assert f"| ALFA-DIA-01 | {DIA_01_DEPOIS} |" in pedido
        assert DIA_01_ANTES not in pedido

    def test_a_prova_do_item_com_conflito_roda_sem_a_regra_que_ele_substitui(self, cenario):
        cliente, _banco, provedor = cenario
        provedor.lote = {**LOTE, "propostas": [LOTE["propostas"][0]]}

        assert cliente.post(ROTA, json={"texto": PEDIDO}).status_code == 200

        pedido = provedor.da_prova()[0]
        assert f"| ALFA-DIA-03 | {DIA_03} |" in pedido
        assert DIA_02 not in pedido

    def test_a_ia_recebe_a_memoria_e_so_a_mensagem_desta_vez(self, cenario):
        cliente, _banco, provedor = cenario
        provedor.lote = {"resposta": "Entendi.", "propostas": []}
        cliente.post(ROTA, json={"texto": "Primeira mensagem, já passada."})

        cliente.post(ROTA, json={"texto": PEDIDO})

        _, pedido = [p for p in provedor.pedidos if p[0] == "LoteDoAuditor"][-1]
        assert f"| ALFA-DIA-01 | {DIA_01_ANTES} |" in pedido
        assert PEDIDO in pedido
        assert "Primeira mensagem" not in pedido


# ═══════════════════════════════════════════════════════════════════════════
# 2. O ok aplica o lote inteiro numa versão nova só da Memória
# ═══════════════════════════════════════════════════════════════════════════

OBITO = "Óbito antes das 12h não gera diária extra no setor de origem."
DIA_02_DECIDIDA = "Transferência de setor antes das 12h não gera diária extra no setor de origem, sem exceção."


def _vigente(banco) -> dict:
    oid = next(o["id"] for o in banco.linhas("cm_operadora") if o["sigla"] == "ALFA")
    return next(v for v in banco.linhas("cm_memoria_versao") if v["operadora_id"] == oid and v["vigente"])


def _regras_vigentes(banco) -> dict[str, dict]:
    vigente = _vigente(banco)
    return {r["codigo"]: r for r in banco.linhas("cm_regra") if r["memoria_versao_id"] == vigente["id"]}


class TestOOk:
    def test_o_ok_num_lote_com_varias_propostas_gera_uma_versao_so_com_as_regras_vigentes(self, cenario):
        cliente, banco, provedor = cenario
        provedor.lote = {
            **LOTE,
            "propostas": [
                _proposta(),
                _proposta(texto=OBITO),
                # A pendente ALFA-DIA-02, decidida pelo lote.
                _proposta(tipo="REGRA_ALTERADA", regra_codigo="ALFA-DIA-02", texto=DIA_02_DECIDIDA),
                LOTE["propostas"][2],
            ],
        }
        assert cliente.post(ROTA, json={"texto": PEDIDO}).status_code == 200

        resposta = cliente.post(ROTA, json={"texto": "ok"})

        assert resposta.status_code == 200, resposta.text
        corpo = resposta.json()
        assert _versoes(banco, "ALFA") == {"1.0": False, "1.1": True}
        assert corpo["aplicado"]["versao"] == "1.1"
        regras = _regras_vigentes(banco)
        tocadas = ("ALFA-DIA-02", "ALFA-DIA-03", "ALFA-DIA-04")
        # As duas regras novas da mesma seção ganham códigos seguidos.
        assert {c: (regras[c]["texto"], regras[c]["status"]) for c in tocadas} == {
            "ALFA-DIA-02": (DIA_02_DECIDIDA, "VIGENTE"),
            "ALFA-DIA-03": (DIA_03, "VIGENTE"),
            "ALFA-DIA-04": (OBITO, "VIGENTE"),
        }
        assert {regras[c]["validado_por"] for c in tocadas} == {GESTAO["id"]}
        # A regra que o lote não toca fica como estava.
        assert (regras["ALFA-PRI-03"]["status"], regras["ALFA-DIA-01"]["texto"]) == ("PENDENTE", DIA_01_ANTES)
        assert _vigente(banco)["parametros_json"]["diaria"]["hora_vencimento"] == "12:00"
        # O lote saiu da mesa.
        assert corpo["lote"] is None

    def test_o_ok_tira_da_memoria_a_regra_que_o_item_substitui_ou_junta(self, cenario):
        """Decisão 8: o conflito se resolve juntando ou substituindo, nunca
        empilhando. A regra em conflito sai da versão nova; a do item fica."""
        cliente, banco, provedor = cenario
        provedor.lote = {
            **LOTE,
            "propostas": [
                LOTE["propostas"][0],
                _proposta(
                    tipo="REGRA_ALTERADA",
                    regra_codigo="ALFA-DIA-01",
                    texto=DIA_01_DEPOIS,
                    conflitos=[{"codigo": "ALFA-PRI-03", "resolucao": "JUNTAR"}],
                ),
            ],
        }
        assert cliente.post(ROTA, json={"texto": PEDIDO}).status_code == 200

        assert cliente.post(ROTA, json={"texto": "ok"}).status_code == 200

        regras = _regras_vigentes(banco)
        assert {c: regras[c]["ativa"] for c in ("ALFA-DIA-02", "ALFA-PRI-03")} == {
            "ALFA-DIA-02": False,
            "ALFA-PRI-03": False,
        }
        assert (regras["ALFA-DIA-03"]["texto"], regras["ALFA-DIA-01"]["texto"]) == (DIA_03, DIA_01_DEPOIS)
        assert DIA_02 not in _vigente(banco)["texto_md"]

    def test_ok_com_item_de_regra_sem_prova_e_recusado_e_nada_muda(self, cenario):
        """Decisão 7: a prova vem antes do ok. A prova que falhou deixa o item
        sem prova, e o lote só se aplica depois que a correção prova de novo."""
        cliente, banco, provedor = cenario
        provedor.prova_falha = True
        assert cliente.post(ROTA, json={"texto": PEDIDO}).status_code == 200

        resposta = cliente.post(ROTA, json={"texto": "ok"})

        assert resposta.status_code == 422
        assert resposta.json()["detail"] == (
            "O item 1 está sem a prova da regra. Peça a correção do item para provar de novo antes do ok."
        )
        assert _versoes(banco, "ALFA") == {"1.0": True}
        assert cliente.get(ROTA).json()["lote"] is not None

    def test_ok_sem_lote_aberto_e_recusado_e_nada_muda(self, cenario):
        cliente, banco, _provedor = cenario

        resposta = cliente.post(ROTA, json={"texto": "ok"})

        assert resposta.status_code == 422
        assert resposta.json()["detail"] == "Não há lote aberto para aplicar."
        assert _versoes(banco, "ALFA") == {"1.0": True}


# ═══════════════════════════════════════════════════════════════════════════
# 3. "Corrige o item N" refaz só aquele item
# ═══════════════════════════════════════════════════════════════════════════

DIA_03_UTI = "Na UTI, transferência de setor antes das 12h não gera diária extra no setor de origem."


class TestCorrigeOItemN:
    def test_corrige_o_item_n_muda_so_o_item_n_e_preserva_os_outros(self, cenario):
        cliente, banco, provedor = cenario
        assert cliente.post(ROTA, json={"texto": PEDIDO}).status_code == 200
        antes = cliente.get(ROTA).json()["lote"]
        provas_antes = len(provedor.da_prova())
        provedor.correcao = {
            "resposta": "Corrigi o item 1: vale só para a UTI.",
            "proposta": _proposta(texto=DIA_03_UTI),
        }

        resposta = cliente.post(ROTA, json={"texto": "Corrige o item 1: só na UTI."})

        assert resposta.status_code == 200, resposta.text
        depois = resposta.json()["lote"]
        assert depois["id"] == antes["id"]
        assert _item(resposta.json(), 1)["proposta"]["texto"] == DIA_03_UTI
        assert [i for i in depois["itens"] if i["numero"] != 1] == [i for i in antes["itens"] if i["numero"] != 1]
        # O Auditor recebeu o item como estava e o que mudar nele.
        _, pedido = [p for p in provedor.pedidos if p[0] == "ItemCorrigido"][-1]
        assert DIA_03 in pedido and "só na UTI." in pedido
        # Só o item corrigido prova de novo.
        assert len(provedor.da_prova()) - provas_antes == 10
        assert [(m["autor"], m["texto"]) for m in resposta.json()["mensagens"]][-2:] == [
            ("PESSOA", "Corrige o item 1: só na UTI."),
            ("AUDITOR", "Corrigi o item 1: vale só para a UTI."),
        ]

        # O ok aplica o item corrigido.
        assert cliente.post(ROTA, json={"texto": "ok"}).status_code == 200
        assert _regras_vigentes(banco)["ALFA-DIA-03"]["texto"] == DIA_03_UTI

    @pytest.mark.parametrize(
        ("refeito", "falha"),
        [
            (_proposta(texto=DIA_03_UTI), True),
            (_proposta(tipo="PARAMETRO", texto="", parametro="diaria.hora_vencimento", valor_json='"12:00"'), False),
        ],
        ids=["prova-nova-falha", "item-vira-parametro"],
    )
    def test_o_item_corrigido_nao_mostra_a_prova_do_texto_antigo(self, cenario, refeito, falha):
        cliente, _banco, provedor = cenario
        assert cliente.post(ROTA, json={"texto": PEDIDO}).status_code == 200
        assert _item(cliente.get(ROTA).json(), 1)["prova"] is not None
        provedor.correcao = {"resposta": "Corrigi o item 1.", "proposta": refeito}
        provedor.prova_falha = falha

        resposta = cliente.post(ROTA, json={"texto": "corrige o item 1: só na UTI."})

        assert resposta.status_code == 200, resposta.text
        assert _item(resposta.json(), 1)["prova"] is None
        # O item que a correção não tocou segue com a prova dele.
        assert _item(resposta.json(), 2)["prova"]["contas"] == 10

    def test_corrigir_item_que_o_lote_nao_tem_e_recusado_sem_chamar_o_auditor(self, cenario):
        cliente, _banco, provedor = cenario
        assert cliente.post(ROTA, json={"texto": PEDIDO}).status_code == 200
        pedidos = len(provedor.pedidos)

        resposta = cliente.post(ROTA, json={"texto": "corrige o item 7: tanto faz"})

        assert resposta.status_code == 422
        assert resposta.json()["detail"] == "O lote não tem o item 7."
        assert len(provedor.pedidos) == pedidos


# ═══════════════════════════════════════════════════════════════════════════
# 4. A conversa fica ligada à versão e nunca entra no prompt das análises
# ═══════════════════════════════════════════════════════════════════════════


class TestAConversaEHistorico:
    def test_a_mensagem_que_pediu_o_lote_e_o_ok_ficam_ligados_a_versao_gerada(self, cenario):
        cliente, banco, _provedor = cenario
        assert cliente.post(ROTA, json={"texto": PEDIDO}).status_code == 200

        corpo = cliente.post(ROTA, json={"texto": "ok"}).json()

        assert [(m["autor"], m["texto"], m["versao"]) for m in corpo["mensagens"][:3]] == [
            ("PESSOA", PEDIDO, "1.1"),
            ("AUDITOR", LOTE["resposta"], None),
            ("PESSOA", "ok", "1.1"),
        ]
        assert (corpo["mensagens"][3]["autor"], corpo["mensagens"][3]["versao"]) == ("AUDITOR", "1.1")
        assert corpo["mensagens"][0]["autor_nome"] == GESTAO["nome_completo"]
        (lote,) = banco.linhas("cm_lote")
        assert (lote["estado"], lote["memoria_versao_id"]) == ("APLICADO", _vigente(banco)["id"])
        assert lote["aplicado_por"] == GESTAO["id"]
        # A conversa continua guardada depois do ok, para quem abrir de novo.
        assert cliente.get(ROTA).json()["mensagens"] == corpo["mensagens"]

    def test_a_conversa_nao_aparece_no_prompt_do_passo_a_nem_do_passo_b(self, monkeypatch):
        """O ok vale na análise seguinte pela Regra aprovada; a conversa que a
        ensinou não vai junto (ADR 0081, decisão 3). A análise roda inteira,
        do envio ao Guia, e o teste lê o prompt que saiu para a IA."""
        from test_contas_medicas_processamento import (
            PASSO_A,
            PASSO_B,
            _cenario,
            _conta,
            _enviar,
            _Extrator,
            _IAFalsa,
            _prontuario,
            _rodar_o_job,
        )
        from test_contas_medicas_processamento import _cliente as _cliente_do_processamento

        from app.services.contas_medicas import envio as envio_service
        from app.services.contas_medicas import processamento

        extrator = _Extrator()
        monkeypatch.setattr(envio_service, "extrair_paginas", extrator)
        monkeypatch.setattr(processamento, "extrair_paginas", extrator)
        ia_falsa = _IAFalsa()
        ia_falsa.nomes = nomear_schemas(monkeypatch)
        monkeypatch.setattr(ia, "_cliente", lambda: cliente_por_transporte(ia_falsa))
        monkeypatch.setattr(ia, "_esperar", lambda _segundos: None)

        aprovada = "Equipo de bomba de infusão é cobrado uma vez por dia de uso."
        da_pessoa = "Conversa da diretoria: o equipo da Dona Fulana foi trocado três vezes."
        do_auditor = "Resposta do Auditor: anotei a troca do equipo e vou lembrar disso."
        ia_falsa.respostas["LoteDoAuditor"] = {
            "resposta": do_auditor,
            "propostas": [_proposta(secao="INS", texto=aprovada)],
        }
        banco = _cenario()
        gestao = _cliente_do_processamento(banco, "gestao")
        gestao.app.include_router(conversa_router.router, prefix="/api")
        assert gestao.post(ROTA, json={"texto": da_pessoa}).status_code == 200
        assert gestao.post(ROTA, json={"texto": "ok"}).status_code == 200

        _enviar(banco, _conta(), _prontuario())
        _rodar_o_job(banco)

        (conta,) = banco.tabelas["cm_conta"]
        assert conta["situacao"] == "A_FAZER", conta.get("erro_motivo")
        prompts = {
            formato: json.dumps(corpo, ensure_ascii=False)
            for corpo in ia_falsa.corpos
            if (formato := corpo["formato"]) in (PASSO_A, PASSO_B)
        }
        assert set(prompts) == {PASSO_A, PASSO_B}
        # A Regra aprovada pesa; nada da conversa vai junto.
        assert aprovada in prompts[PASSO_B]
        for prompt in prompts.values():
            assert "Dona Fulana" not in prompt
            assert "anotei a troca do equipo" not in prompt


# ═══════════════════════════════════════════════════════════════════════════
# 5. Só quem tem "Regra contratual e tabelas" abre a conversa da Operadora
# ═══════════════════════════════════════════════════════════════════════════


class TestQuemConversa:
    def test_quem_nao_tem_regra_contratual_e_tabelas_nao_abre_a_conversa(self, provedor):
        # A faturista com "incluir regra operacional" ligada abre a Memória da
        # operadora, mas não a conversa com o Auditor.
        cliente, banco = _cliente(FATURISTA, ligar=("incluir_regra_operacional",))
        # A memória entra pela gestão (a mesma sessão do teste, com o perfil trocado).
        banco.tabelas["participantes"] = [GESTAO]
        _importar(cliente)
        banco.tabelas["participantes"] = [FATURISTA]
        assert cliente.get("/api/contas-medicas/operadoras/ALFA").status_code == 200

        leitura = cliente.get(ROTA)
        envio = cliente.post(ROTA, json={"texto": PEDIDO})

        assert (leitura.status_code, envio.status_code) == (403, 403)
        assert provedor.pedidos == []
        assert banco.linhas("cm_conversa") == banco.linhas("cm_conversa_mensagem") == banco.linhas("cm_lote") == []

    def test_o_app_de_verdade_registra_as_rotas_da_conversa(self):
        """A fonte é o schema OpenAPI, e não `app.routes` (issues #542 e #546)."""
        from app.main import app

        cache = app.openapi_schema
        try:
            caminhos = app.openapi()["paths"]
        finally:
            app.openapi_schema = cache

        assert len(caminhos) > 50
        assert {"get", "post"} <= set(caminhos["/api/contas-medicas/operadoras/{sigla}/conversa"])


# ═══════════════════════════════════════════════════════════════════════════
# 7. O kit de conhecimento diz o comportamento novo
# ═══════════════════════════════════════════════════════════════════════════

KIT = Path(__file__).resolve().parents[1] / "app" / "conhecimento" / "contas-medicas.md"


class TestOKit:
    def test_o_kit_diz_que_a_operadora_se_ensina_conversando_com_o_auditor_em_lote(self):
        no_ar = KIT.read_text(encoding="utf-8").split("## O que já está no ar")[1].split("\n## ")[0]

        for termo in (
            "Falar com o auditor",
            "lote",
            '"ok"',
            '"corrige o item 2"',
            "uma versão nova da memória só",
            "nasce vigente",
            "regra contratual e tabelas",
            "Enviar tabela",
            "não entra na análise",
        ):
            assert termo in no_ar, termo
