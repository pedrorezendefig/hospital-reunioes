"""Testes da Revisão e Validação de POP — aprovar/devolver com retorno direto (issue #85).

As etapas formais do fluxo (docs/pops/CONTEXT.md, PRD #76): Revisor e
Validador leem a Versão completa e aprovam ou lançam Devolução com
comentários (nome + timestamp). Aprovação do Revisor → EM_VALIDACAO + email
ao Validador; Devolução (de qualquer um) → EM_ELABORACAO + email ao
Elaborador; aprovação do Validador → EM_ASSINATURA (ClickSign chega na fatia
de publicação). O reenvio volta DIRETO a quem devolveu — a Devolução grava a
etapa de retorno; uma Devolução do Validador não repassa pelo Revisor.

Guardas papel × estado no módulo de domínio (403/400); auditoria em toda
transição. LLM sempre mockado; emails capturados no boundary de IO
(padrão test_pops_elaboracao); Supabase mock no padrão de test_pops_criar.
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
from app.routers.pops import elaboracao as elaboracao_router  # noqa: E402
from app.routers.pops import revisao as revisao_router  # noqa: E402
from app.services import pops_email_service  # noqa: E402

# ─── Mock Supabase (padrão do test_pops_criar, com order/limit reais) ─────────


@dataclass
class _Result:
    data: list


class _TableQuery:
    def __init__(self, rows: list[dict], table: str):
        self._rows = rows
        self._table = table
        self._filters: dict = {}
        self._in_filters: dict = {}
        self._order: tuple[str, bool] | None = None
        self._limit: int | None = None
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

    def order(self, col, *, desc: bool = False, **_kwargs):
        self._order = (col, desc)
        return self

    def limit(self, n: int, *_args, **_kwargs):
        self._limit = n
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

        if self._order is not None:
            col, desc = self._order
            filtered = sorted(filtered, key=lambda r: (r.get(col) is None, r.get(col) or ""), reverse=desc)
        if self._limit is not None:
            filtered = filtered[: self._limit]

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


def _pop(**over) -> dict:
    base = {
        "id": "pop-1",
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


def _versao(**over) -> dict:
    base = {
        "id": "v-1",
        "pop_id": "pop-1",
        "numero_versao": "1.0",
        "estado": "EM_REVISAO",
        "rascunho": {"objetivo": "Padronizar a higienização das mãos."},
        "periodicidade_sugerida": None,
    }
    base.update(over)
    return base


def _devolucao(**over) -> dict:
    base = {
        "id": "dev-1",
        "versao_id": "v-1",
        "autor_id": "P2",
        "etapa_retorno": "EM_REVISAO",
        "comentarios": "Ajustar a seção de objetivo.",
        "created_at": "2026-06-11T10:00:00+00:00",
    }
    base.update(over)
    return base


ELABORADOR = _pessoa("P1", perfil_pop="coordenador")
REVISOR = _pessoa("P2", perfil_pop="gestor_qualidade")
VALIDADOR = _pessoa("P3", perfil_pop="gerente")
INTRUSO = _pessoa("P4", perfil_pop="coordenador")
SEM_PERFIL = _pessoa("P5", perfil_pop=None)


def _sb(
    versao: dict | None = None,
    pop: dict | None = None,
    devolucoes: list[dict] | None = None,
    vinculos: list[dict] | None = None,
) -> _SupabaseMock:
    return _SupabaseMock(
        {
            "participantes": [ELABORADOR, REVISOR, VALIDADOR, INTRUSO, SEM_PERFIL],
            "pops_setores": [{"id": "s-cti", "nome": "Coordenação do CTI", "sigla": "CTI"}],
            "pops_setores_participantes": list(vinculos or []),
            "pops": [pop or _pop()],
            "pops_versoes": [versao or _versao()],
            "pops_devolucoes": list(devolucoes or []),
            # O GET/chat da elaboração consultam os Materiais de referência (#84).
            "pops_materiais_referencia": [],
            "audit_log": [],
        }
    )


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """O limiter do slowapi acumula hits por IP entre arquivos da suíte (storage
    global); zera antes de cada teste pra cada um partir limpo."""
    from app.limiter import limiter

    limiter._storage.reset()
    yield


@pytest.fixture(autouse=True)
def _mock_llm_by_default(monkeypatch):
    """O pytest carrega o `.env` real (chave OpenRouter de PROD); força o caminho
    MOCK por padrão — os testes da IA real sobrescrevem com stub próprio."""
    from app.services import ai_processor

    monkeypatch.setattr(ai_processor, "_llm_provider", lambda: "mock")
    yield


@pytest.fixture(autouse=True)
def _mock_envio_clicksign(monkeypatch):
    """A aprovação do Validador dispara o envio ao ClickSign (issue #87) e o
    .env real tem credenciais de PROD: aqui o contrato é só a transição —
    o envio em si é coberto por test_pops_assinatura."""
    from app.services import pops_clicksign_service

    monkeypatch.setattr(
        pops_clicksign_service,
        "enviar_para_assinatura",
        lambda supabase, pop, setor, versao, **kwargs: versao,
    )
    yield


@pytest.fixture(autouse=True)
def emails_enviados(monkeypatch) -> list[dict]:
    """Captura emails no boundary de IO — template e montagem rodam de verdade."""
    capturados: list[dict] = []

    def _fake_enviar(destinatario: str, assunto: str, html_content: str, texto_fallback: str) -> bool:
        capturados.append(
            {"destinatario": destinatario, "assunto": assunto, "html": html_content, "texto": texto_fallback}
        )
        return True

    monkeypatch.setattr(pops_email_service, "_enviar_email", _fake_enviar)
    return capturados


def _client_para(pessoa: dict, sb: _SupabaseMock) -> TestClient:
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded

    from app.limiter import limiter

    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(revisao_router.router, prefix="/api")
    app.include_router(elaboracao_router.router, prefix="/api")

    async def _fake_user() -> dict[str, Any]:
        return {"id": pessoa["auth_user_id"], "email": pessoa["email"], "metadata": {}}

    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_supabase_client] = lambda: sb
    return TestClient(app)


# ═══════════════════════════════════════════════════════════════════════════
# Revisão — POST /pops/{pop_id}/revisao/aprovar
# ═══════════════════════════════════════════════════════════════════════════


class TestRevisorAprova:
    def test_revisor_aprova_move_para_validacao_audita_e_notifica_validador(self, emails_enviados):
        """CA: aprovação do Revisor → EM_VALIDACAO + auditoria + email ao
        Validador designado com link."""
        sb = _sb(versao=_versao(estado="EM_REVISAO"))
        client = _client_para(REVISOR, sb)

        res = client.post("/api/pops/pop-1/revisao/aprovar")

        assert res.status_code == 200
        assert res.json()["estado"] == "EM_VALIDACAO"
        assert sb.tables["pops_versoes"][0]["estado"] == "EM_VALIDACAO"

        acoes = [r["action"] for r in sb.tables["audit_log"]]
        assert "POPS_APROVAR_REVISAO" in acoes

        assert len(emails_enviados) == 1
        email = emails_enviados[0]
        assert email["destinatario"] == "p3@hsm.com"  # Validador designado
        assert "HSM_CTI-001" in email["assunto"]
        assert "valida" in email["assunto"].lower()
        assert "/pops" in email["html"]  # link de acesso


# ═══════════════════════════════════════════════════════════════════════════
# Revisão — POST /pops/{pop_id}/revisao/devolver
# ═══════════════════════════════════════════════════════════════════════════


class TestRevisorDevolve:
    def test_revisor_devolve_com_comentarios_grava_devolucao_e_notifica_elaborador(self, emails_enviados):
        """CA: Devolução do Revisor → EM_ELABORACAO + comentários registrados
        com autor e timestamp (etapa de retorno gravada) + email ao Elaborador
        com os comentários."""
        sb = _sb(versao=_versao(estado="EM_REVISAO"))
        client = _client_para(REVISOR, sb)

        res = client.post(
            "/api/pops/pop-1/revisao/devolver",
            json={"comentarios": "Faltou detalhar a paramentação na seção 6."},
        )

        assert res.status_code == 200
        assert res.json()["estado"] == "EM_ELABORACAO"
        assert sb.tables["pops_versoes"][0]["estado"] == "EM_ELABORACAO"

        devolucoes = sb.tables["pops_devolucoes"]
        assert len(devolucoes) == 1
        dev = devolucoes[0]
        assert dev["versao_id"] == "v-1"
        assert dev["autor_id"] == "P2"  # Revisor
        assert dev["etapa_retorno"] == "EM_REVISAO"  # a Devolução grava a etapa de retorno
        assert dev["comentarios"] == "Faltou detalhar a paramentação na seção 6."
        assert dev.get("created_at")  # timestamp do registro

        acoes = [r["action"] for r in sb.tables["audit_log"]]
        assert "POPS_DEVOLVER_REVISAO" in acoes

        assert len(emails_enviados) == 1
        email = emails_enviados[0]
        assert email["destinatario"] == "p1@hsm.com"  # Elaborador designado
        assert "HSM_CTI-001" in email["assunto"]
        assert "devolv" in email["assunto"].lower()
        assert "Faltou detalhar a paramentação na seção 6." in email["html"]  # comentários visíveis
        assert "Pessoa P2" in email["html"]  # quem devolveu


# ═══════════════════════════════════════════════════════════════════════════
# Validação — POST /pops/{pop_id}/validacao/aprovar e /validacao/devolver
# ═══════════════════════════════════════════════════════════════════════════


class TestValidadorAprova:
    def test_validador_aprova_move_para_assinatura_e_audita(self, emails_enviados):
        """CA: aprovação do Validador → EM_ASSINATURA + auditoria. O disparo
        ClickSign chega na fatia de publicação — nesta, sem email (o estado
        fica visível na lista)."""
        sb = _sb(versao=_versao(estado="EM_VALIDACAO"))
        client = _client_para(VALIDADOR, sb)

        res = client.post("/api/pops/pop-1/validacao/aprovar")

        assert res.status_code == 200
        assert res.json()["estado"] == "EM_ASSINATURA"
        assert sb.tables["pops_versoes"][0]["estado"] == "EM_ASSINATURA"

        acoes = [r["action"] for r in sb.tables["audit_log"]]
        assert "POPS_APROVAR_VALIDACAO" in acoes

        assert emails_enviados == []


class TestValidadorDevolve:
    def test_validador_devolve_grava_etapa_de_retorno_validacao_e_notifica_elaborador(self, emails_enviados):
        """CA: Devolução do Validador → EM_ELABORACAO com etapa de retorno
        EM_VALIDACAO gravada (o reenvio não repassará pelo Revisor) + email ao
        Elaborador com os comentários."""
        sb = _sb(versao=_versao(estado="EM_VALIDACAO"))
        client = _client_para(VALIDADOR, sb)

        res = client.post(
            "/api/pops/pop-1/validacao/devolver",
            json={"comentarios": "Revisar os indicadores de adesão."},
        )

        assert res.status_code == 200
        assert res.json()["estado"] == "EM_ELABORACAO"
        assert sb.tables["pops_versoes"][0]["estado"] == "EM_ELABORACAO"

        devolucoes = sb.tables["pops_devolucoes"]
        assert len(devolucoes) == 1
        dev = devolucoes[0]
        assert dev["autor_id"] == "P3"  # Validador
        assert dev["etapa_retorno"] == "EM_VALIDACAO"
        assert dev["comentarios"] == "Revisar os indicadores de adesão."

        acoes = [r["action"] for r in sb.tables["audit_log"]]
        assert "POPS_DEVOLVER_VALIDACAO" in acoes

        assert len(emails_enviados) == 1
        email = emails_enviados[0]
        assert email["destinatario"] == "p1@hsm.com"  # Elaborador designado
        assert "devolv" in email["assunto"].lower()
        assert "Revisar os indicadores de adesão." in email["html"]
        assert "Pessoa P3" in email["html"]  # quem devolveu


# ═══════════════════════════════════════════════════════════════════════════
# Reenvio após Devolução — a Versão volta DIRETO a quem devolveu
# ═══════════════════════════════════════════════════════════════════════════


class TestReenvioRetornaDireto:
    def test_reenvio_apos_devolucao_do_revisor_volta_a_em_revisao(self, emails_enviados):
        """Devolução do Revisor → corrigiu → reenvio volta a EM_REVISAO, com
        email ao Revisor (o ciclo normal recomeça de onde parou)."""
        sb = _sb(
            versao=_versao(estado="EM_ELABORACAO"),
            devolucoes=[_devolucao(autor_id="P2", etapa_retorno="EM_REVISAO")],
        )
        client = _client_para(ELABORADOR, sb)

        res = client.post("/api/pops/pop-1/elaboracao/aprovar")

        assert res.status_code == 200
        assert res.json()["estado"] == "EM_REVISAO"
        assert sb.tables["pops_versoes"][0]["estado"] == "EM_REVISAO"
        assert len(emails_enviados) == 1
        assert emails_enviados[0]["destinatario"] == "p2@hsm.com"  # Revisor

    def test_reenvio_apos_devolucao_do_validador_vai_direto_a_em_validacao(self, emails_enviados):
        """CA: reenvio após Devolução do Validador → EM_VALIDACAO sem passar
        por EM_REVISAO (a Devolução gravou a etapa de retorno) + email ao
        Validador — não ao Revisor."""
        sb = _sb(
            versao=_versao(estado="EM_ELABORACAO"),
            devolucoes=[_devolucao(autor_id="P3", etapa_retorno="EM_VALIDACAO")],
        )
        client = _client_para(ELABORADOR, sb)

        res = client.post("/api/pops/pop-1/elaboracao/aprovar")

        assert res.status_code == 200
        assert res.json()["estado"] == "EM_VALIDACAO"
        assert sb.tables["pops_versoes"][0]["estado"] == "EM_VALIDACAO"
        assert len(emails_enviados) == 1
        email = emails_enviados[0]
        assert email["destinatario"] == "p3@hsm.com"  # Validador (quem devolveu)
        assert "valida" in email["assunto"].lower()

    def test_reenvio_respeita_a_devolucao_mais_recente(self, emails_enviados):
        """Ciclos sem limite: com Devoluções de ambas as etapas, vale a MAIS
        RECENTE (ex.: Validador devolveu, reenviado, Revisor… não — a última
        foi do Validador de novo: volta à Validação)."""
        sb = _sb(
            versao=_versao(estado="EM_ELABORACAO"),
            devolucoes=[
                _devolucao(
                    id="dev-1", autor_id="P2", etapa_retorno="EM_REVISAO", created_at="2026-06-10T09:00:00+00:00"
                ),
                _devolucao(
                    id="dev-2", autor_id="P3", etapa_retorno="EM_VALIDACAO", created_at="2026-06-11T15:00:00+00:00"
                ),
            ],
        )
        client = _client_para(ELABORADOR, sb)

        res = client.post("/api/pops/pop-1/elaboracao/aprovar")

        assert res.status_code == 200
        assert res.json()["estado"] == "EM_VALIDACAO"

    def test_primeiro_envio_sem_devolucao_segue_o_fluxo_normal(self, emails_enviados):
        """Sem Devolução registrada, o envio da elaboração segue o caminho
        cheio: EM_ELABORACAO → EM_REVISAO (regressão da issue #83)."""
        sb = _sb(versao=_versao(estado="EM_ELABORACAO"))
        client = _client_para(ELABORADOR, sb)

        res = client.post("/api/pops/pop-1/elaboracao/aprovar")

        assert res.status_code == 200
        assert res.json()["estado"] == "EM_REVISAO"
        assert emails_enviados[0]["destinatario"] == "p2@hsm.com"  # Revisor


# ═══════════════════════════════════════════════════════════════════════════
# Guardas papel × estado — 403/400 nas combinações inválidas
# ═══════════════════════════════════════════════════════════════════════════


class TestGuardasPapelEstado:
    def test_so_o_revisor_designado_age_na_revisao(self, emails_enviados):
        """CA: só o Revisor designado age em EM_REVISAO — Elaborador, Validador
        e terceiros (mesmo com perfil POP) levam 403, sem efeito colateral."""
        for pessoa in (ELABORADOR, VALIDADOR, INTRUSO):
            for acao, payload in (("aprovar", None), ("devolver", {"comentarios": "x"})):
                sb = _sb(versao=_versao(estado="EM_REVISAO"))
                client = _client_para(pessoa, sb)
                res = client.post(f"/api/pops/pop-1/revisao/{acao}", json=payload)
                assert res.status_code == 403, f"{pessoa['id']} em revisao/{acao} deveria levar 403"
                assert sb.tables["pops_versoes"][0]["estado"] == "EM_REVISAO"
                assert sb.tables["pops_devolucoes"] == []
        assert emails_enviados == []

    def test_so_o_validador_designado_age_na_validacao(self, emails_enviados):
        """CA: só o Validador designado age em EM_VALIDACAO — inclusive o
        Revisor leva 403."""
        for pessoa in (ELABORADOR, REVISOR, INTRUSO):
            for acao, payload in (("aprovar", None), ("devolver", {"comentarios": "x"})):
                sb = _sb(versao=_versao(estado="EM_VALIDACAO"))
                client = _client_para(pessoa, sb)
                res = client.post(f"/api/pops/pop-1/validacao/{acao}", json=payload)
                assert res.status_code == 403, f"{pessoa['id']} em validacao/{acao} deveria levar 403"
                assert sb.tables["pops_versoes"][0]["estado"] == "EM_VALIDACAO"
                assert sb.tables["pops_devolucoes"] == []
        assert emails_enviados == []

    def test_revisor_fora_de_em_revisao_400(self):
        """CA: ação do Revisor fora de EM_REVISAO → 400 (a matriz completa de
        estados inválidos, aprovar e devolver)."""
        for estado in ("A_ELABORAR", "EM_ELABORACAO", "EM_VALIDACAO", "EM_ASSINATURA", "PUBLICADO"):
            for acao, payload in (("aprovar", None), ("devolver", {"comentarios": "x"})):
                sb = _sb(versao=_versao(estado=estado))
                client = _client_para(REVISOR, sb)
                res = client.post(f"/api/pops/pop-1/revisao/{acao}", json=payload)
                assert res.status_code == 400, f"revisao/{acao} em {estado} deveria dar 400"
                assert sb.tables["pops_versoes"][0]["estado"] == estado

    def test_validador_fora_de_em_validacao_400(self):
        for estado in ("A_ELABORAR", "EM_ELABORACAO", "EM_REVISAO", "EM_ASSINATURA", "PUBLICADO"):
            for acao, payload in (("aprovar", None), ("devolver", {"comentarios": "x"})):
                sb = _sb(versao=_versao(estado=estado))
                client = _client_para(VALIDADOR, sb)
                res = client.post(f"/api/pops/pop-1/validacao/{acao}", json=payload)
                assert res.status_code == 400, f"validacao/{acao} em {estado} deveria dar 400"
                assert sb.tables["pops_versoes"][0]["estado"] == estado

    def test_sem_perfil_pop_403_em_todas_as_acoes(self):
        client = _client_para(SEM_PERFIL, _sb())
        for rota, payload in (
            ("/api/pops/pop-1/revisao/aprovar", None),
            ("/api/pops/pop-1/revisao/devolver", {"comentarios": "x"}),
            ("/api/pops/pop-1/validacao/aprovar", None),
            ("/api/pops/pop-1/validacao/devolver", {"comentarios": "x"}),
        ):
            res = client.post(rota, json=payload)
            assert res.status_code == 403, f"{rota} sem perfil POP deveria levar 403"

    def test_devolver_sem_comentarios_422(self):
        """Comentários são a essência da Devolução — vazio não passa."""
        for pessoa, rota, estado in (
            (REVISOR, "/api/pops/pop-1/revisao/devolver", "EM_REVISAO"),
            (VALIDADOR, "/api/pops/pop-1/validacao/devolver", "EM_VALIDACAO"),
        ):
            sb = _sb(versao=_versao(estado=estado))
            client = _client_para(pessoa, sb)
            res = client.post(rota, json={"comentarios": ""})
            assert res.status_code == 422
            assert sb.tables["pops_devolucoes"] == []

    def test_pop_inexistente_404(self):
        client = _client_para(REVISOR, _sb())
        res = client.post("/api/pops/pop-999/revisao/aprovar")
        assert res.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════
# GET /pops/{pop_id}/versao — leitura da Versão completa (11 seções)
# ═══════════════════════════════════════════════════════════════════════════


class TestLeituraDaVersao:
    def test_revisor_le_a_versao_completa_com_devolucoes(self):
        """CA: Revisor lê a Versão completa (identificação do POP + as seções do
        rascunho) com as Devoluções — comentários com nome e timestamp. Rascunho
        legado (chaves fixas) é migrado para a lista de seções na leitura
        (ADR 0016)."""
        rascunho = {"objetivo": "Padronizar.", "descricao_procedimento": "Passo 1."}
        sb = _sb(
            versao=_versao(estado="EM_REVISAO", rascunho=rascunho),
            devolucoes=[_devolucao(autor_id="P2", comentarios="Ajustar objetivo.")],
        )
        client = _client_para(REVISOR, sb)

        res = client.get("/api/pops/pop-1/versao")

        assert res.status_code == 200
        body = res.json()
        assert body["pop"]["codigo"] == "HSM_CTI-001"
        assert body["pop"]["elaborador_nome"] == "Pessoa P1"
        assert body["pop"]["revisor_nome"] == "Pessoa P2"
        assert body["pop"]["validador_nome"] == "Pessoa P3"
        assert body["versao"]["estado"] == "EM_REVISAO"
        secoes = body["rascunho"]["secoes"]
        assert [s["titulo"] for s in secoes] == ["Objetivo", "Descrição do procedimento"]
        assert secoes[0]["conteudo"] == "Padronizar."
        assert len(body["devolucoes"]) == 1
        dev = body["devolucoes"][0]
        assert dev["comentarios"] == "Ajustar objetivo."
        assert dev["autor_nome"] == "Pessoa P2"  # nome resolvido
        assert dev["created_at"]  # timestamp
        assert dev["etapa_retorno"] == "EM_REVISAO"

    def test_validador_e_elaborador_designados_leem_em_qualquer_estado(self):
        """Designados leem a Versão (a designação vence o escopo de Setor) —
        ex.: acompanhar o estado EM_ASSINATURA na leitura."""
        for pessoa in (VALIDADOR, ELABORADOR):
            client = _client_para(pessoa, _sb(versao=_versao(estado="EM_ASSINATURA")))
            res = client.get("/api/pops/pop-1/versao")
            assert res.status_code == 200, f"{pessoa['id']} deveria ler a Versão"

    def test_gestor_de_qualidade_le_pelo_escopo_institucional(self):
        """User story 26: o Gestor de Qualidade audita comentários e
        devoluções de qualquer Setor (escopo total)."""
        gestor = _pessoa("P6", perfil_pop="gestor_qualidade")
        sb = _sb(devolucoes=[_devolucao()])
        sb.tables["participantes"].append(gestor)
        client = _client_para(gestor, sb)

        res = client.get("/api/pops/pop-1/versao")

        assert res.status_code == 200
        assert len(res.json()["devolucoes"]) == 1

    def test_coordenador_com_vinculo_ao_setor_le(self):
        coordenador = _pessoa("P7", perfil_pop="coordenador")
        sb = _sb(vinculos=[{"participante_id": "P7", "setor_id": "s-cti"}])
        sb.tables["participantes"].append(coordenador)
        client = _client_para(coordenador, sb)

        res = client.get("/api/pops/pop-1/versao")

        assert res.status_code == 200

    def test_coordenador_de_outro_setor_403(self):
        """CA (matriz de acesso do PRD): Coordenador sem vínculo com o Setor e
        sem designação não lê a Versão."""
        coordenador = _pessoa("P7", perfil_pop="coordenador")
        sb = _sb(vinculos=[{"participante_id": "P7", "setor_id": "s-outro"}])
        sb.tables["participantes"].append(coordenador)
        client = _client_para(coordenador, sb)

        res = client.get("/api/pops/pop-1/versao")

        assert res.status_code == 403

    def test_sem_perfil_pop_403(self):
        client = _client_para(SEM_PERFIL, _sb())
        res = client.get("/api/pops/pop-1/versao")
        assert res.status_code == 403

    def test_pop_inexistente_404(self):
        client = _client_para(REVISOR, _sb())
        res = client.get("/api/pops/pop-999/versao")
        assert res.status_code == 404

    def test_devolucoes_vem_da_mais_recente_para_a_mais_antiga(self):
        """O histórico chega ordenado: a Devolução mais recente primeiro (é a
        que o Elaborador precisa atender)."""
        sb = _sb(
            devolucoes=[
                _devolucao(id="dev-1", comentarios="Primeira.", created_at="2026-06-09T08:00:00+00:00"),
                _devolucao(
                    id="dev-2",
                    autor_id="P3",
                    etapa_retorno="EM_VALIDACAO",
                    comentarios="Segunda.",
                    created_at="2026-06-11T08:00:00+00:00",
                ),
            ]
        )
        client = _client_para(REVISOR, sb)

        res = client.get("/api/pops/pop-1/versao")

        assert res.status_code == 200
        comentarios = [d["comentarios"] for d in res.json()["devolucoes"]]
        assert comentarios == ["Segunda.", "Primeira."]


# ═══════════════════════════════════════════════════════════════════════════
# Devoluções na elaboração — visíveis na tela e no contexto do agente
# ═══════════════════════════════════════════════════════════════════════════


class _FakeCompletions:
    def __init__(self, *, content: str, calls: list):
        self._content = content
        self._calls = calls

    def create(self, **kwargs):
        self._calls.append(kwargs)
        from types import SimpleNamespace

        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=self._content))])


class _FakeLLMClient:
    def __init__(self, *, content: str):
        from types import SimpleNamespace

        self.calls: list[dict] = []
        self.chat = SimpleNamespace(completions=_FakeCompletions(content=content, calls=self.calls))


def _stub_openrouter(monkeypatch) -> _FakeLLMClient:
    import json as _json

    from app.services import ai_processor

    content = _json.dumps(
        {"reply": "Vou ajustar.", "rascunho": {"objetivo": "Ajustado."}, "periodicidade_sugerida": None}
    )
    client = _FakeLLMClient(content=content)
    monkeypatch.setattr(ai_processor, "_llm_provider", lambda: "openrouter")
    monkeypatch.setattr(ai_processor, "_get_llm", lambda: (client, "modelo-teste", {}))
    return client


class TestDevolucoesNaElaboracao:
    def test_get_elaboracao_traz_devolucoes_com_nome_e_timestamp(self):
        """CA: os comentários ficam visíveis na tela de elaboração — o GET
        devolve as Devoluções com autor resolvido e timestamp."""
        sb = _sb(
            versao=_versao(estado="EM_ELABORACAO"),
            devolucoes=[_devolucao(autor_id="P2", comentarios="Detalhar a paramentação.")],
        )
        client = _client_para(ELABORADOR, sb)

        res = client.get("/api/pops/pop-1/elaboracao")

        assert res.status_code == 200
        devolucoes = res.json()["devolucoes"]
        assert len(devolucoes) == 1
        assert devolucoes[0]["comentarios"] == "Detalhar a paramentação."
        assert devolucoes[0]["autor_nome"] == "Pessoa P2"
        assert devolucoes[0]["created_at"]

    def test_comentarios_de_devolucao_entram_no_contexto_do_agente(self, monkeypatch):
        """CA: os comentários entram no contexto do agente — o prompt do chat
        carrega a Devolução (autor, etapa e texto) para o ajuste dirigido."""
        client_llm = _stub_openrouter(monkeypatch)
        sb = _sb(
            versao=_versao(estado="EM_ELABORACAO", rascunho={"objetivo": "V1."}),
            devolucoes=[
                _devolucao(autor_id="P3", etapa_retorno="EM_VALIDACAO", comentarios="Indicadores genéricos demais."),
            ],
        )
        client = _client_para(ELABORADOR, sb)

        res = client.post(
            "/api/pops/pop-1/elaboracao/chat",
            json={"rascunho": {"objetivo": "V1."}, "messages": [{"role": "user", "content": "O que ajusto?"}]},
        )

        assert res.status_code == 200
        user_prompt = client_llm.calls[0]["messages"][1]["content"]
        assert "DEVOLU" in user_prompt.upper()  # bloco presente
        assert "Indicadores genéricos demais." in user_prompt
        assert "Pessoa P3" in user_prompt  # quem devolveu
        assert "Valida" in user_prompt  # de qual etapa veio

    def test_chat_sem_devolucao_nao_inventa_bloco_de_pendencias(self, monkeypatch):
        """Sem Devolução, o prompt deixa claro que não há comentários a
        atender (nenhuma pendência fantasma)."""
        client_llm = _stub_openrouter(monkeypatch)
        sb = _sb(versao=_versao(estado="EM_ELABORACAO", rascunho={"objetivo": "V1."}))
        client = _client_para(ELABORADOR, sb)

        res = client.post(
            "/api/pops/pop-1/elaboracao/chat",
            json={"rascunho": {"objetivo": "V1."}, "messages": [{"role": "user", "content": "Oi"}]},
        )

        assert res.status_code == 200
        user_prompt = client_llm.calls[0]["messages"][1]["content"]
        assert "Nenhuma Devolução" in user_prompt


# ═══════════════════════════════════════════════════════════════════════════
# Email best-effort — falha de envio nunca desfaz a transição
# ═══════════════════════════════════════════════════════════════════════════


class TestEmailBestEffort:
    def test_falha_de_email_nao_desfaz_aprovacao_nem_devolucao(self, monkeypatch):
        def _explode(*_a, **_kw):
            raise RuntimeError("SMTP fora do ar")

        monkeypatch.setattr(pops_email_service, "_enviar_email", _explode)

        sb = _sb(versao=_versao(estado="EM_REVISAO"))
        res = _client_para(REVISOR, sb).post("/api/pops/pop-1/revisao/aprovar")
        assert res.status_code == 200
        assert sb.tables["pops_versoes"][0]["estado"] == "EM_VALIDACAO"

        sb = _sb(versao=_versao(estado="EM_VALIDACAO"))
        res = _client_para(VALIDADOR, sb).post("/api/pops/pop-1/validacao/devolver", json={"comentarios": "Ajustar."})
        assert res.status_code == 200
        assert sb.tables["pops_versoes"][0]["estado"] == "EM_ELABORACAO"
        assert len(sb.tables["pops_devolucoes"]) == 1
