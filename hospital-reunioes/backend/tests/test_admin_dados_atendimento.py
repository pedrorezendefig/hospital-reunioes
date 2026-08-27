"""Testes do módulo Dados do Atendimento na área admin (issue #291, ADR 0031).

Cobre (critérios de aceite):
- Secretária edita um preço e o endpoint da API da Ana devolve o valor novo
  na chamada seguinte (leitura direta, sem cache).
- Facilitador vê as tabelas mas tem a edição recusada; anônimo é recusado
  em tudo.
- Criar, editar e desativar linha funcionam nas três tabelas; linha
  desativada some da resposta da API da Ana.
- Cada tabela expõe a data da última atualização.
"""

from __future__ import annotations

import os
import sys
import uuid
from dataclasses import dataclass, field
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.dependencies import _participante_ctx, get_current_user, get_supabase_client  # noqa: E402
from app.limiter import limiter  # noqa: E402

CHAVE_ANA = "chave-teste-ana-para-pytest"


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


@pytest.fixture(autouse=True)
def _reset_participante_ctx():
    # Defesa contra poluição do cache request-scoped entre módulos de teste
    # (mesmo padrão de test_participantes_list.py): sem isso, os asserts de
    # papel (403) ficam dependentes da ordem de coleta do pytest.
    _participante_ctx.set(None)
    yield
    _participante_ctx.set(None)


# ─── Mock Supabase ────────────────────────────────────────────────────────────


@dataclass
class _Result:
    data: list
    count: int | None = None


class _Query:
    """Mock minimalista de PostgREST sobre uma lista de rows.

    Suporta select(...).eq(...).order(...).execute(), insert(payload).execute()
    e update(payload).eq(...).execute() — o que os routers admin e ana usam.
    """

    def __init__(self, rows_ref: list):
        self._rows = rows_ref
        self._op = "select"
        self._payload: Any = None
        self._filters: list[tuple[str, Any]] = []
        self._orders: list[str] = []

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

    def eq(self, col, value):
        self._filters.append((col, value))
        return self

    def order(self, col, *_args, **_kwargs):
        self._orders.append(col)
        return self

    def _matched(self) -> list[dict]:
        return [r for r in self._rows if all(r.get(c) == v for c, v in self._filters)]

    def execute(self):
        if self._op == "insert":
            row = {"id": str(uuid.uuid4()), **self._payload}
            self._rows.append(row)
            return _Result(data=[dict(row)])
        matched = self._matched()
        if self._op == "update":
            for row in matched:
                row.update(self._payload)
            return _Result(data=[dict(r) for r in matched])
        for col in reversed(self._orders):
            matched = sorted(matched, key=lambda r: (r.get(col) is None, r.get(col)))
        return _Result(data=[dict(r) for r in matched])


class _AuditInsert:
    def __init__(self, sink: list):
        self._sink = sink
        self._pending = None

    def insert(self, row):
        self._pending = row
        return self

    def execute(self):
        if self._pending is not None:
            self._sink.append(self._pending)
            self._pending = None
        return _Result(data=[])


@dataclass
class _SupabaseMock:
    tabelas: dict[str, list] = field(default_factory=dict)
    participantes: list = field(default_factory=list)
    audit_rows: list = field(default_factory=list)

    def table(self, name: str):
        if name == "participantes":
            return _Query(self.participantes)
        if name == "audit_log":
            return _AuditInsert(self.audit_rows)
        if name in self.tabelas:
            return _Query(self.tabelas[name])
        raise AssertionError(f"Tabela inesperada: {name}")


# ─── Participantes de teste ──────────────────────────────────────────────────


def _participante(pid: str, auth_id: str, access_profile: str | None, role: str) -> dict:
    return {
        "id": pid,
        "auth_user_id": auth_id,
        "email": f"{pid}@ex.com",
        "nome_completo": f"Pessoa {pid}",
        "cargo": "Cargo X",
        "setor": "Setor X",
        "area": None,
        "role": role,
        "ativo": True,
        "is_externo": False,
        "is_super_admin": access_profile == "super_admin",
        "access_profile": access_profile,
        "perfil_pop": None,
        "data_cadastro": "2026-01-01",
    }


SUPER_ADMIN = _participante("p-admin", "auth-admin", "super_admin", "diretor")
SECRETARIA = _participante("p-sec", "auth-sec", "secretaria", "secretaria")
FACILITADOR = _participante("p-fac", "auth-fac", "regular", "facilitador")


def _consulta_row(especialidade: str = "Cardiologia", valor: float = 380.0) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "especialidade": especialidade,
        "valor_rs": valor,
        "descricao_servico": "Consulta com cardiologista adulto.",
        "diferencial_1": "",
        "diferencial_2": "",
        "diferencial_3": "",
        "alta_demanda": False,
        "observacoes_ana": "",
        "ativo": True,
        "ultima_atualizacao": "2026-03-10",
    }


# ─── Setup app + overrides ────────────────────────────────────────────────────


def _make_app(
    tabelas: dict[str, list] | None = None,
    logado_como: dict | None = FACILITADOR,
) -> tuple[_SupabaseMock, TestClient]:
    """App com os routers admin (dados do atendimento) e ana sobre o mesmo mock.

    logado_como=None monta o app sem override de get_current_user: requisição
    sem Bearer token cai na dependency real e recebe 401.
    """
    from app.routers import ana as ana_router
    from app.routers.admin import dados_atendimento as dados_router

    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(dados_router.router, prefix="/api")
    app.include_router(ana_router.router, prefix="/api")

    sb = _SupabaseMock(
        tabelas=tabelas
        if tabelas is not None
        else {
            "consultas_particulares": [],
            "exames": [],
            "cirurgias_estimativas": [],
        },
        participantes=[dict(SUPER_ADMIN), dict(SECRETARIA), dict(FACILITADOR)],
    )

    app.dependency_overrides[get_supabase_client] = lambda: sb
    if logado_como is not None:
        auth_id = logado_como["auth_user_id"]
        email = logado_como["email"]

        async def _fake_user() -> dict[str, Any]:
            return {"id": auth_id, "email": email, "metadata": {}}

        app.dependency_overrides[get_current_user] = _fake_user

    return sb, TestClient(app)


# ─── Testes ───────────────────────────────────────────────────────────────────


class TestLeitura:
    def test_facilitador_ve_consultas_particulares(self):
        _, client = _make_app(
            tabelas={
                "consultas_particulares": [_consulta_row()],
                "exames": [],
                "cirurgias_estimativas": [],
            },
            logado_como=FACILITADOR,
        )
        res = client.get(
            "/api/admin/dados-atendimento/consultas-particulares",
            headers={"Authorization": "Bearer token-fake"},
        )
        assert res.status_code == 200
        body = res.json()
        assert len(body["data"]) == 1
        assert body["data"][0]["especialidade"] == "Cardiologia"
        assert body["data"][0]["valor_rs"] == 380.0


class TestRecusas:
    def test_facilitador_tem_edicao_recusada(self):
        row = _consulta_row()
        sb, client = _make_app(
            tabelas={
                "consultas_particulares": [row],
                "exames": [],
                "cirurgias_estimativas": [],
            },
            logado_como=FACILITADOR,
        )
        headers = {"Authorization": "Bearer token-fake"}
        res = client.patch(
            f"/api/admin/dados-atendimento/consultas-particulares/{row['id']}",
            json={"valor_rs": 999.0},
            headers=headers,
        )
        assert res.status_code == 403
        res = client.post(
            "/api/admin/dados-atendimento/consultas-particulares",
            json={"especialidade": "Urologia", "valor_rs": 350.0, "descricao_servico": "Consulta."},
            headers=headers,
        )
        assert res.status_code == 403
        # Nada mudou no banco
        assert sb.tabelas["consultas_particulares"][0]["valor_rs"] == 380.0
        assert len(sb.tabelas["consultas_particulares"]) == 1

    def test_anonimo_e_recusado_em_tudo(self):
        row = _consulta_row()
        _, client = _make_app(
            tabelas={
                "consultas_particulares": [row],
                "exames": [],
                "cirurgias_estimativas": [],
            },
            logado_como=None,
        )
        assert client.get("/api/admin/dados-atendimento/consultas-particulares").status_code == 401
        assert (
            client.post(
                "/api/admin/dados-atendimento/consultas-particulares",
                json={"especialidade": "Urologia", "valor_rs": 350.0, "descricao_servico": "Consulta."},
            ).status_code
            == 401
        )
        assert (
            client.patch(
                f"/api/admin/dados-atendimento/consultas-particulares/{row['id']}",
                json={"valor_rs": 999.0},
            ).status_code
            == 401
        )


class TestReflexoImediatoNaAna:
    def test_secretaria_edita_preco_e_ana_devolve_valor_novo(self, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "ana_api_key", CHAVE_ANA)
        row = _consulta_row(valor=380.0)
        _, client = _make_app(
            tabelas={
                "consultas_particulares": [row],
                "exames": [],
                "cirurgias_estimativas": [],
            },
            logado_como=SECRETARIA,
        )
        res = client.patch(
            f"/api/admin/dados-atendimento/consultas-particulares/{row['id']}",
            json={"valor_rs": 420.0},
            headers={"Authorization": "Bearer token-fake"},
        )
        assert res.status_code == 200
        assert res.json()["valor_rs"] == 420.0

        res_ana = client.get(
            "/api/ana/consultas-particulares",
            headers={"X-API-Key": CHAVE_ANA},
        )
        assert res_ana.status_code == 200
        consultas = res_ana.json()["consultas_particulares"]
        assert len(consultas) == 1
        assert consultas[0]["valor_rs"] == 420.0


# (slug, chave da resposta da Ana, payload mínimo de criação, edição, valor esperado pós-edição)
CASOS_TRES_TABELAS = [
    (
        "consultas-particulares",
        "consultas_particulares",
        {"especialidade": "Urologia", "valor_rs": 350.0, "descricao_servico": "Consulta urológica."},
        {"valor_rs": 375.0},
        ("valor_rs", 375.0),
    ),
    (
        "exames",
        "exames",
        {"nome_exame": "Hemograma", "tipo_exame": "Laboratorial", "valor_particular_rs": 45.0},
        {"valor_particular_rs": 50.0},
        ("valor_particular_rs", 50.0),
    ),
    (
        "cirurgias-estimativas",
        "cirurgias_estimativas",
        {
            "procedimento": "Apendicectomia",
            "descricao_procedimento": "Retirada do apêndice.",
            "honorarios_equipe_rs": 5500.0,
            "valor_internacao_rs": 2800.0,
            "estimativa_total_rs": 8300.0,
            "caveat_obrigatorio_ana": "Estimativa geral; valor final após avaliação médica.",
        },
        {"estimativa_total_rs": 8500.0},
        ("estimativa_total_rs", 8500.0),
    ),
]


class TestCrudTresTabelas:
    @pytest.mark.parametrize("slug, chave_ana, payload, edicao, esperado", CASOS_TRES_TABELAS)
    def test_criar_editar_desativar_e_sumico_na_ana(self, monkeypatch, slug, chave_ana, payload, edicao, esperado):
        from app.config import settings

        monkeypatch.setattr(settings, "ana_api_key", CHAVE_ANA)
        sb, client = _make_app(logado_como=SECRETARIA)
        headers = {"Authorization": "Bearer token-fake"}
        headers_ana = {"X-API-Key": CHAVE_ANA}
        base = f"/api/admin/dados-atendimento/{slug}"

        # Criar: linha nasce ativa e aparece na API da Ana
        res = client.post(base, json=payload, headers=headers)
        assert res.status_code == 201, res.text
        criado = res.json()
        assert criado["ativo"] is True
        assert client.get(f"/api/ana/{slug}", headers=headers_ana).json()[chave_ana][0]["id"] == criado["id"]

        # Editar: campo alterado persiste
        res = client.patch(f"{base}/{criado['id']}", json=edicao, headers=headers)
        assert res.status_code == 200, res.text
        campo, valor = esperado
        assert res.json()[campo] == valor

        # Desativar: some da resposta da Ana, mas segue na listagem admin
        res = client.patch(f"{base}/{criado['id']}", json={"ativo": False}, headers=headers)
        assert res.status_code == 200, res.text
        assert res.json()["ativo"] is False
        assert client.get(f"/api/ana/{slug}", headers=headers_ana).json()[chave_ana] == []
        admin_rows = client.get(base, headers=headers).json()["data"]
        assert len(admin_rows) == 1
        assert admin_rows[0]["ativo"] is False


class TestUltimaAtualizacao:
    def test_edicao_carimba_data_da_ultima_atualizacao(self):
        # Oráculo na data local do hospital (America/Sao_Paulo): o backend
        # roda em UTC e um date.today() puro viraria amanhã depois das 21h BRT.
        from datetime import datetime
        from zoneinfo import ZoneInfo

        row = _consulta_row()  # ultima_atualizacao antiga: 2026-03-10
        _, client = _make_app(
            tabelas={
                "consultas_particulares": [row],
                "exames": [],
                "cirurgias_estimativas": [],
            },
            logado_como=SECRETARIA,
        )
        headers = {"Authorization": "Bearer token-fake"}
        base = "/api/admin/dados-atendimento/consultas-particulares"

        antes = client.get(base, headers=headers).json()
        assert antes["ultima_atualizacao"] == "2026-03-10"

        res = client.patch(f"{base}/{row['id']}", json={"valor_rs": 400.0}, headers=headers)
        assert res.status_code == 200

        depois = client.get(base, headers=headers).json()
        assert depois["ultima_atualizacao"] == datetime.now(ZoneInfo("America/Sao_Paulo")).date().isoformat()

    def test_super_admin_tambem_edita(self):
        row = _consulta_row()
        _, client = _make_app(
            tabelas={
                "consultas_particulares": [row],
                "exames": [],
                "cirurgias_estimativas": [],
            },
            logado_como=SUPER_ADMIN,
        )
        res = client.patch(
            f"/api/admin/dados-atendimento/consultas-particulares/{row['id']}",
            json={"valor_rs": 410.0},
            headers={"Authorization": "Bearer token-fake"},
        )
        assert res.status_code == 200
        assert res.json()["valor_rs"] == 410.0


class TestValidacao:
    def test_campo_obrigatorio_vazio_e_recusado(self):
        _, client = _make_app(logado_como=SECRETARIA)
        res = client.post(
            "/api/admin/dados-atendimento/consultas-particulares",
            json={"especialidade": "   ", "valor_rs": 350.0, "descricao_servico": "Consulta."},
            headers={"Authorization": "Bearer token-fake"},
        )
        assert res.status_code == 422

    def test_campo_obrigatorio_so_com_travessao_e_recusado(self):
        # Travessão sanitizado vira "," (truthy): o oráculo de vazio precisa
        # ser \w, o mesmo do ana.py, senão a especialidade "," passa.
        _, client = _make_app(logado_como=SECRETARIA)
        res = client.post(
            "/api/admin/dados-atendimento/consultas-particulares",
            json={"especialidade": "—", "valor_rs": 350.0, "descricao_servico": "Consulta."},
            headers={"Authorization": "Bearer token-fake"},
        )
        assert res.status_code == 422

    def test_valor_negativo_e_recusado(self):
        _, client = _make_app(logado_como=SECRETARIA)
        res = client.post(
            "/api/admin/dados-atendimento/consultas-particulares",
            json={"especialidade": "Urologia", "valor_rs": -350.0, "descricao_servico": "Consulta."},
            headers={"Authorization": "Bearer token-fake"},
        )
        assert res.status_code == 422

    def test_travessao_e_sanitizado_na_escrita(self):
        sb, client = _make_app(logado_como=SECRETARIA)
        res = client.post(
            "/api/admin/dados-atendimento/consultas-particulares",
            json={
                "especialidade": "Urologia",
                "valor_rs": 350.0,
                "descricao_servico": "Consulta urológica — avaliação completa.",
            },
            headers={"Authorization": "Bearer token-fake"},
        )
        assert res.status_code == 201
        assert "—" not in res.json()["descricao_servico"]


class TestConveniosPodados:
    """ADR 0038: a cobertura de convênio por especialidade passa a ter uma fonte
    só (a agenda online da Global Health). As rotas da tabela local não existem
    mais, nem para o admin nem para a Ana."""

    def test_rotas_admin_de_convenio_devolvem_404(self):
        _, client = _make_app(logado_como=SECRETARIA)
        headers = {"Authorization": "Bearer token-fake"}
        base = "/api/admin/dados-atendimento/convenios-especialidade"

        assert client.get(base, headers=headers).status_code == 404
        assert (
            client.post(
                base,
                json={"convenio": "Unimed", "especialidade": "Cardiologia", "cobre": True},
                headers=headers,
            ).status_code
            == 404
        )
        assert (
            client.patch(
                f"{base}/{uuid.uuid4()}",
                json={"cobre": False},
                headers=headers,
            ).status_code
            == 404
        )

    def test_endpoint_da_ana_de_convenio_devolve_404_com_e_sem_chave(self, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "ana_api_key", CHAVE_ANA)
        _, client = _make_app(logado_como=SECRETARIA)

        assert client.get("/api/ana/convenios-especialidade").status_code == 404
        assert client.get("/api/ana/convenios-especialidade", headers={"X-API-Key": CHAVE_ANA}).status_code == 404

    def test_as_tres_tabelas_restantes_seguem_de_pe(self, monkeypatch):
        """A poda é cirúrgica: o que fica responde igual, nas duas camadas."""
        from app.config import settings

        monkeypatch.setattr(settings, "ana_api_key", CHAVE_ANA)
        _, client = _make_app(logado_como=SECRETARIA)
        headers = {"Authorization": "Bearer token-fake"}

        for slug in ("consultas-particulares", "exames", "cirurgias-estimativas"):
            assert client.get(f"/api/admin/dados-atendimento/{slug}", headers=headers).status_code == 200
            assert client.get(f"/api/ana/{slug}", headers={"X-API-Key": CHAVE_ANA}).status_code == 200


class TestMigrationDeDrop:
    """Issue #387 (ADR 0038): o último degrau da poda derruba a tabela no banco.
    A migration vem sozinha no arquivo justamente para poder ser revertida
    sozinha, então o teste olha os comandos, não a prosa que os explica."""

    @pytest.fixture
    def ddl(self) -> str:
        caminho = os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "supabase",
            "migrations",
            "081_drop_convenios_especialidade.sql",
        )
        with open(caminho, encoding="utf-8") as f:
            return f.read().lower()

    @pytest.fixture
    def comandos(self, ddl) -> str:
        return "\n".join(linha for linha in ddl.splitlines() if linha.strip() and not linha.strip().startswith("--"))

    def test_derruba_a_tabela_de_convenios(self, comandos):
        assert "drop table if exists convenios_especialidade" in comandos

    def test_a_migration_traz_somente_o_drop(self, comandos):
        assert comandos.count(";") == 1
        for proibido in ("create table", "alter table", "insert into", "update ", "delete from"):
            assert proibido not in comandos

    def test_nao_toca_nas_tres_tabelas_que_ficam(self, comandos):
        for tabela in ("consultas_particulares", "exames", "cirurgias_estimativas"):
            assert tabela not in comandos

    def test_nenhum_codigo_vivo_do_backend_le_a_tabela(self):
        """Um leitor órfão sobreviveria à poda das rotas e quebraria só depois
        do drop, em produção. A varredura fecha essa porta antes."""
        raiz = os.path.join(os.path.dirname(__file__), "..", "app")
        orfaos = []
        for pasta, _, arquivos in os.walk(raiz):
            for arquivo in arquivos:
                if not arquivo.endswith(".py"):
                    continue
                caminho = os.path.join(pasta, arquivo)
                with open(caminho, encoding="utf-8") as f:
                    if "convenios_especialidade" in f.read():
                        orfaos.append(caminho)
        assert orfaos == []
