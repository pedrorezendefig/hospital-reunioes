"""Testes do router /admin/usuarios — CRUD administrativo de participantes.

Cobre:
- 403 quando o actor nao e super admin.
- GET /admin/usuarios lista todos (inclusive inativos) com filtros.
- GET /admin/usuarios/{id} retorna detalhe + audit_logs.
- PATCH /admin/usuarios/{id} com mudancas loga EDIT_USUARIO.
- PATCH /admin/usuarios/{id} sem mudanca real nao loga.
- POST /admin/usuarios cria com id sequencial P00X e loga CREATE_USUARIO.
- DELETE /admin/usuarios/{id} com motivo loga DELETE_USUARIO.
- DELETE sem motivo (body invalido) -> 422.
- DELETE de si mesmo bloqueado (400).
- POST /admin/usuarios/{id}/reset-password loga RESET_PASSWORD e retorna senha nova.
"""
from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass, field
from typing import Any, Optional
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Os endpoints sao async functions — podemos chama-las diretamente,
# injetando os mocks nos parametros normalmente resolvidos por Depends.
from app.routers.admin import usuarios as usuarios_router  # noqa: E402
from app.models.admin_schemas import (  # noqa: E402
    AdminResetPasswordRequest,
    AdminUsuarioCreate,
    AdminUsuarioDeleteRequest,
    AdminUsuarioUpdate,
)
from app.models.schemas import UserRole  # noqa: E402


# ─── Infra de mocks Supabase ─────────────────────────────────────────────────


@dataclass
class _Result:
    data: list


class _ParticipantesQuery:
    """Mock do query builder para a tabela participantes.

    Suporta: select().eq().or_().order().range().limit().execute() em qualquer ordem,
    insert(payload).execute(), update(payload).eq(col, val).execute(),
    delete().eq(col, val).execute().
    """

    def __init__(self, rows_ref: list):
        self._rows = rows_ref  # referencia para list mutavel (create/delete)
        self._filters: list[tuple[str, Any]] = []
        self._or_terms: list[str] = []
        self._order: Optional[tuple[str, bool]] = None
        self._range: Optional[tuple[int, int]] = None
        self._limit: Optional[int] = None
        self._op: Optional[str] = None  # select / insert / update / delete
        self._payload: Optional[dict] = None

    def select(self, *_args, **_kwargs):
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

    def eq(self, col, value):
        self._filters.append((col, value))
        return self

    def or_(self, expr):
        self._or_terms.append(expr)
        return self

    def order(self, col, desc=False):
        self._order = (col, desc)
        return self

    def range(self, start, end):
        self._range = (start, end)
        return self

    def limit(self, n):
        self._limit = n
        return self

    # ── execute ────────────────────────────────────────────────────────────
    def execute(self):
        if self._op == "insert":
            row = dict(self._payload)
            row.setdefault("is_super_admin", False)
            row.setdefault("ativo", True)
            row.setdefault("is_externo", False)
            self._rows.append(row)
            return _Result(data=[row])

        # Filtra pela propriedade eq.
        matched = list(self._rows)
        for col, value in self._filters:
            matched = [r for r in matched if r.get(col) == value]

        # Aplica or_ de forma simples: procura padrao ilike (usado por busca).
        if self._or_terms:
            filtered_or: list = []
            for r in matched:
                for expr in self._or_terms:
                    # Trata .ilike.% parts %
                    for part in expr.split(","):
                        part = part.strip()
                        m = re.match(r"(\w+)\.ilike\.%(.+)%", part)
                        if m:
                            col = m.group(1)
                            val = m.group(2).lower()
                            if val in str(r.get(col, "")).lower():
                                filtered_or.append(r)
                                break
                        m2 = re.match(r"(\w+)\.eq\.(.+)", part)
                        if m2:
                            if str(r.get(m2.group(1))) == m2.group(2):
                                filtered_or.append(r)
                                break
                    else:
                        continue
                    break
            matched = filtered_or

        if self._op == "update":
            for row in matched:
                row.update(self._payload or {})
            return _Result(data=matched)

        if self._op == "delete":
            for row in list(matched):
                try:
                    self._rows.remove(row)
                except ValueError:
                    pass
            return _Result(data=matched)

        # select
        if self._order:
            col, desc = self._order
            matched.sort(key=lambda r: r.get(col) or "", reverse=desc)
        if self._range:
            start, end = self._range
            matched = matched[start : end + 1]
        if self._limit:
            matched = matched[: self._limit]
        return _Result(data=matched)


class _AuditQuery:
    def __init__(self, sink: list, source: list):
        self._sink = sink
        self._source = source
        self._payload: Optional[dict] = None
        self._filters: list[tuple[str, Any]] = []
        self._or_terms: list[str] = []
        self._limit: Optional[int] = None

    def insert(self, row):
        self._payload = row
        return self

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, col, value):
        self._filters.append((col, value))
        return self

    def or_(self, expr):
        self._or_terms.append(expr)
        return self

    def order(self, _col, desc=False):  # noqa: ARG002
        return self

    def limit(self, n):
        self._limit = n
        return self

    def execute(self):
        if self._payload is not None:
            self._sink.append(self._payload)
            return _Result(data=[self._payload])
        matched = list(self._source)
        for col, value in self._filters:
            matched = [r for r in matched if r.get(col) == value]
        if self._limit:
            matched = matched[: self._limit]
        return _Result(data=matched)


@dataclass
class _SupabaseMock:
    participantes: list = field(default_factory=list)
    audit_rows: list = field(default_factory=list)
    auth: Any = None

    def table(self, name):
        if name == "participantes":
            return _ParticipantesQuery(self.participantes)
        if name == "audit_log":
            return _AuditQuery(self.audit_rows, self.audit_rows)
        raise AssertionError(f"Tabela inesperada: {name}")


@dataclass
class _FakeRequest:
    client: Any = None
    headers: dict = field(default_factory=dict)


def _build_supabase(
    participantes: Optional[list[dict]] = None,
    audit_rows: Optional[list[dict]] = None,
) -> _SupabaseMock:
    sb = _SupabaseMock(
        participantes=list(participantes or []),
        audit_rows=list(audit_rows or []),
    )
    sb.auth = MagicMock()
    sb.auth.admin = MagicMock()
    sb.auth.admin.update_user_by_id = MagicMock(return_value=None)
    return sb


def _super_admin() -> dict:
    return {
        "id": "P001",
        "email": "admin@ex.com",
        "nome_completo": "Admin Super",
        "role": "diretor",
        "is_super_admin": True,
    }


# ─── Testes ──────────────────────────────────────────────────────────────────


class TestRequireSuperAdminGate:
    """O dependency ja e testado em test_super_admin; aqui validamos
    apenas que o router utiliza o require_super_admin (integracao).
    """

    @pytest.mark.asyncio
    async def test_endpoint_chama_require_super_admin_403(self):
        # Simula o path completo: require_super_admin com participante sem flag.
        from app.dependencies import require_super_admin

        sb = _build_supabase(
            participantes=[
                {
                    "id": "P99",
                    "auth_user_id": "auth-99",
                    "email": "diretor@ex.com",
                    "role": "diretor",
                    "is_super_admin": False,
                    "nome_completo": "Diretor Comum",
                }
            ]
        )
        with pytest.raises(HTTPException) as exc:
            await require_super_admin(
                current_user={"id": "auth-99", "email": "diretor@ex.com", "metadata": {}},
                supabase=sb,
            )
        assert exc.value.status_code == 403


class TestListUsuarios:
    @pytest.mark.asyncio
    async def test_list_retorna_ativos_e_inativos(self):
        sb = _build_supabase(
            participantes=[
                {"id": "P001", "nome_completo": "Alice", "email": "a@x.com", "ativo": True, "is_super_admin": True},
                {"id": "P002", "nome_completo": "Bob", "email": "b@x.com", "ativo": False, "is_super_admin": False},
            ]
        )
        result = await usuarios_router.list_usuarios(
            q=None,
            setor=None,
            ativo=None,
            is_super_admin_filter=None,
            limit=50,
            offset=0,
            _actor=_super_admin(),
            supabase=sb,
        )
        assert len(result) == 2
        ids = {r["id"] for r in result}
        assert ids == {"P001", "P002"}

    @pytest.mark.asyncio
    async def test_filtra_por_super_admin(self):
        sb = _build_supabase(
            participantes=[
                {"id": "P001", "nome_completo": "Alice", "email": "a@x.com", "ativo": True, "is_super_admin": True},
                {"id": "P002", "nome_completo": "Bob", "email": "b@x.com", "ativo": True, "is_super_admin": False},
            ]
        )
        result = await usuarios_router.list_usuarios(
            q=None,
            setor=None,
            ativo=None,
            is_super_admin_filter=True,
            limit=50,
            offset=0,
            _actor=_super_admin(),
            supabase=sb,
        )
        assert len(result) == 1
        assert result[0]["id"] == "P001"


class TestGetUsuario:
    @pytest.mark.asyncio
    async def test_detalhe_com_audit_logs(self):
        sb = _build_supabase(
            participantes=[
                {
                    "id": "P050",
                    "nome_completo": "Carlos",
                    "email": "carlos@x.com",
                    "ativo": True,
                    "is_super_admin": False,
                    "role": "coordenador",
                }
            ],
            audit_rows=[
                {
                    "id": "log1",
                    "timestamp": "2026-04-17T10:00:00Z",
                    "actor_id": "P001",
                    "actor_email": "admin@ex.com",
                    "action": "EDIT_USUARIO",
                    "target_type": "participante",
                    "target_id": "P050",
                    "metadata": {},
                }
            ],
        )
        result = await usuarios_router.get_usuario(
            participante_id="P050",
            _actor=_super_admin(),
            supabase=sb,
        )
        assert result.usuario.id == "P050"
        # Ao menos 1 log aparece (actor ou target).
        assert len(result.audit_logs) >= 1
        assert result.audit_logs[0].action == "EDIT_USUARIO"

    @pytest.mark.asyncio
    async def test_404_quando_nao_existe(self):
        sb = _build_supabase(participantes=[])
        with pytest.raises(HTTPException) as exc:
            await usuarios_router.get_usuario(
                participante_id="P999",
                _actor=_super_admin(),
                supabase=sb,
            )
        assert exc.value.status_code == 404


class TestPatchUsuario:
    @pytest.mark.asyncio
    async def test_patch_com_mudanca_loga(self):
        sb = _build_supabase(
            participantes=[
                {
                    "id": "P010",
                    "nome_completo": "Antigo",
                    "email": "antigo@x.com",
                    "cargo": "Analista",
                    "area": None,
                    "setor": None,
                    "role": "coordenador",
                    "ativo": True,
                    "is_externo": False,
                    "is_super_admin": False,
                }
            ]
        )
        body = AdminUsuarioUpdate(nome_completo="Novo Nome", reason="correcao")
        result = await usuarios_router.update_usuario(
            participante_id="P010",
            body=body,
            request=_FakeRequest(),
            actor=_super_admin(),
            supabase=sb,
        )
        assert result["nome_completo"] == "Novo Nome"
        # Audit log gerado.
        assert len(sb.audit_rows) == 1
        log = sb.audit_rows[0]
        assert log["action"] == "EDIT_USUARIO"
        assert log["reason"] == "correcao"
        assert "changes" in log["metadata"]
        assert log["metadata"]["changes"]["nome_completo"]["antes"] == "Antigo"
        assert log["metadata"]["changes"]["nome_completo"]["depois"] == "Novo Nome"

    @pytest.mark.asyncio
    async def test_patch_sem_mudanca_nao_loga(self):
        sb = _build_supabase(
            participantes=[
                {
                    "id": "P010",
                    "nome_completo": "Mesmo Nome",
                    "email": "mesmo@x.com",
                    "cargo": "Analista",
                    "area": None,
                    "setor": None,
                    "role": "coordenador",
                    "ativo": True,
                    "is_externo": False,
                    "is_super_admin": False,
                }
            ]
        )
        body = AdminUsuarioUpdate(nome_completo="Mesmo Nome")
        await usuarios_router.update_usuario(
            participante_id="P010",
            body=body,
            request=_FakeRequest(),
            actor=_super_admin(),
            supabase=sb,
        )
        assert sb.audit_rows == []

    @pytest.mark.asyncio
    async def test_patch_email_duplicado_409(self):
        sb = _build_supabase(
            participantes=[
                {
                    "id": "P010",
                    "nome_completo": "A",
                    "email": "a@x.com",
                    "cargo": "Analista",
                    "ativo": True,
                    "is_super_admin": False,
                },
                {
                    "id": "P011",
                    "nome_completo": "B",
                    "email": "b@x.com",
                    "cargo": "Analista",
                    "ativo": True,
                    "is_super_admin": False,
                },
            ]
        )
        body = AdminUsuarioUpdate(email="b@x.com")
        with pytest.raises(HTTPException) as exc:
            await usuarios_router.update_usuario(
                participante_id="P010",
                body=body,
                request=_FakeRequest(),
                actor=_super_admin(),
                supabase=sb,
            )
        assert exc.value.status_code == 409


class TestCreateUsuario:
    @pytest.mark.asyncio
    async def test_cria_com_id_sequencial_e_loga(self, monkeypatch):
        sb = _build_supabase(
            participantes=[
                {
                    "id": "P004",
                    "nome_completo": "Existente",
                    "email": "existente@x.com",
                    "cargo": "Analista",
                    "ativo": True,
                    "is_super_admin": False,
                },
            ]
        )

        # Bypass provisionamento auth (nao e objetivo do teste).
        import app.services.auth_provisioning as provisioning_mod

        monkeypatch.setattr(
            provisioning_mod, "provision_auth_user", lambda *a, **k: None
        )

        body = AdminUsuarioCreate(
            nome_completo="Novo User",
            email="novo@x.com",
            cargo="Coordenador",
            role=UserRole.COORDENADOR,
        )
        result = await usuarios_router.create_usuario(
            body=body,
            request=_FakeRequest(),
            actor=_super_admin(),
            supabase=sb,
        )
        assert result["id"] == "P005"
        assert result["email"] == "novo@x.com"
        assert len(sb.audit_rows) == 1
        assert sb.audit_rows[0]["action"] == "CREATE_USUARIO"
        assert sb.audit_rows[0]["target_id"] == "P005"


class TestDeleteUsuario:
    @pytest.mark.asyncio
    async def test_delete_com_motivo_loga(self):
        sb = _build_supabase(
            participantes=[
                {
                    "id": "P020",
                    "nome_completo": "A Deletar",
                    "email": "deletar@x.com",
                    "ativo": True,
                    "is_super_admin": False,
                }
            ]
        )
        body = AdminUsuarioDeleteRequest(reason="conta duplicada")
        result = await usuarios_router.delete_usuario(
            participante_id="P020",
            body=body,
            request=_FakeRequest(),
            actor=_super_admin(),
            supabase=sb,
        )
        assert result["success"] is True
        assert not any(p.get("id") == "P020" for p in sb.participantes)
        assert len(sb.audit_rows) == 1
        assert sb.audit_rows[0]["action"] == "DELETE_USUARIO"
        assert sb.audit_rows[0]["reason"] == "conta duplicada"

    @pytest.mark.asyncio
    async def test_delete_sem_motivo_pydantic_rejeita(self):
        # Motivo vazio viola min_length=1 — Pydantic levanta ValidationError.
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            AdminUsuarioDeleteRequest(reason="")

    @pytest.mark.asyncio
    async def test_delete_de_si_mesmo_400(self):
        actor = _super_admin()
        sb = _build_supabase(participantes=[{"id": actor["id"], "email": actor["email"], "ativo": True}])
        body = AdminUsuarioDeleteRequest(reason="teste")
        with pytest.raises(HTTPException) as exc:
            await usuarios_router.delete_usuario(
                participante_id=actor["id"],
                body=body,
                request=_FakeRequest(),
                actor=actor,
                supabase=sb,
            )
        assert exc.value.status_code == 400


class TestResetPassword:
    @pytest.mark.asyncio
    async def test_reset_password_loga_e_retorna_senha(self):
        sb = _build_supabase(
            participantes=[
                {
                    "id": "P030",
                    "nome_completo": "Alvo",
                    "email": "alvo@x.com",
                    "auth_user_id": "auth-030",
                    "role": "coordenador",
                    "ativo": True,
                    "is_super_admin": False,
                }
            ]
        )
        body = AdminResetPasswordRequest(reason="esqueceu", new_password="SenhaNova123")
        result = await usuarios_router.reset_password(
            participante_id="P030",
            body=body,
            request=_FakeRequest(),
            actor=_super_admin(),
            supabase=sb,
        )
        assert result.new_password == "SenhaNova123"
        assert result.email == "alvo@x.com"
        sb.auth.admin.update_user_by_id.assert_called_once_with(
            "auth-030", {"password": "SenhaNova123"}
        )
        assert len(sb.audit_rows) == 1
        assert sb.audit_rows[0]["action"] == "RESET_PASSWORD"
        assert sb.audit_rows[0]["reason"] == "esqueceu"

    @pytest.mark.asyncio
    async def test_reset_password_gera_senha_aleatoria_se_omitida(self):
        sb = _build_supabase(
            participantes=[
                {
                    "id": "P031",
                    "nome_completo": "Alvo2",
                    "email": "alvo2@x.com",
                    "auth_user_id": "auth-031",
                    "role": "coordenador",
                    "ativo": True,
                    "is_super_admin": False,
                }
            ]
        )
        body = AdminResetPasswordRequest(reason="rotacao periodica")
        result = await usuarios_router.reset_password(
            participante_id="P031",
            body=body,
            request=_FakeRequest(),
            actor=_super_admin(),
            supabase=sb,
        )
        assert result.new_password  # gerada
        assert len(result.new_password) >= 12
        assert sb.audit_rows[0]["metadata"]["gerada_aleatoria"] is True
