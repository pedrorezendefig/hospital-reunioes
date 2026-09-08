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
"""

from __future__ import annotations

import datetime as dt
import os
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
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

    def update(self, payload: dict):
        self._update = payload
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
            return type("R", (), {"data": gravados})()
        casadas = [r for r in self.rows if all(teste(r) for teste in self._filtros)]
        if self._update is not None:
            for r in casadas:
                r.update(self._update)
            return type("R", (), {"data": [dict(r) for r in casadas]})()
        if self._janela is not None:
            inicio, fim = self._janela
            casadas = casadas[inicio : fim + 1]
        projetadas = [self._projetar(r) for r in casadas]
        if self.ao_ler is not None and casadas:
            self.ao_ler(casadas)
        return type("R", (), {"data": projetadas})()


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


class _SupabaseFake:
    def __init__(self, casos: list[dict], movimentos: list[dict] | None = None):
        # Quando preenchido, roda uma vez logo depois do primeiro select em
        # `ouvidoria_protocolos` e some. Simula a reabertura concorrente.
        self.reabre_no_meio_da_leitura = False
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
        return _TabelaFake(nome, self.tabelas.setdefault(nome, []), ao_ler)

    def rpc(self, nome: str, params: dict | None = None):
        if nome == "ouvidoria_ultimo_movimento":
            ultimo: dict[str, str] = {}
            for mov in self.tabelas["ouvidoria_movimentos"]:
                caso = str(mov["manifestacao_id"])
                ultimo[caso] = max(str(mov["ocorrido_em"]), ultimo.get(caso, ""))
            return _AgregadoFake([{"manifestacao_id": c, "ultimo_movimento_em": q} for c, q in ultimo.items()])
        raise AssertionError(f"Arquivar não passa por RPC nenhuma, e esta chegou: {nome}")


def _client(monkeypatch, casos: list[dict] | None = None, participante: dict | None = None, movimentos=None):
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(RequestContextMiddleware)
    app.include_router(ouvidoria_router.router, prefix="/api")

    relogio = _Relogio(INICIO)
    supabase = _SupabaseFake(casos if casos is not None else [_caso()], movimentos)
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
