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
        self._inserted: dict | None = None

    def select(self, *_args, **_kwargs):
        return self

    def update(self, payload):
        self._payload = payload
        return self

    def insert(self, payload):
        self._rows.append(dict(payload))
        self._inserted = dict(payload)
        return self

    def eq(self, col, value):
        self._filters.append((col, value))
        return self

    def execute(self):
        if getattr(self, "_inserted", None) is not None:
            return _Result(data=[self._inserted])
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

    @pytest.mark.asyncio
    async def test_ban_que_falha_avisa_o_admin_tecnico(self, monkeypatch):
        """Log de servidor nao e rastro acionavel: ninguem le. Se o ban falhou,
        a pessoa esta `ativo=false` com a conta viva renovando sessao, e a
        janela curta prometida virou permanente. Alguem tem que ser avisado,
        pelo mesmo canal que o alerta sem Diretoria passou a usar."""
        from app.services import ouvidoria_notificacoes

        avisos: list[tuple[str, str]] = []
        monkeypatch.setattr(
            ouvidoria_notificacoes,
            "avisar_admins_tecnicos",
            lambda _sb, assunto, texto: avisos.append((assunto, texto)) or 1,
        )
        sb = _build_supabase([_participante()])
        sb.auth.admin.update_user_by_id.side_effect = ConnectionError("gotrue down")

        await _desligar(sb)

        assert len(avisos) == 1, "a falha do ban tem que chegar a um humano, nao so ao log"
        assert "auth-010" in avisos[0][1]

    @pytest.mark.asyncio
    async def test_ban_que_da_certo_nao_incomoda_o_admin_tecnico(self, monkeypatch):
        """Controle: aviso que sai sempre nao e aviso. Sem ele, um alerta
        incondicional passaria verde no teste acima."""
        from app.services import ouvidoria_notificacoes

        avisos: list = []
        monkeypatch.setattr(
            ouvidoria_notificacoes,
            "avisar_admins_tecnicos",
            lambda _sb, assunto, texto: avisos.append((assunto, texto)) or 1,
        )
        sb = _build_supabase([_participante()])

        await _desligar(sb)

        assert avisos == []


class TestContaNasceCoerenteComOVinculo:
    """Quem nasce desligado nao ganha conta de login viva (issue #415).

    `ParticipanteCreate.ativo` e `AdminUsuarioCreate.ativo` tem default True mas
    aceitam False, e o provisionamento cria a conta no GoTrue sem ban, sempre.
    Sem esta trava, criar alguem ja desligado deixava uma conta viva para um
    vinculo inativo: os gates de papel barram, mas o refresh token nunca morre,
    e a "janela curta" prometida no docstring de `barrar_desligado` virava
    infinita justo por onde ninguem olha.
    """

    def _supabase_com_provisionamento(self, auth_uid: str | None = "auth-novo"):
        sb = _SupabaseMock(participantes=[])
        sb.auth = MagicMock()
        sb.auth.admin = MagicMock()
        sb.auth.admin.update_user_by_id = MagicMock(return_value=None)
        criado = MagicMock()
        criado.user.id = auth_uid
        sb.auth.admin.create_user = MagicMock(return_value=criado if auth_uid else None)
        return sb

    def test_participante_que_nasce_desligado_ja_nasce_com_o_login_banido(self):
        from app.services.auth_provisioning import provision_with_compensation

        sb = self._supabase_com_provisionamento()

        provision_with_compensation(
            sb,
            {"id": "P77", "nome_completo": "Nasce Fora", "email": "fora@x.com", "ativo": False},
            role="coordenador",
        )

        sb.auth.admin.update_user_by_id.assert_called_once_with("auth-novo", {"ban_duration": "876000h"})

    def test_participante_que_nasce_ativo_nao_e_banido(self):
        """Controle: o caminho comum nao pode nascer trancado. Sem ele, um
        banimento incondicional passaria verde no teste acima."""
        from app.services.auth_provisioning import provision_with_compensation

        sb = self._supabase_com_provisionamento()

        provision_with_compensation(
            sb,
            {"id": "P78", "nome_completo": "Nasce Dentro", "email": "dentro@x.com", "ativo": True},
            role="coordenador",
        )

        sb.auth.admin.update_user_by_id.assert_not_called()

    def test_participante_sem_o_campo_ativo_nasce_livre(self):
        """`ativo` e BOOLEAN DEFAULT TRUE: ausente significa ativo, nunca
        desligado. Tratar indefinido como desligado trancaria gente legitima,
        que e a mesma armadilha que `foi_desligado` evita."""
        from app.services.auth_provisioning import provision_with_compensation

        sb = self._supabase_com_provisionamento()

        provision_with_compensation(
            sb,
            {"id": "P79", "nome_completo": "Sem Campo", "email": "sem@x.com"},
            role="coordenador",
        )

        sb.auth.admin.update_user_by_id.assert_not_called()
