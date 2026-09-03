"""A trava de rede da suíte, provada (issue #546, PRD #471).

Testar uma trava tem uma armadilha própria: verificar que ela EXISTE não prova
nada. O que prova é ela pegar uma tentativa de rede de verdade, pelos caminhos
que os testes deste backend usariam sem querer, e continuar deixando passar o
que a suíte precisa.

São cinco coisas, e cada uma cobre um jeito de a trava ser inútil:

1. **`smtplib` para fora falha com mensagem acionável.** É o caminho que vazou
   na #494: `.env` real, usuário e senha do Gmail, quatro testes abrindo
   conexão para `smtp.gmail.com:587`;
2. **HTTP para host externo falha do mesmo jeito**, inclusive quando quem
   chama é o `email_service`, que envolve o envio inteiro num
   `except Exception`. Uma trava capturável ali deixaria o teste VERDE em cima
   de uma tentativa de rede: por isso a exceção herda de `BaseException`;
3. **loopback continua liberado**, e o `TestClient` continua de pé. Trava que
   derruba o que a suíte precisa não é segurança, é indisponibilidade;
4. **um arquivo de teste NOVO já nasce coberto.** É a razão de a issue existir:
   a trava da #494 morava dentro de um arquivo, então o arquivo seguinte
   nascia sem nada. O teste escreve um arquivo do zero e roda o pytest nele em
   outro processo, que é a única forma honesta de perguntar isso;
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

# Os dois arquivos que o teste 4/5 escreve e apaga. O nome do isento é o que
# está na lista EXCECOES do conftest; o outro não é, e essa é a única
# diferença entre eles.
ARQUIVO_GUARDADO = DIR_DOS_TESTES / "test_gerado_pela_trava_de_rede.py"
ARQUIVO_ISENTO = DIR_DOS_TESTES / "test_gerado_isento_da_trava_de_rede.py"

# Sem `pytest.raises`: este arquivo nasce agora e não sabe de nada. Se a trava
# não valer para ele, a chamada vai até o Gmail e o teste passa, e é o pai que
# reprova. Se valer, o teste falha aqui, com a mensagem no relatório.
CORPO_DO_ARQUIVO_GUARDADO = '''"""Arquivo gerado por test_trava_de_rede.py. Se sobrou, pode apagar."""

import smtplib


def test_o_arquivo_recem_criado_ja_nasce_com_a_trava():
    smtplib.SMTP("smtp.gmail.com", 587, timeout=1)
'''

# A contraprova. `pytest.raises(OSError)` NÃO pega `TentativaDeRedeNoTeste`
# (que herda de `BaseException`), então este teste só passa se o socket for
# mesmo o de verdade: com a isenção quebrada, a trava estoura por fora do
# `raises` e o teste reprova. 192.0.2.1 é a faixa de documentação da RFC 5737,
# não roteada, e a porta 9 é a discard: não há serviço nenhum do outro lado.
CORPO_DO_ARQUIVO_ISENTO = '''"""Arquivo gerado por test_trava_de_rede.py. Se sobrou, pode apagar."""

import socket

import pytest


def test_o_arquivo_da_lista_de_excecoes_fala_com_o_socket_de_verdade():
    with pytest.raises(OSError):
        socket.create_connection(("192.0.2.1", 9), timeout=0.05)
'''


class TestOCaminhoQueVazou:
    """`smtplib`, do jeito que a #494 encontrou."""

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

    def test_o_testclient_continua_de_pe(self):
        app = FastAPI()

        @app.get("/ping")
        def _ping():
            return {"pong": True}

        with TestClient(app) as cliente:
            resposta = cliente.get("/ping")

        assert resposta.status_code == 200
        assert resposta.json() == {"pong": True}


class TestArquivoNovoJaNasceCoberto:
    """O ponto da issue. A trava da #494 era `autouse` DENTRO de um arquivo:
    protegia aquele arquivo e mais nada, e o arquivo irmão da #493 seguiu sem
    proteção nenhuma. Sendo de repositório, a pergunta certa é sobre um arquivo
    que ainda não existe."""

    def test_o_nome_do_arquivo_isento_esta_na_lista(self):
        """Guarda do próprio harness: se alguém renomear um dos dois lados, o
        teste de baixo passaria a medir outra coisa em silêncio."""
        assert ARQUIVO_ISENTO.stem in EXCECOES
        assert ARQUIVO_GUARDADO.stem not in EXCECOES

    def test_arquivo_novo_e_coberto_e_a_lista_de_excecoes_isenta(self):
        ARQUIVO_GUARDADO.write_text(CORPO_DO_ARQUIVO_GUARDADO, encoding="utf-8")
        ARQUIVO_ISENTO.write_text(CORPO_DO_ARQUIVO_ISENTO, encoding="utf-8")
        try:
            processo = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    str(ARQUIVO_GUARDADO),
                    str(ARQUIVO_ISENTO),
                    "-q",
                    "-p",
                    "no:cacheprovider",
                ],
                cwd=str(DIR_DOS_TESTES.parent),
                capture_output=True,
                text=True,
                timeout=300,
            )
        finally:
            ARQUIVO_GUARDADO.unlink(missing_ok=True)
            ARQUIVO_ISENTO.unlink(missing_ok=True)

        saida = processo.stdout + processo.stderr

        # As duas linhas abaixo são o detector, e é aqui que um teste destes
        # costuma ficar verde em cima de nada: um processo filho que não
        # coletou teste nenhum sai com código != 0 e com a saída vazia, e
        # passaria por qualquer asserção que só olhasse o código de saída.
        assert "1 failed" in saida, f"O filho não reprovou o arquivo guardado.\n{saida}"
        assert "1 passed" in saida, f"O filho não aprovou o arquivo isento.\n{saida}"

        assert "smtp.gmail.com" in saida, f"A tentativa de rede não foi a que o arquivo novo fez.\n{saida}"
        assert "Mocke o transporte" in saida, f"O arquivo novo reprovou por outro motivo.\n{saida}"
