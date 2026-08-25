"""Job de estouro e cobrança PRAZO_ROMPIDO (issue #327, PRD #317, ADR 0034 decisão 7).

O degrau do vencimento: um job periódico idempotente varre os casos aguardando
área, acha os prazos vencidos pelo motor de prazos e cobra titular e substituto
do setor, registrando o movimento "prazo rompido" uma única vez por caso. A
escada completa de escalonamento (véspera, gestor, Diretoria) é do PRD #318.

Cobre os critérios de aceite da issue #327 pelo seam do service (a função que o
scheduler chama), mais o registro do job no scheduler e a migration. O Resend
nunca é chamado de verdade: o envio é mockado no ponto único por onde todo
email do app passa.
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
from app.services import ouvidoria_cobranca, ouvidoria_notificacoes  # noqa: E402

OUVIDOR = {"id": "P10", "nome_completo": "Marta Ouvidora", "access_profile": None, "perfil_ouvidoria": "ouvidor"}

# Terça-feira, 14h de Brasília: dentro do expediente e longe de feriado. O
# relógio é congelado porque a janela comercial depende dele.
DENTRO_DO_EXPEDIENTE = dt.datetime(2026, 8, 25, 17, 0, tzinfo=dt.UTC)
FORA_DO_EXPEDIENTE = dt.datetime(2026, 8, 26, 1, 30, tzinfo=dt.UTC)  # 22h30 de terça em Brasília

# Segunda-feira às 17h de Brasília: um vencimento que já passou quando o
# relógio congelado marca terça 14h.
PRAZO_VENCIDO = "2026-08-24T20:00:00+00:00"
# Sexta-feira seguinte: um vencimento ainda no futuro.
PRAZO_NO_FUTURO = "2026-08-28T20:00:00+00:00"

SEM_FERIADOS: frozenset[dt.date] = frozenset()


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
        "prazo_area_em": PRAZO_VENCIDO,
        "prazo_rompido_em": None,
        "validada_em": "2026-08-20T14:00:00+00:00",
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
    def __init__(self, manifestacoes: list[dict] | None = None, responsaveis: list[dict] | None = None):
        self.falhar_inserts: set[str] = set()
        self.tabelas: dict[str, list[dict]] = {
            "ouvidoria_protocolos": manifestacoes if manifestacoes is not None else [_manifestacao()],
            "ouvidoria_movimentos": [],
            "ouvidoria_notificacoes": [],
            "ouvidoria_setor_responsaveis": (
                responsaveis if responsaveis is not None else [_responsavel("titular"), _responsavel("substituto")]
            ),
            "participantes": [{"id": "P03", "nome_completo": "Pedro Admin", "email": "admin@hsm.br"}],
        }

    def table(self, nome: str):
        classe = _TabelaQueFalhaNoInsert if nome in self.falhar_inserts else _TabelaFake
        return classe(nome, self.tabelas.setdefault(nome, []))


def _client(monkeypatch, supabase: _SupabaseFake, agora: dt.datetime = DENTRO_DO_EXPEDIENTE):
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


class TestCobrancaPrazoRompido:
    """Caso com prazo vencido gera PRAZO_ROMPIDO para titular e substituto."""

    def test_caso_vencido_cobra_titular_e_substituto_com_faixa_de_contexto(self, _nunca_envia_email_de_verdade):
        supabase = _SupabaseFake()

        cobrados = ouvidoria_cobranca.cobrar_prazos_rompidos(supabase, DENTRO_DO_EXPEDIENTE, SEM_FERIADOS)

        assert cobrados == 1
        destinatarios = {e["destinatario"] for e in _nunca_envia_email_de_verdade}
        assert destinatarios == {"titular@hsm.br", "substituto@hsm.br"}
        for email in _nunca_envia_email_de_verdade:
            assert "2026-0007" in email["html"]
            assert "Recepcao" in email["html"]
            assert "vencido há" in email["html"]

    def test_rodar_o_job_duas_vezes_nao_duplica_email(self, _nunca_envia_email_de_verdade):
        supabase = _SupabaseFake()

        primeira = ouvidoria_cobranca.cobrar_prazos_rompidos(supabase, DENTRO_DO_EXPEDIENTE, SEM_FERIADOS)
        segunda = ouvidoria_cobranca.cobrar_prazos_rompidos(
            supabase, DENTRO_DO_EXPEDIENTE + dt.timedelta(minutes=10), SEM_FERIADOS
        )

        assert primeira == 1
        assert segunda == 0
        assert len(_nunca_envia_email_de_verdade) == 2  # titular + substituto, uma vez só
        assert len(supabase.tabelas["ouvidoria_notificacoes"]) == 2

    def test_caso_que_respondeu_ou_ainda_no_prazo_nao_recebe_cobranca(self, _nunca_envia_email_de_verdade):
        supabase = _SupabaseFake(
            manifestacoes=[
                _manifestacao(1, status="respondido", prazo_area_em=PRAZO_VENCIDO),
                _manifestacao(2, status="aguardando_area", prazo_area_em=PRAZO_NO_FUTURO),
            ]
        )

        cobrados = ouvidoria_cobranca.cobrar_prazos_rompidos(supabase, DENTRO_DO_EXPEDIENTE, SEM_FERIADOS)

        assert cobrados == 0
        assert _nunca_envia_email_de_verdade == []
        assert supabase.tabelas["ouvidoria_notificacoes"] == []

    def test_movimento_prazo_rompido_entra_na_trilha_uma_unica_vez(self):
        supabase = _SupabaseFake()

        ouvidoria_cobranca.cobrar_prazos_rompidos(supabase, DENTRO_DO_EXPEDIENTE, SEM_FERIADOS)
        ouvidoria_cobranca.cobrar_prazos_rompidos(
            supabase, DENTRO_DO_EXPEDIENTE + dt.timedelta(minutes=10), SEM_FERIADOS
        )

        movimentos = supabase.tabelas["ouvidoria_movimentos"]
        assert len(movimentos) == 1
        movimento = movimentos[0]
        # Prazo rompido não muda o estado do caso: a trilha registra o fato com
        # o caso parado em aguardando_area.
        assert movimento["estado_anterior"] == "aguardando_area"
        assert movimento["estado_novo"] == "aguardando_area"
        assert movimento["autor_id"] is None
        assert "prazo" in (movimento["observacao"] or "").lower()

    def test_estouro_acumulado_sai_em_lotes(self, _nunca_envia_email_de_verdade):
        """O primeiro tick depois do deploy acha todo o histórico vencido; o
        lote evita a rajada no provedor de email."""
        supabase = _SupabaseFake(manifestacoes=[_manifestacao(n) for n in range(1, 31)])

        cobrados = ouvidoria_cobranca.cobrar_prazos_rompidos(supabase, DENTRO_DO_EXPEDIENTE, SEM_FERIADOS)

        assert cobrados == ouvidoria_cobranca.LOTE_POR_RODADA
        assert len(_nunca_envia_email_de_verdade) == 2 * ouvidoria_cobranca.LOTE_POR_RODADA

        # A rodada seguinte pega o resto, sem repetir quem já foi cobrado.
        cobrados = ouvidoria_cobranca.cobrar_prazos_rompidos(
            supabase, DENTRO_DO_EXPEDIENTE + dt.timedelta(minutes=10), SEM_FERIADOS
        )
        assert cobrados == 5
        assert len(supabase.tabelas["ouvidoria_movimentos"]) == 30

    def test_casos_sem_responsavel_nao_prendem_a_fila_dos_cobraveis(self, _nunca_envia_email_de_verdade):
        """Caso de setor sem responsável não é carimbado, então volta na
        consulta a cada rodada, e por ser o mais antigo vem sempre primeiro.
        Ele não pode consumir a cota de cobrança e deixar o caso cobrável
        preso atrás para sempre."""
        antigo = dt.datetime(2026, 8, 10, 12, 0, tzinfo=dt.UTC)
        represados = [
            _manifestacao(
                n,
                setor="Setor sem responsavel",
                prazo_area_em=(antigo + dt.timedelta(hours=n)).isoformat(),
            )
            for n in range(1, ouvidoria_cobranca.LOTE_POR_RODADA + 1)
        ]
        cobravel = _manifestacao(99, prazo_area_em=PRAZO_VENCIDO)
        supabase = _SupabaseFake(manifestacoes=[*represados, cobravel])

        cobrados = ouvidoria_cobranca.cobrar_prazos_rompidos(supabase, DENTRO_DO_EXPEDIENTE, SEM_FERIADOS)

        assert cobrados == 1
        assert {e["destinatario"] for e in _nunca_envia_email_de_verdade} == {"titular@hsm.br", "substituto@hsm.br"}

    def test_prazo_malformado_num_caso_nao_derruba_a_varredura_dos_demais(self, _nunca_envia_email_de_verdade):
        supabase = _SupabaseFake(
            manifestacoes=[
                _manifestacao(1, prazo_area_em="isso-nao-e-data"),
                _manifestacao(2, prazo_area_em=PRAZO_VENCIDO),
            ]
        )

        cobrados = ouvidoria_cobranca.cobrar_prazos_rompidos(supabase, DENTRO_DO_EXPEDIENTE, SEM_FERIADOS)

        assert cobrados == 1
        assert {e["destinatario"] for e in _nunca_envia_email_de_verdade} == {"titular@hsm.br", "substituto@hsm.br"}

    def test_titular_e_substituto_com_o_mesmo_email_recebem_uma_cobranca_so(self, _nunca_envia_email_de_verdade):
        supabase = _SupabaseFake(
            responsaveis=[
                _responsavel("titular", email="mesma@hsm.br"),
                _responsavel("substituto", email="mesma@hsm.br"),
            ]
        )

        ouvidoria_cobranca.cobrar_prazos_rompidos(supabase, DENTRO_DO_EXPEDIENTE, SEM_FERIADOS)

        assert [e["destinatario"] for e in _nunca_envia_email_de_verdade] == ["mesma@hsm.br"]

    def test_setor_sem_ninguem_vigente_nao_queima_o_caso(self, _nunca_envia_email_de_verdade):
        """Sem titular nem substituto vigentes o caso NÃO é carimbado: quando a
        Diretoria cadastrar alguém, a rodada seguinte cobra (o degrau do gestor
        é do PRD #318)."""
        supabase = _SupabaseFake(responsaveis=[_responsavel("titular", vigencia_fim="2026-01-31")])

        cobrados = ouvidoria_cobranca.cobrar_prazos_rompidos(supabase, DENTRO_DO_EXPEDIENTE, SEM_FERIADOS)

        assert cobrados == 0
        assert _nunca_envia_email_de_verdade == []
        assert supabase.tabelas["ouvidoria_movimentos"] == []
        assert supabase.tabelas["ouvidoria_protocolos"][0]["prazo_rompido_em"] is None

        # A Diretoria cadastra um titular novo: a próxima rodada cobra.
        supabase.tabelas["ouvidoria_setor_responsaveis"].append(_responsavel("titular", email="nova@hsm.br"))
        cobrados = ouvidoria_cobranca.cobrar_prazos_rompidos(
            supabase, DENTRO_DO_EXPEDIENTE + dt.timedelta(minutes=10), SEM_FERIADOS
        )
        assert cobrados == 1
        assert [e["destinatario"] for e in _nunca_envia_email_de_verdade] == ["nova@hsm.br"]

    def test_notificacao_que_nao_grava_devolve_o_caso_para_a_proxima_rodada(self, _nunca_envia_email_de_verdade):
        """Cenário do deploy antes da migration: o CHECK antigo recusa o
        gatilho novo. O caso não pode ficar carimbado sem cobrança nenhuma."""
        supabase = _SupabaseFake()
        supabase.falhar_inserts = {"ouvidoria_notificacoes"}

        cobrados = ouvidoria_cobranca.cobrar_prazos_rompidos(supabase, DENTRO_DO_EXPEDIENTE, SEM_FERIADOS)

        assert cobrados == 0
        assert _nunca_envia_email_de_verdade == []
        assert supabase.tabelas["ouvidoria_movimentos"] == []
        assert supabase.tabelas["ouvidoria_protocolos"][0]["prazo_rompido_em"] is None

        # Migration aplicada: a rodada seguinte cobra normalmente.
        supabase.falhar_inserts = set()
        cobrados = ouvidoria_cobranca.cobrar_prazos_rompidos(
            supabase, DENTRO_DO_EXPEDIENTE + dt.timedelta(minutes=10), SEM_FERIADOS
        )
        assert cobrados == 1
        assert len(_nunca_envia_email_de_verdade) == 2

    def test_caso_que_respondeu_depois_de_enfileirado_nao_recebe_o_email(self, _nunca_envia_email_de_verdade):
        """Cobrança retida pela janela comercial: se a área responde durante a
        madrugada, o job da fila não manda o email acusatório de manhã."""
        supabase = _SupabaseFake(manifestacoes=[_manifestacao(gravidade="medio")])
        ouvidoria_cobranca.cobrar_prazos_rompidos(supabase, FORA_DO_EXPEDIENTE, SEM_FERIADOS)
        assert _nunca_envia_email_de_verdade == []  # retida pela janela

        # A área responde antes da abertura do expediente.
        supabase.tabelas["ouvidoria_protocolos"][0]["status"] = "respondido"

        abertura = dt.datetime(2026, 8, 26, 11, 0, tzinfo=dt.UTC)
        entregues = ouvidoria_notificacoes.despachar_pendentes(supabase, abertura, SEM_FERIADOS)

        assert entregues == 0
        assert _nunca_envia_email_de_verdade == []
        assert all(r["status"] == "falha" for r in supabase.tabelas["ouvidoria_notificacoes"])
        assert all("respondeu antes" in r["ultimo_erro"] for r in supabase.tabelas["ouvidoria_notificacoes"])

    def test_notificacao_fica_registrada_no_padrao_e_e_reenviavel(self, monkeypatch, _nunca_envia_email_de_verdade):
        supabase = _SupabaseFake()
        ouvidoria_cobranca.cobrar_prazos_rompidos(supabase, DENTRO_DO_EXPEDIENTE, SEM_FERIADOS)

        registros = supabase.tabelas["ouvidoria_notificacoes"]
        assert {r["gatilho"] for r in registros} == {"prazo_rompido"}
        assert {r["papel_destinatario"] for r in registros} == {"titular", "substituto"}
        assert all(r["status"] == "enviada" and r["manifestacao_id"] == "uuid-7" for r in registros)

        # O botão de reenvio é o mesmo das demais notificações: o endpoint
        # genérico remonta o email pelo gatilho e registra o reenvio à parte.
        client = _client(monkeypatch, supabase)
        resposta = client.post(f"/api/ouvidoria/manifestacoes/uuid-7/notificacoes/{registros[0]['id']}/reenviar")

        assert resposta.status_code == 201
        assert resposta.json()["gatilho"] == "prazo_rompido"
        assert resposta.json()["entregue"] is True
        assert len(supabase.tabelas["ouvidoria_notificacoes"]) == 3
        assert len(_nunca_envia_email_de_verdade) == 3
        assert "vencido há" in _nunca_envia_email_de_verdade[-1]["html"]


class TestJanelaComercial:
    """Cobrança não crítica fora do expediente espera a próxima abertura."""

    def test_caso_nao_critico_fora_do_expediente_espera_a_abertura(self, _nunca_envia_email_de_verdade):
        supabase = _SupabaseFake(manifestacoes=[_manifestacao(gravidade="medio")])

        cobrados = ouvidoria_cobranca.cobrar_prazos_rompidos(supabase, FORA_DO_EXPEDIENTE, SEM_FERIADOS)

        assert cobrados == 1
        assert _nunca_envia_email_de_verdade == []  # nada sai de madrugada
        registros = supabase.tabelas["ouvidoria_notificacoes"]
        assert all(r["status"] == "agendada" for r in registros)
        # Quarta-feira, 08h de Brasília: a próxima abertura do expediente.
        abertura = dt.datetime(2026, 8, 26, 11, 0, tzinfo=dt.UTC)
        assert all(dt.datetime.fromisoformat(r["enviar_a_partir_de"]) == abertura for r in registros)

    def test_caso_critico_e_cobrado_na_hora_mesmo_fora_do_expediente(self, _nunca_envia_email_de_verdade):
        supabase = _SupabaseFake(manifestacoes=[_manifestacao(gravidade="critico")])

        ouvidoria_cobranca.cobrar_prazos_rompidos(supabase, FORA_DO_EXPEDIENTE, SEM_FERIADOS)

        assert {e["destinatario"] for e in _nunca_envia_email_de_verdade} == {"titular@hsm.br", "substituto@hsm.br"}


class TestMigration:
    """A 069 abre o CHECK de gatilho para a cobrança e dá ao caso o carimbo de
    idempotência, reaplicável sem quebrar (padrão da casa)."""

    def _ddl(self) -> str:
        caminho = os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "supabase",
            "migrations",
            "069_ouvidoria_prazo_rompido.sql",
        )
        with open(caminho, encoding="utf-8") as f:
            return f.read().lower()

    def test_gatilho_prazo_rompido_entra_no_check(self):
        """CHECK não tem IF NOT EXISTS: derruba e recria, como a 068 fez com o
        CHECK de status."""
        ddl = self._ddl()
        assert "'prazo_rompido'" in ddl
        assert "drop constraint if exists ouvidoria_notificacoes_gatilho_check" in ddl

    def test_caso_ganha_o_carimbo_de_idempotencia(self):
        ddl = self._ddl()
        assert "add column if not exists prazo_rompido_em" in ddl

    def test_migration_e_idempotente(self):
        ddl = self._ddl()
        assert "add column if not exists" in ddl
        assert "create index if not exists" in ddl


class TestJobNoScheduler:
    """O job de estouro roda sozinho, de tempos em tempos, junto dos demais."""

    def test_job_de_cobranca_esta_registrado(self):
        from app.cron import scheduler as cron

        try:
            cron.start_scheduler()
            job = cron.scheduler.get_job("cobranca_prazos_ouvidoria")
            assert job is not None
        finally:
            cron.stop_scheduler()
