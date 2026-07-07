"""Testes da exclusão de POP pré-assinatura pelo Superadmin (issue #185).

Como Superadmin de POPs, excluir um POP que ainda não chegou à assinatura
(teste, duplicado, abandonado). DELETE /pops/{pop_id}, gating igual ao CRUD
de Setores (require_perfil_pop("superadmin")). Permitido apenas quando
NENHUMA Versão chegou a EM_ASSINATURA ou além; senão 409 e nada apagado.
Hard delete em cascata: Versões (o fluxograma SVG vive no rascunho JSONB
delas), Materiais de referência (registros + arquivos no storage) e
Devoluções. As designações de papéis são colunas do próprio POP.

Supabase mock no padrão de test_pops_materiais (com delete); storage mockado
no boundary (app.services.storage).
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
from app.routers.pops import pops as pops_router  # noqa: E402
from app.services import storage  # noqa: E402

# ─── Mock Supabase (padrão test_pops_materiais, com delete) ───────────────────


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

    def insert(self, payload: dict | list):
        rows = payload if isinstance(payload, list) else [payload]
        self._insert_payload = [dict(r) for r in rows]
        return self

    def update(self, payload: dict):
        self._update_payload = dict(payload)
        return self

    def delete(self):
        self._delete = True
        return self

    def execute(self):
        if self._insert_payload is not None:
            inserted = []
            for row in self._insert_payload:
                row = dict(row)
                row.setdefault("id", f"{self._table}-{len(self._rows) + 1}")
                self._rows.append(row)
                inserted.append(dict(row))
            return _Result(data=inserted)

        filtered = [
            r
            for r in self._rows
            if all(r.get(c) == v for c, v in self._filters.items())
            and all(r.get(c) in vs for c, vs in self._in_filters.items())
        ]

        if self._delete:
            self._rows[:] = [r for r in self._rows if r not in filtered]
            return _Result(data=[dict(r) for r in filtered])

        if self._update_payload is not None:
            for row in filtered:
                row.update(self._update_payload)
            return _Result(data=[dict(r) for r in filtered])

        return _Result(data=[dict(r) for r in filtered])


class _SupabaseMock:
    def __init__(self, tables: dict[str, list[dict]]):
        self.tables = tables

    def table(self, name: str):
        if name not in self.tables:
            raise AssertionError(f"Tabela inesperada: {name}")
        return _TableQuery(self.tables[name], name)


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _pessoa(pid: str, perfil_pop: str | None = None) -> dict:
    return {
        "id": pid,
        "auth_user_id": f"auth-{pid}",
        "email": f"{pid.lower()}@hsm.com",
        "nome_completo": f"Pessoa {pid}",
        "cargo": "Cargo",
        "ativo": True,
        "is_externo": False,
        "is_super_admin": False,
        "access_profile": None,
        "perfil_pop": perfil_pop,
    }


def _pop(pid: str = "pop-1", **over) -> dict:
    base = {
        "id": pid,
        "setor_id": "s-cti",
        "numero": 1,
        "codigo": "HSM_CTI-001",
        "nome": "Higienização das Mãos",
        "criticidade": "CRITICA",
        "base_normativa": "RDC 63/2011",
        "periodicidade_revisao": "1_ano",
        "prazo_elaboracao_dias": 15,
        "prazo_revisao_dias": 30,
        "elaborador_id": "P1",
        "revisor_id": "P2",
        "validador_id": "P3",
        "criado_por": "P4",
        "created_at": "2026-06-10T12:00:00+00:00",
    }
    base.update(over)
    return base


def _versao(vid: str = "v-1", *, pop_id: str = "pop-1", estado: str = "A_ELABORAR", **over) -> dict:
    base = {
        "id": vid,
        "pop_id": pop_id,
        "numero_versao": "1.0",
        "estado": estado,
        "rascunho": None,
        "created_at": "2026-06-10T12:00:00+00:00",
    }
    base.update(over)
    return base


def _material(mid: str, *, versao_id: str = "v-1", storage_path: str | None = "definido", **over) -> dict:
    base = {
        "id": mid,
        "versao_id": versao_id,
        "filename": f"{mid}.txt",
        "extensao": ".txt",
        "tamanho_bytes": 10,
        "storage_path": f"versao-{versao_id}/{mid}.txt" if storage_path == "definido" else storage_path,
        "texto": "Texto.",
        "criado_por": "P1",
        "created_at": "2026-06-11T09:00:00+00:00",
    }
    base.update(over)
    return base


SUPERADMIN = _pessoa("ADM", perfil_pop="superadmin")
GESTOR_QUALIDADE = _pessoa("GQ", perfil_pop="gestor_qualidade")
GERENTE = _pessoa("GE", perfil_pop="gerente")
COORDENADOR = _pessoa("CO", perfil_pop="coordenador")
SEM_PERFIL = _pessoa("NX", perfil_pop=None)


def _sb(
    *,
    pops: list[dict] | None = None,
    versoes: list[dict] | None = None,
    materiais: list[dict] | None = None,
    devolucoes: list[dict] | None = None,
) -> _SupabaseMock:
    return _SupabaseMock(
        {
            "participantes": [SUPERADMIN, GESTOR_QUALIDADE, GERENTE, COORDENADOR, SEM_PERFIL],
            "pops_setores": [{"id": "s-cti", "nome": "Coordenação do CTI", "sigla": "CTI"}],
            "pops": pops if pops is not None else [_pop()],
            "pops_versoes": versoes if versoes is not None else [_versao()],
            "pops_materiais_referencia": list(materiais or []),
            "pops_devolucoes": list(devolucoes or []),
            "audit_log": [],
        }
    )


@pytest.fixture(autouse=True)
def storage_mock(monkeypatch) -> SimpleNamespace:
    """Storage no boundary de IO: registra remoções sem rede."""
    chamadas = SimpleNamespace(removidos=[])

    def _fake_delete(_supabase, bucket: str, path: str) -> bool:
        chamadas.removidos.append({"bucket": bucket, "path": path})
        return True

    monkeypatch.setattr(storage, "delete_file", _fake_delete)
    return chamadas


def _client_para(pessoa: dict, sb: _SupabaseMock) -> TestClient:
    app = FastAPI()
    app.include_router(pops_router.router, prefix="/api")

    async def _fake_user() -> dict[str, Any]:
        return {"id": pessoa["auth_user_id"], "email": pessoa["email"], "metadata": {}}

    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_supabase_client] = lambda: sb
    return TestClient(app)


# ═══════════════════════════════════════════════════════════════════════════
# Exclusão feliz: qualquer estado pré-assinatura, cascata completa
# ═══════════════════════════════════════════════════════════════════════════


class TestExclusaoPermitida:
    @pytest.mark.parametrize("estado", ["A_ELABORAR", "EM_ELABORACAO", "EM_REVISAO", "EM_VALIDACAO"])
    def test_superadmin_exclui_pop_pre_assinatura(self, estado):
        """CA: Superadmin POPs exclui POP em qualquer estado pré-assinatura."""
        sb = _sb(versoes=[_versao(estado=estado)])
        client = _client_para(SUPERADMIN, sb)

        res = client.delete("/api/pops/pop-1")

        assert res.status_code == 204
        assert sb.tables["pops"] == []
        assert sb.tables["pops_versoes"] == []

    def test_cascata_remove_versoes_materiais_e_devolucoes(self, storage_mock):
        """CA: Versões, Materiais (registros + arquivos no storage) e
        Devoluções somem junto com o POP."""
        versoes = [
            _versao("v-1", estado="EM_REVISAO"),
            _versao("v-2", numero_versao="1.1", estado="EM_ELABORACAO"),
        ]
        materiais = [
            _material("m-1", versao_id="v-1"),
            _material("m-2", versao_id="v-2"),
        ]
        devolucoes = [{"id": "d-1", "versao_id": "v-1", "etapa": "REVISAO", "comentarios": "Ajustar."}]
        sb = _sb(versoes=versoes, materiais=materiais, devolucoes=devolucoes)
        client = _client_para(SUPERADMIN, sb)

        res = client.delete("/api/pops/pop-1")

        assert res.status_code == 204
        assert sb.tables["pops"] == []
        assert sb.tables["pops_versoes"] == []
        assert sb.tables["pops_materiais_referencia"] == []
        assert sb.tables["pops_devolucoes"] == []
        assert sorted(r["path"] for r in storage_mock.removidos) == [
            "versao-v-1/m-1.txt",
            "versao-v-2/m-2.txt",
        ]

    def test_material_sem_storage_path_nao_chama_storage(self, storage_mock):
        """Material persistido com storage indisponível (path nulo) não gera
        chamada de remoção, e a exclusão segue normal."""
        sb = _sb(materiais=[_material("m-1", storage_path=None)])
        client = _client_para(SUPERADMIN, sb)

        res = client.delete("/api/pops/pop-1")

        assert res.status_code == 204
        assert storage_mock.removidos == []
        assert sb.tables["pops_materiais_referencia"] == []

    def test_exclusao_nao_toca_outros_pops(self):
        """Só o POP alvo (e suas dependências) some; os demais ficam."""
        pops = [_pop("pop-1"), _pop("pop-2", codigo="HSM_CTI-002", numero=2)]
        versoes = [_versao("v-1", pop_id="pop-1"), _versao("v-2", pop_id="pop-2")]
        materiais = [_material("m-1", versao_id="v-1"), _material("m-2", versao_id="v-2")]
        sb = _sb(pops=pops, versoes=versoes, materiais=materiais)
        client = _client_para(SUPERADMIN, sb)

        res = client.delete("/api/pops/pop-1")

        assert res.status_code == 204
        assert [p["id"] for p in sb.tables["pops"]] == ["pop-2"]
        assert [v["id"] for v in sb.tables["pops_versoes"]] == ["v-2"]
        assert [m["id"] for m in sb.tables["pops_materiais_referencia"]] == ["m-2"]

    def test_exclusao_grava_audit_log(self):
        sb = _sb()
        client = _client_para(SUPERADMIN, sb)

        res = client.delete("/api/pops/pop-1")

        assert res.status_code == 204
        acoes = [r for r in sb.tables["audit_log"] if r.get("action") == "POPS_EXCLUIR_POP"]
        assert len(acoes) == 1
        assert acoes[0]["target_id"] == "pop-1"
        assert "HSM_CTI-001" in str(acoes[0].get("metadata"))


# ═══════════════════════════════════════════════════════════════════════════
# Bloqueio por estado: qualquer Versão em assinatura ou além → 409
# ═══════════════════════════════════════════════════════════════════════════


class TestBloqueioPorEstado:
    @pytest.mark.parametrize("estado", ["EM_ASSINATURA", "PUBLICADO"])
    def test_versao_em_assinatura_ou_alem_409_e_nada_apagado(self, estado, storage_mock):
        sb = _sb(versoes=[_versao(estado=estado)], materiais=[_material("m-1")])
        client = _client_para(SUPERADMIN, sb)

        res = client.delete("/api/pops/pop-1")

        assert res.status_code == 409
        assert "assinatura" in res.json()["detail"].lower()
        assert len(sb.tables["pops"]) == 1
        assert len(sb.tables["pops_versoes"]) == 1
        assert len(sb.tables["pops_materiais_referencia"]) == 1
        assert storage_mock.removidos == []

    def test_basta_uma_versao_publicada_para_bloquear(self):
        """POP com histórico: uma Versão pré-assinatura não libera se outra
        já foi publicada."""
        versoes = [
            _versao("v-1", estado="PUBLICADO"),
            _versao("v-2", numero_versao="2.0", estado="EM_ELABORACAO"),
        ]
        sb = _sb(versoes=versoes)
        client = _client_para(SUPERADMIN, sb)

        res = client.delete("/api/pops/pop-1")

        assert res.status_code == 409
        assert len(sb.tables["pops"]) == 1
        assert len(sb.tables["pops_versoes"]) == 2


# ═══════════════════════════════════════════════════════════════════════════
# Bloqueio por perfil: só o Superadmin POPs exclui
# ═══════════════════════════════════════════════════════════════════════════


class TestBloqueioPorPerfil:
    @pytest.mark.parametrize("pessoa", [GESTOR_QUALIDADE, GERENTE, COORDENADOR, SEM_PERFIL])
    def test_nao_superadmin_403_e_nada_apagado(self, pessoa):
        sb = _sb(materiais=[_material("m-1")])
        client = _client_para(pessoa, sb)

        res = client.delete("/api/pops/pop-1")

        assert res.status_code == 403, f"{pessoa['id']} deveria levar 403"
        assert len(sb.tables["pops"]) == 1
        assert len(sb.tables["pops_versoes"]) == 1
        assert len(sb.tables["pops_materiais_referencia"]) == 1


# ═══════════════════════════════════════════════════════════════════════════
# POP inexistente
# ═══════════════════════════════════════════════════════════════════════════


class TestPopInexistente:
    def test_pop_inexistente_404(self):
        client = _client_para(SUPERADMIN, _sb())
        res = client.delete("/api/pops/pop-999")
        assert res.status_code == 404
