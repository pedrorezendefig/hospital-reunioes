"""O Conector para a diretoria executiva: a ferramenta de Reuniões (issue
#1610, PRD #1571, ADR 0085, decisões 1 a 3).

Os seams testados são as portas de verdade:

- A rota do transporte (`POST /api/mcp`), com o gate de pé: o token do WorkOS
  assinado aqui contra um JWKS dublado (a trava de rede da suíte continua de
  pé) e o banco num dublê em memória.
- A rota da tela de Pendências (`GET /api/pendencias?id_reuniao=...`), com o
  mesmo banco: a situação de cada pendência que o Claude recebe tem de ser a
  que a tela mostra.

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

from central_de_comando_apoio import SUPER_ADMIN, pessoa  # noqa: E402

from app.config import settings  # noqa: E402
from app.services.central_de_comando import conector_mcp  # noqa: E402

pytestmark = pytest.mark.usefixtures("gate_e_limitador_zerados", "mcp_configurado", "jwks_no_emissor")

EMISSOR = "https://hsm-teste.authkit.app"
RECURSO = "https://api.hsm-teste.cloud"
KID = "chave-de-teste-reunioes"
CAMINHO_MCP = f"{settings.api_prefix}/mcp"
FERRAMENTA_REUNIOES = "get_reunioes"


def diretoria(pid: str, access_profile: str | None) -> dict:
    """Quem tem `diretoria_executiva` no Perfil da Ouvidoria."""
    return pessoa(pid, access_profile) | {"perfil_ouvidoria": "diretoria_executiva"}


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


_CONDICAO_DO_OR = re.compile(r"([\w>-]+)\.(eq|in|ilike)\.(\([^)]*\)|[^,]+)")


def _valor(linha: dict, coluna: str) -> Any:
    """O valor da coluna, inclusive o caminho `json->>campo` do PostgREST."""
    if "->>" in coluna:
        raiz, campo = coluna.split("->>", 1)
        return (linha.get(raiz) or {}).get(campo)
    return linha.get(coluna)


def _casa_ilike(valor: Any, padrao: str) -> bool:
    trecho = padrao.strip("%*").lower()
    return isinstance(valor, str) and trecho in valor.lower()


class _Consulta:
    """O pedaço do cliente do PostgREST que as portas usam. Leitura filtra as
    linhas da tabela; escrita fica anotada no banco e não muda nada."""

    def __init__(self, banco: BancoFalso, nome: str):
        self._banco = banco
        self._nome = nome
        self._filtros: list = []
        self._ordem: tuple[str, bool] | None = None
        self._faixa: tuple[int, int] | None = None
        self._contar = False

    def _filtra(self, filtro) -> _Consulta:
        self._filtros.append(filtro)
        return self

    def select(self, _campos: str = "*", count: str | None = None) -> _Consulta:
        self._contar = count == "exact"
        return self

    def eq(self, coluna: str, valor: Any) -> _Consulta:
        return self._filtra(lambda r: _valor(r, coluna) == valor)

    def neq(self, coluna: str, valor: Any) -> _Consulta:
        return self._filtra(lambda r: _valor(r, coluna) != valor)

    def is_(self, coluna: str, valor: str) -> _Consulta:
        assert valor == "null"
        return self._filtra(lambda r: _valor(r, coluna) is None)

    def in_(self, coluna: str, valores) -> _Consulta:
        conjunto = set(valores)
        return self._filtra(lambda r: _valor(r, coluna) in conjunto)

    def gte(self, coluna: str, valor: str) -> _Consulta:
        return self._filtra(lambda r: _valor(r, coluna) is not None and str(_valor(r, coluna)) >= valor)

    def lte(self, coluna: str, valor: str) -> _Consulta:
        return self._filtra(lambda r: _valor(r, coluna) is not None and str(_valor(r, coluna)) <= valor)

    def ilike(self, coluna: str, padrao: str) -> _Consulta:
        return self._filtra(lambda r: _casa_ilike(_valor(r, coluna), padrao))

    def or_(self, expressao: str) -> _Consulta:
        condicoes = []
        for coluna, op, valor in _CONDICAO_DO_OR.findall(expressao):
            if op == "in":
                conjunto = set(valor.strip("()").split(","))
                condicoes.append(lambda r, c=coluna, s=conjunto: _valor(r, c) in s)
            elif op == "ilike":
                condicoes.append(lambda r, c=coluna, p=valor: _casa_ilike(_valor(r, c), p))
            else:
                condicoes.append(lambda r, c=coluna, v=valor: _valor(r, c) == v)
        return self._filtra(lambda r: any(cond(r) for cond in condicoes))

    def order(self, coluna: str, desc: bool = False, nullsfirst: bool = False) -> _Consulta:
        self._ordem = (coluna, desc)
        return self

    def range(self, inicio: int, fim: int) -> _Consulta:
        self._faixa = (inicio, fim)
        return self

    def limit(self, n: int) -> _Consulta:
        self._faixa = (0, n - 1)
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
            coluna, desc = self._ordem
            com_valor = sorted((r for r in linhas if r.get(coluna) is not None), key=lambda r: str(r[coluna]))
            if desc:
                com_valor.reverse()
            linhas = com_valor + [r for r in linhas if r.get(coluna) is None]
        if self._faixa:
            linhas = linhas[self._faixa[0] : self._faixa[1] + 1]
        return _Resultado([json.loads(json.dumps(r)) for r in linhas], total if self._contar else None)


class BancoFalso:
    def __init__(self, **tabelas: list[dict]):
        self.tabelas = tabelas
        self.escritas: list[tuple[str, str]] = []

    def table(self, nome: str) -> _Consulta:
        return _Consulta(self, nome)


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


def chamar_reunioes(cliente, chave, quem, **argumentos):
    return rpc(cliente, chave, quem, "tools/call", {"name": FERRAMENTA_REUNIOES, "arguments": argumentos})


def reunioes_do_claude(banco: BancoFalso, chave, quem: dict, **argumentos) -> dict:
    resposta = chamar_reunioes(cliente_mcp(banco), chave, quem, **argumentos)
    assert resposta.status_code == 200, resposta.text
    resultado = resposta.json()["result"]
    assert resultado["isError"] is False, resultado
    return resultado["structuredContent"]


# ─── O hospital de mentira ───────────────────────────────────────────────────


def reuniao(
    id_reuniao: str,
    data: str,
    titulo: str,
    *,
    objetivo: str | None = None,
    status_ata: str = "APROVADA",
    json_ata: dict | None = None,
    deleted_at: str | None = None,
) -> dict:
    return {
        "id_reuniao": id_reuniao,
        "data": data,
        "hora_inicio": "09:00:00",
        "hora_fim": "10:00:00",
        "tipo": "ORDINARIA",
        "titulo": titulo,
        "objetivo": objetivo,
        "status_ata": status_ata,
        "json_ata": json_ata,
        "facilitador_id": "resp-ana",
        "deleted_at": deleted_at,
    }


def ata(resumo: str, *topicos: tuple[str, str]) -> dict:
    return {
        "resumo_executivo": resumo,
        "discussao": [{"titulo": t, "descricao": f"Conversa sobre {t}", "decisao": d} for t, d in topicos],
        "proxima_reuniao": "2026-11-20",
        "quadro_atribuicoes": [{"acao": "não vai ao Claude"}],
    }


def pendencia(id_acao: str, status: str, id_reuniao: str, *, prazo: str | None = "2026-10-01") -> dict:
    return {
        "id_acao": id_acao,
        "descricao_acao": f"Ação {id_acao}",
        "status": status,
        "prazo": prazo,
        "responsavel_id": "resp-ana",
        "responsavel_nome": "Ana Souza",
        "co_responsavel_id": None,
        "co_responsavel_nome": None,
        "cargo": None,
        "meta_entregavel": None,
        "id_reuniao": id_reuniao,
        "deleted_at": None,
    }


def vinculo(id_reuniao: str, participante_id: str, nome: str, cargo: str) -> dict:
    """Uma linha de `reuniao_participantes` com o join de `participantes`."""
    return {
        "id_reuniao": id_reuniao,
        "participante_id": participante_id,
        "participantes": {"nome_completo": nome, "cargo": cargo},
    }


ANA = pessoa("resp-ana", "regular") | {"nome_completo": "Ana Souza"}


def banco_do_hospital(*quem: dict) -> BancoFalso:
    """Três reuniões; a diretora participa de R1 e R2, não de R3."""
    return BancoFalso(
        participantes=[*quem, ANA],
        reunioes=[
            reuniao(
                "R1",
                "2026-10-05",
                "Comitê de Qualidade",
                json_ata=ata("Revisão dos indicadores de infecção.", ("Infecção", "Treinar a equipe da UTI")),
            ),
            reuniao(
                "R2",
                "2026-10-20",
                "Planejamento da Maternidade",
                objetivo="Reforma do centro obstétrico",
                json_ata=ata("Cronograma da obra aprovado.", ("Obra", "Começar em dezembro")),
            ),
            reuniao("R3", "2026-09-10", "Comitê de Compras", json_ata=ata("Contrato de oxigênio.")),
            reuniao("R4", "2026-10-07", "Reunião apagada", deleted_at="2026-10-08T10:00:00Z"),
        ],
        reuniao_participantes=[
            vinculo("R1", "diretora", "Diretora Regular", "Diretora"),
            vinculo("R1", "resp-ana", "Ana Souza", "Enfermeira"),
            vinculo("R2", "diretora", "Diretora Regular", "Diretora"),
            vinculo("R3", "resp-ana", "Ana Souza", "Enfermeira"),
        ],
        pendencias=[
            pendencia("A1", "ATRASADO", "R1", prazo="2026-10-10"),
            pendencia("A2", "PENDENTE", "R1", prazo="2026-12-01"),
            pendencia("A3", "CONCLUIDO", "R1", prazo="2026-10-08"),
            pendencia("A4", "REPACTUADA", "R2", prazo=None),
            pendencia("A5", "EM_PROGRESSO", "R3"),
        ],
        comentarios_pendencias=[],
    )


# ─── 1. Busca por período e por termo ────────────────────────────────────────


class TestBuscaDeReunioes:
    def test_diretoria_busca_por_periodo_e_recebe_ata_participantes_e_pendencias(self, chave_do_emissor):
        payload = reunioes_do_claude(
            banco_do_hospital(DIRETOR_SUPER),
            chave_do_emissor,
            DIRETOR_SUPER,
            dataDe="2026-10-01",
            dataAte="2026-10-31",
        )

        assert [r["id"] for r in payload["reunioes"]] == ["R2", "R1"]
        r1 = next(r for r in payload["reunioes"] if r["id"] == "R1")
        assert r1["titulo"] == "Comitê de Qualidade"
        assert r1["data"] == "2026-10-05"
        assert r1["ata"]["resumoExecutivo"] == "Revisão dos indicadores de infecção."
        assert r1["ata"]["topicos"] == [
            {"titulo": "Infecção", "descricao": "Conversa sobre Infecção", "decisao": "Treinar a equipe da UTI"}
        ]
        assert {p["nome"] for p in r1["participantes"]} == {"Diretora Regular", "Ana Souza"}
        assert [(p["id"], p["responsavel"], p["prazo"]) for p in r1["pendencias"]] == [
            ("A3", "Ana Souza", "2026-10-08"),
            ("A1", "Ana Souza", "2026-10-10"),
            ("A2", "Ana Souza", "2026-12-01"),
        ]
        assert payload["total"] == 2
        assert payload["haMais"] is False
