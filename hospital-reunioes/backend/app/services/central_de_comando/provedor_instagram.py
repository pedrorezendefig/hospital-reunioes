"""Provedor de dados do Instagram da Central de Comando (ADR 0058, PRD #809).

O ÚNICO ponto do app que fala com a Graph API do Instagram. Módulo profundo,
porta estreita, no molde do provedor do Google (`provedor_google.py`) e do
Espelho da Global Health: aqui moram a base da API, o token, o timeout, a
pergunta que cada número faz e a tradução de erro. Quem está fora recebe tipos
do domínio (Seguidores e crescimento, Alcance, Visualizações, Interações e as
partes, Contas que engajaram, Principais publicações), nunca linha crua da API.

**Na interface e nas mensagens diz-se "Instagram".** A empresa dona da rede não
é citada em identificador nem em tela (ADR 0058). O único lugar onde o nome dela
é inevitável é o host real da Graph API, isolado na constante `BASE_URL` deste
módulo server-side: ele nunca chega ao front nem a um identificador de domínio.

Porte das regras de `src/lib/instagram` do repositório antigo (a ADR 0005 de
lá), adaptando o nome do provedor de "meta" para "instagram". Cada teste de
regra de lá tem o seu equivalente aqui (`test_central_de_comando_instagram_*`).

Três invariantes que a tela herda:

- **Terminologia nativa do Instagram** (Alcance, Visualizações, Seguidores,
  Interações), na linguagem que o diretor vê no próprio app.
- **Não configurado é 503, nunca zero.** Sem o token ou sem o id da conta, a
  exceção é `InstagramNaoConfiguradoError`, com a frase fixa
  `FRASE_NAO_CONFIGURADO` (sem nome de variável; o que falta vai para o log).
- **Token vencido mantém o último valor bom.** O token do Instagram expira e é
  renovado à mão. Quando a Graph API o recusa, a exceção é
  `InstagramTokenExpiradoError`, uma falha da fonte (subclasse de
  `InstagramError`): com número guardado, o cache serve o último valor bom e a
  frase de renovação vira o `motivo` do frescor; sem número guardado, é 502.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

import httpx

from app.config import settings
from app.services.central_de_comando.periodo import (
    Intervalo,
    Periodo,
    intervalo_anterior,
    intervalo_atual,
)

logger = logging.getLogger(__name__)

# A Graph API do Instagram. Constante, e não variável de ambiente: apontar para
# outra API é decisão revisada em commit, como a base do provedor do Google. É o
# ÚNICO lugar do módulo onde o host real (que carrega o nome da empresa dona da
# rede) aparece, isolado server-side, longe da tela e de qualquer identificador.
BASE_URL = "https://graph.facebook.com/v23.0"

# Timeout curto: quem espera olha a tela. Erro honesto em segundos vale mais que
# tela pendurada (padrão da casa: connect menor).
_TIMEOUT = httpx.Timeout(10.0, connect=3.0)

# O `code` da Graph API que quer dizer "token vencido ou revogado". Só ele: o
# `code` 100 (janela grande demais, por exemplo) chega com o mesmo type
# OAuthException e NÃO é token vencido (regressão herdada da Central antiga).
_CODE_TOKEN_VENCIDO = 190

# A frase do token vencido: fixa, porque vai para a tela como o motivo do último
# valor bom. Fala em renovar, diz "Instagram" e nunca ecoa o token nem cita a
# empresa dona da rede.
_TOKEN_VENCIDO = "O acesso ao Instagram expirou. Renove o token para voltar a atualizar os números."

# A frase de "não configurado": fixa e sem nome de variável de ambiente (issue
# #843). É a mesma na tela e no cliente MCP; o que falta vai para o log.
FRASE_NAO_CONFIGURADO = (
    "A Central de Comando ainda não está ligada ao Instagram no servidor. "
    "Enquanto isso, nenhum número do Instagram é mostrado."
)


class InstagramError(RuntimeError):
    """A Graph API do Instagram não respondeu, recusou o acesso ou respondeu
    fora do formato. A mensagem é fixa e segura (sem URL nem token) e sobe para
    a tela como o motivo do último valor bom (502 na rota sem número guardado)."""


class InstagramTokenExpiradoError(InstagramError):
    """O token de acesso do Instagram venceu ou foi revogado (`code` 190 da
    Graph API). É uma falha da fonte (subclasse de `InstagramError`, então entra
    na tupla `falhas` da tela): com número guardado, o cache serve o último
    valor bom e esta frase de renovação vira o `motivo` do frescor; sem número
    guardado, é 502. O token é renovado à mão, como na Central antiga."""

    def __init__(self, mensagem: str = _TOKEN_VENCIDO):
        super().__init__(mensagem)


class InstagramNaoConfiguradoError(RuntimeError):
    """Falta o token ou o id da conta profissional do Instagram. A mensagem é
    a `FRASE_NAO_CONFIGURADO`, sem nome de variável; o que falta vai para o
    log, sem nunca ecoar o token. Não é falha da fonte: sempre 503, e nunca
    vira último valor bom."""


# ─── Os tipos do domínio (o que sai deste módulo) ───────────────────────────

TipoDeMidia = Literal["imagem", "carrossel", "reel", "video"]


@dataclass(frozen=True)
class PartesDoEngajamento:
    """As quatro partes que somam as Interações, na ordem em que a tela mostra."""

    curtidas: int
    comentarios: int
    salvamentos: int
    compartilhamentos: int


@dataclass(frozen=True)
class SaudeDaConta:
    """A saúde da conta no período e no anterior: Seguidores (estoque) e o
    crescimento do período, Alcance, Visualizações, Interações e as partes, e
    as Contas que engajaram. Cada número viaja com o do período anterior."""

    seguidores: int
    crescimento: int
    crescimento_anterior: int
    seguidores_ganhos: int
    seguidores_perdidos: int
    alcance: int
    alcance_anterior: int
    visualizacoes: int
    visualizacoes_anterior: int
    interacoes: int
    interacoes_anterior: int
    contas_engajadas: int
    contas_engajadas_anterior: int
    partes: PartesDoEngajamento


@dataclass(frozen=True)
class Publicacao:
    """Uma publicação do período: o tipo, a miniatura, a legenda, o link para o
    Instagram e as Interações que ela teve. Stories não entram."""

    id: str
    legenda: str | None
    tipo: TipoDeMidia
    miniatura: str
    link: str
    data: str
    interacoes: int


# ─── Os mapeadores da Graph API para o domínio (regras puras) ───────────────
#
# Porte de `meta-mappers.ts`. Nenhuma fala com rede: recebem o corpo cru que a
# porta de rede leu e devolvem tipo do domínio. Testadas direto em
# `test_central_de_comando_instagram_mapeamento.py`.


def valor_do_insight(insights: list[dict], nome: str) -> int:
    """O valor de um insight da conta pelo nome, ou 0 quando ausente.

    A métrica que não veio no array vira 0, nunca None: a conta que não teve
    Alcance no período mostra zero, e a tela não quebra. Prefere o
    `total_value.value` (o que a Graph API entrega com `metric_type=total_value`);
    na falta dele, soma os `values[].value`."""
    for insight in insights:
        if insight.get("name") != nome:
            continue
        total_value = insight.get("total_value")
        if isinstance(total_value, dict):
            valor = total_value.get("value")
            return int(valor) if isinstance(valor, int | float) else 0
        valores = insight.get("values")
        if isinstance(valores, list):
            return int(sum(v.get("value", 0) for v in valores if isinstance(v, dict)))
        return 0
    return 0


def delta_de_seguidores(insight: dict | None) -> tuple[int, int]:
    """Ganhos e perdas de seguidores do insight `follows_and_unfollows`.

    Do `total_value.breakdowns[0].results`, `FOLLOWER` é ganho e `NON_FOLLOWER`
    é perda. Insight ausente ou sem breakdown é zero ganhos e zero perdas."""
    if not isinstance(insight, dict):
        return (0, 0)
    breakdowns = (insight.get("total_value") or {}).get("breakdowns") or []
    if not breakdowns:
        return (0, 0)
    ganhos = 0
    perdidos = 0
    for resultado in breakdowns[0].get("results") or []:
        dimensoes = resultado.get("dimension_values") or []
        valor = resultado.get("value") or 0
        if dimensoes[:1] == ["FOLLOWER"]:
            ganhos = int(valor)
        elif dimensoes[:1] == ["NON_FOLLOWER"]:
            perdidos = int(valor)
    return (ganhos, perdidos)


def montar_saude(
    seguidores: int,
    insights_atual: list[dict],
    insights_anterior: list[dict],
    follows_atual: dict | None,
    follows_anterior: dict | None,
) -> SaudeDaConta:
    """Junta os Seguidores, os insights do período e do anterior e o crescimento
    (da chamada dedicada de `follows_and_unfollows`) num `SaudeDaConta`."""
    ganhos, perdidos = delta_de_seguidores(follows_atual)
    ganhos_ant, perdidos_ant = delta_de_seguidores(follows_anterior)
    return SaudeDaConta(
        seguidores=seguidores,
        crescimento=ganhos - perdidos,
        crescimento_anterior=ganhos_ant - perdidos_ant,
        seguidores_ganhos=ganhos,
        seguidores_perdidos=perdidos,
        alcance=valor_do_insight(insights_atual, "reach"),
        alcance_anterior=valor_do_insight(insights_anterior, "reach"),
        visualizacoes=valor_do_insight(insights_atual, "views"),
        visualizacoes_anterior=valor_do_insight(insights_anterior, "views"),
        interacoes=valor_do_insight(insights_atual, "total_interactions"),
        interacoes_anterior=valor_do_insight(insights_anterior, "total_interactions"),
        contas_engajadas=valor_do_insight(insights_atual, "accounts_engaged"),
        contas_engajadas_anterior=valor_do_insight(insights_anterior, "accounts_engaged"),
        partes=PartesDoEngajamento(
            curtidas=valor_do_insight(insights_atual, "likes"),
            comentarios=valor_do_insight(insights_atual, "comments"),
            salvamentos=valor_do_insight(insights_atual, "saves"),
            compartilhamentos=valor_do_insight(insights_atual, "shares"),
        ),
    )


def tipo_de_midia(media_type: str, media_product_type: str | None) -> TipoDeMidia:
    """O tipo de mídia da tela a partir do `media_type` e do `media_product_type`.

    Imagem, carrossel, reel (vídeo publicado como Reel) e vídeo (o resto).
    Qualquer combinação desconhecida cai em vídeo, como na Central antiga."""
    if media_type == "IMAGE":
        return "imagem"
    if media_type == "CAROUSEL_ALBUM":
        return "carrossel"
    if media_type == "VIDEO" and media_product_type == "REELS":
        return "reel"
    return "video"


def dentro_do_periodo(timestamp: str, intervalo: Intervalo) -> bool:
    """A publicação está na janela, comparando só a DATA do timestamp, inclusive
    nas duas pontas. Publicação das 23h do último dia entra."""
    try:
        dia = date.fromisoformat(timestamp[:10])
    except ValueError:
        return False
    return intervalo.inicio <= dia <= intervalo.fim


def para_publicacao(midia: dict, interacoes: int) -> Publicacao:
    """Uma publicação da Graph API vira `Publicacao`. A miniatura é a
    `thumbnail_url`; sem ela, a `media_url`; sem nenhuma, string vazia. A
    legenda ausente é None (a tela decide o texto alternativo)."""
    miniatura = midia.get("thumbnail_url")
    if miniatura is None:
        miniatura = midia.get("media_url")
    if miniatura is None:
        miniatura = ""
    return Publicacao(
        id=str(midia["id"]),
        legenda=midia.get("caption"),
        tipo=tipo_de_midia(midia["media_type"], midia.get("media_product_type")),
        miniatura=miniatura,
        link=midia["permalink"],
        data=midia["timestamp"],
        interacoes=interacoes,
    )


def ranquear_por_interacoes(publicacoes: list[Publicacao], limite: int) -> list[Publicacao]:
    """As publicações da mais engajada para a menos (por Interações), cortadas
    no limite. Empate mantém a ordem de chegada (a ordenação é estável)."""
    return sorted(publicacoes, key=lambda p: p.interacoes, reverse=True)[:limite]


# ─── A configuração e a porta de rede ───────────────────────────────────────

# Os campos de cada mídia que a borda `/media` traz. Sem `like_count` nem
# `comments_count`: as Interações da publicação vêm da métrica `total_interactions`
# de cada mídia, a mesma definição que soma as Interações da conta.
_CAMPOS_DA_MIDIA = "id,caption,media_type,media_product_type,media_url,thumbnail_url,permalink,timestamp"

# As métricas da conta que a saúde pede numa chamada só, na definição da Central
# antiga (Interações = curtidas + comentários + salvamentos + compartilhamentos).
METRICAS_DA_CONTA = ("reach", "views", "total_interactions", "accounts_engaged", "likes", "comments", "saves", "shares")

# Quantas mídias recentes olhar para achar as do período. As Principais
# publicações saem das que caem na janela, então varrer as 25 últimas cobre 7 e
# 28 dias com folga, como na Central antiga.
_MIDIAS_ESCANEADAS = 25


def _verificar_configuracao() -> None:
    """O token e o id da conta, antes de qualquer rede: o log diz TODOS os que
    faltam de uma vez, e nunca ecoa o token."""
    faltando = [
        nome
        for nome, valor in (
            ("INSTAGRAM_ACCESS_TOKEN", settings.instagram_access_token),
            ("INSTAGRAM_BUSINESS_ACCOUNT_ID", settings.instagram_business_account_id),
        )
        if not valor.strip()
    ]
    if faltando:
        logger.warning("[CentralInstagram] não configurado: falta configurar %s", " e ".join(faltando))
        raise InstagramNaoConfiguradoError(FRASE_NAO_CONFIGURADO)


def _conta() -> str:
    return settings.instagram_business_account_id.strip()


def _codigo_do_erro(resposta: httpx.Response) -> int | None:
    """O `error.code` do envelope de erro da Graph API, ou None se ilegível."""
    try:
        return (resposta.json().get("error") or {}).get("code")
    except (ValueError, AttributeError):
        return None


def _motivo(resposta: httpx.Response) -> str:
    """O `code` e a mensagem do envelope de erro, só para o log (nunca a URL,
    que carrega o token)."""
    try:
        erro = resposta.json().get("error") or {}
        return f"code {erro.get('code')}: {str(erro.get('message', ''))[:200]}"
    except (ValueError, AttributeError):
        return "sem corpo legível"


def _pedir(caminho: str, params: dict[str, str]) -> Any:
    """GET numa borda da Graph API; devolve o JSON, ou levanta.

    A ÚNICA porta de rede do módulo: o único lugar onde falha de rede, HTTP ou
    corpo ilegível vira `InstagramError`, e o token vencido (`code` 190) vira
    `InstagramTokenExpiradoError`. A configuração é conferida antes de qualquer
    rede: sem ela, nada sai daqui. O token vai no header `Authorization: Bearer`,
    como no provedor do Google, e nunca na query string: o httpx registra a URL
    do pedido em log, e um token na URL vazaria em texto puro no stdout."""
    _verificar_configuracao()
    url = f"{BASE_URL}/{caminho}"
    cabecalhos = {"Authorization": f"Bearer {settings.instagram_access_token}"}
    try:
        with httpx.Client(timeout=_TIMEOUT) as cliente:
            resposta = cliente.get(url, params=params, headers=cabecalhos)
            resposta.raise_for_status()
            return resposta.json()
    except httpx.HTTPStatusError as exc:
        codigo = exc.response.status_code
        if _codigo_do_erro(exc.response) == _CODE_TOKEN_VENCIDO:
            logger.error("[CentralInstagram] token vencido (code 190, HTTP %s)", codigo)
            raise InstagramTokenExpiradoError() from exc
        logger.error("[CentralInstagram] %s respondeu HTTP %s (%s)", caminho, codigo, _motivo(exc.response))
        raise InstagramError(f"O Instagram respondeu HTTP {codigo}.") from exc
    except httpx.TimeoutException as exc:
        logger.error("[CentralInstagram] timeout em %s", caminho)
        raise InstagramError("O Instagram não respondeu no tempo esperado.") from exc
    except httpx.HTTPError as exc:
        logger.error("[CentralInstagram] falha de rede em %s: %s", caminho, type(exc).__name__)
        raise InstagramError("Não foi possível falar com o Instagram.") from exc
    except ValueError as exc:
        logger.error("[CentralInstagram] corpo ilegível em %s", caminho)
        raise InstagramError("O Instagram devolveu uma resposta ilegível.") from exc


def _seguidores() -> int:
    """O total de Seguidores agora, do perfil (não de uma janela): é estoque."""
    dados = _pedir(_conta(), {"fields": "followers_count"})
    valor = dados.get("followers_count") if isinstance(dados, dict) else None
    return int(valor) if isinstance(valor, int | float) else 0


def _insights_da_conta(metricas: tuple[str, ...], intervalo: Intervalo) -> list[dict]:
    """Os insights da conta no intervalo, numa chamada só (`metric_type=total_value`)."""
    dados = _pedir(
        f"{_conta()}/insights",
        {
            "metric": ",".join(metricas),
            "metric_type": "total_value",
            "period": "day",
            "since": intervalo.inicio.isoformat(),
            "until": intervalo.fim.isoformat(),
        },
    )
    data = dados.get("data") if isinstance(dados, dict) else None
    return data or []


def _seguidores_e_nao_seguidores(intervalo: Intervalo) -> dict | None:
    """O insight `follows_and_unfollows` do intervalo, com o breakdown por
    `follow_type` (ganhos e perdas), a chamada dedicada do crescimento."""
    dados = _pedir(
        f"{_conta()}/insights",
        {
            "metric": "follows_and_unfollows",
            "metric_type": "total_value",
            "breakdown": "follow_type",
            "period": "day",
            "since": intervalo.inicio.isoformat(),
            "until": intervalo.fim.isoformat(),
        },
    )
    data = dados.get("data") if isinstance(dados, dict) else None
    return data[0] if data else None


def _midias_recentes(limite: int) -> list[dict]:
    dados = _pedir(f"{_conta()}/media", {"fields": _CAMPOS_DA_MIDIA, "limit": str(limite)})
    data = dados.get("data") if isinstance(dados, dict) else None
    return data or []


def _interacoes_da_midia(media_id: str) -> int:
    """As Interações de uma mídia (`total_interactions`).

    Sem `metric_type=total_value` (que é da conta), a Graph API devolve o valor
    da mídia como `values:[{value}]`, e NÃO como `total_value`. O
    `valor_do_insight` lê as duas formas, o mesmo `total_value.value ??
    values[0].value ?? 0` do `insightValue` da Central antiga: sem esse fallback,
    toda publicação voltaria com 0 Interações com o token real, e o ranking das
    Principais publicações quebraria."""
    dados = _pedir(f"{media_id}/insights", {"metric": "total_interactions"})
    data = dados.get("data") if isinstance(dados, dict) else None
    if not data:
        return 0
    return valor_do_insight(data, "total_interactions")


# ─── A porta pública do provedor ────────────────────────────────────────────


def saude_da_conta(periodo: Periodo, hoje: date) -> SaudeDaConta:
    """A saúde da conta no período e no anterior de mesmo tamanho.

    Seguidores do perfil (estoque), os insights da conta no atual e no anterior,
    e o crescimento da chamada dedicada, nos dois intervalos. Falha da fonte sobe
    como `InstagramError` (ou `InstagramTokenExpiradoError`): o cache trata acima."""
    atual = intervalo_atual(periodo, hoje)
    anterior = intervalo_anterior(periodo, hoje)
    return montar_saude(
        _seguidores(),
        _insights_da_conta(METRICAS_DA_CONTA, atual),
        _insights_da_conta(METRICAS_DA_CONTA, anterior),
        _seguidores_e_nao_seguidores(atual),
        _seguidores_e_nao_seguidores(anterior),
    )


def _e_story(midia: dict) -> bool:
    """A publicação é um Story. A tela não mostra Stories (critério de aceite):
    a borda `/media` já traz feed, e este filtro garante que um Story que passe
    por ela fique de fora."""
    return midia.get("media_product_type") == "STORY"


def principais_publicacoes(periodo: Periodo, hoje: date, limite: int = 6) -> list[Publicacao]:
    """As Principais publicações do período, ranqueadas por Interações.

    Filtra as mídias recentes pela janela e tira os Stories ANTES de buscar as
    Interações de cada uma: a publicação fora do período não gasta uma chamada,
    e o Story nunca disputa o ranking, mesmo com muitas Interações."""
    intervalo = intervalo_atual(periodo, hoje)
    do_periodo = [
        midia
        for midia in _midias_recentes(_MIDIAS_ESCANEADAS)
        if not _e_story(midia) and dentro_do_periodo(midia["timestamp"], intervalo)
    ]
    publicacoes = [para_publicacao(midia, _interacoes_da_midia(midia["id"])) for midia in do_periodo]
    return ranquear_por_interacoes(publicacoes, limite)
