"""Secretária não é facilitadora de reunião (issue #761).

A Secretária agendava pelo Calendário, o modal não mandava `facilitador_id` e o
`agendar` caía no fallback histórico: quem está logado vira facilitador. A
reunião nascia com uma facilitadora que não monta a ata (a Ata Guiada mostra
"Sem acesso" e as pendências devolvem 403), e ninguém era avisado.

Decisão da triagem de 27/09/2026, com o alcance fechado com o Pedro na mesma
data: Secretária como facilitadora é recusada em QUALQUER caminho, venha de
quem vier, no `agendar` e na edição. E a Secretária que agenda tem que dizer
quem facilita: para ela o fallback não existe mais. Para os outros perfis o
fallback continua igual.

Como no teste de gate vizinho, o assert que importa é o efeito que NÃO
aconteceu: nenhuma reunião nova e nenhum convite disparado, porque uma recusa
tardia (depois do insert ou do `add_task`) também devolveria 4xx.
"""

from __future__ import annotations

import os
import sys
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.dependencies import _participante_ctx, get_current_user, get_supabase_client  # noqa: E402
from app.limiter import limiter  # noqa: E402
from app.routers import reunioes as reunioes_router  # noqa: E402
from app.services import email_service, reuniao_email_service  # noqa: E402

REUNIAO = "R9"

BASE: dict[str, Any] = {
    "id": "P_BASE",
    "auth_user_id": "auth-base",
    "email": "base@hsm.com",
    "nome_completo": "Pessoa Base",
    "role": "diretor",
    "ativo": True,
    "is_externo": False,
    "is_super_admin": False,
    "access_profile": "regular",
    "perfil_pop": None,
    "perfil_ouvidoria": None,
}

FACILITADORA = {**BASE, "id": "P_FACIL", "auth_user_id": "auth-facil", "email": "facil@hsm.com"}

SUPER_ADMIN = {
    **BASE,
    "id": "P_SUPER",
    "auth_user_id": "auth-super",
    "email": "diretoria@hsm.com",
    "is_super_admin": True,
    "access_profile": "super_admin",
}

SECRETARIA = {
    **BASE,
    "id": "P_SECRE",
    "auth_user_id": "auth-secre",
    "email": "secretaria@hsm.com",
    "role": "secretaria",
    "access_profile": "secretaria",
}

OUTRA_SECRETARIA = {**SECRETARIA, "id": "P_SECRE2", "auth_user_id": "auth-secre2", "email": "secretaria2@hsm.com"}

CONVIDADO = {**BASE, "id": "P_CONVIDADO", "auth_user_id": "auth-convidado", "email": "convidado@hsm.com"}


@pytest.fixture(autouse=True)
def _reset_estado_global():
    limiter._storage.reset()
    _participante_ctx.set(None)
    yield
    limiter._storage.reset()
    _participante_ctx.set(None)


@pytest.fixture
def convites(monkeypatch):
    espiao = MagicMock(return_value=None)
    monkeypatch.setattr(reuniao_email_service, "enviar_convites", espiao)
    return espiao


@pytest.fixture
def aviso_ao_facilitador(monkeypatch):
    espiao = MagicMock(return_value=None)
    monkeypatch.setattr(email_service, "send_meeting_scheduled_notification", espiao)
    return espiao


class _Query:
    def __init__(self, tabela: list):
        self._tabela = tabela
        self._op = "select"
        self._payload: Any = None
        self._filtros: list[tuple[str, Any]] = []
        self._filtros_in: list[tuple[str, list]] = []

    def select(self, *_a, **_kw):
        self._op = "select"
        return self

    def insert(self, payload, **_kw):
        self._op = "insert"
        self._payload = payload
        return self

    def update(self, payload):
        self._op = "update"
        self._payload = payload
        return self

    def eq(self, col, valor):
        self._filtros.append((col, valor))
        return self

    def in_(self, col, valores):
        self._filtros_in.append((col, list(valores)))
        return self

    def limit(self, *_a, **_kw):
        return self

    def execute(self):
        if self._op == "insert":
            novas = self._payload if isinstance(self._payload, list) else [self._payload]
            self._tabela.extend(dict(n) for n in novas)
            return type("_R", (), {"data": [dict(n) for n in novas]})()
        casadas = [
            r
            for r in self._tabela
            if all(r.get(c) == v for c, v in self._filtros) and all(r.get(c) in vs for c, vs in self._filtros_in)
        ]
        if self._op == "update":
            for row in casadas:
                row.update(self._payload or {})
        return type("_R", (), {"data": [dict(r) for r in casadas]})()


class _Supabase:
    def __init__(self, participantes: list[dict], facilitador_atual: dict = FACILITADORA):
        self.tabelas: dict[str, list] = {
            "participantes": [dict(p) for p in participantes],
            "reunioes": [
                {
                    "id_reuniao": REUNIAO,
                    "titulo": "Reuniao da Facilitadora",
                    "data": "2026-10-01",
                    "status_ata": "PROGRAMADA",
                    "facilitador_id": facilitador_atual["id"],
                    "criada_por": SECRETARIA["id"],
                    "deleted_at": None,
                }
            ],
            "reuniao_participantes": [
                {"id_reuniao": REUNIAO, "participante_id": FACILITADORA["id"]},
            ],
        }

    def table(self, nome: str):
        return _Query(self.tabelas.setdefault(nome, []))

    def reunioes_novas(self) -> list[dict]:
        return [r for r in self.tabelas["reunioes"] if r["id_reuniao"] != REUNIAO]

    def reuniao(self) -> dict:
        return next(r for r in self.tabelas["reunioes"] if r["id_reuniao"] == REUNIAO)


def _cliente(sb: _Supabase, logado_como: dict) -> TestClient:
    app = FastAPI()
    app.state.limiter = limiter
    app.include_router(reunioes_router.router, prefix="/api")
    app.dependency_overrides[get_supabase_client] = lambda: sb

    async def _fake_user() -> dict:
        return {"id": logado_como["auth_user_id"], "email": logado_como["email"], "metadata": {}}

    app.dependency_overrides[get_current_user] = _fake_user
    return TestClient(app)


def _agendar(sb: _Supabase, ator: dict, **extra):
    corpo = {"titulo": "Reuniao nova", "data": "2026-11-20", "participante_ids": [CONVIDADO["id"]]}
    corpo.update(extra)
    return _cliente(sb, ator).post("/api/reunioes/agendar", json=corpo)


class TestSecretariaAgenda:
    def test_sem_facilitador_e_recusada_sem_criar_nem_convidar(self, convites, aviso_ao_facilitador):
        """O caminho do bug: o modal do Calendário não manda `facilitador_id`."""
        sb = _Supabase([SECRETARIA, FACILITADORA, CONVIDADO])

        resp = _agendar(sb, SECRETARIA)

        assert resp.status_code == 422, resp.text
        assert "facilitador" in resp.json()["detail"].lower()
        assert sb.reunioes_novas() == [], "a recusa veio tarde: a reunião já tinha nascido"
        convites.assert_not_called()
        aviso_ao_facilitador.assert_not_called()

    @pytest.mark.parametrize("facilitadora", [SECRETARIA, OUTRA_SECRETARIA], ids=["ela-mesma", "outra-secretaria"])
    def test_com_secretaria_como_facilitadora_e_recusada(self, convites, aviso_ao_facilitador, facilitadora):
        sb = _Supabase([SECRETARIA, OUTRA_SECRETARIA, FACILITADORA, CONVIDADO])

        resp = _agendar(sb, SECRETARIA, facilitador_id=facilitadora["id"])

        assert resp.status_code == 422, resp.text
        assert "secretária" in resp.json()["detail"].lower()
        assert sb.reunioes_novas() == []
        convites.assert_not_called()
        aviso_ao_facilitador.assert_not_called()


class TestOutrosPerfisAgendam:
    def test_ninguem_aponta_secretaria_como_facilitadora(self, convites, aviso_ao_facilitador):
        """Alcance fechado com o Pedro: a reunião trava do mesmo jeito venha de
        quem vier, então a recusa não depende de quem agenda."""
        sb = _Supabase([SUPER_ADMIN, SECRETARIA, CONVIDADO])

        resp = _agendar(sb, SUPER_ADMIN, facilitador_id=SECRETARIA["id"])

        assert resp.status_code == 422, resp.text
        assert sb.reunioes_novas() == []
        convites.assert_not_called()
        aviso_ao_facilitador.assert_not_called()

    @pytest.mark.parametrize("ator", [FACILITADORA, SUPER_ADMIN], ids=["facilitador", "super-admin"])
    def test_sem_facilitador_quem_agenda_continua_virando_facilitador(self, convites, ator):
        """O fallback histórico só fecha para a Secretária."""
        sb = _Supabase([ator, CONVIDADO])

        resp = _agendar(sb, ator)

        assert resp.status_code == 200, resp.text
        assert resp.json()["facilitador_id"] == ator["id"]
        assert len(sb.reunioes_novas()) == 1


class TestSecretariaAgendaCerto:
    def test_com_facilitador_valido_cria_a_reuniao_com_ele(self, convites, aviso_ao_facilitador):
        """Controle positivo na mesma fixture das recusas: sem ele, um 422 vindo
        de outro lugar deixaria os testes acima verdes e vazios."""
        sb = _Supabase([SECRETARIA, FACILITADORA, CONVIDADO])

        resp = _agendar(sb, SECRETARIA, facilitador_id=FACILITADORA["id"])

        assert resp.status_code == 200, resp.text
        assert resp.json()["facilitador_id"] == FACILITADORA["id"]
        assert resp.json()["criada_por"] == SECRETARIA["id"]
        [nova] = sb.reunioes_novas()
        assert nova["facilitador_id"] == FACILITADORA["id"]
        assert convites.call_count == 1
        aviso_ao_facilitador.assert_called_once()


class TestSerieDaRecorrencia:
    """Issue #890: a Recorrência manda um `agendar` por cópia, cada uma herdando
    o facilitador da original. Quando quem cria a série não é o facilitador,
    cada cópia mandava o aviso "marcaram uma reunião para você": 52 semanas, 52
    emails. Agora é um aviso por série; o convite por cópia aos participantes
    continua como estava."""

    def test_serie_criada_por_outra_pessoa_avisa_o_facilitador_uma_vez(self, convites, aviso_ao_facilitador):
        sb = _Supabase([SECRETARIA, FACILITADORA, CONVIDADO])

        for data in ("2026-11-02", "2026-11-09", "2026-11-16"):
            resp = _agendar(
                sb,
                SECRETARIA,
                data=data,
                facilitador_id=FACILITADORA["id"],
                id_grupo_recorrencia="serie-1",
                nome_grupo_recorrencia="Semanal",
            )
            assert resp.status_code == 200, resp.text

        assert len(sb.reunioes_novas()) == 3
        aviso_ao_facilitador.assert_called_once()
        assert aviso_ao_facilitador.call_args.args[2] == FACILITADORA["id"]
        assert convites.call_count == 3, "o convite por cópia aos participantes não muda"

    def test_outra_serie_avisa_de_novo(self, convites, aviso_ao_facilitador):
        """O aviso é por série, não por facilitador: uma série nova é notícia nova."""
        sb = _Supabase([SECRETARIA, FACILITADORA, CONVIDADO])

        for grupo in ("serie-1", "serie-2"):
            resp = _agendar(sb, SECRETARIA, facilitador_id=FACILITADORA["id"], id_grupo_recorrencia=grupo)
            assert resp.status_code == 200, resp.text

        assert aviso_ao_facilitador.call_count == 2


def _editar(sb: _Supabase, ator: dict, **campos):
    return _cliente(sb, ator).patch(f"/api/reunioes/{REUNIAO}", json=campos)


class TestEdicao:
    @pytest.mark.parametrize(
        "ator", [SECRETARIA, SUPER_ADMIN, FACILITADORA], ids=["secretaria", "super-admin", "facilitador"]
    )
    def test_ninguem_troca_o_facilitador_por_uma_secretaria(self, ator):
        """A `/secretaria/nova?edit=` troca o facilitador por este PATCH."""
        sb = _Supabase([ator, SECRETARIA, FACILITADORA])

        resp = _editar(sb, ator, titulo="Remarcada", facilitador_id=SECRETARIA["id"])

        assert resp.status_code == 422, resp.text
        linha = sb.reuniao()
        assert linha["facilitador_id"] == FACILITADORA["id"], "a Secretária virou facilitadora"
        assert linha["titulo"] == "Reuniao da Facilitadora", "a recusa veio tarde: o update já tinha rodado"

    def test_trocar_por_um_facilitador_de_verdade_continua_valendo(self):
        sb = _Supabase([SECRETARIA, FACILITADORA, SUPER_ADMIN])

        resp = _editar(sb, SECRETARIA, facilitador_id=SUPER_ADMIN["id"])

        assert resp.status_code == 200, resp.text
        assert sb.reuniao()["facilitador_id"] == SUPER_ADMIN["id"]


class TestReuniaoLegada:
    """Issue #890: reunião que já nasceu com a Secretária facilitadora (as da
    #886). A `/secretaria/nova?edit=` sempre reenvia o facilitador, então recusar
    o MESMO id travava a correção de um título. A trava vale só quando o
    facilitador muda para uma Secretária."""

    def test_reenviar_a_mesma_facilitadora_e_mudar_so_o_titulo_e_aceito(self):
        sb = _Supabase([SECRETARIA, OUTRA_SECRETARIA, FACILITADORA], facilitador_atual=SECRETARIA)

        resp = _editar(sb, SECRETARIA, titulo="Titulo corrigido", facilitador_id=SECRETARIA["id"])

        assert resp.status_code == 200, resp.text
        assert sb.reuniao()["titulo"] == "Titulo corrigido"
        assert sb.reuniao()["facilitador_id"] == SECRETARIA["id"]

    def test_trocar_para_outra_secretaria_continua_recusado(self):
        sb = _Supabase([SECRETARIA, OUTRA_SECRETARIA, FACILITADORA], facilitador_atual=SECRETARIA)

        resp = _editar(sb, SECRETARIA, titulo="Titulo corrigido", facilitador_id=OUTRA_SECRETARIA["id"])

        assert resp.status_code == 422, resp.text
        assert sb.reuniao()["facilitador_id"] == SECRETARIA["id"]
        assert sb.reuniao()["titulo"] == "Reuniao da Facilitadora"


def _forcar(sb: _Supabase, **campos):
    corpo = {"reason": "acerto de cadastro", **campos}
    return _cliente(sb, SUPER_ADMIN).patch(f"/api/reunioes/{REUNIAO}/force", json=corpo)


class TestEdicaoForcada:
    """Issue #890: a trava valia no `agendar` e no PATCH comum, e o `force` do
    Super admin ainda deixava a Secretária virar facilitadora."""

    def test_force_com_secretaria_como_facilitadora_e_recusado_sem_alterar(self):
        sb = _Supabase([SUPER_ADMIN, SECRETARIA, FACILITADORA])

        resp = _forcar(sb, titulo="Forcada", facilitador_id=SECRETARIA["id"])

        assert resp.status_code == 422, resp.text
        assert "secretária" in resp.json()["detail"].lower()
        linha = sb.reuniao()
        assert linha["facilitador_id"] == FACILITADORA["id"], "a Secretária virou facilitadora pelo force"
        assert linha["titulo"] == "Reuniao da Facilitadora", "a recusa veio tarde: o update já tinha rodado"

    def test_force_com_facilitador_de_verdade_continua_valendo(self):
        """Controle positivo: sem ele, um 422 de outra origem deixaria a recusa verde e vazia."""
        sb = _Supabase([SUPER_ADMIN, SECRETARIA, FACILITADORA])

        resp = _forcar(sb, titulo="Forcada", facilitador_id=SUPER_ADMIN["id"])

        assert resp.status_code == 200, resp.text
        assert sb.reuniao()["facilitador_id"] == SUPER_ADMIN["id"]
        assert sb.reuniao()["titulo"] == "Forcada"
