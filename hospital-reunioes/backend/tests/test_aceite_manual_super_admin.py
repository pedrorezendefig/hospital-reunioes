"""Aceite manual do Super admin no modo interno (issue #278, ADR 0030).

Seam testado: POST /api/reunioes/{id}/signatarios/{participante_id}/aceite-manual.

- Acao restrita a Super admin (403 para os demais), sem nenhum efeito no 403.
- Aceite registrado com origem `super_admin`, Pendencias do signatario nascem
  na hora e o rastro fica em `audit_log` (quem forcou, quando, em nome de quem).
- Efeito idempotente: repetir nao duplica aceite, Pendencia nem audit.
- O ultimo aceite manual necessario leva a Reuniao a ASSINADA com o selo,
  pelo mesmo desfecho terminal do Aceite interno.

ClickSign SEMPRE mockado (o .env de teste carrega credenciais reais).
"""

from __future__ import annotations

import os
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app.dependencies as deps  # noqa: E402
from app.dependencies import get_current_user, get_supabase_client  # noqa: E402
from app.routers import reunioes as reunioes_router  # noqa: E402

# ─── Mock Supabase (mesmo estilo de test_aceite_interno_e2e) ─────────────────


class _Result:
    def __init__(self, data: list):
        self.data = data


class _TableQuery:
    def __init__(self, rows: list[dict]):
        self._rows = rows
        self._filters: dict = {}
        self._is_filters: dict = {}
        self._in_filters: dict = {}
        self._limit: int | None = None
        self._insert_payload: list[dict] | None = None
        self._update_payload: dict | None = None

    def select(self, *_a, **_kw):
        return self

    def eq(self, col, value):
        self._filters[col] = value
        return self

    def in_(self, col, values):
        self._in_filters[col] = list(values)
        return self

    def is_(self, col, value):
        self._is_filters[col] = None if value in ("null", None) else value
        return self

    def order(self, *_a, **_kw):
        return self

    def limit(self, n):
        self._limit = n
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
            for row in self._insert_payload:
                row.setdefault("id", f"row-{len(self._rows) + 1}")
                self._rows.append(dict(row))
            return _Result(data=[dict(r) for r in self._insert_payload])

        filtered = [
            r
            for r in self._rows
            if all(r.get(c) == v for c, v in self._filters.items())
            and all(r.get(c) in vs for c, vs in self._in_filters.items())
            and all(r.get(c) == v for c, v in self._is_filters.items())
        ]
        if getattr(self, "_delete", False):
            for row in filtered:
                self._rows.remove(row)
            return _Result(data=[dict(r) for r in filtered])
        if self._update_payload is not None:
            for row in filtered:
                row.update(self._update_payload)
            return _Result(data=[dict(r) for r in filtered])
        if self._limit is not None:
            filtered = filtered[: self._limit]
        return _Result(data=[dict(r) for r in filtered])


class _SupabaseMock:
    def __init__(self, tables: dict[str, list[dict]]):
        self.tables = tables

    def table(self, name: str):
        if name not in self.tables:
            raise AssertionError(f"Tabela inesperada: {name}")
        return _TableQuery(self.tables[name])


# ─── Dados ───────────────────────────────────────────────────────────────────

AUTH_SUPER = {"id": "auth-super", "email": "admin@hsm.com"}
AUTH_REGULAR = {"id": "auth-fac", "email": "fabio@hsm.com"}


def _participante(pid: str, nome: str, email: str, **over) -> dict:
    row = {
        "id": pid,
        "nome_completo": nome,
        "cargo": "Cargo",
        "setor": "Setor",
        "email": email,
        "ativo": True,
        "access_profile": "regular",
        "auth_user_id": None,
    }
    row.update(over)
    return row


def _quadro() -> list[dict]:
    return [
        {"acao": "Revisar protocolo", "responsavel": "Ana Lima", "responsavel_id": "P_ANA", "prazo": "2026-09-01"},
        {"acao": "Comprar insumos", "responsavel": "Bruno Costa", "responsavel_id": "P_BRUNO", "prazo": "2026-09-10"},
        {"acao": "Atualizar POP", "responsavel": "Fabio Facilitador", "responsavel_id": "P_FAC", "prazo": None},
    ]


def _sb(**reuniao_over) -> _SupabaseMock:
    reuniao = {
        "id_reuniao": "R1",
        "titulo": "Comissao de Farmacia",
        "tipo": "Comissao",
        "data": "2026-08-01",
        "hora_inicio": "10:00",
        "status_ata": "AGUARDANDO_ASSINATURA",
        "envelope_key_clicksign": "doc-key-r1",
        "envelope_id_clicksign": "env-r1",
        "facilitador_id": "P_FAC",
        "modo_interno_desde": "2026-08-13T09:00:00+00:00",
        "data_assinatura": None,
        "url_pdf_assinado": None,
        "json_ata": {"objetivo": "Alinhar compras", "quadro_atribuicoes": _quadro()},
    }
    reuniao.update(reuniao_over)
    return _SupabaseMock(
        {
            "reunioes": [reuniao],
            "participantes": [
                _participante(
                    "P_SUPER", "Sueli Admin", "admin@hsm.com", access_profile="super_admin", auth_user_id="auth-super"
                ),  # noqa: E501
                _participante("P_FAC", "Fabio Facilitador", "fabio@hsm.com", auth_user_id="auth-fac"),
                _participante("P_ANA", "Ana Lima", "ana@hsm.com"),
                _participante("P_BRUNO", "Bruno Costa", "bruno@hsm.com"),
            ],
            "reuniao_participantes": [
                {"id_reuniao": "R1", "participante_id": "P_FAC"},
                {"id_reuniao": "R1", "participante_id": "P_ANA"},
                {"id_reuniao": "R1", "participante_id": "P_BRUNO"},
            ],
            "pendencias": [],
            "reuniao_aceites": [],
            "audit_log": [],
        }
    )


def _aceite(pid: str, origem: str = "clicksign", email: str | None = None) -> dict:
    return {
        "id": f"aceite-{pid}",
        "id_reuniao": "R1",
        "participante_id": pid,
        "signer_key": f"sk-{pid.lower()}",
        "email": email,
        "origem": origem,
        "aceito_em": "2026-08-10T10:00:00-03:00",
    }


def _pendencia(id_acao: str, quadro_pos: int, responsavel_id: str) -> dict:
    return {
        "id_acao": id_acao,
        "id_reuniao": "R1",
        "status": "PENDENTE",
        "responsavel_id": responsavel_id,
        "quadro_pos": quadro_pos,
    }


# ─── App e fixtures ──────────────────────────────────────────────────────────


def _client(sb: _SupabaseMock, user: dict) -> TestClient:
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded

    from app.limiter import limiter

    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(reunioes_router.router, prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_supabase_client] = lambda: sb
    return TestClient(app, raise_server_exceptions=False)


def _post_aceite_manual(client: TestClient, participante_id: str, id_reuniao: str = "R1"):
    return client.post(f"/api/reunioes/{id_reuniao}/signatarios/{participante_id}/aceite-manual")


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    from app.limiter import limiter

    limiter._storage.reset()
    yield
    limiter._storage.reset()


@pytest.fixture(autouse=True)
def _reset_participante_cache():
    deps._participante_ctx.set(None)
    yield
    deps._participante_ctx.set(None)


@pytest.fixture(autouse=True)
def _bloquear_httpx(monkeypatch):
    import httpx

    def _explode(*_a, **_kw):
        raise AssertionError("Chamada httpx real bloqueada nos testes")

    monkeypatch.setattr(httpx, "Client", _explode)


# ─── Testes ──────────────────────────────────────────────────────────────────


class TestAceiteManualSuperAdmin:
    def test_super_admin_registra_aceite_e_pendencias_do_signatario_nascem(self):
        sb = _sb()
        client = _client(sb, AUTH_SUPER)

        resp = _post_aceite_manual(client, "P_ANA")

        assert resp.status_code == 200, resp.text
        aceites = sb.tables["reuniao_aceites"]
        assert len(aceites) == 1
        assert aceites[0]["participante_id"] == "P_ANA"
        assert aceites[0]["origem"] == "super_admin"
        assert aceites[0]["aceito_em"]

        # Nascem so as Pendencias da Ana (posicao 0 do quadro)
        pendencias = sb.tables["pendencias"]
        assert [p["quadro_pos"] for p in pendencias] == [0]
        assert pendencias[0]["responsavel_id"] == "P_ANA"
        assert resp.json()["pendencias_criadas"] == 1

    def test_403_para_quem_nao_e_super_admin_sem_nenhum_efeito(self):
        sb = _sb()
        client = _client(sb, AUTH_REGULAR)

        resp = _post_aceite_manual(client, "P_ANA")

        assert resp.status_code == 403
        assert sb.tables["reuniao_aceites"] == []
        assert sb.tables["pendencias"] == []
        assert sb.tables["audit_log"] == []

    def test_rastro_em_audit_log_quem_forcou_e_em_nome_de_quem(self):
        sb = _sb()
        client = _client(sb, AUTH_SUPER)

        _post_aceite_manual(client, "P_ANA")

        audit = sb.tables["audit_log"]
        assert len(audit) == 1
        assert audit[0]["action"] == "ACEITE_MANUAL"
        assert audit[0]["actor_email"] == "admin@hsm.com"
        assert audit[0]["target_type"] == "reuniao"
        assert audit[0]["target_id"] == "R1"
        assert audit[0]["metadata"]["participante_id"] == "P_ANA"
        assert audit[0]["metadata"]["participante_nome"] == "Ana Lima"

    def test_repetir_nao_duplica_aceite_pendencia_nem_audit(self):
        sb = _sb()
        client = _client(sb, AUTH_SUPER)

        _post_aceite_manual(client, "P_ANA")
        resp = _post_aceite_manual(client, "P_ANA")

        assert resp.status_code == 200
        body = resp.json()
        assert body["ja_registrado"] is True
        assert body["pendencias_criadas"] == 0
        assert len(sb.tables["reuniao_aceites"]) == 1
        assert len(sb.tables["pendencias"]) == 1
        assert len(sb.tables["audit_log"]) == 1

    def test_ultimo_aceite_manual_leva_a_reuniao_a_assinada_com_selo(self):
        sb = _sb()
        # Bruno e Fabio ja assinaram no ClickSign; as Pendencias deles nasceram.
        sb.tables["reuniao_aceites"].extend(
            [_aceite("P_BRUNO", email="bruno@hsm.com"), _aceite("P_FAC", email="fabio@hsm.com")]
        )
        sb.tables["pendencias"].extend([_pendencia("A001", 1, "P_BRUNO"), _pendencia("A002", 2, "P_FAC")])
        client = _client(sb, AUTH_SUPER)

        resp = _post_aceite_manual(client, "P_ANA")

        assert resp.status_code == 200
        assert resp.json()["reuniao_assinada"] is True
        reuniao = sb.tables["reunioes"][0]
        assert reuniao["status_ata"] == "ASSINADA"
        assert reuniao["data_assinatura"]
        # Selo de assinaturas mistas: 2 de 3 assinaram no ClickSign
        assert reuniao["signatarios_total"] == 3
        assert reuniao["signatarios_assinaram"] == 2

    def test_409_fora_do_modo_interno_sem_nenhum_efeito(self):
        sb = _sb(modo_interno_desde=None)
        client = _client(sb, AUTH_SUPER)

        resp = _post_aceite_manual(client, "P_ANA")

        assert resp.status_code == 409
        assert sb.tables["reuniao_aceites"] == []
        assert sb.tables["pendencias"] == []
        assert sb.tables["audit_log"] == []

    def test_404_para_signatario_fora_da_reuniao(self):
        sb = _sb()
        client = _client(sb, AUTH_SUPER)

        resp = _post_aceite_manual(client, "P_INTRUSO")

        assert resp.status_code == 404
        assert sb.tables["reuniao_aceites"] == []

    def test_404_para_reuniao_inexistente(self):
        sb = _sb()
        client = _client(sb, AUTH_SUPER)

        resp = _post_aceite_manual(client, "P_ANA", id_reuniao="R_NAO_EXISTE")

        assert resp.status_code == 404

    def test_aceite_manual_do_facilitador_libera_acoes_de_fora_do_envelope(self):
        quadro = _quadro() + [{"acao": "Sem dono definido", "responsavel": "", "responsavel_id": None, "prazo": None}]
        sb = _sb(json_ata={"objetivo": "Alinhar compras", "quadro_atribuicoes": quadro})
        client = _client(sb, AUTH_SUPER)

        resp = _post_aceite_manual(client, "P_FAC")

        assert resp.status_code == 200
        # Nascem a acao do proprio Facilitador (pos 2) e a acao sem responsavel
        # (pos 3, fora do Envelope); as de Ana e Bruno seguem aguardando aceite.
        assert sorted(p["quadro_pos"] for p in sb.tables["pendencias"]) == [2, 3]
        assert resp.json()["pendencias_criadas"] == 2
