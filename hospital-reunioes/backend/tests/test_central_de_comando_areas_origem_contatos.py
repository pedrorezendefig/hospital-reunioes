"""Áreas do site, Origem do público e Contatos gerados, os três blocos da
#818 na tela Dados do Google da Central de Comando (PRD #809, ADR 0058).

O seam principal é a ROTA HTTP, com `require_super_admin` de pé, como nas
fatias anteriores: o app mínimo e as pessoas logadas vêm do apoio
compartilhado (`cliente_da_central`). Dublados só o que é fronteira: quem está
logado, a rede do Google (`google_falso`, com o `lote_da_ga4` respondendo o
`batchRunReports`) e os relógios da Central. As tabelas do que a GA4 "sabe"
(`VISITAS_POR_PAGINA_NA_GA4`, `VISITAS_POR_CANAL_NA_GA4` e `EVENTOS_NA_GA4`,
no apoio) foram contadas à mão, e é contra elas que as asserções conferem.
"""

from __future__ import annotations

import os
import sys
from typing import get_args

import httpx
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from central_de_comando_apoio import (  # noqa: E402
    PREFIXO_DA_CENTRAL,
    SUPER_ADMIN,
    cliente_da_central,
)

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
