"""O Arquivo da Manifestação: arquivar e desarquivar um caso encerrado
(issue #592, PRD #591, ADR 0047).

Arquivar é organização da lista, e não fato do caso. É essa frase que os testes
daqui existem para segurar, e ela se decompõe em quatro promessas que erram
juntas com facilidade:

* o `status` não muda e NENHUM movimento entra na trilha. Gravar movimento seria
  acender o ponto de novidade num caso em que ninguém mexeu, e o detector do
  ponto está aqui justamente para provar isso pelo lado de fora;
* só caso `encerrado` arquiva. Caso em andamento tem prazo correndo e setor
  esperando, e escondê-lo da lista é esconder atraso;
* a lista nunca mistura os dois mundos: sem o filtro devolve só os não
  arquivados, com o filtro devolve só os arquivados;
* nada disso mexe em número. Métricas contam o caso arquivado igual a antes.

Duas armadilhas de teste vazio moram aqui:

* provar que a lista filtra é fácil de fazer errado com UM caso só na base: a
  lista vazia passaria por "filtrou" mesmo se a rota tivesse devolvido nada por
  outro motivo. Por isso toda checagem de filtro roda com DOIS casos, um de cada
  lado, e afirma os dois sentidos;
* provar que arquivar não grava movimento é vazio se a requisição morreu antes
  (403, 409, 422). Por isso todo teste do que NÃO acontece confere o 200 antes
  de olhar o efeito.

Desde a issue #627 o LOTE tem uma quinta promessa, e ela é de transação: o
carimbo e o registro de acesso valem juntos ou não valem. Como quem garante isso
é o Postgres, e não o Python, ela é provada em duas camadas que se cobrem: o
Supabase falso é fiel à transação (e o detector dele tem teste próprio nos dois
sentidos), e um guarda estático lê a migration para cobrar do SQL o que faz o
banco desfazer o `UPDATE`. Nenhuma das duas sozinha valeria: o fake prova só a
rota, e o guarda estático prova só o arquivo.
"""

from __future__ import annotations

import datetime as dt
import logging
import os
import re
import sys
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from postgrest.exceptions import APIError
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.dependencies import get_current_user, get_supabase_client  # noqa: E402
from app.limiter import limiter  # noqa: E402
from app.middleware.request_context import RequestContextMiddleware  # noqa: E402
from app.routers import ouvidoria as ouvidoria_router  # noqa: E402
from app.services import ouvidoria_notificacoes  # noqa: E402

OUVIDOR = {"id": "P10", "nome_completo": "Marta Ouvidora", "access_profile": None, "perfil_ouvidoria": "ouvidor"}
DIRETORIA = {
    "id": "P11",
    "nome_completo": "Dr. Diretor",
    "access_profile": None,
    "perfil_ouvidoria": "diretoria_executiva",
}
# Papel nas Reuniões não concede nada na Ouvidoria (RN-40): o super admin
# administra o sistema, e não toca no caso. Os dois têm `access_profile` de
# verdade porque passam no gate LARGO da lista (`require_acesso_painel`): é
# justamente por isso que o recorte do arquivo precisa do gate próprio.
SUPER_ADMIN = {"id": "P99", "nome_completo": "Root", "access_profile": "super_admin", "perfil_ouvidoria": None}
SECRETARIA = {"id": "P12", "nome_completo": "Ana Secretaria", "access_profile": "secretaria", "perfil_ouvidoria": None}

# O nome da RPC do lote sai do ROTEADOR, e não de uma cópia escrita aqui: o
# Supabase falso e a rota precisam falar do mesmo nome por construção, e quem
# amarra esse nome ao SQL de verdade é `TestATransacaoNoSQLDaRpc`, que o procura
# dentro da migration. Com a cópia à mão, um rename da rota deixaria o fake
# atendendo uma função que o banco não tem, e tudo verde.
RPC_DO_LOTE = ouvidoria_router.RPC_DO_LOTE_DO_ARQUIVO

MIGRATIONS = os.path.join(os.path.dirname(__file__), "..", "..", "supabase", "migrations")

# Terça-feira, 14h de Brasília: dentro do expediente e longe de feriado.
INICIO = dt.datetime(2026, 8, 25, 17, 0, tzinfo=dt.UTC)


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


@pytest.fixture(autouse=True)
def _nunca_envia_email_de_verdade(monkeypatch):
    """O pytest do backend carrega o .env real (Resend de produção). Nenhuma
    rota deste arquivo manda email, e o mock existe para que um caminho novo
    não descubra isso disparando de verdade."""

    def _fake(destinatario, assunto, html_content, texto_fallback):
        raise AssertionError("Arquivar não manda email")

    monkeypatch.setattr(ouvidoria_notificacoes, "_enviar_email", _fake)


class _Relogio:
    """O relógio do servidor e o do banco, que são o mesmo e ANDAM. Cada leitura
    avança um segundo, para instantes diferentes serem distinguíveis."""

    def __init__(self, inicio: dt.datetime):
        self._agora = inicio

    def agora(self) -> dt.datetime:
        self._agora += dt.timedelta(seconds=1)
        return self._agora


def _caso(numero: int = 7, **overrides) -> dict:
    """Uma linha de `ouvidoria_protocolos` com as colunas que a fila, o Dossiê e
    as métricas leem."""
    row = {
        "id": f"uuid-{numero}",
        "numero": numero,
        "protocolo": f"2026-{numero:04d}",
        "data_abertura": "2026-08-14",
        "prazo_resposta": "2026-08-21",
        "status": "encerrado",
        "tipo_manifestacao": "reclamacao",
        "sigilo_reforcado": False,
        "categoria": "Demora",
        "setor": "Recepcao",
        "resumo": "Paciente relata espera acima de duas horas na recepcao.",
        "conversa_id": "conv-1",
        "gravidade": "medio",
        "prazo_area_em": None,
        "prazo_conclusivo_em": None,
        "respondida_em": None,
        "minutos_pausados": 0,
        "desfecho": "procedente",
        "desfecho_descricao": "Escala ajustada.",
        "pausada_em": None,
        "area_estourou_em": None,
        "relato_integral": "Cheguei as 8h e so fui atendida as 10h30.",
        "manifestante_nome": "Joana da Silva",
        "manifestante_contato": "(31) 99999-0000",
        "manifestante_vinculo": "acompanhante",
        "anonimo": False,
        "dados_incompletos": False,
        "classificacao_ia": None,
        "natureza_informada": None,
        "canal": "ana",
        "canal_setor": None,
        "canal_ponto": None,
        "contato_em": "2026-08-14T19:50:00+00:00",
        "prazo_rompido_em": None,
        "validada_em": None,
        "validada_por": None,
        "extrato_para_o_setor": None,
        "resposta_da_area": None,
        "respondida_por_nome": None,
        "encerrada_em": "2026-08-20T14:00:00+00:00",
        "reincidencia": 0,
        "reaberta_em": None,
        "critico_avisado_em": None,
        "acuse_recebimento_em": None,
        "acuse_sem_contato_em": None,
        "encerramento_avisado_em": None,
        "encerramento_sem_contato_em": None,
        "vista_pela_ouvidoria_em": None,
        # O Arquivo (migration 099). NULL é o normal, e é o valor com que todo
        # caso já existente entra na coluna.
        "arquivada_em": None,
        "arquivada_por": None,
    }
    row.update(overrides)
    return row


class _TabelaFake:
    """Fake do PostgREST fiel no que importa: o select projeta só as colunas
    pedidas, os filtros casam de verdade (igualdade, nulo, negação do nulo e as
    duas pontas da data) e o `range` recorta, para o laço da paginação ter fim.

    A negação existe porque é o filtro do modo "arquivados": sem ela o fake
    devolveria a lista inteira e o teste do filtro ficaria verde sobre nada."""

    def __init__(self, nome: str, rows: list[dict], ao_ler=None):
        self.nome = nome
        self.rows = rows
        # A query do pedido, no MESMO lugar em que o cliente de verdade a
        # guarda (`request.params`, um `httpx.QueryParams` imutável). É por
        # ela que o lote pede `select=id` no update, e é por ela que os
        # filtros do postgrest entram. Sem isto aqui o fake não conheceria o
        # recorte, e o teste ficaria verde sobre a linha inteira.
        self.request = SimpleNamespace(params=httpx.QueryParams())
        # O que acontece DEPOIS de um select casar e ANTES de a rota voltar a
        # falar com o banco. É assim que a corrida da reabertura entra no
        # teste, sem thread nenhuma.
        self.ao_ler = ao_ler
        self._filtros: list = []
        self._insert: dict | list | None = None
        self._update: dict | None = None
        self._colunas: tuple[str, ...] | None = None
        self._janela: tuple[int, int] | None = None
        self._negar = False
        # A contagem que o PostgREST devolve no `Content-Range` quando alguém
        # pede `count=exact`. Ela conta as linhas AFETADAS, e não as que
        # couberam no corpo: é justamente por serem coisas diferentes que o
        # lote passou a ler daqui.
        self._contagem_pedida: str | None = None

    @property
    def not_(self):
        self._negar = True
        return self

    def select(self, colunas: str = "*", *_a, **_kw):
        if colunas.strip() != "*":
            self._colunas = tuple(c.strip() for c in colunas.split(","))
        return self

    def insert(self, payload):
        self._insert = payload
        return self

    def update(self, payload: dict, count: str | None = None, **_kw):
        self._update = payload
        self._contagem_pedida = count
        return self

    def _guardar(self, teste):
        negado = self._negar
        self._negar = False
        self._filtros.append((lambda row: not teste(row)) if negado else teste)
        return self

    def eq(self, col, value):
        return self._guardar(lambda row: row.get(col) == value)

    def in_(self, col, values):
        return self._guardar(lambda row: row.get(col) in list(values))

    def is_(self, col, value):
        alvo = None if value in ("null", None) else value
        return self._guardar(lambda row: row.get(col) == alvo)

    def gte(self, col, value):
        return self._guardar(lambda row: str(row.get(col) or "") >= str(value))

    def lte(self, col, value):
        return self._guardar(lambda row: str(row.get(col) or "") <= str(value))

    def order(self, col, desc=False):
        self.rows = sorted(self.rows, key=lambda r: str(r.get(col) or ""), reverse=desc)
        return self

    def limit(self, _quantas):
        return self

    def range(self, inicio: int, fim: int):
        self._janela = (inicio, fim)
        return self

    def _projetar(self, row: dict) -> dict:
        if self._colunas is None:
            return dict(row)
        return {c: row.get(c) for c in self._colunas}

    def execute(self):
        if self._insert is not None:
            novos = self._insert if isinstance(self._insert, list) else [self._insert]
            gravados = []
            for n in novos:
                linha = dict(n)
                linha.setdefault("id", f"{self.nome}-{len(self.rows) + 1}")
                self.rows.append(linha)
                gravados.append(dict(linha))
            return type("R", (), {"data": gravados, "count": None})()
        casadas = [r for r in self.rows if all(teste(r) for teste in self._filtros)]
        if self._update is not None:
            for r in casadas:
                r.update(self._update)
            # O `select` da query recorta o RETORNO do update, como no
            # PostgREST. Quem pediu só o id recebe só o id: se a rota tentasse
            # ler outra coluna do que voltou, ela quebraria aqui em vez de
            # passar despercebida.
            recorte = self.request.params.get("select")
            colunas = tuple(c.strip() for c in recorte.split(",")) if recorte else None
            gravadas = [{c: r.get(c) for c in colunas} if colunas else dict(r) for r in casadas]
            contagem = len(casadas) if self._contagem_pedida else None
            return type("R", (), {"data": gravadas, "count": contagem})()
        if self._janela is not None:
            inicio, fim = self._janela
            casadas = casadas[inicio : fim + 1]
        projetadas = [self._projetar(r) for r in casadas]
        if self.ao_ler is not None and casadas:
            self.ao_ler(casadas)
        return type("R", (), {"data": projetadas, "count": None})()


class _AgregadoFake:
    """A função `ouvidoria_ultimo_movimento` (migration 092) servida como o
    PostgREST serve: em páginas e com ordem estável."""

    def __init__(self, linhas: list[dict]):
        self._linhas = sorted(linhas, key=lambda linha: linha["manifestacao_id"])

    def order(self, *_a, **_kw):
        return self

    def range(self, inicio: int, fim: int):
        return _AgregadoFake(self._linhas[inicio : fim + 1])

    def execute(self):
        return type("R", (), {"data": [dict(linha) for linha in self._linhas]})()


class _RpcFake:
    """A chamada de RPC guardada até o `execute()`, como no cliente de verdade."""

    def __init__(self, corpo):
        self._corpo = corpo

    def execute(self):
        return type("R", (), {"data": self._corpo(), "count": None})()


class _SupabaseFake:
    def __init__(self, casos: list[dict], movimentos: list[dict] | None = None, relogio=None):
        # Quando preenchido, roda uma vez logo depois do primeiro select em
        # `ouvidoria_protocolos` e some. Simula a reabertura concorrente.
        self.reabre_no_meio_da_leitura = False
        # O relógio do BANCO. Desde a migration 101 o carimbo do lote é `now()`
        # do Postgres, e não mais um `isoformat()` montado no servidor: os dois
        # relógios do teste são o mesmo objeto justamente porque na vida real
        # eles deixaram de ser dois.
        self.relogio = relogio or _Relogio(INICIO).agora
        # Toda RPC chamada nesta sessão, na ordem, com os parâmetros. É por aqui
        # que o teste prova que o lote virou UMA ida ao banco.
        self.rpcs: list[tuple[str, dict]] = []
        # Todo pedido montado nesta sessão, na ordem. É por aqui que o teste
        # olha a QUERY que a rota montou, e não só o efeito dela no banco:
        # `select=id` no update não muda o que fica gravado, então sem isto
        # nada reprovaria a rota que voltasse a pedir a linha inteira.
        self.pedidos: list[_TabelaFake] = []
        self.tabelas: dict[str, list[dict]] = {
            "ouvidoria_protocolos": casos,
            "ouvidoria_movimentos": movimentos or [],
            "ouvidoria_acessos": [],
            "ouvidoria_notificacoes": [],
            "ouvidoria_prorrogacoes": [],
            "ouvidoria_prazos": [
                {"gravidade": "medio", "marco": "triagem", "valor": 1, "unidade": "dias_uteis"},
                {"gravidade": "medio", "marco": "area_resposta", "valor": 4, "unidade": "dias_uteis"},
                {"gravidade": "medio", "marco": "conclusiva", "valor": 7, "unidade": "dias_uteis"},
            ],
            "ouvidoria_feriados": [{"data": "2026-09-07", "nome": "Independencia", "abrangencia": "nacional"}],
            "ouvidoria_setor_responsaveis": [],
            "setores": [{"id": "s1", "nome": "Recepcao", "ativo": True}],
            "participantes": [],
        }

    def _reabrir_agora(self, casadas: list[dict]) -> None:
        self.reabre_no_meio_da_leitura = False
        for row in casadas:
            row["status"] = "aguardando_area"

    def table(self, nome: str):
        ao_ler = None
        if nome == "ouvidoria_protocolos" and self.reabre_no_meio_da_leitura:
            ao_ler = self._reabrir_agora
        pedido = _TabelaFake(nome, self.tabelas.setdefault(nome, []), ao_ler)
        self.pedidos.append(pedido)
        return pedido

    def arquivar_encerrados(self, params: dict) -> list[dict]:
        """A RPC da migration 101, servida como o Postgres a serve: o UPDATE dos
        carimbos e o INSERT do log na MESMA transação, e SEM bloco EXCEPTION.

        A fidelidade que importa é a de baixo: se o log for recusado, a função
        levanta e o carimbo do UPDATE NÃO fica. Um fake que gravasse o carimbo
        assim mesmo deixaria verde exatamente a rota que a issue #627 existe
        para consertar, e por isso o detector tem teste próprio nos dois
        sentidos (`TestOFakeDaTransacao`).

        O INSERT sai por `self.table(...)`, e não por um append direto na lista:
        é assim que o teste consegue recusar o log no MESMO lugar em que ele
        falharia de verdade, sem monkeypatch nenhum na função sob teste."""
        protocolos = self.tabelas["ouvidoria_protocolos"]
        acessos = self.tabelas["ouvidoria_acessos"]
        # O ponto de restauração da transação, tirado antes de qualquer escrita.
        protocolos_antes = [dict(linha) for linha in protocolos]
        acessos_antes = [dict(linha) for linha in acessos]
        alvos = [c for c in protocolos if c.get("status") == "encerrado" and c.get("arquivada_em") is None]
        try:
            carimbo = self.relogio().isoformat()
            for caso in alvos:
                caso["arquivada_em"] = carimbo
                caso["arquivada_por"] = params["p_ator_id"]
            if alvos:
                self.table("ouvidoria_acessos").insert(
                    [
                        {
                            "manifestacao_id": caso["id"],
                            "ator_id": params["p_ator_id"],
                            "ator_nome": params["p_ator_nome"],
                            "acao": "arquivar",
                        }
                        for caso in alvos
                    ]
                ).execute()
        except Exception:
            # ROLLBACK. As duas tabelas voltam ao ponto de restauração, porque
            # as duas escritas são a mesma transação.
            protocolos[:] = protocolos_antes
            acessos[:] = acessos_antes
            raise
        # `RETURNS TABLE (arquivadas INTEGER)`: uma linha de uma coluna, que é o
        # único formato que o `APIResponse` do postgrest-py aceita.
        return [{"arquivadas": len(alvos)}]

    def rpc(self, nome: str, params: dict | None = None):
        self.rpcs.append((nome, dict(params or {})))
        if nome == "ouvidoria_ultimo_movimento":
            ultimo: dict[str, str] = {}
            for mov in self.tabelas["ouvidoria_movimentos"]:
                caso = str(mov["manifestacao_id"])
                ultimo[caso] = max(str(mov["ocorrido_em"]), ultimo.get(caso, ""))
            return _AgregadoFake([{"manifestacao_id": c, "ultimo_movimento_em": q} for c, q in ultimo.items()])
        if nome == RPC_DO_LOTE:
            return _RpcFake(lambda: self.arquivar_encerrados(params or {}))
        raise AssertionError(f"Arquivar não passa por esta RPC, e ela chegou: {nome}")


def _client(monkeypatch, casos: list[dict] | None = None, participante: dict | None = None, movimentos=None):
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(RequestContextMiddleware)
    app.include_router(ouvidoria_router.router, prefix="/api")

    relogio = _Relogio(INICIO)
    supabase = _SupabaseFake(casos if casos is not None else [_caso()], movimentos, relogio=relogio.agora)
    quem = participante if participante is not None else OUVIDOR

    async def _fake_participante(_user, _sb, fields=None):
        return quem

    monkeypatch.setattr(ouvidoria_router, "get_participante_for_user", _fake_participante)
    monkeypatch.setattr(ouvidoria_router, "agora_utc", relogio.agora)
    app.dependency_overrides[get_current_user] = lambda: {"id": "u1", "email": "u@hsm.br"}
    app.dependency_overrides[get_supabase_client] = lambda: supabase
    return TestClient(app), supabase


# ---------------------------------------------------------------------------
# Os detectores. Cada um é exercitado nos DOIS sentidos ao longo do arquivo: um
# detector que lesse a coluna errada ficaria preso num só valor, e o par de
# testes que o cerca reprovaria.
# ---------------------------------------------------------------------------


def _arquivar(client, numero: int = 7):
    return client.post(f"/api/ouvidoria/manifestacoes/uuid-{numero}/arquivo")


def _desarquivar(client, numero: int = 7):
    return client.delete(f"/api/ouvidoria/manifestacoes/uuid-{numero}/arquivo")


def _gravado(supabase, numero: int = 7) -> dict:
    return next(c for c in supabase.tabelas["ouvidoria_protocolos"] if c["id"] == f"uuid-{numero}")


def _listar(client, **params) -> list[str]:
    """Os protocolos que a lista devolve, na ordem em que ela os devolve."""
    r = client.get("/api/ouvidoria/protocolos", params=params)
    assert r.status_code == 200, r.text
    return [p["protocolo"] for p in r.json()["protocolos"]]


def _ponto_aceso(client, numero: int = 7, **params) -> bool:
    r = client.get("/api/ouvidoria/protocolos", params=params)
    assert r.status_code == 200, r.text
    linha = next(p for p in r.json()["protocolos"] if p["id"] == f"uuid-{numero}")
    return linha["tem_novidade"]


def _contador(client) -> int | None:
    r = client.get("/api/ouvidoria/novidades")
    assert r.status_code == 200, r.text
    return r.json()["total"]


def _movimentos(supabase, numero: int = 7) -> list[dict]:
    return [m for m in supabase.tabelas["ouvidoria_movimentos"] if m["manifestacao_id"] == f"uuid-{numero}"]


class TestArquivarUmCaso:
    def test_caso_encerrado_grava_quando_e_quem(self, monkeypatch):
        client, supabase = _client(monkeypatch)

        r = _arquivar(client)

        assert r.status_code == 200, r.text
        caso = _gravado(supabase)
        assert caso["arquivada_em"], "o carimbo de quando precisa ficar gravado"
        assert caso["arquivada_por"] == OUVIDOR["id"]

    def test_a_resposta_devolve_os_dois_carimbos(self, monkeypatch):
        """A tela adota o que a rota devolve, e não o que ela supôs ter feito."""
        client, supabase = _client(monkeypatch)

        corpo = _arquivar(client).json()

        assert corpo["arquivada_em"] == _gravado(supabase)["arquivada_em"]
        assert corpo["arquivada_por"] == OUVIDOR["id"]

    @pytest.mark.parametrize(
        "estado",
        ["novo", "em_classificacao", "aguardando_area", "aguardando_manifestante", "respondido"],
    )
    def test_caso_em_andamento_recusa_com_409(self, monkeypatch, estado):
        """Esconder da lista um caso com prazo correndo é esconder atraso."""
        client, supabase = _client(monkeypatch, casos=[_caso(status=estado)])

        r = _arquivar(client)

        assert r.status_code == 409, r.text
        assert "encerrad" in r.json()["detail"].lower(), r.json()["detail"]
        assert _gravado(supabase)["arquivada_em"] is None

    def test_manifestacao_inexistente_da_404(self, monkeypatch):
        client, _ = _client(monkeypatch)

        assert _arquivar(client, numero=99).status_code == 404

    def test_arquivar_nao_grava_movimento_nem_muda_status(self, monkeypatch):
        """As duas metades da frase "arquivar não é fato do caso"."""
        client, supabase = _client(monkeypatch)

        assert _arquivar(client).status_code == 200

        assert _movimentos(supabase) == []
        assert _gravado(supabase)["status"] == "encerrado"

    def test_arquivar_de_novo_nao_quebra(self, monkeypatch):
        """Um segundo clique é inofensivo: o carimbo é reescrito, e nada mais."""
        client, supabase = _client(monkeypatch)
        assert _arquivar(client).status_code == 200
        primeiro = _gravado(supabase)["arquivada_em"]

        assert _arquivar(client).status_code == 200

        assert _gravado(supabase)["arquivada_em"] >= primeiro
        assert _movimentos(supabase) == []

    def test_a_diretoria_executiva_tambem_arquiva(self, monkeypatch):
        client, supabase = _client(monkeypatch, participante=DIRETORIA)

        assert _arquivar(client).status_code == 200
        assert _gravado(supabase)["arquivada_por"] == DIRETORIA["id"]


class TestDesarquivarUmCaso:
    def test_limpa_os_dois_campos(self, monkeypatch):
        client, supabase = _client(
            monkeypatch,
            casos=[_caso(arquivada_em="2026-08-25T17:00:01+00:00", arquivada_por="P10")],
        )

        r = _desarquivar(client)

        assert r.status_code == 200, r.text
        caso = _gravado(supabase)
        assert caso["arquivada_em"] is None
        assert caso["arquivada_por"] is None

    def test_nao_tem_pre_condicao_de_estado(self, monkeypatch):
        """Desarquivar é sempre uma saída: caso que chegou ao arquivo por
        qualquer caminho precisa poder voltar à lista."""
        client, supabase = _client(
            monkeypatch,
            casos=[_caso(status="aguardando_area", arquivada_em="2026-08-25T17:00:01+00:00", arquivada_por="P10")],
        )

        assert _desarquivar(client).status_code == 200
        assert _gravado(supabase)["arquivada_em"] is None

    def test_caso_nao_arquivado_e_inofensivo(self, monkeypatch):
        client, supabase = _client(monkeypatch)

        assert _desarquivar(client).status_code == 200
        assert _gravado(supabase)["arquivada_em"] is None

    def test_desarquivar_nao_grava_movimento_nem_muda_status(self, monkeypatch):
        client, supabase = _client(
            monkeypatch,
            casos=[_caso(arquivada_em="2026-08-25T17:00:01+00:00", arquivada_por="P10")],
        )

        assert _desarquivar(client).status_code == 200

        assert _movimentos(supabase) == []
        assert _gravado(supabase)["status"] == "encerrado"

    def test_manifestacao_inexistente_da_404(self, monkeypatch):
        client, _ = _client(monkeypatch)

        assert _desarquivar(client, numero=99).status_code == 404


class TestOGateDePerfil:
    """RN-40: papel nas Reuniões não concede nada na Ouvidoria."""

    @pytest.mark.parametrize("quem", [SUPER_ADMIN, SECRETARIA])
    def test_sem_perfil_da_ouvidoria_recebe_403_nas_duas_rotas(self, monkeypatch, quem):
        client, supabase = _client(monkeypatch, participante=quem)

        assert _arquivar(client).status_code == 403
        assert _desarquivar(client).status_code == 403
        assert _gravado(supabase)["arquivada_em"] is None


class TestAListaFiltraPorArquivo:
    """Dois casos, um de cada lado, e as duas afirmações em cada teste: a lista
    devolve quem tem de devolver E não devolve quem não tem."""

    def _base(self, monkeypatch):
        return _client(
            monkeypatch,
            casos=[
                _caso(7),
                _caso(8, arquivada_em="2026-08-25T17:00:01+00:00", arquivada_por="P10"),
            ],
        )

    def test_sem_o_filtro_devolve_so_os_nao_arquivados(self, monkeypatch):
        client, _ = self._base(monkeypatch)

        assert _listar(client) == ["2026-0007"]

    def test_com_o_filtro_devolve_so_os_arquivados(self, monkeypatch):
        client, _ = self._base(monkeypatch)

        assert _listar(client, arquivados="sim") == ["2026-0008"]

    def test_o_filtro_desligado_explicitamente_e_o_mesmo_que_sem_ele(self, monkeypatch):
        client, _ = self._base(monkeypatch)

        assert _listar(client, arquivados="nao") == ["2026-0007"]

    def test_arquivar_tira_o_caso_da_lista_na_mesma_carga(self, monkeypatch):
        """O caminho inteiro, pelo lado de fora: o ouvidor arquiva pela lista e a
        recarga já vem sem o caso."""
        client, _ = self._base(monkeypatch)
        assert "2026-0007" in _listar(client)

        assert _arquivar(client, numero=7).status_code == 200

        assert _listar(client) == []
        assert sorted(_listar(client, arquivados="sim")) == ["2026-0007", "2026-0008"]

    def test_desarquivar_devolve_o_caso_a_lista(self, monkeypatch):
        client, _ = self._base(monkeypatch)

        assert _desarquivar(client, numero=8).status_code == 200

        assert sorted(_listar(client)) == ["2026-0007", "2026-0008"]
        assert _listar(client, arquivados="sim") == []


class TestACorridaComAReabertura:
    """TOCTOU: a pré-condição "só encerrado arquiva" é checada na leitura, e o
    update precisa repeti-la para valer.

    Sem a condição no próprio update, uma reabertura que caísse entre as duas
    idas ao banco deixaria um caso `aguardando_area` arquivado: prazo correndo,
    setor notificado, e fora da lista de trabalho. Nenhuma linha de código
    estaria errada, e é por isso que o teste precisa forçar a corrida.
    """

    def test_reabertura_no_meio_do_caminho_vira_409_e_nao_arquiva(self, monkeypatch):
        client, supabase = _client(monkeypatch)
        # O caso está encerrado quando a rota lê, e `aguardando_area` quando ela
        # grava. É exatamente a janela do TOCTOU.
        supabase.reabre_no_meio_da_leitura = True

        r = _arquivar(client)

        assert r.status_code == 409, r.text
        caso = _gravado(supabase)
        assert caso["status"] == "aguardando_area", "o gatilho da corrida precisa ter disparado"
        assert caso["arquivada_em"] is None, "o caso reaberto não pode terminar arquivado"

    def test_sem_a_corrida_o_mesmo_caminho_arquiva(self, monkeypatch):
        """A contraprova do teste acima: sem o gatilho, tudo igual, o 200 sai e
        o carimbo entra. Sem ela, um 409 vindo de qualquer outro motivo passaria
        por prova da corrida."""
        client, supabase = _client(monkeypatch)

        assert _arquivar(client).status_code == 200
        assert _gravado(supabase)["arquivada_em"]


class TestORastroDoArquivo:
    """Arquivar não entra na trilha (por desenho) e desarquivar apaga os dois
    carimbos. Sem o log de acesso, o par arquivar + desarquivar não deixaria
    vestígio nenhum de que o caso esteve escondido, por quanto tempo e por
    quem."""

    def _acessos(self, supabase) -> list[dict]:
        return supabase.tabelas["ouvidoria_acessos"]

    def test_arquivar_registra_o_acesso_com_autor_e_acao(self, monkeypatch):
        client, supabase = _client(monkeypatch)

        assert _arquivar(client).status_code == 200

        acessos = self._acessos(supabase)
        assert len(acessos) == 1
        assert acessos[0]["acao"] == "arquivar"
        assert acessos[0]["ator_id"] == OUVIDOR["id"]
        assert acessos[0]["manifestacao_id"] == "uuid-7"

    def test_desarquivar_registra_o_acesso(self, monkeypatch):
        client, supabase = _client(
            monkeypatch,
            casos=[_caso(arquivada_em="2026-08-25T17:00:01+00:00", arquivada_por="P10")],
        )

        assert _desarquivar(client).status_code == 200

        acessos = self._acessos(supabase)
        assert len(acessos) == 1
        assert acessos[0]["acao"] == "desarquivar"

    def test_o_par_arquivar_desarquivar_deixa_os_dois_registros(self, monkeypatch):
        """O caso volta a NULL nas duas colunas, e o rastro é o que sobra."""
        client, supabase = _client(monkeypatch)

        assert _arquivar(client).status_code == 200
        assert _desarquivar(client).status_code == 200

        assert _gravado(supabase)["arquivada_em"] is None
        assert [a["acao"] for a in self._acessos(supabase)] == ["arquivar", "desarquivar"]

    def test_recusa_nao_registra_acesso(self, monkeypatch):
        """O log é de ato, e ato recusado não aconteceu."""
        client, supabase = _client(monkeypatch, casos=[_caso(status="aguardando_area")])

        assert _arquivar(client).status_code == 409

        assert self._acessos(supabase) == []


class TestORecorteTodos:
    """O terceiro recorte existe para quem CONTA em vez de trabalhar (o painel
    em tempo real). Arquivar é organização da lista e não fato do caso, então o
    card de cada estado tem de somar o mesmo que as métricas do bloco ao lado.
    """

    def _base(self, monkeypatch, participante=None):
        return _client(
            monkeypatch,
            casos=[
                _caso(7),
                _caso(8, arquivada_em="2026-08-25T17:00:01+00:00", arquivada_por="P10"),
            ],
            participante=participante,
        )

    def test_todos_devolve_os_dois_mundos(self, monkeypatch):
        client, _ = self._base(monkeypatch)

        assert sorted(_listar(client, arquivados="todos")) == ["2026-0007", "2026-0008"]

    def test_o_total_de_todos_nao_muda_ao_arquivar(self, monkeypatch):
        """O que o painel precisa: a soma das colunas continua fechando com o
        hospital inteiro depois de arquivar."""
        client, _ = self._base(monkeypatch)
        antes = len(_listar(client, arquivados="todos"))

        assert _arquivar(client, numero=7).status_code == 200

        assert len(_listar(client, arquivados="todos")) == antes
        # A contraprova, no mesmo teste: a lista de TRABALHO encolheu de verdade.
        assert _listar(client) == []

    def test_valor_fora_dos_tres_e_recusado(self, monkeypatch):
        client, _ = self._base(monkeypatch)

        r = client.get("/api/ouvidoria/protocolos", params={"arquivados": "talvez"})

        assert r.status_code == 422


class TestOGateDoArquivoNaLista:
    """A vista do arquivo é da Ouvidoria também no servidor, e não só na tela.
    O gate da lista é o largo (a equipe de Reuniões inteira lê o índice), então
    o recorte precisa do seu próprio."""

    def _base(self, monkeypatch, participante):
        return _client(
            monkeypatch,
            casos=[_caso(7), _caso(8, arquivada_em="2026-08-25T17:00:01+00:00", arquivada_por="P10")],
            participante=participante,
        )

    @pytest.mark.parametrize("quem", [SUPER_ADMIN, SECRETARIA])
    @pytest.mark.parametrize("recorte", ["sim", "todos"])
    def test_sem_perfil_da_ouvidoria_nao_le_o_arquivo(self, monkeypatch, quem, recorte):
        client, _ = self._base(monkeypatch, quem)

        r = client.get("/api/ouvidoria/protocolos", params={"arquivados": recorte})

        assert r.status_code == 403, r.text

    @pytest.mark.parametrize("quem", [SUPER_ADMIN, SECRETARIA])
    def test_a_lista_de_trabalho_continua_aberta_a_quem_ja_a_lia(self, monkeypatch, quem):
        """A contraprova do gate: o índice é da equipe de Reuniões, e esta fatia
        não podia fechá-lo. Sem este teste, o 403 acima passaria por prova mesmo
        se a rota inteira tivesse virado exclusiva da Ouvidoria."""
        client, _ = self._base(monkeypatch, quem)

        assert _listar(client) == ["2026-0007"]

    @pytest.mark.parametrize("recorte", ["sim", "todos"])
    def test_a_diretoria_executiva_le_o_arquivo(self, monkeypatch, recorte):
        client, _ = self._base(monkeypatch, DIRETORIA)

        r = client.get("/api/ouvidoria/protocolos", params={"arquivados": recorte})

        assert r.status_code == 200, r.text


class TestNovidadeIgnoraOArquivado:
    """Arquivado não acende ponto nem sobe o contador do menu: o arquivo não
    pode parecer trabalho pendente."""

    def _base(self, monkeypatch):
        # Os dois casos têm movimento na trilha e nunca foram vistos, então os
        # dois acenderiam o ponto se o arquivo não contasse.
        movimentos = [
            {
                "id": f"mov-{n}",
                "manifestacao_id": f"uuid-{n}",
                "estado_anterior": "respondido",
                "estado_novo": "encerrado",
                "autor_id": "P10",
                "autor_nome": "Marta Ouvidora",
                "observacao": None,
                "ocorrido_em": "2026-08-24T12:00:00+00:00",
            }
            for n in (7, 8)
        ]
        return _client(
            monkeypatch,
            casos=[_caso(7), _caso(8, arquivada_em="2026-08-25T17:00:01+00:00", arquivada_por="P10")],
            movimentos=movimentos,
        )

    def test_o_contador_do_menu_nao_conta_o_arquivado(self, monkeypatch):
        client, supabase = self._base(monkeypatch)

        assert _contador(client) == 1

        # O outro sentido do mesmo detector: desarquivado, ele volta a contar.
        assert _desarquivar(client, numero=8).status_code == 200
        assert _contador(client) == 2

    def test_o_ponto_nao_acende_na_linha_do_arquivado(self, monkeypatch):
        client, _ = self._base(monkeypatch)

        assert _ponto_aceso(client, numero=7) is True
        assert _ponto_aceso(client, numero=8, arquivados="sim") is False


class TestODossieAbreOArquivado:
    """Arquivar esconde da lista, e só. Quem ligar perguntando pelo protocolo
    precisa ser atendido."""

    def _base(self, monkeypatch):
        return _client(monkeypatch, casos=[_caso(arquivada_em="2026-08-25T17:00:01+00:00", arquivada_por="P10")])

    def test_por_id(self, monkeypatch):
        client, _ = self._base(monkeypatch)

        r = client.get("/api/ouvidoria/manifestacoes/uuid-7")

        assert r.status_code == 200, r.text
        assert r.json()["protocolo"] == "2026-0007"

    def test_por_protocolo(self, monkeypatch):
        client, _ = self._base(monkeypatch)

        r = client.get("/api/ouvidoria/manifestacoes/por-protocolo/2026-0007")

        assert r.status_code == 200, r.text
        assert r.json()["id"] == "uuid-7"


class TestArquivarNaoMexeEmNumero:
    """O relatório de julho reenviado em setembro mostra o mesmo total."""

    def test_o_volume_das_metricas_nao_muda_ao_arquivar(self, monkeypatch):
        client, _ = _client(monkeypatch, casos=[_caso(7), _caso(8)])
        antes = client.get("/api/ouvidoria/metricas", params={"inicio": "2026-08-01", "fim": "2026-08-25"})
        assert antes.status_code == 200, antes.text
        total_antes = antes.json()["volume"]["total"]
        assert total_antes == 2, "a contraprova: sem dois casos contados, o teste abaixo não prova nada"

        assert _arquivar(client, numero=8).status_code == 200

        depois = client.get("/api/ouvidoria/metricas", params={"inicio": "2026-08-01", "fim": "2026-08-25"})
        assert depois.status_code == 200, depois.text
        assert depois.json()["volume"]["total"] == total_antes


# ---------------------------------------------------------------------------
# O lote (issue #594)
# ---------------------------------------------------------------------------


def _arquivar_o_lote(client):
    return client.post("/api/ouvidoria/manifestacoes/arquivo-dos-encerrados")


def _com_carimbo(supabase) -> list[str]:
    """Os ids que estão com o carimbo do arquivo, na ordem da base."""
    return [c["id"] for c in supabase.tabelas["ouvidoria_protocolos"] if c["arquivada_em"]]


# Um caso que já estava no arquivo antes do lote, com carimbo de OUTRO autor e
# de OUTRO instante. Os dois são o detector de regravação: um lote que perdesse
# o filtro de "sem arquivo" reescreveria os dois valores e o teste veria.
ARQUIVADO_ANTES = {"arquivada_em": "2026-08-01T10:00:00+00:00", "arquivada_por": "P11"}


class TestOLoteDosEncerrados:
    """Arquivar todos os encerrados de uma vez (issue #594, PRD #591).

    O lote é o MESMO ato do arquivo de um caso, repetido: mesmas duas colunas,
    mesma pré-condição de estado, nenhum movimento na trilha. Duas coisas só
    ele pode errar, e são as que os testes daqui cercam: pegar caso que não
    devia (o em andamento, o que já estava guardado) e mentir na contagem.

    Toda base de teste tem os TRÊS mundos ao mesmo tempo (encerrado livre, em
    andamento, já arquivado). Com um mundo só, um lote sem filtro nenhum
    passaria por lote certo.
    """

    def _base(self, monkeypatch, quantos_encerrados: int = 1, participante=None, movimentos=None):
        casos = [_caso(n) for n in range(1, quantos_encerrados + 1)]
        casos.append(_caso(8, status="aguardando_area", encerrada_em=None))
        casos.append(_caso(9, **ARQUIVADO_ANTES))
        return _client(monkeypatch, casos=casos, participante=participante, movimentos=movimentos)

    def test_arquiva_o_encerrado_livre_e_devolve_a_contagem(self, monkeypatch):
        client, supabase = self._base(monkeypatch)

        r = _arquivar_o_lote(client)

        assert r.status_code == 200, r.text
        assert r.json() == {"arquivadas": 1}
        assert _gravado(supabase, 1)["arquivada_em"], "o encerrado livre precisa sair carimbado"
        assert _gravado(supabase, 1)["arquivada_por"] == OUVIDOR["id"]

    def test_o_caso_em_andamento_fica_intocado(self, monkeypatch):
        """Caso em andamento tem prazo correndo: escondê-lo é esconder atraso."""
        client, supabase = self._base(monkeypatch)

        assert _arquivar_o_lote(client).status_code == 200

        em_andamento = _gravado(supabase, 8)
        assert em_andamento["arquivada_em"] is None
        assert em_andamento["arquivada_por"] is None
        assert em_andamento["status"] == "aguardando_area"

    def test_o_ja_arquivado_nao_e_regravado(self, monkeypatch):
        """Quem e quando da primeira leva são a memória do ato: um lote que os
        reescrevesse trocaria o autor de um arquivamento que não foi dele."""
        client, supabase = self._base(monkeypatch)

        assert _arquivar_o_lote(client).status_code == 200

        antigo = _gravado(supabase, 9)
        assert antigo["arquivada_em"] == ARQUIVADO_ANTES["arquivada_em"]
        assert antigo["arquivada_por"] == ARQUIVADO_ANTES["arquivada_por"]

    @pytest.mark.parametrize("quantos", [0, 1, 3])
    def test_a_contagem_e_a_das_linhas_que_o_lote_carimbou(self, monkeypatch, quantos):
        """Três tamanhos, porque contagem fixa acerta um deles por acaso. E a
        contagem é conferida contra o BANCO, não contra si mesma: devolver o
        total da tabela também morre aqui, já que o em andamento e o já
        arquivado nunca entram."""
        client, supabase = self._base(monkeypatch, quantos_encerrados=quantos)

        r = _arquivar_o_lote(client)

        assert r.status_code == 200, r.text
        assert r.json()["arquivadas"] == quantos
        novos = [i for i in _com_carimbo(supabase) if i != "uuid-9"]
        assert len(novos) == quantos

    def test_a_segunda_rodada_devolve_zero_e_nao_regrava_a_primeira_leva(self, monkeypatch):
        """O relógio dos testes anda a cada leitura, então um segundo carimbo
        sobre o mesmo caso teria valor diferente do primeiro."""
        client, supabase = self._base(monkeypatch)

        primeira = _arquivar_o_lote(client)
        assert primeira.status_code == 200, primeira.text
        assert primeira.json()["arquivadas"] == 1, "a contraprova: sem a primeira leva, o zero abaixo é vazio"
        carimbo_da_primeira = _gravado(supabase, 1)["arquivada_em"]

        segunda = _arquivar_o_lote(client)

        assert segunda.status_code == 200, segunda.text
        assert segunda.json()["arquivadas"] == 0
        assert _gravado(supabase, 1)["arquivada_em"] == carimbo_da_primeira

    def test_o_lote_nao_grava_movimento_nem_muda_status(self, monkeypatch):
        """Movimento acenderia o ponto de novidade num caso em que ninguém
        mexeu, e o arquivo viraria trabalho pendente."""
        client, supabase = self._base(monkeypatch, quantos_encerrados=2)

        assert _arquivar_o_lote(client).status_code == 200

        assert supabase.tabelas["ouvidoria_movimentos"] == []
        assert _gravado(supabase, 1)["status"] == "encerrado"
        assert _gravado(supabase, 2)["status"] == "encerrado"

    def test_a_diretoria_executiva_tambem_roda_o_lote(self, monkeypatch):
        """Os dois papéis do Perfil da Ouvidoria arquivam (ADR 0047)."""
        client, supabase = self._base(monkeypatch, participante=DIRETORIA)

        r = _arquivar_o_lote(client)

        assert r.status_code == 200, r.text
        assert _gravado(supabase, 1)["arquivada_por"] == DIRETORIA["id"]

    @pytest.mark.parametrize("quem", [SUPER_ADMIN, SECRETARIA], ids=["super_admin", "secretaria"])
    def test_sem_perfil_da_ouvidoria_recebe_403_e_nada_e_arquivado(self, monkeypatch, quem):
        client, supabase = self._base(monkeypatch, participante=quem)

        assert _arquivar_o_lote(client).status_code == 403

        assert _com_carimbo(supabase) == ["uuid-9"], "só o que já estava guardado antes do pedido"

    @pytest.mark.parametrize(
        "falha",
        [
            APIError({"message": "canceling statement due to statement timeout", "code": "57014"}),
            # O timeout do transporte NÃO é `APIError`: ele nasce antes de haver
            # resposta HTTP para virar erro do PostgREST. É a falha típica desta
            # rota, que é a escrita mais pesada do módulo, e um `except APIError`
            # sozinho a deixaria escapar como 500.
            httpx.ReadTimeout("timed out"),
            httpx.ConnectError("connection refused"),
        ],
        ids=["postgrest_recusou", "timeout_de_leitura", "conexao_recusada"],
    )
    def test_a_falha_do_banco_vira_503_e_nao_lote_vazio(self, monkeypatch, falha, caplog):
        """Zero arquivadas com 200 diria ao ouvidor que não havia nada a fazer,
        e o acúmulo continuaria na tela sem explicação.

        A falha é levantada DENTRO do `execute` da RPC, e não antes: é lá que
        ela cai na vida real. Desde a migration 101 o que o timeout deixa para
        trás mudou de natureza, e é o que o teste abaixo confere junto: a
        transação do banco não commitou, então NADA ficou carimbado."""
        client, supabase = self._base(monkeypatch)
        de_verdade = supabase.rpc

        def _rpc_que_recusa(nome: str, params: dict | None = None):
            chamada = de_verdade(nome, params)
            if nome == RPC_DO_LOTE:

                def _explodir():
                    raise falha

                chamada.execute = _explodir
            return chamada

        monkeypatch.setattr(supabase, "rpc", _rpc_que_recusa)

        with caplog.at_level(logging.ERROR):
            assert _arquivar_o_lote(client).status_code == 503

        assert _com_carimbo(supabase) == ["uuid-9"], "a transação não commitou: só o arquivo antigo sobra"
        # O 503 da função que não existe (migration 101 pendente) e o 503 do
        # timeout são o mesmo status e a mesma frase na tela: o que os separa
        # em produção é esta linha. O nome da exceção distingue as famílias, e
        # o código distingue as recusas do PostgREST entre si.
        registrado = "\n".join(caplog.messages)
        assert falha.__class__.__name__ in registrado
        assert getattr(falha, "code", None) is None or str(falha.code) in registrado

    def test_o_lote_e_uma_ida_so_ao_banco_pela_rpc(self, monkeypatch):
        """O conserto da issue #627 em uma frase: o `UPDATE` e o `INSERT` do log
        pararam de ser duas idas ao banco.

        Duas asserções, e as duas precisam estar aqui. A primeira prova que a
        RPC foi chamada; a segunda prova que a rota não montou mais nenhum
        `update` do lado de cá. Sem a segunda, a rota que chamasse a RPC E
        continuasse carimbando por fora ficaria verde, com a janela aberta do
        mesmo jeito."""
        client, supabase = self._base(monkeypatch)

        assert _arquivar_o_lote(client).status_code == 200

        assert [nome for nome, _ in supabase.rpcs] == [RPC_DO_LOTE]
        escritas = [pedido for pedido in supabase.pedidos if pedido._update is not None]
        assert escritas == [], "o carimbo do lote é do banco: nenhum update sai mais daqui"

    def test_a_rota_manda_o_ator_para_a_rpc(self, monkeypatch):
        """Quem arquivou entra no carimbo E na linha do log, e as duas coisas
        agora acontecem lá dentro: o nome precisa atravessar a fronteira. Sem
        `p_ator_nome`, `ouvidoria_acessos.ator_nome` é NOT NULL e o lote inteiro
        passaria a falhar em produção sem nada aqui reprovar."""
        client, supabase = self._base(monkeypatch)

        assert _arquivar_o_lote(client).status_code == 200

        assert supabase.rpcs == [(RPC_DO_LOTE, {"p_ator_id": OUVIDOR["id"], "p_ator_nome": OUVIDOR["nome_completo"]})]

    def test_o_participante_sem_nome_manda_o_id_no_lugar(self, monkeypatch):
        """`ator_nome` é NOT NULL, e o cadastro tem participante sem nome
        completo. A rota já resolvia isso no log de um caso; a RPC herda a mesma
        regra, e é aqui que ela fica presa."""
        sem_nome = {**OUVIDOR, "nome_completo": None}
        client, supabase = self._base(monkeypatch, participante=sem_nome)

        assert _arquivar_o_lote(client).status_code == 200

        assert supabase.rpcs[-1][1]["p_ator_nome"] == sem_nome["id"]

    def test_o_cliente_de_verdade_recusa_a_contagem_escalar(self):
        """Por que a RPC é `RETURNS TABLE (arquivadas INTEGER)`, e não
        `RETURNS INTEGER`.

        O PostgREST devolve função escalar como escalar nu (`3`), e o
        `APIResponse` do postgrest-py declara `data: List[JSON]`: o corpo
        escalar levanta ValidationError antes de a rota ver número nenhum, e o
        lote viraria 500 DEPOIS de a transação já ter commitado, que é o pior
        desfecho possível para esta rota.

        Este teste fala com a classe REAL da biblioteca, e não com o Supabase
        falso: o falso devolve o que eu mandar, então ele nunca reprovaria a
        migration que voltasse ao escalar."""
        from postgrest.base_request_builder import APIResponse
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            APIResponse(data=3, count=None)

        # O outro sentido, que é o formato que a migration 101 produz.
        assert APIResponse(data=[{"arquivadas": 3}], count=None).data == [{"arquivadas": 3}]


class TestOFakeDaTransacao:
    """O detector dos testes do lote, exercitado nos DOIS sentidos.

    Todo teste de atomicidade acima só vale enquanto o Supabase falso for fiel
    numa coisa: a recusa do log tem que DESFAZER o carimbo. Um fake que
    gravasse o carimbo assim mesmo deixaria verde exatamente a rota que a issue
    #627 existe para consertar."""

    def test_a_transacao_grava_os_dois_lados_quando_o_log_aceita(self):
        supabase = _SupabaseFake([_caso(1), _caso(2)])

        devolvido = supabase.arquivar_encerrados({"p_ator_id": "P10", "p_ator_nome": "Marta"})

        assert devolvido == [{"arquivadas": 2}]
        assert all(c["arquivada_em"] for c in supabase.tabelas["ouvidoria_protocolos"])
        assert len(supabase.tabelas["ouvidoria_acessos"]) == 2

    def test_a_transacao_desfaz_o_carimbo_quando_o_log_recusa(self):
        supabase = _SupabaseFake([_caso(1), _caso(2)])
        de_verdade = supabase.table

        def _table_que_recusa_o_log(nome: str):
            tabela = de_verdade(nome)
            if nome == "ouvidoria_acessos":

                def _explodir():
                    raise APIError({"message": "insert or update violates foreign key", "code": "23503"})

                tabela.execute = _explodir
            return tabela

        supabase.table = _table_que_recusa_o_log

        with pytest.raises(APIError):
            supabase.arquivar_encerrados({"p_ator_id": "P10", "p_ator_nome": "Marta"})

        assert [c["arquivada_em"] for c in supabase.tabelas["ouvidoria_protocolos"]] == [None, None]
        assert supabase.tabelas["ouvidoria_acessos"] == []


class TestORastroDoLote:
    """Arquivar não entra na trilha, então o log de acesso é o único vestígio
    de que o caso saiu da vista, por quem e quando. Um lote sem ele apagaria de
    uma vez o rastro de dezenas de casos."""

    def _acessos(self, supabase) -> list[dict]:
        return supabase.tabelas["ouvidoria_acessos"]

    def test_um_registro_por_caso_arquivado_e_so_por_eles(self, monkeypatch):
        client, supabase = _client(
            monkeypatch,
            casos=[
                _caso(1),
                _caso(2),
                _caso(8, status="aguardando_area", encerrada_em=None),
                _caso(9, **ARQUIVADO_ANTES),
            ],
        )

        assert _arquivar_o_lote(client).status_code == 200

        acessos = self._acessos(supabase)
        assert sorted(a["manifestacao_id"] for a in acessos) == ["uuid-1", "uuid-2"]
        assert {a["acao"] for a in acessos} == {"arquivar"}
        assert {a["ator_id"] for a in acessos} == {OUVIDOR["id"]}

    def test_a_recusa_do_log_desfaz_o_arquivamento_inteiro(self, monkeypatch, caplog):
        """O critério de aceite da issue #627, e a inversão do que valia até a
        migration 101: o log do lote DEIXOU de ser fail-open.

        Até aqui, o log recusado devolvia 200 e o arquivamento ficava gravado
        sem rastro nenhum, porque arquivar não entra na trilha e desarquivar
        apaga os dois carimbos. Dentro de uma transação a conta muda de sinal:
        ou as duas escritas valem, ou nenhuma vale.

        A recusa é injetada no INSERT do log, que é onde ela cai de verdade, e
        NÃO na rota: nada aqui monkeypatcha a guarda sob teste. As três
        asserções cobrem os três lados do ato, e o carimbo é o que importa: um
        conserto que só trocasse o status para 503 e deixasse a linha carimbada
        passaria nas outras duas."""
        client, supabase = _client(monkeypatch, casos=[_caso(1), _caso(2)])
        de_verdade = supabase.table

        def _table_que_recusa_o_log(nome: str):
            tabela = de_verdade(nome)
            if nome == "ouvidoria_acessos":

                def _explodir():
                    raise APIError({"message": "insert or update violates foreign key", "code": "23503"})

                tabela.execute = _explodir
            return tabela

        monkeypatch.setattr(supabase, "table", _table_que_recusa_o_log)

        with caplog.at_level(logging.ERROR):
            r = _arquivar_o_lote(client)

        assert r.status_code == 503, r.text
        assert _com_carimbo(supabase) == [], "o log recusado não pode deixar carimbo gravado"
        assert self._acessos(supabase) == []
        assert "23503" in "\n".join(caplog.messages), "o código da recusa é o que separa as causas em produção"

    def test_o_lote_recusado_nao_esconde_nada_da_lista(self, monkeypatch):
        """O mesmo desfecho pelo lado de fora, que é onde o ouvidor está: a
        recusa do log não pode tirar caso nenhum da vista.

        Sem este par, a asserção de cima ficaria presa ao dicionário do fake, e
        um dia em que a lista passasse a ler o arquivo de outra coluna nada
        reprovaria."""
        client, supabase = _client(monkeypatch, casos=[_caso(1), _caso(2)])
        assert _listar(client) == ["2026-0002", "2026-0001"], "a contraprova do estado inicial"
        de_verdade = supabase.table

        def _table_que_recusa_o_log(nome: str):
            tabela = de_verdade(nome)
            if nome == "ouvidoria_acessos":

                def _explodir():
                    raise APIError({"message": "insert or update violates foreign key", "code": "23503"})

                tabela.execute = _explodir
            return tabela

        monkeypatch.setattr(supabase, "table", _table_que_recusa_o_log)

        assert _arquivar_o_lote(client).status_code == 503

        monkeypatch.setattr(supabase, "table", de_verdade)
        assert _listar(client) == ["2026-0002", "2026-0001"], "a fila continua inteira"
        assert _listar(client, arquivados="sim") == []

    def test_lote_sem_nada_para_arquivar_nao_registra_acesso(self, monkeypatch):
        """O outro sentido do mesmo detector: log de ATO, e ato que não
        aconteceu não se registra."""
        client, supabase = _client(monkeypatch, casos=[_caso(8, status="aguardando_area", encerrada_em=None)])

        assert _arquivar_o_lote(client).json()["arquivadas"] == 0

        assert self._acessos(supabase) == []


class TestOLoteNaListaEnoContador:
    """O lote é a limpeza da lista: o que ele carimba sai do grupo Encerrado e
    aparece atrás do filtro, na mesma carga."""

    def _base(self, monkeypatch):
        # Os dois encerrados têm movimento na trilha e nunca foram vistos: os
        # dois estão com o ponto de novidade aceso antes do lote, que é o caso
        # que a issue manda entrar no lote como qualquer outro.
        movimentos = [
            {
                "id": f"mov-{n}",
                "manifestacao_id": f"uuid-{n}",
                "estado_anterior": "respondido",
                "estado_novo": "encerrado",
                "autor_id": "P10",
                "autor_nome": "Marta Ouvidora",
                "observacao": None,
                "ocorrido_em": "2026-08-24T12:00:00+00:00",
            }
            for n in (1, 2)
        ]
        return _client(
            monkeypatch,
            casos=[_caso(1), _caso(2), _caso(8, status="aguardando_area", encerrada_em=None)],
            movimentos=movimentos,
        )

    def test_o_lote_esvazia_o_grupo_encerrado_e_enche_o_arquivo(self, monkeypatch):
        client, _ = self._base(monkeypatch)
        assert _listar(client) == ["2026-0008", "2026-0002", "2026-0001"], "a contraprova do estado inicial"

        assert _arquivar_o_lote(client).json()["arquivadas"] == 2

        assert _listar(client) == ["2026-0008"]
        assert _listar(client, arquivados="sim") == ["2026-0002", "2026-0001"]

    def test_o_caso_com_o_ponto_aceso_entra_no_lote_e_sai_do_contador(self, monkeypatch):
        client, _ = self._base(monkeypatch)
        # Os três casos da base acendem o ponto: os dois encerrados por causa
        # do movimento nunca visto, e o em andamento por ser caso novo que a
        # Ouvidoria ainda não abriu. Sem esta contraprova, o número de baixo
        # passaria por "o lote apagou a novidade" mesmo sobre uma fila apagada.
        assert _contador(client) == 3

        assert _arquivar_o_lote(client).json()["arquivadas"] == 2

        # Sobra o em andamento, e só ele: o contador do menu perde exatamente
        # os dois casos que foram para o arquivo.
        assert _contador(client) == 1


class TestOAcordoEntreOLoteEAListaDaTela:
    """O lote arquiva TODO encerrado sem arquivo, e o botão que o dispara mora
    no cabeçalho do grupo Encerrado. Os dois conjuntos são o mesmo HOJE por uma
    razão só: a lista não tem nenhum outro recorte. Nada no código amarra isso,
    e é o que esta classe existe para amarrar.

    No dia em que a lista ganhar filtro de setor, período ou busca, o botão
    passa a arquivar além do que o ouvidor está vendo, sem nada mais quebrar. O
    teste abaixo quebra, e quem estiver mexendo decide: ou o lote passa a
    respeitar o recorte novo, ou o botão sai do cabeçalho do grupo.
    """

    def test_a_lista_nao_ganhou_recorte_novo_sem_o_lote_saber(self):
        from inspect import signature

        parametros = set(signature(ouvidoria_router.listar_protocolos).parameters)

        assert parametros == {"request", "arquivados", "me", "supabase"}, (
            "A lista da Ouvidoria ganhou (ou perdeu) um parâmetro. Se ele recorta a fila, "
            "o botão 'Arquivar todos os encerrados' passou a prometer o grupo da tela e a "
            "arquivar o banco inteiro: acerte o lote ou tire o botão do cabeçalho."
        )

    def test_o_unico_recorte_extra_da_lista_nao_alcanca_quem_roda_o_lote(self, monkeypatch):
        """A contraprova do teste acima: o sigilo reforçado É um recorte da
        lista, e ele não conta aqui porque só se aplica a quem está FORA da
        Ouvidoria, e quem roda o lote tem o perfil. Com dois casos sigilosos e
        encerrados, o ouvidor vê os dois e o lote leva os dois."""
        client, _ = _client(monkeypatch, casos=[_caso(1, sigilo_reforcado=True), _caso(2, sigilo_reforcado=True)])
        assert _listar(client) == ["2026-0002", "2026-0001"], "o ouvidor enxerga o caso sigiloso"

        assert _arquivar_o_lote(client).json()["arquivadas"] == 2

        assert _listar(client) == []


# ---------------------------------------------------------------------------
# A transação, lida no SQL (issue #627)
# ---------------------------------------------------------------------------
#
# O Supabase falso acima é fiel à transação porque eu o escrevi assim, e isso
# não prova nada sobre o banco: quem faz o `INSERT` recusado desfazer o `UPDATE`
# em produção é o Postgres, e o que decide se ele vai fazer isso está no arquivo
# da migration. Por isso os guardas abaixo leem o SQL.
#
# Eles são exercidos contra SQL SINTÉTICO nos dois sentidos, e não só contra a
# migration de hoje. Rodar só contra o repositório real provaria pouco: ele está
# certo agora, então o guarda ficaria verde mesmo com as regras apagadas.


def _sem_comentarios(sql: str) -> str:
    """O SQL sem as linhas de `--`. Sem isto, o guarda do `EXCEPTION` casaria
    com o cabeçalho da própria migration, que explica por extenso por que o
    bloco não existe, e reprovaria o arquivo certo."""
    return "\n".join(linha.split("--")[0] for linha in sql.splitlines())


def _declaracao_e_corpo(sql: str, funcao: str) -> tuple[str, str]:
    """A declaração (do `CREATE` até o `AS $$`) e o CORPO da função.

    O corpo é o que está ENTRE os dois `$$`, e é essa fronteira que dá sentido
    ao guarda: escrita que caia fora dela é outra transação."""
    achado = re.search(rf"CREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\s+(?:public\.)?{funcao}\s*\(", sql, re.IGNORECASE)
    assert achado is not None, f"`{funcao}` não é criada neste SQL"
    abertura = sql.index("$$", achado.start())
    fechamento = sql.index("$$", abertura + 2)
    return sql[achado.start() : abertura], sql[abertura + 2 : fechamento]


def _tem_bloco_exception(corpo: str) -> bool:
    """O bloco que reintroduziria o fail-open dentro da transação."""
    return re.search(r"\bEXCEPTION\b", _sem_comentarios(corpo), re.IGNORECASE) is not None


def _escritas_do_corpo(corpo: str) -> set[str]:
    """As tabelas que o corpo da função escreve, pelo comando que as alcança."""
    limpo = _sem_comentarios(corpo)
    escritas = set()
    if re.search(r"\bUPDATE\s+ouvidoria_protocolos\b", limpo, re.IGNORECASE):
        escritas.add("ouvidoria_protocolos")
    if re.search(r"\bINSERT\s+INTO\s+ouvidoria_acessos\b", limpo, re.IGNORECASE):
        escritas.add("ouvidoria_acessos")
    return escritas


def _entre_parenteses(texto: str, abertura: int) -> str:
    """O que está entre o parêntese aberto em `abertura` e o que o FECHA.

    Regex não serve: `VARCHAR(10)` tem parênteses aninhados, e a declaração
    inteira ainda traz o `RETURNS TABLE (...)` depois da lista de parâmetros.
    Cortar no primeiro (ou no último) `)` devolveria lista torta nos dois
    sentidos."""
    profundidade = 0
    for i in range(abertura, len(texto)):
        if texto[i] == "(":
            profundidade += 1
        elif texto[i] == ")":
            profundidade -= 1
            if profundidade == 0:
                return texto[abertura + 1 : i]
    raise AssertionError("Parêntese aberto e nunca fechado no SQL.")


def _recorte_do_update(corpo: str) -> set[str]:
    """As condições que o `UPDATE` do corpo carrega, pelo que elas recortam.

    Existe porque o recorte MUDOU DE LADO na issue #627: até a migration 101 ele
    era `.eq("status", ...)` e `.is_("arquivada_em", "null")` em Python, e os
    testes do lote o exerciam de verdade contra o Supabase falso. Agora ele mora
    no SQL, e o fake o reimplementa: sem este guarda, apagar a linha do filtro na
    migration deixaria todos aqueles testes verdes sobre um banco que passou a
    arquivar caso em andamento e a reescrever o autor de uma leva antiga."""
    limpo = _sem_comentarios(corpo)
    recorte = set()
    if re.search(r"status\s*=\s*'encerrado'", limpo, re.IGNORECASE):
        recorte.add("so_encerrado")
    if re.search(r"arquivada_em\s+IS\s+NULL", limpo, re.IGNORECASE):
        recorte.add("so_sem_arquivo")
    return recorte


def _carimbos_do_update(corpo: str) -> set[str]:
    """As colunas que o `UPDATE` grava. As duas andam juntas desde a migration
    099: sem `arquivada_por`, o caso sai da vista sem dizer por quem, que é
    metade do dano que esta issue existe para impedir."""
    limpo = _sem_comentarios(corpo)
    atribuidas = set()
    if re.search(r"arquivada_em\s*=\s*now\(\)", limpo, re.IGNORECASE):
        atribuidas.add("arquivada_em")
    if re.search(r"arquivada_por\s*=\s*p_ator_id", limpo, re.IGNORECASE):
        atribuidas.add("arquivada_por")
    return atribuidas


def _parametros(declaracao: str) -> list[str]:
    """Os nomes dos parâmetros, na ordem, lidos da declaração."""
    lista = _entre_parenteses(declaracao, declaracao.index("("))
    partes: list[str] = []
    atual: list[str] = []
    profundidade = 0
    for caractere in lista:
        if caractere == "(":
            profundidade += 1
        elif caractere == ")":
            profundidade -= 1
        if caractere == "," and profundidade == 0:
            partes.append("".join(atual))
            atual = []
        else:
            atual.append(caractere)
    partes.append("".join(atual))
    return [parte.split()[0] for parte in partes if parte.split()]


def _migration_do_lote() -> tuple[str, str]:
    """O arquivo de migration que cria a RPC do lote, e o SQL dele.

    Achado por varredura, e não por nome escrito à mão: renumerar a migration é
    rotina nesta casa (sessões paralelas colidem no número), e um caminho fixo
    aqui quebraria o guarda por um motivo que não é o dele."""
    achados = []
    for arquivo in sorted(os.listdir(MIGRATIONS)):
        if not arquivo.endswith(".sql"):
            continue
        with open(os.path.join(MIGRATIONS, arquivo), encoding="utf-8") as f:
            sql = f.read()
        if re.search(rf"CREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\s+(?:public\.)?{RPC_DO_LOTE}\s*\(", sql, re.IGNORECASE):
            achados.append((arquivo, sql))
    assert len(achados) == 1, f"a RPC do lote precisa nascer em UMA migration só, e está em {[a for a, _ in achados]}"
    return achados[0]


class TestATransacaoNoSQLDaRpc:
    """O que faz o log recusado desfazer o arquivamento mora no SQL, não aqui.

    Estes guardas não rodam o Postgres: eles cobram do arquivo as coisas sem as
    quais o banco NÃO desfaz nada, e cada uma tem um mutante que a mata.
    """

    def test_as_duas_escritas_moram_no_corpo_da_mesma_funcao(self):
        """A issue inteira em uma asserção: uma transação só.

        Não basta as duas escritas existirem no arquivo; elas têm que estar
        DENTRO do `$$ ... $$`. Um `INSERT` que voltasse para depois do `END`
        seria outro comando, com o mesmo bug de hoje."""
        _, sql = _migration_do_lote()

        _, corpo = _declaracao_e_corpo(sql, RPC_DO_LOTE)

        assert _escritas_do_corpo(corpo) == {"ouvidoria_protocolos", "ouvidoria_acessos"}

    def test_a_funcao_nao_tem_bloco_exception(self):
        """O log NÃO é fail-open aqui dentro. Um `EXCEPTION WHEN OTHERS` engole
        a falha do `INSERT`, a função devolve a contagem como se nada tivesse
        acontecido, e o lote volta a ficar arquivado sem rastro, agora com a
        transação inteira verde e sem nem o log de aplicação para contar."""
        _, sql = _migration_do_lote()

        _, corpo = _declaracao_e_corpo(sql, RPC_DO_LOTE)

        assert not _tem_bloco_exception(corpo)

    def test_o_recorte_do_lote_continua_no_update(self):
        """O recorte mudou de lado nesta issue: era `.eq()` e `.is_()` em
        Python, e agora vive no SQL. Os testes do lote que provam que o caso em
        andamento fica intocado e que a leva antiga não é regravada passaram a
        exercer o Supabase falso, e não o banco: é este guarda que os impede de
        virar vácuo se a linha do filtro sumir da migration."""
        _, sql = _migration_do_lote()

        _, corpo = _declaracao_e_corpo(sql, RPC_DO_LOTE)

        assert _recorte_do_update(corpo) == {"so_encerrado", "so_sem_arquivo"}

    def test_o_update_carimba_as_duas_colunas_do_arquivo(self):
        """Quem e quando andam juntos desde a migration 099. Um `UPDATE` que
        esquecesse `arquivada_por` esconderia o caso sem dizer por quem, com o
        log de acesso gravado do mesmo jeito e a contagem certa na tela."""
        _, sql = _migration_do_lote()

        _, corpo = _declaracao_e_corpo(sql, RPC_DO_LOTE)

        assert _carimbos_do_update(corpo) == {"arquivada_em", "arquivada_por"}

    def test_a_contagem_volta_como_linha_e_nao_como_escalar(self):
        """O par de `test_o_cliente_de_verdade_recusa_a_contagem_escalar`:
        aquele prova que o cliente recusa o escalar, este prova que a migration
        não manda escalar. Sem os dois, `RETURNS INTEGER` passaria aqui e
        quebraria o lote em produção DEPOIS do commit."""
        _, sql = _migration_do_lote()

        declaracao, _ = _declaracao_e_corpo(sql, RPC_DO_LOTE)

        assert re.search(r"RETURNS\s+TABLE\s*\(\s*arquivadas\b", declaracao, re.IGNORECASE), declaracao

    def test_os_parametros_da_rota_sao_os_da_funcao(self, monkeypatch):
        """No Postgres a função é o nome MAIS os argumentos, e o PostgREST casa
        a chamada pelos NOMES deles. Uma rota que mandasse `p_ator` para uma
        função que declara `p_ator_id` levaria PGRST202 em produção com tudo
        verde aqui, porque o Supabase falso aceita qualquer dicionário.

        O lado da rota é lido de uma chamada de verdade, e não do código: é a
        mesma chamada que a produção faz."""
        _, sql = _migration_do_lote()
        declaracao, _ = _declaracao_e_corpo(sql, RPC_DO_LOTE)
        client, supabase = _client(monkeypatch, casos=[_caso(1)])

        assert _arquivar_o_lote(client).status_code == 200

        nome, params = supabase.rpcs[-1]
        assert nome == RPC_DO_LOTE
        assert sorted(params) == sorted(_parametros(declaracao))

    def test_a_rpc_do_lote_perde_o_execute_das_roles_do_bundle(self):
        """A função ESCREVE em duas tabelas, e o `ALTER DEFAULT PRIVILEGES` do
        Supabase concede EXECUTE a `anon` e `authenticated` por nome no momento
        em que ela nasce (a lição das migrations 095 e 097). O `REVOKE` e o
        `GRANT` são cobrados com a ASSINATURA, e não só com o nome: fechar
        `(TEXT, TEXT)` onde a função declara `(VARCHAR, TEXT)` fecha uma função
        que não existe e deixa a de verdade aberta."""
        _, sql = _migration_do_lote()
        limpo = _sem_comentarios(sql)

        revogado = re.search(
            rf"REVOKE\s+EXECUTE\s+ON\s+FUNCTION\s+{RPC_DO_LOTE}\s*\(\s*VARCHAR\s*,\s*TEXT\s*\)\s*FROM\s+([^;]+);",
            limpo,
            re.IGNORECASE,
        )
        assert revogado is not None, "sem REVOKE com a assinatura certa, a anon_key alcança o corpo da função"
        for role in ("PUBLIC", "anon", "authenticated"):
            assert re.search(rf"\b{role}\b", revogado.group(1), re.IGNORECASE), role

        assert re.search(
            rf"GRANT\s+EXECUTE\s+ON\s+FUNCTION\s+{RPC_DO_LOTE}\s*\(\s*VARCHAR\s*,\s*TEXT\s*\)\s*TO\s+service_role\s*;",
            limpo,
            re.IGNORECASE,
        ), "sem o GRANT explícito, o backend fica dependendo do default privilege que criou este tipo de furo"


class TestOsGuardasDoSQLReprovamOQueDevem:
    """Os detectores da classe acima, exercitados nos dois sentidos contra SQL
    sintético. Sem esta classe, uma regex que deixasse de casar transformaria
    todos os guardas de cima em vácuo silencioso."""

    FUNCAO_CERTA = """
    CREATE OR REPLACE FUNCTION ouvidoria_arquivar_encerrados(p_ator_id VARCHAR, p_ator_nome TEXT)
    RETURNS TABLE (arquivadas INTEGER)
    LANGUAGE plpgsql
    AS $$
    BEGIN
      -- Sem EXCEPTION aqui, de proposito.
      WITH c AS (UPDATE ouvidoria_protocolos SET arquivada_em = now(), arquivada_por = p_ator_id
                  WHERE status = 'encerrado' AND arquivada_em IS NULL RETURNING id)
      SELECT array_agg(id) INTO v FROM c;
      INSERT INTO ouvidoria_acessos (manifestacao_id) SELECT unnest(v);
      RETURN NEXT;
    END;
    $$;
    """

    def test_o_guarda_do_exception_ignora_a_palavra_em_comentario(self):
        """O sentido que mantém o arquivo de verdade verde: o cabeçalho da
        migration explica o bloco que ela não tem, e essa explicação não pode
        reprovar a própria migration."""
        _, corpo = _declaracao_e_corpo(self.FUNCAO_CERTA, "ouvidoria_arquivar_encerrados")

        assert not _tem_bloco_exception(corpo)

    def test_o_guarda_do_exception_pega_o_fail_open_de_verdade(self):
        """O mutante que a issue #627 existe para impedir."""
        fail_open = self.FUNCAO_CERTA.replace(
            "RETURN NEXT;",
            "RETURN NEXT;\n    EXCEPTION WHEN OTHERS THEN\n      RETURN NEXT;",
        )

        _, corpo = _declaracao_e_corpo(fail_open, "ouvidoria_arquivar_encerrados")

        assert _tem_bloco_exception(corpo)

    def test_o_guarda_das_escritas_pega_o_log_que_saiu_do_corpo(self):
        """A outra forma de reabrir a janela: o `INSERT` continua no arquivo,
        mas DEPOIS do `END`. São duas transações de novo, e um guarda que só
        procurasse a string no arquivo inteiro ficaria verde."""
        fora = self.FUNCAO_CERTA.replace(
            "INSERT INTO ouvidoria_acessos (manifestacao_id) SELECT unnest(v);", ""
        ).replace("$$;", "$$;\n    INSERT INTO ouvidoria_acessos (manifestacao_id) VALUES ('x');")

        _, corpo = _declaracao_e_corpo(fora, "ouvidoria_arquivar_encerrados")

        assert _escritas_do_corpo(corpo) == {"ouvidoria_protocolos"}

    def test_o_guarda_das_escritas_pega_o_update_que_saiu_do_corpo(self):
        """O sentido espelhado: o carimbo por fora e o log por dentro erram
        exatamente igual, e um guarda que só olhasse o `INSERT` não veria."""
        sem_update = self.FUNCAO_CERTA.replace("UPDATE ouvidoria_protocolos", "SELECT id FROM ouvidoria_protocolos")

        _, corpo = _declaracao_e_corpo(sem_update, "ouvidoria_arquivar_encerrados")

        assert _escritas_do_corpo(corpo) == {"ouvidoria_acessos"}

    def test_o_guarda_do_recorte_le_as_duas_condicoes(self):
        _, corpo = _declaracao_e_corpo(self.FUNCAO_CERTA, "ouvidoria_arquivar_encerrados")

        assert _recorte_do_update(corpo) == {"so_encerrado", "so_sem_arquivo"}

    @pytest.mark.parametrize(
        ("apagado", "sobra"),
        [
            ("status = 'encerrado' AND ", {"so_sem_arquivo"}),
            (" AND arquivada_em IS NULL", {"so_encerrado"}),
        ],
        ids=["sem_o_filtro_de_estado", "sem_o_filtro_do_arquivo"],
    )
    def test_o_guarda_do_recorte_pega_a_condicao_que_sumiu(self, apagado, sobra):
        """Um mutante por condição, porque um guarda que só olhasse uma delas
        ficaria verde sobre a outra. Sem o estado, o lote esconde caso em
        andamento; sem o arquivo, ele reescreve o autor da leva antiga."""
        mutante = self.FUNCAO_CERTA.replace(apagado, "")

        _, corpo = _declaracao_e_corpo(mutante, "ouvidoria_arquivar_encerrados")

        assert _recorte_do_update(corpo) == sobra

    def test_o_guarda_dos_carimbos_pega_o_autor_que_sumiu(self):
        sem_autor = self.FUNCAO_CERTA.replace(", arquivada_por = p_ator_id", "")

        _, corpo = _declaracao_e_corpo(sem_autor, "ouvidoria_arquivar_encerrados")

        assert _carimbos_do_update(corpo) == {"arquivada_em"}

    def test_o_leitor_de_parametros_le_os_nomes_na_ordem(self):
        declaracao, _ = _declaracao_e_corpo(self.FUNCAO_CERTA, "ouvidoria_arquivar_encerrados")

        assert _parametros(declaracao) == ["p_ator_id", "p_ator_nome"]

    def test_o_leitor_de_parametros_aguenta_o_tipo_com_parenteses(self):
        """`VARCHAR(10)` tem parênteses dentro, e é o tipo da coluna que guarda
        o ator. Um leitor que cortasse no primeiro `)` devolveria lista torta e
        o teste dos parâmetros ficaria verde sobre metade da assinatura."""
        com_tamanho = self.FUNCAO_CERTA.replace("p_ator_id VARCHAR", "p_ator_id VARCHAR(10)")

        declaracao, _ = _declaracao_e_corpo(com_tamanho, "ouvidoria_arquivar_encerrados")

        assert _parametros(declaracao) == ["p_ator_id", "p_ator_nome"]
