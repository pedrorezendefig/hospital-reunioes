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
    as 01h de 02/11 em UTC e o domingo 01/11 no hospital, semana de 26/10 e mes
    de outubro."""
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
            "2026-10-14T12:00:00Z",
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
            ("2026-10-26", 1),
            ("2026-10-12", 2),
        ]
