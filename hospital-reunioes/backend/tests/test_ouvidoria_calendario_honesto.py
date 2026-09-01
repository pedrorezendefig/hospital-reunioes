"""A leitura do calendário de feriados falha de forma visível (issue #449).

Follow-up da #430. `carregar_feriados` tinha um `except Exception` mudo: sem a
lista, o motor conta feriado como dia útil e o rótulo de prazo de cada linha do
painel sai errado com HTTP 200, sem nada na tela nem no log dizendo por quê.

Os testes daqui cobram três coisas do fail-open, que FICA:
- a causa engolida chega ao log (era `logger.warning` sem `exc_info`);
- a resposta distingue "calendário vazio" de "não consegui ler o calendário",
  com o mesmo vocabulário `degradado` que as métricas já usam;
- erro de programação (`AttributeError`, `TypeError`) SOBE, em vez de virar
  calendário vazio: foi esse `except` largo que deixou quatro arquivos de teste
  passarem verdes rodando com o calendário vazio.
"""

from __future__ import annotations

import datetime as dt
import logging
import os
import sys

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

OUVIDOR = {"id": "P10", "nome_completo": "Marta Ouvidora", "access_profile": None, "perfil_ouvidoria": "ouvidor"}

AGORA = dt.datetime(2026, 8, 26, 17, 0, tzinfo=dt.UTC)
# Uma quinta-feira DENTRO da janela do prazo: é ela que faz o calendário mudar
# o número. Sem feriado no meio, "ler" e "não ler" dariam a mesma conta e o
# teste passaria por falta de dente, não por acerto.
FERIADO_NO_MEIO = "2026-08-27"
CALENDARIO = [{"data": FERIADO_NO_MEIO, "nome": "Padroeira", "abrangencia": "municipal_rio"}]


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


def _caso() -> dict:
    """Uma manifestação com prazo da área: é o `prazo_area_em` que faz a
    listagem ler o calendário."""
    return {
        "id": "uuid-0001",
        "numero": 1,
        "protocolo": "2026-0001",
        "data_abertura": "2026-08-03",
        "contato_em": "2026-08-03T12:00:00+00:00",
        "status": "aguardando_area",
        "tipo_manifestacao": "reclamacao",
        "setor": "Recepcao",
        "resumo": "Paciente relata espera acima de duas horas na recepcao.",
        "canal": "ana",
        "gravidade": "medio",
        "sigilo_reforcado": False,
        "prazo_area_em": "2026-08-28T12:00:00+00:00",
        "prazo_rompido_em": None,
        "area_estourou_em": None,
        "validada_em": None,
        "respondida_em": None,
        "encerrada_em": None,
        "desfecho": None,
        "pausada_em": None,
        "minutos_pausados": 0,
        "reincidencia": False,
        "reaberta_em": None,
    }


class _TabelaFake:
    def __init__(self, nome: str, rows: list[dict], falha_no_execute: Exception | None = None):
        self.nome = nome
        self.rows = rows
        # A falha levantada DENTRO do `execute`, e não ao pegar a tabela. É onde
        # a falha de transporte nasce de verdade: o cliente PostgREST monta a
        # query sem tocar na rede e só chama o httpx no `execute` de cada
        # página, então fake que quebra no `table()` nunca exercita este caminho.
        self.falha_no_execute = falha_no_execute
        self._filters: dict = {}
        self._colunas: tuple[str, ...] | None = None
        self._janela: tuple[int, int] | None = None

    def select(self, colunas: str = "*", *_a, **_kw):
        if colunas.strip() != "*":
            self._colunas = tuple(c.strip() for c in colunas.split(","))
        return self

    def eq(self, col, value):
        self._filters[col] = value
        return self

    def order(self, _col, desc=False):
        return self

    def range(self, inicio: int, fim: int):
        self._janela = (inicio, fim)
        return self

    def execute(self):
        if self.falha_no_execute is not None:
            raise self.falha_no_execute
        casadas = [r for r in self.rows if all(r.get(c) == v for c, v in self._filters.items())]
        inicio, fim = self._janela or (0, len(casadas))
        recorte = casadas[inicio : fim + 1]
        if self._colunas is not None:
            recorte = [{c: r.get(c) for c in self._colunas} for r in recorte]
        return type("R", (), {"data": [dict(r) for r in recorte]})()


class _TabelaSemRecorte:
    """O fake mal montado: esqueceu o `range`. É exatamente o erro de
    programação que o `except Exception` largo transformava em calendário vazio,
    deixando o teste verde com o motor contando errado."""

    def select(self, *_a, **_kw):
        return self

    def order(self, *_a, **_kw):
        return self


class _SupabaseFake:
    def __init__(
        self,
        feriados: list[dict] | None = None,
        indisponiveis: set[str] | None = None,
        sem_recorte=False,
        falha_de_transporte: Exception | None = None,
    ):
        # Tabelas que o banco recusa a servir: é como o PostgREST fora do ar
        # chega na aplicação, DEPOIS de a resposta HTTP ter chegado.
        self.indisponiveis = indisponiveis or set()
        # Quando ligado, a leitura do calendário cai num fake sem `range`.
        self.sem_recorte = sem_recorte
        # A exceção que o httpx levanta ANTES de existir resposta: timeout,
        # conexão recusada. Nasce dentro do `execute` da leitura do calendário.
        self.falha_de_transporte = falha_de_transporte
        self.tabelas: dict[str, list[dict]] = {
            "ouvidoria_protocolos": [_caso()],
            "ouvidoria_feriados": [] if feriados is None else [dict(f) for f in feriados],
        }

    def table(self, nome: str):
        if nome in self.indisponiveis:
            raise APIError({"message": f"{nome} indisponivel", "code": "PGRST000"})
        if self.sem_recorte and nome == "ouvidoria_feriados":
            return _TabelaSemRecorte()
        falha = self.falha_de_transporte if nome == "ouvidoria_feriados" else None
        return _TabelaFake(nome, self.tabelas.setdefault(nome, []), falha)


def _client(monkeypatch, supabase: _SupabaseFake) -> TestClient:
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(RequestContextMiddleware)
    app.include_router(ouvidoria_router.router, prefix="/api")

    async def _fake_participante(_user, _sb, fields=None):
        return OUVIDOR

    monkeypatch.setattr(ouvidoria_router, "get_participante_for_user", _fake_participante)
    monkeypatch.setattr(ouvidoria_router, "agora_utc", lambda: AGORA)
    app.dependency_overrides[get_current_user] = lambda: {"id": "u1", "email": "u@hsm.br"}
    app.dependency_overrides[get_supabase_client] = lambda: supabase
    return TestClient(app)


def _listagem(monkeypatch, supabase: _SupabaseFake) -> dict:
    resposta = _client(monkeypatch, supabase).get("/api/ouvidoria/protocolos")
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


class TestOLogDizOQueFoiEngolido:
    def test_a_causa_da_falha_chega_ao_log(self, caplog):
        """O fail-open fica, mas o log passa a dizer O QUE foi engolido: sem a
        causa, quem lê o log sabe que faltou calendário e não tem como saber se
        foi o banco, a rede ou um bug."""
        supabase = _SupabaseFake(CALENDARIO, indisponiveis={"ouvidoria_feriados"})
        with caplog.at_level(logging.WARNING, logger="app.routers.ouvidoria"):
            feriados, degradado = ouvidoria_router.carregar_feriados_ou_degradado(supabase)
        assert feriados == frozenset(), "o fail-open é a promessa da função e não mudou"
        assert degradado == ["feriados"]
        assert "Falha ao carregar feriados" in caplog.text
        assert "APIError" in caplog.text, "o log não diz a causa: o warning saiu sem exc_info"
        assert "PGRST000" in caplog.text, "o log não diz nem o erro que o banco devolveu"


class TestVazioNaoEIlegivel:
    def test_a_funcao_separa_calendario_vazio_de_calendario_ilegivel(self):
        """Os dois casos devolvem o MESMO conjunto vazio, e é por isso que o
        número nunca vai poder distingui-los. Quem distingue é o `degradado`."""
        vazio, marca_do_vazio = ouvidoria_router.carregar_feriados_ou_degradado(_SupabaseFake([]))
        ilegivel, marca_do_ilegivel = ouvidoria_router.carregar_feriados_ou_degradado(
            _SupabaseFake(CALENDARIO, indisponiveis={"ouvidoria_feriados"})
        )
        assert vazio == ilegivel == frozenset()
        assert marca_do_vazio == [], "hospital sem feriado cadastrado não é falha de leitura"
        assert marca_do_ilegivel == ["feriados"]

    def test_a_listagem_diz_na_resposta_quando_nao_leu_o_calendario(self, monkeypatch):
        """A resposta do painel passa a carregar a marca. As outras portas ficam
        abertas de propósito: a listagem dos protocolos continua vindo inteira,
        então o teste mede a marca, e não um erro que apagou a resposta."""
        lido = _listagem(monkeypatch, _SupabaseFake(CALENDARIO))
        ilegivel = _listagem(monkeypatch, _SupabaseFake(CALENDARIO, indisponiveis={"ouvidoria_feriados"}))

        assert lido["degradado"] == []
        assert ilegivel["degradado"] == ["feriados"]
        # A porta dos protocolos estava aberta: a falha do calendário não
        # derrubou nem esvaziou a listagem, que é a promessa do fail-open.
        assert [linha["protocolo"] for linha in ilegivel["protocolos"]] == ["2026-0001"]
        assert ilegivel["protocolos"][0]["prazo_area_em"] == "2026-08-28T12:00:00+00:00"

    def test_o_numero_em_dias_uteis_nao_denuncia_a_falha_sozinho(self, monkeypatch):
        """Por que a marca é necessária: sem calendário o rótulo sai MAIOR (o
        feriado virou dia útil) e igualzinho ao de um hospital sem feriado
        nenhum. Nada na resposta separava os dois antes da marca."""
        com_feriado = _listagem(monkeypatch, _SupabaseFake(CALENDARIO))["protocolos"][0]
        sem_ler = _listagem(monkeypatch, _SupabaseFake(CALENDARIO, indisponiveis={"ouvidoria_feriados"}))["protocolos"][
            0
        ]
        sem_feriado_cadastrado = _listagem(monkeypatch, _SupabaseFake([]))["protocolos"][0]

        assert sem_ler["minutos_uteis_restantes"] > com_feriado["minutos_uteis_restantes"], (
            "o cenário não tem dente: o feriado do meio não mudou a conta"
        )
        assert sem_ler["minutos_uteis_restantes"] == sem_feriado_cadastrado["minutos_uteis_restantes"]
        assert sem_ler["rotulo_prazo"] == sem_feriado_cadastrado["rotulo_prazo"]


# As falhas de transporte do httpx, que nascem ANTES de existir resposta HTTP e
# por isso não são `APIError`. Nenhuma delas é subclasse de `OSError`: todas
# herdam de `httpx.HTTPError`, que herda direto de `Exception`. É a falha mais
# provável de todas em produção, e sem ela na tupla o fail-open viraria
# fail-closed no primeiro blip de rede.
FALHAS_DE_TRANSPORTE = [
    pytest.param(httpx.ReadTimeout("o banco não respondeu no tempo"), id="read-timeout"),
    pytest.param(httpx.ConnectError("conexão recusada"), id="connect-error"),
    pytest.param(httpx.PoolTimeout("pool de conexões estourado"), id="pool-timeout"),
]


class TestFalhaDeRedeNaoDerrubaAPagina:
    """O fail-open FICA, e é justamente na falha de rede que ele mais importa.

    A tupla estreitada tem que continuar cobrindo transporte: se não cobrir, um
    timeout do banco derruba a página com 500 em vez de abri-la marcada, e a
    issue #449 pediu o contrário."""

    @pytest.mark.parametrize("falha", FALHAS_DE_TRANSPORTE)
    def test_timeout_na_leitura_do_calendario_abre_o_painel_marcado(self, monkeypatch, falha):
        corpo = _listagem(monkeypatch, _SupabaseFake(CALENDARIO, falha_de_transporte=falha))
        assert corpo["degradado"] == ["feriados"]
        # A porta dos protocolos ficou aberta: a rede caiu só na leitura do
        # calendário, e o painel abriu com a listagem inteira.
        assert [linha["protocolo"] for linha in corpo["protocolos"]] == ["2026-0001"]

    @pytest.mark.parametrize("falha", FALHAS_DE_TRANSPORTE)
    def test_a_funcao_devolve_o_fail_open_marcado_e_loga_a_causa(self, caplog, falha):
        with caplog.at_level(logging.WARNING, logger="app.routers.ouvidoria"):
            feriados, degradado = ouvidoria_router.carregar_feriados_ou_degradado(
                _SupabaseFake(CALENDARIO, falha_de_transporte=falha)
            )
        assert (feriados, degradado) == (frozenset(), ["feriados"])
        assert type(falha).__name__ in caplog.text, "o log não diz que a causa foi transporte"

    @pytest.mark.parametrize("falha", FALHAS_DE_TRANSPORTE)
    def test_o_caminho_de_escrita_tambem_segue_de_pe(self, falha):
        """`carregar_feriados`, o wrapper que os ~13 pontos de escrita e os jobs
        de cron usam, herda a mesma tupla. Timeout ali abortaria o ato no meio,
        e na pausa e na retomada a leitura acontece DEPOIS da transição já
        comitada: a resposta perderia a mensagem acionável que o próprio código
        escreve para esse estado."""
        assert ouvidoria_router.carregar_feriados(_SupabaseFake(CALENDARIO, falha_de_transporte=falha)) == frozenset()


class TestErroDeProgramacaoSobe:
    def test_fake_sem_range_derruba_o_teste_em_vez_de_virar_calendario_vazio(self):
        """O que a issue veio comprar: `AttributeError` SOBE. Quatro arquivos de
        teste ficaram verdes rodando com calendário vazio porque o `except`
        largo engoliu justamente este erro."""
        with pytest.raises(AttributeError):
            ouvidoria_router.carregar_feriados_ou_degradado(_SupabaseFake(CALENDARIO, sem_recorte=True))

    def test_o_mesmo_fake_com_range_le_o_calendario(self):
        """A outra ponta do teste acima: o cenário não é vermelho por estar
        quebrado de fábrica, e o caminho feliz devolve o feriado."""
        feriados, degradado = ouvidoria_router.carregar_feriados_ou_degradado(_SupabaseFake(CALENDARIO))
        assert feriados == frozenset({dt.date.fromisoformat(FERIADO_NO_MEIO)})
        assert degradado == []

    def test_data_malformada_no_banco_continua_no_fail_open(self):
        """Onde o `except` continua largo de propósito: uma data que não parseia
        é dado ruim, não bug de código, e a promessa é a tela abrir."""
        feriados, degradado = ouvidoria_router.carregar_feriados_ou_degradado(
            _SupabaseFake([{"data": "31/12/2026", "nome": "Malformada", "abrangencia": "nacional"}])
        )
        assert feriados == frozenset()
        assert degradado == ["feriados"]
