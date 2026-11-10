"""O webhook do GitHub e a reconciliacao de hora em hora (issue #678, PRD #673).

Tres seams, e cada um existe porque o anterior nao alcanca o proximo:

* **A porta**, pela ROTA de verdade com `TestClient`. A assinatura HMAC so e
  provavel aqui: chamar a funcao de conferencia direto deixaria de fora a
  pergunta que importa, que e se a ROTA a chama antes de mexer no banco. Todo
  teste de recusa desta secao termina olhando o banco: 401 que grava e 401 que
  nao serve para nada.
* **A sincronizacao**, tambem pela rota, com o cliente do GitHub dublado. E ela
  que deriva a Etapa, e a guarda da foto igual e criterio de aceite: a entrega
  repetida do GitHub nao reescreve nada. Desde a issue #1386 (ADR 0077) ela nao
  escreve na Conversa da Demanda, aposentada.
* **A reconciliacao**, pela funcao do job com o Supabase dublado, mais o
  registro dela no scheduler. O intervalo de uma hora nao se testa esperando uma
  hora: o que se testa e que o job registrado APONTA para a rotina, e que a
  rotina faz o lote inteiro mesmo com uma Demanda quebrada no meio.

O cliente do GitHub NUNCA e chamado de verdade: a fixture `_sem_github_de_verdade`
troca o transporte por um que estoura, e a trava de rede do `conftest.py`
continua por baixo.

O segredo usado aqui e um valor FALSO deste arquivo. O de producao mora no
Coolify e nao entra em teste, log, commit nem corpo de PR.
"""

from __future__ import annotations

import hashlib
import hmac
import itertools
import json
import logging
import os
import sys
from dataclasses import dataclass
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from slowapi import _rate_limit_exceeded_handler  # noqa: E402
from slowapi.errors import RateLimitExceeded  # noqa: E402

from app.config import settings  # noqa: E402
from app.cron import scheduler as scheduler_mod  # noqa: E402
from app.dependencies import get_supabase_client  # noqa: E402
from app.limiter import limiter  # noqa: E402
from app.routers import webhooks as webhooks_router  # noqa: E402
from app.services import github_client, tecnologia_sincronizacao  # noqa: E402
from app.services.tecnologia import ESTADOS_FECHADOS  # noqa: E402
from app.services.tecnologia_vinculo import (  # noqa: E402
    ETAPA_EM_ANALISE,
    ETAPA_EM_DESENVOLVIMENTO,
    ETAPA_ENTREGUE,
    ETAPA_PLANEJADA,
)

ROTA = "/api/webhooks/github"

# Valor de mentira, deste arquivo. O segredo de verdade e do Coolify.
SEGREDO = "segredo-falso-de-teste-678"

REPO = "pedrorezendefig/hospital-reunioes"


# ─── Fixtures de seguranca ───────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _sem_github_de_verdade(monkeypatch):
    """Nenhum teste deste arquivo fala com api.github.com.

    A troca e no TRANSPORTE (`httpx.request` dentro do modulo do cliente), e nao
    nas funcoes do cliente: assim ela vale mesmo nos testes que NAO dublam
    `ler_issue`, e um caminho novo que chamasse o GitHub sem duble estoura aqui,
    com o nome do arquivo, em vez de sair para a rede.
    """

    def _proibido(*a, **kw):
        raise AssertionError("O cliente do GitHub foi chamado de verdade neste teste. Duble-o.")

    monkeypatch.setattr(github_client.httpx, "request", _proibido)


# A funcao de verdade, guardada antes de o duble abaixo trocar o nome no modulo:
# e por ela que o teste do cliente passa pelo transporte dublado.
_LER_PRS_ABERTOS_DE_VERDADE = github_client.ler_prs_abertos


@pytest.fixture(autouse=True)
def _sem_pr_aberto(monkeypatch):
    """O lote da reconciliacao le os PRs abertos uma vez (issue #1064). Por
    padrao nao ha nenhum: quem quer PR aberto, ou a leitura falhando, troca este
    duble no proprio teste."""
    monkeypatch.setattr(github_client, "ler_prs_abertos", lambda: [])


@pytest.fixture(autouse=True)
def _pr_do_app(monkeypatch):
    """O PR mergeado toca no app e leva uma subida (revisao do PR #1100). Quem
    quer o PR de ferramenta, ou a leitura falhando, troca este duble no proprio
    teste."""
    monkeypatch.setattr(github_client, "pr_toca_o_app", lambda numero: True)


@pytest.fixture(autouse=True)
def _segredo_configurado(monkeypatch):
    """O segredo e o repositorio de pe, como estarao no Coolify.

    O `.env` local nao os tem, e sem isto TODA entrega responderia 503 (ou
    passaria pela guarda do repositorio sem nada com o que comparar) e os testes
    de 401 ficariam verdes pelo motivo errado. Quem prova o 503 e o teste que
    APAGA a variavel, e nao a ausencia dela por acidente.
    """
    monkeypatch.setattr(settings, "github_webhook_secret", SEGREDO)
    monkeypatch.setattr(settings, "github_integracao_repo", REPO)


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """O slowapi guarda a contagem num storage de PROCESSO: sem o reset, o 429
    de um arquivo anterior quebraria um teste daqui que nada tem com o teto, e o
    teste do teto veria o balde de outra pessoa."""
    limiter._storage.reset()
    yield
    limiter._storage.reset()


# ─── Supabase duble ──────────────────────────────────────────────────────────

# O `now()` do gatilho de `atualizado_em`: um valor novo a cada escrita.
_RELOGIO_DO_GATILHO = itertools.count(1)


@dataclass
class _Result:
    data: list
    count: int = 0


class _Nao:
    """O `.not_` do PostgREST, que so precisa responder por `is`."""

    def __init__(self, query: _TableQuery):
        self._query = query

    def is_(self, coluna, valor):
        self._query._nao_e[coluna] = valor
        return self._query


class _TableQuery:
    """PostgREST minimo: select/eq/in_/not_.is_/insert/update."""

    def __init__(
        self,
        rows: list[dict],
        nome: str,
        falhas: dict[str, Exception] | None = None,
        antes_do_update=None,
        falhar_ao_ler: str | None = None,
    ):
        self._rows = rows
        self._nome = nome
        self._falhas = falhas or {}
        self._antes_do_update = antes_do_update
        self._falhar_ao_ler = falhar_ao_ler
        self._eq: dict[str, Any] = {}
        self._in: dict[str, list] = {}
        self._nao_e: dict[str, str] = {}
        self._insert: list[dict] | None = None
        self._update: dict | None = None

    @property
    def not_(self):
        return _Nao(self)

    def select(self, *_a, **_kw):
        return self

    def eq(self, coluna, valor):
        self._eq[coluna] = valor
        return self

    def in_(self, coluna, valores):
        self._in[coluna] = list(valores)
        return self

    def insert(self, payload):
        linhas = payload if isinstance(payload, list) else [payload]
        self._insert = [dict(linha) for linha in linhas]
        return self

    def update(self, payload: dict):
        self._update = dict(payload)
        return self

    def _casa(self, linha: dict) -> bool:
        if not all(linha.get(c) == v for c, v in self._eq.items()):
            return False
        if not all(linha.get(c) in v for c, v in self._in.items()):
            return False
        return all(linha.get(c) is not None for c in self._nao_e)

    def execute(self):
        if self._insert is not None:
            for i, linha in enumerate(self._insert):
                linha.setdefault("id", f"{self._nome}-{len(self._rows) + i + 1}")
                linha.setdefault("criado_em", f"2026-09-10T12:00:{len(self._rows) + i:02d}Z")
            self._rows.extend(self._insert)
            return _Result(data=[dict(linha) for linha in self._insert])

        if self._update is None and self._falhar_ao_ler == self._nome:
            # O timeout do PostgREST numa LEITURA. Sobe cru (`httpx.HTTPError`
            # nao e `APIError`), que e a forma pela qual ele morde de verdade.
            raise httpx.ReadTimeout(f"timeout lendo {self._nome}")

        if self._update is not None and self._antes_do_update is not None:
            # O gancho da CORRIDA: ele mexe nas linhas ANTES de a consulta
            # peneirar, que e a unica forma de encenar "alguem escreveu entre a
            # leitura e o UPDATE" contra um compare-and-swap de verdade.
            self._antes_do_update(self._nome, self._update, self._rows)

        casadas = [linha for linha in self._rows if self._casa(linha)]

        if self._update is not None:
            for linha in casadas:
                # A falha injetada e por DEMANDA, e no UPDATE: e o ponto em que
                # o lote da reconciliacao pode morrer no meio.
                erro = self._falhas.get(str(linha.get("id")))
                if erro is not None:
                    raise erro
                linha.update(self._update)
                if self._nome == "tecnologia_demandas":
                    # O gatilho `trg_tecnologia_demandas_atualizado_em` da
                    # migration 102: toda escrita na Demanda troca o carimbo, e
                    # e nele que a sincronizacao trava a escrita (issue #1064).
                    linha["atualizado_em"] = f"2026-09-10T12:00:00.{next(_RELOGIO_DO_GATILHO):06d}+00:00"
            return _Result(data=[dict(linha) for linha in casadas])

        return _Result(data=[dict(linha) for linha in casadas])


class _SupabaseMock:
    def __init__(
        self,
        tabelas: dict[str, list[dict]],
        falhas: dict[str, Exception] | None = None,
        antes_do_update=None,
        falhar_ao_ler: str | None = None,
    ):
        self.tabelas = tabelas
        self.falhas = falhas or {}
        self.antes_do_update = antes_do_update
        self.falhar_ao_ler = falhar_ao_ler

    def table(self, nome: str):
        return _TableQuery(
            self.tabelas.setdefault(nome, []),
            nome,
            self.falhas,
            self.antes_do_update,
            self.falhar_ao_ler,
        )


# ─── Cenario ─────────────────────────────────────────────────────────────────


def _issue(numero: int, *, estado: str = "open", motivo=None, labels=(), resumo=None) -> dict:
    dados = {
        "number": numero,
        "title": "Tecnologia: webhook do GitHub",
        "html_url": f"https://github.com/pedrorezendefig/hospital-reunioes/issues/{numero}",
        "state": estado,
        "state_reason": motivo,
        "labels": [{"name": nome} for nome in labels],
        "body": "## Para o diretor\n\nO selo se atualiza sozinho.",
    }
    if resumo is not None:
        dados["sub_issues_summary"] = resumo
    return dados


def _demanda(did: str, **campos) -> dict:
    base = {
        "id": did,
        "titulo": "Levar o selo de Etapa ao card",
        "descricao": None,
        "tipo": "novo",
        "produto_id": "prod-1",
        "estado": "em_andamento",
        "responsavel_id": "P1",
        "autor_id": "P1",
        "prioridade": "normal",
        "prazo": None,
        "criado_em": "2026-09-01T09:00:00Z",
        "atualizado_em": "2026-09-01T09:00:00Z",
        "concluida_em": None,
        "concluida_por": None,
        "cancelada_em": None,
        "cancelada_por": None,
        "github_issue_numero": None,
        "etapa": ETAPA_EM_ANALISE,
        "partes_entregues": None,
        "partes_total": None,
        "o_que_muda": None,
        "partes": None,
        "github_foto": None,
        "github_sincronizado_em": None,
        "vinculado_por": None,
    }
    base.update(campos)
    return base


class _GithubFalso:
    """O GitHub como o teste o quer: uma issue por numero, e o registro de quem
    foi lido (para provar que o evento ignorado nao chega a ler nada)."""

    def __init__(self, issues: dict[int, dict], *, sub_issues: dict[int, list[dict]] | None = None, erro=None):
        self.issues = issues
        self.sub_issues = sub_issues or {}
        self.erro = erro
        self.leituras: list[int] = []

    def ler_issue(self, numero: int) -> dict:
        self.leituras.append(numero)
        if self.erro is not None:
            raise self.erro
        if numero not in self.issues:
            raise github_client.IssueNaoEncontradaError(str(numero))
        return self.issues[numero]

    def ler_sub_issues(self, numero: int) -> list[dict]:
        return self.sub_issues.get(numero, [])


def _foto_guardada(gh: _GithubFalso, numero: int) -> dict:
    """A foto que a Demanda ja tem guardada: a MESMA que o cliente devolveria
    agora. E o unico jeito honesto de montar o caso "a foto nao mudou": escrever
    o dicionario a mao provaria a comparacao contra um dado que o codigo talvez
    nem produza assim."""
    return github_client.montar_foto(gh.issues[numero], gh.sub_issues.get(numero, []))


# O carimbo que a sincronizacao ANTERIOR deixou. Valor fixo para os casos poderem
# dizer "este carimbo nao foi tocado" sem depender do relogio.
CARIMBO_ANTERIOR = "2026-09-09T08:00:00+00:00"


def _ja_sincronizada(gh: _GithubFalso, numero: int, did: str = "D1", **campos) -> dict:
    """A Demanda como a sincronizacao anterior a deixou: a foto guardada E o
    cache que a regra de hoje deriva dela.

    O cache vem do MESMO `mudanca_da_foto` que a rotina usa (issue #690), e nao
    escrito a mao: uma Demanda com a foto guardada e as colunas derivadas vazias
    nao e "ja sincronizada", e sim uma Demanda desatualizada, que a rotina tem o
    dever de regravar. Testes de idempotencia montados assim ficariam verdes
    provando o contrario do que dizem.

    Quem quer o cache VELHO (a regra mudou desde entao) passa a coluna por
    `campos`: o caso mostra, numa linha so, o que esta fora de dia.
    """
    cache = tecnologia_sincronizacao.mudanca_da_foto(_foto_guardada(gh, numero))
    cache["github_sincronizado_em"] = CARIMBO_ANTERIOR
    # O Responsavel tambem e derivado (issue #1534): a issue sem dono no GitHub
    # deixa a Demanda sem Responsavel. Quem monta issue com dono passa o
    # Responsavel dele por `campos`.
    cache["responsavel_id"] = None
    return _demanda(did, github_issue_numero=numero, **{**cache, **campos})


def _montar(
    *,
    demandas: list[dict] | None = None,
    conversas: list[dict] | None = None,
    participantes: list[dict] | None = None,
    produtos: list[dict] | None = None,
    github: _GithubFalso | None = None,
    falhas: dict[str, Exception] | None = None,
    antes_do_update=None,
    falhar_ao_ler: str | None = None,
    monkeypatch=None,
) -> tuple[TestClient, _SupabaseMock, _GithubFalso]:
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(webhooks_router.router, prefix="/api")

    sb = _SupabaseMock(
        {
            "tecnologia_demandas": [dict(d) for d in (demandas or [])],
            "tecnologia_conversas": [dict(c) for c in (conversas or [])],
            "participantes": [dict(p) for p in (participantes or [])],
            "tecnologia_produtos": [dict(p) for p in (produtos or [])],
        },
        falhas=falhas,
        antes_do_update=antes_do_update,
        falhar_ao_ler=falhar_ao_ler,
    )

    gh = github or _GithubFalso({})
    if monkeypatch is not None:
        monkeypatch.setattr(github_client, "ler_issue", gh.ler_issue)
        monkeypatch.setattr(github_client, "ler_sub_issues", gh.ler_sub_issues)

    app.dependency_overrides[get_supabase_client] = lambda: sb
    # `raise_server_exceptions=False` para o 500 chegar como RESPOSTA, e nao como
    # excecao que estoura no teste: e assim que o cliente de verdade (o GitHub)
    # ve a rota, e e a unica forma de assertar "isto responde 401, e nao 500".
    return TestClient(app, raise_server_exceptions=False), sb, gh


def _fio(sb: _SupabaseMock) -> list[dict]:
    return sb.tabelas["tecnologia_conversas"]


def _demandas(sb: _SupabaseMock) -> list[dict]:
    return sb.tabelas["tecnologia_demandas"]


def _corpo(numero: int | bool | None = 673, acao: str = "labeled", repo: str = REPO) -> bytes:
    """O corpo CRU, com os espacos que o GitHub manda.

    Cru de proposito, e nao um `dict` que o teste serializa na hora do envio: e a
    unica forma de o teste distinguir o corpo recebido do corpo re-serializado, e
    e essa distincao que a assinatura do GitHub cobra.
    """
    payload = {"action": acao, "issue": {"number": numero}, "repository": {"full_name": repo}}
    return json.dumps(payload, indent=2).encode("utf-8")


def _assinar(corpo: bytes, segredo: str = SEGREDO) -> str:
    return "sha256=" + hmac.new(segredo.encode("utf-8"), corpo, hashlib.sha256).hexdigest()


def _entregar(
    cliente: TestClient,
    corpo: bytes,
    *,
    assinatura: str | None = "auto",
    evento: str | None = "issues",
    entrega: str = "d-1",
):
    cabecalhos = {"Content-Type": "application/json", "X-GitHub-Delivery": entrega}
    if evento is not None:
        cabecalhos["X-GitHub-Event"] = evento
    if assinatura == "auto":
        assinatura = _assinar(corpo)
    if assinatura is not None:
        cabecalhos["X-Hub-Signature-256"] = assinatura
    return cliente.post(ROTA, content=corpo, headers=cabecalhos)


def _entregar_com_header_cru(cliente: TestClient, corpo: bytes, assinatura: bytes):
    """A entrega com o header da assinatura em BYTES.

    Existe porque o httpx codifica header em ASCII e recusaria o valor antes de
    sair, o que apagaria o caso justamente onde ele morde. Em bytes, o valor
    atravessa e chega a rota como o Starlette o entrega em producao: decodificado
    em latin-1, com o byte alto virando caractere nao ASCII.
    """
    cabecalhos = {
        b"Content-Type": b"application/json",
        b"X-GitHub-Event": b"issues",
        b"X-Hub-Signature-256": assinatura,
    }
    return cliente.post(ROTA, content=corpo, headers=cabecalhos)


def _entregar_em_pedacos(cliente: TestClient, corpo: bytes, *, tamanho_do_pedaco: int = 8):
    """A entrega SEM anunciar `Content-Length`, como faz quem manda o corpo em
    pedacos (`Transfer-Encoding: chunked`).

    O httpx so omite o `Content-Length` quando o conteudo e um iteravel de
    tamanho desconhecido, e e por isso que o corpo sai daqui por um gerador: com
    `bytes` ele anunciaria o tamanho e o caso perderia o sentido, porque o
    pre-check do anunciado o recusaria antes de a leitura comecar.

    O corpo sai daqui partido, mas nao chega partido: o transporte do
    `TestClient` o junta num pedaco util so antes de entrega-lo a rota. O que
    este helper alcanca, entao, e a AUSENCIA do `Content-Length`, e nao a ordem
    dos pedacos, que e assunto do `_entregar_por_asgi`.
    """

    def _pedacos():
        for inicio in range(0, len(corpo), tamanho_do_pedaco):
            yield corpo[inicio : inicio + tamanho_do_pedaco]

    cabecalhos = {
        "Content-Type": "application/json",
        "X-GitHub-Delivery": "d-1",
        "X-GitHub-Event": "issues",
        "X-Hub-Signature-256": _assinar(corpo),
    }
    return cliente.post(ROTA, content=_pedacos(), headers=cabecalhos)


async def _entregar_por_asgi(
    cliente: TestClient,
    pedacos: list[bytes],
    *,
    anunciado: str | None = None,
) -> tuple[int, list[int]]:
    """A entrega falando ASGI direto com o app da rota, devolvendo o status e o
    tamanho de cada pedaco que a rota chegou a PEDIR.

    Existe porque o transporte do `TestClient` junta o corpo num pedaco so: por
    ele, "recusou no terceiro pedaco" e "leu os cinco e recusou depois" sao
    indistinguiveis, e essa distincao e o criterio de aceite. Aqui quem entrega
    os pedacos e o teste, um a um, e o que fica registrado e o que foi pedido.

    Continua sendo a ROTA de verdade: o mesmo app montado, o mesmo roteamento e
    as mesmas dependencias. O que muda e so quem fala do outro lado do fio.
    """
    corpo = b"".join(pedacos)
    cabecalhos = [
        (b"host", b"testserver"),
        (b"content-type", b"application/json"),
        (b"x-github-delivery", b"d-1"),
        (b"x-github-event", b"issues"),
        (b"x-hub-signature-256", _assinar(corpo).encode("ascii")),
    ]
    if anunciado is None:
        cabecalhos.append((b"transfer-encoding", b"chunked"))
    else:
        cabecalhos.append((b"content-length", anunciado.encode("ascii")))

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": ROTA,
        "raw_path": ROTA.encode("ascii"),
        "query_string": b"",
        "root_path": "",
        "headers": cabecalhos,
        "client": ("127.0.0.1", 50000),
        "server": ("testserver", 80),
    }

    pendentes = list(pedacos)
    pedidos: list[int] = []

    async def receive():
        if not pendentes:
            return {"type": "http.request", "body": b"", "more_body": False}
        pedaco = pendentes.pop(0)
        pedidos.append(len(pedaco))
        return {"type": "http.request", "body": pedaco, "more_body": bool(pendentes)}

    mensagens: list[dict] = []

    async def send(mensagem):
        mensagens.append(mensagem)

    await cliente.app(scope, receive, send)
    status = next(m["status"] for m in mensagens if m["type"] == "http.response.start")
    return status, pedidos


# ─── 1. A porta: HMAC ────────────────────────────────────────────────────────


class TestATravaDeRedeContinuaDePe:
    """A contraprova da fixture que impede este arquivo de sair para a rede.

    Uma fixture que ninguem observa pode virar no-op sem que nada acuse. Este
    teste a torna visivel: se a `_sem_github_de_verdade` sumir, e AQUI que o
    vermelho aparece, e nao numa chamada silenciosa para api.github.com.
    """

    def test_o_cliente_do_github_nao_sai_para_a_rede(self, monkeypatch):
        monkeypatch.setattr(settings, "github_integracao_token", "token-de-teste")
        monkeypatch.setattr(settings, "github_integracao_repo", "dono/repo")
        with pytest.raises(AssertionError, match="de verdade"):
            github_client.ler_issue(673)


class TestAssinatura:
    def test_assinatura_certa_e_aceita(self, monkeypatch):
        """O detector. Sem ele, uma rota que respondesse 401 a TUDO passaria em
        todos os testes de recusa abaixo."""
        gh = _GithubFalso({673: _issue(673, labels=("in-progress",))})
        cliente, sb, _ = _montar(demandas=[_demanda("D1", github_issue_numero=673)], github=gh, monkeypatch=monkeypatch)

        resposta = _entregar(cliente, _corpo())

        assert resposta.status_code == 200
        assert _demandas(sb)[0]["etapa"] == ETAPA_EM_DESENVOLVIMENTO

    def test_sem_assinatura_e_401_e_nao_escreve(self, monkeypatch):
        gh = _GithubFalso({673: _issue(673, labels=("in-progress",))})
        cliente, sb, _ = _montar(demandas=[_demanda("D1", github_issue_numero=673)], github=gh, monkeypatch=monkeypatch)

        resposta = _entregar(cliente, _corpo(), assinatura=None)

        assert resposta.status_code == 401
        assert _demandas(sb)[0]["etapa"] == ETAPA_EM_ANALISE
        assert _fio(sb) == []
        assert gh.leituras == []

    @pytest.mark.parametrize(
        "cabecalho",
        (
            "",
            "sha256=",
            "nao-e-uma-assinatura",
            "sha1=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "sha256=nao-e-hexadecimal",
        ),
        ids=("vazio", "sem-o-hash", "sem-algoritmo", "outro-algoritmo", "hash-ilegivel"),
    )
    def test_assinatura_malformada_e_401(self, cabecalho, monkeypatch):
        gh = _GithubFalso({673: _issue(673, labels=("in-progress",))})
        cliente, sb, _ = _montar(demandas=[_demanda("D1", github_issue_numero=673)], github=gh, monkeypatch=monkeypatch)

        resposta = _entregar(cliente, _corpo(), assinatura=cabecalho)

        assert resposta.status_code == 401
        assert _fio(sb) == []

    def test_assinatura_de_outro_segredo_e_401(self, monkeypatch):
        gh = _GithubFalso({673: _issue(673, labels=("in-progress",))})
        cliente, sb, _ = _montar(demandas=[_demanda("D1", github_issue_numero=673)], github=gh, monkeypatch=monkeypatch)
        corpo = _corpo()

        resposta = _entregar(cliente, corpo, assinatura=_assinar(corpo, "outro-segredo-falso"))

        assert resposta.status_code == 401
        assert _demandas(sb)[0]["etapa"] == ETAPA_EM_ANALISE

    def test_corpo_trocado_depois_de_assinado_e_401(self, monkeypatch):
        gh = _GithubFalso({673: _issue(673, labels=("in-progress",))})
        cliente, _, _ = _montar(demandas=[_demanda("D1", github_issue_numero=673)], github=gh, monkeypatch=monkeypatch)

        resposta = _entregar(cliente, _corpo(acao="closed"), assinatura=_assinar(_corpo(acao="labeled")))

        assert resposta.status_code == 401

    def test_a_conferencia_e_sobre_o_corpo_cru_e_nao_sobre_o_json_reserializado(self, monkeypatch):
        """O mutante que este teste mata: conferir a assinatura contra
        `json.dumps(await request.json())` em vez de `await request.body()`.

        O GitHub assina os BYTES que mandou. O corpo daqui vem com indentacao; o
        re-serializado sai compacto. As duas formas carregam o mesmo dicionario,
        entao um webhook que re-serializa continua sincronizando certo e so quebra
        quando o GitHub muda o espacamento, em producao, sem teste nenhum reclamar.
        """
        gh = _GithubFalso({673: _issue(673, labels=("in-progress",))})
        cliente, sb, _ = _montar(demandas=[_demanda("D1", github_issue_numero=673)], github=gh, monkeypatch=monkeypatch)
        corpo = _corpo()
        reserializado = json.dumps(json.loads(corpo), separators=(",", ":")).encode("utf-8")

        assert reserializado != corpo, "o caso perdeu o sentido: os dois corpos ficaram iguais"

        resposta = _entregar(cliente, corpo, assinatura=_assinar(reserializado))

        assert resposta.status_code == 401
        assert _fio(sb) == []

    def test_byte_nao_ascii_no_header_e_401_e_nao_500(self, monkeypatch):
        """A recusa tem que ser recusa, e nao defeito.

        `hmac.compare_digest` com dois `str` exige ASCII nos dois lados: fora
        disso ele LEVANTA `TypeError` em vez de devolver `False`. O Starlette
        decodifica header em latin-1 e os parsers de HTTP deixam passar qualquer
        byte 0x80-0xFF no valor, entao um header assim virava 500 com traceback,
        e a linha de log da recusa nem era alcancada: justamente a tentativa
        malformada era a unica que nao deixava rastro.

        Enviado com o header em BYTES porque o httpx recusaria o valor antes de
        sair, o que e o motivo de nenhum dos casos anteriores ter pego isto.
        """
        gh = _GithubFalso({673: _issue(673, labels=("in-progress",))})
        cliente, sb, _ = _montar(demandas=[_demanda("D1", github_issue_numero=673)], github=gh, monkeypatch=monkeypatch)

        resposta = _entregar_com_header_cru(cliente, _corpo(), b"sha256=" + b"a" * 63 + b"\xe7")

        assert resposta.status_code == 401
        assert _fio(sb) == []
        assert _demandas(sb)[0]["etapa"] == ETAPA_EM_ANALISE

    def test_a_recusa_do_header_nao_ascii_fica_no_log(self, monkeypatch, caplog):
        """O par do teste acima: 401 sem log seria a mesma cegueira com outro
        numero. A linha da recusa precisa ser ALCANCADA neste caminho."""
        cliente, _, _ = _montar(monkeypatch=monkeypatch)

        with caplog.at_level(logging.WARNING, logger="app.routers.webhooks"):
            _entregar_com_header_cru(cliente, _corpo(), b"sha256=" + b"a" * 63 + b"\xe7")

        assert "Assinatura inválida" in caplog.text

    def test_o_algoritmo_declarado_precisa_ser_sha256(self, monkeypatch):
        """O MESMO hash, com outro rotulo na frente, nao passa.

        O GitHub manda `sha256=`. Ignorar o rotulo faria o app aceitar
        `sha1=<hash sha256>`, isto e, dizer que confere um algoritmo e conferir
        outro. O caso e diferente dos malformados acima: la o hash tambem estava
        errado, e o 401 vinha de graca; aqui o hash esta CERTO, e so o rotulo
        muda.
        """
        cliente, _, _ = _montar(monkeypatch=monkeypatch)
        corpo = _corpo(numero=999)

        resposta = _entregar(cliente, corpo, assinatura=_assinar(corpo).replace("sha256=", "sha1="))

        assert resposta.status_code == 401

    def test_a_comparacao_e_em_tempo_constante(self, monkeypatch):
        """A guarda contra ataque de tempo nao tem desfecho observavel pela rota:
        o `==` e o `compare_digest` recusam a MESMA assinatura errada, e aceitam a
        mesma certa. O que da para observar e se a conferencia passou por
        `hmac.compare_digest`, e e isso que o espiao faz.

        Ler o codigo-fonte da funcao atras da palavra `compare_digest` seria
        teste em vacuo: a palavra tambem esta no docstring, e o mutante que troca
        so a linha do `return` continua verde.
        """
        chamadas: list = []
        original = hmac.compare_digest

        def _espiao(a, b):
            chamadas.append((a, b))
            return original(a, b)

        monkeypatch.setattr(webhooks_router.hmac, "compare_digest", _espiao)
        cliente, _, _ = _montar(monkeypatch=monkeypatch)
        corpo = _corpo(numero=999)
        # Em BYTES: a comparacao e de bytes justamente para nao levantar
        # `TypeError` com header nao ASCII (ver o caso do byte alto acima).
        digest = _assinar(corpo).removeprefix("sha256=").encode("ascii")

        resposta = _entregar(cliente, corpo)

        assert resposta.status_code == 200, "o caso perdeu o sentido: a entrega nem chegou a conferir a assinatura"
        # O QUE o espiao viu, e nao so que viu algo: a lista nao vazia sozinha
        # ficaria verde se o proprio teste enchesse a lista sem instalar o espiao.
        assert chamadas == [(digest, digest)], (
            "a assinatura foi conferida sem `hmac.compare_digest` sobre o digest esperado: "
            "o `==` conta ao atacante quantos bytes ele ja acertou"
        )


class TestTetoDoCorpo:
    """O HMAC precisa dos bytes CRUS, entao o corpo inteiro vai para a memoria
    ANTES de qualquer prova de origem. O teto e o que impede uma porta publica de
    aceitar cem megabytes de quem nao provou ser ninguem."""

    def test_o_teto_e_o_do_proprio_github(self):
        """O piso do teste abaixo, que roda com o teto rebaixado: sem esta linha,
        o valor que VAI para producao nao teria asserção nenhuma, e trocar 25 MB
        por 25 KB (ou por 2 GB) passaria batido."""
        assert webhooks_router.TETO_DO_CORPO_DO_WEBHOOK == 25 * 1024 * 1024

    def test_corpo_acima_do_teto_e_recusado_antes_de_ir_para_a_memoria(self, monkeypatch):
        """A recusa vem do `Content-Length` ANUNCIADO, e a prova disso e a
        assinatura VALIDA: se a rota lesse o corpo antes de olhar o tamanho, esta
        entrega passaria pela assinatura e sincronizaria.

        O teto e rebaixado em vez de o teste mandar 25 MB pela suite. Rebaixar o
        NUMERO nao e monkeypatch da guarda: a guarda continua sendo a que roda, e
        o valor de producao tem o teste acima.
        """
        monkeypatch.setattr(webhooks_router, "TETO_DO_CORPO_DO_WEBHOOK", 10)
        gh = _GithubFalso({673: _issue(673, labels=("in-progress",))})
        cliente, sb, _ = _montar(demandas=[_demanda("D1", github_issue_numero=673)], github=gh, monkeypatch=monkeypatch)

        resposta = _entregar(cliente, _corpo())

        assert resposta.status_code == 413
        assert gh.leituras == []
        assert _fio(sb) == []
        assert _demandas(sb)[0]["etapa"] == ETAPA_EM_ANALISE

    def test_corpo_dentro_do_teto_passa(self, monkeypatch):
        """O detector: um teto que recusasse tudo passaria no teste acima."""
        gh = _GithubFalso({673: _issue(673, labels=("in-progress",))})
        cliente, sb, _ = _montar(demandas=[_demanda("D1", github_issue_numero=673)], github=gh, monkeypatch=monkeypatch)

        resposta = _entregar(cliente, _corpo())

        assert resposta.status_code == 200
        assert _demandas(sb)[0]["etapa"] == ETAPA_EM_DESENVOLVIMENTO

    async def test_o_anunciado_recusa_sem_pedir_um_byte_do_corpo(self, monkeypatch):
        """O pre-check do `Content-Length` anunciado continua de pe, e a prova e
        que a rota nem PEDE o corpo: 413 com a lista de pedacos pedidos vazia.

        Sem esta asserção, a contagem na leitura (o teste abaixo) sozinha
        deixaria o pre-check virar codigo morto sem nada acusar, e a entrega
        honesta grande passaria a custar a leitura inteira antes da recusa.
        """
        monkeypatch.setattr(webhooks_router, "TETO_DO_CORPO_DO_WEBHOOK", 10)
        gh = _GithubFalso({673: _issue(673, labels=("in-progress",))})
        cliente, sb, _ = _montar(demandas=[_demanda("D1", github_issue_numero=673)], github=gh, monkeypatch=monkeypatch)
        corpo = _corpo()

        status, pedidos = await _entregar_por_asgi(cliente, [corpo], anunciado=str(len(corpo)))

        assert status == 413
        assert pedidos == [], "a rota leu o corpo antes de olhar o tamanho anunciado"
        assert gh.leituras == []
        assert _fio(sb) == []
        assert _demandas(sb)[0]["etapa"] == ETAPA_EM_ANALISE

    def test_corpo_em_pedacos_sem_content_length_e_recusado(self, monkeypatch):
        """O buraco que esta issue fecha: quem manda o corpo em pedacos nao
        anuncia `Content-Length` nenhum, e o pre-check do anunciado nao tem o que
        olhar. Um atacante deliberado nunca anuncia.

        A assinatura e VALIDA de proposito: e ela que separa "recusou pelo
        tamanho" de "leu tudo e recusou por outro motivo". Se a rota confiasse so
        no anunciado, esta entrega passaria pela assinatura e sincronizaria.
        """
        monkeypatch.setattr(webhooks_router, "TETO_DO_CORPO_DO_WEBHOOK", 10)
        gh = _GithubFalso({673: _issue(673, labels=("in-progress",))})
        cliente, sb, _ = _montar(demandas=[_demanda("D1", github_issue_numero=673)], github=gh, monkeypatch=monkeypatch)

        resposta = _entregar_em_pedacos(cliente, _corpo())

        assert resposta.status_code == 413
        assert gh.leituras == []
        assert _fio(sb) == []
        assert _demandas(sb)[0]["etapa"] == ETAPA_EM_ANALISE

    async def test_a_leitura_para_no_pedaco_que_passa_do_teto(self, monkeypatch):
        """O 413 sai ANTES de o corpo inteiro ir para a memoria, e nao depois de
        acumular tudo e conferir no fim.

        Contar os bytes so no fim do laco daria o mesmo 413 do teste acima: o que
        distingue os dois desfechos e quantos pedacos a rota chegou a pedir. Com
        teto de 10 e pedacos de 4, a soma passa no terceiro, e e ali que a
        leitura tem que parar, por mais corpo que ainda houvesse para vir.
        """
        monkeypatch.setattr(webhooks_router, "TETO_DO_CORPO_DO_WEBHOOK", 10)
        gh = _GithubFalso({673: _issue(673, labels=("in-progress",))})
        cliente, sb, _ = _montar(demandas=[_demanda("D1", github_issue_numero=673)], github=gh, monkeypatch=monkeypatch)
        corpo = _corpo()
        pedacos = [corpo[i : i + 4] for i in range(0, len(corpo), 4)]
        assert len(pedacos) > 3, "o corpo do caso precisa ter mais pedacos do que a rota deveria ler"

        status, pedidos = await _entregar_por_asgi(cliente, pedacos)

        assert status == 413
        assert pedidos == [4, 4, 4], (
            f"a rota pediu {len(pedidos)} pedacos de {len(pedacos)}: ela acumulou o corpo antes de conferir o teto"
        )
        assert _fio(sb) == []
        assert _demandas(sb)[0]["etapa"] == ETAPA_EM_ANALISE

    def test_entrega_sem_content_length_dentro_do_teto_passa(self, monkeypatch):
        """O detector: uma guarda que recusasse toda entrega sem
        `Content-Length` passaria nos dois testes acima, e o GitHub tem liberdade
        de mandar o corpo em pedacos.

        O que este caso NAO prova e a ordem dos bytes: o transporte do
        `TestClient` junta o corpo num pedaco util so antes de entrega-lo a rota,
        e com um pedaco toda ordem e a mesma ordem. Quem prova a ordem e o teste
        seguinte, que entrega os pedacos um a um.
        """
        gh = _GithubFalso({673: _issue(673, labels=("in-progress",))})
        cliente, sb, _ = _montar(demandas=[_demanda("D1", github_issue_numero=673)], github=gh, monkeypatch=monkeypatch)

        resposta = _entregar_em_pedacos(cliente, _corpo())

        assert resposta.status_code == 200
        assert _demandas(sb)[0]["etapa"] == ETAPA_EM_DESENVOLVIMENTO

    async def test_o_corpo_montado_em_varios_pedacos_fecha_o_hmac_na_ordem(self, monkeypatch):
        """O HMAC fecha sobre os bytes crus NA ORDEM EM QUE VIERAM, e para isso o
        caso precisa de mais de um pedaco util de verdade.

        Montar o corpo ao contrario (`acumulado[:0] = pedaco`) e mutante de uma
        linha que atravessaria a suite inteira sem este teste: com um pedaco util
        so, inverter a ordem nao muda nada. Em producao o preco seria 401 em toda
        entrega grande, justamente a que o GitHub parte em pedacos, e o card so
        andaria pela reconciliacao da hora seguinte, sem nada vermelho no CI.

        Teto de PRODUCAO aqui, e nao rebaixado: o caso nao e sobre o teto, e sim
        sobre a entrega legitima que chega partida e precisa fechar a assinatura.
        """
        gh = _GithubFalso({673: _issue(673, labels=("in-progress",))})
        cliente, sb, _ = _montar(demandas=[_demanda("D1", github_issue_numero=673)], github=gh, monkeypatch=monkeypatch)
        corpo = _corpo()
        pedacos = [corpo[i : i + 8] for i in range(0, len(corpo), 8)]
        assert len(pedacos) > 2, "o caso perde o sentido com um pedaco util so: e a ordem que ele cobra"

        status, pedidos = await _entregar_por_asgi(cliente, pedacos)

        assert status == 200, "a entrega legitima partida em pedacos foi recusada"
        assert len(pedidos) == len(pedacos), "a rota parou de ler antes do fim de uma entrega que cabia no teto"
        assert _demandas(sb)[0]["etapa"] == ETAPA_EM_DESENVOLVIMENTO

    async def test_o_corpo_do_tamanho_exato_do_teto_passa_pelas_duas_guardas(self, monkeypatch):
        """A fronteira, nas DUAS guardas: o teto e `>` estrito, entao a entrega
        de tamanho exatamente igual ao teto passa.

        Todo outro caso deste arquivo esta longe da borda (corpo de ~100 bytes
        contra teto de 10), e por isso trocar `>` por `>=` sobreviveria nas duas
        linhas. O risco nao e so o mutante: e as duas guardas divergirem na
        borda, e a mesma entrega ser aceita por uma e recusada pela outra sem
        nada acusar.

        A entrega que anuncia passa pelas DUAS guardas, entao dizer "foi o
        anunciado" na falha seria culpar causa que o desfecho nao distingue. Quem
        distingue e a lista de pedacos PEDIDOS: vazia so quando a recusa veio
        antes de a leitura comecar.
        """
        corpo = _corpo()
        monkeypatch.setattr(webhooks_router, "TETO_DO_CORPO_DO_WEBHOOK", len(corpo))
        gh = _GithubFalso({673: _issue(673, labels=("in-progress",))})
        cliente, sb, _ = _montar(demandas=[_demanda("D1", github_issue_numero=673)], github=gh, monkeypatch=monkeypatch)

        anunciando, pedidos = await _entregar_por_asgi(cliente, [corpo], anunciado=str(len(corpo)))
        em_pedacos, _ = await _entregar_por_asgi(cliente, [corpo[:40], corpo[40:]])

        assert anunciando == 200, "o corpo do tamanho EXATO do teto foi recusado " + (
            "pela guarda do anunciado, sem ler um byte" if pedidos == [] else "pela contagem da leitura"
        )
        assert em_pedacos == 200, "a contagem da leitura recusou o corpo do tamanho EXATO do teto"
        assert _demandas(sb)[0]["etapa"] == ETAPA_EM_DESENVOLVIMENTO

    async def test_a_recusa_pela_contagem_fica_no_log(self, monkeypatch, caplog):
        """As duas recusas respondem o MESMO 413 com o mesmo motivo generico, que
        e o que a porta publica deve a quem nao provou ser ninguem.

        No stdout do container, entao, a linha do log e a UNICA coisa que
        distingue "recusou o que foi anunciado" de "cortou no meio da leitura", e
        e por ela que o operador ve alguem mandando corpo grande sem anunciar.
        Apagar o `logger.warning` nao muda resposta nenhuma.
        """
        monkeypatch.setattr(webhooks_router, "TETO_DO_CORPO_DO_WEBHOOK", 10)
        cliente, _, _ = _montar(monkeypatch=monkeypatch)
        corpo = _corpo()
        pedacos = [corpo[i : i + 4] for i in range(0, len(corpo), 4)]

        with caplog.at_level(logging.WARNING, logger="app.routers.webhooks"):
            status, _ = await _entregar_por_asgi(cliente, pedacos)

        assert status == 413
        assert "passou do teto de 10 bytes durante a leitura" in caplog.text


class TestTetoDeTaxa:
    def test_martelar_a_porta_leva_429(self, monkeypatch):
        """Sem teto, quem martela sem assinatura gasta leitura de corpo e HMAC do
        app a vontade, e uma entrega capturada no `Recent Deliveries` vira replay
        sem fim queimando a cota da API do GitHub, que e uma so para o app."""
        cliente, _, _ = _montar(monkeypatch=monkeypatch)
        corpo = _corpo(numero=999)

        vistos = {_entregar(cliente, corpo, assinatura=None).status_code for _ in range(130)}

        assert 429 in vistos

    def test_o_teto_e_folgado_o_bastante_para_um_pico_legitimo(self, monkeypatch):
        """A folga E a decisao: o GitHub nao reentrega, entao um 429 numa faxina
        de labels em lote perderia o evento ate a reconciliacao da hora seguinte.
        Uma dezena de entregas seguidas nao pode esbarrar no teto."""
        gh = _GithubFalso({999: _issue(999)})
        cliente, _, _ = _montar(demandas=[], github=gh, monkeypatch=monkeypatch)
        corpo = _corpo(numero=999)

        vistos = {_entregar(cliente, corpo).status_code for _ in range(30)}

        assert vistos == {200}


class TestSemSegredoConfigurado:
    def test_sem_segredo_a_rota_responde_503(self, monkeypatch):
        """O passo humano do deploy: sem `GITHUB_WEBHOOK_SECRET` no Coolify, a
        rota nao tem como conferir NADA, e fingir que confere seria pior do que
        recusar."""
        monkeypatch.setattr(settings, "github_webhook_secret", "")
        gh = _GithubFalso({673: _issue(673, labels=("in-progress",))})
        cliente, sb, _ = _montar(demandas=[_demanda("D1", github_issue_numero=673)], github=gh, monkeypatch=monkeypatch)

        resposta = _entregar(cliente, _corpo())

        assert resposta.status_code == 503
        assert _fio(sb) == []
        assert _demandas(sb)[0]["etapa"] == ETAPA_EM_ANALISE

    def test_sem_segredo_a_resposta_nao_conta_o_que_falta(self, monkeypatch):
        """Quem bate na porta nao esta autenticado: a frase nao diz o nome da
        variavel nem que ela e o que falta. O motivo de verdade vai para o log."""
        monkeypatch.setattr(settings, "github_webhook_secret", "")
        cliente, _, _ = _montar(monkeypatch=monkeypatch)

        corpo = _entregar(cliente, _corpo()).text.lower()

        assert "secret" not in corpo
        assert "segredo" not in corpo
        assert "github_webhook_secret" not in corpo

    def test_sem_segredo_o_log_diz_o_que_falta(self, monkeypatch, caplog):
        """O par do teste acima: a frase generica na resposta so e aceitavel
        porque a causa fica registrada de algum lugar que o operador le."""
        monkeypatch.setattr(settings, "github_webhook_secret", "")
        cliente, _, _ = _montar(monkeypatch=monkeypatch)

        with caplog.at_level(logging.ERROR, logger="app.routers.webhooks"):
            _entregar(cliente, _corpo())

        assert "GITHUB_WEBHOOK_SECRET" in caplog.text

    def test_o_segredo_nasce_vazio_na_config(self):
        """Ambiente sem a variavel nao pode subir com um segredo default: um
        default seria um segredo publico, e a porta ficaria aberta."""
        assert type(settings)().github_webhook_secret == ""


# ─── 2. So o evento `issues` ─────────────────────────────────────────────────


class TestSoOEventoIssues:
    @pytest.mark.parametrize("evento", ("issue_comment", "push", "pull_request_review", "ping"))
    def test_outro_evento_responde_2xx_e_nao_faz_nada(self, evento, monkeypatch):
        gh = _GithubFalso({673: _issue(673, labels=("in-progress",))})
        cliente, sb, _ = _montar(demandas=[_demanda("D1", github_issue_numero=673)], github=gh, monkeypatch=monkeypatch)

        resposta = _entregar(cliente, _corpo(), evento=evento)

        assert resposta.status_code == 200
        assert gh.leituras == [], "o evento ignorado nem chegou a gastar cota do GitHub"
        assert _fio(sb) == []
        assert _demandas(sb)[0]["etapa"] == ETAPA_EM_ANALISE

    def test_sem_o_header_do_evento_nao_faz_nada(self, monkeypatch):
        gh = _GithubFalso({673: _issue(673, labels=("in-progress",))})
        cliente, sb, _ = _montar(demandas=[_demanda("D1", github_issue_numero=673)], github=gh, monkeypatch=monkeypatch)

        resposta = _entregar(cliente, _corpo(), evento=None)

        assert resposta.status_code == 200
        assert _fio(sb) == []

    def test_o_evento_errado_ainda_passa_pela_assinatura(self, monkeypatch):
        """A ordem importa: conferir o evento ANTES da assinatura deixaria
        qualquer um descobrir, sem segredo nenhum, quais eventos o app trata."""
        cliente, _, _ = _montar(monkeypatch=monkeypatch)

        resposta = _entregar(cliente, _corpo(), evento="push", assinatura=None)

        assert resposta.status_code == 401


class TestAcoesTratadas:
    @pytest.mark.parametrize("acao", ("labeled", "unlabeled", "closed", "reopened", "edited", "assigned", "unassigned"))
    def test_a_acao_da_lista_sincroniza(self, acao, monkeypatch):
        gh = _GithubFalso({673: _issue(673, labels=("in-progress",))})
        cliente, sb, _ = _montar(demandas=[_demanda("D1", github_issue_numero=673)], github=gh, monkeypatch=monkeypatch)

        resposta = _entregar(cliente, _corpo(acao=acao))

        assert resposta.status_code == 200
        assert _demandas(sb)[0]["etapa"] == ETAPA_EM_DESENVOLVIMENTO

    @pytest.mark.parametrize("acao", ("milestoned", "opened", "deleted"))
    def test_a_acao_de_fora_da_lista_nao_faz_nada(self, acao, monkeypatch):
        gh = _GithubFalso({673: _issue(673, labels=("in-progress",))})
        cliente, sb, _ = _montar(demandas=[_demanda("D1", github_issue_numero=673)], github=gh, monkeypatch=monkeypatch)

        resposta = _entregar(cliente, _corpo(acao=acao))

        assert resposta.status_code == 200
        assert gh.leituras == []
        assert _fio(sb) == []
        assert _demandas(sb)[0]["etapa"] == ETAPA_EM_ANALISE


class TestIssueSemDemandaVinculada:
    def test_issue_sem_vinculo_responde_2xx_sem_escrever(self, monkeypatch):
        """A maioria esmagadora das entregas: o repositorio tem centenas de
        issues e um punhado de Demandas vinculadas."""
        gh = _GithubFalso({999: _issue(999)})
        cliente, sb, _ = _montar(demandas=[_demanda("D1", github_issue_numero=673)], github=gh, monkeypatch=monkeypatch)

        resposta = _entregar(cliente, _corpo(numero=999))

        assert resposta.status_code == 200
        assert gh.leituras == []
        assert _fio(sb) == []
        assert _demandas(sb)[0]["github_foto"] is None

    @pytest.mark.parametrize(
        "numero",
        (None, "673", 0, -1, True),
        ids=("ausente", "texto", "zero", "negativo", "booleano"),
    )
    def test_numero_que_nao_serve_e_ignorado_sem_consultar_o_banco(self, numero, monkeypatch):
        """A guarda diz "e um numero de issue", e precisa ser isso.

        O `True` esta na lista porque em Python bool E int: `isinstance(x, int)`
        sozinho aceitaria `{"number": true}` e viraria uma consulta por
        `github_issue_numero=True`.

        A tabela tem uma Demanda VINCULADA e uma SEM vinculo de proposito. Com so
        a vinculada, tirar a guarda inteira manteria o teste verde, porque
        nenhuma linha casaria com o numero invalido: e a nao vinculada
        (`github_issue_numero=None`) que faz o `.eq(..., None)` casar e denunciar
        a ausencia da guarda pelo CORPO da resposta.
        """
        cliente, sb, _ = _montar(
            demandas=[_demanda("D1", github_issue_numero=673), _demanda("D2", github_issue_numero=None)],
            monkeypatch=monkeypatch,
        )
        corpo = _corpo(numero=numero)

        resposta = _entregar(cliente, corpo)

        assert resposta.status_code == 200
        assert resposta.json() == {"ignorado": "issue"}
        assert _fio(sb) == []


class TestRepositorioDaEntrega:
    """Defesa em profundidade: o mesmo segredo reaproveitado noutro repositorio
    ou num fork mandaria o app reler issues pelo numero errado."""

    def test_entrega_de_outro_repositorio_e_ignorada(self, monkeypatch):
        gh = _GithubFalso({673: _issue(673, labels=("in-progress",))})
        cliente, sb, _ = _montar(demandas=[_demanda("D1", github_issue_numero=673)], github=gh, monkeypatch=monkeypatch)

        resposta = _entregar(cliente, _corpo(repo="outra-pessoa/hospital-reunioes"))

        assert resposta.status_code == 200
        assert resposta.json() == {"ignorado": "outro_repositorio"}
        assert gh.leituras == []
        assert _fio(sb) == []
        assert _demandas(sb)[0]["etapa"] == ETAPA_EM_ANALISE

    def test_entrega_sem_repositorio_no_payload_e_ignorada(self, monkeypatch):
        """Todo evento `issues` do GitHub traz `repository`. Um payload sem ele
        nao veio de la, e "nao consigo comparar" nao pode virar "pode passar"."""
        cliente, sb, _ = _montar(demandas=[_demanda("D1", github_issue_numero=673)], monkeypatch=monkeypatch)
        corpo = json.dumps({"action": "labeled", "issue": {"number": 673}}).encode("utf-8")

        resposta = _entregar(cliente, corpo)

        assert resposta.json() == {"ignorado": "outro_repositorio"}
        assert _fio(sb) == []

    def test_sem_repositorio_configurado_a_guarda_nao_bloqueia(self, monkeypatch):
        """Sem `GITHUB_INTEGRACAO_REPO` nao ha com o que comparar, e recusar aqui
        trocaria uma falha honesta adiante (o cliente exige a variavel) por um
        silencio que ninguem liga a causa."""
        monkeypatch.setattr(settings, "github_integracao_repo", "")
        cliente, sb, _ = _montar(demandas=[_demanda("D1", github_issue_numero=673)], monkeypatch=monkeypatch)

        resposta = _entregar(cliente, _corpo(repo="qualquer/coisa"))

        assert resposta.json() != {"ignorado": "outro_repositorio"}
        assert _fio(sb) == []


# ─── 3. A sincronizacao ──────────────────────────────────────────────────────


class TestSincronizacaoPeloWebhook:
    def test_a_etapa_muda_e_a_conversa_aposentada_nao_ganha_linha(self, monkeypatch):
        gh = _GithubFalso({673: _issue(673, labels=("in-progress",))})
        cliente, sb, _ = _montar(
            demandas=[_demanda("D1", github_issue_numero=673, etapa=ETAPA_PLANEJADA)],
            github=gh,
            monkeypatch=monkeypatch,
        )

        _entregar(cliente, _corpo())

        demanda = _demandas(sb)[0]
        assert demanda["etapa"] == ETAPA_EM_DESENVOLVIMENTO
        assert demanda["github_sincronizado_em"]
        assert _fio(sb) == [], "a Conversa da Demanda saiu com a ADR 0077: ninguem a le"

    def test_a_entrega_guarda_a_foto_e_as_partes(self, monkeypatch):
        gh = _GithubFalso(
            {673: _issue(673, resumo={"total": 7, "completed": 3})},
            sub_issues={673: [_issue(678, labels=("in-progress",))]},
        )
        cliente, sb, _ = _montar(demandas=[_demanda("D1", github_issue_numero=673)], github=gh, monkeypatch=monkeypatch)

        _entregar(cliente, _corpo())

        demanda = _demandas(sb)[0]
        assert demanda["partes_entregues"] == 3
        assert demanda["partes_total"] == 7
        assert demanda["github_foto"]["partes"][0]["numero"] == 678
        assert demanda["etapa"] == ETAPA_EM_DESENVOLVIMENTO

    def test_foto_igual_e_derivado_igual_nao_escrevem_nada(self, monkeypatch):
        """Criterio de aceite: foto igual a guardada nao grava linha nem mexe na
        ultima sincronizacao. Sem esta guarda, a reconciliacao de hora em hora
        encheria o fio do diretor de linhas repetidas.

        Desde a issue #690 a guarda olha o DERIVADO, e nao so a foto crua, e o
        caso cobra o UPDATE de frente: sem o espiao, um `update` que casasse
        zero linha (ou que regravasse o mesmo valor) passaria despercebido, e a
        promessa aqui e que nenhuma escrita SAI.
        """
        gh = _GithubFalso({673: _issue(673, labels=("in-progress",))})
        updates: list[tuple[str, dict]] = []
        cliente, sb, _ = _montar(
            demandas=[_ja_sincronizada(gh, 673)],
            github=gh,
            antes_do_update=lambda nome, update, _linhas: updates.append((nome, update)),
            monkeypatch=monkeypatch,
        )

        resposta = _entregar(cliente, _corpo())

        assert resposta.status_code == 200
        assert updates == [], "nada mudou no GitHub nem na regra: nenhum UPDATE pode sair"
        assert _fio(sb) == []
        assert _demandas(sb)[0]["github_sincronizado_em"] == CARIMBO_ANTERIOR

    def test_a_foto_crua_que_muda_sozinha_e_regravada_com_o_fio_calado(self, monkeypatch):
        """O avesso do caso acima: a foto mudou e nenhum derivado mudou.

        O repositorio foi renomeado, a `url` da issue e outra, e label, corpo e
        partes continuam iguais. A foto e uma das colunas do cache, e por isso
        entra na comparacao junto com os derivados (issue #690): sem ela, o
        `github_foto` congelaria no endereco velho, e como o `_vinculo_visivel`
        do router le a `url` de la, o link do Vinculo na tela apontaria para o
        endereco morto para sempre. Nada ficaria vermelho, e ninguem tem por que
        editar a issue de novo so para destravar isso.
        """
        gh = _GithubFalso({673: _issue(673, labels=("in-progress",))})
        demandas = [_ja_sincronizada(gh, 673)]
        url_nova = "https://github.com/pedrorezendefig/hospital-reunioes-renomeado/issues/673"
        gh.issues[673]["html_url"] = url_nova
        cliente, sb, _ = _montar(demandas=demandas, github=gh, monkeypatch=monkeypatch)

        _entregar(cliente, _corpo(acao="edited"))

        demanda = _demandas(sb)[0]
        assert demanda["github_foto"]["url"] == url_nova
        assert demanda["github_sincronizado_em"] != CARIMBO_ANTERIOR
        assert demanda["etapa"] == ETAPA_EM_DESENVOLVIMENTO, "o piso: nenhum derivado mudou, so a foto crua"
        assert demanda["o_que_muda"] == "O selo se atualiza sozinho."
        assert _fio(sb) == [], "a Etapa nao mudou: o fio fica calado"

    def test_a_entrega_repetida_nao_reescreve_a_demanda(self, monkeypatch):
        """O GitHub reentrega, e a mesma entrega duas vezes so escreve uma. A
        guarda e a foto, e nao o id da entrega: quem chega pela reconciliacao
        nao tem id de entrega nenhum e precisa da mesma protecao."""
        gh = _GithubFalso({673: _issue(673, labels=("in-progress",))})
        updates: list[str] = []
        cliente, sb, _ = _montar(
            demandas=[_demanda("D1", github_issue_numero=673)],
            github=gh,
            antes_do_update=lambda nome, _update, _linhas: updates.append(nome),
            monkeypatch=monkeypatch,
        )
        corpo = _corpo()

        primeira = _entregar(cliente, corpo)
        segunda = _entregar(cliente, corpo)

        assert (primeira.status_code, segunda.status_code) == (200, 200)
        assert updates == ["tecnologia_demandas"]
        assert _demandas(sb)[0]["etapa"] == ETAPA_EM_DESENVOLVIMENTO

    def test_a_etapa_igual_nao_grava_linha_mesmo_com_a_foto_diferente(self, monkeypatch):
        """Editar o corpo da issue muda a foto sem mudar a Etapa. O cache e
        atualizado (a fatia do "O que muda" depende dele), e o fio fica calado."""
        gh = _GithubFalso({673: _issue(673, labels=("in-progress",))})
        guardada = _foto_guardada(gh, 673)
        gh.issues[673]["labels"].append({"name": "area:backend"})
        cliente, sb, _ = _montar(
            demandas=[
                _demanda("D1", github_issue_numero=673, etapa=ETAPA_EM_DESENVOLVIMENTO, github_foto=guardada),
            ],
            github=gh,
            monkeypatch=monkeypatch,
        )

        _entregar(cliente, _corpo(acao="edited"))

        assert "area:backend" in _demandas(sb)[0]["github_foto"]["labels"]
        assert _fio(sb) == []

    def test_a_edicao_do_bloco_no_github_chega_ao_card(self, monkeypatch):
        """ "O que muda" é relido a cada webhook (issue #676, história 35).

        O cache dele nasceu na porta de vincular. Sem passar pelo MESMO
        `mudanca_da_foto`, o webhook atualizaria a Etapa e deixaria o texto que o
        diretor lê congelado no dia do Vínculo, e a edição no GitHub nunca
        chegaria à tela.
        """
        gh = _GithubFalso({673: _issue(673)})
        guardada = _foto_guardada(gh, 673)
        gh.issues[673]["body"] = "## Para o diretor\n\nAgora o selo também conta as partes."
        cliente, sb, _ = _montar(
            demandas=[
                _demanda(
                    "D1",
                    github_issue_numero=673,
                    etapa=ETAPA_EM_ANALISE,
                    github_foto=guardada,
                    o_que_muda="O selo se atualiza sozinho.",
                )
            ],
            github=gh,
            monkeypatch=monkeypatch,
        )

        _entregar(cliente, _corpo(acao="edited"))

        assert _demandas(sb)[0]["o_que_muda"] == "Agora o selo também conta as partes."

    def test_github_fora_do_ar_nao_derruba_a_entrega(self, monkeypatch):
        """O GitHub NAO reentrega webhook que falhou: responder 500 aqui perderia
        o evento para sempre. A reconciliacao de hora em hora e quem recupera."""
        gh = _GithubFalso({673: _issue(673)}, erro=github_client.GithubIndisponivelError("timeout"))
        cliente, sb, _ = _montar(demandas=[_demanda("D1", github_issue_numero=673)], github=gh, monkeypatch=monkeypatch)

        resposta = _entregar(cliente, _corpo())

        assert resposta.status_code == 200
        assert _fio(sb) == []
        assert _demandas(sb)[0]["etapa"] == ETAPA_EM_ANALISE

    def test_demanda_concluida_nao_e_tocada_pelo_webhook(self, monkeypatch):
        """Os dois gatilhos precisam concordar: a reconciliacao ja exclui
        Concluida e Cancelada pelo filtro de estado, e o webhook chega pelo numero
        da issue, sem esse filtro. Sem a guarda na rotina, fechar a issue depois
        de alguem concluir a Demanda a mao escreveria no fio de um card fechado.
        """
        gh = _GithubFalso({673: _issue(673, estado="closed", motivo="completed")})
        cliente, sb, _ = _montar(
            demandas=[_demanda("D1", github_issue_numero=673, estado="concluida", etapa=ETAPA_PLANEJADA)],
            github=gh,
            monkeypatch=monkeypatch,
        )

        resposta = _entregar(cliente, _corpo(acao="closed"))

        assert resposta.status_code == 200
        assert gh.leituras == [], "nem chegou a gastar cota sobre um card fechado"
        assert _fio(sb) == []
        assert _demandas(sb)[0]["etapa"] == ETAPA_PLANEJADA


class TestARegraQueMudaAlcancaQuemNaoTeveNovidade:
    """Issue #690. Etapa, partes e "O que muda" sao funcoes PURAS da foto, e a
    regra que as calcula muda com o app: uma label nova em `LABELS_PLANEJADA`, um
    fim de bloco diferente no "Para o diretor".

    Quem decidisse escrever so pela foto CRUA deixaria toda Demanda sem novidade
    no GitHub com o valor da regra velha para sempre: a foto continua identica,
    a reconciliacao de hora em hora passa por ela e nao conserta nada. A guarda
    compara o DERIVADO (sem o carimbo) com o que ja esta nas colunas.

    Os casos montam a Demanda com o cache de ONTEM (o helper `_ja_sincronizada`
    deriva o de hoje) porque e assim que a mudanca de regra chega ao banco: a
    coluna ficou para tras sozinha, sem ninguem tocar na issue.
    """

    def _com_partes(self) -> _GithubFalso:
        return _GithubFalso(
            {673: _issue(673, labels=("in-progress",), resumo={"total": 7, "completed": 3})},
            sub_issues={673: [_issue(678, labels=("in-progress",))]},
        )

    def test_a_etapa_da_regra_velha_e_reescrita_com_a_foto_igual(self, monkeypatch):
        """O caso do criterio de aceite: a Etapa volta a bater com a regra de
        hoje na primeira sincronizacao depois da mudanca."""
        gh = _GithubFalso({673: _issue(673, labels=("in-progress",))})
        cliente, sb, _ = _montar(
            # A regra de ontem lia esta MESMA foto como "Em análise".
            demandas=[_ja_sincronizada(gh, 673, etapa=ETAPA_EM_ANALISE)],
            github=gh,
            monkeypatch=monkeypatch,
        )

        resposta = _entregar(cliente, _corpo())

        demanda = _demandas(sb)[0]
        assert resposta.json()["sincronizada"] is True
        assert demanda["etapa"] == ETAPA_EM_DESENVOLVIMENTO
        assert demanda["github_sincronizado_em"] != CARIMBO_ANTERIOR

    def test_o_bloco_do_diretor_da_regra_velha_e_reescrito_sem_linha_no_fio(self, monkeypatch):
        """A regra do "Para o diretor" muda sem mexer na Etapa: o cache
        acompanha e o fio fica calado, como na edicao do corpo da issue."""
        gh = _GithubFalso({673: _issue(673, labels=("in-progress",))})
        cliente, sb, _ = _montar(
            demandas=[_ja_sincronizada(gh, 673, o_que_muda="O que o fim de bloco antigo cortava aqui.")],
            github=gh,
            monkeypatch=monkeypatch,
        )

        _entregar(cliente, _corpo(acao="edited"))

        assert _demandas(sb)[0]["o_que_muda"] == "O selo se atualiza sozinho."
        assert _fio(sb) == [], "a Etapa nao mudou: a linha do fio repetiria o que o diretor ja leu"

    @pytest.mark.parametrize(
        "coluna, de_ontem",
        [
            ("etapa", ETAPA_EM_ANALISE),
            ("o_que_muda", "O que o fim de bloco antigo cortava aqui."),
            ("partes", []),
            ("partes_entregues", None),
            ("partes_total", None),
        ],
    )
    def test_qualquer_coluna_derivada_fora_de_dia_manda_regravar(self, monkeypatch, coluna, de_ontem):
        """Uma por uma, e nao so a Etapa: a comparacao e sobre o cache INTEIRO.

        Olhar so a Etapa deixaria "3 de 7 partes" e a lista que o diretor le
        congeladas na regra velha, com o selo certo em cima delas, que e pior do
        que o selo errado: parece atualizado.
        """
        gh = self._com_partes()
        cliente, sb, _ = _montar(
            demandas=[_ja_sincronizada(gh, 673, **{coluna: de_ontem})],
            github=gh,
            monkeypatch=monkeypatch,
        )

        _entregar(cliente, _corpo())

        de_hoje = tecnologia_sincronizacao.mudanca_da_foto(_foto_guardada(gh, 673))
        demanda = _demandas(sb)[0]
        assert demanda[coluna] == de_hoje[coluna]
        assert demanda["github_sincronizado_em"] != CARIMBO_ANTERIOR

    def test_o_piso_do_caso_igual_e_a_foto_identica_com_o_cache_cheio(self):
        """O detector, e nao o codigo: sem este piso, "foto igual e derivado
        igual nao escreve nada" poderia estar verde porque a Demanda montada nem
        tem foto guardada (e a rotina escreveria por outro motivo), ou porque as
        colunas derivadas estao vazias dos dois lados.

        E o mesmo piso do lado de cima: os casos da regra velha so provam algo
        se o resto do cache estiver em dia.
        """
        gh = self._com_partes()
        demanda = _ja_sincronizada(gh, 673)

        assert demanda["github_foto"] == _foto_guardada(gh, 673)
        assert demanda["etapa"] == ETAPA_EM_DESENVOLVIMENTO
        assert demanda["o_que_muda"] == "O selo se atualiza sozinho."
        assert (demanda["partes_entregues"], demanda["partes_total"]) == (3, 7)
        assert [parte["numero"] for parte in demanda["partes"]] == [678]


class TestOEventLoopNaoFicaBloqueado:
    """`sincronizar_demanda` faz DUAS chamadas sincronas ao GitHub (10 s de
    timeout cada) mais o I/O sincrono do PostgREST, e o container sobe com UM
    worker so. Chamada direto de dentro do `async def`, ela para o backend
    inteiro enquanto roda, `/api/health` incluido, e uma fila de entregas marca o
    container unhealthy no Traefik, tirando o app do ar para todo mundo."""

    def test_a_sincronizacao_roda_fora_do_event_loop(self, monkeypatch):
        """Prova pela THREAD em que a rotina roda.

        Asserir "a rota respondeu" nao provaria nada: ela responde igual dos dois
        jeitos, e o bloqueio so aparece com carga. O que distingue o codigo certo
        do errado e ONDE o I/O acontece, e isso da para observar de dentro dele.

        As duas threads sao lidas de dentro da propria rota, e nao da thread do
        teste: o `TestClient` ja roda o app noutra thread, entao comparar com a
        do teste ficaria verde ate sem o `run_in_threadpool`. O
        `demanda_vinculada` e chamado direto do corpo `async`, entao ele DA a
        thread do event loop; o `sincronizar_demanda` e o que precisa estar fora
        dela.
        """
        import threading

        do_event_loop: list[int] = []
        da_rotina: list[int] = []
        gh = _GithubFalso({673: _issue(673, labels=("in-progress",))})
        buscar = tecnologia_sincronizacao.demanda_vinculada
        sincronizar = tecnologia_sincronizacao.sincronizar_demanda

        def _espiao_do_loop(supabase, numero):
            do_event_loop.append(threading.get_ident())
            return buscar(supabase, numero)

        def _espiao_da_rotina(supabase, demanda):
            da_rotina.append(threading.get_ident())
            return sincronizar(supabase, demanda)

        monkeypatch.setattr(tecnologia_sincronizacao, "demanda_vinculada", _espiao_do_loop)
        monkeypatch.setattr(tecnologia_sincronizacao, "sincronizar_demanda", _espiao_da_rotina)
        cliente, sb, _ = _montar(demandas=[_demanda("D1", github_issue_numero=673)], github=gh, monkeypatch=monkeypatch)

        resposta = _entregar(cliente, _corpo())

        assert resposta.status_code == 200
        assert _demandas(sb)[0]["etapa"] == ETAPA_EM_DESENVOLVIMENTO, "o caso perdeu o sentido: nada sincronizou"
        assert do_event_loop and da_rotina, "os dois espiões precisam ter sido chamados"
        assert da_rotina[0] != do_event_loop[0], (
            "a sincronização rodou na thread que carrega o event loop: com um worker só, "
            "isso para o backend inteiro por até 20 segundos, /api/health incluído"
        )


class TestCorridaEntreOJobEOWebhook:
    """O job roda numa THREAD do `BackgroundScheduler` e o webhook roda no event
    loop (agora tambem numa thread, pelo `run_in_threadpool`): entre o `select` de
    um e o `update` do outro ha uma janela sem trava, e os dois leriam a mesma
    Etapa antiga.

    A corrida e encenada de forma DETERMINISTICA: as duas leituras acontecem
    antes de qualquer escrita, que e exatamente o estado que a janela produz.
    """

    def _dois_leitores(self, monkeypatch):
        gh = _GithubFalso({673: _issue(673, labels=("in-progress",))})
        monkeypatch.setattr(github_client, "ler_issue", gh.ler_issue)
        monkeypatch.setattr(github_client, "ler_sub_issues", gh.ler_sub_issues)
        sb = _SupabaseMock(
            {
                "tecnologia_demandas": [_demanda("D1", github_issue_numero=673, etapa=ETAPA_PLANEJADA)],
                "tecnologia_conversas": [],
            }
        )
        guardada = sb.tabelas["tecnologia_demandas"][0]
        return sb, dict(guardada), dict(guardada)

    def test_a_etapa_e_movida_por_um_so(self, monkeypatch):
        sb, pelo_webhook, pelo_job = self._dois_leitores(monkeypatch)

        primeira = tecnologia_sincronizacao.sincronizar_demanda(sb, pelo_webhook)
        segunda = tecnologia_sincronizacao.sincronizar_demanda(sb, pelo_job)

        assert primeira is True
        assert segunda is False, "o segundo leitor achou que ainda era ele quem movia a Etapa"
        assert _demandas(sb)[0]["etapa"] == ETAPA_EM_DESENVOLVIMENTO

    def test_o_detector_da_corrida_nao_e_vacuo(self, monkeypatch):
        """O piso: os dois leitores precisam MESMO chegar com a Etapa antiga na
        mao, senao o teste acima estaria provando "a segunda chamada nao faz
        nada" por outro motivo (foto igual, por exemplo)."""
        _, pelo_webhook, pelo_job = self._dois_leitores(monkeypatch)

        assert pelo_webhook["etapa"] == pelo_job["etapa"] == ETAPA_PLANEJADA
        assert pelo_webhook["github_foto"] is None and pelo_job["github_foto"] is None


class TestOCorpoDaRespostaEOSmokeDoPassoHumano:
    """O corpo do PR manda o operador conferir a instalacao pelo CORPO da
    delivery, e nao pelo 200. Entao o corpo e contrato, e nao enfeite: sem estes
    testes, fixar `sincronizada: true` no caminho de sucesso E no `except` que
    engole a falha ficaria verde, e quem cadastrasse o webhook leria "funcionou"
    sobre uma integracao que falha em toda entrega."""

    def test_evento_ignorado_diz_que_foi_o_evento(self, monkeypatch):
        cliente, _, _ = _montar(monkeypatch=monkeypatch)

        assert _entregar(cliente, _corpo(), evento="push").json() == {"ignorado": "evento"}

    def test_acao_ignorada_diz_que_foi_a_acao(self, monkeypatch):
        cliente, _, _ = _montar(monkeypatch=monkeypatch)

        assert _entregar(cliente, _corpo(acao="milestoned")).json() == {"ignorado": "acao"}

    def test_issue_sem_vinculo_diz_que_nao_ha_vinculo(self, monkeypatch):
        gh = _GithubFalso({999: _issue(999)})
        cliente, _, _ = _montar(demandas=[_demanda("D1", github_issue_numero=673)], github=gh, monkeypatch=monkeypatch)

        assert _entregar(cliente, _corpo(numero=999)).json() == {"ignorado": "sem_vinculo"}

    def test_sincronizada_de_verdade(self, monkeypatch):
        gh = _GithubFalso({673: _issue(673, labels=("in-progress",))})
        cliente, _, _ = _montar(demandas=[_demanda("D1", github_issue_numero=673)], github=gh, monkeypatch=monkeypatch)

        assert _entregar(cliente, _corpo()).json() == {"recebido": True, "sincronizada": True}

    def test_nada_mudou_e_falha_nao_dizem_a_mesma_coisa(self, monkeypatch):
        """O par que faz o smoke valer alguma coisa.

        "Recebi e nao havia novidade" e "recebi e quebrei" sao desfechos
        diferentes, e o operador precisa distinguir os dois na tela do GitHub. Um
        `sincronizada: false` para os dois casos deixaria a falha invisivel
        exatamente na hora em que ele confere o passo humano.
        """
        gh_calmo = _GithubFalso({673: _issue(673, labels=("in-progress",))})
        cliente_calmo, _, _ = _montar(
            demandas=[_ja_sincronizada(gh_calmo, 673)],
            github=gh_calmo,
            monkeypatch=monkeypatch,
        )
        # A entrega calma sai ANTES da segunda montagem: as duas dublam o mesmo
        # `github_client`, e montar as duas primeiro faria o GitHub quebrado
        # atender tambem o cliente calmo.
        sem_novidade = _entregar(cliente_calmo, _corpo()).json()

        gh_quebrado = _GithubFalso({673: _issue(673)}, erro=github_client.GithubIndisponivelError("502"))
        cliente_quebrado, _, _ = _montar(
            demandas=[_demanda("D1", github_issue_numero=673)],
            github=gh_quebrado,
            monkeypatch=monkeypatch,
        )
        com_falha = _entregar(cliente_quebrado, _corpo()).json()

        assert sem_novidade == {"recebido": True, "sincronizada": False}
        assert com_falha == {"recebido": True, "sincronizada": False, "falhou": True}
        assert sem_novidade != com_falha

    def test_issue_apagada_nao_gera_stack_no_log(self, monkeypatch, caplog):
        """Condicao PERMANENTE, e nao indisponibilidade: repetir o traceback a
        cada entrega (e a cada hora, no lote) nao acrescenta nada sobre algo que
        nao se auto-resolve."""
        gh = _GithubFalso({})
        cliente, _, _ = _montar(demandas=[_demanda("D1", github_issue_numero=673)], github=gh, monkeypatch=monkeypatch)

        with caplog.at_level(logging.WARNING, logger="app.routers.webhooks"):
            resposta = _entregar(cliente, _corpo())

        assert resposta.json() == {"recebido": True, "sincronizada": False, "falhou": True}
        assert "não existe mais no repositório" in caplog.text
        assert "Traceback" not in caplog.text


# ─── 4. A reconciliacao de hora em hora ──────────────────────────────────────


class TestReconciliacao:
    def test_le_so_as_vinculadas_ainda_abertas(self, monkeypatch):
        """Vinculada e nao fechada. As tres exclusoes tem causas diferentes e
        estao no mesmo teste porque e a MESMA consulta que erra as tres."""
        gh = _GithubFalso(
            {
                673: _issue(673, labels=("in-progress",)),
                700: _issue(700, labels=("in-progress",)),
                701: _issue(701, labels=("in-progress",)),
            }
        )
        monkeypatch.setattr(github_client, "ler_issue", gh.ler_issue)
        monkeypatch.setattr(github_client, "ler_sub_issues", gh.ler_sub_issues)
        sb = _SupabaseMock(
            {
                "tecnologia_demandas": [
                    _demanda("D1", github_issue_numero=673, estado="em_andamento"),
                    _demanda("D2", github_issue_numero=None, estado="em_andamento"),
                    _demanda("D3", github_issue_numero=700, estado="concluida"),
                    _demanda("D4", github_issue_numero=701, estado="cancelada"),
                ],
                "tecnologia_conversas": [],
            }
        )

        contagem = tecnologia_sincronizacao.reconciliar_vinculos(sb)

        assert gh.leituras == [673]
        assert contagem["lidas"] == 1
        assert contagem["mudadas"] == 1
        assert [d["id"] for d in _demandas(sb) if d["etapa"] == ETAPA_EM_DESENVOLVIMENTO] == ["D1"]

    def test_aguardando_entra_no_lote(self, monkeypatch):
        """`aguardando` e o estado em que a Demanda cai quando a Entrega a
        devolve (fatia #679). Deixa-la de fora congelaria justo o card que espera
        o desfecho."""
        gh = _GithubFalso({673: _issue(673, estado="closed", motivo="completed")})
        monkeypatch.setattr(github_client, "ler_issue", gh.ler_issue)
        monkeypatch.setattr(github_client, "ler_sub_issues", gh.ler_sub_issues)
        sb = _SupabaseMock(
            {
                "tecnologia_demandas": [_demanda("D1", github_issue_numero=673, estado="aguardando")],
                "tecnologia_conversas": [],
            }
        )

        tecnologia_sincronizacao.reconciliar_vinculos(sb)

        assert sb.tabelas["tecnologia_demandas"][0]["etapa"] == ETAPA_ENTREGUE

    def test_os_estados_do_lote_sao_o_complemento_dos_fechados(self):
        """O piso da consulta acima: um estado novo que nao entrasse em nenhuma
        das duas listas sumiria da reconciliacao em silencio.

        A asserção e de UNIAO sobre os cinco estados do CHECK da migration 102,
        e nao a igualdade com
        `ESTADOS_ABERTOS`: essa seria tautologia, porque
        `ESTADOS_DA_RECONCILIACAO` e um alias dele, e um estado novo passaria
        batido justamente aqui.
        """
        do_lote = set(tecnologia_sincronizacao.ESTADOS_DA_RECONCILIACAO)

        assert do_lote & set(ESTADOS_FECHADOS) == set()
        assert do_lote | set(ESTADOS_FECHADOS) == {"nova", "em_andamento", "aguardando", "concluida", "cancelada"}

    def test_uma_falha_nao_derruba_o_lote(self, monkeypatch):
        """Criterio de aceite. A falha e no UPDATE da segunda Demanda, e nao no
        GitHub: o lote precisa seguir por qualquer causa, e o `except` que so
        pegasse erro do GitHub deixaria o timeout do PostgREST passar cru."""
        gh = _GithubFalso(
            {
                673: _issue(673, labels=("in-progress",)),
                678: _issue(678, labels=("in-progress",)),
                679: _issue(679, labels=("in-progress",)),
            }
        )
        monkeypatch.setattr(github_client, "ler_issue", gh.ler_issue)
        monkeypatch.setattr(github_client, "ler_sub_issues", gh.ler_sub_issues)
        sb = _SupabaseMock(
            {
                "tecnologia_demandas": [
                    _demanda("D1", github_issue_numero=673),
                    _demanda("D2", github_issue_numero=678),
                    _demanda("D3", github_issue_numero=679),
                ],
                "tecnologia_conversas": [],
            },
            falhas={"D2": RuntimeError("PostgREST fora do ar")},
        )

        contagem = tecnologia_sincronizacao.reconciliar_vinculos(sb)

        assert contagem == {"lidas": 3, "mudadas": 2, "falhas": 1}
        assert [d["etapa"] for d in sb.tabelas["tecnologia_demandas"]] == [
            ETAPA_EM_DESENVOLVIMENTO,
            ETAPA_EM_ANALISE,
            ETAPA_EM_DESENVOLVIMENTO,
        ]

    def test_uma_falha_do_github_tambem_nao_derruba_o_lote(self, monkeypatch):
        chamadas: list[int] = []

        def _ler(numero: int) -> dict:
            chamadas.append(numero)
            if numero == 678:
                raise github_client.GithubIndisponivelError("502")
            return _issue(numero, labels=("in-progress",))

        monkeypatch.setattr(github_client, "ler_issue", _ler)
        monkeypatch.setattr(github_client, "ler_sub_issues", lambda numero: [])
        sb = _SupabaseMock(
            {
                "tecnologia_demandas": [
                    _demanda("D1", github_issue_numero=673),
                    _demanda("D2", github_issue_numero=678),
                    _demanda("D3", github_issue_numero=679),
                ],
                "tecnologia_conversas": [],
            }
        )

        contagem = tecnologia_sincronizacao.reconciliar_vinculos(sb)

        assert chamadas == [673, 678, 679]
        assert contagem == {"lidas": 3, "mudadas": 2, "falhas": 1}

    def test_o_log_diz_quantas_mudaram(self, monkeypatch, caplog):
        gh = _GithubFalso({673: _issue(673, labels=("in-progress",)), 678: _issue(678)})
        monkeypatch.setattr(github_client, "ler_issue", gh.ler_issue)
        monkeypatch.setattr(github_client, "ler_sub_issues", gh.ler_sub_issues)
        sb = _SupabaseMock(
            {
                "tecnologia_demandas": [
                    _demanda("D1", github_issue_numero=673),
                    _ja_sincronizada(gh, 678, did="D2"),
                ],
                "tecnologia_conversas": [],
            }
        )

        with caplog.at_level(logging.INFO, logger="app.services.tecnologia_sincronizacao"):
            tecnologia_sincronizacao.reconciliar_vinculos(sb)

        assert "2 lida(s)" in caplog.text
        assert "1 mudada(s)" in caplog.text

    def test_issue_apagada_conta_como_falha_sem_stack(self, monkeypatch, caplog):
        """Condicao PERMANENTE tratada como as outras falhas viraria um traceback
        inteiro por HORA, para sempre, sobre algo que nao se auto-resolve: quem
        for consertar desfaz o Vinculo na tela."""
        gh = _GithubFalso({673: _issue(673, labels=("in-progress",))})
        monkeypatch.setattr(github_client, "ler_issue", gh.ler_issue)
        monkeypatch.setattr(github_client, "ler_sub_issues", gh.ler_sub_issues)
        sb = _SupabaseMock(
            {
                "tecnologia_demandas": [
                    _demanda("D1", github_issue_numero=673),
                    _demanda("D2", github_issue_numero=404),
                ],
                "tecnologia_conversas": [],
            }
        )

        with caplog.at_level(logging.WARNING, logger="app.services.tecnologia_sincronizacao"):
            contagem = tecnologia_sincronizacao.reconciliar_vinculos(sb)

        assert contagem == {"lidas": 2, "mudadas": 1, "falhas": 1}
        assert "não existe mais no repositório" in caplog.text
        assert "Traceback" not in caplog.text

    def test_falha_de_verdade_continua_com_stack(self, monkeypatch, caplog):
        """O par do teste acima: tirar o `exc_info` de TODAS as falhas apagaria a
        unica pista das que sao mesmo defeito."""
        monkeypatch.setattr(github_client, "ler_issue", lambda numero: _issue(numero, labels=("in-progress",)))
        monkeypatch.setattr(github_client, "ler_sub_issues", lambda numero: [])
        sb = _SupabaseMock(
            {"tecnologia_demandas": [_demanda("D1", github_issue_numero=673)], "tecnologia_conversas": []},
            falhas={"D1": RuntimeError("PostgREST fora do ar")},
        )

        with caplog.at_level(logging.WARNING, logger="app.services.tecnologia_sincronizacao"):
            tecnologia_sincronizacao.reconciliar_vinculos(sb)

        assert "Traceback" in caplog.text

    def test_sem_demanda_vinculada_o_lote_nao_le_o_github(self, monkeypatch):
        sb = _SupabaseMock(
            {"tecnologia_demandas": [_demanda("D1", github_issue_numero=None)], "tecnologia_conversas": []}
        )

        contagem = tecnologia_sincronizacao.reconciliar_vinculos(sb)

        assert contagem == {"lidas": 0, "mudadas": 0, "falhas": 0}


class TestJobNoScheduler:
    def _registrados(self, monkeypatch) -> list[tuple]:
        registrados: list[tuple] = []

        def _add_job(func, gatilho=None, **kw):
            registrados.append((func, gatilho, kw))

        monkeypatch.setattr(scheduler_mod.scheduler, "add_job", _add_job)
        monkeypatch.setattr(scheduler_mod.scheduler, "start", lambda: None)
        scheduler_mod.start_scheduler()
        return registrados

    def test_o_job_esta_registrado_de_hora_em_hora_com_id_proprio(self, monkeypatch):
        registrados = self._registrados(monkeypatch)

        meus = [r for r in registrados if r[2].get("id") == "reconciliacao_tecnologia"]

        assert len(meus) == 1, "o job da reconciliacao do Vinculo nao esta no scheduler"
        func, gatilho, kw = meus[0]
        assert gatilho == "interval"
        assert kw["hours"] == 1
        assert func is scheduler_mod.reconciliar_vinculos_tecnologia

    def test_o_id_do_job_nao_colide_com_os_que_ja_existiam(self, monkeypatch):
        ids = [r[2].get("id") for r in self._registrados(monkeypatch)]

        assert len(ids) == len(set(ids)), "dois jobs com o mesmo id: o `replace_existing` apagaria um deles"

    def test_o_job_chama_a_rotina_de_verdade(self, monkeypatch):
        """O par do teste acima: registrar uma funcao vazia passaria por ele. O
        que este cobra e que a funcao registrada leve o cliente do banco ate a
        reconciliacao."""
        sb = object()
        chamadas: list = []
        monkeypatch.setattr(scheduler_mod, "_supabase", lambda: sb)
        monkeypatch.setattr(
            tecnologia_sincronizacao,
            "reconciliar_vinculos",
            lambda cliente: chamadas.append(cliente) or {"lidas": 0, "mudadas": 0, "falhas": 0},
        )

        scheduler_mod.reconciliar_vinculos_tecnologia()

        assert chamadas == [sb]

    def test_falha_no_job_nao_sobe_para_o_scheduler(self, monkeypatch):
        """Excecao que escapa de um job derruba a execucao dele no APScheduler e
        polui o log com stack de biblioteca. O job registra e engole."""
        monkeypatch.setattr(scheduler_mod, "_supabase", lambda: (_ for _ in ()).throw(RuntimeError("banco fora")))

        scheduler_mod.reconciliar_vinculos_tecnologia()


# ─── 6. A Entrega devolve a Demanda a quem pediu (issue #679) ────────────────


def _entregue(numero: int = 673) -> dict:
    """A issue fechada como concluida, que e o que leva a Etapa a Entregue."""
    return _issue(numero, estado="closed", motivo="completed")


def _pessoa(pid: str = "P1", nome: str | None = "Diretor Geral", **campos) -> dict:
    """Quem ve a aba: ativo e Super admin (`e_pessoa_da_aba`).

    Super admin pelo Perfil de acesso, e nao so pela flag legada: desde a issue
    #752 o perfil nulo com a flag ligada e "sem papel" e fica fora da aba.
    """
    return {
        "id": pid,
        "nome_completo": nome,
        "ativo": True,
        "is_super_admin": True,
        "access_profile": "super_admin",
        **campos,
    }


# ─── 7. O PR que fecha a raiz (issue #1064, ADR 0069, decisao 6) ─────────────


def _corpo_pr(
    numero_pr: int = 1100,
    acao: str = "opened",
    *,
    fecha: str | None = "Closes #673",
    merged: bool = False,
    repo: str = REPO,
) -> bytes:
    """O corpo CRU de um evento `pull_request`, com o corpo do PR dentro.

    As issues que o PR fecha saem do corpo dele, pelas palavras de fechamento
    do GitHub (`Closes #N`), que e como o `/ship` escreve todo PR.
    """
    payload = {
        "action": acao,
        "number": numero_pr,
        "pull_request": {"number": numero_pr, "body": fecha, "merged": merged},
        "repository": {"full_name": repo},
    }
    return json.dumps(payload, indent=2).encode("utf-8")


class TestOPrQueFechaARaiz:
    def test_pr_aberto_que_fecha_a_raiz_vira_em_desenvolvimento_sem_label(self, monkeypatch):
        """Criterio de aceite: ninguem pos `in-progress`, e o PR aberto basta."""
        gh = _GithubFalso({673: _issue(673)})
        cliente, sb, _ = _montar(
            demandas=[_ja_sincronizada(gh, 673, etapa=ETAPA_PLANEJADA)],
            github=gh,
            monkeypatch=monkeypatch,
        )

        resposta = _entregar(cliente, _corpo_pr(), evento="pull_request")

        assert resposta.status_code == 200
        assert resposta.json() == {"recebido": True, "sincronizada": True}
        demanda = _demandas(sb)[0]
        assert demanda["etapa"] == ETAPA_EM_DESENVOLVIMENTO
        assert demanda["github_foto"]["prs_abertos"] == [1100]

    def test_pr_fechado_sem_merge_limpa_o_fato_e_a_etapa_volta_as_labels(self, monkeypatch):
        """Criterio de aceite: o PR some, e quem manda de novo e a label."""
        gh = _GithubFalso({673: _issue(673, labels=("ready-for-agent",))})
        cliente, sb, _ = _montar(demandas=[_ja_sincronizada(gh, 673)], github=gh, monkeypatch=monkeypatch)

        _entregar(cliente, _corpo_pr(), evento="pull_request")
        assert _demandas(sb)[0]["etapa"] == ETAPA_EM_DESENVOLVIMENTO, "o piso: o PR aberto valeu"

        resposta = _entregar(cliente, _corpo_pr(acao="closed", merged=False), evento="pull_request")

        assert resposta.status_code == 200
        demanda = _demandas(sb)[0]
        assert demanda["etapa"] == ETAPA_PLANEJADA
        assert "prs_abertos" not in demanda["github_foto"]
        assert "fechada_por_pr" not in demanda["github_foto"]

    def test_fechar_um_pr_sem_merge_nao_apaga_o_outro_pr_aberto(self, monkeypatch):
        gh = _GithubFalso({673: _issue(673)})
        cliente, sb, _ = _montar(demandas=[_ja_sincronizada(gh, 673)], github=gh, monkeypatch=monkeypatch)

        _entregar(cliente, _corpo_pr(1100), evento="pull_request")
        _entregar(cliente, _corpo_pr(1101), evento="pull_request")
        _entregar(cliente, _corpo_pr(1100, acao="closed"), evento="pull_request")

        demanda = _demandas(sb)[0]
        assert demanda["github_foto"]["prs_abertos"] == [1101]
        assert demanda["etapa"] == ETAPA_EM_DESENVOLVIMENTO

    def test_pr_mergeado_grava_fechada_por_pr_na_foto(self, monkeypatch):
        """Criterio de aceite: e o fato que a fatia do deploy le para decidir o
        gatilho da devolucao."""
        gh = _GithubFalso({673: _issue(673)})
        cliente, sb, _ = _montar(demandas=[_ja_sincronizada(gh, 673)], github=gh, monkeypatch=monkeypatch)
        _entregar(cliente, _corpo_pr(), evento="pull_request")
        gh.issues[673] = _issue(673, estado="closed", motivo="completed")

        resposta = _entregar(cliente, _corpo_pr(acao="closed", merged=True), evento="pull_request")

        assert resposta.status_code == 200
        foto = _demandas(sb)[0]["github_foto"]
        assert foto["fechada_por_pr"] == 1100
        assert "prs_abertos" not in foto
        assert _demandas(sb)[0]["etapa"] == ETAPA_ENTREGUE

    def test_o_evento_issues_seguinte_nao_apaga_os_fatos_do_pr(self, monkeypatch):
        """A issue relida nao fala de PR: uma label posta depois do PR aberto
        regravaria a foto sem o fato, e o card voltaria para tras."""
        gh = _GithubFalso({673: _issue(673)})
        cliente, sb, _ = _montar(demandas=[_ja_sincronizada(gh, 673)], github=gh, monkeypatch=monkeypatch)
        _entregar(cliente, _corpo_pr(), evento="pull_request")
        gh.issues[673] = _issue(673, labels=("ready-for-agent",))

        _entregar(cliente, _corpo(acao="labeled"))

        demanda = _demandas(sb)[0]
        assert demanda["github_foto"]["prs_abertos"] == [1100]
        assert demanda["github_foto"]["labels"] == ["ready-for-agent"]
        assert demanda["etapa"] == ETAPA_EM_DESENVOLVIMENTO

    @pytest.mark.parametrize(
        "fecha",
        (None, "Sem referencia nenhuma", "Closes #999", "Refs #673", "Closes outra-pessoa/hospital-reunioes#673"),
        ids=("sem_corpo", "sem_palavra", "issue_sem_demanda", "so_menciona", "outro_repositorio"),
    )
    def test_pr_que_nao_fecha_demanda_vinculada_e_ignorado_com_2xx(self, fecha, monkeypatch):
        """Criterio de aceite: o PR de ferramenta, o de outra aba e o que so
        menciona a issue sem fecha-la nao tocam na Demanda nem gastam cota."""
        gh = _GithubFalso({673: _issue(673), 999: _issue(999)})
        cliente, sb, _ = _montar(demandas=[_ja_sincronizada(gh, 673)], github=gh, monkeypatch=monkeypatch)

        resposta = _entregar(cliente, _corpo_pr(fecha=fecha), evento="pull_request")

        assert resposta.status_code == 200
        assert resposta.json() == {"ignorado": "sem_vinculo"}
        assert gh.leituras == []
        assert _fio(sb) == []
        assert _demandas(sb)[0]["github_sincronizado_em"] == CARIMBO_ANTERIOR

    @pytest.mark.parametrize("acao", ("edited", "synchronize", "labeled", "assigned"))
    def test_acao_de_pr_fora_da_lista_nao_faz_nada(self, acao, monkeypatch):
        gh = _GithubFalso({673: _issue(673)})
        cliente, _, _ = _montar(demandas=[_ja_sincronizada(gh, 673)], github=gh, monkeypatch=monkeypatch)

        resposta = _entregar(cliente, _corpo_pr(acao=acao), evento="pull_request")

        assert resposta.json() == {"ignorado": "acao"}
        assert gh.leituras == []

    def test_pr_de_outro_repositorio_e_ignorado(self, monkeypatch):
        gh = _GithubFalso({673: _issue(673)})
        cliente, _, _ = _montar(demandas=[_ja_sincronizada(gh, 673)], github=gh, monkeypatch=monkeypatch)

        resposta = _entregar(cliente, _corpo_pr(repo="outra-pessoa/hospital-reunioes"), evento="pull_request")

        assert resposta.json() == {"ignorado": "outro_repositorio"}
        assert gh.leituras == []

    @pytest.mark.parametrize(
        "assinatura",
        (None, "sha256=" + "0" * 64, "outro-segredo"),
        ids=("sem_assinatura", "assinatura_errada", "outro_segredo"),
    )
    def test_pull_request_sem_assinatura_valida_e_recusado(self, assinatura, monkeypatch):
        """Criterio de aceite: o HMAC continua obrigatorio, e a recusa vem antes
        de qualquer leitura ou escrita."""
        gh = _GithubFalso({673: _issue(673)})
        cliente, sb, _ = _montar(
            demandas=[_ja_sincronizada(gh, 673, etapa=ETAPA_PLANEJADA)], github=gh, monkeypatch=monkeypatch
        )
        corpo = _corpo_pr()
        if assinatura == "outro-segredo":
            assinatura = _assinar(corpo, segredo="outro-segredo")

        resposta = _entregar(cliente, corpo, evento="pull_request", assinatura=assinatura)

        assert resposta.status_code == 401
        assert gh.leituras == []
        assert _fio(sb) == []
        assert _demandas(sb)[0]["etapa"] == ETAPA_PLANEJADA


class TestOMergeChegaJuntoComOFechamentoDaIssue:
    """O merge de um PR com `Closes #N` manda `pull_request.closed` e
    `issues.closed` quase no mesmo segundo, e cada handler le a Demanda ANTES
    das duas chamadas ao GitHub. O evento `issues` parte da foto que leu, sem
    `fechada_por_pr`, e o GitHub nao reentrega o `pull_request`: se a escrita
    do `issues` apagar o fato, ninguem o devolve (a reconciliacao so le PR
    aberto).

    A corrida e encenada como a da Etapa acima: as duas leituras antes de
    qualquer escrita, e as escritas uma depois da outra, nas duas ordens.
    """

    def _dois_leitores(self, monkeypatch, issue: dict, etapa: str):
        gh = _GithubFalso({673: _issue(673)})
        foto = {**_foto_guardada(gh, 673), "prs_abertos": [1100]}
        gh.issues[673] = issue
        monkeypatch.setattr(github_client, "ler_issue", gh.ler_issue)
        monkeypatch.setattr(github_client, "ler_sub_issues", gh.ler_sub_issues)
        sb = _SupabaseMock(
            {
                "tecnologia_demandas": [_demanda("D1", github_issue_numero=673, etapa=etapa, github_foto=foto)],
                "tecnologia_conversas": [],
            }
        )
        guardada = sb.tabelas["tecnologia_demandas"][0]
        return sb, dict(guardada), dict(guardada)

    def _merge(self, sb, demanda):
        return tecnologia_sincronizacao.sincronizar_pelo_pr(sb, demanda, pr=1100, acao="closed", mergeado=True)

    def test_issues_escrevendo_depois_do_merge_nao_apaga_o_fato_sem_mudar_a_etapa(self, monkeypatch):
        """A Etapa nao muda nos dois (a label `in-progress` segura Em
        desenvolvimento), entao nenhum UPDATE leva a trava da Etapa: o ultimo a
        escrever ganhava, e era o `issues`, com a foto velha."""
        sb, pelo_pr, pelo_issues = self._dois_leitores(
            monkeypatch, _issue(673, labels=("in-progress",)), ETAPA_EM_DESENVOLVIMENTO
        )

        self._merge(sb, pelo_pr)
        tecnologia_sincronizacao.sincronizar_demanda(sb, pelo_issues)

        foto = _demandas(sb)[0]["github_foto"]
        assert foto.get("fechada_por_pr") == 1100, "o evento issues apagou o fato que o merge gravou"
        assert "prs_abertos" not in foto

    def test_merge_escrevendo_depois_do_issues_que_moveu_a_etapa_grava_o_fato(self, monkeypatch):
        """A Etapa vai de Em desenvolvimento a Entregue nos dois. O `issues`
        ganha a trava da Etapa, e o PR, que perdia e saia sem escrever, levava
        o `fechada_por_pr` junto."""
        sb, pelo_pr, pelo_issues = self._dois_leitores(monkeypatch, _entregue(), ETAPA_EM_DESENVOLVIMENTO)

        tecnologia_sincronizacao.sincronizar_demanda(sb, pelo_issues)
        self._merge(sb, pelo_pr)

        demanda = _demandas(sb)[0]
        assert demanda["github_foto"].get("fechada_por_pr") == 1100, "o merge perdeu a corrida e o fato junto"
        assert "prs_abertos" not in demanda["github_foto"]
        assert demanda["etapa"] == ETAPA_ENTREGUE
        assert _demandas(sb)[0]["etapa"] == ETAPA_ENTREGUE

    def test_merge_escrevendo_antes_do_issues_que_moveria_a_etapa_mantem_o_fato(self, monkeypatch):
        sb, pelo_pr, pelo_issues = self._dois_leitores(monkeypatch, _entregue(), ETAPA_EM_DESENVOLVIMENTO)

        self._merge(sb, pelo_pr)
        tecnologia_sincronizacao.sincronizar_demanda(sb, pelo_issues)

        demanda = _demandas(sb)[0]
        assert demanda["github_foto"].get("fechada_por_pr") == 1100
        assert "prs_abertos" not in demanda["github_foto"]
        assert _demandas(sb)[0]["etapa"] == ETAPA_ENTREGUE

    def test_o_detector_da_corrida_nao_e_vacuo(self, monkeypatch):
        """O piso: o leitor do `issues` chega MESMO com a foto sem o fato e com
        o PR ainda aberto, que e o que a escrita dele regravaria."""
        _, _, pelo_issues = self._dois_leitores(monkeypatch, _entregue(), ETAPA_EM_DESENVOLVIMENTO)

        assert pelo_issues["github_foto"]["prs_abertos"] == [1100]
        assert "fechada_por_pr" not in pelo_issues["github_foto"]


class TestIssuesQueOCorpoFecha:
    @pytest.mark.parametrize(
        ("corpo", "esperado"),
        (
            ("Closes #673", [673]),
            ("closes #673\n\nfixes: #674", [673, 674]),
            ("Resolved pedrorezendefig/hospital-reunioes#673", [673]),
            ("Closes #1, #2", [1]),
            ("Close #10 e close #10 de novo", [10]),
            ("Foreclose #673", []),
            ("#673 fechado", []),
        ),
    )
    def test_as_palavras_de_fechamento_do_github(self, corpo, esperado):
        assert github_client.issues_que_o_corpo_fecha(corpo) == esperado

    def test_a_leitura_dos_prs_abertos_traz_as_issues_que_cada_um_fecha(self, monkeypatch):
        """O cliente de verdade, com o transporte dublado: o caminho pedido e
        o dos PRs ABERTOS, e cada PR sai com as issues que o corpo dele fecha."""
        monkeypatch.setattr(settings, "github_integracao_token", "token-falso")
        pedidos: list[str] = []

        def _transporte(metodo, url, **_kw):
            pedidos.append(f"{metodo} {url}")
            corpo = [{"number": 1100, "body": "Closes #673"}, {"number": 1101, "body": None}]
            return httpx.Response(200, json=corpo)

        monkeypatch.setattr(github_client.httpx, "request", _transporte)

        prs = _LER_PRS_ABERTOS_DE_VERDADE()

        assert pedidos == [f"GET https://api.github.com/repos/{REPO}/pulls?state=open&per_page=100"]
        assert prs == [{"numero": 1100, "fecha": [673]}, {"numero": 1101, "fecha": []}]


class TestAReconciliacaoRecuperaOPrAberto:
    def _lote(self, monkeypatch, gh: _GithubFalso, demanda: dict, ler_prs_abertos) -> _SupabaseMock:
        monkeypatch.setattr(github_client, "ler_issue", gh.ler_issue)
        monkeypatch.setattr(github_client, "ler_sub_issues", gh.ler_sub_issues)
        monkeypatch.setattr(github_client, "ler_prs_abertos", ler_prs_abertos)
        return _SupabaseMock({"tecnologia_demandas": [demanda], "tecnologia_conversas": []})

    def test_o_pr_aberto_que_o_webhook_perdeu_entra_na_passagem_de_hora_em_hora(self, monkeypatch):
        """Criterio de aceite: o webhook do PR nao chegou, a issue segue sem
        label, e a passagem de hora em hora le os PRs abertos pelo cliente."""
        gh = _GithubFalso({673: _issue(673)})
        sb = self._lote(
            monkeypatch,
            gh,
            _ja_sincronizada(gh, 673, etapa=ETAPA_PLANEJADA),
            lambda: [{"numero": 1100, "fecha": [673]}, {"numero": 1101, "fecha": [999]}],
        )

        contagem = tecnologia_sincronizacao.reconciliar_vinculos(sb)

        demanda = _demandas(sb)[0]
        assert contagem["mudadas"] == 1
        assert demanda["etapa"] == ETAPA_EM_DESENVOLVIMENTO
        assert demanda["github_foto"]["prs_abertos"] == [1100]

    def test_o_pr_que_fechou_sem_o_webhook_sai_da_foto(self, monkeypatch):
        gh = _GithubFalso({673: _issue(673, labels=("ready-for-agent",))})
        foto = {**_foto_guardada(gh, 673), "prs_abertos": [1100]}
        demanda = _demanda("D1", github_issue_numero=673, etapa=ETAPA_EM_DESENVOLVIMENTO, github_foto=foto)
        sb = self._lote(monkeypatch, gh, demanda, lambda: [])

        tecnologia_sincronizacao.reconciliar_vinculos(sb)

        assert _demandas(sb)[0]["etapa"] == ETAPA_PLANEJADA
        assert "prs_abertos" not in _demandas(sb)[0]["github_foto"]

    def test_falha_ao_ler_os_prs_nao_derruba_o_lote_nem_apaga_o_fato(self, monkeypatch):
        """Sem a lista de PRs, "nao sei" nao pode virar "nao ha PR aberto": o
        lote segue com o fato que a foto ja tinha."""
        gh = _GithubFalso({673: _issue(673, labels=("ready-for-agent",))})
        foto = {**_foto_guardada(gh, 673), "prs_abertos": [1100]}
        demanda = _demanda("D1", github_issue_numero=673, etapa=ETAPA_PLANEJADA, github_foto=foto)

        def _fora_do_ar():
            raise github_client.GithubIndisponivelError("timeout")

        sb = self._lote(monkeypatch, gh, demanda, _fora_do_ar)

        contagem = tecnologia_sincronizacao.reconciliar_vinculos(sb)

        assert contagem["falhas"] == 0
        assert _demandas(sb)[0]["etapa"] == ETAPA_EM_DESENVOLVIMENTO
        assert _demandas(sb)[0]["github_foto"]["prs_abertos"] == [1100]
