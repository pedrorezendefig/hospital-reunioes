"""Gate de acesso em `POST /reunioes/upload-transcricao` (issue #539).

A ultima porta irma da #459/#464, achada pelo revisor independente de seguranca
no gate do PR #538, que varreu o router inteiro atras do que ficou de fora do
escopo daquela issue. Mesma raiz das anteriores: `require_acesso_reunioes`, a
dependency do router, deixa `me=None` (token orfao) passar de proposito, e a
unica checagem da rota era `if is_secretaria(me)`, que devolve `False` para
`None`. Quem tinha token vivo no Supabase Auth sem linha em `participantes`
passava direto.

O efeito que a rota entregava ao orfao:

- criava linha em `reunioes` com `facilitador_id` e `criada_por` nulos;
- disparava `run_pipeline`, que consome IA PAGA e gera PDF.

Esta rota e a irma do `agendar`, nao do `anexar-transcricao`: ela CRIA a reuniao
em vez de agir sobre uma existente, entao nao tem `id_reuniao` para escopar e
`get_allowed_reuniao_ids` (que devolve `[]` para o orfao e portanto 404 nas
outras rotas) nao a alcanca. O gate e a unica porta possivel.

O ator recusado tem TODAS as outras portas abertas (ativo, papel nas Reunioes,
perfil de POPs, perfil de Ouvidoria, role de diretor) menos a que cada teste
fecha: sem isso o 4xx poderia vir do gate errado e o teste ficaria verde e
vazio. E o assert que importa nao e o status, e o efeito que NAO aconteceu:
nenhuma linha nova em `reunioes` e zero chamada ao pipeline. Uma recusa tardia,
depois do insert ou depois do `add_task`, tambem devolveria 403 e passaria
despercebida (mutante M9 do PR #538).
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
from app.pipeline import orchestrator  # noqa: E402
from app.routers import reunioes as reunioes_router  # noqa: E402


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
def pipeline(monkeypatch):
    """Espiao no pipeline de IA paga. A rota resolve o atributo no `add_task`
    (`from app.pipeline.orchestrator import run_pipeline` roda no request), e o
    TestClient executa a background task antes de devolver a resposta."""
    espiao = MagicMock(return_value=None)
    monkeypatch.setattr(orchestrator, "run_pipeline", espiao)
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

# Facilitadora comum, ativa, com papel nas Reunioes: o controle positivo.
DONA = {**BASE, "id": "P_DONA", "auth_user_id": "auth-dona", "email": "dona@hsm.com"}

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
    """select/insert/update com eq, que e tudo que esta rota usa."""

    def __init__(self, tabela: list):
        self._tabela = tabela
        self._op = "select"
        self._payload: Any = None
        self._filtros_eq: list[tuple[str, Any]] = []

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
        self._filtros_eq.append((col, valor))
        return self

    def limit(self, *_a, **_kw):
        return self

    def execute(self):
        if self._op == "insert":
            novas = self._payload if isinstance(self._payload, list) else [self._payload]
            for nova in novas:
                self._tabela.append(dict(nova))
            return type("_R", (), {"data": [dict(n) for n in novas]})()

        casadas = [r for r in self._tabela if all(r.get(c) == v for c, v in self._filtros_eq)]
        if self._op == "update":
            for row in casadas:
                row.update(self._payload or {})
        return type("_R", (), {"data": [dict(r) for r in casadas]})()


class _Supabase:
    def __init__(self, participantes: list):
        self.tabelas: dict[str, list] = {
            "participantes": participantes,
            "setores": [],
            "reunioes": [],
            "reuniao_participantes": [],
        }

    def table(self, nome: str):
        return _Query(self.tabelas.setdefault(nome, []))


def _cenario(*atores: dict) -> _Supabase:
    return _Supabase([dict(a) for a in atores])


def _upload(sb: _Supabase, ator: dict):
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(reunioes_router.router, prefix="/api")
    app.dependency_overrides[get_supabase_client] = lambda: sb

    async def _fake_user() -> dict:
        return {"id": ator["auth_user_id"], "email": ator["email"], "metadata": {}}

    app.dependency_overrides[get_current_user] = _fake_user
    return TestClient(app).post(
        "/api/reunioes/upload-transcricao",
        files={"file": ("transcricao.txt", b"Fulano: bom dia a todos.\nCiclana: bom dia.\n", "text/plain")},
        data={"titulo": "Reuniao nova", "data": "2026-11-20", "tipo": "Gerencial"},
    )


# ─── O gate ───────────────────────────────────────────────────────────────────


class TestUploadTranscricao:
    def test_token_orfao_nao_cria_reuniao_nem_dispara_pipeline(self, pipeline):
        """O furo da issue: o orfao criava reuniao com `facilitador_id` e
        `criada_por` nulos e queimava IA paga no `run_pipeline`."""
        sb = _cenario(DONA)

        resp = _upload(sb, ORFAO)

        assert resp.status_code == 403, resp.text
        assert sb.tabelas["reunioes"] == [], "o gate recusou tarde: o insert ja tinha rodado"
        pipeline.assert_not_called()

    def test_quem_tem_papel_continua_subindo_transcricao(self, pipeline):
        """Controle positivo na MESMA fixture: sem ele, uma recusa vinda do gate
        errado (arquivo, formulario, rate limit) deixaria o teste acima verde e
        vazio."""
        sb = _cenario(DONA)

        resp = _upload(sb, DONA)

        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "PROCESSANDO"
        assert len(sb.tabelas["reunioes"]) == 1
        assert sb.tabelas["reunioes"][0]["status_ata"] == "PROCESSANDO"
        assert pipeline.call_count == 1

    def test_secretaria_continua_sem_acesso_a_ata(self, pipeline):
        """A recusa que a rota JA tinha, agora decidida sobre o participante que
        a dependency devolve. Se o gate novo tomasse o lugar dela, a secretaria
        (que tem papel nas Reunioes) passaria a criar ata."""
        sb = _cenario(SECRETARIA)

        resp = _upload(sb, SECRETARIA)

        assert resp.status_code == 403, resp.text
        assert "Secretária" in resp.json()["detail"]
        assert sb.tabelas["reunioes"] == []
        pipeline.assert_not_called()
