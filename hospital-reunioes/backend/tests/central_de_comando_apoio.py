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
- `gate_e_limitador_zerados`: o limitador de taxa e o participante do gate
  zerados antes e depois do teste, para quem bate na rota.
- `lote_da_ga4`: o `batchRunReports` no Google de mentira (#817), que responde
  os Visitantes por dia e as Visitas por dispositivo pelas tabelas daqui. A
  #818 ensina as perguntas dela em `lote_da_ga4.perguntas`.

E, para testar pela rota real sem importar outro arquivo de teste (#815), o
app mínimo com o gate de pé e quem está logado: `cliente_da_central(logado)`,
as pessoas `SUPER_ADMIN`, `SECRETARIA` e `FACILITADOR` (ou `pessoa(...)`) e o
`PREFIXO_DA_CENTRAL`. Um arquivo novo da Central usa assim:

    pytestmark = pytest.mark.usefixtures("gate_e_limitador_zerados")

    def test_...(google_falso, central_configurada):
        resposta = cliente_da_central(SUPER_ADMIN).get(f"{PREFIXO_DA_CENTRAL}/...")

Nenhuma fixture daqui é `autouse`: plugin vale para a suíte inteira, e só pede
quem precisa. Nenhuma credencial de verdade mora aqui, e nada sai da máquina: a
trava de rede do `tests/conftest.py` continua de pé.

O `app` é importado dentro das fixtures e das funções, e não no topo: este
módulo carrega com o `conftest.py`, antes de qualquer teste pôr o backend no
`sys.path`.
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
from fastapi import FastAPI
from fastapi.testclient import TestClient
from google.auth import jwt as jwt_do_google
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

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
    # O gate (`app.dependencies`) é importado ANTES da troca (#818): o
    # `postgrest`, que ele carrega, herda de `httpx.Client` na importação, e
    # herdar da função que fica no lugar da classe quebra. Na suíte inteira
    # alguém sempre o importa antes; um arquivo da Central rodado sozinho
    # quebrava na primeira rota.
    import app.dependencies  # noqa: F401

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


# ─── O lote da GA4: a tela Dados do Google (issue #817) ─────────────────────
#
# A tela Dados do Google faz todas as perguntas dela numa ida só à GA4, o
# `batchRunReports`, com até 5 relatórios por chamada. O `LoteDaGA4` é o
# respondedor do `GoogleFalso` para esse método: responde cada pedido do lote
# como a GA4 responderia um `runReport`. A fatia seguinte da mesma tela (#818)
# ensina as perguntas dela acrescentando em `lote_da_ga4.perguntas`, ou enchendo
# as tabelas daqui, sem editar a classe.

# Visitantes (`activeUsers`) por dia (`date`) que a GA4 "sabe". Dia que não está
# aqui é dia sem visita: a GA4 não devolve linha para ele. Uma tabela só, por
# dia, como a da GA4: o dia 04/09 é o primeiro do período anterior de 7 dias e
# está dentro do período atual de 28, com o mesmo número nos dois.
VISITANTES_POR_DIA_NA_GA4: dict[str, int] = {
    # 90 dias: a ponta do anterior (22/03 a 19/06) e o primeiro dia (20/06 a 17/09).
    "2026-03-22": 95,
    "2026-06-19": 101,
    "2026-06-20": 120,
    # 28 dias: as pontas do anterior (24/07 a 20/08) e o primeiro dia (21/08 a 17/09).
    "2026-07-24": 250,
    "2026-08-20": 333,
    "2026-08-21": 300,
    # O anterior dos 7 dias (04/09 a 10/09): todos os dias com visita.
    "2026-09-04": 350,
    "2026-09-05": 362,
    "2026-09-06": 298,
    "2026-09-07": 301,
    "2026-09-08": 455,
    "2026-09-09": 470,
    "2026-09-10": 441,
    # Os 7 dias (11/09 a 17/09): o dia 13 não teve visita, e a GA4 o omite.
    "2026-09-11": 410,
    "2026-09-12": 385,
    "2026-09-14": 520,
    "2026-09-15": 498,
    "2026-09-16": 471,
    "2026-09-17": 402,
}

# Visitas (`sessions`) por `deviceCategory`, no período atual de cada tamanho,
# pelo intervalo (início, fim). A GA4 fala inglês e conhece categorias além das
# três da Central (a "smart tv").
VISITAS_POR_DISPOSITIVO_NA_GA4: dict[tuple[str, str], dict[str, int]] = {
    # 7 dias: ninguém de tablet.
    ("2026-09-11", "2026-09-17"): {"mobile": 1850, "desktop": 640},
    # 28 dias: 10.000 Visitas nas três categorias, e 3 numa smart tv.
    ("2026-08-21", "2026-09-17"): {"mobile": 7100, "desktop": 2300, "tablet": 600, "smart tv": 3},
    # 90 dias: o computador na frente.
    ("2026-06-20", "2026-09-17"): {"desktop": 12000, "mobile": 11000, "tablet": 1000},
}

# Visitas (`sessions`) por página (`pagePath`), pelo intervalo (início, fim), para
# as Áreas do site (#818). A GA4 só conhece páginas soltas, com e sem barra no
# fim, e o Site tem páginas que não são de Área nenhuma. Intervalo que não está
# aqui não teve visita em página nenhuma (os 90 dias).
VISITAS_POR_PAGINA_NA_GA4: dict[tuple[str, str], dict[str, int]] = {
    # 28 dias (21/08 a 17/09): Maternidade 3.842, Emergência 3.610, Centro de
    # Imagem e Centro Médico empatados em 1.230, Laboratório 480.
    ("2026-08-21", "2026-09-17"): {
        "/": 8000,
        "/maternidade/": 3100,
        "/maternidade/amamentacao/": 742,
        "/maternidade-clinica/": 99,
        "/emergencia/": 2610,
        "/emergencia/pediatrica/": 1000,
        "/emergencia-24h/": 57,
        "/centro-de-imagem/": 1230,
        "/centro-medico/": 900,
        "/centro-medico/cardiologia/": 330,
        "/laboratorio/": 480,
        "/blog/": 5000,
    },
    # O anterior dos 28 dias (24/07 a 20/08): ninguém no Centro Médico.
    ("2026-07-24", "2026-08-20"): {
        "/": 7000,
        "/maternidade/": 3500,
        "/emergencia/": 3700,
        "/centro-de-imagem/": 1230,
        "/laboratorio/": 400,
    },
    # 7 dias (11/09 a 17/09): o Laboratório na frente, e duas Áreas sem visita.
    ("2026-09-11", "2026-09-17"): {
        "/laboratorio/": 300,
        "/laboratorio/resultados/": 150,
        "/maternidade/": 400,
        "/emergencia/": 200,
    },
    # O anterior dos 7 dias (04/09 a 10/09).
    ("2026-09-04", "2026-09-10"): {
        "/laboratorio/": 500,
        "/maternidade/": 400,
    },
}

# O limite da GA4: um `batchRunReports` leva de 1 a 5 relatórios.
MAXIMO_DE_RELATORIOS_POR_LOTE = 5

# Uma pergunta do lote recebe UM pedido de relatório e devolve o relatório (sem
# o `kind`, que o lote põe) ou `None` para passar o pedido adiante.
PerguntaDoLote = Callable[[dict], dict | None]


def relatorio_de_uma_dimensao(dimensao: str, metrica: str, valores: dict[str, int]) -> dict:
    """O relatório da GA4 com uma dimensão e uma métrica. As linhas vêm da maior
    para a menor, e não na ordem do calendário: sem `orderBys`, a GA4 não
    promete ordem nenhuma. Sem valor nenhum, sem `rows`, que é como a GA4 diz
    que o intervalo não teve dado."""
    relatorio: dict[str, Any] = {
        "dimensionHeaders": [{"name": dimensao}],
        "metricHeaders": [{"name": metrica, "type": "TYPE_INTEGER"}],
    }
    linhas = sorted(valores.items(), key=lambda item: item[1], reverse=True)
    if linhas:
        relatorio["rows"] = [
            {"dimensionValues": [{"value": valor}], "metricValues": [{"value": str(numero)}]}
            for valor, numero in linhas
        ]
        relatorio["rowCount"] = len(linhas)
    return relatorio


def faixa_unica(pedido: dict) -> tuple[str, str] | None:
    """O (início, fim) do pedido de UM intervalo e sem filtro, ou `None`."""
    faixas = pedido.get("dateRanges") or []
    if len(faixas) != 1 or pedido.get("dimensionFilter"):
        return None
    return faixas[0]["startDate"], faixas[0]["endDate"]


class LoteDaGA4:
    """O `batchRunReports` da GA4 de mentira, respondedor do `GoogleFalso`.

    Responde cada pedido do lote pelas `perguntas`, na ordem: vale a primeira
    que souber responder. Como a GA4, o lote leva de 1 a 5 pedidos, e basta um
    pedido que ninguém sabe responder para o lote inteiro levar 400 (o
    `GoogleFalso` responde o 400 quando o respondedor devolve `None`).

    Nasce sabendo as duas perguntas da #817, pelas tabelas: Visitantes por dia
    e Visitas por dispositivo. `lotes` guarda os pedidos de cada lote que a
    GA4 respondeu.

    E as da #818, na mesma tela, acrescentadas no fim do `__init__`: as
    Visitas por página (Áreas do site).
    """

    def __init__(self) -> None:
        self.visitantes_por_dia = dict(VISITANTES_POR_DIA_NA_GA4)
        self.visitas_por_dispositivo = {faixa: dict(v) for faixa, v in VISITAS_POR_DISPOSITIVO_NA_GA4.items()}
        self.perguntas: list[PerguntaDoLote] = [self._visitantes_por_dia, self._visitas_por_dispositivo]
        self.lotes: list[list[dict]] = []
        # As perguntas da #818: a tela pergunta tudo numa ida só, então o lote
        # de qualquer teste da tela precisa saber respondê-las.
        self.visitas_por_pagina = {faixa: dict(v) for faixa, v in VISITAS_POR_PAGINA_NA_GA4.items()}
        self.perguntas += [self._visitas_por_pagina]

    def __call__(self, metodo: str, corpo: dict) -> dict | None:
        if metodo != "batchRunReports":
            return None
        pedidos = corpo.get("requests")
        if not isinstance(pedidos, list) or not 1 <= len(pedidos) <= MAXIMO_DE_RELATORIOS_POR_LOTE:
            return None
        relatorios = []
        for pedido in pedidos:
            relatorio = next((r for pergunta in self.perguntas if (r := pergunta(pedido)) is not None), None)
            if relatorio is None:
                return None
            relatorios.append({"kind": "analyticsData#runReport", **relatorio})
        self.lotes.append(pedidos)
        return {"reports": relatorios}

    def _visitantes_por_dia(self, pedido: dict) -> dict | None:
        faixa = faixa_unica(pedido)
        if (
            faixa is None
            or pedido.get("metrics") != [{"name": "activeUsers"}]
            or pedido.get("dimensions") != [{"name": "date"}]
        ):
            return None
        inicio, fim = faixa
        # A dimensão `date` da GA4 chega sem hífen: "20260917".
        no_intervalo = {dia.replace("-", ""): n for dia, n in self.visitantes_por_dia.items() if inicio <= dia <= fim}
        return relatorio_de_uma_dimensao("date", "activeUsers", no_intervalo)

    def _visitas_por_dispositivo(self, pedido: dict) -> dict | None:
        faixa = faixa_unica(pedido)
        if (
            faixa is None
            or pedido.get("metrics") != [{"name": "sessions"}]
            or pedido.get("dimensions") != [{"name": "deviceCategory"}]
        ):
            return None
        return relatorio_de_uma_dimensao("deviceCategory", "sessions", self.visitas_por_dispositivo.get(faixa, {}))

    def _visitas_por_pagina(self, pedido: dict) -> dict | None:
        faixa = faixa_unica(pedido)
        if (
            faixa is None
            or pedido.get("metrics") != [{"name": "sessions"}]
            or pedido.get("dimensions") != [{"name": "pagePath"}]
        ):
            return None
        return relatorio_de_uma_dimensao("pagePath", "sessions", self.visitas_por_pagina.get(faixa, {}))


@pytest.fixture
def lote_da_ga4(google_falso) -> LoteDaGA4:
    """O `batchRunReports` no Google de mentira, com as tabelas da #817. Pede
    o `google_falso`, então o cache da Central também nasce vazio."""
    lote = LoteDaGA4()
    google_falso.respondedores.append(lote)
    return lote


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


# ─── O app mínimo com o gate de pé, e quem está logado (issue #815) ──────────
#
# Morava em `test_central_de_comando_visao_geral.py`, e o arquivo de teste
# seguinte o importava de lá: importar um arquivo de teste roda o que ele roda
# na coleta (a varredura de rotas monta o app inteiro) e amarra um ao outro.
# Aqui ele serve a qualquer fatia da Central (#817, #818) sem isso.

PREFIXO_DA_CENTRAL = "/api/admin/central-de-comando"


def pessoa(pid: str, access_profile: str | None, *, ativo: bool = True) -> dict:
    """Uma linha de `participantes`, como o gate de Super admin a lê."""
    return {
        "id": pid,
        "auth_user_id": f"auth-{pid}",
        "email": f"{pid}@hsm.com",
        "nome_completo": f"Pessoa {pid}",
        "cargo": None,
        "setor": None,
        "area": None,
        "role": None,
        "ativo": ativo,
        "is_externo": False,
        "is_super_admin": access_profile == "super_admin",
        "access_profile": access_profile,
        "perfil_pop": None,
        "perfil_ouvidoria": None,
        "github_login": None,
        "data_cadastro": "2026-01-01",
    }


SUPER_ADMIN = pessoa("super", "super_admin")
SECRETARIA = pessoa("secretaria", "secretaria")
FACILITADOR = pessoa("facilitador", "regular")


class _Resultado:
    def __init__(self, data: list):
        self.data = data


class _ConsultaDeParticipantes:
    def __init__(self, linhas: list[dict]):
        self._linhas = linhas
        self._filtros: list[tuple[str, Any]] = []

    def select(self, *_a, **_kw):
        return self

    def eq(self, coluna, valor):
        self._filtros.append((coluna, valor))
        return self

    def execute(self):
        return _Resultado([dict(li) for li in self._linhas if all(li.get(c) == v for c, v in self._filtros)])


class SupabaseDosParticipantes:
    """O cliente Supabase que o gate usa: só a tabela `participantes`. A Central
    não lê tabela nenhuma além dessa, e o dublê grita se alguém tentar."""

    def __init__(self, participantes: list[dict]):
        self._participantes = participantes

    def table(self, nome: str):
        assert nome == "participantes", f"a Central não lê tabela nenhuma além do gate: {nome}"
        return _ConsultaDeParticipantes(self._participantes)


def cliente_da_central(logado: dict | None, participantes: list[dict] | None = None) -> TestClient:
    """O router de verdade da Central num app mínimo, com o gate de pé.

    Só dois dublês: `get_current_user` (quem está logado) e o cliente Supabase
    (a tabela que o gate lê). `logado=None` é o anônimo, que passa pelo
    `get_current_user` de verdade e leva 401. `participantes` troca a tabela;
    o padrão são as três pessoas daqui.
    """
    from app.dependencies import get_current_user, get_supabase_client
    from app.limiter import limiter
    from app.routers.admin import central_de_comando as central_router

    tabela = participantes if participantes is not None else [SUPER_ADMIN, SECRETARIA, FACILITADOR]
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(central_router.router, prefix="/api")
    app.dependency_overrides[get_supabase_client] = lambda: SupabaseDosParticipantes(tabela)
    if logado is not None:

        async def _usuario() -> dict[str, Any]:
            return {"id": logado["auth_user_id"], "email": logado["email"], "metadata": {}}

        app.dependency_overrides[get_current_user] = _usuario
    return TestClient(app)


@pytest.fixture
def gate_e_limitador_zerados():
    """O limitador de taxa (que conta em memória do processo) e o participante
    que o gate guarda no contexto, zerados antes e depois do teste: pedido de um
    teste não gasta a cota nem responde pela pessoa do seguinte."""
    from app.dependencies import _participante_ctx
    from app.limiter import limiter

    limiter._storage.reset()
    _participante_ctx.set(None)
    yield
    limiter._storage.reset()
    _participante_ctx.set(None)
