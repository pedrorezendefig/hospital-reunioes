"""Desligamento mata a conta de login, nao so a linha da tabela (issue #415).

O soft delete de participante (`DELETE /participantes/{id}`) gravava
`ativo = false` e parava ai. A conta do Supabase Auth continuava viva, e com ela
o refresh token: quem saiu do hospital seguia renovando sessao sozinho, pra
sempre. O PR #414 fechou os gates de papel, mas gate e a rede de seguranca, nao
a tranca; a tranca e a conta morrer no desligamento.

Cobre:
- Desligamento de quem tem conta de login bane a conta no Supabase Auth.
- Desligamento de quem NAO tem conta (o Colaborador que so recebe email) nao
  chama o Auth e nao falha.
- Falha do Auth nao desfaz o desligamento: a pessoa fica `ativo=False` do mesmo
  jeito, e o gate do #414 segura o resto.
- A reativacao pela area admin devolve o login, senao o ban vira armadilha:
  a pessoa volta `ativo=True` na tabela e continua trancada pra sempre.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.routers import participantes as participantes_router  # noqa: E402

# ─── Infra de mocks Supabase ─────────────────────────────────────────────────


@dataclass
class _Result:
    data: list


class _ParticipantesQuery:
    """Mock minimo do query builder: update(payload).eq().execute()."""

    def __init__(self, rows_ref: list):
        self._rows = rows_ref
        self._filters: list[tuple[str, Any]] = []
        self._payload: dict | None = None

    def select(self, *_args, **_kwargs):
        return self

    def update(self, payload):
        self._payload = payload
        return self

    def eq(self, col, value):
        self._filters.append((col, value))
        return self

    def execute(self):
        matched = list(self._rows)
        for col, value in self._filters:
            matched = [r for r in matched if r.get(col) == value]
        if self._payload is not None:
            for row in matched:
                row.update(self._payload)
        return _Result(data=matched)


@dataclass
class _SupabaseMock:
    participantes: list = field(default_factory=list)
    auth: Any = None

    def table(self, name):
        assert name == "participantes", f"Tabela inesperada: {name}"
        return _ParticipantesQuery(self.participantes)


def _build_supabase(participantes: list[dict]) -> _SupabaseMock:
    sb = _SupabaseMock(participantes=list(participantes))
    sb.auth = MagicMock()
    sb.auth.admin = MagicMock()
    sb.auth.admin.update_user_by_id = MagicMock(return_value=None)
    return sb


def _participante(**overrides) -> dict:
    row = {
        "id": "P010",
        "nome_completo": "Maria",
        "email": "maria@x.com",
        "role": "coordenador",
        "ativo": True,
        "is_externo": False,
        "auth_user_id": "auth-010",
    }
    row.update(overrides)
    return row


def _quem_desliga() -> dict:
    return {"id": "auth-99", "email": "gerente@x.com"}


async def _desligar(sb: _SupabaseMock, participante_id: str = "P010"):
    return await participantes_router.soft_delete_participante(
        participante_id=participante_id,
        _=_quem_desliga(),
        supabase=sb,
    )


# ─── Testes ──────────────────────────────────────────────────────────────────


class TestDesligamentoRevogaLogin:
    """A conta de login morre junto com o vinculo (issue #415)."""

    @pytest.mark.asyncio
    async def test_desligar_quem_tem_login_bane_a_conta_no_supabase_auth(self):
        """Banir e o que invalida o refresh token: sem isso a sessao se renova
        sozinha depois do desligamento."""
        sb = _build_supabase([_participante()])

        await _desligar(sb)

        assert sb.participantes[0]["ativo"] is False
        sb.auth.admin.update_user_by_id.assert_called_once_with("auth-010", {"ban_duration": "876000h"})

    @pytest.mark.asyncio
    async def test_desligar_colaborador_sem_conta_de_login_nao_chama_o_auth(self):
        """O Colaborador só recebe email, nunca teve login (CONTEXT.md). Sem
        conta não há o que banir, e tentar seria erro no provedor."""
        sb = _build_supabase([_participante(auth_user_id=None)])

        await _desligar(sb)

        assert sb.participantes[0]["ativo"] is False
        sb.auth.admin.update_user_by_id.assert_not_called()

    @pytest.mark.asyncio
    async def test_provedor_de_auth_caido_nao_desfaz_o_desligamento(self, caplog):
        """O oposto da troca de email, que compensa e devolve 500. Aqui derrubar
        o desligamento por causa do GoTrue deixaria a pessoa ATIVA, que e o pior
        dos dois lados; o gate de papel do PR #414 le a tabela e segura."""
        sb = _build_supabase([_participante()])
        sb.auth.admin.update_user_by_id.side_effect = ConnectionError("gotrue down")

        with caplog.at_level("ERROR"):
            await _desligar(sb)

        assert sb.participantes[0]["ativo"] is False
        assert any("gotrue down" in r.getMessage() for r in caplog.records), (
            "a falha do Auth precisa deixar rastro: e o unico aviso de que a conta ficou viva"
        )
