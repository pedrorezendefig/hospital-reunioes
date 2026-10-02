"""O aquecimento do cache da Central no boot (issue #867, ADR 0059).

O cache da Central mora na memória do processo e começa vazio a cada deploy.
Sem aquecer, a primeira abertura de cada tela depois do deploy ia à fonte na
hora (até 29 s na galeria dos Objetivos). Agora o boot dispara UMA rodada, numa
thread, no período padrão de cada tela, e a primeira abertura sai do cache.

Dois seams: o `lifespan` do app de verdade (`app.main`), pelo `TestClient`, e a
rodada em si (`aquecimento.aquecer`), chamada direto quando o assunto é o que
ela faz com cada chave. A rede é dublada pelo transporte: Google e Instagram no
mesmo `httpx.Client`, despachando pelo host, como nos testes dos Objetivos. O
scheduler do app é trocado por nada no boot do teste, exceto onde o assunto é
ele.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
from dataclasses import replace
from types import SimpleNamespace

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from central_de_comando_apoio import (  # noqa: E402
    HOST_DA_GRAPH_API,
    VISITANTES_NA_GA4,
    GoogleFalso,
    InstagramFalso,
    LoteDaGA4,
)

from app.config import settings  # noqa: E402
from app.services.central_de_comando import aquecimento, telas  # noqa: E402

# As chaves que a primeira abertura de cada tela pede, no período padrão (28
# dias). Escritas à mão, e não derivadas do código: é a especificação.
CHAVES_DO_GOOGLE = [
    ("visao-geral:visitantes", "28d"),
    ("dados-do-google", "28d"),
    ("objetivo", "site-visitantes", "28d"),
    ("objetivo", "contatos", "28d"),
]
CHAVES_DO_INSTAGRAM = [
    ("visao-geral:instagram", "28d"),
    ("instagram", "28d"),
    ("objetivo", "instagram-seguidores", "28d"),
    ("objetivo", "instagram-engajamento", "28d"),
]
# A galeria lê as duas fontes numa leitura só.
CHAVE_DA_GALERIA = ("objetivo-galeria", "28d")
CHAVES_DO_PERIODO_PADRAO = [*CHAVES_DO_GOOGLE, *CHAVES_DO_INSTAGRAM, CHAVE_DA_GALERIA]

# As mesmas telas em outro período: o aquecimento não passa por elas.
CHAVES_DE_OUTRO_PERIODO = [
    ("visao-geral:visitantes", "7d"),
    ("visao-geral:visitantes", "90d"),
    ("visao-geral:instagram", "7d"),
    ("dados-do-google", "7d"),
    ("dados-do-google", "90d"),
    ("instagram", "7d"),
    ("objetivo", "site-visitantes", "90d"),
    ("objetivo", "instagram-seguidores", "7d"),
]

# O quanto um teste espera por uma thread antes de desistir. Folga para a
# máquina lenta, nunca tempo de regra: nada aqui depende de relógio.
PACIENCIA = 30


@pytest.fixture(autouse=True)
def _no_dia_de_teste(hoje_da_central):
    """Todo teste daqui vive em 18/09/2026, o dia dos intervalos do apoio."""


@pytest.fixture
def aquecimento_ligado(monkeypatch):
    """O aquecimento como em produção. A suíte roda com ele desligado."""
    monkeypatch.setattr(settings, "central_aquecer_no_boot", True)


@pytest.fixture
def fontes_sem_credencial(monkeypatch):
    """Google e Instagram sem credencial, como no CI e no localhost sem `.env`.
    Explícito, e não pela ausência: o `.env` desta máquina pode ter a de verdade."""
    for nome in (
        "ga4_property_id",
        "google_application_credentials_json",
        "instagram_access_token",
        "instagram_business_account_id",
    ):
        monkeypatch.setattr(settings, nome, "")


@pytest.fixture
def central_falsa(monkeypatch, chave_rsa_da_central, cache_da_central, central_configurada, instagram_configurado):
    """Google e Instagram de mentira no MESMO transporte, despachando pelo host.

    A rodada lê as duas fontes, e os dublês do apoio trocam o `httpx.Client`
    inteiro (um sobrescreveria o outro). `liberar` segura toda resposta quando
    o teste o desarma: é a fonte que demora. `chegou` diz que um pedido já está
    esperando, e `estourou` registra a fonte segurada além da paciência (o
    dublê então se solta sozinho, para um defeito não virar teste pendurado)."""
    import app.dependencies  # noqa: F401

    chave_publica = chave_rsa_da_central.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    google = GoogleFalso(chave_publica, VISITANTES_NA_GA4)
    google.respondedores.append(LoteDaGA4())
    instagram = InstagramFalso()
    falsa = SimpleNamespace(
        google=google,
        instagram=instagram,
        liberar=threading.Event(),
        chegou=threading.Event(),
        estourou=[],
    )
    falsa.liberar.set()

    def despachar(pedido: httpx.Request) -> httpx.Response:
        falsa.chegou.set()
        if not falsa.liberar.wait(5):
            falsa.estourou.append(str(pedido.url))
            falsa.liberar.set()
        if pedido.url.host == HOST_DA_GRAPH_API:
            return instagram(pedido)
        return google(pedido)

    cliente_de_verdade = httpx.Client

    def _cliente(*args, **kwargs):
        return cliente_de_verdade(*args, transport=httpx.MockTransport(despachar), **kwargs)

    monkeypatch.setattr(httpx, "Client", _cliente)
    return falsa


class _SupabaseDaSaude:
    """O banco que o `/api/health` pinga: responde na hora, sem rede."""

    def table(self, _nome):
        return self

    def select(self, *_a, **_kw):
        return self

    def limit(self, *_a, **_kw):
        return self

    def execute(self):
        return SimpleNamespace(data=[])


@pytest.fixture
def app_do_hospital(monkeypatch):
    """O app de verdade, com o `lifespan` de verdade. O scheduler é trocado por
    nada (os jobs do app não são assunto daqui) e o banco do health check
    responde na hora."""
    from app import main
    from app.dependencies import get_supabase_client
    from app.routers import health

    monkeypatch.setattr(main, "start_scheduler", lambda: None)
    monkeypatch.setattr(main, "stop_scheduler", lambda: None)
    monkeypatch.setattr(health, "get_supabase_client", _SupabaseDaSaude)
    monkeypatch.setitem(main.app.dependency_overrides, get_supabase_client, _SupabaseDaSaude)
    return main.app


def _aquecida(cache, chave) -> bool:
    """A chave tem número guardado (o frescor dela tem hora)."""
    return cache.frescor(chave).atualizado_em is not None


def _rodada_do_boot(app):
    """A thread do aquecimento que o `lifespan` disparou."""
    return app.state.aquecimento_da_central


# ─── No boot ─────────────────────────────────────────────────────────────────


class TestNoBoot:
    def test_depois_do_boot_sem_requisicao_cada_chave_do_periodo_padrao_tem_numero(
        self, app_do_hospital, central_falsa, cache_da_central, aquecimento_ligado
    ):
        with TestClient(app_do_hospital):
            rodada = _rodada_do_boot(app_do_hospital)
            rodada.join(PACIENCIA)
            assert not rodada.is_alive()

        faltando = [c for c in CHAVES_DO_PERIODO_PADRAO if not _aquecida(cache_da_central, c)]
        assert faltando == []

    def test_so_o_periodo_padrao_e_aquecido(self, app_do_hospital, central_falsa, cache_da_central, aquecimento_ligado):
        with TestClient(app_do_hospital):
            _rodada_do_boot(app_do_hospital).join(PACIENCIA)

        aquecidas = [c for c in CHAVES_DE_OUTRO_PERIODO if _aquecida(cache_da_central, c)]
        assert aquecidas == []

    def test_o_boot_nao_espera_o_aquecimento(self, app_do_hospital, central_falsa, aquecimento_ligado):
        """Com a fonte segurando a resposta, o app já responde ao health check e
        a uma rota de outra área (Reuniões) antes de a rodada acabar."""
        central_falsa.liberar.clear()
        try:
            with TestClient(app_do_hospital) as cliente:
                assert central_falsa.chegou.wait(PACIENCIA), "a rodada não chegou a pedir nada à fonte"
                saude = cliente.get("/api/health")
                reunioes = cliente.get("/api/reunioes")
                rodada = _rodada_do_boot(app_do_hospital)
                ainda_aquecendo = rodada.is_alive()
                central_falsa.liberar.set()
                rodada.join(PACIENCIA)
        finally:
            central_falsa.liberar.set()

        assert saude.status_code == 200
        # Sem login: quem respondeu foi a rota de Reuniões, e na hora.
        assert reunioes.status_code == 401
        assert ainda_aquecendo
        assert central_falsa.estourou == []

    def test_com_o_aquecimento_desligado_o_boot_nao_dispara_nada(self, app_do_hospital, monkeypatch):
        monkeypatch.setattr(settings, "central_aquecer_no_boot", False)
        rodadas = []
        monkeypatch.setattr(aquecimento, "aquecer", lambda: rodadas.append(1))

        with TestClient(app_do_hospital):
            assert _rodada_do_boot(app_do_hospital) is None

        assert rodadas == []

    def test_uma_rodada_por_boot_e_nenhum_job_no_scheduler(self, app_do_hospital, monkeypatch, aquecimento_ligado):
        """O scheduler de verdade sobe com o app: o aquecimento não entra nele,
        nem agendado, nem recorrente."""
        from app import main
        from app.cron import scheduler as cron

        monkeypatch.setattr(main, "start_scheduler", cron.start_scheduler)
        monkeypatch.setattr(main, "stop_scheduler", cron.stop_scheduler)
        rodadas = []
        monkeypatch.setattr(aquecimento, "aquecer", lambda: rodadas.append(1))

        with TestClient(app_do_hospital):
            _rodada_do_boot(app_do_hospital).join(PACIENCIA)
            jobs = cron.scheduler.get_jobs()

        assert rodadas == [1]
        assert jobs, "o scheduler de verdade não subiu: o teste não conferiu nada"
        da_central = [j.id for j in jobs if j.func.__module__.startswith("app.services.central_de_comando")]
        assert da_central == []


# ─── Durante a rodada ────────────────────────────────────────────────────────


class TestLeituraDuranteOAquecimento:
    def test_a_tela_lida_no_meio_da_rodada_espera_a_ida_no_ar(
        self, monkeypatch, fontes_sem_credencial, cache_da_central, aquecimento_ligado
    ):
        """A mesma chave, lida pela tela enquanto a rodada está na fonte: uma
        ida só, e a tela recebe o que a rodada trouxe (#858)."""
        entrou, liberar = threading.Event(), threading.Event()
        idas = []

        def montar_lento(periodo):
            idas.append(periodo)
            entrou.set()
            liberar.wait(5)
            return {"seguidores": 18420}

        instagram = replace(telas.TELAS["instagram"], montar=montar_lento)
        monkeypatch.setitem(telas.TELAS, "instagram", instagram)

        rodada = aquecimento.disparar()
        try:
            assert entrou.wait(PACIENCIA)
            a_caminho = threading.Event()
            lidas = []

            def ler_a_tela():
                a_caminho.set()
                lidas.append(telas.ler("instagram", "28d"))

            leitor = threading.Thread(target=ler_a_tela)
            leitor.start()
            assert a_caminho.wait(PACIENCIA)
            # A folga para a tela chegar enquanto a rodada segura a fonte.
            leitor.join(0.1)
            # Ainda viva: a tela está esperando a ida no ar, não leu depois.
            assert leitor.is_alive()
        finally:
            liberar.set()
        leitor.join(PACIENCIA)
        rodada.join(PACIENCIA)

        assert idas == ["28d"]
        assert [tela["seguidores"] for tela in lidas] == [18420]


# ─── Falhas ──────────────────────────────────────────────────────────────────


class TestFalhaNaoDerrubaNada:
    @pytest.mark.parametrize(
        ("fonte_fora", "chaves_da_fonte_fora", "chaves_da_outra"),
        [
            ("google", CHAVES_DO_GOOGLE, CHAVES_DO_INSTAGRAM),
            ("instagram", CHAVES_DO_INSTAGRAM, CHAVES_DO_GOOGLE),
        ],
    )
    def test_a_fonte_que_cai_nao_segura_as_chaves_da_outra(
        self, central_falsa, cache_da_central, caplog, fonte_fora, chaves_da_fonte_fora, chaves_da_outra
    ):
        getattr(central_falsa, fonte_fora).forcar = httpx.ConnectError("sem rede")
        caplog.set_level(logging.INFO, logger=aquecimento.logger.name)

        aquecimento.aquecer()

        assert [c for c in chaves_da_outra if not _aquecida(cache_da_central, c)] == []
        assert [c for c in chaves_da_fonte_fora if _aquecida(cache_da_central, c)] == []
        assert not _aquecida(cache_da_central, CHAVE_DA_GALERIA)
        avisos = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert avisos, "a falha da fonte não apareceu no log"

    def test_o_erro_inesperado_numa_chave_vai_ao_log_e_a_rodada_segue(
        self, monkeypatch, central_falsa, cache_da_central, caplog
    ):
        def quebrada(_periodo):
            raise ValueError("defeito de código")

        monkeypatch.setitem(telas.TELAS, "dados-do-google", replace(telas.TELAS["dados-do-google"], montar=quebrada))
        caplog.set_level(logging.INFO, logger=aquecimento.logger.name)

        aquecimento.aquecer()

        outras = [c for c in CHAVES_DO_PERIODO_PADRAO if c != ("dados-do-google", "28d")]
        assert [c for c in outras if not _aquecida(cache_da_central, c)] == []
        (erro,) = [r for r in caplog.records if r.levelno == logging.ERROR]
        assert "dados-do-google" in erro.getMessage()
        assert erro.exc_info is not None

    def test_sem_credencial_nao_vai_a_rede_e_diz_numa_linha(
        self, monkeypatch, fontes_sem_credencial, cache_da_central, caplog
    ):
        def sem_rede(*_a, **_kw):
            raise AssertionError("o aquecimento sem credencial abriu um cliente HTTP")

        monkeypatch.setattr(httpx, "Client", sem_rede)
        caplog.set_level(logging.DEBUG, logger=aquecimento.logger.name)

        aquecimento.aquecer()

        (linha,) = [r for r in caplog.records if r.name == aquecimento.logger.name]
        assert linha.levelno == logging.INFO
        assert "sem credencial" in linha.getMessage()
        assert [c for c in CHAVES_DO_PERIODO_PADRAO if _aquecida(cache_da_central, c)] == []


# ─── A lista das leituras sai dos registros ──────────────────────────────────


class TestTelaNovaNaoFicaDeFora:
    def test_tela_nova_no_registro_entra_no_aquecimento(self, monkeypatch, fontes_sem_credencial, cache_da_central):
        monkeypatch.setitem(telas.TELAS, "tela-nova", telas.Tela(montar=lambda _p: {"n": 1}, falhas=()))

        aquecimento.aquecer()

        assert _aquecida(cache_da_central, ("tela-nova", "28d"))

    def test_tela_sem_o_periodo_padrao_fica_de_fora(self, monkeypatch, fontes_sem_credencial, cache_da_central):
        so_7_dias = telas.Tela(montar=lambda _p: {"n": 1}, falhas=(), periodos=("7d",))
        monkeypatch.setitem(telas.TELAS, "so-7-dias", so_7_dias)

        aquecimento.aquecer()

        assert not _aquecida(cache_da_central, ("so-7-dias", "7d"))
        assert not _aquecida(cache_da_central, ("so-7-dias", "28d"))

    def test_toda_tela_composta_do_atualizar_agora_e_aquecida(self):
        """A tela composta (a Visão Geral) não está no registro de `telas.py`:
        é a única escrita à mão na rodada. Uma nova, no router, sem entrar aqui,
        ficaria fria depois do deploy sem ninguém notar."""
        from app.routers.admin.central_de_comando import LEITORES_COMPOSTOS

        nomes = {nome for nome, _ler in aquecimento.leituras_do_boot()}

        assert set(LEITORES_COMPOSTOS) <= nomes

    def test_a_lente_de_cada_objetivo_navegavel_e_aquecida(self):
        from app.services.central_de_comando.objetivos.montador import MONTADORES

        nomes = {nome for nome, _ler in aquecimento.leituras_do_boot()}

        assert {f"objetivos/{identificador}" for identificador in MONTADORES} <= nomes


# ─── A suíte não vai à rede por causa do aquecimento ─────────────────────────


def test_a_suite_roda_com_o_aquecimento_desligado():
    """O `tests/conftest.py` desliga o aquecimento antes de qualquer import do
    app: todo `TestClient` que suba o app inteiro fica sem rodada, e nenhum
    teste bate no Google ou no Instagram por causa dela."""
    assert settings.central_aquecer_no_boot is False
