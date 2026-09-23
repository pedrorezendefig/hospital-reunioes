"""Provedor de dados do Google da Central de Comando (ADR 0058, PRD #809).

O ÚNICO ponto do app que fala com o Google Analytics. Módulo profundo, porta
estreita, no molde do Espelho da Global Health (`global_health_service.py`):
aqui moram a base da API, a credencial, o timeout, a pergunta que cada número
faz à GA4 e a tradução de erro. Quem está fora recebe números do domínio
("Visitantes do período e do anterior"), nunca linha de relatório da GA4.

Três invariantes que o resto do app herda de graça:

- **Só leitura.** A credencial pede só o escopo de leitura, e o único verbo é
  o `runReport` (o Ao vivo acrescenta o `runRealtimeReport`, também leitura),
  sozinho ou em lote (`batchRunReports`, que junta vários `runReport` numa ida
  só).
- **Não configurado é 503, nunca zero.** Sem propriedade ou sem chave, a
  exceção é `GoogleNaoConfiguradoError`, com o que falta na mensagem. O
  provedor falso da Central antiga, que desenhava número de demonstração sem
  credencial, não foi portado de propósito.
- **Falha é falha.** Timeout, 5xx, acesso recusado e corpo ilegível viram
  `GoogleError` (502 na rota), distinta de período sem dado, que é zero de
  verdade porque a GA4 respondeu.

**A credencial.** É a chave da service account com papel Leitor na propriedade.
Ela assina aqui mesmo um JWT com o escopo de leitura, o "JWT de acesso" das
APIs do Google, e é esse JWT que vai no `Authorization`. É o mesmo modo que o
cliente oficial usava na Central antiga (`useJWTAccessWithScope`), e por isso
não existe ida ao endpoint de token: a única chamada de rede é a da GA4, pelo
`httpx`, como toda API externa da casa. O `google-auth` só assina.

**Para as próximas fatias.** Cada número do Site é uma função pública daqui
(Visitantes comparados, movimento diário, Áreas do site, Origem do público,
dispositivos, Contatos gerados, Ao vivo), e toda chamada à GA4 sai por uma de
duas portas de rede, com o mesmo timeout e a mesma tradução de falha: o
`_postar_na_ga4`, para um relatório só (o `runReport` das telas de tendência e
o `runRealtimeReport` do Ao vivo), e o `_um_lote` (`batchRunReports`), para as
telas que pedem vários relatórios de uma vez (Dados do Google, #817).
"""

from __future__ import annotations

import json
import logging
import math
import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date
from functools import partial
from typing import Any, Literal

import google.auth.exceptions
import google.auth.transport
import httpx
from google.oauth2 import service_account

from app.config import settings
from app.services.central_de_comando.periodo import (
    Intervalo,
    Periodo,
    dias_do_intervalo,
    intervalo_anterior,
    intervalo_atual,
)

logger = logging.getLogger(__name__)

# A GA4 Data API. Constante, e não variável de ambiente: apontar para outra API
# é decisão revisada em commit, como a base do Espelho.
BASE_URL = "https://analyticsdata.googleapis.com/v1beta"

# Só leitura: mesmo que a service account ganhasse mais papel na propriedade,
# a credencial montada aqui não teria como usá-lo.
ESCOPO_DE_LEITURA = "https://www.googleapis.com/auth/analytics.readonly"

# Timeout curto: quem espera olha a tela. Erro honesto em segundos vale mais
# que tela pendurada (padrão da casa: connect menor).
_TIMEOUT = httpx.Timeout(10.0, connect=3.0)

# A assinatura do relatório da GA4: toda resposta do `runReport` traz este
# `kind`, fixo. É ele que distingue "a GA4 respondeu que não há linha" (zero de
# verdade) de um `{}` de proxy ou de página de erro, que não é resposta nenhuma.
_KIND_DO_RELATORIO = "analyticsData#runReport"

# A frase de todo relatório que chega fora do formato, em qualquer tela: fixa,
# porque vai para a tela e fica no cache como o motivo do último valor bom.
_RELATORIO_FORA_DO_FORMATO = "O Google Analytics devolveu um relatório fora do formato esperado."

_FALTA_CONFIGURAR = (
    "A Central de Comando ainda não está ligada ao Google Analytics: falta configurar {faltando} no "
    "backend. Enquanto isso, nenhum número do Site é mostrado."
)

_PROPRIEDADE_INVALIDA = (
    "GA4_PROPERTY_ID precisa ser só o número da propriedade do Google Analytics, sem letras, espaços nem barras."
)

_CREDENCIAL_INVALIDA = (
    "GOOGLE_APPLICATION_CREDENTIALS_JSON não é a chave de uma service account do Google. Cole o "
    "conteúdo inteiro do arquivo JSON da chave, numa linha só."
)


class GoogleError(RuntimeError):
    """O Google Analytics não respondeu, recusou o acesso ou respondeu fora do
    formato. Distinta de período sem dado: a mensagem sobe para a tela."""


class GoogleNaoConfiguradoError(RuntimeError):
    """Falta configurar (ou está malformada) a propriedade ou a chave da
    service account. A mensagem diz o que falta, sem nunca ecoar a chave."""


@dataclass(frozen=True)
class VisitantesComparados:
    """Os Visitantes do período e do anterior, cada número com a janela a que
    se refere: o número nunca viaja sem dizer de quando é."""

    atual: int
    anterior: int
    intervalo_atual: Intervalo
    intervalo_anterior: Intervalo


def visitantes_comparados(periodo: Periodo, hoje: date) -> VisitantesComparados:
    """Visitantes do período e do período anterior de mesmo tamanho.

    Visitantes são pessoas diferentes, o `activeUsers` da GA4: o número que o
    Google mostra por padrão como "usuários ativos", de propósito, para quem
    for conferir (glossário, seção "Central de Comando"). Uma pergunta por
    intervalo, como a Central antiga fazia, para o número bater com o dela.
    """
    atual = intervalo_atual(periodo, hoje)
    anterior = intervalo_anterior(periodo, hoje)
    return VisitantesComparados(
        atual=_visitantes_em(atual),
        anterior=_visitantes_em(anterior),
        intervalo_atual=atual,
        intervalo_anterior=anterior,
    )


def _visitantes_em(intervalo: Intervalo) -> int:
    relatorio = _relatorio(
        {
            "dateRanges": [{"startDate": intervalo.inicio.isoformat(), "endDate": intervalo.fim.isoformat()}],
            "metrics": [{"name": "activeUsers"}],
        }
    )
    return int(_primeira_metrica(relatorio))


def _primeira_metrica(relatorio: dict) -> float:
    """O primeiro valor de métrica do relatório (relatório sem dimensão).

    Sem linha nenhuma é zero: a GA4 omite `rows` quando o intervalo não tem
    dado, e isso é resposta, não falha. Só vale porque o `_relatorio` já
    conferiu que a resposta É um relatório da GA4 (o `kind`): um `{}` de proxy
    nunca chega aqui para virar zero. Valor que não é número finito também é
    zero, como na Central antiga (`firstMetric`): anomalia da GA4 nunca chega à
    tela como "NaN". Um `rows` que não é lista, ou linha sem o campo de métrica,
    esses sim, são resposta fora do formato, como no `_linhas`: um `rows` `{}`,
    `0` ou `''` lido como lista vazia viraria 0 Visitantes que ninguém mediu.
    """
    linhas = relatorio.get("rows")
    if linhas is None:
        return 0
    if not isinstance(linhas, list):
        raise GoogleError(_RELATORIO_FORA_DO_FORMATO)
    if not linhas:
        return 0
    try:
        valor = linhas[0]["metricValues"][0]["value"]
    except (KeyError, IndexError, TypeError) as exc:
        raise GoogleError(_RELATORIO_FORA_DO_FORMATO) from exc
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return 0
    return numero if math.isfinite(numero) else 0


# ─── Ao vivo: as pessoas no Site agora (issue #816) ─────────────────────────
#
# O único número em tempo real da Central, e o único que NÃO passa pelo cache:
# um cache de 1 hora mataria o "agora". Vem do `runRealtimeReport`, a fonte de
# tempo real da GA4, leitura como o `runReport`, pela sua própria porta de rede
# (`_relatorio_em_tempo_real`, mais abaixo).


def pessoas_no_site_agora() -> int:
    """Quantas pessoas estão no Site agora, da fonte de tempo real do Google.

    O `activeUsers` do `runRealtimeReport`, sem dimensão: as pessoas ativas no
    Site nos últimos minutos, o mesmo número que o Google mostra como ativos
    agora. Sem ninguém online, a GA4 omite `rows`, e isso é zero de verdade,
    como no relatório de período. Falha da fonte é `GoogleError` (502 na rota),
    nunca um zero inventado.
    """
    relatorio = _relatorio_em_tempo_real({"metrics": [{"name": "activeUsers"}]})
    return int(_primeira_metrica(relatorio))


# ─── Dados do Google: as perguntas em lote (issue #817) ─────────────────────


@dataclass(frozen=True)
class Pergunta[T]:
    """Um número do Site como pergunta à GA4: os relatórios que ele pede e como
    lê as respostas deles, na mesma ordem.

    Quem faz a pergunta é o `perguntar`, que junta num lote só as perguntas de
    uma tela. É por aqui que a tela Dados do Google cresce (#818): cada número
    novo é uma função daqui que devolve a `Pergunta` dele.
    """

    relatorios: tuple[dict, ...]
    ler: Callable[[tuple[dict, ...]], T]


def perguntar(*perguntas: Pergunta[Any]) -> list[Any]:
    """Faz as perguntas à GA4 e devolve as respostas, na ordem das perguntas.

    Os relatórios de todas vão juntos pelo `batchRunReports`, até 5 por
    chamada (o limite da GA4): a tela que pede três relatórios faz uma ida só
    ao Google, e não três em série. Qualquer falha derruba todas as respostas,
    como a tela, que é tudo ou nada até a #821.
    """
    relatorios = _relatorios_em_lote([corpo for pergunta in perguntas for corpo in pergunta.relatorios])
    respostas: list[Any] = []
    inicio = 0
    for pergunta in perguntas:
        fim = inicio + len(pergunta.relatorios)
        respostas.append(pergunta.ler(tuple(relatorios[inicio:fim])))
        inicio = fim
    return respostas


@dataclass(frozen=True)
class VisitantesNoDia:
    dia: date
    visitantes: int


@dataclass(frozen=True)
class MovimentoDiario:
    """Os Visitantes de cada dia do período e do anterior, sem buraco: o dia
    sem visita vem com zero. As duas séries têm o mesmo tamanho e andam juntas,
    o primeiro dia do período ao lado do primeiro do anterior."""

    atual: tuple[VisitantesNoDia, ...]
    anterior: tuple[VisitantesNoDia, ...]
    intervalo_atual: Intervalo
    intervalo_anterior: Intervalo


def movimento_diario(periodo: Periodo, hoje: date) -> Pergunta[MovimentoDiario]:
    """Os Visitantes por dia, no período e no anterior de mesmo tamanho.

    O `activeUsers` da GA4 por `date`, um relatório por intervalo, como a
    Central antiga (`getVisitorsByDay`), para os números baterem com os dela.
    Cada dia conta as pessoas daquele dia: a soma dos dias passa dos Visitantes
    do período, porque quem volta em outro dia conta de novo.
    """
    atual = intervalo_atual(periodo, hoje)
    anterior = intervalo_anterior(periodo, hoje)

    def ler(relatorios: tuple[dict, ...]) -> MovimentoDiario:
        do_atual, do_anterior = relatorios
        return MovimentoDiario(
            atual=_serie_por_dia(do_atual, atual),
            anterior=_serie_por_dia(do_anterior, anterior),
            intervalo_atual=atual,
            intervalo_anterior=anterior,
        )

    return Pergunta(relatorios=(_visitantes_por_dia_em(atual), _visitantes_por_dia_em(anterior)), ler=ler)


def _visitantes_por_dia_em(intervalo: Intervalo) -> dict:
    return {
        "dateRanges": [_faixa_da_ga4(intervalo)],
        "metrics": [{"name": "activeUsers"}],
        "dimensions": [{"name": "date"}],
    }


def _faixa_da_ga4(intervalo: Intervalo) -> dict[str, str]:
    return {"startDate": intervalo.inicio.isoformat(), "endDate": intervalo.fim.isoformat()}


def _serie_por_dia(relatorio: dict, intervalo: Intervalo) -> tuple[VisitantesNoDia, ...]:
    """Um item por dia do intervalo, na ordem do calendário, com zero no dia
    que a GA4 não devolveu (ela omite o dia sem dado e não promete ordem).

    Linha com um dia que não se lê fica de fora, como na Central antiga
    (`mapVisitorsByDay`), e o dia dela fica com zero.
    """
    por_dia: dict[date, int] = {}
    for valor, numero in _linhas(relatorio):
        dia = _dia_da_ga4(valor)
        if dia is not None:
            por_dia[dia] = int(numero)
    return tuple(VisitantesNoDia(dia, por_dia.get(dia, 0)) for dia in dias_do_intervalo(intervalo))


def _dia_da_ga4(valor: str) -> date | None:
    """A dimensão `date` da GA4 vem sem hífen: "20260917" é 17/09/2026."""
    if not re.fullmatch(r"[0-9]{8}", valor):
        return None
    try:
        return date(int(valor[:4]), int(valor[4:6]), int(valor[6:]))
    except ValueError:
        return None


Dispositivo = Literal["celular", "computador", "tablet"]

# As três categorias de dispositivo da Central, pelo nome que a GA4 dá a cada
# uma. As outras que a GA4 conhece (a "smart tv", por exemplo) ficam de fora,
# como na Central antiga: nenhum termo da fonte chega à tela.
_DISPOSITIVO_DA_GA4: dict[str, Dispositivo] = {"mobile": "celular", "desktop": "computador", "tablet": "tablet"}


@dataclass(frozen=True)
class VisitasNoDispositivo:
    dispositivo: Dispositivo
    visitas: int


def visitas_por_dispositivo(periodo: Periodo, hoje: date) -> Pergunta[tuple[VisitasNoDispositivo, ...]]:
    """As Visitas do período em cada categoria de dispositivo.

    As `sessions` da GA4 por `deviceCategory`, como a Central antiga
    (`getDeviceBreakdown`): conta idas ao Site, e não pessoas, porque a mesma
    pessoa pode entrar pelo celular e pelo computador. Só as categorias que
    apareceram na resposta, somadas por categoria, na ordem celular,
    computador, tablet.
    """

    def ler(relatorios: tuple[dict, ...]) -> tuple[VisitasNoDispositivo, ...]:
        (relatorio,) = relatorios
        visitas: dict[Dispositivo, int] = {}
        for valor, numero in _linhas(relatorio):
            dispositivo = _DISPOSITIVO_DA_GA4.get(valor)
            if dispositivo is not None:
                visitas[dispositivo] = visitas.get(dispositivo, 0) + int(numero)
        return tuple(
            VisitasNoDispositivo(dispositivo, visitas[dispositivo])
            for dispositivo in _DISPOSITIVO_DA_GA4.values()
            if dispositivo in visitas
        )

    corpo = {
        "dateRanges": [_faixa_da_ga4(intervalo_atual(periodo, hoje))],
        "metrics": [{"name": "sessions"}],
        "dimensions": [{"name": "deviceCategory"}],
    }
    return Pergunta(relatorios=(corpo,), ler=ler)


def _linhas(relatorio: dict) -> list[tuple[str, float]]:
    """O valor da dimensão e o número de cada linha, num relatório de uma
    dimensão e uma métrica.

    Sem linha nenhuma, lista vazia: a GA4 omite `rows` quando não houve dado, e
    isso é resposta. Um `rows` que não é lista, ou linha sem a dimensão ou sem a
    métrica, é resposta fora do formato: `GoogleError`, e não um erro de código,
    para a rota responder 502 e o cache servir o último valor bom. Número que
    não é número finito é zero, nunca NaN (o `num` da Central antiga).
    """
    linhas = relatorio.get("rows")
    if linhas is None:
        return []
    if not isinstance(linhas, list):
        raise GoogleError(_RELATORIO_FORA_DO_FORMATO)
    resultado: list[tuple[str, float]] = []
    for linha in linhas:
        try:
            valor = linha["dimensionValues"][0]["value"]
            bruto = linha["metricValues"][0]["value"]
        except (KeyError, IndexError, TypeError) as exc:
            raise GoogleError(_RELATORIO_FORA_DO_FORMATO) from exc
        resultado.append((str(valor), _numero(bruto)))
    return resultado


def _numero(bruto: Any) -> float:
    try:
        numero = float(bruto)
    except (TypeError, ValueError):
        return 0
    return numero if math.isfinite(numero) else 0


def _propriedade() -> str:
    """O número da propriedade, validado: ele entra no caminho da URL."""
    propriedade = settings.ga4_property_id.strip()
    if not re.fullmatch(r"[0-9]+", propriedade):
        raise GoogleNaoConfiguradoError(_PROPRIEDADE_INVALIDA)
    return propriedade


class _SemRede(google.auth.transport.Request):
    """O transporte entregue ao `google-auth`, que nunca deveria usá-lo.

    O JWT de acesso é assinado localmente. Se uma versão futura da biblioteca
    tentar sair para a rede (o endpoint de token, por exemplo), a tentativa
    aparece como erro honesto, em vez de virar uma segunda porta de rede fora
    do timeout e do tratamento de erro deste módulo.
    """

    def __call__(self, url, method="GET", body=None, headers=None, timeout=None, **kwargs):
        raise GoogleError("A credencial do Google tentou uma chamada de rede que a Central não faz.")


def _token_de_acesso() -> str:
    """O JWT de acesso assinado pela service account, com o escopo de leitura.

    Montado a cada chamada: a assinatura é local e custa um milissegundo, e
    sem estado guardado não há chave velha em memória depois de trocar a
    variável.
    """
    conteudo = settings.google_application_credentials_json
    try:
        info = json.loads(conteudo)
    except ValueError:
        # `from None`: o erro do `json` carrega o documento inteiro, que é a
        # chave privada. Ele não pode subir encadeado para log nenhum.
        raise GoogleNaoConfiguradoError(_CREDENCIAL_INVALIDA) from None
    if not isinstance(info, dict) or info.get("type") != "service_account":
        raise GoogleNaoConfiguradoError(_CREDENCIAL_INVALIDA)
    try:
        credencial = service_account.Credentials.from_service_account_info(
            info, scopes=[ESCOPO_DE_LEITURA], always_use_jwt_access=True
        )
        credencial.refresh(_SemRede())
    except (ValueError, TypeError, KeyError, google.auth.exceptions.GoogleAuthError):
        raise GoogleNaoConfiguradoError(_CREDENCIAL_INVALIDA) from None
    return credencial.token


def _verificar_configuracao() -> None:
    """As duas variáveis, antes de qualquer coisa: a mensagem diz TODAS as que
    faltam de uma vez, e não uma por deploy."""
    faltando = [
        nome
        for nome, valor in (
            ("GA4_PROPERTY_ID", settings.ga4_property_id),
            ("GOOGLE_APPLICATION_CREDENTIALS_JSON", settings.google_application_credentials_json),
        )
        if not valor.strip()
    ]
    if faltando:
        raise GoogleNaoConfiguradoError(_FALTA_CONFIGURAR.format(faltando=" e ".join(faltando)))


def _frase_do_status(codigo: int) -> str:
    if codigo in (401, 403):
        return (
            f"O Google Analytics recusou o acesso da Central (HTTP {codigo}). Confira se a service "
            "account tem o papel Leitor na propriedade e se GA4_PROPERTY_ID é o número dela."
        )
    if codigo == 429:
        return "O Google Analytics limitou as consultas da Central (HTTP 429). Tente de novo em alguns minutos."
    return f"O Google Analytics respondeu HTTP {codigo}."


def _motivo_do_google(resposta: httpx.Response) -> str:
    """O `status` e a mensagem do envelope de erro do Google, só para o log."""
    try:
        erro = resposta.json().get("error") or {}
        return f"{erro.get('status', '')}: {str(erro.get('message', ''))[:200]}"
    except (ValueError, AttributeError):
        return "sem corpo legível"


def _postar_na_ga4(verbo: str, corpo: dict) -> Any:
    """POST `{propriedade}:{verbo}` na GA4; devolve o JSON da resposta, ou levanta.

    A porta de rede das perguntas de um relatório só, o `runReport` das telas de
    tendência e o `runRealtimeReport` do Ao vivo: o único lugar onde falha de
    rede, HTTP ou corpo ilegível vira `GoogleError`. A configuração é conferida
    antes de qualquer rede: sem ela, nada sai daqui. Quem chama confere o `kind`
    do relatório que pediu, porque é ele que distingue a resposta da GA4 de um
    `{}` de proxy ou de página de erro.
    """
    _verificar_configuracao()
    propriedade = _propriedade()
    token = _token_de_acesso()
    url = f"{BASE_URL}/properties/{propriedade}:{verbo}"
    try:
        with httpx.Client(timeout=_TIMEOUT) as cliente:
            resposta = cliente.post(url, json=corpo, headers={"Authorization": f"Bearer {token}"})
            resposta.raise_for_status()
            return resposta.json()
    except httpx.HTTPStatusError as exc:
        codigo = exc.response.status_code
        logger.error("[CentralGoogle] %s respondeu HTTP %s (%s)", verbo, codigo, _motivo_do_google(exc.response))
        raise GoogleError(_frase_do_status(codigo)) from exc
    except httpx.TimeoutException as exc:
        logger.error("[CentralGoogle] timeout no %s", verbo)
        raise GoogleError("O Google Analytics não respondeu no tempo esperado.") from exc
    except httpx.HTTPError as exc:
        logger.error("[CentralGoogle] falha de rede no %s: %s", verbo, type(exc).__name__)
        raise GoogleError("Não foi possível falar com o Google Analytics.") from exc
    except ValueError as exc:
        logger.error("[CentralGoogle] corpo ilegível no %s", verbo)
        raise GoogleError("O Google Analytics devolveu uma resposta ilegível.") from exc


def _relatorio(corpo: dict) -> dict:
    """`runReport` na propriedade; devolve o relatório, ou levanta.

    A falha vira `GoogleError` no `_postar_na_ga4`; aqui fica a conferência do
    `kind`: sem ele, o corpo pode ser um `{}` de proxy ou de página de erro, e
    "sem linha" nele viraria um zero que ninguém mediu.
    """
    relatorio = _postar_na_ga4("runReport", corpo)
    if not isinstance(relatorio, dict) or relatorio.get("kind") != _KIND_DO_RELATORIO:
        logger.error("[CentralGoogle] runReport respondeu sem o kind do relatório da GA4")
        raise GoogleError("O Google Analytics devolveu uma resposta fora do formato esperado.")
    return relatorio


# O `kind` fixo do relatório de tempo real, como o `_KIND_DO_RELATORIO` para o de
# período: é ele que distingue "a GA4 respondeu" de um `{}` de proxy, que sem ele
# viraria um zero inventado de pessoas no Site.
_KIND_DO_RELATORIO_EM_TEMPO_REAL = "analyticsData#runRealtimeReport"


def _relatorio_em_tempo_real(corpo: dict) -> dict:
    """`runRealtimeReport` na propriedade; devolve o relatório, ou levanta.

    Como o `_relatorio`, mas na fonte de tempo real do Ao vivo (issue #816): a
    falha sai do `_postar_na_ga4`, e aqui confere o `kind` do relatório de tempo
    real, e não o de período, para um `{}` sem `kind` ser resposta fora do
    formato (502), nunca "ninguém no Site".
    """
    relatorio = _postar_na_ga4("runRealtimeReport", corpo)
    if not isinstance(relatorio, dict) or relatorio.get("kind") != _KIND_DO_RELATORIO_EM_TEMPO_REAL:
        logger.error("[CentralGoogle] runRealtimeReport respondeu sem o kind do relatório de tempo real da GA4")
        raise GoogleError("O Google Analytics devolveu uma resposta fora do formato esperado.")
    return relatorio


# ─── O lote: `batchRunReports` (issue #817) ──────────────────────────────────

# O limite da GA4: um `batchRunReports` leva até 5 relatórios.
_RELATORIOS_POR_LOTE = 5

# A assinatura do lote da GA4, como o `kind` do relatório no `_relatorio`: é ela
# que distingue a resposta do Google de um `{}` de proxy, que viraria zero.
_KIND_DO_LOTE = "analyticsData#batchRunReports"


def _relatorios_em_lote(corpos: list[dict]) -> list[dict]:
    """Os relatórios pedidos, na ordem, pelo `batchRunReports` da propriedade.

    A segunda porta de rede do módulo, no molde do `_relatorio`: a configuração
    é conferida antes de qualquer rede, e toda falha vira `GoogleError`. Mais
    de 5 relatórios viram lotes de 5, que vão ao mesmo tempo, cada um com o seu
    cliente e o mesmo timeout: a tela espera a GA4 uma vez, e não uma por lote.
    """
    _verificar_configuracao()
    propriedade = _propriedade()
    token = _token_de_acesso()
    lotes = [corpos[i : i + _RELATORIOS_POR_LOTE] for i in range(0, len(corpos), _RELATORIOS_POR_LOTE)]
    if len(lotes) <= 1:
        return [relatorio for lote in lotes for relatorio in _um_lote(propriedade, token, lote)]
    with ThreadPoolExecutor(max_workers=len(lotes)) as executor:
        respostas = list(executor.map(partial(_um_lote, propriedade, token), lotes))
    return [relatorio for resposta in respostas for relatorio in resposta]


def _um_lote(propriedade: str, token: str, corpos: list[dict]) -> list[dict]:
    """Um `batchRunReports` de até 5 relatórios; devolve os relatórios, na
    ordem dos pedidos, ou levanta. A tradução de falha é a do `_relatorio`."""
    url = f"{BASE_URL}/properties/{propriedade}:batchRunReports"
    try:
        with httpx.Client(timeout=_TIMEOUT) as cliente:
            resposta = cliente.post(url, json={"requests": corpos}, headers={"Authorization": f"Bearer {token}"})
            resposta.raise_for_status()
            lote = resposta.json()
    except httpx.HTTPStatusError as exc:
        codigo = exc.response.status_code
        logger.error("[CentralGoogle] batchRunReports respondeu HTTP %s (%s)", codigo, _motivo_do_google(exc.response))
        raise GoogleError(_frase_do_status(codigo)) from exc
    except httpx.TimeoutException as exc:
        logger.error("[CentralGoogle] timeout no batchRunReports")
        raise GoogleError("O Google Analytics não respondeu no tempo esperado.") from exc
    except httpx.HTTPError as exc:
        logger.error("[CentralGoogle] falha de rede no batchRunReports: %s", type(exc).__name__)
        raise GoogleError("Não foi possível falar com o Google Analytics.") from exc
    except ValueError as exc:
        logger.error("[CentralGoogle] corpo ilegível no batchRunReports")
        raise GoogleError("O Google Analytics devolveu uma resposta ilegível.") from exc

    relatorios = lote.get("reports") if isinstance(lote, dict) and lote.get("kind") == _KIND_DO_LOTE else None
    if (
        not isinstance(relatorios, list)
        or len(relatorios) != len(corpos)
        or not all(isinstance(relatorio, dict) for relatorio in relatorios)
    ):
        # Sem o `kind` do lote, ou com relatório a menos, a resposta não é da
        # GA4 (ou não é inteira): "sem linha" nela viraria um zero inventado.
        logger.error("[CentralGoogle] batchRunReports respondeu fora do formato do lote da GA4")
        raise GoogleError("O Google Analytics devolveu uma resposta fora do formato esperado.")
    return relatorios


# ─── Áreas do site, Origem do público e Contatos gerados (issue #818) ────────
#
# Mais três números da tela Dados do Google, cada um uma `Pergunta` que entra no
# mesmo `perguntar` da tela. A GA4 só conhece páginas, grupos de canal e eventos
# soltos: juntar isso no que a Central mostra é interpretação da Central, e mora
# aqui, como o nome dos dispositivos. As métricas, as dimensões, os filtros e o
# agrupamento são os da Central antiga, para os números baterem com os dela.

AreaDoSite = Literal["maternidade", "emergencia", "centro-de-imagem", "centro-medico", "laboratorio"]

# A página de cada Área do site no Site, na ordem do catálogo. A Área é a página
# e as subpáginas dela. O caminho segue o endereço VIVO do Site: a Emergência
# mudou de "/emergencia-24h" para "/emergencia", e um caminho morto zeraria a
# Área em silêncio (a Central antiga caiu nisso uma vez).
_CAMINHO_DA_AREA: dict[AreaDoSite, str] = {
    "maternidade": "/maternidade",
    "emergencia": "/emergencia",
    "centro-de-imagem": "/centro-de-imagem",
    "centro-medico": "/centro-medico",
    "laboratorio": "/laboratorio",
}


def area_da_pagina(caminho: str) -> AreaDoSite | None:
    """A Área do site da página, ou `None` para a página que não é de Área
    nenhuma (a inicial, o blog).

    Conta a própria página da Área e as subpáginas dela ("/maternidade" e
    "/maternidade/amamentacao/"), nunca um prefixo parcial: "/maternidade-
    clinica/" não é da Maternidade. Porte do `inSection` da Central antiga.
    """
    for area, base in _CAMINHO_DA_AREA.items():
        if caminho == base or caminho.startswith(f"{base}/"):
            return area
    return None


@dataclass(frozen=True)
class VisitasNaArea:
    area: AreaDoSite
    visitas: int
    visitas_anterior: int


def visitas_por_area_do_site(periodo: Periodo, hoje: date) -> Pergunta[tuple[VisitasNaArea, ...]]:
    """As Visitas às páginas de cada Área do site, no período e no anterior.

    As `sessions` da GA4 por `pagePath`, um relatório por intervalo, somadas
    na Área de cada página, como a Central antiga (`getVisitsByBranch` e
    `mapBranchVisits`). Página fora do catálogo não conta. Sempre as cinco
    Áreas, na ordem do catálogo, com zero na que não teve visita: quem ordena
    o ranking é a tela.
    """
    atual = intervalo_atual(periodo, hoje)
    anterior = intervalo_anterior(periodo, hoje)

    def ler(relatorios: tuple[dict, ...]) -> tuple[VisitasNaArea, ...]:
        do_atual, do_anterior = relatorios
        no_atual = _visitas_por_area(do_atual)
        no_anterior = _visitas_por_area(do_anterior)
        return tuple(VisitasNaArea(area, no_atual[area], no_anterior[area]) for area in _CAMINHO_DA_AREA)

    return Pergunta(relatorios=(_visitas_por_pagina_em(atual), _visitas_por_pagina_em(anterior)), ler=ler)


def _visitas_por_pagina_em(intervalo: Intervalo) -> dict:
    return {
        "dateRanges": [_faixa_da_ga4(intervalo)],
        "metrics": [{"name": "sessions"}],
        "dimensions": [{"name": "pagePath"}],
    }


def _visitas_por_area(relatorio: dict) -> dict[AreaDoSite, int]:
    """As Visitas de cada Área num relatório de Visitas por página, com zero
    na Área que não teve página visitada."""
    visitas = dict.fromkeys(_CAMINHO_DA_AREA, 0)
    for caminho, numero in _linhas(relatorio):
        area = area_da_pagina(caminho)
        if area is not None:
            visitas[area] += int(numero)
    return visitas


OrigemDoPublico = Literal["busca", "direto", "redes", "anuncios", "outros", "nao-identificado"]

# O grupo de canal padrão da GA4 (`sessionDefaultChannelGroup`) de cada Origem do
# público, como o CONTEXT.md define (decisão do dono na #856, que tirou o mapa
# do `CHANNEL_FROM_GA4` da Central antiga). O que o Google não soube classificar
# ("Unassigned", "(not set)" e o nome vazio) é Não identificado; o "(other)", a
# linha em que o Google soma as fatias pequenas, e o grupo identificado que não
# está aqui ("Email", "SMS") são Outros: nenhum termo cru da GA4 chega à tela.
_ORIGEM_DO_CANAL: dict[str, OrigemDoPublico] = {
    "Organic Search": "busca",
    "Direct": "direto",
    "Organic Social": "redes",
    "Paid Social": "redes",
    "Paid Search": "anuncios",
    "Display": "anuncios",
    "Paid Shopping": "anuncios",
    "Paid Video": "anuncios",
    "Paid Other": "anuncios",
    "Cross-network": "anuncios",
    "Unassigned": "nao-identificado",
    "(not set)": "nao-identificado",
    "(other)": "outros",
}


def origem_do_canal(canal: str) -> OrigemDoPublico:
    """A Origem do público de um grupo de canal da GA4, com três regras: o
    grupo do mapa vira a origem dele; o nome vazio é Não identificado;
    qualquer outro grupo é Outros."""
    if canal in _ORIGEM_DO_CANAL:
        return _ORIGEM_DO_CANAL[canal]
    if canal == "":
        return "nao-identificado"
    return "outros"


@dataclass(frozen=True)
class VisitasNaOrigem:
    origem: OrigemDoPublico
    visitas: int


def visitas_por_origem(periodo: Periodo, hoje: date) -> Pergunta[tuple[VisitasNaOrigem, ...]]:
    """As Visitas do período em cada Origem do público.

    As `sessions` da GA4 por `sessionDefaultChannelGroup`, como a Central
    antiga (`getTrafficSources` e `mapTrafficSources`), somadas por origem.
    Só as origens que apareceram na resposta, na ordem em que apareceram:
    quem ordena para a tela é a tela.
    """

    def ler(relatorios: tuple[dict, ...]) -> tuple[VisitasNaOrigem, ...]:
        (relatorio,) = relatorios
        visitas: dict[OrigemDoPublico, int] = {}
        for canal, numero in _linhas(relatorio):
            origem = origem_do_canal(canal)
            visitas[origem] = visitas.get(origem, 0) + int(numero)
        return tuple(VisitasNaOrigem(origem, numero) for origem, numero in visitas.items())

    corpo = {
        "dateRanges": [_faixa_da_ga4(intervalo_atual(periodo, hoje))],
        "metrics": [{"name": "sessions"}],
        "dimensions": [{"name": "sessionDefaultChannelGroup"}],
    }
    return Pergunta(relatorios=(corpo,), ler=ler)


CanalDeContato = Literal["agendar", "whatsapp", "fale-conosco", "telefone"]


@dataclass(frozen=True)
class CliquesNoCanal:
    canal: CanalDeContato
    cliques: int


def cliques_de_contato(periodo: Periodo, hoje: date) -> Pergunta[tuple[CliquesNoCanal, ...]]:
    """Os cliques do período nos canais de contato que a GA4 mede.

    O `eventCount` da GA4 por `eventName`, filtrado pelos dois eventos que o
    Site dispara (`GA4_EVENTO_WHATSAPP` e `GA4_EVENTO_FALE_CONOSCO`), como a
    Central antiga (`getContactClicks` e `mapContactClicks`). O agendar entra
    sempre com zero, porque o botão de marcar consulta ainda não dispara
    evento, e a tela o lê como em construção; o telefone fica de fora, porque
    ligação não é clique, e a tela o lê como não medido. Evento que não
    aconteceu no período é zero, não ausência: a GA4 omite a linha dele.
    """
    whatsapp = settings.ga4_evento_whatsapp
    fale_conosco = settings.ga4_evento_fale_conosco

    def ler(relatorios: tuple[dict, ...]) -> tuple[CliquesNoCanal, ...]:
        (relatorio,) = relatorios
        por_evento = {evento: int(numero) for evento, numero in _linhas(relatorio)}
        return (
            CliquesNoCanal("agendar", 0),
            CliquesNoCanal("whatsapp", por_evento.get(whatsapp, 0)),
            CliquesNoCanal("fale-conosco", por_evento.get(fale_conosco, 0)),
        )

    corpo = {
        "dateRanges": [_faixa_da_ga4(intervalo_atual(periodo, hoje))],
        "metrics": [{"name": "eventCount"}],
        "dimensions": [{"name": "eventName"}],
        "dimensionFilter": {
            "filter": {"fieldName": "eventName", "inListFilter": {"values": [whatsapp, fale_conosco]}},
        },
    }
    return Pergunta(relatorios=(corpo,), ler=ler)
