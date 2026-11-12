"""A nota do Google buscada toda semana (issue #1619, PRD #1527, ADR 0089).

O job sem IA lê a nota e o total de avaliações pela Places API (New) e grava
no diário de Nota externa, com a marca de leitura automática. Sem a chave
`GOOGLE_PLACES_API_KEY`, ele não chama nada. A rede é um `httpx.MockTransport`:
o serviço roda de verdade, só o Google é de mentira.
"""

from __future__ import annotations

import datetime as dt
import os
import sys

import httpx
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from central_de_comando_apoio import (  # noqa: E402
    PREFIXO_DA_CENTRAL,
    SUPER_ADMIN,
    SupabaseDosParticipantes,
    cliente_da_central,
)

from app.services import ouvidoria_nota_externa, ouvidoria_nota_google  # noqa: E402

PLACE_ID = "ChIJN5IUl-vfmwARsSET9nFjh70"
AGORA = dt.datetime(2026, 11, 16, 9, 45, tzinfo=dt.UTC)


class _Tabela:
    """O PostgREST no que o job e a leitura usam: grava, filtra, ordena, limita."""

    def __init__(self, rows: list[dict]):
        self.rows = rows
        self._eq: dict = {}
        self._gte: dict = {}
        self._insert: dict | None = None
        self._ordem: tuple[str, bool] | None = None
        self._limite: int | None = None

    def select(self, *_a, **_kw):
        return self

    def eq(self, col, valor):
        self._eq[col] = valor
        return self

    def gte(self, col, valor):
        self._gte[col] = valor
        return self

    def insert(self, payload):
        self._insert = payload
        return self

    def order(self, col, desc=False):
        self._ordem = (col, desc)
        return self

    def limit(self, quantos):
        self._limite = quantos
        return self

    def execute(self):
        if self._insert is not None:
            self.rows.append(dict(self._insert))
            return type("R", (), {"data": [dict(self._insert)]})()
        linhas = [
            r
            for r in self.rows
            if all(r.get(c) == v for c, v in self._eq.items())
            and all(str(r.get(c) or "") >= str(v) for c, v in self._gte.items())
        ]
        if self._ordem:
            col, desc = self._ordem
            linhas = sorted(linhas, key=lambda r: str(r.get(col) or ""), reverse=desc)
        if self._limite is not None:
            linhas = linhas[: self._limite]
        return type("R", (), {"data": [dict(r) for r in linhas]})()


class SupabaseFalso:
    def __init__(self, notas: list[dict] | None = None, place_id: str = PLACE_ID):
        self.tabelas = {
            "ouvidoria_nota_externa": list(notas or []),
            "ouvidoria_config": [{"id": True, "google_place_id": place_id, "google_review_url": ""}],
        }

    def table(self, nome: str):
        return _Tabela(self.tabelas.setdefault(nome, []))

    @property
    def notas(self) -> list[dict]:
        return self.tabelas["ouvidoria_nota_externa"]


class GoogleFalso:
    """A Places API (New): GET /v1/places/{id} com a máscara de campos."""

    def __init__(self, rating: float = 2.5, total: int = 1629):
        self.pedidos: list[httpx.Request] = []
        self.rating = rating
        self.total = total

    def __call__(self, pedido: httpx.Request) -> httpx.Response:
        self.pedidos.append(pedido)
        return httpx.Response(200, json={"rating": self.rating, "userRatingCount": self.total})

    def cliente(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self))


class TestJobSemanal:
    def test_com_a_api_simulada_grava_nota_total_e_marca_automatica(self):
        supabase = SupabaseFalso()
        google = GoogleFalso(rating=2.5, total=1629)

        ouvidoria_nota_google.buscar_e_gravar(supabase, AGORA, chave="chave-de-teste", cliente=google.cliente())

        assert len(supabase.notas) == 1
        linha = supabase.notas[0]
        assert linha["fonte"] == "google"
        assert linha["nota"] == 2.5
        assert linha["total_avaliacoes"] == 1629
        assert linha["origem"] == "automatica"
        pedido = google.pedidos[0]
        assert pedido.url.path == f"/v1/places/{PLACE_ID}"
        assert pedido.headers["X-Goog-Api-Key"] == "chave-de-teste"
        assert set(pedido.headers["X-Goog-FieldMask"].split(",")) == {"rating", "userRatingCount"}

    def test_sem_a_chave_nao_chama_nada_e_nao_grava(self):
        supabase = SupabaseFalso()
        google = GoogleFalso()

        ouvidoria_nota_google.buscar_e_gravar(supabase, AGORA, chave="", cliente=google.cliente())

        assert google.pedidos == []
        assert supabase.notas == []

    def test_com_leitura_automatica_na_semana_nao_busca_de_novo(self):
        """O job roda todo dia e busca uma vez por semana."""
        ontem = (AGORA - dt.timedelta(days=1)).isoformat()
        supabase = SupabaseFalso([_leitura(ontem, 2.5, 1629)])
        google = GoogleFalso()

        ouvidoria_nota_google.buscar_e_gravar(supabase, AGORA, chave="chave-de-teste", cliente=google.cliente())

        assert google.pedidos == []
        assert len(supabase.notas) == 1

    def test_uma_semana_depois_da_ultima_leitura_busca_de_novo(self):
        semana_passada = (AGORA - dt.timedelta(days=7)).isoformat()
        supabase = SupabaseFalso([_leitura(semana_passada, 2.5, 1629)])
        google = GoogleFalso(rating=2.6, total=1640)

        ouvidoria_nota_google.buscar_e_gravar(supabase, AGORA, chave="chave-de-teste", cliente=google.cliente())

        assert len(google.pedidos) == 1
        assert supabase.notas[-1]["total_avaliacoes"] == 1640

    def test_o_google_fora_do_ar_nao_grava_nem_levanta(self):
        supabase = SupabaseFalso()
        cliente = httpx.Client(transport=httpx.MockTransport(lambda _p: httpx.Response(503)))

        assert ouvidoria_nota_google.buscar_e_gravar(supabase, AGORA, chave="chave-de-teste", cliente=cliente) is None
        assert supabase.notas == []


class TestJobNoScheduler:
    def test_o_job_esta_agendado_todo_dia_no_fuso_de_sao_paulo(self):
        from apscheduler.triggers.cron import CronTrigger

        from app.cron import scheduler as cron

        try:
            cron.start_scheduler()
            job = cron.scheduler.get_job("nota_do_google")
            assert job is not None
            assert job.func is cron.buscar_nota_do_google
            assert isinstance(job.trigger, CronTrigger)
            assert str(job.trigger.timezone) == "America/Sao_Paulo"
        finally:
            cron.stop_scheduler()

    def test_sem_a_chave_no_ambiente_o_job_nao_chama_o_google(self, monkeypatch):
        from app.config import settings
        from app.cron import scheduler as cron

        supabase = SupabaseFalso()
        monkeypatch.setattr(cron, "_supabase", lambda: supabase)
        monkeypatch.setattr(settings, "google_places_api_key", "")

        # Conta, em vez de levantar: o job engole exceção no log, e um dublê que
        # levantasse deixaria este teste verde com o Google chamado.
        google = GoogleFalso()
        cliente = google.cliente()
        monkeypatch.setattr(httpx, "Client", lambda *_a, **_kw: cliente)

        cron.buscar_nota_do_google()

        assert google.pedidos == []
        assert supabase.notas == []


def _leitura(quando: str, nota: float, total: int | None, origem: str = "automatica") -> dict:
    return {
        "fonte": "google",
        "nota": nota,
        "total_avaliacoes": total,
        "origem": origem,
        "registrada_em": quando,
        "registrada_por_nome": "",
    }


HOJE = dt.date(2026, 11, 16)


class TestResumoDoMes:
    def test_sem_a_chave_a_nota_nao_e_medida(self):
        supabase = SupabaseFalso([_leitura("2026-11-09T09:45:00+00:00", 2.5, 1629)])

        resumo = ouvidoria_nota_google.resumo_do_mes(supabase, HOJE, medida=False)

        assert resumo["medida"] is False
        assert resumo["nota"] is None

    def test_nota_avaliacoes_novas_do_mes_e_tendencia(self):
        supabase = SupabaseFalso(
            [
                _leitura("2026-10-05T09:45:00+00:00", 2.3, 1590),
                _leitura("2026-10-26T09:45:00+00:00", 2.4, 1620),
                _leitura("2026-11-02T09:45:00+00:00", 2.5, 1629),
                _leitura("2026-11-09T09:45:00+00:00", 2.5, 1635),
                _leitura("2026-11-16T09:45:00+00:00", 2.6, 1641),
            ]
        )

        resumo = ouvidoria_nota_google.resumo_do_mes(supabase, HOJE, medida=True)

        assert resumo["medida"] is True
        assert resumo["nota"] == 2.6
        assert resumo["escala"] == 5
        assert resumo["total"] == 1641
        assert resumo["avaliacoes_do_mes"] == 12
        assert resumo["nota_mes_anterior"] == 2.4
        assert resumo["tendencia"] == "melhorou"

    def test_nota_abaixo_da_do_fim_do_mes_anterior_piorou(self):
        supabase = SupabaseFalso(
            [
                _leitura("2026-10-26T09:45:00+00:00", 2.6, 1620),
                _leitura("2026-11-09T09:45:00+00:00", 2.5, 1635),
            ]
        )

        assert ouvidoria_nota_google.resumo_do_mes(supabase, HOJE, medida=True)["tendencia"] == "piorou"

    def test_uma_leitura_so_no_mes_nao_inventa_avaliacoes_novas(self):
        """Com uma leitura, a diferença do total seria zero e leria como "ninguém
        avaliou": sem duas leituras no mês, não há número."""
        supabase = SupabaseFalso([_leitura("2026-11-02T09:45:00+00:00", 2.5, 1629)])

        resumo = ouvidoria_nota_google.resumo_do_mes(supabase, HOJE, medida=True)

        assert resumo["nota"] == 2.5
        assert resumo["avaliacoes_do_mes"] is None
        assert resumo["tendencia"] is None

    def test_a_nota_digitada_antes_conta_na_tendencia_mas_nao_no_total(self):
        """O histórico digitado fica (ADR 0089, decisão 2): a nota de outubro
        digitada pelo ouvidor é a base da tendência de novembro."""
        supabase = SupabaseFalso(
            [
                _leitura("2026-10-20T12:00:00+00:00", 2.5, None, origem="manual"),
                _leitura("2026-11-09T09:45:00+00:00", 2.5, 1635),
            ]
        )

        resumo = ouvidoria_nota_google.resumo_do_mes(supabase, HOJE, medida=True)

        assert resumo["tendencia"] == "igual"
        assert resumo["total"] == 1635


class _SupabaseDaCentral(SupabaseFalso):
    """O gate da Central lê `participantes`; a nota, o diário."""

    def __init__(self, notas: list[dict] | None = None):
        from central_de_comando_apoio import FACILITADOR, SECRETARIA, SUPER_ADMIN

        super().__init__(notas)
        self._gate = SupabaseDosParticipantes([SUPER_ADMIN, SECRETARIA, FACILITADOR])

    def table(self, nome: str):
        return self._gate.table(nome) if nome == "participantes" else super().table(nome)


def _nota_na_central(supabase, logado=None) -> httpx.Response:
    from app.dependencies import get_supabase_client

    cliente = cliente_da_central(logado or SUPER_ADMIN)
    cliente.app.dependency_overrides[get_supabase_client] = lambda: supabase
    return cliente.get(f"{PREFIXO_DA_CENTRAL}/objetivos/google-reputacao")


@pytest.mark.usefixtures("gate_e_limitador_zerados")
class TestObjetivoNaCentral:
    def test_mostra_nota_avaliacoes_novas_do_mes_e_tendencia(self, monkeypatch):
        from app.config import settings
        from app.services.central_de_comando import periodo

        monkeypatch.setattr(settings, "google_places_api_key", "chave-de-teste")
        monkeypatch.setattr(periodo, "hoje_utc", lambda: HOJE)
        supabase = _SupabaseDaCentral(
            [
                _leitura("2026-10-26T09:45:00+00:00", 2.4, 1620),
                _leitura("2026-11-02T09:45:00+00:00", 2.5, 1629),
                _leitura("2026-11-16T09:45:00+00:00", 2.6, 1641),
            ]
        )

        resposta = _nota_na_central(supabase)

        assert resposta.status_code == 200, resposta.text
        corpo = resposta.json()
        assert corpo["objetivo"]["id"] == "google-reputacao"
        assert corpo["reputacao"]["medida"] is True
        assert corpo["reputacao"]["nota"] == 2.6
        assert corpo["reputacao"]["avaliacoes_do_mes"] == 12
        assert corpo["reputacao"]["tendencia"] == "melhorou"

    def test_sem_a_chave_a_central_diz_que_a_nota_nao_e_medida(self, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "google_places_api_key", "")
        supabase = _SupabaseDaCentral([_leitura("2026-11-16T09:45:00+00:00", 2.6, 1641)])

        corpo = _nota_na_central(supabase).json()

        assert corpo["reputacao"]["medida"] is False
        assert corpo["reputacao"]["nota"] is None

    def test_so_super_admin_ve(self, monkeypatch):
        from central_de_comando_apoio import SECRETARIA

        assert _nota_na_central(_SupabaseDaCentral(), SECRETARIA).status_code == 403

    def test_o_objetivo_do_google_nao_esta_mais_em_construcao(self):
        from app.services.central_de_comando.objetivos.catalogo import objetivo_por_id

        assert objetivo_por_id("google-reputacao").em_construcao is False


class TestRelatorioDaDiretoria:
    def test_o_relatorio_continua_lendo_a_ultima_nota_de_cada_fonte(self):
        """A leitura automática entra no mesmo diário, e o relatório pega a
        última de cada fonte, venha ela do job ou da mão do ouvidor."""
        reclame_aqui = {"fonte": "reclame_aqui", "nota": 7.8, "registrada_em": "2026-11-03T12:00:00+00:00"}
        supabase = SupabaseFalso(
            [
                _leitura("2026-11-01T12:00:00+00:00", 2.4, None, origem="manual"),
                _leitura("2026-11-09T09:45:00+00:00", 2.6, 1635),
                reclame_aqui,
            ]
        )

        notas = {n["fonte"]: n for n in ouvidoria_nota_externa.ultimas(supabase)}

        assert notas["google"]["nota"] == 2.6
        assert notas["google"]["escala"] == 5
        assert notas["reclame_aqui"]["nota"] == 7.8
