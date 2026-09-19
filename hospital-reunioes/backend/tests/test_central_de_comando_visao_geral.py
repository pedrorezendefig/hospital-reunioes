"""A Visão Geral da Central de Comando pela rota real (issue #814, ADR 0058).

O seam é a ROTA HTTP, com `require_super_admin` de pé (PRD #809, "Decisões de
teste"). Só três coisas são dubladas:

* `get_current_user` e o cliente Supabase, que dizem quem está logado;
* a fronteira de rede do provedor do Google: o `httpx.Client` ganha um
  transporte de mentira (`httpx.MockTransport`), e todo o resto roda de
  verdade, inclusive a assinatura do JWT da service account.

O Google de mentira, a service account de mentira e o app mínimo com o gate
(`cliente_da_central` e as pessoas) moram em `tests/central_de_comando_apoio.py`,
compartilhados com as fatias seguintes da Central. O dublê responde como a GA4
Data API responderia: confere a assinatura
do token com a chave pública da service account do teste, a propriedade no
caminho e devolve os `activeUsers` do intervalo pedido. Por isso as asserções
olham só o que a rota devolve: se o provedor pedisse o intervalo errado ou a
métrica errada, o número da resposta sairia errado.

A chave RSA é gerada a cada execução: nenhuma credencial de verdade entra em
arquivo. E nenhum teste fala com o Google: a trava de rede da suíte
(`tests/conftest.py`) segue de pé, e o último bloco prova que ela pega o
provedor quando o dublê falta.

Porte dos testes de `src/lib/analytics` do repositório antigo que cabem nesta
fatia: `ga4-provider.test.ts` (Visitantes atual e anterior, erro propagado),
`ga4-mappers.test.ts` (`firstMetric`), `get-provider.test.ts` (credencial
exige propriedade E chave) e `overview.test.ts` (o resumo por período).
"""

from __future__ import annotations

import json
import os
import re
import sys

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from central_de_comando_apoio import (  # noqa: E402
    FACILITADOR,
    HOJE_DE_TESTE,
    PROPRIEDADE_DE_TESTE,
    SECRETARIA,
    SUPER_ADMIN,
    cliente_da_central,
    erro_da_ga4,
    pem_da_chave_privada,
    pessoa,
)
from central_de_comando_apoio import PREFIXO_DA_CENTRAL as PREFIXO  # noqa: E402
from conftest import TentativaDeRedeNoTeste  # noqa: E402

from app.config import settings  # noqa: E402
from app.services.central_de_comando import provedor_google  # noqa: E402

# O limitador de taxa e o participante do gate zerados antes e depois de cada
# teste (fixture de `central_de_comando_apoio.py`).
pytestmark = pytest.mark.usefixtures("gate_e_limitador_zerados")


@pytest.fixture(autouse=True)
def _hoje_fixo(hoje_da_central):
    """Todo teste deste arquivo vive no mesmo dia, o dos intervalos contados à
    mão em `VISITANTES_NA_GA4` (18/09/2026)."""


# Quem está logado e o app mínimo com o gate de pé moram em
# `central_de_comando_apoio.py` (`cliente_da_central`, `SUPER_ADMIN`, ...),
# para toda fatia da Central testar pela rota sem importar este arquivo.


def _visao_geral(periodo: str | None = None, logado: dict | None = SUPER_ADMIN) -> httpx.Response:
    params = {"periodo": periodo} if periodo is not None else None
    return cliente_da_central(logado).get(f"{PREFIXO}/visao-geral", params=params)


# ─── 1. Os Visitantes de ponta a ponta ──────────────────────────────────────


@pytest.mark.usefixtures("central_configurada")
class TestVisitantesDoPeriodo:
    def test_super_admin_recebe_os_visitantes_de_28_dias_e_do_periodo_anterior(self, google_falso):
        resposta = _visao_geral("28d")

        assert resposta.status_code == 200, resposta.text
        corpo = resposta.json()
        assert corpo["visitantes"]["atual"] == 12345
        assert corpo["visitantes"]["anterior"] == 10000
        assert corpo["visitantes"]["variacao"] == pytest.approx(0.2345)
        assert corpo["periodo"] == {
            "chave": "28d",
            "dias": 28,
            "atual": {"inicio": "2026-08-21", "fim": "2026-09-17"},
            "anterior": {"inicio": "2026-07-24", "fim": "2026-08-20"},
        }

    @pytest.mark.parametrize(
        ("periodo", "dias", "atual", "anterior", "datas_atual", "datas_anterior"),
        [
            ("7d", 7, 3100, 3350, ("2026-09-11", "2026-09-17"), ("2026-09-04", "2026-09-10")),
            ("28d", 28, 12345, 10000, ("2026-08-21", "2026-09-17"), ("2026-07-24", "2026-08-20")),
            ("90d", 90, 38412, 34174, ("2026-06-20", "2026-09-17"), ("2026-03-22", "2026-06-19")),
        ],
    )
    def test_cada_periodo_traz_os_seus_numeros_e_as_suas_datas(
        self, google_falso, periodo, dias, atual, anterior, datas_atual, datas_anterior
    ):
        corpo = _visao_geral(periodo).json()

        assert corpo["visitantes"]["atual"] == atual
        assert corpo["visitantes"]["anterior"] == anterior
        assert corpo["periodo"]["chave"] == periodo
        assert corpo["periodo"]["dias"] == dias
        assert corpo["periodo"]["atual"] == {"inicio": datas_atual[0], "fim": datas_atual[1]}
        assert corpo["periodo"]["anterior"] == {"inicio": datas_anterior[0], "fim": datas_anterior[1]}

    def test_a_variacao_negativa_vem_com_sinal(self, google_falso):
        """7 dias: 3.100 contra 3.350 é uma queda de 7,46%."""
        assert _visao_geral("7d").json()["visitantes"]["variacao"] == pytest.approx(-0.07462686)

    def test_sem_periodo_vale_o_de_28_dias(self, google_falso):
        corpo = _visao_geral(None).json()

        assert corpo["periodo"]["chave"] == "28d"
        assert corpo["visitantes"]["atual"] == 12345

    @pytest.mark.parametrize("periodo", ["30d", "7", "", "ano"])
    def test_periodo_que_nao_existe_e_recusado_sem_consultar_o_google(self, google_falso, periodo):
        """A API é estrita; quem cai no padrão com o que se digita no endereço
        é a tela."""
        assert _visao_geral(periodo).status_code == 422
        assert google_falso.pedidos == []

    def test_periodo_anterior_sem_visitantes_nao_inventa_variacao(self, google_falso):
        """Anterior zerado: a GA4 respondeu que ninguém veio, e não existe
        variação honesta contra zero. O número atual continua de pé."""
        google_falso.visitantes = {("2026-08-21", "2026-09-17"): 500}

        corpo = _visao_geral("28d").json()

        assert corpo["visitantes"] == {"atual": 500, "anterior": 0, "variacao": None}


# ─── 3. Sem credencial: 503 de configuração, nunca zero ─────────────────────


def _config(monkeypatch, *, propriedade: str, credencial: str) -> None:
    monkeypatch.setattr(settings, "ga4_property_id", propriedade)
    monkeypatch.setattr(settings, "google_application_credentials_json", credencial)


class TestSemCredencial:
    """Porte de `get-provider.test.ts`: a credencial só existe com a
    propriedade E a chave. Lá, sem ela, entrava o provedor de demonstração com
    números inventados; aqui é 503 com o que falta (ADR 0058, decisão 2)."""

    @pytest.mark.parametrize(
        ("propriedade", "tem_chave", "faltando"),
        [
            ("", False, ["GA4_PROPERTY_ID", "GOOGLE_APPLICATION_CREDENTIALS_JSON"]),
            ("", True, ["GA4_PROPERTY_ID"]),
            (PROPRIEDADE_DE_TESTE, False, ["GOOGLE_APPLICATION_CREDENTIALS_JSON"]),
            ("   ", True, ["GA4_PROPERTY_ID"]),
        ],
        ids=["nenhuma", "sem-propriedade", "sem-chave", "propriedade-em-branco"],
    )
    def test_falta_configurar_e_503_dizendo_o_que_falta(
        self, monkeypatch, google_falso, credencial_da_central, propriedade, tem_chave, faltando
    ):
        _config(
            monkeypatch,
            propriedade=propriedade,
            credencial=json.dumps(credencial_da_central) if tem_chave else "",
        )

        resposta = _visao_geral("28d")

        assert resposta.status_code == 503
        detalhe = resposta.json()["detail"]
        for nome in faltando:
            assert nome in detalhe
        assert "configurar" in detalhe

    def test_503_nao_traz_numero_nenhum_nem_toca_a_rede(self, monkeypatch, google_falso):
        """Nunca zero: o corpo do erro não tem Visitantes, e o Google nem é
        chamado (não há o que perguntar sem a credencial)."""
        _config(monkeypatch, propriedade="", credencial="")

        corpo = _visao_geral("28d").json()

        assert set(corpo) == {"detail"}
        assert google_falso.pedidos == []

    @pytest.mark.parametrize("propriedade", ["properties/123456789", "12345 6789", "G-ABC123", "123abc"])
    def test_propriedade_que_nao_e_so_numero_e_503(self, monkeypatch, google_falso, credencial_da_central, propriedade):
        """O número entra no caminho da URL: o que não for só dígito é
        configuração errada, dita como tal, e não uma chamada ao Google."""
        _config(monkeypatch, propriedade=propriedade, credencial=json.dumps(credencial_da_central))

        resposta = _visao_geral("28d")

        assert resposta.status_code == 503
        assert "GA4_PROPERTY_ID" in resposta.json()["detail"]
        assert google_falso.pedidos == []

    @pytest.mark.parametrize(
        "conteudo",
        [
            "/caminho/para/chave.json",
            "{nao e json",
            json.dumps(["lista", "nao", "chave"]),
            json.dumps({"type": "authorized_user", "client_id": "x"}),
            json.dumps({"type": "service_account"}),
        ],
        ids=["caminho-de-arquivo", "json-quebrado", "lista", "outro-tipo", "sem-campos"],
    )
    def test_chave_que_nao_e_de_service_account_e_503(self, monkeypatch, google_falso, conteudo):
        _config(monkeypatch, propriedade=PROPRIEDADE_DE_TESTE, credencial=conteudo)

        resposta = _visao_geral("28d")

        assert resposta.status_code == 503
        assert "GOOGLE_APPLICATION_CREDENTIALS_JSON" in resposta.json()["detail"]
        assert google_falso.pedidos == []

    def test_chave_privada_estragada_e_503_sem_ecoar_a_chave(self, monkeypatch, google_falso, credencial_da_central):
        """O 503 diz o que está errado e nunca devolve o conteúdo da chave."""
        estragada = {
            **credencial_da_central,
            "private_key": "-----BEGIN PRIVATE KEY-----\nSEGREDO-QUEBRADO\n-----END PRIVATE KEY-----\n",
        }
        _config(monkeypatch, propriedade=PROPRIEDADE_DE_TESTE, credencial=json.dumps(estragada))

        resposta = _visao_geral("28d")

        assert resposta.status_code == 503
        assert "SEGREDO-QUEBRADO" not in resposta.text
        assert google_falso.pedidos == []


# ─── 4. A fonte falhou: 502, nunca zero ─────────────────────────────────────


@pytest.mark.usefixtures("central_configurada")
class TestGoogleFalhou:
    """Porte de "propaga erro do client" (`ga4-provider.test.ts`): o erro sobe
    do provedor e, sem número guardado no cache (o `google_falso` o entrega
    vazio), a rota responde 502 com a frase. Com número guardado, é o último
    valor bom: `test_central_de_comando_frescor.py` (#815)."""

    @pytest.mark.parametrize(
        ("resposta_do_google", "trecho"),
        [
            (erro_da_ga4(500, "INTERNAL", "Internal error encountered."), "HTTP 500"),
            (erro_da_ga4(503, "UNAVAILABLE", "The service is currently unavailable."), "HTTP 503"),
            (erro_da_ga4(429, "RESOURCE_EXHAUSTED", "Exhausted property tokens."), "Tente de novo"),
            (httpx.Response(200, content=b"<html>proxy</html>"), "ilegível"),
            (httpx.Response(200, json=["nao", "e", "relatorio"]), "fora do formato"),
            (
                httpx.Response(200, json={"kind": "analyticsData#runReport", "rows": [{"dimensionValues": []}]}),
                "fora do formato",
            ),
        ],
        ids=["500", "503", "429", "html", "lista", "linha-sem-metrica"],
    )
    def test_resposta_ruim_do_google_e_502_com_a_frase(self, google_falso, resposta_do_google, trecho):
        google_falso.forcar = resposta_do_google

        resposta = _visao_geral("28d")

        assert resposta.status_code == 502
        assert trecho in resposta.json()["detail"]
        assert "visitantes" not in resposta.json()

    @pytest.mark.parametrize(
        "corpo",
        [{}, {"rowCount": 0}, {"rows": []}, {"kind": "analyticsData#runRealtimeReport"}],
        ids=["vazio", "so-contagem", "linhas-vazias", "outro-kind"],
    )
    def test_resposta_que_nao_e_relatorio_da_ga4_nunca_vira_zero(self, google_falso, corpo):
        """Um `{}` de proxy ou de página de erro não é "ninguém veio": só o
        relatório da GA4 (`kind` "analyticsData#runReport") sem `rows` é o zero
        honesto. O resto é resposta fora do formato, 502."""
        google_falso.forcar = httpx.Response(200, json=corpo)

        resposta = _visao_geral("28d")

        assert resposta.status_code == 502
        assert "fora do formato" in resposta.json()["detail"]

    @pytest.mark.parametrize(
        ("falha", "trecho"),
        [
            (httpx.ReadTimeout("lento demais"), "tempo esperado"),
            (httpx.ConnectTimeout("sem conexão"), "tempo esperado"),
            (httpx.ConnectError("rede fora"), "Não foi possível falar"),
        ],
        ids=["timeout-de-leitura", "timeout-de-conexao", "rede-fora"],
    )
    def test_google_que_nao_responde_e_502(self, google_falso, falha, trecho):
        google_falso.forcar = falha

        resposta = _visao_geral("28d")

        assert resposta.status_code == 502
        assert trecho in resposta.json()["detail"]

    def test_propriedade_sem_acesso_e_502_que_manda_conferir_o_papel_de_leitor(self, monkeypatch, google_falso):
        """A GA4 responde 403 para propriedade em que a service account não
        tem papel: é o erro mais provável da conferência com a credencial real,
        e a frase diz onde olhar."""
        monkeypatch.setattr(settings, "ga4_property_id", "999999999")

        resposta = _visao_geral("28d")

        assert resposta.status_code == 502
        assert "Leitor" in resposta.json()["detail"]

    def test_chave_de_outra_service_account_e_recusada_pelo_google(
        self, monkeypatch, google_falso, credencial_da_central
    ):
        """Assinatura que o Google não reconhece: 401 lá, 502 aqui, com a
        mesma frase de conferir o acesso."""
        outra_chave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        credencial_de_outra = {**credencial_da_central, "private_key": pem_da_chave_privada(outra_chave)}
        monkeypatch.setattr(settings, "google_application_credentials_json", json.dumps(credencial_de_outra))

        resposta = _visao_geral("28d")

        assert resposta.status_code == 502
        assert "HTTP 401" in resposta.json()["detail"]


@pytest.mark.usefixtures("central_configurada")
class TestPrimeiraMetrica:
    """Porte de `firstMetric` (`ga4-mappers.test.ts`), pela rota."""

    def test_intervalo_sem_dado_e_zero_de_verdade(self, google_falso):
        """A GA4 omite `rows` quando ninguém veio: é resposta, e zero é o
        número honesto (diferente do 503, em que ninguém perguntou)."""
        google_falso.visitantes = {}

        resposta = _visao_geral("28d")

        assert resposta.status_code == 200
        assert resposta.json()["visitantes"] == {"atual": 0, "anterior": 0, "variacao": None}

    def test_valor_que_nao_e_numero_vira_zero_e_nunca_nan(self, google_falso):
        google_falso.forcar = httpx.Response(
            200,
            json={"kind": "analyticsData#runReport", "rows": [{"metricValues": [{"value": "(not set)"}]}]},
        )

        resposta = _visao_geral("28d")

        assert resposta.status_code == 200
        assert resposta.json()["visitantes"]["atual"] == 0


# ─── 5. Nenhum teste fala com o Google ──────────────────────────────────────


@pytest.mark.usefixtures("central_configurada")
class TestTravaDeRede:
    def test_sem_o_duble_o_provedor_bate_na_trava_da_suite(self):
        """Sem a fixture `google_falso`, a chamada sairia de verdade para a
        GA4. A trava de `tests/conftest.py` pega antes do primeiro pacote, e é
        isso que garante que nenhum teste da Central fala com o Google."""
        with pytest.raises(TentativaDeRedeNoTeste) as erro:
            provedor_google.visitantes_comparados("28d", HOJE_DE_TESTE)

        assert "analyticsdata.googleapis.com" in str(erro.value)

    def test_o_provedor_nao_espera_o_google_para_sempre(self, google_falso):
        """Timeout curto no cliente (padrão da casa): erro honesto em segundos
        vale mais que tela pendurada."""
        _visao_geral("28d")

        assert google_falso.clientes, "o provedor não criou cliente nenhum"
        for kwargs in google_falso.clientes:
            timeout = kwargs.get("timeout")
            assert isinstance(timeout, httpx.Timeout)
            assert timeout.read is not None and timeout.read <= 10
            assert timeout.connect is not None and timeout.connect <= 5


# ─── 2. O gate: só Super admin ──────────────────────────────────────────────


def _rotas_da_central() -> list[tuple[str, str]]:
    """Toda rota da Central que o app REAL publica, pelo schema OpenAPI.

    Varredura, e não lista cravada: o gate está no router, e uma rota
    acrescentada por uma fatia seguinte entra aqui sozinha. A fonte é o schema
    e não `app.routes`, que volta quase vazia desde o FastAPI 0.141 (issues
    #542 e #546). O cache do schema volta como estava, para não envelhecer o
    schema de quem acrescenta rota ao app real depois (mesmo cuidado do
    `test_admin_tecnologia.py`).
    """
    from app.main import app

    cache = app.openapi_schema
    try:
        caminhos = app.openapi()["paths"]
    finally:
        app.openapi_schema = cache

    return sorted(
        (metodo.upper(), re.sub(r"\{[^}]+\}", "qualquer", caminho))
        for caminho, operacoes in caminhos.items()
        if caminho.startswith(PREFIXO)
        for metodo in operacoes
    )


ROTAS = _rotas_da_central()


def test_a_varredura_enxerga_as_rotas_da_central_no_app_real():
    """Controle antes da matriz: varredura vazia passaria em "toda rota leva
    403" sem olhar rota nenhuma. Também prova que o router está registrado no
    `main.py`. Fatia que acrescentar rota à Central entra na matriz sozinha."""
    assert ("GET", f"{PREFIXO}/visao-geral") in ROTAS


@pytest.mark.usefixtures("central_configurada", "google_falso")
class TestSoSuperAdmin:
    @pytest.mark.parametrize("metodo,caminho", ROTAS)
    @pytest.mark.parametrize("persona", [SECRETARIA, FACILITADOR], ids=["secretaria", "facilitador"])
    def test_quem_nao_e_super_admin_leva_403(self, persona, metodo, caminho):
        assert cliente_da_central(persona).request(metodo, caminho).status_code == 403

    @pytest.mark.parametrize("metodo,caminho", ROTAS)
    def test_anonimo_leva_401(self, metodo, caminho):
        assert cliente_da_central(None).request(metodo, caminho).status_code == 401

    @pytest.mark.parametrize("metodo,caminho", ROTAS)
    def test_super_admin_passa_pelo_gate(self, metodo, caminho):
        """O par de presença: sem ele, um 403 cravado em toda rota passaria
        pelos dois testes de cima. O que se mede é o gate: rota de fatia
        seguinte que exija corpo pode responder 422 aqui, nunca 401 ou 403."""
        assert cliente_da_central(SUPER_ADMIN).request(metodo, caminho).status_code not in (401, 403)

    def test_super_admin_desligado_leva_403(self):
        """Sessão viva de quem foi desligado não abre os números (issue #309)."""
        desligado = pessoa("super", "super_admin", ativo=False)
        cliente = cliente_da_central(desligado, participantes=[desligado])

        assert cliente.get(f"{PREFIXO}/visao-geral").status_code == 403

    def test_quem_nao_passa_no_gate_nao_gasta_consulta_no_google(self, google_falso):
        """O gate responde antes de a fonte ser tocada."""
        cliente_da_central(SECRETARIA).get(f"{PREFIXO}/visao-geral")
        cliente_da_central(None).get(f"{PREFIXO}/visao-geral")

        assert google_falso.pedidos == []
