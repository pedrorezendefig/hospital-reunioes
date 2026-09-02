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

from app.config import settings  # noqa: E402
from app.dependencies import get_current_user, get_supabase_client  # noqa: E402
from app.limiter import limiter  # noqa: E402
from app.middleware.request_context import RequestContextMiddleware  # noqa: E402
from app.middleware.sem_cache import SemCacheMiddleware, prefixos_sem_cache  # noqa: E402
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

    def range(self, inicio, fim):
        """O recorte de página do PostgREST (issue #430): as leituras integrais
        da Ouvidoria passaram a pedir a resposta em janelas."""
        self._janela = (inicio, fim)
        return self

    def execute(self):
        resposta = self._executar()
        dados = resposta.data or []
        inicio, fim = getattr(self, "_janela", None) or (0, len(dados))
        return type("R", (), {"data": dados[inicio : fim + 1]})()

    def _executar(self):
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


class _AgregadoFake:
    """A leitura da função `ouvidoria_ultimo_movimento` do jeito que a rota a
    faz: em páginas (`ler_tudo`) e com ordem estável. O recorte recorta de
    verdade, senão o laço de paginação giraria até o teto de páginas."""

    def __init__(self, linhas: list[dict]):
        self._linhas = sorted(linhas, key=lambda linha: linha["manifestacao_id"])

    def order(self, *_a, **_kw):
        return self

    def range(self, inicio: int, fim: int):
        return _AgregadoFake(self._linhas[inicio : fim + 1])

    def execute(self):
        return type("R", (), {"data": [dict(linha) for linha in self._linhas]})()


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

    def rpc(self, nome: str, _params: dict):
        """Efeito da função `ouvidoria_ultimo_movimento` (migration 092, issue
        #484): o instante do movimento mais recente de cada caso, agregado da
        trilha. É o outro lado da comparação que acende o ponto de novidade na
        fila do ouvidor."""
        assert nome == "ouvidoria_ultimo_movimento", f"RPC inesperada: {nome}"
        ultimo: dict[str, str] = {}
        for mov in self.tabelas.get("ouvidoria_movimentos", []):
            quando = mov.get("ocorrido_em")
            if quando is None:
                continue
            caso = str(mov["manifestacao_id"])
            ultimo[caso] = max(str(quando), ultimo.get(caso, ""))
        agregado = [{"manifestacao_id": c, "ultimo_movimento_em": q} for c, q in ultimo.items()]
        return _AgregadoFake(agregado)


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

    def test_a_listagem_entrega_o_prazo_de_referencia_do_caso_ainda_nao_triado(self, monkeypatch):
        # A fila de triagem é a única do painel sem `prazo_area_em`: ele só nasce
        # quando o ouvidor valida e aciona a área. Sem `prazo_resposta` na
        # resposta, cinco casos parados desde segunda não seriam cobrados por
        # bloco nenhum na sexta, e o atraso é da própria Ouvidoria.
        supabase = _SupabaseFake(
            casos=[
                _caso(
                    1,
                    status="novo",
                    gravidade=None,
                    prazo_area_em=None,
                    validada_em=None,
                    prazo_resposta="2026-08-26",
                )
            ]
        )

        corpo = _client(monkeypatch, supabase).get("/api/ouvidoria/protocolos").json()

        linha = corpo["protocolos"][0]
        assert linha["prazo_area_em"] is None
        assert linha["prazo_resposta"] == "2026-08-26"
        # Vencimento da área ausente não é vencimento estourado: quem decide a
        # janela desse caso é o prazo de referência, não este campo.
        assert linha["prazo_estourado"] is False

    def test_a_listagem_entrega_a_marca_de_sigilo_do_caso(self, monkeypatch):
        # A denúncia sigilosa é candidata natural a crítica e cai no bloco de
        # destaque, com protocolo, setor e resumo. Sem esta coluna a tela não tem
        # como distingui-la de uma reclamação de fila (RN-40, ADR 0034 decisão 8).
        supabase = _SupabaseFake(
            casos=[
                _caso(1, gravidade="critico", sigilo_reforcado=True, tipo_manifestacao="denuncia"),
                _caso(2, gravidade="critico"),
            ]
        )

        corpo = _client(monkeypatch, supabase).get("/api/ouvidoria/protocolos").json()

        marcas = {linha["protocolo"]: linha["sigilo_reforcado"] for linha in corpo["protocolos"]}
        assert marcas == {"2026-0001": True, "2026-0002": False}


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


def _app_com_middleware(monkeypatch, supabase: _SupabaseFake, participante: dict) -> TestClient:
    """O app com o middleware montado, e nao so o router: e o middleware que
    esta sendo testado, e ele vive no `main`."""
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SemCacheMiddleware)
    app.add_middleware(RequestContextMiddleware)
    app.include_router(ouvidoria_router.router, prefix="/api")

    async def _fake_participante(_user, _sb, fields=None):
        return participante

    monkeypatch.setattr(ouvidoria_router, "get_participante_for_user", _fake_participante)
    monkeypatch.setattr(ouvidoria_router, "agora_utc", lambda: AGORA)
    app.dependency_overrides[get_current_user] = lambda: {"id": "u1", "email": "u@hsm.br"}
    app.dependency_overrides[get_supabase_client] = lambda: supabase
    return TestClient(app)


class TestRespostaDaOuvidoriaNaoFicaGuardada:
    """As respostas que carregam dossie saem com `Cache-Control: no-store`
    (issue #344). O corpo tem protocolo, setor e resumo do relato, e o painel
    repete o par de leituras de minuto em minuto: sem cabecalho, a garantia de
    que nada disso fica guardado no caminho seria comportamento de terceiro, e
    nao decisao deste codigo."""

    @pytest.mark.parametrize("rota", ["/api/ouvidoria/metricas", "/api/ouvidoria/protocolos"])
    def test_as_duas_portas_do_painel_saem_sem_cache(self, monkeypatch, rota):
        cliente = _app_com_middleware(monkeypatch, _SupabaseFake(casos=[_caso(1)]), OUVIDOR)

        resposta = cliente.get(rota)

        assert resposta.status_code == 200, resposta.text
        assert resposta.headers.get("cache-control") == "no-store"
        # A fixture precisa mesmo carregar dossie, senao o teste passaria numa
        # resposta vazia sem provar nada sobre o que esta sendo protegido.
        assert "Recepcao" in resposta.text

    def test_a_recusa_por_perfil_tambem_sai_sem_cache(self, monkeypatch):
        # O 403 e resposta como qualquer outra e nao pode ser guardado: uma
        # recusa em cache prenderia fora quem acabou de receber o perfil.
        cliente = _app_com_middleware(monkeypatch, _SupabaseFake(casos=[_caso(1)]), SECRETARIA)

        resposta = cliente.get("/api/ouvidoria/metricas")

        assert resposta.status_code == 403, resposta.text
        assert resposta.headers.get("cache-control") == "no-store"

    def test_o_app_real_liga_o_middleware(self):
        """Os testes acima montam um app sintético e adicionam o middleware à
        mão: nenhum deles toca `app.main`. Sem esta asserção, apagar a linha
        `app.add_middleware(SemCacheMiddleware)` do `main.py` deixava a suíte
        inteira verde enquanto produção perdia o cabeçalho em silêncio.

        Mesmo teste que o irmão gêmeo deste middleware já tem
        (`test_limite_corpo.py::test_app_real_liga_o_teto`)."""
        from app.main import app

        assert any(m.cls is SemCacheMiddleware for m in app.user_middleware)

    def test_a_area_da_ouvidoria_esta_na_lista_de_prefixos(self):
        """Ligar a peça sem a área dentro dela seria o mesmo silêncio, um passo
        adiante: o middleware roda e não carimba nada."""
        assert "/api/ouvidoria" in prefixos_sem_cache()

    def test_o_portal_do_setor_esta_na_lista_por_decisao(self):
        """Ele cairia dentro de "/api/ouvidoria" por acidente de nome. A
        entrada própria é o que torna a cobertura dele uma decisão."""
        assert "/api/ouvidoria-setor" in prefixos_sem_cache()

    def test_prefixo_da_api_mudado_por_env_continua_carimbado(self, monkeypatch):
        """O prefixo da API é configuração (`settings.api_prefix`), e é com ele
        que o `main` monta todo router. Com "/api" escrito à mão na lista,
        mudar o prefixo por env transformava esta peça em no-op silencioso: o
        middleware roda, caminho nenhum casa, nada cai (issue #439)."""
        monkeypatch.setattr(settings, "api_prefix", "/api/v2")

        app = FastAPI()
        app.add_middleware(SemCacheMiddleware)

        @app.get("/api/v2/ouvidoria/metricas")
        def _metricas():
            return {"ok": True}

        resposta = TestClient(app).get("/api/v2/ouvidoria/metricas")

        assert resposta.status_code == 200
        assert resposta.headers.get("cache-control") == "no-store"

    def test_o_500_do_app_real_sai_sem_carimbo_e_com_corpo_generico(self):
        """A decisão da issue #439, item 3, presa no `app.main` de verdade.

        O `@app.exception_handler(Exception)` do `main` é montado no
        `ServerErrorMiddleware`, que o Starlette põe FORA de todo
        `user_middleware`, portanto fora desta peça: o 500 sem tratamento sai
        sem o cabeçalho. A decisão foi não carimbá-lo, e ela se apoia em duas
        pernas. A primeira é o custo: trazer o handler para dentro exigiria
        embrulhar o app no entrypoint do uvicorn. A segunda é o que sustenta a
        primeira: o corpo desse 500 é a frase genérica do
        `DETALHE_ERRO_GENERICO`, sem protocolo, setor nem resumo, e por isso
        não há dossiê a proteger ali.

        As duas pernas ficam presas aqui. Se um dia o handler passar a ecoar a
        exceção ou o caminho, a segunda cai e a decisão inteira deixa de valer:
        este teste fica vermelho em vez de o argumento envelhecer calado.

        Contra o `app.main`, e não contra um app sintético: um sintético
        provaria a ordem de montagem do Starlette, que não é o que está em
        jogo, e seguiria verde se alguém adotasse a alternativa descartada.

        O controle no começo existe para o teste não passar por engano: ele
        prova que a peça está viva neste caminho antes de afirmar o que NÃO
        acontece nele."""
        from app.main import DETALHE_ERRO_GENERICO
        from app.main import app as app_real

        cliente = TestClient(app_real, raise_server_exceptions=False)

        # Controle: a recusa por falta de credencial passa pela peça e sai
        # carimbada. Sem isto, um caminho errado daria o mesmo verde adiante.
        recusa = cliente.get("/api/ouvidoria/metricas")
        assert recusa.status_code in (401, 403), recusa.text
        assert recusa.headers.get("cache-control") == "no-store"

        # O segredo entra pela mensagem da exceção: é o que vazaria se o
        # handler ecoasse `str(exc)`.
        segredo = "ouvidoria_protocolos.relato_integral"

        def _supabase_que_estoura():
            raise RuntimeError(segredo)

        anteriores = dict(app_real.dependency_overrides)
        app_real.dependency_overrides[get_current_user] = lambda: {"id": "u1", "email": "u@hsm.br"}
        app_real.dependency_overrides[get_supabase_client] = _supabase_que_estoura
        try:
            resposta = cliente.get("/api/ouvidoria/metricas")
        finally:
            app_real.dependency_overrides.clear()
            app_real.dependency_overrides.update(anteriores)

        assert resposta.status_code == 500, resposta.text
        # Perna 1: o 500 não é carimbado, e a docstring da peça diz isso.
        assert "cache-control" not in resposta.headers
        # Perna 2: o corpo é a frase genérica, sem nada do dossiê nem da falha.
        assert resposta.json() == {"detail": DETALHE_ERRO_GENERICO}
        assert segredo not in resposta.text

    def test_rota_de_fora_da_ouvidoria_nao_e_carimbada(self):
        # O middleware e por area, e nao para o app inteiro: apagar cache de
        # tudo tiraria do resto do app uma escolha que ele nunca fez.
        app = FastAPI()
        app.add_middleware(SemCacheMiddleware)

        @app.get("/api/participantes/me")
        def _me():
            return {"id": "P10"}

        resposta = TestClient(app).get("/api/participantes/me")

        assert resposta.status_code == 200
        assert "cache-control" not in resposta.headers
