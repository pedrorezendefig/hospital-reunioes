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

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.config import settings  # noqa: E402
from app.cron import scheduler as scheduler_mod  # noqa: E402
from app.dependencies import get_supabase_client  # noqa: E402
from app.routers import webhooks as webhooks_router  # noqa: E402
from app.services import github_client, tecnologia_sincronizacao  # noqa: E402
from app.services.tecnologia import ESTADOS_ABERTOS, ESTADOS_FECHADOS  # noqa: E402
from app.services.tecnologia_vinculo import (  # noqa: E402
    ETAPA_EM_ANALISE,
    ETAPA_EM_DESENVOLVIMENTO,
    ETAPA_ENTREGUE,
    ETAPA_PLANEJADA,
)

ROTA = "/api/webhooks/github"

# Valor de mentira, deste arquivo. O segredo de verdade e do Coolify.
SEGREDO = "segredo-falso-de-teste-678"


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
def _segredo_configurado(monkeypatch):
    """O segredo de pe, como estara no Coolify.

    O `.env` local nao o tem, e sem isto TODA entrega responderia 503 e os testes
    de 401 ficariam verdes pelo motivo errado. Quem prova o 503 e o teste que
    APAGA a variavel, e nao a ausencia dela por acidente.
    """
    monkeypatch.setattr(settings, "github_webhook_secret", SEGREDO)


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

    def __init__(self, rows: list[dict], nome: str, falhas: dict[str, Exception] | None = None):
        self._rows = rows
        self._nome = nome
        self._falhas = falhas or {}
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
    def __init__(self, tabelas: dict[str, list[dict]], falhas: dict[str, Exception] | None = None):
        self.tabelas = tabelas
        self.falhas = falhas or {}

    def table(self, nome: str):
        return _TableQuery(self.tabelas.setdefault(nome, []), nome, self.falhas)


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


def _montar(
    *,
    demandas: list[dict] | None = None,
    conversas: list[dict] | None = None,
    github: _GithubFalso | None = None,
    falhas: dict[str, Exception] | None = None,
    monkeypatch=None,
) -> tuple[TestClient, _SupabaseMock, _GithubFalso]:
    app = FastAPI()
    app.include_router(webhooks_router.router, prefix="/api")

    sb = _SupabaseMock(
        {
            "tecnologia_demandas": [dict(d) for d in (demandas or [])],
            "tecnologia_conversas": [dict(c) for c in (conversas or [])],
        },
        falhas=falhas,
    )

    gh = github or _GithubFalso({})
    if monkeypatch is not None:
        monkeypatch.setattr(github_client, "ler_issue", gh.ler_issue)
        monkeypatch.setattr(github_client, "ler_sub_issues", gh.ler_sub_issues)

    app.dependency_overrides[get_supabase_client] = lambda: sb
    return TestClient(app), sb, gh


def _fio(sb: _SupabaseMock) -> list[dict]:
    return sb.tabelas["tecnologia_conversas"]


def _demandas(sb: _SupabaseMock) -> list[dict]:
    return sb.tabelas["tecnologia_demandas"]


def _corpo(numero: int = 673, acao: str = "labeled") -> bytes:
    """O corpo CRU, com os espacos que o GitHub manda.

    Cru de proposito, e nao um `dict` que o teste serializa na hora do envio: e a
    unica forma de o teste distinguir o corpo recebido do corpo re-serializado, e
    e essa distincao que a assinatura do GitHub cobra.
    """
    return json.dumps({"action": acao, "issue": {"number": numero}}, indent=2).encode("utf-8")


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
        digest = _assinar(corpo).removeprefix("sha256=")

        resposta = _entregar(cliente, corpo)

        assert resposta.status_code == 200, "o caso perdeu o sentido: a entrega nem chegou a conferir a assinatura"
        # O QUE o espiao viu, e nao so que viu algo: a lista nao vazia sozinha
        # ficaria verde se o proprio teste enchesse a lista sem instalar o espiao.
        assert chamadas == [(digest, digest)], (
            "a assinatura foi conferida sem `hmac.compare_digest` sobre o digest esperado: "
            "o `==` conta ao atacante quantos bytes ele ja acertou"
        )


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

    def test_payload_sem_numero_de_issue_nao_derruba_a_rota(self, monkeypatch):
        cliente, sb, _ = _montar(demandas=[_demanda("D1", github_issue_numero=673)], monkeypatch=monkeypatch)
        corpo = json.dumps({"action": "labeled", "issue": {}}).encode("utf-8")

        resposta = _entregar(cliente, corpo)

        assert resposta.status_code == 200
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

    def test_foto_igual_nao_escreve_nada(self, monkeypatch):
        """Criterio de aceite: foto igual a guardada nao grava linha nem mexe na
        ultima sincronizacao. Sem esta guarda, a reconciliacao de hora em hora
        encheria o fio do diretor de linhas repetidas."""
        gh = _GithubFalso({673: _issue(673, labels=("in-progress",))})
        antes = "2026-09-09T08:00:00+00:00"
        cliente, sb, _ = _montar(
            demandas=[
                _demanda(
                    "D1",
                    github_issue_numero=673,
                    etapa=ETAPA_EM_DESENVOLVIMENTO,
                    github_foto=_foto_guardada(gh, 673),
                    github_sincronizado_em=antes,
                )
            ],
            github=gh,
            monkeypatch=monkeypatch,
        )

        resposta = _entregar(cliente, _corpo())

        assert resposta.status_code == 200
        assert _fio(sb) == []
        assert _demandas(sb)[0]["github_sincronizado_em"] == antes

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
        das duas listas sumiria da reconciliacao em silencio."""
        assert set(ESTADOS_ABERTOS) & set(ESTADOS_FECHADOS) == set()
        assert set(tecnologia_sincronizacao.ESTADOS_DA_RECONCILIACAO) == set(ESTADOS_ABERTOS)

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
                    _demanda(
                        "D2",
                        github_issue_numero=678,
                        etapa=ETAPA_EM_ANALISE,
                        github_foto=_foto_guardada(gh, 678),
                    ),
                ],
                "tecnologia_conversas": [],
            }
        )

        with caplog.at_level(logging.INFO, logger="app.services.tecnologia_sincronizacao"):
            tecnologia_sincronizacao.reconciliar_vinculos(sb)

        assert "2 lida(s)" in caplog.text
        assert "1 mudada(s)" in caplog.text

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
