"""O Conector para a diretoria executiva: gate por ferramenta e pendências
(issue #1609, PRD #1571, ADR 0085, decisões 1 a 3).

Os seams testados são as duas portas de verdade:

- A rota do transporte (`POST /api/mcp`), com o gate de pé: o token do WorkOS
  assinado aqui contra um JWKS dublado (a trava de rede da suíte continua de
  pé) e o banco num dublê em memória. É por ela que o `tools/list` muda por
  pessoa, que a ferramenta fora do gate dá erro sem dado e que perder a
  `diretoria_executiva` corta a chamada seguinte.
- A rota da tela de Pendências (`GET /api/pendencias`), com o mesmo banco: a
  pendência que o Claude recebe como atrasada tem de ser a que a tela mostra
  como atrasada.

Nenhum arquivo de teste importa outro (regra das fatias da Central): as
pessoas e o gate zerado vêm do `central_de_comando_apoio`, e o token e o banco
dublado moram aqui.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from typing import Any

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from central_de_comando_apoio import FACILITADOR, SUPER_ADMIN, pessoa  # noqa: E402

from app.config import settings  # noqa: E402
from app.services.central_de_comando import conector_mcp  # noqa: E402

pytestmark = pytest.mark.usefixtures("gate_e_limitador_zerados", "mcp_configurado", "jwks_no_emissor")

EMISSOR = "https://hsm-teste.authkit.app"
RECURSO = "https://api.hsm-teste.cloud"
KID = "chave-de-teste-pendencias"
CAMINHO_MCP = f"{settings.api_prefix}/mcp"
FERRAMENTAS_DA_CENTRAL = {"get_active_now", "get_site_analytics", "get_instagram_analytics"}
FERRAMENTA_PENDENCIAS = "get_pendencias"


def diretoria(pid: str, access_profile: str | None) -> dict:
    """Quem tem `diretoria_executiva` no Perfil da Ouvidoria."""
    return pessoa(pid, access_profile) | {"perfil_ouvidoria": "diretoria_executiva"}


# A diretora sem Super admin (participante regular das Reuniões) e o diretor
# de hoje, que é as duas coisas.
DIRETORA = diretoria("diretora", "regular")
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
    def __init__(self, data: list, count: int | None = None):
        self.data = data
        self.count = count


_CONDICAO_DO_OR = re.compile(r"(\w+)\.(eq|in)\.(\([^)]*\)|[^,]+)")


class _Consulta:
    """O pedaço do cliente do PostgREST que as duas portas usam. Leitura filtra
    as linhas da tabela; escrita fica anotada no banco e não muda nada."""

    def __init__(self, banco: BancoFalso, nome: str):
        self._banco = banco
        self._nome = nome
        self._filtros: list = []
        self._ordem: str | None = None
        self._faixa: tuple[int, int] | None = None
        self._contar = False

    def _filtra(self, filtro) -> _Consulta:
        self._filtros.append(filtro)
        return self

    def select(self, _campos: str = "*", count: str | None = None) -> _Consulta:
        self._contar = count == "exact"
        return self

    def eq(self, coluna: str, valor: Any) -> _Consulta:
        return self._filtra(lambda r: r.get(coluna) == valor)

    def is_(self, coluna: str, valor: str) -> _Consulta:
        assert valor == "null"
        return self._filtra(lambda r: r.get(coluna) is None)

    def in_(self, coluna: str, valores) -> _Consulta:
        conjunto = set(valores)
        return self._filtra(lambda r: r.get(coluna) in conjunto)

    def gte(self, coluna: str, valor: str) -> _Consulta:
        return self._filtra(lambda r: r.get(coluna) is not None and str(r[coluna]) >= valor)

    def lte(self, coluna: str, valor: str) -> _Consulta:
        return self._filtra(lambda r: r.get(coluna) is not None and str(r[coluna]) <= valor)

    def ilike(self, coluna: str, padrao: str) -> _Consulta:
        trecho = padrao.strip("%").lower()
        return self._filtra(lambda r: trecho in (r.get(coluna) or "").lower())

    def or_(self, expressao: str) -> _Consulta:
        condicoes = []
        for coluna, op, valor in _CONDICAO_DO_OR.findall(expressao):
            if op == "in":
                conjunto = set(valor.strip("()").split(","))
                condicoes.append(lambda r, c=coluna, s=conjunto: r.get(c) in s)
            else:
                condicoes.append(lambda r, c=coluna, v=valor: r.get(c) == v)
        return self._filtra(lambda r: any(cond(r) for cond in condicoes))

    def order(self, coluna: str, desc: bool = False, nullsfirst: bool = False) -> _Consulta:
        assert not desc
        self._ordem = coluna
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
        total = len(linhas)
        if self._ordem:
            linhas.sort(key=lambda r: (r.get(self._ordem) is None, str(r.get(self._ordem) or "")))
        if self._faixa:
            linhas = linhas[self._faixa[0] : self._faixa[1] + 1]
        return _Resultado([dict(r) for r in linhas], total if self._contar else None)


class BancoFalso:
    def __init__(self, **tabelas: list[dict]):
        self.tabelas = tabelas
        self.escritas: list[tuple[str, str]] = []

    def table(self, nome: str) -> _Consulta:
        return _Consulta(self, nome)


def banco_com(*pessoas: dict, **tabelas: list[dict]) -> BancoFalso:
    return BancoFalso(participantes=list(pessoas), **tabelas)


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


def nomes_no_tools_list(cliente, chave, quem) -> set[str]:
    resposta = rpc(cliente, chave, quem, "tools/list")
    assert resposta.status_code == 200, resposta.text
    return {f["name"] for f in resposta.json()["result"]["tools"]}


def chamar_pendencias(cliente, chave, quem, **argumentos):
    return rpc(cliente, chave, quem, "tools/call", {"name": FERRAMENTA_PENDENCIAS, "arguments": argumentos})


# ─── 1. O gate por ferramenta ────────────────────────────────────────────────


class TestGatePorFerramenta:
    def test_super_admin_sem_diretoria_ve_so_a_central_e_nao_chama_pendencias(self, chave_do_emissor):
        banco = banco_com(SUPER_ADMIN, pendencias=[pendencia("A1", "ATRASADO")])
        cliente = cliente_mcp(banco)

        assert nomes_no_tools_list(cliente, chave_do_emissor, SUPER_ADMIN) == FERRAMENTAS_DA_CENTRAL

        resposta = chamar_pendencias(cliente, chave_do_emissor, SUPER_ADMIN)
        assert resposta.status_code == 200, resposta.text
        resultado = resposta.json()["result"]
        assert resultado["isError"] is True
        assert "structuredContent" not in resultado
        assert "A1" not in resposta.text

    def test_diretoria_sem_super_admin_ve_pendencias_e_nao_a_central(self, chave_do_emissor):
        cliente = cliente_mcp(banco_com(DIRETORA))

        assert nomes_no_tools_list(cliente, chave_do_emissor, DIRETORA) == {FERRAMENTA_PENDENCIAS}

        chamada = rpc(cliente, chave_do_emissor, DIRETORA, "tools/call", {"name": "get_active_now", "arguments": {}})
        assert chamada.json()["result"]["isError"] is True

    def test_diretor_que_e_super_admin_ve_as_quatro(self, chave_do_emissor):
        cliente = cliente_mcp(banco_com(DIRETOR_SUPER))

        assert nomes_no_tools_list(cliente, chave_do_emissor, DIRETOR_SUPER) == FERRAMENTAS_DA_CENTRAL | {
            FERRAMENTA_PENDENCIAS
        }

    def test_participante_sem_nenhum_dos_dois_recebe_401(self, chave_do_emissor):
        resposta = rpc(cliente_mcp(banco_com(FACILITADOR)), chave_do_emissor, FACILITADOR, "tools/list")

        assert resposta.status_code == 401
        assert "resource_metadata=" in resposta.headers["www-authenticate"]

    def test_retirar_a_diretoria_entre_duas_chamadas_corta_a_segunda(self, chave_do_emissor):
        diretora = diretoria("diretora", "regular")
        banco = banco_com(diretora, pendencias=[pendencia("A1", "ATRASADO")])
        cliente = cliente_mcp(banco)

        primeira = chamar_pendencias(cliente, chave_do_emissor, diretora)
        assert primeira.json()["result"]["isError"] is False

        diretora["perfil_ouvidoria"] = None
        segunda = chamar_pendencias(cliente, chave_do_emissor, diretora)

        assert segunda.status_code == 401
        assert "A1" not in segunda.text

    def test_super_admin_que_perde_a_diretoria_perde_so_as_pendencias(self, chave_do_emissor):
        diretor = diretoria("diretor", "super_admin")
        banco = banco_com(diretor, pendencias=[pendencia("A1", "ATRASADO")])
        cliente = cliente_mcp(banco)
        assert chamar_pendencias(cliente, chave_do_emissor, diretor).json()["result"]["isError"] is False

        diretor["perfil_ouvidoria"] = None
        segunda = chamar_pendencias(cliente, chave_do_emissor, diretor)

        assert segunda.json()["result"]["isError"] is True
        assert "A1" not in segunda.text


# ─── Dados de pendência ──────────────────────────────────────────────────────


def pendencia(
    id_acao: str,
    status: str,
    *,
    prazo: str | None = "2026-10-01",
    responsavel_id: str | None = "resp-ana",
    responsavel_nome: str | None = "Ana Souza",
    id_reuniao: str = "R1",
    deleted_at: str | None = None,
) -> dict:
    return {
        "id_acao": id_acao,
        "descricao_acao": f"Ação {id_acao}",
        "status": status,
        "prazo": prazo,
        "responsavel_id": responsavel_id,
        "responsavel_nome": responsavel_nome,
        "co_responsavel_id": None,
        "co_responsavel_nome": None,
        "cargo": None,
        "meta_entregavel": None,
        "id_reuniao": id_reuniao,
        "deleted_at": deleted_at,
    }
