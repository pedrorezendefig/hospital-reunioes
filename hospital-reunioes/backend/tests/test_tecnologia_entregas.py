"""A aba Entregas da Tecnologia (issue #1556, PRD #1548, ADR 0084, decisao 8).

A rota de leitura conta por card os entregues por semana ou por mes, com a
data de entrega (o fechamento da issue-raiz), a data em producao e o
Responsavel, e filtra por periodo, tipo, Origem e Responsavel. Card apagado e
card nao entregue ficam fora. Ninguem escreve por ela.

Tudo pela ROTA, no molde de `test_tecnologia_lista_filtros`.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from test_tecnologia_chat import _cenario  # noqa: E402
from test_tecnologia_vinculo import BASE, DIRETOR, PEDRO, _demanda, _pessoa  # noqa: E402

from app.limiter import limiter  # noqa: E402
from app.services.conhecimento import CONHECIMENTO_DIR  # noqa: E402

ENTREGAS = f"{BASE}/entregas"

RIB = _pessoa("P4", "Pedro Rib", github_login="pedrorib")
OUTRA_DIRETORA = _pessoa("P7", "Outra Diretora")
# Tem acesso ao app, mas nao e Super admin: nao ve a aba.
FACILITADOR = _pessoa("P8", "Facilitador", access_profile="facilitador")


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


def _entregue(did: str, numero: int, fechada_em: str, **campos) -> dict:
    campos.setdefault("etapa", "em_producao")
    foto = {"fechada_em": fechada_em, **campos.pop("foto", {})}
    return _demanda(did, github_issue_numero=numero, github_foto=foto, **campos)


def _demandas() -> list[dict]:
    """As datas sao fixas. O hospital fica em Sao Paulo (UTC-3): o fechamento
    as 01h de 02/11 em UTC e o domingo 01/11 no hospital, semana de 26/10; o das
    02h de 01/11 em UTC e o sabado 31/10, mes de outubro."""
    return [
        _entregue(
            "e-bug-diretor",
            901,
            "2026-11-03T12:00:00Z",
            titulo="Botao de responder sumiu",
            tipo="defeito",
            autor_id=DIRETOR["id"],
            responsavel_id=PEDRO["id"],
            em_producao_em="2026-11-04T15:00:00Z",
        ),
        _entregue(
            "e-vitta-rib",
            902,
            "2026-11-05T20:00:00Z",
            etapa="entregue",
            titulo="Aviso quando a ata sair",
            tipo="novo",
            origem="vitta",
            autor_id=PEDRO["id"],
            responsavel_id=RIB["id"],
        ),
        _entregue(
            "e-domingo",
            903,
            "2026-11-02T01:00:00Z",
            titulo="Relatorio por setor",
            tipo="novo",
            autor_id=DIRETOR["id"],
            responsavel_id=PEDRO["id"],
            em_producao_em="2026-11-02T18:00:00Z",
        ),
        _entregue(
            "e-vitta-terceiro",
            904,
            "2026-11-01T02:00:00Z",
            titulo="Impressao da escala",
            tipo="defeito",
            origem="vitta",
            autor_id=PEDRO["id"],
            responsavel_id=None,
            foto={"assignee": "terceiro-gh"},
        ),
        _entregue(
            "e-outra-diretora",
            905,
            "2026-10-15T12:00:00Z",
            titulo="Painel da outra diretora",
            tipo="novo",
            autor_id=OUTRA_DIRETORA["id"],
            responsavel_id=PEDRO["id"],
        ),
        # Fora: apagado, ainda em desenvolvimento, e fechado como nao planejado.
        _entregue(
            "x-apagado",
            906,
            "2026-11-03T12:00:00Z",
            titulo="Apagado",
            autor_id=DIRETOR["id"],
            apagada_em="2026-11-06T10:00:00Z",
        ),
        _demanda(
            "x-em-desenvolvimento",
            github_issue_numero=907,
            etapa="em_desenvolvimento",
            titulo="Ainda sendo feito",
            autor_id=DIRETOR["id"],
        ),
        _entregue(
            "x-nao-sera-feita",
            908,
            "2026-11-03T12:00:00Z",
            etapa="nao_sera_feita",
            titulo="Nao sera feita",
            autor_id=DIRETOR["id"],
        ),
    ]


@pytest.fixture
def entregas(monkeypatch):
    def pedir(logado: dict, consulta: str = ""):
        client, _, _ = _cenario(
            monkeypatch,
            logado=logado,
            participantes=[PEDRO, DIRETOR, RIB, OUTRA_DIRETORA, FACILITADOR],
            demandas=_demandas(),
        )
        return client.get(f"{ENTREGAS}?{consulta}" if consulta else ENTREGAS)

    return pedir


def _corpo(resposta) -> dict:
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


def _periodos(resposta) -> list[tuple[str, int]]:
    return [(p["inicio"], p["total"]) for p in _corpo(resposta)["periodos"]]


def _ids(resposta) -> list[str]:
    return [d["id"] for d in _corpo(resposta)["entregas"]]


# ═══════════════════════════════════════════════════════════════════════════
# 1. A contagem por semana e por mes
# ═══════════════════════════════════════════════════════════════════════════


class TestContagem:
    def test_a_semana_comeca_na_segunda_e_conta_pelo_dia_do_hospital(self, entregas):
        assert _periodos(entregas(PEDRO, "agrupar=semana")) == [
            ("2026-11-02", 2),
            ("2026-10-26", 2),
            ("2026-10-12", 1),
        ]

    def test_o_mes_conta_pelo_dia_do_hospital(self, entregas):
        assert _periodos(entregas(PEDRO, "agrupar=mes")) == [("2026-11-01", 3), ("2026-10-01", 2)]

    def test_sem_agrupar_a_contagem_e_por_semana(self, entregas):
        corpo = _corpo(entregas(PEDRO))

        assert corpo["agrupar"] == "semana"
        assert corpo["periodos"][0] == {"inicio": "2026-11-02", "total": 2}

    def test_a_lista_vem_da_entrega_mais_recente_para_a_mais_antiga(self, entregas):
        assert _ids(entregas(PEDRO)) == [
            "e-vitta-rib",
            "e-bug-diretor",
            "e-domingo",
            "e-vitta-terceiro",
            "e-outra-diretora",
        ]

    def test_o_diretor_conta_as_dele_e_as_da_vitta(self, entregas):
        """A mesma regra da lista do chat (`pode_ver`): o pedido de outra
        diretora nao entra, nem na contagem."""
        resposta = entregas(DIRETOR, "agrupar=mes")

        assert _periodos(resposta) == [("2026-11-01", 3), ("2026-10-01", 1)]
        assert "e-outra-diretora" not in _ids(resposta)


# ═══════════════════════════════════════════════════════════════════════════
# 2. Os filtros combinam
# ═══════════════════════════════════════════════════════════════════════════


class TestFiltros:
    @pytest.mark.parametrize(
        ("consulta", "esperado"),
        [
            ("de=2026-10-31&ate=2026-11-03", ["e-bug-diretor", "e-domingo", "e-vitta-terceiro"]),
            ("de=2026-11-01", ["e-vitta-rib", "e-bug-diretor", "e-domingo"]),
            ("ate=2026-10-31", ["e-vitta-terceiro", "e-outra-diretora"]),
            ("tipo=bug", ["e-bug-diretor", "e-vitta-terceiro"]),
            ("tipo=melhoria&origem=vitta", ["e-vitta-rib"]),
            ("origem=diretor&de=2026-11-01", ["e-bug-diretor", "e-domingo"]),
            ("responsavel=P1&tipo=melhoria", ["e-domingo", "e-outra-diretora"]),
            ("responsavel=terceiro-gh", ["e-vitta-terceiro"]),
            ("responsavel=P4&origem=vitta&de=2026-11-01&tipo=melhoria", ["e-vitta-rib"]),
        ],
    )
    def test_periodo_tipo_origem_e_responsavel_combinam(self, entregas, consulta, esperado):
        assert _ids(entregas(PEDRO, consulta)) == esperado

    def test_a_contagem_segue_os_filtros(self, entregas):
        assert _periodos(entregas(PEDRO, "agrupar=mes&origem=vitta")) == [("2026-11-01", 1), ("2026-10-01", 1)]

    def test_o_diretor_filtra_por_responsavel(self, entregas):
        """Nas Entregas o Responsavel e filtro de todos: e a pergunta do diretor
        "o que o Rib entregou"."""
        assert _ids(entregas(DIRETOR, "responsavel=P4")) == ["e-vitta-rib"]

    def test_as_opcoes_do_responsavel_vem_de_tudo_o_que_ele_ve_entregue(self, entregas):
        """As opcoes nao somem com o filtro ligado, senao nao da para trocar."""
        corpo = _corpo(entregas(DIRETOR, "responsavel=P4"))

        assert corpo["responsaveis"] == [
            {"valor": "P4", "nome": "Pedro Rib"},
            {"valor": "P1", "nome": "Pedro Vitta"},
            {"valor": "terceiro-gh", "nome": "terceiro-gh"},
        ]

    def test_periodo_invertido_e_recusado(self, entregas):
        assert entregas(PEDRO, "de=2026-11-05&ate=2026-11-01").status_code == 422
