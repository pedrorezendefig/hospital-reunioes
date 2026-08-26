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

    def __init__(self, nome: str, rows: list[dict]):
        self.nome = nome
        self.rows = rows
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

    def _projetar(self, row: dict) -> dict:
        if self._colunas is None:
            return dict(row)
        return {c: row.get(c) for c in self._colunas}

    def execute(self):
        if self._insert is not None:
            novos = self._insert if isinstance(self._insert, list) else [self._insert]
            gravados = []
            for novo in novos:
                linha = dict(novo)
                linha.setdefault("id", f"{self.nome}-{len(self.rows) + 1}")
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
    def __init__(self, casos: list[dict] | None = None, **tabelas):
        self.tabelas: dict[str, list[dict]] = {
            "ouvidoria_protocolos": casos if casos is not None else [],
            "ouvidoria_prorrogacoes": [],
            "ouvidoria_setor_responsaveis": [_responsavel()],
            "ouvidoria_prazos": [dict(p) for p in PRAZOS],
            "ouvidoria_feriados": [{"data": "2026-09-07", "nome": "Independencia", "abrangencia": "nacional"}],
        }
        self.tabelas.update(tabelas)

    def table(self, nome: str):
        return _TabelaFake(nome, self.tabelas.setdefault(nome, []))

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


def _metricas(client: TestClient, inicio: str = INICIO, fim: str = FIM):
    return client.get(f"/api/ouvidoria/metricas?inicio={inicio}&fim={fim}")


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
        casos = []
        numero = 0
        # Seis temas com frequências decrescentes: 6, 5, 4, 3, 2 e 1.
        for posicao, quantidade in enumerate([6, 5, 4, 3, 2, 1], start=1):
            for _ in range(quantidade):
                numero += 1
                casos.append(_caso(numero, categoria=f"Tema {posicao}"))
        corpo = _metricas(_client(monkeypatch, _SupabaseFake(casos=casos))).json()

        assert [linha["chave"] for linha in corpo["top_temas"]] == [f"Tema {p}" for p in range(1, 6)]
        assert corpo["top_temas"][0]["total"] == 6

    def test_areas_mais_frequentes_saem_pela_mesma_regua(self, monkeypatch):
        supabase = _SupabaseFake(
            casos=[
                _caso(1, setor="Recepcao"),
                _caso(2, setor="Recepcao"),
                _caso(3, setor="Farmacia"),
            ]
        )
        top_areas = _metricas(_client(monkeypatch, supabase)).json()["top_areas"]

        assert [(linha["chave"], linha["total"]) for linha in top_areas] == [("Recepcao", 2), ("Farmacia", 1)]


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
