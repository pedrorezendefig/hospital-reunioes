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

O middleware, porém, é UMA porta. O mesmo token saía no MESMO stdout por outras
duas, e enquanto elas existirem o critério de aceite não vale no log do Coolify,
que é o que o operador abre: o access log do uvicorn (logger com handler próprio
e `propagate=False`, fora do alcance do `configure_logging`) e o handler de
exceção não tratada do `main`. `TestOutrasPortasDoMesmoStdout` tranca as três.

A varredura da issue vive aqui como teste, e não como parágrafo do PR:
`TestVarreduraDeSegredoNoPath` monta o app de verdade e trava porta irmã, tanto
a rota nova com `{token}` quanto a rota nova com um nome de parâmetro que
ninguém classificou ainda.

Nenhum teste aqui toca banco ou provedor externo: o log do middleware é escrito
antes de a rota resolver qualquer coisa, então o Supabase falso devolve vazio e
as rotas respondem 404, que é o mesmo caminho de log do 200.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from pathlib import Path
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

_DOCKERFILE = Path(__file__).resolve().parents[1] / "Dockerfile"

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


@pytest.mark.parametrize(("metodo", "caminho"), [(metodo, caminho) for metodo, caminho, _t in ROTAS_TOKENIZADAS])
def test_o_token_em_claro_nao_aparece_no_log(metodo, caminho):
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


# As formas de path que furavam a rede do 404: nenhuma delas casa rota, então
# todas caem no mascaramento por prefixo. Barra dupla é a realista (base de URL
# com barra final grudando no caminho); as outras são o que alguém tenta de
# propósito ao descobrir que o log guarda o path.
CAMINHOS_DEFORMADOS = [
    f"/api/ouvidoria-setor//{TOKEN}",
    f"/api/ouvidoria-setor/x/{TOKEN}",
    f"/api/ouvidoria-setor/%2e%2e/{TOKEN}",
    f"/API/ouvidoria-setor/{TOKEN}",
    f"/api/aceite//{TOKEN}",
    f"/api/Aceite/{TOKEN}",
]


@pytest.mark.parametrize("caminho", CAMINHOS_DEFORMADOS)
def test_path_deformado_nao_escapa_da_rede_do_404(caminho):
    """O token não pode depender da forma do path para sair do log.

    Todas estas casavam o prefixo de um jeito que deixava o token na cauda: o
    `startswith` era cru (caixa e barra repetida furavam) e só o primeiro
    segmento virava `{token}`."""
    linha = _chamar("GET", caminho)

    assert TOKEN not in linha, f"o token vazou por {caminho}: {linha}"


# As mesmas deformações, agora onde o cliente HTTP não deixa passar: httpx
# normaliza barra repetida antes de mandar, então a barra dupla NO MEIO do
# prefixo só chega ao mascarador vindo direto do scope (proxy, redirect
# montado à mão, cliente que não normaliza). O 404 do roteador é o cenário: sem
# rota casada não há `path_params`.
PATHS_COM_BARRA_REPETIDA = [
    f"//api/ouvidoria-setor/{TOKEN}",
    f"/api//ouvidoria-setor/{TOKEN}",
    f"/api//aceite/{TOKEN}",
]


@pytest.mark.parametrize("caminho", PATHS_COM_BARRA_REPETIDA)
def test_barra_repetida_no_prefixo_nao_escapa(caminho):
    """`startswith` cru não casa `//api/...` nem `/api//aceite/...`, e o token
    saía inteiro. Barra repetida é forma válida de path."""
    saida = path_para_log({"path": caminho})

    assert TOKEN not in saida, f"o token vazou por {caminho}: {saida}"


def test_token_de_um_caractere_nao_pica_o_path():
    """`str.replace` global trocava toda ocorrência da string do token.

    Com um token curto (`a`), `/api/aceite/a` virava
    `/{token}pi/aceite/{token}` no log: não vaza segredo, mas entrega uma linha
    que ninguém consegue ler nem agrupar."""
    scope = {"path": "/api/aceite/a", "path_params": {"token": "a"}}

    assert path_para_log(scope) == "/api/aceite/{token}"


def test_id_de_recurso_continua_inteiro_no_log():
    """O que NÃO é segredo continua no log: mascarar id de manifestação ou de
    reunião custaria a correlação entre a linha do log e o caso, sem ganho
    nenhum de segurança (esses ids já dependem de sessão autenticada)."""
    scope = {
        "path": "/api/ouvidoria/manifestacoes/uuid-7/movimentos",
        "path_params": {"manifestacao_id": "uuid-7"},
    }

    assert path_para_log(scope) == "/api/ouvidoria/manifestacoes/uuid-7/movimentos"


class TestOutrasPortasDoMesmoStdout:
    """O middleware é UMA porta. O mesmo token saía por outras duas.

    Enquanto elas existirem, o critério de aceite não vale no log do Coolify,
    que é o alvo da issue: o operador lê o stdout do container inteiro, não a
    linha do `app.requests`."""

    @staticmethod
    def _cmd_do_dockerfile() -> list[str]:
        """O `CMD [` em forma exec, não o `CMD curl` do HEALTHCHECK."""
        for linha in _DOCKERFILE.read_text().splitlines():
            if linha.strip().startswith("CMD ["):
                return json.loads(linha.strip().removeprefix("CMD").strip())
        raise AssertionError("Dockerfile sem linha CMD em forma exec")

    def test_o_dockerfile_sobe_o_uvicorn_sem_access_log(self):
        """O `uvicorn.access` tem handler próprio e `propagate=False`, então o
        `configure_logging` (que só mexe no root) não o alcança: sem a flag, o
        container imprime `"GET /api/ouvidoria-setor/<token> HTTP/1.1" 200 OK`
        em toda abertura do portal, ao lado da linha já mascarada.

        Nada de observabilidade se perde: método, path, status, latência e
        request_id já saem na linha do `app.requests`, e o path CRU era a única
        coisa exclusiva do access log."""
        assert "--no-access-log" in self._cmd_do_dockerfile()

    def test_a_stack_local_sobe_com_a_mesma_flag(self):
        """O `command:` do compose sobrescreve o CMD do Dockerfile (por causa
        do --reload): sem repetir a flag ali, o token volta ao log do dev, que é
        onde se testa com caso de verdade."""
        compose = (_DOCKERFILE.parents[1] / "docker-compose.yml").read_text()
        linha = next(ln for ln in compose.splitlines() if "uvicorn app.main:app" in ln)

        assert "--no-access-log" in linha

    def test_o_500_dentro_da_rota_tokenizada_nao_grava_o_token(self):
        """A outra porta: o handler de exceção não tratada logava
        `request.url.path` cru.

        O 500 é justamente o que faz o operador abrir o log, e o timeout de
        httpx no PostgREST (que o `except APIError` não pega) chega aqui de
        verdade. Contra o `app.main`, e não contra app sintético: o handler é
        montado lá, no `ServerErrorMiddleware`, e um sintético provaria outra
        coisa."""
        from app.dependencies import get_supabase_client
        from app.main import app as app_real

        def _banco_fora_do_ar():
            raise RuntimeError("timeout no PostgREST")

        captura = _CapturaJson()
        # Os dois loggers do app, e não o root: o root pegaria junto a linha do
        # `httpx` do próprio TestClient, que loga a URL que ELE montou. Essa
        # linha é do cliente de teste, não do container.
        loggers = [logging.getLogger("app.requests"), logging.getLogger("unhandled")]
        niveis = [lg.level for lg in loggers]
        app_real.dependency_overrides[get_supabase_client] = _banco_fora_do_ar
        for lg in loggers:
            lg.addHandler(captura)
            lg.setLevel(logging.INFO)
        try:
            resposta = TestClient(app_real, raise_server_exceptions=False).get(f"/api/ouvidoria-setor/{TOKEN}")
        finally:
            for lg, nivel in zip(loggers, niveis, strict=True):
                lg.removeHandler(captura)
                lg.setLevel(nivel)
            app_real.dependency_overrides.pop(get_supabase_client, None)

        assert resposta.status_code == 500, resposta.text
        # Controle: o handler correu mesmo. Sem isto, um 500 que não passasse
        # por ele daria o mesmo verde adiante.
        assert any('"logger": "unhandled"' in linha for linha in captura.linhas), captura.linhas
        for linha in captura.linhas:
            assert TOKEN not in linha, f"o token vazou no 500: {linha}"


class TestVarreduraDeSegredoNoPath:
    """A varredura da issue #465, executável: o app real, rota por rota."""

    @staticmethod
    def _rotas_com_params() -> list[tuple[str, list[str]]]:
        """Os paths do app real, lidos do schema OpenAPI.

        `app.routes` não serve como fonte: desde o FastAPI 0.141 o
        `include_router` guarda o router incluído em vez de copiar as rotas para
        cima, e a lista volta sem rota nenhuma de router. Isso não daria erro,
        daria varredura vazia, que é o pior jeito de uma defesa morrer. O schema
        é contrato público e vale nas duas versões."""
        from app.main import app

        achadas = []
        for caminho in app.openapi()["paths"]:
            params = re.findall(r"\{([^}:]+)", caminho)
            if params:
                achadas.append((caminho, params))
        return achadas

    def test_a_varredura_enxerga_o_app_inteiro(self):
        """Controle, antes de qualquer asserção de ausência: varredura vazia
        satisfaz "todo parâmetro está classificado" sem olhar rota nenhuma.
        Foi exatamente o que aconteceu com `app.routes` no FastAPI 0.141."""
        rotas = self._rotas_com_params()

        assert len(rotas) > 50, f"a varredura só enxergou {len(rotas)} rotas com parâmetro: {rotas[:5]}"

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
        """E todas elas passam pelo mascarador de fato.

        O nome do parâmetro sai da rota, nunca do literal `token`: escrito à
        mão, este teste aprovaria em falso o dia em que o segredo se chamasse
        outra coisa (o `replace` não trocaria nada, a saída seria igual ao
        template e as duas asserções passariam sem exercitar o mascarador),
        justamente no passo em que alguém classifica o parâmetro novo no teste e
        esquece de `_PARAMS_DE_SEGREDO`."""
        rotas = [
            (caminho, [n for n in params if n in PARAMS_DE_SEGREDO]) for caminho, params in self._rotas_com_params()
        ]
        com_segredo = [(caminho, nomes) for caminho, nomes in rotas if nomes]
        assert com_segredo, "nenhuma rota com segredo: a varredura não enxergou o app"

        for caminho, nomes in com_segredo:
            concreto = caminho
            path_params = {}
            for nome in nomes:
                concreto = concreto.replace("{" + nome + "}", TOKEN)
                path_params[nome] = TOKEN
            assert TOKEN in concreto, f"{caminho}: o parâmetro {nomes} não entrou no path de teste"

            saida = path_para_log({"path": concreto, "path_params": path_params})

            assert TOKEN not in saida, f"{caminho} não é mascarada"
            assert saida == caminho

    def test_nenhuma_rota_do_app_se_esconde_do_schema(self):
        """A varredura lê o schema OpenAPI, então rota com
        `include_in_schema=False` sairia da rede sem nada ficar vermelho.

        Hoje o app não tem nenhuma. Esta trava é o que garante que a fonte da
        varredura continua completa: quem esconder uma rota do schema tem que
        passar por aqui e resolver a cobertura antes."""
        fonte = list(Path(__file__).resolve().parents[1].joinpath("app").rglob("*.py"))
        assert len(fonte) > 20, "a varredura do fonte não achou o pacote app"

        escondidas = [
            f"{arquivo.name}:{numero}"
            for arquivo in fonte
            for numero, linha in enumerate(arquivo.read_text().splitlines(), start=1)
            if "include_in_schema=False" in linha.replace(" ", "")
        ]

        assert not escondidas, (
            f"rota fora do schema em {escondidas}: a varredura de segredo no path lê `app.openapi()` e "
            "não enxerga rota escondida (issue #465)."
        )
