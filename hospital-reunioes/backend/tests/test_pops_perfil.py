"""Testes de conceder/revogar perfil POP (/pops/admin/usuarios) — issue #81.

O Superadmin (POPs) concede/revoga o eixo `perfil_pop` da pessoa (entidade
única dos dois contextos, ADR 0007). Conceder a quem não loga provisiona o
login automaticamente (reusa o provisionamento de auth existente) SEM dar
papel no contexto Reuniões (access_profile fica NULL). Revogar encerra o
acesso ao contexto POPs (gates 403 nos endpoints /pops).
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.dependencies import get_current_user, get_supabase_client  # noqa: E402
from app.routers.pops import usuarios as pops_usuarios_router  # noqa: E402

# ─── Mock Supabase (participantes + audit_log + auth.admin) ──────────────────


@dataclass
class _Result:
    data: list


class _TableQuery:
    def __init__(self, rows: list[dict], table: str):
        self._rows = rows
        self._table = table
        self._filters: dict = {}
        self._in_filters: dict = {}
        self._insert_payload: list[dict] | None = None
        self._update_payload: dict | None = None
        self._delete = False

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, col, value):
        self._filters[col] = value
        return self

    def in_(self, col, values):
        self._in_filters[col] = list(values)
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def insert(self, payload):
        rows = payload if isinstance(payload, list) else [payload]
        self._insert_payload = [dict(r) for r in rows]
        return self

    def update(self, payload: dict):
        self._update_payload = dict(payload)
        return self

    def delete(self):
        self._delete = True
        return self

    def _match(self, row: dict) -> bool:
        if not all(row.get(c) == v for c, v in self._filters.items()):
            return False
        return all(row.get(c) in v for c, v in self._in_filters.items())

    def execute(self):
        if self._insert_payload is not None:
            self._rows.extend(self._insert_payload)
            return _Result(data=[dict(r) for r in self._insert_payload])

        filtered = [r for r in self._rows if self._match(r)]

        if self._delete:
            self._rows[:] = [r for r in self._rows if not self._match(r)]
            return _Result(data=[dict(r) for r in filtered])

        if self._update_payload is not None:
            for row in filtered:
                row.update(self._update_payload)
            return _Result(data=[dict(r) for r in filtered])

        return _Result(data=[dict(r) for r in filtered])


class _AuthAdmin:
    def __init__(self):
        self.created: list[dict] = []

    def create_user(self, payload: dict):
        self.created.append(payload)
        return SimpleNamespace(user=SimpleNamespace(id=f"auth-novo-{len(self.created)}"))


class _SupabaseMock:
    def __init__(self, participantes: list[dict], pops_setores: list[dict] | None = None):
        self.tables: dict[str, list[dict]] = {
            "participantes": participantes,
            "pops_setores": pops_setores or [],
            "pops_setores_participantes": [],
            "audit_log": [],
        }
        self.auth = SimpleNamespace(admin=_AuthAdmin())

    def table(self, name: str):
        if name not in self.tables:
            raise AssertionError(f"Tabela inesperada: {name}")
        return _TableQuery(self.tables[name], name)


# ─── Helpers ──────────────────────────────────────────────────────────────────

SUPERADMIN_POPS = {
    "id": "P_DIR",
    "auth_user_id": "auth-dir",
    "email": "diretoria@hsm.com",
    "nome_completo": "Diretoria Executiva",
    "ativo": True,
    "is_externo": False,
    "is_super_admin": False,
    "access_profile": None,
    "perfil_pop": "superadmin",
}

# Super Admin de Reuniões SEM perfil POP. Autoridade unificada (#148): administra
# a concessão de perfil_pop sem ter papel no contexto POPs.
SUPER_ADMIN_REUNIOES = {
    "id": "P_SA",
    "auth_user_id": "auth-sa",
    "email": "admin@hsm.com",
    "nome_completo": "Super Admin Reunioes",
    "ativo": True,
    "is_externo": False,
    "is_super_admin": True,
    "access_profile": "super_admin",
    "perfil_pop": None,
}


def _alvo(pid: str = "P_ALVO", auth_user_id: str | None = "auth-alvo", **extra) -> dict:
    row = {
        "id": pid,
        "auth_user_id": auth_user_id,
        "email": "alvo@hsm.com",
        "nome_completo": "Pessoa Alvo",
        "ativo": True,
        "is_externo": False,
        "is_super_admin": False,
        "access_profile": "regular",
        "perfil_pop": None,
    }
    row.update(extra)
    return row


def _client_para(
    atuante: dict, *outros: dict, pops_setores: list[dict] | None = None
) -> tuple[TestClient, _SupabaseMock]:
    app = FastAPI()
    app.include_router(pops_usuarios_router.router, prefix="/api")

    sb = _SupabaseMock(participantes=[atuante, *outros], pops_setores=pops_setores)

    async def _fake_user() -> dict[str, Any]:
        return {"id": atuante["auth_user_id"], "email": atuante["email"], "metadata": {}}

    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_supabase_client] = lambda: sb
    return TestClient(app), sb


def _row(sb: _SupabaseMock, pid: str) -> dict:
    return next(r for r in sb.tables["participantes"] if r["id"] == pid)


# ─── Conceder perfil POP ──────────────────────────────────────────────────────


class TestConcederPerfilPop:
    def test_conceder_a_pessoa_que_ja_loga_nao_reprovisiona(self):
        client, sb = _client_para(dict(SUPERADMIN_POPS), _alvo())
        r = client.patch("/api/pops/admin/usuarios/P_ALVO/perfil-pop", json={"perfil_pop": "gerente"})
        assert r.status_code == 200
        body = r.json()
        assert body["perfil_pop"] == "gerente"
        assert body["new_password"] is None
        alvo = _row(sb, "P_ALVO")
        assert alvo["perfil_pop"] == "gerente"
        # Eixos ortogonais: o papel nas Reuniões não muda.
        assert alvo["access_profile"] == "regular"
        assert sb.auth.admin.created == []

    def test_conceder_a_pessoa_sem_login_provisiona_o_acesso(self):
        # Colaborador que não loga (auth_user_id ausente) ganha login ao
        # receber perfil POP — sem ganhar papel no contexto Reuniões.
        client, sb = _client_para(dict(SUPERADMIN_POPS), _alvo(auth_user_id=None))
        r = client.patch("/api/pops/admin/usuarios/P_ALVO/perfil-pop", json={"perfil_pop": "coordenador"})
        assert r.status_code == 200
        body = r.json()
        assert body["perfil_pop"] == "coordenador"
        assert body["new_password"]  # senha exibida uma única vez
        assert len(sb.auth.admin.created) == 1
        assert sb.auth.admin.created[0]["email"] == "alvo@hsm.com"
        alvo = _row(sb, "P_ALVO")
        assert alvo["auth_user_id"] == "auth-novo-1"
        assert alvo["perfil_pop"] == "coordenador"
        assert alvo["access_profile"] is None  # sem papel nas Reuniões

    def test_conceder_sem_email_recebe_400(self):
        client, _ = _client_para(dict(SUPERADMIN_POPS), _alvo(auth_user_id=None, email=None))
        r = client.patch("/api/pops/admin/usuarios/P_ALVO/perfil-pop", json={"perfil_pop": "gerente"})
        assert r.status_code == 400

    def test_perfil_invalido_recebe_422(self):
        client, _ = _client_para(dict(SUPERADMIN_POPS), _alvo())
        r = client.patch("/api/pops/admin/usuarios/P_ALVO/perfil-pop", json={"perfil_pop": "chefe"})
        assert r.status_code == 422

    def test_pessoa_inexistente_recebe_404(self):
        client, _ = _client_para(dict(SUPERADMIN_POPS))
        r = client.patch("/api/pops/admin/usuarios/P_NAO_EXISTE/perfil-pop", json={"perfil_pop": "gerente"})
        assert r.status_code == 404

    def test_demais_perfis_recebem_403(self):
        for perfil in ("gestor_qualidade", "gerente", "coordenador", None):
            atuante = dict(SUPERADMIN_POPS, perfil_pop=perfil)
            client, sb = _client_para(atuante, _alvo())
            r = client.patch("/api/pops/admin/usuarios/P_ALVO/perfil-pop", json={"perfil_pop": "gerente"})
            assert r.status_code == 403, f"perfil_pop={perfil} deveria receber 403"
            assert _row(sb, "P_ALVO")["perfil_pop"] is None


# ─── Revogar perfil POP ───────────────────────────────────────────────────────


class TestRevogarPerfilPop:
    def test_revogar_zera_o_perfil(self):
        client, sb = _client_para(dict(SUPERADMIN_POPS), _alvo(perfil_pop="coordenador"))
        r = client.patch("/api/pops/admin/usuarios/P_ALVO/perfil-pop", json={"perfil_pop": None})
        assert r.status_code == 200
        assert r.json()["perfil_pop"] is None
        assert _row(sb, "P_ALVO")["perfil_pop"] is None

    def test_revogar_o_proprio_perfil_recebe_400(self):
        client, sb = _client_para(dict(SUPERADMIN_POPS))
        r = client.patch("/api/pops/admin/usuarios/P_DIR/perfil-pop", json={"perfil_pop": None})
        assert r.status_code == 400
        assert _row(sb, "P_DIR")["perfil_pop"] == "superadmin"


# ─── Vínculos de Setor (N:N pessoa↔Setor) ─────────────────────────────────────

_SETORES = [
    {"id": "s1", "nome": "Farmácia", "sigla": "FAR"},
    {"id": "s2", "nome": "CTI", "sigla": "CTI"},
]


class TestVinculosDeSetor:
    def test_define_varios_setores_para_gerente(self):
        # Gerente pode ter vários Setores sob sua gestão.
        client, sb = _client_para(dict(SUPERADMIN_POPS), _alvo(perfil_pop="gerente"), pops_setores=list(_SETORES))
        r = client.put("/api/pops/admin/usuarios/P_ALVO/setores", json={"setor_ids": ["s1", "s2"]})
        assert r.status_code == 200
        assert {s["sigla"] for s in r.json()} == {"FAR", "CTI"}
        vinculos = sb.tables["pops_setores_participantes"]
        assert {(v["setor_id"], v["participante_id"]) for v in vinculos} == {("s1", "P_ALVO"), ("s2", "P_ALVO")}

    def test_redefinir_substitui_os_vinculos_anteriores(self):
        client, sb = _client_para(dict(SUPERADMIN_POPS), _alvo(perfil_pop="coordenador"), pops_setores=list(_SETORES))
        client.put("/api/pops/admin/usuarios/P_ALVO/setores", json={"setor_ids": ["s1"]})
        r = client.put("/api/pops/admin/usuarios/P_ALVO/setores", json={"setor_ids": ["s2"]})
        assert r.status_code == 200
        vinculos = sb.tables["pops_setores_participantes"]
        assert [(v["setor_id"], v["participante_id"]) for v in vinculos] == [("s2", "P_ALVO")]

    def test_setor_inexistente_recebe_400(self):
        client, sb = _client_para(dict(SUPERADMIN_POPS), _alvo(perfil_pop="gerente"), pops_setores=list(_SETORES))
        r = client.put("/api/pops/admin/usuarios/P_ALVO/setores", json={"setor_ids": ["s1", "s9"]})
        assert r.status_code == 400
        assert sb.tables["pops_setores_participantes"] == []

    def test_lista_setores_vinculados(self):
        client, sb = _client_para(dict(SUPERADMIN_POPS), _alvo(perfil_pop="coordenador"), pops_setores=list(_SETORES))
        sb.tables["pops_setores_participantes"].append({"setor_id": "s2", "participante_id": "P_ALVO"})
        r = client.get("/api/pops/admin/usuarios/P_ALVO/setores")
        assert r.status_code == 200
        assert [s["sigla"] for s in r.json()] == ["CTI"]

    def test_pessoa_inexistente_recebe_404(self):
        client, _ = _client_para(dict(SUPERADMIN_POPS), pops_setores=list(_SETORES))
        r = client.put("/api/pops/admin/usuarios/P_NAO_EXISTE/setores", json={"setor_ids": ["s1"]})
        assert r.status_code == 404

    def test_demais_perfis_recebem_403(self):
        for perfil in ("gestor_qualidade", "gerente", "coordenador", None):
            atuante = dict(SUPERADMIN_POPS, perfil_pop=perfil)
            client, sb = _client_para(atuante, _alvo(perfil_pop="gerente"), pops_setores=list(_SETORES))
            r = client.put("/api/pops/admin/usuarios/P_ALVO/setores", json={"setor_ids": ["s1"]})
            assert r.status_code == 403, f"perfil_pop={perfil} deveria receber 403"
            assert sb.tables["pops_setores_participantes"] == []


# ─── Listagem de pessoas (porta do Superadmin POPs) ──────────────────────────


class TestListarUsuariosPops:
    def test_superadmin_lista_pessoas_com_perfil_pop(self):
        client, _ = _client_para(
            dict(SUPERADMIN_POPS),
            _alvo(pid="P2", perfil_pop="gerente", email="g@hsm.com"),
            _alvo(pid="P3", perfil_pop=None, email="c@hsm.com"),
        )
        r = client.get("/api/pops/admin/usuarios", params={"com_perfil": "true"})
        assert r.status_code == 200
        ids = [u["id"] for u in r.json()]
        assert "P2" in ids and "P_DIR" in ids
        assert "P3" not in ids

    def test_busca_por_nome_para_conceder_perfil(self):
        alvo = _alvo(pid="P2", auth_user_id=None)
        alvo["nome_completo"] = "Maria da Silva"
        client, _ = _client_para(dict(SUPERADMIN_POPS), alvo)
        r = client.get("/api/pops/admin/usuarios", params={"q": "maria"})
        assert r.status_code == 200
        body = r.json()
        assert [u["id"] for u in body] == ["P2"]
        # UI precisa saber se a pessoa já loga (provisionamento automático).
        assert body[0]["auth_user_id"] is None

    def test_demais_perfis_recebem_403(self):
        for perfil in ("gestor_qualidade", "gerente", "coordenador", None):
            atuante = dict(SUPERADMIN_POPS, perfil_pop=perfil)
            client, _ = _client_para(atuante)
            r = client.get("/api/pops/admin/usuarios")
            assert r.status_code == 403, f"perfil_pop={perfil} deveria receber 403"


# ─── Autoridade unificada: Super Admin de Reuniões concede perfil POP (#148) ───


class TestAutoridadeSuperAdminReunioes:
    """O Super Admin de Reuniões administra a concessão de perfil_pop (autoridade
    unificada, #148), sem ter perfil POP. A ortogonalidade de ACESSO do ADR 0007
    se mantém: administrar a concessão não dá acesso aos dados do contexto POPs.
    """

    def test_super_admin_reunioes_concede_perfil_pop(self):
        client, sb = _client_para(dict(SUPER_ADMIN_REUNIOES), _alvo())
        r = client.patch("/api/pops/admin/usuarios/P_ALVO/perfil-pop", json={"perfil_pop": "superadmin"})
        assert r.status_code == 200
        assert _row(sb, "P_ALVO")["perfil_pop"] == "superadmin"

    def test_super_admin_reunioes_concede_a_quem_nao_loga_provisiona(self):
        client, sb = _client_para(dict(SUPER_ADMIN_REUNIOES), _alvo(auth_user_id=None))
        r = client.patch("/api/pops/admin/usuarios/P_ALVO/perfil-pop", json={"perfil_pop": "coordenador"})
        assert r.status_code == 200
        assert r.json()["new_password"]
        assert _row(sb, "P_ALVO")["auth_user_id"] == "auth-novo-1"

    def test_super_admin_reunioes_revoga_perfil_pop(self):
        client, sb = _client_para(dict(SUPER_ADMIN_REUNIOES), _alvo(perfil_pop="coordenador"))
        r = client.patch("/api/pops/admin/usuarios/P_ALVO/perfil-pop", json={"perfil_pop": None})
        assert r.status_code == 200
        assert _row(sb, "P_ALVO")["perfil_pop"] is None

    def test_regular_sem_perfil_pop_continua_403(self):
        # Não-regressão: quem não é Super Admin de Reuniões nem superadmin POP segue barrado.
        regular = _alvo(pid="P_REG", auth_user_id="auth-reg", email="reg@hsm.com")
        client, sb = _client_para(regular, _alvo())
        r = client.patch("/api/pops/admin/usuarios/P_ALVO/perfil-pop", json={"perfil_pop": "gerente"})
        assert r.status_code == 403
        assert _row(sb, "P_ALVO")["perfil_pop"] is None

    def test_super_admin_reunioes_nao_acessa_area_interna_pops(self):
        # Ortogonalidade de ACESSO (ADR 0007): administrar a concessão não abre a
        # área interna dos POPs. A listagem do admin POPs segue exigindo perfil POP.
        client, _ = _client_para(dict(SUPER_ADMIN_REUNIOES), _alvo())
        r = client.get("/api/pops/admin/usuarios")
        assert r.status_code == 403
