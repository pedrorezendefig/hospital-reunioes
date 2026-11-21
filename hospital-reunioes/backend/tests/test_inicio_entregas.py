"""Os números de 90 dias e o que foi entregue (issue #1946, PRD #1932, ADR 0104 decisões 7 e 9).

Cada pessoa vê no Início os próprios números dos últimos 90 dias (entregas no
prazo e fora), e quem está em dia vê o que entregou nos últimos 7 dias. O
bloco Quem responde a você ganha a mesma conta, por pessoa. A régua é a do
ranking do painel de Reuniões: a data de conclusão sai do Histórico da
Pendência, então só conta a conclusão feita depois que o ciclo novo entrou, e
a Repactuação feita depois do vencimento pesa como atraso.
"""

from __future__ import annotations

import asyncio
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.routers import inicio as inicio_router  # noqa: E402
from app.services.inicio import entregas  # noqa: E402

BRT = ZoneInfo("America/Sao_Paulo")
# Quarta-feira, 18/11/2026, 10h em Brasília.
AGORA = datetime(2026, 11, 18, 10, 0, tzinfo=BRT)
HOJE = AGORA.date()


# ─── O banco de mentira ───────────────────────────────────────────────────


@dataclass
class _Result:
    data: list


class _Consulta:
    """`teto` imita o `max_rows` do PostgREST: corta a resposta em silêncio.
    Recorte sem `order` é recusado, porque a página seguinte pularia linha."""

    def __init__(self, linhas: list[dict], teto: int | None = None):
        self._linhas = linhas
        self._teto = teto
        self._filtros: list = []
        self._ordem: list[str] = []
        self._recorte: tuple[int, int] | None = None

    def select(self, *_a, **_kw):
        return self

    def order(self, coluna, *_a, **_kw):
        self._ordem.append(coluna)
        return self

    def range(self, inicio, fim):
        self._recorte = (inicio, fim)
        return self

    def eq(self, coluna, valor):
        self._filtros.append(lambda linha: linha.get(coluna) == valor)
        return self

    def in_(self, coluna, valores):
        valores = set(valores)
        self._filtros.append(lambda linha: linha.get(coluna) in valores)
        return self

    def is_(self, coluna, valor):
        assert valor == "null"
        self._filtros.append(lambda linha: linha.get(coluna) is None)
        return self

    def execute(self):
        linhas = [dict(linha) for linha in self._linhas if all(f(linha) for f in self._filtros)]
        if self._ordem:
            linhas.sort(key=lambda linha: tuple(str(linha.get(c)) for c in self._ordem))
        if self._recorte:
            assert self._ordem, "recorte sem order: a página seguinte pode repetir ou pular linha"
            linhas = linhas[self._recorte[0] : self._recorte[1] + 1]
        if self._teto is not None:
            linhas = linhas[: self._teto]
        return _Result(linhas)


@dataclass
class _Banco:
    pendencias: list = field(default_factory=list)
    pendencia_historico: list = field(default_factory=list)
    teto: int | None = None

    def table(self, nome):
        return _Consulta(getattr(self, nome), self.teto)


def _pendencia(id_acao: str, responsavel_id: str = "P_ANA", **campos) -> dict:
    base = {
        "id_acao": id_acao,
        "descricao_acao": f"Ação {id_acao}",
        "responsavel_id": responsavel_id,
        "co_responsavel_id": None,
        "id_reuniao": "R1",
        "status": "CONCLUIDO",
        "deleted_at": None,
    }
    return {**base, **campos}


_IDS = iter(range(1, 10_000))


def _evento(id_acao: str, comando: str, dia: str, *, prazo_antes: str | None, conta_atraso: bool = False) -> dict:
    """Um evento do Histórico às 10h de Brasília (13h em UTC) do `dia`."""
    return {
        "id": next(_IDS),
        "id_acao": id_acao,
        "comando": comando,
        "criado_em": f"{dia}T13:00:00+00:00",
        "prazo_antes": prazo_antes,
        "conta_atraso": conta_atraso,
    }


def _concluida(id_acao: str, dia: str, prazo: str) -> dict:
    return _evento(id_acao, "concluir", dia, prazo_antes=prazo)


ANA = {"id": "P_ANA", "nome_completo": "Ana Souza", "access_profile": "regular"}
BRUNO = {"id": "P_BRUNO", "nome_completo": "Bruno Reis", "access_profile": "regular"}
SECRETARIA = {"id": "P_SEC", "nome_completo": "Selma Souza", "access_profile": "secretaria"}


@pytest.fixture
def nucleo(monkeypatch):
    """As Reuniões do Núcleo que a pessoa não alcança: nenhuma, por padrão."""
    estado = {"ocultas": []}
    monkeypatch.setattr(entregas, "reunioes_ocultas", lambda _sb, _me: list(estado["ocultas"]))
    return estado


def _rota(monkeypatch, me: dict | None, banco: _Banco):
    async def _participante(_user, _sb, fields=None):
        return me

    monkeypatch.setattr(inicio_router, "get_participante_for_user", _participante)
    monkeypatch.setattr(inicio_router, "agora_em_brasilia", lambda: AGORA)
    return asyncio.run(inicio_router.get_meus_numeros(current_user={"id": "u1"}, supabase=banco))


def _numeros(resposta) -> tuple[int, int]:
    return resposta.numeros_90_dias.no_prazo, resposta.numeros_90_dias.fora_do_prazo


# ═══════════════════════════════════════════════════════════════════════════
# 1. Os próprios números de 90 dias
# ═══════════════════════════════════════════════════════════════════════════


class TestProprioNumero:
    def test_a_pessoa_ve_as_proprias_entregas_no_prazo_e_fora_e_nao_as_de_outra(self, monkeypatch, nucleo):
        banco = _Banco(
            pendencias=[
                _pendencia("A1"),
                _pendencia("A2"),
                _pendencia("A3"),
                _pendencia("B1", "P_BRUNO"),
                _pendencia("B2", "P_BRUNO"),
            ],
            pendencia_historico=[
                # No dia do prazo ainda é no prazo; no dia seguinte, fora.
                _concluida("A1", "2026-11-10", "2026-11-10"),
                _concluida("A2", "2026-11-11", "2026-11-10"),
                _concluida("A3", "2026-10-01", "2026-10-05"),
                _concluida("B1", "2026-11-12", "2026-11-01"),
                _concluida("B2", "2026-11-12", "2026-11-01"),
            ],
        )

        assert _numeros(_rota(monkeypatch, ANA, banco)) == (2, 1)
        assert _numeros(_rota(monkeypatch, BRUNO, banco)) == (0, 2)
