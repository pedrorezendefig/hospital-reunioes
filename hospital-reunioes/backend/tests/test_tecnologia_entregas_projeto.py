"""O filtro Projeto nas Entregas (issue #1716, PRD #1710, ADR 0093, decisao 8,
e ADR 0092, decisao 7).

A rota das Entregas aceita o `projeto` (o Aplicativo do Hospital ou a Ana), que
vale para os dois numeros do topo, as 12 semanas do grafico e a lista por
semana, e combina com os outros filtros. Cada entrega da lista e da previa da
semana traz o Projeto, que vira o selo. Sem o filtro, os dois juntos.

Tudo pela ROTA, no molde de `test_tecnologia_entregas`.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from test_tecnologia_chat import _cenario  # noqa: E402
from test_tecnologia_entregas import AGORA, ENTREGAS, _entregue, _kit, _secao  # noqa: E402
from test_tecnologia_vinculo import DIRETOR, PEDRO, _demanda  # noqa: E402

from app.limiter import limiter  # noqa: E402
from app.routers.admin import tecnologia as tecnologia_router  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


def _demandas() -> list[dict]:
    """Com o relogio na sexta 13/11/2026: as 4 semanas do topo vao de 19/10 a
    15/11, e as 4 anteriores de 21/09 a 18/10. A Ana tem duas entregas no topo
    e uma nas anteriores, cada uma pedida uma semana antes; o Hospital, duas
    entregas no topo e um pedido ainda aberto. A Ana nao tem Em producao: a
    ultima Etapa dela e Entregue."""
    return [
        _entregue(
            "a-audio",
            50,
            "2026-11-04T12:00:00Z",
            etapa="entregue",
            projeto="ana",
            origem="vitta",
            titulo="Ana entende audio",
            tipo="defeito",
            partes_total=2,
            foto={"criada_em": "2026-10-28T12:00:00Z"},
        ),
        _entregue(
            "a-visita",
            51,
            "2026-10-21T12:00:00Z",
            etapa="entregue",
            projeto="ana",
            origem="vitta",
            titulo="Ana responde o horario da visita",
            tipo="novo",
            foto={"criada_em": "2026-10-20T12:00:00Z"},
        ),
        _entregue(
            "a-antiga",
            52,
            "2026-10-05T12:00:00Z",
            etapa="entregue",
            projeto="ana",
            origem="vitta",
            titulo="Ana marca a consulta",
            tipo="novo",
            foto={"criada_em": "2026-09-28T12:00:00Z"},
        ),
        _entregue(
            "h-botao",
            50,
            "2026-11-03T12:00:00Z",
            projeto="hospital",
            titulo="Botao de responder sumiu",
            tipo="defeito",
            autor_id=DIRETOR["id"],
            versao_em_producao="v0.280.0",
            foto={"criada_em": "2026-11-02T12:00:00Z"},
        ),
        _entregue(
            "h-relatorio",
            53,
            "2026-10-27T12:00:00Z",
            projeto="hospital",
            titulo="Relatorio por setor",
            tipo="novo",
            autor_id=DIRETOR["id"],
            foto={"criada_em": "2026-10-26T12:00:00Z"},
        ),
        _demanda(
            "h-aberto",
            github_issue_numero=54,
            projeto="hospital",
            etapa="em_desenvolvimento",
            titulo="Escala no celular",
            tipo="novo",
            autor_id=DIRETOR["id"],
            github_foto={"criada_em": "2026-11-10T12:00:00Z"},
        ),
    ]


@pytest.fixture
def entregas(monkeypatch):
    monkeypatch.setattr(tecnologia_router, "agora_utc", lambda: AGORA)

    def pedir(consulta: str = ""):
        client, _, _ = _cenario(monkeypatch, logado=PEDRO, participantes=[PEDRO, DIRETOR], demandas=_demandas())
        resposta = client.get(f"{ENTREGAS}?{consulta}" if consulta else ENTREGAS)
        assert resposta.status_code == 200, resposta.text
        return resposta.json()

    return pedir


def _ids(corpo: dict) -> list[str]:
    return [e["id"] for g in corpo["grupos"] for e in g["entregas"]]


def _semana(corpo: dict, inicio: str) -> dict:
    [semana] = [s for s in corpo["semanas"] if s["inicio"] == inicio]
    return semana


class TestFiltroProjeto:
    def test_com_ana_os_numeros_o_grafico_e_a_lista_contam_so_a_ana(self, entregas):
        corpo = entregas("projeto=ana")

        assert corpo["topo"] == {
            "pedidos": {"total": 2, "anteriores": 1, "bugs": 1, "melhorias": 1},
            "entregas": {"total": 2, "anteriores": 1, "g": 0, "m": 1, "p": 1},
        }
        assert [e["titulo"] for e in _semana(corpo, "2026-11-02")["entregas"]] == ["Ana entende audio"]
        assert _semana(corpo, "2026-11-09")["pedidos"] == 0
        assert _semana(corpo, "2026-10-26") == {
            "inicio": "2026-10-26",
            "pedidos": 1,
            "g": 0,
            "m": 0,
            "p": 0,
            "entregas": [],
        }
        assert _ids(corpo) == ["a-audio", "a-visita", "a-antiga"]

    def test_com_o_aplicativo_do_hospital_a_ana_fica_fora(self, entregas):
        corpo = entregas("projeto=hospital")

        assert corpo["topo"]["entregas"]["total"] == 2
        assert corpo["topo"]["pedidos"]["total"] == 3
        assert _ids(corpo) == ["h-botao", "h-relatorio"]

    def test_sem_o_filtro_os_dois_projetos_entram(self, entregas):
        """O Todos da tela: a rota sem `projeto`."""
        corpo = entregas()

        assert corpo["topo"]["entregas"] == {"total": 4, "anteriores": 1, "g": 0, "m": 1, "p": 3}
        assert _ids(corpo) == ["a-audio", "h-botao", "h-relatorio", "a-visita", "a-antiga"]

    def test_o_projeto_combina_com_os_outros_filtros(self, entregas):
        assert _ids(entregas("projeto=ana&tipo=bug")) == ["a-audio"]
        assert _ids(entregas("projeto=hospital&tipo=bug")) == ["h-botao"]

    def test_o_projeto_vale_para_as_semanas_anteriores(self, entregas):
        """Ver semanas anteriores (issue #1704) com o mesmo filtro."""
        corpo = entregas("projeto=hospital&corte=2026-11-09")

        assert _ids(corpo) == ["h-botao", "h-relatorio"]
        assert corpo["proximo_corte"] is None

    def test_projeto_desconhecido_e_recusado(self, monkeypatch):
        monkeypatch.setattr(tecnologia_router, "agora_utc", lambda: AGORA)
        client, _, _ = _cenario(monkeypatch, logado=PEDRO, participantes=[PEDRO], demandas=_demandas())

        assert client.get(f"{ENTREGAS}?projeto=outro").status_code == 422


class TestSeloDoProjeto:
    def test_a_entrega_da_lista_traz_o_projeto(self, entregas):
        projetos = {e["id"]: e["projeto"] for g in entregas()["grupos"] for e in g["entregas"]}

        assert projetos == {
            "a-audio": "ana",
            "a-visita": "ana",
            "a-antiga": "ana",
            "h-botao": "hospital",
            "h-relatorio": "hospital",
        }

    def test_a_previa_da_semana_traz_o_projeto_de_cada_entrega(self, entregas):
        """A semana de 02/11 tem uma entrega de cada Projeto, a mais nova em cima."""
        assert _semana(entregas(), "2026-11-02")["entregas"] == [
            {"titulo": "Ana entende audio", "tamanho": "M", "projeto": "ana"},
            {"titulo": "Botao de responder sumiu", "tamanho": "P", "projeto": "hospital"},
        ]


class TestKit:
    def test_o_kit_diz_que_as_entregas_filtram_por_projeto(self):
        """O Assistente fala pela lingua do Kit (ADR 0093, decisao 8)."""
        secao = _secao("As Entregas")

        for trecho in ("**Projeto**", "Aplicativo do Hospital", "Ana", "selo", "sem versão"):
            assert trecho in secao, trecho
        assert _kit().count("## As Entregas") == 1
