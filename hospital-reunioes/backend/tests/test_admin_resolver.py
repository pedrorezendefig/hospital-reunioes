"""Testes de resolver externo (merge/promote) + super admin inline.

Merge:
- Pre-validacoes HTTP (400 quando externo_id == interno_id, 400 quando o
  participante nao e externo, 400 quando o destino e externo).
- Execucao via RPC e mockada: a logica SQL esta coberta pela migration
  029 e deve ser validada em ambiente integrado (usando Postgres real).
  Aqui garantimos que a rota chama supabase.rpc() com os args corretos.

Promote:
- Flags setadas (is_externo=false, ativo=true).
- 400 quando o alvo ja e interno.
- Email duplicado retorna 409.

Super admin inline (grant/revoke):
- Grant loga audit_log super_admin_grant_inline e marca flag.
- Revoke bloqueado em self.
- Idempotente.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import Any

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.models.admin_schemas import (  # noqa: E402
    MergeExternoPayload,
    PromoteExternoPayload,
    ReasonRequest,
)
from app.routers.admin import usuarios as usuarios_router  # noqa: E402

# ─── Mock Supabase (suporta rpc + tabelas) ────────────────────────────────────


@dataclass
class _Result:
    data: Any


class _RpcCall:
    def __init__(self, sink: dict, return_value: Any):
        self._sink = sink
        self._return_value = return_value

    def execute(self):
        return _Result(data=self._return_value)


class _TableQuery:
    """Mock simples: select().eq().execute() / update().eq().execute() / delete().eq().execute()."""

    def __init__(self, rows_ref: list):
        self._rows = rows_ref
        self._op: str | None = None
        self._payload: Any = None
        self._filters: list[tuple[str, Any]] = []
        self._or_terms: list[str] = []

    def select(self, *_a, **_kw):
        self._op = "select"
        return self

    def insert(self, payload):
        self._op = "insert"
        self._payload = payload
        return self

    def update(self, payload):
        self._op = "update"
        self._payload = payload
        return self

    def delete(self):
        self._op = "delete"
        return self

    def eq(self, col, val):
        self._filters.append((col, val))
        return self

    def or_(self, expr):
        self._or_terms.append(expr)
        return self

    def ilike(self, col, pattern):
        self._filters.append((col, pattern))
        return self

    def order(self, *_a, **_kw):
        return self

    def range(self, *_a):
        return self

    def limit(self, _n):
        return self

    def execute(self):
        if self._op == "insert":
            if isinstance(self._payload, list):
                self._rows.extend(self._payload)
                return _Result(data=list(self._payload))
            self._rows.append(self._payload)
            return _Result(data=[self._payload])
        matched = list(self._rows)
        for col, val in self._filters:
            if isinstance(val, str) and "%" in val:
                needle = val.strip("%").lower()
                matched = [r for r in matched if needle in str(r.get(col, "")).lower()]
            else:
                matched = [r for r in matched if r.get(col) == val]
        if self._op == "update":
            for r in matched:
                r.update(self._payload or {})
            return _Result(data=list(matched))
        if self._op == "delete":
            for r in list(matched):
                self._rows.remove(r)
            return _Result(data=list(matched))
        return _Result(data=list(matched))


@dataclass
class _SupabaseMock:
    participantes: list = field(default_factory=list)
    audit_rows: list = field(default_factory=list)
    rpc_calls: list = field(default_factory=list)
    rpc_return: Any = None
    auth: Any = None

    def table(self, name):
        if name == "participantes":
            return _TableQuery(self.participantes)
        if name == "audit_log":
            return _AuditInsert(self.audit_rows)
        if name in {"setores", "cargos"}:
            return _TableQuery([])  # lookup silencioso sempre vazio nos testes
        raise AssertionError(f"Tabela inesperada: {name}")

    def rpc(self, name: str, params: dict):
        self.rpc_calls.append({"name": name, "params": params})
        default_return = [
            {
                "reuniao_participantes_moved": 3,
                "reuniao_participantes_dropped": 1,
                "reunioes_facilitador": 0,
                "reunioes_importado_por": 0,
                "pendencias_responsavel": 2,
                "pendencias_co_responsavel": 0,
                "comentarios_autor": 1,
                "comentarios_mencoes": 1,
                "notificacoes": 4,
            }
        ]
        return _RpcCall(
            self.rpc_calls[-1],
            self.rpc_return if self.rpc_return is not None else default_return,
        )


class _AuditInsert:
    def __init__(self, sink: list):
        self._sink = sink
        self._payload: dict | None = None

    def insert(self, payload):
        self._payload = payload
        return self

    def select(self, *_a, **_kw):
        return self

    def eq(self, *_a):
        return self

    def or_(self, *_a):
        return self

    def order(self, *_a, **_kw):
        return self

    def limit(self, _n):
        return self

    def execute(self):
        if self._payload is not None:
            self._sink.append(self._payload)
        return _Result(data=[self._payload] if self._payload else [])


@dataclass
class _FakeRequest:
    client: Any = None
    headers: dict = field(default_factory=dict)


def _super_admin() -> dict:
    return {
        "id": "P001",
        "email": "admin@ex.com",
        "nome_completo": "Admin",
        "role": "diretor",
        "is_super_admin": True,
    }


def _participante(
    pid: str,
    nome: str,
    is_externo: bool = False,
    is_super_admin: bool = False,
    email: str | None = "x@y.com",
    ativo: bool = True,
) -> dict:
    return {
        "id": pid,
        "nome_completo": nome,
        "email": email,
        "cargo": "Analista",
        "area": None,
        "setor": "TI",
        "role": "coordenador",
        "ativo": ativo,
        "is_externo": is_externo,
        "is_super_admin": is_super_admin,
        "auth_user_id": None,
        "data_cadastro": None,
    }


# ─── Merge ───────────────────────────────────────────────────────────────────


class TestMergeExterno:
    @pytest.mark.asyncio
    async def test_400_quando_externo_igual_interno(self):
        sb = _SupabaseMock(
            participantes=[_participante("P10", "Ext", is_externo=True)],
        )
        with pytest.raises(HTTPException) as exc:
            await usuarios_router.merge_externo(
                externo_id="P10",
                body=MergeExternoPayload(interno_id="P10", reason="teste"),
                request=_FakeRequest(),
                actor=_super_admin(),
                supabase=sb,
            )
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_400_quando_participante_nao_e_externo(self):
        sb = _SupabaseMock(
            participantes=[
                _participante("P10", "Interno", is_externo=False),
                _participante("P20", "Outro", is_externo=False),
            ],
        )
        with pytest.raises(HTTPException) as exc:
            await usuarios_router.merge_externo(
                externo_id="P10",
                body=MergeExternoPayload(interno_id="P20", reason="teste"),
                request=_FakeRequest(),
                actor=_super_admin(),
                supabase=sb,
            )
        assert exc.value.status_code == 400
        assert "nao e externo" in exc.value.detail.lower()

    @pytest.mark.asyncio
    async def test_400_quando_destino_e_externo(self):
        sb = _SupabaseMock(
            participantes=[
                _participante("P10", "Ext1", is_externo=True),
                _participante("P20", "Ext2", is_externo=True),
            ],
        )
        with pytest.raises(HTTPException) as exc:
            await usuarios_router.merge_externo(
                externo_id="P10",
                body=MergeExternoPayload(interno_id="P20", reason="teste"),
                request=_FakeRequest(),
                actor=_super_admin(),
                supabase=sb,
            )
        assert exc.value.status_code == 400
        assert "externo" in exc.value.detail.lower()

    @pytest.mark.asyncio
    async def test_chama_rpc_e_retorna_contadores(self):
        sb = _SupabaseMock(
            participantes=[
                _participante("P10", "Ext", is_externo=True),
                _participante("P20", "Interno", is_externo=False),
            ],
        )
        res = await usuarios_router.merge_externo(
            externo_id="P10",
            body=MergeExternoPayload(interno_id="P20", reason="dedup STT"),
            request=_FakeRequest(),
            actor=_super_admin(),
            supabase=sb,
        )
        assert res.externo_id == "P10"
        assert res.interno_id == "P20"
        assert res.reuniao_participantes_moved == 3
        assert res.pendencias_responsavel == 2
        assert len(sb.rpc_calls) == 1
        assert sb.rpc_calls[0]["name"] == "merge_participante_externo"
        assert sb.rpc_calls[0]["params"]["p_motivo"] == "dedup STT"
        assert sb.rpc_calls[0]["params"]["p_actor_id"] == "P001"


# ─── Promote ─────────────────────────────────────────────────────────────────


class TestPromoteExterno:
    @pytest.mark.asyncio
    async def test_promove_marca_flags_corretas(self):
        sb = _SupabaseMock(
            participantes=[
                _participante("P30", "Nova Pessoa", is_externo=True, ativo=False, email=None),
            ],
        )
        res = await usuarios_router.promote_externo(
            externo_id="P30",
            body=PromoteExternoPayload(email="nova@ex.com", cargo="Analista", setor="RH"),
            request=_FakeRequest(),
            actor=_super_admin(),
            supabase=sb,
        )
        assert res["is_externo"] is False
        assert res["ativo"] is True
        assert res["email"] == "nova@ex.com"
        # audit_log gravado
        assert any(r["action"] == "promote_participante" for r in sb.audit_rows)

    @pytest.mark.asyncio
    async def test_400_quando_ja_interno(self):
        sb = _SupabaseMock(
            participantes=[_participante("P40", "Interno", is_externo=False)],
        )
        with pytest.raises(HTTPException) as exc:
            await usuarios_router.promote_externo(
                externo_id="P40",
                body=PromoteExternoPayload(cargo="X"),
                request=_FakeRequest(),
                actor=_super_admin(),
                supabase=sb,
            )
        assert exc.value.status_code == 400
        assert "ja e interno" in exc.value.detail.lower()

    @pytest.mark.asyncio
    async def test_email_duplicado_retorna_409(self):
        sb = _SupabaseMock(
            participantes=[
                _participante("P50", "Externo", is_externo=True, email=None),
                _participante("P51", "Outro", is_externo=False, email="usado@ex.com"),
            ],
        )
        with pytest.raises(HTTPException) as exc:
            await usuarios_router.promote_externo(
                externo_id="P50",
                body=PromoteExternoPayload(email="usado@ex.com"),
                request=_FakeRequest(),
                actor=_super_admin(),
                supabase=sb,
            )
        assert exc.value.status_code == 409

    @pytest.mark.asyncio
    async def test_promover_quem_estava_desligado_reabre_a_conta_de_login(self):
        """Issue #415: a promocao e a terceira porta que devolve `ativo=True`.
        Se so ela ficasse de fora, a pessoa voltaria ao quadro com o login
        banido e ninguem entenderia por que ela nao entra."""
        from unittest.mock import MagicMock

        sb = _SupabaseMock(
            participantes=[
                {**_participante("P31", "Voltou", is_externo=True, ativo=False), "auth_user_id": "auth-031"},
            ],
        )
        sb.auth = MagicMock()

        res = await usuarios_router.promote_externo(
            externo_id="P31",
            body=PromoteExternoPayload(cargo="Analista"),
            request=_FakeRequest(),
            actor=_super_admin(),
            supabase=sb,
        )

        assert res["ativo"] is True
        sb.auth.admin.update_user_by_id.assert_called_once_with("auth-031", {"ban_duration": "none"})

    @pytest.mark.asyncio
    async def test_promover_mantendo_desligado_nao_toca_no_login(self):
        """Controle: `ativo=False` explicito no payload manda mais que o default
        da promocao, entao o vinculo NAO virou e o Auth fica intocado.

        Nao mexer e diferente de banir: uma conta banida a mao no Supabase por
        outro motivo nao pode ser reaberta de carona, nem rebanida sem motivo,
        por uma promocao que nao mudou o vinculo."""
        from unittest.mock import MagicMock

        sb = _SupabaseMock(
            participantes=[
                {**_participante("P32", "Ainda fora", is_externo=True, ativo=False), "auth_user_id": "auth-032"},
            ],
        )
        sb.auth = MagicMock()

        res = await usuarios_router.promote_externo(
            externo_id="P32",
            body=PromoteExternoPayload(cargo="Analista", ativo=False),
            request=_FakeRequest(),
            actor=_super_admin(),
            supabase=sb,
        )

        assert res["ativo"] is False
        sb.auth.admin.update_user_by_id.assert_not_called()

    @pytest.mark.asyncio
    async def test_promover_quem_ja_estava_ativo_nao_toca_no_login(self):
        """O externo ativo promovido continua ativo: o vinculo nao virou, entao
        a promocao nao pode desbanir de carona uma conta trancada a mao."""
        from unittest.mock import MagicMock

        sb = _SupabaseMock(
            participantes=[
                {**_participante("P33", "Ja ativo", is_externo=True, ativo=True), "auth_user_id": "auth-033"},
            ],
        )
        sb.auth = MagicMock()

        await usuarios_router.promote_externo(
            externo_id="P33",
            body=PromoteExternoPayload(cargo="Analista"),
            request=_FakeRequest(),
            actor=_super_admin(),
            supabase=sb,
        )

        sb.auth.admin.update_user_by_id.assert_not_called()


# ─── Super admin inline ──────────────────────────────────────────────────────


class TestGrantSuperAdminInline:
    @pytest.mark.asyncio
    async def test_grant_marca_flag_e_loga(self):
        sb = _SupabaseMock(
            participantes=[_participante("P60", "Alvo", is_super_admin=False)],
        )
        res = await usuarios_router.grant_super_admin_inline(
            participante_id="P60",
            body=ReasonRequest(reason="novo admin"),
            request=_FakeRequest(),
            actor=_super_admin(),
            supabase=sb,
        )
        assert res["is_super_admin"] is True
        assert any(r["action"] == "super_admin_grant_inline" for r in sb.audit_rows)

    @pytest.mark.asyncio
    async def test_grant_idempotente_nao_loga(self):
        sb = _SupabaseMock(
            participantes=[_participante("P61", "Alvo", is_super_admin=True)],
        )
        res = await usuarios_router.grant_super_admin_inline(
            participante_id="P61",
            body=ReasonRequest(reason="idempotente"),
            request=_FakeRequest(),
            actor=_super_admin(),
            supabase=sb,
        )
        assert res["is_super_admin"] is True
        assert sb.audit_rows == []


class TestRevokeSuperAdminInline:
    @pytest.mark.asyncio
    async def test_revoke_marca_flag_e_loga(self):
        sb = _SupabaseMock(
            participantes=[_participante("P70", "Alvo", is_super_admin=True)],
        )
        res = await usuarios_router.revoke_super_admin_inline(
            participante_id="P70",
            body=ReasonRequest(reason="revogado"),
            request=_FakeRequest(),
            actor=_super_admin(),
            supabase=sb,
        )
        assert res["is_super_admin"] is False
        assert any(r["action"] == "super_admin_revoke_inline" for r in sb.audit_rows)

    @pytest.mark.asyncio
    async def test_self_revoke_bloqueado(self):
        sb = _SupabaseMock(
            participantes=[_participante("P001", "Admin", is_super_admin=True)],
        )
        with pytest.raises(HTTPException) as exc:
            await usuarios_router.revoke_super_admin_inline(
                participante_id="P001",  # mesmo id que actor
                body=ReasonRequest(reason="tentando"),
                request=_FakeRequest(),
                actor=_super_admin(),
                supabase=sb,
            )
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_revoke_idempotente_quando_nao_e_super(self):
        sb = _SupabaseMock(
            participantes=[_participante("P71", "Alvo", is_super_admin=False)],
        )
        res = await usuarios_router.revoke_super_admin_inline(
            participante_id="P71",
            body=ReasonRequest(reason="idempotente"),
            request=_FakeRequest(),
            actor=_super_admin(),
            supabase=sb,
        )
        assert res["is_super_admin"] is False
        assert sb.audit_rows == []
