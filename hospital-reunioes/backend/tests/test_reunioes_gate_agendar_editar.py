"""Gate de acesso em `POST /reunioes/agendar` e `PATCH /reunioes/{id}` (issue #464).

As portas irmas da #459, achadas pelo revisor independente de seguranca no gate
do PR #461. Mesma raiz: `require_acesso_reunioes` deixa `me=None` (token orfao)
passar de proposito, e nenhuma das duas rotas resolvia o participante nem
chamava `get_allowed_reuniao_ids`.

- `POST /agendar` criava reuniao com `criada_por: null` e disparava
  `enviar_convites` para ids arbitrarios do cadastro: a rota virava disparador
  de email pelo dominio do hospital, que e o impacto que a propria #459 nomeia
  como principal e que o PR #461 nao alcancou.
- `PATCH /{id}` reescrevia titulo e data de reuniao de terceiro, tomava o
  `facilitador_id` para outra pessoa e zerava `lembrete_24h_enviado_at`, a flag
  que suprime o lembrete de 24h.

Cada teste de recusa monta o ator com TODAS as outras portas abertas (ativo,
papel nas Reunioes, perfil de POPs, perfil de Ouvidoria, role de diretor) e so
fecha a porta em teste: sem isso o 4xx poderia vir do gate errado e o teste
ficaria verde e vazio. E o assert que importa nao e o status, e o efeito que NAO
aconteceu: nenhuma linha nova em `reunioes`, a linha do terceiro byte a byte
como estava e zero convite disparado. Uma recusa tardia, depois do insert ou
depois do `add_task`, tambem devolveria 4xx e passaria despercebida.
"""

from __future__ import annotations

import os
import sys
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from slowapi.errors import RateLimitExceeded
from slowapi.extension import _rate_limit_exceeded_handler

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.dependencies import _participante_ctx, get_current_user, get_supabase_client  # noqa: E402
from app.limiter import limiter  # noqa: E402
from app.routers import reunioes as reunioes_router  # noqa: E402
from app.services import email_service, reuniao_email_service  # noqa: E402

REUNIAO = "R9"


@pytest.fixture(autouse=True)
def _reset_estado_global():
    # O storage do slowapi e global por IP e acumula 429 entre arquivos de
    # teste; o cache de participante e request-scoped mas sobrevive fora de um
    # request de verdade.
    limiter._storage.reset()
    _participante_ctx.set(None)
    yield
    limiter._storage.reset()
    _participante_ctx.set(None)


@pytest.fixture
def convites(monkeypatch):
    """Espiao no disparo de email. A rota resolve o atributo no `add_task`, e o
    TestClient roda a background task antes de devolver a resposta."""
    espiao = MagicMock(return_value=None)
    monkeypatch.setattr(reuniao_email_service, "enviar_convites", espiao)
    return espiao


@pytest.fixture(autouse=True)
def _sem_email_de_verdade(monkeypatch):
    """A rota `agendar` tem um segundo disparo, o aviso ao facilitador alocado
    por outra pessoa. Nenhum teste deste arquivo pode mandar email real."""
    monkeypatch.setattr(email_service, "send_meeting_scheduled_notification", MagicMock(return_value=None))


# ─── Os atores ────────────────────────────────────────────────────────────────

# Todas as portas abertas menos a que cada teste fecha.
BASE: dict[str, Any] = {
    "id": "P_BASE",
    "auth_user_id": "auth-base",
    "email": "base@hsm.com",
    "nome_completo": "Pessoa Base",
    "cargo": "Coordenadora",
    "area": "Assistencial",
    "setor": "UTI",
    "telefone": None,
    "role": "diretor",
    "ativo": True,
    "is_externo": False,
    "is_super_admin": False,
    "access_profile": "regular",
    "perfil_pop": "superadmin",
    "perfil_ouvidoria": "diretoria_executiva",
    "data_cadastro": "2026-01-10",
}

# Facilitadora que PARTICIPA da reuniao: o controle positivo.
DONA = {**BASE, "id": "P_DONA", "auth_user_id": "auth-dona", "email": "dona@hsm.com"}

# Facilitadora comum, ativa, com papel nas Reunioes, que NAO participa da
# reuniao. E o ator do segundo furo da issue: atinge todo mundo com login.
ESTRANHA = {**BASE, "id": "P_ESTRANHA", "auth_user_id": "auth-estranha", "email": "estranha@hsm.com"}

# Ja no roster da reuniao alheia.
TERCEIRO = {**BASE, "id": "P_TERCEIRO", "auth_user_id": "auth-terceiro", "email": "terceiro@hsm.com"}

# Fora do roster: e quem o `agendar` convidava por email.
CONVIDADO = {**BASE, "id": "P_CONVIDADO", "auth_user_id": "auth-convidado", "email": "convidado@hsm.com"}

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

# Sem linha em `participantes`: token vivo no Supabase Auth sem cadastro.
ORFAO = {"auth_user_id": "auth-fantasma", "email": "fantasma@hsm.com"}


# ─── Mock Supabase ────────────────────────────────────────────────────────────


class _Query:
    """select/insert/update/delete com eq e in_, que e tudo que estas rotas usam."""

    def __init__(self, tabela: list):
        self._tabela = tabela
        self._op = "select"
        self._payload: Any = None
        self._filtros_eq: list[tuple[str, Any]] = []
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

    def upsert(self, payload, **_kw):
        self._op = "upsert"
        self._payload = payload
        return self

    def delete(self):
        self._op = "delete"
        return self

    def eq(self, col, valor):
        self._filtros_eq.append((col, valor))
        return self

    def in_(self, col, valores):
        self._filtros_in.append((col, list(valores)))
        return self

    def limit(self, *_a, **_kw):
        return self

    def order(self, *_a, **_kw):
        return self

    def range(self, *_a, **_kw):
        return self

    def _casadas(self) -> list[dict]:
        return [
            r
            for r in self._tabela
            if all(r.get(c) == v for c, v in self._filtros_eq) and all(r.get(c) in vals for c, vals in self._filtros_in)
        ]

    def execute(self):
        if self._op in ("insert", "upsert"):
            novas = self._payload if isinstance(self._payload, list) else [self._payload]
            for nova in novas:
                if self._op == "upsert" and any(all(r.get(k) == v for k, v in nova.items()) for r in self._tabela):
                    continue
                self._tabela.append(dict(nova))
            return type("_R", (), {"data": [dict(n) for n in novas]})()

        casadas = self._casadas()
        if self._op == "update":
            for row in casadas:
                row.update(self._payload or {})
        elif self._op == "delete":
            for row in casadas:
                self._tabela.remove(row)
        return type("_R", (), {"data": [dict(r) for r in casadas]})()


class _Supabase:
    def __init__(self, participantes: list, roster: list[str]):
        self.tabelas: dict[str, list] = {
            "participantes": participantes,
            "setores": [],
            "reunioes": [
                {
                    "id_reuniao": REUNIAO,
                    "titulo": "Reuniao da Dona",
                    "data": "2026-10-01",
                    "hora_inicio": "09:00",
                    "status_ata": "PROGRAMADA",
                    "facilitador_id": DONA["id"],
                    "criada_por": DONA["id"],
                    "lembrete_24h_enviado_at": "2026-09-30T09:00:00",
                    "deleted_at": None,
                }
            ],
            "reuniao_participantes": [{"id_reuniao": REUNIAO, "participante_id": pid} for pid in roster],
        }

    def table(self, nome: str):
        return _Query(self.tabelas.setdefault(nome, []))


def _cenario(*atores: dict, roster: list[str] | None = None) -> _Supabase:
    return _Supabase([dict(a) for a in atores], roster if roster is not None else [DONA["id"], TERCEIRO["id"]])


def _app(sb: _Supabase, logado_como: dict) -> TestClient:
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(reunioes_router.router, prefix="/api")
    app.dependency_overrides[get_supabase_client] = lambda: sb

    async def _fake_user() -> dict:
        return {"id": logado_como["auth_user_id"], "email": logado_como["email"], "metadata": {}}

    app.dependency_overrides[get_current_user] = _fake_user
    return TestClient(app)


def _reuniao(sb: _Supabase, id_reuniao: str = REUNIAO) -> dict | None:
    for row in sb.tabelas["reunioes"]:
        if row["id_reuniao"] == id_reuniao:
            return row
    return None


def _agendar(sb: _Supabase, ator: dict, participante_ids: list[str], **extra):
    corpo = {"titulo": "Reuniao nova", "data": "2026-11-20", "participante_ids": participante_ids}
    corpo.update(extra)
    return _app(sb, ator).post("/api/reunioes/agendar", json=corpo)


def _editar(sb: _Supabase, ator: dict, id_reuniao: str = REUNIAO, **campos):
    return _app(sb, ator).patch(f"/api/reunioes/{id_reuniao}", json=campos)


# ─── POST /agendar: o disparador de email ─────────────────────────────────────


class TestAgendarReuniao:
    def test_token_orfao_nao_agenda_nem_dispara_convite(self, convites):
        """A porta 1 da issue: o orfao criava reuniao com `criada_por: null` e
        convidava por email quem quisesse do cadastro."""
        sb = _cenario(DONA, TERCEIRO, CONVIDADO)
        antes = len(sb.tabelas["reunioes"])

        resp = _agendar(sb, ORFAO, [TERCEIRO["id"], CONVIDADO["id"]])

        assert resp.status_code == 403, resp.text
        assert len(sb.tabelas["reunioes"]) == antes, "o gate recusou tarde: o insert ja tinha rodado"
        convites.assert_not_called()

    def test_quem_tem_papel_continua_agendando_e_convidando(self, convites):
        """Controle positivo na MESMA fixture: sem ele, uma recusa vinda do gate
        errado deixaria o teste acima verde e vazio."""
        sb = _cenario(DONA, TERCEIRO, CONVIDADO)

        resp = _agendar(sb, DONA, [CONVIDADO["id"]])

        assert resp.status_code == 200, resp.text
        assert resp.json()["criada_por"] == DONA["id"]
        nova = [r for r in sb.tabelas["reunioes"] if r["id_reuniao"] != REUNIAO]
        assert len(nova) == 1
        assert convites.call_count == 1
        assert convites.call_args.args[2] == [CONVIDADO["id"]]

    def test_secretaria_continua_agendando_para_outro_facilitador(self, convites):
        """A visao de gestora de agendamentos da secretaria nao pode fechar."""
        sb = _cenario(SECRETARIA, DONA, CONVIDADO)

        resp = _agendar(sb, SECRETARIA, [CONVIDADO["id"]], facilitador_id=DONA["id"])

        assert resp.status_code == 200, resp.text
        assert resp.json()["facilitador_id"] == DONA["id"]
        assert resp.json()["criada_por"] == SECRETARIA["id"]

    def test_rajada_de_agendamento_e_limitada(self, convites):
        """A rota dispara email por participante e nao tinha `@limiter.limit`,
        enquanto vizinhas como `lembrar_signatario` tem."""
        sb = _cenario(DONA, CONVIDADO)

        respostas = [_agendar(sb, DONA, [CONVIDADO["id"]]) for _ in range(61)]

        assert respostas[0].status_code == 200, respostas[0].text
        assert respostas[-1].status_code == 429
        criadas = [r for r in respostas if r.status_code == 200]
        assert len(criadas) < 61

    def test_teto_da_rajada_cabe_a_recorrencia_de_52_semanas(self, convites):
        """O teto nao e livre: a tela de Recorrencia manda ate 52 POSTs
        sequenciais (`quantidade` vai a 52 no slider). Um teto menor quebraria
        a criacao de recorrencia anual, que e feature entregue."""
        sb = _cenario(DONA, CONVIDADO)

        respostas = [_agendar(sb, DONA, [CONVIDADO["id"]]) for _ in range(52)]

        assert all(r.status_code == 200 for r in respostas), "recorrencia anual quebrou no rate limit"


# ─── PATCH /{id}: a reuniao alheia ────────────────────────────────────────────


class TestEditarReuniao:
    def test_token_orfao_nao_reescreve_reuniao(self, convites):
        """A porta 2 da issue, primeiro ator."""
        sb = _cenario(DONA, TERCEIRO)

        resp = _editar(sb, ORFAO, titulo="Sequestrada", data="2027-01-01")

        assert resp.status_code == 403, resp.text
        linha = _reuniao(sb)
        assert linha["titulo"] == "Reuniao da Dona", "o gate recusou tarde: o update ja tinha rodado"
        assert linha["data"] == "2026-10-01"
        assert linha["lembrete_24h_enviado_at"] == "2026-09-30T09:00:00"

    def test_papel_nas_reunioes_sem_participar_nao_edita_nem_toma_o_facilitador(self, convites):
        """O furo que atinge todo mundo com login: a estranha reescrevia titulo
        e data, tomava o facilitador e zerava a flag do lembrete de 24h."""
        sb = _cenario(DONA, ESTRANHA, TERCEIRO)

        resp = _editar(sb, ESTRANHA, titulo="Sequestrada", data="2027-01-01", facilitador_id=ESTRANHA["id"])

        # 404 e nao 403: o filtro de visibilidade do router nao vaza a
        # existencia da reuniao (mesma escolha das outras rotas, issue #194).
        assert resp.status_code == 404, resp.text
        linha = _reuniao(sb)
        assert linha["titulo"] == "Reuniao da Dona", "o gate recusou tarde: o update ja tinha rodado"
        assert linha["data"] == "2026-10-01"
        assert linha["facilitador_id"] == DONA["id"], "a estranha tomou o facilitador"
        assert linha["lembrete_24h_enviado_at"] == "2026-09-30T09:00:00", "a flag do lembrete de 24h foi zerada"

    def test_reuniao_alheia_fora_de_programada_nao_vira_oraculo_de_existencia(self, convites):
        """Antes do fix o par 404/400 respondia se a reuniao existe: inexistente
        dava 404, existente fora de PROGRAMADA dava 400 com o texto do status.
        O escopo tem que ser decidido ANTES do gate de status."""
        sb = _cenario(DONA, ESTRANHA, TERCEIRO)
        _reuniao(sb)["status_ata"] = "ENCERRADA"

        resp = _editar(sb, ESTRANHA, titulo="Sequestrada")

        assert resp.status_code == 404, resp.text
        assert "ENCERRADA" not in resp.text
        assert _reuniao(sb)["titulo"] == "Reuniao da Dona"

    def test_quem_participa_continua_editando(self, convites):
        sb = _cenario(DONA, ESTRANHA, TERCEIRO)

        resp = _editar(sb, DONA, titulo="Reuniao remarcada", data="2026-10-08")

        assert resp.status_code == 200, resp.text
        linha = _reuniao(sb)
        assert linha["titulo"] == "Reuniao remarcada"
        assert linha["data"] == "2026-10-08"
        # Data mexida reseta a flag para o cron reavaliar o lembrete de 24h.
        assert linha["lembrete_24h_enviado_at"] is None

    def test_secretaria_continua_editando_reuniao_alheia(self, convites):
        sb = _cenario(SECRETARIA, DONA, TERCEIRO)

        resp = _editar(sb, SECRETARIA, titulo="Remarcada pela secretaria", facilitador_id=TERCEIRO["id"])

        assert resp.status_code == 200, resp.text
        linha = _reuniao(sb)
        assert linha["titulo"] == "Remarcada pela secretaria"
        assert linha["facilitador_id"] == TERCEIRO["id"]

    def test_super_admin_continua_editando_reuniao_alheia(self, convites):
        sb = _cenario(SUPER_ADMIN, DONA, TERCEIRO)

        resp = _editar(sb, SUPER_ADMIN, titulo="Remarcada pela diretoria")

        assert resp.status_code == 200, resp.text
        assert _reuniao(sb)["titulo"] == "Remarcada pela diretoria"

    def test_facilitador_inexistente_e_recusado_para_quem_participa(self, convites):
        """A validacao do `facilitador_id` so rodava quando `is_secretaria(me)`,
        entao qualquer outra pessoa gravava um ponteiro solto na coluna."""
        sb = _cenario(DONA, TERCEIRO)

        resp = _editar(sb, DONA, facilitador_id="P_NADA")

        assert resp.status_code == 404, resp.text
        assert _reuniao(sb)["facilitador_id"] == DONA["id"]

    def test_facilitador_inativo_e_recusado_para_quem_participa(self, convites):
        sb = _cenario(DONA, {**TERCEIRO, "ativo": False})

        resp = _editar(sb, DONA, facilitador_id=TERCEIRO["id"])

        assert resp.status_code == 400, resp.text
        assert _reuniao(sb)["facilitador_id"] == DONA["id"]


# ─── A porta que ja funcionava ────────────────────────────────────────────────


def test_sem_papel_nas_reunioes_continua_barrado_pelo_gate_de_router(convites):
    """`access_profile = None` e quem ganhou login por outro contexto (POPs,
    Ouvidoria). Este ator ja era recusado antes da issue #464, e continua."""
    sem_papel = {**ESTRANHA, "access_profile": None}
    sb = _cenario(DONA, sem_papel, TERCEIRO, CONVIDADO)
    antes = len(sb.tabelas["reunioes"])

    assert _agendar(sb, sem_papel, [CONVIDADO["id"]]).status_code == 403
    assert _editar(sb, sem_papel, titulo="Sequestrada").status_code == 403
    assert len(sb.tabelas["reunioes"]) == antes
    assert _reuniao(sb)["titulo"] == "Reuniao da Dona"
    convites.assert_not_called()
