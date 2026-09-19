"""A tela Dados do Google da Central de Comando pela rota real (issue #817).

O seam é a ROTA HTTP, com `require_super_admin` de pé (PRD #809, "Decisões de
teste"), como na Visão Geral. Dublados só o que é fronteira: quem está logado,
a rede do Google (`google_falso`, com o `lote_da_ga4` respondendo o
`batchRunReports`) e o relógio do dia (`hoje_da_central`, 18/09/2026). As
tabelas do que a GA4 "sabe" (`VISITANTES_POR_DIA_NA_GA4` e
`VISITAS_POR_DISPOSITIVO_NA_GA4`) foram contadas à mão, e é contra elas que as
asserções conferem: se o provedor pedisse o dia errado, a métrica errada ou a
dimensão errada, o número da resposta sairia errado.
"""

from __future__ import annotations

import os
import sys

import httpx
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from central_de_comando_apoio import HOJE_DE_TESTE, erro_da_ga4  # noqa: E402
from conftest import TentativaDeRedeNoTeste  # noqa: E402
from test_central_de_comando_visao_geral import FACILITADOR, PREFIXO, SECRETARIA, SUPER_ADMIN, _montar  # noqa: E402

from app.config import settings  # noqa: E402
from app.dependencies import _participante_ctx  # noqa: E402
from app.limiter import limiter  # noqa: E402
from app.services.central_de_comando import provedor_google  # noqa: E402
from app.services.central_de_comando.dados_do_google import percentuais_que_somam_100  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


@pytest.fixture(autouse=True)
def _reset_participante_ctx():
    _participante_ctx.set(None)
    yield
    _participante_ctx.set(None)


@pytest.fixture(autouse=True)
def _central_no_dia_de_teste(hoje_da_central, central_configurada):
    """Todo teste daqui vive em 18/09/2026, com a Central ligada ao Google."""


def _dados_do_google(periodo: str | None = None, logado: dict | None = SUPER_ADMIN) -> httpx.Response:
    params = {"periodo": periodo} if periodo is not None else None
    return _montar(logado).get(f"{PREFIXO}/dados-do-google", params=params)


# ─── Visitantes por dia ──────────────────────────────────────────────────────


@pytest.mark.usefixtures("lote_da_ga4")
class TestVisitantesPorDia:
    def test_cobre_todos_os_dias_do_periodo_inclusive_o_dia_sem_visita(self):
        """7 dias: 11/09 a 17/09. O dia 13 não teve visita e a GA4 não o
        devolve; na tela ele existe, com zero, em vez de sumir do gráfico."""
        resposta = _dados_do_google("7d")

        assert resposta.status_code == 200, resposta.text
        movimento = resposta.json()["movimento"]
        assert [dia["data"] for dia in movimento] == [
            "2026-09-11",
            "2026-09-12",
            "2026-09-13",
            "2026-09-14",
            "2026-09-15",
            "2026-09-16",
            "2026-09-17",
        ]
        assert [dia["visitantes"] for dia in movimento] == [410, 385, 0, 520, 498, 471, 402]

    def test_cada_dia_vem_ao_lado_do_dia_correspondente_do_periodo_anterior(self):
        """Porte de `mapVisitorsByDay` ("alinha por índice"): o 1º dia do
        período ao lado do 1º do anterior (04/09 a 10/09), e assim por diante."""
        movimento = _dados_do_google("7d").json()["movimento"]

        assert [(dia["data_anterior"], dia["visitantes_anterior"]) for dia in movimento] == [
            ("2026-09-04", 350),
            ("2026-09-05", 362),
            ("2026-09-06", 298),
            ("2026-09-07", 301),
            ("2026-09-08", 455),
            ("2026-09-09", 470),
            ("2026-09-10", 441),
        ]

    def test_a_variacao_de_cada_dia_vem_pronta_contra_o_dia_do_anterior(self):
        """A conta é do backend: 410 contra 350 é alta de 17,1%; o dia sem
        visita contra 298 é queda de 100%."""
        movimento = _dados_do_google("7d").json()["movimento"]

        assert movimento[0]["variacao"] == pytest.approx(0.17142857)
        assert movimento[2]["variacao"] == pytest.approx(-1.0)

    def test_dia_do_anterior_sem_visita_nao_inventa_variacao(self):
        """90 dias: 21/06 e o dia correspondente do anterior, 23/03, não
        tiveram visita. Contra zero não há variação honesta."""
        movimento = _dados_do_google("90d").json()["movimento"]

        assert movimento[1] == {
            "data": "2026-06-21",
            "visitantes": 0,
            "data_anterior": "2026-03-23",
            "visitantes_anterior": 0,
            "variacao": None,
        }

    @pytest.mark.parametrize(
        ("periodo", "dias", "primeiro", "ultimo", "primeiro_do_anterior", "ultimo_do_anterior"),
        [
            ("7d", 7, ("2026-09-11", 410), ("2026-09-17", 402), ("2026-09-04", 350), ("2026-09-10", 441)),
            ("28d", 28, ("2026-08-21", 300), ("2026-09-17", 402), ("2026-07-24", 250), ("2026-08-20", 333)),
            ("90d", 90, ("2026-06-20", 120), ("2026-09-17", 402), ("2026-03-22", 95), ("2026-06-19", 101)),
        ],
    )
    def test_cada_periodo_traz_um_item_por_dia_do_periodo(
        self, periodo, dias, primeiro, ultimo, primeiro_do_anterior, ultimo_do_anterior
    ):
        movimento = _dados_do_google(periodo).json()["movimento"]

        assert len(movimento) == dias
        assert (movimento[0]["data"], movimento[0]["visitantes"]) == primeiro
        assert (movimento[-1]["data"], movimento[-1]["visitantes"]) == ultimo
        assert (movimento[0]["data_anterior"], movimento[0]["visitantes_anterior"]) == primeiro_do_anterior
        assert (movimento[-1]["data_anterior"], movimento[-1]["visitantes_anterior"]) == ultimo_do_anterior

    def test_periodo_sem_visita_nenhuma_tem_todos_os_dias_com_zero(self, lote_da_ga4):
        """A GA4 respondeu que ninguém veio: 7 dias com zero, e não uma lista
        vazia que a tela leria como "sem dado"."""
        lote_da_ga4.visitantes_por_dia = {}

        movimento = _dados_do_google("7d").json()["movimento"]

        assert [dia["visitantes"] for dia in movimento] == [0] * 7
        assert [dia["visitantes_anterior"] for dia in movimento] == [0] * 7


# ─── Por dispositivo ─────────────────────────────────────────────────────────


@pytest.mark.usefixtures("lote_da_ga4")
class TestPorDispositivo:
    def test_as_visitas_de_cada_dispositivo_com_rotulo_em_portugues_e_percentual(self):
        """28 dias: 7.100 Visitas no celular, 2.300 no computador e 600 no
        tablet, de 10.000. O líder vem primeiro."""
        assert _dados_do_google("28d").json()["dispositivos"] == [
            {"chave": "celular", "rotulo": "Celular", "visitas": 7100, "percentual": 71},
            {"chave": "computador", "rotulo": "Computador", "visitas": 2300, "percentual": 23},
            {"chave": "tablet", "rotulo": "Tablet", "visitas": 600, "percentual": 6},
        ]

    def test_categoria_que_a_central_nao_conhece_fica_de_fora_e_nao_mostra_termo_da_fonte(self):
        """As 3 Visitas numa smart tv ficam de fora, como na Central antiga
        (`mapDeviceBreakdown`): nenhum termo da GA4 chega à tela, e as fatias
        somam 100% entre as três categorias."""
        corpo = _dados_do_google("28d").json()

        assert {d["chave"] for d in corpo["dispositivos"]} == {"celular", "computador", "tablet"}
        for termo_da_fonte in ("mobile", "desktop", "smart tv"):
            assert termo_da_fonte not in str(corpo["dispositivos"])

    @pytest.mark.parametrize("periodo", ["7d", "28d", "90d"])
    def test_os_percentuais_somam_100(self, periodo):
        assert sum(d["percentual"] for d in _dados_do_google(periodo).json()["dispositivos"]) == 100

    def test_os_percentuais_somam_100_mesmo_quando_o_arredondamento_de_cada_um_nao_fecharia(self, lote_da_ga4):
        """Um terço para cada: arredondar cada fatia daria 33 + 33 + 33 = 99. O
        ponto que sobra vai para quem ficou mais perto de subir (empate: a
        ordem da tela)."""
        lote_da_ga4.visitas_por_dispositivo[("2026-09-11", "2026-09-17")] = {"mobile": 1, "desktop": 1, "tablet": 1}

        dispositivos = _dados_do_google("7d").json()["dispositivos"]

        assert [(d["chave"], d["percentual"]) for d in dispositivos] == [
            ("celular", 34),
            ("computador", 33),
            ("tablet", 33),
        ]

    def test_dispositivo_sem_visita_no_periodo_nao_aparece(self):
        """7 dias: ninguém de tablet. A fatia vazia não entra na rosca."""
        assert _dados_do_google("7d").json()["dispositivos"] == [
            {"chave": "celular", "rotulo": "Celular", "visitas": 1850, "percentual": 74},
            {"chave": "computador", "rotulo": "Computador", "visitas": 640, "percentual": 26},
        ]

    def test_o_mais_usado_vem_primeiro(self):
        """90 dias: o computador na frente do celular."""
        dispositivos = _dados_do_google("90d").json()["dispositivos"]

        assert [(d["chave"], d["visitas"], d["percentual"]) for d in dispositivos] == [
            ("computador", 12000, 50),
            ("celular", 11000, 46),
            ("tablet", 1000, 4),
        ]

    def test_periodo_sem_visita_nenhuma_nao_tem_dispositivo_nenhum(self, lote_da_ga4):
        """A GA4 respondeu que ninguém veio: lista vazia, e a tela diz que não
        há dado de dispositivo, sem rosca de zeros."""
        lote_da_ga4.visitas_por_dispositivo = {}

        assert _dados_do_google("28d").json()["dispositivos"] == []

    def test_a_mesma_categoria_em_mais_de_uma_linha_soma(self, lote_da_ga4):
        """Porte de "somando por chave" (`mapDeviceBreakdown`)."""
        lote_da_ga4.perguntas.insert(0, _dispositivos_em_duas_linhas)

        dispositivos = _dados_do_google("7d").json()["dispositivos"]

        assert [(d["chave"], d["visitas"]) for d in dispositivos] == [("celular", 150), ("computador", 50)]


class TestPercentuaisQueSomam100:
    """A regra pura das fatias da rosca, direto, sem rota (PRD #809, "regras
    puras testadas direto"). Os esperados foram contados à mão."""

    @pytest.mark.parametrize(
        ("valores", "esperado"),
        [
            ([7100, 2300, 600], [71, 23, 6]),
            # 33,3 cada: o ponto que falta vai para o primeiro da lista.
            ([1, 1, 1], [34, 33, 33]),
            # 70,5 e 24,5 empatam no resto; o ponto vai para o que vem antes.
            ([705, 245, 50], [71, 24, 5]),
            # 74,3 e 25,7: o 25,7 é o que mais perto fica de subir.
            ([1850, 640], [74, 26]),
            # 0,5%: a fatia fica com 0 ponto, e a tela escreve "<1%".
            ([995, 5], [100, 0]),
            ([42], [100]),
        ],
    )
    def test_os_pontos_percentuais_somam_100(self, valores, esperado):
        assert percentuais_que_somam_100(valores) == esperado

    @pytest.mark.parametrize("valores", [[], [0, 0, 0]])
    def test_sem_total_tudo_e_zero(self, valores):
        assert percentuais_que_somam_100(valores) == [0] * len(valores)


def _dispositivos_em_duas_linhas(pedido: dict) -> dict | None:
    """Uma GA4 que devolve o celular em duas linhas (100 e 50)."""
    if pedido.get("dimensions") != [{"name": "deviceCategory"}]:
        return None
    return {
        "rows": [
            {"dimensionValues": [{"value": "mobile"}], "metricValues": [{"value": "100"}]},
            {"dimensionValues": [{"value": "desktop"}], "metricValues": [{"value": "50"}]},
            {"dimensionValues": [{"value": "mobile"}], "metricValues": [{"value": "50"}]},
        ]
    }


@pytest.mark.usefixtures("lote_da_ga4")
class TestPeriodo:
    def test_o_periodo_diz_as_datas_do_periodo_e_do_anterior(self):
        assert _dados_do_google("28d").json()["periodo"] == {
            "chave": "28d",
            "dias": 28,
            "atual": {"inicio": "2026-08-21", "fim": "2026-09-17"},
            "anterior": {"inicio": "2026-07-24", "fim": "2026-08-20"},
        }

    def test_sem_periodo_vale_o_de_28_dias(self):
        corpo = _dados_do_google(None).json()

        assert corpo["periodo"]["chave"] == "28d"
        assert len(corpo["movimento"]) == 28

    @pytest.mark.parametrize("periodo", ["30d", "7", "", "ano"])
    def test_periodo_que_nao_existe_e_recusado_sem_consultar_o_google(self, google_falso, periodo):
        assert _dados_do_google(periodo).status_code == 422
        assert google_falso.pedidos == []

    def test_a_tela_inteira_sai_de_uma_ida_so_ao_google(self, google_falso, lote_da_ga4):
        """Os relatórios da tela vão juntos, num `batchRunReports`: uma espera
        pela GA4 por leitura, e não uma por relatório, em série."""
        _dados_do_google("28d")

        assert len(google_falso.pedidos) == 1
        assert google_falso.pedidos[0].url.path.endswith(":batchRunReports")
        assert len(lote_da_ga4.lotes) == 1


# ─── Frescor e Atualizar agora: o cache da #815 vale para a tela ─────────────


@pytest.mark.usefixtures("lote_da_ga4")
class TestFrescor:
    def test_o_payload_diz_de_quando_sao_os_numeros(self, relogio_da_central):
        assert _dados_do_google("28d").json()["frescor"] == {
            "atualizado_em": "2026-09-18T13:45:00+00:00",
            "atualizacao_falhou": False,
            "motivo": None,
        }

    def test_segunda_leitura_dentro_da_hora_nao_vai_ao_google(self, google_falso, lote_da_ga4, relogio_da_central):
        cliente = _montar(SUPER_ADMIN)
        primeira = cliente.get(f"{PREFIXO}/dados-do-google", params={"periodo": "28d"}).json()
        lote_da_ga4.visitantes_por_dia["2026-09-17"] = 999
        relogio_da_central.avancar(minutes=59)

        segunda = cliente.get(f"{PREFIXO}/dados-do-google", params={"periodo": "28d"}).json()

        assert segunda == primeira
        assert len(google_falso.pedidos) == 1

    def test_trocar_o_periodo_troca_os_dois_blocos(self, google_falso, relogio_da_central):
        """A chave do cache é tela e período: os 7 dias guardados não
        respondem pelos 90, e os dois blocos mudam juntos."""
        cliente = _montar(SUPER_ADMIN)
        de_7_dias = cliente.get(f"{PREFIXO}/dados-do-google", params={"periodo": "7d"}).json()

        de_90_dias = cliente.get(f"{PREFIXO}/dados-do-google", params={"periodo": "90d"}).json()

        assert (len(de_7_dias["movimento"]), len(de_90_dias["movimento"])) == (7, 90)
        assert [d["chave"] for d in de_7_dias["dispositivos"]] == ["celular", "computador"]
        assert [d["chave"] for d in de_90_dias["dispositivos"]] == ["computador", "celular", "tablet"]
        assert len(google_falso.pedidos) == 2

    def test_atualizar_agora_renova_os_dois_blocos_e_o_carimbo(self, google_falso, lote_da_ga4, relogio_da_central):
        """A tela ganha o Atualizar agora pela rota genérica da #815, sem rota
        nova: vai ao Google mesmo dentro da hora e troca os dois blocos."""
        cliente = _montar(SUPER_ADMIN)
        cliente.get(f"{PREFIXO}/dados-do-google", params={"periodo": "7d"})
        lote_da_ga4.visitantes_por_dia["2026-09-17"] = 999
        lote_da_ga4.visitas_por_dispositivo[("2026-09-11", "2026-09-17")] = {"mobile": 1, "desktop": 3}
        relogio_da_central.avancar(minutes=5)

        resposta = cliente.post(f"{PREFIXO}/atualizar-agora", params={"tela": "dados-do-google", "periodo": "7d"})

        assert resposta.status_code == 200, resposta.text
        corpo = resposta.json()
        assert corpo["movimento"][-1]["visitantes"] == 999
        assert [(d["chave"], d["percentual"]) for d in corpo["dispositivos"]] == [("computador", 75), ("celular", 25)]
        assert corpo["frescor"]["atualizado_em"] == "2026-09-18T13:50:00+00:00"
        assert len(google_falso.pedidos) == 2

    def test_google_fora_com_numero_guardado_mostra_o_ultimo_valor_bom(self, google_falso, relogio_da_central):
        cliente = _montar(SUPER_ADMIN)
        cliente.get(f"{PREFIXO}/dados-do-google", params={"periodo": "28d"})
        relogio_da_central.avancar(hours=2)
        google_falso.forcar = erro_da_ga4(503, "UNAVAILABLE", "The service is currently unavailable.")

        resposta = cliente.get(f"{PREFIXO}/dados-do-google", params={"periodo": "28d"})

        assert resposta.status_code == 200, resposta.text
        corpo = resposta.json()
        assert corpo["movimento"][-1]["visitantes"] == 402
        assert corpo["dispositivos"][0]["visitas"] == 7100
        assert corpo["frescor"] == {
            "atualizado_em": "2026-09-18T13:45:00+00:00",
            "atualizacao_falhou": True,
            "motivo": "O Google Analytics respondeu HTTP 503.",
        }


# ─── A honestidade do dado: sem credencial e Google fora ─────────────────────


class TestSemCredencial:
    def test_falta_configurar_e_503_sem_numero_nem_ida_ao_google(self, monkeypatch, google_falso):
        monkeypatch.setattr(settings, "ga4_property_id", "")
        monkeypatch.setattr(settings, "google_application_credentials_json", "")

        resposta = _dados_do_google("28d")

        assert resposta.status_code == 503
        assert set(resposta.json()) == {"detail"}
        assert "GA4_PROPERTY_ID" in resposta.json()["detail"]
        assert "GOOGLE_APPLICATION_CREDENTIALS_JSON" in resposta.json()["detail"]
        assert google_falso.pedidos == []


@pytest.mark.usefixtures("lote_da_ga4")
class TestGoogleFalhou:
    @pytest.mark.parametrize(
        ("resposta_do_google", "trecho"),
        [
            (erro_da_ga4(500, "INTERNAL", "Internal error encountered."), "HTTP 500"),
            (erro_da_ga4(429, "RESOURCE_EXHAUSTED", "Exhausted property tokens."), "Tente de novo"),
            (erro_da_ga4(403, "PERMISSION_DENIED", "User does not have sufficient permissions."), "Leitor"),
            (httpx.Response(200, content=b"<html>proxy</html>"), "ilegível"),
            (httpx.Response(200, json=["nao", "e", "lote"]), "fora do formato"),
            (httpx.Response(200, json={}), "fora do formato"),
            (httpx.Response(200, json={"kind": "analyticsData#runReport", "rows": []}), "fora do formato"),
            (
                httpx.Response(
                    200,
                    json={"kind": "analyticsData#batchRunReports", "reports": [{"kind": "analyticsData#runReport"}]},
                ),
                "fora do formato",
            ),
        ],
        ids=["500", "429", "403", "html", "lista", "vazio", "kind-do-relatorio", "relatorio-a-menos"],
    )
    def test_resposta_ruim_do_google_e_502_com_a_frase_e_sem_numero(self, google_falso, resposta_do_google, trecho):
        """Sem número guardado, a falha é 502 com a frase. Um `{}` de proxy, ou
        um lote com relatório a menos, nunca vira "ninguém veio"."""
        google_falso.forcar = resposta_do_google

        resposta = _dados_do_google("28d")

        assert resposta.status_code == 502
        assert trecho in resposta.json()["detail"]
        assert set(resposta.json()) == {"detail"}

    @pytest.mark.parametrize(
        ("falha", "trecho"),
        [
            (httpx.ReadTimeout("lento demais"), "tempo esperado"),
            (httpx.ConnectError("rede fora"), "Não foi possível falar"),
        ],
        ids=["timeout", "rede-fora"],
    )
    def test_google_que_nao_responde_e_502(self, google_falso, falha, trecho):
        google_falso.forcar = falha

        resposta = _dados_do_google("28d")

        assert resposta.status_code == 502
        assert trecho in resposta.json()["detail"]

    def test_linha_sem_metrica_e_resposta_fora_do_formato(self, lote_da_ga4):
        lote_da_ga4.perguntas.insert(0, _dia_sem_metrica)

        resposta = _dados_do_google("7d")

        assert resposta.status_code == 502
        assert "fora do formato" in resposta.json()["detail"]

    def test_valor_que_nao_e_numero_vira_zero_e_nunca_nan(self, lote_da_ga4):
        """Porte do `num` de `ga4-mappers.ts`: anomalia da GA4 nunca chega à
        tela como NaN."""
        lote_da_ga4.perguntas.insert(0, _dia_com_valor_que_nao_e_numero)

        movimento = _dados_do_google("7d").json()["movimento"]

        assert movimento[0]["visitantes"] == 0

    def test_dia_que_nao_se_le_fica_de_fora_e_o_dia_fica_com_zero(self, lote_da_ga4):
        """Como na Central antiga: a linha com um dia ilegível não entra, e
        nenhum dia do período some por causa dela."""
        lote_da_ga4.perguntas.insert(0, _dia_ilegivel)

        movimento = _dados_do_google("7d").json()["movimento"]

        assert [dia["visitantes"] for dia in movimento] == [410, 0, 0, 0, 0, 0, 0]


def _so_o_periodo_de_7_dias(pedido: dict) -> bool:
    return pedido.get("dimensions") == [{"name": "date"}] and pedido["dateRanges"][0]["startDate"] == "2026-09-11"


def _dia_sem_metrica(pedido: dict) -> dict | None:
    if not _so_o_periodo_de_7_dias(pedido):
        return None
    return {"rows": [{"dimensionValues": [{"value": "20260911"}]}]}


def _dia_com_valor_que_nao_e_numero(pedido: dict) -> dict | None:
    if not _so_o_periodo_de_7_dias(pedido):
        return None
    return {"rows": [{"dimensionValues": [{"value": "20260911"}], "metricValues": [{"value": "(not set)"}]}]}


def _dia_ilegivel(pedido: dict) -> dict | None:
    if not _so_o_periodo_de_7_dias(pedido):
        return None
    return {
        "rows": [
            {"dimensionValues": [{"value": "20260911"}], "metricValues": [{"value": "410"}]},
            {"dimensionValues": [{"value": "(other)"}], "metricValues": [{"value": "77"}]},
        ]
    }


# ─── O lote: mais de 5 relatórios ────────────────────────────────────────────


@pytest.mark.usefixtures("lote_da_ga4")
class TestPerguntasEmLote:
    """O `perguntar` do provedor, direto: é a porta que a #818 usa para pôr
    mais blocos na mesma tela. A GA4 recusa lote de mais de 5 relatórios (o
    dublê responde 400, como ela), então 7 relatórios só dão certo em mais de
    um lote."""

    def test_mais_de_5_relatorios_respondem_todos_na_ordem_das_perguntas(self):
        de_7, de_28, de_90, dispositivos = provedor_google.perguntar(
            provedor_google.movimento_diario("7d", HOJE_DE_TESTE),
            provedor_google.movimento_diario("28d", HOJE_DE_TESTE),
            provedor_google.movimento_diario("90d", HOJE_DE_TESTE),
            provedor_google.visitas_por_dispositivo("7d", HOJE_DE_TESTE),
        )

        assert [len(m.atual) for m in (de_7, de_28, de_90)] == [7, 28, 90]
        assert de_7.atual[0].visitantes == 410
        assert de_28.anterior[0].visitantes == 250
        assert de_90.anterior[-1].visitantes == 101
        assert [(d.dispositivo, d.visitas) for d in dispositivos] == [("celular", 1850), ("computador", 640)]

    def test_o_lote_nao_espera_o_google_para_sempre(self, google_falso):
        _dados_do_google("28d")

        assert google_falso.clientes, "o provedor não criou cliente nenhum"
        for kwargs in google_falso.clientes:
            timeout = kwargs.get("timeout")
            assert isinstance(timeout, httpx.Timeout)
            assert timeout.read is not None and timeout.read <= 10
            assert timeout.connect is not None and timeout.connect <= 5


class TestTravaDeRede:
    def test_sem_o_duble_o_lote_bate_na_trava_da_suite(self):
        """Sem o `google_falso`, o lote sairia de verdade para a GA4: a trava de
        `tests/conftest.py` pega antes do primeiro pacote."""
        with pytest.raises(TentativaDeRedeNoTeste) as erro:
            provedor_google.perguntar(provedor_google.visitas_por_dispositivo("28d", HOJE_DE_TESTE))

        assert "analyticsdata.googleapis.com" in str(erro.value)


# ─── O gate: só Super admin ──────────────────────────────────────────────────


@pytest.mark.usefixtures("lote_da_ga4")
class TestSoSuperAdmin:
    @pytest.mark.parametrize("persona", [SECRETARIA, FACILITADOR], ids=["secretaria", "facilitador"])
    def test_quem_nao_e_super_admin_leva_403_sem_gastar_consulta_no_google(self, google_falso, persona):
        assert _dados_do_google("28d", logado=persona).status_code == 403
        assert google_falso.pedidos == []

    def test_anonimo_leva_401(self, google_falso):
        assert _dados_do_google("28d", logado=None).status_code == 401
        assert google_falso.pedidos == []

    def test_o_atualizar_agora_da_tela_tambem_e_so_do_super_admin(self, google_falso):
        resposta = _montar(SECRETARIA).post(
            f"{PREFIXO}/atualizar-agora", params={"tela": "dados-do-google", "periodo": "28d"}
        )

        assert resposta.status_code == 403
        assert google_falso.pedidos == []
