"""O modelo e o custo da conversa no cabeçalho do chat (issue #1439, PRD #1436).

ADR 0079, decisão 6, que emenda a decisão 9 da ADR 0077: a resposta do chat,
ao abrir a conversa e em cada turno, traz o modelo da chamada mais recente (no
nome de exibição) e a soma em dólar das chamadas de IA gravadas daquela
Demanda. Uma chamada com tokens e custo zero é o preço ausente que o código já
grava: a soma vira nula, e a tela diz "custo não medido". Tudo pela ROTA, com o
modelo dublado no molde de `test_tecnologia_chat`.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from test_planejamento_demanda import _ia, _uso  # noqa: E402
from test_tecnologia_chat import CHAT, _cenario, _chamadas, _comecar, _turno  # noqa: E402

from app.config import settings  # noqa: E402
from app.limiter import limiter  # noqa: E402
from app.services.conhecimento import CONHECIMENTO_DIR  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


@pytest.fixture(autouse=True)
def _integracao_configurada(monkeypatch):
    monkeypatch.setattr(settings, "github_integracao_token", "token-de-teste")
    monkeypatch.setattr(settings, "github_integracao_repo", "pedrorezendefig/hospital-reunioes")


def _chamada(demanda_id: str | None, *, custo: float, modelo: str = "claude-opus-5-5", criado_em: str, **kw) -> dict:
    return {
        "demanda_id": demanda_id,
        "passo": "pergunta",
        "modelo": modelo,
        "tokens_entrada": kw.get("entrada", 1000),
        "tokens_saida": kw.get("saida", 200),
        "tokens_cache": 0,
        "custo_usd": custo,
        "duracao_ms": 900,
        "sucesso": True,
        "criado_em": criado_em,
    }


def _conversa_com(monkeypatch, *chamadas_de) -> tuple:
    """Uma conversa guardada cujas chamadas gravadas são só as dadas."""
    client, sb, _ = _cenario(monkeypatch)
    demanda_id = _comecar(client, monkeypatch)
    _chamadas(sb).clear()
    _chamadas(sb).extend(c(demanda_id) for c in chamadas_de)
    return client, sb, demanda_id


class TestCustoAoAbrirAConversa:
    def test_duas_chamadas_com_preco_somam_o_custo_exato(self, monkeypatch):
        client, _, demanda_id = _conversa_com(
            monkeypatch,
            lambda d: _chamada(d, custo=1.234567, criado_em="2026-11-06T10:00:00Z"),
            lambda d: _chamada(d, custo=0.605433, criado_em="2026-11-06T10:05:00Z"),
        )

        custo = client.get(f"{CHAT}/{demanda_id}").json()["custo"]

        assert custo["custo_usd"] == 1.84

    def test_chamada_com_tokens_e_custo_zero_deixa_o_custo_nulo(self, monkeypatch):
        """Custo zero com tokens é o modelo sem preço na tabela: somar o zero
        daria um valor menor que o de verdade, com cara de exato."""
        client, _, demanda_id = _conversa_com(
            monkeypatch,
            lambda d: _chamada(d, custo=1.20, criado_em="2026-11-06T10:00:00Z"),
            lambda d: _chamada(d, custo=0, modelo="claude-fable-6-0", criado_em="2026-11-06T10:05:00Z"),
        )

        custo = client.get(f"{CHAT}/{demanda_id}").json()["custo"]

        assert custo == {"modelo": "Fable 6.0", "custo_usd": None}

    def test_chamadas_de_outra_demanda_nao_entram_na_soma(self, monkeypatch):
        client, sb, demanda_id = _conversa_com(
            monkeypatch,
            lambda d: _chamada(d, custo=0.50, criado_em="2026-11-06T10:00:00Z"),
        )
        _chamadas(sb).append(_chamada("outra-demanda", custo=9.99, criado_em="2026-11-06T10:01:00Z"))
        _chamadas(sb).append(_chamada(None, custo=3.00, criado_em="2026-11-06T10:02:00Z"))

        custo = client.get(f"{CHAT}/{demanda_id}").json()["custo"]

        assert custo["custo_usd"] == 0.5

    def test_o_modelo_exibido_e_o_da_chamada_mais_recente(self, monkeypatch):
        """A gravação fora de ordem no banco não engana: vale o `criado_em`."""
        client, _, demanda_id = _conversa_com(
            monkeypatch,
            lambda d: _chamada(d, custo=0.10, modelo="claude-opus-5-5", criado_em="2026-11-06T10:05:00Z"),
            lambda d: _chamada(d, custo=0.10, modelo="claude-sonnet-5-5", criado_em="2026-11-06T10:00:00Z"),
        )

        custo = client.get(f"{CHAT}/{demanda_id}").json()["custo"]

        assert custo["modelo"] == "Opus 5.5"

    def test_conversa_com_print_deixa_o_custo_nulo(self, monkeypatch):
        """A leitura do print chama a IA e não grava a chamada em lugar nenhum:
        somar só o resto daria um valor menor que o de verdade, com cara de
        exato (revisão do PR #1443)."""
        client, sb, demanda_id = _conversa_com(
            monkeypatch,
            lambda d: _chamada(d, custo=1.20, criado_em="2026-11-06T10:00:00Z"),
        )
        sb.tabelas.setdefault("tecnologia_anexos", []).append(
            {"demanda_id": demanda_id, "ordem": 1, "storage_path": "x/print.png", "apagado_em": None}
        )

        custo = client.get(f"{CHAT}/{demanda_id}").json()["custo"]

        assert custo == {"modelo": "Opus 5.5", "custo_usd": None}

    def test_conversa_com_documento_continua_somando_os_turnos(self, monkeypatch):
        """O documento é lido sem IA (issue #1520): não há chamada fora da
        tabela, e o custo dos turnos com documento é o que está gravado."""
        client, sb, demanda_id = _conversa_com(
            monkeypatch,
            lambda d: _chamada(d, custo=1.20, criado_em="2026-11-06T10:00:00Z"),
            lambda d: _chamada(d, custo=0.64, criado_em="2026-11-06T10:05:00Z"),
        )
        sb.tabelas.setdefault("tecnologia_anexos", []).append(
            {
                "demanda_id": demanda_id,
                "ordem": 1,
                "storage_path": "x/melhorias.md",
                "content_type": "text/markdown",
                "apagado_em": None,
            }
        )

        custo = client.get(f"{CHAT}/{demanda_id}").json()["custo"]

        assert custo == {"modelo": "Opus 5.5", "custo_usd": 1.84}

    def test_sem_chamada_nenhuma_nao_ha_custo(self, monkeypatch):
        client, _, demanda_id = _conversa_com(monkeypatch)

        assert client.get(f"{CHAT}/{demanda_id}").json()["custo"] is None


class TestCustoEmCadaTurno:
    def test_o_turno_devolve_o_custo_ja_com_a_chamada_dele(self, monkeypatch):
        client, _, demanda_id = _conversa_com(
            monkeypatch,
            lambda d: _chamada(d, custo=1.812, criado_em="2026-11-06T10:00:00Z"),
        )
        monkeypatch.setattr(settings, "llm_model_planejamento", "claude-opus-5-5")
        # 1000*4 + 500*20 + 20000*0,20 + 2000*5 = 28000 por milhão (Opus 5.5)
        _ia(monkeypatch, _turno(), usage=_uso(entrada=1000, saida=500, lidos=20000, escritos=2000))

        resposta = client.post(f"{CHAT}/{demanda_id}", json={"texto": "Na Ouvidoria"})

        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["custo"] == {"modelo": "Opus 5.5", "custo_usd": 1.84}


class TestKitDizOCusto:
    def test_o_kit_diz_o_custo_no_alto_da_conversa_e_o_que_e_custo_nao_medido(self):
        """O kit é a língua do Assistente: sem o custo escrito, ele não saberia
        explicar ao diretor o número no alto da conversa."""
        texto = (CONHECIMENTO_DIR / "tecnologia.md").read_text(encoding="utf-8")

        secao = texto.split("## A conversa com o Assistente", 1)[1].split("\n## ", 1)[0]
        paragrafo = next(p for p in secao.split("\n\n") if "custo não medido" in p)
        for trecho in ("no alto da conversa", "dólar", "não está na lista", "sem preço", "a conversa tem print"):
            assert trecho in paragrafo, trecho


class TestCustoForaDaLista:
    def test_a_lista_lateral_nao_traz_custo(self, monkeypatch):
        client, _, _ = _conversa_com(
            monkeypatch,
            lambda d: _chamada(d, custo=1.84, criado_em="2026-11-06T10:00:00Z"),
        )

        [item] = client.get(CHAT).json()

        assert not any("custo" in chave or "modelo" in chave for chave in item)
