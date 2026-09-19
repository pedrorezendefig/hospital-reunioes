"""Áreas do site, Origem do público e Contatos gerados, os três blocos da
#818 na tela Dados do Google da Central de Comando (PRD #809, ADR 0058).

O seam principal é a ROTA HTTP, com `require_super_admin` de pé, como nas
fatias anteriores: o app mínimo e as pessoas logadas vêm do apoio
compartilhado (`cliente_da_central`). Dublados só o que é fronteira: quem está
logado, a rede do Google (`google_falso`, com o `lote_da_ga4` respondendo o
`batchRunReports`) e os relógios da Central. As tabelas do que a GA4 "sabe"
(`VISITAS_POR_PAGINA_NA_GA4`, `VISITAS_POR_CANAL_NA_GA4` e `EVENTOS_NA_GA4`,
no apoio) foram contadas à mão, e é contra elas que as asserções conferem: o
Google de mentira só responde a pergunta certa (métrica, dimensão, intervalo e
filtro), então o número só sai certo se o provedor perguntar certo.

As regras de agrupamento e de rótulo são testadas também direto, sem rota
(`area_da_pagina`, `origem_do_canal`, `ordenar_origens`, `canais_de_contato` e
os catálogos), como o PRD pede para as regras puras.

Porte dos testes de `src/lib/analytics` do repositório antigo que cabem nesta
fatia: o catálogo das Áreas, o ranking (`getBranchRanking`), a Origem
(`orderSources`, `getTrafficSources`), os Contatos (`montarCanais`,
`getContacts`), os mapeadores (`mapTrafficSources` e o `sumMetric`) e as
perguntas do provedor (`getVisitsByBranch`, `getTrafficSources`,
`getContactClicks`), além do "serve do cache no segundo acesso" de cada um.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import get_args

import httpx
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from central_de_comando_apoio import (  # noqa: E402
    PREFIXO_DA_CENTRAL,
    SUPER_ADMIN,
    cliente_da_central,
)

# O `google_falso` troca o `httpx.Client` por uma função enquanto o teste roda,
# e o `postgrest`, que o gate carrega na primeira vez, herda do `httpx.Client`
# ao ser importado. As classes daqui pedem o `lote_da_ga4` antes do gate, então
# o app é importado já aqui, antes de qualquer troca: sem isto, o arquivo passa
# na suíte (outro arquivo importa o app antes) e quebra quando roda sozinho.
import app.dependencies  # noqa: E402, F401
from app.config import settings  # noqa: E402
from app.services.central_de_comando import dados_do_google, provedor_google  # noqa: E402

pytestmark = pytest.mark.usefixtures("gate_e_limitador_zerados")


@pytest.fixture(autouse=True)
def _central_no_dia_de_teste(hoje_da_central, central_configurada):
    """Todo teste daqui vive em 18/09/2026, com a Central ligada ao Google."""


def _dados_do_google(periodo: str | None = None, logado: dict | None = SUPER_ADMIN) -> httpx.Response:
    params = {"periodo": periodo} if periodo is not None else None
    return cliente_da_central(logado).get(f"{PREFIXO_DA_CENTRAL}/dados-do-google", params=params)


# ─── Áreas do site ───────────────────────────────────────────────────────────


@pytest.mark.usefixtures("lote_da_ga4")
class TestAreasDoSite:
    def test_as_cinco_areas_por_visitas_da_maior_para_a_menor(self):
        """28 dias: as Visitas às páginas de cada Área, somadas, e o ranking
        da maior para a menor."""
        resposta = _dados_do_google("28d")

        assert resposta.status_code == 200, resposta.text
        assert [(area["chave"], area["visitas"]) for area in resposta.json()["areas_do_site"]] == [
            ("maternidade", 3842),
            ("emergencia", 3610),
            ("centro-de-imagem", 1230),
            ("centro-medico", 1230),
            ("laboratorio", 480),
        ]

    def test_cada_area_traz_o_nome_o_que_reune_e_a_comparacao_com_o_anterior(self):
        """O nome e a descrição são do catálogo da Central, e a variação é
        conta do backend: 3.842 contra 3.500 é alta de 9,8%."""
        assert _dados_do_google("28d").json()["areas_do_site"][0] == {
            "chave": "maternidade",
            "nome": "Maternidade",
            "descricao": "Estrutura, preparativos, amamentação",
            "visitas": 3842,
            "visitas_anterior": 3500,
            "variacao": pytest.approx(0.0977142857),
        }

    def test_a_variacao_so_existe_quando_o_anterior_teve_visita(self):
        """Estável é variação zero; sem visita no anterior (o Centro Médico,
        24/07 a 20/08) não há base, e a variação é nula, nunca infinita."""
        areas = _dados_do_google("28d").json()["areas_do_site"]

        assert [(a["nome"], a["visitas_anterior"], a["variacao"]) for a in areas] == [
            ("Maternidade", 3500, pytest.approx(0.0977142857)),
            ("Emergência 24h", 3700, pytest.approx(-0.0243243243)),
            ("Centro de Imagem", 1230, 0.0),
            ("Centro Médico", 0, None),
            ("Laboratório", 400, pytest.approx(0.2)),
        ]

    def test_a_pagina_da_area_e_as_subpaginas_contam_na_mesma_area(self, lote_da_ga4):
        """Porte de "soma sessions por prefixo" (`getVisitsByBranch`)."""
        lote_da_ga4.visitas_por_pagina[_28_DIAS] = {"/maternidade/": 10, "/maternidade/amamentacao/": 5}
        lote_da_ga4.visitas_por_pagina[_ANTERIOR_DOS_28_DIAS] = {}

        assert _area("maternidade", _dados_do_google("28d")) == (15, 0)

    def test_as_visitas_do_anterior_vem_do_periodo_anterior(self, lote_da_ga4):
        """O mesmo caminho, um número em cada período: 20 agora, 12 antes."""
        lote_da_ga4.visitas_por_pagina[_28_DIAS] = {"/laboratorio/": 20}
        lote_da_ga4.visitas_por_pagina[_ANTERIOR_DOS_28_DIAS] = {"/laboratorio/": 12}

        assert _area("laboratorio", _dados_do_google("28d")) == (20, 12)

    def test_pagina_fora_do_catalogo_e_prefixo_parcial_nao_contam_e_as_cinco_areas_sempre_vem(self, lote_da_ga4):
        """O blog é página solta do Site, e "/maternidade-clinica/" só começa
        com o mesmo texto: nenhum dos dois é da Maternidade. As cinco Áreas
        vêm sempre, com zero na que não teve visita."""
        lote_da_ga4.visitas_por_pagina[_28_DIAS] = {"/blog/": 99, "/maternidade-clinica/": 50, "/emergencia/": 8}
        lote_da_ga4.visitas_por_pagina[_ANTERIOR_DOS_28_DIAS] = {}

        resposta = _dados_do_google("28d")

        assert len(resposta.json()["areas_do_site"]) == 5
        assert _area("maternidade", resposta) == (0, 0)
        assert _area("emergencia", resposta) == (8, 0)

    def test_a_emergencia_conta_no_endereco_vivo_e_o_endereco_antigo_nao_conta(self, lote_da_ga4):
        """A Emergência mudou de "/emergencia-24h" para "/emergencia": contar
        o endereço antigo, ou só ele, zeraria a Área em silêncio."""
        lote_da_ga4.visitas_por_pagina[_28_DIAS] = {
            "/emergencia/": 8,
            "/emergencia/pediatrica/": 4,
            "/emergencia-24h/": 3,
        }

        assert _area("emergencia", _dados_do_google("28d"))[0] == 12

    def test_no_empate_vale_a_ordem_do_catalogo(self, lote_da_ga4):
        """Maternidade e Laboratório empatados em 100: a Maternidade vem antes,
        como no catálogo (e não o Laboratório, como na ordem alfabética)."""
        lote_da_ga4.visitas_por_pagina[_28_DIAS] = {"/laboratorio/": 100, "/maternidade/": 100, "/emergencia/": 300}

        assert [a["chave"] for a in _dados_do_google("28d").json()["areas_do_site"]] == [
            "emergencia",
            "maternidade",
            "laboratorio",
            "centro-de-imagem",
            "centro-medico",
        ]

    def test_o_ranking_e_o_do_periodo_escolhido(self):
        """7 dias: o Laboratório na frente, e as Áreas sem visita no fim, com
        zero."""
        areas = _dados_do_google("7d").json()["areas_do_site"]

        assert [(a["chave"], a["visitas"], a["visitas_anterior"], a["variacao"]) for a in areas] == [
            ("laboratorio", 450, 500, pytest.approx(-0.1)),
            ("maternidade", 400, 400, 0.0),
            ("emergencia", 200, 0, None),
            ("centro-de-imagem", 0, 0, None),
            ("centro-medico", 0, 0, None),
        ]

    def test_periodo_sem_visita_nas_areas_tem_as_cinco_com_zero(self):
        """90 dias: a GA4 respondeu que nenhuma página das Áreas teve visita. É
        zero de verdade, e as cinco aparecem, sem variação inventada."""
        areas = _dados_do_google("90d").json()["areas_do_site"]

        assert [(a["visitas"], a["visitas_anterior"], a["variacao"]) for a in areas] == [(0, 0, None)] * 5


_28_DIAS = ("2026-08-21", "2026-09-17")
_ANTERIOR_DOS_28_DIAS = ("2026-07-24", "2026-08-20")
_7_DIAS = ("2026-09-11", "2026-09-17")


def _area(chave: str, resposta: httpx.Response) -> tuple[int, int]:
    """As Visitas da Área no período e no anterior."""
    (area,) = [a for a in resposta.json()["areas_do_site"] if a["chave"] == chave]
    return area["visitas"], area["visitas_anterior"]


class TestAreaDaPagina:
    """A regra pura de página para Área do site, direto, sem rota (PRD #809,
    "regras puras testadas direto")."""

    @pytest.mark.parametrize(
        ("caminho", "area"),
        [
            ("/maternidade", "maternidade"),
            ("/maternidade/", "maternidade"),
            ("/maternidade/amamentacao/", "maternidade"),
            ("/emergencia/", "emergencia"),
            ("/emergencia/pediatrica/", "emergencia"),
            ("/centro-de-imagem/", "centro-de-imagem"),
            ("/centro-de-imagem/tomografia/", "centro-de-imagem"),
            ("/centro-medico/", "centro-medico"),
            ("/centro-medico/cardiologia/", "centro-medico"),
            ("/laboratorio/", "laboratorio"),
            ("/laboratorio/resultados/", "laboratorio"),
        ],
    )
    def test_a_pagina_da_area_e_as_subpaginas_sao_da_area(self, caminho, area):
        assert provedor_google.area_da_pagina(caminho) == area

    @pytest.mark.parametrize(
        "caminho",
        ["/", "", "/blog/", "/maternidade-clinica/", "/laboratorios/", "/emergencia-24h/", "/contato/maternidade/"],
    )
    def test_pagina_que_nao_e_de_area_nenhuma(self, caminho):
        """A página inicial, o blog, o prefixo parcial, o endereço antigo da
        Emergência e a página que só menciona uma Área no meio do caminho."""
        assert provedor_google.area_da_pagina(caminho) is None


class TestCatalogoDasAreas:
    """Porte do teste do catálogo da Central antiga, com o nome novo."""

    def test_sao_exatamente_as_cinco_areas_com_pagina_propria_na_ordem_do_catalogo(self):
        assert list(dados_do_google.AREAS_DO_SITE) == [
            "maternidade",
            "emergencia",
            "centro-de-imagem",
            "centro-medico",
            "laboratorio",
        ]

    def test_cada_area_tem_nome_e_descricao(self):
        for area in dados_do_google.AREAS_DO_SITE.values():
            assert area.nome.strip()
            assert area.descricao.strip()

    def test_servico_sem_pagina_propria_no_site_nao_entra(self):
        for sem_pagina in ("centro-cirurgico", "day-clinic", "pediatria"):
            assert sem_pagina not in dados_do_google.AREAS_DO_SITE

    def test_toda_area_que_o_provedor_agrupa_tem_nome_na_tela(self):
        """O provedor agrupa as páginas e a tela dá o nome: as duas listas são
        a mesma, na mesma ordem, senão uma Área chegaria à tela sem nome."""
        assert list(get_args(provedor_google.AreaDoSite)) == list(dados_do_google.AREAS_DO_SITE)


# ─── Origem do público ───────────────────────────────────────────────────────


@pytest.mark.usefixtures("lote_da_ga4")
class TestOrigemDoPublico:
    def test_as_visitas_por_origem_com_rotulo_e_percentual_e_o_resto_no_fim(self):
        """28 dias, 9.410 Visitas: os grupos de canal da GA4 somados em cada
        Origem do público, as origens da maior para a menor e o resto (Outros
        e Não identificado) sempre no fim. Os pontos percentuais somam 100."""
        resposta = _dados_do_google("28d")

        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["origem_do_publico"] == [
            {"chave": "busca", "rotulo": "Busca no Google", "visitas": 5700, "percentual": 61},
            {"chave": "direto", "rotulo": "Direto", "visitas": 1800, "percentual": 19},
            {"chave": "redes", "rotulo": "Redes sociais", "visitas": 800, "percentual": 9},
            {"chave": "anuncios", "rotulo": "Anúncios", "visitas": 750, "percentual": 8},
            {"chave": "outros", "rotulo": "Outros", "visitas": 320, "percentual": 3},
            {"chave": "nao-identificado", "rotulo": "Não identificado", "visitas": 40, "percentual": 0},
        ]

    def test_nunca_mostra_o_termo_cru_da_fonte(self):
        """O "(not set)" e o "(other)" da GA4 chegam somados nos rótulos
        gentis, como na Central antiga: nenhum termo técnico chega à tela."""
        origem = _dados_do_google("28d").json()["origem_do_publico"]

        for termo_da_fonte in ("(not set)", "(other)", "not set", "Unassigned", "Referral", "Organic Search"):
            assert termo_da_fonte not in str(origem)

    def test_a_ordem_e_a_do_periodo_escolhido(self):
        """7 dias: o direto na frente da busca, e nada de resto."""
        assert _dados_do_google("7d").json()["origem_do_publico"] == [
            {"chave": "direto", "rotulo": "Direto", "visitas": 900, "percentual": 60},
            {"chave": "busca", "rotulo": "Busca no Google", "visitas": 600, "percentual": 40},
        ]

    def test_o_resto_fica_no_fim_mesmo_quando_e_maior_que_as_origens(self, lote_da_ga4):
        """Porte de "mantém Outros e Não identificado no fim, mesmo se
        grandes" (`orderSources`)."""
        lote_da_ga4.visitas_por_canal[_28_DIAS] = {
            "Referral": 9999,
            "Organic Search": 100,
            "Unassigned": 5000,
            "Direct": 200,
        }

        origem = _dados_do_google("28d").json()["origem_do_publico"]

        assert [o["chave"] for o in origem] == ["direto", "busca", "outros", "nao-identificado"]

    def test_grupos_da_mesma_origem_somam(self, lote_da_ga4):
        """Porte de "mapeia para chaves canônicas, agrega e usa fallback"
        (`mapTrafficSources`): as redes pagas e as orgânicas são as mesmas
        redes, e o "Referral", que não está no mapa, é Outros."""
        lote_da_ga4.visitas_por_canal[_28_DIAS] = {
            "Organic Search": 100,
            "Paid Social": 30,
            "Organic Social": 20,
            "Unassigned": 5,
            "Referral": 8,
        }

        origem = _dados_do_google("28d").json()["origem_do_publico"]

        assert [(o["chave"], o["visitas"]) for o in origem] == [
            ("busca", 100),
            ("redes", 50),
            ("outros", 8),
            ("nao-identificado", 5),
        ]

    @pytest.mark.parametrize(
        ("canais", "fatias"),
        [
            # 8 de 3.008 é 0,27%: abaixo de 1% é "<1%" (0 ponto), e não 1%.
            ({"Organic Search": 1000, "Direct": 1000, "Organic Social": 1000, "Unassigned": 8}, [33, 33, 33, 0]),
            # Um sétimo e dois sétimos: 14,3% e 28,6% viram 14 e 29, e a soma dá 101.
            ({"Organic Search": 2, "Direct": 2, "Organic Social": 2, "Paid Search": 1}, [29, 29, 29, 14]),
            # 3 de 200 é 1,5%: arredonda para cima, 2. E 1 de 200 é 0,5%: "<1%".
            ({"Organic Search": 196, "Direct": 3, "Unassigned": 1}, [98, 2, 0]),
        ],
        ids=["abaixo-de-1-por-cento", "soma-101", "meio-ponto"],
    )
    def test_a_fatia_de_cada_origem_e_a_da_central_antiga(self, lote_da_ga4, canais, fatias):
        """Porte do `formatShare` da Central antiga, para a tela bater lado a
        lado com ela: cada fatia arredondada sozinha (meio ponto para cima), e
        a que fica abaixo de 1% vem com 0 ponto, que a tela escreve "<1%". A
        soma pode dar 99 ou 101, como lá."""
        lote_da_ga4.visitas_por_canal[_28_DIAS] = canais

        origem = _dados_do_google("28d").json()["origem_do_publico"]

        assert [o["percentual"] for o in origem] == fatias

    def test_origem_sem_visita_nao_aparece(self, lote_da_ga4):
        """A fatia vazia não vira barra: só entra origem com Visita."""
        lote_da_ga4.visitas_por_canal[_7_DIAS] = {"Direct": 900, "Paid Search": 0, "Unassigned": 0}

        origem = _dados_do_google("7d").json()["origem_do_publico"]

        assert [(o["chave"], o["percentual"]) for o in origem] == [("direto", 100)]

    def test_periodo_sem_visita_nenhuma_nao_tem_origem_nenhuma(self):
        """90 dias: a GA4 respondeu que ninguém veio. Lista vazia, e a tela
        diz que não há dado de origem, sem barra de zeros."""
        assert _dados_do_google("90d").json()["origem_do_publico"] == []


class TestOrigemDoCanal:
    """A regra pura de grupo de canal da GA4 para Origem do público, direto,
    sem rota. O mapa é o da Central antiga, grupo por grupo."""

    @pytest.mark.parametrize(
        ("canal", "origem"),
        [
            ("Organic Search", "busca"),
            ("Direct", "direto"),
            ("Organic Social", "redes"),
            ("Paid Social", "redes"),
            ("Paid Search", "anuncios"),
            ("Display", "anuncios"),
            ("Paid Shopping", "anuncios"),
            ("Paid Video", "anuncios"),
            ("Paid Other", "anuncios"),
            ("Cross-network", "anuncios"),
            ("Unassigned", "nao-identificado"),
            ("(other)", "nao-identificado"),
            ("", "nao-identificado"),
        ],
    )
    def test_o_grupo_do_mapa_vira_a_origem_dele(self, canal, origem):
        assert provedor_google.origem_do_canal(canal) == origem

    @pytest.mark.parametrize("canal", ["Referral", "Email", "Organic Video", "Affiliates", "SMS", "(not set)"])
    def test_grupo_identificado_fora_do_mapa_e_outros(self, canal):
        """Como na Central antiga: o "(not set)" não está no mapa e não é o
        nome vazio, então é Outros (e não Não identificado)."""
        assert provedor_google.origem_do_canal(canal) == "outros"

    def test_toda_origem_tem_rotulo_na_tela(self):
        assert list(get_args(provedor_google.OrigemDoPublico)) == list(dados_do_google.ROTULO_DA_ORIGEM)


class TestFatiaComoNaCentralAntiga:
    """A fatia de cada origem, direto (`formatShare`): cada uma arredondada
    sozinha, meio ponto para cima, e abaixo de 1% é 0 ponto ("<1%" na tela).
    Os esperados foram contados à mão."""

    @pytest.mark.parametrize(
        ("visitas", "total", "fatia"),
        [
            (5700, 9410, 61),  # 60,57%
            (800, 9410, 9),  # 8,50%: meio ponto para cima
            (1, 7, 14),  # 14,29%
            (2, 7, 29),  # 28,57%
            (3, 200, 2),  # 1,5%: meio ponto para cima
            (2, 200, 1),  # 1% em ponto: já não é "<1%"
            (199, 200, 100),  # 99,5%
            (7, 7, 100),
        ],
    )
    def test_a_fatia_arredondada_sozinha(self, visitas, total, fatia):
        assert dados_do_google.fatia_como_na_central_antiga(visitas, total) == fatia

    @pytest.mark.parametrize(("visitas", "total"), [(40, 9410), (8, 3008), (1, 200), (99, 10000)])
    def test_abaixo_de_1_por_cento_e_0_ponto_e_nao_1(self, visitas, total):
        """0,5% arredondaria para 1%; a Central antiga escrevia "<1%"."""
        assert dados_do_google.fatia_como_na_central_antiga(visitas, total) == 0

    def test_sem_total_e_zero(self):
        assert dados_do_google.fatia_como_na_central_antiga(0, 0) == 0


class TestOrdenarOrigens:
    """A ordem da Origem do público, direto (`orderSources`)."""

    def test_o_resto_no_fim_na_ordem_outros_e_nao_identificado(self):
        origens = [
            provedor_google.VisitasNaOrigem("outros", 9999),
            provedor_google.VisitasNaOrigem("busca", 100),
            provedor_google.VisitasNaOrigem("nao-identificado", 5000),
            provedor_google.VisitasNaOrigem("direto", 200),
        ]

        assert [o.origem for o in dados_do_google.ordenar_origens(origens)] == [
            "direto",
            "busca",
            "outros",
            "nao-identificado",
        ]

    def test_no_empate_vale_a_ordem_em_que_chegaram(self):
        origens = [
            provedor_google.VisitasNaOrigem("redes", 800),
            provedor_google.VisitasNaOrigem("anuncios", 800),
            provedor_google.VisitasNaOrigem("busca", 800),
        ]

        assert [o.origem for o in dados_do_google.ordenar_origens(origens)] == ["redes", "anuncios", "busca"]


# ─── Contatos gerados ────────────────────────────────────────────────────────


@pytest.mark.usefixtures("lote_da_ga4")
class TestContatosGerados:
    def test_os_quatro_canais_com_o_estado_honesto_de_cada_um(self):
        """28 dias: o WhatsApp e o Fale Conosco medidos pelos eventos que o
        Site dispara; o agendar em construção (o botão ainda não dispara
        evento) e o telefone não medido (ligação não é clique). Nenhum dos dois
        traz número: nem zero."""
        resposta = _dados_do_google("28d")

        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["contatos_gerados"] == [
            {"chave": "agendar", "rotulo": "Cliques para agendar", "estado": "em-construcao"},
            {"chave": "whatsapp", "rotulo": "WhatsApp", "estado": "medido", "cliques": 4514},
            {"chave": "fale-conosco", "rotulo": "Fale Conosco", "estado": "medido", "cliques": 2272},
            {"chave": "telefone", "rotulo": "Telefone", "estado": "nao-medido"},
        ]

    def test_canal_medido_sem_clique_no_periodo_fica_em_construcao_e_nao_mostra_zero(self):
        """7 dias: ninguém enviou o Fale Conosco, e a GA4 não devolve linha
        para ele. Como na Central antiga, o zero de um canal medido não é
        mostrado como resultado: o canal fica em construção."""
        contatos = _dados_do_google("7d").json()["contatos_gerados"]

        assert [(c["chave"], c["estado"], c.get("cliques")) for c in contatos] == [
            ("agendar", "em-construcao", None),
            ("whatsapp", "medido", 1100),
            ("fale-conosco", "em-construcao", None),
            ("telefone", "nao-medido", None),
        ]

    def test_periodo_sem_clique_nenhum_nao_inventa_numero(self):
        """90 dias: a GA4 respondeu que nenhum evento de contato aconteceu.
        Nenhum canal traz número, nem zero."""
        contatos = _dados_do_google("90d").json()["contatos_gerados"]

        assert [c["estado"] for c in contatos] == ["em-construcao", "em-construcao", "em-construcao", "nao-medido"]
        assert all("cliques" not in c for c in contatos)

    def test_os_eventos_contados_sao_os_da_configuracao(self, monkeypatch, lote_da_ga4):
        """O nome de cada evento vem de `GA4_EVENTO_WHATSAPP` e
        `GA4_EVENTO_FALE_CONOSCO`: se o Site trocar o nome, troca-se a
        variável, e o evento com o nome antigo deixa de contar."""
        monkeypatch.setattr(settings, "ga4_evento_whatsapp", "clique_no_whatsapp")
        monkeypatch.setattr(settings, "ga4_evento_fale_conosco", "envio_do_formulario")
        lote_da_ga4.eventos[_28_DIAS] = {"clique_no_whatsapp": 77, "envio_do_formulario": 5, "wa_click": 4514}

        contatos = _dados_do_google("28d").json()["contatos_gerados"]

        assert [(c["chave"], c.get("cliques")) for c in contatos] == [
            ("agendar", None),
            ("whatsapp", 77),
            ("fale-conosco", 5),
            ("telefone", None),
        ]


class TestCanaisDeContato:
    """A regra pura dos estados dos Contatos gerados, direto, sem rota. Porte
    dos testes de `montarCanais` da Central antiga."""

    def test_os_quatro_canais_na_ordem_da_tela(self):
        assert [c["chave"] for c in dados_do_google.canais_de_contato({})] == [
            "agendar",
            "whatsapp",
            "fale-conosco",
            "telefone",
        ]

    def test_canal_medido_com_zero_clique_fica_em_construcao_e_nao_medido_com_zero(self):
        (agendar, *_) = dados_do_google.canais_de_contato({"agendar": 0})

        assert agendar == {"chave": "agendar", "rotulo": "Cliques para agendar", "estado": "em-construcao"}

    def test_canal_com_clique_e_medido_com_o_numero(self):
        (agendar, *_) = dados_do_google.canais_de_contato({"agendar": 42})

        assert agendar == {"chave": "agendar", "rotulo": "Cliques para agendar", "estado": "medido", "cliques": 42}

    def test_canal_que_a_ga4_nao_mede_e_nao_medido_sem_numero(self):
        _, whatsapp, _, telefone = dados_do_google.canais_de_contato({"agendar": 42})

        assert whatsapp == {"chave": "whatsapp", "rotulo": "WhatsApp", "estado": "nao-medido"}
        assert telefone == {"chave": "telefone", "rotulo": "Telefone", "estado": "nao-medido"}

    def test_todo_canal_tem_nome_na_tela(self):
        assert list(get_args(provedor_google.CanalDeContato)) == list(dados_do_google.ROTULO_DO_CONTATO)


# ─── A tela: mesmo payload, mesma chave de cache, mesmo Atualizar agora ──────


@pytest.mark.usefixtures("lote_da_ga4")
class TestNaMesmaTela:
    """Decisão da triagem (18/09/2026): os três blocos entram no payload e na
    chave de cache da tela Dados do Google, sem rota nova, e o frescor e o
    Atualizar agora da tela valem para eles."""

    def test_o_payload_da_tela_traz_os_blocos_de_antes_os_tres_novos_e_o_frescor(self, relogio_da_central):
        """Porte de "monta todos os painéis e o frescor agregado"
        (`google-data-screen.test.ts`)."""
        corpo = _dados_do_google("28d").json()

        assert set(corpo) == {
            "periodo",
            "movimento",
            "dispositivos",
            "areas_do_site",
            "origem_do_publico",
            "contatos_gerados",
            "frescor",
        }
        assert corpo["frescor"] == {
            "atualizado_em": "2026-09-18T13:45:00+00:00",
            "atualizacao_falhou": False,
            "motivo": None,
        }

    def test_a_segunda_leitura_dentro_da_hora_serve_os_tres_blocos_do_cache(
        self, google_falso, lote_da_ga4, relogio_da_central
    ):
        """Porte de "serve do cache no segundo acesso ao mesmo período" do
        ranking, da origem e dos contatos da Central antiga."""
        cliente = cliente_da_central(SUPER_ADMIN)
        primeira = cliente.get(f"{PREFIXO_DA_CENTRAL}/dados-do-google", params={"periodo": "28d"}).json()
        idas_da_primeira = len(google_falso.pedidos)
        _mudar_os_tres_blocos_na_ga4(lote_da_ga4)
        relogio_da_central.avancar(minutes=59)

        segunda = cliente.get(f"{PREFIXO_DA_CENTRAL}/dados-do-google", params={"periodo": "28d"}).json()

        assert segunda == primeira
        assert len(google_falso.pedidos) == idas_da_primeira

    def test_o_atualizar_agora_da_tela_renova_os_tres_blocos(self, lote_da_ga4, relogio_da_central):
        """O Atualizar agora é o da rota genérica da #815, sem rota nova: vai à
        GA4 mesmo dentro da hora e traz os três blocos novos, com o carimbo
        novo."""
        cliente = cliente_da_central(SUPER_ADMIN)
        cliente.get(f"{PREFIXO_DA_CENTRAL}/dados-do-google", params={"periodo": "28d"})
        _mudar_os_tres_blocos_na_ga4(lote_da_ga4)
        relogio_da_central.avancar(minutes=5)

        resposta = cliente.post(
            f"{PREFIXO_DA_CENTRAL}/atualizar-agora", params={"tela": "dados-do-google", "periodo": "28d"}
        )

        assert resposta.status_code == 200, resposta.text
        corpo = resposta.json()
        assert corpo["areas_do_site"][0]["chave"] == "centro-medico"
        assert corpo["areas_do_site"][0]["visitas"] == 9000
        assert [(o["chave"], o["percentual"]) for o in corpo["origem_do_publico"]] == [("redes", 100)]
        assert corpo["contatos_gerados"][1] == {
            "chave": "whatsapp",
            "rotulo": "WhatsApp",
            "estado": "medido",
            "cliques": 1,
        }
        assert corpo["frescor"]["atualizado_em"] == "2026-09-18T13:50:00+00:00"

    def test_google_fora_com_numero_guardado_mostra_os_tres_blocos_de_antes(self, google_falso, relogio_da_central):
        """A tela nunca zera por causa de uma falha: o último valor bom inclui
        os três blocos, e o frescor diz que a atualização falhou."""
        cliente = cliente_da_central(SUPER_ADMIN)
        antes = cliente.get(f"{PREFIXO_DA_CENTRAL}/dados-do-google", params={"periodo": "28d"}).json()
        relogio_da_central.avancar(hours=2)
        google_falso.forcar = httpx.Response(503, json={"error": {"code": 503, "status": "UNAVAILABLE"}})

        resposta = cliente.get(f"{PREFIXO_DA_CENTRAL}/dados-do-google", params={"periodo": "28d"})

        assert resposta.status_code == 200, resposta.text
        corpo = resposta.json()
        for bloco in ("areas_do_site", "origem_do_publico", "contatos_gerados"):
            assert corpo[bloco] == antes[bloco]
        assert corpo["frescor"]["atualizacao_falhou"] is True

    def test_um_lote_que_falha_derruba_a_tela_inteira_sem_bloco_pela_metade(self, lote_da_ga4):
        """Os 7 relatórios vão em dois lotes. Se a GA4 recusar o lote dos
        Contatos gerados, a tela é 502 com a frase, e não um payload com os
        blocos do outro lote e um buraco (ou um zero) no lugar dos contatos.
        A tela é tudo ou nada até a #821."""
        lote_da_ga4.perguntas.remove(lote_da_ga4._eventos_filtrados_por_nome)

        resposta = _dados_do_google("28d")

        assert resposta.status_code == 502
        assert set(resposta.json()) == {"detail"}
        assert "HTTP 400" in resposta.json()["detail"]


def _mudar_os_tres_blocos_na_ga4(lote_da_ga4) -> None:
    """A GA4 passa a responder outra coisa nos três blocos, nos 28 dias."""
    lote_da_ga4.visitas_por_pagina[_28_DIAS] = {"/centro-medico/": 9000}
    lote_da_ga4.visitas_por_canal[_28_DIAS] = {"Organic Social": 10}
    lote_da_ga4.eventos[_28_DIAS] = {"wa_click": 1}


# ─── O nome novo e nenhum vínculo com a taxonomia de Setores ─────────────────

_RAIZ_DO_BACKEND = Path(__file__).resolve().parent.parent

# O código da Central no backend: o pacote de serviços e o router.
_CODIGO_DA_CENTRAL = [
    *sorted((_RAIZ_DO_BACKEND / "app" / "services" / "central_de_comando").glob("*.py")),
    _RAIZ_DO_BACKEND / "app" / "routers" / "admin" / "central_de_comando.py",
]

# O nome antigo da Área do site, com e sem cedilha, no singular e no plural.
_NOME_ANTIGO = re.compile(r"bra[cç]os?\b", re.IGNORECASE)


class TestVocabulario:
    def test_a_varredura_acha_o_codigo_da_central(self):
        """Sem isto, varrer nada passaria em tudo."""
        nomes = {arquivo.name for arquivo in _CODIGO_DA_CENTRAL}

        assert {"provedor_google.py", "dados_do_google.py", "central_de_comando.py"} <= nomes

    def test_o_nome_antigo_da_area_do_site_nao_aparece_no_codigo_nem_no_payload(self, lote_da_ga4):
        """ADR 0058, decisão 7: a Área do site tem o nome novo em toda a
        interface e no código."""
        culpados = [a.name for a in _CODIGO_DA_CENTRAL if _NOME_ANTIGO.search(a.read_text(encoding="utf-8"))]

        assert culpados == []
        assert not _NOME_ANTIGO.search(_dados_do_google("28d").text)

    def test_as_areas_do_site_nao_tem_vinculo_com_a_taxonomia_de_setores(self):
        """O catálogo das Áreas mora no código da Central e não lê nem importa
        Setor nenhum. A leitura de tabela também está trancada: o Supabase de
        mentira do `cliente_da_central` só conhece a tabela do gate."""
        importa_setores = [
            arquivo.name
            for arquivo in _CODIGO_DA_CENTRAL
            for linha in arquivo.read_text(encoding="utf-8").splitlines()
            if linha.lstrip().startswith(("import ", "from ")) and re.search(r"setor|taxonomia", linha, re.IGNORECASE)
        ]

        assert importa_setores == []
