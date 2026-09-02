"""O token do link não vai para o log do container (issue #465).

No portal do setor e no Aceite interno o token **é** o path
(`/api/ouvidoria-setor/{token}`), e o banco guarda só o hash: o invariante que
`test_banco_guarda_so_o_hash_do_token` declara é que vazar o banco não vaza o
link. O log do container furava esse invariante pela outra ponta, porque o
middleware de request gravava `request.url.path` cru em toda requisição. Quem
lê o log do Coolify, sem perfil nenhum na Ouvidoria, abria o caso e respondia
pelo setor até o token ser usado ou expirar.

O estrago é maior que o da issue #450 (corpo do email no log): lá é leitura de
conteúdo, aqui é ação em nome do setor.

O que fica no log é o TEMPLATE da rota (`/api/ouvidoria-setor/{token}`), mais
`request_id`, método, status e latência: o diagnóstico de operação continua de
pé, o que sai é só o segredo. Id de recurso (manifestação, reunião,
participante) continua inteiro, porque não é segredo e é o que liga a linha do
log ao caso.

A varredura da issue vive aqui como teste, e não como parágrafo do PR:
`TestVarreduraDeSegredoNoPath` monta o app de verdade e trava porta irmã, tanto
a rota nova com `{token}` quanto a rota nova com um nome de parâmetro que
ninguém classificou ainda.

Nenhum teste aqui toca banco ou provedor externo: o log do middleware é escrito
antes de a rota resolver qualquer coisa, então o Supabase falso devolve vazio e
as rotas respondem 404, que é o mesmo caminho de log do 200.
"""

from __future__ import annotations

import logging
import os
import re
import sys
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.limiter import limiter  # noqa: E402
from app.middleware.request_context import (  # noqa: E402
    JsonFormatter,
    RequestContextMiddleware,
    path_para_log,
)
from app.routers import aceite as aceite_router  # noqa: E402
from app.routers import ouvidoria_setor as ouvidoria_setor_router  # noqa: E402

# No formato real: `secrets.token_urlsafe(32)` gera 43 caracteres url-safe.
TOKEN = "kzN7Vv2r0QhTf3lXqB9dJm4sPcW8yAeR1uGhOiZbNxE"

# As rotas em que o token É o path, exercitadas pelo seam HTTP. O corpo vai
# vazio de propósito: 422 e 404 passam pelo mesmo log do middleware que o 200, e
# o que se mede aqui é o que o middleware grava, não o que a rota decide.
ROTAS_TOKENIZADAS = [
    ("GET", f"/api/ouvidoria-setor/{TOKEN}", "/api/ouvidoria-setor/{token}"),
    ("POST", f"/api/ouvidoria-setor/{TOKEN}/responder", "/api/ouvidoria-setor/{token}/responder"),
    ("POST", f"/api/ouvidoria-setor/{TOKEN}/prorrogacao", "/api/ouvidoria-setor/{token}/prorrogacao"),
    ("GET", f"/api/aceite/{TOKEN}", "/api/aceite/{token}"),
    ("POST", f"/api/aceite/{TOKEN}/aceitar", "/api/aceite/{token}/aceitar"),
]

# Os nomes de parâmetro de path do app inteiro, classificados um a um. Qualquer
# rota nova com um nome fora desta lista deixa o teste vermelho: é assim que a
# varredura da issue #465 continua valendo depois que ela fecha.
PARAMS_DE_SEGREDO = {"token"}
PARAMS_SEM_SEGREDO = {
    "anexo_id",
    "codigo",
    "comentario_id",
    "convenio_id",
    "data",
    "especialidade_id",
    "externo_id",
    "gravidade",
    "id_acao",
    "id_grupo_recorrencia",
    "id_reuniao",
    "index",
    "item_id",
    "manifestacao_id",
    "marco",
    "material_id",
    "nome",
    "notificacao_id",
    "plano_id",
    "ponto_id",
    "pop_id",
    "participante_id",
    "prorrogacao_id",
    "protocolo",
    "relatorio_id",
    "responsavel_id",
    "setor_id",
    "signer_id",
}

# As rotas com segredo no path, congeladas. Rota nova com `{token}` entra aqui
# de propósito, junto com a conferência de que ela é mascarada.
ROTAS_COM_SEGREDO_NO_PATH = {
    "/api/aceite/{token}",
    "/api/aceite/{token}/aceitar",
    "/api/ouvidoria-setor/{token}",
    "/api/ouvidoria-setor/{token}/prorrogacao",
    "/api/ouvidoria-setor/{token}/responder",
}


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """O storage do slowapi é global por IP e acumula 429 entre arquivos."""
    limiter._storage.reset()
    yield
    limiter._storage.reset()


class _SupabaseVazio:
    """Devolve vazio para qualquer consulta: o token nunca resolve caso nenhum.

    A rota então responde 404, e o middleware loga a linha do request do mesmo
    jeito, que é o que está sob teste."""

    def table(self, _nome):
        return self

    def select(self, *_a, **_k):
        return self

    def insert(self, *_a, **_k):
        return self

    def update(self, *_a, **_k):
        return self

    def eq(self, *_a, **_k):
        return self

    def order(self, *_a, **_k):
        return self

    def limit(self, *_a, **_k):
        return self

    def maybe_single(self):
        return self

    def single(self):
        return self

    def execute(self):
        return SimpleNamespace(data=[])


class _CapturaJson(logging.Handler):
    """Formata cada linha NA HORA, com o JsonFormatter de produção.

    Formatar depois do request (o que `caplog` faria) leria o `request_id` já
    resetado pelo middleware, e o teste do sinal de operação mediria um campo
    vazio que em produção existe."""

    def __init__(self) -> None:
        super().__init__()
        self.setFormatter(JsonFormatter())
        self.linhas: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.linhas.append(self.format(record))


def _app() -> FastAPI:
    """As rotas de verdade, na mesma montagem do `main` (prefixo `/api`)."""
    from app.dependencies import get_supabase_client

    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(RequestContextMiddleware)
    app.include_router(ouvidoria_setor_router.router, prefix="/api")
    app.include_router(aceite_router.router, prefix="/api")
    app.dependency_overrides[get_supabase_client] = lambda: _SupabaseVazio()
    return app


def _chamar(metodo: str, caminho: str) -> str:
    """Faz a requisição e devolve a linha de log do request, já formatada."""
    captura = _CapturaJson()
    logger = logging.getLogger("app.requests")
    nivel_anterior = logger.level
    logger.addHandler(captura)
    logger.setLevel(logging.INFO)
    try:
        cliente = TestClient(_app(), raise_server_exceptions=False)
        cliente.request(metodo, caminho, json={})
    finally:
        logger.removeHandler(captura)
        logger.setLevel(nivel_anterior)
    assert len(captura.linhas) == 1, f"esperava 1 linha de request, veio {captura.linhas}"
    return captura.linhas[0]


@pytest.mark.parametrize(("metodo", "caminho", "template"), ROTAS_TOKENIZADAS)
def test_o_token_em_claro_nao_aparece_no_log(metodo, caminho, template):
    """CA: abrir o portal do setor (e o aceite) não grava o token no log.

    As cinco rotas juntas porque o furo é da família toda: fechar só a que a
    issue nomeia deixaria a irmã (`/responder`, que é a que age em nome do
    setor) escrevendo o mesmo token na linha seguinte."""
    linha = _chamar(metodo, caminho)

    assert TOKEN not in linha, f"o token vazou para o log: {linha}"


@pytest.mark.parametrize(("metodo", "caminho", "template"), ROTAS_TOKENIZADAS)
def test_o_log_continua_dizendo_qual_rota_foi(metodo, caminho, template):
    """CA: o mascaramento não pode cegar o diagnóstico.

    Trocar o path por um literal fixo ("[mascarado]") também tiraria o token do
    log, e deixaria a operação sem saber se o que respondeu 500 foi a abertura
    do portal ou a resposta do setor."""
    linha = _chamar(metodo, caminho)

    assert f'"path": "{template}"' in linha


def test_o_log_mantem_request_id_metodo_status_e_latencia():
    """CA: o resto do sinal de operação continua inteiro."""
    linha = _chamar("GET", f"/api/ouvidoria-setor/{TOKEN}")

    assert re.search(r'"request_id": "[0-9a-f]{32}"', linha), linha
    assert '"method": "GET"' in linha
    assert '"status_code": 404' in linha
    assert '"latency_ms": ' in linha


def test_a_rota_fixa_vizinha_do_token_continua_legivel():
    """`/api/aceite/meu-link` mora ao lado de `/api/aceite/{token}`.

    Mascarar por posição no path (o segmento depois de `/api/aceite/`) tiraria o
    token e levaria junto o nome desta rota, e ela é justamente a que o suporte
    procura no log quando alguém diz que o link não chegou."""
    linha = _chamar("POST", "/api/aceite/meu-link")

    assert '"path": "/api/aceite/meu-link"' in linha


def test_o_caminho_que_nao_casa_rota_nenhuma_tambem_sai_mascarado():
    """404 do roteador é o buraco que o mascaramento por parâmetro não vê.

    Sem rota casada não há `path_params` no scope, e o path cru voltaria ao log
    com o token inteiro. Um link do email com sujeira colada no fim cai aqui."""
    linha = _chamar("GET", f"/api/ouvidoria-setor/{TOKEN}/inexistente")

    assert TOKEN not in linha, f"o token vazou pelo 404 do roteador: {linha}"
    assert '"status_code": 404' in linha


def test_id_de_recurso_continua_inteiro_no_log():
    """O que NÃO é segredo continua no log: mascarar id de manifestação ou de
    reunião custaria a correlação entre a linha do log e o caso, sem ganho
    nenhum de segurança (esses ids já dependem de sessão autenticada)."""
    scope = {
        "path": "/api/ouvidoria/manifestacoes/uuid-7/movimentos",
        "path_params": {"manifestacao_id": "uuid-7"},
    }

    assert path_para_log(scope) == "/api/ouvidoria/manifestacoes/uuid-7/movimentos"


class TestVarreduraDeSegredoNoPath:
    """A varredura da issue #465, executável: o app real, rota por rota."""

    @staticmethod
    def _rotas_com_params() -> list[tuple[str, list[str]]]:
        from app.main import app

        achadas = []
        for rota in app.routes:
            caminho = getattr(rota, "path", "")
            params = re.findall(r"\{([^}:]+)", caminho)
            if params:
                achadas.append((caminho, params))
        return achadas

    def test_todo_parametro_de_path_do_app_esta_classificado(self):
        """Rota nova com nome de parâmetro que ninguém classificou fica
        vermelha aqui. É esta a trava contra a porta irmã de amanhã: um
        `{codigo_de_acesso}` não seria pego por procurar a palavra "token"."""
        nomes = {nome for _caminho, params in self._rotas_com_params() for nome in params}

        assert nomes <= PARAMS_DE_SEGREDO | PARAMS_SEM_SEGREDO, (
            f"parâmetro de path não classificado: {sorted(nomes - PARAMS_DE_SEGREDO - PARAMS_SEM_SEGREDO)}. "
            "Diga se ele carrega segredo (issue #465) antes de seguir."
        )

    def test_as_rotas_com_segredo_no_path_sao_exatamente_estas(self):
        """A lista congelada como literal de propósito: derivá-la do app faria o
        teste concordar com qualquer rota nova em silêncio."""
        com_segredo = {caminho for caminho, params in self._rotas_com_params() if PARAMS_DE_SEGREDO & set(params)}

        assert com_segredo == ROTAS_COM_SEGREDO_NO_PATH

    def test_cada_rota_com_segredo_sai_mascarada(self):
        """E todas elas passam pelo mascarador de fato."""
        for caminho in sorted(ROTAS_COM_SEGREDO_NO_PATH):
            concreto = caminho.replace("{token}", TOKEN)
            saida = path_para_log({"path": concreto, "path_params": {"token": TOKEN}})

            assert TOKEN not in saida, f"{caminho} não é mascarada"
            assert saida == caminho
