"""Testes da criação de POP e lista por estado (/pops) — issue #82.

O nascimento de um POP (docs/pops/CONTEXT.md): formulário institucional,
Código travado HSM_[SIGLA]-[NNN] com sequência por Setor, Versão 1.0 nascendo
em A_ELABORAR, email ao Elaborador designado e lista por estado filtrada pelo
escopo do perfil (Coordenador: seu Setor; Gerente: seus Setores; Gestor de
Qualidade/Superadmin: todos). Gating explícito por endpoint (ADR 0002);
terminologia conforme docs/pops/CONTEXT.md.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.dependencies import get_current_user, get_supabase_client  # noqa: E402
from app.routers.pops import pops as pops_router  # noqa: E402
from app.routers.pops import setores as pops_setores_router  # noqa: E402
from app.services import pops_email_service  # noqa: E402

# ─── Mock Supabase (padrão do test_pops_setores, estendido p/ o ciclo do POP) ─


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


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _pessoa(
    pid: str = "P1",
    perfil_pop: str | None = None,
    access_profile: str | None = None,
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


def _setor(sid: str, nome: str, sigla: str) -> dict:
    return {"id": sid, "nome": nome, "sigla": sigla}


def _client_para(
    pessoa: dict,
    *,
    participantes_extra: list[dict] | None = None,
    setores: list[dict] | None = None,
    vinculos: list[tuple[str, str]] | None = None,
    pops: list[dict] | None = None,
    versoes: list[dict] | None = None,
) -> tuple[TestClient, _SupabaseMock]:
    app = FastAPI()
    app.include_router(pops_router.router, prefix="/api")
    app.include_router(pops_setores_router.router, prefix="/api")

    sb = _SupabaseMock(
        {
            "participantes": [pessoa, *(participantes_extra or [])],
            "pops_setores": setores or [],
            "pops_setores_participantes": [{"setor_id": sid, "participante_id": pid} for sid, pid in (vinculos or [])],
            "pops": pops or [],
            "pops_versoes": versoes or [],
            "audit_log": [],
        }
    )

    async def _fake_user() -> dict[str, Any]:
        return {"id": pessoa["auth_user_id"], "email": pessoa["email"], "metadata": {}}

    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_supabase_client] = lambda: sb
    return TestClient(app), sb


@pytest.fixture(autouse=True)
def emails_enviados(monkeypatch) -> list[dict]:
    """Captura emails no boundary de IO — o template e a montagem rodam de verdade."""
    capturados: list[dict] = []

    def _fake_enviar(destinatario: str, assunto: str, html_content: str, texto_fallback: str) -> bool:
        capturados.append(
            {"destinatario": destinatario, "assunto": assunto, "html": html_content, "texto": texto_fallback}
        )
        return True

    monkeypatch.setattr(pops_email_service, "_enviar_email", _fake_enviar)
    return capturados


def _payload_pop(**overrides) -> dict:
    base = {
        "setor_id": "s-cti",
        "nome": "Higienização das Mãos",
        "elaborador_id": "P2",
        "revisor_id": "P3",
        "validador_id": "P4",
        "criticidade": "CRITICA",
        "periodicidade_revisao": "1_ano",
    }
    base.update(overrides)
    return base


def _designados() -> list[dict]:
    return [
        _pessoa("P2", perfil_pop="coordenador"),
        _pessoa("P3", perfil_pop="gerente"),
        _pessoa("P4", perfil_pop="gestor_qualidade"),
    ]


# ─── Criar POP — formulário institucional e Código travado ──────────────────


class TestCriarPop:
    def test_coordenador_cria_pop_no_seu_setor(self):
        client, sb = _client_para(
            _pessoa("P1", perfil_pop="coordenador"),
            participantes_extra=_designados(),
            setores=[_setor("s-cti", "Centro de Terapia Intensiva", "CTI")],
            vinculos=[("s-cti", "P1")],
        )
        r = client.post("/api/pops", json=_payload_pop())
        assert r.status_code == 201
        body = r.json()
        assert body["codigo"] == "HSM_CTI-001"
        assert body["nome"] == "Higienização das Mãos"
        assert body["versao"]["numero_versao"] == "1.0"
        assert body["versao"]["estado"] == "A_ELABORAR"
        assert len(sb.tables["pops"]) == 1
        assert len(sb.tables["pops_versoes"]) == 1

    def test_coordenador_fora_do_seu_setor_recebe_403(self):
        client, sb = _client_para(
            _pessoa("P1", perfil_pop="coordenador"),
            participantes_extra=_designados(),
            setores=[
                _setor("s-cti", "Centro de Terapia Intensiva", "CTI"),
                _setor("s-far", "Farmácia", "FAR"),
            ],
            vinculos=[("s-far", "P1")],  # vínculo é com a Farmácia, não com o CTI
        )
        r = client.post("/api/pops", json=_payload_pop(setor_id="s-cti"))
        assert r.status_code == 403
        assert sb.tables["pops"] == []
        assert sb.tables["pops_versoes"] == []

    def test_gerente_cria_nos_seus_setores_e_403_fora(self):
        setores = [
            _setor("s-cti", "Centro de Terapia Intensiva", "CTI"),
            _setor("s-far", "Farmácia", "FAR"),
            _setor("s-fat", "Faturamento", "FAT"),
        ]
        # Gerente de dois Setores: cria nos dois, 403 no terceiro.
        for setor_ok in ("s-cti", "s-far"):
            client, _ = _client_para(
                _pessoa("P1", perfil_pop="gerente"),
                participantes_extra=_designados(),
                setores=list(setores),
                vinculos=[("s-cti", "P1"), ("s-far", "P1")],
            )
            r = client.post("/api/pops", json=_payload_pop(setor_id=setor_ok))
            assert r.status_code == 201, f"Gerente deveria criar no Setor {setor_ok}"

        client, sb = _client_para(
            _pessoa("P1", perfil_pop="gerente"),
            participantes_extra=_designados(),
            setores=list(setores),
            vinculos=[("s-cti", "P1"), ("s-far", "P1")],
        )
        r = client.post("/api/pops", json=_payload_pop(setor_id="s-fat"))
        assert r.status_code == 403
        assert sb.tables["pops"] == []

    def test_gestor_qualidade_e_superadmin_criam_em_qualquer_setor(self):
        # Escopo institucional: criam sem vínculo algum com o Setor.
        for perfil in ("gestor_qualidade", "superadmin"):
            client, sb = _client_para(
                _pessoa("P1", perfil_pop=perfil),
                participantes_extra=_designados(),
                setores=[_setor("s-cti", "Centro de Terapia Intensiva", "CTI")],
            )
            r = client.post("/api/pops", json=_payload_pop())
            assert r.status_code == 201, f"perfil_pop={perfil} deveria criar em qualquer Setor"
            assert len(sb.tables["pops"]) == 1

    def test_sem_perfil_pop_recebe_403(self):
        # Facilitador das Reuniões (mesmo Super admin) não entra no contexto POPs.
        pessoa = _pessoa("P1", perfil_pop=None, access_profile="super_admin")
        client, sb = _client_para(
            pessoa,
            participantes_extra=_designados(),
            setores=[_setor("s-cti", "Centro de Terapia Intensiva", "CTI")],
        )
        r = client.post("/api/pops", json=_payload_pop())
        assert r.status_code == 403
        assert sb.tables["pops"] == []


# ─── Código travado — sequência por Setor ────────────────────────────────────


class TestCodigoSequencialPorSetor:
    def test_sequencia_avanca_dentro_do_setor_e_e_independente_entre_setores(self):
        setores = [
            _setor("s-cti", "Centro de Terapia Intensiva", "CTI"),
            _setor("s-far", "Farmácia", "FAR"),
        ]
        existentes = [
            {"id": "pop-1", "setor_id": "s-cti", "numero": 1, "codigo": "HSM_CTI-001"},
            {"id": "pop-2", "setor_id": "s-cti", "numero": 2, "codigo": "HSM_CTI-002"},
        ]
        client, _ = _client_para(
            _pessoa("P1", perfil_pop="gestor_qualidade"),
            participantes_extra=_designados(),
            setores=setores,
            pops=list(existentes),
        )
        r = client.post("/api/pops", json=_payload_pop(setor_id="s-cti"))
        assert r.status_code == 201
        assert r.json()["codigo"] == "HSM_CTI-003"

        # A Farmácia tem sequência própria: nasce no 001 mesmo com o CTI no 003.
        r = client.post("/api/pops", json=_payload_pop(setor_id="s-far"))
        assert r.status_code == 201
        assert r.json()["codigo"] == "HSM_FAR-001"

    def test_codigo_e_imutavel_nenhum_endpoint_o_altera(self):
        # Guard-rail do critério "Código travado": não existe rota de edição
        # de POP nesta fatia — se alguém criar um PATCH/PUT genérico, este
        # teste quebra e força a exclusão explícita do campo codigo.
        client, sb = _client_para(
            _pessoa("P1", perfil_pop="superadmin"),
            setores=[_setor("s-cti", "Centro de Terapia Intensiva", "CTI")],
            pops=[{"id": "pop-1", "setor_id": "s-cti", "numero": 1, "codigo": "HSM_CTI-001"}],
        )
        for metodo in ("patch", "put"):
            r = getattr(client, metodo)("/api/pops/pop-1", json={"codigo": "HSM_CTI-999"})
            assert r.status_code in (404, 405), f"{metodo.upper()} /pops/{{id}} não deveria existir"
        assert sb.tables["pops"][0]["codigo"] == "HSM_CTI-001"


# ─── Versão 1.0, auditoria e email ───────────────────────────────────────────


class TestVersaoAuditoriaEmail:
    def test_criacao_registra_auditoria_com_autor_e_codigo(self):
        client, sb = _client_para(
            _pessoa("P1", perfil_pop="coordenador"),
            participantes_extra=_designados(),
            setores=[_setor("s-cti", "Centro de Terapia Intensiva", "CTI")],
            vinculos=[("s-cti", "P1")],
        )
        r = client.post("/api/pops", json=_payload_pop())
        assert r.status_code == 201
        registros = sb.tables["audit_log"]
        assert len(registros) == 1
        log = registros[0]
        assert log["action"] == "POPS_CRIAR_POP"
        assert log["target_type"] == "pop"
        assert log["target_id"] == r.json()["id"]
        assert log["actor_id"] == "P1"
        assert log["metadata"]["codigo"] == "HSM_CTI-001"

    def test_email_ao_elaborador_designado_com_link(self, emails_enviados):
        client, _ = _client_para(
            _pessoa("P1", perfil_pop="coordenador"),
            participantes_extra=_designados(),
            setores=[_setor("s-cti", "Centro de Terapia Intensiva", "CTI")],
            vinculos=[("s-cti", "P1")],
        )
        r = client.post("/api/pops", json=_payload_pop())
        assert r.status_code == 201
        assert len(emails_enviados) == 1
        email = emails_enviados[0]
        assert email["destinatario"] == "p2@hsm.com"  # email do Elaborador (P2)
        assert "HSM_CTI-001" in email["assunto"] or "HSM_CTI-001" in email["html"]
        assert "/pops" in email["html"]  # link de acesso à área POPs

    def test_elaborador_sem_email_nao_quebra_a_criacao(self, emails_enviados):
        elaborador_sem_email = _pessoa("P2", perfil_pop="coordenador")
        elaborador_sem_email["email"] = None
        client, sb = _client_para(
            _pessoa("P1", perfil_pop="coordenador"),
            participantes_extra=[
                elaborador_sem_email,
                _pessoa("P3", perfil_pop="gerente"),
                _pessoa("P4", perfil_pop="gestor_qualidade"),
            ],
            setores=[_setor("s-cti", "Centro de Terapia Intensiva", "CTI")],
            vinculos=[("s-cti", "P1")],
        )
        r = client.post("/api/pops", json=_payload_pop())
        assert r.status_code == 201  # email é best-effort
        assert len(sb.tables["pops"]) == 1
        assert emails_enviados == []


# ─── Designados (Elaborador, Revisor, Validador) ─────────────────────────────


class TestDesignados:
    def test_designado_sem_perfil_pop_recebe_400(self):
        # Sem perfil POP a pessoa não loga no contexto: o fluxo de elaboração/
        # revisão/validação (fatias #83+) nasceria morto.
        sem_perfil = _pessoa("P2", perfil_pop=None, access_profile="regular")
        client, sb = _client_para(
            _pessoa("P1", perfil_pop="gestor_qualidade"),
            participantes_extra=[
                sem_perfil,
                _pessoa("P3", perfil_pop="gerente"),
                _pessoa("P4", perfil_pop="coordenador"),
            ],
            setores=[_setor("s-cti", "Centro de Terapia Intensiva", "CTI")],
        )
        r = client.post("/api/pops", json=_payload_pop())
        assert r.status_code == 400
        assert "P2" in r.json()["detail"]
        assert sb.tables["pops"] == []

    def test_designado_inexistente_recebe_400(self):
        client, sb = _client_para(
            _pessoa("P1", perfil_pop="gestor_qualidade"),
            participantes_extra=_designados(),
            setores=[_setor("s-cti", "Centro de Terapia Intensiva", "CTI")],
        )
        r = client.post("/api/pops", json=_payload_pop(revisor_id="P9"))
        assert r.status_code == 400
        assert sb.tables["pops"] == []

    def test_mesma_pessoa_pode_acumular_papeis(self):
        # O DRF não veda acúmulo (Elaborador = Revisor etc.) — não inventamos trava.
        client, _ = _client_para(
            _pessoa("P1", perfil_pop="gestor_qualidade"),
            participantes_extra=[_pessoa("P2", perfil_pop="coordenador")],
            setores=[_setor("s-cti", "Centro de Terapia Intensiva", "CTI")],
        )
        r = client.post("/api/pops", json=_payload_pop(elaborador_id="P2", revisor_id="P2", validador_id="P2"))
        assert r.status_code == 201


# ─── Defaults do DRF (§3.2) ──────────────────────────────────────────────────


class TestDefaultsDoFormulario:
    def test_prazos_omitidos_assumem_defaults_do_drf(self):
        # DRF §3.2: elaboração 15 dias úteis, revisão 30 dias.
        client, sb = _client_para(
            _pessoa("P1", perfil_pop="gestor_qualidade"),
            participantes_extra=_designados(),
            setores=[_setor("s-cti", "Centro de Terapia Intensiva", "CTI")],
        )
        r = client.post("/api/pops", json=_payload_pop())
        assert r.status_code == 201
        body = r.json()
        assert body["prazo_elaboracao_dias"] == 15
        assert body["prazo_revisao_dias"] == 30
        assert sb.tables["pops"][0]["prazo_elaboracao_dias"] == 15
        assert sb.tables["pops"][0]["prazo_revisao_dias"] == 30


# ─── Lista por estado, filtrada pelo escopo do perfil ────────────────────────


def _cenario_lista() -> dict:
    """Dois Setores com POPs em estados distintos, para exercitar escopo+filtro."""
    return {
        "setores": [
            _setor("s-cti", "Centro de Terapia Intensiva", "CTI"),
            _setor("s-far", "Farmácia", "FAR"),
        ],
        "pops": [
            {
                "id": "pop-1",
                "setor_id": "s-cti",
                "numero": 1,
                "codigo": "HSM_CTI-001",
                "nome": "Higienização das Mãos",
                "criticidade": "CRITICA",
                "base_normativa": None,
                "periodicidade_revisao": "1_ano",
                "prazo_elaboracao_dias": 15,
                "prazo_revisao_dias": 30,
                "elaborador_id": "P2",
                "revisor_id": "P3",
                "validador_id": "P4",
                "criado_por": "P1",
            },
            {
                "id": "pop-2",
                "setor_id": "s-far",
                "numero": 1,
                "codigo": "HSM_FAR-001",
                "nome": "Diluição de Quimioterápicos",
                "criticidade": "ALTA",
                "base_normativa": None,
                "periodicidade_revisao": "6_meses",
                "prazo_elaboracao_dias": 15,
                "prazo_revisao_dias": 30,
                "elaborador_id": "P2",
                "revisor_id": "P3",
                "validador_id": "P4",
                "criado_por": "P1",
            },
        ],
        "versoes": [
            {"id": "v-1", "pop_id": "pop-1", "numero_versao": "1.0", "estado": "A_ELABORAR"},
            {"id": "v-2", "pop_id": "pop-2", "numero_versao": "1.0", "estado": "EM_REVISAO"},
        ],
    }


class TestListaPorEstado:
    def test_coordenador_ve_apenas_pops_do_seu_setor(self):
        cenario = _cenario_lista()
        client, _ = _client_para(
            _pessoa("P1", perfil_pop="coordenador"),
            participantes_extra=_designados(),
            setores=cenario["setores"],
            vinculos=[("s-cti", "P1")],
            pops=cenario["pops"],
            versoes=cenario["versoes"],
        )
        r = client.get("/api/pops")
        assert r.status_code == 200
        codigos = [p["codigo"] for p in r.json()]
        assert codigos == ["HSM_CTI-001"]

    def test_gerente_ve_os_setores_da_sua_gestao(self):
        cenario = _cenario_lista()
        client, _ = _client_para(
            _pessoa("P1", perfil_pop="gerente"),
            participantes_extra=_designados(),
            setores=cenario["setores"],
            vinculos=[("s-cti", "P1"), ("s-far", "P1")],
            pops=cenario["pops"],
            versoes=cenario["versoes"],
        )
        r = client.get("/api/pops")
        assert r.status_code == 200
        assert {p["codigo"] for p in r.json()} == {"HSM_CTI-001", "HSM_FAR-001"}

    def test_gestor_qualidade_e_superadmin_veem_todos(self):
        cenario = _cenario_lista()
        for perfil in ("gestor_qualidade", "superadmin"):
            client, _ = _client_para(
                _pessoa("P1", perfil_pop=perfil),
                participantes_extra=_designados(),
                setores=cenario["setores"],
                pops=cenario["pops"],
                versoes=cenario["versoes"],
            )
            r = client.get("/api/pops")
            assert r.status_code == 200, f"perfil_pop={perfil}"
            assert {p["codigo"] for p in r.json()} == {"HSM_CTI-001", "HSM_FAR-001"}

    def test_filtro_por_estado_da_versao(self):
        cenario = _cenario_lista()
        client, _ = _client_para(
            _pessoa("P1", perfil_pop="gestor_qualidade"),
            participantes_extra=_designados(),
            setores=cenario["setores"],
            pops=cenario["pops"],
            versoes=cenario["versoes"],
        )
        r = client.get("/api/pops", params={"estado": "EM_REVISAO"})
        assert r.status_code == 200
        assert [p["codigo"] for p in r.json()] == ["HSM_FAR-001"]

    def test_lista_traz_versao_e_dados_de_exibicao(self):
        cenario = _cenario_lista()
        client, _ = _client_para(
            _pessoa("P1", perfil_pop="gestor_qualidade"),
            participantes_extra=_designados(),
            setores=cenario["setores"],
            pops=cenario["pops"],
            versoes=cenario["versoes"],
        )
        r = client.get("/api/pops")
        assert r.status_code == 200
        pop = next(p for p in r.json() if p["codigo"] == "HSM_CTI-001")
        assert pop["setor_sigla"] == "CTI"
        assert pop["setor_nome"] == "Centro de Terapia Intensiva"
        assert pop["versao"]["numero_versao"] == "1.0"
        assert pop["versao"]["estado"] == "A_ELABORAR"

    def test_sem_perfil_pop_recebe_403_na_lista(self):
        client, _ = _client_para(_pessoa("P1", perfil_pop=None, access_profile="regular"))
        r = client.get("/api/pops")
        assert r.status_code == 403


# ─── Apoio ao formulário: designáveis e Setores do escopo ────────────────────


class TestApoioAoFormulario:
    def test_designaveis_lista_apenas_usuarios_ativos_com_perfil_pop(self):
        inativo = _pessoa("P5", perfil_pop="coordenador")
        inativo["ativo"] = False
        client, _ = _client_para(
            _pessoa("P1", perfil_pop="coordenador"),
            participantes_extra=[*_designados(), _pessoa("P9", perfil_pop=None), inativo],
        )
        r = client.get("/api/pops/designaveis")
        assert r.status_code == 200
        ids = {p["id"] for p in r.json()}
        assert ids == {"P1", "P2", "P3", "P4"}  # quem tem perfil POP e está ativo

    def test_setores_meus_respeita_o_escopo(self):
        setores = [
            _setor("s-cti", "Centro de Terapia Intensiva", "CTI"),
            _setor("s-far", "Farmácia", "FAR"),
        ]
        client, _ = _client_para(
            _pessoa("P1", perfil_pop="coordenador"),
            setores=list(setores),
            vinculos=[("s-far", "P1")],
        )
        r = client.get("/api/pops/setores/meus")
        assert r.status_code == 200
        assert [s["sigla"] for s in r.json()] == ["FAR"]

        client, _ = _client_para(_pessoa("P1", perfil_pop="superadmin"), setores=list(setores))
        r = client.get("/api/pops/setores/meus")
        assert r.status_code == 200
        assert {s["sigla"] for s in r.json()} == {"CTI", "FAR"}
