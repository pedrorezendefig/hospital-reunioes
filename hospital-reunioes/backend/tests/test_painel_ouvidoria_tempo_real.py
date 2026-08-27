"""As duas portas que o painel em tempo real da Ouvidoria consome (issue #344).

O painel não tem rota própria: ele lê o módulo de métricas (fatia I1) para saber
o que cada área deve AGORA, e a listagem existente para saber QUAIS casos vencem
hoje e amanhã e quais críticos seguem abertos. Este arquivo cobre as duas portas
no modo exato em que o painel as chama, que é o que os testes da fatia I1 não
exercitam: ele pede o retrato de agora, sem intervalo nenhum na querystring.

Critério 5 da issue: a resposta responde por perfil (ouvidor e diretoria sim,
demais papéis não). O gate da Ouvidoria não tem bypass de super admin
(ADR 0034, decisão 8), e o pior caso é justamente ele: no contexto Reuniões o
super admin passa em tudo.
"""

from __future__ import annotations

import datetime as dt
import json
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
DIRETORIA = {
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
FACILITADOR = {
    "id": "P03",
    "nome_completo": "Ana Facilitadora",
    "access_profile": "regular",
    "perfil_ouvidoria": None,
}

# Quarta-feira, 26/08/2026, 14h de Brasília: dia útil, dentro do expediente.
AGORA = dt.datetime(2026, 8, 26, 17, 0, tzinfo=dt.UTC)
# Terça 25/08 às 17h de Brasília: o vencimento que a Recepção já rompeu.
VENCIMENTO_ROMPIDO = "2026-08-25T20:00:00+00:00"
# Quarta 26/08 às 17h de Brasília: vence hoje, ainda não rompeu.
VENCIMENTO_DE_HOJE = "2026-08-26T20:00:00+00:00"


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


def _caso(numero: int, **overrides) -> dict:
    """Uma manifestação no molde da tabela real (migrations 063 a 079)."""
    row = {
        "id": f"uuid-{numero}",
        "numero": numero,
        "protocolo": f"2026-{numero:04d}",
        "data_abertura": "2026-08-20",
        "prazo_resposta": "2026-08-27",
        "contato_em": "2026-08-20T12:00:00+00:00",
        "status": "aguardando_area",
        "categoria": "Demora no atendimento",
        "tipo_manifestacao": "reclamacao",
        "setor": "Recepcao",
        "resumo": "Paciente relata espera acima de duas horas na recepcao.",
        "conversa_id": "",
        "canal": "ana",
        "gravidade": "medio",
        "sigilo_reforcado": False,
        "prazo_area_em": VENCIMENTO_ROMPIDO,
        "prazo_rompido_em": None,
        "area_estourou_em": None,
        "validada_em": "2026-08-20T13:00:00+00:00",
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


class _TabelaFake:
    def __init__(self, nome: str, rows: list[dict]):
        self.nome = nome
        self.rows = rows
        self._filters: dict = {}
        self._in: dict = {}
        self._gte: dict = {}
        self._lte: dict = {}
        self._colunas: tuple[str, ...] | None = None

    def select(self, colunas: str = "*", *_a, **_kw):
        if colunas.strip() != "*":
            self._colunas = tuple(c.strip() for c in colunas.split(","))
        return self

    def eq(self, col, value):
        self._filters[col] = value
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

    def execute(self):
        casadas = [
            r
            for r in self.rows
            if all(r.get(c) == v for c, v in self._filters.items())
            and all(r.get(c) in v for c, v in self._in.items())
            and all(str(r.get(c) or "") >= v for c, v in self._gte.items())
            and all(str(r.get(c) or "") <= v for c, v in self._lte.items())
        ]
        if self._colunas is not None:
            casadas = [{c: r.get(c) for c in self._colunas} for r in casadas]
        else:
            casadas = [dict(r) for r in casadas]
        return type("R", (), {"data": casadas})()


class _SupabaseFake:
    def __init__(self, casos: list[dict] | None = None, **tabelas):
        self.tabelas: dict[str, list[dict]] = {
            "ouvidoria_protocolos": casos if casos is not None else [],
            "ouvidoria_prorrogacoes": [],
            "ouvidoria_setor_responsaveis": [
                {
                    "id": "resp-1",
                    "setor": "Recepcao",
                    "papel": "titular",
                    "nome": "Carlos Titular",
                    "email": "carlos@hsm.br",
                    "vigencia_inicio": "2026-01-01",
                    "vigencia_fim": None,
                }
            ],
            "ouvidoria_prazos": [
                {"gravidade": "medio", "marco": "triagem", "valor": 1, "unidade": "dias_uteis"},
                {"gravidade": "medio", "marco": "area_resposta", "valor": 4, "unidade": "dias_uteis"},
                {"gravidade": "medio", "marco": "conclusiva", "valor": 7, "unidade": "dias_uteis"},
                {"gravidade": "critico", "marco": "triagem", "valor": 0, "unidade": "horas_uteis"},
                {"gravidade": "critico", "marco": "area_resposta", "valor": 4, "unidade": "horas_uteis"},
                {"gravidade": "critico", "marco": "conclusiva", "valor": None, "unidade": "dias_uteis"},
            ],
            "ouvidoria_feriados": [],
        }
        self.tabelas.update(tabelas)

    def table(self, nome: str):
        return _TabelaFake(nome, self.tabelas.setdefault(nome, []))


def _client(monkeypatch, supabase: _SupabaseFake, participante: dict | None = OUVIDOR) -> TestClient:
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


def _retrato_de_agora(client: TestClient):
    """Como o painel pede: sem intervalo nenhum. É o retrato de agora, e não
    uma janela escolhida por quem abriu a tela."""
    return client.get("/api/ouvidoria/metricas")


class TestQuemAbreOPainel:
    """Critério 3 da issue: ouvidor e diretoria executiva acessam; demais papéis
    não veem o painel."""

    @pytest.mark.parametrize("participante", [OUVIDOR, DIRETORIA], ids=["ouvidor", "diretoria"])
    def test_os_dois_perfis_recebem_a_fila_viva_sem_pedir_periodo(self, monkeypatch, participante):
        supabase = _SupabaseFake(casos=[_caso(1)])

        resposta = _retrato_de_agora(_client(monkeypatch, supabase, participante))

        assert resposta.status_code == 200, resposta.text
        corpo = resposta.json()
        # Sem intervalo, o período é o mês corrente até hoje. A fila viva não
        # depende dele, e é ela que o painel lê.
        assert corpo["periodo"] == {"inicio": "2026-08-01", "fim": "2026-08-26"}
        assert [(a["setor"], a["pendentes"], a["vencidas"]) for a in corpo["pendencias_por_area"]] == [
            ("Recepcao", 1, 1)
        ]
        assert corpo["pendencias_por_area"][0]["responsavel"] == "Carlos Titular"
        assert corpo["pendencias_por_area"][0]["dias_uteis_de_atraso"] > 0

    @pytest.mark.parametrize(
        "participante",
        [SUPER_ADMIN, SECRETARIA, FACILITADOR, None],
        ids=["super_admin", "secretaria", "facilitador", "sem_participante"],
    )
    def test_quem_esta_fora_da_ouvidoria_nao_recebe_numero_nenhum_do_painel(self, monkeypatch, participante):
        # A fixture deixa TODAS as outras portas abertas: o super admin e a
        # secretária passam no gate da listagem (`require_acesso_painel`), então
        # é o gate da Ouvidoria, e não outra guarda, que precisa barrar aqui.
        supabase = _SupabaseFake(casos=[_caso(1), _caso(2, setor="Farmacia")])

        resposta = _retrato_de_agora(_client(monkeypatch, supabase, participante))

        assert resposta.status_code == 403, resposta.text
        # Vasculhar a resposta inteira, e não campo a campo: o que não pode
        # sair é o retrato da fila, com o nome de quem responde por ela.
        inteira = json.dumps(resposta.json(), ensure_ascii=False)
        for vazamento in ("pendencias_por_area", "Recepcao", "Farmacia", "Carlos Titular"):
            assert vazamento not in inteira, f"O 403 vazou o painel: {inteira}"

    def test_quem_esta_fora_da_ouvidoria_continua_lendo_a_listagem_que_ja_era_dele(self, monkeypatch):
        # A prova de que o teste acima barra pela porta certa: a MESMA fixture e
        # o MESMO participante passam na listagem, que é do time de Reuniões
        # inteiro (issue #292). Se o 403 viesse de uma guarda mais larga, esta
        # chamada também falharia.
        supabase = _SupabaseFake(casos=[_caso(1)])

        resposta = _client(monkeypatch, supabase, SECRETARIA).get("/api/ouvidoria/protocolos")

        assert resposta.status_code == 200, resposta.text
        assert [p["protocolo"] for p in resposta.json()["protocolos"]] == ["2026-0001"]


class TestOQueOPainelLeDeCadaPorta:
    """As duas fontes respondem perguntas diferentes, e o painel não pode
    trocá-las: a fila viva é o universo de AGORA, e a listagem é quem tem nome."""

    def test_a_fila_viva_nao_identifica_caso_nenhum(self, monkeypatch):
        # Contrato da #341: nenhum protocolo sai do módulo de métricas. O painel
        # que quiser listar caso nominalmente tem que ir à listagem.
        supabase = _SupabaseFake(casos=[_caso(1), _caso(2, setor="Farmacia", sigilo_reforcado=True)])

        corpo = _retrato_de_agora(_client(monkeypatch, supabase)).json()

        assert len(corpo["pendencias_por_area"]) == 2, corpo["pendencias_por_area"]
        for proibido in ("2026-0001", "2026-0002", "protocolo", "uuid-1"):
            assert proibido not in json.dumps(corpo["pendencias_por_area"], ensure_ascii=False)

    def test_a_fila_viva_conta_caso_aberto_fora_do_periodo_que_a_rota_devolve(self, monkeypatch):
        # O painel é de agora: o caso aberto em julho e vencido desde julho
        # precisa aparecer na cobrança da área mesmo quando o volume do mês
        # corrente é zero. Somar `pendentes` com `volume.total` somaria universos
        # diferentes, e é por isso que o painel lê os dois separados.
        supabase = _SupabaseFake(casos=[_caso(1, data_abertura="2026-07-10", contato_em="2026-07-10T12:00:00+00:00")])

        corpo = _retrato_de_agora(_client(monkeypatch, supabase)).json()

        assert corpo["volume"]["total"] == 0
        assert [(a["setor"], a["vencidas"]) for a in corpo["pendencias_por_area"]] == [("Recepcao", 1)]

    def test_a_listagem_entrega_ao_painel_o_vencimento_a_gravidade_e_o_estado(self, monkeypatch):
        # São os três campos de que a régua da tela vive: `prazo_area_em` decide
        # a janela (vence hoje, amanhã, vencido), `gravidade` separa o crítico do
        # comum e `status` para o relógio do caso que não corre mais.
        supabase = _SupabaseFake(
            casos=[
                _caso(1, gravidade="critico", prazo_area_em=VENCIMENTO_DE_HOJE),
                _caso(2, status="aguardando_manifestante", pausada_em="2026-08-24T13:00:00+00:00"),
            ]
        )

        corpo = _client(monkeypatch, _SupabaseFake(casos=supabase.tabelas["ouvidoria_protocolos"])).get(
            "/api/ouvidoria/protocolos"
        )

        por_protocolo = {p["protocolo"]: p for p in corpo.json()["protocolos"]}
        critico = por_protocolo["2026-0001"]
        assert critico["gravidade"] == "critico"
        assert critico["prazo_area_em"] == VENCIMENTO_DE_HOJE
        assert critico["prazo_estourado"] is False
        pausado = por_protocolo["2026-0002"]
        assert pausado["status"] == "aguardando_manifestante"
        # O caso parado é medido no instante em que parou: sem isso ele
        # atravessaria o próprio vencimento e o painel o mostraria vencido.
        assert pausado["prazo_estourado"] is False


class TestQuandoUmaLeituraDeApoioFalha:
    """A tela precisa distinguir "não houve o que medir" de "não consegui
    medir": o número da segunda tem cara de bom e só o `degradado` denuncia."""

    def test_o_nome_do_responsavel_some_e_a_resposta_diz_qual_leitura_falhou(self, monkeypatch):
        supabase = _SupabaseFake(casos=[_caso(1)])
        original = supabase.table

        def _sem_responsaveis(nome: str):
            if nome == "ouvidoria_setor_responsaveis":
                raise RuntimeError("responsaveis indisponivel")
            return original(nome)

        monkeypatch.setattr(supabase, "table", _sem_responsaveis)

        corpo = _retrato_de_agora(_client(monkeypatch, supabase)).json()

        assert corpo["degradado"] == ["responsaveis"]
        # Sem o aviso, este nulo seria lido como "setor sem titular cadastrado",
        # e o painel acusaria de cadastro vazio um setor que tem titular.
        assert corpo["pendencias_por_area"][0]["responsavel"] is None

    def test_o_calendario_que_nao_foi_lido_aparece_no_degradado_mesmo_com_o_numero_saindo(self, monkeypatch):
        # O pior caso do contrato: nada vem nulo. O atraso sai calculado como se
        # todo dia útil fosse trabalhado, e só esta lista denuncia.
        supabase = _SupabaseFake(casos=[_caso(1)])
        original = supabase.table

        def _sem_feriados(nome: str):
            if nome == "ouvidoria_feriados":
                raise RuntimeError("feriados indisponivel")
            return original(nome)

        monkeypatch.setattr(supabase, "table", _sem_feriados)

        corpo = _retrato_de_agora(_client(monkeypatch, supabase)).json()

        assert corpo["degradado"] == ["feriados"]
        assert corpo["pendencias_por_area"][0]["dias_uteis_de_atraso"] > 0
