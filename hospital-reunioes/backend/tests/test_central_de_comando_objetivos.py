"""Os Objetivos da Central de Comando pela rota real (issue #820, PRD #809).

O seam é a ROTA HTTP, com `require_super_admin` de pé, como nas outras telas. A
galeria combina as duas fontes (Google e Instagram) numa leitura só, então o
transporte de mentira daqui despacha pelo host: um teste não pode instalar os
dois `httpx.Client` de mentira do apoio ao mesmo tempo. Todo o resto (provedores,
cache, gate, regras) roda de verdade; só a rede e quem está logado são dublados.

Porte de `objetivo-screen.test.ts` do repositório antigo: a galeria com o número
de hoje dos quatro Objetivos com montador, a lente de cada um com números,
sugestões (com o porquê) e frescor, e o identificador inexistente que dá 404.
"""

from __future__ import annotations

import os
import re
import sys
from types import SimpleNamespace

import httpx
import pytest
from cryptography.hazmat.primitives import serialization

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from central_de_comando_apoio import (  # noqa: E402
    HOST_DA_GRAPH_API,
    PREFIXO_DA_CENTRAL,
    SECRETARIA,
    SUPER_ADMIN,
    VISITANTES_NA_GA4,
    GoogleFalso,
    InstagramFalso,
    LoteDaGA4,
    cliente_da_central,
)

pytestmark = pytest.mark.usefixtures("gate_e_limitador_zerados")

_28_DIAS = ("2026-08-21", "2026-09-17")

# Media com maioria de Reels no top, para a regra reels-rendem-mais na lente.
_MIDIAS_COM_REELS = [
    {
        "id": "r1",
        "media_type": "VIDEO",
        "media_product_type": "REELS",
        "permalink": "https://www.instagram.com/reel/r1",
        "timestamp": "2026-09-10T12:00:00+0000",
        "caption": "Reel um",
        "media_url": "https://cdn/r1.mp4",
        "thumbnail_url": "https://cdn/r1.jpg",
    },
    {
        "id": "r2",
        "media_type": "VIDEO",
        "media_product_type": "REELS",
        "permalink": "https://www.instagram.com/reel/r2",
        "timestamp": "2026-09-09T12:00:00+0000",
        "caption": "Reel dois",
        "media_url": "https://cdn/r2.mp4",
        "thumbnail_url": "https://cdn/r2.jpg",
    },
    {
        "id": "r3",
        "media_type": "VIDEO",
        "media_product_type": "REELS",
        "permalink": "https://www.instagram.com/reel/r3",
        "timestamp": "2026-09-08T12:00:00+0000",
        "caption": "Reel tres",
        "media_url": "https://cdn/r3.mp4",
        "thumbnail_url": "https://cdn/r3.jpg",
    },
    {
        "id": "i1",
        "media_type": "IMAGE",
        "permalink": "https://www.instagram.com/p/i1",
        "timestamp": "2026-09-07T12:00:00+0000",
        "caption": "Imagem",
        "media_url": "https://cdn/i1.jpg",
    },
]


@pytest.fixture(autouse=True)
def _no_dia_de_teste(hoje_da_central):
    """Todo teste daqui vive em 18/09/2026, o dia dos intervalos do apoio."""


@pytest.fixture
def central_falsa(monkeypatch, chave_rsa_da_central, cache_da_central, central_configurada, instagram_configurado):
    """Google e Instagram de mentira no MESMO transporte, despachando pelo host.

    A galeria dos Objetivos lê as duas fontes numa leitura só, e os dublês do
    apoio trocam o `httpx.Client` inteiro (um sobrescreveria o outro). Aqui os
    dois convivem: o provedor roda de verdade, e a resposta vem do dublê da
    fonte certa. Devolve os dublês para o teste ajustar o que a fonte "sabe"."""
    import app.dependencies  # noqa: F401

    chave_publica = chave_rsa_da_central.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    google = GoogleFalso(chave_publica, VISITANTES_NA_GA4)
    lote = LoteDaGA4()
    google.respondedores.append(lote)
    instagram = InstagramFalso()

    def despachar(pedido: httpx.Request) -> httpx.Response:
        if pedido.url.host == HOST_DA_GRAPH_API:
            return instagram(pedido)
        return google(pedido)

    cliente_de_verdade = httpx.Client

    def _cliente(*args, **kwargs):
        return cliente_de_verdade(*args, transport=httpx.MockTransport(despachar), **kwargs)

    monkeypatch.setattr(httpx, "Client", _cliente)
    return SimpleNamespace(google=google, instagram=instagram, lote=lote)


def _galeria(logado: dict | None = SUPER_ADMIN) -> httpx.Response:
    return cliente_da_central(logado).get(f"{PREFIXO_DA_CENTRAL}/objetivos")


def _lente(identificador: str, periodo: str | None = None, logado: dict | None = SUPER_ADMIN) -> httpx.Response:
    params = {"periodo": periodo} if periodo is not None else None
    return cliente_da_central(logado).get(f"{PREFIXO_DA_CENTRAL}/objetivos/{identificador}", params=params)


# ─── A galeria ───────────────────────────────────────────────────────────────


class TestGaleria:
    def test_lista_os_seis_objetivos_na_ordem_do_catalogo(self, central_falsa):
        corpo = _galeria().json()
        assert [o["id"] for o in corpo["objetivos"]] == [
            "site-visitantes",
            "instagram-seguidores",
            "instagram-engajamento",
            "site-area",
            "contatos",
            "google-reputacao",
        ]

    def test_quatro_com_numero_vivo(self, central_falsa):
        """Os quatro Objetivos com montador trazem o número de hoje (28 dias)."""
        por_id = {o["id"]: o for o in _galeria().json()["objetivos"]}

        assert por_id["site-visitantes"]["numero"]["valor"] == 12345
        assert por_id["instagram-seguidores"]["numero"]["valor"] == 18420
        assert por_id["instagram-engajamento"]["numero"]["valor"] == 7820
        assert por_id["contatos"]["numero"]["valor"] == 6786
        for navegavel in ("site-visitantes", "instagram-seguidores", "instagram-engajamento", "contatos"):
            assert por_id[navegavel]["em_construcao"] is False

    def test_contatos_com_todo_canal_medido_em_zero_mostra_0_no_card(self, central_falsa):
        """Nenhum clique em canal medido nos 28 dias: o card diz 0, e não "Ver os
        números" (decisão do dono na revisão do PR #872)."""
        central_falsa.lote.eventos[_28_DIAS] = {"page_view": 88000}

        por_id = {o["id"]: o for o in _galeria().json()["objetivos"]}

        assert por_id["contatos"]["numero"]["valor"] == 0

    def test_dois_em_construcao_sem_numero_nem_destino_navegavel(self, central_falsa):
        por_id = {o["id"]: o for o in _galeria().json()["objetivos"]}

        for em_construcao in ("site-area", "google-reputacao"):
            assert por_id[em_construcao]["em_construcao"] is True
            assert por_id[em_construcao]["numero"] is None

    def test_a_galeria_traz_o_frescor(self, central_falsa, relogio_da_central):
        assert _galeria().json()["frescor"] == {
            "atualizado_em": "2026-09-18T13:45:00+00:00",
            "atualizacao_falhou": False,
            "motivo": None,
        }

    def test_a_galeria_nao_fala_em_meta_nem_em_braco(self, central_falsa):
        texto = _galeria().text
        assert not re.search(r"\bmeta\b", texto, re.IGNORECASE)
        assert not re.search(r"bra[cç]os?\b", texto, re.IGNORECASE)


# ─── A lente: Crescer no Instagram (Seguidores) ──────────────────────────────


class TestLenteInstagramSeguidores:
    def test_traz_os_numeros_o_periodo_e_o_frescor(self, central_falsa, relogio_da_central):
        corpo = _lente("instagram-seguidores", "28d").json()

        assert corpo["objetivo"]["id"] == "instagram-seguidores"
        assert corpo["objetivo"]["nome"] == "Crescer no Instagram"
        assert corpo["periodo"]["chave"] == "28d"
        assert corpo["periodo"]["dias"] == 28
        numeros = {n["chave"]: n for n in corpo["numeros"]}
        assert numeros["followers"]["valor"] == 18420
        assert numeros["followers"]["crescimento"] == 312
        assert numeros["reach"]["valor"] == 41280
        assert numeros["reach"]["anterior"] == 37650
        assert numeros["reach"]["variacao"] == pytest.approx((41280 - 37650) / 37650)
        assert numeros["views"]["valor"] == 96540
        assert corpo["frescor"]["atualizado_em"] == "2026-09-18T13:45:00+00:00"

    def test_alcance_subindo_nao_gera_sugestao(self, central_falsa):
        """Alcance padrão (41280) subiu contra o anterior (37650): estado calmo."""
        assert _lente("instagram-seguidores", "28d").json()["sugestoes"] == []

    def test_alcance_em_queda_gera_a_sugestao_com_o_porque(self, central_falsa):
        central_falsa.instagram.insights[_28_DIAS]["reach"] = 30120

        sugestoes = {s["id"]: s for s in _lente("instagram-seguidores", "28d").json()["sugestoes"]}

        assert "queda-de-alcance" in sugestoes
        assert "20%" in sugestoes["queda-de-alcance"]["porque"]
        assert "37.650" in sugestoes["queda-de-alcance"]["porque"]


# ─── A lente: Aumentar o engajamento no Instagram ────────────────────────────


class TestLenteInstagramEngajamento:
    def test_traz_interacoes_e_contas_que_engajaram(self, central_falsa):
        numeros = {n["chave"]: n for n in _lente("instagram-engajamento", "28d").json()["numeros"]}

        assert numeros["interactions"]["valor"] == 7820
        assert numeros["accountsEngaged"]["valor"] == 5140

    def test_sem_regra_disparada_vem_sem_sugestao(self, central_falsa):
        """Interações e Alcance subindo, sem Reels no topo: estado calmo, e a
        tela diz que está tudo no rumo (issue #861)."""
        assert _lente("instagram-engajamento", "28d").json()["sugestoes"] == []

    def test_interacoes_em_queda_com_alcance_mantido_gera_sugestao(self, central_falsa):
        central_falsa.instagram.insights[_28_DIAS]["total_interactions"] = 5000

        sugestoes = {s["id"] for s in _lente("instagram-engajamento", "28d").json()["sugestoes"]}

        assert "queda-de-interacoes" in sugestoes

    def test_reels_dominando_o_top_gera_sugestao(self, central_falsa):
        central_falsa.instagram.midias = [dict(m) for m in _MIDIAS_COM_REELS]
        central_falsa.instagram.interacoes = {"r1": 100, "r2": 90, "r3": 80, "i1": 70}

        sugestoes = {s["id"] for s in _lente("instagram-engajamento", "28d").json()["sugestoes"]}

        assert "reels-rendem-mais" in sugestoes


# ─── A lente: Atrair mais visitantes pro site ────────────────────────────────


class TestLenteSiteVisitantes:
    def test_traz_os_visitantes_e_a_sugestao_do_celular(self, central_falsa):
        corpo = _lente("site-visitantes", "28d").json()

        numeros = {n["chave"]: n for n in corpo["numeros"]}
        assert numeros["visitors"]["valor"] == 12345
        assert numeros["visitors"]["anterior"] == 10000
        # celular 7100 de 10000 (71%) domina
        assert "dispositivo-celular-domina" in {s["id"] for s in corpo["sugestoes"]}

    def test_tem_os_tres_periodos(self, central_falsa):
        assert _lente("site-visitantes", "90d").status_code == 200


# ─── A lente: Gerar mais contatos ────────────────────────────────────────────


class TestLenteContatos:
    def test_traz_os_contatos_medidos_e_a_sugestao_de_instrumentar(self, central_falsa):
        corpo = _lente("contatos", "28d").json()

        numeros = {n["chave"]: n for n in corpo["numeros"]}
        assert numeros["contatos"]["valor"] == 6786
        sugestoes = {s["id"]: s for s in corpo["sugestoes"]}
        assert "contatos-instrumentar" in sugestoes
        assert "2 de 4" in sugestoes["contatos-instrumentar"]["porque"]

    def test_canal_medido_sem_clique_nao_entra_na_sugestao_de_instrumentar(self, central_falsa):
        """7 dias: ninguém enviou o Fale Conosco. O canal segue medido (com 0),
        então a sugestão pede para instrumentar só o que o Site não avisa ao
        Google: o agendar e o telefone (#856)."""
        corpo = _lente("contatos", "7d").json()

        porque = {s["id"]: s for s in corpo["sugestoes"]}["contatos-instrumentar"]["porque"]
        assert "2 de 4" in porque
        assert "Fale Conosco" not in porque

    def test_canal_medido_com_zero_clique_mostra_contatos_medidos_0(self, central_falsa):
        """90 dias: nenhum clique no WhatsApp nem no Fale Conosco. Os dois seguem
        medidos, então a lente diz "Contatos medidos 0", igual à tela Dados do
        Google, e não esconde o número (decisão do dono na revisão do PR #872)."""
        corpo = _lente("contatos", "90d").json()

        numeros = {n["chave"]: n for n in corpo["numeros"]}
        assert numeros["contatos"]["valor"] == 0
        assert numeros["contatos"]["rotulo"] == "Contatos medidos"


# ─── 404, 422 e o cache ──────────────────────────────────────────────────────


class TestLenteNaoEncontradaEPeriodo:
    @pytest.mark.parametrize("identificador", ["nao-existe", "site-area", "google-reputacao"])
    def test_identificador_sem_lente_e_404(self, identificador):
        """Inexistente ou em construção (sem destino navegável): 404, com frase."""
        resposta = _lente(identificador, "28d")

        assert resposta.status_code == 404
        assert resposta.json()["detail"]

    def test_o_instagram_nao_tem_90_dias_e_e_422(self):
        assert _lente("instagram-seguidores", "90d").status_code == 422


class TestCache:
    def test_a_segunda_leitura_dentro_da_hora_sai_do_cache(self, central_falsa, relogio_da_central):
        primeira = _lente("site-visitantes", "28d").json()
        idas_da_primeira = len(central_falsa.google.pedidos)
        central_falsa.google.visitantes[_28_DIAS] = 99999
        relogio_da_central.avancar(minutes=59)

        segunda = _lente("site-visitantes", "28d").json()

        assert segunda == primeira
        assert len(central_falsa.google.pedidos) == idas_da_primeira


def _atualizar_lente(identificador: str, periodo: str = "28d", logado: dict | None = SUPER_ADMIN) -> httpx.Response:
    return cliente_da_central(logado).post(
        f"{PREFIXO_DA_CENTRAL}/atualizar-agora",
        params={"tela": f"objetivos/{identificador}", "periodo": periodo},
    )


class TestAtualizarAgoraNaLente:
    """A lente tem o Atualizar agora das outras telas (issue #861), pela mesma
    rota genérica e com o mesmo limite de taxa: forçar a lente é ir às fontes
    que ela lê, e o carimbo muda."""

    def test_vai_a_fonte_mesmo_com_o_cache_valido_e_o_carimbo_muda(self, central_falsa, relogio_da_central):
        _lente("instagram-seguidores", "28d")
        idas_da_leitura = len(central_falsa.instagram.pedidos)
        central_falsa.instagram.insights[_28_DIAS]["reach"] = 50000
        relogio_da_central.avancar(minutes=5)

        resposta = _atualizar_lente("instagram-seguidores")

        assert resposta.status_code == 200, resposta.text
        corpo = resposta.json()
        assert len(central_falsa.instagram.pedidos) > idas_da_leitura
        assert {n["chave"]: n["valor"] for n in corpo["numeros"]}["reach"] == 50000
        assert corpo["frescor"] == {
            "atualizado_em": "2026-09-18T13:50:00+00:00",
            "atualizacao_falhou": False,
            "motivo": None,
        }

    def test_depois_dele_a_leitura_comum_ja_serve_o_numero_novo(self, central_falsa, relogio_da_central):
        _lente("site-visitantes", "28d")
        central_falsa.google.visitantes[_28_DIAS] = 99999
        relogio_da_central.avancar(minutes=5)
        _atualizar_lente("site-visitantes")
        relogio_da_central.avancar(minutes=5)

        corpo = _lente("site-visitantes", "28d").json()

        assert {n["chave"]: n["valor"] for n in corpo["numeros"]}["visitors"] == 99999
        assert corpo["frescor"]["atualizado_em"] == "2026-09-18T13:50:00+00:00"

    @pytest.mark.parametrize("identificador", ["nao-existe", "site-area", "../instagram", ""])
    def test_objetivo_sem_lente_e_recusado_sem_ir_a_fonte(self, central_falsa, identificador):
        resposta = _atualizar_lente(identificador)

        assert resposta.status_code == 422
        assert central_falsa.google.pedidos == []
        assert central_falsa.instagram.pedidos == []

    def test_o_instagram_nao_tem_90_dias_e_e_422_sem_ir_a_fonte(self, central_falsa):
        resposta = _atualizar_lente("instagram-engajamento", "90d")

        assert resposta.status_code == 422
        assert central_falsa.instagram.pedidos == []

    def test_divide_o_limite_de_5_por_minuto_do_atualizar_agora(self, central_falsa):
        respostas = [_atualizar_lente("instagram-seguidores").status_code for _ in range(5)]
        idas_antes = len(central_falsa.instagram.pedidos)

        sexto = _atualizar_lente("instagram-seguidores")

        assert respostas == [200] * 5
        assert sexto.status_code == 429
        assert len(central_falsa.instagram.pedidos) == idas_antes

    def test_quem_nao_e_super_admin_nao_forca_ida_nenhuma(self, central_falsa):
        resposta = _atualizar_lente("instagram-seguidores", logado=SECRETARIA)

        assert resposta.status_code == 403
        assert central_falsa.instagram.pedidos == []


def _instagram(periodo: str = "28d") -> httpx.Response:
    return cliente_da_central(SUPER_ADMIN).get(f"{PREFIXO_DA_CENTRAL}/instagram", params={"periodo": periodo})


def _atualizar_tela(tela: str, periodo: str = "28d") -> httpx.Response:
    return cliente_da_central(SUPER_ADMIN).post(
        f"{PREFIXO_DA_CENTRAL}/atualizar-agora", params={"tela": tela, "periodo": periodo}
    )


def _seguidores_na_galeria() -> int:
    objetivos = {o["id"]: o for o in _galeria().json()["objetivos"]}
    return objetivos["instagram-seguidores"]["numero"]["valor"]


def _seguidores_na_lente() -> int:
    numeros = _lente("instagram-seguidores", "28d").json()["numeros"]
    return {n["chave"]: n["valor"] for n in numeros}["followers"]


class TestSincroniaEntreTelas:
    """Depois do Atualizar agora numa tela, as telas vizinhas que mostram a
    mesma métrica no mesmo período mostram o mesmo número (issue #858, achado
    do revisor no PR #863). Todas já estavam no cache, dentro da hora."""

    @pytest.fixture(autouse=True)
    def _tudo_lido_e_seguidores_mudaram(self, central_falsa, relogio_da_central):
        _galeria()
        _lente("instagram-seguidores", "28d")
        _instagram()
        central_falsa.instagram.seguidores = 20000
        relogio_da_central.avancar(minutes=5)

    def test_atualizar_a_lente_renova_a_galeria_e_a_tela_do_instagram(self):
        assert _atualizar_tela("objetivos/instagram-seguidores").status_code == 200

        assert _seguidores_na_galeria() == 20000
        assert _instagram().json()["seguidores"]["total"] == 20000

    def test_atualizar_a_tela_do_instagram_renova_a_lente_e_a_galeria(self):
        assert _atualizar_tela("instagram").status_code == 200

        assert _seguidores_na_lente() == 20000
        assert _seguidores_na_galeria() == 20000

    def test_outro_periodo_continua_no_cache(self, central_falsa):
        _lente("instagram-seguidores", "7d")
        _atualizar_tela("instagram", "28d")
        idas = len(central_falsa.instagram.pedidos)

        _lente("instagram-seguidores", "7d")

        assert len(central_falsa.instagram.pedidos) == idas


class TestVocabularioNaLente:
    def test_a_lente_nao_fala_em_meta_nem_em_braco(self, central_falsa):
        texto = _lente("site-visitantes", "28d").text

        assert not re.search(r"\bmeta\b", texto, re.IGNORECASE)
        assert not re.search(r"bra[cç]os?\b", texto, re.IGNORECASE)
