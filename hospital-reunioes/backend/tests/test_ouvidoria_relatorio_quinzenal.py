"""Relatório quinzenal da Ouvidoria em PDF, agendado por email (issue #345, PRD #319).

O relatório nasce de um job nos dias 1 e 16 às 07h, sai por email à Diretoria
Executiva com o PDF anexo, fica registrado e o ouvidor consegue reenviar.

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
  - rodar duas vezes não manda dois emails;
  - só ouvidor e Diretoria Executiva acessam o registro e o reenvio.

O envio é sempre mockado: nenhum teste toca provedor de email real.
"""

from __future__ import annotations

import datetime as dt
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


class _TabelaFake:
    """Fake do PostgREST fiel no que importa: projeta o que foi pedido, filtra
    o que foi filtrado e devolve as linhas gravadas."""

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
                linha.setdefault("gerado_em", linha.get("medido_em"))
                linha.setdefault("enviado_em", None)
                linha.setdefault("destinatarios", [])
                linha.setdefault("ultimo_erro", None)
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
        if self._ordem:
            col, desc = self._ordem
            casadas = sorted(casadas, key=lambda r: str(r.get(col) or ""), reverse=desc)
        if self._limite is not None:
            casadas = casadas[: self._limite]
        return type("R", (), {"data": [self._projetar(r) for r in casadas]})()


class _SupabaseFake:
    def __init__(self, casos: list[dict] | None = None, **tabelas):
        self.indisponiveis: set[str] = set()
        self.tabelas: dict[str, list[dict]] = {
            "ouvidoria_protocolos": casos if casos is not None else [],
            "ouvidoria_prorrogacoes": [],
            "ouvidoria_setor_responsaveis": [dict(r) for r in RESPONSAVEIS],
            "ouvidoria_prazos": [dict(p) for p in PRAZOS],
            "ouvidoria_feriados": [{"data": "2026-09-07", "nome": "Independencia", "abrangencia": "nacional"}],
            "ouvidoria_relatorios": [],
            "participantes": [dict(DIRETORA)],
        }
        self.tabelas.update(tabelas)

    def table(self, nome: str):
        if nome in self.indisponiveis:
            raise APIError({"message": f"{nome} indisponivel", "code": "PGRST000"})
        return _TabelaFake(nome, self.tabelas.setdefault(nome, []))


class _Correio:
    """O provedor de email, no lugar do de verdade. Guarda o que sairia."""

    def __init__(self, entrega: bool = True):
        self.entrega = entrega
        self.enviados: list[dict] = []

    def __call__(self, destinatario, assunto, html_content, texto_fallback, anexos):
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

    def test_o_agendamento_e_a_unica_guarda_de_quando_o_relatorio_sai(self, monkeypatch):
        """Dias 1 e 16 às 07h estão no cron, e em nenhum outro lugar: uma
        guarda só, para desligá-la deixar teste vermelho."""
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
        assert job["day"] == "1,16"
        assert job["hour"] == 7
        assert job["minute"] == 0

    def test_falha_do_relatorio_nao_derruba_os_outros_jobs(self, monkeypatch, caplog):
        """O job novo entra na mesma disciplina dos vizinhos: exceção vira log,
        não sobe para o scheduler e leva a rodada inteira junto."""
        from app.cron import scheduler as cron

        def _banco_fora(*_a, **_kw):
            raise RuntimeError("banco fora do ar")

        monkeypatch.setattr(cron, "_supabase", _banco_fora)

        cron.enviar_relatorio_quinzenal()

        assert "enviar_relatorio_quinzenal" in caplog.text


# ═══════════════════════════════════════════════════════════════════════════
# O PDF
# ═══════════════════════════════════════════════════════════════════════════


class TestConteudoDoPdf:
    def test_html_traz_as_secoes_e_os_numeros_das_metricas(self, correio):
        """CA: o PDF renderiza com as seções e os números do módulo de métricas."""
        supabase = _cenario()
        registro = ouvidoria_relatorio.gerar_e_enviar(supabase, PERIODO, AGORA)

        html = ouvidoria_relatorio.montar_html(supabase.tabelas["ouvidoria_relatorios"][0])

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
        # 43 manifestações no período, das quais 40 pelo canal aberto.
        assert ">43<" in html
        assert registro is not None

    def test_ranking_sai_com_o_denominador_de_quem_foi_classificado(self, correio):
        """O topo sem denominador apresenta ausência de medição como medição:
        "Recepção (3)" ao lado de "43 manifestações" lê como 3 de 43."""
        supabase = _cenario()
        ouvidoria_relatorio.gerar_e_enviar(supabase, PERIODO, AGORA)

        html = ouvidoria_relatorio.montar_html(supabase.tabelas["ouvidoria_relatorios"][0])

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

    def test_fila_de_pendencias_sai_carimbada_com_o_instante_da_medicao(self, correio):
        """`pendencias_por_area` tem universo próprio e não tem recorte de
        data: é sempre a fila de HOJE. Sem o carimbo, o leitor de um relatório
        de agosto soma essa fila ao volume de agosto, e são universos
        diferentes."""
        supabase = _SupabaseFake(casos=[_caso(1), _pendente(2)])
        ouvidoria_relatorio.gerar_e_enviar(supabase, PERIODO, AGORA)

        html = ouvidoria_relatorio.montar_html(supabase.tabelas["ouvidoria_relatorios"][0])

        assert "Fila medida em 16/08/2026 às 07h00" in html
        assert "não se soma ao volume do período" in html
        assert "Carlos Titular" in html

    def test_pdf_nao_carrega_protocolo_de_manifestacao_nenhuma(self, correio):
        """RN-40 e ADR 0034 decisão 8: este PDF sai do hospital por email, e um
        protocolo de denúncia sigilosa cruzado com o email de acionamento
        identificaria o caso."""
        sigilosa = _caso(42, tipo_manifestacao="denuncia", sigilo_reforcado=True)
        assert sigilosa["protocolo"] == PROTOCOLO_SIGILOSO
        supabase = _SupabaseFake(casos=[sigilosa, _pendente(2)])
        ouvidoria_relatorio.gerar_e_enviar(supabase, PERIODO, AGORA)

        html = ouvidoria_relatorio.montar_html(supabase.tabelas["ouvidoria_relatorios"][0])

        assert PROTOCOLO_SIGILOSO not in html
        assert "uuid-42" not in html
        assert correio.enviados
        assert PROTOCOLO_SIGILOSO not in correio.enviados[0]["html"]

    def test_pdf_nao_usa_travessao_nem_meia_risca(self, correio):
        """ADR 0013: o hífen entra em compostos, o travessão não entra em nada
        que o usuário lê."""
        supabase = _cenario()
        ouvidoria_relatorio.gerar_e_enviar(supabase, PERIODO, AGORA)

        html = ouvidoria_relatorio.montar_html(supabase.tabelas["ouvidoria_relatorios"][0])

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
        "prazo": {
            "trechos": [
                {
                    "trecho": "triagem",
                    "de": "T0",
                    "ate": "T1",
                    "responsavel": "ouvidoria",
                    "medidos": 2,
                    "cumpridos": 2,
                    "estourados": 0,
                    "em_andamento": 0,
                    "sem_prazo": 1,
                    "percentual_cumprido": 100.0,
                }
            ]
        },
        "pendencias_por_area": [
            {
                "setor": "Recepcao",
                "responsavel": "Carlos Titular",
                "pendentes": 1,
                "vencidas": 1,
                "dias_uteis_de_atraso": 2.0,
            }
        ],
        "ranking_areas": [
            {"setor": "Recepcao", "respondidas": 1, "minutos_uteis_medios": 480, "dias_uteis_medios": 1.0}
        ],
        "prorrogacao": {"casos": 0, "com_a_area": 1, "taxa_pct": 0.0, "por_area": []},
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
    for campo in ("top_temas", "top_areas", "prorrogacao", "reincidencia"):
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
        "destinatarios": [],
        "ultimo_erro": None,
    }


class TestRenderReal:
    """WeasyPrint e o template de verdade, sem mock: o PDF precisa sair."""

    def test_gera_pdf_de_verdade(self, correio):
        supabase = _cenario()
        ouvidoria_relatorio.gerar_e_enviar(supabase, PERIODO, AGORA)

        pdf = ouvidoria_relatorio.renderizar_pdf(supabase.tabelas["ouvidoria_relatorios"][0])

        assert pdf.startswith(b"%PDF")
        assert len(pdf) > 1000

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

        registro = ouvidoria_relatorio.gerar_e_enviar(supabase, PERIODO, AGORA)

        assert len(correio.enviados) == 1
        enviado = correio.enviados[0]
        assert enviado["destinatario"] == "helena@hsm.br"
        assert "01/08/2026 a 15/08/2026" in enviado["assunto"]
        nome, conteudo = enviado["anexos"][0]
        assert nome == f"relatorio-ouvidoria-{COMPETENCIA}.pdf"
        assert conteudo.startswith(b"%PDF")
        assert registro["enviado_em"] == AGORA.isoformat()
        assert registro["destinatarios"] == ["helena@hsm.br"]

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

        assert primeira["enviado_em"] is None
        assert primeira["ultimo_erro"] == "O provedor de email recusou a mensagem"

        aceita = _Correio(entrega=True)
        monkeypatch.setattr(ouvidoria_relatorio, "enviar_com_anexo", aceita)
        segunda = ouvidoria_relatorio.gerar_e_enviar(supabase, PERIODO, AGORA + dt.timedelta(hours=1))

        assert len(aceita.enviados) == 1
        assert segunda["enviado_em"] is not None
        assert segunda["ultimo_erro"] is None
        assert len(supabase.tabelas["ouvidoria_relatorios"]) == 1
        # Os números são os da primeira medição: o retrato é do instante em que
        # foi tirado, e não do dia em que o email conseguiu sair.
        assert supabase.tabelas["ouvidoria_relatorios"][0]["medido_em"] == AGORA.isoformat()

    def test_sem_diretoria_cadastrada_o_relatorio_fica_registrado_com_o_motivo(self, correio):
        """Ninguém com o perfil não é o mesmo que email entregue: o relatório
        existe, ninguém recebeu, e o registro diz por quê."""
        supabase = _cenario()
        supabase.tabelas["participantes"] = []

        registro = ouvidoria_relatorio.gerar_e_enviar(supabase, PERIODO, AGORA)

        assert not correio.enviados
        assert registro["enviado_em"] is None
        assert "Diretoria Executiva" in registro["ultimo_erro"]

    def test_falha_ao_ler_a_diretoria_nao_vira_relatorio_enviado(self, correio):
        """Leitura que falhou e lista vazia são coisas diferentes: um timeout
        não pode carimbar a edição como entregue."""
        supabase = _cenario()
        supabase.indisponiveis.add("participantes")

        registro = ouvidoria_relatorio.gerar_e_enviar(supabase, PERIODO, AGORA)

        assert not correio.enviados
        assert registro["enviado_em"] is None
        assert "ler quem é a Diretoria Executiva" in registro["ultimo_erro"]


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

    def test_reenvio_mostra_os_numeros_congelados_e_nao_os_de_hoje(self, monkeypatch, correio):
        """A fila de pendências não tem recorte de data: ela é sempre a de
        hoje. Um relatório de agosto reenviado em setembro precisa carregar a
        fila de agosto, e não a que cresceu depois.

        A asserção é sobre o que foi PARA o PDF que saiu, e não sobre a linha
        guardada no banco: é o papel que chega à Diretoria que importa, e é ele
        que uma remedição no reenvio estragaria."""
        supabase = _SupabaseFake(casos=[_caso(1), _pendente(2)])
        impressos: list[dict] = []
        renderizar = ouvidoria_relatorio.renderizar_pdf
        monkeypatch.setattr(
            ouvidoria_relatorio,
            "renderizar_pdf",
            lambda registro: (impressos.append(registro), renderizar(registro))[1],
        )
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

    def test_reenvio_de_relatorio_inexistente_da_404(self, monkeypatch, correio):
        client = _client(monkeypatch, _cenario(), OUVIDOR)

        res = client.post("/api/ouvidoria/relatorios/rel-que-nao-existe/reenvio")

        assert res.status_code == 404
        assert not correio.enviados


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
