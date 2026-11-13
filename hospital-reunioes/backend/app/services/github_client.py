"""O unico ponto do app que fala com a API do GitHub (issue #674, ADR 0054).

Modulo profundo, porta estreita: quem chama pede "a foto da issue #673" ou
"crie a issue desta Demanda", e recebe dado pronto ou uma
excecao. Base, header, timeout e traducao de erro moram aqui; nenhum outro
modulo importa `httpx` para falar com o GitHub.

Tres invariantes que o resto do app herda:

- **So os repositorios dos Projetos** (issue #1713, ADR 0093, decisao 2). O
  do Hospital vem de `GITHUB_INTEGRACAO_REPO` e o da Ana de
  `GITHUB_INTEGRACAO_REPO_ANA`. Toda chamada que mexe numa issue ou num PR
  recebe o Projeto, e o repositorio entra no caminho da URL uma vez so, aqui.
  A leitura do codigo, o `history.json` e a lista das issues fechadas sao do
  Hospital, o unico Projeto com o app e a subida.
- **Leitura do codigo so com GET** (issue #1385, ADR 0077, decisao 5): o
  agente da aba le arquivo, pasta, busca e issues abertas por
  `ler_do_repositorio`, `buscar_no_codigo` e `listar_issues_abertas`, e
  nenhuma delas escreve.
- **Escrita minima.** So o "Criar o card" do chat escreve (ADR 0077, decisao
  6): o POST que abre a issue e o PATCH que a designa. Desde a ADR 0084
  (decisao 2) o "Apagar" tambem: o comentario de motivo e o PATCH que fecha a
  issue como nao planejada. E o "Atualizar o card" da revisao (decisao 3,
  issue #1558): o comentario do que mudou e o PATCH que regrava o corpo e as
  labels. E a passada unica do bloco "Para o desenvolvedor" (issue #1636),
  rodada a mao, que regrava so o corpo. Issue nunca se apaga. Nenhum verbo de LEITURA de
  comentario: nada do GitHub volta para o app alem da foto da issue (ADR 0054,
  decisao 5). O token fine-grained do Pedro tem Issues: write neste
  repositorio e mais nada (ADR 0054, decisao 8).
- **Falha e falha.** Timeout, 5xx e erro de rede viram `GithubIndisponivelError`;
  404 vira `IssueNaoEncontradaError`. Sem token ou sem repositorio configurado e
  `GithubNaoConfiguradoError`, que a rota traduz em 503: o app nao FINGE que leu.

A foto que sai daqui e o dicionario que o servico puro (`tecnologia_vinculo`)
sabe ler, e nao o JSON cru do GitHub: a Etapa nao pode depender do nome de um
campo de terceiro espalhado por tres arquivos.
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
import re
from typing import Any
from urllib.parse import quote, urlencode, urlsplit

import httpx

from app.config import settings
from app.services.tecnologia_vinculo import FECHAMENTO_NAO_PLANEJADA, bloco_para_o_diretor

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
    """Falta `GITHUB_INTEGRACAO_TOKEN` ou o repositorio do Projeto."""


class GithubIndisponivelError(RuntimeError):
    """O GitHub nao respondeu (timeout, 5xx, rede, corpo ilegivel)."""


class IssueNaoEncontradaError(RuntimeError):
    """O numero pedido nao existe no repositorio da integracao."""


# O Projeto da Demanda (issue #1713, ADR 0093, decisoes 1 e 2): o Aplicativo
# do Hospital ou a Ana. E a mesma lista do CHECK da migration 145.
PROJETO_HOSPITAL = "hospital"
PROJETO_ANA = "ana"
PROJETOS: tuple[str, ...] = (PROJETO_HOSPITAL, PROJETO_ANA)


def repositorio_do_projeto(projeto: str) -> str:
    """O `dono/repositorio` do Projeto, ou "" quando a variavel dele esta vazia
    (a Ana desligada). Projeto fora da lista tambem e "": nunca cai no Hospital
    por engano."""
    if projeto == PROJETO_HOSPITAL:
        return settings.github_integracao_repo or ""
    if projeto == PROJETO_ANA:
        return settings.github_integracao_repo_ana or ""
    return ""


def projeto_do_repositorio(nome: object) -> str | None:
    """O Projeto cujo repositorio configurado e este nome, ou `None`.

    E a traducao do webhook: o `repository.full_name` da entrega vira o Projeto
    da Demanda. Sem diferenca de maiuscula, como o GitHub. Repositorio vazio
    nao casa com nada, e e assim que a Ana desligada descarta a entrega dela.
    """
    alvo = str(nome or "").strip().lower()
    if not alvo:
        return None
    for projeto in PROJETOS:
        repositorio = repositorio_do_projeto(projeto)
        if repositorio and repositorio.lower() == alvo:
            return projeto
    return None


def integracao_configurada(projeto: str = PROJETO_HOSPITAL) -> bool:
    """Se o token e o repositorio do Projeto estao de pe.

    A tela pergunta isto ANTES de desenhar os controles: um campo de vincular
    que so descobre no clique que a integracao nao existe faz a pessoa digitar
    o numero a toa.
    """
    return bool(settings.github_integracao_token and repositorio_do_projeto(projeto))


def _exigir_configuracao(projeto: str) -> tuple[str, str]:
    if not integracao_configurada(projeto):
        raise GithubNaoConfiguradoError(
            f"GITHUB_INTEGRACAO_TOKEN e o repositorio do Projeto {projeto!r} precisam estar configurados no ambiente"
        )
    return settings.github_integracao_token, repositorio_do_projeto(projeto)


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": _VERSAO_DA_API,
    }


def _chamar(metodo: str, caminho: str, *, projeto: str, json: dict | None = None, no_repositorio: bool = True) -> Any:
    """Uma chamada a API, com a traducao de erro da casa.

    O 404 e o unico status que vira excecao PROPRIA: ele e uma resposta ("esse
    numero nao existe"), e a rota o transforma em 422 com frase de gente. O
    resto (401 de token vencido, 403 de permissao, 5xx, timeout) e ausencia de
    resposta, e a pessoa precisa saber que o app nao conseguiu conferir.
    """
    token, repo = _exigir_configuracao(projeto)
    # A busca de codigo e a unica rota fora de `/repos/{repo}`: ela recebe o
    # repositorio dentro da consulta (`buscar_no_codigo`).
    url = f"{BASE_URL}/repos/{repo}{caminho}" if no_repositorio else f"{BASE_URL}{caminho}"
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
    no = {
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
    # A data do fechamento, que o Documento do card mostra na parte e em Datas
    # (issue #1552, ADR 0084). So entra com a issue fechada: a foto da issue
    # aberta continua identica a de antes, e a reconciliacao nao a regrava.
    if dados.get("closed_at"):
        no["fechada_em"] = dados["closed_at"]
    return no


# As palavras com que um PR diz que fecha uma issue, as mesmas que o GitHub
# reconhece (issue #1064): `Closes #673`, `fixes: #673`, `Resolved
# dono/repo#673`. A palavra vale para UMA referencia: em "Closes #1, #2" o
# GitHub fecha so a #1, e a regra daqui diz o mesmo.
_FECHAMENTO = re.compile(
    r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\b:?\s+([\w.-]+/[\w.-]+)?#(\d+)\b",
    re.IGNORECASE,
)


def issues_que_o_corpo_fecha(corpo: str | None, *, projeto: str) -> list[int]:
    """As issues do repositorio do Projeto que o corpo de um PR fecha, em ordem.

    E a mesma leitura para os dois gatilhos (o webhook `pull_request` e a
    reconciliacao), e por isso mora aqui: lida de dois jeitos, a issue que o
    webhook chama de "fechada pelo PR" poderia ser outra na passagem de hora em
    hora, e o fato iria e voltaria a cada hora.

    Referencia a outro repositorio (`outra-pessoa/repo#673`) nao conta: o
    numero e de la, e a issue #673 daqui nao tem nada com isso.
    """
    repo = repositorio_do_projeto(projeto).lower()
    numeros: list[int] = []
    for outro_repo, numero in _FECHAMENTO.findall(corpo or ""):
        if outro_repo and outro_repo.lower() != repo:
            continue
        if int(numero) not in numeros:
            numeros.append(int(numero))
    return numeros


def ler_prs_abertos(*, projeto: str) -> list[dict[str, Any]]:
    """Os PRs abertos do repositorio, cada um com as issues que ele fecha.

    Uma leitura so para o lote inteiro da reconciliacao (issue #1064), e nao
    uma por Demanda: a lista de PRs abertos e curta e a cota do GitHub e
    compartilhada. A primeira pagina (100) basta para o volume deste
    repositorio; um PR alem dela so perde o fato "PR aberto" no lote, e o
    webhook continua cobrindo.
    """
    dados = _chamar("GET", "/pulls?state=open&per_page=100", projeto=projeto)
    if not isinstance(dados, list):
        raise GithubIndisponivelError("GitHub respondeu a lista de PRs fora do formato")
    return [
        {"numero": pr.get("number"), "fecha": issues_que_o_corpo_fecha(pr.get("body"), projeto=projeto)}
        for pr in dados
        if isinstance(pr, dict) and isinstance(pr.get("number"), int)
    ]


# A pasta do app. O PR que nao toca nela e lote de ferramenta para a subida
# (`classe_do_lote` no `fechar_onda.py`): so merge, sem build, sem registro no
# `history.json` e sem webhook de deploy.
PASTA_DO_APP = "hospital-reunioes/"

# A API lista ate 3000 arquivos de um PR, 100 por pagina.
_PAGINAS_DE_ARQUIVOS = 30


def pr_toca_o_app(numero: int, *, projeto: str) -> bool:
    """Se o PR mexe em algum arquivo do app, e por isso leva uma subida
    (revisao do PR #1100, ADR 0069, decisao 5).

    Para na primeira pagina que acha um arquivo do app, ou na primeira que vem
    incompleta (a ultima). Falha de leitura sobe como `GithubIndisponivelError`:
    quem chama decide o que "nao sei" quer dizer.
    """
    for pagina in range(1, _PAGINAS_DE_ARQUIVOS + 1):
        dados = _chamar("GET", f"/pulls/{numero}/files?per_page=100&page={pagina}", projeto=projeto)
        if not isinstance(dados, list):
            raise GithubIndisponivelError("GitHub respondeu os arquivos do PR fora do formato")
        if any(isinstance(a, dict) and str(a.get("filename") or "").startswith(PASTA_DO_APP) for a in dados):
            return True
        if len(dados) < 100:
            return False
    return False


# O registro de todas as subidas, como a Action pos-merge o grava na `main`
# (ADR 0064, decisao 6b). E o arquivo, e nao o evento: so a reconciliacao le
# daqui (ADR 0069, decisao 4).
CAMINHO_DO_HISTORICO = "docs/spec/deploy/history.json"


def ler_historico_de_deploys() -> list[dict[str, Any]]:
    """As subidas registradas no `history.json` da `main`, a mais nova primeiro.

    Pela API de conteudo, que devolve o arquivo em base64 ate 1 MB (o arquivo
    tem dezenas de KB). O repositorio e publico, e o token so le. Qualquer
    coisa fora do formato vira indisponibilidade: quem chama nao marca nada e
    tenta de novo na hora seguinte, em vez de ler "nenhuma subida" de um
    arquivo que nao conseguiu ler.
    """
    try:
        dados = _chamar("GET", f"/contents/{CAMINHO_DO_HISTORICO}?ref=main", projeto=PROJETO_HOSPITAL)
    except IssueNaoEncontradaError as exc:
        raise GithubIndisponivelError("O history.json nao esta na main") from exc
    if not isinstance(dados, dict) or dados.get("encoding") != "base64" or not isinstance(dados.get("content"), str):
        raise GithubIndisponivelError("GitHub respondeu o history.json fora do formato")
    try:
        historico = json.loads(base64.b64decode(dados["content"]))
    except (ValueError, binascii.Error) as exc:
        raise GithubIndisponivelError("O history.json da main nao e JSON") from exc
    deploys = historico.get("deploys") if isinstance(historico, dict) else None
    if not isinstance(deploys, list):
        raise GithubIndisponivelError("O history.json da main nao tem a lista de deploys")
    return deploys


# ─── A leitura do codigo pelo agente da aba (issue #1385, ADR 0077, decisao 5) ─


def _caminho_do_repositorio(caminho: str) -> str:
    """O caminho relativo a raiz, sem barra nas pontas e sem `..`: o caminho
    entra na URL, e quem o escreve e o modelo."""
    limpo = (caminho or "").strip().strip("/")
    if any(parte in ("", ".", "..") for parte in limpo.split("/")) and limpo:
        raise IssueNaoEncontradaError(caminho)
    return limpo


def ler_do_repositorio(caminho: str) -> str | list[str]:
    """O texto de um arquivo da `main`, ou os nomes de uma pasta.

    Pela API de conteudo, so GET. Arquivo que nao e texto (imagem, binario)
    volta como indisponivel: o agente segue sem ele.
    """
    dados = _chamar("GET", f"/contents/{quote(_caminho_do_repositorio(caminho))}?ref=main", projeto=PROJETO_HOSPITAL)
    if isinstance(dados, list):
        return [str(item.get("name")) for item in dados if isinstance(item, dict) and item.get("name")]
    if not isinstance(dados, dict) or dados.get("encoding") != "base64" or not isinstance(dados.get("content"), str):
        raise GithubIndisponivelError("GitHub respondeu o arquivo fora do formato")
    try:
        return base64.b64decode(dados["content"]).decode("utf-8")
    except (ValueError, binascii.Error) as exc:
        raise GithubIndisponivelError("O arquivo nao e texto") from exc


# A primeira pagina da busca basta para o agente escolher o que abrir.
_RESULTADOS_DA_BUSCA = 20


def buscar_no_codigo(termo: str) -> list[str]:
    """Os caminhos dos arquivos da `main` onde o termo aparece, pela busca de
    codigo do GitHub restrita a este repositorio."""
    _, repo = _exigir_configuracao(PROJETO_HOSPITAL)
    consulta = urlencode({"q": f"{termo} repo:{repo}", "per_page": _RESULTADOS_DA_BUSCA})
    dados = _chamar("GET", f"/search/code?{consulta}", projeto=PROJETO_HOSPITAL, no_repositorio=False)
    itens = dados.get("items") if isinstance(dados, dict) else None
    if not isinstance(itens, list):
        raise GithubIndisponivelError("GitHub respondeu a busca fora do formato")
    return [str(item["path"]) for item in itens if isinstance(item, dict) and item.get("path")]


def listar_issues_abertas() -> list[dict[str, Any]]:
    """As issues abertas (sem os PRs), numero e titulo, a primeira pagina."""
    dados = _chamar("GET", "/issues?state=open&per_page=100", projeto=PROJETO_HOSPITAL)
    if not isinstance(dados, list):
        raise GithubIndisponivelError("GitHub respondeu a lista de issues fora do formato")
    return [
        {"numero": issue.get("number"), "titulo": str(issue.get("title") or "")}
        for issue in dados
        if isinstance(issue, dict) and isinstance(issue.get("number"), int) and not e_pull_request(issue)
    ]


_POR_PAGINA = 100


def listar_issues_fechadas() -> list[dict[str, Any]]:
    """Todas as issues fechadas (sem os PRs), cruas, pagina a pagina ate vir uma
    pagina curta. So a carga do historico de entregas le isto (issue #1555): e
    leitura de uma vez, e a cota de uma hora cobre as poucas dezenas de paginas."""
    issues: list[dict[str, Any]] = []
    pagina = 1
    while True:
        dados = _chamar("GET", f"/issues?state=closed&per_page={_POR_PAGINA}&page={pagina}", projeto=PROJETO_HOSPITAL)
        if not isinstance(dados, list):
            raise GithubIndisponivelError("GitHub respondeu a lista de issues fora do formato")
        issues.extend(
            i for i in dados if isinstance(i, dict) and isinstance(i.get("number"), int) and not e_pull_request(i)
        )
        if len(dados) < _POR_PAGINA:
            return issues
        pagina += 1


def e_pull_request(dados: dict[str, Any]) -> bool:
    """A API de issues tambem responde por PR, e o `pull_request` e o que os
    separa (o Vinculo e com a issue-raiz, ADR 0054, decisao 1)."""
    return bool(dados.get("pull_request"))


def ler_issue(numero: int, *, projeto: str) -> dict[str, Any]:
    """O JSON cru da issue. Cru de proposito: quem decide se e PR e a rota."""
    return _chamar("GET", f"/issues/{numero}", projeto=projeto)


def ler_comentarios(numero: int, *, projeto: str) -> list[dict[str, Any]]:
    """Os comentarios da issue, do mais antigo ao mais novo, a primeira pagina
    (issue #1557): quem escreveu, o texto e quando. E o que a Revisao com o
    codigo de hoje le do que se combinou por fora do app."""
    dados = _chamar("GET", f"/issues/{numero}/comments?per_page={_POR_PAGINA}", projeto=projeto)
    if not isinstance(dados, list):
        raise GithubIndisponivelError("GitHub respondeu os comentarios fora do formato")
    return [
        {
            "autor": str((c.get("user") or {}).get("login") or ""),
            "corpo": str(c.get("body") or ""),
            "criado_em": c.get("created_at"),
        }
        for c in dados
        if isinstance(c, dict)
    ]


def ler_sub_issues(numero: int, *, projeto: str) -> list[dict[str, Any]]:
    """As partes da issue-raiz.

    Repositorio sem sub-issues, ou issue sem nenhuma, responde lista vazia. Um
    404 aqui NAO e "a issue nao existe" (ela acabou de ser lida): e a API de
    sub-issues indisponivel para este repositorio, e o certo e seguir sem
    partes em vez de recusar o Vinculo inteiro.
    """
    try:
        dados = _chamar("GET", f"/issues/{numero}/sub_issues", projeto=projeto)
    except IssueNaoEncontradaError:
        return []
    return dados if isinstance(dados, list) else []


def criar_issue(
    *, projeto: str, titulo: str, corpo: str, labels: list[str], assignees: list[str] | None = None
) -> dict[str, Any]:
    """Abre uma issue nova no repositorio da integracao (issue #677).

    `assignees` e o login do responsavel da Demanda, quando ele tem um: a
    issue vai para a coluna da pessoa certa do Hospital OS. Ele NAO vai no
    POST: login que nao e assignable neste repositorio (sem acesso, digitado
    errado) faz o GitHub recusar a criacao inteira com 422, e um campo de
    conveniencia derrubaria o botao. A issue nasce sem ninguem e a designacao
    vem depois, num PATCH cuja falha so loga (PR #1050).

    Devolve o JSON da issue criada, INTEIRO: e dele que a foto e a Etapa saem
    logo em seguida, sem uma segunda leitura que gastaria cota e ainda poderia
    voltar diferente do que acabou de ser escrito.

    Um 404 aqui nao e "issue nao encontrada" (nao ha issue nenhuma ainda): e o
    repositorio que sumiu ou o token que perdeu acesso a ele. Vira
    indisponibilidade, que e a leitura honesta para quem clicou e para a rota,
    que devolve 502 em vez de uma frase sobre um numero que ninguem digitou.
    """
    try:
        dados = _chamar("POST", "/issues", projeto=projeto, json={"title": titulo, "body": corpo, "labels": labels})
    except IssueNaoEncontradaError as exc:
        raise GithubIndisponivelError("O repositorio da integracao nao aceitou a criacao da issue") from exc

    numero = dados.get("number") if isinstance(dados, dict) else None
    if assignees and isinstance(numero, int):
        try:
            designada = designar(numero, assignees, projeto=projeto)
            # Os donos saem da resposta do PATCH: e por eles que quem chama
            # sabe se a designacao pegou (`designado`, issue #1536).
            dados = {**dados, "assignees": designada.get("assignees") or []}
        except GithubIndisponivelError as exc:
            logger.warning("[github] a issue #%s nasceu sem assignee (%s): %s", numero, assignees, exc)
    return dados


def designado(dados: dict[str, Any], logins: list[str]) -> bool:
    """Se a issue tem todos os `logins` entre os donos. O login do GitHub nao
    diferencia maiuscula, e a resposta volta com a grafia da conta."""
    donos = {
        str(dono.get("login") or "").casefold() for dono in (dados.get("assignees") or []) if isinstance(dono, dict)
    }
    return {login.casefold() for login in logins} <= donos


def designar(numero: int, logins: list[str], *, projeto: str) -> dict[str, Any]:
    """Pede ao GitHub so a designacao da issue (issue #1536, ADR 0083, decisao 7).

    Devolve a issue como o GitHub a devolve. Levanta `GithubIndisponivelError`
    quando ele nao designou: o 422 de login que nao e assignable, a falta de
    resposta, e o 200 que volta sem o login pedido entre os donos.
    """
    try:
        dados = _chamar("PATCH", f"/issues/{numero}", projeto=projeto, json={"assignees": logins})
    except IssueNaoEncontradaError as exc:
        raise GithubIndisponivelError(f"A issue #{numero} nao foi encontrada para designar") from exc
    if not isinstance(dados, dict) or not designado(dados, logins):
        raise GithubIndisponivelError(f"O GitHub nao designou {', '.join(logins)} na issue #{numero}")
    return dados


def fechar_como_nao_planejada(numero: int, *, projeto: str, comentario: str) -> None:
    """Comenta o motivo e fecha a issue como nao planejada (issue #1549, ADR 0084,
    decisao 2).

    O comentario vai antes, para o motivo aparecer na issue antes do fechamento.
    Um 404 aqui nao e resposta (a issue estava vinculada): vira
    indisponibilidade, e quem chama nao apaga nada no app.
    """
    try:
        _chamar("POST", f"/issues/{numero}/comments", projeto=projeto, json={"body": comentario})
        _chamar(
            "PATCH",
            f"/issues/{numero}",
            projeto=projeto,
            json={"state": "closed", "state_reason": FECHAMENTO_NAO_PLANEJADA},
        )
    except IssueNaoEncontradaError as exc:
        raise GithubIndisponivelError(f"A issue #{numero} nao foi encontrada para fechar") from exc


def comentar(numero: int, corpo: str, *, projeto: str) -> None:
    """Deixa um comentario na issue (issue #1558, ADR 0084, decisao 3): o que
    o "Atualizar o card" mudou. Um 404 aqui nao e resposta (a issue estava
    vinculada): vira indisponibilidade."""
    try:
        _chamar("POST", f"/issues/{numero}/comments", projeto=projeto, json={"body": corpo})
    except IssueNaoEncontradaError as exc:
        raise GithubIndisponivelError(f"A issue #{numero} nao foi encontrada para comentar") from exc


def regravar(numero: int, *, projeto: str, corpo: str, labels: list[str]) -> dict[str, Any]:
    """Regrava o corpo e as labels da issue num PATCH so (issue #1558, ADR
    0084, decisao 3): o PRD revisado e a volta para a triagem saem juntos, ou
    nenhum dos dois. Devolve a issue como o GitHub a devolve."""
    try:
        dados = _chamar("PATCH", f"/issues/{numero}", projeto=projeto, json={"body": corpo, "labels": labels})
    except IssueNaoEncontradaError as exc:
        raise GithubIndisponivelError(f"A issue #{numero} nao foi encontrada para regravar") from exc
    if not isinstance(dados, dict):
        raise GithubIndisponivelError(f"GitHub respondeu a issue #{numero} fora do formato")
    return dados


def regravar_corpo(numero: int, *, projeto: str, corpo: str) -> dict[str, Any]:
    """Regrava so o corpo da issue, sem tocar nas labels (issue #1636): a
    passada unica que poe o bloco "Para o desenvolvedor" nas Demandas abertas.
    Devolve a issue como o GitHub a devolve."""
    try:
        dados = _chamar("PATCH", f"/issues/{numero}", projeto=projeto, json={"body": corpo})
    except IssueNaoEncontradaError as exc:
        raise GithubIndisponivelError(f"A issue #{numero} nao foi encontrada para regravar") from exc
    if not isinstance(dados, dict):
        raise GithubIndisponivelError(f"GitHub respondeu a issue #{numero} fora do formato")
    return dados


# A chave do dono da raiz na foto (issue #1534).
FATO_ASSIGNEE = "assignee"


def _primeiro_assignee(dados: dict[str, Any]) -> str | None:
    """O login do primeiro dono da issue, na ordem do GitHub, ou `None`.

    Um Responsavel so (ADR 0083): com dois donos no GitHub, vale o primeiro.
    """
    candidatos = [*(dados.get("assignees") or []), dados.get("assignee")]
    for pessoa in candidatos:
        if isinstance(pessoa, dict) and isinstance(pessoa.get("login"), str) and pessoa["login"].strip():
            return pessoa["login"].strip()
    return None


# A chave do link da Demonstracao na foto (issue #1559).
FATO_DEMONSTRACAO = "demonstracao"

# O marcador da Demonstracao no corpo da issue-raiz (issue #1559):
# `<!-- demonstracao: https://... -->`. O link e um token so, sem espaco.
_MARCADOR_DA_DEMONSTRACAO = re.compile(r"<!--\s*demonstracao:\s*(\S+)\s*-->", re.IGNORECASE)

# O que nunca entra num link que a tela poe num `href`: aspas e sinais de tag.
_FORA_DO_LINK = re.compile(r"[\"'<>\\]")


def demonstracao_do_corpo(corpo: str | None) -> str | None:
    """O link da Demonstracao que o corpo da issue carrega, ou `None`.

    So `https` com endereco entra (issue #1559): o link vai para a tela do
    diretor, e `http`, `javascript:` ou um `https://` sem host nao sao link de
    video. Marcador malformado vale o mesmo que marcador nenhum.

    Vale o ultimo marcador do corpo, o que o `/divulgar` grava no fim: o texto
    da issue pode citar o marcador antes (a spec do PRD #1548 cita). O host
    precisa de um ponto e nenhum pedaco vazio, para `https://...` nao passar.
    """
    achados = _MARCADOR_DA_DEMONSTRACAO.findall(corpo or "")
    if not achados:
        return None
    url = achados[-1]
    if _FORA_DO_LINK.search(url):
        return None
    partes = urlsplit(url)
    host = partes.hostname or ""
    if partes.scheme != "https" or "." not in host or not all(host.split(".")):
        return None
    return url


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

    # O dono da raiz no GitHub, de que o Responsavel da Demanda e derivado
    # (issue #1534, ADR 0083, decisao 6). So entra quando ha dono: a foto da
    # issue sem assignee continua identica a de antes desta fatia.
    assignee = _primeiro_assignee(dados)
    if assignee is not None:
        foto[FATO_ASSIGNEE] = assignee

    # O link da Demonstracao, so da raiz (issue #1559). So entra quando o
    # marcador e valido: a foto da issue sem ele continua identica.
    demonstracao = demonstracao_do_corpo(dados.get("body"))
    if demonstracao is not None:
        foto[FATO_DEMONSTRACAO] = demonstracao

    resumo = dados.get("sub_issues_summary")
    if isinstance(resumo, dict) and isinstance(resumo.get("total"), int):
        foto["resumo_das_partes"] = {
            "total": resumo.get("total"),
            "entregues": resumo.get("completed"),
        }
    return foto
