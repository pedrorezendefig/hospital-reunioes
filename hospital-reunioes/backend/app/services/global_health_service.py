"""Espelho da Global Health (ADR 0038): o único ponto do app que fala com a
agenda online da Global Health (GH).

Módulo profundo, porta estreita: cada elo da cadeia da GH vira uma função que
devolve linhas prontas para a tela. Aqui moram a base, o header de
autenticação, o timeout e a tradução de erro; nenhum outro módulo importa
`httpx` para falar com a GH.

Três invariantes que o resto do app herda de graça:

- **Só homologação.** A base é constante fixa neste arquivo; produção
  (`app.agenda.globalhealth.mv`) jamais é chamada por este código.
- **Só leitura.** Nenhum verbo de escrita existe aqui: o Espelho não agenda,
  não cadastra e não altera nada na GH.
- **Falha é falha.** Timeout, 5xx e erro de rede viram `GlobalHealthError`,
  distinta de resposta vazia. Lista vazia é uma resposta ("nada publicado");
  falha é ausência de resposta, e a tela precisa saber a diferença.

Nada do que a GH responde é gravado em banco: é espelho, não cópia.
"""

from __future__ import annotations

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# Base de HOMOLOGAÇÃO da agenda online da Global Health (ADR 0038, decisão 6).
# Produção (`https://app.agenda.globalhealth.mv`) jamais é chamada por este
# código: trocar esta constante é decisão consciente, revisada em commit.
BASE_URL = "https://dem.agenda.globalhealth.mv/rest/whatsapp"

# Timeout curto: a secretária espera a resposta olhando a tela. Erro honesto
# em segundos vale mais que tela pendurada (padrão da casa: connect menor).
_TIMEOUT = httpx.Timeout(10.0, connect=3.0)


class GlobalHealthError(RuntimeError):
    """A Global Health não respondeu (timeout, 5xx, rede, corpo ilegível).

    Distinta de resposta vazia: a mensagem sobe para a tela como erro.
    """


class GlobalHealthNaoConfiguradaError(RuntimeError):
    """`GH_TOKEN_HOMOLOG` ausente: o app não tem como se autenticar na GH."""


def _headers() -> dict[str, str]:
    token = settings.gh_token_homolog
    if not token:
        raise GlobalHealthNaoConfiguradaError("GH_TOKEN_HOMOLOG não configurado no backend")
    return {"Token": token, "Accept": "application/json"}


def _listar(path: str, params: dict | None = None) -> list[dict]:
    """GET numa lista paginada da GH; devolve o `conteudo` da página.

    O envelope da GH é `{"conteudo": [...], "paginaAnterior": "",
    "paginaSeguinte": ""}`. Só GET: este é o único acesso à rede do módulo.
    """
    headers = _headers()
    url = f"{BASE_URL}{path}"
    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            resposta = client.get(url, params=params or None, headers=headers)
            resposta.raise_for_status()
            corpo = resposta.json()
    except httpx.HTTPStatusError as exc:
        codigo = exc.response.status_code
        logger.error(f"[GlobalHealth] {path} respondeu HTTP {codigo}")
        raise GlobalHealthError(f"A Global Health respondeu HTTP {codigo}.") from exc
    except httpx.TimeoutException as exc:
        logger.error(f"[GlobalHealth] timeout em {path}")
        raise GlobalHealthError("A Global Health não respondeu no tempo esperado.") from exc
    except httpx.HTTPError as exc:
        logger.error(f"[GlobalHealth] falha de rede em {path}: {type(exc).__name__}")
        raise GlobalHealthError("Não foi possível falar com a Global Health.") from exc
    except ValueError as exc:
        logger.error(f"[GlobalHealth] corpo ilegível em {path}")
        raise GlobalHealthError("A Global Health devolveu uma resposta ilegível.") from exc

    if not isinstance(corpo, dict):
        raise GlobalHealthError("A Global Health devolveu uma resposta fora do formato esperado.")
    # Item sem `id` é inútil: não identifica nada na GH, não serve de chave na
    # tela e não pode alimentar o elo seguinte da cadeia. Fica de fora.
    return [item for item in (corpo.get("conteudo") or []) if isinstance(item, dict) and item.get("id") is not None]


def listar_especialidades(pesquisa: str | None = None) -> list[dict]:
    """Elo 1: especialidades publicadas na agenda (`GET /consultas`).

    É a lista do que a Ana consegue agendar hoje. `pesquisa` filtra pelo nome
    na própria GH. Campos publicados: `id`, `nome`, `bloqueado`.
    """
    params = {"pesquisa": pesquisa} if pesquisa else None
    return [
        {
            "id": item.get("id"),
            "nome": item.get("nome"),
            "bloqueado": bool(item.get("bloqueado")),
        }
        for item in _listar("/consultas", params)
    ]
