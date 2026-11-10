"""O segundo agente: a releitura das Contas concluídas (issue #1493, PRD
#1484, ADR 0081, decisão 14; botão no Painel desde a ADR 0082, issue #1523).

Quando alguém com o painel completo clica, ele sorteia até 10 Contas
concluídas que ainda não revisou, relê os eventos guardados de cada uma
procurando o que o prontuário registra como administrado e não está nos itens
da Conta, e grava cada achado como Faltou isto de origem AGENTE, já com a
classificação e a explicação. Nenhum job do agendador o chama.

O serviço é chamado direto ou pela rota do Painel, com o dublê do banco da
carga da operadora e as Contas concluídas da Prova da regra (12 da ALFA, uma
da BETA, uma A fazer). O provedor da IA é dublado no transporte HTTP (o
adaptador roda inteiro) e responde pela Conta do pedido, pelo código do item
dela.
"""

from __future__ import annotations

import json
import re
from typing import Any

import httpx2
import pytest
from anthropic_apoio import cliente_por_transporte, erro, mensagem
from test_contas_medicas_memoria_tela import _importar, _versao
from test_contas_medicas_operadoras import FATURISTA, GESTAO
from test_contas_medicas_prova_da_regra import KIT, _passos_do_check, _semear
from test_contas_medicas_regra_nova import _cliente

from app.routers import contas_medicas_painel as painel_router
from app.services.contas_medicas import ia, revisor

CONCLUIDAS = {f"c{n:02d}" for n in range(1, 13)} | {"c14"}


def _achado(dia: str, item: str = "Equipo macrogotas", pagina: int = 3) -> dict[str, Any]:
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
        self.falha = False

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        if self.falha:
            return erro(529, "overloaded_error", "Overloaded")
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
    da_beta = next(c for c in banco.linhas("cm_conta") if c["id"] == "c14")
    da_beta["memoria_versao_id"] = _versao(banco, "BETA", "1.0")["id"]
    return banco, provedor


def _revisadas(banco) -> list[str]:
    return [c["conta_id"] for c in banco.linhas("cm_chamada_ia") if c["passo"] == "REVISOR"]


class TestOsAchados:
    def test_o_achado_vira_faltou_isto_do_agente_com_a_explicacao(self, cenario):
        banco, provedor = cenario
        provedor.por_codigo = {f"M{n:03d}": [_achado(f"2026-10-{n:02d}")] for n in range(1, 15)}

        revisor.revisar_concluidas(banco)

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

    def test_achado_fora_do_periodo_ou_sem_item_nao_e_gravado(self, cenario):
        banco, provedor = cenario
        # Cada Conta tem um dia só (c03 = 03/10): o 20/10 não é dela.
        provedor.por_codigo = {
            f"M{n:03d}": [_achado("2026-10-20"), _achado(f"2026-10-{n:02d}", item="  ")] for n in range(1, 15)
        }

        revisor.revisar_concluidas(banco)

        assert len(_revisadas(banco)) == 10
        assert banco.linhas("cm_faltou_isto") == []


class TestAAmostra:
    def test_sorteia_ate_dez_concluidas_sem_repetir_a_ja_revisada(self, cenario):
        banco, provedor = cenario

        revisor.revisar_concluidas(banco)
        primeira = _revisadas(banco)
        revisor.revisar_concluidas(banco)
        segunda = _revisadas(banco)[len(primeira) :]
        revisor.revisar_concluidas(banco)

        # 13 concluídas (12 da ALFA e a da BETA); a A fazer, c13, nunca entra.
        assert len(primeira) == 10 and len(set(primeira)) == 10
        assert set(primeira).isdisjoint(segunda)
        assert set(primeira) | set(segunda) == CONCLUIDAS
        # Na terceira semana não sobra Conta a revisar.
        assert len(_revisadas(banco)) == 13
        assert len(provedor.pedidos) == 13

    def test_a_conta_cuja_revisao_falhou_volta_ao_sorteio(self, cenario):
        banco, provedor = cenario
        provedor.falha = True

        revisor.revisar_concluidas(banco)
        provedor.falha = False
        revisor.revisar_concluidas(banco)

        # A primeira semana falhou nas 10: a segunda ainda acha 10 a revisar.
        assert len([c for c in banco.linhas("cm_chamada_ia") if c["sucesso"]]) == 10


class TestAsChamadas:
    def test_cada_conta_revisada_grava_uma_chamada_revisor_com_a_conta(self, cenario):
        banco, _provedor = cenario

        revisor.revisar_concluidas(banco)

        chamadas = banco.linhas("cm_chamada_ia")
        assert [c["passo"] for c in chamadas] == ["REVISOR"] * 10
        assert "REVISOR" in _passos_do_check()
        assert all(c["conta_id"] in CONCLUIDAS for c in chamadas)
        assert all(c["atendimento_id"] == f"at-{c['conta_id'][1:]}" for c in chamadas)


ROTA_DO_SEGUNDO_AGENTE = "/api/contas-medicas/painel/segundo-agente"


def _no_painel(banco, pessoa=GESTAO):
    """O app da carga com a rota do Painel, para a pessoa."""
    cliente, _banco = _cliente(pessoa, banco)
    cliente.app.include_router(painel_router.router, prefix="/api")
    return cliente


class TestOBotaoDoPainel:
    def test_nenhum_job_do_agendador_chama_o_segundo_agente(self):
        from app.cron import scheduler as cron

        try:
            cron.start_scheduler()
            assert cron.scheduler.get_job("revisor_contas_medicas") is None
        finally:
            cron.stop_scheduler()
        assert not hasattr(cron, "revisar_contas_medicas")

    def test_o_botao_mostra_quantas_contas_e_o_custo_antes_do_clique(self, cenario):
        banco, provedor = cenario

        pedido = _no_painel(banco).get(ROTA_DO_SEGUNDO_AGENTE)

        assert pedido.status_code == 200, pedido.text
        corpo = pedido.json()
        assert (corpo["contas"], corpo["em_andamento"]) == (10, False)
        assert corpo["custo_estimado_usd"] == pytest.approx(10 * revisor.CUSTO_POR_CONTA_USD)
        assert provedor.pedidos == []

    def test_o_clique_rele_as_contas_e_grava_o_faltou_isto(self, cenario):
        banco, provedor = cenario
        provedor.por_codigo = {f"M{n:03d}": [_achado(f"2026-10-{n:02d}")] for n in range(1, 15)}

        resposta = _no_painel(banco).post(ROTA_DO_SEGUNDO_AGENTE)

        assert resposta.status_code == 202, resposta.text
        assert len(_revisadas(banco)) == 10
        assert {f["origem"] for f in banco.linhas("cm_faltou_isto")} == {"AGENTE"}
        assert len(banco.linhas("cm_faltou_isto")) == 10
        assert _no_painel(banco).get(ROTA_DO_SEGUNDO_AGENTE).json()["contas"] == 3

    def test_segundo_clique_enquanto_o_primeiro_roda_nao_dispara_outra_rodada(self, cenario):
        banco, provedor = cenario
        assert revisor.reservar()
        try:
            assert _no_painel(banco).get(ROTA_DO_SEGUNDO_AGENTE).json()["em_andamento"] is True
            resposta = _no_painel(banco).post(ROTA_DO_SEGUNDO_AGENTE)
        finally:
            revisor.liberar()

        assert resposta.status_code == 409
        assert provedor.pedidos == []

    def test_so_quem_tem_o_painel_completo_chama_o_segundo_agente(self, cenario):
        banco, provedor = cenario

        assert _no_painel(banco, FATURISTA).post(ROTA_DO_SEGUNDO_AGENTE).status_code == 403
        assert _no_painel(banco, FATURISTA).get(ROTA_DO_SEGUNDO_AGENTE).status_code == 403
        assert provedor.pedidos == []


class TestOKit:
    def test_o_kit_diz_que_o_segundo_agente_rele_dez_contas_quando_alguem_pede(self):
        no_ar = KIT.read_text(encoding="utf-8").split("## O que já está no ar")[1].split("\n## ")[0]

        for termo in (
            "segundo agente",
            "Reler contas concluídas",
            "10 contas concluídas",
            "ainda não revisou",
            "achado pelo agente",
        ):
            assert termo in no_ar, termo
