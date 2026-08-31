"""Módulo de métricas do período da Ouvidoria (issue #341, PRD #319).

O módulo fundo que responde os números de qualquer intervalo de datas: volume,
prazo cumprido por trecho, pendências e ranking por área, prorrogação,
reincidência, tempo pausado e os cinco temas e áreas mais frequentes. O painel
(fatia I2) e os relatórios (fatias I3 e I5) consomem esta MESMA interface, e é
isso que impede o número da tela de divergir do número do PDF.

Os testes montam o cenário pelo seam HTTP, como o resto da Ouvidoria, e
conferem os números agregados. Nenhum teste olha o SQL da agregação: o que a
issue promete é o número, não o caminho até ele.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys

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
from app.routers import ouvidoria_publica  # noqa: E402
from app.services import ouvidoria_notificacoes  # noqa: E402
from app.services.ouvidoria_taxonomia import CATEGORIA_PENDENTE, SETOR_PENDENTE  # noqa: E402

OUVIDOR = {"id": "P10", "nome_completo": "Marta Ouvidora", "access_profile": None, "perfil_ouvidoria": "ouvidor"}
DIRETORIA = {
    "id": "P11",
    "nome_completo": "Helena Diretora",
    "access_profile": None,
    "perfil_ouvidoria": "diretoria_executiva",
}
# As outras portas do app, todas abertas, e nenhuma delas vale aqui: o gate da
# Ouvidoria não tem bypass de super admin (ADR 0034, decisão 8).
SUPER_ADMIN = {"id": "P01", "nome_completo": "Pedro Admin", "access_profile": "super_admin", "perfil_ouvidoria": None}
SECRETARIA = {
    "id": "P02",
    "nome_completo": "Sofia Secretaria",
    "access_profile": "secretaria",
    "perfil_ouvidoria": None,
}

# Agosto de 2026 é o período medido; julho é o anterior com que ele se compara.
INICIO = "2026-08-01"
FIM = "2026-08-31"
# Quarta-feira, 14h de Brasília: dentro do expediente, no meio do período.
AGORA = dt.datetime(2026, 8, 26, 17, 0, tzinfo=dt.UTC)


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


def _caso(numero: int, **overrides) -> dict:
    """Uma manifestação no molde da tabela real (migrations 063 a 078)."""
    abertura = overrides.pop("data_abertura", "2026-08-03")
    row = {
        "id": f"uuid-{numero}",
        "numero": numero,
        "protocolo": f"2026-{numero:04d}",
        "data_abertura": abertura,
        "contato_em": f"{abertura}T12:00:00+00:00",
        "status": "encerrado",
        "categoria": "Demora no atendimento",
        "tipo_manifestacao": "reclamacao",
        "setor": "Recepcao",
        "resumo": "Paciente relata espera acima de duas horas na recepcao.",
        "conversa_id": "",
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


def _responsavel(setor: str = "Recepcao", **overrides) -> dict:
    row = {
        "id": f"resp-{setor}",
        "setor": setor,
        "papel": "titular",
        "nome": "Carlos Titular",
        "email": "carlos@hsm.br",
        "vigencia_inicio": "2026-01-01",
        "vigencia_fim": None,
    }
    row.update(overrides)
    return row


# A tabela de prazos como a migration 065 semeia (RN-21).
PRAZOS = [
    {"gravidade": "critico", "marco": "triagem", "valor": 0, "unidade": "horas_uteis"},
    {"gravidade": "critico", "marco": "area_resposta", "valor": 4, "unidade": "horas_uteis"},
    {"gravidade": "critico", "marco": "conclusiva", "valor": None, "unidade": "dias_uteis"},
    {"gravidade": "alto", "marco": "triagem", "valor": 4, "unidade": "horas_uteis"},
    {"gravidade": "alto", "marco": "area_resposta", "valor": 2, "unidade": "dias_uteis"},
    {"gravidade": "alto", "marco": "conclusiva", "valor": 5, "unidade": "dias_uteis"},
    {"gravidade": "medio", "marco": "triagem", "valor": 1, "unidade": "dias_uteis"},
    {"gravidade": "medio", "marco": "area_resposta", "valor": 4, "unidade": "dias_uteis"},
    {"gravidade": "medio", "marco": "conclusiva", "valor": 7, "unidade": "dias_uteis"},
    {"gravidade": "baixo", "marco": "triagem", "valor": 1, "unidade": "dias_uteis"},
    {"gravidade": "baixo", "marco": "area_resposta", "valor": None, "unidade": "dias_uteis"},
    {"gravidade": "baixo", "marco": "conclusiva", "valor": 2, "unidade": "dias_uteis"},
]


class _TabelaFake:
    """Fake do PostgREST fiel no que importa: o select projeta só o que foi
    pedido e os filtros de intervalo filtram como lá."""

    def __init__(
        self,
        nome: str,
        rows: list[dict],
        relogio_do_banco: dt.datetime | None = None,
        colunas_lidas: dict[str, set[str]] | None = None,
    ):
        self.nome = nome
        self.rows = rows
        # O que cada leitura pediu ao banco, para o teste de minimização
        # conseguir perguntar isso sem inspecionar o SQL (issue #429).
        self.colunas_lidas = colunas_lidas if colunas_lidas is not None else {}
        self.relogio_do_banco = relogio_do_banco or dt.datetime(2026, 8, 3, 12, 0, tzinfo=dt.UTC)
        self._filters: dict = {}
        self._in: dict = {}
        self._gte: dict = {}
        self._lte: dict = {}
        self._insert: dict | list | None = None
        self._update: dict | None = None
        self._colunas: tuple[str, ...] | None = None

    def select(self, colunas: str = "*", *_a, **_kw):
        if colunas.strip() != "*":
            self._colunas = tuple(c.strip() for c in colunas.split(","))
            self.colunas_lidas.setdefault(self.nome, set()).update(self._colunas)
        return self

    def eq(self, col, value):
        self._filters[col] = value
        return self

    def insert(self, payload):
        self._insert = payload
        return self

    def update(self, payload: dict):
        self._update = payload
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
        self.rows = sorted(self.rows, key=lambda r: str(r.get(col) or ""), reverse=desc)
        return self

    def _com_defaults_do_banco(self, linha: dict) -> dict:
        """Os defaults que as migrations 063 a 077 aplicam quando o cliente não
        manda a coluna. Sem eles o fake devolveria uma manifestação que o banco
        nunca produziria, e é exatamente aí que os furos de leitura se escondem.

        `data_abertura` sai do `CURRENT_DATE` do banco, e `contato_em` do
        `now()`: os dois do MESMO relógio, que é o do servidor, não o do
        hospital. É essa diferença que o teste do fuso explora."""
        agora_do_banco = self.relogio_do_banco
        padroes = {
            "numero": len(self.rows) + 1,
            "protocolo": f"2026-{len(self.rows) + 1:04d}",
            "data_abertura": agora_do_banco.date().isoformat(),
            "contato_em": agora_do_banco.isoformat(),
            "status": "em_classificacao",
            "tipo_manifestacao": None,
            "gravidade": None,
            "prazo_area_em": None,
            "area_estourou_em": None,
            "validada_em": None,
            "respondida_em": None,
            "encerrada_em": None,
            "pausada_em": None,
            "minutos_pausados": 0,
            "reincidencia": False,
            "reaberta_em": None,
        }
        return padroes | linha

    def _projetar(self, row: dict) -> dict:
        if self._colunas is None:
            return dict(row)
        return {c: row.get(c) for c in self._colunas}

    def range(self, inicio, fim):
        """O recorte de página do PostgREST (issue #430): as leituras integrais
        da Ouvidoria passaram a pedir a resposta em janelas."""
        self._janela = (inicio, fim)
        return self

    def execute(self):
        resposta = self._executar()
        dados = resposta.data or []
        inicio, fim = getattr(self, "_janela", None) or (0, len(dados))
        return type("R", (), {"data": dados[inicio : fim + 1]})()

    def _executar(self):
        if self._insert is not None:
            novos = self._insert if isinstance(self._insert, list) else [self._insert]
            gravados = []
            for novo in novos:
                linha = dict(novo)
                linha.setdefault("id", f"{self.nome}-{len(self.rows) + 1}")
                if self.nome == "ouvidoria_protocolos":
                    linha = self._com_defaults_do_banco(linha)
                self.rows.append(linha)
                gravados.append(dict(linha))
            return type("R", (), {"data": gravados})()
        casadas = [
            r
            for r in self.rows
            if all(r.get(c) == v for c, v in self._filters.items())
            and all(r.get(c) in v for c, v in self._in.items())
            and all(str(r.get(c) or "") >= v for c, v in self._gte.items())
            and all(str(r.get(c) or "") <= v for c, v in self._lte.items())
        ]
        if self._update is not None:
            atualizadas = []
            for r in casadas:
                r.update(self._update)
                atualizadas.append(dict(r))
            return type("R", (), {"data": atualizadas})()
        return type("R", (), {"data": [self._projetar(r) for r in casadas]})()


class _SupabaseFake:
    def __init__(self, casos: list[dict] | None = None, relogio_do_banco: dt.datetime | None = None, **tabelas):
        # O relógio do BANCO, que carimba `data_abertura` e `contato_em` nos
        # canais automáticos. Separado do relógio da aplicação de propósito.
        self.relogio_do_banco = relogio_do_banco or dt.datetime(2026, 8, 3, 12, 0, tzinfo=dt.UTC)
        # Tabelas que o banco recusa a servir, para exercitar a degradação.
        self.indisponiveis: set[str] = set()
        # Por tabela, as colunas que as leituras pediram (issue #429).
        self.colunas_lidas: dict[str, set[str]] = {}
        self.tabelas: dict[str, list[dict]] = {
            "ouvidoria_protocolos": casos if casos is not None else [],
            "ouvidoria_prorrogacoes": [],
            "ouvidoria_setor_responsaveis": [_responsavel()],
            "ouvidoria_prazos": [dict(p) for p in PRAZOS],
            "ouvidoria_feriados": [{"data": "2026-09-07", "nome": "Independencia", "abrangencia": "nacional"}],
        }
        self.tabelas.update(tabelas)

    def table(self, nome: str):
        if nome in self.indisponiveis:
            raise APIError({"message": f"{nome} indisponivel", "code": "PGRST000"})
        return _TabelaFake(nome, self.tabelas.setdefault(nome, []), self.relogio_do_banco, self.colunas_lidas)

    def rpc(self, nome: str, params: dict):
        """O efeito da função `ouvidoria_transicionar`: estado e movimento na
        mesma transação, como no banco (migration 064)."""
        assert nome == "ouvidoria_transicionar", f"RPC inesperada: {nome}"
        alvo = next(m for m in self.tabelas["ouvidoria_protocolos"] if m["id"] == params["p_manifestacao_id"])
        anterior = alvo["status"]
        alvo["status"] = params["p_estado_novo"]
        self.tabelas.setdefault("ouvidoria_movimentos", []).append(
            {
                "id": f"mov-{len(self.tabelas.get('ouvidoria_movimentos', [])) + 1}",
                "manifestacao_id": params["p_manifestacao_id"],
                "estado_anterior": anterior,
                "estado_novo": params["p_estado_novo"],
                "autor_nome": params["p_autor_nome"],
                "observacao": params.get("p_observacao"),
            }
        )
        return type("Exec", (), {"execute": lambda _s: type("R", (), {"data": [dict(alvo)]})()})()


def _client(monkeypatch, supabase: _SupabaseFake, participante: dict = OUVIDOR) -> TestClient:
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(RequestContextMiddleware)
    app.include_router(ouvidoria_router.router, prefix="/api")

    async def _fake_participante(_user, _sb, fields=None):
        return participante

    monkeypatch.setattr(ouvidoria_router, "get_participante_for_user", _fake_participante)
    monkeypatch.setattr(ouvidoria_router, "agora_utc", lambda: AGORA)
    app.dependency_overrides[get_current_user] = lambda: {"id": "u1", "email": "u@hsm.br"}
    app.dependency_overrides[get_supabase_client] = lambda: supabase
    return TestClient(app)


def _client_publico(monkeypatch, supabase: _SupabaseFake) -> TestClient:
    """O canal aberto de verdade, que é quem grava a manifestação sem
    `data_abertura` e sem `contato_em` e deixa os dois para o banco."""
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(RequestContextMiddleware)
    app.include_router(ouvidoria_publica.router, prefix="/api")
    app.dependency_overrides[get_supabase_client] = lambda: supabase
    return TestClient(app)


def _metricas(client: TestClient, inicio: str = INICIO, fim: str = FIM):
    return client.get(f"/api/ouvidoria/metricas?inicio={inicio}&fim={fim}")


def resposta_inteira(corpo: dict) -> str:
    """A resposta serializada, para asserir que um texto NÃO está em lugar
    nenhum dela. Vasculhar campo a campo deixaria passar o campo que ninguém
    lembrou de olhar, que é justamente o risco."""
    return json.dumps(corpo, ensure_ascii=False)


# Os marcos de um caso `medio` aberto na segunda 03/08/2026 às 9h de Brasília.
# Os vencimentos saem da tabela de prazos da migration 065 e do calendário útil
# (RN-22), contados à mão para não repetir a conta do motor:
#   triagem, 1 dia útil    -> dia 1 é terça 04/08, vence 04/08 às 17h  (20h UTC)
#   conclusiva, 7 dias úteis -> 04, 05, 06, 07, 10, 11, 12/08, vence 12/08 17h
T0 = "2026-08-03"
TRIAGEM_NO_PRAZO = "2026-08-04T17:00:00+00:00"  # terça, 14h de Brasília
TRIAGEM_ATRASADA = "2026-08-05T13:00:00+00:00"  # quarta, 10h de Brasília
PRAZO_DA_AREA = "2026-08-10T20:00:00+00:00"  # segunda 10/08, 17h de Brasília
AREA_NO_PRAZO = "2026-08-10T14:00:00+00:00"  # segunda, 11h de Brasília
AREA_ATRASADA = "2026-08-11T14:00:00+00:00"  # terça, 11h de Brasília
CONCLUSAO_NO_PRAZO = "2026-08-12T19:00:00+00:00"  # quarta 12/08, 16h de Brasília
CONCLUSAO_ATRASADA = "2026-08-14T12:00:00+00:00"  # sexta 14/08, 9h de Brasília


def _tramitado(numero: int, *, triagem: str, area: str, conclusao: str, **overrides) -> dict:
    """Um caso que percorreu os quatro marcos, com o desfecho de cada trecho
    escolhido pelo teste."""
    return _caso(
        numero,
        data_abertura=T0,
        gravidade="medio",
        validada_em=triagem,
        prazo_area_em=PRAZO_DA_AREA,
        respondida_em=area,
        encerrada_em=conclusao,
        status="encerrado",
        **overrides,
    )


def _por_trecho(corpo: dict) -> dict:
    return {linha["trecho"]: linha for linha in corpo["prazo"]["trechos"]}


class TestPrazoCumpridoPorTrecho:
    """Critério 2: o percentual de prazo cumprido sai separado por trecho, que
    é o que diz QUEM atrasou, a Ouvidoria ou o setor (PRD #319, história 5)."""

    def test_cada_trecho_tem_o_proprio_percentual_de_cumprimento(self, monkeypatch):
        supabase = _SupabaseFake(
            casos=[
                _tramitado(1, triagem=TRIAGEM_NO_PRAZO, area=AREA_NO_PRAZO, conclusao=CONCLUSAO_NO_PRAZO),
                _tramitado(2, triagem=TRIAGEM_ATRASADA, area=AREA_NO_PRAZO, conclusao=CONCLUSAO_NO_PRAZO),
                _tramitado(3, triagem=TRIAGEM_ATRASADA, area=AREA_ATRASADA, conclusao=CONCLUSAO_NO_PRAZO),
                _tramitado(4, triagem=TRIAGEM_ATRASADA, area=AREA_ATRASADA, conclusao=CONCLUSAO_ATRASADA),
            ]
        )
        trechos = _por_trecho(_metricas(_client(monkeypatch, supabase)).json())

        # Um cumprido em quatro na triagem, dois na área, três na conclusiva:
        # três números diferentes sobre os MESMOS quatro casos.
        assert trechos["triagem"]["percentual_cumprido"] == 25.0
        assert trechos["area"]["percentual_cumprido"] == 50.0
        assert trechos["conclusiva"]["percentual_cumprido"] == 75.0

    def test_cada_trecho_diz_quais_marcos_mede_e_de_quem_e_o_prazo(self, monkeypatch):
        supabase = _SupabaseFake(
            casos=[_tramitado(1, triagem=TRIAGEM_NO_PRAZO, area=AREA_NO_PRAZO, conclusao=CONCLUSAO_NO_PRAZO)]
        )
        trechos = _por_trecho(_metricas(_client(monkeypatch, supabase)).json())

        # A Ouvidoria e a área saem separadas nos dois primeiros trechos, que é
        # o que a issue pede. O conclusivo é o caso inteiro, e o rótulo diz
        # isso: a célula conclusiva da tabela de prazos é o total do caso, e
        # carimbá-la como falha "da Ouvidoria" cobraria dela o atraso da área.
        assert [(t["de"], t["ate"], t["responsavel"]) for t in trechos.values()] == [
            ("T0", "T1", "ouvidoria"),
            ("T1", "T2", "area"),
            ("T0", "T3", "caso"),
        ]

    def test_gravidade_sem_prazo_no_trecho_fica_fora_da_conta_em_vez_de_inflar(self, monkeypatch):
        # Baixo não passa pela área (a célula da tabela é nula). Contá-lo como
        # acerto encheria o indicador da área com casos que ela nunca recebeu.
        supabase = _SupabaseFake(
            casos=[
                _tramitado(1, triagem=TRIAGEM_ATRASADA, area=AREA_ATRASADA, conclusao=CONCLUSAO_NO_PRAZO),
                _caso(
                    2,
                    data_abertura=T0,
                    gravidade="baixo",
                    validada_em=TRIAGEM_NO_PRAZO,
                    prazo_area_em=None,
                    respondida_em=None,
                    encerrada_em=CONCLUSAO_NO_PRAZO,
                ),
            ]
        )
        area = _por_trecho(_metricas(_client(monkeypatch, supabase)).json())["area"]

        assert area["medidos"] == 1
        assert area["sem_prazo"] == 1
        assert area["percentual_cumprido"] == 0.0


def _pendente(numero: int, setor: str, prazo: str, **overrides) -> dict:
    """Caso já despachado e ainda sem resposta da área."""
    campos = {
        "setor": setor,
        "status": "aguardando_area",
        "validada_em": TRIAGEM_NO_PRAZO,
        "prazo_area_em": prazo,
        "respondida_em": None,
        "encerrada_em": None,
    }
    campos.update(overrides)
    return _caso(numero, **campos)


# Prazo vencido na segunda 24/08 às 17h de Brasília. Do vencimento até AGORA
# (quarta 26/08, 14h de Brasília) o expediente corrido é: terça inteira, 9h,
# mais 6h da quarta. São 15 horas úteis, e o dia útil tem 9: 1,7 dia de atraso.
PRAZO_VENCIDO = "2026-08-24T20:00:00+00:00"
ATRASO_EM_DIAS_UTEIS = 1.7
# Vence hoje às 17h de Brasília, três horas depois de AGORA: ainda no prazo.
PRAZO_DE_HOJE = "2026-08-26T20:00:00+00:00"


class TestPendenciasPorArea:
    """Critério 3: as pendências saem por área, com o nome de quem responde por
    ela e o atraso em dias úteis (PRD #319, história 6)."""

    def test_pendencia_vencida_traz_o_setor_o_responsavel_e_os_dias_de_atraso(self, monkeypatch):
        supabase = _SupabaseFake(
            casos=[_pendente(1, "Recepcao", PRAZO_VENCIDO)],
            ouvidoria_setor_responsaveis=[_responsavel("Recepcao", nome="Carlos Titular")],
        )
        pendencias = _metricas(_client(monkeypatch, supabase)).json()["pendencias_por_area"]

        assert len(pendencias) == 1
        assert pendencias[0]["setor"] == "Recepcao"
        assert pendencias[0]["responsavel"] == "Carlos Titular"
        assert pendencias[0]["vencidas"] == 1
        assert pendencias[0]["dias_uteis_de_atraso"] == ATRASO_EM_DIAS_UTEIS

    def test_setor_sem_titular_vigente_aparece_sem_nome_em_vez_de_sumir(self, monkeypatch):
        # Sumir seria o pior resultado: o setor sem dono é justamente o que a
        # Diretoria precisa enxergar.
        supabase = _SupabaseFake(
            casos=[_pendente(1, "Farmacia", PRAZO_VENCIDO)],
            ouvidoria_setor_responsaveis=[
                _responsavel("Farmacia", nome="Ex Titular", vigencia_fim="2026-01-31"),
            ],
        )
        pendencias = _metricas(_client(monkeypatch, supabase)).json()["pendencias_por_area"]

        assert [(p["setor"], p["responsavel"]) for p in pendencias] == [("Farmacia", None)]

    def test_caso_dentro_do_prazo_conta_como_pendencia_mas_nao_como_vencida(self, monkeypatch):
        supabase = _SupabaseFake(
            casos=[_pendente(1, "Recepcao", PRAZO_DE_HOJE)],
            ouvidoria_setor_responsaveis=[_responsavel("Recepcao")],
        )
        pendencias = _metricas(_client(monkeypatch, supabase)).json()["pendencias_por_area"]

        assert pendencias[0]["pendentes"] == 1
        assert pendencias[0]["vencidas"] == 0
        assert pendencias[0]["dias_uteis_de_atraso"] == 0.0

    def test_caso_ja_respondido_nao_e_pendencia(self, monkeypatch):
        supabase = _SupabaseFake(
            casos=[_pendente(1, "Recepcao", PRAZO_VENCIDO, status="respondido", respondida_em=AREA_ATRASADA)],
            ouvidoria_setor_responsaveis=[_responsavel("Recepcao")],
        )
        assert _metricas(_client(monkeypatch, supabase)).json()["pendencias_por_area"] == []


class TestRankingDeAreasPorTempoDeResposta:
    """Critério 3, segunda metade: o ranking por tempo médio de resposta
    (PRD #319, história 8). O mais lento primeiro: o ranking existe para
    apontar onde apertar."""

    def test_areas_saem_ordenadas_da_mais_lenta_para_a_mais_rapida(self, monkeypatch):
        # Validado segunda 10/08 às 11h de Brasília. A Recepção responde no dia
        # seguinte às 11h (um dia útil, 9h úteis); a Farmácia responde 3h depois
        # (3h úteis).
        validado = "2026-08-10T14:00:00+00:00"
        supabase = _SupabaseFake(
            casos=[
                _caso(
                    1,
                    setor="Recepcao",
                    status="respondido",
                    validada_em=validado,
                    prazo_area_em=PRAZO_DE_HOJE,
                    respondida_em="2026-08-11T14:00:00+00:00",
                ),
                _caso(
                    2,
                    setor="Farmacia",
                    status="respondido",
                    validada_em=validado,
                    prazo_area_em=PRAZO_DE_HOJE,
                    respondida_em="2026-08-10T17:00:00+00:00",
                ),
            ]
        )
        ranking = _metricas(_client(monkeypatch, supabase)).json()["ranking_areas"]

        assert [linha["setor"] for linha in ranking] == ["Recepcao", "Farmacia"]
        assert ranking[0]["minutos_uteis_medios"] == 9 * 60
        assert ranking[1]["minutos_uteis_medios"] == 3 * 60
        assert ranking[0]["respondidas"] == 1


def _prorrogacao(manifestacao_id: str, status: str = "aprovada", **overrides) -> dict:
    row = {
        "id": f"pror-{manifestacao_id}",
        "manifestacao_id": manifestacao_id,
        "status": status,
        "dias_uteis_pedidos": 2,
        "prazo_anterior": PRAZO_DA_AREA,
        "prazo_novo": "2026-08-14T20:00:00+00:00",
    }
    row.update(overrides)
    return row


class TestProrrogacaoPorArea:
    """Critério 4: a taxa de prorrogação por área, que separa a área que
    planeja da que empurra (PRD #319, história 7)."""

    def test_taxa_por_area_e_a_fatia_dos_casos_daquela_area_que_foram_prorrogados(self, monkeypatch):
        supabase = _SupabaseFake(
            casos=[_caso(n, setor="Recepcao", prazo_area_em=PRAZO_DA_AREA) for n in (1, 2, 3, 4)]
            + [_caso(5, setor="Farmacia", prazo_area_em=PRAZO_DA_AREA)],
            ouvidoria_prorrogacoes=[_prorrogacao("uuid-1")],
        )
        prorrogacao = _metricas(_client(monkeypatch, supabase)).json()["prorrogacao"]
        por_area = {linha["setor"]: linha for linha in prorrogacao["por_area"]}

        assert por_area["Recepcao"]["prorrogados"] == 1
        assert por_area["Recepcao"]["casos"] == 4
        assert por_area["Recepcao"]["taxa_pct"] == 25.0
        assert por_area["Farmacia"]["taxa_pct"] == 0.0

    def test_caso_que_nunca_chegou_a_area_fica_fora_do_denominador(self, monkeypatch):
        # Um caso na área e três que nunca foram (baixo não passa pela área;
        # em classificação ainda não saiu da Ouvidoria). Contá-los diluiria a
        # taxa de 100% para 25% com trabalho que ninguém teve como prorrogar.
        supabase = _SupabaseFake(
            casos=[
                _caso(1, setor="Recepcao", prazo_area_em=PRAZO_DA_AREA),
                _caso(2, setor="Recepcao", gravidade="baixo", prazo_area_em=None),
                _caso(3, setor="Recepcao", status="em_classificacao", gravidade=None, prazo_area_em=None),
                _caso(4, setor="Recepcao", gravidade="baixo", prazo_area_em=None),
            ],
            ouvidoria_prorrogacoes=[_prorrogacao("uuid-1")],
        )
        prorrogacao = _metricas(_client(monkeypatch, supabase)).json()["prorrogacao"]

        assert prorrogacao["com_a_area"] == 1
        assert prorrogacao["taxa_pct"] == 100.0

    def test_pedido_negado_ou_pendente_nao_conta_como_prorrogacao(self, monkeypatch):
        supabase = _SupabaseFake(
            casos=[
                _caso(1, setor="Recepcao", prazo_area_em=PRAZO_DA_AREA),
                _caso(2, setor="Recepcao", prazo_area_em=PRAZO_DA_AREA),
            ],
            ouvidoria_prorrogacoes=[_prorrogacao("uuid-1", status="negada"), _prorrogacao("uuid-2", status="pendente")],
        )
        prorrogacao = _metricas(_client(monkeypatch, supabase)).json()["prorrogacao"]

        assert prorrogacao["casos"] == 0
        assert prorrogacao["taxa_pct"] == 0.0

    def test_resposta_dentro_do_prazo_prorrogado_conta_como_cumprida(self, monkeypatch):
        # Respondeu depois do vencimento ORIGINAL e antes do prorrogado: a
        # régua é o vencimento vigente, então isto é acerto, não estouro.
        prorrogado = "2026-08-14T20:00:00+00:00"
        supabase = _SupabaseFake(
            casos=[
                _caso(
                    1,
                    status="respondido",
                    validada_em=TRIAGEM_NO_PRAZO,
                    prazo_area_em=prorrogado,
                    respondida_em="2026-08-12T14:00:00+00:00",
                )
            ],
            ouvidoria_prorrogacoes=[_prorrogacao("uuid-1", prazo_novo=prorrogado)],
        )
        area = _por_trecho(_metricas(_client(monkeypatch, supabase)).json())["area"]

        assert (area["cumpridos"], area["estourados"]) == (1, 0)


class TestOPeriodoPedido:
    """O contrato do intervalo, que as fatias I2 e I3 vão consumir."""

    def test_sem_intervalo_o_periodo_e_o_mes_corrente_ate_hoje(self, monkeypatch):
        # AGORA é 26/08/2026: o painel abre pedindo o mês até hoje.
        supabase = _SupabaseFake(casos=[_caso(1, data_abertura="2026-08-03"), _caso(2, data_abertura="2026-08-27")])

        resposta = _client(monkeypatch, supabase).get("/api/ouvidoria/metricas")

        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["periodo"] == {"inicio": "2026-08-01", "fim": "2026-08-26"}
        assert resposta.json()["volume"]["total"] == 1

    def test_intervalo_invertido_e_recusado(self, monkeypatch):
        resposta = _metricas(_client(monkeypatch, _SupabaseFake()), inicio=FIM, fim=INICIO)

        assert resposta.status_code == 400, resposta.text

    def test_periodo_sem_nenhum_caso_responde_zerado_em_vez_de_quebrar(self, monkeypatch):
        corpo = _metricas(_client(monkeypatch, _SupabaseFake())).json()

        assert corpo["volume"]["total"] == 0
        assert corpo["pendencias_por_area"] == []
        assert corpo["prazo"]["trechos"][0]["percentual_cumprido"] is None


class TestReincidencia:
    """Critério 5: o caso reincidente fica fora do volume de casos novos, para
    o número medir problema e não eco (PRD #319, história 16)."""

    def test_reincidente_conta_no_total_e_fica_fora_dos_novos(self, monkeypatch):
        supabase = _SupabaseFake(
            casos=[
                _caso(1),
                _caso(2),
                _caso(3, reincidencia=True),
            ]
        )
        corpo = _metricas(_client(monkeypatch, supabase)).json()

        assert corpo["volume"]["total"] == 3
        assert corpo["volume"]["novos"] == 2
        assert corpo["volume"]["reincidentes"] == 1

    def test_taxa_de_reincidencia_e_a_fatia_reincidente_do_periodo(self, monkeypatch):
        supabase = _SupabaseFake(casos=[_caso(1), _caso(2), _caso(3), _caso(4, reincidencia=True)])

        assert _metricas(_client(monkeypatch, supabase)).json()["reincidencia"] == {"casos": 1, "taxa_pct": 25.0}


class TestTempoPausado:
    """Critério 6: o tempo aguardando o manifestante aparece à parte, nunca
    somado ao tempo de resposta (PRD #319, história 15)."""

    def test_tempo_pausado_sai_num_indicador_proprio(self, monkeypatch):
        supabase = _SupabaseFake(
            casos=[
                _caso(1, minutos_pausados=540),  # um dia útil parado
                _caso(2, minutos_pausados=0),
            ]
        )
        pausa = _metricas(_client(monkeypatch, supabase)).json()["tempo_pausado"]

        assert pausa["casos_com_pausa"] == 1
        assert pausa["minutos_uteis_totais"] == 540
        assert pausa["dias_uteis_medios"] == 1.0

    def test_espera_pelo_manifestante_nao_engorda_o_tempo_de_resposta_da_area(self, monkeypatch):
        # Os dois casos levaram o MESMO tempo de relógio entre T1 e T2 (um dia
        # útil), mas o segundo passou 3h úteis esperando o manifestante. Se a
        # espera entrasse no tempo da área, os dois setores empatariam.
        validado = "2026-08-10T14:00:00+00:00"
        respondido = "2026-08-11T14:00:00+00:00"
        supabase = _SupabaseFake(
            casos=[
                _caso(1, setor="Recepcao", status="respondido", validada_em=validado, respondida_em=respondido),
                _caso(
                    2,
                    setor="Farmacia",
                    status="respondido",
                    validada_em=validado,
                    respondida_em=respondido,
                    minutos_pausados=180,
                ),
            ]
        )
        ranking = {linha["setor"]: linha for linha in _metricas(_client(monkeypatch, supabase)).json()["ranking_areas"]}

        assert ranking["Recepcao"]["minutos_uteis_medios"] == 9 * 60
        assert ranking["Farmacia"]["minutos_uteis_medios"] == 6 * 60


class TestTemasEAreasMaisFrequentes:
    """Critério 8: os cinco temas e as cinco áreas mais frequentes, que é onde
    dói (PRD #319, história 3)."""

    def test_temas_saem_do_mais_frequente_para_o_menos_e_param_em_cinco(self, monkeypatch):
        # O tema é o TIPO da manifestação, lista fechada (ADR 0037): são cinco,
        # e o topo pega os cinco em ordem de frequência.
        frequencia = {"reclamacao": 6, "denuncia": 5, "sugestao": 4, "elogio": 3, "relato_de_conduta": 2}
        casos = []
        numero = 0
        for tipo, quantidade in frequencia.items():
            for _ in range(quantidade):
                numero += 1
                casos.append(_caso(numero, tipo_manifestacao=tipo))
        corpo = _metricas(_client(monkeypatch, _SupabaseFake(casos=casos))).json()

        assert [linha["chave"] for linha in corpo["top_temas"]["itens"]] == list(frequencia)
        assert corpo["top_temas"]["itens"][0]["total"] == 6

    def test_tema_nao_carrega_o_texto_livre_que_o_ouvidor_digitou(self, monkeypatch):
        # `categoria` é o rótulo humano do caso, escrito com as palavras de quem
        # classificou. Um ouvidor que digita a frase inteira do caso a colocaria
        # no top 5 do painel e do PDF, com total 1.
        indiscreta = "Assedio do enfermeiro do plantao noturno da UTI"
        supabase = _SupabaseFake(casos=[_caso(1, categoria=indiscreta, tipo_manifestacao="denuncia")])

        corpo = _metricas(_client(monkeypatch, supabase)).json()

        assert indiscreta not in resposta_inteira(corpo)
        assert [linha["chave"] for linha in corpo["top_temas"]["itens"]] == ["denuncia"]

    def test_areas_mais_frequentes_saem_pela_mesma_regua(self, monkeypatch):
        supabase = _SupabaseFake(
            casos=[
                _caso(1, setor="Recepcao"),
                _caso(2, setor="Recepcao"),
                _caso(3, setor="Farmacia"),
            ]
        )
        top_areas = _metricas(_client(monkeypatch, supabase)).json()["top_areas"]

        assert [(linha["chave"], linha["total"]) for linha in top_areas["itens"]] == [("Recepcao", 2), ("Farmacia", 1)]

    def test_tops_comparam_com_o_periodo_anterior_como_as_outras_quebras(self, monkeypatch):
        # A linha tem o mesmo formato de `por_canal`, então `anterior` e
        # `variacao_pct` precisam significar a mesma coisa: um tema que caiu de
        # 30 para 12 não pode ser impresso como novidade do mês.
        casos = [_caso(n, data_abertura="2026-08-10", setor="Recepcao") for n in range(1, 13)]
        casos += [_caso(100 + n, data_abertura="2026-07-10", setor="Recepcao") for n in range(1, 31)]
        supabase = _SupabaseFake(casos=casos)

        top_areas = _metricas(_client(monkeypatch, supabase)).json()["top_areas"]

        assert top_areas["itens"][0]["total"] == 12
        assert top_areas["itens"][0]["anterior"] == 30
        assert top_areas["itens"][0]["variacao_pct"] == -60.0

    def test_marcador_de_nao_classificado_nao_disputa_o_topo(self, monkeypatch):
        # O formulário público não pergunta tema nem área: 40 casos recém
        # chegados imprimiriam "Área mais frequente: A definir (40)" no PDF do
        # diretor, que é o tamanho da fila de triagem, não uma área do hospital.
        casos = [_caso(n, setor=SETOR_PENDENTE, tipo_manifestacao=None) for n in range(1, 41)]
        casos += [_caso(100 + n, setor="Recepcao") for n in range(1, 4)]
        supabase = _SupabaseFake(casos=casos)

        corpo = _metricas(_client(monkeypatch, supabase)).json()

        assert [linha["chave"] for linha in corpo["top_areas"]["itens"]] == ["Recepcao"]
        assert SETOR_PENDENTE not in resposta_inteira(corpo)
        # E o denominador conta os 40 que ficaram de fora: sem ele, o PDF diria
        # "Área mais frequente: Recepção (3)" ao lado de "43 no período".
        assert corpo["top_areas"]["classificados"] == 3
        assert corpo["top_areas"]["nao_classificados"] == 40


class TestCadaMarcadorSoValeNoCampoDele:
    """Os dois marcadores de "ainda não classificado" moram na mesma taxonomia,
    mas são de campos diferentes: "A classificar" é da categoria e "A definir" é
    da área. Reconhecidos por um conjunto único, cada um censuraria também o
    campo do outro, e o valor legítimo sairia do ranking sem deixar rastro: some
    dos itens E engorda `nao_classificados`, que é a fila de triagem (#433)."""

    def test_area_com_o_nome_do_marcador_da_categoria_continua_no_ranking(self, monkeypatch):
        # Três casos numa área chamada com a mesma frase que marca categoria
        # pendente, e dois de fato sem área. Só os dois últimos são fila.
        casos = [_caso(n, setor=CATEGORIA_PENDENTE) for n in range(1, 4)]
        casos += [_caso(10 + n, setor=SETOR_PENDENTE) for n in range(1, 3)]

        top_areas = _metricas(_client(monkeypatch, _SupabaseFake(casos=casos))).json()["top_areas"]

        assert [(linha["chave"], linha["total"]) for linha in top_areas["itens"]] == [(CATEGORIA_PENDENTE, 3)]
        assert (top_areas["classificados"], top_areas["nao_classificados"]) == (3, 2)

    def test_categoria_com_o_nome_do_marcador_da_area_continua_contada(self):
        """O espelho, no outro domínio: o ouvidor que digita "A definir" em
        `categoria` classificou o caso, e a agregação tem que contá-lo.

        Aqui o seam é a própria agregação, e não a rota: os temas do painel saem
        de `tipo_manifestacao` desde a issue #429, e `categoria` deixou de ser
        lida do banco. Quem escolhe o conjunto é o campo pedido, e é esse
        despacho que o teste segura para o dia em que a categoria voltar."""
        from app.services.ouvidoria_metricas import _mais_frequentes

        casos = [
            {"categoria": SETOR_PENDENTE},
            {"categoria": SETOR_PENDENTE},
            {"categoria": "Demora no atendimento"},
            {"categoria": CATEGORIA_PENDENTE},
        ]

        topo = _mais_frequentes(casos, [], "categoria")

        assert [(linha["chave"], linha["total"]) for linha in topo["itens"]] == [
            (SETOR_PENDENTE, 2),
            ("Demora no atendimento", 1),
        ]
        assert (topo["classificados"], topo["nao_classificados"]) == (3, 1)


@pytest.fixture
def _nunca_envia_email_de_verdade(monkeypatch):
    """O pytest do backend carrega o .env real (Resend de produção): a
    reabertura notifica o setor, e a notificação passa pelo mock."""
    enviados: list[dict] = []

    def _fake(destinatario, assunto, html_content, texto_fallback):
        enviados.append({"destinatario": destinatario, "assunto": assunto})
        return True

    monkeypatch.setattr(ouvidoria_notificacoes, "_enviar_email", _fake)
    return enviados


class TestCasoReabertoPelaRotaReal:
    """O cenário mais traiçoeiro do módulo, montado pela ROTA de reabertura e
    não à mão: é ela que decide o que fica e o que sai quando um caso encerrado
    volta a tramitar, e as métricas leem exatamente o que ela deixou.

    Duas armadilhas moram aqui, e as duas só aparecem com o estado que a rota
    produz. A reabertura preserva `encerrada_em` de propósito (é o marco T3 da
    tramitação anterior) e preserva `validada_em`, mas zera `minutos_pausados` e
    dá prazo inteiro novo. Lidos cru, esses dois carimbos velhos fariam o caso
    reaberto contar como fechado no prazo e entregariam à área o tempo do ciclo
    anterior inteiro."""

    # Fechado às 16h de 12/08, o último instante do prazo conclusivo do "médio"
    # (7 dias úteis a partir do T0 de 03/08 vencem em 12/08 às 17h). Lido cru,
    # este carimbo diz CUMPRIDO, e é exatamente por isso que ele está aqui: o
    # caso reaberto não pode continuar contando como fechado no prazo.
    T3_DO_CICLO_ANTERIOR = "2026-08-12T19:00:00+00:00"

    def _reaberto(self, monkeypatch, enviados):
        # Encerrado dentro da janela de reincidência de 30 dias.
        caso = _caso(
            7,
            status="encerrado",
            gravidade="medio",
            validada_em="2026-08-04T13:00:00+00:00",
            prazo_area_em="2026-08-10T20:00:00+00:00",
            respondida_em="2026-08-10T14:00:00+00:00",
            encerrada_em=self.T3_DO_CICLO_ANTERIOR,
            desfecho="resolvido",
            minutos_pausados=1080,
        )
        supabase = _SupabaseFake(casos=[caso], ouvidoria_setor_responsaveis=[_responsavel("Recepcao")])
        client = _client(monkeypatch, supabase)

        resposta = client.post(
            "/api/ouvidoria/manifestacoes/uuid-7/reaberturas",
            json={"motivo": "O manifestante voltou dizendo que a espera continua igual."},
        )
        assert resposta.status_code == 201, resposta.text
        return client, supabase

    def test_caso_reaberto_nao_conta_como_conclusiva_cumprida(self, monkeypatch, _nunca_envia_email_de_verdade):
        client, supabase = self._reaberto(monkeypatch, _nunca_envia_email_de_verdade)

        # O marco T3 do ciclo anterior continua gravado, e dentro do prazo: é
        # ele a armadilha.
        assert supabase.tabelas["ouvidoria_protocolos"][0]["encerrada_em"] == self.T3_DO_CICLO_ANTERIOR

        conclusiva = _por_trecho(_metricas(client).json())["conclusiva"]

        assert conclusiva["cumpridos"] == 0, "Reabrir não pode fechar o indicador de um caso que voltou a tramitar"
        assert conclusiva["estourados"] == 1

    def test_caso_reaberto_fica_fora_do_volume_de_casos_novos(self, monkeypatch, _nunca_envia_email_de_verdade):
        client, _ = self._reaberto(monkeypatch, _nunca_envia_email_de_verdade)

        volume = _metricas(client).json()["volume"]

        assert (volume["total"], volume["novos"], volume["reincidentes"]) == (1, 0, 1)

    def test_tempo_de_resposta_do_ciclo_novo_nao_carrega_o_ciclo_anterior(
        self, monkeypatch, _nunca_envia_email_de_verdade
    ):
        client, supabase = self._reaberto(monkeypatch, _nunca_envia_email_de_verdade)
        caso = supabase.tabelas["ouvidoria_protocolos"][0]

        # A rota zerou o acumulado de pausa e manteve o T1 antigo: medir dali
        # cobraria da área três semanas por uma resposta dada em três horas.
        assert caso["minutos_pausados"] == 0
        assert caso["validada_em"] == "2026-08-04T13:00:00+00:00"

        # A área responde três horas úteis depois da reabertura (AGORA, 14h de
        # Brasília), ainda no mesmo dia de expediente.
        caso["respondida_em"] = "2026-08-26T20:00:00+00:00"
        caso["status"] = "respondido"

        ranking = _metricas(client).json()["ranking_areas"]

        assert ranking[0]["minutos_uteis_medios"] == 3 * 60


class TestTriagemQueNaoAconteceu:
    """O furo que fazia o indicador SUBIR quanto pior fosse a Ouvidoria.

    `gravidade` só é gravada na validação, no mesmo ato que carimba o T1. Sem
    régua para o caso ainda não triado, ele caía em `sem_prazo` e saía do
    denominador: o que sumia da conta era justamente o conjunto das falhas."""

    def _parado(self, numero: int, **overrides) -> dict:
        """Manifestação que ninguém olhou: sem gravidade, sem tipo, sem T1."""
        campos = {
            "data_abertura": T0,
            "status": "em_classificacao",
            "gravidade": None,
            "tipo_manifestacao": None,
            "validada_em": None,
            "prazo_area_em": None,
            "respondida_em": None,
            "encerrada_em": None,
        }
        campos.update(overrides)
        return _caso(numero, **campos)

    def _triagem(self, monkeypatch, casos: list[dict]) -> dict:
        return _por_trecho(_metricas(_client(monkeypatch, _SupabaseFake(casos=casos))).json())["triagem"]

    def test_fila_abandonada_nao_pode_devolver_cem_por_cento_de_triagem(self, monkeypatch):
        # Três triados no prazo e sete largados desde 03/08. Com AGORA em 26/08,
        # os sete passaram de qualquer célula de triagem da tabela.
        casos = [
            _tramitado(n, triagem=TRIAGEM_NO_PRAZO, area=AREA_NO_PRAZO, conclusao=CONCLUSAO_NO_PRAZO)
            for n in range(1, 4)
        ]
        casos += [self._parado(100 + n) for n in range(1, 8)]

        triagem = self._triagem(monkeypatch, casos)

        assert triagem["estourados"] == 7, "A triagem que não aconteceu precisa aparecer como estouro"
        assert triagem["percentual_cumprido"] == 30.0

    def test_triar_com_atraso_nao_pode_pontuar_pior_que_nao_triar(self, monkeypatch):
        # A régua invertida era o pior do furo: deixar parado dava 100, triar
        # atrasado dava 30. Os dois cenários agora dão o mesmo número.
        base = [
            _tramitado(n, triagem=TRIAGEM_NO_PRAZO, area=AREA_NO_PRAZO, conclusao=CONCLUSAO_NO_PRAZO)
            for n in range(1, 4)
        ]
        parados = self._triagem(monkeypatch, base + [self._parado(100 + n) for n in range(1, 8)])
        atrasados = self._triagem(
            monkeypatch,
            base
            + [
                _tramitado(100 + n, triagem=TRIAGEM_ATRASADA, area=AREA_NO_PRAZO, conclusao=CONCLUSAO_NO_PRAZO)
                for n in range(1, 8)
            ],
        )

        assert parados["percentual_cumprido"] == atrasados["percentual_cumprido"] == 30.0

    def test_celula_sem_prazo_nunca_vira_a_regua_da_triagem(self, monkeypatch):
        """A tabela de prazos tem célula vazia por desenho (valor NULL significa
        "sem prazo para esta combinação"). Ela não pode ganhar o `max` que
        escolhe a régua: se ganhasse, o caso não triado voltaria a `sem_prazo` e
        a fila abandonada sumiria do denominador de novo.

        É o contrato de `minutos_do_prazo`, que devolve None para célula vazia,
        e a razão de o módulo usar a função do motor de prazos em vez de uma
        cópia local que tratasse "sem prazo" como "prazo zero"."""
        prazos = [dict(p) for p in PRAZOS if not (p["marco"] == "triagem" and p["gravidade"] == "critico")]
        prazos.append({"gravidade": "critico", "marco": "triagem", "valor": None, "unidade": "horas_uteis"})
        supabase = _SupabaseFake(casos=[self._parado(1)], ouvidoria_prazos=prazos)

        triagem = _por_trecho(_metricas(_client(monkeypatch, supabase)).json())["triagem"]

        assert triagem["sem_prazo"] == 0, "Célula vazia virou a régua e apagou a triagem não feita"
        assert triagem["estourados"] == 1

    def test_caso_recem_chegado_ainda_dentro_da_maior_celula_fica_em_andamento(self, monkeypatch):
        # Chegou hoje: nenhuma gravidade teria estourado ainda, então ele não é
        # erro nem acerto. Carimbar estouro aqui seria o exagero oposto.
        triagem = self._triagem(monkeypatch, [self._parado(1, data_abertura="2026-08-26")])

        assert (triagem["estourados"], triagem["em_andamento"]) == (0, 1)


class TestConclusivaComOPrazoQueAOperacaoMoveu:
    """O prazo conclusivo não tem coluna própria, e prorrogação e pausa movem
    só `prazo_area_em`. Recalculado do zero, o mesmo caso saía CUMPRIDO no
    trecho da área e ESTOURADO no conclusivo: o PDF acusaria de atraso um prazo
    que a própria Diretoria estendeu."""

    # Médio: conclusiva de 7 dias úteis do T0 (03/08) vence em 12/08 às 17h.
    # Encerrar em 18/08 estoura, a menos que a operação tenha dado o crédito.
    ENCERRADA_EM = "2026-08-18T14:00:00+00:00"

    def _caso_esticado(self, **overrides) -> dict:
        campos = {
            "data_abertura": T0,
            "status": "encerrado",
            "validada_em": TRIAGEM_NO_PRAZO,
            "prazo_area_em": "2026-08-17T20:00:00+00:00",
            "respondida_em": "2026-08-17T14:00:00+00:00",
            "encerrada_em": self.ENCERRADA_EM,
        }
        campos.update(overrides)
        return _caso(1, **campos)

    def test_prorrogacao_aprovada_tambem_vale_para_o_prazo_conclusivo(self, monkeypatch):
        supabase = _SupabaseFake(
            casos=[self._caso_esticado()],
            ouvidoria_prorrogacoes=[
                _prorrogacao(
                    "uuid-1",
                    prazo_anterior="2026-08-10T20:00:00+00:00",
                    prazo_novo="2026-08-17T20:00:00+00:00",
                )
            ],
        )
        trechos = _por_trecho(_metricas(_client(monkeypatch, supabase)).json())

        assert trechos["area"]["cumpridos"] == 1
        assert trechos["conclusiva"]["estourados"] == 0, (
            "Prazo estendido pela Diretoria não pode virar estouro no trecho conclusivo"
        )
        assert trechos["conclusiva"]["cumpridos"] == 1

    def test_espera_pelo_manifestante_tambem_vale_para_o_prazo_conclusivo(self, monkeypatch):
        # Cinco dias úteis (2700 minutos) parados aguardando o manifestante. Esse
        # tempo já voltou ao prazo da área na retomada; sem devolvê-lo aqui, a
        # espera viraria falha do caso.
        supabase = _SupabaseFake(casos=[self._caso_esticado(minutos_pausados=2700)])

        conclusiva = _por_trecho(_metricas(_client(monkeypatch, supabase)).json())["conclusiva"]

        assert (conclusiva["cumpridos"], conclusiva["estourados"]) == (1, 0)

    def test_sem_credito_nenhum_o_atraso_conclusivo_continua_aparecendo(self, monkeypatch):
        # A contraprova: sem prorrogação e sem pausa, encerrar em 18/08 estoura
        # o prazo conclusivo de 12/08, e o indicador precisa dizer isso.
        supabase = _SupabaseFake(casos=[self._caso_esticado(prazo_area_em=PRAZO_DA_AREA, respondida_em=AREA_NO_PRAZO)])

        assert _por_trecho(_metricas(_client(monkeypatch, supabase)).json())["conclusiva"]["estourados"] == 1


class TestFilaVivaDasPendencias:
    """As pendências respondem "o que está pendente AGORA", e não "o que entrou
    no período": a área com o caso mais atrasado do hospital não pode sumir do
    painel porque o caso entrou no mês passado (issue #344)."""

    def test_caso_vencido_de_periodo_anterior_aparece_nas_pendencias(self, monkeypatch):
        # Aberto em 20/07, vencido em 25/07, sem resposta até hoje. O painel de
        # agosto mostrava a Recepção com zero pendências.
        supabase = _SupabaseFake(
            casos=[_pendente(1, "Recepcao", "2026-07-25T20:00:00+00:00", data_abertura="2026-07-20")],
            ouvidoria_setor_responsaveis=[_responsavel("Recepcao", nome="Carlos Titular")],
        )
        corpo = _metricas(_client(monkeypatch, supabase)).json()

        assert corpo["volume"]["total"] == 0, "O volume continua sendo o do período pedido"
        assert [(p["setor"], p["vencidas"]) for p in corpo["pendencias_por_area"]] == [("Recepcao", 1)]

    def test_caso_que_nao_deve_resposta_da_area_nao_entra_na_fila_viva(self, monkeypatch):
        supabase = _SupabaseFake(
            casos=[
                _caso(1, status="encerrado", prazo_area_em=PRAZO_VENCIDO, respondida_em=AREA_ATRASADA),
                _caso(2, status="aguardando_manifestante", prazo_area_em=PRAZO_VENCIDO, respondida_em=None),
            ],
            ouvidoria_setor_responsaveis=[_responsavel("Recepcao")],
        )

        assert _metricas(_client(monkeypatch, supabase)).json()["pendencias_por_area"] == []


class TestReguaDoPeriodoNaoDependeDoFusoDoBanco:
    """`data_abertura` é DATE com `DEFAULT CURRENT_DATE`, e nos canais
    automáticos ninguém a escreve. Com o banco em UTC, a manifestação feita às
    22h de 31/08 no horário de Brasília nasce carimbada 01/09.

    O cenário é montado pela ROTA pública real: é ela que decide o que grava e o
    que deixa para o default do banco, e o furo mora nessa fronteira."""

    RELATO = "Esperei quase tres horas na recepcao e ninguem me explicou o motivo."

    def _enviar(self, monkeypatch, relogio_do_banco: dt.datetime) -> _SupabaseFake:
        supabase = _SupabaseFake(casos=[], relogio_do_banco=relogio_do_banco)
        resposta = _client_publico(monkeypatch, supabase).post(
            "/api/ouvidoria/publico/manifestacoes",
            json={"relato": self.RELATO, "anonimo": True},
        )
        assert resposta.status_code == 201, resposta.text
        return supabase

    def test_manifestacao_da_noite_da_virada_entra_no_mes_em_que_foi_feita(self, monkeypatch):
        # 31/08 às 22h de Brasília é 01/09 às 01h em UTC: é o que o banco carimba.
        supabase = self._enviar(monkeypatch, dt.datetime(2026, 9, 1, 1, 0, tzinfo=dt.UTC))

        gravado = supabase.tabelas["ouvidoria_protocolos"][0]
        assert gravado["data_abertura"] == "2026-09-01", "O banco carimba o dia dele, e é essa a armadilha"

        corpo = _metricas(_client(monkeypatch, supabase)).json()

        assert corpo["volume"]["total"] == 1, "A manifestação de 31/08 pertence ao relatório de agosto"

    def test_manifestacao_do_dia_seguinte_continua_fora(self, monkeypatch):
        # A contraprova: 01/09 às 10h de Brasília é 01/09 mesmo, e não entra.
        supabase = self._enviar(monkeypatch, dt.datetime(2026, 9, 1, 13, 0, tzinfo=dt.UTC))

        assert _metricas(_client(monkeypatch, supabase)).json()["volume"]["total"] == 0


class TestCasoSigilosoNaoEIdentificado:
    """A agregação enxerga a denúncia sigilosa, e é por isso que o gate da rota
    é estreito. O que ela não pode é IDENTIFICAR o caso: este objeto sai desta
    função para o PDF que a fatia I5 manda por email a gestor de área, e um
    protocolo ali seria a denúncia entregue pelo cruzamento com o email de
    acionamento que o próprio gestor recebeu (RN-40, ADR 0034 decisão 8)."""

    def test_denuncia_sigilosa_conta_na_cobranca_mas_nao_sai_identificada(self, monkeypatch):
        supabase = _SupabaseFake(
            casos=[_pendente(42, "Recepcao", PRAZO_VENCIDO, tipo_manifestacao="denuncia", sigilo_reforcado=True)],
            ouvidoria_setor_responsaveis=[_responsavel("Recepcao")],
        )
        corpo = _metricas(_client(monkeypatch, supabase)).json()

        assert corpo["pendencias_por_area"][0]["vencidas"] == 1, "O caso sigiloso conta na cobrança da área"
        assert "2026-0042" not in resposta_inteira(corpo), "Nenhum protocolo pode sair na resposta"
        assert "protocolo" not in resposta_inteira(corpo)


class TestJanelaPedida:
    """O que a rota aceita como intervalo."""

    def test_periodo_maior_que_o_teto_e_recusado(self, monkeypatch):
        resposta = _metricas(_client(monkeypatch, _SupabaseFake()), inicio="2016-01-01", fim="2036-01-01")

        assert resposta.status_code == 400, resposta.text

    def test_data_no_comeco_do_calendario_responde_400_e_nao_500(self, monkeypatch):
        # `Periodo.anterior()` recua uma janela inteira: sem guarda isto
        # estourava OverflowError e virava 500 em cima de parâmetro do cliente.
        resposta = _metricas(_client(monkeypatch, _SupabaseFake()), inicio="0001-01-01", fim="0001-01-01")

        assert resposta.status_code == 400, resposta.text


class TestLeituraDegradada:
    """Falha de leitura não pode virar número. Num módulo cujo propósito é
    painel e PDF não divergirem, o zero fabricado é o pior modo de falha."""

    def test_falha_ao_ler_prorrogacoes_e_carimbada_na_resposta(self, monkeypatch):
        supabase = _SupabaseFake(casos=[_caso(1, prazo_area_em=PRAZO_DA_AREA)])
        supabase.indisponiveis = {"ouvidoria_prorrogacoes"}

        corpo = _metricas(_client(monkeypatch, supabase)).json()

        assert corpo["degradado"] == ["prorrogacoes"]
        assert corpo["prorrogacao"]["taxa_pct"] is None, "Sem leitura não há taxa, e zero passaria por medição"

    def test_periodo_sem_falha_nenhuma_declara_lista_vazia(self, monkeypatch):
        assert _metricas(_client(monkeypatch, _SupabaseFake(casos=[_caso(1)]))).json()["degradado"] == []

    def test_falha_ao_ler_a_tabela_de_prazos_tira_a_regua_de_quem_dependia_dela(self, monkeypatch):
        # Um caso que percorreu os quatro marcos no prazo: com a tabela lida, os
        # três trechos saem 100% cumpridos. Sem ela, triagem e conclusiva ficam
        # sem régua (as duas contam a partir do T0 pela tabela) e nenhum dos dois
        # pode declarar percentual. O trecho da área continua medindo: ele lê o
        # `prazo_area_em` persistido, que não passa pela tabela, e escondê-lo
        # junto seria jogar fora medição que existe.
        supabase = _SupabaseFake(
            casos=[_tramitado(1, triagem=TRIAGEM_NO_PRAZO, area=AREA_NO_PRAZO, conclusao=CONCLUSAO_NO_PRAZO)]
        )
        supabase.indisponiveis = {"ouvidoria_prazos"}

        corpo = _metricas(_client(monkeypatch, supabase)).json()
        trechos = _por_trecho(corpo)

        assert corpo["degradado"] == ["prazos"], "As outras três leituras estavam abertas"
        assert trechos["triagem"]["percentual_cumprido"] is None
        assert trechos["conclusiva"]["percentual_cumprido"] is None
        assert (trechos["triagem"]["sem_prazo"], trechos["conclusiva"]["sem_prazo"]) == (1, 1)
        assert trechos["area"]["percentual_cumprido"] == 100.0

    def test_falha_ao_ler_os_feriados_conta_o_atraso_sem_o_calendario(self, monkeypatch):
        # O feriado de terça 25/08 tira 9 horas úteis da conta: o atraso do caso
        # vencido na segunda 17h cai de 1,7 para 0,7 dia útil. Sem a leitura, o
        # número volta a ser o do calendário cheio, e é por isso que ele precisa
        # viajar carimbado: quem lê o painel tem que saber que aquele atraso foi
        # contado sem os feriados.
        def _corpo(indisponiveis: set[str]) -> dict:
            supabase = _SupabaseFake(
                casos=[_pendente(1, "Recepcao", PRAZO_VENCIDO)],
                ouvidoria_feriados=[{"data": "2026-08-25", "nome": "Feriado local", "abrangencia": "municipal"}],
            )
            supabase.indisponiveis = indisponiveis
            return _metricas(_client(monkeypatch, supabase)).json()

        com_calendario = _corpo(set())
        sem_calendario = _corpo({"ouvidoria_feriados"})

        assert com_calendario["degradado"] == []
        assert com_calendario["pendencias_por_area"][0]["dias_uteis_de_atraso"] == 0.7
        assert sem_calendario["degradado"] == ["feriados"], "As outras três leituras estavam abertas"
        assert sem_calendario["pendencias_por_area"][0]["dias_uteis_de_atraso"] == ATRASO_EM_DIAS_UTEIS

    def test_falha_ao_ler_os_responsaveis_deixa_a_pendencia_sem_nome_e_com_o_resto(self, monkeypatch):
        # O cadastro tem titular vigente para a Recepção: o nome SAIRIA. Sem a
        # leitura ele não pode ser inventado, mas a pendência não some do painel
        # nem perde o atraso, que vêm da leitura dos casos e não desta.
        supabase = _SupabaseFake(
            casos=[_pendente(1, "Recepcao", PRAZO_VENCIDO)],
            ouvidoria_setor_responsaveis=[_responsavel("Recepcao", nome="Carlos Titular")],
        )
        supabase.indisponiveis = {"ouvidoria_setor_responsaveis"}

        corpo = _metricas(_client(monkeypatch, supabase)).json()
        pendencia = corpo["pendencias_por_area"][0]

        assert corpo["degradado"] == ["responsaveis"], "As outras três leituras estavam abertas"
        assert pendencia["responsavel"] is None
        assert "Carlos Titular" not in resposta_inteira(corpo)
        assert (pendencia["setor"], pendencia["pendentes"], pendencia["vencidas"]) == ("Recepcao", 1, 1)
        assert pendencia["dias_uteis_de_atraso"] == ATRASO_EM_DIAS_UTEIS

    def test_duas_leituras_falhando_juntas_saem_as_duas_na_lista(self, monkeypatch):
        # A cascata é o modo de falha real (o banco não cai por tabela), e a
        # lista é o que a tela lê para saber o que não vale. Guardar só a última
        # falha deixaria a tela imprimindo como medido um número que não foi.
        supabase = _SupabaseFake(
            casos=[_tramitado(1, triagem=TRIAGEM_NO_PRAZO, area=AREA_NO_PRAZO, conclusao=CONCLUSAO_NO_PRAZO)]
        )
        supabase.indisponiveis = {"ouvidoria_prazos", "ouvidoria_setor_responsaveis"}

        corpo = _metricas(_client(monkeypatch, supabase)).json()

        assert corpo["degradado"] == ["prazos", "responsaveis"]
        assert _por_trecho(corpo)["triagem"]["percentual_cumprido"] is None
        assert corpo["prorrogacao"]["taxa_pct"] is not None, "A leitura que ficou de pé continua medindo"


class TestTaxaSemNadaAMedir:
    """A convenção do módulo: sem denominador, o número é `None`, nunca zero.
    "Taxa de prorrogação: 0%" lê como "nenhuma área precisou de mais tempo"."""

    def test_quinzena_sem_caso_na_area_nao_declara_zero_por_cento(self, monkeypatch):
        corpo = _metricas(_client(monkeypatch, _SupabaseFake())).json()

        assert corpo["prorrogacao"]["taxa_pct"] is None
        assert corpo["reincidencia"]["taxa_pct"] is None


class TestDegradacaoNaoVazaNumeroPelaLinhaDaArea:
    """O topo admitir que não mediu e a linha de CADA área imprimir "0,0%" logo
    abaixo é a afirmação entrando pela porta dos fundos: é o número por área que
    vai para o PDF do diretor."""

    def _degradado(self, monkeypatch):
        supabase = _SupabaseFake(
            casos=[
                _caso(1, setor="Recepcao", prazo_area_em=PRAZO_DA_AREA),
                _caso(2, setor="Farmacia", prazo_area_em=PRAZO_DA_AREA),
            ]
        )
        supabase.indisponiveis = {"ouvidoria_prorrogacoes"}
        return _metricas(_client(monkeypatch, supabase)).json()["prorrogacao"]

    def test_sem_leitura_nenhuma_area_declara_taxa(self, monkeypatch):
        prorrogacao = self._degradado(monkeypatch)

        assert [linha["taxa_pct"] for linha in prorrogacao["por_area"]] == [None, None]
        assert [linha["prorrogados"] for linha in prorrogacao["por_area"]] == [None, None]

    def test_sem_leitura_a_contagem_do_topo_tambem_e_ausencia_e_nao_zero(self, monkeypatch):
        assert self._degradado(monkeypatch)["casos"] is None

    def test_o_denominador_sobrevive_a_degradacao_porque_nao_depende_dela(self, monkeypatch):
        # `com_a_area` sai da leitura dos casos, que não falhou: escondê-lo
        # junto seria jogar fora medição que existe.
        prorrogacao = self._degradado(monkeypatch)

        assert prorrogacao["com_a_area"] == 2
        assert [linha["setor"] for linha in prorrogacao["por_area"]] == ["Farmacia", "Recepcao"]


class TestTopsDizemSobreQuantosCasosForamCalculados:
    """Tirar o marcador do topo sem o denominador troca um erro por outro:
    ausência de medição apresentada como medição."""

    def test_lista_vazia_por_falta_de_classificacao_se_distingue_de_ausencia_de_tema(self, monkeypatch):
        # Nada classificado: sem o denominador, `[]` aqui é indistinguível de
        # "não houve tema nenhum no período".
        supabase = _SupabaseFake(casos=[_caso(n, tipo_manifestacao=None) for n in range(1, 6)])

        top_temas = _metricas(_client(monkeypatch, supabase)).json()["top_temas"]

        assert top_temas["itens"] == []
        assert top_temas["classificados"] == 0
        assert top_temas["nao_classificados"] == 5

    def test_periodo_sem_caso_nenhum_zera_os_dois_lados(self, monkeypatch):
        top_temas = _metricas(_client(monkeypatch, _SupabaseFake())).json()["top_temas"]

        assert (top_temas["classificados"], top_temas["nao_classificados"]) == (0, 0)


class TestFimDoCalendario:
    """A guarda da rodada anterior cobriu o começo do calendário e deixou o fim
    aberto, e a folga de fuso desta mesma rodada soma um dia ao `fim`: o
    transbordo estourava dentro do serviço, sem try, e virava 500."""

    def test_data_no_fim_do_calendario_responde_400_e_nao_500(self, monkeypatch):
        resposta = _metricas(_client(monkeypatch, _SupabaseFake()), inicio="9999-12-31", fim="9999-12-31")

        assert resposta.status_code == 400, resposta.text


class TestQuemLeAsMetricas:
    """Critério 7: só ouvidor e diretoria executiva. O gate é o mesmo do
    Dossiê, e pela mesma razão: a agregação conta o caso sigiloso junto, e um
    número por setor com um caso só já entrega de quem era o caso."""

    @pytest.mark.parametrize("participante", [OUVIDOR, DIRETORIA], ids=["ouvidor", "diretoria"])
    def test_os_dois_perfis_da_ouvidoria_leem_as_metricas(self, monkeypatch, participante):
        supabase = _SupabaseFake(casos=[_caso(1)])

        resposta = _metricas(_client(monkeypatch, supabase, participante))

        assert resposta.status_code == 200, resposta.text

    @pytest.mark.parametrize(
        "participante", [SUPER_ADMIN, SECRETARIA, None], ids=["super_admin", "secretaria", "sem_participante"]
    )
    def test_quem_esta_fora_da_ouvidoria_recebe_403_e_nenhum_numero(self, monkeypatch, participante):
        # Fixture com TODAS as outras portas abertas: o super admin do contexto
        # Reuniões é o pior caso, porque em Reuniões ele passa em tudo.
        supabase = _SupabaseFake(casos=[_caso(1), _caso(2)])

        resposta = _metricas(_client(monkeypatch, supabase, participante))

        assert resposta.status_code == 403, resposta.text
        assert "volume" not in resposta.json(), f"O 403 vazou número: {resposta.text}"


class TestVolumeDoPeriodo:
    """Critério 1: volume total e por canal/tipo do período, com variação
    frente ao período anterior."""

    def test_volume_conta_so_o_que_entrou_no_periodo(self, monkeypatch):
        supabase = _SupabaseFake(
            casos=[
                _caso(1, data_abertura="2026-08-03"),
                _caso(2, data_abertura="2026-08-20"),
                _caso(3, data_abertura="2026-08-31"),
                # Fora do período: um antes, um depois.
                _caso(4, data_abertura="2026-07-31"),
                _caso(5, data_abertura="2026-09-01"),
            ]
        )
        resposta = _metricas(_client(monkeypatch, supabase))

        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["volume"]["total"] == 3

    def test_volume_sai_quebrado_por_canal_e_por_tipo(self, monkeypatch):
        supabase = _SupabaseFake(
            casos=[
                _caso(1, canal="ana", tipo_manifestacao="reclamacao"),
                _caso(2, canal="ana", tipo_manifestacao="denuncia"),
                _caso(3, canal="telefone", tipo_manifestacao="reclamacao"),
                _caso(4, canal="qr", tipo_manifestacao="elogio"),
            ]
        )
        volume = _metricas(_client(monkeypatch, supabase)).json()["volume"]

        assert {linha["chave"]: linha["total"] for linha in volume["por_canal"]} == {"ana": 2, "telefone": 1, "qr": 1}
        assert {linha["chave"]: linha["total"] for linha in volume["por_tipo"]} == {
            "reclamacao": 2,
            "denuncia": 1,
            "elogio": 1,
        }

    def test_variacao_compara_com_o_periodo_anterior_de_mesmo_tamanho(self, monkeypatch):
        supabase = _SupabaseFake(
            casos=[
                # Agosto: 3 casos.
                _caso(1, data_abertura="2026-08-03"),
                _caso(2, data_abertura="2026-08-10"),
                _caso(3, data_abertura="2026-08-20"),
                # Julho, o período anterior de 31 dias: 2 casos.
                _caso(4, data_abertura="2026-07-02"),
                _caso(5, data_abertura="2026-07-30"),
                # Junho não entra em nenhum dos dois.
                _caso(6, data_abertura="2026-06-15"),
            ]
        )
        corpo = _metricas(_client(monkeypatch, supabase)).json()

        assert corpo["periodo_anterior"] == {"inicio": "2026-07-01", "fim": "2026-07-31"}
        assert corpo["volume"]["anterior"] == 2
        # De 2 para 3 é meio a mais.
        assert corpo["volume"]["variacao_pct"] == 50.0

    def test_canal_que_existia_antes_e_sumiu_aparece_com_a_queda(self, monkeypatch):
        # Sumir da quebra esconderia justamente a notícia: o canal caiu a zero.
        supabase = _SupabaseFake(
            casos=[
                _caso(1, data_abertura="2026-08-03", canal="ana"),
                _caso(2, data_abertura="2026-07-10", canal="qr"),
                _caso(3, data_abertura="2026-07-11", canal="qr"),
            ]
        )
        por_canal = {
            linha["chave"]: linha for linha in _metricas(_client(monkeypatch, supabase)).json()["volume"]["por_canal"]
        }

        assert por_canal["qr"]["total"] == 0
        assert por_canal["qr"]["anterior"] == 2
        assert por_canal["qr"]["variacao_pct"] == -100.0


class TestLeituraMinima:
    """Issue #429, critério 1: nenhuma leitura do módulo pede campo que ninguém
    consome. Dado que não é lido não deve entrar no processo, e isso vale em
    dobro para o email de quem responde pela área, que é dado pessoal servindo
    de nada dentro de uma agregação.

    Este é o único teste do módulo que olha o caminho até o número em vez do
    número: o que a issue promete aqui é justamente o que a leitura pede."""

    def _colunas(self, monkeypatch) -> dict[str, set[str]]:
        supabase = _SupabaseFake(casos=[_pendente(1, "Recepcao", PRAZO_VENCIDO)])
        assert _metricas(_client(monkeypatch, supabase)).status_code == 200
        return supabase.colunas_lidas

    def test_o_cadastro_de_responsaveis_e_lido_sem_o_email(self, monkeypatch):
        assert "email" not in self._colunas(monkeypatch)["ouvidoria_setor_responsaveis"]

    def test_as_manifestacoes_sao_lidas_sem_a_categoria(self, monkeypatch):
        # `categoria` ficou sem consumidor quando os temas passaram a sair de
        # `tipo_manifestacao`.
        assert "categoria" not in self._colunas(monkeypatch)["ouvidoria_protocolos"]


class TestRateLimitDasMetricas:
    """Issue #429, critério 2: a porta de métricas custa cinco idas ao banco e o
    período inteiro em memória, bem mais que os GETs vizinhos de onde ela herdou
    60 por minuto. O limite é 15 por minuto."""

    def test_a_decima_sexta_chamada_do_minuto_e_recusada(self, monkeypatch):
        client = _client(monkeypatch, _SupabaseFake())

        assert [_metricas(client).status_code for _ in range(15)] == [200] * 15
        assert _metricas(client).status_code == 429
