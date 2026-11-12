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

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

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
