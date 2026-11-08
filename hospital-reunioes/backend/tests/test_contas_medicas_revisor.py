"""O segundo agente: a releitura semanal das Contas concluídas (issue #1493,
PRD #1484, ADR 0081, decisão 14).

Toda semana o job sorteia até 10 Contas concluídas que ele ainda não revisou,
relê os eventos guardados de cada uma procurando o que o prontuário registra
como administrado e não está nos itens da Conta, e grava cada achado como
Faltou isto de origem AGENTE, já com a classificação e a explicação.

O job é chamado direto, com o dublê do banco da carga da operadora e as Contas
concluídas da Prova da regra (12 da ALFA, uma da BETA, uma A fazer). O
provedor da IA é dublado no transporte HTTP (o adaptador roda inteiro) e
responde pela Conta do pedido, pelo código do item dela.
"""

from __future__ import annotations

import json
import re
from typing import Any

import httpx2
import pytest
from anthropic_apoio import cliente_por_transporte, mensagem
from test_contas_medicas_memoria_tela import _importar, _versao
from test_contas_medicas_operadoras import GESTAO
from test_contas_medicas_prova_da_regra import _passos_do_check, _semear
from test_contas_medicas_regra_nova import _cliente

from app.services.contas_medicas import ia, revisor

CONCLUIDAS = {f"c{n:02d}" for n in range(1, 13)} | {"c14"}


def _achado(dia: str, item: str = "Equipo macrogotas", pagina: int | None = 3) -> dict[str, Any]:
    return {
        "data": dia,
        "item": item,
        "pagina": pagina,
        "classificacao": "DEFEITO",
        "explicacao": "A página 3 registra o acesso periférico instalado, e a conta não tem o equipo.",
        "esperado": "Incluir 1 equipo macrogotas no dia, pelo acesso periférico.",
    }


class _Provedor:
    """A Anthropic do teste: responde a revisão pela Conta do pedido (o código
    do item dela) e guarda o texto de cada pedido."""

    def __init__(self):
        self.pedidos: list[str] = []
        self.por_codigo: dict[str, list[dict]] = {}

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        corpo = json.loads(request.content)
        texto = "\n".join(bloco["text"] for m in corpo["messages"] for bloco in m["content"])
        self.pedidos.append(texto)
        codigo = re.search(r"\bM\d{3}\b", texto.split("A CONTA CONCLUÍDA\n", 1)[1]).group(0)
        resposta = {"achados": self.por_codigo.get(codigo, [])}
        return httpx2.Response(200, json=mensagem(json.dumps(resposta)))


@pytest.fixture
def cenario(monkeypatch):
    provedor = _Provedor()
    monkeypatch.setattr(ia, "_cliente", lambda: cliente_por_transporte(provedor))
    monkeypatch.setattr(ia, "_esperar", lambda _segundos: None)
    cliente, banco = _cliente(GESTAO)
    _importar(cliente)
    _importar(cliente, "MEMORIA-BETA-v1.0.md")
    _semear(banco)
    # A da BETA foi analisada com a memória da BETA.
    next(c for c in banco.linhas("cm_conta") if c["id"] == "c14")["memoria_versao_id"] = _versao(banco, "BETA", "1.0")["id"]
    return banco, provedor


def _revisadas(banco) -> list[str]:
    return [c["conta_id"] for c in banco.linhas("cm_chamada_ia") if c["passo"] == "REVISOR"]


class TestOsAchados:
    def test_o_achado_vira_faltou_isto_do_agente_com_a_explicacao(self, cenario):
        banco, provedor = cenario
        provedor.por_codigo = {f"M{n:03d}": [_achado(f"2026-10-{n:02d}")] for n in range(1, 15)}

        revisor.revisar_semana(banco)

        gravados = banco.linhas("cm_faltou_isto")
        revisadas = _revisadas(banco)
        assert sorted(f["conta_id"] for f in gravados) == sorted(revisadas)
        gravado = gravados[0]
        n = int(gravado["conta_id"][1:])
        assert {chave: gravado[chave] for chave in ("data", "item", "pagina", "origem", "classificacao")} == {
            "data": f"2026-10-{n:02d}",
            "item": "Equipo macrogotas",
            "pagina": 3,
            "origem": "AGENTE",
            "classificacao": "DEFEITO",
        }
        assert gravado.get("apontado_por") is None
        assert gravado["explicacao"] == (
            "A página 3 registra o acesso periférico instalado, e a conta não tem o equipo.\n\n"
            "O Guia deveria ter apontado: Incluir 1 equipo macrogotas no dia, pelo acesso periférico."
        )
        assert gravado["classificado_em"]
