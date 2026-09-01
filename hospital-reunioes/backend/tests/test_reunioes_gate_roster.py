"""Gate de acesso nas rotas de roster de Reuniao (issue #459).

Achado pelo revisor independente de seguranca no gate do PR #456 (issue #440).
`POST /reunioes/{id}/participantes` e `DELETE /reunioes/{id}/participantes/{pid}`
confiavam so na dependency de router `require_acesso_reunioes`, que de proposito
deixa `me=None` (token orfao) passar e nao olha PARA QUAL reuniao a escrita vai.
Resultado: qualquer pessoa com login nas Reunioes escrevia no roster de reuniao
alheia, e o POST ainda disparava `enviar_convites`, isto e, email de verdade pelo
dominio do hospital para qualquer pessoa do cadastro.

Cada teste de recusa monta o ator com TODAS as outras portas abertas (ativo,
papel nas Reunioes, perfil de POPs, perfil de Ouvidoria, role de diretor) e so
fecha a porta em teste: sem isso o 403 poderia vir do gate errado e o teste
ficaria verde e vazio. Cada recusa vem acompanhada do controle positivo na MESMA
fixture, provando que quem participa da reuniao continua add e removendo.

E o assert que importa nao e o status, e o efeito que NAO aconteceu: o roster do
terceiro intacto no banco E zero convite disparado. Uma recusa tardia, depois do
upsert ou depois do `add_task`, tambem devolveria 4xx e passaria despercebida.
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
from app.services import reuniao_email_service  # noqa: E402

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

# Ja no roster: e o vinculo de terceiro que o DELETE apagava.
TERCEIRO = {**BASE, "id": "P_TERCEIRO", "auth_user_id": "auth-terceiro", "email": "terceiro@hsm.com"}

# Fora do roster: e quem o POST adicionava (e convidava por email).
CONVIDADO = {**BASE, "id": "P_CONVIDADO", "auth_user_id": "auth-convidado", "email": "convidado@hsm.com"}

# Sem linha em `participantes`: token vivo no Supabase Auth sem cadastro.
ORFAO = {"auth_user_id": "auth-fantasma", "email": "fantasma@hsm.com"}


# ─── Mock Supabase ────────────────────────────────────────────────────────────


class _Query:
    """select/upsert/delete com eq e in_, que e tudo que estas rotas usam."""

    def __init__(self, tabela: list):
        self._tabela = tabela
        self._op = "select"
        self._payload: Any = None
        self._filtros_eq: list[tuple[str, Any]] = []
        self._filtros_in: list[tuple[str, list]] = []

    def select(self, *_a, **_kw):
        self._op = "select"
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
        if self._op == "upsert":
            novas = self._payload if isinstance(self._payload, list) else [self._payload]
            for nova in novas:
                if not any(all(r.get(k) == v for k, v in nova.items()) for r in self._tabela):
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
                    "status_ata": "PROGRAMADA",
                    "facilitador_id": DONA["id"],
                    "criada_por": DONA["email"],
                    "deleted_at": None,
                }
            ],
            "reuniao_participantes": [{"id_reuniao": REUNIAO, "participante_id": pid} for pid in roster],
        }

    def table(self, nome: str):
        return _Query(self.tabelas.setdefault(nome, []))


def _cenario(*atores: dict, roster: list[str]) -> _Supabase:
    return _Supabase([dict(a) for a in atores], roster)


def _app(sb: _Supabase, logado_como: dict) -> TestClient:
    app = FastAPI()
    app.state.limiter = limiter
    app.include_router(reunioes_router.router, prefix="/api")
    app.dependency_overrides[get_supabase_client] = lambda: sb

    async def _fake_user() -> dict:
        return {"id": logado_como["auth_user_id"], "email": logado_como["email"], "metadata": {}}

    app.dependency_overrides[get_current_user] = _fake_user
    return TestClient(app)


def _roster(sb: _Supabase) -> set[str]:
    return {r["participante_id"] for r in sb.tabelas["reuniao_participantes"] if r["id_reuniao"] == REUNIAO}


def _post(sb: _Supabase, ator: dict, participante_ids: list[str]):
    return _app(sb, ator).post(
        f"/api/reunioes/{REUNIAO}/participantes",
        json={"participante_ids": participante_ids},
    )


def _delete(sb: _Supabase, ator: dict, participante_id: str):
    return _app(sb, ator).delete(f"/api/reunioes/{REUNIAO}/participantes/{participante_id}")


# ─── POST: escrita no roster alheio e o convite por email ─────────────────────


class TestAdicionarParticipantes:
    def test_token_orfao_nao_escreve_no_roster_nem_dispara_convite(self, convites):
        """`require_acesso_reunioes` deixa `me=None` passar de proposito (o gate
        de contexto so decide sobre papel). A rota de escrita nao pode."""
        sb = _cenario(DONA, TERCEIRO, CONVIDADO, roster=[DONA["id"], TERCEIRO["id"]])

        resp = _post(sb, ORFAO, [CONVIDADO["id"]])

        assert resp.status_code == 403, resp.text
        assert _roster(sb) == {DONA["id"], TERCEIRO["id"]}, "o gate recusou tarde: o upsert ja tinha rodado"
        convites.assert_not_called()

    def test_papel_nas_reunioes_sem_participar_nao_escreve_nem_dispara_convite(self, convites):
        """O furo que atinge todo mundo com login nas Reunioes: facilitadora
        comum, ativa, que nao esta na reuniao."""
        sb = _cenario(DONA, ESTRANHA, TERCEIRO, CONVIDADO, roster=[DONA["id"], TERCEIRO["id"]])

        resp = _post(sb, ESTRANHA, [CONVIDADO["id"]])

        # 404 e nao 403: o filtro de visibilidade do router nao vaza a
        # existencia da reuniao (mesma escolha das outras rotas, issue #194).
        assert resp.status_code == 404, resp.text
        assert _roster(sb) == {DONA["id"], TERCEIRO["id"]}, "o gate recusou tarde: o upsert ja tinha rodado"
        convites.assert_not_called()

    def test_quem_participa_continua_adicionando_e_convidando(self, convites):
        """Controle positivo na MESMA fixture. Sem ele, uma recusa vinda do gate
        errado faria as duas recusas acima passarem sozinhas."""
        sb = _cenario(DONA, ESTRANHA, TERCEIRO, CONVIDADO, roster=[DONA["id"], TERCEIRO["id"]])

        resp = _post(sb, DONA, [CONVIDADO["id"]])

        assert resp.status_code == 200, resp.text
        assert _roster(sb) == {DONA["id"], TERCEIRO["id"], CONVIDADO["id"]}
        assert convites.call_count == 1
        assert convites.call_args.args[1:] == (REUNIAO, [CONVIDADO["id"]])

    def test_super_admin_continua_adicionando_em_reuniao_que_nao_e_dele(self, convites):
        """`get_allowed_reuniao_ids` devolve None para super admin e secretaria:
        o gate novo nao pode fechar a visao global de agendamento."""
        super_admin = {**BASE, "id": "P_SUPER", "auth_user_id": "auth-super", "email": "diretoria@hsm.com"}
        super_admin |= {"is_super_admin": True, "access_profile": "super_admin"}
        sb = _cenario(DONA, super_admin, TERCEIRO, CONVIDADO, roster=[DONA["id"], TERCEIRO["id"]])

        resp = _post(sb, super_admin, [CONVIDADO["id"]])

        assert resp.status_code == 200, resp.text
        assert CONVIDADO["id"] in _roster(sb)
        assert convites.call_count == 1


# ─── DELETE: o vinculo de terceiro ────────────────────────────────────────────


class TestRemoverParticipante:
    def test_token_orfao_nao_apaga_vinculo_de_terceiro(self, convites):
        sb = _cenario(DONA, TERCEIRO, roster=[DONA["id"], TERCEIRO["id"]])

        resp = _delete(sb, ORFAO, TERCEIRO["id"])

        assert resp.status_code == 403, resp.text
        assert _roster(sb) == {DONA["id"], TERCEIRO["id"]}, "o gate recusou tarde: o delete ja tinha rodado"

    def test_papel_nas_reunioes_sem_participar_nao_apaga_vinculo_de_terceiro(self, convites):
        """O vinculo e o que governa quem enxerga a Reuniao e a Ata: apagar
        expulsa o terceiro do proprio historico."""
        sb = _cenario(DONA, ESTRANHA, TERCEIRO, roster=[DONA["id"], TERCEIRO["id"]])

        resp = _delete(sb, ESTRANHA, TERCEIRO["id"])

        assert resp.status_code == 404, resp.text
        assert _roster(sb) == {DONA["id"], TERCEIRO["id"]}, "o gate recusou tarde: o delete ja tinha rodado"

    def test_quem_participa_continua_removendo(self, convites):
        sb = _cenario(DONA, ESTRANHA, TERCEIRO, roster=[DONA["id"], TERCEIRO["id"]])

        resp = _delete(sb, DONA, TERCEIRO["id"])

        assert resp.status_code == 200, resp.text
        assert _roster(sb) == {DONA["id"]}


# ─── A porta que ja funcionava ────────────────────────────────────────────────


def test_sem_papel_nas_reunioes_continua_barrado_pelo_gate_de_router(convites):
    """`access_profile = None` e quem ganhou login por outro contexto (POPs,
    Ouvidoria). Este ator ja era recusado antes da issue #459, e continua."""
    sem_papel = {**ESTRANHA, "access_profile": None}
    sb = _cenario(DONA, sem_papel, TERCEIRO, CONVIDADO, roster=[DONA["id"], TERCEIRO["id"]])

    assert _post(sb, sem_papel, [CONVIDADO["id"]]).status_code == 403
    assert _delete(sb, sem_papel, TERCEIRO["id"]).status_code == 403
    assert _roster(sb) == {DONA["id"], TERCEIRO["id"]}
    convites.assert_not_called()
