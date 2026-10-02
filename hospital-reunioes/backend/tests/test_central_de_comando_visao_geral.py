"""A Visão Geral da Central de Comando, completa e por bloco (issue #821, ADR 0058).

O seam é a ROTA HTTP, com `require_super_admin` de pé (PRD #809). A Visão Geral
lê as DUAS fontes (Google e Instagram) numa leitura só, então o transporte de
mentira daqui despacha pelo host, como na galeria de Objetivos (#820): um teste
não pode instalar os dois `httpx.Client` de mentira do apoio ao mesmo tempo.
Todo o resto (provedores, cache, gate) roda de verdade; só a rede e quem está
logado são dublados.

**A mudança da #821: status por bloco.** Até aqui a tela era tudo ou nada (uma
falha do Google virava 502/503 da tela inteira). Agora cada um dos blocos de
fonte degrada sozinho: se a fonte de um bloco falha, o bloco mostra o estado
honesto (`sem-dado` ou `nao-configurado`), e os outros seguem. A rota responde
200 com o payload inteiro; o erro mora dentro do bloco, nunca derruba a tela.

Os blocos de fonte do payload:

- `visitantes`: o número-manchete e o contexto dele (Área do site que mais atrai,
  principal Origem do público, dispositivo mais usado), do Google.
- `instagram`: o Instagram num relance (Seguidores, Alcance, Visualizações,
  Interações).
- `objetivos`: os três Objetivos em foco, com o número vivo reaproveitado dos
  dois blocos acima (zero ida extra à fonte).

Os atalhos e o "O que vem por aí" são conteúdo fixo da tela (front), não do
payload: o menu só lista o que funciona, e o roadmap é texto, não dado.
"""

from __future__ import annotations

import json
import os
import re
import sys
from types import SimpleNamespace

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from central_de_comando_apoio import (  # noqa: E402
    FACILITADOR,
    HOJE_DE_TESTE,
    HOST_DA_GRAPH_API,
    SECRETARIA,
    SUPER_ADMIN,
    TOKEN_DO_INSTAGRAM,
    VISITANTES_NA_GA4,
    GoogleFalso,
    InstagramFalso,
    LoteDaGA4,
    cliente_da_central,
    erro_da_ga4,
    erro_do_instagram,
    pem_da_chave_privada,
    pessoa,
)
from central_de_comando_apoio import PREFIXO_DA_CENTRAL as PREFIXO  # noqa: E402
from conftest import TentativaDeRedeNoTeste  # noqa: E402

from app.services.central_de_comando import provedor_google  # noqa: E402

pytestmark = pytest.mark.usefixtures("gate_e_limitador_zerados")

_28_DIAS = ("2026-08-21", "2026-09-17")


@pytest.fixture(autouse=True)
def _no_dia_de_teste(hoje_da_central):
    """Todo teste daqui vive em 18/09/2026, o dia dos intervalos do apoio."""


@pytest.fixture
def central_falsa(monkeypatch, chave_rsa_da_central, cache_da_central, central_configurada, instagram_configurado):
    """Google e Instagram de mentira no MESMO transporte, despachando pelo host.

    A Visão Geral lê as duas fontes numa leitura só, e os dublês do apoio trocam
    o `httpx.Client` inteiro (um sobrescreveria o outro). Aqui os dois convivem:
    o provedor roda de verdade, e a resposta vem do dublê da fonte certa. Devolve
    os dublês para o teste ajustar o que a fonte "sabe" ou forçar uma falha."""
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


def _visao_geral(periodo: str | None = None, logado: dict | None = SUPER_ADMIN) -> httpx.Response:
    params = {"periodo": periodo} if periodo is not None else None
    return cliente_da_central(logado).get(f"{PREFIXO}/visao-geral", params=params)


def _atualizar_agora(periodo: str = "28d", logado: dict | None = SUPER_ADMIN) -> httpx.Response:
    return cliente_da_central(logado).post(
        f"{PREFIXO}/atualizar-agora", params={"tela": "visao-geral", "periodo": periodo}
    )


# ─── 1. O número-manchete e o contexto dele (Google) ────────────────────────


class TestBlocoVisitantes:
    def test_o_numero_manchete_do_periodo_e_a_variacao(self, central_falsa):
        corpo = _visao_geral("28d").json()

        assert corpo["visitantes"]["estado"] == "ok"
        assert corpo["visitantes"]["atual"] == 12345
        assert corpo["visitantes"]["anterior"] == 10000
        assert corpo["visitantes"]["variacao"] == pytest.approx(0.2345)
        assert corpo["periodo"] == {
            "chave": "28d",
            "dias": 28,
            "atual": {"inicio": "2026-08-21", "fim": "2026-09-17"},
            "anterior": {"inicio": "2026-07-24", "fim": "2026-08-20"},
        }

    def test_o_contexto_do_numero_manchete(self, central_falsa):
        """Área do site que mais atrai, principal Origem do público e dispositivo
        mais usado, cada um do topo do seu ranking (reaproveita os Dados do
        Google, #818)."""
        contexto = _visao_geral("28d").json()["visitantes"]["contexto"]

        assert contexto["area"] == {"chave": "maternidade", "nome": "Maternidade", "visitas": 3842}
        assert contexto["origem"] == {"chave": "busca", "rotulo": "Busca no Google", "percentual": 61}
        assert contexto["dispositivo"] == {"chave": "celular", "rotulo": "Celular", "percentual": 71}

    def test_contexto_sem_dado_vem_nulo_sem_derrubar_o_numero(self, central_falsa):
        """90 dias: a GA4 de mentira não tem páginas nem canais nesse intervalo,
        então a Área e a Origem vêm nulas. O número-manchete e o dispositivo (que
        tem dado) seguem: fato sem dado é nulo, nunca inventado (ADR 0003 de lá)."""
        corpo = _visao_geral("90d").json()

        assert corpo["visitantes"]["estado"] == "ok"
        assert corpo["visitantes"]["atual"] == 38412
        assert corpo["visitantes"]["contexto"]["area"] is None
        assert corpo["visitantes"]["contexto"]["origem"] is None
        assert corpo["visitantes"]["contexto"]["dispositivo"]["chave"] == "computador"

    def test_variacao_negativa_vem_com_sinal(self, central_falsa):
        assert _visao_geral("7d").json()["visitantes"]["variacao"] == pytest.approx(-0.07462686)

    @pytest.mark.parametrize(
        "rows",
        [{}, 0, "", 5, "linhas", {"linha": 1}],
        ids=["objeto-vazio", "zero", "texto-vazio", "numero", "texto", "objeto"],
    )
    def test_rows_que_nao_e_lista_e_resposta_fora_do_formato(self, central_falsa, rows):
        """O `rows` da GA4 é uma lista de linhas, como o `_linhas` dos Dados do
        Google já confere (#834). Qualquer outra coisa no relatório dos
        Visitantes é resposta fora do formato: o bloco fica `sem-dado` com a
        frase, e não um número. Inclusive o que é "falso" sem ser lista (`{}`,
        `0`, `''`): lido como lista vazia, viraria 0 Visitantes que ninguém
        mediu."""
        central_falsa.google.respondedores.insert(0, _visitantes_com_rows(rows))

        corpo = _visao_geral("28d")

        assert corpo.status_code == 200, corpo.text
        visitantes = corpo.json()["visitantes"]
        assert visitantes["estado"] == "sem-dado"
        assert visitantes["motivo"] == "O Google Analytics devolveu um relatório fora do formato esperado."
        assert "atual" not in visitantes


def _visitantes_com_rows(rows: object):
    """Uma GA4 que devolve os Visitantes sem dimensão (o `runReport` do
    número-manchete) com o `rows` como veio aqui."""

    def responder(metodo: str, corpo: dict) -> dict | None:
        if metodo != "runReport" or corpo.get("dimensions") or corpo.get("metrics") != [{"name": "activeUsers"}]:
            return None
        return {"rows": rows}

    return responder


# ─── 2. O Instagram num relance (Instagram) ─────────────────────────────────


class TestBlocoInstagram:
    def test_os_quatro_numeros_de_relance(self, central_falsa):
        instagram = _visao_geral("28d").json()["instagram"]

        assert instagram["estado"] == "ok"
        assert instagram["seguidores"] == {"total": 18420, "crescimento": 312}
        assert instagram["alcance"] == {"atual": 41280, "variacao": pytest.approx((41280 - 37650) / 37650)}
        assert instagram["visualizacoes"] == {"atual": 96540, "variacao": pytest.approx((96540 - 88210) / 88210)}
        assert instagram["interacoes"] == {"atual": 7820, "variacao": pytest.approx((7820 - 6910) / 6910)}

    def test_em_90_dias_o_relance_usa_28_dias(self, central_falsa):
        """A Graph API entrega no máximo 30 dias; o relance de 90 dias mostra os
        28 dias, como na Central antiga, sem derrubar a tela."""
        instagram = _visao_geral("90d").json()["instagram"]

        assert instagram["estado"] == "ok"
        assert instagram["seguidores"]["total"] == 18420
        assert instagram["alcance"]["atual"] == 41280


# ─── 3. Os três Objetivos em foco (reaproveitados) ──────────────────────────


class TestBlocoObjetivos:
    def test_os_tres_objetivos_em_foco_com_o_numero_vivo(self, central_falsa):
        em_foco = {o["id"]: o for o in _visao_geral("28d").json()["objetivos"]["em_foco"]}

        assert list(em_foco) == ["site-visitantes", "instagram-seguidores", "instagram-engajamento"]
        assert em_foco["site-visitantes"]["nome"] == "Atrair mais visitantes pro site"
        assert em_foco["site-visitantes"]["numero"] == {"rotulo": "Visitantes", "valor": 12345}
        assert em_foco["instagram-seguidores"]["numero"] == {"rotulo": "Seguidores", "valor": 18420}
        assert em_foco["instagram-engajamento"]["numero"] == {"rotulo": "Interações", "valor": 7820}

    def test_objetivo_sem_a_sua_fonte_fica_sem_numero_mas_aparece(self, central_falsa):
        """O Instagram fora: os Objetivos de Instagram ficam sem número, mas o
        card continua (com nome, descrição e destino). O do site segue com número."""
        central_falsa.instagram.forcar = erro_do_instagram(500, 1, "Internal", "boom")

        em_foco = {o["id"]: o for o in _visao_geral("28d").json()["objetivos"]["em_foco"]}

        assert em_foco["site-visitantes"]["numero"] == {"rotulo": "Visitantes", "valor": 12345}
        assert em_foco["instagram-seguidores"]["numero"] is None
        assert em_foco["instagram-engajamento"]["numero"] is None
        assert em_foco["instagram-seguidores"]["nome"] == "Crescer no Instagram"


# ─── 4. Cada bloco degrada sozinho (critério de aceite 1 e 2) ───────────────


class TestDegradacaoPorBloco:
    def test_instagram_nao_configurado_mostra_o_estado_calmo_e_o_resto_segue(self, central_falsa, monkeypatch):
        """Critério 2: sem a conta do Instagram, o relance mostra o estado calmo
        (`nao-configurado`), e o resto da tela segue com os números do Google."""
        from app.config import settings

        monkeypatch.setattr(settings, "instagram_access_token", "")
        monkeypatch.setattr(settings, "instagram_business_account_id", "")

        corpo = _visao_geral("28d")

        assert corpo.status_code == 200
        corpo = corpo.json()
        assert corpo["instagram"]["estado"] == "nao-configurado"
        assert corpo["instagram"]["motivo"]
        assert corpo["visitantes"]["estado"] == "ok"
        assert corpo["visitantes"]["atual"] == 12345

    def test_google_nao_configurado_nao_derruba_o_instagram(self, central_falsa, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "ga4_property_id", "")
        monkeypatch.setattr(settings, "google_application_credentials_json", "")

        corpo = _visao_geral("28d")

        assert corpo.status_code == 200
        corpo = corpo.json()
        assert corpo["visitantes"]["estado"] == "nao-configurado"
        assert corpo["visitantes"]["motivo"] == provedor_google.FRASE_NAO_CONFIGURADO
        assert corpo["instagram"]["estado"] == "ok"
        assert corpo["instagram"]["seguidores"]["total"] == 18420

    def test_google_fora_sem_numero_guardado_e_sem_dado_no_bloco_nao_502(self, central_falsa):
        """Critério 1: a fonte do bloco caiu e não há número guardado. Antes era
        502 da tela inteira; agora o bloco fica `sem-dado` e a tela segue 200."""
        central_falsa.google.forcar = erro_da_ga4(500, "INTERNAL", "Internal error encountered.")

        corpo = _visao_geral("28d")

        assert corpo.status_code == 200
        corpo = corpo.json()
        assert corpo["visitantes"]["estado"] == "sem-dado"
        assert "HTTP 500" in corpo["visitantes"]["motivo"]
        assert "atual" not in corpo["visitantes"]
        assert corpo["instagram"]["estado"] == "ok"

    def test_instagram_fora_sem_numero_guardado_e_sem_dado_no_bloco(self, central_falsa):
        central_falsa.instagram.forcar = erro_do_instagram(500, 1, "Internal", "boom")

        corpo = _visao_geral("28d")

        assert corpo.status_code == 200
        corpo = corpo.json()
        assert corpo["instagram"]["estado"] == "sem-dado"
        assert corpo["visitantes"]["estado"] == "ok"

    def test_as_duas_fontes_fora_ainda_e_200_com_os_dois_blocos_marcados(self, central_falsa):
        central_falsa.google.forcar = erro_da_ga4(503, "UNAVAILABLE", "unavailable")
        central_falsa.instagram.forcar = erro_do_instagram(500, 1, "Internal", "boom")

        corpo = _visao_geral("28d")

        assert corpo.status_code == 200
        corpo = corpo.json()
        assert corpo["visitantes"]["estado"] == "sem-dado"
        assert corpo["instagram"]["estado"] == "sem-dado"
        assert all(o["numero"] is None for o in corpo["objetivos"]["em_foco"])


# ─── 5. Último valor bom por bloco (o cache da #815 segue por bloco) ────────


class TestUltimoValorBomPorBloco:
    def test_google_fora_com_numero_guardado_mostra_o_ultimo_valor_bom(self, central_falsa, relogio_da_central):
        """Passou a hora e o Google caiu: o bloco `visitantes` mostra os números
        de antes (`ok`), e o `frescor` avisa que a atualização falhou. Nunca zero."""
        _visao_geral("28d")
        relogio_da_central.avancar(hours=2)
        central_falsa.google.forcar = erro_da_ga4(500, "INTERNAL", "Internal error encountered.")

        corpo = _visao_geral("28d").json()

        assert corpo["visitantes"]["estado"] == "ok"
        assert corpo["visitantes"]["atual"] == 12345
        assert corpo["frescor"]["atualizacao_falhou"] is True
        assert "HTTP 500" in corpo["frescor"]["motivo"]
        assert corpo["frescor"]["atualizado_em"] == "2026-09-18T13:45:00+00:00"


# ─── 6. O frescor combinado dos blocos ──────────────────────────────────────


class TestFrescorCombinado:
    def test_a_tela_diz_de_quando_sao_os_numeros(self, central_falsa, relogio_da_central):
        corpo = _visao_geral("28d").json()

        assert corpo["frescor"] == {
            "atualizado_em": "2026-09-18T13:45:00+00:00",
            "atualizacao_falhou": False,
            "motivo": None,
        }

    def test_bloco_nao_configurado_nao_conta_no_frescor(self, central_falsa, relogio_da_central, monkeypatch):
        """Instagram não configurado não é falha de atualização: o frescor é o do
        Google, que respondeu."""
        from app.config import settings

        monkeypatch.setattr(settings, "instagram_access_token", "")
        monkeypatch.setattr(settings, "instagram_business_account_id", "")

        frescor = _visao_geral("28d").json()["frescor"]

        assert frescor["atualizacao_falhou"] is False
        assert frescor["atualizado_em"] == "2026-09-18T13:45:00+00:00"


# ─── 7. O cache de 1 hora e o Atualizar agora ───────────────────────────────


class TestCacheEAtualizarAgora:
    def test_a_segunda_leitura_dentro_da_hora_nao_vai_a_fonte(self, central_falsa, relogio_da_central):
        _visao_geral("28d")
        idas_google = len(central_falsa.google.pedidos)
        idas_instagram = len(central_falsa.instagram.pedidos)
        central_falsa.google.visitantes[_28_DIAS] = 99999
        relogio_da_central.avancar(minutes=59)

        corpo = _visao_geral("28d").json()

        assert corpo["visitantes"]["atual"] == 12345
        assert len(central_falsa.google.pedidos) == idas_google
        assert len(central_falsa.instagram.pedidos) == idas_instagram

    def test_atualizar_agora_vai_a_fonte_e_traz_o_numero_novo(self, central_falsa, relogio_da_central):
        _visao_geral("28d")
        central_falsa.google.visitantes[_28_DIAS] = 12400
        relogio_da_central.avancar(minutes=5)

        resposta = _atualizar_agora("28d")

        assert resposta.status_code == 200, resposta.text
        corpo = resposta.json()
        assert corpo["visitantes"]["atual"] == 12400
        assert corpo["frescor"]["atualizado_em"] == "2026-09-18T13:50:00+00:00"


# ─── 8. O vocabulário (ADR 0058, decisão 7) ─────────────────────────────────


class TestVocabulario:
    def test_a_tela_nao_fala_em_meta_nem_em_braco(self, central_falsa):
        texto = _visao_geral("28d").text

        assert not re.search(r"\bmeta\b", texto, re.IGNORECASE)
        assert not re.search(r"bra[cç]os?\b", texto, re.IGNORECASE)


# ─── 9. O gate: só Super admin, em toda rota ────────────────────────────────


def _rotas_da_central() -> list[tuple[str, str]]:
    """Toda rota da Central que o app REAL publica, pelo schema OpenAPI. O gate
    está no router: rota de fatia seguinte entra aqui sozinha (mesmo cuidado do
    `test_admin_tecnologia.py`, cache do schema devolvido)."""
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
    assert ("GET", f"{PREFIXO}/visao-geral") in ROTAS


@pytest.mark.usefixtures("central_falsa")
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
        """Rota que exija corpo pode responder 422 aqui, nunca 401 ou 403."""
        assert cliente_da_central(SUPER_ADMIN).request(metodo, caminho).status_code not in (401, 403)

    def test_super_admin_desligado_leva_403(self):
        desligado = pessoa("super", "super_admin", ativo=False)
        cliente = cliente_da_central(desligado, participantes=[desligado])

        assert cliente.get(f"{PREFIXO}/visao-geral").status_code == 403


# ─── 10. Período inválido e a trava de rede ─────────────────────────────────


class TestPeriodo:
    @pytest.mark.parametrize("periodo", ["30d", "7", "ano"])
    def test_periodo_que_nao_existe_e_recusado(self, central_falsa, periodo):
        """A API é estrita; quem cai no padrão com o que se digita no endereço é a
        tela. Período fora de 7, 28 e 90 dias é 422."""
        assert _visao_geral(periodo).status_code == 422

    def test_sem_periodo_vale_o_de_28_dias(self, central_falsa):
        corpo = _visao_geral(None).json()

        assert corpo["periodo"]["chave"] == "28d"
        assert corpo["visitantes"]["atual"] == 12345


class TestTravaDeRede:
    def test_sem_o_duble_o_provedor_bate_na_trava_da_suite(self, central_configurada):
        """Sem o dublê, a chamada sairia de verdade para a GA4. A trava de
        `tests/conftest.py` pega antes do primeiro pacote."""
        with pytest.raises(TentativaDeRedeNoTeste) as erro:
            provedor_google.visitantes_comparados("28d", HOJE_DE_TESTE)

        assert "analyticsdata.googleapis.com" in str(erro.value)


# ─── 11. O motivo nunca carrega segredo (issue #848) ────────────────────────
#
# Com o status por bloco (#821), o `motivo` da falha viaja num 200, dentro do
# bloco e do frescor, e não mais só no `detail` de um 5xx. Os provedores já
# montam frases fixas; estes testes travam isso na tela, que é onde o segredo
# vazaria: nenhum `motivo` carrega material de chave, `Bearer`, URL ou tira com
# cara de token, nem quando a fonte ecoa o segredo na mensagem de erro dela.

# O que tem cara de segredo num texto que vai para a tela.
_CARA_DE_SEGREDO = (
    re.compile(r"PRIVATE KEY|-----"),  # material de chave PEM
    re.compile(r"\bbearer\b", re.IGNORECASE),  # o esquema do header de acesso
    re.compile(r"://|googleapis|facebook", re.IGNORECASE),  # URL da fonte
    re.compile(r"eyJ[A-Za-z0-9_-]{8,}"),  # JWT (o `{"` do cabeçalho em base64)
    re.compile(r"(?=[A-Za-z0-9_-]*[0-9])(?=[A-Za-z0-9_-]*[A-Za-z])[A-Za-z0-9_-]{20,}"),  # tira de token
)

# Um token do Instagram com a cara do real (longo, letras e dígitos), vencido.
_TOKEN_DO_INSTAGRAM_VENCIDO = "EAAGvencido0123456789abcdefSEGREDO"


def _motivos(no) -> list[str]:
    """Todo `motivo` do payload, de bloco e do frescor, em qualquer profundidade."""
    if isinstance(no, dict):
        proprio = [no["motivo"]] if isinstance(no.get("motivo"), str) else []
        return proprio + [m for valor in no.values() for m in _motivos(valor)]
    if isinstance(no, list):
        return [m for valor in no for m in _motivos(valor)]
    return []


def _sem_segredo(resposta: httpx.Response, *segredos: str) -> list[str]:
    """Confere que nenhum `motivo` tem cara de segredo e que os segredos do
    cenário não aparecem em lugar nenhum da resposta. Devolve os motivos."""
    assert resposta.status_code == 200, resposta.text
    motivos = _motivos(resposta.json())
    assert motivos, "o cenário tinha de produzir ao menos um motivo"
    for motivo in motivos:
        for cara in _CARA_DE_SEGREDO:
            assert not cara.search(motivo), f"{cara.pattern!r} no motivo: {motivo!r}"
    for segredo in segredos:
        assert segredo not in resposta.text
    return motivos


@pytest.mark.parametrize(
    "texto",
    [
        "-----BEGIN PRIVATE KEY-----",
        "Authorization: Bearer abc",
        "https://graph.facebook.com/v21.0/me",
        "eyJhbGciOiJSUzI1NiJ9.eyJpc3MiOiJ4In0.assinatura",
        _TOKEN_DO_INSTAGRAM_VENCIDO,
    ],
)
def test_o_detector_enxerga_o_que_tem_cara_de_segredo(texto):
    """O detector tem dente: se ele não pegasse isto, os testes abaixo passariam
    sem provar nada."""
    assert any(cara.search(texto) for cara in _CARA_DE_SEGREDO)


class TestMotivoSemSegredo:
    def test_chave_privada_estragada(self, central_falsa, credencial_da_central, monkeypatch):
        """Volta o `test_chave_privada_estragada_e_503_sem_ecoar_a_chave`, que saiu
        com o 503: agora a falha mora no bloco, num 200."""
        from app.config import settings

        miolo = "SEGREDOquebrado0123456789abcdefXYZ"
        estragada = {
            **credencial_da_central,
            "private_key": f"-----BEGIN PRIVATE KEY-----\n{miolo}\n-----END PRIVATE KEY-----\n",
        }
        monkeypatch.setattr(settings, "google_application_credentials_json", json.dumps(estragada))

        resposta = _visao_geral("28d")

        assert resposta.json()["visitantes"]["estado"] == "nao-configurado"
        _sem_segredo(resposta, miolo)
        assert central_falsa.google.pedidos == []

    def test_credencial_cortada_no_meio_da_chave(self, central_falsa, credencial_da_central, monkeypatch):
        """O JSON colado pela metade: o erro do `json` carrega o documento, que é
        a chave privada. Nada dele chega à tela."""
        from app.config import settings

        inteira = json.dumps(credencial_da_central)
        cortada = inteira[: inteira.index("-----END")]
        linha_da_chave = credencial_da_central["private_key"].splitlines()[1]
        monkeypatch.setattr(settings, "google_application_credentials_json", cortada)

        resposta = _visao_geral("28d")

        assert resposta.json()["visitantes"]["estado"] == "nao-configurado"
        _sem_segredo(resposta, linha_da_chave)

    def test_chave_de_outra_conta_recusada_pelo_google(self, central_falsa, credencial_da_central, monkeypatch):
        """A chave é válida, mas não é a da service account: o Google recusa o
        token assinado (401). O `motivo` explica sem ecoar o token nem a chave."""
        from app.config import settings

        outra = pem_da_chave_privada(rsa.generate_private_key(public_exponent=65537, key_size=2048))
        monkeypatch.setattr(
            settings, "google_application_credentials_json", json.dumps({**credencial_da_central, "private_key": outra})
        )

        resposta = _visao_geral("28d")

        assert resposta.json()["visitantes"]["estado"] == "sem-dado"
        token = central_falsa.google.pedidos[0].headers["authorization"].removeprefix("Bearer ")
        motivos = _sem_segredo(resposta, token, outra.splitlines()[1])
        assert any("HTTP 401" in m for m in motivos)

    def test_o_google_ecoa_o_token_na_mensagem_de_erro(self, central_falsa):
        """A mensagem que o Google devolve fica no log, nunca na tela: mesmo que
        ela traga o token e a URL, o `motivo` é a frase fixa da Central."""
        eco = "Bearer eyJhbGciOiJSUzI1NiJ9.eyJzZWdyZWRvIjoxfQ.assinatura0123456789 em https://analyticsdata.googleapis.com/x"
        central_falsa.google.forcar = erro_da_ga4(401, "UNAUTHENTICATED", eco)

        resposta = _visao_geral("28d")

        assert resposta.json()["visitantes"]["estado"] == "sem-dado"
        _sem_segredo(resposta, "eyJzZWdyZWRvIjoxfQ", "assinatura0123456789")

    def test_token_do_instagram_vencido_sem_numero_guardado(self, central_falsa, monkeypatch):
        """O token venceu antes da primeira leitura: o bloco fica `sem-dado`, e o
        `motivo` pede a renovação sem ecoar o token, nem quando a Graph API o
        devolve na mensagem de erro."""
        from app.config import settings

        monkeypatch.setattr(settings, "instagram_access_token", _TOKEN_DO_INSTAGRAM_VENCIDO)
        central_falsa.instagram.forcar = erro_do_instagram(
            400,
            190,
            "OAuthException",
            f"Error validating access token {_TOKEN_DO_INSTAGRAM_VENCIDO}: "
            f"https://graph.facebook.com/v21.0/me?access_token={_TOKEN_DO_INSTAGRAM_VENCIDO}",
        )

        resposta = _visao_geral("28d")

        assert resposta.json()["instagram"]["estado"] == "sem-dado"
        motivos = _sem_segredo(resposta, _TOKEN_DO_INSTAGRAM_VENCIDO)
        assert any("Renove o token" in m for m in motivos)

    def test_token_do_instagram_vencido_com_o_ultimo_valor_bom(self, central_falsa, relogio_da_central, monkeypatch):
        """Passou a hora e o token venceu: o relance mostra o último valor bom, e
        o `motivo` do frescor pede a renovação sem ecoar token nenhum."""
        from app.config import settings

        _visao_geral("28d")
        relogio_da_central.avancar(hours=2)
        monkeypatch.setattr(settings, "instagram_access_token", _TOKEN_DO_INSTAGRAM_VENCIDO)

        resposta = _visao_geral("28d")

        corpo = resposta.json()
        assert corpo["instagram"]["estado"] == "ok"
        assert corpo["frescor"]["atualizacao_falhou"] is True
        _sem_segredo(resposta, _TOKEN_DO_INSTAGRAM_VENCIDO, TOKEN_DO_INSTAGRAM)
        assert "Renove o token" in corpo["frescor"]["motivo"]
