"""Provedor de dados do Google da Central de Comando (ADR 0058, PRD #809).

O ÚNICO ponto do app que fala com o Google Analytics. Módulo profundo, porta
estreita, no molde do Espelho da Global Health (`global_health_service.py`):
aqui moram a base da API, a credencial, o timeout, a pergunta que cada número
faz à GA4 e a tradução de erro. Quem está fora recebe números do domínio
("Visitantes do período e do anterior"), nunca linha de relatório da GA4.

Três invariantes que o resto do app herda de graça:

- **Só leitura.** A credencial pede só o escopo de leitura, e o único verbo é
  o `runReport` (o Ao vivo acrescenta o `runRealtimeReport`, também leitura).
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
dispositivos, Contatos gerados, Ao vivo), e toda chamada à GA4 passa pelo
`_relatorio`, que é a única porta de rede do módulo.
"""

from __future__ import annotations

import json
import logging
import math
import re
from dataclasses import dataclass
from datetime import date

import google.auth.exceptions
import google.auth.transport
import httpx
from google.oauth2 import service_account

from app.config import settings
from app.services.central_de_comando.periodo import Intervalo, Periodo, intervalo_anterior, intervalo_atual

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
    dado, e isso é resposta, não falha. Valor que não é número finito também é
    zero, como na Central antiga (`firstMetric`): anomalia da GA4 nunca chega à
    tela como "NaN". Linha sem o campo de métrica, essa sim, é resposta fora do
    formato.
    """
    linhas = relatorio.get("rows") or []
    if not linhas:
        return 0
    try:
        valor = linhas[0]["metricValues"][0]["value"]
    except (KeyError, IndexError, TypeError) as exc:
        raise GoogleError("O Google Analytics devolveu um relatório fora do formato esperado.") from exc
    try:
        numero = float(valor)
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


def _relatorio(corpo: dict) -> dict:
    """`runReport` na propriedade; devolve o relatório, ou levanta.

    A única porta de rede do módulo, e o único lugar onde falha vira
    `GoogleError`. A configuração é conferida antes de qualquer rede: sem ela,
    nada sai daqui.
    """
    _verificar_configuracao()
    propriedade = _propriedade()
    token = _token_de_acesso()
    url = f"{BASE_URL}/properties/{propriedade}:runReport"
    try:
        with httpx.Client(timeout=_TIMEOUT) as cliente:
            resposta = cliente.post(url, json=corpo, headers={"Authorization": f"Bearer {token}"})
            resposta.raise_for_status()
            relatorio = resposta.json()
    except httpx.HTTPStatusError as exc:
        codigo = exc.response.status_code
        logger.error("[CentralGoogle] runReport respondeu HTTP %s (%s)", codigo, _motivo_do_google(exc.response))
        raise GoogleError(_frase_do_status(codigo)) from exc
    except httpx.TimeoutException as exc:
        logger.error("[CentralGoogle] timeout no runReport")
        raise GoogleError("O Google Analytics não respondeu no tempo esperado.") from exc
    except httpx.HTTPError as exc:
        logger.error("[CentralGoogle] falha de rede no runReport: %s", type(exc).__name__)
        raise GoogleError("Não foi possível falar com o Google Analytics.") from exc
    except ValueError as exc:
        logger.error("[CentralGoogle] corpo ilegível no runReport")
        raise GoogleError("O Google Analytics devolveu uma resposta ilegível.") from exc

    if not isinstance(relatorio, dict):
        raise GoogleError("O Google Analytics devolveu uma resposta fora do formato esperado.")
    return relatorio
