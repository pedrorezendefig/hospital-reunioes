"""O Conector para a diretoria executiva: casos da Ouvidoria com prazo
estourado por setor (issue #1611, PRD #1571, ADR 0085, decisões 1 a 3 e 5).

Os seams testados são as duas portas de verdade:

- A rota do transporte (`POST /api/mcp`), com o gate de pé: o token do WorkOS
  assinado aqui contra um JWKS dublado (a trava de rede da suíte continua de
  pé) e o banco num dublê em memória.
- A rota da fila da Ouvidoria (`GET /api/ouvidoria/protocolos`), com o mesmo
  banco: o caso que o Claude recebe como estourado tem de ser o que a fila
  pinta de estourado, pela regra da tela (`classificarPrazoDaManifestacao`, em
  `frontend/src/lib/ouvidoria/prazo.ts`), transcrita aqui em
  `estourado_na_tela`.

Nenhum arquivo de teste importa outro (regra das fatias da Central): as
pessoas e o gate zerado vêm do `central_de_comando_apoio`, e o token e o banco
dublado moram aqui.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
import time
from typing import Any
from zoneinfo import ZoneInfo

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from central_de_comando_apoio import SUPER_ADMIN, pessoa  # noqa: E402

from app.config import settings  # noqa: E402
from app.services.central_de_comando import conector_mcp  # noqa: E402

pytestmark = pytest.mark.usefixtures("gate_e_limitador_zerados", "mcp_configurado", "jwks_no_emissor", "relogio_parado")

EMISSOR = "https://hsm-teste.authkit.app"
RECURSO = "https://api.hsm-teste.cloud"
KID = "chave-de-teste-ouvidoria-prazo"
CAMINHO_MCP = f"{settings.api_prefix}/mcp"
FERRAMENTA = "get_ouvidoria_prazo_estourado"

# Terça-feira, 14h de Brasília: dentro do expediente e longe de feriado.
AGORA = dt.datetime(2026, 8, 25, 17, 0, tzinfo=dt.UTC)
HOJE = "2026-08-25"
FUSO = ZoneInfo("America/Sao_Paulo")


def diretoria(pid: str, access_profile: str | None) -> dict:
    """Quem tem `diretoria_executiva` no Perfil da Ouvidoria."""
    return pessoa(pid, access_profile) | {"perfil_ouvidoria": "diretoria_executiva"}


DIRETORA = diretoria("diretora", None)
DIRETOR_SUPER = diretoria("diretor", "super_admin")


# ─── O WorkOS de mentira: chave, JWKS e token assinados aqui ─────────────────


@pytest.fixture(scope="module")
def chave_do_emissor() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def mcp_configurado(monkeypatch):
    monkeypatch.setattr(settings, "mcp_auth_issuer", EMISSOR)
    monkeypatch.setattr(settings, "mcp_resource_url", RECURSO)
    monkeypatch.setattr(settings, "mcp_auth_jwks_uri", "")
    monkeypatch.setattr(settings, "mcp_clientes_permitidos", "")


@pytest.fixture
def jwks_no_emissor(monkeypatch, chave_do_emissor):
    """Dubla a única ida de rede do gate: o JWKS do emissor."""
    jwk = json.loads(pyjwt.algorithms.RSAAlgorithm.to_jwk(chave_do_emissor.public_key()))
    jwk.update({"kid": KID, "use": "sig", "alg": "RS256"})
    conector_mcp._jwks_cache.clear()
    conector_mcp._jwks_falha_ate.clear()
    monkeypatch.setattr(conector_mcp, "_buscar_jwks", lambda _uri: {"keys": [jwk]})
    yield
    conector_mcp._jwks_cache.clear()
    conector_mcp._jwks_falha_ate.clear()


@pytest.fixture
def relogio_parado(monkeypatch):
    """O relógio da Ouvidoria parado em `AGORA`, para a fila e o Claude medirem
    o prazo no mesmo instante que o teste."""
    from app.routers import ouvidoria

    monkeypatch.setattr(ouvidoria, "agora_utc", lambda: AGORA)


def token_de(chave: rsa.RSAPrivateKey, quem: dict) -> str:
    agora = int(time.time())
    claims = {
        "sub": f"user_{quem['id']}",
        "iat": agora,
        "exp": agora + 3600,
        "iss": EMISSOR,
        "aud": RECURSO,
        "email": quem["email"],
        "email_verified": True,
        "client_id": conector_mcp.CLIENTES_PADRAO[0],
    }
    pem = chave.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()
    return pyjwt.encode(claims, pem, algorithm="RS256", headers={"kid": KID})


# ─── O banco de mentira ──────────────────────────────────────────────────────


class _Resultado:
    def __init__(self, data: list):
        self.data = data
        self.count = None


class _Consulta:
    """O pedaço do cliente do PostgREST que as duas portas usam. Leitura filtra
    as linhas da tabela; escrita fica anotada no banco e não muda nada."""

    def __init__(self, banco: BancoFalso, nome: str):
        self._banco = banco
        self._nome = nome
        self._filtros: list = []
        self._ordem: tuple[str, bool] | None = None
        self._faixa: tuple[int, int] | None = None
        self._negar = False

    @property
    def not_(self) -> _Consulta:
        self._negar = True
        return self

    def _filtra(self, teste) -> _Consulta:
        negado, self._negar = self._negar, False
        self._filtros.append((lambda r: not teste(r)) if negado else teste)
        return self

    def select(self, *_a, **_kw) -> _Consulta:
        return self

    def eq(self, coluna: str, valor: Any) -> _Consulta:
        return self._filtra(lambda r: r.get(coluna) == valor)

    def is_(self, coluna: str, valor: str) -> _Consulta:
        assert valor == "null"
        return self._filtra(lambda r: r.get(coluna) is None)

    def order(self, coluna: str, desc: bool = False, **_kw) -> _Consulta:
        self._ordem = (coluna, desc)
        return self

    def range(self, inicio: int, fim: int) -> _Consulta:
        self._faixa = (inicio, fim)
        return self

    def _escreve(self, metodo: str, *_a, **_kw) -> _Consulta:
        self._banco.escritas.append((self._nome, metodo))
        return self

    def update(self, *a, **kw) -> _Consulta:
        return self._escreve("update", *a, **kw)

    def insert(self, *a, **kw) -> _Consulta:
        return self._escreve("insert", *a, **kw)

    def upsert(self, *a, **kw) -> _Consulta:
        return self._escreve("upsert", *a, **kw)

    def delete(self, *a, **kw) -> _Consulta:
        return self._escreve("delete", *a, **kw)

    def execute(self) -> _Resultado:
        linhas = [r for r in self._banco.tabelas.get(self._nome, []) if all(f(r) for f in self._filtros)]
        if self._ordem:
            coluna, desc = self._ordem
            linhas.sort(key=lambda r: str(r.get(coluna) if r.get(coluna) is not None else ""), reverse=desc)
        if self._faixa:
            linhas = linhas[self._faixa[0] : self._faixa[1] + 1]
        return _Resultado([dict(r) for r in linhas])


class _Rpc:
    """A função do PostgREST. Só a do último movimento (leitura da fila) é
    conhecida; qualquer outra fica anotada como escrita."""

    def __init__(self, banco: BancoFalso, nome: str):
        if nome != "ouvidoria_ultimo_movimento":
            banco.escritas.append((nome, "rpc"))

    def order(self, *_a, **_kw) -> _Rpc:
        return self

    def range(self, *_a) -> _Rpc:
        return self

    def execute(self) -> _Resultado:
        return _Resultado([])


class BancoFalso:
    def __init__(self, **tabelas: list[dict]):
        self.tabelas = tabelas
        self.escritas: list[tuple[str, str]] = []

    def table(self, nome: str) -> _Consulta:
        return _Consulta(self, nome)

    def rpc(self, nome: str, _params: dict | None = None) -> _Rpc:
        return _Rpc(self, nome)


# ─── Os casos da Ouvidoria ───────────────────────────────────────────────────


def caso(numero: int, status: str, setor: str, **campos) -> dict:
    """Uma linha de `ouvidoria_protocolos` com as colunas que a fila lê."""
    linha = {
        "id": f"uuid-{numero}",
        "numero": numero,
        "protocolo": f"2026-{numero:04d}",
        "data_abertura": "2026-08-14",
        "prazo_resposta": "2026-08-21",
        "status": status,
        "categoria": "Demora",
        "setor": setor,
        "resumo": "Espera longa.",
        "conversa_id": None,
        "tipo_manifestacao": "reclamacao",
        "sigilo_reforcado": False,
        "gravidade": "medio",
        "prazo_area_em": None,
        "respondida_em": None,
        "minutos_pausados": 0,
        "desfecho": None,
        "pausada_em": None,
        "area_estourou_em": None,
        "encerramento_sem_contato_em": None,
        "anonimo": False,
        "vista_pela_ouvidoria_em": None,
        "arquivada_em": None,
    }
    return linha | campos


RECEPCAO = "Recepção"
MATERNIDADE = "Maternidade"

CASOS = [
    # Na área, vencido ontem.
    caso(1, "aguardando_area", RECEPCAO, prazo_area_em="2026-08-24T20:00:00+00:00"),
    # Outro setor, vencido.
    caso(2, "aguardando_area", MATERNIDADE, prazo_area_em="2026-08-20T20:00:00+00:00"),
    # Na área, vence sexta.
    caso(3, "aguardando_area", RECEPCAO, prazo_area_em="2026-08-28T20:00:00+00:00"),
    # A área respondeu depois do vencimento: saiu do relógio, a fila não pinta.
    caso(
        4,
        "respondido",
        RECEPCAO,
        prazo_area_em="2026-08-21T20:00:00+00:00",
        respondida_em="2026-08-22T12:00:00+00:00",
    ),
    # Elogio não vence (ADR 0088), nem com o prazo de referência passado.
    caso(5, "aguardando_area", RECEPCAO, tipo_manifestacao="elogio", prazo_resposta="2026-08-18"),
    # Sem gravidade ainda: o prazo de referência da fundação já passou.
    caso(6, "novo", RECEPCAO, prazo_resposta="2026-08-20"),
    # Sem gravidade, prazo de referência adiante.
    caso(7, "novo", RECEPCAO, prazo_resposta="2026-08-30"),
    # Parado aguardando o manifestante: o relógio da área não corre.
    caso(
        8,
        "aguardando_manifestante",
        RECEPCAO,
        prazo_area_em="2026-08-21T20:00:00+00:00",
        pausada_em="2026-08-19T12:00:00+00:00",
    ),
    # Arquivado: fora da fila de trabalho.
    caso(
        9,
        "encerrado",
        RECEPCAO,
        prazo_area_em="2026-08-21T20:00:00+00:00",
        arquivada_em="2026-08-24T12:00:00+00:00",
    ),
    # Sigiloso, vencido hoje às 10h: a diretoria executiva o vê na fila.
    caso(10, "aguardando_area", RECEPCAO, sigilo_reforcado=True, prazo_area_em="2026-08-25T13:00:00+00:00"),
]


def banco_da_ouvidoria(*quem: dict, casos: list[dict] | None = None) -> BancoFalso:
    return BancoFalso(
        participantes=list(quem),
        ouvidoria_protocolos=[dict(c) for c in (CASOS if casos is None else casos)],
        ouvidoria_feriados=[],
        ouvidoria_acessos=[],
        ouvidoria_movimentos=[],
    )


# ─── As portas de verdade ────────────────────────────────────────────────────


def cliente_mcp(banco: BancoFalso) -> TestClient:
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded

    from app.dependencies import get_supabase_client
    from app.limiter import limiter
    from app.routers import conector_mcp as router_mcp

    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(router_mcp.router)
    app.dependency_overrides[get_supabase_client] = lambda: banco
    return TestClient(app)


def rpc(cliente: TestClient, chave, quem: dict, metodo: str, params: dict | None = None):
    corpo: dict = {"jsonrpc": "2.0", "id": 1, "method": metodo}
    if params is not None:
        corpo["params"] = params
    return cliente.post(CAMINHO_MCP, json=corpo, headers={"Authorization": f"Bearer {token_de(chave, quem)}"})


def chamar(cliente, chave, quem, **argumentos):
    return rpc(cliente, chave, quem, "tools/call", {"name": FERRAMENTA, "arguments": argumentos})


def casos_do_claude(banco: BancoFalso, chave, quem: dict, **argumentos) -> dict:
    resposta = chamar(cliente_mcp(banco), chave, quem, **argumentos)
    assert resposta.status_code == 200, resposta.text
    resultado = resposta.json()["result"]
    assert resultado["isError"] is False, resultado
    return resultado["structuredContent"]


def fila_da_ouvidoria(banco: BancoFalso, quem: dict) -> list[dict]:
    """O que a fila da Ouvidoria recebe: o `GET /api/ouvidoria/protocolos` de
    verdade, a lista de trabalho, como a tela pede."""
    from app.dependencies import _participante_ctx, get_current_user, get_supabase_client
    from app.limiter import limiter
    from app.routers import ouvidoria as router_ouvidoria

    _participante_ctx.set(None)
    app = FastAPI()
    app.state.limiter = limiter
    app.include_router(router_ouvidoria.router, prefix="/api")
    app.dependency_overrides[get_supabase_client] = lambda: banco

    async def _usuario() -> dict[str, Any]:
        return {"id": quem["auth_user_id"], "email": quem["email"], "metadata": {}}

    app.dependency_overrides[get_current_user] = _usuario
    resposta = TestClient(app).get("/api/ouvidoria/protocolos")
    assert resposta.status_code == 200, resposta.text
    _participante_ctx.set(None)
    return resposta.json()["protocolos"]


def estourado_na_tela(m: dict, hoje: str) -> bool:
    """A regra da fila na tela: `classificarPrazoDaManifestacao(m, hoje) ===
    "estourado"`, de `frontend/src/lib/ouvidoria/prazo.ts`, transcrita."""
    if m["status"] not in ("novo", "em_classificacao", "aguardando_area"):
        return False
    if m.get("tipo_manifestacao") == "elogio":
        return False
    if not m["prazo_area_em"]:
        return m["prazo_resposta"] < hoje
    dia = dt.datetime.fromisoformat(m["prazo_area_em"]).astimezone(FUSO).date().isoformat()
    return m["prazo_estourado"] or dia < hoje


# ─── 1. Prazo estourado e setor, iguais aos da fila ──────────────────────────


class TestPrazoEstouradoComoNaFila:
    def test_diretoria_filtra_estourados_do_setor_e_recebe_os_mesmos_casos_da_fila(self, chave_do_emissor):
        banco = banco_da_ouvidoria(DIRETORA)

        na_fila = {
            m["protocolo"]
            for m in fila_da_ouvidoria(banco, DIRETORA)
            if estourado_na_tela(m, HOJE) and m["setor"] == RECEPCAO
        }
        payload = casos_do_claude(banco, chave_do_emissor, DIRETORA, prazoEstourado=True, setor=RECEPCAO)
        no_claude = {c["protocolo"] for c in payload["casos"]}

        assert no_claude == na_fila
        assert no_claude == {"2026-0001", "2026-0006", "2026-0010"}
        assert payload["total"] == 3
        assert payload["haMais"] is False

    @pytest.mark.parametrize("quem", [DIRETOR_SUPER, DIRETORA], ids=["diretor-super-admin", "diretora"])
    def test_sem_filtro_de_setor_os_estourados_e_os_em_dia_batem_com_a_fila(self, chave_do_emissor, quem):
        banco = banco_da_ouvidoria(quem)
        fila = fila_da_ouvidoria(banco, quem)

        for estourado in (True, False):
            na_fila = {m["protocolo"] for m in fila if estourado_na_tela(m, HOJE) is estourado}
            payload = casos_do_claude(banco, chave_do_emissor, quem, prazoEstourado=estourado)
            assert {c["protocolo"] for c in payload["casos"]} == na_fila
            assert all(c["prazoEstourado"] is estourado for c in payload["casos"])

        estourados = casos_do_claude(banco, chave_do_emissor, quem, prazoEstourado=True)
        assert {c["protocolo"] for c in estourados["casos"]} == {"2026-0001", "2026-0002", "2026-0006", "2026-0010"}

    def test_cada_caso_traz_protocolo_setor_situacao_gravidade_e_prazo(self, chave_do_emissor):
        payload = casos_do_claude(banco_da_ouvidoria(DIRETORA), chave_do_emissor, DIRETORA, setor="materni")

        rotulo = payload["casos"][0]["rotuloPrazo"]
        assert rotulo.startswith("vencido há")
        assert payload["casos"] == [
            {
                "protocolo": "2026-0002",
                "setor": MATERNIDADE,
                "situacao": "aguardando_area",
                "gravidade": "medio",
                "tipo": "reclamacao",
                "vencimento": "20/08/2026 às 17h00",
                "rotuloPrazo": rotulo,
                "prazoDeReferencia": "2026-08-21",
                "prazoEstourado": True,
            }
        ]

    def test_filtra_por_situacao(self, chave_do_emissor):
        payload = casos_do_claude(banco_da_ouvidoria(DIRETORA), chave_do_emissor, DIRETORA, situacao="novo")

        assert [c["protocolo"] for c in payload["casos"]] == ["2026-0006", "2026-0007"]

    @pytest.mark.parametrize(
        "argumentos",
        [{"prazoEstourado": "sim"}, {"situacao": "vencido"}, {"situacao": ["novo"]}, {"setor": ""}, {"setor": 3}],
        ids=["estourado-texto", "situacao-desconhecida", "situacao-lista", "setor-vazio", "setor-numero"],
    )
    def test_argumento_invalido_e_erro_de_ferramenta_sem_dado(self, chave_do_emissor, argumentos):
        resposta = chamar(cliente_mcp(banco_da_ouvidoria(DIRETORA)), chave_do_emissor, DIRETORA, **argumentos)

        assert resposta.status_code == 200, resposta.text
        resultado = resposta.json()["result"]
        assert resultado["isError"] is True
        assert "2026-0001" not in resposta.text


# ─── 2. O gate: só a diretoria executiva ─────────────────────────────────────


class TestGate:
    def test_super_admin_sem_diretoria_nao_ve_a_ferramenta_e_chamar_e_erro_sem_dado(self, chave_do_emissor):
        cliente = cliente_mcp(banco_da_ouvidoria(SUPER_ADMIN))

        lista = rpc(cliente, chave_do_emissor, SUPER_ADMIN, "tools/list")
        assert lista.status_code == 200, lista.text
        nomes = {f["name"] for f in lista.json()["result"]["tools"]}
        assert "get_active_now" in nomes
        assert FERRAMENTA not in nomes

        resposta = chamar(cliente, chave_do_emissor, SUPER_ADMIN, prazoEstourado=True)
        assert resposta.status_code == 200, resposta.text
        resultado = resposta.json()["result"]
        assert resultado["isError"] is True
        assert "structuredContent" not in resultado
        assert "2026-0001" not in resposta.text

    def test_diretoria_ve_a_ferramenta_no_tools_list(self, chave_do_emissor):
        lista = rpc(cliente_mcp(banco_da_ouvidoria(DIRETORA)), chave_do_emissor, DIRETORA, "tools/list")

        assert FERRAMENTA in {f["name"] for f in lista.json()["result"]["tools"]}


# ─── 3. Lista não grava acesso; 4. só leitura ────────────────────────────────

_PEDIDOS = ({}, {"prazoEstourado": True}, {"prazoEstourado": True, "setor": RECEPCAO}, {"situacao": "respondido"})


class TestSoLeitura:
    def test_chamar_a_ferramenta_nao_grava_linha_em_ouvidoria_acessos(self, chave_do_emissor):
        banco = banco_da_ouvidoria(DIRETORA)
        cliente = cliente_mcp(banco)

        for argumentos in _PEDIDOS:
            assert chamar(cliente, chave_do_emissor, DIRETORA, **argumentos).json()["result"]["isError"] is False

        assert banco.tabelas["ouvidoria_acessos"] == []
        assert [e for e in banco.escritas if e[0] == "ouvidoria_acessos"] == []

    def test_a_ferramenta_nao_escreve_em_caso_nem_em_trilha(self, chave_do_emissor):
        banco = banco_da_ouvidoria(DIRETOR_SUPER, DIRETORA)
        cliente = cliente_mcp(banco)

        for quem in (DIRETOR_SUPER, DIRETORA):
            for argumentos in _PEDIDOS:
                assert chamar(cliente, chave_do_emissor, quem, **argumentos).json()["result"]["isError"] is False

        assert banco.escritas == []
        assert banco.tabelas["ouvidoria_protocolos"] == CASOS
        assert banco.tabelas["ouvidoria_movimentos"] == []


# ─── Lista longa ─────────────────────────────────────────────────────────────


class TestListaLongaCortadaNoTeto:
    def test_volta_o_teto_com_o_total_e_o_aviso_o_mais_antigo_primeiro(self, chave_do_emissor):
        muitos = [
            caso(100 + i, "aguardando_area", RECEPCAO, prazo_area_em=f"2026-08-{1 + i % 20:02d}T20:00:00+00:00")
            for i in range(60)
        ]
        banco = banco_da_ouvidoria(DIRETORA, casos=muitos)

        payload = casos_do_claude(banco, chave_do_emissor, DIRETORA, prazoEstourado=True)

        assert payload["total"] == 60
        assert payload["mostrados"] == 50
        assert len(payload["casos"]) == 50
        assert payload["haMais"] is True
        assert "60" in payload["aviso"]
        dias = [c["vencimento"][:2] for c in payload["casos"]]
        assert dias == sorted(dias)
        assert dias[0] == "01"
