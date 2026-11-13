"""O filtro Projeto da lista e do Quadro (issue #1715, PRD #1710, ADR 0093, decisao 8).

A rota da lista aceita o `projeto` (o Aplicativo do Hospital ou a Ana), que
combina com o recorte e com os outros filtros, e devolve o Projeto de cada
Demanda, que vira o selo do card. Sem o filtro, a lista traz os dois Projetos
juntos, como o "Todos" da tela.

Tudo pela ROTA, no molde de `test_tecnologia_lista_filtros`.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from test_tecnologia_chat import CHAT, _cenario  # noqa: E402
from test_tecnologia_vinculo import DIRETOR, PEDRO, _demanda  # noqa: E402

from app.limiter import limiter  # noqa: E402
from app.services.conhecimento import CONHECIMENTO_DIR  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


def _demandas() -> list[dict]:
    """Duas do Hospital e duas da Ana, a mais recente primeiro. A ultima nao tem
    a coluna, como a linha de antes da migration 145: e do Hospital."""
    sem_coluna = _demanda(
        "d-hospital-antiga",
        titulo="Escala some no domingo",
        github_issue_numero=50,
        tipo="defeito",
        autor_id=DIRETOR["id"],
        criado_em="2026-11-01T10:00:00Z",
    )
    del sem_coluna["projeto"]
    return [
        _demanda(
            "d-ana-1",
            titulo="Ana responde o horario da visita",
            projeto="ana",
            github_issue_numero=50,
            tipo="novo",
            autor_id=DIRETOR["id"],
            criado_em="2026-11-05T10:00:00Z",
        ),
        _demanda(
            "d-hospital-1",
            titulo="Aviso quando a ata sair",
            projeto="hospital",
            github_issue_numero=51,
            tipo="novo",
            autor_id=DIRETOR["id"],
            criado_em="2026-11-04T10:00:00Z",
        ),
        _demanda(
            "d-ana-2",
            titulo="Ana nao entende audio",
            projeto="ana",
            github_issue_numero=7,
            tipo="defeito",
            autor_id=DIRETOR["id"],
            criado_em="2026-11-03T10:00:00Z",
        ),
        sem_coluna,
    ]


@pytest.fixture
def lista(monkeypatch):
    def pedir(logado: dict, consulta: str = ""):
        client, _, _ = _cenario(monkeypatch, logado=logado, participantes=[PEDRO, DIRETOR], demandas=_demandas())
        return client.get(f"{CHAT}?{consulta}" if consulta else CHAT)

    return pedir


def _ids(resposta) -> list[str]:
    assert resposta.status_code == 200, resposta.text
    return [d["id"] for d in resposta.json()]


class TestFiltroProjeto:
    def test_com_ana_a_lista_traz_so_as_demandas_da_ana(self, lista):
        assert _ids(lista(DIRETOR, "projeto=ana")) == ["d-ana-1", "d-ana-2"]

    def test_com_hospital_a_lista_traz_so_as_do_aplicativo_inclusive_a_de_antes_da_coluna(self, lista):
        assert _ids(lista(DIRETOR, "projeto=hospital")) == ["d-hospital-1", "d-hospital-antiga"]

    def test_sem_o_filtro_a_lista_traz_os_dois_projetos(self, lista):
        assert _ids(lista(DIRETOR)) == ["d-ana-1", "d-hospital-1", "d-ana-2", "d-hospital-antiga"]

    @pytest.mark.parametrize(
        ("consulta", "esperado"),
        [
            ("filtro=todas&projeto=ana&tipo=bug", ["d-ana-2"]),
            ("filtro=todas&projeto=hospital&busca=ata", ["d-hospital-1"]),
        ],
    )
    def test_o_projeto_combina_com_os_outros_filtros(self, lista, consulta, esperado):
        assert _ids(lista(PEDRO, consulta)) == esperado

    def test_projeto_desconhecido_e_recusado(self, lista):
        assert lista(DIRETOR, "projeto=outro").status_code == 422


class TestProjetoDeCadaDemanda:
    def test_a_lista_devolve_o_projeto_de_cada_demanda(self, lista):
        resposta = lista(DIRETOR)

        assert resposta.status_code == 200, resposta.text
        assert {d["id"]: d["projeto"] for d in resposta.json()} == {
            "d-ana-1": "ana",
            "d-hospital-1": "hospital",
            "d-ana-2": "ana",
            "d-hospital-antiga": "hospital",
        }


class TestKit:
    def test_o_kit_diz_como_filtrar_por_projeto_e_que_os_pedidos_da_ana_aparecem_ali(self):
        """O Assistente fala pela lingua do Kit: sem isto, ele diria que a aba
        so tem os pedidos do aplicativo."""
        abertura = (CONHECIMENTO_DIR / "tecnologia.md").read_text(encoding="utf-8").split("\n## ", 1)[0]
        for trecho in ("**Projeto**", "**Aplicativo do Hospital**", "**Ana**", "selo", "Todos", "Limpar filtros"):
            assert trecho in abertura, trecho
        assert "pedidos da Ana aparecem" in abertura
