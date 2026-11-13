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
                if linha.get("avaliacao_id") and any(r.get("avaliacao_id") == linha["avaliacao_id"] for r in linhas):
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

    @pytest.mark.parametrize(
        "quem", [SUPER_ADMIN, SECRETARIA, FACILITADOR], ids=["super_admin", "secretaria", "facilitador"]
    )
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


COMENTARIO_GRAVE = "A recepcionista gritou comigo e me empurrou na frente de todo mundo."


def _uma_marcada() -> _Banco:
    # Quarta 11/11, 22h40 em Brasília (01h40 de quinta em UTC).
    return _Banco(
        [
            _avaliacao(
                "av-1",
                "2026-11-12T01:40:00+00:00",
                1,
                comentario=COMENTARIO_GRAVE,
                revisar=True,
                motivos=["recepcao"],
            )
        ]
    )


class TestConverterEmManifestacao:
    """CA: converter cria o caso com canal qr, o ponto, a ligação, tipo vazio
    e T0 da avaliação, e marca o desfecho convertida."""

    def test_o_caso_nasce_do_cartaz_com_a_ligacao_e_o_t0_da_avaliacao(self, monkeypatch, _sem_agente):
        banco = _uma_marcada()
        client = _cliente(monkeypatch, OUVIDOR, banco)

        r = client.post("/api/ouvidoria/avaliacoes/av-1/conversao")

        assert r.status_code == 201, r.text
        assert len(banco.casos) == 1
        caso = banco.casos[0]
        assert r.json() == {"id": caso["id"], "protocolo": caso["protocolo"]}
        assert caso["canal"] == "qr"
        assert caso["canal_setor"] == "Pronto Socorro"
        assert caso["canal_ponto"] == "Hall da emergência"
        assert caso["avaliacao_id"] == "av-1"
        assert caso["relato_integral"] == COMENTARIO_GRAVE
        # Tipo vazio: sigiloso até o ouvidor classificar.
        assert caso.get("tipo_manifestacao") is None
        assert caso["sigilo_reforcado"] is True
        assert caso["setor"] == "A definir"
        # T0 é a hora da avaliação, não a do clique; e o dia de abertura é o
        # do hospital (quarta), não o de UTC (quinta).
        assert caso["contato_em"] == "2026-11-12T01:40:00+00:00"
        assert caso["data_abertura"] == "2026-11-11"
        assert caso["anonimo"] is False
        assert caso.get("manifestante_nome") is None
        assert caso.get("manifestante_contato") is None
        assert caso["registrado_por"] == OUVIDOR["id"]

    def test_a_avaliacao_fica_com_o_desfecho_convertida_e_sai_de_para_revisar(self, monkeypatch):
        banco = _uma_marcada()
        client = _cliente(monkeypatch, OUVIDOR, banco)

        client.post("/api/ouvidoria/avaliacoes/av-1/conversao")

        avaliacao = banco.avaliacoes[0]
        assert avaliacao["revisao_desfecho"] == "convertida"
        assert avaliacao["revisada_por"] == OUVIDOR["id"]
        assert avaliacao["revisada_em"] == AGORA.isoformat()
        lista = client.get("/api/ouvidoria/avaliacoes", params={"para_revisar": True}).json()
        assert lista["itens"] == []
        assert lista["para_revisar_total"] == 0
        item = client.get("/api/ouvidoria/avaliacoes").json()["itens"][0]
        assert item["para_revisar"] is False
        assert item["caso"] == {"id": banco.casos[0]["id"], "protocolo": banco.casos[0]["protocolo"]}

    def test_sem_contato_o_caso_nasce_com_a_anotacao_na_trilha(self, monkeypatch):
        banco = _uma_marcada()
        client = _cliente(monkeypatch, OUVIDOR, banco)

        client.post("/api/ouvidoria/avaliacoes/av-1/conversao")

        assert len(banco.movimentos) == 1
        abertura = banco.movimentos[0]
        assert abertura["manifestacao_id"] == banco.casos[0]["id"]
        assert abertura["autor_id"] == OUVIDOR["id"]
        assert "não tem manifestante para retorno" in abertura["observacao"]
        assert "nota 1 de 5" in abertura["observacao"]

    def test_o_agente_de_triagem_le_o_caso_novo(self, monkeypatch, _sem_agente):
        banco = _uma_marcada()
        client = _cliente(monkeypatch, OUVIDOR, banco)

        client.post("/api/ouvidoria/avaliacoes/av-1/conversao")

        assert [caso["id"] for caso in _sem_agente] == [banco.casos[0]["id"]]

    def test_converter_duas_vezes_nao_abre_dois_casos(self, monkeypatch):
        banco = _uma_marcada()
        client = _cliente(monkeypatch, OUVIDOR, banco)

        client.post("/api/ouvidoria/avaliacoes/av-1/conversao")
        r = client.post("/api/ouvidoria/avaliacoes/av-1/conversao")

        assert r.status_code == 409
        assert r.json()["detail"] == "Esta avaliação já virou caso."
        assert len(banco.casos) == 1

    def test_a_nota_que_ja_pediu_retorno_nao_vira_segundo_caso(self, monkeypatch):
        banco = _Banco([_avaliacao("av-1", "2026-11-12T13:00:00+00:00", 2, comentario="Demora", pediu_retorno=True)])
        banco.casos.append({"id": "caso-0", "protocolo": "2026-0001", "avaliacao_id": "av-1"})
        client = _cliente(monkeypatch, OUVIDOR, banco)

        r = client.post("/api/ouvidoria/avaliacoes/av-1/conversao")

        assert r.status_code == 409
        assert len(banco.casos) == 1

    def test_avaliacao_sem_comentario_nao_vira_caso(self, monkeypatch):
        banco = _Banco([_avaliacao("av-1", "2026-11-12T13:00:00+00:00", 1)])
        client = _cliente(monkeypatch, OUVIDOR, banco)

        r = client.post("/api/ouvidoria/avaliacoes/av-1/conversao")

        assert r.status_code == 409
        assert banco.casos == []

    def test_avaliacao_que_nao_existe_e_404(self, monkeypatch):
        client = _cliente(monkeypatch, OUVIDOR, _Banco([]))

        assert client.post("/api/ouvidoria/avaliacoes/nao-existe/conversao").status_code == 404


class TestArquivarRevisao:
    """CA: arquivar revisão exige motivo e tira a marca Para revisar."""

    @pytest.mark.parametrize("corpo", [{}, {"motivo": ""}, {"motivo": "   "}, {"motivo": "x" * 201}])
    def test_sem_motivo_e_recusado_e_a_marca_fica(self, monkeypatch, corpo):
        banco = _uma_marcada()
        client = _cliente(monkeypatch, OUVIDOR, banco)

        r = client.post("/api/ouvidoria/avaliacoes/av-1/arquivamento", json=corpo)

        assert r.status_code == 422
        assert banco.avaliacoes[0]["revisao_desfecho"] is None
        assert client.get("/api/ouvidoria/avaliacoes", params={"para_revisar": True}).json()["para_revisar_total"] == 1

    def test_com_motivo_tira_a_marca_e_guarda_quem_e_por_que(self, monkeypatch):
        banco = _uma_marcada()
        client = _cliente(monkeypatch, OUVIDOR, banco)

        r = client.post("/api/ouvidoria/avaliacoes/av-1/arquivamento", json={"motivo": "  Já tratado por telefone  "})

        assert r.status_code == 200, r.text
        avaliacao = banco.avaliacoes[0]
        assert avaliacao["revisao_desfecho"] == "arquivada"
        assert avaliacao["revisao_motivo"] == "Já tratado por telefone"
        assert avaliacao["revisada_por"] == OUVIDOR["id"]
        assert avaliacao["revisada_em"] == AGORA.isoformat()
        assert banco.casos == []
        lista = client.get("/api/ouvidoria/avaliacoes", params={"para_revisar": True}).json()
        assert lista["itens"] == []
        assert lista["para_revisar_total"] == 0

    def test_avaliacao_sem_a_marca_nao_tem_revisao_para_arquivar(self, monkeypatch):
        banco = _Banco([_avaliacao("av-1", "2026-11-12T13:00:00+00:00", 5, comentario="Ótimo")])
        client = _cliente(monkeypatch, OUVIDOR, banco)

        r = client.post("/api/ouvidoria/avaliacoes/av-1/arquivamento", json={"motivo": "Sem gravidade"})

        assert r.status_code == 409
        assert banco.avaliacoes[0]["revisao_desfecho"] is None

    def test_arquivar_de_novo_nao_reescreve_o_motivo(self, monkeypatch):
        banco = _uma_marcada()
        client = _cliente(monkeypatch, OUVIDOR, banco)

        client.post("/api/ouvidoria/avaliacoes/av-1/arquivamento", json={"motivo": "Primeiro"})
        r = client.post("/api/ouvidoria/avaliacoes/av-1/arquivamento", json={"motivo": "Segundo"})

        assert r.status_code == 409
        assert banco.avaliacoes[0]["revisao_motivo"] == "Primeiro"


class TestAListaComOsFiltros:
    """A lista da aba (seção 4.5): ponto, nota, período, só com comentário e
    Para revisar, a mais nova primeiro."""

    def _banco(self) -> _Banco:
        return _Banco(
            [
                _avaliacao("av-1", "2026-11-12T13:00:00+00:00", 5, comentario="Equipe atenciosa"),
                _avaliacao(
                    "av-2",
                    "2026-11-11T13:00:00+00:00",
                    1,
                    ponto=PONTO_CENTRO,
                    comentario=COMENTARIO_GRAVE,
                    revisar=True,
                ),
                _avaliacao("av-3", "2026-11-10T13:00:00+00:00", 1),
                _avaliacao("av-4", "2026-09-01T13:00:00+00:00", 2, comentario="Antiga", revisar=True),
            ]
        )

    def _ids(self, client, **params) -> list[str]:
        r = client.get("/api/ouvidoria/avaliacoes", params=params)
        assert r.status_code == 200, r.text
        return [item["id"] for item in r.json()["itens"]]

    def test_a_mais_nova_primeiro_dentro_do_periodo(self, monkeypatch):
        client = _cliente(monkeypatch, OUVIDOR, self._banco())

        assert self._ids(client) == ["av-1", "av-2", "av-3"]
        assert self._ids(client, periodo="tudo") == ["av-1", "av-2", "av-3", "av-4"]

    def test_cada_filtro_recorta_a_lista(self, monkeypatch):
        client = _cliente(monkeypatch, OUVIDOR, self._banco())

        assert self._ids(client, ponto_id=PONTO_CENTRO["id"]) == ["av-2"]
        assert self._ids(client, nota=1) == ["av-2", "av-3"]
        assert self._ids(client, com_comentario=True) == ["av-1", "av-2"]
        assert self._ids(client, para_revisar=True) == ["av-2"]
        assert self._ids(client, para_revisar=True, periodo="tudo") == ["av-2", "av-4"]

    def test_o_card_traz_nota_motivos_comentario_ponto_e_data(self, monkeypatch):
        client = _cliente(monkeypatch, OUVIDOR, self._banco())

        corpo = client.get("/api/ouvidoria/avaliacoes").json()
        item = corpo["itens"][1]

        assert item["nota"] == 1
        assert item["comentario"] == COMENTARIO_GRAVE
        assert item["ponto_nome"] == "Centro médico"
        assert item["criada_em"] == "2026-11-11T13:00:00+00:00"
        assert item["para_revisar"] is True
        assert item["revisar_motivo"] == "Relata agressão"
        assert item["caso"] is None
        # O contador é de todas as datas: a marca antiga também espera.
        assert corpo["para_revisar_total"] == 2
        assert corpo["total"] == 3


class TestOKitDeConhecimentoDizOComportamentoNovo:
    """CA: o texto do Produto Ouvidoria no kit de conhecimento diz o
    comportamento novo."""

    @pytest.fixture
    def secao(self) -> str:
        from app.services.conhecimento import CONHECIMENTO_DIR

        texto = (CONHECIMENTO_DIR / "ouvidoria.md").read_text(encoding="utf-8")
        partes = texto.split("\n## ")
        achadas = [parte for parte in partes if parte.startswith("A aba Avaliações\n")]
        assert len(achadas) == 1
        return achadas[0]

    def test_diz_quem_ve_e_o_que_a_aba_mostra(self, secao):
        assert "Só o ouvidor e a diretoria executiva" in secao
        assert "nota média" in secao
        assert "notas 4 e 5" in secao
        assert "pediu retorno" in secao
        assert "por ponto, por turno, por dia da semana e por semana" in secao
        assert "últimos 30 dias" in secao

    def test_diz_como_converter_e_arquivar(self, secao):
        assert "Converter em manifestação" in secao
        assert "hora da avaliação" in secao
        assert "sem tipo" in secao
        assert "não tem para quem responder" in secao
        assert "Arquivar revisão" in secao
        assert "motivo curto" in secao
