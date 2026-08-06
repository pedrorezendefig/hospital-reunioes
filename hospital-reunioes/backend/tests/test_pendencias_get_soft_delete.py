"""Teste do GET /pendencias/{id_acao} com soft delete (issue #270).

Pendência com deleted_at preenchido deve retornar 404, alinhado à listagem.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.routers import pendencias as pendencias_router  # noqa: E402


@dataclass
class _Result:
    data: list


class _FakeTable:
    def __init__(self, rows: list[dict]):
        self._rows = rows
        self._filters_eq: dict = {}
        self._filters_is: dict = {}
        self._filters_in: dict = {}

    def select(self, *_a, **_kw):
        return self

    def eq(self, col, val):
        self._filters_eq[col] = val
        return self

    def is_(self, col, val):
        self._filters_is[col] = val
        return self

    def in_(self, col, vals):
        self._filters_in[col] = set(vals)
        return self

    def execute(self):
        rows = []
        for r in self._rows:
            if any(r.get(k) != v for k, v in self._filters_eq.items()):
                continue
            if any(r.get(k) is not None for k, v in self._filters_is.items() if v == "null"):
                continue
            if any(r.get(k) not in vals for k, vals in self._filters_in.items()):
                continue
            rows.append(r)
        return _Result(rows)


@dataclass
class _Sb:
    pendencias: list = field(default_factory=list)
    participantes: list = field(default_factory=list)

    def table(self, name):
        if name == "pendencias":
            return _FakeTable(self.pendencias)
        if name == "participantes":
            return _FakeTable(self.participantes)
        raise AssertionError(f"Tabela inesperada: {name}")


def _patch_deps(monkeypatch, allowed: list[str] | None):
    async def _fake_participante(_user, _sb, fields=None):
        return {"id": "P01", "nome_completo": "Pedro Rezende"}

    async def _fake_allowed(_user, _sb):
        return allowed

    monkeypatch.setattr(pendencias_router, "get_participante_for_user", _fake_participante)
    monkeypatch.setattr(pendencias_router, "get_allowed_reuniao_ids", _fake_allowed)


class TestGetPendenciaSoftDelete:
    @pytest.mark.asyncio
    async def test_pendencia_excluida_retorna_404(self, monkeypatch):
        sb = _Sb(
            pendencias=[
                {
                    "id_acao": "A001",
                    "id_reuniao": "RD_001",
                    "co_responsavel_id": None,
                    "responsavel_id": "P99",
                    "deleted_at": "2026-08-01T10:00:00Z",
                }
            ]
        )
        _patch_deps(monkeypatch, allowed=None)

        with pytest.raises(HTTPException) as exc:
            await pendencias_router.get_pendencia(id_acao="A001", current_user={"id": "u1"}, supabase=sb)
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_pendencia_ativa_continua_acessivel(self, monkeypatch):
        sb = _Sb(
            pendencias=[
                {
                    "id_acao": "A002",
                    "id_reuniao": "RD_001",
                    "co_responsavel_id": None,
                    "responsavel_id": "P99",
                    "deleted_at": None,
                }
            ],
            participantes=[{"id": "P99", "is_externo": False}],
        )
        _patch_deps(monkeypatch, allowed=None)

        resultado = await pendencias_router.get_pendencia(id_acao="A002", current_user={"id": "u1"}, supabase=sb)
        assert resultado["id_acao"] == "A002"

    @pytest.mark.asyncio
    async def test_token_orfao_recebe_404_em_pendencia_sem_corresponsavel(self, monkeypatch):
        """Órfão (allowed=[] e my_id=None) não pode enxergar Pendência sem co-responsável."""
        sb = _Sb(
            pendencias=[
                {
                    "id_acao": "A003",
                    "id_reuniao": "RD_001",
                    "co_responsavel_id": None,
                    "responsavel_id": "P99",
                    "deleted_at": None,
                }
            ]
        )
        _patch_deps(monkeypatch, allowed=[])

        async def _sem_participante_id(_user, _sb):
            return None

        monkeypatch.setattr(pendencias_router, "get_participante_id_for_user", _sem_participante_id)

        with pytest.raises(HTTPException) as exc:
            await pendencias_router.get_pendencia(id_acao="A003", current_user={"id": "orfao"}, supabase=sb)
        assert exc.value.status_code == 404
