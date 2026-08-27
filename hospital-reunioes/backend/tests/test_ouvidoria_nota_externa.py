"""Nota externa manual: Google e Reclame Aqui (issue #347, PRD #319, história 10).

O retrato que o hospital tem FORA dele não é medido pelo sistema: ninguém aqui
consegue calcular a estrela do Google. Quem sabe é o ouvidor, que abre as duas
páginas e digita o que leu. Esta fatia é a porta para esse número entrar, e o
lugar dele no relatório da Diretoria.

O que está sob teste, em ordem de risco:

  - as duas escalas NÃO são a mesma, e o relatório nunca imprime o número
    sozinho: 4,3 do Google é de 5, e 7,8 do Reclame Aqui é de 10. Lado a lado,
    sem denominador, o leitor conclui que o hospital está melhor no Reclame
    Aqui que no Google;
  - a nota entra no relatório CONGELADA, como o resto dos números: o reenvio de
    uma edição velha mostra a nota daquela quinzena, não a de hoje;
  - período sem nota registrada diz que não há registro, e nunca imprime zero,
    que leria como nota zero;
  - só ouvidor e Diretoria Executiva gravam e leem. Papel nas Reuniões,
    inclusive super admin, não concede (ADR 0034, decisão 8).
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

OUVIDOR = {"id": "P10", "nome_completo": "Marta Ouvidora", "access_profile": None, "perfil_ouvidoria": "ouvidor"}
DIRETORA = {
    "id": "P11",
    "nome_completo": "Helena Diretora",
    "access_profile": None,
    "perfil_ouvidoria": "diretoria_executiva",
}
# As outras portas do app, todas abertas, e nenhuma delas vale aqui.
SUPER_ADMIN = {"id": "P01", "nome_completo": "Pedro Admin", "access_profile": "super_admin", "perfil_ouvidoria": None}
SECRETARIA = {
    "id": "P02",
    "nome_completo": "Sofia Secretaria",
    "access_profile": "secretaria",
    "perfil_ouvidoria": None,
}

AGORA = dt.datetime(2026, 8, 16, 10, 0, tzinfo=dt.UTC)


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


class _TabelaFake:
    """Fake do PostgREST no que esta fatia usa: grava, filtra, ordena, limita."""

    def __init__(self, nome: str, rows: list[dict]):
        self.nome = nome
        self.rows = rows
        self._filters: dict = {}
        self._insert: dict | list | None = None
        self._colunas: tuple[str, ...] | None = None
        self._limite: int | None = None
        self._ordem: tuple[str, bool] | None = None

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

    def limit(self, quantos: int):
        self._limite = quantos
        return self

    def order(self, col, desc=False):
        self._ordem = (col, desc)
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
        casadas = [r for r in self.rows if all(r.get(c) == v for c, v in self._filters.items())]
        if self._ordem:
            col, desc = self._ordem
            casadas = sorted(casadas, key=lambda r: str(r.get(col) or ""), reverse=desc)
        if self._limite is not None:
            casadas = casadas[: self._limite]
        return type("R", (), {"data": [self._projetar(r) for r in casadas]})()


class _SupabaseFake:
    def __init__(self, **tabelas):
        self.tabelas: dict[str, list[dict]] = {"ouvidoria_nota_externa": []}
        self.tabelas.update(tabelas)

    def table(self, nome: str):
        return _TabelaFake(nome, self.tabelas.setdefault(nome, []))


def _client(monkeypatch, supabase: _SupabaseFake, participante: dict = OUVIDOR) -> TestClient:
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(RequestContextMiddleware)
    app.include_router(ouvidoria_router.router, prefix="/api")

    async def _fake_participante(_user, _sb, fields=None):
        return participante

    monkeypatch.setattr(ouvidoria_router, "get_participante_for_user", _fake_participante)
    # O relógio ANDA entre as chamadas, como o de verdade. Congelado, duas
    # notas da mesma fonte teriam o mesmo instante, e "a última registrada"
    # deixaria de ter resposta: o teste passaria ou falharia por sorte da
    # ordenação, e a coluna que ordena a leitura ficaria sem prova.
    tique = iter(range(1, 1000))
    monkeypatch.setattr(ouvidoria_router, "agora_utc", lambda: AGORA + dt.timedelta(seconds=next(tique)))
    app.dependency_overrides[get_current_user] = lambda: {"id": "u1", "email": "u@hsm.br"}
    app.dependency_overrides[get_supabase_client] = lambda: supabase
    return TestClient(app)


# ═══════════════════════════════════════════════════════════════════════════
# O ouvidor registra
# ═══════════════════════════════════════════════════════════════════════════


class TestRegistro:
    def test_ouvidor_registra_a_nota_do_google_e_a_do_reclame_aqui(self, monkeypatch):
        """CA: o ouvidor registra a nota das duas fontes pela interface."""
        client = _client(monkeypatch, _SupabaseFake())

        google = client.post("/api/ouvidoria/nota-externa", json={"fonte": "google", "nota": 4.3})
        reclame = client.post("/api/ouvidoria/nota-externa", json={"fonte": "reclame_aqui", "nota": 7.8})

        assert google.status_code == 201, google.text
        assert reclame.status_code == 201, reclame.text
        assert google.json()["fonte"] == "google"
        assert google.json()["nota"] == 4.3
        assert reclame.json()["nota"] == 7.8

    def test_nota_fora_da_escala_da_fonte_e_recusada(self, monkeypatch):
        """8 é nota boa no Reclame Aqui e é impossível no Google. Um teto único
        de 10 aceitaria "Google 8", e o PDF imprimiria "8,0 de 5"."""
        client = _client(monkeypatch, _SupabaseFake())

        assert client.post("/api/ouvidoria/nota-externa", json={"fonte": "google", "nota": 8}).status_code == 422
        assert client.post("/api/ouvidoria/nota-externa", json={"fonte": "reclame_aqui", "nota": 8}).status_code == 201
        assert client.post("/api/ouvidoria/nota-externa", json={"fonte": "google", "nota": -1}).status_code == 422


# ═══════════════════════════════════════════════════════════════════════════
# A leitura: a última de cada fonte
# ═══════════════════════════════════════════════════════════════════════════


class TestLeitura:
    def test_leitura_devolve_a_ultima_nota_de_cada_fonte(self, monkeypatch):
        """CA: o que vale é a última nota registrada, não a primeira.

        Atualizar é registrar de novo: a tabela é um diário, e a leitura é que
        escolhe a linha mais recente."""
        client = _client(monkeypatch, _SupabaseFake())
        client.post("/api/ouvidoria/nota-externa", json={"fonte": "google", "nota": 4.1})
        client.post("/api/ouvidoria/nota-externa", json={"fonte": "reclame_aqui", "nota": 7.0})
        client.post("/api/ouvidoria/nota-externa", json={"fonte": "google", "nota": 4.6})

        resposta = client.get("/api/ouvidoria/nota-externa")

        assert resposta.status_code == 200, resposta.text
        notas = {linha["fonte"]: linha for linha in resposta.json()["notas"]}
        assert notas["google"]["nota"] == 4.6
        assert notas["reclame_aqui"]["nota"] == 7.0

    def test_leitura_leva_a_escala_junto_do_numero(self, monkeypatch):
        """4,3 do Google é de 5 e 7,8 do Reclame Aqui é de 10. Quem mostra o
        número precisa receber a régua dele na mesma resposta."""
        client = _client(monkeypatch, _SupabaseFake())
        client.post("/api/ouvidoria/nota-externa", json={"fonte": "google", "nota": 4.3})
        client.post("/api/ouvidoria/nota-externa", json={"fonte": "reclame_aqui", "nota": 7.8})

        notas = {linha["fonte"]: linha for linha in client.get("/api/ouvidoria/nota-externa").json()["notas"]}

        assert notas["google"]["escala"] == 5
        assert notas["reclame_aqui"]["escala"] == 10

    def test_fonte_nunca_registrada_nao_vira_nota_zero(self, monkeypatch):
        """Ausência de registro é ausência, e não nota zero: a fonte sai da
        leitura com `nota` nula, para a tela e o PDF dizerem que não há."""
        client = _client(monkeypatch, _SupabaseFake())
        client.post("/api/ouvidoria/nota-externa", json={"fonte": "google", "nota": 4.3})

        notas = {linha["fonte"]: linha for linha in client.get("/api/ouvidoria/nota-externa").json()["notas"]}

        assert notas["reclame_aqui"]["nota"] is None
        assert notas["reclame_aqui"]["escala"] == 10


# ═══════════════════════════════════════════════════════════════════════════
# Quem entra
# ═══════════════════════════════════════════════════════════════════════════


class TestPermissao:
    """As duas portas: quem não é da Ouvidoria não grava nem lê.

    Os perfis recusados chegam com o papel das Reuniões ABERTO no máximo que o
    app tem (`super_admin`), porque é essa a recusa que importa provar: um 403
    que viesse de "não tem papel nenhum" ficaria verde com o gate da Ouvidoria
    desligado."""

    @pytest.mark.parametrize("participante", [SUPER_ADMIN, SECRETARIA])
    def test_perfil_de_fora_nao_grava_nem_le(self, monkeypatch, participante):
        """CA: perfis fora de ouvidor/diretoria executiva não gravam nem leem."""
        banco = _SupabaseFake()
        client = _client(monkeypatch, banco, participante)

        gravacao = client.post("/api/ouvidoria/nota-externa", json={"fonte": "google", "nota": 4.3})
        leitura = client.get("/api/ouvidoria/nota-externa")

        assert gravacao.status_code == 403
        assert leitura.status_code == 403
        # A recusa tem que ser ANTES do banco: 403 com a linha gravada seria a
        # nota do hospital entrando pela mão de quem não responde por ela.
        assert banco.tabelas["ouvidoria_nota_externa"] == []

    @pytest.mark.parametrize("participante", [OUVIDOR, DIRETORA])
    def test_os_dois_perfis_da_ouvidoria_gravam_e_leem(self, monkeypatch, participante):
        """A outra metade da prova: sem ela, um 403 universal deixaria o teste
        acima verde."""
        client = _client(monkeypatch, _SupabaseFake(), participante)

        gravacao = client.post("/api/ouvidoria/nota-externa", json={"fonte": "google", "nota": 4.3})
        leitura = client.get("/api/ouvidoria/nota-externa")

        assert gravacao.status_code == 201, gravacao.text
        assert leitura.status_code == 200, leitura.text
