"""O IP do cliente volta para a linha do `app.requests` (issue #543).

O PR #530 (issue #465) subiu o uvicorn com `--no-access-log`, porque o access
log tem handler próprio e `propagate=False` e escrevia o path CRU (com o token
do portal do setor) no mesmo stdout. Foi a correção certa, e levou junto a
única coisa que só o access log dava: o `client_addr`. Sem ele, ligar uma linha
de log a uma origem exige cruzar o log do Traefik por timestamp.

O campo entra lido de `request.client.host`, e nunca do header cru. O backend
sobe com `--proxy-headers --forwarded-allow-ips=<faixas privadas>`, então o
`ProxyHeadersMiddleware` do uvicorn já decidiu, ANTES da app, se o
`X-Forwarded-For` daquele peer vale: quem escolhe é a lista de confiança, não a
requisição. Ler o header aqui dentro devolveria ao cliente o poder de escrever
o próprio IP no log, que é o mesmo furo que a issue #349 fechou no rate limit.

Vale lembrar do NAT: o hospital inteiro sai por um IP só, e o campo serve para
separar tráfego de fora do de dentro, não para identificar uma pessoa.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.middleware.request_context import (  # noqa: E402
    JsonFormatter,
    RequestContextMiddleware,
)

_DOCKERFILE = Path(__file__).resolve().parents[1] / "Dockerfile"

# As faixas privadas do Dockerfile, que é onde mora a rede do Docker e o
# Traefik do Coolify.
FAIXAS_CONFIAVEIS = ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"]

IP_PUBLICO_DO_VISITANTE = "203.0.113.9"
IP_FORJADO = "198.51.100.77"
IP_DO_PROXY_INTERNO = "10.1.2.3"


class _CapturaJson(logging.Handler):
    """Formata na hora, com o JsonFormatter de produção: é a linha do container
    que está sob teste, e não o LogRecord cru."""

    def __init__(self) -> None:
        super().__init__()
        self.setFormatter(JsonFormatter())
        self.linhas: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.linhas.append(self.format(record))


def _app() -> FastAPI:
    """App mínima: o que se mede é o que o middleware grava, não o que a rota
    decide."""
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)

    @app.get("/api/qualquer")
    async def _qualquer():
        return {"ok": True}

    return app


def _chamar(
    *,
    peer: tuple[str, int] | None = (IP_PUBLICO_DO_VISITANTE, 44321),
    headers: dict[str, str] | None = None,
    com_proxy_headers: bool = False,
    apagar_peer: bool = False,
) -> dict:
    """Faz a requisição e devolve a linha de log do request, já em dict.

    `com_proxy_headers` envolve a app no mesmo middleware que o uvicorn monta
    com `--proxy-headers`, com a mesma lista de confiança do Dockerfile:
    é ele que decide se o `X-Forwarded-For` daquele peer vale.
    """
    alvo = _app()
    if com_proxy_headers:
        alvo = ProxyHeadersMiddleware(alvo, trusted_hosts=FAIXAS_CONFIAVEIS)
    if apagar_peer:
        alvo = _SemPeerNoScope(alvo)

    captura = _CapturaJson()
    logger = logging.getLogger("app.requests")
    nivel_anterior = logger.level
    logger.addHandler(captura)
    logger.setLevel(logging.INFO)
    try:
        cliente = TestClient(alvo, client=peer, raise_server_exceptions=False)
        cliente.get("/api/qualquer", headers=headers or {})
    finally:
        logger.removeHandler(captura)
        logger.setLevel(nivel_anterior)
    assert len(captura.linhas) == 1, f"esperava 1 linha de request, veio {captura.linhas}"
    return json.loads(captura.linhas[0])


class _SemPeerNoScope:
    """Simula o transporte que não informa peer (`scope["client"]` ausente).

    Não é hipótese de laboratório: socket de domínio unix e alguns servidores
    ASGI entregam scope sem `client`, e `request.client` volta `None`."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            scope = dict(scope)
            scope.pop("client", None)
        return await self.app(scope, receive, send)


def test_a_linha_do_request_carrega_o_ip_do_cliente():
    """CA: a linha do `app.requests` carrega o IP do cliente.

    É o campo que o `--no-access-log` levou junto, e o motivo da issue."""
    linha = _chamar()

    assert linha["client_ip"] == IP_PUBLICO_DO_VISITANTE, linha


def test_o_resto_do_sinal_de_operacao_continua_na_mesma_linha():
    """Controle: o IP entra ao lado do que já existia, e não no lugar.

    Um `extra` reescrito no lugar do antigo daria verde no teste de cima e
    apagaria path, método, status e latência da linha."""
    linha = _chamar()

    assert linha["path"] == "/api/qualquer"
    assert linha["method"] == "GET"
    assert linha["status_code"] == 200
    assert "latency_ms" in linha
    assert linha["request_id"], linha


def test_x_forwarded_for_forjado_nao_entra_no_log():
    """CA: o IP vem do Starlette, não do header cru.

    Sem `--proxy-headers` na frente (ou com o peer fora da lista de confiança),
    o header é só texto que o cliente escolheu. Ler `request.headers` aqui
    dentro deixaria qualquer visitante do portal público assinar a linha de log
    com o IP que quisesse, e apontar a investigação de abuso para um terceiro."""
    linha = _chamar(headers={"X-Forwarded-For": IP_FORJADO})

    assert linha["client_ip"] == IP_PUBLICO_DO_VISITANTE, linha
    assert IP_FORJADO not in json.dumps(linha), f"o header forjado vazou para o log: {linha}"


@pytest.mark.parametrize(
    "valor",
    [
        IP_FORJADO,
        f"{IP_FORJADO}, {IP_DO_PROXY_INTERNO}",
        f"{IP_DO_PROXY_INTERNO}, {IP_FORJADO}",
        "10.0.0.1",
    ],
)
def test_x_forwarded_for_de_origem_nao_confiavel_e_ignorado_mesmo_com_proxy_headers(valor):
    """CA, na montagem de produção: o `--proxy-headers` está lá, e ainda assim
    o header não vale, porque o peer é público.

    Inclusive o valor que finge vir da rede interna (`10.0.0.1`): quem decide é
    o endereço do socket, e não o conteúdo do header. As variações com lista
    cobrem o cliente que já manda uma cadeia montada para escolher qual ponta o
    servidor vai ler."""
    linha = _chamar(headers={"X-Forwarded-For": valor}, com_proxy_headers=True)

    assert linha["client_ip"] == IP_PUBLICO_DO_VISITANTE, linha
    assert IP_FORJADO not in json.dumps(linha), f"o header forjado vazou para o log: {linha}"


def test_x_forwarded_for_de_proxy_confiavel_e_o_ip_que_entra_no_log():
    """O outro lado do mesmo invariante, e o controle contra teste vácuo.

    Sem este, o campo poderia estar lendo o endereço do socket na mão (ou
    ignorando `X-Forwarded-For` sempre) e os testes de recusa ficariam verdes
    de graça, com o log carimbando o IP do Traefik em toda requisição de
    produção, que é justamente o que não serve para nada. Aqui o peer está na
    faixa privada, o `ProxyHeadersMiddleware` reescreve `scope["client"]`, e o
    valor resolvido tem que aparecer na linha."""
    linha = _chamar(
        peer=(IP_DO_PROXY_INTERNO, 55000),
        headers={"X-Forwarded-For": IP_PUBLICO_DO_VISITANTE},
        com_proxy_headers=True,
    )

    assert linha["client_ip"] == IP_PUBLICO_DO_VISITANTE, linha


def test_requisicao_sem_peer_no_scope_nao_derruba_o_log():
    """`request.client` volta `None` quando o transporte não informa peer.

    A linha do request é escrita no `finally` do middleware mais externo: um
    `AttributeError` ali viraria erro dentro do log de toda requisição, e não um
    campo faltando."""
    linha = _chamar(apagar_peer=True)

    assert linha["client_ip"] == "", linha
    assert linha["status_code"] == 200


def _dockerfile_em_prosa() -> str:
    """O comentário do Dockerfile como texto corrido, minúsculo.

    A frase procurada quebra no meio (`Nada se` / `# perde:`), então buscar a
    substring no arquivo cru é detector cego: passa verde com a frase inteira
    ainda lá. Aqui o `# ` de cada linha sai e o espaço em branco colapsa antes
    de comparar."""
    cru = _DOCKERFILE.read_text()
    sem_marca = " ".join(linha.strip().lstrip("#").strip() for linha in cru.splitlines())
    return " ".join(sem_marca.split()).lower()


def test_o_detector_le_o_comentario_que_justifica_a_flag():
    """Controle do detector, antes de qualquer asserção de ausência.

    Um `_dockerfile_em_prosa` que devolvesse vazio (arquivo movido, prefixo
    trocado) satisfaria "a frase não está lá" sem ler nada."""
    prosa = _dockerfile_em_prosa()

    assert "--no-access-log" in prosa
    assert "issue #465" in prosa


def test_o_dockerfile_nao_diz_mais_que_nada_se_perde():
    """CA: corrigir o comentário do `Dockerfile`.

    A justificativa do `--no-access-log` afirmava que nada se perdia, e o
    `client_addr` era exclusivo do access log. A frase é o que faz a próxima
    revisão parar de procurar, então ela não pode voltar."""
    prosa = _dockerfile_em_prosa()

    assert "nada se perde" not in prosa
    assert "unica coisa exclusiva" not in prosa
