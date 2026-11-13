"""O Conector entrega o Dossiê de um caso da Ouvidoria à diretoria executiva
(issue #1612, PRD #1571, ADR 0085, decisões 4 e 5).

Os seams testados são as portas de verdade:

- A rota do transporte (`POST /api/mcp`), com o gate de pé: o token do WorkOS
  assinado aqui contra um JWKS dublado e o banco num dublê em memória.
- As rotas da página do caso (`GET /api/ouvidoria/manifestacoes/por-protocolo`,
  `/movimentos` e `/respostas`), com o mesmo banco: o Dossiê que o Claude
  recebe tem de ser o que a tela mostra para a diretoria executiva.

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

pytestmark = pytest.mark.usefixtures("gate_e_limitador_zerados", "mcp_configurado", "jwks_no_emissor", "relogio")

EMISSOR = "https://hsm-teste.authkit.app"
RECURSO = "https://api.hsm-teste.cloud"
KID = "chave-de-teste-dossie"
CAMINHO_MCP = f"{settings.api_prefix}/mcp"
FERRAMENTA = "get_ouvidoria_dossie"
AGORA = dt.datetime(2026, 11, 12, 15, 0, tzinfo=dt.UTC)

DIRETOR = pessoa("diretor", "super_admin") | {"perfil_ouvidoria": "diretoria_executiva", "nome_completo": "Diretor"}


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
def relogio(monkeypatch):
    """O relógio da Ouvidoria parado: a tela e o Claude contam os marcos do
    mesmo instante."""
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
    """O pedaço do cliente do PostgREST que as portas usam. Leitura filtra as
    linhas da tabela; escrita fica anotada no banco (tabela, método e linha) e
    não muda nada. `falha_no_insert` faz o insert daquela tabela explodir."""

    def __init__(self, banco: BancoFalso, nome: str):
        self._banco = banco
        self._nome = nome
        self._filtros: list = []
        self._ordem: list[tuple[str, bool]] = []
        self._faixa: tuple[int, int] | None = None
        self._limite: int | None = None
        self._escrita: tuple[str, Any] | None = None

    def _filtra(self, filtro) -> _Consulta:
        self._filtros.append(filtro)
        return self

    def select(self, _campos: str = "*", count: str | None = None) -> _Consulta:
        return self

    def eq(self, coluna: str, valor: Any) -> _Consulta:
        return self._filtra(lambda r: r.get(coluna) == valor)

    def order(self, coluna: str, desc: bool = False, nullsfirst: bool = False) -> _Consulta:
        self._ordem.append((coluna, desc))
        return self

    def range(self, inicio: int, fim: int) -> _Consulta:
        self._faixa = (inicio, fim)
        return self

    def limit(self, n: int) -> _Consulta:
        self._limite = n
        return self

    def _escreve(self, metodo: str, dados: Any = None, **_kw) -> _Consulta:
        self._escrita = (metodo, dados)
        return self

    def update(self, dados: Any = None, **kw) -> _Consulta:
        return self._escreve("update", dados, **kw)

    def insert(self, dados: Any = None, **kw) -> _Consulta:
        return self._escreve("insert", dados, **kw)

    def upsert(self, dados: Any = None, **kw) -> _Consulta:
        return self._escreve("upsert", dados, **kw)

    def delete(self, **kw) -> _Consulta:
        return self._escreve("delete", None, **kw)

    def execute(self) -> _Resultado:
        if self._escrita is not None:
            metodo, dados = self._escrita
            if metodo == "insert" and self._nome in self._banco.falha_no_insert:
                raise RuntimeError(f"insert em {self._nome} falhou")
            self._banco.escritas.append((self._nome, metodo, dados))
            return _Resultado([dados] if isinstance(dados, dict) else [])
        linhas = [dict(r) for r in self._banco.tabelas.get(self._nome, []) if all(f(r) for f in self._filtros)]
        for coluna, desc in reversed(self._ordem):
            linhas.sort(key=lambda r, c=coluna: str(r.get(c) or ""), reverse=desc)
        if self._faixa:
            linhas = linhas[self._faixa[0] : self._faixa[1] + 1]
        if self._limite is not None:
            linhas = linhas[: self._limite]
        return _Resultado(linhas)


class BancoFalso:
    def __init__(self, **tabelas: list[dict]):
        self.tabelas = tabelas
        self.escritas: list[tuple[str, str, Any]] = []
        self.falha_no_insert: set[str] = set()

    def table(self, nome: str) -> _Consulta:
        return _Consulta(self, nome)


# ─── Os casos ────────────────────────────────────────────────────────────────


def caso(id_: str, protocolo: str, **campos) -> dict:
    base = {
        "id": id_,
        "protocolo": protocolo,
        "numero": int(protocolo.split("-")[1]),
        "status": "respondido",
        "setor_destino": "Emergência",
        "gravidade": "media",
        "tipo_manifestacao": "reclamacao",
        "resumo": f"Resumo do {protocolo}",
        "relato_integral": f"Relato integral do {protocolo}: esperei quatro horas na emergência.",
        "manifestante_nome": "Maria das Dores",
        "manifestante_contato": "maria@exemplo.com",
        "manifestante_vinculo": "paciente",
        "paciente_nome": "Maria das Dores",
        "paciente_referencia": "Prontuário 4471",
        "anonimo": False,
        "sigilo_reforcado": False,
        "canal": "formulario",
        "criado_em": "2026-11-02T13:00:00+00:00",
        "validada_em": "2026-11-03T13:00:00+00:00",
        "prazo_area_em": "2026-11-10T20:00:00+00:00",
        "respondida_em": "2026-11-05T13:00:00+00:00",
        "resposta_da_area": "Reforçamos a escala de triagem.",
        "respondida_por_nome": "Chefe da Emergência",
        "anonimizada_em": None,
    }
    return base | campos


def movimentos_de(manifestacao_id: str) -> list[dict]:
    return [
        {
            "id": f"{manifestacao_id}-m1",
            "manifestacao_id": manifestacao_id,
            "ocorrido_em": "2026-11-02T13:00:00+00:00",
            "estado_anterior": None,
            "estado_novo": "em_classificacao",
            "autor_id": None,
            "autor_nome": "Formulário público",
            "observacao": None,
        },
        {
            "id": f"{manifestacao_id}-m2",
            "manifestacao_id": manifestacao_id,
            "ocorrido_em": "2026-11-03T13:00:00+00:00",
            "estado_anterior": "em_classificacao",
            "estado_novo": "aguardando_area",
            "autor_id": "ouvidora",
            "autor_nome": "Ouvidora",
            "observacao": None,
        },
        {
            "id": f"{manifestacao_id}-m3",
            "manifestacao_id": manifestacao_id,
            "ocorrido_em": "2026-11-05T13:00:00+00:00",
            "estado_anterior": "aguardando_area",
            "estado_novo": "respondido",
            "autor_id": None,
            "autor_nome": "Chefe da Emergência",
            "observacao": "Resposta da área pelo portal do setor: Reforçamos a escala de triagem.",
        },
    ]


COMUM = caso("c-comum", "2026-0101")
SIGILOSO = caso("c-sigiloso", "2026-0102", tipo_manifestacao="denuncia", sigilo_reforcado=True)
ANONIMO = caso(
    "c-anonimo",
    "2026-0103",
    anonimo=True,
    manifestante_nome=None,
    manifestante_contato=None,
    manifestante_vinculo=None,
    paciente_nome=None,
    paciente_referencia=None,
)
APAGADO = caso(
    "c-apagado",
    "2026-0104",
    status="encerrado",
    resumo="[anonimizado pela retenção]",
    relato_integral=None,
    manifestante_nome=None,
    manifestante_contato=None,
    paciente_nome=None,
    paciente_referencia=None,
    resposta_da_area=None,
    anonimizada_em="2026-11-11T12:00:00+00:00",
    apagamento_pedido_em="2026-11-11T11:00:00+00:00",
    apagamento_pedido_por="diretor",
    apagamento_motivo="Pedido do titular",
)
CASOS = (COMUM, SIGILOSO, ANONIMO, APAGADO)


def banco_do_hospital(*quem: dict) -> BancoFalso:
    return BancoFalso(
        participantes=list(quem),
        ouvidoria_protocolos=[dict(c) for c in CASOS],
        ouvidoria_movimentos=[m for c in CASOS for m in movimentos_de(c["id"])],
        ouvidoria_feriados=[{"data": "2026-11-04"}],
        ouvidoria_notificacoes=[],
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


def dossie_do_claude(banco: BancoFalso, chave, quem: dict, protocolo: str) -> dict:
    resposta = chamar(cliente_mcp(banco), chave, quem, protocolo=protocolo)
    assert resposta.status_code == 200, resposta.text
    resultado = resposta.json()["result"]
    assert resultado["isError"] is False, resultado
    assert json.loads(resultado["content"][0]["text"]) == resultado["structuredContent"]
    return resultado["structuredContent"]


def pagina_do_caso(banco: BancoFalso, quem: dict, protocolo: str) -> dict:
    """O que a página do caso recebe: as três rotas que ela consome, de
    verdade, com quem está logado."""
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded

    from app.dependencies import _participante_ctx, get_current_user, get_supabase_client
    from app.limiter import limiter
    from app.routers import ouvidoria

    _participante_ctx.set(None)
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(ouvidoria.router, prefix="/api")
    app.dependency_overrides[get_supabase_client] = lambda: banco

    async def _usuario() -> dict[str, Any]:
        return {"id": quem["auth_user_id"], "email": quem["email"], "metadata": {}}

    app.dependency_overrides[get_current_user] = _usuario
    tela = TestClient(app)
    dossie = tela.get(f"/api/ouvidoria/manifestacoes/por-protocolo/{protocolo}")
    assert dossie.status_code == 200, dossie.text
    mid = dossie.json()["id"]
    movimentos = tela.get(f"/api/ouvidoria/manifestacoes/{mid}/movimentos")
    respostas = tela.get(f"/api/ouvidoria/manifestacoes/{mid}/respostas")
    assert movimentos.status_code == 200, movimentos.text
    assert respostas.status_code == 200, respostas.text
    _participante_ctx.set(None)
    return {"dossie": dossie.json(), "trilha": movimentos.json(), "respostas": respostas.json()["respostas"]}


# ─── 1. O Dossiê é o da tela ─────────────────────────────────────────────────


class TestDossieDaTela:
    @pytest.mark.parametrize("caso_", [COMUM, SIGILOSO, ANONIMO], ids=["comum", "sigiloso", "anonimo"])
    def test_diretoria_recebe_o_dossie_que_a_tela_mostra(self, chave_do_emissor, caso_):
        banco = banco_do_hospital(DIRETOR)

        na_tela = pagina_do_caso(banco, DIRETOR, caso_["protocolo"])
        no_claude = dossie_do_claude(banco, chave_do_emissor, DIRETOR, caso_["protocolo"])

        assert no_claude["dossie"] == na_tela["dossie"]
        assert no_claude["trilha"] == na_tela["trilha"]
        assert no_claude["respostas"] == na_tela["respostas"]
        # A fonte independente: o que o caso gravou chega como gravou.
        assert no_claude["dossie"]["relato_integral"] == caso_["relato_integral"]
        assert no_claude["dossie"]["manifestante_nome"] == caso_["manifestante_nome"]
        assert no_claude["dossie"]["paciente_referencia"] == caso_["paciente_referencia"]
        assert no_claude["respostas"][0]["resposta"] == "Reforçamos a escala de triagem."
        assert len(no_claude["trilha"]["movimentos"]) == 3

    def test_o_sigiloso_chega_marcado_e_com_a_identificacao(self, chave_do_emissor):
        no_claude = dossie_do_claude(banco_do_hospital(DIRETOR), chave_do_emissor, DIRETOR, SIGILOSO["protocolo"])

        assert no_claude["dossie"]["sigilo_reforcado"] is True
        assert no_claude["dossie"]["manifestante_contato"] == "maria@exemplo.com"

    def test_caso_apagado_chega_com_o_aviso_no_lugar_do_relato(self, chave_do_emissor):
        no_claude = dossie_do_claude(banco_do_hospital(DIRETOR), chave_do_emissor, DIRETOR, APAGADO["protocolo"])

        dossie = no_claude["dossie"]
        assert "relato_integral" not in dossie
        assert "resumo" not in dossie
        assert "[anonimizado pela retenção]" not in json.dumps(no_claude, ensure_ascii=False)
        # 12:00 UTC é 09:00 no horário do hospital.
        assert dossie["aviso_caso_apagado"].startswith("Este caso foi apagado em 11/11/2026 às 09:00.")
        assert "Motivo: Pedido do titular." in dossie["aviso_caso_apagado"]
        # A ficha e a trilha continuam, como na tela.
        assert dossie["protocolo"] == APAGADO["protocolo"]
        assert len(no_claude["trilha"]["movimentos"]) == 3

    def test_caso_comum_nao_traz_aviso_de_apagado(self, chave_do_emissor):
        no_claude = dossie_do_claude(banco_do_hospital(DIRETOR), chave_do_emissor, DIRETOR, COMUM["protocolo"])

        assert "aviso_caso_apagado" not in no_claude["dossie"]

    @pytest.mark.parametrize(
        "protocolo", ["2026-9999", "nao-e-protocolo", ""], ids=["inexistente", "malformado", "vazio"]
    )
    def test_protocolo_sem_caso_e_erro_de_ferramenta_claro(self, chave_do_emissor, protocolo):
        banco = banco_do_hospital(DIRETOR)

        resultado = chamar(cliente_mcp(banco), chave_do_emissor, DIRETOR, protocolo=protocolo).json()["result"]

        assert resultado["isError"] is True
        assert "structuredContent" not in resultado
        assert "protocolo" in resultado["content"][0]["text"]
        assert banco.escritas == []


# ─── 2. O registro de acesso ─────────────────────────────────────────────────


def acessos(banco: BancoFalso) -> list[dict]:
    return [dados for tabela, metodo, dados in banco.escritas if tabela == "ouvidoria_acessos" and metodo == "insert"]


class TestRegistroDeAcesso:
    def test_cada_chamada_grava_uma_consulta_conector_com_o_ator_certo(self, chave_do_emissor):
        banco = banco_do_hospital(DIRETOR)
        cliente = cliente_mcp(banco)

        for _ in range(2):
            resultado = chamar(cliente, chave_do_emissor, DIRETOR, protocolo=COMUM["protocolo"]).json()["result"]
            assert resultado["isError"] is False

        linha = {
            "manifestacao_id": "c-comum",
            "ator_id": "diretor",
            "ator_nome": "Diretor",
            "acao": "consulta_conector",
        }
        assert acessos(banco) == [linha, linha]

    def test_falha_no_registro_nao_impede_a_resposta(self, chave_do_emissor):
        banco = banco_do_hospital(DIRETOR)
        banco.falha_no_insert.add("ouvidoria_acessos")

        no_claude = dossie_do_claude(banco, chave_do_emissor, DIRETOR, COMUM["protocolo"])

        assert no_claude["dossie"]["relato_integral"] == COMUM["relato_integral"]


# ─── 3. O gate ───────────────────────────────────────────────────────────────


class TestGate:
    def test_super_admin_sem_diretoria_nao_ve_nem_chama_a_ferramenta(self, chave_do_emissor):
        banco = banco_do_hospital(SUPER_ADMIN)
        cliente = cliente_mcp(banco)

        lista = rpc(cliente, chave_do_emissor, SUPER_ADMIN, "tools/list").json()["result"]["tools"]
        assert FERRAMENTA not in {f["name"] for f in lista}

        resposta = chamar(cliente, chave_do_emissor, SUPER_ADMIN, protocolo=COMUM["protocolo"])
        assert resposta.status_code == 200, resposta.text
        resultado = resposta.json()["result"]
        assert resultado["isError"] is True
        assert "structuredContent" not in resultado
        assert "esperei quatro horas" not in resposta.text
        assert "Maria" not in resposta.text
        assert banco.escritas == []

    def test_diretoria_ve_a_ferramenta_na_lista(self, chave_do_emissor):
        lista = rpc(cliente_mcp(banco_do_hospital(DIRETOR)), chave_do_emissor, DIRETOR, "tools/list").json()
        assert FERRAMENTA in {f["name"] for f in lista["result"]["tools"]}


# ─── 4. Só leitura ───────────────────────────────────────────────────────────


class TestSoLeitura:
    def test_a_ferramenta_nao_escreve_em_caso_nem_em_trilha(self, chave_do_emissor):
        banco = banco_do_hospital(DIRETOR)
        cliente = cliente_mcp(banco)

        for caso_ in CASOS:
            resultado = chamar(cliente, chave_do_emissor, DIRETOR, protocolo=caso_["protocolo"]).json()["result"]
            assert resultado["isError"] is False

        assert banco.escritas
        assert {(tabela, metodo) for tabela, metodo, _ in banco.escritas} == {("ouvidoria_acessos", "insert")}
