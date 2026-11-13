"""A aba Avaliações da Ouvidoria (issue #1626, PRD #1527, ADR 0086 decisões 4 e 8).

As notas do QR, os comentários e os números por ponto, turno e dia da semana,
só para o Perfil da Ouvidoria. Daqui o ouvidor converte uma avaliação em caso
(canal `qr`, o cartaz, a ligação, tipo vazio e T0 da avaliação) ou arquiva a
revisão de uma avaliação marcada Para revisar, com um motivo curto.

Os testes sobem as rotas reais com um banco falso em memória.
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
from app.services import ouvidoria_agente_triagem  # noqa: E402

OUVIDOR = {"id": "P10", "nome_completo": "Marta Ouvidora", "access_profile": None, "perfil_ouvidoria": "ouvidor"}
DIRETORIA = {
    "id": "P11",
    "nome_completo": "Dr. Diretor",
    "access_profile": "regular",
    "perfil_ouvidoria": "diretoria_executiva",
}
SUPER_ADMIN = {"id": "P12", "nome_completo": "Ana Admin", "access_profile": "super_admin", "perfil_ouvidoria": None}
SECRETARIA = {"id": "P13", "nome_completo": "Sônia", "access_profile": "secretaria", "perfil_ouvidoria": None}
FACILITADOR = {"id": "P14", "nome_completo": "Fábio", "access_profile": "regular", "perfil_ouvidoria": None}

# Sexta-feira, 13/11/2026, 15h em Brasília.
AGORA = dt.datetime(2026, 11, 13, 18, 0, tzinfo=dt.UTC)


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


@pytest.fixture(autouse=True)
def _sem_agente(monkeypatch):
    """O agente de triagem não sai para a internet daqui: a conversão só
    precisa provar que ele foi chamado para o caso novo."""
    chamados: list[dict] = []
    monkeypatch.setattr(ouvidoria_agente_triagem, "agendar_caso", lambda _t, _s, caso: chamados.append(caso))
    return chamados


def _ponto(pid: str, *, nome: str | None, setor: str = "Pronto Socorro", rotulo: str = "Hall") -> dict:
    return {
        "id": pid,
        "codigo": pid[-6:].upper(),
        "setor": setor,
        "ponto": rotulo,
        "ativo": True,
        "criado_em": "2026-10-01T12:00:00+00:00",
        "nome_publico": nome,
        "descricao_local": "Parede ao lado da passagem",
        "titulo_cartaz": "atendimento_hoje",
        "codigo_controle": None,
        "ala_internacao": False,
        "google_teste_ativo": False,
    }


PONTO_EMERGENCIA = _ponto("ponto-emerg1", nome="Emergência adulta", setor="Pronto Socorro", rotulo="Hall da emergência")
PONTO_CENTRO = _ponto("ponto-centr1", nome="Centro médico", setor="Ambulatório", rotulo="Recepção do centro")


def _avaliacao(
    aid: str,
    criada_em: str,
    nota: int,
    *,
    ponto: dict = PONTO_EMERGENCIA,
    comentario: str | None = None,
    pediu_retorno: bool = False,
    revisar: bool = False,
    motivos: list[str] | None = None,
) -> dict:
    return {
        "id": aid,
        "ponto_id": ponto["id"] if ponto else None,
        "canal": "qr",
        "nota": nota,
        "motivos": motivos or [],
        "comentario": comentario,
        "criada_em": criada_em,
        "convite_google_exibido": False,
        "convite_google_clicado": False,
        "pediu_retorno": pediu_retorno,
        "revisar": revisar,
        "revisar_motivo": "Relata agressão" if revisar else None,
        "revisao_desfecho": None,
        "revisao_motivo": None,
        "revisada_por": None,
        "revisada_em": None,
    }


class _Negado:
    def __init__(self, tabela: _Tabela):
        self._tabela = tabela

    def is_(self, col, valor):
        assert valor == "null"
        self._tabela._filtros.append(lambda r, c=col: r.get(c) is not None)
        return self._tabela


class _Tabela:
    def __init__(self, banco: _Banco, nome: str):
        self._banco = banco
        self.nome = nome
        self._filtros: list = []
        self._colunas: tuple[str, ...] | None = None
        self._insert: dict | None = None
        self._update: dict | None = None
        self._ordem: list[tuple[str, bool]] = []
        self._recorte: tuple[int, int] | None = None
        self._contar = False

    def select(self, colunas: str = "*", *_a, count=None, **_k):
        if colunas != "*":
            self._colunas = tuple(c.strip() for c in colunas.split(","))
        self._contar = count == "exact"
        return self

    def insert(self, payload: dict):
        self._insert = dict(payload)
        return self

    def update(self, payload: dict):
        self._update = dict(payload)
        return self

    def delete(self):
        raise AssertionError(f"ninguém apaga linha de {self.nome}")

    @property
    def not_(self):
        return _Negado(self)

    def eq(self, col, valor):
        self._filtros.append(lambda r, c=col, v=valor: r.get(c) == v)
        return self

    def is_(self, col, valor):
        assert valor == "null"
        self._filtros.append(lambda r, c=col: r.get(c) is None)
        return self

    def in_(self, col, valores):
        self._filtros.append(lambda r, c=col, v=tuple(valores): r.get(c) in v)
        return self

    def gte(self, col, valor):
        self._filtros.append(lambda r, c=col, v=valor: _instante(r.get(c)) >= _instante(v))
        return self

    def lt(self, col, valor):
        self._filtros.append(lambda r, c=col, v=valor: _instante(r.get(c)) < _instante(v))
        return self

    def order(self, col, desc=False):
        self._ordem.append((col, desc))
        return self

    def limit(self, _n):
        return self

    def range(self, inicio, fim):
        self._recorte = (inicio, fim)
        return self

    def execute(self):
        if self._banco.quebrar == self.nome:
            raise RuntimeError("PostgREST fora do ar")
        linhas = self._banco.tabelas.setdefault(self.nome, [])
        if self._insert is not None:
            linha = {"id": f"{self.nome}-{len(linhas) + 1}", **self._insert}
            if self.nome == "ouvidoria_protocolos":
                if linha.get("avaliacao_id") and any(
                    r.get("avaliacao_id") == linha["avaliacao_id"] for r in linhas
                ):
                    from postgrest.exceptions import APIError

                    raise APIError({"code": "23505", "message": "duplicate key", "details": "", "hint": ""})
                linha.setdefault("protocolo", f"2026-{len(linhas) + 1:04d}")
                linha.setdefault("status", "em_classificacao")
            linhas.append(linha)
            self._banco.escritas.append((self.nome, "insert", dict(linha)))
            return type("R", (), {"data": [dict(linha)], "count": None})()
        casadas = [r for r in linhas if all(f(r) for f in self._filtros)]
        if self._update is not None:
            for r in casadas:
                r.update(self._update)
            self._banco.escritas.append((self.nome, "update", dict(self._update)))
        for col, desc in reversed(self._ordem):
            casadas = sorted(casadas, key=lambda r, c=col: str(r.get(c) or ""), reverse=desc)
        total = len(casadas)
        if self._recorte:
            casadas = casadas[self._recorte[0] : self._recorte[1] + 1]
        dados = [({c: r.get(c) for c in self._colunas} if self._colunas else dict(r)) for r in casadas]
        return type("R", (), {"data": dados, "count": total if self._contar else None})()


def _instante(valor) -> dt.datetime:
    return valor if isinstance(valor, dt.datetime) else dt.datetime.fromisoformat(str(valor))


class _Banco:
    def __init__(self, avaliacoes: list[dict] | None = None, pontos: list[dict] | None = None):
        self.escritas: list[tuple[str, str, dict]] = []
        self.quebrar: str | None = None
        self.tabelas: dict[str, list[dict]] = {
            "ouvidoria_pontos": pontos if pontos is not None else [PONTO_EMERGENCIA, PONTO_CENTRO],
            "ouvidoria_avaliacoes": avaliacoes or [],
            "ouvidoria_protocolos": [],
            "ouvidoria_movimentos": [],
        }

    def table(self, nome: str):
        return _Tabela(self, nome)

    @property
    def avaliacoes(self) -> list[dict]:
        return self.tabelas["ouvidoria_avaliacoes"]

    @property
    def casos(self) -> list[dict]:
        return self.tabelas["ouvidoria_protocolos"]

    @property
    def movimentos(self) -> list[dict]:
        return self.tabelas["ouvidoria_movimentos"]


def _cliente(monkeypatch, participante: dict, banco: _Banco) -> TestClient:
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
    app.dependency_overrides[get_supabase_client] = lambda: banco
    return TestClient(app)


ROTAS = [
    ("get", "/api/ouvidoria/avaliacoes/numeros", None),
    ("get", "/api/ouvidoria/avaliacoes", None),
    ("post", "/api/ouvidoria/avaliacoes/av-1/conversao", None),
    ("post", "/api/ouvidoria/avaliacoes/av-1/arquivamento", {"motivo": "Já tratado por telefone"}),
]


class TestSoOPerfilDaOuvidoria:
    """CA: Super admin sem perfil da Ouvidoria e equipe de Reuniões recebem 403."""

    @pytest.mark.parametrize("quem", [SUPER_ADMIN, SECRETARIA, FACILITADOR], ids=["super_admin", "secretaria", "facilitador"])
    @pytest.mark.parametrize(("metodo", "rota", "corpo"), ROTAS, ids=["numeros", "lista", "conversao", "arquivamento"])
    def test_quem_esta_fora_da_ouvidoria_recebe_403_e_nada_muda(self, monkeypatch, quem, metodo, rota, corpo):
        banco = _Banco([_avaliacao("av-1", "2026-11-12T13:00:00+00:00", 1, comentario="Me trataram mal", revisar=True)])
        client = _cliente(monkeypatch, quem, banco)

        r = getattr(client, metodo)(rota, **({"json": corpo} if corpo else {}))

        assert r.status_code == 403, r.text
        assert banco.escritas == []

    @pytest.mark.parametrize("quem", [OUVIDOR, DIRETORIA], ids=["ouvidor", "diretoria"])
    def test_o_ouvidor_e_a_diretoria_abrem_a_aba(self, monkeypatch, quem):
        banco = _Banco([_avaliacao("av-1", "2026-11-12T13:00:00+00:00", 4)])
        client = _cliente(monkeypatch, quem, banco)

        assert client.get("/api/ouvidoria/avaliacoes/numeros").status_code == 200
        assert client.get("/api/ouvidoria/avaliacoes").status_code == 200


def _avaliacoes_do_periodo() -> list[dict]:
    """Cinco notas dentro dos últimos 30 dias (15/10 a 13/11, no fuso do
    hospital) e duas fora, uma de cada lado da janela."""
    return [
        # Quinta 12/11, 10h: manhã.
        _avaliacao("av-a", "2026-11-12T13:00:00+00:00", 5),
        # Quinta 12/11, 19h30: noite.
        _avaliacao("av-b", "2026-11-12T22:30:00+00:00", 4),
        # Terça 10/11, 2h: madrugada; pediu retorno.
        _avaliacao("av-c", "2026-11-10T05:00:00+00:00", 1, ponto=PONTO_CENTRO, pediu_retorno=True),
        # Segunda 02/11, 14h: tarde.
        _avaliacao("av-d", "2026-11-02T17:00:00+00:00", 2, ponto=PONTO_CENTRO),
        # Quinta 15/10, 0h30: o primeiro dia da janela, de madrugada.
        _avaliacao("av-e", "2026-10-15T03:30:00+00:00", 3),
        # Quarta 14/10, 23h30 em Brasília: um dia antes da janela.
        _avaliacao("av-fora-antes", "2026-10-15T02:30:00+00:00", 1),
        # Sábado 14/11, 0h30 em Brasília: depois de hoje.
        _avaliacao("av-fora-depois", "2026-11-14T03:30:00+00:00", 1),
    ]


class TestOsNumerosBatemComOPeriodo:
    """CA: os indicadores batem com as avaliações do período."""

    def test_indicadores_dos_ultimos_30_dias_por_padrao(self, monkeypatch):
        client = _cliente(monkeypatch, OUVIDOR, _Banco(_avaliacoes_do_periodo()))

        r = client.get("/api/ouvidoria/avaliacoes/numeros")

        assert r.status_code == 200, r.text
        corpo = r.json()
        assert corpo["periodo"] == "30d"
        assert corpo["intervalo"] == {"inicio": "2026-10-15", "fim": "2026-11-13"}
        assert corpo["indicadores"] == {
            "volume": 5,
            "nota_media": 3.0,
            "pct_4_e_5": 0.4,
            "pct_pediu_retorno": 0.2,
        }

    def test_nota_media_por_ponto(self, monkeypatch):
        client = _cliente(monkeypatch, OUVIDOR, _Banco(_avaliacoes_do_periodo()))

        por_ponto = client.get("/api/ouvidoria/avaliacoes/numeros").json()["por_ponto"]

        assert {p["nome"]: (p["nota_media"], p["volume"]) for p in por_ponto} == {
            "Emergência adulta": (4.0, 3),
            "Centro médico": (1.5, 2),
        }

    def test_nota_media_por_turno_no_fuso_do_hospital(self, monkeypatch):
        client = _cliente(monkeypatch, OUVIDOR, _Banco(_avaliacoes_do_periodo()))

        por_turno = client.get("/api/ouvidoria/avaliacoes/numeros").json()["por_turno"]

        assert [(t["turno"], t["nota_media"], t["volume"]) for t in por_turno] == [
            ("manha", 5.0, 1),
            ("tarde", 2.0, 1),
            ("noite", 4.0, 1),
            ("madrugada", 2.0, 2),
        ]

    def test_nota_media_por_dia_da_semana(self, monkeypatch):
        client = _cliente(monkeypatch, OUVIDOR, _Banco(_avaliacoes_do_periodo()))

        por_dia = client.get("/api/ouvidoria/avaliacoes/numeros").json()["por_dia_da_semana"]

        assert [(d["dia"], d["nota_media"], d["volume"]) for d in por_dia] == [
            ("seg", 2.0, 1),
            ("ter", 1.0, 1),
            ("qua", None, 0),
            ("qui", 4.0, 3),
            ("sex", None, 0),
            ("sab", None, 0),
            ("dom", None, 0),
        ]

    def test_evolucao_semanal_com_as_semanas_vazias(self, monkeypatch):
        client = _cliente(monkeypatch, OUVIDOR, _Banco(_avaliacoes_do_periodo()))

        por_semana = client.get("/api/ouvidoria/avaliacoes/numeros").json()["por_semana"]

        assert [(s["semana"], s["nota_media"], s["volume"]) for s in por_semana] == [
            ("2026-10-12", 3.0, 1),
            ("2026-10-19", None, 0),
            ("2026-10-26", None, 0),
            ("2026-11-02", 2.0, 1),
            ("2026-11-09", 3.33, 3),
        ]

    def test_o_filtro_de_periodo_muda_a_janela(self, monkeypatch):
        client = _cliente(monkeypatch, OUVIDOR, _Banco(_avaliacoes_do_periodo()))

        corpo = client.get("/api/ouvidoria/avaliacoes/numeros", params={"periodo": "7d"}).json()

        assert corpo["intervalo"] == {"inicio": "2026-11-07", "fim": "2026-11-13"}
        assert corpo["indicadores"] == {
            "volume": 3,
            "nota_media": 3.33,
            "pct_4_e_5": 0.6667,
            "pct_pediu_retorno": 0.3333,
        }

    def test_periodo_sem_nota_nao_inventa_media(self, monkeypatch):
        client = _cliente(monkeypatch, OUVIDOR, _Banco([]))

        corpo = client.get("/api/ouvidoria/avaliacoes/numeros").json()

        assert corpo["indicadores"] == {"volume": 0, "nota_media": None, "pct_4_e_5": None, "pct_pediu_retorno": None}
        assert corpo["por_ponto"] == []

    def test_periodo_fora_da_lista_e_422(self, monkeypatch):
        client = _cliente(monkeypatch, OUVIDOR, _Banco([]))

        assert client.get("/api/ouvidoria/avaliacoes/numeros", params={"periodo": "2d"}).status_code == 422
