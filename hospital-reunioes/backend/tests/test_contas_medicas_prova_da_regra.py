"""A Prova da regra antes do Validar (issue #1488, PRD #1484, ADR 0081).

A regra que a pessoa vai validar refaz o Passo B nas 10 últimas Contas
concluídas da Operadora, a partir do que ficou guardado (os eventos que a IA
leu, os itens e o Guia), e devolve, por Conta, as Linhas que entrariam,
sairiam ou mudariam em relação ao Guia original. Nada muda nas Contas.

Tudo pela rota de verdade, com o dublê do banco da carga da operadora e o
provedor da IA dublado no transporte HTTP (o adaptador roda inteiro). O
provedor responde pela Conta que está no pedido, pelo código do item dela.
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

import httpx2
import pytest
from anthropic_apoio import cliente_por_transporte, mensagem
from test_contas_medicas_memoria_tela import _importar, _operadora_id, _versao
from test_contas_medicas_regra_nova import _cliente

from app.limiter import limiter
from app.services.contas_medicas import ia
from test_contas_medicas_operadoras import GESTAO

MIGRATION_126 = Path(__file__).resolve().parents[2] / "supabase" / "migrations" / "126_contas_medicas_auditor.sql"
KIT = Path(__file__).resolve().parents[1] / "app" / "conhecimento" / "contas-medicas.md"


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


REGRA = {
    "secao": "DIA",
    "texto": "Transferência de setor antes das 12h não gera diária extra no setor de origem.",
    "tipo": "CONTRATUAL",
    "origem": "PRÁTICA",
    "parametro": None,
}
# O código que a regra ganha na ALFA: a seção DIA já tem a 01 e a 02.
CODIGO_NOVO = "ALFA-DIA-03"


def _rota(sigla: str = "ALFA") -> str:
    return f"/api/contas-medicas/operadoras/{sigla}/regras/prova"


def _linha_da_ia(codigo: str, dia: str, devida: float, regra: str = CODIGO_NOVO) -> dict[str, Any]:
    return {
        "acao": "INCLUIR",
        "data": dia,
        "data_fim": "",
        "setor": "UTI",
        "codigo": codigo,
        "descricao": f"Item {codigo}",
        "quantidade_lancada": 1,
        "quantidade_devida": devida,
        "regra_id": regra,
        "motivo": "Dado na evolução.",
        "evidencia": {"pagina": 3, "trecho": "administrado"},
        "nivel_evidencia": "REGISTRADO",
        "causa_raiz": "DISPENSACAO",
        "confianca": "ALTA",
    }


class _Provedor:
    """A Anthropic do teste: responde o Passo B pela Conta do pedido (o código
    do item dela na tabela CONTA) e guarda o texto de cada pedido."""

    def __init__(self):
        self.pedidos: list[str] = []
        self.por_codigo: dict[str, list[dict]] = {}

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        corpo = json.loads(request.content)
        texto = "\n".join(bloco["text"] for m in corpo["messages"] for bloco in m["content"])
        self.pedidos.append(texto)
        conta = texto.split("CONTA\n", 1)[1]
        codigo = re.search(r"\bM\d{3}\b", conta).group(0)
        resposta = {"linhas": self.por_codigo.get(codigo, []), "resumo": "Comparada."}
        return httpx2.Response(200, json=mensagem(json.dumps(resposta)))


@pytest.fixture
def provedor(monkeypatch) -> _Provedor:
    duble = _Provedor()
    monkeypatch.setattr(ia, "_cliente", lambda: cliente_por_transporte(duble))
    monkeypatch.setattr(ia, "_esperar", lambda _segundos: None)
    return duble


def _dia(n: int) -> str:
    return f"2026-10-{n:02d}"


def _semear(banco) -> None:
    """Doze Contas concluídas da ALFA, uma por dia de 01 a 12/10, cada uma no
    seu atendimento e com o item M0nn; mais uma A fazer da ALFA e uma
    concluída da BETA, as duas mais novas que todas."""
    alfa, beta = _operadora_id(banco, "ALFA"), _operadora_id(banco, "BETA")
    versao = _versao(banco, "ALFA", "1.0")["id"]
    atendimentos, contas, itens, eventos = [], [], [], []

    def conta(n: int, operadora: str, situacao: str, concluida_em: str | None) -> None:
        atendimento = f"at-{n:02d}"
        atendimentos.append({"id": atendimento, "numero_atendimento": f"31{n:03d}", "operadora_id": operadora})
        contas.append(
            {
                "id": f"c{n:02d}",
                "atendimento_id": atendimento,
                "numero_conta": f"N{n:02d}",
                "situacao": situacao,
                "periodo_inicio": _dia(n),
                "periodo_fim": _dia(n),
                "concluida_em": concluida_em,
                "memoria_versao_id": versao,
                "nota_entrada": 90.0,
                "custo_usd": 0.5,
            }
        )
        itens.append(
            {
                "id": f"i{n:02d}",
                "conta_id": f"c{n:02d}",
                "ordem": 1,
                "data": _dia(n),
                "grupo_conta": "MATERIAL",
                "setor": "UTI",
                "grupo_procedimento": None,
                "codigo": f"M{n:03d}",
                "descricao": f"Item M{n:03d}",
                "quantidade": 1,
                "unidade": "UN",
                "valor_unitario": 10.0,
                "valor_total": 10.0,
                "percentual": 100.0,
            }
        )
        eventos.append(
            {
                "id": f"ev{n:02d}",
                "atendimento_id": atendimento,
                "criado_em": f"{_dia(n)}T08:00:00+00:00",
                "eventos_json": {
                    "arquivo_id": f"arq-{n:02d}",
                    "ia": {"movimentacoes": [], "prescricoes": [], "observacoes": [f"evento do dia {n}"]},
                },
            }
        )

    for n in range(1, 13):
        conta(n, alfa, "CONCLUIDA", f"{_dia(n)}T18:00:00+00:00")
    conta(13, alfa, "A_FAZER", None)
    conta(14, beta, "CONCLUIDA", f"{_dia(14)}T18:00:00+00:00")
    banco.tabelas["cm_atendimento"] = atendimentos
    banco.tabelas["cm_conta"] = contas
    banco.tabelas["cm_conta_item"] = itens
    banco.tabelas["cm_eventos"] = eventos
    banco.tabelas["cm_guia_linha"] = []


def _linha_do_guia(conta: str, codigo: str, dia: str, devida: float, estado: str = "ABERTA") -> dict[str, Any]:
    return {
        "id": f"g-{conta}-{codigo}",
        "conta_id": conta,
        "acao": "INCLUIR",
        "data": dia,
        "data_fim": None,
        "setor": "UTI",
        "codigo": codigo,
        "descricao": f"Item {codigo}",
        "quantidade_lancada": 1.0,
        "quantidade_devida": devida,
        "regra_codigo": "ALFA-DIA-01",
        "motivo": "Dado na evolução.",
        "estado": estado,
        "origem": "IA",
    }


@pytest.fixture
def cenario(provedor):
    cliente, banco = _cliente(GESTAO)
    _importar(cliente)
    _importar(cliente, "MEMORIA-BETA-v1.0.md")
    _semear(banco)
    return cliente, banco, provedor


def _da_conta(corpo: dict, conta_id: str) -> dict:
    return next(c for c in corpo["por_conta"] if c["conta_id"] == conta_id)


# ═══════════════════════════════════════════════════════════════════════════
# 1. O diff de Linhas por Conta, nas 10 últimas concluídas da Operadora
# ═══════════════════════════════════════════════════════════════════════════


class TestODiffPorConta:
    def test_a_prova_refaz_as_dez_ultimas_concluidas_da_operadora_e_so_dela(self, cenario):
        cliente, banco, provedor = cenario
        # c12 tinha uma Linha que a regra tira; c11, uma que muda de quantidade;
        # c10 ganha uma Linha que cita a regra nova.
        banco.tabelas["cm_guia_linha"] = [
            _linha_do_guia("c12", "M012", _dia(12), 2.0),
            _linha_do_guia("c11", "M011", _dia(11), 2.0),
        ]
        provedor.por_codigo = {
            "M011": [_linha_da_ia("M011", "11/10/2026", 3)],
            "M010": [_linha_da_ia("M010", "10/10/2026", 2)],
        }

        resposta = cliente.post(_rota(), json=REGRA)

        assert resposta.status_code == 200, resposta.text
        corpo = resposta.json()
        assert corpo["regra"] == CODIGO_NOVO
        assert corpo["contas"] == 10
        # As 10 mais novas da ALFA, da mais nova para a mais velha: nem a A
        # fazer, nem a da BETA, nem as duas mais velhas.
        assert [c["conta_id"] for c in corpo["por_conta"]] == [f"c{n:02d}" for n in range(12, 2, -1)]
        assert len(provedor.pedidos) == 10

        c12 = _da_conta(corpo, "c12")
        assert [(l["codigo"], l["quantidade_devida"]) for l in c12["sairiam"]] == [("M012", 2.0)]
        assert c12["entrariam"] == [] and c12["mudariam"] == []

        c11 = _da_conta(corpo, "c11")
        assert [(m["antes"]["quantidade_devida"], m["depois"]["quantidade_devida"]) for m in c11["mudariam"]] == [
            (2.0, 3.0)
        ]
        assert c11["entrariam"] == [] and c11["sairiam"] == []

        c10 = _da_conta(corpo, "c10")
        assert [(l["codigo"], l["regra_codigo"]) for l in c10["entrariam"]] == [("M010", CODIGO_NOVO)]

        assert all(not c["mudaria"] for c in corpo["por_conta"] if c["conta_id"] not in ("c10", "c11", "c12"))
        assert corpo["mudaria"] is True
        assert corpo["aviso"] is None

    def test_a_ia_recebe_a_memoria_com_a_regra_candidata_e_os_eventos_guardados(self, cenario):
        cliente, _banco, provedor = cenario

        assert cliente.post(_rota(), json=REGRA).status_code == 200

        pedido = next(p for p in provedor.pedidos if "M012" in p.split("CONTA\n", 1)[1])
        assert f"| {CODIGO_NOVO} | {REGRA['texto']} |" in pedido
        assert "evento do dia 12" in pedido


# ═══════════════════════════════════════════════════════════════════════════
# 2. A Linha Feito que sumiria e o "não mudaria nada"
# ═══════════════════════════════════════════════════════════════════════════


class TestFeitoENaoMudaria:
    def test_a_linha_feito_que_sumiria_vem_marcada(self, cenario):
        cliente, banco, _provedor = cenario
        banco.tabelas["cm_guia_linha"] = [
            _linha_do_guia("c12", "M012", _dia(12), 2.0, estado="FEITO"),
            _linha_do_guia("c11", "M011", _dia(11), 2.0, estado="ABERTA"),
        ]

        corpo = cliente.post(_rota(), json=REGRA).json()

        assert [(l["codigo"], l["feito"]) for l in _da_conta(corpo, "c12")["sairiam"]] == [("M012", True)]
        assert [(l["codigo"], l["feito"]) for l in _da_conta(corpo, "c11")["sairiam"]] == [("M011", False)]
        assert corpo["feitas_que_sumiriam"] == 1

    def test_prova_sem_mudanca_devolve_o_aviso_de_que_nao_mudaria_nada(self, cenario):
        cliente, banco, provedor = cenario
        # A IA devolve de novo a mesma Linha que o Guia já tinha.
        banco.tabelas["cm_guia_linha"] = [_linha_do_guia("c12", "M012", _dia(12), 2.0, estado="FEITO")]
        provedor.por_codigo = {"M012": [_linha_da_ia("M012", "12/10/2026", 2, regra="ALFA-DIA-01")]}

        corpo = cliente.post(_rota(), json=REGRA).json()

        assert corpo["mudaria"] is False
        assert corpo["aviso"] == "A regra não mudaria nada nas 10 últimas contas concluídas."
        assert corpo["feitas_que_sumiriam"] == 0
        assert all(c["entrariam"] == c["sairiam"] == c["mudariam"] == [] for c in corpo["por_conta"])


# ═══════════════════════════════════════════════════════════════════════════
# 3. Nada muda nas Contas, nas Linhas nem na Memória
# ═══════════════════════════════════════════════════════════════════════════

_INTOCADAS = ("cm_conta", "cm_guia_linha", "cm_conta_item", "cm_eventos", "cm_memoria_versao", "cm_regra")


class TestNadaMuda:
    def test_a_prova_nao_altera_conta_linha_nem_versao_da_memoria(self, cenario):
        cliente, banco, provedor = cenario
        banco.tabelas["cm_guia_linha"] = [
            _linha_do_guia("c12", "M012", _dia(12), 2.0, estado="FEITO"),
            _linha_do_guia("c11", "M011", _dia(11), 2.0),
        ]
        provedor.por_codigo = {
            "M011": [_linha_da_ia("M011", "11/10/2026", 3)],
            "M010": [_linha_da_ia("M010", "10/10/2026", 2)],
        }
        antes = {tabela: copy.deepcopy(banco.linhas(tabela)) for tabela in _INTOCADAS}
        com_parametro = {**REGRA, "parametro": {"chave": "diaria.hora_vencimento", "valor": "12:00"}}

        resposta = cliente.post(_rota(), json=com_parametro)

        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["mudaria"] is True
        assert {tabela: banco.linhas(tabela) for tabela in _INTOCADAS} == antes

    def test_a_prova_fica_guardada_com_o_resultado(self, cenario):
        cliente, banco, _provedor = cenario
        banco.tabelas["cm_guia_linha"] = [_linha_do_guia("c12", "M012", _dia(12), 2.0, estado="FEITO")]

        corpo = cliente.post(_rota(), json=REGRA).json()

        [prova] = banco.linhas("cm_prova")
        assert prova["id"] == corpo["prova_id"]
        assert prova["operadora_id"] == _operadora_id(banco, "ALFA")
        assert prova["memoria_versao_id"] == _versao(banco, "ALFA", "1.0")["id"]
        assert (prova["regra_codigo"], prova["regra_texto"]) == (CODIGO_NOVO, REGRA["texto"])
        assert (prova["contas"], prova["mudaria"]) == (10, True)
        assert prova["resultado_json"] == corpo["por_conta"]


# ═══════════════════════════════════════════════════════════════════════════
# 4. As chamadas da prova em cm_chamada_ia, com o passo PROVA
# ═══════════════════════════════════════════════════════════════════════════


def _passos_do_check() -> set[str]:
    sql = MIGRATION_126.read_text(encoding="utf-8")
    bloco = re.search(r"cm_chamada_ia_passo_check\s+CHECK \(passo IN \(([^)]*)\)\)", sql)
    return set(re.findall(r"'(\w+)'", bloco.group(1)))


class TestAsChamadasDaProva:
    def test_cada_conta_refeita_grava_uma_chamada_prova_sem_somar_na_conta(self, cenario):
        cliente, banco, _provedor = cenario

        assert cliente.post(_rota(), json=REGRA).status_code == 200

        chamadas = banco.linhas("cm_chamada_ia")
        assert [c["passo"] for c in chamadas] == ["PROVA"] * 10
        assert "PROVA" in _passos_do_check()
        assert sorted(c["atendimento_id"] for c in chamadas) == [f"at-{n:02d}" for n in range(3, 13)]
        # O custo da prova não entra na soma da Conta: a Conta não muda.
        assert all(c["conta_id"] is None for c in chamadas)
