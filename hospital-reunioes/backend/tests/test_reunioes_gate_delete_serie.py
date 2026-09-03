"""Escopo em `DELETE /reunioes/grupo/{id_grupo_recorrencia}` (issue #540).

A porta irma achada pelo revisor independente de seguranca no gate do PR #538: a
rota tinha so `require_role("diretor", "presidente", "gerente")` e nenhum escopo,
entao qualquer pessoa com papel de gestao apagava (delete duro) a serie recorrente
inteira de qualquer outra pessoa. O par 404/400 ainda funcionava como oraculo de
existencia: serie alheia ja em andamento respondia 400 com a contagem das
reunioes bloqueadas, e serie inexistente respondia 404.

Decisao de dominio da triagem de 03/09/2026: leitura 2, so apaga serie de que
participa. Mesmo desenho do `PATCH /reunioes/{id}` da #464 (PR #538), com o
escopo de `get_allowed_reuniao_ids` decidido ANTES do select e do gate de status,
e recusa em 404 (precedente #461 e #194), nao 403.

Cada teste de recusa monta o ator com TODAS as outras portas abertas (ativo,
papel nas Reunioes, perfil de POPs, perfil de Ouvidoria, role de diretor) e a
serie EXISTINDO no banco, so que pertencendo a outra pessoa: sem isso o 404
poderia vir de "serie nao existe" e o teste ficaria verde e vazio. E o assert que
importa nao e o status, e o efeito que NAO aconteceu: as reunioes da serie
continuam no banco, byte a byte.
"""

from __future__ import annotations

import os
import sys
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from slowapi.errors import RateLimitExceeded
from slowapi.extension import _rate_limit_exceeded_handler

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.dependencies import _participante_ctx, get_current_user, get_supabase_client  # noqa: E402
from app.limiter import limiter  # noqa: E402
from app.routers import reunioes as reunioes_router  # noqa: E402

# As series do cenario.
SERIE_DONA = "G_DONA"  # duas ocorrencias PROGRAMADAS, roster da Dona
SERIE_EM_ANDAMENTO = "G_ANDAMENTO"  # uma ocorrencia ja CONCLUIDA, roster da Dona
SERIE_MISTA = "G_MISTA"  # uma ocorrencia da Dona, outra so do Terceiro
SERIE_ESTRANHA = "G_ESTRANHA"  # a serie propria da Estranha, pra ela ter escopo nao vazio
SERIE_INEXISTENTE = "G_QUE_NAO_EXISTE"


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

# Participa das series: o controle positivo.
DONA = {**BASE, "id": "P_DONA", "auth_user_id": "auth-dona", "email": "dona@hsm.com"}

# Diretora ativa, com papel nas Reunioes, que participa da PROPRIA serie e de
# nenhuma outra. E a atora do furo: papel de gestao sem vinculo com a serie
# alheia apagava tudo. O escopo dela e proposital nao vazio, senao a recusa
# passaria pela porta errada (a saida curta de quem nao participa de nada) e o
# teste ficaria verde mesmo com o filtro por id fora do select.
ESTRANHA = {**BASE, "id": "P_ESTRANHA", "auth_user_id": "auth-estranha", "email": "estranha@hsm.com"}

# Participa das series junto com a Dona, e e o dono unico de uma ocorrencia da
# serie mista.
TERCEIRO = {**BASE, "id": "P_TERCEIRO", "auth_user_id": "auth-terceiro", "email": "terceiro@hsm.com"}

SUPER_ADMIN = {
    **BASE,
    "id": "P_SUPER",
    "auth_user_id": "auth-super",
    "email": "diretoria@hsm.com",
    "is_super_admin": True,
    "access_profile": "super_admin",
}

# Sem linha em `participantes`: token vivo no Supabase Auth sem cadastro.
ORFAO = {"auth_user_id": "auth-fantasma", "email": "fantasma@hsm.com"}


# ─── Mock Supabase ────────────────────────────────────────────────────────────


class _Query:
    """select/delete com eq e in_, que e tudo que esta rota usa."""

    def __init__(self, tabela: list):
        self._tabela = tabela
        self._op = "select"
        self._filtros_eq: list[tuple[str, Any]] = []
        self._filtros_in: list[tuple[str, list]] = []

    def select(self, *_a, **_kw):
        self._op = "select"
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

    def _casadas(self) -> list[dict]:
        return [
            r
            for r in self._tabela
            if all(r.get(c) == v for c, v in self._filtros_eq) and all(r.get(c) in vals for c, vals in self._filtros_in)
        ]

    def execute(self):
        casadas = self._casadas()
        if self._op == "delete":
            for row in casadas:
                self._tabela.remove(row)
        return type("_R", (), {"data": [dict(r) for r in casadas]})()


def _reuniao(id_reuniao: str, grupo: str, status: str = "PROGRAMADA") -> dict:
    return {
        "id_reuniao": id_reuniao,
        "titulo": f"Ocorrencia {id_reuniao}",
        "data": "2026-10-01",
        "hora_inicio": "09:00",
        "status_ata": status,
        "facilitador_id": DONA["id"],
        "criada_por": DONA["id"],
        "id_grupo_recorrencia": grupo,
        "nome_grupo_recorrencia": grupo,
        "deleted_at": None,
    }


class _Supabase:
    def __init__(self, participantes: list):
        self.tabelas: dict[str, list] = {
            "participantes": participantes,
            "reunioes": [
                _reuniao("R_DONA_1", SERIE_DONA),
                _reuniao("R_DONA_2", SERIE_DONA),
                _reuniao("R_AND_1", SERIE_EM_ANDAMENTO),
                _reuniao("R_AND_2", SERIE_EM_ANDAMENTO, status="CONCLUIDA"),
                _reuniao("R_MISTA_DONA", SERIE_MISTA),
                _reuniao("R_MISTA_TERCEIRO", SERIE_MISTA),
                _reuniao("R_ESTRANHA_1", SERIE_ESTRANHA),
            ],
            # A Dona participa de tudo menos da segunda ocorrencia da serie
            # mista, que e so do Terceiro.
            "reuniao_participantes": [
                {"id_reuniao": "R_DONA_1", "participante_id": DONA["id"]},
                {"id_reuniao": "R_DONA_2", "participante_id": DONA["id"]},
                {"id_reuniao": "R_AND_1", "participante_id": DONA["id"]},
                {"id_reuniao": "R_AND_2", "participante_id": DONA["id"]},
                {"id_reuniao": "R_MISTA_DONA", "participante_id": DONA["id"]},
                {"id_reuniao": "R_MISTA_TERCEIRO", "participante_id": TERCEIRO["id"]},
                {"id_reuniao": "R_ESTRANHA_1", "participante_id": ESTRANHA["id"]},
            ],
        }

    def table(self, nome: str):
        return _Query(self.tabelas.setdefault(nome, []))


def _cenario(*atores: dict) -> _Supabase:
    return _Supabase([dict(a) for a in atores])


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


def _apagar_serie(sb: _Supabase, ator: dict, grupo: str):
    return _app(sb, ator).delete(f"/api/reunioes/grupo/{grupo}")


def _ids_no_banco(sb: _Supabase) -> set[str]:
    return {r["id_reuniao"] for r in sb.tabelas["reunioes"]}


# ─── A recusa: papel de gestao sem vinculo ────────────────────────────────────


class TestSerieAlheia:
    def test_diretora_sem_vinculo_nao_apaga_serie_de_terceiro(self):
        """O furo da issue. A serie EXISTE e esta toda PROGRAMADA (ou seja,
        nenhum outro gate teria motivo pra recusar): a unica coisa que segura o
        delete duro e o escopo."""
        sb = _cenario(DONA, ESTRANHA, TERCEIRO)
        antes = _ids_no_banco(sb)

        resp = _apagar_serie(sb, ESTRANHA, SERIE_DONA)

        assert resp.status_code == 404, resp.text
        assert _ids_no_banco(sb) == antes, "a serie alheia foi apagada: o escopo recusou tarde ou nao existe"

    def test_recusa_por_escopo_e_indistinguivel_de_serie_inexistente(self):
        """Criterio de aceite: mesmo corpo e mesmo status nos dois casos, senao a
        rota vira oraculo de existencia de serie alheia."""
        sb = _cenario(DONA, ESTRANHA, TERCEIRO)

        alheia = _apagar_serie(sb, ESTRANHA, SERIE_DONA)
        inexistente = _apagar_serie(sb, ESTRANHA, SERIE_INEXISTENTE)

        assert alheia.status_code == inexistente.status_code == 404
        assert alheia.json() == inexistente.json()

    def test_serie_alheia_em_andamento_tambem_devolve_404(self):
        """O mutante que move o escopo pra depois do select e do gate de status
        morre aqui: com a ordem invertida, a serie alheia que ja tem reuniao
        CONCLUIDA responde 400 contando quantas ocorrencias estao em andamento, e
        a existencia dela vaza."""
        sb = _cenario(DONA, ESTRANHA, TERCEIRO)
        antes = _ids_no_banco(sb)

        resp = _apagar_serie(sb, ESTRANHA, SERIE_EM_ANDAMENTO)

        assert resp.status_code == 404, "o gate de status respondeu antes do escopo e vazou a serie alheia"
        assert resp.json() == _apagar_serie(sb, ESTRANHA, SERIE_INEXISTENTE).json()
        assert _ids_no_banco(sb) == antes

    def test_token_orfao_nao_apaga_serie(self):
        """Controle da porta que ja estava fechada (`require_role` nao acha linha
        em `participantes`): o orfao para em 403 e nada some do banco."""
        sb = _cenario(DONA, TERCEIRO)
        antes = _ids_no_banco(sb)

        resp = _apagar_serie(sb, ORFAO, SERIE_DONA)

        assert resp.status_code == 403, resp.text
        assert _ids_no_banco(sb) == antes


# ─── O controle positivo: guarda-corpo nao pode virar indisponibilidade ───────


class TestSeriePropria:
    def test_quem_participa_continua_apagando_a_propria_serie(self):
        """Sem este teste, um escopo que recusa todo mundo passaria verde."""
        sb = _cenario(DONA, ESTRANHA, TERCEIRO)

        resp = _apagar_serie(sb, DONA, SERIE_DONA)

        assert resp.status_code == 200, resp.text
        assert resp.json()["id_grupo_recorrencia"] == SERIE_DONA
        assert "R_DONA_1" not in _ids_no_banco(sb)
        assert "R_DONA_2" not in _ids_no_banco(sb)

    def test_super_admin_continua_sem_filtro(self):
        """`get_allowed_reuniao_ids` devolve None pra super admin: a visao global
        nao pode fechar."""
        sb = _cenario(SUPER_ADMIN, DONA, TERCEIRO)

        resp = _apagar_serie(sb, SUPER_ADMIN, SERIE_DONA)

        assert resp.status_code == 200, resp.text
        assert "R_DONA_1" not in _ids_no_banco(sb)

    def test_gate_de_status_continua_valendo_na_propria_serie(self):
        """O escopo nao substitui o gate de status: na serie de que a Dona
        participa, a ocorrencia CONCLUIDA continua bloqueando a exclusao."""
        sb = _cenario(DONA, TERCEIRO)
        antes = _ids_no_banco(sb)

        resp = _apagar_serie(sb, DONA, SERIE_EM_ANDAMENTO)

        assert resp.status_code == 400, resp.text
        assert "1 reunião(ões)" in resp.json()["detail"]
        assert _ids_no_banco(sb) == antes

    def test_serie_mista_apaga_so_as_ocorrencias_de_quem_pediu(self):
        """Roster desigual dentro da mesma serie: o delete carrega o mesmo escopo
        do select, senao a rota checaria o status das ocorrencias visiveis e
        apagaria as invisiveis junto."""
        sb = _cenario(DONA, TERCEIRO)

        resp = _apagar_serie(sb, DONA, SERIE_MISTA)

        assert resp.status_code == 200, resp.text
        assert "R_MISTA_DONA" not in _ids_no_banco(sb)
        assert "R_MISTA_TERCEIRO" in _ids_no_banco(sb), "o delete apagou ocorrencia fora do escopo de quem pediu"
