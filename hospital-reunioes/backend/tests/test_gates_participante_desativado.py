"""Gates de papel recusam quem foi desligado (issue #309).

Achado do security review do PR #308: uma pessoa desativada cuja sessao do
Supabase Auth ainda e valida continuava passando em todo gate de papel, e
seguia editando dados que a Ana informa a pacientes pelo WhatsApp.

Cada gate e testado com o ator que ELE aceita quando ativo, e com todas as
outras portas abertas (super admin, papel nas Reunioes, perfil de POPs, perfil
de Ouvidoria). Um teste de recusa que passa pela porta errada fica verde e
vazio: por isso todo gate tem, logo abaixo, o controle com a MESMA fixture e
`ativo=True`, que precisa atravessar.

O supabase injetado nos testes de gate explode se alguem tocar nele: e assim
que se prova o efeito que NAO aconteceu. Um gate que recusasse tarde, depois de
consultar, faria o mock levantar AssertionError em vez de 403.
"""

from __future__ import annotations

import os
import sys
import uuid
from typing import Any

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import dependencies as deps  # noqa: E402
from app.dependencies import _participante_ctx, get_current_user, get_supabase_client  # noqa: E402
from app.limiter import limiter  # noqa: E402
from app.routers import ouvidoria as ouvidoria_router  # noqa: E402

CURRENT_USER = {"id": "auth-uid-desligada", "email": "desligada@hospital.com"}


@pytest.fixture(autouse=True)
def _reset_estado_global():
    # O storage do slowapi e global por IP e acumula 429 entre arquivos de
    # teste; o cache de participante e request-scoped mas sobrevive fora de um
    # request de verdade. Os dois sujam o resultado se nao forem zerados.
    limiter._storage.reset()
    _participante_ctx.set(None)
    yield
    limiter._storage.reset()
    _participante_ctx.set(None)


# ─── O ator ───────────────────────────────────────────────────────────────────

# Todas as portas abertas: super admin, papel nas Reunioes, perfil de POPs e
# perfil de Ouvidoria. So `ativo` esta fechado.
DESLIGADA: dict[str, Any] = {
    "id": "P_OFF",
    "auth_user_id": CURRENT_USER["id"],
    "email": CURRENT_USER["email"],
    "nome_completo": "Pessoa Desligada",
    "access_profile": "super_admin",
    "is_super_admin": True,
    "role": "diretor",
    "perfil_pop": "superadmin",
    "perfil_ouvidoria": "diretoria_executiva",
    "ativo": False,
}


def _ator(**mudancas) -> dict:
    return {**DESLIGADA, **mudancas}


class _SupabaseQueExplode:
    """Nenhum gate deste arquivo pode chegar ao banco."""

    def table(self, name: str):
        raise AssertionError(
            f"O gate deixou passar: alguem consultou a tabela {name!r} depois de recusar a pessoa desligada."
        )


@pytest.fixture
def logar(monkeypatch):
    """Troca o participante que os gates enxergam, sem tocar no banco."""

    def _instalar(participante: dict):
        async def _fake(*_a, **_kw):
            return participante

        monkeypatch.setattr(deps, "get_participante_for_user", _fake)
        monkeypatch.setattr(ouvidoria_router, "get_participante_for_user", _fake)
        return participante

    return _instalar


# ─── Gates de papel, um a um ──────────────────────────────────────────────────

# (gate, ajuste que o gate exige para ACEITAR o ator quando ele esta ativo).
# `require_secretaria` so aceita access_profile "secretaria": sem esse ajuste o
# 403 dele viria do perfil errado, nao do desligamento, e o teste nao provaria
# nada.
GATES = [
    (deps.require_acesso_reunioes, {}),
    (deps.require_participante_reunioes, {}),
    (deps.require_super_admin, {}),
    (deps.require_secretaria, {"access_profile": "secretaria", "is_super_admin": False}),
    (deps.require_super_admin_ou_secretaria, {}),
    (deps.require_perfil_pop("superadmin", "gestor_qualidade"), {}),
    (deps.require_super_admin_ou_perfil_pop("superadmin"), {}),
    (ouvidoria_router.require_acesso_painel, {}),
    (ouvidoria_router.require_perfil_ouvidoria, {}),
    (ouvidoria_router.require_diretoria_executiva, {}),
]

IDS = [
    "require_acesso_reunioes",
    "require_participante_reunioes",
    "require_super_admin",
    "require_secretaria",
    "require_super_admin_ou_secretaria",
    "require_perfil_pop",
    "require_super_admin_ou_perfil_pop",
    "require_acesso_painel",
    "require_perfil_ouvidoria",
    "require_diretoria_executiva",
]


@pytest.mark.parametrize("gate,ajuste", GATES, ids=IDS)
@pytest.mark.asyncio
async def test_gate_recusa_desligada(gate, ajuste, logar):
    logar(_ator(**ajuste))
    with pytest.raises(HTTPException) as exc:
        await gate(current_user=CURRENT_USER, supabase=_SupabaseQueExplode())
    assert exc.value.status_code == 403


@pytest.mark.parametrize("gate,ajuste", GATES, ids=IDS)
@pytest.mark.asyncio
async def test_mesma_pessoa_ativa_passa(gate, ajuste, logar):
    """O controle que impede o teste acima de ficar verde pela porta errada: a
    MESMA fixture, mudando so `ativo` para True, atravessa o gate."""
    logar(_ator(ativo=True, **ajuste))
    await gate(current_user=CURRENT_USER, supabase=_SupabaseQueExplode())


@pytest.mark.parametrize("gate,ajuste", GATES, ids=IDS)
@pytest.mark.parametrize("caso", ["null", "sem_a_chave"])
@pytest.mark.asyncio
async def test_ativo_indefinido_continua_passando(gate, ajuste, caso, logar):
    """`participantes.ativo` e BOOLEAN DEFAULT TRUE sem NOT NULL (migration
    001): linha antiga pode ter NULL, e caller antigo pode nao trazer a chave.

    Tratar isso como desligado derrubaria gente legitima no proximo deploy, sem
    aviso (mesma armadilha da issue #175 com coluna nullable). So o
    desligamento explicito fecha a porta."""
    me = _ator(ativo=None, **ajuste)
    if caso == "sem_a_chave":
        me.pop("ativo")
    logar(me)
    await gate(current_user=CURRENT_USER, supabase=_SupabaseQueExplode())


# ─── require_role: faz select proprio, nao passa por get_participante_for_user ─


class _SupabaseComParticipante:
    def __init__(self, row: dict):
        self._row = row
        self.campos_pedidos: str | None = None

    def table(self, name: str):
        assert name == "participantes"
        return self

    def select(self, campos: str):
        self.campos_pedidos = campos
        return self

    def eq(self, _campo: str, _valor):
        return self

    def execute(self):
        class _R:
            data = [self._row] if self._row else []

        _R.data = [self._row] if self._row else []
        return _R()


@pytest.mark.asyncio
async def test_require_role_recusa_desligada():
    sb = _SupabaseComParticipante(_ator())
    gate = deps.require_role("diretor", "coordenador")
    with pytest.raises(HTTPException) as exc:
        await gate(current_user=CURRENT_USER, supabase=sb)
    assert exc.value.status_code == 403
    assert "ativo" in (sb.campos_pedidos or ""), (
        "require_role precisa pedir a coluna `ativo` no select proprio; sem ela o gate nao tem como saber."
    )


@pytest.mark.asyncio
async def test_require_role_deixa_passar_a_mesma_pessoa_ativa():
    gate = deps.require_role("diretor", "coordenador")
    await gate(current_user=CURRENT_USER, supabase=_SupabaseComParticipante(_ator(ativo=True)))


# ─── Integracao: uma escrita de verdade, pela rota real ───────────────────────


def _consulta_row() -> dict:
    return {
        "id": str(uuid.uuid4()),
        "especialidade": "Cardiologia",
        "valor_rs": 380.0,
        "descricao_servico": "Consulta com cardiologista adulto.",
        "diferencial_1": "",
        "diferencial_2": "",
        "diferencial_3": "",
        "alta_demanda": False,
        "observacoes_ana": "",
        "ativo": True,
        "ultima_atualizacao": "2026-03-10",
    }


class _Query:
    def __init__(self, rows: list):
        self._rows = rows
        self._op = "select"
        self._payload: Any = None
        self._filtros: list[tuple[str, Any]] = []

    def select(self, *_a, **_kw):
        self._op = "select"
        return self

    def update(self, payload):
        self._op = "update"
        self._payload = payload
        return self

    def eq(self, col, valor):
        self._filtros.append((col, valor))
        return self

    def order(self, *_a, **_kw):
        return self

    def execute(self):
        casadas = [r for r in self._rows if all(r.get(c) == v for c, v in self._filtros)]
        if self._op == "update":
            for row in casadas:
                row.update(self._payload)
        return type("_R", (), {"data": [dict(r) for r in casadas], "count": None})()


class _SupabaseIntegracao:
    def __init__(self, consultas: list, participantes: list):
        self.tabelas = {"consultas_particulares": consultas, "participantes": participantes}
        self.audit: list = []

    def table(self, name: str):
        if name == "audit_log":
            sink = self.audit

            class _A:
                def insert(self, row):
                    sink.append(row)
                    return self

                def execute(self):
                    return type("_R", (), {"data": []})()

            return _A()
        return _Query(self.tabelas[name])


def _app_dados_atendimento(consultas: list, me: dict) -> TestClient:
    from app.routers.admin import dados_atendimento as dados_router

    app = FastAPI()
    app.state.limiter = limiter
    app.include_router(dados_router.router, prefix="/api")

    sb = _SupabaseIntegracao(consultas, [dict(me)])
    app.dependency_overrides[get_supabase_client] = lambda: sb

    async def _fake_user() -> dict:
        return {"id": me["auth_user_id"], "email": me["email"], "metadata": {}}

    app.dependency_overrides[get_current_user] = _fake_user
    return TestClient(app)


def test_escrita_em_dados_do_atendimento_nao_acontece_para_desligada():
    """Gate de ESCRITA, ponta a ponta pela rota real: o PATCH de Dados do
    Atendimento, cujo valor chega ao paciente pelo WhatsApp da Ana.

    O assert que importa nao e o 403: e o preco continuar 380. Uma recusa
    tardia, depois do update, tambem devolveria 403 e passaria despercebida."""
    linha = _consulta_row()
    consultas = [linha]
    client = _app_dados_atendimento(consultas, DESLIGADA)

    resp = client.patch(f"/api/admin/dados-atendimento/consultas-particulares/{linha['id']}", json={"valor_rs": 999.0})

    assert resp.status_code == 403
    assert consultas[0]["valor_rs"] == 380.0, "o gate recusou tarde: a linha foi gravada antes do 403"
    assert consultas[0]["ultima_atualizacao"] == "2026-03-10"


def test_escrita_acontece_para_a_mesma_pessoa_ativa():
    """Controle da integracao: a MESMA pessoa, so com `ativo=True`, grava. Sem
    isto, um 404 de rota errada faria o teste acima passar sozinho."""
    linha = _consulta_row()
    consultas = [linha]
    client = _app_dados_atendimento(consultas, _ator(ativo=True))

    resp = client.patch(f"/api/admin/dados-atendimento/consultas-particulares/{linha['id']}", json={"valor_rs": 999.0})

    assert resp.status_code == 200, resp.text
    assert consultas[0]["valor_rs"] == 999.0


def test_leitura_em_dados_do_atendimento_nao_acontece_para_desligada():
    """Gate de LEITURA (`require_participante_reunioes`) na mesma rota real."""
    consultas = [_consulta_row()]
    client = _app_dados_atendimento(consultas, DESLIGADA)

    resp = client.get("/api/admin/dados-atendimento/consultas-particulares")

    assert resp.status_code == 403


def test_leitura_acontece_para_a_mesma_pessoa_ativa():
    consultas = [_consulta_row()]
    client = _app_dados_atendimento(consultas, _ator(ativo=True))

    resp = client.get("/api/admin/dados-atendimento/consultas-particulares")

    assert resp.status_code == 200, resp.text
