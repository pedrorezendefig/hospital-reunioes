"""Matriz de acesso perfil × endpoints — POPs L1 (issue #81, critério 5).

Cruza cada persona (eixos access_profile × perfil_pop, ADR 0007) com os
endpoints de Setores/admin do contexto POPs e com o gating cruzado entre
contextos. Persona fora do conjunto permitido recebe 403; dentro, nunca 403.
A pessoa com papel nos dois contextos transita no mesmo login.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.dependencies import get_current_user, get_supabase_client  # noqa: E402
from app.routers import reunioes as reunioes_router  # noqa: E402
from app.routers.pops import setores as pops_setores_router  # noqa: E402
from app.routers.pops import usuarios as pops_usuarios_router  # noqa: E402

# ─── Mock Supabase ────────────────────────────────────────────────────────────


@dataclass
class _Result:
    data: list
    count: int = 0


class _TableQuery:
    def __init__(self, rows: list[dict]):
        self._rows = rows
        self._filters: dict = {}
        self._in_filters: dict = {}
        self._insert_payload: list[dict] | None = None
        self._update_payload: dict | None = None
        self._is_delete = False

    def eq(self, col, value):
        self._filters[col] = value
        return self

    def in_(self, col, values):
        self._in_filters[col] = list(values)
        return self

    def insert(self, payload):
        rows = payload if isinstance(payload, list) else [payload]
        self._insert_payload = [dict(r) for r in rows]
        return self

    def update(self, payload: dict):
        self._update_payload = dict(payload)
        return self

    def delete(self):
        self._is_delete = True
        return self

    def __getattr__(self, _name):
        # select/order/range/limit/or_/ilike/neq... — chainável, sem efeito.
        return lambda *_a, **_kw: self

    def _match(self, row: dict) -> bool:
        if not all(row.get(c) == v for c, v in self._filters.items()):
            return False
        return all(row.get(c) in v for c, v in self._in_filters.items())

    def execute(self):
        if self._insert_payload is not None:
            for row in self._insert_payload:
                row.setdefault("id", f"id-{len(self._rows) + 1}")
            self._rows.extend(self._insert_payload)
            return _Result(data=[dict(r) for r in self._insert_payload])

        filtered = [r for r in self._rows if self._match(r)]

        if self._is_delete:
            self._rows[:] = [r for r in self._rows if not self._match(r)]
            return _Result(data=[dict(r) for r in filtered])

        if self._update_payload is not None:
            for row in filtered:
                row.update(self._update_payload)
            return _Result(data=[dict(r) for r in filtered])

        return _Result(data=[dict(r) for r in filtered])


class _SupabaseMock:
    def __init__(self, tables: dict[str, list[dict]]):
        self.tables = tables
        self.auth = SimpleNamespace(
            admin=SimpleNamespace(create_user=lambda payload: SimpleNamespace(user=SimpleNamespace(id="auth-novo")))
        )

    def table(self, name: str):
        return _TableQuery(self.tables.setdefault(name, []))


# ─── Personas (access_profile, perfil_pop) ────────────────────────────────────

PERSONAS: dict[str, tuple[str | None, str | None]] = {
    "superadmin_pops": (None, "superadmin"),
    "gestor_qualidade": (None, "gestor_qualidade"),
    "gerente_pop": (None, "gerente"),
    "coordenador_pop": (None, "coordenador"),
    "facilitador": ("regular", None),
    "secretaria": ("secretaria", None),
    "super_admin_reunioes": ("super_admin", None),
    "ambos": ("regular", "gerente"),
}

TODOS_PERFIS_POP = {"superadmin_pops", "gestor_qualidade", "gerente_pop", "coordenador_pop", "ambos"}
CONTEXTO_REUNIOES = {"facilitador", "secretaria", "super_admin_reunioes", "ambos"}

# (método, path, payload, personas autorizadas)
CASOS: list[tuple[str, str, dict | None, set[str]]] = [
    # Setores: gestão é exclusiva do Superadmin (POPs); leitura é do contexto.
    ("POST", "/api/pops/setores", {"nome": "Novo Setor", "sigla": "NS"}, {"superadmin_pops"}),
    ("GET", "/api/pops/setores", None, TODOS_PERFIS_POP),
    ("PATCH", "/api/pops/setores/s1", {"nome": "Setor Editado"}, {"superadmin_pops"}),
    # Admin de usuários POPs: exclusivo do Superadmin (POPs).
    ("PATCH", "/api/pops/admin/usuarios/P_ALVO/perfil-pop", {"perfil_pop": "gerente"}, {"superadmin_pops"}),
    ("PUT", "/api/pops/admin/usuarios/P_ALVO/setores", {"setor_ids": ["s1"]}, {"superadmin_pops"}),
    ("GET", "/api/pops/admin/usuarios/P_ALVO/setores", None, {"superadmin_pops"}),
    # Gating cruzado: contexto Reuniões é invisível para quem só tem perfil POP.
    ("GET", "/api/reunioes/calendario", None, CONTEXTO_REUNIOES),
]


def _client_para(persona: str) -> TestClient:
    access_profile, perfil_pop = PERSONAS[persona]
    pessoa = {
        "id": "P1",
        "auth_user_id": "auth-1",
        "email": "p1@hsm.com",
        "nome_completo": "Persona",
        "cargo": None,
        "area": None,
        "setor": None,
        "role": None,
        "ativo": True,
        "is_externo": False,
        "is_super_admin": access_profile == "super_admin",
        "access_profile": access_profile,
        "perfil_pop": perfil_pop,
        "data_cadastro": "2026-06-01",
    }
    alvo = {
        "id": "P_ALVO",
        "auth_user_id": "auth-alvo",
        "email": "alvo@hsm.com",
        "nome_completo": "Pessoa Alvo",
        "ativo": True,
        "is_externo": False,
        "is_super_admin": False,
        "access_profile": "regular",
        "perfil_pop": None,
    }

    app = FastAPI()
    for mod in (pops_setores_router, pops_usuarios_router, reunioes_router):
        app.include_router(mod.router, prefix="/api")

    sb = _SupabaseMock(
        tables={
            "participantes": [pessoa, alvo],
            "pops_setores": [{"id": "s1", "nome": "Farmácia", "sigla": "FAR"}],
        }
    )

    async def _fake_user() -> dict[str, Any]:
        return {"id": pessoa["auth_user_id"], "email": pessoa["email"], "metadata": {}}

    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_supabase_client] = lambda: sb
    return TestClient(app)


# ─── Matriz ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("persona", list(PERSONAS))
@pytest.mark.parametrize("method,path,payload,autorizados", CASOS, ids=lambda v: v if isinstance(v, str) else "")
def test_matriz_de_acesso(persona, method, path, payload, autorizados):
    client = _client_para(persona)
    r = client.request(method, path, json=payload)
    if persona in autorizados:
        assert r.status_code != 403, f"{persona} deveria acessar {method} {path} (recebeu 403)"
        assert r.status_code < 500, f"{persona} em {method} {path} estourou {r.status_code}"
    else:
        assert r.status_code == 403, f"{persona} NÃO deveria acessar {method} {path} (recebeu {r.status_code})"


def test_pessoa_com_os_dois_papeis_transita_no_mesmo_login():
    client = _client_para("ambos")
    assert client.get("/api/pops/setores").status_code == 200
    assert client.get("/api/reunioes/calendario").status_code == 200
