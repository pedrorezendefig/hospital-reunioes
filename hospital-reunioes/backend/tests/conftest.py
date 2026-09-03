"""Trava de rede da suíte inteira (issue #546, PRD #471).

O pytest deste backend carrega o `.env` REAL. Nele há usuário e senha de SMTP
do Gmail, chave da ClickSign e chave do OpenRouter: um teste que esqueça de
mockar o transporte não estoura, ele CONVERSA com o serviço de verdade. Foi o
que aconteceu na #494 (PR #545), onde quatro testes abriam conexão para
`smtp.gmail.com:587` sem ninguém perceber, e a suíte daquele arquivo caía de
8 segundos para 1 quando alguém trancava a porta.

A trava daquela vez ficou DENTRO do arquivo de teste, e por isso protegia o
arquivo e mais nada: o arquivo irmão da #493 seguiu sem trava e todo arquivo
novo nascia sem proteção. Aqui ela é de repositório, e sobretudo é de SESSÃO:
sobe em `pytest_configure`, antes da coleta, e fica de pé até o fim. Uma trava
`autouse` de escopo `function` deixaria três portas abertas, todas com o teste
VERDE: rede em tempo de import, rede dentro de fixture `scope="module"` e
dentro de fixture `scope="session"` (o repo já usa `scope="class"` em
`test_ouvidoria_revoke_rpc.py`, então não é hipótese de laboratório: basta um
arquivo novo montar o cliente do Resend numa fixture cara e compartilhada).

Três escolhas de projeto que parecem detalhe e não são:

1. **A trava FALHA o teste, não silencia a chamada.** Silenciar devolveria
   sucesso para um envio que não aconteceu, que é exatamente o defeito que a
   issue #435 já custou caro em produção. A mensagem diz o host, a porta e o
   que fazer.

2. **A exceção herda de `BaseException`, não de `Exception`.** O código que
   fala com o mundo lá fora é justamente o que envolve tudo em `except
   Exception`: `email_service._enviar_via_smtp`, `_enviar_via_resend` e o
   próprio SDK do Resend engolem qualquer `Exception` e devolvem `False` ou um
   `ResendError`. Uma trava que herdasse de `Exception` seria capturada por
   eles, o teste ficaria verde e a tentativa de rede continuaria invisível, que
   é o pior dos mundos: guarda que existe e não guarda.

3. **A isenção é hook, não fixture.** Fixture `autouse` pode ser desligada por
   qualquer módulo que declare outra com o mesmo nome, e aí a lista `EXCECOES`
   deixaria de ser a única porta. Ligar e desligar a trava é decisão do
   `conftest.py`, e o arquivo de teste não vota.

O que a trava fecha, exatamente: `socket.create_connection`,
`socket.socket.connect`, `connect_ex`, `sendto` e `sendmsg` (o UDP sai sem
`connect` nenhum), `socket.getaddrinfo`, `socket.gethostbyname` e
`gethostbyname_ex`. É o chão por onde `smtplib`, `requests` (transporte
síncrono do SDK do Resend), `httpx`, `urllib`, `asyncio` e o cliente do
Supabase passam. O que NÃO passa pelo módulo `socket` do processo (um
`subprocess` chamando `curl`, por exemplo) está fora do alcance desta trava, e
não há como fingir o contrário.

Loopback continua liberado de propósito. A suíte roda contra o Supabase local
em `127.0.0.1` e o `TestClient` do FastAPI é in-process; uma trava que também
fechasse essa porta não seria segurança, seria indisponibilidade.
"""

from __future__ import annotations

import ipaddress
import socket

import pytest

# Escape hatch, no estilo da lista `EXCECOES` do guard de leitura direta
# (issue #492): isenção é por ARQUIVO, escrita à mão aqui, e é a ÚNICA porta
# (ver decisão 3 no topo). O nome é o do arquivo de teste, sem o `.py`.
#
# A isenção vale enquanto o teste roda. O import do módulo continua trancado
# para todo mundo, inclusive para quem está nesta lista: import que fala com o
# mundo lá fora acontece na coleta, longe de qualquer teste, e ninguém liga
# uma tentativa dessas ao arquivo que a causou.
#
# Antes de acrescentar um nome: teste que precisa de rede de verdade quase
# sempre é teste que precisa de dublê. A isenção existe para o caso legítimo
# (hoje, apenas o arquivo que a própria trava gera para provar que a isenção
# funciona), e cada entrada nova merece uma linha dizendo por quê.
EXCECOES: frozenset[str] = frozenset(
    {
        # Gerado e apagado por `test_trava_de_rede.py`. É a contraprova da
        # isenção: sem ele, ninguém saberia se o escape hatch ainda funciona.
        "test_gerado_isento_da_trava_de_rede",
    }
)


class TentativaDeRedeNoTeste(BaseException):
    """Um teste tentou sair da máquina. Ver o docstring do módulo para o
    motivo de herdar de `BaseException`."""


def _host_do_destino(destino: object) -> str | None:
    """O host de um endereço de socket, ou `None` quando o destino não sai da
    máquina (AF_UNIX, que é caminho de arquivo, e o que mais não for tupla)."""
    if not isinstance(destino, tuple) or not destino:
        return None
    return _nome_limpo(destino[0])


def _nome_limpo(host: object) -> str | None:
    if isinstance(host, bytes):
        host = host.decode("utf-8", "replace")
    if not isinstance(host, str):
        return None
    # `fe80::1%lo0` e `[::1]` chegam assim de alguns caminhos do stdlib.
    return host.strip("[]").partition("%")[0]


def _porta_do_destino(destino: object) -> object:
    return destino[1] if isinstance(destino, tuple) and len(destino) > 1 else "?"


def _e_loopback(host: str) -> bool:
    if host in ("", "localhost"):
        return True
    if host.endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        # Nome que ainda não foi resolvido: para a trava, nome é destino de
        # fora. Quem fala com o serviço local usa `localhost` ou o IP.
        return False


def _mensagem(host: str, porta: object) -> str:
    return (
        f"Este teste tentou falar com {host}:{porta}. Mocke o transporte "
        "(o `.env` desta máquina tem credencial de verdade, então a chamada "
        "sairia mesmo). A trava vive em tests/conftest.py; se o teste precisa "
        "MESMO de rede, acrescente o arquivo à lista EXCECOES de lá."
    )


def _guardar(destino: object) -> None:
    host = _host_do_destino(destino)
    if host is not None and not _e_loopback(host):
        raise TentativaDeRedeNoTeste(_mensagem(host, _porta_do_destino(destino)))


def _guardar_nome(host: object, porta: object) -> None:
    """A resolução também fica trancada, por dois motivos. O primeiro é a
    mensagem: o `urllib3` (transporte síncrono do SDK do Resend) resolve o nome
    sozinho e só depois chama `connect` com o IP, então sem esta porta o erro
    diria "104.18.x.x" em vez de "api.resend.com". O segundo é que a consulta
    de DNS já é um pacote saindo da máquina, com o nome do serviço dentro."""
    nome = _nome_limpo(host)
    if nome is not None and not _e_loopback(nome):
        raise TentativaDeRedeNoTeste(_mensagem(nome, porta))


# Os originais, guardados enquanto a trava está de pé. Dicionário vazio
# significa trava desinstalada, e é o que o `_instalada()` responde.
_REAIS: dict[str, object] = {}


def _instalada() -> bool:
    return bool(_REAIS)


def _instalar() -> None:
    if _instalada():
        return
    _REAIS.update(
        {
            "create_connection": socket.create_connection,
            "connect": socket.socket.connect,
            "connect_ex": socket.socket.connect_ex,
            "sendto": socket.socket.sendto,
            "sendmsg": socket.socket.sendmsg,
            "getaddrinfo": socket.getaddrinfo,
            "gethostbyname": socket.gethostbyname,
            "gethostbyname_ex": socket.gethostbyname_ex,
        }
    )

    def create_connection(address, *args, **kwargs):
        _guardar(address)
        return _REAIS["create_connection"](address, *args, **kwargs)

    def connect(self, address):
        _guardar(address)
        return _REAIS["connect"](self, address)

    def connect_ex(self, address):
        # Também levanta: `connect_ex` devolve errno em vez de estourar, e um
        # errno silencioso é o mesmo silêncio que esta trava existe para acabar.
        _guardar(address)
        return _REAIS["connect_ex"](self, address)

    def sendto(self, *args):
        # UDP não faz `connect`: o destino viaja no último argumento, tanto em
        # `sendto(dados, destino)` quanto em `sendto(dados, flags, destino)`.
        if len(args) >= 2:
            _guardar(args[-1])
        return _REAIS["sendto"](self, *args)

    def sendmsg(self, buffers, ancdata=None, flags=0, address=None):
        _guardar(address)
        return _REAIS["sendmsg"](self, buffers, ancdata or [], flags, address)

    def getaddrinfo(host, port, *args, **kwargs):
        _guardar_nome(host, port)
        return _REAIS["getaddrinfo"](host, port, *args, **kwargs)

    def gethostbyname(host):
        # `gethostbyname` não passa por `getaddrinfo`: é outro resolvedor, e
        # sem esta porta a consulta de DNS sairia da máquina.
        _guardar_nome(host, "53")
        return _REAIS["gethostbyname"](host)

    def gethostbyname_ex(host):
        _guardar_nome(host, "53")
        return _REAIS["gethostbyname_ex"](host)

    socket.create_connection = create_connection
    socket.socket.connect = connect
    socket.socket.connect_ex = connect_ex
    socket.socket.sendto = sendto
    socket.socket.sendmsg = sendmsg
    socket.getaddrinfo = getaddrinfo
    socket.gethostbyname = gethostbyname
    socket.gethostbyname_ex = gethostbyname_ex


def _desinstalar() -> None:
    if not _instalada():
        return
    socket.create_connection = _REAIS["create_connection"]
    socket.socket.connect = _REAIS["connect"]
    socket.socket.connect_ex = _REAIS["connect_ex"]
    socket.socket.sendto = _REAIS["sendto"]
    socket.socket.sendmsg = _REAIS["sendmsg"]
    socket.getaddrinfo = _REAIS["getaddrinfo"]
    socket.gethostbyname = _REAIS["gethostbyname"]
    socket.gethostbyname_ex = _REAIS["gethostbyname_ex"]
    _REAIS.clear()


def pytest_configure(config):
    """Sobe a trava ANTES da coleta, e não numa fixture de teste. É o que faz
    valer para rede em tempo de import e para fixture de escopo maior que o do
    teste."""
    _instalar()


def pytest_unconfigure(config):
    _desinstalar()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_protocol(item, nextitem):
    """A isenção da lista `EXCECOES`, aplicada em volta do teste inteiro
    (setup, chamada e teardown)."""
    caminho = getattr(item, "path", None)
    if caminho is not None and caminho.stem in EXCECOES:
        _desinstalar()
        try:
            yield
        finally:
            _instalar()
    else:
        yield


@pytest.fixture
def sem_transporte_de_email(monkeypatch):
    """Põe o `email_service` no modo mock, sem provedor nenhum configurado.

    Isto NÃO é trava (a trava é a de cima, e é automática): é escolha de
    observação. O modo mock é o caminho de log mais falante do `email_service`,
    e é o que roda em produção quando a chave do Resend está vazia. Os testes
    que auditam o que sobra escrito no log pedem esta fixture de propósito;
    antes da #546 eles dependiam de uma versão `autouse` disto dentro do
    arquivo da #494, que protegia aquele arquivo e mais nada."""
    from app.services import email_service

    monkeypatch.setattr(email_service, "_resend_configurado", lambda: False)
    monkeypatch.setattr(email_service, "_smtp_configurado", lambda: False)
