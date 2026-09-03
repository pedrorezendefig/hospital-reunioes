"""A trava de rede da suíte, provada (issue #546, PRD #471).

Testar uma trava tem uma armadilha própria: verificar que ela EXISTE não prova
nada. O que prova é ela pegar uma tentativa de rede de verdade, pelos caminhos
que os testes deste backend usariam sem querer, e continuar deixando passar o
que a suíte precisa.

São cinco coisas, e cada uma cobre um jeito de a trava ser inútil:

1. **As portas de saída do `socket` falham com mensagem acionável.** `smtplib`
   é o caminho que vazou na #494 (`.env` real, usuário e senha do Gmail,
   quatro testes abrindo conexão para `smtp.gmail.com:587`); `connect_ex`,
   `gethostbyname` e o `sendto` do UDP são os vizinhos que não estouram
   sozinhos e por isso passariam despercebidos;
2. **HTTP para host externo falha do mesmo jeito**, inclusive quando quem
   chama é o `email_service`, que envolve o envio inteiro num
   `except Exception`. Uma trava capturável ali deixaria o teste VERDE em cima
   de uma tentativa de rede: por isso a exceção herda de `BaseException`;
3. **loopback continua liberado**, e o `TestClient` continua de pé. Trava que
   derruba o que a suíte precisa não é segurança, é indisponibilidade;
4. **um arquivo de teste NOVO já nasce coberto, e não tem como se livrar.** É a
   razão de a issue existir. O corpo do teste é a borda fácil; as outras três
   são rede em tempo de IMPORT e rede dentro de fixture `scope="module"` ou
   `scope="session"`, que uma trava de escopo `function` deixaria passar com o
   teste VERDE (e o repo já usa fixture de escopo maior em
   `test_ouvidoria_revoke_rpc.py`). A quinta borda é o arquivo que tenta
   desligar a trava declarando uma fixture homônima. O teste escreve os
   arquivos do zero e roda o pytest neles em outro processo, que é a única
   forma honesta de perguntar isso;
5. **o escape hatch ainda isenta**, provado no mesmo processo filho.
"""

from __future__ import annotations

import os
import smtplib
import socket
import subprocess
import sys
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from conftest import EXCECOES, TentativaDeRedeNoTeste  # noqa: E402

from app.services import email_service  # noqa: E402

DIR_DOS_TESTES = Path(__file__).parent

# Os arquivos que o teste das bordas escreve e apaga. O nome do isento é o que
# está na lista EXCECOES do conftest; os outros não são, e essa é a única
# diferença entre eles.
ARQUIVO_GUARDADO = DIR_DOS_TESTES / "test_gerado_pela_trava_de_rede.py"
ARQUIVO_IMPORT = DIR_DOS_TESTES / "test_gerado_rede_no_import.py"
ARQUIVO_SESSAO = DIR_DOS_TESTES / "test_gerado_fixture_de_sessao.py"
ARQUIVO_MODULO = DIR_DOS_TESTES / "test_gerado_fixture_de_modulo.py"
ARQUIVO_IMPOSTOR = DIR_DOS_TESTES / "test_gerado_fixture_impostora.py"
ARQUIVO_ISENTO_DO_MEIO = DIR_DOS_TESTES / "test_gerado_isento_do_meio.py"
ARQUIVO_DEPOIS_DO_ISENTO = DIR_DOS_TESTES / "test_gerado_depois_do_isento.py"
ARQUIVO_ISENTO = DIR_DOS_TESTES / "test_gerado_isento_da_trava_de_rede.py"

_CABECALHO = '"""Arquivo gerado por test_trava_de_rede.py. Se sobrou, pode apagar."""\n\n'

# Sem `pytest.raises` em nenhum deles: estes arquivos nascem agora e não sabem
# de nada. Se a trava não valer para eles, a chamada vai até o Gmail e o teste
# passa, e é o pai que reprova. Se valer, cada um reprova aqui, com a mensagem
# no relatório do processo filho.
CORPO_GUARDADO = (
    _CABECALHO
    + """import smtplib


def test_o_arquivo_recem_criado_ja_nasce_com_a_trava():
    smtplib.SMTP("smtp.gmail.com", 587, timeout=1)
"""
)

CORPO_IMPORT = (
    _CABECALHO
    + """import smtplib

# No nível do módulo: acontece na COLETA, antes de qualquer fixture de teste.
smtplib.SMTP("smtp.gmail.com", 587, timeout=1)


def test_nunca_deveria_ser_coletado():
    assert True
"""
)

CORPO_SESSAO = (
    _CABECALHO
    + '''import smtplib

import pytest


@pytest.fixture(scope="session", autouse=True)
def _cliente_caro_compartilhado():
    """O cenário concreto: setup caro montado uma vez por sessão."""
    smtplib.SMTP("smtp.gmail.com", 587, timeout=1)
    yield


def test_o_setup_de_sessao_nao_escapa():
    assert True
'''
)

CORPO_MODULO = (
    _CABECALHO
    + """import smtplib

import pytest


@pytest.fixture(scope="module", autouse=True)
def _cliente_caro_do_modulo():
    smtplib.SMTP("smtp.gmail.com", 587, timeout=1)
    yield


def test_o_setup_de_modulo_nao_escapa():
    assert True
"""
)

# A trava não é fixture, e este arquivo é a prova. Enquanto ela fosse uma
# fixture `autouse`, qualquer módulo desligaria a trava só declarando outra com
# o mesmo nome, e a lista EXCECOES deixaria de ser a única porta: a proteção
# passaria a depender de quem escreve o arquivo, que é justamente o que a issue
# veio consertar.
CORPO_IMPOSTOR = (
    _CABECALHO
    + '''import smtplib

import pytest


@pytest.fixture(autouse=True)
def sem_rede_externa():
    """Homônima da trava de antes, na tentativa de sobrescrevê-la."""
    yield


def test_declarar_a_fixture_homonima_nao_desliga_a_trava():
    smtplib.SMTP("smtp.gmail.com", 587, timeout=1)
'''
)

# A contraprova. `pytest.raises(OSError)` NÃO pega `TentativaDeRedeNoTeste`
# (que herda de `BaseException`), então este teste só passa se o socket for
# mesmo o de verdade: com a isenção quebrada, a trava estoura por fora do
# `raises` e o teste reprova. 192.0.2.1 é a faixa de documentação da RFC 5737,
# não roteada, e a porta 9 é a discard: não há serviço nenhum do outro lado.
CORPO_ISENTO = (
    _CABECALHO
    + """import socket

import pytest


def test_o_arquivo_da_lista_de_excecoes_fala_com_o_socket_de_verdade():
    with pytest.raises(OSError):
        socket.create_connection(("192.0.2.1", 9), timeout=0.05)
"""
)

# A dupla que prova a VOLTA da trava. O isento do meio fala com o socket de
# verdade; o de baixo, logo em seguida na fila, tem que continuar bloqueado.
# Sem esta dupla, a isenção poderia desligar a trava e nunca mais religar, e
# ninguém veria: hoje o único isento é o último arquivo da fila, então o
# estrago apareceria só no dia em que alguém puser um arquivo real na lista sem
# ser o último. É a falha silenciosa da #546 mudada de lugar.
CORPO_ISENTO_DO_MEIO = (
    _CABECALHO
    + """import socket

import pytest


def test_o_isento_do_meio_fala_com_o_socket_de_verdade():
    with pytest.raises(OSError):
        socket.create_connection(("192.0.2.1", 9), timeout=0.05)
"""
)

CORPO_DEPOIS_DO_ISENTO = (
    _CABECALHO
    + """import smtplib


def test_o_arquivo_seguinte_ao_isento_continua_guardado():
    smtplib.SMTP("smtp.gmail.com", 587, timeout=1)
"""
)

ARQUIVOS_GERADOS = {
    ARQUIVO_GUARDADO: CORPO_GUARDADO,
    ARQUIVO_IMPORT: CORPO_IMPORT,
    ARQUIVO_SESSAO: CORPO_SESSAO,
    ARQUIVO_MODULO: CORPO_MODULO,
    ARQUIVO_IMPOSTOR: CORPO_IMPOSTOR,
    ARQUIVO_ISENTO_DO_MEIO: CORPO_ISENTO_DO_MEIO,
    ARQUIVO_DEPOIS_DO_ISENTO: CORPO_DEPOIS_DO_ISENTO,
    ARQUIVO_ISENTO: CORPO_ISENTO,
}


class TestAsPortasDeSaida:
    """Cada porta do módulo `socket` por onde uma credencial do `.env` sairia."""

    def test_smtp_para_fora_falha_com_mensagem_acionavel(self):
        with pytest.raises(TentativaDeRedeNoTeste) as erro:
            smtplib.SMTP("smtp.gmail.com", 587, timeout=1)

        mensagem = str(erro.value)
        assert "smtp.gmail.com" in mensagem, "A mensagem não diz com quem o teste tentou falar"
        assert "587" in mensagem
        assert "Mocke o transporte" in mensagem, "A mensagem não diz o que fazer"
        assert "tests/conftest.py" in mensagem, "A mensagem não diz onde a trava mora"

    def test_a_trava_nao_silencia_o_envio(self):
        """A diferença entre falhar e silenciar. `_enviar_email` sem provedor
        configurado devolve `True` sem nada ter saído (modo mock, issue #435);
        uma trava que engolisse a chamada devolveria esse mesmo `True` com o
        provedor configurado, e o teste seguiria em frente achando que o email
        foi montado e entregue."""
        with pytest.raises(TentativaDeRedeNoTeste):
            smtplib.SMTP("smtp.gmail.com", 587, timeout=1)

    def test_connect_ex_para_fora_falha(self):
        """`connect_ex` é a porta silenciosa: devolve errno em vez de estourar,
        então quem a usa não repara em nada e a conexão sai igual."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        try:
            with pytest.raises(TentativaDeRedeNoTeste) as erro:
                sock.connect_ex(("smtp.gmail.com", 587))
        finally:
            sock.close()

        assert "smtp.gmail.com" in str(erro.value)

    def test_gethostbyname_para_fora_falha(self):
        """Resolver não é conectar, mas a consulta de DNS já é um pacote
        saindo da máquina com o nome do serviço dentro. E `gethostbyname` é
        outro resolvedor: não passa por `getaddrinfo`."""
        with pytest.raises(TentativaDeRedeNoTeste) as erro:
            socket.gethostbyname("api.resend.com")

        assert "api.resend.com" in str(erro.value)

    def test_udp_para_fora_falha(self):
        """UDP não faz `connect` nenhum: o pacote sai direto no `sendto`."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            with pytest.raises(TentativaDeRedeNoTeste) as erro:
                sock.sendto(b"ping", ("8.8.8.8", 53))
        finally:
            sock.close()

        assert "8.8.8.8" in str(erro.value)

    def test_udp_por_sendmsg_tambem_falha(self):
        """`sendmsg` é o irmão de `sendto` que ninguém lembra: mesmo pacote,
        outra função."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            with pytest.raises(TentativaDeRedeNoTeste) as erro:
                sock.sendmsg([b"ping"], [], 0, ("8.8.8.8", 53))
        finally:
            sock.close()

        assert "8.8.8.8" in str(erro.value)


class TestHTTPParaFora:
    def test_httpx_para_host_externo_falha(self):
        with pytest.raises(TentativaDeRedeNoTeste) as erro:
            httpx.get("https://api.clicksign.com/v1/documents", timeout=1)

        assert "api.clicksign.com" in str(erro.value)

    def test_o_cliente_do_resend_nao_escapa_pelo_except_exception(self, monkeypatch):
        """O teste que justifica a herança de `BaseException`.

        `_enviar_via_resend` envolve o envio inteiro em `except Exception`, e o
        próprio SDK do Resend faz o mesmo por dentro. Com uma trava capturável,
        estes dois `except` transformariam a tentativa de rede em
        `logger.error` + `return False`: teste verde, pacote saindo. Aqui o
        caminho é o do app, do `_enviar_email` até o transporte, e o que se
        exige é que a trava ATRAVESSE os dois."""
        monkeypatch.setattr(email_service, "_resend_configurado", lambda: True)
        monkeypatch.setattr(email_service.settings, "resend_api_key", "chave-de-teste", raising=False)

        with pytest.raises(TentativaDeRedeNoTeste) as erro:
            email_service._enviar_email("alguem@exemplo.com", "Assunto", "<p>html</p>", "texto")

        assert "resend.com" in str(erro.value), "A trava pegou, mas não sabe dizer com quem o teste falaria"


class TestOQueASuiteAindaPrecisa:
    """A outra metade da conta. A trava boa demais fecha o que a suíte usa e
    vira indisponibilidade: o Supabase local mora em 127.0.0.1 e a suíte
    inteira conversa com o `TestClient`."""

    def test_loopback_continua_permitido(self):
        servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        servidor.bind(("127.0.0.1", 0))
        # Backlog folgado: ninguém aceita as conexões deste teste, e com
        # backlog 1 a segunda ficaria esperando até estourar o timeout.
        servidor.listen(8)
        porta = servidor.getsockname()[1]
        try:
            with socket.create_connection(("127.0.0.1", porta), timeout=1):
                pass
            with socket.create_connection(("localhost", porta), timeout=1):
                pass
        finally:
            servidor.close()

        assert socket.gethostbyname("localhost") == "127.0.0.1"

    def test_o_testclient_continua_de_pe(self):
        app = FastAPI()

        @app.get("/ping")
        def _ping():
            return {"pong": True}

        with TestClient(app) as cliente:
            resposta = cliente.get("/ping")

        assert resposta.status_code == 200
        assert resposta.json() == {"pong": True}


def _estados_por_arquivo(saida: str) -> dict[str, str]:
    """Lê o resumo do processo filho e devolve {nome do arquivo: FAILED|ERROR}.

    Só entra aqui o que o pytest reprovou; arquivo que passou não aparece no
    resumo, e é assim que se pergunta pelo isento."""
    estados: dict[str, str] = {}
    for linha in saida.splitlines():
        for estado in ("FAILED", "ERROR"):
            if linha.startswith(f"{estado} "):
                caminho = linha.split()[1].split("::")[0]
                estados[Path(caminho).stem] = estado
    return estados


class TestArquivoNovoJaNasceCoberto:
    """O ponto da issue. A trava da #494 era `autouse` DENTRO de um arquivo:
    protegia aquele arquivo e mais nada, e o arquivo irmão da #493 seguiu sem
    proteção nenhuma. Sendo de repositório, a pergunta certa é sobre um arquivo
    que ainda não existe, e por todas as bordas por onde a rede sai dele."""

    def test_o_nome_do_arquivo_isento_esta_na_lista(self):
        """Guarda do próprio harness: se alguém renomear um dos lados, o teste
        de baixo passaria a medir outra coisa em silêncio."""
        assert ARQUIVO_ISENTO.stem in EXCECOES
        assert ARQUIVO_ISENTO_DO_MEIO.stem in EXCECOES
        for arquivo in (
            ARQUIVO_GUARDADO,
            ARQUIVO_IMPORT,
            ARQUIVO_SESSAO,
            ARQUIVO_MODULO,
            ARQUIVO_IMPOSTOR,
            ARQUIVO_DEPOIS_DO_ISENTO,
        ):
            assert arquivo.stem not in EXCECOES

        # A ordem importa: o arquivo guardado tem que rodar DEPOIS do isento,
        # senão o teste de baixo não pergunta nada sobre a volta da trava.
        fila = list(ARQUIVOS_GERADOS)
        assert fila.index(ARQUIVO_DEPOIS_DO_ISENTO) == fila.index(ARQUIVO_ISENTO_DO_MEIO) + 1

    def test_arquivo_novo_e_coberto_nas_cinco_bordas_e_so_a_lista_isenta(self):
        # Também antes de escrever: se um processo morreu no meio de uma
        # execução passada, o arquivo gerado sobrou em `tests/` e reprovaria a
        # suíte inteira de propósito até alguém apagar à mão.
        for arquivo in ARQUIVOS_GERADOS:
            arquivo.unlink(missing_ok=True)

        for arquivo, corpo in ARQUIVOS_GERADOS.items():
            arquivo.write_text(corpo, encoding="utf-8")
        try:
            processo = subprocess.run(
                # `--continue-on-collection-errors` porque a borda do import
                # estoura na COLETA, e sem ela o pytest interromperia a sessão
                # antes de chegar nas outras três.
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "-q",
                    "-p",
                    "no:cacheprovider",
                    "--continue-on-collection-errors",
                ]
                + [str(arquivo) for arquivo in ARQUIVOS_GERADOS],
                cwd=str(DIR_DOS_TESTES.parent),
                capture_output=True,
                text=True,
                timeout=300,
            )
        finally:
            for arquivo in ARQUIVOS_GERADOS:
                arquivo.unlink(missing_ok=True)

        saida = processo.stdout + processo.stderr
        estados = _estados_por_arquivo(saida)

        # As bordas. Sem a trava de sessão, as três do meio ficariam
        # VERDES com o pacote saindo, que é o furo que a revisão do PR #564
        # encontrou.
        assert estados.get(ARQUIVO_GUARDADO.stem) == "FAILED", f"O corpo do teste escapou.\n{saida}"
        assert estados.get(ARQUIVO_IMPORT.stem) == "ERROR", f"A rede em tempo de import escapou.\n{saida}"
        assert estados.get(ARQUIVO_SESSAO.stem) == "ERROR", f"A fixture de sessão escapou.\n{saida}"
        assert estados.get(ARQUIVO_MODULO.stem) == "ERROR", f"A fixture de módulo escapou.\n{saida}"
        assert estados.get(ARQUIVO_IMPOSTOR.stem) == "FAILED", f"A fixture homônima desligou a trava.\n{saida}"

        # E a trava VOLTA quando o arquivo isento termina. Este é o arquivo
        # logo depois do isento do meio: se a isenção desligasse a trava e não
        # religasse, ele passaria em silêncio, e todo arquivo dali para baixo
        # rodaria sem proteção nenhuma.
        assert estados.get(ARQUIVO_DEPOIS_DO_ISENTO.stem) == "FAILED", (
            f"A trava não voltou depois do arquivo isento.\n{saida}"
        )

        # O escape hatch. Arquivo aprovado não aparece no resumo, então o
        # "2 passed" (os dois isentos) é o que separa "isentou" de "o filho não
        # rodou nada": é aqui que um teste destes fica verde em cima de uma
        # varredura vazia.
        assert ARQUIVO_ISENTO.stem not in estados, f"A lista EXCECOES não isentou.\n{saida}"
        assert ARQUIVO_ISENTO_DO_MEIO.stem not in estados, f"A lista EXCECOES não isentou no meio.\n{saida}"
        assert "2 passed" in saida, f"O filho não aprovou os dois arquivos isentos.\n{saida}"

        assert "smtp.gmail.com" in saida, f"A tentativa de rede não foi a que os arquivos novos fizeram.\n{saida}"
        assert "Mocke o transporte" in saida, f"Os arquivos novos reprovaram por outro motivo.\n{saida}"
