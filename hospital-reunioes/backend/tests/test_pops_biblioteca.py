"""Testes da Biblioteca de POPs Publicados (issue #87).

O repositório oficial: lista dos POPs com Versão Publicada por Setor
(código, nome, versão vigente, datas de cada etapa, responsáveis) + download
do PDF assinado — tudo respeitando o escopo do perfil (Coordenador: seu
Setor; Gerente: seus Setores; Gestor de Qualidade/Superadmin: todos).

As datas de cada etapa vêm da auditoria das transições (audit_log) e da
data_publicacao da Versão. Terminologia conforme docs/pops/CONTEXT.md.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.dependencies import get_current_user, get_supabase_client  # noqa: E402
from app.routers.pops import biblioteca as biblioteca_router  # noqa: E402
from app.routers.pops import documento as documento_router  # noqa: E402
from app.services import pops_pdf_service, storage  # noqa: E402

# ─── Mock Supabase (padrão dos testes de POPs) ───────────────────────────────


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


# ─── Dados ───────────────────────────────────────────────────────────────────


def _pessoa(pid: str, perfil_pop: str | None = None) -> dict:
    return {
        "id": pid,
        "auth_user_id": f"auth-{pid}",
        "email": f"{pid.lower()}@hsm.com",
        "nome_completo": f"Pessoa {pid}",
        "ativo": True,
        "access_profile": None,
        "perfil_pop": perfil_pop,
    }


ELABORADOR = _pessoa("P1", perfil_pop="coordenador")
REVISOR = _pessoa("P2", perfil_pop="coordenador")
VALIDADOR = _pessoa("P3", perfil_pop="gerente")
INTRUSO_OUTRO_SETOR = _pessoa("P4", perfil_pop="coordenador")
SEM_PERFIL = _pessoa("P5", perfil_pop=None)
COORD_CTI = _pessoa("P6", perfil_pop="coordenador")
GESTOR = _pessoa("P7", perfil_pop="gestor_qualidade")

DATA_PUBLICACAO = "2026-06-12T15:00:00+00:00"


def _pop(pid: str, setor_id: str, codigo: str, **over) -> dict:
    base = {
        "id": pid,
        "setor_id": setor_id,
        "codigo": codigo,
        "nome": "Cateter Venoso Central",
        "criticidade": "CRITICA",
        "periodicidade_revisao": "1_ano",
        "prazo_elaboracao_dias": 15,
        "prazo_revisao_dias": 30,
        "elaborador_id": "P1",
        "revisor_id": "P2",
        "validador_id": "P3",
        "criado_por": "P6",
        "created_at": "2026-06-01T12:00:00+00:00",
    }
    base.update(over)
    return base


def _versao(vid: str, pop_id: str, estado: str = "PUBLICADO", **over) -> dict:
    base = {
        "id": vid,
        "pop_id": pop_id,
        "numero_versao": "1.0",
        "estado": estado,
        "rascunho": {"objetivo": "Padronizar."},
        "envelope_id_clicksign": "env-1" if estado == "PUBLICADO" else None,
        "envelope_key_clicksign": "doc-1" if estado == "PUBLICADO" else None,
        "url_pdf_assinado": "http://storage/pdfs-assinados/pops/x.pdf" if estado == "PUBLICADO" else None,
        "data_publicacao": DATA_PUBLICACAO if estado == "PUBLICADO" else None,
    }
    base.update(over)
    return base


def _audit(versao_id: str, action: str, ts: str) -> dict:
    return {
        "id": f"a-{action}-{ts}",
        "action": action,
        "target_type": "pop_versao",
        "target_id": versao_id,
        "timestamp": ts,
        "actor_id": "P2",
        "actor_email": "p2@hsm.com",
        "metadata": {},
    }


def _sb() -> _SupabaseMock:
    return _SupabaseMock(
        {
            "participantes": [ELABORADOR, REVISOR, VALIDADOR, INTRUSO_OUTRO_SETOR, SEM_PERFIL, COORD_CTI, GESTOR],
            "pops_setores": [
                {"id": "s-cti", "nome": "Coordenação do CTI", "sigla": "CTI"},
                {"id": "s-outro", "nome": "Coordenação de Farmácia", "sigla": "FAR"},
            ],
            "pops_setores_participantes": [
                {"participante_id": "P4", "setor_id": "s-outro"},
                {"participante_id": "P6", "setor_id": "s-cti"},
            ],
            "pops": [
                _pop("pop-1", "s-cti", "HSM_CTI-001"),
                _pop("pop-2", "s-outro", "HSM_FAR-001", nome="Dispensação de Medicamentos"),
                _pop("pop-3", "s-cti", "HSM_CTI-002", nome="Higienização das Mãos"),
            ],
            "pops_versoes": [
                _versao("v-1", "pop-1"),
                _versao("v-2", "pop-2"),
                _versao("v-3", "pop-3", estado="EM_REVISAO"),
            ],
            "audit_log": [
                # Duas aprovações de versão final (houve Devolução): vale a mais recente
                _audit("v-1", "POPS_APROVAR_VERSAO_FINAL", "2026-06-09T09:00:00+00:00"),
                _audit("v-1", "POPS_APROVAR_VERSAO_FINAL", "2026-06-10T09:00:00+00:00"),
                _audit("v-1", "POPS_APROVAR_REVISAO", "2026-06-11T09:00:00+00:00"),
                _audit("v-1", "POPS_APROVAR_VALIDACAO", "2026-06-12T09:00:00+00:00"),
            ],
        }
    )


def _client_para(pessoa: dict, sb: _SupabaseMock) -> TestClient:
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded

    from app.limiter import limiter

    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(biblioteca_router.router, prefix="/api")
    app.include_router(documento_router.router, prefix="/api")

    async def _fake_user() -> dict[str, Any]:
        return {"id": pessoa["auth_user_id"], "email": pessoa["email"], "metadata": {}}

    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_supabase_client] = lambda: sb
    return TestClient(app)


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    from app.limiter import limiter

    limiter._storage.reset()
    yield


@pytest.fixture
def downloads(monkeypatch) -> list[dict]:
    feitos: list[dict] = []

    def _fake(supabase, bucket, path):
        feitos.append({"bucket": bucket, "path": path})
        return b"%PDF-signed"

    monkeypatch.setattr(storage, "download_file", _fake)
    return feitos


@pytest.fixture
def pdf_gerado(monkeypatch) -> list[dict]:
    chamadas: list[dict] = []

    def _fake(**kwargs) -> bytes:
        chamadas.append(kwargs)
        return b"%PDF-preliminar"

    monkeypatch.setattr(pops_pdf_service, "gerar_pdf_pop", _fake)
    return chamadas


# ═══════════════════════════════════════════════════════════════════════════
# CA: Biblioteca lista Publicados por Setor respeitando escopo
# ═══════════════════════════════════════════════════════════════════════════


class TestEscopoDaBiblioteca:
    def test_gestor_de_qualidade_ve_publicados_de_todos_os_setores(self):
        client = _client_para(GESTOR, _sb())

        res = client.get("/api/pops/biblioteca")

        assert res.status_code == 200
        itens = res.json()
        assert [i["codigo"] for i in itens] == ["HSM_CTI-001", "HSM_FAR-001"]

    def test_em_fluxo_nao_aparece_na_biblioteca(self):
        """pop-3 (EM_REVISAO) não é Publicado — Biblioteca é só o oficial."""
        client = _client_para(GESTOR, _sb())

        res = client.get("/api/pops/biblioteca")

        assert "HSM_CTI-002" not in [i["codigo"] for i in res.json()]

    def test_coordenador_ve_apenas_seu_setor(self):
        client = _client_para(COORD_CTI, _sb())

        res = client.get("/api/pops/biblioteca")

        assert res.status_code == 200
        assert [i["codigo"] for i in res.json()] == ["HSM_CTI-001"]

    def test_sem_perfil_pop_403(self):
        client = _client_para(SEM_PERFIL, _sb())

        res = client.get("/api/pops/biblioteca")

        assert res.status_code == 403


# ═══════════════════════════════════════════════════════════════════════════
# CA: metadados completos — código, nome, versão, datas de cada etapa,
# responsáveis
# ═══════════════════════════════════════════════════════════════════════════


class TestMetadados:
    def test_item_traz_metadados_completos(self):
        client = _client_para(GESTOR, _sb())

        res = client.get("/api/pops/biblioteca")

        item = next(i for i in res.json() if i["codigo"] == "HSM_CTI-001")
        assert item["pop_id"] == "pop-1"
        assert item["nome"] == "Cateter Venoso Central"
        assert item["setor_nome"] == "Coordenação do CTI"
        assert item["setor_sigla"] == "CTI"
        assert item["numero_versao"] == "1.0"
        assert item["criticidade"] == "CRITICA"
        assert item["periodicidade_revisao"] == "1_ano"

        # Responsáveis designados, por nome
        assert item["elaborador_nome"] == "Pessoa P1"
        assert item["revisor_nome"] == "Pessoa P2"
        assert item["validador_nome"] == "Pessoa P3"

        # Datas de cada etapa: criação, fim da elaboração (a mais recente,
        # houve Devolução), aprovações e publicação
        assert item["criado_em"] == "2026-06-01T12:00:00+00:00"
        assert item["elaboracao_concluida_em"] == "2026-06-10T09:00:00+00:00"
        assert item["revisao_aprovada_em"] == "2026-06-11T09:00:00+00:00"
        assert item["validacao_aprovada_em"] == "2026-06-12T09:00:00+00:00"
        assert item["publicado_em"] == DATA_PUBLICACAO

    def test_datas_de_etapa_ausentes_nao_quebram(self):
        """pop-2 não tem trilha de auditoria no mock — as datas de etapa vêm
        nulas e o item continua listável (dado legado/incompleto)."""
        client = _client_para(GESTOR, _sb())

        res = client.get("/api/pops/biblioteca")

        item = next(i for i in res.json() if i["codigo"] == "HSM_FAR-001")
        assert item["elaboracao_concluida_em"] is None
        assert item["publicado_em"] == DATA_PUBLICACAO


# ═══════════════════════════════════════════════════════════════════════════
# CA: download do PDF assinado, respeitando escopo
# ═══════════════════════════════════════════════════════════════════════════


class TestDownloadAssinado:
    def test_documento_publicado_serve_o_pdf_assinado_do_storage(self, downloads, pdf_gerado):
        """PUBLICADO: o assinado substitui o download (não regenera o
        preliminar) — bytes do storage com o nome travado _ASSINADO.pdf."""
        client = _client_para(GESTOR, _sb())

        res = client.get("/api/pops/pop-1/documento?download=1")

        assert res.status_code == 200
        assert res.content == b"%PDF-signed"
        assert "_ASSINADO.pdf" in res.headers["content-disposition"]
        assert pdf_gerado == []

        assert len(downloads) == 1
        nome_esperado = pops_pdf_service.nome_arquivo_pop(
            codigo="HSM_CTI-001",
            nome="Cateter Venoso Central",
            numero_versao="1.0",
            status="ASSINADO",
            quando=datetime(2026, 6, 12, 15, 0, 0),
        )
        assert downloads[0]["path"] == f"pops/pop-1/{nome_esperado}"

    def test_download_do_assinado_respeita_escopo(self, downloads, pdf_gerado):
        """Coordenador de outro Setor (não designado) não baixa: 403."""
        client = _client_para(INTRUSO_OUTRO_SETOR, _sb())

        res = client.get("/api/pops/pop-1/documento?download=1")

        assert res.status_code == 403
        assert downloads == []

    def test_assinado_ausente_no_storage_da_404(self, monkeypatch, pdf_gerado):
        """PUBLICADO sem o arquivo no storage (publicação sem PDF): 404
        explícito — nunca regenera o preliminar mascarando o problema."""
        monkeypatch.setattr(storage, "download_file", lambda *_a: None)
        client = _client_para(GESTOR, _sb())

        res = client.get("/api/pops/pop-1/documento?download=1")

        assert res.status_code == 404
        assert pdf_gerado == []
