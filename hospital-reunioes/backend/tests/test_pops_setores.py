"""Testes do CRUD de Setores do contexto POPs (/pops/setores) — issue #81.

Setor (POPs) é a unidade do organograma do HSM, com nome e sigla únicos
(a sigla é a base do Código travado HSM_[SIGLA]-[NNN]). Só o Superadmin
(POPs) cria/edita; demais perfis recebem 403. Terminologia conforme
docs/pops/CONTEXT.md; gating explícito por endpoint (ADR 0002).
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.dependencies import get_current_user, get_supabase_client  # noqa: E402
from app.routers.pops import setores as pops_setores_router  # noqa: E402

# ─── Mock Supabase (query builder mínimo p/ participantes + pops_setores) ────


@dataclass
class _Result:
    data: list


class _TableQuery:
    def __init__(self, rows: list[dict], table: str):
        self._rows = rows
        self._table = table
        self._filters: dict = {}
        self._insert_payload: dict | None = None
        self._update_payload: dict | None = None

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, col, value):
        self._filters[col] = value
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def insert(self, payload: dict):
        self._insert_payload = dict(payload)
        return self

    def update(self, payload: dict):
        self._update_payload = dict(payload)
        return self

    def execute(self):
        if self._insert_payload is not None:
            row = dict(self._insert_payload)
            row.setdefault("id", f"{self._table}-{len(self._rows) + 1}")
            self._rows.append(row)
            return _Result(data=[dict(row)])

        filtered = [r for r in self._rows if all(r.get(c) == v for c, v in self._filters.items())]

        if self._update_payload is not None:
            for row in filtered:
                row.update(self._update_payload)
            return _Result(data=[dict(r) for r in filtered])

        return _Result(data=[dict(r) for r in filtered])


class _SupabaseMock:
    def __init__(self, participantes: list[dict] | None = None, pops_setores: list[dict] | None = None):
        self.tables: dict[str, list[dict]] = {
            "participantes": participantes or [],
            "pops_setores": pops_setores or [],
        }

    def table(self, name: str):
        if name not in self.tables:
            raise AssertionError(f"Tabela inesperada: {name}")
        return _TableQuery(self.tables[name], name)


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _pessoa(
    pid: str = "P1",
    perfil_pop: str | None = None,
    access_profile: str | None = "regular",
) -> dict:
    """Linha de participantes — pessoa única dos dois contextos (ADR 0007)."""
    return {
        "id": pid,
        "auth_user_id": f"auth-{pid}",
        "email": f"{pid.lower()}@hsm.com",
        "nome_completo": f"Pessoa {pid}",
        "cargo": "Cargo",
        "area": None,
        "setor": None,
        "role": None,
        "ativo": True,
        "is_externo": False,
        "is_super_admin": False,
        "access_profile": access_profile,
        "perfil_pop": perfil_pop,
        "data_cadastro": "2026-06-01",
    }


def _client_para(pessoa: dict, pops_setores: list[dict] | None = None) -> tuple[TestClient, _SupabaseMock]:
    app = FastAPI()
    app.include_router(pops_setores_router.router, prefix="/api")

    sb = _SupabaseMock(participantes=[pessoa], pops_setores=pops_setores)

    async def _fake_user() -> dict[str, Any]:
        return {"id": pessoa["auth_user_id"], "email": pessoa["email"], "metadata": {}}

    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_supabase_client] = lambda: sb
    return TestClient(app), sb


# ─── Criar Setor ──────────────────────────────────────────────────────────────


class TestCriarSetor:
    def test_superadmin_pops_cria_setor_com_nome_e_sigla(self):
        client, sb = _client_para(_pessoa(perfil_pop="superadmin", access_profile=None))
        r = client.post("/api/pops/setores", json={"nome": "Centro de Terapia Intensiva", "sigla": "CTI"})
        assert r.status_code == 201
        body = r.json()
        assert body["nome"] == "Centro de Terapia Intensiva"
        assert body["sigla"] == "CTI"
        assert body["id"]
        assert len(sb.tables["pops_setores"]) == 1

    def test_demais_perfis_pop_recebem_403(self):
        for perfil in ("gestor_qualidade", "gerente", "coordenador"):
            client, sb = _client_para(_pessoa(perfil_pop=perfil, access_profile=None))
            r = client.post("/api/pops/setores", json={"nome": "Farmácia", "sigla": "FAR"})
            assert r.status_code == 403, f"perfil_pop={perfil} deveria receber 403"
            assert sb.tables["pops_setores"] == []

    def test_facilitador_sem_perfil_pop_recebe_403(self):
        # Mesmo Super admin das Reuniões (homônimo, conceito distinto) não passa.
        pessoa = _pessoa(perfil_pop=None, access_profile="super_admin")
        pessoa["is_super_admin"] = True
        client, sb = _client_para(pessoa)
        r = client.post("/api/pops/setores", json={"nome": "Farmácia", "sigla": "FAR"})
        assert r.status_code == 403
        assert sb.tables["pops_setores"] == []

    def test_nome_duplicado_recebe_409(self):
        client, sb = _client_para(
            _pessoa(perfil_pop="superadmin", access_profile=None),
            pops_setores=[{"id": "s1", "nome": "Farmácia", "sigla": "FAR"}],
        )
        r = client.post("/api/pops/setores", json={"nome": "farmácia", "sigla": "FRM"})
        assert r.status_code == 409
        assert len(sb.tables["pops_setores"]) == 1

    def test_sigla_duplicada_recebe_409(self):
        client, _ = _client_para(
            _pessoa(perfil_pop="superadmin", access_profile=None),
            pops_setores=[{"id": "s1", "nome": "Farmácia", "sigla": "FAR"}],
        )
        r = client.post("/api/pops/setores", json={"nome": "Faturamento", "sigla": "far"})
        assert r.status_code == 409


# ─── Listar e editar Setor ────────────────────────────────────────────────────


class TestListarSetores:
    def test_qualquer_perfil_pop_lista_setores(self):
        # Leitura de Setores é necessária a todos os perfis do contexto
        # (Gerente/Coordenador veem os próprios Setores nas fatias seguintes).
        setores = [
            {"id": "s1", "nome": "Farmácia", "sigla": "FAR"},
            {"id": "s2", "nome": "CTI", "sigla": "CTI"},
        ]
        for perfil in ("superadmin", "gestor_qualidade", "gerente", "coordenador"):
            client, _ = _client_para(_pessoa(perfil_pop=perfil, access_profile=None), pops_setores=list(setores))
            r = client.get("/api/pops/setores")
            assert r.status_code == 200, f"perfil_pop={perfil} deveria listar"
            assert [s["sigla"] for s in r.json()] == ["FAR", "CTI"]

    def test_facilitador_sem_perfil_pop_recebe_403(self):
        client, _ = _client_para(_pessoa(perfil_pop=None, access_profile="regular"))
        r = client.get("/api/pops/setores")
        assert r.status_code == 403


class TestEditarSetor:
    def test_superadmin_pops_edita_nome_e_sigla(self):
        client, sb = _client_para(
            _pessoa(perfil_pop="superadmin", access_profile=None),
            pops_setores=[{"id": "s1", "nome": "Farmacia", "sigla": "FRM"}],
        )
        r = client.patch("/api/pops/setores/s1", json={"nome": "Farmácia", "sigla": "far"})
        assert r.status_code == 200
        body = r.json()
        assert body["nome"] == "Farmácia"
        assert body["sigla"] == "FAR"
        assert sb.tables["pops_setores"][0]["sigla"] == "FAR"

    def test_editar_para_nome_de_outro_setor_recebe_409(self):
        client, _ = _client_para(
            _pessoa(perfil_pop="superadmin", access_profile=None),
            pops_setores=[
                {"id": "s1", "nome": "Farmácia", "sigla": "FAR"},
                {"id": "s2", "nome": "CTI", "sigla": "CTI"},
            ],
        )
        r = client.patch("/api/pops/setores/s2", json={"nome": "FARMÁCIA"})
        assert r.status_code == 409

    def test_editar_mantendo_proprio_nome_nao_conflita(self):
        client, _ = _client_para(
            _pessoa(perfil_pop="superadmin", access_profile=None),
            pops_setores=[{"id": "s1", "nome": "Farmácia", "sigla": "FAR"}],
        )
        r = client.patch("/api/pops/setores/s1", json={"nome": "Farmácia", "sigla": "FAR"})
        assert r.status_code == 200

    def test_setor_inexistente_recebe_404(self):
        client, _ = _client_para(_pessoa(perfil_pop="superadmin", access_profile=None))
        r = client.patch("/api/pops/setores/s9", json={"nome": "X"})
        assert r.status_code == 404

    def test_demais_perfis_pop_recebem_403_no_patch(self):
        for perfil in ("gestor_qualidade", "gerente", "coordenador"):
            client, _ = _client_para(
                _pessoa(perfil_pop=perfil, access_profile=None),
                pops_setores=[{"id": "s1", "nome": "Farmácia", "sigla": "FAR"}],
            )
            r = client.patch("/api/pops/setores/s1", json={"nome": "Outro"})
            assert r.status_code == 403, f"perfil_pop={perfil} deveria receber 403"
