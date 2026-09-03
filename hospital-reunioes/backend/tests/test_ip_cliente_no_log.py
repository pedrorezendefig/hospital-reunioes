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
import re
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.dependencies.utils import get_flat_dependant
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# O parse do CMD já existe no arquivo irmão do contrato de proxy (issue #349).
# Reaproveitado em vez de virar a terceira cópia do mesmo loop.
from test_proxy_confiavel import _cmd_do_dockerfile  # noqa: E402

from app.middleware.request_context import (  # noqa: E402
    JsonFormatter,
    RequestContextMiddleware,
    _e_canal_anonimo_da_ouvidoria,
)

_DOCKERFILE = Path(__file__).resolve().parents[1] / "Dockerfile"


def _faixas_confiaveis_do_dockerfile() -> list[str]:
    """A lista de confiança que PRODUÇÃO usa, lida da flag do CMD.

    Escrita à mão aqui, ela montaria o `ProxyHeadersMiddleware` do teste com uma
    configuração que o container não tem, e o teste passaria a medir uma app
    imaginária: trocar a flag por `*` ligaria `always_trust` no uvicorn (o
    `get_trusted_client_host` passa a devolver `hosts[0]`, que é a ponta que o
    CLIENTE escreveu, porque o Traefik appenda o IP real no FIM), e os testes de
    recusa continuariam verdes em cima de forja total do campo de auditoria.

    Lendo a flag, o mutante no `Dockerfile` chega até aqui e fica vermelho.
    """
    for parte in _cmd_do_dockerfile():
        if parte.startswith("--forwarded-allow-ips="):
            return parte.removeprefix("--forwarded-allow-ips=").split(",")
    raise AssertionError("CMD do Dockerfile sem --forwarded-allow-ips")


FAIXAS_CONFIAVEIS = _faixas_confiaveis_do_dockerfile()

IP_PUBLICO_DO_VISITANTE = "203.0.113.9"
IP_FORJADO = "198.51.100.77"
IP_DO_PROXY_INTERNO = "10.1.2.3"
# Outro endereço da rede privada, para a cadeia em que TODOS os saltos são
# confiáveis.
IP_INTERNO_VIZINHO = "172.18.0.5"


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
    decide.

    A rota curinga no fim deixa exercitar QUALQUER path pelo seam HTTP (o
    middleware só lê `scope["path"]`), inclusive os do canal público da
    Ouvidoria, sem subir banco nem router de verdade. Quem amarra o path do
    teste ao path que a app monta de fato é `TestOCanalAnonimoEstaTodoCoberto`,
    que varre o schema do app real."""
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)

    @app.get("/api/qualquer")
    async def _qualquer():
        return {"ok": True}

    @app.api_route("/{resto:path}", methods=["GET", "POST"])
    async def _curinga(resto: str):
        return {"ok": True}

    return app


def _chamar(
    *,
    caminho: str = "/api/qualquer",
    metodo: str = "GET",
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
        cliente.request(metodo, caminho, headers=headers or {})
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

    # O CONJUNTO de chaves, e não só a presença de cada uma: este PR abre o
    # precedente de campo novo no `extra`, e conferir presença deixaria passar
    # verde o campo de amanhã (um `"auth": request.headers.get(...)` não
    # apareceria em teste nenhum, porque nenhuma requisição de teste manda
    # Authorization e o detector do token procura só a string do fixture).
    # `user_id` entra nesta lista quando há sessão: aqui não há.
    assert set(linha) == {
        "timestamp",
        "level",
        "logger",
        "message",
        "request_id",
        "path",
        "method",
        "client_ip",
        "status_code",
        "latency_ms",
    }, sorted(linha)


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


class TestCaminhoDeProducao:
    """Em produção o peer é SEMPRE o Traefik, e o header SEMPRE é lido.

    Os testes de recusa acima usam peer público, e com peer público o
    `ProxyHeadersMiddleware` nem entra no `if client_host in self.trusted_hosts`:
    o servidor descarta o header antes de escolher coisa nenhuma. Eles provam
    que a app não lê o header, e não provam nada sobre a ESCOLHA do valor
    dentro da cadeia, que é o que roda em toda requisição real.

    A escolha é do uvicorn (`get_trusted_client_host`): ele varre a cadeia da
    DIREITA para a esquerda e devolve o primeiro salto não confiável, porque
    cada proxy appenda no fim. O que o cliente escreve entra pela esquerda, e
    por isso perde.
    """

    def test_a_cadeia_forjada_perde_para_o_salto_que_o_traefik_appendou(self):
        """O caminho de produção do canal público, com o header sendo lido.

        O visitante manda a cadeia já montada para escolher qual ponta o
        servidor lê. O Traefik appenda o IP real no fim, e é ele que fica."""
        linha = _chamar(
            peer=(IP_DO_PROXY_INTERNO, 55000),
            headers={"X-Forwarded-For": f"{IP_FORJADO}, {IP_PUBLICO_DO_VISITANTE}"},
            com_proxy_headers=True,
        )

        assert linha["client_ip"] == IP_PUBLICO_DO_VISITANTE, linha
        assert IP_FORJADO not in json.dumps(linha), f"a ponta forjada venceu: {linha}"

    def test_valor_privado_semeado_pelo_visitante_nao_vira_o_ip_da_linha(self):
        """A tentativa de cair no fallback de cadeia toda confiável.

        Semear `10.0.0.1` não funciona pelo canal público justamente porque o
        Traefik appenda o endereço real depois: a cadeia deixa de ser toda
        privada, e a varredura da direita acha o salto público."""
        linha = _chamar(
            peer=(IP_DO_PROXY_INTERNO, 55000),
            headers={"X-Forwarded-For": f"10.0.0.1, {IP_PUBLICO_DO_VISITANTE}"},
            com_proxy_headers=True,
        )

        assert linha["client_ip"] == IP_PUBLICO_DO_VISITANTE, linha

    def test_cadeia_toda_privada_carimba_a_ponta_esquerda_e_isso_e_conhecido(self):
        """O fallback do uvicorn, cravado como comportamento conhecido.

        Quando TODOS os saltos são confiáveis, `get_trusted_client_host` não
        acha salto não confiável e cai em `return hosts[0]`: o valor que o
        emissor escolheu. Quem alcança isso já está DENTRO da rede privada
        (outro container, healthcheck, alguém na rede interna), e não o
        visitante do portal público, que sempre ganha o salto do Traefik no fim.

        Cravado como asserção, e não como comentário, para que a mudança desse
        fallback num upgrade do uvicorn apareça aqui em vez de virar um campo de
        auditoria escolhido pelo emissor sem ninguém notar."""
        linha = _chamar(
            peer=(IP_DO_PROXY_INTERNO, 55000),
            headers={"X-Forwarded-For": f"10.0.0.1, {IP_INTERNO_VIZINHO}"},
            com_proxy_headers=True,
        )

        assert linha["client_ip"] == "10.0.0.1", linha


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
    campo faltando.

    Manda `X-Forwarded-For` de propósito: sem header nenhum, este teste provaria
    ausência de ERRO e não ausência de HEADER, e um `return
    request.headers.get("x-forwarded-for", "")` no lugar do `return ""` passaria
    verde."""
    linha = _chamar(apagar_peer=True, headers={"X-Forwarded-For": IP_FORJADO})

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


# ---------------------------------------------------------------------------
# O canal público da Ouvidoria: log guarda a rede, não o endereço (issue #543)
# ---------------------------------------------------------------------------

MANIFESTACOES = "/api/ouvidoria/publico/manifestacoes"
PONTOS = "/api/ouvidoria/publico/pontos/ABC123"
QR = "/api/ouvidoria/qr"

# As rotas que qualquer um alcança sem apresentar credencial e mesmo assim NÃO
# truncam, classificadas uma a uma. Não há anonimato a proteger nelas: nenhuma
# registra ato de uma pessoa identificável pelo par IP e horário.
SEM_ANONIMATO_A_PROTEGER = {
    # Sonda de saúde do container, chamada pelo Docker e pelo Traefik.
    "/api/health",
    # Callback servidor a servidor da ClickSign, não é visitante.
    "/api/webhooks/clicksign",
}

IPV4_DO_MANIFESTANTE = "187.45.12.203"
IPV4_TRUNCADO = "187.45.12.0"
IPV6_DO_MANIFESTANTE = "2001:db8:abcd:1234::5"
IPV6_TRUNCADO = "2001:db8:abcd::"


class TestIpTruncadoNoCanalPublicoDaOuvidoria:
    """Manifestação anônima não pode ser reidentificada pelo log.

    Uma linha 201 em `POST /api/ouvidoria/publico/manifestacoes` É uma
    manifestação criada. Com o IP cheio e o timestamp, quem lê o stdout do
    container (sem perfil nenhum na Ouvidoria, que é a população que a issue
    #465 nomeou como ameaça) liga a manifestação anônima à origem, e fora do
    NAT do hospital (celular, casa) o IP individualiza via ISP. IP é dado
    pessoal (LGPD art. 5, I).

    Mesmo espírito da decisão 5 da issue #375, que tirou o ponto do cartaz do
    registro anônimo: em sala pequena, "Poltrona 12" naquele dia identifica a
    pessoa.

    O campo NÃO é removido: a rastreabilidade grossa de abuso (spam, flood no
    canal sem login) continua, porque a rede continua na linha. O que sai é a
    individualização.
    """

    def test_o_ipv4_do_manifestante_entra_truncado_na_rede(self):
        """O valor EXATO do campo, e não a ausência do IP cheio: um código que
        parasse de logar IP nenhum passaria num teste de ausência."""
        linha = _chamar(caminho=MANIFESTACOES, metodo="POST", peer=(IPV4_DO_MANIFESTANTE, 44321))

        assert linha["client_ip"] == IPV4_TRUNCADO, linha

    def test_o_ipv6_do_manifestante_entra_truncado_no_prefixo_de_rede(self):
        """IPv6 tem espaço de sobra para individualizar no sufixo (o interface
        identifier é do aparelho), então o corte é no /48."""
        linha = _chamar(caminho=MANIFESTACOES, metodo="POST", peer=(IPV6_DO_MANIFESTANTE, 44321))

        assert linha["client_ip"] == IPV6_TRUNCADO, linha

    def test_o_qr_do_cartaz_impresso_tambem_trunca(self):
        """A porta de entrada do fluxo, e o furo que anulava o resto.

        `/api/ouvidoria/qr` é o destino do cartaz impresso e não pede login. Com
        IP cheio aqui, a linha do QR e a linha truncada do
        `POST .../manifestacoes` saem na mesma /24 e a segundos de distância:
        quem lê o stdout junta as duas e recupera o endereço inteiro de quem
        manifestou. Truncar só a manifestação não protege ninguém."""
        linha = _chamar(caminho=QR, peer=(IPV4_DO_MANIFESTANTE, 44321))

        assert linha["client_ip"] == IPV4_TRUNCADO, linha

    def test_o_fluxo_do_cartaz_inteiro_sai_truncado(self):
        """O invariante que interessa é da SEQUÊNCIA, não de uma linha isolada:
        nenhuma das duas pontas do fluxo pode carregar o endereço cheio."""
        linhas = [
            _chamar(caminho=QR, peer=(IPV4_DO_MANIFESTANTE, 44321)),
            _chamar(caminho=MANIFESTACOES, metodo="POST", peer=(IPV4_DO_MANIFESTANTE, 44321)),
        ]

        for linha in linhas:
            assert IPV4_DO_MANIFESTANTE not in json.dumps(linha), linha
            assert linha["client_ip"] == IPV4_TRUNCADO, linha

    def test_a_consulta_do_ponto_do_cartaz_tambem_trunca(self):
        """A outra rota do mesmo canal anônimo: quem lê o cartaz e não
        manifesta também não precisa ficar identificado no log."""
        linha = _chamar(caminho=PONTOS, peer=(IPV4_DO_MANIFESTANTE, 44321))

        assert linha["client_ip"] == IPV4_TRUNCADO, linha

    def test_fora_do_canal_publico_o_ip_continua_cheio(self):
        """O contrapeso, e o mutante 2 do checkpoint: truncar tudo mataria a
        investigação de abuso nas rotas internas, que é o motivo da issue.

        Aqui existe sessão autenticada e não há anonimato a proteger."""
        linha = _chamar(caminho="/api/reunioes", peer=(IPV4_DO_MANIFESTANTE, 44321))

        assert linha["client_ip"] == IPV4_DO_MANIFESTANTE, linha

    def test_o_portal_do_setor_nao_e_o_canal_anonimo(self):
        """`/api/ouvidoria-setor/...` mora ao lado no nome e NÃO é o canal
        anônimo: é o setor respondendo por link com token, e é justamente onde
        rastrear origem importa. Prefixo solto (`/api/ouvidoria`) pegaria esta
        rota junto."""
        linha = _chamar(caminho="/api/ouvidoria-setor/abc123", peer=(IPV4_DO_MANIFESTANTE, 44321))

        assert linha["client_ip"] == IPV4_DO_MANIFESTANTE, linha

    @pytest.mark.parametrize(
        "caminho",
        [
            "/api/ouvidoria/publicoXYZ",
            "/api/ouvidoria/publico-interno/relatorio",
            "/api/ouvidoria/publicos",
        ],
    )
    def test_rota_que_so_parece_publica_nao_trunca(self, caminho):
        """O casamento é por segmento, não por `startswith` cru: truncar de
        mais aqui seria perder rastreio numa rota interna sem ninguém notar."""
        linha = _chamar(caminho=caminho, peer=(IPV4_DO_MANIFESTANTE, 44321))

        assert linha["client_ip"] == IPV4_DO_MANIFESTANTE, linha

    @pytest.mark.parametrize(
        "caminho",
        [
            "/api/ouvidoria//publico/manifestacoes",
            "/API/Ouvidoria/Publico/manifestacoes",
        ],
    )
    def test_path_deformado_nao_escapa_do_truncamento(self, caminho):
        """Barra repetida é forma válida de path e caixa diferente casa a mesma
        rota no proxy. As duas furaram a rede do 404 na issue #465, e aqui o
        estrago seria o IP cheio do manifestante anônimo no log."""
        linha = _chamar(caminho=caminho, metodo="POST", peer=(IPV4_DO_MANIFESTANTE, 44321))

        assert linha["client_ip"] == IPV4_TRUNCADO, linha

    @pytest.mark.parametrize(
        "caminho",
        [
            "//api/ouvidoria/publico/manifestacoes",
            "/api//ouvidoria/publico/manifestacoes",
        ],
    )
    def test_barra_repetida_no_inicio_do_prefixo_tambem_trunca(self, caminho):
        """Contra a função, e não pelo seam HTTP, pelo mesmo motivo que o
        arquivo irmão registra em `PATHS_COM_BARRA_REPETIDA`: o httpx lê
        `//api/...` como URL relativa a esquema (o `api` vira HOST) e o path
        nunca chega assim ao servidor. Essa forma só aparece vinda direto do
        scope (proxy, redirect montado à mão, cliente que não normaliza)."""
        assert _e_canal_anonimo_da_ouvidoria(caminho)

    def test_endereco_que_o_ipaddress_rejeita_nao_derruba_o_log(self):
        """O middleware roda em 100% do tráfego e a linha é escrita no
        `finally`: explodir no truncamento trocaria um campo por falha no log
        de toda requisição do canal público.

        O texto inválido também não é ecoado de volta: nesse canal o valor é,
        no pior caso, texto de origem não confiável."""
        linha = _chamar(caminho=MANIFESTACOES, metodo="POST", peer=("nao-e-um-ip", 44321))

        assert linha["client_ip"] == "", linha
        assert linha["status_code"] == 200

    def test_sem_peer_no_canal_publico_tambem_nao_derruba(self):
        linha = _chamar(caminho=MANIFESTACOES, metodo="POST", apagar_peer=True)

        assert linha["client_ip"] == "", linha


class TestOCanalAnonimoEstaTodoCoberto:
    """A trava contra a rota anônima de amanhã, ancorada em QUEM PODE ENTRAR.

    A primeira versão desta varredura filtrava por `"/publico" in path`, e isso
    não guardava nada: só acordava para rota que já se chamasse `/publico`, que
    é exatamente o caso que o prefixo literal já cobria. Foi assim que
    `/api/ouvidoria/qr` (o destino do cartaz impresso, sem login) passou batido
    e ficou gravando IP cheio ao lado da manifestação truncada, na mesma /24 e
    na mesma janela de tempo: quem lê o stdout junta as duas linhas e recupera o
    endereço inteiro, anulando o truncamento no fluxo que o QR existe para
    servir.

    A pergunta certa não é "o path tem a palavra publico", é "esta rota exige
    credencial de alguém". As duas camadas abaixo perguntam isso: uma ancorada
    no router sem login, outra no app inteiro.
    """

    @staticmethod
    def _nomes_das_dependencias(rota: APIRoute) -> set[str]:
        nomes: set[str] = set()

        def anda(dependencia) -> None:
            if dependencia.call is not None:
                nomes.add(getattr(dependencia.call, "__name__", str(dependencia.call)))
            for sub in dependencia.dependencies:
                anda(sub)

        anda(rota.dependant)
        for sub in get_flat_dependant(rota.dependant, skip_repeats=False).dependencies:
            anda(sub)
        return nomes

    @classmethod
    def _rotas_sem_credencial(cls) -> list[tuple[str, str]]:
        """As rotas que qualquer um alcança sem apresentar NADA.

        Fora daqui ficam as que pedem sessão (`get_current_user`), chave de API
        (`require_ana_api_key`) e as que carregam segredo no próprio path (o
        portal do setor e o Aceite): lá quem chega já provou ser alguém
        convidado, e é onde rastrear origem importa."""
        from app.main import app

        achadas = []
        for rota in app.routes:
            if not isinstance(rota, APIRoute):
                continue
            # Só rota que a APP monta. `tests/test_handler_global_excecao.py`
            # registra `/api/_teste_excecao_nao_tratada` no app real na hora do
            # import, e ela existe apenas debaixo do pytest: sem este filtro a
            # varredura acusa rota que não vai para produção, e o vermelho passa
            # a depender da ORDEM dos arquivos de teste.
            if not getattr(rota.endpoint, "__module__", "").startswith("app."):
                continue
            nomes = cls._nomes_das_dependencias(rota)
            if {"get_current_user", "require_ana_api_key"} & nomes:
                continue
            if re.findall(r"\{([^}:]+)", rota.path) and set(re.findall(r"\{([^}:]+)", rota.path)) & {"token"}:
                continue
            achadas.append((sorted(rota.methods)[0], rota.path))
        return sorted(achadas)

    def test_a_varredura_enxerga_o_app_inteiro(self):
        """Controle antes de qualquer asserção de cobertura: varredura vazia
        satisfaz "toda rota anônima está coberta" sem olhar rota nenhuma."""
        from app.main import app

        assert sum(1 for r in app.routes if isinstance(r, APIRoute)) > 150

    def test_toda_rota_do_router_sem_login_e_truncada(self):
        """Camada 1, ancorada no ROUTER, e não no nome do path.

        Rota nova no router público entra coberta sozinha, chame-se ela
        `/aberto/...`, `/manifestacoes-anonimas` ou qualquer outra coisa."""
        from app.config import settings
        from app.routers import ouvidoria_publica

        # `rota.path` já traz o prefixo do próprio router (`/ouvidoria/qr`);
        # só falta o prefixo com que o `main` monta o router (`/api`).
        caminhos = [
            f"{settings.api_prefix}{rota.path}"
            for rota in ouvidoria_publica.router.routes
            if isinstance(rota, APIRoute)
        ]

        assert len(caminhos) >= 3, f"o router sem login encolheu: {caminhos}"
        for caminho in caminhos:
            assert _e_canal_anonimo_da_ouvidoria(caminho), (
                f"{caminho} é rota do router SEM LOGIN e não seria truncada (issue #543)"
            )

    def test_toda_rota_sem_credencial_do_app_esta_classificada(self):
        """Camada 2, o app inteiro: pega a rota anônima montada em outro router.

        Rota que qualquer um alcança sem apresentar nada tem que estar truncada
        OU declarada aqui como sem anonimato a proteger. Rota nova fora das duas
        listas fica vermelha, que é o ponto: a classificação é humana."""
        nao_classificadas = [
            (metodo, caminho)
            for metodo, caminho in self._rotas_sem_credencial()
            if not _e_canal_anonimo_da_ouvidoria(caminho) and caminho not in SEM_ANONIMATO_A_PROTEGER
        ]

        assert not nao_classificadas, (
            f"rota sem credencial não classificada: {nao_classificadas}. "
            "Diga se ela é canal anônimo (o IP vai truncado, issue #543) ou se não há "
            "anonimato a proteger nela, antes de seguir."
        )

    def test_o_qr_do_cartaz_esta_entre_as_rotas_sem_credencial(self):
        """Controle do filtro da camada 2: se ele parasse de enxergar as rotas
        anônimas (dependência renomeada, `APIRoute` trocada), a asserção de
        cima passaria vazia e a trava morreria em silêncio."""
        caminhos = [caminho for _metodo, caminho in self._rotas_sem_credencial()]

        assert "/api/ouvidoria/qr" in caminhos, caminhos
        assert "/api/ouvidoria/publico/manifestacoes" in caminhos, caminhos
        assert "/api/reunioes" not in caminhos, "rota autenticada vazou para a lista de anônimas"

    def test_o_portal_do_setor_e_o_aceite_ficam_fora_do_truncamento(self):
        """O contrapeso, dito na varredura e não só nos testes de unidade: quem
        chega com token no path já provou ser o convidado, e ali rastrear a
        origem é o que se quer."""
        for caminho in ("/api/ouvidoria-setor/abc", "/api/aceite/abc", "/api/reunioes", "/api/health"):
            assert not _e_canal_anonimo_da_ouvidoria(caminho), caminho
