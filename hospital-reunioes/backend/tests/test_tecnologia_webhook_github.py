"""O webhook do GitHub e a reconciliacao de hora em hora (issue #678, PRD #673).

Tres seams, e cada um existe porque o anterior nao alcanca o proximo:

* **A porta**, pela ROTA de verdade com `TestClient`. A assinatura HMAC so e
  provavel aqui: chamar a funcao de conferencia direto deixaria de fora a
  pergunta que importa, que e se a ROTA a chama antes de mexer no banco. Todo
  teste de recusa desta secao termina olhando o banco: 401 que grava e 401 que
  nao serve para nada.
* **A sincronizacao**, tambem pela rota, com o cliente do GitHub dublado. E ela
  que decide se a linha entra no fio do diretor, e a guarda da foto igual e
  criterio de aceite: a entrega repetida do GitHub nao pode virar duas linhas.
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
from app.services.tecnologia import (  # noqa: E402
    AUTOR_DA_ENTREGA,
    ESTADOS,
    ESTADOS_ABERTOS,
    ESTADOS_FECHADOS,
    RECADO_DA_ENTREGA,
    SEM_EFEITO,
    EfeitoDaEtapa,
    efeito_da_etapa,
)
from app.services.tecnologia_vinculo import (  # noqa: E402
    ETAPA_EM_ANALISE,
    ETAPA_EM_DESENVOLVIMENTO,
    ETAPA_ENTREGUE,
    ETAPA_NAO_SERA_FEITA,
    ETAPA_PLANEJADA,
    ETAPAS,
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


@pytest.fixture(autouse=True)
def _sem_email_de_verdade(monkeypatch):
    """Nenhum teste deste arquivo manda e-mail, e todos podem tentar.

    Desde a issue #679 a sincronizacao chama o aviso de atribuicao quando a
    Entrega devolve o card, e o `.env` que os testes carregam tem credencial de
    verdade. A troca e AUTOUSE por isso: um caso novo que caia na devolucao sem
    lembrar do dublê tentaria falar com o provedor.

    Devolve a lista dos avisos pedidos, que e o que os testes da devolucao
    asseguram.
    """
    enviados: list[dict] = []

    def _registrar(supabase, **argumentos):
        enviados.append(argumentos)
        return True

    monkeypatch.setattr(tecnologia_sincronizacao, "avisar_atribuicao", _registrar)
    return enviados


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
    @pytest.mark.parametrize("evento", ("issue_comment", "push", "pull_request", "ping"))
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
    @pytest.mark.parametrize("acao", ("labeled", "unlabeled", "closed", "reopened", "edited"))
    def test_a_acao_da_lista_sincroniza(self, acao, monkeypatch):
        gh = _GithubFalso({673: _issue(673, labels=("in-progress",))})
        cliente, sb, _ = _montar(demandas=[_demanda("D1", github_issue_numero=673)], github=gh, monkeypatch=monkeypatch)

        resposta = _entregar(cliente, _corpo(acao=acao))

        assert resposta.status_code == 200
        assert _demandas(sb)[0]["etapa"] == ETAPA_EM_DESENVOLVIMENTO

    @pytest.mark.parametrize("acao", ("assigned", "unassigned", "milestoned", "opened", "deleted"))
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
    def test_a_etapa_e_a_linha_do_fio_mudam_juntas(self, monkeypatch):
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
        assert [linha["texto"] for linha in _fio(sb)] == ["Etapa: Em desenvolvimento"]
        assert _fio(sb)[0]["movimento_campo"] == "etapa"
        assert _fio(sb)[0]["movimento_de"] == ETAPA_PLANEJADA
        assert _fio(sb)[0]["movimento_para"] == ETAPA_EM_DESENVOLVIMENTO
        assert _fio(sb)[0]["autor_id"] is None, "ninguem AGIU no app: quem mudou foi o GitHub"

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
        assert [linha["texto"] for linha in _fio(sb)] == ["Etapa: Em desenvolvimento (3 de 7 partes)"]

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

    def test_a_entrega_repetida_nao_duplica_a_linha(self, monkeypatch):
        """O GitHub reentrega, e a mesma entrega duas vezes nao pode virar duas
        linhas no fio. A guarda e a foto, e nao o id da entrega: quem chega pela
        reconciliacao nao tem id de entrega nenhum e precisa da mesma protecao."""
        gh = _GithubFalso({673: _issue(673, labels=("in-progress",))})
        cliente, sb, _ = _montar(demandas=[_demanda("D1", github_issue_numero=673)], github=gh, monkeypatch=monkeypatch)
        corpo = _corpo()

        primeira = _entregar(cliente, corpo)
        segunda = _entregar(cliente, corpo)

        assert (primeira.status_code, segunda.status_code) == (200, 200)
        assert len(_fio(sb)) == 1

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
        hoje, e o fio ganha a linha, na primeira sincronizacao depois da
        mudanca."""
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
        assert [linha["texto"] for linha in _fio(sb)] == ["Etapa: Em desenvolvimento"]

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
    um e o `insert` do outro ha uma janela sem trava, e os dois leriam a mesma
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

    def test_a_linha_da_etapa_nao_sai_duas_vezes(self, monkeypatch):
        sb, pelo_webhook, pelo_job = self._dois_leitores(monkeypatch)

        primeira = tecnologia_sincronizacao.sincronizar_demanda(sb, pelo_webhook)
        segunda = tecnologia_sincronizacao.sincronizar_demanda(sb, pelo_job)

        assert primeira is True
        assert segunda is False, "o segundo leitor achou que ainda era ele quem movia a Etapa"
        assert [linha["texto"] for linha in _fio(sb)] == ["Etapa: Em desenvolvimento"]
        assert _demandas(sb)[0]["etapa"] == ETAPA_EM_DESENVOLVIMENTO

    def test_quem_perde_a_corrida_deixa_rastro(self, monkeypatch, caplog):
        """Silencio aqui seria indistinguivel de "nada mudou", e quem for
        investigar uma linha faltando no fio precisa achar o motivo."""
        sb, pelo_webhook, pelo_job = self._dois_leitores(monkeypatch)
        tecnologia_sincronizacao.sincronizar_demanda(sb, pelo_webhook)

        with caplog.at_level(logging.INFO, logger="app.services.tecnologia_sincronizacao"):
            tecnologia_sincronizacao.sincronizar_demanda(sb, pelo_job)

        assert "já tinha sido movida" in caplog.text

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

        assert _entregar(cliente, _corpo(acao="assigned")).json() == {"ignorado": "acao"}

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
        assert [linha["demanda_id"] for linha in _fio(sb)] == ["D1"]

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

        A asserção e de UNIAO sobre `ESTADOS`, e nao a igualdade com
        `ESTADOS_ABERTOS`: essa seria tautologia, porque
        `ESTADOS_DA_RECONCILIACAO` e um alias dele, e um estado novo passaria
        batido justamente aqui.
        """
        do_lote = set(tecnologia_sincronizacao.ESTADOS_DA_RECONCILIACAO)

        assert do_lote & set(ESTADOS_FECHADOS) == set()
        assert do_lote | set(ESTADOS_FECHADOS) == set(ESTADOS)

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


class TestEfeitoDaEtapa:
    """A regra pura da devolucao, direto e sem duble.

    Ela mora com a sincronizacao porque e ela que a devolucao serve, e nao o
    Quadro: esta e a UNICA regra automatica de movimento do app (ADR 0054,
    decisao 6). O que se prova aqui e a tabela inteira, inclusive o que NAO
    acontece; a costura com o banco e provada logo abaixo, pela rota.
    """

    @pytest.mark.parametrize("estado", ESTADOS_ABERTOS)
    def test_entregue_devolve_o_card_ao_autor(self, estado):
        demanda = {"estado": estado, "autor_id": "P1", "responsavel_id": "P2"}

        efeito = efeito_da_etapa(demanda, etapa_nova=ETAPA_ENTREGUE)

        assert efeito.atribuir_a == "P1"
        assert efeito.mover_para == (None if estado == "aguardando" else "aguardando")

    def test_o_autor_que_ja_e_o_responsavel_nao_e_atribuido_de_novo(self):
        """Criterio de aceite: nao se atribui a Demanda a quem ja a tem na mao,
        e por isso nao sai e-mail dizendo "a Demanda e sua" para essa pessoa."""
        demanda = {"estado": "em_andamento", "autor_id": "P1", "responsavel_id": "P1"}

        assert efeito_da_etapa(demanda, etapa_nova=ETAPA_ENTREGUE) == EfeitoDaEtapa(mover_para="aguardando")

    def test_card_ja_em_aguardando_com_o_autor_nao_tem_o_que_fazer(self):
        demanda = {"estado": "aguardando", "autor_id": "P1", "responsavel_id": "P1"}

        assert efeito_da_etapa(demanda, etapa_nova=ETAPA_ENTREGUE) == SEM_EFEITO

    @pytest.mark.parametrize("estado", ESTADOS_FECHADOS)
    def test_demanda_fechada_nao_e_reaberta_pela_entrega(self, estado):
        """Criterio de aceite (historia 28): a Entrega nao mexe no que alguem
        fechou a mao."""
        demanda = {"estado": estado, "autor_id": "P1", "responsavel_id": "P2"}

        assert efeito_da_etapa(demanda, etapa_nova=ETAPA_ENTREGUE) == SEM_EFEITO

    def test_estado_que_o_quadro_nao_conhece_nao_move(self):
        """A lista consultada e a POSITIVA. Escrita ao contrario ("tudo menos
        Concluida e Cancelada"), a regra moveria em silencio um estado novo que
        entrasse no banco sem passar por aqui."""
        demanda = {"estado": "arquivada", "autor_id": "P1", "responsavel_id": "P2"}

        assert efeito_da_etapa(demanda, etapa_nova=ETAPA_ENTREGUE) == SEM_EFEITO

    @pytest.mark.parametrize("etapa", [e for e in ETAPAS if e != ETAPA_ENTREGUE])
    def test_nenhuma_outra_etapa_move_a_demanda(self, etapa):
        """ "Nao sera feita" esta nesta lista de proposito (historia 29): ela so
        escreve a linha automatica, e quem cancela e a Vitta, a mao, depois de
        explicar na Conversa."""
        demanda = {"estado": "em_andamento", "autor_id": "P1", "responsavel_id": "P2"}

        assert efeito_da_etapa(demanda, etapa_nova=etapa) == SEM_EFEITO

    def test_demanda_sem_autor_nao_tem_a_quem_voltar(self):
        """`autor_id` e `ON DELETE SET NULL` na migration 102: quem abriu o
        pedido pode ter sido apagado. Sem esta guarda a Demanda seria "atribuida
        a ninguem", apagando o responsavel que ela tinha."""
        demanda = {"estado": "em_andamento", "autor_id": None, "responsavel_id": "P2"}

        assert efeito_da_etapa(demanda, etapa_nova=ETAPA_ENTREGUE) == SEM_EFEITO


def _entregue(numero: int = 673) -> dict:
    """A issue fechada como concluida, que e o que leva a Etapa a Entregue."""
    return _issue(numero, estado="closed", motivo="completed")


def _pessoa(pid: str = "P1", nome: str | None = "Diretor Geral", **campos) -> dict:
    """Quem ve a aba: ativo e Super admin (`e_pessoa_da_aba`)."""
    return {"id": pid, "nome_completo": nome, "ativo": True, "is_super_admin": True, "access_profile": None, **campos}


def _campos_do_fio(sb: _SupabaseMock) -> list[tuple]:
    return [(linha["movimento_campo"], linha["movimento_de"], linha["movimento_para"]) for linha in _fio(sb)]


def _alarme_da_atribuicao(caplog) -> logging.LogRecord:
    """O registro do UPDATE do responsavel que nao casou, seja qual for o ramo.

    O filtro morde o trecho que os DOIS ramos compartilham ("da Demanda D1"),
    e nunca o nivel nem a frase: sao eles que cada teste vai conferir. Um helper
    que ja procurasse "pela metade" acharia so o ramo do ERROR, e o teste do
    outro ramo passaria por nao encontrar nada.
    """
    alarmes = [registro for registro in caplog.records if "responsável da Demanda D1" in registro.getMessage()]
    assert len(alarmes) == 1, f"esperado um alarme da atribuição, e vieram {len(alarmes)}"
    return alarmes[0]


class TestADevolucaoPelaRota:
    """A costura, pela porta de verdade: o webhook entrega, a rotina sincroniza,
    e o card volta para a mao de quem pediu.

    Pela ROTA, e nao chamando `sincronizar_demanda` direto, porque a devolucao
    tem que valer para os DOIS gatilhos, e e a rota que prova o caminho inteiro
    (assinatura, threadpool, corpo da resposta). O lote usa a mesma rotina.
    """

    def _cenario(self, monkeypatch, *, demanda: dict, participantes=None, **extra):
        return _montar(
            demandas=[demanda],
            participantes=[_pessoa()] if participantes is None else participantes,
            produtos=[{"id": "prod-1", "nome": "Prontuário"}],
            github=_GithubFalso({673: _entregue()}),
            monkeypatch=monkeypatch,
            **extra,
        )

    def test_a_entrega_devolve_o_card_e_avisa_quem_pediu(self, monkeypatch, _sem_email_de_verdade):
        """Criterio de aceite inteiro: move, atribui, grava as duas linhas e
        chama o e-mail de atribuicao com o recado da Entrega."""
        cliente, sb, _ = self._cenario(
            monkeypatch,
            demanda=_demanda("D1", github_issue_numero=673, estado="em_andamento", responsavel_id="P2", autor_id="P1"),
        )

        resposta = _entregar(cliente, _corpo(acao="closed"))

        assert resposta.json() == {"recebido": True, "sincronizada": True}
        demanda = _demandas(sb)[0]
        assert (demanda["etapa"], demanda["estado"], demanda["responsavel_id"]) == (ETAPA_ENTREGUE, "aguardando", "P1")
        assert _campos_do_fio(sb) == [
            ("etapa", ETAPA_EM_ANALISE, ETAPA_ENTREGUE),
            ("estado", "em_andamento", "aguardando"),
            ("responsavel", "P2", "P1"),
        ]
        assert _fio(sb)[1]["texto"] == f"{AUTOR_DA_ENTREGA} moveu para Aguardando"
        assert _fio(sb)[2]["texto"] == f"{AUTOR_DA_ENTREGA} atribuiu a Diretor Geral"
        assert [(aviso["destinatario_id"], aviso["trecho"]) for aviso in _sem_email_de_verdade] == [
            ("P1", RECADO_DA_ENTREGA)
        ]
        assert _sem_email_de_verdade[0]["demanda"]["produto_nome"] == "Prontuário"

    def test_a_issue_recusada_nao_devolve_o_card_nem_avisa_ninguem(self, monkeypatch, _sem_email_de_verdade):
        """Issue #701, pela rota, que e onde a correcao tem de valer.

        A foto e a do caminho comum de recusa: `wontfix` na issue e fechamento
        pelo botao padrao do GitHub, que fecha como CONCLUIDA. Antes da
        correcao ela virava Entregue, e Entregue e a unica Etapa que move o
        Kanban: o card ia para Aguardando com o autor como responsavel e saia o
        e-mail "Entregue, confira e conclua" sobre um pedido recusado.

        Este teste atravessa a assinatura, o threadpool, o `sincronizar_demanda`,
        o compare-and-swap e o `_devolver_a_quem_pediu`. E o unico lugar que
        prova as tres coisas juntas: a Etapa certa, o card parado e o silencio
        do e-mail. Chamar `etapa_da_foto` e `efeito_da_etapa` em sequencia
        dentro do teste nao provaria nada: quem liga as duas e o codigo de
        producao, e e justamente essa ligacao que esta sob teste.
        """
        cliente, sb, _ = _montar(
            demandas=[
                _demanda("D1", github_issue_numero=673, estado="em_andamento", responsavel_id="P2", autor_id="P1")
            ],
            participantes=[_pessoa()],
            produtos=[{"id": "prod-1", "nome": "Prontuário"}],
            github=_GithubFalso({673: _issue(673, estado="closed", motivo="completed", labels=("wontfix",))}),
            monkeypatch=monkeypatch,
        )

        _entregar(cliente, _corpo(acao="closed"))

        demanda = _demandas(sb)[0]
        assert demanda["etapa"] == ETAPA_NAO_SERA_FEITA
        assert (demanda["estado"], demanda["responsavel_id"]) == ("em_andamento", "P2")
        assert _campos_do_fio(sb) == [("etapa", ETAPA_EM_ANALISE, ETAPA_NAO_SERA_FEITA)]
        assert _sem_email_de_verdade == []

    def test_o_autor_que_ja_e_o_responsavel_nao_recebe_email(self, monkeypatch, _sem_email_de_verdade):
        """Criterio de aceite: a regra de nao avisar quem ja tem a Demanda na mao
        continua valendo quando quem atribui e a Entrega. O card ainda ANDA, o
        que prova que o silencio e do aviso, e nao da devolucao inteira."""
        cliente, sb, _ = self._cenario(
            monkeypatch,
            demanda=_demanda("D1", github_issue_numero=673, estado="em_andamento", responsavel_id="P1", autor_id="P1"),
        )

        _entregar(cliente, _corpo(acao="closed"))

        assert _demandas(sb)[0]["estado"] == "aguardando"
        assert _campos_do_fio(sb) == [
            ("etapa", ETAPA_EM_ANALISE, ETAPA_ENTREGUE),
            ("estado", "em_andamento", "aguardando"),
        ]
        assert _sem_email_de_verdade == []

    @pytest.mark.parametrize("estado", ESTADOS_FECHADOS)
    def test_demanda_fechada_nao_e_movida_nem_atribuida(self, monkeypatch, _sem_email_de_verdade, estado):
        """Historia 28. Quem segura isto e a guarda da issue #678, um degrau
        acima: a Demanda fechada nao e sequer lida (nem gasta cota do GitHub), e
        por isso ela tambem nao ganha a linha da Etapa.
        """
        cliente, sb, gh = self._cenario(
            monkeypatch,
            demanda=_demanda("D1", github_issue_numero=673, estado=estado, responsavel_id="P2", autor_id="P1"),
        )

        _entregar(cliente, _corpo(acao="closed"))

        demanda = _demandas(sb)[0]
        assert (demanda["estado"], demanda["responsavel_id"]) == (estado, "P2")
        assert gh.leituras == []
        assert _fio(sb) == []
        assert _sem_email_de_verdade == []

    def test_nao_sera_feita_so_escreve_a_linha_da_etapa(self, monkeypatch, _sem_email_de_verdade):
        """Historia 29: a Vitta explica na Conversa e cancela a mao."""
        cliente, sb, _ = _montar(
            demandas=[
                _demanda("D1", github_issue_numero=673, estado="em_andamento", responsavel_id="P2", autor_id="P1")
            ],
            github=_GithubFalso({673: _issue(673, estado="closed", motivo="not_planned")}),
            monkeypatch=monkeypatch,
        )

        _entregar(cliente, _corpo(acao="closed"))

        demanda = _demandas(sb)[0]
        assert demanda["etapa"] == ETAPA_NAO_SERA_FEITA
        assert (demanda["estado"], demanda["responsavel_id"]) == ("em_andamento", "P2")
        assert _campos_do_fio(sb) == [("etapa", ETAPA_EM_ANALISE, ETAPA_NAO_SERA_FEITA)]
        assert _sem_email_de_verdade == []

    @pytest.mark.parametrize(
        "issue",
        (
            _issue(673, estado="closed", motivo="completed"),
            _issue(673, estado="closed", motivo="not_planned"),
            _issue(673, labels=("in-progress",)),
            _issue(673, labels=("ready-for-agent",)),
        ),
        ids=("entregue", "nao_sera_feita", "em_desenvolvimento", "planejada"),
    )
    def test_a_sincronizacao_nunca_conclui_a_demanda(self, monkeypatch, issue):
        """Historia 30: a Demanda so vai para Concluida pela mao de alguem.

        Por foto, e nao so pela Entrega: a porta por onde um "concluida" entraria
        e o UPDATE do estado, e ele nao distingue de onde a Etapa veio.
        """
        cliente, sb, _ = _montar(
            demandas=[
                _demanda("D1", github_issue_numero=673, estado="em_andamento", responsavel_id="P2", autor_id="P1")
            ],
            github=_GithubFalso({673: issue}),
            monkeypatch=monkeypatch,
        )

        _entregar(cliente, _corpo(acao="closed"))

        assert _demandas(sb)[0]["estado"] in ESTADOS_ABERTOS

    def test_a_edicao_do_corpo_depois_da_entrega_nao_devolve_de_novo(self, monkeypatch, _sem_email_de_verdade):
        """A foto muda (o corpo da issue foi editado) e a Etapa nao: o card ja
        estava Entregue.

        E o caso que morde de verdade em producao: depois da devolucao o diretor
        pode ter movido o card e passado a bola adiante, e uma segunda devolucao
        a cada edicao de issue o puxaria de volta para a mao dele para sempre.
        Quem segura isto e o LUGAR de onde a devolucao e chamada, dentro do ramo
        que so a mudanca de Etapa alcanca.
        """
        foto_antiga = github_client.montar_foto(_entregue(), [])
        foto_antiga["corpo"] = "## Para o diretor\n\nOutro texto, editado depois."
        cliente, sb, _ = _montar(
            demandas=[
                _demanda(
                    "D1",
                    github_issue_numero=673,
                    estado="em_andamento",
                    responsavel_id="P2",
                    autor_id="P1",
                    etapa=ETAPA_ENTREGUE,
                    github_foto=foto_antiga,
                )
            ],
            github=_GithubFalso({673: _entregue()}),
            monkeypatch=monkeypatch,
        )

        resposta = _entregar(cliente, _corpo(acao="edited"))

        assert resposta.json() == {"recebido": True, "sincronizada": True}, "o cache do texto acompanha"
        demanda = _demandas(sb)[0]
        assert (demanda["estado"], demanda["responsavel_id"]) == ("em_andamento", "P2")
        assert _fio(sb) == []
        assert _sem_email_de_verdade == []

    def test_os_textos_da_entrega_sao_estes(self):
        """As duas constantes, presas ao LITERAL.

        Sem esta linha, toda asserção da devolução calcula o esperado a partir
        da propria constante, e trocar o texto deixa o backend inteiro verde: o
        e-mail passaria a dizer uma coisa e o selo da tela outra, quebrando a
        promessa escrita em cima da constante. O par do outro lado e o teste do
        `MOTIVO_ROTULO` no frontend, que prende o mesmo literal em TypeScript.
        """
        assert RECADO_DA_ENTREGA == "Entregue, confira e conclua"
        assert AUTOR_DA_ENTREGA == "A entrega"

    def test_quem_conclui_a_mao_no_meio_da_devolucao_ganha(self, monkeypatch, _sem_email_de_verdade):
        """A corrida real: a rotina le o card em Em andamento e o diretor conclui
        no mesmo segundo.

        O UPDATE amarra o estado LIDO, entao ele nao casa linha nenhuma e a
        devolucao para ali: nem move, nem atribui, nem avisa. Sem a amarra, a
        Demanda que alguem acabou de concluir voltaria para Aguardando.
        """

        def conclui_no_meio(nome, payload, linhas):
            if nome == "tecnologia_demandas" and payload.get("estado"):
                for linha in linhas:
                    linha["estado"] = "concluida"

        cliente, sb, _ = self._cenario(
            monkeypatch,
            demanda=_demanda("D1", github_issue_numero=673, estado="em_andamento", responsavel_id="P2", autor_id="P1"),
            antes_do_update=conclui_no_meio,
        )

        _entregar(cliente, _corpo(acao="closed"))

        demanda = _demandas(sb)[0]
        assert (demanda["estado"], demanda["responsavel_id"]) == ("concluida", "P2")
        assert _campos_do_fio(sb) == [("etapa", ETAPA_EM_ANALISE, ETAPA_ENTREGUE)]
        assert _sem_email_de_verdade == []

    def test_quem_conclui_a_mao_ganha_tambem_quando_nao_ha_o_que_mover(
        self, monkeypatch, _sem_email_de_verdade, caplog
    ):
        """O par do teste acima, no ramo em que NAO ha movimento.

        A Demanda ja esta em Aguardando, entao a devolucao so tem a atribuicao a
        fazer, e o bloco do movimento (com a amarra) nem roda. Sem uma amarra
        PROPRIA no UPDATE do responsavel, este e o caminho por onde o fio de uma
        Demanda FECHADA ganharia "A entrega atribuiu a Fulano" e o e-mail sairia
        para quem acabou de concluir o card.

        O alarme sai em WARNING, e nao em ERROR (issue #694): aqui o UPDATE que
        nao casa e a UNICA escrita que a devolucao tinha para fazer, entao nada
        foi escrito e o card ficou intacto. E o mesmo desfecho correto que o ramo
        do movimento registra em INFO.
        """

        def conclui_no_meio(nome, payload, linhas):
            if nome == "tecnologia_demandas" and payload.get("responsavel_id"):
                for linha in linhas:
                    linha["estado"] = "concluida"

        cliente, sb, _ = self._cenario(
            monkeypatch,
            demanda=_demanda("D1", github_issue_numero=673, estado="aguardando", responsavel_id="P2", autor_id="P1"),
            antes_do_update=conclui_no_meio,
        )

        with caplog.at_level(logging.INFO):
            _entregar(cliente, _corpo(acao="closed"))

        demanda = _demandas(sb)[0]
        assert (demanda["estado"], demanda["responsavel_id"]) == ("concluida", "P2")
        assert _campos_do_fio(sb) == [("etapa", ETAPA_EM_ANALISE, ETAPA_ENTREGUE)]
        assert _sem_email_de_verdade == []
        alarme = _alarme_da_atribuicao(caplog)
        assert alarme.levelno == logging.WARNING, "o desfecho em que nada foi escrito nao pode virar alerta"
        assert "nada foi escrito" in alarme.getMessage(), (
            "a devolução que não escreveu nada precisa de alarme com essa frase, e não de silêncio"
        )

    def test_o_card_que_ja_andou_e_perdeu_a_atribuicao_grita_em_error(self, monkeypatch, _sem_email_de_verdade, caplog):
        """O outro ramo, o que de fato fica pela metade (issue #694).

        A Demanda estava em Em andamento: o movimento para Aguardando VALEU e ja
        gravou a linha do fio. So entao alguem conclui o card, e o UPDATE do
        responsavel nao casa. Aqui o card andou, ninguem foi avisado e a passagem
        seguinte nao refaz nada: e o ERROR que continua de pe, nomeando a Demanda
        e mandando conferir o card antes de terminar a mao.
        """

        def conclui_depois_do_movimento(nome, payload, linhas):
            if nome == "tecnologia_demandas" and payload.get("responsavel_id"):
                for linha in linhas:
                    linha["estado"] = "concluida"

        cliente, sb, _ = self._cenario(
            monkeypatch,
            demanda=_demanda("D1", github_issue_numero=673, estado="em_andamento", responsavel_id="P2", autor_id="P1"),
            antes_do_update=conclui_depois_do_movimento,
        )

        with caplog.at_level(logging.INFO):
            _entregar(cliente, _corpo(acao="closed"))

        demanda = _demandas(sb)[0]
        assert (demanda["estado"], demanda["responsavel_id"]) == ("concluida", "P2"), "o movimento valeu e foi por cima"
        assert _campos_do_fio(sb) == [
            ("etapa", ETAPA_EM_ANALISE, ETAPA_ENTREGUE),
            ("estado", "em_andamento", "aguardando"),
        ], "a linha do movimento ficou gravada: e o que torna esta devolução uma metade"
        assert _sem_email_de_verdade == []
        alarme = _alarme_da_atribuicao(caplog)
        assert alarme.levelno == logging.ERROR, "a devolução que ficou pela metade continua sendo alerta"
        assert "pela metade" in alarme.getMessage()
        assert "Confira o estado do card" in alarme.getMessage(), (
            "quem lê no susto precisa olhar o card antes de refazer"
        )

    @pytest.mark.parametrize(
        "autor",
        (_pessoa(ativo=False), _pessoa(is_super_admin=False)),
        ids=("desativado", "sem_super_admin"),
    )
    def test_autor_que_saiu_da_aba_nao_recebe_o_card_de_volta(self, monkeypatch, _sem_email_de_verdade, caplog, autor):
        """A mesma guarda que o `atribuir` do router tem, e pelo mesmo motivo.

        Se o card fosse para quem saiu, ele sumiria da "Minha vez" de TODO
        MUNDO (ninguem seria responsavel, e mencao nao ha) e o e-mail tambem nao
        sairia, porque o envio pula quem nao esta na aba e so registra um INFO.
        O card fica em Aguardando com o responsavel que tinha: alguem da Vitta
        ainda o ve e pode repassa-lo a mao.
        """
        cliente, sb, _ = self._cenario(
            monkeypatch,
            demanda=_demanda("D1", github_issue_numero=673, estado="em_andamento", responsavel_id="P2", autor_id="P1"),
            participantes=[autor],
        )

        with caplog.at_level(logging.WARNING):
            _entregar(cliente, _corpo(acao="closed"))

        demanda = _demandas(sb)[0]
        assert (demanda["estado"], demanda["responsavel_id"]) == ("aguardando", "P2")
        assert _campos_do_fio(sb) == [
            ("etapa", ETAPA_EM_ANALISE, ETAPA_ENTREGUE),
            ("estado", "em_andamento", "aguardando"),
        ]
        assert _sem_email_de_verdade == []
        assert "não está mais na lista de acesso" in caplog.text

    def test_a_linha_do_fio_cai_no_id_quando_o_nome_nao_veio(self, monkeypatch):
        """`nome_completo` e anulavel. Sem o resguardo, a linha sairia como
        "A entrega atribuiu a ", que nao diz a quem."""
        cliente, sb, _ = self._cenario(
            monkeypatch,
            demanda=_demanda("D1", github_issue_numero=673, estado="em_andamento", responsavel_id="P2", autor_id="P1"),
            participantes=[_pessoa(nome=None)],
        )

        _entregar(cliente, _corpo(acao="closed"))

        assert _fio(sb)[2]["texto"] == f"{AUTOR_DA_ENTREGA} atribuiu a P1"

    def test_a_devolucao_perdida_no_meio_grita(self, monkeypatch, caplog):
        """O pior estado possivel, e o unico alarme que existe para ele.

        O cache e a linha da Etapa ja estao gravados quando a devolucao estoura,
        e a passagem seguinte vai sair no `foto_mudou` sem refazer nada: esta
        devolucao esta PERDIDA. O webhook responde `falhou: true` como sempre, e
        o que distingue este caso de uma falha comum e o ERROR nomeando a
        Demanda, para alguem termina-la a mao.
        """

        def estoura_no_movimento(nome, payload, linhas):
            if nome == "tecnologia_demandas" and payload.get("estado"):
                raise httpx.ReadTimeout("timeout no PostgREST")

        cliente, sb, _ = self._cenario(
            monkeypatch,
            demanda=_demanda("D1", github_issue_numero=673, estado="em_andamento", responsavel_id="P2", autor_id="P1"),
            antes_do_update=estoura_no_movimento,
        )

        with caplog.at_level(logging.ERROR):
            resposta = _entregar(cliente, _corpo(acao="closed"))

        assert resposta.json() == {"recebido": True, "sincronizada": False, "falhou": True}
        assert _demandas(sb)[0]["etapa"] == ETAPA_ENTREGUE, "o cache ficou gravado: e o que torna a perda definitiva"
        assert "NÃO foi concluída na Demanda D1" in caplog.text
        assert "termine à mão" in caplog.text

    def test_a_leitura_do_produto_que_falha_nao_desfaz_a_devolucao(self, monkeypatch, _sem_email_de_verdade, caplog):
        """A leitura do nome do Produto acontece com a devolucao JA GRAVADA.

        Um timeout do PostgREST ali nao pode virar `falhou: true` sobre um
        movimento que valeu: a reconciliacao veria a foto igual e o aviso se
        perderia de vez. O e-mail sai assim mesmo, sem o nome do Produto.
        """
        cliente, sb, _ = self._cenario(
            monkeypatch,
            demanda=_demanda("D1", github_issue_numero=673, estado="em_andamento", responsavel_id="P2", autor_id="P1"),
            falhar_ao_ler="tecnologia_produtos",
        )

        with caplog.at_level(logging.WARNING):
            resposta = _entregar(cliente, _corpo(acao="closed"))

        assert resposta.json() == {"recebido": True, "sincronizada": True}
        demanda = _demandas(sb)[0]
        assert (demanda["estado"], demanda["responsavel_id"]) == ("aguardando", "P1")
        assert _sem_email_de_verdade[0]["demanda"]["produto_nome"] is None
        assert "Falha ao ler o Produto" in caplog.text

    def test_o_card_reaberto_e_devolvido_de_novo_quando_a_entrega_sai_outra_vez(
        self, monkeypatch, _sem_email_de_verdade
    ):
        """O ciclo inteiro: entregue, o diretor pede ajuste, entregue de novo.

        A re-devolucao AQUI e desejada (PRD #673, historia 21: "Voltou para
        desenvolvimento"), e e o outro lado do teste da edicao de corpo: o que
        nao pode repetir e a devolucao sobre a MESMA Etapa, e nao a devolucao
        depois de a Etapa dar a volta.
        """
        gh = _GithubFalso({673: _issue(673, labels=("in-progress",))})
        cliente, sb, _ = _montar(
            demandas=[
                _demanda(
                    "D1",
                    github_issue_numero=673,
                    estado="aguardando",
                    responsavel_id="P1",
                    autor_id="P1",
                    etapa=ETAPA_ENTREGUE,
                    github_foto=github_client.montar_foto(_entregue(), []),
                )
            ],
            participantes=[_pessoa()],
            github=gh,
            monkeypatch=monkeypatch,
        )

        # 1. O diretor pediu ajuste: a issue reabriu e voltou a andar.
        _entregar(cliente, _corpo(acao="reopened"))

        assert _demandas(sb)[0]["etapa"] == ETAPA_EM_DESENVOLVIMENTO
        assert _sem_email_de_verdade == [], "voltar para desenvolvimento não devolve nada"

        # 2. A Vitta passou a bola de volta para si enquanto refazia.
        _demandas(sb)[0]["responsavel_id"] = "P2"
        gh.issues[673] = _entregue()

        _entregar(cliente, _corpo(acao="closed"))

        demanda = _demandas(sb)[0]
        assert (demanda["etapa"], demanda["estado"], demanda["responsavel_id"]) == (ETAPA_ENTREGUE, "aguardando", "P1")
        assert [aviso["trecho"] for aviso in _sem_email_de_verdade] == [RECADO_DA_ENTREGA]
