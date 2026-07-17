"""Testes do PATCH /participantes/{id} - troca de email pela porta comum.

Issue #195: a edicao comum de participante gravava o email so na tabela
`participantes`, sem validar unicidade nem sincronizar o Supabase Auth,
reabrindo a mesma classe de bug corrigida no caminho admin (issue #29).

Cobre:
- Email de participante COM conta de login sincroniza o auth (mesma semantica
  do caminho admin: auth primeiro, tabela depois).
- Email ja usado por outro participante responde 409 e nada e gravado.
- Email ja registrado no provedor de auth (outra conta) responde 409.
- Provedor de auth indisponivel responde 500 sem alterar a tabela.
- Falha na tabela apos o auth sincronizado reverte o auth (compensacao).
- Participante SEM conta de login: edicao continua so na tabela.
- Email normalizado (lowercase/trim) antes de validar e sincronizar.
- Edicao sem email (ou com o mesmo email) nao toca no auth.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.routers import participantes as participantes_router  # noqa: E402
from app.routers.participantes import ParticipanteUpdate  # noqa: E402

# ─── Infra de mocks Supabase ─────────────────────────────────────────────────


@dataclass
class _Result:
    data: list


class _ParticipantesQuery:
    """Mock minimo do query builder da tabela participantes.

    Suporta select().eq().execute() e update(payload).eq().execute(), que e
    tudo que o PATCH publico usa (fetch, unicidade e update).
    """

    def __init__(self, rows_ref: list):
        self._rows = rows_ref
        self._filters: list[tuple[str, Any]] = []
        self._op: str | None = None
        self._payload: dict | None = None

    def select(self, *_args, **_kwargs):
        self._op = "select"
        return self

    def update(self, payload):
        self._op = "update"
        self._payload = payload
        return self

    def eq(self, col, value):
        self._filters.append((col, value))
        return self

    def execute(self):
        matched = list(self._rows)
        for col, value in self._filters:
            matched = [r for r in matched if r.get(col) == value]
        if self._op == "update":
            for row in matched:
                row.update(self._payload or {})
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
        "email": "antigo@x.com",
        "cargo": "Analista",
        "area": None,
        "setor": None,
        "telefone": None,
        "role": "coordenador",
        "ativo": True,
        "is_externo": False,
        "is_super_admin": False,
        "auth_user_id": "auth-010",
    }
    row.update(overrides)
    return row


def _user() -> dict:
    return {"id": "auth-99", "email": "facilitador@x.com"}


async def _patch(sb: _SupabaseMock, body: ParticipanteUpdate, participante_id: str = "P010"):
    return await participantes_router.update_participante(
        participante_id=participante_id,
        body=body,
        _=_user(),
        supabase=sb,
    )


# ─── Testes ──────────────────────────────────────────────────────────────────


class TestSincronizacaoEmailAuthPortaComum:
    """Mesma semantica do caminho admin (issue #29) na porta comum (#195)."""

    @pytest.mark.asyncio
    async def test_editar_email_com_conta_sincroniza_login_no_supabase_auth(self):
        sb = _build_supabase([_participante()])
        result = await _patch(sb, ParticipanteUpdate(email="novo@x.com"))
        assert result["email"] == "novo@x.com"
        sb.auth.admin.update_user_by_id.assert_called_once_with(
            "auth-010", {"email": "novo@x.com", "email_confirm": True}
        )

    @pytest.mark.asyncio
    async def test_email_duplicado_na_tabela_responde_409_sem_gravar(self):
        sb = _build_supabase(
            [
                _participante(),
                _participante(id="P011", email="ocupado@x.com", auth_user_id="auth-011"),
            ]
        )
        with pytest.raises(HTTPException) as exc:
            await _patch(sb, ParticipanteUpdate(email="ocupado@x.com"))
        assert exc.value.status_code == 409
        assert sb.participantes[0]["email"] == "antigo@x.com"
        sb.auth.admin.update_user_by_id.assert_not_called()

    @pytest.mark.asyncio
    async def test_email_ja_registrado_no_auth_retorna_409_sem_alterar_tabela(self):
        from supabase_auth.errors import AuthApiError

        sb = _build_supabase([_participante()])
        sb.auth.admin.update_user_by_id.side_effect = AuthApiError(
            "A user with this email address has already been registered",
            422,
            "email_exists",
        )
        with pytest.raises(HTTPException) as exc:
            await _patch(sb, ParticipanteUpdate(email="ocupado@x.com"))
        assert exc.value.status_code == 409
        # Tabela permanece com o email antigo - nunca dessincroniza.
        assert sb.participantes[0]["email"] == "antigo@x.com"

    @pytest.mark.asyncio
    async def test_provedor_de_auth_indisponivel_retorna_500_sem_alterar_tabela(self):
        sb = _build_supabase([_participante()])
        sb.auth.admin.update_user_by_id.side_effect = ConnectionError("gotrue down")
        with pytest.raises(HTTPException) as exc:
            await _patch(sb, ParticipanteUpdate(email="novo@x.com"))
        assert exc.value.status_code == 500
        assert sb.participantes[0]["email"] == "antigo@x.com"

    @pytest.mark.asyncio
    async def test_falha_na_tabela_reverte_email_no_auth(self):
        sb = _build_supabase([_participante()])

        def _sync_then_drop_table(uid, attrs):  # noqa: ARG001
            # Primeira chamada (sync do email novo): simula a tabela sumindo
            # antes do UPDATE; chamadas seguintes (compensacao) passam normal.
            if attrs.get("email") == "novo@x.com":
                sb.participantes.clear()

        sb.auth.admin.update_user_by_id.side_effect = _sync_then_drop_table
        with pytest.raises(HTTPException) as exc:
            await _patch(sb, ParticipanteUpdate(email="novo@x.com"))
        assert exc.value.status_code == 500
        # Compensacao: o login volta a valer pelo email antigo.
        calls = sb.auth.admin.update_user_by_id.call_args_list
        assert len(calls) == 2
        assert calls[1].args == ("auth-010", {"email": "antigo@x.com", "email_confirm": True})

    @pytest.mark.asyncio
    async def test_participante_sem_conta_de_login_edita_so_a_tabela(self):
        sb = _build_supabase([_participante(auth_user_id=None)])
        result = await _patch(sb, ParticipanteUpdate(email="novo@x.com"))
        assert result["email"] == "novo@x.com"
        sb.auth.admin.update_user_by_id.assert_not_called()

    @pytest.mark.asyncio
    async def test_email_normalizado_lowercase_trim_antes_de_validar_e_sincronizar(self):
        sb = _build_supabase([_participante()])
        result = await _patch(sb, ParticipanteUpdate(email="  Novo@X.com "))
        assert result["email"] == "novo@x.com"
        sb.auth.admin.update_user_by_id.assert_called_once_with(
            "auth-010", {"email": "novo@x.com", "email_confirm": True}
        )

    @pytest.mark.asyncio
    async def test_edicao_sem_email_nao_toca_no_auth(self):
        sb = _build_supabase([_participante()])
        result = await _patch(sb, ParticipanteUpdate(nome_completo="Maria Souza"))
        assert result["nome_completo"] == "Maria Souza"
        sb.auth.admin.update_user_by_id.assert_not_called()

    @pytest.mark.asyncio
    async def test_mesmo_email_nao_toca_no_auth(self):
        sb = _build_supabase([_participante()])
        result = await _patch(sb, ParticipanteUpdate(email="antigo@x.com"))
        assert result["email"] == "antigo@x.com"
        sb.auth.admin.update_user_by_id.assert_not_called()

    @pytest.mark.asyncio
    async def test_email_nulo_explicito_responde_400(self):
        # NULL na tabela com conta auth viva = divergencia; mesma regra do admin.
        sb = _build_supabase([_participante()])
        with pytest.raises(HTTPException) as exc:
            await _patch(sb, ParticipanteUpdate(email=None, nome_completo="Maria"))
        assert exc.value.status_code == 400
        assert sb.participantes[0]["email"] == "antigo@x.com"

    @pytest.mark.asyncio
    async def test_participante_inexistente_responde_404(self):
        sb = _build_supabase([_participante()])
        with pytest.raises(HTTPException) as exc:
            await _patch(sb, ParticipanteUpdate(email="novo@x.com"), participante_id="P999")
        assert exc.value.status_code == 404
        sb.auth.admin.update_user_by_id.assert_not_called()
