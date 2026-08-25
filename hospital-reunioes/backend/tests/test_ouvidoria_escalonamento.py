"""Escada de escalonamento e crítico imediato (issue #336, PRD #318, ADR 0034 decisão 12).

A cobrança sobe sozinha quando ninguém responde: véspera avisa o titular; no
vencimento, titular e substituto (degrau já entregue na issue #327); 24h úteis
depois, o gestor da área; 48h úteis depois, a Diretoria Executiva. Caso crítico
validado avisa a Diretoria na hora, sem esperar prazo nenhum.

Cobre os critérios de aceite pelo seam do service (a função que o scheduler
chama) e pelo seam HTTP da validação (o crítico imediato), mais o registro do
job no scheduler e a migration. O Resend nunca é chamado de verdade: o envio é
mockado no ponto único por onde todo email do app passa.
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
from app.services import ouvidoria_escalonamento, ouvidoria_notificacoes  # noqa: E402

OUVIDOR = {"id": "P10", "nome_completo": "Marta Ouvidora", "access_profile": None, "perfil_ouvidoria": "ouvidor"}

SEM_FERIADOS: frozenset[dt.date] = frozenset()

# O caso de referência: validado na quinta 20/08/2026 às 11h de Brasília, com
# prazo da área vencendo na terça 25/08 às 14h. Os quatro gatilhos do motor
# (issue #331) caem, então, dentro do expediente:
#   véspera   = segunda 24/08, 14h de Brasília
#   vencimento= terça   25/08, 14h
#   +24h      = quarta  26/08, 14h
#   +48h      = quinta  27/08, 14h
VALIDADA_EM = "2026-08-20T14:00:00+00:00"
VENCIMENTO = "2026-08-25T17:00:00+00:00"

ANTES_DA_VESPERA = dt.datetime(2026, 8, 24, 16, 0, tzinfo=dt.UTC)  # segunda, 13h de Brasília
NA_VESPERA = dt.datetime(2026, 8, 24, 17, 0, tzinfo=dt.UTC)  # segunda, 14h
NO_MAIS_24H = dt.datetime(2026, 8, 26, 17, 0, tzinfo=dt.UTC)  # quarta, 14h
NO_MAIS_48H = dt.datetime(2026, 8, 27, 17, 0, tzinfo=dt.UTC)  # quinta, 14h

# O mesmo caso com o prazo vencendo às 17h (fechamento): aí os gatilhos caem
# fora do expediente e a janela comercial entra em cena.
VENCIMENTO_NO_FECHAMENTO = "2026-08-25T20:00:00+00:00"
VESPERA_NO_FECHAMENTO = dt.datetime(2026, 8, 24, 20, 0, tzinfo=dt.UTC)  # segunda, 17h
MAIS_24H_NO_FECHAMENTO = dt.datetime(2026, 8, 26, 20, 0, tzinfo=dt.UTC)  # quarta, 17h
ABERTURA_DE_TERCA = dt.datetime(2026, 8, 25, 11, 0, tzinfo=dt.UTC)  # terça, 8h de Brasília
ABERTURA_DE_QUINTA = dt.datetime(2026, 8, 27, 11, 0, tzinfo=dt.UTC)  # quinta, 8h

FORA_DO_EXPEDIENTE = dt.datetime(2026, 8, 26, 1, 30, tzinfo=dt.UTC)  # 22h30 de terça em Brasília


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


@pytest.fixture(autouse=True)
def _nunca_envia_email_de_verdade(monkeypatch):
    """O pytest do backend carrega o .env real (Resend de produção). Todo teste
    deste arquivo passa pelo mock, mesmo os que não olham o email."""
    enviados: list[dict] = []

    def _fake(destinatario, assunto, html_content, texto_fallback):
        enviados.append(
            {
                "destinatario": destinatario,
                "assunto": assunto,
                "html": html_content,
                "texto": texto_fallback,
            }
        )
        return True

    monkeypatch.setattr(ouvidoria_notificacoes, "_enviar_email", _fake)
    return enviados


def _manifestacao(numero: int = 7, **overrides) -> dict:
    row = {
        "id": f"uuid-{numero}",
        "numero": numero,
        "protocolo": f"2026-{numero:04d}",
        "status": "aguardando_area",
        "categoria": "Demora no atendimento",
        "setor": "Recepcao",
        "resumo": "Paciente relata espera acima de duas horas na recepcao.",
        "extrato_para_o_setor": "Espera acima de duas horas na recepcao. Apurar e responder a Ouvidoria.",
        "manifestante_nome": "Joana da Silva",
        "anonimo": False,
        "sigilo_reforcado": False,
        "gravidade": "medio",
        "prazo_area_em": VENCIMENTO,
        "prazo_rompido_em": None,
        "vespera_avisada_em": None,
        "escalonado_gestor_em": None,
        "escalonado_diretoria_em": None,
        "critico_avisado_em": None,
        "validada_em": VALIDADA_EM,
        "validada_por": "P10",
    }
    row.update(overrides)
    return row


def _responsavel(papel: str = "titular", **overrides) -> dict:
    row = {
        "id": f"resp-{papel}",
        "setor": "Recepcao",
        "papel": papel,
        "nome": f"Carlos {papel.capitalize()}",
        "email": f"{papel}@hsm.br",
        "vigencia_inicio": "2026-01-01",
        "vigencia_fim": None,
    }
    row.update(overrides)
    return row


def _diretor(numero: int = 1) -> dict:
    return {
        "id": f"D{numero:02d}",
        "nome_completo": f"Diretor {numero}",
        "email": f"diretoria{numero}@hsm.br",
        "perfil_ouvidoria": "diretoria_executiva",
    }


class _TabelaFake:
    """Fake do PostgREST fiel no que importa: o select projeta só o que foi
    pedido, o update filtra antes de gravar (inclusive IS NULL) e o insert
    devolve a linha com o id que o banco geraria."""

    def __init__(self, nome: str, rows: list[dict]):
        self.nome = nome
        self.rows = rows
        self._filters: dict = {}
        self._nulos: list[str] = []
        self._ate: dict = {}
        self._insert: dict | list | None = None
        self._update: dict | None = None
        self._colunas: tuple[str, ...] | None = None
        self._limite: int | None = None

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

    def eq(self, col, value):
        self._filters[col] = value
        return self

    def is_(self, col, value):
        assert value in ("null", None)
        self._nulos.append(col)
        return self

    def lte(self, col, value):
        self._ate[col] = value
        return self

    def order(self, col, desc=False):
        self.rows = sorted(self.rows, key=lambda r: str(r.get(col) or ""), reverse=desc)
        return self

    def limit(self, n):
        self._limite = n
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
        casadas = [
            r
            for r in self.rows
            if all(r.get(c) == v for c, v in self._filters.items())
            and all(r.get(c) is None for c in self._nulos)
            and all(str(r.get(c) or "") <= v for c, v in self._ate.items())
        ]
        if self._update is not None:
            for r in casadas:
                r.update(self._update)
        if self._limite is not None:
            casadas = casadas[: self._limite]
        return type("R", (), {"data": [self._projetar(r) for r in casadas]})()


class _TabelaQueFalhaNoInsert(_TabelaFake):
    def execute(self):
        if self._insert is not None:
            raise RuntimeError("insert recusado (simulando CHECK antigo no banco)")
        return super().execute()


class _SupabaseFake:
    def __init__(
        self,
        manifestacoes: list[dict] | None = None,
        responsaveis: list[dict] | None = None,
        diretoria: list[dict] | None = None,
    ):
        self.falhar_inserts: set[str] = set()
        participantes = [{"id": "P03", "nome_completo": "Pedro Admin", "email": "admin@hsm.br"}]
        participantes.extend(diretoria if diretoria is not None else [_diretor(1)])
        self.tabelas: dict[str, list[dict]] = {
            "ouvidoria_protocolos": manifestacoes if manifestacoes is not None else [_manifestacao()],
            "ouvidoria_movimentos": [],
            "ouvidoria_notificacoes": [],
            "ouvidoria_setor_responsaveis": (
                responsaveis
                if responsaveis is not None
                else [_responsavel("titular"), _responsavel("substituto"), _responsavel("gestor")]
            ),
            "participantes": participantes,
        }

    def table(self, nome: str):
        classe = _TabelaQueFalhaNoInsert if nome in self.falhar_inserts else _TabelaFake
        return classe(nome, self.tabelas.setdefault(nome, []))

    def rpc(self, _nome, _args):
        return self

    def execute(self):  # pragma: no cover - só a validação usa a RPC
        return type("R", (), {"data": self.tabelas["ouvidoria_protocolos"][0]})()


def _client(monkeypatch, supabase: _SupabaseFake, agora: dt.datetime):
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(RequestContextMiddleware)
    app.include_router(ouvidoria_router.router, prefix="/api")

    async def _fake_participante(_user, _sb, fields=None):
        return OUVIDOR

    monkeypatch.setattr(ouvidoria_router, "get_participante_for_user", _fake_participante)
    monkeypatch.setattr(ouvidoria_router, "agora_utc", lambda: agora)
    app.dependency_overrides[get_current_user] = lambda: {"id": "u1", "email": "u@hsm.br"}
    app.dependency_overrides[get_supabase_client] = lambda: supabase
    return TestClient(app)


def _emails_por_destinatario(enviados: list[dict]) -> set[str]:
    return {e["destinatario"] for e in enviados}


class TestVespera:
    """Degrau 1: a véspera do vencimento avisa só o titular."""

    def test_vespera_notifica_o_titular(self, _nunca_envia_email_de_verdade):
        supabase = _SupabaseFake()

        degraus = ouvidoria_escalonamento.escalar_prazos(supabase, NA_VESPERA, SEM_FERIADOS)

        assert degraus == 1
        # O substituto e o gestor entram nos degraus seguintes, não neste.
        assert _emails_por_destinatario(_nunca_envia_email_de_verdade) == {"titular@hsm.br"}
        registros = supabase.tabelas["ouvidoria_notificacoes"]
        assert [r["gatilho"] for r in registros] == [ouvidoria_notificacoes.GATILHO_VESPERA_VENCIMENTO]
        assert registros[0]["papel_destinatario"] == "titular"
        html = _nunca_envia_email_de_verdade[0]["html"]
        assert "2026-0007" in html
        assert "vence em" in html

    def test_vespera_nao_dispara_antes_da_hora(self, _nunca_envia_email_de_verdade):
        supabase = _SupabaseFake()

        degraus = ouvidoria_escalonamento.escalar_prazos(supabase, ANTES_DA_VESPERA, SEM_FERIADOS)

        assert degraus == 0
        assert _nunca_envia_email_de_verdade == []
        assert supabase.tabelas["ouvidoria_protocolos"][0]["vespera_avisada_em"] is None

    def test_prazo_curto_demais_nao_tem_vespera(self, _nunca_envia_email_de_verdade):
        """Caso validado depois do instante da véspera (prazo de horas, típico
        do crítico) não tem "vence amanhã" a avisar: o motor devolve véspera
        None e o degrau simplesmente não existe."""
        supabase = _SupabaseFake(
            manifestacoes=[_manifestacao(validada_em="2026-08-25T13:00:00+00:00")],
        )

        degraus = ouvidoria_escalonamento.escalar_prazos(supabase, NA_VESPERA, SEM_FERIADOS)

        assert degraus == 0
        assert _nunca_envia_email_de_verdade == []

    def test_vespera_no_fechamento_espera_a_abertura_do_expediente(self, _nunca_envia_email_de_verdade):
        """Notificação não crítica respeita a janela comercial: a véspera de um
        prazo que vence às 17h cai no fechamento e sai na abertura seguinte."""
        supabase = _SupabaseFake(manifestacoes=[_manifestacao(prazo_area_em=VENCIMENTO_NO_FECHAMENTO)])

        degraus = ouvidoria_escalonamento.escalar_prazos(supabase, VESPERA_NO_FECHAMENTO, SEM_FERIADOS)

        assert degraus == 1
        assert _nunca_envia_email_de_verdade == []
        registro = supabase.tabelas["ouvidoria_notificacoes"][0]
        assert registro["status"] == "agendada"
        assert dt.datetime.fromisoformat(registro["enviar_a_partir_de"]) == ABERTURA_DE_TERCA


class TestDegrauDoGestor:
    """Degrau 3: 24h úteis depois do vencimento, sem resposta, cobra o gestor."""

    def test_mais_24h_sem_resposta_notifica_o_gestor_da_area(self, _nunca_envia_email_de_verdade):
        supabase = _SupabaseFake(manifestacoes=[_manifestacao(vespera_avisada_em=NA_VESPERA.isoformat())])

        degraus = ouvidoria_escalonamento.escalar_prazos(supabase, NO_MAIS_24H, SEM_FERIADOS)

        assert degraus == 1
        assert _emails_por_destinatario(_nunca_envia_email_de_verdade) == {"gestor@hsm.br"}
        registro = supabase.tabelas["ouvidoria_notificacoes"][0]
        assert registro["gatilho"] == ouvidoria_notificacoes.GATILHO_ESCALONAMENTO_GESTOR
        assert registro["papel_destinatario"] == "gestor"

    def test_sem_gestor_cadastrado_o_degrau_alerta_a_diretoria(self, _nunca_envia_email_de_verdade):
        """Sem gestor no cadastro do setor, o degrau não some: vira o alerta à
        Diretoria (critério de aceite da issue #336)."""
        supabase = _SupabaseFake(
            manifestacoes=[_manifestacao(vespera_avisada_em=NA_VESPERA.isoformat())],
            responsaveis=[_responsavel("titular"), _responsavel("substituto")],
        )

        degraus = ouvidoria_escalonamento.escalar_prazos(supabase, NO_MAIS_24H, SEM_FERIADOS)

        assert degraus == 1
        assert _emails_por_destinatario(_nunca_envia_email_de_verdade) == {"diretoria1@hsm.br"}
        registro = supabase.tabelas["ouvidoria_notificacoes"][0]
        assert registro["gatilho"] == ouvidoria_notificacoes.GATILHO_ESCALONAMENTO_DIRETORIA
        assert registro["papel_destinatario"] == "diretoria_executiva"
        # A Diretoria precisa saber POR QUE o caso chegou nela um dia antes.
        assert "gestor" in (registro["detalhe"] or "").lower()

    def test_sem_gestor_e_sem_diretoria_o_caso_volta_na_proxima_rodada(self, _nunca_envia_email_de_verdade):
        """Nenhum destinatário não queima o degrau: sem carimbo, a rodada
        seguinte tenta de novo quando alguém for cadastrado."""
        supabase = _SupabaseFake(
            manifestacoes=[_manifestacao(vespera_avisada_em=NA_VESPERA.isoformat())],
            responsaveis=[_responsavel("titular")],
            diretoria=[],
        )

        degraus = ouvidoria_escalonamento.escalar_prazos(supabase, NO_MAIS_24H, SEM_FERIADOS)

        assert degraus == 0
        assert _nunca_envia_email_de_verdade == []
        assert supabase.tabelas["ouvidoria_protocolos"][0]["escalonado_gestor_em"] is None

        supabase.tabelas["participantes"].append(_diretor(2))
        degraus = ouvidoria_escalonamento.escalar_prazos(supabase, NO_MAIS_24H + dt.timedelta(minutes=10), SEM_FERIADOS)
        assert degraus == 1
        assert _emails_por_destinatario(_nunca_envia_email_de_verdade) == {"diretoria2@hsm.br"}


class TestDegrauDaDiretoria:
    """Degrau 4: 48h úteis depois do vencimento, a Diretoria Executiva."""

    def test_mais_48h_sem_resposta_notifica_a_diretoria_executiva(self, _nunca_envia_email_de_verdade):
        supabase = _SupabaseFake(
            manifestacoes=[
                _manifestacao(
                    vespera_avisada_em=NA_VESPERA.isoformat(),
                    escalonado_gestor_em=NO_MAIS_24H.isoformat(),
                )
            ],
            diretoria=[_diretor(1), _diretor(2)],
        )

        degraus = ouvidoria_escalonamento.escalar_prazos(supabase, NO_MAIS_48H, SEM_FERIADOS)

        assert degraus == 1
        assert _emails_por_destinatario(_nunca_envia_email_de_verdade) == {
            "diretoria1@hsm.br",
            "diretoria2@hsm.br",
        }
        registros = supabase.tabelas["ouvidoria_notificacoes"]
        assert {r["gatilho"] for r in registros} == {ouvidoria_notificacoes.GATILHO_ESCALONAMENTO_DIRETORIA}
        # A Diretoria tem painel: o email dela não carrega link tokenizado do
        # portal do setor.
        for email in _nunca_envia_email_de_verdade:
            assert "/ouvidoria-setor/" not in email["html"]


class TestIdempotencia:
    """Rodar o job duas vezes não duplica nenhum degrau."""

    def test_rodar_o_job_duas_vezes_nao_duplica_degrau(self, _nunca_envia_email_de_verdade):
        supabase = _SupabaseFake()

        primeira = ouvidoria_escalonamento.escalar_prazos(supabase, NO_MAIS_48H, SEM_FERIADOS)
        segunda = ouvidoria_escalonamento.escalar_prazos(supabase, NO_MAIS_48H + dt.timedelta(minutes=10), SEM_FERIADOS)

        # Caso abandonado desde a véspera: os três degraus deste job sobem na
        # mesma rodada, cada um uma vez.
        assert primeira == 3
        assert segunda == 0
        gatilhos = [r["gatilho"] for r in supabase.tabelas["ouvidoria_notificacoes"]]
        assert sorted(gatilhos) == sorted(
            [
                ouvidoria_notificacoes.GATILHO_VESPERA_VENCIMENTO,
                ouvidoria_notificacoes.GATILHO_ESCALONAMENTO_GESTOR,
                ouvidoria_notificacoes.GATILHO_ESCALONAMENTO_DIRETORIA,
            ]
        )
        assert len(_nunca_envia_email_de_verdade) == 3

    def test_degrau_cuja_notificacao_nao_grava_volta_para_a_proxima_rodada(self, _nunca_envia_email_de_verdade):
        """Cenário do deploy antes da migration: o CHECK antigo recusa o
        gatilho novo. O degrau não pode ficar carimbado sem cobrança nenhuma."""
        supabase = _SupabaseFake()
        supabase.falhar_inserts = {"ouvidoria_notificacoes"}

        degraus = ouvidoria_escalonamento.escalar_prazos(supabase, NA_VESPERA, SEM_FERIADOS)

        assert degraus == 0
        assert supabase.tabelas["ouvidoria_protocolos"][0]["vespera_avisada_em"] is None
        assert supabase.tabelas["ouvidoria_movimentos"] == []

        supabase.falhar_inserts = set()
        degraus = ouvidoria_escalonamento.escalar_prazos(supabase, NA_VESPERA + dt.timedelta(minutes=10), SEM_FERIADOS)
        assert degraus == 1
        assert _emails_por_destinatario(_nunca_envia_email_de_verdade) == {"titular@hsm.br"}

    def test_caso_que_respondeu_nao_escala(self, _nunca_envia_email_de_verdade):
        supabase = _SupabaseFake(manifestacoes=[_manifestacao(status="respondido")])

        degraus = ouvidoria_escalonamento.escalar_prazos(supabase, NO_MAIS_48H, SEM_FERIADOS)

        assert degraus == 0
        assert _nunca_envia_email_de_verdade == []

    def test_area_que_responde_antes_do_envio_nao_recebe_o_escalonamento(self, _nunca_envia_email_de_verdade):
        """Degrau retido pela janela comercial: se a área responde durante a
        noite, o job da fila não manda a cobrança de manhã."""
        supabase = _SupabaseFake(manifestacoes=[_manifestacao(prazo_area_em=VENCIMENTO_NO_FECHAMENTO)])
        ouvidoria_escalonamento.escalar_prazos(supabase, VESPERA_NO_FECHAMENTO, SEM_FERIADOS)
        assert _nunca_envia_email_de_verdade == []

        supabase.tabelas["ouvidoria_protocolos"][0]["status"] = "respondido"
        entregues = ouvidoria_notificacoes.despachar_pendentes(supabase, ABERTURA_DE_TERCA, SEM_FERIADOS)

        assert entregues == 0
        assert _nunca_envia_email_de_verdade == []
        registro = supabase.tabelas["ouvidoria_notificacoes"][0]
        assert registro["status"] == "falha"
        assert "respondeu antes" in registro["ultimo_erro"]


class TestTrilhaERegistro:
    """Cada degrau é registrado, reenviável e aparece na trilha do caso."""

    def test_cada_degrau_vira_movimento_na_trilha(self):
        supabase = _SupabaseFake()

        ouvidoria_escalonamento.escalar_prazos(supabase, NO_MAIS_48H, SEM_FERIADOS)
        ouvidoria_escalonamento.escalar_prazos(supabase, NO_MAIS_48H + dt.timedelta(minutes=10), SEM_FERIADOS)

        movimentos = supabase.tabelas["ouvidoria_movimentos"]
        assert len(movimentos) == 3
        for movimento in movimentos:
            # Escalonamento não muda o estado do caso: a trilha registra o fato
            # com o caso parado em aguardando_area.
            assert movimento["estado_anterior"] == "aguardando_area"
            assert movimento["estado_novo"] == "aguardando_area"
            assert movimento["autor_id"] is None
        observacoes = " | ".join(m["observacao"] for m in movimentos).lower()
        assert "véspera" in observacoes
        assert "gestor" in observacoes
        assert "diretoria" in observacoes

    def test_degrau_e_reenviavel_pelo_botao_da_ouvidoria(self, monkeypatch, _nunca_envia_email_de_verdade):
        supabase = _SupabaseFake()
        ouvidoria_escalonamento.escalar_prazos(supabase, NA_VESPERA, SEM_FERIADOS)
        registro = supabase.tabelas["ouvidoria_notificacoes"][0]

        client = _client(monkeypatch, supabase, NA_VESPERA)
        resposta = client.post(f"/api/ouvidoria/manifestacoes/uuid-7/notificacoes/{registro['id']}/reenviar")

        assert resposta.status_code == 201
        assert resposta.json()["gatilho"] == ouvidoria_notificacoes.GATILHO_VESPERA_VENCIMENTO
        assert resposta.json()["entregue"] is True
        assert len(_nunca_envia_email_de_verdade) == 2

    def test_alerta_a_diretoria_por_falta_de_gestor_e_reenviavel_com_o_mesmo_motivo(
        self, monkeypatch, _nunca_envia_email_de_verdade
    ):
        """O reenvio copia o `detalhe`: o email remontado explica de novo que o
        setor não tem gestor."""
        supabase = _SupabaseFake(
            manifestacoes=[_manifestacao(vespera_avisada_em=NA_VESPERA.isoformat())],
            responsaveis=[_responsavel("titular")],
        )
        ouvidoria_escalonamento.escalar_prazos(supabase, NO_MAIS_24H, SEM_FERIADOS)
        registro = supabase.tabelas["ouvidoria_notificacoes"][0]

        client = _client(monkeypatch, supabase, NO_MAIS_24H)
        resposta = client.post(f"/api/ouvidoria/manifestacoes/uuid-7/notificacoes/{registro['id']}/reenviar")

        assert resposta.status_code == 201
        assert "gestor" in (supabase.tabelas["ouvidoria_notificacoes"][-1]["detalhe"] or "").lower()
        assert len(_nunca_envia_email_de_verdade) == 2


class TestJanelaComercial:
    """Notificação não crítica respeita o horário comercial; crítica ignora."""

    def test_degrau_nao_critico_no_fechamento_espera_a_abertura(self, _nunca_envia_email_de_verdade):
        supabase = _SupabaseFake(
            manifestacoes=[
                _manifestacao(
                    prazo_area_em=VENCIMENTO_NO_FECHAMENTO,
                    vespera_avisada_em=VESPERA_NO_FECHAMENTO.isoformat(),
                )
            ]
        )

        degraus = ouvidoria_escalonamento.escalar_prazos(supabase, MAIS_24H_NO_FECHAMENTO, SEM_FERIADOS)

        assert degraus == 1
        assert _nunca_envia_email_de_verdade == []
        registro = supabase.tabelas["ouvidoria_notificacoes"][0]
        assert dt.datetime.fromisoformat(registro["enviar_a_partir_de"]) == ABERTURA_DE_QUINTA

    def test_degrau_de_caso_critico_ignora_a_janela(self, _nunca_envia_email_de_verdade):
        supabase = _SupabaseFake(
            manifestacoes=[
                _manifestacao(
                    gravidade="critico",
                    prazo_area_em=VENCIMENTO_NO_FECHAMENTO,
                    vespera_avisada_em=VESPERA_NO_FECHAMENTO.isoformat(),
                )
            ]
        )

        degraus = ouvidoria_escalonamento.escalar_prazos(supabase, MAIS_24H_NO_FECHAMENTO, SEM_FERIADOS)

        assert degraus == 1
        assert _emails_por_destinatario(_nunca_envia_email_de_verdade) == {"gestor@hsm.br"}


class TestCriticoImediato:
    """Caso crítico validado notifica a Diretoria na hora, sem esperar prazo."""

    def _pedido(self, gravidade: str) -> dict:
        return {
            "categoria": "Demora no atendimento",
            "setor": "Recepcao",
            "gravidade": gravidade,
            "extrato_para_o_setor": "Apurar a espera relatada e responder a Ouvidoria.",
        }

    def _caso_novo(self) -> dict:
        return _manifestacao(
            status="em_classificacao",
            gravidade=None,
            prazo_area_em=None,
            validada_em=None,
            validada_por=None,
            extrato_para_o_setor=None,
        )

    def test_caso_critico_validado_avisa_a_diretoria_na_hora(self, monkeypatch, _nunca_envia_email_de_verdade):
        supabase = _SupabaseFake(manifestacoes=[self._caso_novo()], diretoria=[_diretor(1), _diretor(2)])
        client = _client(monkeypatch, supabase, FORA_DO_EXPEDIENTE)

        resposta = client.post("/api/ouvidoria/manifestacoes/uuid-7/validar", json=self._pedido("critico"))

        assert resposta.status_code == 200
        criticos = [
            r
            for r in supabase.tabelas["ouvidoria_notificacoes"]
            if r["gatilho"] == ouvidoria_notificacoes.GATILHO_CRITICO_IMEDIATO
        ]
        assert {r["destinatario_email"] for r in criticos} == {"diretoria1@hsm.br", "diretoria2@hsm.br"}
        # Fora do expediente e mesmo assim entregue: crítico não espera a janela.
        assert all(r["status"] == "enviada" for r in criticos)
        assert {"diretoria1@hsm.br", "diretoria2@hsm.br"} <= _emails_por_destinatario(_nunca_envia_email_de_verdade)
        assert supabase.tabelas["ouvidoria_protocolos"][0]["critico_avisado_em"] is not None

    def test_caso_nao_critico_validado_nao_aciona_a_diretoria(self, monkeypatch, _nunca_envia_email_de_verdade):
        supabase = _SupabaseFake(manifestacoes=[self._caso_novo()])
        client = _client(monkeypatch, supabase, FORA_DO_EXPEDIENTE)

        resposta = client.post("/api/ouvidoria/manifestacoes/uuid-7/validar", json=self._pedido("medio"))

        assert resposta.status_code == 200
        gatilhos = {r["gatilho"] for r in supabase.tabelas["ouvidoria_notificacoes"]}
        assert ouvidoria_notificacoes.GATILHO_CRITICO_IMEDIATO not in gatilhos
        assert supabase.tabelas["ouvidoria_protocolos"][0]["critico_avisado_em"] is None

    def test_aviso_critico_entra_na_trilha_do_caso(self, monkeypatch):
        supabase = _SupabaseFake(manifestacoes=[self._caso_novo()])
        client = _client(monkeypatch, supabase, FORA_DO_EXPEDIENTE)

        client.post("/api/ouvidoria/manifestacoes/uuid-7/validar", json=self._pedido("critico"))

        observacoes = " | ".join((m.get("observacao") or "") for m in supabase.tabelas["ouvidoria_movimentos"]).lower()
        assert "crítico" in observacoes
        assert "diretoria" in observacoes


class TestMigration:
    """A 072 abre o CHECK de gatilho para a escada e dá ao caso os carimbos de
    idempotência, reaplicável sem quebrar (padrão da casa)."""

    def _ddl(self) -> str:
        caminho = os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "supabase",
            "migrations",
            "072_ouvidoria_escalonamento.sql",
        )
        with open(caminho, encoding="utf-8") as f:
            return f.read().lower()

    def test_gatilhos_da_escada_entram_no_check(self):
        ddl = self._ddl()
        for gatilho in (
            "vespera_vencimento",
            "escalonamento_gestor",
            "escalonamento_diretoria",
            "critico_imediato",
        ):
            assert f"'{gatilho}'" in ddl
        # Os gatilhos anteriores continuam válidos.
        for gatilho in ("nova_demanda", "alerta_sem_titular", "prazo_rompido"):
            assert f"'{gatilho}'" in ddl
        assert "drop constraint if exists ouvidoria_notificacoes_gatilho_check" in ddl

    def test_cada_degrau_ganha_o_proprio_carimbo(self):
        ddl = self._ddl()
        for coluna in (
            "vespera_avisada_em",
            "escalonado_gestor_em",
            "escalonado_diretoria_em",
            "critico_avisado_em",
        ):
            assert f"add column if not exists {coluna}" in ddl

    def test_migration_e_idempotente(self):
        ddl = self._ddl()
        assert "add column if not exists" in ddl
        assert "create index if not exists" in ddl


class TestJobNoScheduler:
    """A escada sobe sozinha, de tempos em tempos, junto dos demais jobs."""

    def test_job_de_escalonamento_esta_registrado(self):
        from app.cron import scheduler as cron

        try:
            cron.start_scheduler()
            assert cron.scheduler.get_job("escalonamento_ouvidoria") is not None
        finally:
            cron.stop_scheduler()
