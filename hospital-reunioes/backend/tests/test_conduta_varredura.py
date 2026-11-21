"""As travas que valem para toda rota do Canal de Conduta (issue #1820, ADR 0097).

1. A varredura: toda rota do Comitê depende do portão, e toda rota pública
   depende da chave de abertura. Rota nova sem portão fica vermelha aqui.
2. A chave de abertura: desligada, a rota pública responde 404.
3. O log das rotas do módulo sai sem IP.
"""

from __future__ import annotations

import importlib
import json
import logging
import os
import pkgutil
import sys

import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app.routers as pacote_dos_routers  # noqa: E402
from app.config import settings  # noqa: E402
from app.dependencies import get_current_user  # noqa: E402
from app.middleware.request_context import JsonFormatter, RequestContextMiddleware  # noqa: E402
from app.routers import conduta_comite, conduta_publico  # noqa: E402
from app.routers.conduta_publico import exigir_canal_aberto  # noqa: E402
from app.services.conduta.portao import (  # noqa: E402
    portao_da_acao,
    portao_da_coordenacao,
    portao_da_lista,
    portao_da_tela_inicial,
    portao_do_cadastro,
    portao_do_caso,
    portao_dos_membros,
)

# Os do caso, o da tela inicial (issue #1823) e, para a tela Membros (issue
# #1822) e as configurações do módulo (issue #1826), os que não abrem caso.
PORTOES_DO_COMITE = {
    portao_da_lista,
    portao_do_caso,
    portao_da_acao,
    portao_da_tela_inicial,
    portao_dos_membros,
    portao_do_cadastro,
    portao_da_coordenacao,
}
PREFIXO_PUBLICO = "/conduta"
IP_DE_QUEM_RELATA = "203.0.113.45"


def _chamadas(dependente) -> set:
    """Todas as funções de que a rota depende, em qualquer profundidade."""
    achadas = set()
    for sub in dependente.dependencies:
        achadas.add(sub.call)
        achadas |= _chamadas(sub)
    return achadas


def _routers_do_modulo() -> list[APIRouter]:
    nomes = [m.name for m in pkgutil.iter_modules(pacote_dos_routers.__path__) if m.name.startswith("conduta")]
    return [importlib.import_module(f"app.routers.{nome}").router for nome in sorted(nomes)]


def rotas_sem_trava(routers: list[APIRouter]) -> list[str]:
    """As rotas do módulo sem a trava do seu lado: o portão no Comitê, a chave
    de abertura na pública."""
    sem_trava = []
    for router in routers:
        for rota in router.routes:
            if not isinstance(rota, APIRoute):
                continue
            chamadas = _chamadas(rota.dependant)
            if rota.path.startswith(PREFIXO_PUBLICO + "/"):
                ok = exigir_canal_aberto in chamadas
            else:
                ok = bool(PORTOES_DO_COMITE & chamadas)
            if not ok:
                sem_trava.append(f"{sorted(rota.methods)} {rota.path}")
    return sem_trava


class TestVarredura:
    def test_a_varredura_enxerga_as_rotas_do_modulo(self):
        """Controle: varredura vazia satisfaria "toda rota tem portão"."""
        caminhos = {rota.path for router in _routers_do_modulo() for rota in router.routes}
        assert {
            "/comite-de-conduta/casos",
            "/comite-de-conduta/casos/{caso_id}",
            "/comite-de-conduta/membros",
            "/comite-de-conduta/configuracoes",
            "/comite-de-conduta/configuracoes/{chave}",
            "/conduta/abertura",
            "/conduta/textos",
        } <= caminhos

    def test_toda_rota_do_modulo_passa_pela_trava(self):
        assert rotas_sem_trava(_routers_do_modulo()) == []

    def test_a_varredura_reprova_rota_do_comite_sem_portao(self):
        """O detector também é código: uma rota do Comitê que só pede login
        tem que aparecer."""
        router = APIRouter(prefix="/comite-de-conduta")

        @router.get("/casos/{caso_id}/anexos")
        async def _sem_portao(me: dict = Depends(get_current_user)):
            return {}

        assert rotas_sem_trava([router]) == ["['GET'] /comite-de-conduta/casos/{caso_id}/anexos"]

    def test_a_varredura_reprova_rota_publica_sem_a_chave_de_abertura(self):
        router = APIRouter(prefix="/conduta")

        @router.post("/relatos")
        async def _aberta():
            return {}

        assert rotas_sem_trava([router]) == ["['POST'] /conduta/relatos"]

    def test_toda_rota_com_conduta_no_app_e_de_um_router_do_modulo(self):
        """Uma rota do módulo escrita noutro router escaparia da varredura."""
        from app.main import app

        do_app = {caminho for caminho in app.openapi()["paths"] if "conduta" in caminho}
        do_modulo = {
            f"{settings.api_prefix}{rota.path}"
            for router in _routers_do_modulo()
            for rota in router.routes
            if isinstance(rota, APIRoute)
        }

        assert do_app == do_modulo


@pytest.fixture
def canal(monkeypatch):
    def _montar(aberto: bool) -> TestClient:
        monkeypatch.setattr(settings, "conduta_canal_aberto", aberto)
        app = FastAPI()
        app.add_middleware(RequestContextMiddleware)
        app.include_router(conduta_publico.router, prefix="/api")
        app.include_router(conduta_comite.router, prefix="/api")
        return TestClient(app, client=(IP_DE_QUEM_RELATA, 50123), raise_server_exceptions=False)

    return _montar


class TestChaveDeAbertura:
    def test_com_a_chave_desligada_a_rota_publica_responde_404(self, canal):
        """Mutante: tirar a dependência do router público."""
        resposta = canal(False).get("/api/conduta/abertura")

        assert resposta.status_code == 404
        assert resposta.json() == {"detail": "Not Found"}

    def test_com_a_chave_ligada_a_rota_publica_responde(self, canal):
        resposta = canal(True).get("/api/conduta/abertura")

        assert resposta.status_code == 200
        assert resposta.json() == {"aberto": True}

    def test_o_canal_nasce_fechado(self):
        from app.config import Settings

        assert Settings.model_fields["conduta_canal_aberto"].default is False


class _Captura(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.setFormatter(JsonFormatter())
        self.linhas: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.linhas.append(self.format(record))


def _linhas_do_log(cliente: TestClient, caminho: str) -> list[str]:
    captura = _Captura()
    logger = logging.getLogger("app.requests")
    nivel = logger.level
    logger.addHandler(captura)
    logger.setLevel(logging.INFO)
    try:
        cliente.get(caminho)
    finally:
        logger.removeHandler(captura)
        logger.setLevel(nivel)
    return captura.linhas


class TestLogSemIp:
    @pytest.mark.parametrize(
        "caminho",
        ["/api/conduta/abertura", "/api/comite-de-conduta/casos", "/api//CONDUTA/abertura", "/api/conduta/nao-existe"],
    )
    def test_o_log_das_rotas_do_modulo_nao_registra_ip(self, canal, caminho):
        """Mutante: tirar o Canal de Conduta da regra do IP no middleware."""
        (linha,) = _linhas_do_log(canal(True), caminho)

        assert json.loads(linha)["client_ip"] == ""
        assert "203.0.113" not in linha

    def test_controle_fora_do_modulo_o_ip_continua_no_log(self, canal):
        """Sem este controle, um middleware que nunca gravasse IP passaria."""
        (linha,) = _linhas_do_log(canal(True), "/api/outra-coisa")

        assert json.loads(linha)["client_ip"] == IP_DE_QUEM_RELATA
