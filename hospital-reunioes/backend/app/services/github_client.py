"""O unico ponto do app que fala com a API do GitHub (issue #674, ADR 0054).

Modulo profundo, porta estreita: quem chama pede "a foto da issue #673" ou
"marque esta issue com o id desta Demanda", e recebe dado pronto ou uma
excecao. Base, header, timeout e traducao de erro moram aqui; nenhum outro
modulo importa `httpx` para falar com o GitHub.

Tres invariantes que o resto do app herda:

- **So este repositorio.** O repositorio vem de `GITHUB_INTEGRACAO_REPO` e
  entra no caminho da URL uma vez so, aqui.
- **Escrita minima.** O unico verbo de escrita e o PATCH do corpo da issue, que
  serve ao marcador do Vinculo. O token fine-grained do Pedro tem Issues: write
  neste repositorio e mais nada (ADR 0054, decisao 8).
- **Falha e falha.** Timeout, 5xx e erro de rede viram `GithubIndisponivelError`;
  404 vira `IssueNaoEncontradaError`. Sem token ou sem repositorio configurado e
  `GithubNaoConfiguradoError`, que a rota traduz em 503: o app nao FINGE que leu.

A foto que sai daqui e o dicionario que o servico puro (`tecnologia_vinculo`)
sabe ler, e nao o JSON cru do GitHub: a Etapa nao pode depender do nome de um
campo de terceiro espalhado por tres arquivos.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import settings
from app.services.tecnologia_vinculo import bloco_para_o_diretor

logger = logging.getLogger(__name__)

BASE_URL = "https://api.github.com"

# Timeout curto: quem clicou em Vincular esta olhando a tela esperando o selo.
# Erro honesto em segundos vale mais do que tela pendurada (o mesmo criterio do
# Espelho da Global Health).
_TIMEOUT = httpx.Timeout(10.0, connect=3.0)

# Versao do formato de resposta, como a doc do GitHub pede. Sem ela, a API pode
# mudar a forma do corpo sob os pes do app sem aviso nenhum.
_VERSAO_DA_API = "2022-11-28"


class GithubNaoConfiguradoError(RuntimeError):
    """Falta `GITHUB_INTEGRACAO_TOKEN` ou `GITHUB_INTEGRACAO_REPO`."""


class GithubIndisponivelError(RuntimeError):
    """O GitHub nao respondeu (timeout, 5xx, rede, corpo ilegivel)."""


class IssueNaoEncontradaError(RuntimeError):
    """O numero pedido nao existe no repositorio da integracao."""


def integracao_configurada() -> bool:
    """Se as duas variaveis estao de pe.

    A tela pergunta isto ANTES de desenhar os controles: um campo de vincular
    que so descobre no clique que a integracao nao existe faz a pessoa digitar
    o numero a toa.
    """
    return bool(settings.github_integracao_token and settings.github_integracao_repo)


def _exigir_configuracao() -> tuple[str, str]:
    if not integracao_configurada():
        raise GithubNaoConfiguradoError(
            "GITHUB_INTEGRACAO_TOKEN e GITHUB_INTEGRACAO_REPO precisam estar configurados no ambiente"
        )
    return settings.github_integracao_token, settings.github_integracao_repo


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": _VERSAO_DA_API,
    }


def _chamar(metodo: str, caminho: str, *, json: dict | None = None) -> Any:
    """Uma chamada a API, com a traducao de erro da casa.

    O 404 e o unico status que vira excecao PROPRIA: ele e uma resposta ("esse
    numero nao existe"), e a rota o transforma em 422 com frase de gente. O
    resto (401 de token vencido, 403 de permissao, 5xx, timeout) e ausencia de
    resposta, e a pessoa precisa saber que o app nao conseguiu conferir.
    """
    token, repo = _exigir_configuracao()
    url = f"{BASE_URL}/repos/{repo}{caminho}"
    try:
        resposta = httpx.request(metodo, url, headers=_headers(token), json=json, timeout=_TIMEOUT)
    except httpx.HTTPError as exc:
        logger.warning("[github] %s %s falhou: %s", metodo, caminho, exc)
        raise GithubIndisponivelError(f"Falha ao falar com o GitHub: {exc}") from exc

    if resposta.status_code == 404:
        raise IssueNaoEncontradaError(caminho)
    if resposta.status_code >= 400:
        logger.warning("[github] %s %s respondeu %s", metodo, caminho, resposta.status_code)
        raise GithubIndisponivelError(f"GitHub respondeu {resposta.status_code}")

    try:
        return resposta.json()
    except ValueError as exc:
        raise GithubIndisponivelError("GitHub respondeu um corpo que nao e JSON") from exc


def _no(dados: dict[str, Any]) -> dict[str, Any]:
    """Um no da foto: o que a Etapa precisa saber de uma issue.

    Sempre os mesmos campos, para a raiz e para cada parte, porque a regra da
    Etapa le os dois do mesmo jeito.

    Do `body` fica so o bloco "Para o diretor" (issue #676): e o unico pedaco do
    corpo que o app mostra, e guardar o resto poria numero de issue, nome de
    label e caminho de arquivo dentro do cache, a um `select` de distancia da
    tela do diretor. O corte e feito AQUI, na entrada, e nao na saida, porque a
    saida tem varias portas e a entrada tem uma so.
    """
    return {
        "numero": dados.get("number"),
        "titulo": dados.get("title"),
        "url": dados.get("html_url"),
        "estado": dados.get("state"),
        "motivo_do_fechamento": dados.get("state_reason"),
        "o_que_muda": bloco_para_o_diretor(dados.get("body")),
        "labels": sorted(
            str(label["name"]) for label in (dados.get("labels") or []) if isinstance(label, dict) and label.get("name")
        ),
    }


def e_pull_request(dados: dict[str, Any]) -> bool:
    """A API de issues tambem responde por PR, e o `pull_request` e o que os
    separa (o Vinculo e com a issue-raiz, ADR 0054, decisao 1)."""
    return bool(dados.get("pull_request"))


def ler_issue(numero: int) -> dict[str, Any]:
    """O JSON cru da issue. Cru de proposito: quem decide se e PR e a rota."""
    return _chamar("GET", f"/issues/{numero}")


def ler_sub_issues(numero: int) -> list[dict[str, Any]]:
    """As partes da issue-raiz.

    Repositorio sem sub-issues, ou issue sem nenhuma, responde lista vazia. Um
    404 aqui NAO e "a issue nao existe" (ela acabou de ser lida): e a API de
    sub-issues indisponivel para este repositorio, e o certo e seguir sem
    partes em vez de recusar o Vinculo inteiro.
    """
    try:
        dados = _chamar("GET", f"/issues/{numero}/sub_issues")
    except IssueNaoEncontradaError:
        return []
    return dados if isinstance(dados, list) else []


def atualizar_corpo(numero: int, corpo: str) -> None:
    """Reescreve o `body` da issue. O unico verbo de escrita deste modulo."""
    _chamar("PATCH", f"/issues/{numero}", json={"body": corpo})


def montar_foto(dados: dict[str, Any], partes: list[dict[str, Any]]) -> dict[str, Any]:
    """A foto que o servico puro le: a raiz, as partes e o resumo das partes.

    Recebe o que ja foi lido em vez de ler de novo: quem chama precisa do JSON
    cru antes disto (para separar issue de pull request e para pegar o corpo
    onde o marcador entra), e uma segunda leitura gastaria cota e ainda poderia
    voltar diferente da primeira.

    O `sub_issues_summary` da raiz e guardado quando veio, porque e a contagem
    que a propria tela do GitHub mostra; a lista de partes entra inteira porque
    a Etapa olha a label de CADA uma.
    """
    foto = _no(dados)
    foto["partes"] = [_no(parte) for parte in partes if isinstance(parte, dict)]

    resumo = dados.get("sub_issues_summary")
    if isinstance(resumo, dict) and isinstance(resumo.get("total"), int):
        foto["resumo_das_partes"] = {
            "total": resumo.get("total"),
            "entregues": resumo.get("completed"),
        }
    return foto
