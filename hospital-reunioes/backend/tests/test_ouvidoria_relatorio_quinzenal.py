"""Relatório quinzenal da Ouvidoria em PDF, agendado por email (issue #345, PRD #319).

O relatório nasce de um job diário, sai por email à Diretoria Executiva com o
PDF anexo nos dias 1 e 16 (quando a quinzena fecha), fica registrado e o
ouvidor consegue reenviar.

Os números vêm de `ouvidoria_metricas.metricas_do_periodo`, a MESMA função que
a rota do painel chama: aqui não se testa de novo o que a #341 já garante, e
sim o que esta fatia acrescenta. Que é, em ordem de risco:

  - o PDF diz quando NÃO mediu, em vez de imprimir zero;
  - o ranking sai com o denominador ("3 já classificados de 43"), porque três
    de três ao lado de quarenta e três lê como três de quarenta e três;
  - a fila de pendências vai carimbada com o instante da medição e CONGELADA,
    porque ela não tem recorte de período: sem congelar, o relatório de julho
    reenviado em setembro mostraria a fila de setembro;
  - nenhum protocolo sai no PDF nem no email (RN-40, ADR 0034 decisão 8);
  - rodar duas vezes não manda dois emails, e rodar todo dia também não;
  - o que foi gerado e não saiu volta para a fila, em vez de sumir;
  - quem foi desligado do hospital não recebe;
  - quem recebeu não é apagado do registro por um reenvio;
  - só ouvidor e Diretoria Executiva acessam o registro e o reenvio.

O envio é sempre mockado: nenhum teste toca provedor de email real.
"""

from __future__ import annotations

import datetime as dt
import logging
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
from app.services import email_service, ouvidoria_relatorio  # noqa: E402
from app.services.ouvidoria_metricas import Periodo  # noqa: E402

OUVIDOR = {"id": "P10", "nome_completo": "Marta Ouvidora", "access_profile": None, "perfil_ouvidoria": "ouvidor"}
DIRETORA = {
    "id": "P11",
    "nome_completo": "Helena Diretora",
    "access_profile": None,
    "perfil_ouvidoria": "diretoria_executiva",
    "email": "helena@hsm.br",
    "ativo": True,
}
# O desligamento do hospital é soft delete e NÃO limpa `perfil_ouvidoria`
# (participantes.py, DELETE só faz `ativo: False`).
DIRETORA_DESLIGADA = {
    "id": "P12",
    "nome_completo": "Bianca Ex-Diretora",
    "access_profile": None,
    "perfil_ouvidoria": "diretoria_executiva",
    "email": "bianca@antigo.com",
    "ativo": False,
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

# A quinzena medida: 01 a 15 de agosto de 2026. O job que a fecha roda no dia 16.
PERIODO = Periodo(inicio=dt.date(2026, 8, 1), fim=dt.date(2026, 8, 15))
COMPETENCIA = "quinzenal-2026-08-01-2026-08-15"
# 16/08/2026 às 07h de Brasília, que é a hora do job.
AGORA = dt.datetime(2026, 8, 16, 10, 0, tzinfo=dt.UTC)
# Um mês depois, para o reenvio de um relatório velho.
DEPOIS = dt.datetime(2026, 9, 20, 12, 0, tzinfo=dt.UTC)

PROTOCOLO_SIGILOSO = "2026-0042"


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


@pytest.fixture(autouse=True)
def _sem_memoria_de_aviso(monkeypatch):
    """O aviso de cadastro sem Diretoria sai no máximo uma vez por dia, e a
    memória disso é de módulo. Sem zerar, o primeiro teste que avisa cala todos
    os outros do mesmo dia, e o vermelho apareceria em quem não tem culpa."""
    monkeypatch.setattr(ouvidoria_relatorio, "_ultimo_aviso_de_cadastro", None)


@pytest.fixture(autouse=True)
def _sem_provedor_de_email(monkeypatch):
    """Nenhum teste sai para a rede. Quem quiser exercitar o Resend liga o dele
    explicitamente."""
    monkeypatch.setattr(email_service.settings, "resend_api_key", "")
    monkeypatch.setattr(email_service.settings, "smtp_user", "")


def _caso(numero: int, **overrides) -> dict:
    """Uma manifestação no molde da tabela real (migrations 063 a 079)."""
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


def _pendente(numero: int, setor: str = "Recepcao", **overrides) -> dict:
    """Caso na fila viva: aguardando a área, com prazo já vencido."""
    return _caso(
        numero,
        status="aguardando_area",
        setor=setor,
        prazo_area_em="2026-08-10T20:00:00+00:00",
        validada_em="2026-08-04T12:00:00+00:00",
        **overrides,
    )


PRAZOS = [
    {"gravidade": "critico", "marco": "triagem", "valor": 0, "unidade": "horas_uteis"},
    {"gravidade": "critico", "marco": "area_resposta", "valor": 4, "unidade": "horas_uteis"},
    {"gravidade": "critico", "marco": "conclusiva", "valor": None, "unidade": "dias_uteis"},
    {"gravidade": "medio", "marco": "triagem", "valor": 1, "unidade": "dias_uteis"},
    {"gravidade": "medio", "marco": "area_resposta", "valor": 4, "unidade": "dias_uteis"},
    {"gravidade": "medio", "marco": "conclusiva", "valor": 7, "unidade": "dias_uteis"},
]

RESPONSAVEIS = [
    {
        "id": "resp-1",
        "setor": "Recepcao",
        "papel": "titular",
        "nome": "Carlos Titular",
        "email": "carlos@hsm.br",
        "vigencia_inicio": "2026-01-01",
        "vigencia_fim": None,
    }
]


def _ordenavel(valor):
    """A chave de ordenação do fake, que precisa distinguir número de texto:
    `tentativas` é inteiro, e ordenar "10" contra "9" como texto poria a linha
    mais tentada na frente da fila."""
    if isinstance(valor, bool) or valor is None:
        return str(valor or "")
    if isinstance(valor, (int, float)):
        return valor
    return str(valor)


class _TabelaFake:
    """Fake do PostgREST fiel no que importa: projeta o que foi pedido, filtra
    o que foi filtrado e devolve as linhas gravadas."""

    def __init__(self, nome: str, rows: list[dict], recusa_filtro_de_id: bool = False):
        self.nome = nome
        self.rows = rows
        # O PostgREST recusando um `id` que não é UUID (22P02), que é o que o
        # banco real faz e o fake, sem isto, nunca faria.
        self.recusa_filtro_de_id = recusa_filtro_de_id
        self._filters: dict = {}
        self._neq: dict = {}
        self._in: dict = {}
        self._gte: dict = {}
        self._lte: dict = {}
        self._insert: dict | list | None = None
        self._update: dict | None = None
        self._colunas: tuple[str, ...] | None = None
        self._limite: int | None = None
        # As ordens ACUMULAM, como no postgrest-py: `.order(a).order(b)` vira
        # `order=a.asc,b.asc`. Com uma só, a segunda chave da fila de
        # recuperação sumiria e o fake ordenaria diferente do banco.
        self._ordens: list[tuple[str, bool]] = []
        self._is_null: list[str] = []

    def select(self, colunas: str = "*", *_a, **_kw):
        if colunas.strip() != "*":
            self._colunas = tuple(c.strip() for c in colunas.split(","))
        return self

    def eq(self, col, value):
        self._filters[col] = value
        return self

    def neq(self, col, value):
        self._neq[col] = value
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

    def is_(self, col, valor):
        assert valor == "null", f"o fake só entende is_ null, veio {valor}"
        self._is_null.append(col)
        return self

    def gte(self, col, value):
        self._gte[col] = value
        return self

    def lte(self, col, value):
        self._lte[col] = value
        return self

    def limit(self, quantos: int):
        self._limite = quantos
        return self

    def order(self, col, desc=False):
        self._ordens.append((col, desc))
        return self

    def _projetar(self, row: dict) -> dict:
        if self._colunas is None:
            return dict(row)
        return {c: row.get(c) for c in self._colunas}

    def execute(self):
        if self.recusa_filtro_de_id and "id" in self._filters:
            raise APIError({"message": 'invalid input syntax for type uuid: "nao-e-uuid"', "code": "22P02"})
        if self._insert is not None:
            novos = self._insert if isinstance(self._insert, list) else [self._insert]
            gravados = []
            for novo in novos:
                linha = dict(novo)
                linha.setdefault("id", f"{self.nome}-{len(self.rows) + 1}")
                linha.setdefault("gerado_em", linha.get("medido_em"))
                linha.setdefault("enviado_em", None)
                linha.setdefault("destinatarios", [])
                linha.setdefault("ultimo_erro", None)
                linha.setdefault("tentativas", 0)
                linha.setdefault("desistido_em", None)
                self.rows.append(linha)
                gravados.append(dict(linha))
            return type("R", (), {"data": gravados})()
        casadas = [
            r
            for r in self.rows
            if all(r.get(c) == v for c, v in self._filters.items())
            and all(r.get(c) != v for c, v in self._neq.items())
            and all(r.get(c) in v for c, v in self._in.items())
            and all(str(r.get(c) or "") >= v for c, v in self._gte.items())
            and all(str(r.get(c) or "") <= v for c, v in self._lte.items())
            and all(r.get(c) is None for c in self._is_null)
        ]
        if self._update is not None:
            atualizadas = []
            for r in casadas:
                r.update(self._update)
                atualizadas.append(dict(r))
            return type("R", (), {"data": atualizadas})()
        # Do menos significativo para o mais significativo: `sorted` é
        # estável, e é assim que várias chaves de ordenação se compõem.
        for col, desc in reversed(self._ordens):
            casadas = sorted(casadas, key=lambda r, c=col: _ordenavel(r.get(c)), reverse=desc)
        if self._limite is not None:
            casadas = casadas[: self._limite]
        return type("R", (), {"data": [self._projetar(r) for r in casadas]})()


class _SupabaseFake:
    def __init__(self, casos: list[dict] | None = None, **tabelas):
        self.indisponiveis: set[str] = set()
        self.recusa_filtro_de_id = False
        self.tabelas: dict[str, list[dict]] = {
            "ouvidoria_protocolos": casos if casos is not None else [],
            "ouvidoria_prorrogacoes": [],
            "ouvidoria_setor_responsaveis": [dict(r) for r in RESPONSAVEIS],
            "ouvidoria_prazos": [dict(p) for p in PRAZOS],
            "ouvidoria_feriados": [{"data": "2026-09-07", "nome": "Independencia", "abrangencia": "nacional"}],
            "ouvidoria_relatorios": [],
            # As duas na tabela, como o banco fica depois de um desligamento.
            "participantes": [dict(DIRETORA), dict(DIRETORA_DESLIGADA)],
        }
        self.tabelas.update(tabelas)

    def table(self, nome: str):
        if nome in self.indisponiveis:
            raise APIError({"message": f"{nome} indisponivel", "code": "PGRST000"})
        return _TabelaFake(nome, self.tabelas.setdefault(nome, []), self.recusa_filtro_de_id)


class _Correio:
    """O provedor de email, no lugar do de verdade. Guarda o que sairia.

    `recusa` derruba destinatários específicos, que é como o Resend falha de
    verdade: caixa cheia, domínio fora do ar, endereço em quarentena."""

    def __init__(self, entrega: bool = True, recusa: set[str] | None = None):
        self.entrega = entrega
        self.recusa = recusa or set()
        self.enviados: list[dict] = []

    def __call__(self, destinatario, assunto, html_content, texto_fallback, anexos):  # noqa: PLR0913
        if destinatario in self.recusa:
            return False
        self.enviados.append(
            {
                "destinatario": destinatario,
                "assunto": assunto,
                "html": html_content,
                "texto": texto_fallback,
                "anexos": anexos,
            }
        )
        return self.entrega


@pytest.fixture
def correio(monkeypatch) -> _Correio:
    postado = _Correio()
    monkeypatch.setattr(ouvidoria_relatorio, "enviar_com_anexo", postado)
    return postado


@pytest.fixture
def impressos(monkeypatch) -> list[dict]:
    """Os registros que viraram PDF, na ordem em que foram impressos.

    As asserções sobre o conteúdo entram por aqui, e não relendo a linha do
    banco: reler e renderizar de novo testa um caminho que ninguém percorre em
    produção, e deixaria passar um envio que mandou outro registro no anexo."""
    renderizar = ouvidoria_relatorio.renderizar_pdf
    capturados: list[dict] = []

    def _espiao(registro):
        capturados.append(registro)
        return renderizar(registro)

    monkeypatch.setattr(ouvidoria_relatorio, "renderizar_pdf", _espiao)
    return capturados


def _client(monkeypatch, supabase: _SupabaseFake, participante: dict = OUVIDOR) -> TestClient:
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(RequestContextMiddleware)
    app.include_router(ouvidoria_router.router, prefix="/api")

    async def _fake_participante(_user, _sb, fields=None):
        return participante

    monkeypatch.setattr(ouvidoria_router, "get_participante_for_user", _fake_participante)
    monkeypatch.setattr(ouvidoria_router, "agora_utc", lambda: DEPOIS)
    app.dependency_overrides[get_current_user] = lambda: {"id": "u1", "email": "u@hsm.br"}
    app.dependency_overrides[get_supabase_client] = lambda: supabase
    return TestClient(app)


def _cenario() -> _SupabaseFake:
    """Quarenta e três manifestações, três classificadas, como a Ouvidoria
    realmente chega numa quinzena: o canal público entra sem tipo e sem área."""
    classificados = [_caso(n) for n in (1, 2, 3)]
    triagem = [
        _caso(n, status="em_classificacao", tipo_manifestacao=None, setor="A definir", canal="site")
        for n in range(4, 44)
    ]
    return _SupabaseFake(casos=classificados + triagem)


# ═══════════════════════════════════════════════════════════════════════════
# Qual quinzena o dia fecha
# ═══════════════════════════════════════════════════════════════════════════


class TestQuinzena:
    def test_dia_16_fecha_a_primeira_quinzena_do_mes(self):
        """CA: o relatório do dia 16 é o dos dias 1 a 15 do próprio mês."""
        assert ouvidoria_relatorio.quinzena_encerrada(dt.date(2026, 8, 16)) == Periodo(
            inicio=dt.date(2026, 8, 1), fim=dt.date(2026, 8, 15)
        )

    def test_dia_1_fecha_a_segunda_quinzena_do_mes_anterior(self):
        """CA: o do dia 1 é o do dia 16 ao último dia do mês que acabou, e o
        último dia é o do calendário, não um 30 fixo."""
        assert ouvidoria_relatorio.quinzena_encerrada(dt.date(2026, 8, 1)) == Periodo(
            inicio=dt.date(2026, 7, 16), fim=dt.date(2026, 7, 31)
        )
        assert ouvidoria_relatorio.quinzena_encerrada(dt.date(2027, 3, 1)) == Periodo(
            inicio=dt.date(2027, 2, 16), fim=dt.date(2027, 2, 28)
        )

    def test_dia_29_de_fevereiro_e_a_virada_do_ano(self):
        """Os dois limites que a aritmética de data costuma errar."""
        assert ouvidoria_relatorio.quinzena_encerrada(dt.date(2028, 3, 1)) == Periodo(
            inicio=dt.date(2028, 2, 16), fim=dt.date(2028, 2, 29)
        )
        assert ouvidoria_relatorio.quinzena_encerrada(dt.date(2027, 1, 1)) == Periodo(
            inicio=dt.date(2026, 12, 16), fim=dt.date(2026, 12, 31)
        )

    def test_o_agendamento_e_a_unica_guarda_de_quando_o_relatorio_sai(self, monkeypatch):
        """A hora está no cron, e em nenhum outro lugar: uma guarda só, para
        desligá-la deixar teste vermelho.

        O job roda TODO DIA às 07h, e não só nos dias 1 e 16, porque o jobstore
        do APScheduler é em memória: um restart do container em torno das 07h do
        dia 16 não adia o disparo, descarta. Quem impede o segundo email é a
        competência, não o calendário do cron."""
        from app.cron import scheduler as cron

        registrados: dict[str, dict] = {}

        class _SchedulerEspiao:
            running = False

            def add_job(self, func, gatilho, **kwargs):
                registrados[kwargs["id"]] = {"gatilho": gatilho, **kwargs}

            def start(self):
                pass

        monkeypatch.setattr(cron, "scheduler", _SchedulerEspiao())
        cron.start_scheduler()

        job = registrados["relatorio_quinzenal_ouvidoria"]
        assert job["gatilho"] == "cron"
        assert job["hour"] == 7
        assert job["minute"] == 0
        assert "day" not in job, "o job é diário: restringir ao dia perde a edição quando o container reinicia"

    def test_falha_do_relatorio_nao_derruba_os_outros_jobs(self, monkeypatch, caplog):
        """O job novo entra na mesma disciplina dos vizinhos: exceção vira log,
        não sobe para o scheduler e leva a rodada inteira junto."""
        from app.cron import scheduler as cron

        def _banco_fora(*_a, **_kw):
            raise RuntimeError("banco fora do ar")

        monkeypatch.setattr(cron, "_supabase", _banco_fora)

        cron.enviar_relatorio_quinzenal()

        assert "enviar_relatorio_quinzenal" in caplog.text

    def test_o_job_avisa_quando_a_entrega_sai_incompleta(self, monkeypatch, caplog):
        """O log do job é o ÚNICO observador automático da entrega, porque esta
        fatia não põe o registro em tela nenhuma. Tratando parcial como sucesso,
        ele diz "enviado para 1 destinatário(s)" enquanto dois diretores não
        receberam, e o motivo, que traz os nomes, não é escrito em lugar
        nenhum."""
        from app.cron import scheduler as cron

        supabase = _cenario()
        supabase.tabelas["participantes"] = [
            dict(DIRETORA),
            {
                "id": "P14",
                "nome_completo": "Rita",
                "perfil_ouvidoria": "diretoria_executiva",
                "email": "rita@hsm.br",
                "ativo": True,
            },
        ]
        monkeypatch.setattr(cron, "_supabase", lambda: supabase)
        monkeypatch.setattr(ouvidoria_relatorio, "enviar_com_anexo", _Correio(recusa={"rita@hsm.br"}))

        with caplog.at_level(logging.WARNING):
            cron.enviar_relatorio_quinzenal()

        avisos = [r for r in caplog.records if r.levelno == logging.WARNING and "rita@hsm.br" in r.getMessage()]
        assert avisos, "a entrega parcial passou sem aviso nenhum no log do job"
        assert "INCOMPLETO" in avisos[0].getMessage()

    def test_container_fora_do_ar_no_dia_16_nao_perde_a_quinzena(self, correio):
        """A edição é insubstituível: um deploy às 07h do dia 16 descarta o
        disparo (jobstore em memória), e o dia 1 já calcularia OUTRA
        competência. Rodando todo dia, o dia 17 entrega o que o 16 não
        entregou, e os dias seguintes não repetem."""
        supabase = _cenario()
        dia_17 = dt.datetime(2026, 8, 17, 10, 0, tzinfo=dt.UTC)

        primeira = ouvidoria_relatorio.gerar_e_enviar(
            supabase, ouvidoria_relatorio.quinzena_encerrada(dia_17.date()), dia_17
        )
        for dia in (18, 19, 20):
            momento = dt.datetime(2026, 8, dia, 10, 0, tzinfo=dt.UTC)
            ouvidoria_relatorio.gerar_e_enviar(
                supabase, ouvidoria_relatorio.quinzena_encerrada(momento.date()), momento
            )

        assert primeira.registro["competencia"] == COMPETENCIA
        assert len(correio.enviados) == 1
        assert len(supabase.tabelas["ouvidoria_relatorios"]) == 1

    def test_edicao_que_nao_saiu_volta_para_a_fila_na_rodada_seguinte(self, monkeypatch, correio):
        """Sem a varredura, um relatório gerado que não saiu ficaria parado
        para sempre: a rodada seguinte já calcula outra competência e nunca
        revisita a anterior."""
        supabase = _cenario()
        monkeypatch.setattr(ouvidoria_relatorio, "enviar_com_anexo", _Correio(entrega=False))
        ouvidoria_relatorio.gerar_e_enviar(supabase, PERIODO, AGORA)
        assert supabase.tabelas["ouvidoria_relatorios"][0]["enviado_em"] is None

        # Duas semanas depois, com o provedor de volta: a rodada trata a
        # quinzena nova e varre a que ficou para trás.
        monkeypatch.setattr(ouvidoria_relatorio, "enviar_com_anexo", correio)
        setembro = dt.datetime(2026, 9, 1, 10, 0, tzinfo=dt.UTC)
        quinzena_nova = ouvidoria_relatorio.quinzena_encerrada(setembro.date())
        atrasados = ouvidoria_relatorio.entregar_atrasados(
            supabase, setembro, exceto=ouvidoria_relatorio.competencia_de("quinzenal", quinzena_nova)
        )

        assert [e.registro["competencia"] for e in atrasados] == [COMPETENCIA]
        assert supabase.tabelas["ouvidoria_relatorios"][0]["enviado_em"] == setembro.isoformat()
        assert len(correio.enviados) == 1

    def test_duas_varreduras_ao_mesmo_tempo_reentregam_uma_vez_so(self, monkeypatch, correio):
        """O caminho que mais depende da reivindicação, porque nem passa pelo
        INSERT: as duas varreduras leem a mesma linha não enviada, e sem o
        carimbo antes do envio as duas mandam o mesmo PDF.

        A segunda varredura entra NO MEIO do envio da primeira, que é a única
        forma de as duas verem a linha no mesmo estado."""
        supabase = _cenario()
        ouvidoria_relatorio._registrar(supabase, "quinzenal", PERIODO, AGORA)
        cruzou = {"ja": False}

        def _correio_que_cruza(**kwargs):
            if not cruzou["ja"]:
                cruzou["ja"] = True
                ouvidoria_relatorio.entregar_atrasados(supabase, AGORA)
            return correio(**kwargs)

        monkeypatch.setattr(ouvidoria_relatorio, "enviar_com_anexo", _correio_que_cruza)

        ouvidoria_relatorio.entregar_atrasados(supabase, AGORA)

        assert cruzou["ja"], "a segunda varredura não chegou a rodar"
        assert len(correio.enviados) == 1

    def test_varredura_nao_toca_a_edicao_que_a_propria_rodada_vai_gerar(self, monkeypatch, correio):
        """Sem o `exceto`, a mesma competência seria tentada duas vezes no
        mesmo minuto: uma pela varredura e outra pela geração."""
        supabase = _cenario()
        monkeypatch.setattr(ouvidoria_relatorio, "enviar_com_anexo", _Correio(entrega=False))
        ouvidoria_relatorio.gerar_e_enviar(supabase, PERIODO, AGORA)

        monkeypatch.setattr(ouvidoria_relatorio, "enviar_com_anexo", correio)
        atrasados = ouvidoria_relatorio.entregar_atrasados(supabase, AGORA + dt.timedelta(days=1), exceto=COMPETENCIA)

        assert atrasados == []
        assert not correio.enviados


# ═══════════════════════════════════════════════════════════════════════════
# O PDF
# ═══════════════════════════════════════════════════════════════════════════


class TestConteudoDoPdf:
    def test_html_traz_as_secoes_e_os_numeros_das_metricas(self, correio, impressos):
        """CA: o PDF renderiza com as seções e os números do módulo de métricas."""
        supabase = _cenario()
        entrega = ouvidoria_relatorio.gerar_e_enviar(supabase, PERIODO, AGORA)

        html = ouvidoria_relatorio.montar_html(impressos[-1])

        assert "Relatório quinzenal da Ouvidoria" in html
        assert "01/08/2026 a 15/08/2026" in html
        for secao in (
            "Volume",
            "Volume por canal",
            "Temas mais frequentes",
            "Áreas mais frequentes",
            "Prazo cumprido por trecho",
            "Pendências por área",
            "Prorrogação por área",
        ):
            assert secao in html, f"seção ausente: {secao}"
        # 43 manifestações no período, ancoradas no destaque em que saem: "43"
        # solto casa com a tabela de prazos logo abaixo.
        assert '<div class="valor">43</div>' in _secao(html, "Volume")
        assert entrega.saiu

    def test_os_quatro_numeros_em_destaque_sao_os_do_periodo(self):
        """Os quatro números de corpo 17 que a Diretoria lê primeiro, ancorados
        no elemento em que saem.

        `">43<"` no documento inteiro não serve: 43 aparece sete vezes no HTML,
        cinco delas na tabela de prazos, e zerar os destaques deixaria a
        asserção casando com a tabela vizinha."""
        html = ouvidoria_relatorio.montar_html(_registro_cheio())
        destaques = _secao(html, "Volume")

        for valor, rotulo in (
            ("43", "manifestações no período"),
            ("40", "casos novos"),
            ("3", "reincidentes"),
            ("7", "casos com pausa"),
        ):
            assert f'<div class="valor">{valor}</div>' in destaques, f"destaque perdido: {rotulo}"
            assert rotulo in destaques

    def test_ranking_sai_com_o_denominador_de_quem_foi_classificado(self, correio, impressos):
        """O topo sem denominador apresenta ausência de medição como medição:
        "Recepção (3)" ao lado de "43 manifestações" lê como 3 de 43."""
        supabase = _cenario()
        ouvidoria_relatorio.gerar_e_enviar(supabase, PERIODO, AGORA)

        html = ouvidoria_relatorio.montar_html(impressos[-1])

        # Os 3 classificados são todos reclamação da Recepção: um item em cada
        # ranking, e a frase concorda no singular.
        assert "1 tema mais frequente entre os 3 casos já classificados de 43. 40 ainda sem classificação." in html
        assert "1 área mais frequente entre os 3 casos já classificados de 43." in html

    def test_nada_classificado_diz_que_esta_tudo_na_triagem(self):
        """`itens: []` com `classificados: 0` não é "nenhum tema": é "ninguém
        classificou ainda". O PDF precisa dizer qual dos dois."""
        registro = _registro_de_teste(
            top_temas={"itens": [], "classificados": 0, "nao_classificados": 43},
            volume_total=43,
        )

        html = ouvidoria_relatorio.montar_html(registro)

        assert "Nada foi classificado ainda: os 43 casos do período seguem na triagem." in html

    def test_percentual_sem_medicao_nunca_vira_zero(self):
        """Convenção do contrato, item 4: `null` é ausência de medição, e zero
        é uma afirmação. "0,0% de prorrogação" logo abaixo de um topo que
        admitiu não ter medido é a afirmação entrando pela porta dos fundos, e
        lê como "nenhuma área precisou de mais tempo"."""
        registro = _registro_de_teste(
            prorrogacao={
                "casos": None,
                "com_a_area": 4,
                "taxa_pct": None,
                "por_area": [{"setor": "Recepcao", "casos": 4, "prorrogados": None, "taxa_pct": None}],
            },
            degradado=["prorrogacoes"],
        )

        secao = _secao(ouvidoria_relatorio.montar_html(registro), "Prorrogação por área")

        assert "A taxa de prorrogação não pôde ser medida" in secao
        # A linha da área também: ela é a que o gestor lê.
        assert "%" not in secao
        assert secao.count("sem dados") == 2

    def test_prazo_sem_medicao_nao_diz_que_nada_foi_cumprido(self):
        """A tabela que o diretor lê primeiro. Com `prazos` em `degradado`, os
        TRÊS trechos vêm com `percentual_cumprido: null` (contrato da #341,
        item 3), e imprimir "0,0%" neles é dizer à Diretoria que NADA foi
        cumprido na quinzena, o que é o oposto de "não deu para medir"."""
        registro = _registro_de_teste(
            degradado=["prazos"],
            prazo={
                "trechos": [
                    {
                        "trecho": trecho,
                        "de": de,
                        "ate": ate,
                        "responsavel": responsavel,
                        "medidos": 0,
                        "cumpridos": 0,
                        "estourados": 0,
                        "em_andamento": 0,
                        "sem_prazo": 12,
                        "percentual_cumprido": None,
                    }
                    for trecho, de, ate, responsavel in (
                        ("triagem", "T0", "T1", "ouvidoria"),
                        ("area", "T1", "T2", "area"),
                        ("conclusiva", "T0", "T3", "caso"),
                    )
                ]
            },
        )

        secao = _secao(ouvidoria_relatorio.montar_html(registro), "Prazo cumprido por trecho")

        assert "%" not in secao
        assert secao.count("sem dados") == 3
        # E os três trechos continuam na tabela, cada um com o seu responsável.
        for rotulo in ("Triagem", "Ouvidoria", "Conclusiva", "Caso inteiro"):
            assert rotulo in secao

    @pytest.mark.parametrize(
        ("leitura", "trecho_do_aviso"),
        [
            ("prazos", "tabela de prazos não pôde ser lida"),
            ("feriados", "calendário de feriados não pôde ser lido"),
            ("responsaveis", "cadastro de responsáveis não pôde ser lido"),
            ("prorrogacoes", "taxa de prorrogação do período e a de cada área não puderam ser medidas"),
        ],
    )
    def test_cada_leitura_degradada_diz_o_que_ela_estragou(self, leitura, trecho_do_aviso):
        """Um aviso genérico ("alguns dados podem estar incompletos") não conta:
        cada leitura estraga um número diferente, e quem lê precisa saber qual
        deles parar de acreditar."""
        html = ouvidoria_relatorio.montar_html(_registro_de_teste(degradado=[leitura]))

        assert trecho_do_aviso in html

    def test_comparacao_leva_as_datas_ao_lado_do_numero(self):
        """O período anterior é uma janela deslizante do mesmo tamanho, que NÃO
        coincide com a quinzena passada (para 01 a 15/08 ele é 17 a 31/07).
        Quem lê "+50,0%" em corpo 17 entende "contra a quinzena passada" se as
        datas ficarem só na linha cinza do cabeçalho."""
        html = ouvidoria_relatorio.montar_html(_registro_de_teste())

        # Os DOIS destaques que comparam com o período anterior: o total e os
        # casos novos. Um deles sozinho deixaria o outro sem a ressalva.
        assert html.count("+50,0% sobre 17/07/2026 a 31/07/2026") == 2

    def test_leitura_degradada_vira_aviso_no_topo(self):
        """A linha dos feriados é a pior: nada vem nulo, o número sai com cara
        de bom e só o `degradado` denuncia. Quem imprimir sem olhar essa lista
        publica tempo médio errado sem aviso nenhum."""
        registro = _registro_de_teste(degradado=["feriados"])

        html = ouvidoria_relatorio.montar_html(registro)

        assert "Nem tudo pôde ser medido nesta edição" in html
        assert "calendário de feriados não pôde ser lido" in html

    def test_sem_degradacao_nao_ha_aviso(self):
        """O aviso só aparece quando há o que avisar: um alarme que toca sempre
        deixa de ser lido."""
        html = ouvidoria_relatorio.montar_html(_registro_de_teste())

        assert "Nem tudo pôde ser medido" not in html

    def test_fila_de_pendencias_sai_carimbada_com_o_instante_da_medicao(self, correio, impressos):
        """`pendencias_por_area` tem universo próprio e não tem recorte de
        data: é sempre a fila de HOJE. Sem o carimbo, o leitor de um relatório
        de agosto soma essa fila ao volume de agosto, e são universos
        diferentes."""
        supabase = _SupabaseFake(casos=[_caso(1), _pendente(2)])
        ouvidoria_relatorio.gerar_e_enviar(supabase, PERIODO, AGORA)

        html = ouvidoria_relatorio.montar_html(impressos[-1])

        assert "Fila medida em 16/08/2026 às 07h00" in html
        assert "não se soma ao volume do período" in html
        assert "Carlos Titular" in html

    def test_pdf_nao_carrega_protocolo_de_manifestacao_nenhuma(self, correio, impressos):
        """RN-40 e ADR 0034 decisão 8: este PDF sai do hospital por email, e um
        protocolo de denúncia sigilosa cruzado com o email de acionamento
        identificaria o caso."""
        sigilosa = _caso(42, tipo_manifestacao="denuncia", sigilo_reforcado=True)
        assert sigilosa["protocolo"] == PROTOCOLO_SIGILOSO
        supabase = _SupabaseFake(casos=[sigilosa, _pendente(2)])
        ouvidoria_relatorio.gerar_e_enviar(supabase, PERIODO, AGORA)

        html = ouvidoria_relatorio.montar_html(impressos[-1])

        assert PROTOCOLO_SIGILOSO not in html
        assert "uuid-42" not in html
        assert correio.enviados
        assert PROTOCOLO_SIGILOSO not in correio.enviados[0]["html"]

    def test_pdf_nao_usa_travessao_nem_meia_risca(self, correio, impressos):
        """ADR 0013: o hífen entra em compostos, o travessão não entra em nada
        que o usuário lê."""
        supabase = _cenario()
        ouvidoria_relatorio.gerar_e_enviar(supabase, PERIODO, AGORA)

        html = ouvidoria_relatorio.montar_html(impressos[-1])

        assert "—" not in html
        assert "–" not in html


def _secao(html: str, titulo: str) -> str:
    """Só o pedaço do relatório que fica sob um título. Asserção sobre o HTML
    inteiro confunde o "0,0%" de uma seção com o de outra."""
    _, _, resto = html.partition(f"<h2>{titulo}</h2>")
    assert resto, f"seção ausente: {titulo}"
    return resto.partition("<h2>")[0]


def _registro_de_teste(**mudancas) -> dict:
    """Um registro congelado no formato que o banco guarda, para os testes de
    apresentação que não precisam medir nada."""
    volume_total = mudancas.pop("volume_total", 3)
    dados = {
        "periodo": {"inicio": "2026-08-01", "fim": "2026-08-15"},
        "periodo_anterior": {"inicio": "2026-07-17", "fim": "2026-07-31"},
        "degradado": mudancas.pop("degradado", []),
        # A leitura da nota externa, como o `_registrar` a congela (issue #347).
        # Os testes que precisam da ausência da chave dão `del` nela.
        "nota_externa": mudancas.pop(
            "nota_externa",
            [
                {"fonte": "google", "nota": 4.3, "escala": 5, "registrada_em": "2026-08-14T12:00:00+00:00"},
                {"fonte": "reclame_aqui", "nota": None, "escala": 10, "registrada_em": None},
            ],
        ),
        "volume": {
            "total": volume_total,
            "anterior": 2,
            "variacao_pct": 50.0,
            "novos": volume_total,
            "novos_anterior": 2,
            "novos_variacao_pct": 50.0,
            "reincidentes": 0,
            "por_canal": [{"chave": "ana", "total": volume_total, "anterior": 2, "variacao_pct": 50.0}],
            "por_tipo": [{"chave": "reclamacao", "total": volume_total, "anterior": 2, "variacao_pct": 50.0}],
        },
        # Cada coluna com um número só dela: duas colunas com o mesmo valor
        # deixam passar a troca de uma pela outra, que é como um número errado
        # chega ao PDF sem mudar de aparência.
        "prazo": {
            "trechos": [
                {
                    "trecho": "triagem",
                    "de": "T0",
                    "ate": "T1",
                    "responsavel": "ouvidoria",
                    "medidos": 5,
                    "cumpridos": 4,
                    "estourados": 1,
                    "em_andamento": 2,
                    "sem_prazo": 3,
                    "percentual_cumprido": 80.0,
                }
            ]
        },
        "pendencias_por_area": [
            {
                "setor": "Recepcao",
                "responsavel": "Carlos Titular",
                "pendentes": 5,
                "vencidas": 2,
                "dias_uteis_de_atraso": 3.5,
            }
        ],
        "ranking_areas": [
            {"setor": "Recepcao", "respondidas": 6, "minutos_uteis_medios": 1200, "dias_uteis_medios": 2.5}
        ],
        # `por_area` acompanha `com_a_area`: no módulo real, caso que passou
        # pela área sempre vira linha aqui.
        "prorrogacao": {
            "casos": 1,
            "com_a_area": 4,
            "taxa_pct": 25.0,
            "por_area": [{"setor": "Recepcao", "casos": 4, "prorrogados": 1, "taxa_pct": 25.0}],
        },
        "reincidencia": {"casos": 0, "taxa_pct": 0.0},
        "tempo_pausado": {
            "casos_com_pausa": 0,
            "minutos_uteis_totais": 0,
            "minutos_uteis_medios": 0,
            "dias_uteis_medios": 0.0,
        },
        "top_temas": {
            "itens": [{"chave": "reclamacao", "total": volume_total, "anterior": 2, "variacao_pct": 50.0}],
            "classificados": volume_total,
            "nao_classificados": 0,
        },
        "top_areas": {
            "itens": [{"chave": "Recepcao", "total": volume_total, "anterior": 2, "variacao_pct": 50.0}],
            "classificados": volume_total,
            "nao_classificados": 0,
        },
    }
    for campo in ("top_temas", "top_areas", "prorrogacao", "reincidencia", "prazo", "volume", "tempo_pausado"):
        if campo in mudancas:
            dados[campo] = mudancas.pop(campo)
    assert not mudancas, f"mudanças não aplicadas: {mudancas}"
    return {
        "id": "rel-1",
        "tipo": "quinzenal",
        "competencia": COMPETENCIA,
        "periodo_inicio": "2026-08-01",
        "periodo_fim": "2026-08-15",
        "medido_em": AGORA.isoformat(),
        "dados": dados,
        "enviado_em": None,
        "reenviado_em": None,
        "reenvios": 0,
        "destinatarios": [],
        "ultimo_erro": None,
    }


def _texto_do_pdf(pdf: bytes) -> str:
    """O texto que o PDF realmente imprime, lido de volta dos bytes.

    `%PDF` e tamanho provam que o WeasyPrint não estourou, não que a página
    tem conteúdo: o layout dos destaques usa `display: table-cell`, e uma
    tabela que sumisse no render deixaria o teste verde do mesmo jeito."""
    import io

    import pdfplumber

    with pdfplumber.open(io.BytesIO(pdf)) as documento:
        return "\n".join(pagina.extract_text() or "" for pagina in documento.pages)


# Um registro com os quatro destaques DIFERENTES entre si e com todas as
# tabelas povoadas: é o que permite afirmar, número a número e linha a linha,
# que cada um chegou ao papel. Com dois destaques valendo zero, zerar os quatro
# passaria despercebido.
def _registro_cheio() -> dict:
    return _registro_de_teste(
        volume={
            "total": 43,
            "anterior": 30,
            "variacao_pct": 43.3,
            "novos": 40,
            "novos_anterior": 28,
            "novos_variacao_pct": 42.9,
            "reincidentes": 3,
            "por_canal": [
                {"chave": "site", "total": 38, "anterior": 25, "variacao_pct": 52.0},
                {"chave": "ana", "total": 5, "anterior": 5, "variacao_pct": 0.0},
            ],
        },
        tempo_pausado={
            "casos_com_pausa": 7,
            "minutos_uteis_totais": 2400,
            "minutos_uteis_medios": 342,
            "dias_uteis_medios": 0.7,
        },
        # `classificados + nao_classificados == volume.total`, como o contrato
        # da #341 garante.
        top_temas={
            "itens": [{"chave": "reclamacao", "total": 3, "anterior": 2, "variacao_pct": 50.0}],
            "classificados": 3,
            "nao_classificados": 40,
        },
        # Números diferentes dos do ranking de temas, para as duas linhas não
        # se confundirem na conferência.
        top_areas={
            "itens": [{"chave": "Recepcao", "total": 3, "anterior": 1, "variacao_pct": 200.0}],
            "classificados": 3,
            "nao_classificados": 40,
        },
    )


def _linha_com(texto: str, *pedacos: str) -> str:
    """A linha do PDF que traz TODOS os pedaços juntos.

    Serve para ACHAR a linha, não para conferi-la: casar pedaços soltos aceita
    substring e ignora ordem, então "4" casa com "49" e uma linha com as
    colunas trocadas entre si continua casando. Quem confere é a igualdade da
    linha inteira, em `_linha_igual`."""
    for linha in texto.splitlines():
        if all(pedaco in linha for pedaco in pedacos):
            return linha
    raise AssertionError(f"nenhuma linha do PDF traz {pedacos} juntos")


def _linha_igual(texto: str, *ancoras: str, igual_a: str) -> None:
    """A linha achada pelas âncoras tem que ser EXATAMENTE a esperada.

    É o que separa "o número está na página" de "o número está certo, na coluna
    certa": com igualdade, trocar duas colunas de lugar, imprimir 49 no lugar
    de 4 ou 389 no lugar de 38 fica vermelho."""
    assert _linha_com(texto, *ancoras).strip() == igual_a


class TestRenderReal:
    """WeasyPrint e o template de verdade, sem mock: o PDF precisa sair, e sair
    com o conteúdo dentro."""

    def test_o_pdf_impresso_traz_cada_numero_e_cada_tabela(self):
        """Título de seção não prova tabela, e número solto no documento não
        prova destaque: uma célula de CADA tabela e os quatro números em
        destaque, conferidos na linha em que saem.

        Sem isto, zerar os quatro destaques, apagar a tabela de canais, sumir
        com a seção de tempo médio ou pôr `display:none` na tabela de prazos
        deixa a suíte inteira verde, e o PDF diz à Diretoria que a quinzena teve
        zero manifestação."""
        texto = _texto_do_pdf(ouvidoria_relatorio.renderizar_pdf(_registro_cheio()))

        # Os quatro em destaque saem juntos numa linha, e são diferentes entre
        # si de propósito: com dois valendo zero, zerar os quatro passaria.
        assert _linha_com(texto, "43", "40", "3", "7").strip() == "43 40 3 7"
        _linha_com(texto, "manifestações no período", "casos novos", "reincidentes", "casos com pausa")
        # Uma linha INTEIRA de cada tabela. Conferir por pedaço solto aceitaria
        # a linha com as colunas trocadas entre si, e o PDF diria à Diretoria
        # que a Recepção teve 1 caso e 4 prorrogados quando foram 4 e 1.
        _linha_igual(texto, "Site", igual_a="Site 38 25 +52,0%")
        _linha_igual(texto, "Reclamação", igual_a="Reclamação 3 2 +50,0%")
        _linha_igual(texto, "Triagem", igual_a="Triagem Ouvidoria 5 4 1 2 3 80,0%")
        _linha_igual(texto, "Carlos Titular", igual_a="Recepcao Carlos Titular 5 2 3,5")
        assert "Tempo médio de resposta por área" in texto
        # As três linhas que começam por "Recepcao", cada uma achada pelo número
        # que só ela tem.
        _linha_igual(texto, "Recepcao", "+200,0%", igual_a="Recepcao 3 1 +200,0%")
        _linha_igual(texto, "Recepcao", "25,0%", igual_a="Recepcao 4 1 25,0%")
        _linha_igual(texto, "Recepcao", "2,5", igual_a="Recepcao 6 2,5")

    def test_gera_pdf_de_verdade_com_as_secoes_e_os_numeros(self, correio, impressos):
        supabase = _cenario()
        ouvidoria_relatorio.gerar_e_enviar(supabase, PERIODO, AGORA)

        pdf = ouvidoria_relatorio.renderizar_pdf(impressos[-1])

        assert pdf.startswith(b"%PDF")
        texto = _texto_do_pdf(pdf)
        for secao in (
            "Relatório quinzenal da Ouvidoria",
            "Volume por canal",
            "Temas mais frequentes",
            "Áreas mais frequentes",
            "Prazo cumprido por trecho",
            "Pendências por área",
            "Prorrogação por área",
        ):
            assert secao in texto, f"seção ausente do PDF impresso: {secao}"
        # As duas frases de denominador chegaram inteiras ao papel. Os números
        # em destaque e as células das tabelas têm teste próprio, acima.
        assert "1 tema mais frequente entre os 3 casos já classificados de 43" in texto
        assert "1 área mais frequente entre os 3 casos já classificados de 43" in texto

    def test_gera_pdf_de_verdade_com_a_quinzena_vazia(self):
        """Quinzena sem manifestação nenhuma continua rendendo relatório: é o
        primeiro que a Diretoria vai receber."""
        supabase = _SupabaseFake(casos=[])
        registro = ouvidoria_relatorio._registrar(supabase, "quinzenal", PERIODO, AGORA)

        pdf = ouvidoria_relatorio.renderizar_pdf(registro)

        assert pdf.startswith(b"%PDF")


# ═══════════════════════════════════════════════════════════════════════════
# O envio agendado
# ═══════════════════════════════════════════════════════════════════════════


class TestEnvio:
    def test_email_chega_a_diretoria_com_o_pdf_anexo(self, correio):
        """CA: email à Diretoria Executiva com o PDF anexo."""
        supabase = _cenario()

        entrega = ouvidoria_relatorio.gerar_e_enviar(supabase, PERIODO, AGORA)

        assert len(correio.enviados) == 1
        enviado = correio.enviados[0]
        assert enviado["destinatario"] == "helena@hsm.br"
        assert "01/08/2026 a 15/08/2026" in enviado["assunto"]
        nome, conteudo = enviado["anexos"][0]
        assert nome == f"relatorio-ouvidoria-{COMPETENCIA}.pdf"
        assert conteudo.startswith(b"%PDF")
        assert entrega.registro["enviado_em"] == AGORA.isoformat()
        assert entrega.registro["destinatarios"] == ["helena@hsm.br"]
        assert entrega.entregues == ("helena@hsm.br",)

    def test_quem_foi_desligado_do_hospital_nao_recebe(self, correio):
        """O desligamento é soft delete e não limpa `perfil_ouvidoria`: sem o
        filtro por `ativo`, a diretora desligada continuaria recebendo o
        retrato inteiro da Ouvidoria em PDF, duas vezes por mês, numa caixa que
        já não é do hospital, e nem apareceria mais na tela de Usuários para
        alguém notar."""
        supabase = _cenario()
        assert any(p["email"] == DIRETORA_DESLIGADA["email"] for p in supabase.tabelas["participantes"])

        entrega = ouvidoria_relatorio.gerar_e_enviar(supabase, PERIODO, AGORA)

        assert [e["destinatario"] for e in correio.enviados] == ["helena@hsm.br"]
        assert entrega.registro["destinatarios"] == ["helena@hsm.br"]

    def test_anexo_chega_ao_provedor_de_email(self, monkeypatch):
        """O núcleo de email não suportava anexo. Este teste entra pela porta
        do provedor, e não pela do serviço, para o anexo ser verificado onde
        ele realmente precisa aparecer."""
        monkeypatch.setattr(email_service.settings, "resend_api_key", "chave-de-teste")
        payloads: list[dict] = []
        monkeypatch.setattr(email_service.resend.Emails, "send", lambda payload: payloads.append(payload))

        entregue = email_service.enviar_com_anexo(
            destinatario="helena@hsm.br",
            assunto="Relatório",
            html_content="<p>oi</p>",
            texto_fallback="oi",
            anexos=[("relatorio.pdf", b"%PDF-1.7 bytes")],
        )

        assert entregue is True
        anexo = payloads[0]["attachments"][0]
        assert anexo["filename"] == "relatorio.pdf"
        assert anexo["content_type"] == "application/pdf"
        assert __import__("base64").b64decode(anexo["content"]) == b"%PDF-1.7 bytes"

    def test_rodar_duas_vezes_nao_manda_dois_emails(self, correio):
        """CA: o job é idempotente. O registro da competência é a guarda."""
        supabase = _cenario()

        ouvidoria_relatorio.gerar_e_enviar(supabase, PERIODO, AGORA)
        segunda = ouvidoria_relatorio.gerar_e_enviar(supabase, PERIODO, AGORA + dt.timedelta(minutes=5))

        assert len(correio.enviados) == 1
        assert segunda is None
        assert len(supabase.tabelas["ouvidoria_relatorios"]) == 1

    def test_envio_que_falha_deixa_o_registro_para_a_rodada_seguinte(self, monkeypatch):
        """Provedor fora do ar não pode consumir a edição: o relatório fica
        registrado, o motivo fica escrito e a rodada seguinte entrega os MESMOS
        números, sem remedir."""
        supabase = _cenario()
        recusa = _Correio(entrega=False)
        monkeypatch.setattr(ouvidoria_relatorio, "enviar_com_anexo", recusa)

        primeira = ouvidoria_relatorio.gerar_e_enviar(supabase, PERIODO, AGORA)

        assert primeira.registro["enviado_em"] is None
        assert primeira.entregues == ()
        assert primeira.erro == "O provedor de email recusou a mensagem"

        aceita = _Correio(entrega=True)
        monkeypatch.setattr(ouvidoria_relatorio, "enviar_com_anexo", aceita)
        # A rodada do dia seguinte, que é o que o job diário faz de verdade.
        segunda = ouvidoria_relatorio.gerar_e_enviar(supabase, PERIODO, AGORA + dt.timedelta(days=1))

        assert len(aceita.enviados) == 1
        assert segunda.registro["enviado_em"] is not None
        assert segunda.registro["ultimo_erro"] is None
        assert len(supabase.tabelas["ouvidoria_relatorios"]) == 1
        # Os números são os da primeira medição: o retrato é do instante em que
        # foi tirado, e não do dia em que o email conseguiu sair.
        assert supabase.tabelas["ouvidoria_relatorios"][0]["medido_em"] == AGORA.isoformat()

    def test_entrega_parcial_nao_e_carimbada_como_sucesso(self, monkeypatch):
        """Três diretores, um email aceito. Sem ressalva, o registro afirma que
        os três receberam e o carimbo tira a edição da varredura: ninguém mais
        olharia para ela, e dois diretores nunca souberam do relatório."""
        supabase = _cenario()
        supabase.tabelas["participantes"] = [
            dict(DIRETORA),
            {
                "id": "P14",
                "nome_completo": "Rita",
                "perfil_ouvidoria": "diretoria_executiva",
                "email": "rita@hsm.br",
                "ativo": True,
            },
            {
                "id": "P15",
                "nome_completo": "Ivo",
                "perfil_ouvidoria": "diretoria_executiva",
                "email": "ivo@hsm.br",
                "ativo": True,
            },
        ]
        monkeypatch.setattr(ouvidoria_relatorio, "enviar_com_anexo", _Correio(recusa={"rita@hsm.br", "ivo@hsm.br"}))

        entrega = ouvidoria_relatorio.gerar_e_enviar(supabase, PERIODO, AGORA)

        assert entrega.entregues == ("helena@hsm.br",)
        assert "rita@hsm.br" in entrega.erro and "ivo@hsm.br" in entrega.erro
        linha = supabase.tabelas["ouvidoria_relatorios"][0]
        assert linha["destinatarios"] == ["helena@hsm.br"]
        assert "Entrega parcial" in linha["ultimo_erro"]

    def test_dois_containers_as_07h_mandam_um_email_so(self, correio):
        """Duas réplicas do backend acordam às 07h e leem a MESMA linha ainda
        não enviada. Sem reivindicação atômica, as duas rendem o PDF e a
        Diretoria recebe dois emails iguais. O container órfão servindo código
        antigo já aconteceu nesta casa, e ele roda o scheduler também."""
        supabase = _cenario()
        registro = ouvidoria_relatorio._registrar(supabase, "quinzenal", PERIODO, AGORA)

        container_a = ouvidoria_relatorio._enviar(supabase, dict(registro), AGORA, primeira_entrega=True)
        # O container B carrega a linha como ela estava ANTES do carimbo de A.
        container_b = ouvidoria_relatorio._enviar(supabase, dict(registro), AGORA, primeira_entrega=True)

        assert container_a.saiu
        assert container_b is None
        assert len(correio.enviados) == 1

    def test_reivindicacao_que_nao_entrega_devolve_a_edicao_para_a_fila(self, monkeypatch, correio):
        """Quem carimba e não entrega tem que soltar o carimbo: senão a edição
        sai da varredura de atrasados sem nunca ter saído por email, e o job
        seguinte já calcula outra competência."""
        supabase = _cenario()
        monkeypatch.setattr(ouvidoria_relatorio, "enviar_com_anexo", _Correio(entrega=False))

        ouvidoria_relatorio.gerar_e_enviar(supabase, PERIODO, AGORA)

        assert supabase.tabelas["ouvidoria_relatorios"][0]["enviado_em"] is None
        monkeypatch.setattr(ouvidoria_relatorio, "enviar_com_anexo", correio)
        atrasados = ouvidoria_relatorio.entregar_atrasados(supabase, AGORA + dt.timedelta(days=1), exceto="")
        assert [e.registro["competencia"] for e in atrasados] == [COMPETENCIA]
        assert len(correio.enviados) == 1

    def test_render_que_estoura_escreve_o_motivo_em_vez_de_sumir(self, monkeypatch, correio):
        """A linha é gravada ANTES do render. Se o WeasyPrint levantar e nada
        capturar, sobra na tabela uma edição com `enviado_em` NULL e
        `ultimo_erro` NULL, que na listagem lê como "gerado, aguardando", e
        ninguém fica sabendo que houve falha."""
        supabase = _cenario()

        def _weasyprint_fora(_registro):
            raise RuntimeError("libpango sumiu do container")

        monkeypatch.setattr(ouvidoria_relatorio, "renderizar_pdf", _weasyprint_fora)

        entrega = ouvidoria_relatorio.gerar_e_enviar(supabase, PERIODO, AGORA)

        assert not correio.enviados
        linha = supabase.tabelas["ouvidoria_relatorios"][0]
        assert linha["enviado_em"] is None
        assert "libpango sumiu do container" in linha["ultimo_erro"]
        assert entrega.erro == linha["ultimo_erro"]

    def test_sem_diretoria_cadastrada_o_relatorio_fica_registrado_com_o_motivo(self, correio):
        """Ninguém com o perfil não é o mesmo que email entregue: o relatório
        existe, ninguém recebeu, e o registro diz por quê."""
        supabase = _cenario()
        supabase.tabelas["participantes"] = []

        entrega = ouvidoria_relatorio.gerar_e_enviar(supabase, PERIODO, AGORA)

        assert not correio.enviados
        assert entrega.registro["enviado_em"] is None
        assert "Diretoria Executiva" in entrega.erro

    def test_falha_ao_ler_a_diretoria_nao_vira_relatorio_enviado(self, correio):
        """Leitura que falhou e lista vazia são coisas diferentes: um timeout
        não pode carimbar a edição como entregue."""
        supabase = _cenario()
        supabase.indisponiveis.add("participantes")

        entrega = ouvidoria_relatorio.gerar_e_enviar(supabase, PERIODO, AGORA)

        assert not correio.enviados
        assert entrega.registro["enviado_em"] is None
        assert "ler quem é a Diretoria Executiva" in entrega.erro


# ═══════════════════════════════════════════════════════════════════════════
# Registro e reenvio
# ═══════════════════════════════════════════════════════════════════════════


class TestRegistroEReenvio:
    def test_ouvidor_lista_os_relatorios_gerados(self, monkeypatch, correio):
        """CA: o relatório gerado fica registrado."""
        supabase = _cenario()
        ouvidoria_relatorio.gerar_e_enviar(supabase, PERIODO, AGORA)
        client = _client(monkeypatch, supabase, OUVIDOR)

        res = client.get("/api/ouvidoria/relatorios")

        assert res.status_code == 200
        linha = res.json()["relatorios"][0]
        assert linha["competencia"] == COMPETENCIA
        assert linha["enviado_em"] == AGORA.isoformat()
        assert linha["destinatarios"] == ["helena@hsm.br"]
        # A listagem é prateleira: o objeto inteiro de métricas não viaja nela.
        assert "dados" not in linha

    def test_ouvidor_reenvia_o_relatorio_ja_gerado(self, monkeypatch, correio):
        """CA: o ouvidor recupera email perdido sem esperar a próxima quinzena."""
        supabase = _cenario()
        ouvidoria_relatorio.gerar_e_enviar(supabase, PERIODO, AGORA)
        relatorio_id = supabase.tabelas["ouvidoria_relatorios"][0]["id"]
        client = _client(monkeypatch, supabase, OUVIDOR)

        res = client.post(f"/api/ouvidoria/relatorios/{relatorio_id}/reenvio")

        assert res.status_code == 200
        assert res.json()["destinatarios"] == ["helena@hsm.br"]
        assert len(correio.enviados) == 2
        assert correio.enviados[1]["anexos"][0][1].startswith(b"%PDF")

    def test_reenvio_preserva_o_carimbo_da_primeira_entrega(self, monkeypatch, correio):
        """`enviado_em` responde "esta edição saiu?", e a resposta é a data da
        primeira entrega. Se o reenvio a reescrevesse, o histórico passaria a
        dizer que o relatório de agosto saiu em setembro."""
        supabase = _cenario()
        ouvidoria_relatorio.gerar_e_enviar(supabase, PERIODO, AGORA)
        registro = supabase.tabelas["ouvidoria_relatorios"][0]

        ouvidoria_relatorio.reenviar(supabase, registro["id"], DEPOIS)

        assert supabase.tabelas["ouvidoria_relatorios"][0]["enviado_em"] == AGORA.isoformat()

    def test_reenvio_mostra_os_numeros_congelados_e_nao_os_de_hoje(self, correio, impressos):
        """A fila de pendências não tem recorte de data: ela é sempre a de
        hoje. Um relatório de agosto reenviado em setembro precisa carregar a
        fila de agosto, e não a que cresceu depois.

        A asserção é sobre o que foi PARA o PDF que saiu, e não sobre a linha
        guardada no banco: é o papel que chega à Diretoria que importa, e é ele
        que uma remedição no reenvio estragaria."""
        supabase = _SupabaseFake(casos=[_caso(1), _pendente(2)])
        ouvidoria_relatorio.gerar_e_enviar(supabase, PERIODO, AGORA)
        assert "Cardiologia" not in ouvidoria_relatorio.montar_html(impressos[-1])

        # A fila viva cresce depois da geração, com outro setor.
        supabase.tabelas["ouvidoria_protocolos"].append(_pendente(3, setor="Cardiologia"))
        supabase.tabelas["ouvidoria_setor_responsaveis"].append(
            {
                "id": "resp-2",
                "setor": "Cardiologia",
                "papel": "titular",
                "nome": "Ana Cardio",
                "email": "ana@hsm.br",
                "vigencia_inicio": "2026-01-01",
                "vigencia_fim": None,
            }
        )
        registro = supabase.tabelas["ouvidoria_relatorios"][0]

        ouvidoria_relatorio.reenviar(supabase, registro["id"], DEPOIS)

        reenviado = ouvidoria_relatorio.montar_html(impressos[-1])
        assert len(impressos) == 2
        assert "Cardiologia" not in reenviado
        assert "Fila medida em 16/08/2026 às 07h00" in reenviado

    def test_reenvio_roda_fora_do_event_loop(self):
        """A rota renderiza um PDF com o WeasyPrint e faz um POST no Resend, os
        dois síncronos e os dois medidos em segundos. Como corrotina, isso
        prende o event loop, e o backend roda com um worker só: dez reenvios
        seguidos, que o limite de 10/minuto permite, deixariam a API do
        hospital inteira sem atender. Com `def`, o FastAPI usa o threadpool."""
        import inspect

        rota = next(r for r in ouvidoria_router.router.routes if getattr(r, "name", "") == "reenviar_relatorio")

        assert not inspect.iscoroutinefunction(rota.endpoint)

    def test_reenvio_de_relatorio_inexistente_da_404(self, monkeypatch, correio):
        client = _client(monkeypatch, _cenario(), OUVIDOR)

        res = client.post("/api/ouvidoria/relatorios/rel-que-nao-existe/reenvio")

        assert res.status_code == 404
        assert not correio.enviados

    def test_reenvio_com_id_que_o_banco_recusa_da_404_sem_vazar_o_erro(self, monkeypatch, correio):
        """`id` é UUID no Postgres: um id qualquer faz o PostgREST recusar o
        filtro (22P02). Sem tratar, o APIError sobe e o handler global devolve
        500 com a mensagem inteira do banco para quem chamou."""
        supabase = _cenario()
        supabase.recusa_filtro_de_id = True
        client = _client(monkeypatch, supabase, OUVIDOR)

        res = client.post("/api/ouvidoria/relatorios/nao-e-uuid/reenvio")

        assert res.status_code == 404
        assert "22P02" not in res.text
        assert not correio.enviados

    def test_reenvio_que_falha_nao_diz_que_alguem_recebeu(self, monkeypatch, correio):
        """No caminho de recusa, a resposta traria a lista da PRIMEIRA entrega
        se ela viesse da coluna do banco, e a tela avisaria "reenviado para
        Helena" depois de um envio que não saiu."""
        supabase = _cenario()
        ouvidoria_relatorio.gerar_e_enviar(supabase, PERIODO, AGORA)
        relatorio_id = supabase.tabelas["ouvidoria_relatorios"][0]["id"]
        monkeypatch.setattr(ouvidoria_relatorio, "enviar_com_anexo", _Correio(entrega=False))
        client = _client(monkeypatch, supabase, OUVIDOR)

        res = client.post(f"/api/ouvidoria/relatorios/{relatorio_id}/reenvio")

        assert res.status_code == 200
        assert res.json()["destinatarios"] == []
        assert res.json()["erro"] == "O provedor de email recusou a mensagem"
        # E o histórico de quem recebeu de verdade continua no registro.
        assert supabase.tabelas["ouvidoria_relatorios"][0]["destinatarios"] == ["helena@hsm.br"]

    def test_reenvio_para_outra_diretoria_nao_apaga_quem_recebeu_antes(self, correio):
        """Em setembro o relatório sai para Helena; em outubro ela saiu do
        hospital e quem reenvia manda para Rita. Numa distribuição de dado da
        Ouvidoria para fora do sistema, quem recebeu é evidência: a lista
        acumula, não troca."""
        supabase = _cenario()
        ouvidoria_relatorio.gerar_e_enviar(supabase, PERIODO, AGORA)
        registro = supabase.tabelas["ouvidoria_relatorios"][0]
        supabase.tabelas["participantes"] = [
            {**DIRETORA, "ativo": False},
            {
                "id": "P13",
                "nome_completo": "Rita Diretora",
                "perfil_ouvidoria": "diretoria_executiva",
                "email": "rita@hsm.br",
                "ativo": True,
            },
        ]

        entrega = ouvidoria_relatorio.reenviar(supabase, registro["id"], DEPOIS)

        assert entrega.entregues == ("rita@hsm.br",)
        assert supabase.tabelas["ouvidoria_relatorios"][0]["destinatarios"] == ["helena@hsm.br", "rita@hsm.br"]

    def test_reenvio_deixa_rastro_de_quando_e_de_quantas_vezes(self, correio):
        """Num documento arquivado, "saiu em 16/08" não responde quantas vezes
        o PDF foi reemitido depois nem quando."""
        supabase = _cenario()
        ouvidoria_relatorio.gerar_e_enviar(supabase, PERIODO, AGORA)
        registro = supabase.tabelas["ouvidoria_relatorios"][0]

        ouvidoria_relatorio.reenviar(supabase, registro["id"], DEPOIS)
        ouvidoria_relatorio.reenviar(supabase, registro["id"], DEPOIS + dt.timedelta(days=1))

        linha = supabase.tabelas["ouvidoria_relatorios"][0]
        assert linha["enviado_em"] == AGORA.isoformat()
        assert linha["reenvios"] == 2
        assert linha["reenviado_em"] == (DEPOIS + dt.timedelta(days=1)).isoformat()

    def test_reenvio_registra_quem_apertou_o_botao(self, monkeypatch, correio):
        """O PDF da Ouvidoria SAI do sistema quando alguém aperta este botão.
        Sem trilha, dez reenvios num dia não têm autor (CONTEXT.md: todo acesso
        gera registro)."""
        supabase = _cenario()
        ouvidoria_relatorio.gerar_e_enviar(supabase, PERIODO, AGORA)
        relatorio_id = supabase.tabelas["ouvidoria_relatorios"][0]["id"]
        client = _client(monkeypatch, supabase, OUVIDOR)

        client.post(f"/api/ouvidoria/relatorios/{relatorio_id}/reenvio")

        trilha = supabase.tabelas.get("audit_log") or []
        assert len(trilha) == 1
        assert trilha[0]["action"] == "REENVIAR_RELATORIO_OUVIDORIA"
        assert trilha[0]["actor_id"] == OUVIDOR["id"]
        assert trilha[0]["target_id"] == relatorio_id
        assert trilha[0]["metadata"]["destinatarios"] == ["helena@hsm.br"]


class TestAcesso:
    """CA: perfis fora de ouvidor e diretoria executiva não acessam registro
    nem reenvio. As fixtures deixam as OUTRAS portas abertas de propósito, para
    o 403 vir da guarda da Ouvidoria e não de outra guarda qualquer."""

    @pytest.mark.parametrize("participante", [SUPER_ADMIN, SECRETARIA], ids=["super_admin", "secretaria"])
    def test_perfil_de_fora_nao_lista_nem_reenvia(self, monkeypatch, correio, participante):
        supabase = _cenario()
        ouvidoria_relatorio.gerar_e_enviar(supabase, PERIODO, AGORA)
        relatorio_id = supabase.tabelas["ouvidoria_relatorios"][0]["id"]
        emails_antes = len(correio.enviados)
        client = _client(monkeypatch, supabase, participante)

        listagem = client.get("/api/ouvidoria/relatorios")
        reenvio = client.post(f"/api/ouvidoria/relatorios/{relatorio_id}/reenvio")

        assert listagem.status_code == 403
        assert reenvio.status_code == 403
        # O que NÃO aconteceu: nenhum email saiu na recusa.
        assert len(correio.enviados) == emails_antes

    def test_diretoria_executiva_lista_e_reenvia(self, monkeypatch, correio):
        """A outra ponta da mesma guarda: quem tem o perfil passa. Sem isto, um
        403 universal deixaria o teste acima verde."""
        supabase = _cenario()
        ouvidoria_relatorio.gerar_e_enviar(supabase, PERIODO, AGORA)
        relatorio_id = supabase.tabelas["ouvidoria_relatorios"][0]["id"]
        client = _client(monkeypatch, supabase, DIRETORA)

        assert client.get("/api/ouvidoria/relatorios").status_code == 200
        assert client.post(f"/api/ouvidoria/relatorios/{relatorio_id}/reenvio").status_code == 200


# ═══════════════════════════════════════════════════════════════════════════
# Retrato externo: a nota do Google e a do Reclame Aqui (issue #347)
# ═══════════════════════════════════════════════════════════════════════════


def _nota(fonte: str, nota: float, registrada_em: str, quem: str = "Marta Ouvidora") -> dict:
    return {
        "id": f"nota-{fonte}-{registrada_em}",
        "fonte": fonte,
        "nota": nota,
        "registrada_em": registrada_em,
        "registrada_por": "P10",
        "registrada_por_nome": quem,
    }


class TestNotaExterna:
    """A nota que o hospital tem fora dele entra no relatório pelo mesmo
    contrato do resto: congelada na geração e nunca inventada."""

    def test_o_pdf_traz_a_ultima_nota_de_cada_fonte_com_a_escala(self, correio, impressos):
        """CA: o relatório exibe a última nota registrada de cada fonte.

        Com a escala ao lado, e não o número sozinho: 4,3 de 5 é 86% e 7,8 de
        10 é 78%. Lado a lado sem denominador, o leitor conclui o contrário."""
        supabase = _cenario()
        supabase.tabelas["ouvidoria_nota_externa"] = [
            _nota("google", 4.1, "2026-08-02T12:00:00+00:00"),
            _nota("google", 4.3, "2026-08-14T12:00:00+00:00"),
            _nota("reclame_aqui", 7.8, "2026-08-10T12:00:00+00:00"),
        ]

        ouvidoria_relatorio.gerar_e_enviar(supabase, PERIODO, AGORA)
        texto = _texto_do_pdf(ouvidoria_relatorio.renderizar_pdf(impressos[-1]))

        assert "Retrato externo" in texto
        # As âncoras levam o valor junto: a frase do bloco também nomeia as
        # duas fontes, e ancorar só no nome acharia a frase, não a linha.
        _linha_igual(texto, "Google", "de 5", igual_a="Google 4,3 de 5 14/08/2026")
        _linha_igual(texto, "Reclame Aqui", "de 10", igual_a="Reclame Aqui 7,8 de 10 10/08/2026")

    def test_fonte_sem_nota_registrada_nao_imprime_zero(self, correio, impressos):
        """Ausência de registro é ausência. "0,0 de 5" leria como a pior nota
        possível no Google, e o hospital apareceria no chão por não ter sido
        digitado nada."""
        supabase = _cenario()
        supabase.tabelas["ouvidoria_nota_externa"] = [_nota("google", 4.3, "2026-08-14T12:00:00+00:00")]

        ouvidoria_relatorio.gerar_e_enviar(supabase, PERIODO, AGORA)
        texto = _texto_do_pdf(ouvidoria_relatorio.renderizar_pdf(impressos[-1]))

        _linha_igual(texto, "Reclame Aqui", "sem registro", igual_a="Reclame Aqui sem registro")
        assert "0,0 de 10" not in texto

    def test_reenvio_mostra_a_nota_congelada_e_nao_a_de_hoje(self, correio, impressos):
        """O mesmo contrato da fila de pendências: o relatório de agosto
        reenviado em setembro carrega a nota de agosto."""
        supabase = _cenario()
        supabase.tabelas["ouvidoria_nota_externa"] = [_nota("google", 4.3, "2026-08-14T12:00:00+00:00")]
        ouvidoria_relatorio.gerar_e_enviar(supabase, PERIODO, AGORA)

        # O ouvidor registra uma nota nova depois da geração.
        supabase.tabelas["ouvidoria_nota_externa"].append(_nota("google", 2.9, "2026-09-19T12:00:00+00:00"))
        ouvidoria_relatorio.reenviar(supabase, supabase.tabelas["ouvidoria_relatorios"][0]["id"], DEPOIS)

        assert len(impressos) == 2
        reenviado = _texto_do_pdf(ouvidoria_relatorio.renderizar_pdf(impressos[-1]))
        _linha_igual(reenviado, "Google", "de 5", igual_a="Google 4,3 de 5 14/08/2026")
        assert "2,9" not in reenviado

    def test_leitura_da_nota_que_falha_vira_aviso_em_vez_de_numero(self, correio, impressos):
        """A tabela fora do ar não pode derrubar o relatório inteiro, e também
        não pode virar "sem registro": uma coisa é ninguém ter digitado, outra
        é o sistema não ter conseguido ler."""
        supabase = _cenario()
        supabase.indisponiveis.add("ouvidoria_nota_externa")

        ouvidoria_relatorio.gerar_e_enviar(supabase, PERIODO, AGORA)
        texto = _texto_do_pdf(ouvidoria_relatorio.renderizar_pdf(impressos[-1]))

        assert "sem registro" not in texto
        assert "nota externa" in texto.lower()
        assert len(correio.enviados) == 1

    def test_relatorio_gerado_antes_desta_fatia_nao_diz_que_a_leitura_falhou(self):
        """A edição congelada ANTES de a nota externa existir não tem a chave
        `nota_externa` no `dados`, e reenviá-la é caminho vivo (o botão do
        ouvidor).

        Chave ausente é diferente de leitura que falhou. Tratar as duas como a
        mesma coisa faz o PDF de agosto, reenviado hoje, acusar uma falha de
        sistema que nunca houve, e ainda contradizer o corpo do email, cujos
        avisos vêm do `degradado` congelado e não mencionam nada."""
        antigo = _registro_de_teste()
        del antigo["dados"]["nota_externa"]

        texto = _texto_do_pdf(ouvidoria_relatorio.renderizar_pdf(antigo))

        assert "Retrato externo" not in texto
        assert "não pôde ser lida" not in texto

    def test_leitura_que_falha_continua_dizendo_que_falhou(self):
        """A outra metade: sem ela, omitir o bloco sempre deixaria o teste
        acima verde e a degradação sumiria do papel."""
        texto = _texto_do_pdf(ouvidoria_relatorio.renderizar_pdf(_registro_de_teste(nota_externa=None)))

        assert "Retrato externo" in texto
        assert "não pôde ser lida" in texto


# ═══════════════════════════════════════════════════════════════════════════
# A fila de recuperação do job (issue #434)
# ═══════════════════════════════════════════════════════════════════════════

# O super admin que recebe os avisos operacionais do módulo. ATIVO e com email:
# `avisar_admins_tecnicos` filtra os dois.
ADMIN_TECNICO = {
    "id": "P03",
    "nome_completo": "Pedro Admin",
    "access_profile": "super_admin",
    "perfil_ouvidoria": None,
    "email": "pedro@hsm.br",
    "ativo": True,
}


def _sem_render(monkeypatch) -> list[dict]:
    """Troca o WeasyPrint por um espião e devolve o que foi impresso.

    Estes testes contam TENTATIVAS, não conteúdo: renderizar de verdade cinco
    PDFs por teste só compra segundos. Quem afere o PDF é a fixture
    `impressos`, que renderiza de verdade."""
    impressos: list[dict] = []

    def _espiao(registro):
        impressos.append(registro)
        return b"%PDF-fake"

    monkeypatch.setattr(ouvidoria_relatorio, "renderizar_pdf", _espiao)
    return impressos


def _atrasada(supabase: _SupabaseFake, competencia: str, periodo_fim: str, **campos) -> dict:
    """Uma edição já gerada que nunca saiu, direto na tabela."""
    linha = _registro_de_teste()
    linha.update(
        {
            "id": f"rel-{competencia}",
            "competencia": competencia,
            "periodo_fim": periodo_fim,
            "enviado_em": None,
            "tentativas": 0,
            "desistido_em": None,
        }
    )
    linha.update(campos)
    supabase.tabelas["ouvidoria_relatorios"].append(linha)
    return linha


def _quatro_atrasadas(supabase: _SupabaseFake) -> list[dict]:
    """Quatro quinzenas seguidas geradas e não entregues: uma a mais do que o
    lote de uma rodada, que é o cenário em que alguém fica de fora."""
    return [
        _atrasada(supabase, "quinzenal-2026-06-01-2026-06-15", "2026-06-15"),
        _atrasada(supabase, "quinzenal-2026-06-16-2026-06-30", "2026-06-30"),
        _atrasada(supabase, "quinzenal-2026-07-01-2026-07-15", "2026-07-15"),
        _atrasada(supabase, "quinzenal-2026-07-16-2026-07-31", "2026-07-31"),
    ]


def _avisos_ao_admin(monkeypatch) -> list[dict]:
    """O que sairia por `avisar_admins_tecnicos`, sem tocar provedor nenhum."""
    from app.services import ouvidoria_notificacoes

    recebidos: list[dict] = []

    def _espiao(destinatario, assunto, html, texto):
        recebidos.append({"destinatario": destinatario, "assunto": assunto, "texto": texto})
        return True

    monkeypatch.setattr(ouvidoria_notificacoes, "_enviar_email", _espiao)
    return recebidos


class TestTetoDeTentativas:
    def test_falha_definitiva_desiste_no_teto_e_para_de_tentar(self, monkeypatch):
        """CA: a edição que falha em definitivo vira estado terminal e não
        gera PDF todo dia para sempre.

        Sem teto, o provedor recusando aquele domínio (ou o render quebrado
        naquela edição) faz o job render e tentar a MESMA linha todo dia até
        alguém olhar o log, e ninguém olha o log."""
        supabase = _cenario()
        monkeypatch.setattr(ouvidoria_relatorio, "enviar_com_anexo", _Correio(entrega=False))
        impressos = _sem_render(monkeypatch)

        for dia in range(ouvidoria_relatorio.TETO_DE_TENTATIVAS):
            ouvidoria_relatorio.gerar_e_enviar(supabase, PERIODO, AGORA + dt.timedelta(days=dia))

        linha = supabase.tabelas["ouvidoria_relatorios"][0]
        assert linha["tentativas"] == ouvidoria_relatorio.TETO_DE_TENTATIVAS
        assert linha["desistido_em"] is not None
        renders_ate_desistir = len(impressos)

        # O dia seguinte, e o outro: nenhuma tentativa nova, nenhum PDF novo.
        for dia in (ouvidoria_relatorio.TETO_DE_TENTATIVAS, ouvidoria_relatorio.TETO_DE_TENTATIVAS + 1):
            assert ouvidoria_relatorio.gerar_e_enviar(supabase, PERIODO, AGORA + dt.timedelta(days=dia)) is None
        assert len(impressos) == renders_ate_desistir, "a edição terminal continuou rendendo PDF"
        assert linha["tentativas"] == ouvidoria_relatorio.TETO_DE_TENTATIVAS

    def test_a_edicao_terminal_sai_da_fila_de_recuperacao(self, monkeypatch, correio):
        """A varredura tem lote: uma edição morta que continua na fila ocupa a
        vaga de uma viva, e a viva nunca é tentada."""
        supabase = _SupabaseFake()
        _atrasada(
            supabase,
            "quinzenal-2026-05-01-2026-05-15",
            "2026-05-15",
            tentativas=ouvidoria_relatorio.TETO_DE_TENTATIVAS,
            desistido_em=AGORA.isoformat(),
        )
        viva = _atrasada(supabase, "quinzenal-2026-07-01-2026-07-15", "2026-07-15")
        monkeypatch.setattr(ouvidoria_relatorio, "enviar_com_anexo", correio)
        _sem_render(monkeypatch)

        entregas = ouvidoria_relatorio.entregar_atrasados(supabase, AGORA)

        assert [e.registro["competencia"] for e in entregas] == [viva["competencia"]]
        assert len(correio.enviados) == 1

    def test_listagem_mostra_a_edicao_que_a_entrega_automatica_abandonou(self):
        """O estado terminal precisa aparecer para quem olha a prateleira. Sem
        as duas colunas na listagem, a linha lê como "gerada, aguardando", que
        é exatamente o que ela deixou de ser."""
        supabase = _SupabaseFake()
        _atrasada(
            supabase,
            COMPETENCIA,
            "2026-08-15",
            tentativas=ouvidoria_relatorio.TETO_DE_TENTATIVAS,
            desistido_em=AGORA.isoformat(),
        )

        linha = ouvidoria_relatorio.listar(supabase)[0]

        assert linha["desistido_em"] == AGORA.isoformat()
        assert linha["tentativas"] == ouvidoria_relatorio.TETO_DE_TENTATIVAS

    def test_reenvio_manual_entrega_a_edicao_que_o_job_abandonou(self, monkeypatch, correio):
        """Desistir é do caminho automático, e não da edição. O `ultimo_erro`
        manda usar o reenvio, e a promessa tem que valer: sem isso o teto
        transforma uma quinzena atrasada numa quinzena perdida."""
        supabase = _SupabaseFake()
        linha = _atrasada(
            supabase,
            COMPETENCIA,
            "2026-08-15",
            tentativas=ouvidoria_relatorio.TETO_DE_TENTATIVAS,
            desistido_em=AGORA.isoformat(),
        )
        monkeypatch.setattr(ouvidoria_relatorio, "enviar_com_anexo", correio)
        _sem_render(monkeypatch)

        entrega = ouvidoria_relatorio.reenviar(supabase, linha["id"], DEPOIS)

        assert entrega.entregues == (DIRETORA["email"],)
        assert linha["enviado_em"] == DEPOIS.isoformat()
        # Entregue e desistida ao mesmo tempo são duas afirmações contrárias
        # sobre a mesma edição, e é a listagem que fica dizendo as duas.
        assert linha["desistido_em"] is None
        assert linha["tentativas"] == 0

    def test_reenvio_manual_que_falha_nao_gasta_o_teto_do_job(self, monkeypatch):
        """O teto é do caminho AUTOMÁTICO. Quem aperta o botão está olhando o
        resultado na tela, e um ouvidor insistindo não pode enterrar a edição
        para o job."""
        supabase = _SupabaseFake()
        linha = _atrasada(supabase, COMPETENCIA, "2026-08-15")
        monkeypatch.setattr(ouvidoria_relatorio, "enviar_com_anexo", _Correio(entrega=False))
        _sem_render(monkeypatch)

        for _ in range(ouvidoria_relatorio.TETO_DE_TENTATIVAS + 1):
            ouvidoria_relatorio.reenviar(supabase, linha["id"], AGORA)

        assert linha["tentativas"] == 0
        assert linha["desistido_em"] is None


class TestFilaPorEstado:
    def test_quatro_edicoes_atrasadas_e_nenhuma_fica_de_fora(self, monkeypatch):
        """CA: a varredura não abandona edição antiga em silêncio.

        Com lote de 3 e ordem fixa por período, a quarta edição não enviada
        fica fora da janela para SEMPRE: toda rodada relê as mesmas três. A
        fila anda por ESTADO (quem tentou menos vai na frente), e por isso duas
        rodadas alcançam as quatro."""
        supabase = _SupabaseFake()
        _quatro_atrasadas(supabase)
        monkeypatch.setattr(ouvidoria_relatorio, "enviar_com_anexo", _Correio(entrega=False))
        _sem_render(monkeypatch)

        for dia in (0, 1):
            ouvidoria_relatorio.entregar_atrasados(supabase, AGORA + dt.timedelta(days=dia))

        esquecidas = [
            linha["competencia"] for linha in supabase.tabelas["ouvidoria_relatorios"] if not linha["tentativas"]
        ]
        assert esquecidas == [], f"a varredura nunca chegou em {esquecidas}"

    def test_lote_de_recuperacao_entrega_tres_no_dia_da_virada(self, monkeypatch, correio):
        """CA: nos dias 1 e 16 o lote continua sendo 3.

        Nesses dois dias a rodada passa `exceto` com a competência que ela
        mesma vai gerar. Resolvido em Python DEPOIS do limite do banco, o
        `exceto` come uma vaga do lote e a recuperação anda 2 por dia em vez
        de 3, justamente nos dias em que a fila mais cresce.

        A edição do dia entra na fila com ZERO tentativa, e as atrasadas já
        acumularam as suas: é isso que a põe na frente do lote, e é por isso
        que a vaga que ela come é a de uma edição que precisa da vaga."""
        supabase = _SupabaseFake()
        for linha in _quatro_atrasadas(supabase):
            linha["tentativas"] = 2
        do_dia = _atrasada(supabase, COMPETENCIA, "2026-08-15")
        monkeypatch.setattr(ouvidoria_relatorio, "enviar_com_anexo", correio)
        _sem_render(monkeypatch)

        entregas = ouvidoria_relatorio.entregar_atrasados(supabase, AGORA, exceto=do_dia["competencia"])

        assert len(entregas) == ouvidoria_relatorio.LOTE_DE_ATRASADOS
        assert do_dia["competencia"] not in [e.registro["competencia"] for e in entregas]
        assert do_dia["enviado_em"] is None


class TestTrilhaDoCaminhoAutomatico:
    def test_falha_do_job_entra_no_audit_log(self, monkeypatch):
        """CA: a falha do caminho automático deixa rastro permanente, como o
        reenvio manual já deixa. O log da aplicação some no rodízio do
        container; a trilha é o que sobra para reconstruir por que a Diretoria
        não recebeu a edição de agosto."""
        supabase = _cenario()
        monkeypatch.setattr(ouvidoria_relatorio, "enviar_com_anexo", _Correio(entrega=False))
        _sem_render(monkeypatch)

        ouvidoria_relatorio.gerar_e_enviar(supabase, PERIODO, AGORA)

        trilha = supabase.tabelas.get("audit_log", [])
        assert [linha["action"] for linha in trilha] == ["RELATORIO_OUVIDORIA_FALHA_AUTOMATICA"]
        assert trilha[0]["metadata"]["competencia"] == COMPETENCIA
        assert "provedor de email" in trilha[0]["metadata"]["erro"]
        assert trilha[0]["metadata"]["tentativas"] == 1

    def test_desistencia_aparece_na_trilha_como_desistencia(self, monkeypatch):
        """O teto atingido é o evento que muda o mundo: ninguém mais vai tentar
        aquela edição sozinho. Uma falha igual às outras na trilha esconde
        exatamente isso."""
        supabase = _cenario()
        monkeypatch.setattr(ouvidoria_relatorio, "enviar_com_anexo", _Correio(entrega=False))
        _sem_render(monkeypatch)

        for dia in range(ouvidoria_relatorio.TETO_DE_TENTATIVAS):
            ouvidoria_relatorio.gerar_e_enviar(supabase, PERIODO, AGORA + dt.timedelta(days=dia))

        trilha = supabase.tabelas.get("audit_log", [])
        assert [linha["metadata"]["desistiu"] for linha in trilha] == [False] * (
            ouvidoria_relatorio.TETO_DE_TENTATIVAS - 1
        ) + [True]

    def test_recuperacao_do_job_entra_no_audit_log(self, monkeypatch, correio):
        """A outra metade do CA: a edição que a varredura salvou também é
        evento, e é ela que responde "quando a Diretoria finalmente recebeu?"."""
        supabase = _SupabaseFake()
        atrasada = _atrasada(supabase, COMPETENCIA, "2026-08-15", tentativas=2)
        monkeypatch.setattr(ouvidoria_relatorio, "enviar_com_anexo", correio)
        _sem_render(monkeypatch)

        ouvidoria_relatorio.entregar_atrasados(supabase, AGORA)

        trilha = supabase.tabelas.get("audit_log", [])
        assert [linha["action"] for linha in trilha] == ["RELATORIO_OUVIDORIA_RECUPERADO"]
        assert trilha[0]["target_id"] == atrasada["id"]
        assert trilha[0]["metadata"]["destinatarios"] == [DIRETORA["email"]]
        assert trilha[0]["metadata"]["tentativas"] == 2

    def test_varredura_que_falha_nao_diz_que_recuperou(self, monkeypatch):
        """A recuperação é o evento de que a edição SAIU. Escrita também na
        tentativa que não entregou, a trilha afirmaria que a Diretoria recebeu
        uma edição que continua parada, e é a trilha que responde isso meses
        depois, quando ninguém lembra da manhã em que o provedor caiu."""
        supabase = _SupabaseFake()
        _atrasada(supabase, COMPETENCIA, "2026-08-15")
        monkeypatch.setattr(ouvidoria_relatorio, "enviar_com_anexo", _Correio(entrega=False))
        _sem_render(monkeypatch)

        ouvidoria_relatorio.entregar_atrasados(supabase, AGORA)

        acoes = [linha["action"] for linha in supabase.tabelas.get("audit_log", [])]
        assert acoes == ["RELATORIO_OUVIDORIA_FALHA_AUTOMATICA"]

    def test_entrega_do_dia_que_deu_certo_nao_vira_evento(self, monkeypatch, correio):
        """A trilha registra o que saiu do trilho. O caminho saudável de todo
        dia 16 na trilha seria ruído com cara de incidente, e afogaria os dois
        eventos que importam."""
        supabase = _cenario()
        monkeypatch.setattr(ouvidoria_relatorio, "enviar_com_anexo", correio)
        _sem_render(monkeypatch)

        entrega = ouvidoria_relatorio.gerar_e_enviar(supabase, PERIODO, AGORA)

        assert entrega.saiu
        assert supabase.tabelas.get("audit_log", []) == []


class TestAvisoSemDiretoria:
    def test_sem_diretoria_ativa_o_admin_tecnico_e_avisado(self, monkeypatch, correio):
        """CA: hoje o relatório é gerado, nunca sai, e ninguém fica sabendo.

        A Diretoria desligada fica na fixture de propósito: o cadastro NÃO está
        vazio, e mesmo assim não há ninguém ativo para receber. É esse o caso
        que acontece de verdade, porque o desligamento é soft delete e não
        limpa o perfil."""
        supabase = _cenario()
        supabase.tabelas["participantes"] = [dict(DIRETORA_DESLIGADA), dict(ADMIN_TECNICO)]
        avisos = _avisos_ao_admin(monkeypatch)
        _sem_render(monkeypatch)

        entrega = ouvidoria_relatorio.gerar_e_enviar(supabase, PERIODO, AGORA)

        assert not correio.enviados
        assert entrega.registro["enviado_em"] is None
        assert [aviso["destinatario"] for aviso in avisos] == [ADMIN_TECNICO["email"]]
        assert COMPETENCIA in avisos[0]["texto"]
        assert "Diretoria Executiva" in avisos[0]["texto"]

    def test_com_diretoria_ativa_ninguem_incomoda_o_admin_tecnico(self, monkeypatch, correio):
        """O avesso do teste acima: o aviso é do buraco de cadastro, e não de
        toda rodada do job."""
        supabase = _cenario()
        supabase.tabelas["participantes"] = [dict(DIRETORA), dict(ADMIN_TECNICO)]
        avisos = _avisos_ao_admin(monkeypatch)
        _sem_render(monkeypatch)

        ouvidoria_relatorio.gerar_e_enviar(supabase, PERIODO, AGORA)

        assert len(correio.enviados) == 1
        assert avisos == []

    def test_reenvio_manual_sem_diretoria_nao_avisa_o_admin(self, monkeypatch, correio):
        """Quem apertou o botão está na tela e recebe o motivo por lá. Avisar o
        admin técnico a cada clique transformaria o alerta em ruído."""
        supabase = _SupabaseFake()
        linha = _atrasada(supabase, COMPETENCIA, "2026-08-15")
        supabase.tabelas["participantes"] = [dict(DIRETORA_DESLIGADA), dict(ADMIN_TECNICO)]
        avisos = _avisos_ao_admin(monkeypatch)
        _sem_render(monkeypatch)

        entrega = ouvidoria_relatorio.reenviar(supabase, linha["id"], AGORA)

        assert "Diretoria Executiva" in entrega.erro
        assert avisos == []


class TestDecisaoDaEstreia:
    def test_a_estreia_do_job_esta_explicada_junto_dele(self):
        """CA: a decisão fica escrita no código do job. Ela é a que mais parece
        bug para quem chega depois: no primeiro 07h após o deploy a Diretoria
        recebe uma edição fora do calendário de 1 e 16. Sem o registro ao lado
        do job, o próximo leitor "conserta" isso."""
        from app.cron import scheduler as cron

        doc = cron.enviar_relatorio_quinzenal.__doc__ or ""

        assert "estreia" in doc.lower()
        assert "deploy" in doc.lower()


class TestAvisoNaoDerrubaAEntrega:
    def test_aviso_que_levanta_nao_deixa_a_edicao_carimbada_como_entregue(self, monkeypatch, correio):
        """O aviso sai ENTRE a reivindicação e a devolução do carimbo. Se ele
        levantar (o logo do email faz `read_bytes` e some quando o PNG não está
        na imagem do container), a exceção sobe até o `try` do scheduler, o
        `_falha` não completa, e a linha fica com `enviado_em` preenchido sem
        ninguém ter recebido: some da fila para sempre e a listagem a reporta
        como entregue. É o buraco que o `_reivindicar` documenta."""
        from app.services import email_constants

        supabase = _cenario()
        supabase.tabelas["participantes"] = [dict(DIRETORA_DESLIGADA), dict(ADMIN_TECNICO)]

        def _logo_sumiu():
            raise FileNotFoundError("logo-hsm.png não está na imagem")

        monkeypatch.setattr(email_constants, "get_logo_data_uri", _logo_sumiu)
        _sem_render(monkeypatch)

        entrega = ouvidoria_relatorio.gerar_e_enviar(supabase, PERIODO, AGORA)

        assert not correio.enviados
        linha = supabase.tabelas["ouvidoria_relatorios"][0]
        assert linha["enviado_em"] is None, "a edição ficou carimbada como entregue sem ter saído"
        assert linha["tentativas"] == 1, "a tentativa não foi contada"
        assert "Diretoria Executiva" in linha["ultimo_erro"]
        assert entrega is not None and not entrega.saiu

    def test_aviso_que_levanta_nao_para_a_varredura_na_primeira_linha(self, monkeypatch, correio):
        """A varredura trata um lote. Uma exceção no aviso da primeira linha
        levaria junto as outras duas, que podiam ter saído."""
        from app.services import email_constants

        supabase = _SupabaseFake()
        supabase.tabelas["participantes"] = [dict(DIRETORA_DESLIGADA), dict(ADMIN_TECNICO)]
        _quatro_atrasadas(supabase)

        def _logo_sumiu():
            raise FileNotFoundError("logo-hsm.png não está na imagem")

        monkeypatch.setattr(email_constants, "get_logo_data_uri", _logo_sumiu)
        _sem_render(monkeypatch)

        entregas = ouvidoria_relatorio.entregar_atrasados(supabase, AGORA)

        assert len(entregas) == ouvidoria_relatorio.LOTE_DE_ATRASADOS
        tentadas = [linha for linha in supabase.tabelas["ouvidoria_relatorios"] if linha["tentativas"]]
        assert len(tentadas) == ouvidoria_relatorio.LOTE_DE_ATRASADOS


class TestDesistenciaAvisa:
    def test_a_desistencia_avisa_os_admins_tecnicos(self, monkeypatch):
        """CA da rodada de review: a desistência é o evento que nada mais
        persegue depois. Sem aviso, uma quinzena inteira deixa de chegar à
        Diretoria em definitivo e ninguém fica sabendo.

        A Diretoria está ATIVA na fixture de propósito: o aviso que sai aqui é
        o da desistência, não o do cadastro vazio."""
        supabase = _cenario()
        supabase.tabelas["participantes"] = [dict(DIRETORA), dict(ADMIN_TECNICO)]
        monkeypatch.setattr(ouvidoria_relatorio, "enviar_com_anexo", _Correio(entrega=False))
        avisos = _avisos_ao_admin(monkeypatch)
        _sem_render(monkeypatch)

        for dia in range(ouvidoria_relatorio.TETO_DE_TENTATIVAS - 1):
            ouvidoria_relatorio.gerar_e_enviar(supabase, PERIODO, AGORA + dt.timedelta(days=dia))
        assert avisos == [], "avisou antes de desistir: o job ainda ia tentar de novo"

        ouvidoria_relatorio.gerar_e_enviar(
            supabase, PERIODO, AGORA + dt.timedelta(days=ouvidoria_relatorio.TETO_DE_TENTATIVAS - 1)
        )

        assert [aviso["destinatario"] for aviso in avisos] == [ADMIN_TECNICO["email"]]
        assert COMPETENCIA in avisos[0]["texto"]
        assert "provedor de email" in avisos[0]["texto"]

    def test_a_instrucao_do_estado_terminal_sobrevive_ao_motivo_comprido(self, monkeypatch):
        """`ultimo_erro` tem 300 caracteres. Com a instrução atrás do motivo, a
        exceção comprida do render come o campo inteiro e a instrução some
        justamente na edição em que alguém precisa lê-la."""
        supabase = _cenario()

        def _weasyprint_tagarela(_registro):
            raise RuntimeError("libpango: " + "x" * 400)

        monkeypatch.setattr(ouvidoria_relatorio, "renderizar_pdf", _weasyprint_tagarela)

        for dia in range(ouvidoria_relatorio.TETO_DE_TENTATIVAS):
            ouvidoria_relatorio.gerar_e_enviar(supabase, PERIODO, AGORA + dt.timedelta(days=dia))

        linha = supabase.tabelas["ouvidoria_relatorios"][0]
        assert linha["desistido_em"] is not None
        assert "desistiu" in linha["ultimo_erro"]
        assert "reenvio" in linha["ultimo_erro"]


class TestRuidoDoAviso:
    def test_o_aviso_de_cadastro_sai_uma_vez_por_dia(self, monkeypatch, correio):
        """O cadastro vazio é um fato só. O aviso nasce por edição
        reivindicada, então uma manhã manda o mesmo email cinco vezes a cada
        super admin (as três do lote, a edição do dia e a mensal), todo dia."""
        supabase = _SupabaseFake()
        supabase.tabelas["participantes"] = [dict(DIRETORA_DESLIGADA), dict(ADMIN_TECNICO)]
        _quatro_atrasadas(supabase)
        avisos = _avisos_ao_admin(monkeypatch)
        _sem_render(monkeypatch)

        ouvidoria_relatorio.entregar_atrasados(supabase, AGORA)
        assert len(avisos) == 1, "a mesma manhã mandou o aviso do cadastro mais de uma vez"

        # O dia seguinte é outra rodada: o problema continua e o aviso volta.
        ouvidoria_relatorio.entregar_atrasados(supabase, AGORA + dt.timedelta(days=1))
        assert len(avisos) == 2
