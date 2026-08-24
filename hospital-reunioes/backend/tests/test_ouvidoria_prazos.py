"""Motor de prazos da Ouvidoria em calendário útil (issue #322, ADR 0034 decisão 6).

O motor é função pura: recebe o instante de início, o prazo da gravidade e a
lista de feriados, e devolve vencimento e rótulo. Não lê banco, não olha o
relógio por conta própria. Estes testes exercitam esse seam direto, como pede
a seção "Decisões de teste" do PRD #317.

Datas escritas no fuso America/Sao_Paulo, que é o do expediente; o motor
devolve em UTC, que é como o prazo é persistido.
"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

FUSO = ZoneInfo("America/Sao_Paulo")

SEM_FERIADO: frozenset[date] = frozenset()


def _sp(ano: int, mes: int, dia: int, hora: int = 0, minuto: int = 0) -> datetime:
    return datetime(ano, mes, dia, hora, minuto, tzinfo=FUSO)


class TestContagemEmDiasUteis:
    """Dia útil não conta o dia do fato: a contagem abre no expediente
    seguinte e o prazo vence no fim do expediente do enésimo dia."""

    def test_dois_dias_uteis_a_partir_de_sexta_16h50_vencem_terca_as_17h(self):
        """Critério de aceite da #322, na letra: caso validado sexta 16h50 com
        prazo de 2 dias úteis vence terça às 17h, porque a contagem só abre
        segunda às 08h."""
        from app.services.ouvidoria_prazos import Prazo, calcular_vencimento

        vencimento = calcular_vencimento(_sp(2026, 8, 21, 16, 50), Prazo(2, "dias_uteis"), SEM_FERIADO)

        assert vencimento == _sp(2026, 8, 25, 17, 0)


class TestFeriadoAdministravel:
    """Feriado cadastrado sai do calendário útil; tirado da tabela, o dia volta
    a contar. O motor não tem feriado embutido: recebe o conjunto pronto."""

    # Quinta, 23/04/2026: São Jorge, feriado estadual do Rio de Janeiro.
    SAO_JORGE = date(2026, 4, 23)

    def test_feriado_cadastrado_empurra_o_vencimento(self):
        from app.services.ouvidoria_prazos import Prazo, calcular_vencimento

        # Quarta-feira: a contagem abriria na quinta, mas ela é feriado.
        vencimento = calcular_vencimento(_sp(2026, 4, 22, 10, 0), Prazo(2, "dias_uteis"), frozenset({self.SAO_JORGE}))

        assert vencimento == _sp(2026, 4, 27, 17, 0), "Feriado do RJ contou como dia útil"

    def test_feriado_removido_volta_a_contar(self):
        from app.services.ouvidoria_prazos import Prazo, calcular_vencimento

        vencimento = calcular_vencimento(_sp(2026, 4, 22, 10, 0), Prazo(2, "dias_uteis"), SEM_FERIADO)

        assert vencimento == _sp(2026, 4, 24, 17, 0)


class TestContagemEmHorasUteis:
    """Gravidade crítica trabalha em horas úteis (4h para a área responder):
    o relógio anda dentro do expediente e para às 17h."""

    def test_quatro_horas_uteis_no_meio_da_tarde_viram_a_manha_seguinte(self):
        from app.services.ouvidoria_prazos import Prazo, calcular_vencimento

        # Segunda 15h: sobram 2h de expediente, as outras 2h caem na terça.
        vencimento = calcular_vencimento(_sp(2026, 8, 24, 15, 0), Prazo(4, "horas_uteis"), SEM_FERIADO)

        assert vencimento == _sp(2026, 8, 25, 10, 0)

    def test_entrada_fora_do_expediente_conta_da_proxima_abertura(self):
        """RN-23: manifestação de sábado à noite não consome prazo de
        madrugada; a contagem abre segunda às 08h."""
        from app.services.ouvidoria_prazos import Prazo, calcular_vencimento

        vencimento = calcular_vencimento(_sp(2026, 8, 22, 22, 0), Prazo(4, "horas_uteis"), SEM_FERIADO)

        assert vencimento == _sp(2026, 8, 24, 12, 0)


class TestPrazoImediato:
    """Triagem de caso crítico é "imediato" na spec, ou seja, prazo zero. A
    tela deixa a Diretoria digitar zero em qualquer unidade, e zero significa
    a mesma coisa nas duas."""

    @pytest.mark.parametrize("unidade", ["horas_uteis", "dias_uteis"])
    def test_prazo_zero_vence_na_abertura_da_contagem(self, unidade):
        from app.services.ouvidoria_prazos import Prazo, calcular_vencimento

        vencimento = calcular_vencimento(_sp(2026, 8, 24, 15, 0), Prazo(0, unidade), SEM_FERIADO)

        assert vencimento == _sp(2026, 8, 24, 15, 0)


class TestViradaDeMes:
    """A contagem atravessa a virada de mês sem tropeçar no calendário."""

    def test_dois_dias_uteis_na_ultima_segunda_de_agosto_vencem_em_setembro(self):
        from app.services.ouvidoria_prazos import Prazo, calcular_vencimento

        vencimento = calcular_vencimento(_sp(2026, 8, 31, 9, 0), Prazo(2, "dias_uteis"), SEM_FERIADO)

        assert vencimento == _sp(2026, 9, 2, 17, 0)


class TestRotuloEmLinguagemNatural:
    """O que o painel e o email do setor exibem (RN-35): contagem regressiva
    em português, na mesma unidade em que o prazo foi combinado."""

    def test_logo_apos_a_validacao_o_rotulo_repete_o_prazo_combinado(self):
        from app.services.ouvidoria_prazos import rotular_vencimento

        # Validada sexta 16h50 com 2 dias úteis: o vencimento é terça 17h.
        rotulo = rotular_vencimento(_sp(2026, 8, 25, 17, 0), _sp(2026, 8, 21, 16, 50), SEM_FERIADO)

        assert rotulo == "vence em 2 dias úteis"

    def test_ultimo_dia_fala_no_singular(self):
        from app.services.ouvidoria_prazos import rotular_vencimento

        rotulo = rotular_vencimento(_sp(2026, 8, 25, 17, 0), _sp(2026, 8, 24, 9, 0), SEM_FERIADO)

        assert rotulo == "vence em 1 dia útil"

    def test_prazo_curto_de_critico_e_dito_em_horas(self):
        from app.services.ouvidoria_prazos import rotular_vencimento

        rotulo = rotular_vencimento(_sp(2026, 8, 24, 13, 0), _sp(2026, 8, 24, 9, 0), SEM_FERIADO)

        assert rotulo == "vence em 4 horas úteis"

    def test_prazo_estourado_diz_ha_quanto_tempo(self):
        from app.services.ouvidoria_prazos import rotular_vencimento

        # Vencia terça 17h; agora é quarta 10h, ou seja, 2h de expediente depois.
        rotulo = rotular_vencimento(_sp(2026, 8, 25, 17, 0), _sp(2026, 8, 26, 10, 0), SEM_FERIADO)

        assert rotulo == "vencido há 2 horas úteis"

    def test_gravidade_sem_prazo_nao_finge_contagem(self):
        """Crítico não tem prazo conclusivo fixo e baixo não passa pela área:
        nesses casos o motor devolve vencimento None e o rótulo diz isso."""
        from app.services.ouvidoria_prazos import rotular_vencimento

        assert rotular_vencimento(None, _sp(2026, 8, 24, 9, 0), SEM_FERIADO) == "sem prazo definido"


class TestEstouro:
    """O que o job de cobrança (#327) e o destaque do painel perguntam."""

    def test_antes_do_vencimento_nao_esta_estourado(self):
        from app.services.ouvidoria_prazos import esta_vencido

        assert esta_vencido(_sp(2026, 8, 25, 17, 0), _sp(2026, 8, 25, 16, 59)) is False

    def test_no_instante_do_vencimento_ja_esta_estourado(self):
        from app.services.ouvidoria_prazos import esta_vencido

        assert esta_vencido(_sp(2026, 8, 25, 17, 0), _sp(2026, 8, 25, 17, 0)) is True

    def test_caso_sem_prazo_nunca_estoura(self):
        from app.services.ouvidoria_prazos import esta_vencido

        assert esta_vencido(None, _sp(2027, 1, 1, 12, 0)) is False


import os  # noqa: E402
import sys  # noqa: E402

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from slowapi import _rate_limit_exceeded_handler  # noqa: E402
from slowapi.errors import RateLimitExceeded  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.dependencies import get_current_user, get_supabase_client  # noqa: E402
from app.limiter import limiter  # noqa: E402
from app.middleware.request_context import RequestContextMiddleware  # noqa: E402
from app.routers import ouvidoria as ouvidoria_router  # noqa: E402

OUVIDOR = {"id": "P10", "nome_completo": "Marta Ouvidora", "access_profile": None, "perfil_ouvidoria": "ouvidor"}
DIRETORIA = {
    "id": "P11",
    "nome_completo": "Dr. Diretor",
    "access_profile": "regular",
    "perfil_ouvidoria": "diretoria_executiva",
}
SECRETARIA = {"id": "P02", "nome_completo": "Sofia Secretaria", "access_profile": "secretaria"}
SUPER_ADMIN = {"id": "P03", "nome_completo": "Pedro Admin", "access_profile": "super_admin"}

# Recorte da tabela da especificação da Diretoria (seção 7.2) que o motor usa.
SEED_DA_SPEC = [
    {"gravidade": "critico", "marco": "area_resposta", "valor": 4, "unidade": "horas_uteis"},
    {"gravidade": "alto", "marco": "area_resposta", "valor": 2, "unidade": "dias_uteis"},
    {"gravidade": "medio", "marco": "area_resposta", "valor": 4, "unidade": "dias_uteis"},
    {"gravidade": "baixo", "marco": "area_resposta", "valor": None, "unidade": "dias_uteis"},
]


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


class _TabelaFake:
    """Fake do PostgREST no que importa: filtros, projeção do select, insert,
    update e delete. Mesmo espírito do fake de test_ouvidoria_manifestacao."""

    def __init__(self, rows: list[dict]):
        self.rows = rows
        self._filters: dict = {}
        self._insert: dict | list | None = None
        self._update: dict | None = None
        self._delete = False
        self._colunas: tuple[str, ...] | None = None

    def select(self, colunas: str = "*", *_a, **_kw):
        if colunas.strip() != "*":
            self._colunas = tuple(c.strip() for c in colunas.split(","))
        return self

    def _projetar(self, row: dict) -> dict:
        return dict(row) if self._colunas is None else {c: row.get(c) for c in self._colunas}

    def insert(self, payload):
        self._insert = payload
        return self

    def upsert(self, payload, **_kw):
        self._insert = payload
        return self

    def update(self, payload: dict):
        self._update = payload
        return self

    def delete(self):
        self._delete = True
        return self

    def eq(self, col, value):
        self._filters[col] = value
        return self

    def order(self, col, desc=False):
        self.rows = sorted(self.rows, key=lambda r: (r[col] is None, r[col]), reverse=desc)
        return self

    def execute(self):
        if self._insert is not None:
            novos = self._insert if isinstance(self._insert, list) else [self._insert]
            self.rows.extend(dict(n) for n in novos)
            return type("R", (), {"data": [dict(n) for n in novos]})()
        casadas = [r for r in self.rows if all(r.get(c) == v for c, v in self._filters.items())]
        if self._delete:
            for r in casadas:
                self.rows.remove(r)
            return type("R", (), {"data": [dict(r) for r in casadas]})()
        if self._update is not None:
            for r in casadas:
                r.update(self._update)
        return type("R", (), {"data": [self._projetar(r) for r in casadas]})()


class _SupabaseFake:
    def __init__(self, tabelas: dict[str, list[dict]]):
        self.tabelas = tabelas

    def table(self, nome: str):
        return _TabelaFake(self.tabelas.setdefault(nome, []))


def _prazos_semeados() -> list[dict]:
    return [dict(linha) for linha in SEED_DA_SPEC]


def _client(monkeypatch, participante: dict | None, **tabelas):
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(RequestContextMiddleware)
    app.include_router(ouvidoria_router.router, prefix="/api")

    supabase = _SupabaseFake(
        {
            "ouvidoria_prazos": tabelas.get("prazos", _prazos_semeados()),
            "ouvidoria_prazos_historico": tabelas.get("historico", []),
            "ouvidoria_feriados": tabelas.get("feriados", []),
            "ouvidoria_protocolos": tabelas.get("protocolos", []),
            "ouvidoria_acessos": [],
        }
    )

    async def _fake_participante(_user, _sb, fields=None):
        return participante

    monkeypatch.setattr(ouvidoria_router, "get_participante_for_user", _fake_participante)
    app.dependency_overrides[get_current_user] = lambda: {"id": "u1", "email": "u@hsm.br"}
    app.dependency_overrides[get_supabase_client] = lambda: supabase
    return TestClient(app), supabase


class TestLeituraDaTabelaDePrazos:
    """A tabela de prazos é a fonte do motor: quem trabalha na Ouvidoria
    precisa vê-la para saber o prazo de cada gravidade."""

    @pytest.mark.parametrize("perfil", [OUVIDOR, DIRETORIA])
    def test_perfil_da_ouvidoria_le_a_tabela(self, monkeypatch, perfil):
        client, _ = _client(monkeypatch, perfil)

        r = client.get("/api/ouvidoria/prazos")

        assert r.status_code == 200
        celulas = {(p["gravidade"], p["marco"]): p for p in r.json()["prazos"]}
        assert celulas[("alto", "area_resposta")]["valor"] == 2
        assert celulas[("alto", "area_resposta")]["unidade"] == "dias_uteis"

    def test_papel_de_reunioes_nao_le_a_tabela(self, monkeypatch):
        client, _ = _client(monkeypatch, SECRETARIA)

        assert client.get("/api/ouvidoria/prazos").status_code == 403


class TestEdicaoPelaDiretoria:
    """RN-21: só a diretoria executiva edita, e toda edição deixa histórico."""

    def test_diretoria_edita_um_prazo_e_a_mudanca_vale(self, monkeypatch):
        client, supabase = _client(monkeypatch, DIRETORIA)

        r = client.put("/api/ouvidoria/prazos/alto/area_resposta", json={"valor": 3, "unidade": "dias_uteis"})

        assert r.status_code == 200
        assert r.json()["valor"] == 3
        vigente = next(
            p for p in supabase.tabelas["ouvidoria_prazos"] if (p["gravidade"], p["marco"]) == ("alto", "area_resposta")
        )
        assert vigente["valor"] == 3, "A edição não passou a valer para validação nova"

    def test_edicao_registra_de_que_para_que_e_quem_mudou(self, monkeypatch):
        client, supabase = _client(monkeypatch, DIRETORIA)

        client.put("/api/ouvidoria/prazos/alto/area_resposta", json={"valor": 3, "unidade": "dias_uteis"})

        historico = supabase.tabelas["ouvidoria_prazos_historico"]
        assert len(historico) == 1
        registro = historico[0]
        assert registro["valor_anterior"] == 2
        assert registro["valor_novo"] == 3
        assert registro["autor_id"] == DIRETORIA["id"]
        assert registro["autor_nome"] == DIRETORIA["nome_completo"]

    @pytest.mark.parametrize("papel", [OUVIDOR, SECRETARIA, SUPER_ADMIN])
    def test_quem_nao_e_diretoria_nao_edita(self, monkeypatch, papel):
        """O ouvidor entra nesta lista de propósito: ele usa o prazo, quem
        define é a Diretoria (RN-21)."""
        client, supabase = _client(monkeypatch, papel)

        r = client.put("/api/ouvidoria/prazos/alto/area_resposta", json={"valor": 9, "unidade": "dias_uteis"})

        assert r.status_code == 403
        assert supabase.tabelas["ouvidoria_prazos_historico"] == []

    def test_caso_ja_despachado_mantem_o_prazo_que_o_setor_recebeu(self, monkeypatch):
        """Critério de aceite da #322: a edição vale para validação nova; caso
        já despachado não é recalculado."""
        despachada = {
            "id": "uuid-7",
            "status": "aguardando_area",
            "gravidade": "alto",
            "prazo_area_em": "2026-08-25T20:00:00+00:00",
        }
        client, supabase = _client(monkeypatch, DIRETORIA, protocolos=[despachada])

        client.put("/api/ouvidoria/prazos/alto/area_resposta", json={"valor": 9, "unidade": "dias_uteis"})

        assert supabase.tabelas["ouvidoria_protocolos"][0]["prazo_area_em"] == "2026-08-25T20:00:00+00:00"


class TestFeriadosAdministraveis:
    """RN-22: a lista de feriados é tabela, não constante do código. Quem
    administra é a Diretoria Executiva, como na tabela de prazos."""

    SAO_JORGE = {"data": "2026-04-23", "nome": "Sao Jorge", "abrangencia": "estadual_rj"}

    def test_perfil_da_ouvidoria_le_os_feriados(self, monkeypatch):
        client, _ = _client(monkeypatch, OUVIDOR, feriados=[dict(self.SAO_JORGE)])

        r = client.get("/api/ouvidoria/feriados")

        assert r.status_code == 200
        assert r.json()["feriados"][0]["data"] == "2026-04-23"

    def test_diretoria_cadastra_feriado(self, monkeypatch):
        client, supabase = _client(monkeypatch, DIRETORIA, feriados=[])

        r = client.post("/api/ouvidoria/feriados", json=self.SAO_JORGE)

        assert r.status_code == 201
        assert supabase.tabelas["ouvidoria_feriados"][0]["nome"] == "Sao Jorge"

    def test_diretoria_remove_feriado(self, monkeypatch):
        client, supabase = _client(monkeypatch, DIRETORIA, feriados=[dict(self.SAO_JORGE)])

        r = client.delete("/api/ouvidoria/feriados/2026-04-23")

        assert r.status_code == 204
        assert supabase.tabelas["ouvidoria_feriados"] == []

    @pytest.mark.parametrize("papel", [OUVIDOR, SECRETARIA, SUPER_ADMIN])
    def test_quem_nao_e_diretoria_nao_mexe_no_calendario(self, monkeypatch, papel):
        client, supabase = _client(monkeypatch, papel, feriados=[dict(self.SAO_JORGE)])

        assert client.post("/api/ouvidoria/feriados", json={**self.SAO_JORGE, "data": "2026-05-05"}).status_code == 403
        assert client.delete("/api/ouvidoria/feriados/2026-04-23").status_code == 403
        assert len(supabase.tabelas["ouvidoria_feriados"]) == 1


def _indice(protocolo: str, **overrides) -> dict:
    row = {
        "id": f"uuid-{protocolo}",
        "numero": 7,
        "protocolo": protocolo,
        "data_abertura": "2026-08-14",
        "prazo_resposta": "2026-08-21",
        "status": "aguardando_area",
        "categoria": "Demora",
        "setor": "Recepcao",
        "resumo": "Paciente relata espera acima de duas horas.",
        "conversa_id": "conv-4711",
        "sigilo_reforcado": False,
        "gravidade": "alto",
        "prazo_area_em": None,
    }
    row.update(overrides)
    return row


class TestPainelUsaOMotorNovo:
    """Critério de aceite da #322: o painel mostra o prazo calculado e o
    rótulo "vence em X", em vez do prazo de 7 dias corridos da fundação."""

    def test_caso_com_prazo_vencido_vem_marcado_como_estourado(self, monkeypatch):
        vencida = _indice("2026-0007", prazo_area_em="2020-01-06T20:00:00+00:00")
        client, _ = _client(monkeypatch, OUVIDOR, protocolos=[vencida])

        item = client.get("/api/ouvidoria/protocolos").json()["protocolos"][0]

        assert item["prazo_estourado"] is True
        assert item["rotulo_prazo"].startswith("vencido há"), item["rotulo_prazo"]

    def test_caso_dentro_do_prazo_traz_a_contagem_regressiva(self, monkeypatch):
        no_prazo = _indice("2026-0008", prazo_area_em="2099-01-06T20:00:00+00:00")
        client, _ = _client(monkeypatch, OUVIDOR, protocolos=[no_prazo])

        item = client.get("/api/ouvidoria/protocolos").json()["protocolos"][0]

        assert item["prazo_estourado"] is False
        assert item["rotulo_prazo"].startswith("vence em"), item["rotulo_prazo"]

    def test_caso_ainda_sem_gravidade_nao_finge_prazo(self, monkeypatch):
        """Enquanto o ouvidor não classifica, não existe prazo da área: o
        painel diz isso em vez de inventar uma data."""
        sem_classificacao = _indice("2026-0009", gravidade=None, status="em_classificacao")
        client, _ = _client(monkeypatch, OUVIDOR, protocolos=[sem_classificacao])

        item = client.get("/api/ouvidoria/protocolos").json()["protocolos"][0]

        assert item["gravidade"] is None
        assert item["prazo_area_em"] is None
        assert item["prazo_estourado"] is False
        assert item["rotulo_prazo"] == "sem prazo definido"

    def test_indice_do_painel_nao_vaza_campo_do_dossie(self, monkeypatch):
        """O prazo novo entra no índice; relato e identificação continuam
        atrás do perfil da Ouvidoria (ADR 0034, decisão 8)."""
        com_dossie = _indice("2026-0010", relato_integral="Relato inteiro", manifestante_nome="Joana")
        client, _ = _client(monkeypatch, SECRETARIA, protocolos=[com_dossie])

        item = client.get("/api/ouvidoria/protocolos").json()["protocolos"][0]

        assert item["gravidade"] == "alto"
        for campo in ("relato_integral", "manifestante_nome", "sigilo_reforcado"):
            assert campo not in item, f"Campo do Dossiê vazou no índice: {campo}"


class TestMigracaoDoMotorDePrazos:
    """A migration é o contrato de dados do motor: seed da spec, histórico
    append-only e RLS default-deny (padrão da casa)."""

    MIGRATION = "065_ouvidoria_prazos_calendario.sql"

    def _ddl(self) -> str:
        caminho = os.path.join(os.path.dirname(__file__), "..", "..", "supabase", "migrations", self.MIGRATION)
        with open(caminho, encoding="utf-8") as f:
            return f.read()

    @pytest.mark.parametrize("celula", SEED_DA_SPEC)
    def test_seed_traz_os_valores_da_especificacao_da_diretoria(self, celula):
        """Seção 7.2 da especificação de 19/08/2026, coluna "Área responde"."""
        ddl = self._ddl()
        valor = "NULL" if celula["valor"] is None else str(celula["valor"])
        esperado = f"('{celula['gravidade']}', '{celula['marco']}', {valor},"
        linha = next((ln for ln in (" ".join(bruta.split()) for bruta in ddl.splitlines()) if esperado in ln), None)
        assert linha is not None, f"Seed ausente ou diferente da spec: {celula}"
        assert celula["unidade"] in linha, f"Unidade do seed diverge da spec: {celula}"

    def test_historico_de_prazo_e_append_only(self):
        ddl = self._ddl().lower()
        assert "trg_ouvidoria_prazos_historico_sem_update" in ddl
        assert "trg_ouvidoria_prazos_historico_sem_delete" in ddl

    @pytest.mark.parametrize("tabela", ["ouvidoria_prazos", "ouvidoria_prazos_historico", "ouvidoria_feriados"])
    def test_tabela_nova_nasce_com_rls(self, tabela):
        ddl = self._ddl().lower()
        assert f"alter table {tabela} enable row level security" in ddl, (
            f"Tabela {tabela} sem RLS default-deny (padrão da casa: 009/041/051/063/064)"
        )

    def test_migration_e_idempotente(self):
        ddl = self._ddl().lower()
        assert ddl.count("create table if not exists") == 3
        assert "on conflict" in ddl, "Rodar a migration duas vezes duplicaria o seed"
