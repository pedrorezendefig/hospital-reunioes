"""Trava de rede da suíte inteira (issue #546, PRD #471).

O pytest deste backend carrega o `.env` REAL. Nele há usuário e senha de SMTP
do Gmail, chave da ClickSign e endereço de banco: um teste que esqueça de
mockar o transporte não estoura, ele CONVERSA com o serviço de verdade. Foi o
que aconteceu na #494 (PR #545), onde quatro testes abriam conexão para
`smtp.gmail.com:587` sem ninguém perceber, e a suíte daquele arquivo caía de
8 segundos para 1 quando alguém trancava a porta.

A trava daquela vez ficou DENTRO do arquivo de teste, e por isso protegia o
arquivo e mais nada: o arquivo irmão da #493 seguiu sem trava e todo arquivo
novo nascia sem proteção. Aqui ela é de repositório: mora no `conftest.py`, é
`autouse`, e por isso vale para o arquivo que alguém criar amanhã sem ler nada
disto.

Duas escolhas de projeto que parecem detalhe e não são:

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

Loopback continua liberado de propósito. A suíte roda contra o Supabase local
em `127.0.0.1` e o `TestClient` do FastAPI é in-process; uma trava que também
fechasse essa porta não seria segurança, seria indisponibilidade.
"""

from __future__ import annotations

import ipaddress
import socket

import pytest

# Escape hatch, no estilo da lista `EXCECOES` do guard de leitura direta
# (issue #492): isenção é por ARQUIVO, escrita à mão aqui, e não por um
# argumento que qualquer teste possa passar sozinho. O nome é o do módulo de
# teste, sem o `.py`.
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
    host = destino[0]
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


@pytest.fixture(autouse=True)
def sem_rede_externa(request, monkeypatch):
    """Fecha a saída de rede para fora de loopback durante o teste.

    Fecha no chão do stack (`socket`), e não em cada biblioteca: `smtplib`,
    `requests` (o transporte síncrono do SDK do Resend), `httpx` e o cliente do
    Supabase terminam todos aqui. Cobrir biblioteca por biblioteca deixaria de
    fora a próxima que alguém adicionar."""
    if getattr(request.module, "__name__", "") in EXCECOES:
        yield
        return

    create_connection_real = socket.create_connection
    connect_real = socket.socket.connect
    connect_ex_real = socket.socket.connect_ex
    getaddrinfo_real = socket.getaddrinfo

    def _guardar(destino: object) -> None:
        host = _host_do_destino(destino)
        if host is not None and not _e_loopback(host):
            raise TentativaDeRedeNoTeste(_mensagem(host, _porta_do_destino(destino)))

    def create_connection(address, *args, **kwargs):
        _guardar(address)
        return create_connection_real(address, *args, **kwargs)

    def connect(self, address):
        _guardar(address)
        return connect_real(self, address)

    def connect_ex(self, address):
        # Também levanta: `connect_ex` devolve errno em vez de estourar, e um
        # errno silencioso é o mesmo silêncio que esta trava existe para acabar.
        _guardar(address)
        return connect_ex_real(self, address)

    def getaddrinfo(host, port, *args, **kwargs):
        # A resolução também fica trancada, por dois motivos. O primeiro é a
        # mensagem: o `urllib3` (transporte síncrono do SDK do Resend) resolve
        # o nome sozinho e só depois chama `connect` com o IP, então sem esta
        # porta o erro diria "104.18.x.x" em vez de "api.resend.com". O
        # segundo é que a consulta de DNS já é um pacote saindo da máquina, com
        # o nome do serviço dentro.
        nome = host.decode("utf-8", "replace") if isinstance(host, bytes) else host
        if isinstance(nome, str) and not _e_loopback(nome.strip("[]").partition("%")[0]):
            raise TentativaDeRedeNoTeste(_mensagem(nome, port))
        return getaddrinfo_real(host, port, *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", create_connection)
    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", connect_ex)
    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
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
