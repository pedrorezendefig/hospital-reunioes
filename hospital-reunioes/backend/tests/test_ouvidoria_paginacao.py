"""Paginação explícita contra o teto do PostgREST (issue #430, PRD #399).

O PostgREST aceita um teto de linhas por resposta (`PGRST_DB_MAX_ROWS`). Ligado,
ele corta TODA leitura sem `range` no teto, devolvendo HTTP 200 e menos linhas:
a métrica sai menor sem erro nenhum na tela, que é o modo de falha mais caro que
um módulo de números pode ter.

O fake daqui é o mesmo PostgREST dos outros testes da Ouvidoria com uma peça a
mais, a que interessa: um `teto_de_linhas` que limita CADA resposta, exatamente
como o servidor configurado faria. Os testes conferem o número, não o caminho:
com o teto ligado, o número tem que ser o mesmo de sem teto.
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
from app.services import ouvidoria_metricas  # noqa: E402

OUVIDOR = {"id": "P10", "nome_completo": "Marta Ouvidora", "access_profile": None, "perfil_ouvidoria": "ouvidor"}

INICIO = "2026-08-01"
FIM = "2026-08-31"
AGORA = dt.datetime(2026, 8, 26, 17, 0, tzinfo=dt.UTC)

# Bem acima de qualquer teto usado aqui: é o volume que faz o corte aparecer.
CASOS = 250
# O teto do servidor fingido. Pequeno de propósito, para o corte bater várias
# vezes dentro de um lote de ids (`LOTE_DE_IDS` é 100).
TETO = 40


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


def _caso(numero: int, **overrides) -> dict:
    """Uma manifestação no molde da tabela real (migrations 063 a 078)."""
    row = {
        "id": f"uuid-{numero:04d}",
        "numero": numero,
        "protocolo": f"2026-{numero:04d}",
        "data_abertura": "2026-08-03",
        "contato_em": "2026-08-03T12:00:00+00:00",
        "status": "encerrado",
        "tipo_manifestacao": "reclamacao",
        "setor": "Recepcao",
        "resumo": "Paciente relata espera acima de duas horas na recepcao.",
        "canal": "ana",
        "gravidade": "medio",
        "sigilo_reforcado": False,
        "prazo_area_em": None,
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
    row.update(overrides)
    return row


PRAZOS = [
    {"gravidade": gravidade, "marco": marco, "valor": 2, "unidade": "dias_uteis"}
    for gravidade in ("critico", "alto", "medio", "baixo")
    for marco in ("triagem", "area_resposta", "conclusiva")
]


def _chave_de_ordem(valor):
    """Ordena como o banco: número por grandeza, texto por caractere. Ordenar
    `numero` como string faria o 250 vir antes do 3 e a asserção de ordem da
    listagem cobrar do código um defeito do fake."""
    return (valor is None, valor) if isinstance(valor, (int, float)) else (valor is None, str(valor or ""))


class _TabelaFake:
    """Fake do PostgREST fiel no que importa aqui: o `range` recorta a janela e
    o `teto_de_linhas` corta a resposta por cima dela, como o servidor com
    `PGRST_DB_MAX_ROWS` faz, sem avisar."""

    def __init__(self, nome: str, rows: list[dict], teto_de_linhas: int | None, chamadas: list[tuple]):
        self.nome = nome
        self.rows = rows
        self.teto_de_linhas = teto_de_linhas
        self.chamadas = chamadas
        self._filters: dict = {}
        self._in: dict = {}
        self._gte: dict = {}
        self._lte: dict = {}
        self._colunas: tuple[str, ...] | None = None
        self._ordem: list[tuple[str, bool]] = []
        self._janela: tuple[int, int] | None = None

    def select(self, colunas: str = "*", *_a, **_kw):
        if colunas.strip() != "*":
            self._colunas = tuple(c.strip() for c in colunas.split(","))
        return self

    def eq(self, col, value):
        self._filters[col] = value
        return self

    def in_(self, col, values):
        self._in[col] = list(values)
        return self

    def gte(self, col, value):
        self._gte[col] = value
        return self

    def lte(self, col, value):
        self._lte[col] = value
        return self

    def order(self, col, desc=False):
        self._ordem.append((col, desc))
        return self

    def range(self, inicio: int, fim: int):
        self._janela = (inicio, fim)
        return self

    def _projetar(self, row: dict) -> dict:
        if self._colunas is None:
            return dict(row)
        return {c: row.get(c) for c in self._colunas}

    def execute(self):
        casadas = [
            r
            for r in self.rows
            if all(r.get(c) == v for c, v in self._filters.items())
            and all(r.get(c) in v for c, v in self._in.items())
            and all(str(r.get(c) or "") >= v for c, v in self._gte.items())
            and all(str(r.get(c) or "") <= v for c, v in self._lte.items())
        ]
        for col, desc in reversed(self._ordem):
            casadas = sorted(casadas, key=lambda r: _chave_de_ordem(r.get(col)), reverse=desc)
        # A ordem de quem NÃO pediu `order` é a do banco: aqui, arbitrária de
        # propósito, porque paginar sem ordenação estável é bug esperando data.
        if not self._ordem:
            casadas = list(reversed(casadas))
        inicio, fim = self._janela or (0, len(casadas))
        recorte = casadas[inicio : fim + 1]
        self.chamadas.append((self.nome, self._janela, tuple(self._ordem)))
        if self.teto_de_linhas is not None:
            recorte = recorte[: self.teto_de_linhas]
        return type("R", (), {"data": [self._projetar(r) for r in recorte]})()


class _SupabaseFake:
    def __init__(self, casos: list[dict], teto_de_linhas: int | None = None, **tabelas):
        self.teto_de_linhas = teto_de_linhas
        # O que cada leitura pediu, para o teste conseguir provar a ordenação
        # sem inspecionar SQL.
        self.chamadas: list[tuple] = []
        self.tabelas: dict[str, list[dict]] = {
            "ouvidoria_protocolos": casos,
            "ouvidoria_prorrogacoes": [],
            "ouvidoria_setor_responsaveis": [],
            "ouvidoria_prazos": [dict(p) for p in PRAZOS],
            "ouvidoria_feriados": [],
        }
        self.tabelas.update(tabelas)

    def table(self, nome: str):
        return _TabelaFake(nome, self.tabelas.setdefault(nome, []), self.teto_de_linhas, self.chamadas)


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


def _metricas(client: TestClient) -> dict:
    resposta = client.get(f"/api/ouvidoria/metricas?inicio={INICIO}&fim={FIM}")
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


def test_volume_do_periodo_ignora_o_teto_do_servidor(monkeypatch):
    """O agregado do período conta os 250 casos, e não as 40 que couberam na
    primeira resposta."""
    supabase = _SupabaseFake([_caso(n) for n in range(1, CASOS + 1)], teto_de_linhas=TETO)
    dados = _metricas(_client(monkeypatch, supabase))
    assert dados["volume"]["total"] == CASOS
    assert dados["volume"]["por_canal"][0]["total"] == CASOS


def test_fila_viva_do_painel_ignora_o_teto_do_servidor(monkeypatch):
    """As pendências por área leem a fila viva inteira: com o teto agindo, a
    área apareceria devendo 40 respostas em vez de 250."""
    casos = [
        _caso(
            n,
            status="aguardando_area",
            validada_em="2026-08-04T12:00:00+00:00",
            prazo_area_em="2026-08-10T12:00:00+00:00",
        )
        for n in range(1, CASOS + 1)
    ]
    supabase = _SupabaseFake(casos, teto_de_linhas=TETO)
    dados = _metricas(_client(monkeypatch, supabase))
    assert sum(linha["pendentes"] for linha in dados["pendencias_por_area"]) == CASOS


def test_prorrogacoes_do_periodo_ignoram_o_teto_do_servidor(monkeypatch):
    """A taxa de prorrogação lê os pedidos em lotes de ids; o teto corta DENTRO
    do lote e a taxa sairia menor que a real."""
    casos = [_caso(n, prazo_area_em="2026-08-10T12:00:00+00:00") for n in range(1, CASOS + 1)]
    prorrogacoes = [
        {
            "id": f"pror-{n:04d}",
            "manifestacao_id": f"uuid-{n:04d}",
            "status": "aprovada",
            "prazo_anterior": "2026-08-10T12:00:00+00:00",
            "prazo_novo": "2026-08-12T12:00:00+00:00",
        }
        for n in range(1, CASOS + 1)
    ]
    supabase = _SupabaseFake(casos, teto_de_linhas=TETO, ouvidoria_prorrogacoes=prorrogacoes)
    dados = _metricas(_client(monkeypatch, supabase))
    assert dados["prorrogacao"]["casos"] == CASOS
    assert dados["prorrogacao"]["taxa_pct"] == 100.0


def test_responsaveis_de_todos_os_setores_ignoram_o_teto(monkeypatch):
    """Quem responde pela área sai do cadastro inteiro: cortado no teto, o
    último setor da lista apareceria pendente e sem dono."""
    casos = [
        _caso(
            n,
            setor=f"Setor {n:04d}",
            status="aguardando_area",
            validada_em="2026-08-04T12:00:00+00:00",
            prazo_area_em="2026-08-10T12:00:00+00:00",
        )
        for n in range(1, CASOS + 1)
    ]
    responsaveis = [
        {
            "id": f"resp-{n:04d}",
            "setor": f"Setor {n:04d}",
            "papel": "titular",
            "nome": f"Titular {n:04d}",
            "vigencia_inicio": "2026-01-01",
            "vigencia_fim": None,
        }
        for n in range(1, CASOS + 1)
    ]
    supabase = _SupabaseFake(casos, teto_de_linhas=TETO, ouvidoria_setor_responsaveis=responsaveis)
    dados = _metricas(_client(monkeypatch, supabase))
    assert len(dados["pendencias_por_area"]) == CASOS
    assert all(linha["responsavel"] for linha in dados["pendencias_por_area"])


def test_calendario_util_ignora_o_teto():
    """O calendário cresce um punhado de linhas por ano: cortado, o feriado do
    fim da lista voltaria a contar como dia útil e todo prazo sairia diferente."""
    feriados = [
        {"data": (dt.date(2026, 1, 1) + dt.timedelta(days=n)).isoformat(), "nome": f"F{n}", "abrangencia": "nacional"}
        for n in range(CASOS)
    ]
    supabase = _SupabaseFake([], teto_de_linhas=TETO, ouvidoria_feriados=feriados)
    assert len(ouvidoria_metricas._feriados(supabase)) == CASOS


def test_tabela_de_prazos_ignora_o_teto():
    """A régua de prazo tem uma linha por (gravidade, marco): faltando uma, o
    trecho correspondente sai sem prazo em vez de sair medido."""
    supabase = _SupabaseFake([], teto_de_linhas=5)
    assert len(ouvidoria_metricas._tabela_de_prazos(supabase)) == len(PRAZOS)


def test_listagem_de_protocolos_ignora_o_teto_do_servidor(monkeypatch):
    """A listagem que alimenta os contadores do painel (issue #402) devolve
    todos os protocolos, e não os que couberam na primeira resposta."""
    supabase = _SupabaseFake([_caso(n) for n in range(1, CASOS + 1)], teto_de_linhas=TETO)
    resposta = _client(monkeypatch, supabase).get("/api/ouvidoria/protocolos")
    assert resposta.status_code == 200, resposta.text
    protocolos = resposta.json()["protocolos"]
    assert len(protocolos) == CASOS
    # Sem repetição nem buraco: paginar sem ordenação estável devolveria os dois.
    assert len({p["id"] for p in protocolos}) == CASOS
    # A ordem prometida pela rota sobrevive à paginação.
    assert [p["numero"] for p in protocolos] == sorted((p["numero"] for p in protocolos), reverse=True)


def test_sem_teto_os_numeros_sao_os_mesmos(monkeypatch):
    """A paginação não pode mudar nada onde não há teto: mesmo cenário, mesmos
    números com e sem corte."""
    casos = [
        _caso(
            n,
            setor=f"Setor {n % 7}",
            status="aguardando_area" if n % 2 else "encerrado",
            validada_em="2026-08-04T12:00:00+00:00",
            prazo_area_em="2026-08-10T12:00:00+00:00",
            reincidencia=n % 5 == 0,
        )
        for n in range(1, CASOS + 1)
    ]
    sem_teto = _metricas(_client(monkeypatch, _SupabaseFake([dict(c) for c in casos])))
    com_teto = _metricas(_client(monkeypatch, _SupabaseFake([dict(c) for c in casos], teto_de_linhas=TETO)))
    assert com_teto == sem_teto
    assert sem_teto["volume"]["total"] == CASOS


def test_leituras_integrais_pedem_ordenacao_estavel(monkeypatch):
    """Paginar sem `order` é sorteio: a página seguinte pode repetir ou pular
    linha. Toda leitura que passou a ser paginada tem que pedir ordem."""
    casos = [_caso(n, status="aguardando_area", validada_em="2026-08-04T12:00:00+00:00") for n in range(1, CASOS + 1)]
    supabase = _SupabaseFake(casos, teto_de_linhas=TETO, ouvidoria_setor_responsaveis=[])
    _metricas(_client(monkeypatch, supabase))
    assert supabase.chamadas, "nenhuma leitura chegou ao banco"
    sem_recorte = [chamada for chamada in supabase.chamadas if chamada[1] is None]
    assert not sem_recorte, f"leitura integral sem paginação: {sem_recorte}"
    sem_ordem = [chamada for chamada in supabase.chamadas if not chamada[2]]
    assert not sem_ordem, f"leitura paginada sem ordenação estável: {sem_ordem}"
