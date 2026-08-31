"""Gate do router de participantes: dono ou papel, nunca "basta ter login" (issue #440).

Achado do code review de seguranca do PR #427. `participantes.py` e `aceite.py`
nao tinham dependency de router nenhuma, e `PATCH /participantes/{id}` exigia so
autenticacao: qualquer pessoa com login trocava o email do Super Admin, pedia
"esqueci minha senha" na caixa dela e assumia a conta.

Cada teste de recusa monta o ator com TODAS as outras portas abertas (ativo,
papel nas Reunioes, perfil de POPs, perfil de Ouvidoria, role de diretor) e so
fecha a porta que esta sendo testada. Sem isso o 403 poderia vir do gate errado
e o teste ficaria verde e vazio. Logo abaixo de cada recusa vem o controle
positivo com a MESMA fixture, provando que quem tem direito continua passando.

E o assert que importa nao e o status: e o efeito que NAO aconteceu. Na cadeia
de tomada de conta o que se afirma e que o email do alvo continua o mesmo na
tabela E que o Supabase Auth nunca foi tocado. Uma recusa tardia, depois da
sincronizacao do Auth, tambem devolveria 403 e passaria despercebida.
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
from app.routers import aceite as aceite_router  # noqa: E402
from app.routers import participantes as participantes_router  # noqa: E402


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

# Todas as portas abertas menos a que cada teste fecha: ativo, papel nas
# Reunioes, perfil de POPs, perfil de Ouvidoria e role de diretor.
ATACANTE: dict[str, Any] = {
    "id": "P_ATACANTE",
    "auth_user_id": "auth-atacante",
    "email": "atacante@hsm.com",
    "nome_completo": "Pessoa Qualquer",
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

ALVO: dict[str, Any] = {
    **ATACANTE,
    "id": "P_SUPER",
    "auth_user_id": "auth-super",
    "email": "diretoria@hsm.com",
    "nome_completo": "Super Admin do Hospital",
    "is_super_admin": True,
    "access_profile": "super_admin",
}


def _ator(base: dict, **mudancas) -> dict:
    return {**base, **mudancas}


# ─── Mock Supabase ────────────────────────────────────────────────────────────


class _Query:
    """select/insert/update com eq e in_, que e tudo que estas rotas usam."""

    def __init__(self, rows: list):
        self._rows = rows
        self._op = "select"
        self._payload: Any = None
        self._filtros_eq: list[tuple[str, Any]] = []
        self._filtros_in: list[tuple[str, list]] = []
        self._filtros_nao_nulo: list[str] = []
        self._negando = False

    def select(self, *_a, **_kw):
        self._op = "select"
        return self

    def update(self, payload):
        self._op = "update"
        self._payload = payload
        return self

    def eq(self, col, valor):
        self._filtros_eq.append((col, valor))
        return self

    def in_(self, col, valores):
        self._filtros_in.append((col, list(valores)))
        return self

    def is_(self, col, _valor):
        if self._negando:
            self._negando = False
            self._filtros_nao_nulo.append(col)
        else:
            self._filtros_eq.append((col, None))
        return self

    @property
    def not_(self):
        self._negando = True
        return self

    def ilike(self, *_a, **_kw):
        return self

    def order(self, *_a, **_kw):
        return self

    def range(self, *_a, **_kw):
        return self

    def execute(self):
        casadas = [
            r
            for r in self._rows
            if all(r.get(c) == v for c, v in self._filtros_eq)
            and all(r.get(c) in vals for c, vals in self._filtros_in)
            and all(r.get(c) is not None for c in self._filtros_nao_nulo)
        ]
        if self._op == "update":
            for row in casadas:
                row.update(self._payload or {})
        return type("_R", (), {"data": [dict(r) for r in casadas]})()


class _Supabase:
    def __init__(self, participantes: list):
        # A reuniao existe para que `/facilitadores` tenha o que devolver: sem
        # ela a rota responderia `[]` mesmo passando, e o assert de corpo dos
        # testes de recusa nao provaria nada.
        self.tabelas: dict[str, list] = {
            "participantes": participantes,
            "setores": [],
            "reunioes": [{"id_reuniao": "R1", "facilitador_id": ALVO["id"], "deleted_at": None}],
        }
        self.auth = MagicMock()
        self.auth.admin = MagicMock()
        self.auth.admin.update_user_by_id = MagicMock(return_value=None)

    def table(self, nome: str):
        return _Query(self.tabelas.setdefault(nome, []))


def _app(sb: _Supabase, logado_como: dict) -> TestClient:
    app = FastAPI()
    app.state.limiter = limiter
    app.include_router(participantes_router.router, prefix="/api")
    app.include_router(aceite_router.router, prefix="/api")
    app.dependency_overrides[get_supabase_client] = lambda: sb

    async def _fake_user() -> dict:
        return {"id": logado_como["auth_user_id"], "email": logado_como["email"], "metadata": {}}

    app.dependency_overrides[get_current_user] = _fake_user
    return TestClient(app)


def _cenario(*atores: dict) -> _Supabase:
    return _Supabase([dict(a) for a in atores])


def _linha(sb: _Supabase, participante_id: str) -> dict:
    return next(r for r in sb.tabelas["participantes"] if r["id"] == participante_id)


# ─── A cadeia de tomada de conta ──────────────────────────────────────────────


class TestTomadaDeConta:
    """O caminho inteiro descrito na issue #440, montado e provado que para."""

    def test_pessoa_qualquer_nao_troca_o_email_do_super_admin(self):
        sb = _cenario(ATACANTE, ALVO)
        resp = _app(sb, ATACANTE).patch(
            f"/api/participantes/{ALVO['id']}",
            json={"email": "atacante@dominio-dele.com"},
        )

        assert resp.status_code == 403, resp.text
        # O que importa: o "esqueci minha senha" do Super Admin continua caindo
        # na caixa dele. As duas pontas precisam estar intactas.
        assert _linha(sb, ALVO["id"])["email"] == "diretoria@hsm.com", "o gate recusou tarde: a tabela ja tinha mudado"
        sb.auth.admin.update_user_by_id.assert_not_called()

    def test_super_admin_continua_editando_terceiros(self):
        """Controle positivo com a MESMA fixture: quem tem papel passa. Sem
        isto, um 404 de rota errada faria o teste acima passar sozinho."""
        sb = _cenario(_ator(ALVO, id="P_DONO_DA_CASA"), ATACANTE)
        atuando_como = _linha(sb, "P_DONO_DA_CASA")
        resp = _app(sb, atuando_como).patch(
            f"/api/participantes/{ATACANTE['id']}",
            json={"email": "novo@hsm.com"},
        )

        assert resp.status_code == 200, resp.text
        assert _linha(sb, ATACANTE["id"])["email"] == "novo@hsm.com"
        sb.auth.admin.update_user_by_id.assert_called_once_with(
            "auth-atacante", {"email": "novo@hsm.com", "email_confirm": True}
        )

    def test_dono_continua_editando_o_proprio_cadastro(self):
        """O outro controle positivo: o gate e dono OU papel, nao so papel."""
        sb = _cenario(ATACANTE, ALVO)
        resp = _app(sb, ATACANTE).patch(
            f"/api/participantes/{ATACANTE['id']}",
            json={"email": "eu-mesma@hsm.com"},
        )

        assert resp.status_code == 200, resp.text
        assert _linha(sb, ATACANTE["id"])["email"] == "eu-mesma@hsm.com"

    def test_desligado_com_token_vivo_nao_edita_nem_o_proprio_cadastro(self):
        """O desligamento fecha a porta tambem aqui: `barrar_desligado` chega
        ao router que ate agora nao tinha gate nenhum."""
        desligado = _ator(ATACANTE, ativo=False)
        sb = _cenario(desligado, ALVO)
        resp = _app(sb, desligado).patch(
            f"/api/participantes/{desligado['id']}",
            json={"email": "ainda-eu@hsm.com"},
        )

        assert resp.status_code == 403, resp.text
        assert _linha(sb, desligado["id"])["email"] == "atacante@hsm.com"
        sb.auth.admin.update_user_by_id.assert_not_called()

    def test_token_orfao_nao_edita_ninguem(self):
        """Sem linha em `participantes`, nao ha dono nem papel: recusa. O gate
        de contexto deixa `me=None` passar de proposito; o de escrita nao."""
        orfao = {"auth_user_id": "auth-fantasma", "email": "fantasma@hsm.com"}
        sb = _cenario(ALVO)
        resp = _app(sb, orfao).patch(
            f"/api/participantes/{ALVO['id']}",
            json={"email": "fantasma@dominio-dele.com"},
        )

        assert resp.status_code == 403, resp.text
        assert _linha(sb, ALVO["id"])["email"] == "diretoria@hsm.com"
        sb.auth.admin.update_user_by_id.assert_not_called()


# ─── As leituras do mesmo router ──────────────────────────────────────────────

# (metodo, caminho) das rotas que passaram a exigir papel nas Reunioes.
ROTAS_DE_REUNIOES = [
    ("get", "/api/participantes?ativo=true&limit=50"),
    ("get", "/api/participantes/facilitadores"),
    ("get", f"/api/participantes/{ALVO['id']}"),
]

IDS_REUNIOES = ["listar", "facilitadores", "detalhe"]


@pytest.mark.parametrize("metodo,caminho", ROTAS_DE_REUNIOES, ids=IDS_REUNIOES)
def test_sem_papel_nas_reunioes_nao_le_o_diretorio(metodo, caminho):
    """`access_profile = None` e quem ganhou login por outro contexto (POPs,
    Ouvidoria). O diretorio do hospital com nome, email, cargo e setor de
    terceiros nao e dado desse contexto."""
    sem_papel = _ator(ATACANTE, access_profile=None)
    sb = _cenario(sem_papel, ALVO)
    resp = getattr(_app(sb, sem_papel), metodo)(caminho)

    assert resp.status_code == 403, resp.text


@pytest.mark.parametrize("metodo,caminho", ROTAS_DE_REUNIOES, ids=IDS_REUNIOES)
def test_com_papel_nas_reunioes_continua_lendo(metodo, caminho):
    """Controle positivo: a MESMA fixture com `access_profile` preenchido
    atravessa. E o que impede o gate de fechar a tela do calendario.

    O assert do corpo e o que tira o vacuo dos testes de recusa: aqui o dado do
    terceiro SAI nas tres rotas, entao a ausencia dele la e recusa de verdade,
    nao resposta vazia por falta de dado na fixture."""
    sb = _cenario(ATACANTE, ALVO)
    resp = getattr(_app(sb, ATACANTE), metodo)(caminho)

    assert resp.status_code == 200, resp.text
    assert ALVO["nome_completo"] in resp.text


def _corpo_sem_terceiro(resp) -> None:
    """O assert que importa nas leituras: o dado de terceiro nao saiu no corpo.

    Status 403 sozinho nao prova nada: uma rota que respondesse 200 com o
    diretorio e outra que respondesse 403 depois de montar a lista dariam a
    mesma cara em log. Aqui se olha o corpo inteiro, serializado.
    """
    assert ALVO["email"] not in resp.text, "o email do Super Admin vazou no corpo"
    assert ALVO["nome_completo"] not in resp.text, "o nome do Super Admin vazou no corpo"


@pytest.mark.parametrize("metodo,caminho", ROTAS_DE_REUNIOES, ids=IDS_REUNIOES)
def test_token_orfao_nao_le_o_diretorio(metodo, caminho):
    """Token valido do Supabase Auth sem linha em `participantes`.

    E o furo que `require_acesso_reunioes` deixaria aberto: ela solta `me=None`
    de proposito, porque as rotas dos routers que a usam devolvem 404 ou lista
    vazia nesse caso. As daqui nao: `GET ""` devolveria o diretorio inteiro.
    E o orfao nao e hipotetico, o hard delete e a RPC de merge apagam o vinculo
    e deixam a conta autenticando no GoTrue.
    """
    orfao = {"auth_user_id": "auth-fantasma", "email": "fantasma@hsm.com"}
    sb = _cenario(ALVO)
    resp = getattr(_app(sb, orfao), metodo)(caminho)

    assert resp.status_code == 403, resp.text
    _corpo_sem_terceiro(resp)


@pytest.mark.parametrize("metodo,caminho", ROTAS_DE_REUNIOES, ids=IDS_REUNIOES)
def test_desligado_com_token_vivo_nao_le_o_diretorio(metodo, caminho):
    """A sessao do Supabase Auth sobrevive ao desligamento (issue #415). Quem
    saiu do hospital nao leva o diretorio junto enquanto o token dura."""
    desligado = _ator(ATACANTE, ativo=False)
    sb = _cenario(desligado, ALVO)
    resp = getattr(_app(sb, desligado), metodo)(caminho)

    assert resp.status_code == 403, resp.text
    _corpo_sem_terceiro(resp)


@pytest.mark.parametrize("metodo,caminho", ROTAS_DE_REUNIOES, ids=IDS_REUNIOES)
def test_sem_papel_nas_reunioes_nao_vaza_o_terceiro_no_corpo(metodo, caminho):
    """O par do teste de status logo acima, olhando o corpo em vez do numero."""
    sem_papel = _ator(ATACANTE, access_profile=None)
    sb = _cenario(sem_papel, ALVO)
    resp = getattr(_app(sb, sem_papel), metodo)(caminho)

    assert resp.status_code == 403, resp.text
    _corpo_sem_terceiro(resp)


# As rotas que ficam abertas a qualquer pessoa logada, de proposito: `/me` e a
# propria pessoa, e `/cargos` e `/setores` sao listas canonicas do organograma
# que POPs e Ouvidoria consomem sem ter papel nas Reunioes. Fechar aqui derruba
# tela em producao sem fechar buraco nenhum.
ROTAS_ABERTAS = ["/api/participantes/me", "/api/participantes/cargos", "/api/participantes/setores"]


@pytest.mark.parametrize("caminho", ROTAS_ABERTAS)
def test_rotas_transversais_continuam_abertas_a_quem_tem_login(caminho):
    sem_papel = _ator(ATACANTE, access_profile=None)
    sb = _cenario(sem_papel, ALVO)
    resp = _app(sb, sem_papel).get(caminho)

    assert resp.status_code == 200, resp.text


# ─── A criacao, que provisiona conta de login ─────────────────────────────────


class TestCriacaoDeParticipante:
    """`POST /participantes` cria a pessoa E provisiona o login dela. Mesma
    autoridade que desliga (`DELETE`, `require_role("diretor", "gerente")`)."""

    _CORPO = {"nome_completo": "Pessoa Nova", "email": "nova@hsm.com", "cargo": "Coordenador"}

    def test_sem_papel_de_diretor_ou_gerente_nao_provisiona_login(self, monkeypatch):
        from app.services import auth_provisioning

        # O retorno precisa ser o par que a rota desempacota. Com um MagicMock
        # cru, tirar o gate daria 500 de mock mal montado em vez de 201, e o
        # mutante morreria pelo motivo errado: verde falso disfarçado de vermelho.
        criada = {**ATACANTE, "id": "P_NOVA", "email": "nova@hsm.com", "nome_completo": "Pessoa Nova"}
        provisionou = MagicMock(return_value=(criada, "auth-nova"))
        monkeypatch.setattr(auth_provisioning, "provision_with_compensation", provisionou)

        coordenadora = _ator(ATACANTE, role="coordenador")
        sb = _cenario(coordenadora)
        resp = _app(sb, coordenadora).post("/api/participantes", json=self._CORPO)

        assert resp.status_code == 403, resp.text
        provisionou.assert_not_called()
        assert len(sb.tabelas["participantes"]) == 1, "criou a linha antes de recusar"

    def test_diretor_continua_criando(self, monkeypatch):
        from app.services import auth_provisioning

        criada = {**ATACANTE, "id": "P_NOVA", "email": "nova@hsm.com", "nome_completo": "Pessoa Nova"}
        monkeypatch.setattr(
            auth_provisioning,
            "provision_with_compensation",
            MagicMock(return_value=(criada, "auth-nova")),
        )

        sb = _cenario(ATACANTE)  # role "diretor"
        resp = _app(sb, ATACANTE).post("/api/participantes", json=self._CORPO)

        assert resp.status_code == 201, resp.text
        assert resp.json()["email"] == "nova@hsm.com"


# ─── aceite.py: a decisao escrita ─────────────────────────────────────────────


class TestAceiteMeuLink:
    """`POST /aceite/meu-link` ja autorizava pelo par (Reuniao, signatario);
    o que faltava era `barrar_desligado`. As duas rotas publicas de `/aceite`
    continuam publicas: o token opaco de uso unico e a credencial (ADR 0030)."""

    def test_desligado_nao_reemite_o_proprio_link(self, monkeypatch):
        from app.services import aceite_service

        reemitiu = MagicMock()
        monkeypatch.setattr(aceite_service, "reemitir_link_aceite_interno", reemitiu)

        desligado = _ator(ATACANTE, ativo=False)
        sb = _cenario(desligado)
        resp = _app(sb, desligado).post("/api/aceite/meu-link", json={"id_reuniao": "R1"})

        assert resp.status_code == 403, resp.text
        reemitiu.assert_not_called()

    def test_a_mesma_pessoa_ativa_reemite(self, monkeypatch):
        from app.services import aceite_service

        monkeypatch.setattr(aceite_service, "reemitir_link_aceite_interno", MagicMock(return_value="tok-novo"))

        sb = _cenario(ATACANTE)
        resp = _app(sb, ATACANTE).post("/api/aceite/meu-link", json={"id_reuniao": "R1"})

        assert resp.status_code == 200, resp.text
        assert resp.json()["url"] == "/aceite/tok-novo"

    def test_a_pagina_publica_continua_publica(self, monkeypatch):
        """Controle da decisao escrita: um gate no router de `/aceite` fecharia
        a pagina do signatario que nao tem login, que e o ponto dela."""
        from app.services import aceite_service

        monkeypatch.setattr(
            aceite_service,
            "consultar_aceite_interno",
            MagicMock(return_value={"reuniao": {}, "signatario": {}}),
        )

        app = FastAPI()
        app.state.limiter = limiter
        app.include_router(aceite_router.router, prefix="/api")
        app.dependency_overrides[get_supabase_client] = lambda: _cenario()
        resp = TestClient(app).get("/api/aceite/um-token-qualquer")

        assert resp.status_code == 200, resp.text
