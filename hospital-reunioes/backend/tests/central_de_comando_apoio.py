"""Apoio compartilhado dos testes da Central de Comando (issue #814, ADR 0058).

O Google de mentira e a service account de mentira, num lugar só, para as
fatias seguintes da Central (#815 a #818) testarem pela rota real sem copiar o
dublê. O `tests/conftest.py` registra este módulo como plugin
(`pytest_plugins`), então as fixtures valem em qualquer arquivo de teste, pelo
nome:

- `chave_rsa_da_central`: chave RSA gerada a cada execução. A assinatura é de
  verdade; a conta, não.
- `credencial_da_central`: o JSON da service account de mentira, com essa chave.
- `central_configurada`: as duas variáveis do Google preenchidas no `settings`.
- `google_falso`: troca só o transporte do `httpx.Client` pelo `GoogleFalso`,
  com o cache da Central vazio (pede o `cache_da_central`).
- `hoje_da_central`: congela o relógio da Central em `HOJE_DE_TESTE`.
- `cache_da_central`: o cache com frescor do processo (#815), vazio no começo e
  no fim do teste.
- `relogio_da_central`: o relógio do cache (#815) nas mãos do teste, um
  `RelogioDeTeste` parado em `AGORA_DE_TESTE` que só anda quando mandam.

Nenhuma fixture daqui é `autouse`: plugin vale para a suíte inteira, e só pede
quem precisa. Nenhuma credencial de verdade mora aqui, e nada sai da máquina: a
trava de rede do `tests/conftest.py` continua de pé.

O `app` é importado dentro das fixtures, e não no topo: este módulo carrega com
o `conftest.py`, antes de qualquer teste pôr o backend no `sys.path`.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from google.auth import jwt as jwt_do_google

PROPRIEDADE_DE_TESTE = "123456789"
# O escopo que a GA4 exige para ler. Escrito aqui, e não importado do provedor:
# é a fonte independente contra a qual o provedor é conferido.
ESCOPO_DE_LEITURA = "https://www.googleapis.com/auth/analytics.readonly"
EMAIL_DA_SERVICE_ACCOUNT = "central-teste@projeto-de-teste.iam.gserviceaccount.com"

# O "hoje" dos testes. Os intervalos abaixo foram contados à mão a partir dele:
# N dias completos terminando ontem (17/09) e o bloco de mesmo tamanho antes.
HOJE_DE_TESTE = date(2026, 9, 18)

VISITANTES_NA_GA4: dict[tuple[str, str], int] = {
    # 28 dias: 21/08 a 17/09, contra 24/07 a 20/08.
    ("2026-08-21", "2026-09-17"): 12345,
    ("2026-07-24", "2026-08-20"): 10000,
    # 7 dias: 11/09 a 17/09, contra 04/09 a 10/09.
    ("2026-09-11", "2026-09-17"): 3100,
    ("2026-09-04", "2026-09-10"): 3350,
    # 90 dias: 20/06 a 17/09, contra 22/03 a 19/06.
    ("2026-06-20", "2026-09-17"): 38412,
    ("2026-03-22", "2026-06-19"): 34174,
}

# Um respondedor recebe o método da GA4 ("runReport", "runRealtimeReport") e o
# corpo do pedido, e devolve o relatório (sem o `kind`, que o dublê põe) ou
# `None` para passar a pergunta adiante.
Respondedor = Callable[[str, dict], dict | None]


def erro_da_ga4(codigo: int, status: str, mensagem: str) -> httpx.Response:
    """O envelope de erro das APIs do Google."""
    return httpx.Response(codigo, json={"error": {"code": codigo, "message": mensagem, "status": status}})


class GoogleFalso:
    """A GA4 Data API de mentira, no lugar do transporte do `httpx.Client`.

    Confere o que a GA4 confere: a assinatura do JWT de acesso pela chave
    pública da service account, a validade, o escopo de leitura e a
    propriedade no caminho. E responde pelo que foi pedido:

    1. Os `respondedores`, na ordem. É por aqui que uma fatia seguinte ensina
       o dublê a responder a pergunta dela (dimensões, o Ao vivo), sem copiar
       nem editar esta classe.
    2. `runReport` de `activeUsers` sem dimensão: os Visitantes de
       `self.visitantes`, por (início, fim). Intervalo que não está lá é a
       resposta sem `rows`, como a GA4 faz.
    3. Pergunta que ninguém sabe responder leva 400, barulhento de propósito:
       um dublê que responde qualquer coisa esconderia a pergunta errada.

    `forcar` troca TODA resposta por uma resposta fixa, ou por uma exceção de
    rede do `httpx`. `pedidos` e `clientes` registram o que passou.
    """

    def __init__(self, chave_publica: bytes, visitantes: dict[tuple[str, str], int]):
        self._chave_publica = chave_publica
        # O que a GA4 "sabe": activeUsers por (início, fim). O teste pode trocar.
        self.visitantes = dict(visitantes)
        self.respondedores: list[Respondedor] = []
        self.pedidos: list[httpx.Request] = []
        self.clientes: list[dict[str, Any]] = []
        # Quando preenchido, é o que TODA chamada responde (ou levanta).
        self.forcar: httpx.Response | Exception | None = None

    def __call__(self, pedido: httpx.Request) -> httpx.Response:
        self.pedidos.append(pedido)
        if isinstance(self.forcar, Exception):
            raise self.forcar
        if self.forcar is not None:
            return self.forcar

        if pedido.url.host != "analyticsdata.googleapis.com" or pedido.method != "POST":
            return httpx.Response(404)

        autorizacao = pedido.headers.get("authorization", "")
        if not self._token_valido(autorizacao.removeprefix("Bearer ")):
            return erro_da_ga4(401, "UNAUTHENTICATED", "Request had invalid authentication credentials.")

        prefixo = f"/v1beta/properties/{PROPRIEDADE_DE_TESTE}:"
        if not pedido.url.path.startswith(prefixo):
            # O que a GA4 responde para propriedade em que a conta não tem papel.
            return erro_da_ga4(403, "PERMISSION_DENIED", "User does not have sufficient permissions.")
        metodo = pedido.url.path.removeprefix(prefixo)
        corpo = json.loads(pedido.content)

        for responder in self.respondedores:
            relatorio = responder(metodo, corpo)
            if relatorio is not None:
                return httpx.Response(200, json={"kind": f"analyticsData#{metodo}", **relatorio})

        faixas = corpo.get("dateRanges") or []
        pergunta_de_visitantes = (
            metodo == "runReport"
            and corpo.get("metrics") == [{"name": "activeUsers"}]
            and not corpo.get("dimensions")
            and len(faixas) == 1
        )
        if not pergunta_de_visitantes:
            return erro_da_ga4(400, "INVALID_ARGUMENT", f"pergunta que o dublê não sabe responder: {metodo} {corpo}")

        chave = (faixas[0]["startDate"], faixas[0]["endDate"])
        if chave not in self.visitantes:
            # A GA4 omite `rows` quando o intervalo não tem dado nenhum.
            return httpx.Response(200, json={"kind": "analyticsData#runReport", "rowCount": 0})
        return httpx.Response(
            200,
            json={
                "kind": "analyticsData#runReport",
                "metricHeaders": [{"name": "activeUsers", "type": "TYPE_INTEGER"}],
                "rows": [{"metricValues": [{"value": str(self.visitantes[chave])}]}],
                "rowCount": 1,
            },
        )

    def _token_valido(self, token: str) -> bool:
        """Assinatura da service account, validade e escopo. Assinatura de outra
        chave, token vencido ou lixo: recusado."""
        try:
            claims = jwt_do_google.decode(token, certs=self._chave_publica, verify=True)
        except ValueError:
            return False
        return claims.get("iss") == EMAIL_DA_SERVICE_ACCOUNT and ESCOPO_DE_LEITURA in claims.get("scope", "").split()


def pem_da_chave_privada(chave: rsa.RSAPrivateKey) -> str:
    return chave.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()


@pytest.fixture(scope="session")
def chave_rsa_da_central() -> rsa.RSAPrivateKey:
    """Uma chave por execução da suíte: a assinatura é de verdade, a conta não."""
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def credencial_da_central(chave_rsa_da_central) -> dict:
    """O JSON da chave da service account de mentira, no formato do Google."""
    return {
        "type": "service_account",
        "project_id": "projeto-de-teste",
        "private_key_id": "id-da-chave-de-teste",
        "private_key": pem_da_chave_privada(chave_rsa_da_central),
        "client_email": EMAIL_DA_SERVICE_ACCOUNT,
        "client_id": "000000000000000000000",
        "token_uri": "https://oauth2.googleapis.com/token",
    }


@pytest.fixture
def central_configurada(monkeypatch, credencial_da_central) -> None:
    """As duas variáveis do Google preenchidas, como no `.env` de quem confere."""
    from app.config import settings

    monkeypatch.setattr(settings, "ga4_property_id", PROPRIEDADE_DE_TESTE)
    monkeypatch.setattr(settings, "google_application_credentials_json", json.dumps(credencial_da_central))


@pytest.fixture
def cache_da_central():
    """O cache com frescor do processo (issue #815), vazio no começo e no fim
    do teste: número guardado por um teste não responde pelo seguinte."""
    from app.services.central_de_comando.cache import cache_da_central as cache

    cache.limpar()
    yield cache
    cache.limpar()


@pytest.fixture
def google_falso(monkeypatch, chave_rsa_da_central, cache_da_central) -> GoogleFalso:
    """Troca só o transporte do `httpx.Client`: o cliente de verdade monta o
    pedido, e a resposta vem do Google de mentira.

    O Google de mentira nasce com o cache da Central vazio: sem isso, um
    número guardado por um teste anterior responderia no lugar dele, e o teste
    passaria ou falharia conforme a ordem da suíte."""
    chave_publica = chave_rsa_da_central.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    falso = GoogleFalso(chave_publica, VISITANTES_NA_GA4)
    cliente_de_verdade = httpx.Client

    def _cliente(*args, **kwargs):
        falso.clientes.append(dict(kwargs))
        return cliente_de_verdade(*args, transport=httpx.MockTransport(falso), **kwargs)

    monkeypatch.setattr(httpx, "Client", _cliente)
    return falso


@pytest.fixture
def hoje_da_central(monkeypatch) -> date:
    """O relógio é fronteira: o teste diz que dia é hoje para a Central."""
    from app.services.central_de_comando import periodo

    monkeypatch.setattr(periodo, "hoje_utc", lambda: HOJE_DE_TESTE)
    return HOJE_DE_TESTE


# O instante em que os testes do cache começam: o `HOJE_DE_TESTE`, às 13h45 em
# UTC. Hora redonda de propósito, para o carimbo de frescor ser conferido de
# olho ("2026-09-18T13:45:00+00:00").
AGORA_DE_TESTE = datetime(2026, 9, 18, 13, 45, tzinfo=UTC)


class RelogioDeTeste:
    """O relógio do cache com frescor nas mãos do teste: parado até o teste
    mandar andar. É ele que diz se a hora do cache já passou."""

    def __init__(self, agora: datetime = AGORA_DE_TESTE):
        self.agora = agora

    def __call__(self) -> datetime:
        return self.agora

    def avancar(self, **quanto: float) -> None:
        """Anda o relógio: `avancar(minutes=59)`, `avancar(hours=1)`."""
        self.agora += timedelta(**quanto)


@pytest.fixture
def relogio_da_central(monkeypatch) -> RelogioDeTeste:
    """O relógio do cache com frescor nas mãos do teste, parado em
    `AGORA_DE_TESTE`. É outro relógio que o do `hoje_da_central`: aquele diz
    que dia é (os períodos), este diz há quanto tempo o número foi buscado."""
    from app.services.central_de_comando import cache

    relogio = RelogioDeTeste()
    monkeypatch.setattr(cache, "agora_utc", relogio)
    return relogio
