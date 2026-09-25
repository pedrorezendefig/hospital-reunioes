"""As ferramentas de Site e de Instagram do conector MCP da Central (issue #823).

Esta fatia acrescenta ao MESMO conector da #822 as duas ferramentas de período:
os números do Site (`get_site_analytics`) e os do Instagram
(`get_instagram_analytics`). O contrato é o do conector antigo (ADR 0006 de lá),
com uma diferença de nome no payload do Site: a chave das áreas do hospital com
página é "areasDoSite", o nome da casa (ADR 0058, decisão 7), no lugar do nome
antigo, de marca.

Dois seams, no molde do repositório antigo:

- **A serialização, direto** (`serializar_site`, `serializar_instagram_*`,
  `serializar_frescor`): funções puras que recebem o payload da tela e devolvem
  o payload do Claude. Porte dos casos de `serialize.test.ts`.
- **As ferramentas, pela leitura de verdade**: o Site e o Instagram lidos do
  MESMO cache das telas (o painel, o registro de telas), com a fonte dublada
  pelo `google_falso`/`instagram_falso` do apoio compartilhado. Prova o critério
  "leem do mesmo cache das telas": a ferramenta serve do que a tela guardou, sem
  ir à fonte de novo.
"""

from __future__ import annotations

import os
import re
import sys
import unicodedata
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from central_de_comando_apoio import erro_da_ga4, erro_do_instagram  # noqa: E402

from app.config import settings  # noqa: E402
from app.services.central_de_comando import conector_mcp, provedor_instagram, telas, visao_geral  # noqa: E402

pytestmark = pytest.mark.usefixtures("gate_e_limitador_zerados")

# O relógio dos testes de serialização direta: um instante fixo em UTC, para o
# "há quantos minutos" do frescor ser conferido de olho.
AGORA = datetime(2026, 9, 18, 13, 45, tzinfo=UTC)


# ─── 1. serializar_frescor: porte de serializeFrescor ────────────────────────


class TestSerializarFrescor:
    def test_converte_atualizado_em_para_minutos_atras(self):
        frescor = {
            "atualizado_em": (AGORA - timedelta(minutes=5)).isoformat(),
            "atualizacao_falhou": False,
            "motivo": None,
        }

        assert conector_mcp.serializar_frescor(frescor, AGORA) == {
            "atualizadoHaMin": 5,
            "falhaAoAtualizar": False,
            "motivo": None,
        }

    def test_sem_hora_o_atualizado_ha_min_e_nulo_nunca_vira_zero(self):
        frescor = {"atualizado_em": None, "atualizacao_falhou": False, "motivo": None}

        assert conector_mcp.serializar_frescor(frescor, AGORA)["atualizadoHaMin"] is None

    def test_propaga_a_falha_de_atualizacao_e_o_motivo(self):
        frescor = {"atualizado_em": AGORA.isoformat(), "atualizacao_falhou": True, "motivo": "token"}

        saida = conector_mcp.serializar_frescor(frescor, AGORA)

        assert saida["falhaAoAtualizar"] is True
        assert saida["motivo"] == "token"


# ─── 2. serializar_site: porte de serializeSite (com a renomeação) ───────────

_VISITANTES_OK = {"estado": "ok", "atual": 112, "anterior": 100, "variacao": 0.12, "contexto": {}}

_GOOGLE = {
    "movimento": [
        {
            "data": "2026-05-01",
            "visitantes": 10,
            "data_anterior": "2026-04-01",
            "visitantes_anterior": 8,
            "variacao": 0.25,
        },
        {
            "data": "2026-05-02",
            "visitantes": 20,
            "data_anterior": "2026-04-02",
            "visitantes_anterior": 12,
            "variacao": 0.66,
        },
    ],
    "dispositivos": [{"chave": "celular", "rotulo": "Celular", "visitas": 90, "percentual": 100}],
    "areas_do_site": [
        {
            "chave": "maternidade",
            "nome": "Maternidade",
            "descricao": "...",
            "visitas": 50,
            "visitas_anterior": 40,
            "variacao": 0.25,
        }
    ],
    "origem_do_publico": [{"chave": "busca", "rotulo": "Busca no Google", "visitas": 70, "percentual": 100}],
    "contatos_gerados": [
        {"chave": "agendar", "rotulo": "Cliques para agendar", "estado": "medido", "cliques": 12},
        {"chave": "whatsapp", "rotulo": "WhatsApp", "estado": "nao-medido"},
    ],
    "frescor": {"atualizado_em": AGORA.isoformat(), "atualizacao_falhou": False, "motivo": None},
}


class TestSerializarSite:
    def test_monta_visitantes_com_variacao_percentual(self):
        payload = conector_mcp.serializar_site("28d", _VISITANTES_OK, _GOOGLE, _GOOGLE["frescor"], AGORA)

        assert payload["periodo"] == "28d"
        assert payload["visitantes"] == {"atual": 112, "anterior": 100, "variacaoPct": 12}

    def test_alinha_o_movimento_dia_atual_e_o_mesmo_dia_do_anterior(self):
        payload = conector_mcp.serializar_site("28d", _VISITANTES_OK, _GOOGLE, _GOOGLE["frescor"], AGORA)

        assert payload["movimento"][1] == {"data": "2026-05-02", "visitantes": 20, "anterior": 12}

    def test_a_chave_das_areas_e_o_nome_novo_e_nunca_o_antigo(self):
        """ADR 0058, decisão 7: a chave é "areasDoSite" (o nome da casa), e o
        nome antigo, de marca, não aparece no payload."""
        payload = conector_mcp.serializar_site("28d", _VISITANTES_OK, _GOOGLE, _GOOGLE["frescor"], AGORA)

        assert "areasDoSite" in payload
        assert not re.search(r"bra[cç]os?", str(payload), re.IGNORECASE)
        assert payload["areasDoSite"] == {
            "disponivel": True,
            "itens": [
                {"chave": "maternidade", "nome": "Maternidade", "visitas": 50, "visitasAnterior": 40, "variacaoPct": 25}
            ],
        }

    def test_origens_e_dispositivos_so_com_chave_rotulo_e_visitas(self):
        """O contrato do conector antigo: origens e dispositivos não levam o
        percentual da tela."""
        payload = conector_mcp.serializar_site("28d", _VISITANTES_OK, _GOOGLE, _GOOGLE["frescor"], AGORA)

        assert payload["origens"] == [{"chave": "busca", "rotulo": "Busca no Google", "visitas": 70}]
        assert payload["dispositivos"] == [{"chave": "celular", "rotulo": "Celular", "visitas": 90}]

    def test_preserva_o_estado_dos_contatos(self):
        payload = conector_mcp.serializar_site("28d", _VISITANTES_OK, _GOOGLE, _GOOGLE["frescor"], AGORA)

        assert {"chave": "agendar", "rotulo": "Cliques para agendar", "estado": "medido", "cliques": 12} in payload[
            "contatos"
        ]
        assert {"chave": "whatsapp", "rotulo": "WhatsApp", "estado": "nao-medido"} in payload["contatos"]

    def test_o_frescor_do_payload_e_o_combinado_passado_nao_o_de_uma_chave_so(self):
        """Honestidade do frescor: o payload reporta o frescor COMBINADO que o
        chamador passa (o pior caso das chaves), nunca o de uma chave só. Aqui o
        combinado falhou; o frescor da tela Dados do Google segue sem falha, e o
        payload conta a falha, não mente."""
        frescor_combinado = {
            "atualizado_em": (AGORA - timedelta(minutes=90)).isoformat(),
            "atualizacao_falhou": True,
            "motivo": "renovacao falhou",
        }

        payload = conector_mcp.serializar_site("28d", _VISITANTES_OK, _GOOGLE, frescor_combinado, AGORA)

        assert _GOOGLE["frescor"]["atualizacao_falhou"] is False
        assert payload["frescor"] == {"atualizadoHaMin": 90, "falhaAoAtualizar": True, "motivo": "renovacao falhou"}


# ─── 3. serializar_instagram: porte de serializeInstagram ────────────────────

_IG = {
    "periodo": {"chave": "28d", "dias": 28, "atual": {}, "anterior": {}},
    "seguidores": {"total": 5000, "crescimento": 120, "crescimento_anterior": 100, "ganhos": 120, "perdidos": 0},
    "alcance": {"atual": 8000, "anterior": 6000, "variacao": 0.33},
    "visualizacoes": {"atual": 20000, "anterior": 18000, "variacao": 0.11},
    "engajamento": {
        "interacoes": 900,
        "interacoes_anterior": 1000,
        "variacao": -0.1,
        "partes": [
            {"chave": "curtidas", "rotulo": "Curtidas", "valor": 600},
            {"chave": "comentarios", "rotulo": "Comentários", "valor": 100},
            {"chave": "salvamentos", "rotulo": "Salvamentos", "valor": 120},
            {"chave": "compartilhamentos", "rotulo": "Compartilhamentos", "valor": 80},
        ],
        "contas_engajadas": 700,
        "contas_engajadas_anterior": 650,
    },
    "principais_publicacoes": [
        {
            "id": "1",
            "legenda": "Oi",
            "tipo": "reel",
            "rotulo_tipo": "Reel",
            "miniatura": "u",
            "link": "p",
            "data": "2026-05-01T00:00:00Z",
            "interacoes": 300,
        }
    ],
    "frescor": {"atualizado_em": AGORA.isoformat(), "atualizacao_falhou": False, "motivo": None},
}


class TestSerializarInstagram:
    def test_monta_metricas_comparadas_inclusive_variacao_negativa(self):
        payload = conector_mcp.serializar_instagram_disponivel("28d", _IG, AGORA)

        assert payload["disponivel"] is True
        assert payload["seguidores"] == {
            "total": 5000,
            "crescimento": {"atual": 120, "anterior": 100, "variacaoPct": 20},
        }
        assert payload["interacoes"] == {"atual": 900, "anterior": 1000, "variacaoPct": -10}
        assert payload["contasEngajadas"] == {"atual": 700, "anterior": 650, "variacaoPct": 8}

    def test_abre_as_quatro_partes_das_interacoes(self):
        payload = conector_mcp.serializar_instagram_disponivel("28d", _IG, AGORA)

        assert payload["detalheInteracoes"] == {
            "curtidas": 600,
            "comentarios": 100,
            "salvamentos": 120,
            "compartilhamentos": 80,
        }

    def test_principais_publicacoes_com_o_quando(self):
        publicacoes = conector_mcp.serializar_instagram_disponivel("28d", _IG, AGORA)["principaisPublicacoes"]

        assert publicacoes[0] == {
            "id": "1",
            "legenda": "Oi",
            "tipo": "reel",
            "interacoes": 300,
            "link": "p",
            "quando": "2026-05-01T00:00:00Z",
        }

    def test_indisponivel_e_disponivel_false_com_motivo_e_sem_numeros(self):
        """Porte de "health null (token sem cache) => indisponível, não zero":
        sem números, com o motivo, e a lista de publicações vazia."""
        payload = conector_mcp.serializar_instagram_indisponivel("28d", "token")

        assert payload["disponivel"] is False
        assert "seguidores" not in payload
        assert payload["principaisPublicacoes"] == []
        assert payload["frescor"]["motivo"] == "token"
        assert payload["frescor"]["atualizadoHaMin"] is None


# ─── 4. A lista de ferramentas: nomes, períodos e glossário ──────────────────


class TestFerramentasListadas:
    def test_traz_as_tres_ferramentas_com_os_periodos_de_cada_uma(self):
        por_nome = {f["name"]: f for f in conector_mcp.ferramentas()}

        assert set(por_nome) == {"get_active_now", "get_site_analytics", "get_instagram_analytics"}
        assert por_nome["get_site_analytics"]["inputSchema"]["properties"]["period"]["enum"] == ["7d", "28d", "90d"]
        assert por_nome["get_instagram_analytics"]["inputSchema"]["properties"]["period"]["enum"] == ["7d", "28d"]

    def test_as_descricoes_carregam_o_glossario_da_casa(self):
        por_nome = {f["name"]: f for f in conector_mcp.ferramentas()}
        descricao_site = por_nome["get_site_analytics"]["description"]

        assert "Áreas do site" in descricao_site
        assert "Visitantes".lower() in descricao_site.lower()
        assert not re.search(r"bra[cç]os?", descricao_site, re.IGNORECASE)
        assert "Alcance" in por_nome["get_instagram_analytics"]["description"]

    def test_a_descricao_do_site_cita_toda_origem_que_o_payload_pode_trazer(self):
        """O Claude lê as origens pelo rótulo: a descrição da ferramenta nomeia
        cada uma, inclusive a Indicação (#856), para ele não inventar sentido."""
        from app.services.central_de_comando.dados_do_google import ROTULO_DA_ORIGEM

        descricao_site = {f["name"]: f for f in conector_mcp.ferramentas()}["get_site_analytics"]["description"]

        for rotulo in ROTULO_DA_ORIGEM.values():
            assert rotulo.lower() in descricao_site.lower(), rotulo

    def test_a_descricao_do_site_diz_que_o_canal_medido_pode_ter_zero(self):
        """Canal medido sem clique no período traz 0; em construção e não
        medido seguem sem número (#856)."""
        descricao_site = {f["name"]: f for f in conector_mcp.ferramentas()}["get_site_analytics"]["description"]

        assert "zero incluso" in descricao_site


# ─── 5. A ferramenta de Site, lida do cache das telas ────────────────────────


@pytest.fixture(autouse=True)
def _central_no_dia_de_teste(hoje_da_central):
    """Todo teste de ferramenta daqui vive em 18/09/2026, o dia dos intervalos
    do dublê."""


@pytest.mark.usefixtures("central_configurada", "lote_da_ga4")
class TestFerramentaSite:
    def test_responde_os_numeros_do_site_com_o_nome_novo_das_areas(self, google_falso, relogio_da_central):
        resultado = conector_mcp._ferramenta_site({"period": "28d"})

        assert resultado["isError"] is False
        payload = resultado["structuredContent"]
        assert payload["periodo"] == "28d"
        assert payload["visitantes"] == {"atual": 12345, "anterior": 10000, "variacaoPct": 23}
        assert payload["areasDoSite"]["disponivel"] is True
        assert payload["areasDoSite"]["itens"][0] == {
            "chave": "maternidade",
            "nome": "Maternidade",
            "visitas": 3842,
            "visitasAnterior": 3500,
            "variacaoPct": 10,
        }
        assert [o["chave"] for o in payload["origens"][:2]] == ["busca", "direto"]
        assert all("percentual" not in o for o in payload["origens"])
        assert payload["contatos"][1] == {
            "chave": "whatsapp",
            "rotulo": "WhatsApp",
            "estado": "medido",
            "cliques": 4514,
        }
        assert payload["frescor"] == {"atualizadoHaMin": 0, "falhaAoAtualizar": False, "motivo": None}
        assert not re.search(r"bra[cç]os?", str(payload), re.IGNORECASE)

    def test_aceita_90_dias(self, google_falso, relogio_da_central):
        resultado = conector_mcp._ferramenta_site({"period": "90d"})

        assert resultado["isError"] is False
        assert resultado["structuredContent"]["periodo"] == "90d"
        assert resultado["structuredContent"]["visitantes"]["atual"] == 38412

    def test_le_do_mesmo_cache_que_as_telas_populam(self, google_falso, relogio_da_central):
        """O critério central: aquecido o cache pelas telas (o painel e a tela
        Dados do Google), a ferramenta serve do mesmo cache, sem ir à fonte de
        novo."""
        visao_geral.ler("28d")
        telas.ler("dados-do-google", "28d")
        idas_das_telas = len(google_falso.pedidos)

        resultado = conector_mcp._ferramenta_site({"period": "28d"})

        assert resultado["isError"] is False
        assert len(google_falso.pedidos) == idas_das_telas

    def test_a_segunda_chamada_dentro_da_hora_nao_vai_a_fonte(self, google_falso, relogio_da_central):
        conector_mcp._ferramenta_site({"period": "28d"})
        idas_da_primeira = len(google_falso.pedidos)
        relogio_da_central.avancar(minutes=59)

        conector_mcp._ferramenta_site({"period": "28d"})

        assert len(google_falso.pedidos) == idas_da_primeira

    def test_periodo_invalido_e_erro_claro_sem_tocar_a_fonte(self, google_falso):
        resultado = conector_mcp._ferramenta_site({"period": "ano"})

        assert resultado["isError"] is True
        assert "inválido" in resultado["content"][0]["text"].lower()
        assert google_falso.pedidos == []

    def test_fonte_fora_sem_numero_guardado_e_erro_honesto_nunca_zero(self, google_falso, relogio_da_central):
        google_falso.forcar = httpx.Response(503, json={"error": {"code": 503, "status": "UNAVAILABLE"}})

        resultado = conector_mcp._ferramenta_site({"period": "28d"})

        assert resultado["isError"] is True

    def test_frescor_honesto_quando_visitantes_venceu_com_falha_e_dados_estao_frescos(
        self, google_falso, relogio_da_central
    ):
        """As duas chaves do Site (Visitantes e Dados do Google) têm TTL e estado
        de falha independentes. Aqui a de Visitantes vence e a renovação falha,
        enquanto a de Dados do Google está fresca. O frescor do payload tem que
        contar a falha do pior caso, nunca dizer "fresco, sem falha" com o
        manchete de Visitantes velho renovando com erro."""
        conector_mcp._ferramenta_site({"period": "28d"})  # aquece as duas chaves
        relogio_da_central.avancar(hours=2)
        telas.ler("dados-do-google", "28d", forcar=True)  # só Dados do Google renova, fresco
        google_falso.forcar = httpx.Response(503, json={"error": {"code": 503, "status": "UNAVAILABLE"}})

        resultado = conector_mcp._ferramenta_site({"period": "28d"})

        assert resultado["isError"] is False  # serve o último valor bom
        frescor = resultado["structuredContent"]["frescor"]
        assert frescor["falhaAoAtualizar"] is True
        assert frescor["atualizadoHaMin"] == 120  # a hora do número mais velho (Visitantes)
        assert frescor["motivo"]

    def test_frescor_honesto_quando_dados_venceram_com_falha_e_visitantes_estao_frescos(
        self, google_falso, relogio_da_central
    ):
        """O outro lado da divergência: Dados do Google vence e a renovação
        falha, Visitantes está fresco. O frescor do Site tem que ancorar nas DUAS
        chaves, então a falha de Dados do Google também aparece (guarda contra
        reportar só a chave dos Visitantes)."""
        conector_mcp._ferramenta_site({"period": "28d"})  # aquece as duas chaves
        relogio_da_central.avancar(hours=2)
        visao_geral.ler_visitantes("28d", forcar=True)  # só Visitantes renova, fresco
        google_falso.forcar = httpx.Response(503, json={"error": {"code": 503, "status": "UNAVAILABLE"}})

        resultado = conector_mcp._ferramenta_site({"period": "28d"})

        assert resultado["isError"] is False
        frescor = resultado["structuredContent"]["frescor"]
        assert frescor["falhaAoAtualizar"] is True
        assert frescor["atualizadoHaMin"] == 120
        assert frescor["motivo"]


# ─── 6. A ferramenta de Instagram, lida do cache da tela ─────────────────────


class TestFerramentaInstagram:
    @pytest.mark.usefixtures("instagram_configurado")
    def test_responde_os_numeros_do_instagram(self, instagram_falso, relogio_da_central):
        resultado = conector_mcp._ferramenta_instagram({"period": "28d"})

        assert resultado["isError"] is False
        payload = resultado["structuredContent"]
        assert payload["disponivel"] is True
        assert payload["periodo"] == "28d"
        assert payload["seguidores"] == {
            "total": 18420,
            "crescimento": {"atual": 312, "anterior": 248, "variacaoPct": 26},
        }
        assert payload["interacoes"] == {"atual": 7820, "anterior": 6910, "variacaoPct": 13}
        assert payload["detalheInteracoes"] == {
            "curtidas": 5980,
            "comentarios": 540,
            "salvamentos": 820,
            "compartilhamentos": 480,
        }
        assert [p["id"] for p in payload["principaisPublicacoes"]] == ["m1", "m2", "m3"]
        assert payload["principaisPublicacoes"][0]["quando"] == "2026-09-10T12:00:00+0000"

    def test_nao_configurado_devolve_indisponivel_com_motivo_e_nao_erro(self, monkeypatch, instagram_falso):
        """Critério de aceite: Instagram não configurado é indisponível com o
        motivo, nunca um erro, e sem tocar a fonte."""
        monkeypatch.setattr(settings, "instagram_access_token", "")
        monkeypatch.setattr(settings, "instagram_business_account_id", "")

        resultado = conector_mcp._ferramenta_instagram({"period": "28d"})

        assert resultado["isError"] is False
        payload = resultado["structuredContent"]
        assert payload["disponivel"] is False
        assert payload["frescor"]["motivo"]
        assert "seguidores" not in payload
        assert instagram_falso.pedidos == []

    @pytest.mark.usefixtures("instagram_configurado")
    def test_token_vencido_sem_numero_guardado_e_indisponivel_nao_erro(self, instagram_falso, relogio_da_central):
        """Sem número guardado, o token vencido não vira erro técnico: o Claude
        recebe indisponível com o motivo, como a saúde nula do conector antigo."""
        instagram_falso.forcar = erro_do_instagram(400, 190, "OAuthException", "Session has expired.")

        resultado = conector_mcp._ferramenta_instagram({"period": "28d"})

        assert resultado["isError"] is False
        assert resultado["structuredContent"]["disponivel"] is False
        assert resultado["structuredContent"]["frescor"]["motivo"]

    @pytest.mark.usefixtures("instagram_configurado")
    def test_recusa_90_dias_com_erro_claro_sem_tocar_a_fonte(self, instagram_falso):
        resultado = conector_mcp._ferramenta_instagram({"period": "90d"})

        assert resultado["isError"] is True
        texto = resultado["content"][0]["text"]
        assert "7d" in texto and "28d" in texto
        assert instagram_falso.pedidos == []

    @pytest.mark.usefixtures("instagram_configurado")
    def test_le_do_mesmo_cache_que_a_tela_do_instagram(self, instagram_falso, relogio_da_central):
        telas.ler("instagram", "28d")
        idas_da_tela = len(instagram_falso.pedidos)

        resultado = conector_mcp._ferramenta_instagram({"period": "28d"})

        assert resultado["isError"] is False
        assert len(instagram_falso.pedidos) == idas_da_tela


# ─── 7. Ponta a ponta pelo dispatch do protocolo (tools/call) ────────────────


@pytest.mark.usefixtures("central_configurada", "lote_da_ga4")
class TestToolsCallPeloResponderMcp:
    async def test_tools_list_traz_as_tres_ferramentas(self):
        resposta = await conector_mcp.responder_mcp({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})

        nomes = {f["name"] for f in resposta["result"]["tools"]}
        assert nomes == {"get_active_now", "get_site_analytics", "get_instagram_analytics"}

    async def test_tools_call_do_site_responde_o_payload(self, google_falso, relogio_da_central):
        pedido = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "get_site_analytics", "arguments": {"period": "28d"}},
        }

        resposta = await conector_mcp.responder_mcp(pedido)

        resultado = resposta["result"]
        assert resultado["isError"] is False
        assert resultado["structuredContent"]["visitantes"]["atual"] == 12345
        assert resultado["structuredContent"]["areasDoSite"]["disponivel"] is True

    async def test_tools_call_com_arguments_nao_dict_e_invalid_params(self):
        """`arguments` que não é objeto (array, string, número) é -32602 (Params
        inválidos), no mesmo molde do `params` da #822: nunca um 500 quando a
        ferramenta for desreferenciar o que não é dict."""
        pedido = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "get_site_analytics", "arguments": ["nao", "e", "objeto"]},
        }

        resposta = await conector_mcp.responder_mcp(pedido)

        assert resposta["error"]["code"] == -32602


# ─── 8. Não configurado e acesso recusado: sem nome de variável (issue #843) ─

# Um nome de variável de ambiente: letras maiúsculas com sublinhado
# (GA4_PROPERTY_ID, INSTAGRAM_ACCESS_TOKEN). Nem o cliente MCP nem a tela da
# Central recebem nome de variável: a fonte não configurada é a mesma frase fixa
# nos dois lados, e o acesso recusado pelo Google (401/403) também não cita
# nenhum. Quais variáveis faltam fica no log do backend.
_NOME_DE_VARIAVEL = re.compile(r"\b[A-Z][A-Z0-9]*_[A-Z0-9_]+\b")


def _sem_nome_de_variavel(texto: str) -> None:
    assert texto
    assert not _NOME_DE_VARIAVEL.search(texto), texto


@pytest.fixture
def google_sem_configurar(monkeypatch):
    monkeypatch.setattr(settings, "ga4_property_id", "")
    monkeypatch.setattr(settings, "google_application_credentials_json", "")


class TestNaoConfiguradoSemNomeDeVariavel:
    @pytest.mark.usefixtures("google_sem_configurar")
    async def test_ao_vivo_sem_configurar_diz_o_motivo_sem_nome_de_variavel(self):
        resultado = await conector_mcp._ferramenta_ao_vivo()

        assert resultado["isError"] is True
        texto = resultado["content"][0]["text"]
        _sem_nome_de_variavel(texto)
        assert "Google Analytics" in texto

    async def test_ao_vivo_com_a_chave_invalida_diz_o_motivo_sem_nome_de_variavel(self, monkeypatch):
        monkeypatch.setattr(settings, "ga4_property_id", "123456789")
        monkeypatch.setattr(settings, "google_application_credentials_json", "não é a chave")

        resultado = await conector_mcp._ferramenta_ao_vivo()

        assert resultado["isError"] is True
        _sem_nome_de_variavel(resultado["content"][0]["text"])

    @pytest.mark.usefixtures("google_sem_configurar")
    def test_site_sem_configurar_diz_o_motivo_sem_nome_de_variavel(self, google_falso):
        resultado = conector_mcp._ferramenta_site({"period": "28d"})

        assert resultado["isError"] is True
        texto = resultado["content"][0]["text"]
        _sem_nome_de_variavel(texto)
        assert "Site" in texto
        assert google_falso.pedidos == []

    def test_site_com_a_propriedade_invalida_diz_o_motivo_sem_nome_de_variavel(
        self, monkeypatch, central_configurada, google_falso
    ):
        monkeypatch.setattr(settings, "ga4_property_id", "properties/123")

        resultado = conector_mcp._ferramenta_site({"period": "28d"})

        assert resultado["isError"] is True
        _sem_nome_de_variavel(resultado["content"][0]["text"])

    def test_instagram_sem_configurar_diz_o_motivo_sem_nome_de_variavel(self, monkeypatch, instagram_falso):
        monkeypatch.setattr(settings, "instagram_access_token", "")
        monkeypatch.setattr(settings, "instagram_business_account_id", "")

        resultado = conector_mcp._ferramenta_instagram({"period": "28d"})

        payload = resultado["structuredContent"]
        assert payload["disponivel"] is False
        _sem_nome_de_variavel(payload["frescor"]["motivo"])
        assert "Instagram" in payload["frescor"]["motivo"]
        _sem_nome_de_variavel(resultado["content"][0]["text"])

    @pytest.mark.usefixtures("google_sem_configurar")
    async def test_a_tela_mostra_a_mesma_frase_fixa_que_o_cliente_mcp_recebe(self, cache_da_central):
        """A triagem pediu a frase fixa "a mesma das telas": o bloco de
        Visitantes da tela e o cliente MCP dizem exatamente a mesma coisa."""
        bloco, _ = visao_geral.ler_visitantes("28d")
        ao_vivo = await conector_mcp._ferramenta_ao_vivo()
        site = conector_mcp._ferramenta_site({"period": "28d"})

        assert bloco["estado"] == "nao-configurado"
        _sem_nome_de_variavel(bloco["motivo"])
        assert ao_vivo["content"][0]["text"] == bloco["motivo"]
        assert site["content"][0]["text"] == bloco["motivo"]

    def test_a_tela_do_instagram_mostra_a_mesma_frase_fixa_que_o_cliente_mcp_recebe(self, monkeypatch, instagram_falso):
        monkeypatch.setattr(settings, "instagram_access_token", "")
        monkeypatch.setattr(settings, "instagram_business_account_id", "")

        with pytest.raises(provedor_instagram.InstagramNaoConfiguradoError) as erro:
            telas.ler("instagram", "28d")
        resultado = conector_mcp._ferramenta_instagram({"period": "28d"})

        _sem_nome_de_variavel(str(erro.value))
        assert resultado["structuredContent"]["frescor"]["motivo"] == str(erro.value)


def _acesso_recusado_pelo_google():
    return erro_da_ga4(403, "PERMISSION_DENIED", "User does not have sufficient permissions.")


@pytest.mark.usefixtures("central_configurada")
class TestAcessoRecusadoPeloGoogleSemNomeDeVariavel:
    """O 401/403 da GA4 é `GoogleError`, não "não configurado": chega ao
    cliente MCP pelo texto do erro (Ao vivo e Site), pelo motivo do bloco de
    Visitantes e pelo `frescor.motivo` do último valor bom. Em nenhum dos
    quatro caminhos a frase cita nome de variável."""

    async def test_ao_vivo(self, google_falso):
        google_falso.forcar = _acesso_recusado_pelo_google()

        resultado = await conector_mcp._ferramenta_ao_vivo()

        assert resultado["isError"] is True
        texto = resultado["content"][0]["text"]
        _sem_nome_de_variavel(texto)
        assert "HTTP 403" in texto

    def test_site_sem_numero_guardado(self, google_falso, relogio_da_central):
        google_falso.forcar = _acesso_recusado_pelo_google()

        resultado = conector_mcp._ferramenta_site({"period": "28d"})

        assert resultado["isError"] is True
        texto = resultado["content"][0]["text"]
        _sem_nome_de_variavel(texto)
        assert "HTTP 403" in texto

    def test_motivo_do_bloco_de_visitantes(self, google_falso, relogio_da_central):
        google_falso.forcar = _acesso_recusado_pelo_google()

        bloco, _ = visao_geral.ler_visitantes("28d")

        assert bloco["estado"] != "ok"
        _sem_nome_de_variavel(bloco["motivo"])
        assert "HTTP 403" in bloco["motivo"]

    @pytest.mark.usefixtures("lote_da_ga4")
    def test_frescor_motivo_do_ultimo_valor_bom(self, google_falso, relogio_da_central):
        conector_mcp._ferramenta_site({"period": "28d"})  # aquece as duas chaves
        relogio_da_central.avancar(hours=2)
        google_falso.forcar = _acesso_recusado_pelo_google()

        resultado = conector_mcp._ferramenta_site({"period": "28d"})

        assert resultado["isError"] is False  # serve o último valor bom
        frescor = resultado["structuredContent"]["frescor"]
        assert frescor["falhaAoAtualizar"] is True
        _sem_nome_de_variavel(frescor["motivo"])
        assert "HTTP 403" in frescor["motivo"]


# ─── 9. O glossário das ferramentas bate com o CONTEXT.md (issue #843) ───────

# O glossário nas descrições das ferramentas é uma cópia, à mão, dos verbetes da
# seção "Central de Comando" do CONTEXT.md. O teste lê o CONTEXT.md (nunca o
# altera) e confere os fatos que não podem divergir: o catálogo das Áreas do
# site, as partes das Interações, os estados dos Contatos gerados, os termos da
# casa e o que os verbetes mandam evitar.
_CONTEXT_MD = Path(__file__).resolve().parents[3] / "CONTEXT.md"


def _secao_da_central() -> str:
    texto = _CONTEXT_MD.read_text(encoding="utf-8")
    inicio = texto.index("## Central de Comando")
    fim = texto.index("\n## ", inicio + 1)
    return texto[inicio:fim]


def _nomes_dos_verbetes() -> set[str]:
    """Os nomes de verbete da seção, inclusive os pares (`**A** / **B**:`)."""
    nomes: set[str] = set()
    for cabeca in re.findall(r"^(\*\*.+\*\*):$", _secao_da_central(), re.MULTILINE):
        nomes.update(re.findall(r"\*\*(.+?)\*\*", cabeca))
    return nomes


def _verbete(nome: str) -> str:
    """O texto de um verbete: a definição e a linha _Evitar_."""
    achado = re.search(
        rf"^\*\*{re.escape(nome)}\*\*[^\n]*:\n(.+?)(?:\n\n|\Z)", _secao_da_central(), re.MULTILINE | re.DOTALL
    )
    assert achado, f"verbete {nome!r} sumiu do CONTEXT.md"
    return achado.group(1)


def _sem_negrito(texto: str) -> str:
    return texto.replace("**", "")


def _descricoes() -> str:
    return " ".join(f["description"] for f in conector_mcp.ferramentas())


def _descricao(nome: str) -> str:
    return next(f["description"] for f in conector_mcp.ferramentas() if f["name"] == nome)


def _slug(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return sem_acento.lower().replace(" ", "-")


class TestGlossarioBateComOContext:
    def test_as_areas_do_site_sao_o_mesmo_catalogo_fechado(self):
        do_context = re.search(r"\(([^)]+)\)", _verbete("Área do site")).group(1)
        da_descricao = re.search(r'"areasDoSite"[^(]+\(([^)]+)\)', conector_mcp.GLOSSARIO_SITE).group(1)

        assert da_descricao.split(", ") == do_context.split(", ")

    def test_as_interacoes_somam_as_mesmas_partes(self):
        partes = re.search(r"A soma de (.+?) no período", _verbete("Interações")).group(1)

        assert f"soma de {partes}" in conector_mcp.GLOSSARIO_INSTAGRAM

    def test_os_estados_dos_contatos_sao_os_do_verbete(self):
        estados = re.findall(r"\*\*(.+?)\*\*", _verbete("Contatos gerados"))

        assert [_slug(e) for e in estados] == ["medido", "em-construcao", "nao-medido"]
        for estado in estados:
            assert f'"{_slug(estado)}"' in conector_mcp.GLOSSARIO_SITE

    @pytest.mark.parametrize(
        ("termo", "verbete"),
        [
            ("Central de Comando", "Central de Comando"),
            ("Site", "Site"),
            ("Visitantes", "Visitantes"),
            ("Visitas", "Visita"),
            ("Áreas do site", "Área do site"),
            ("Origem do público", "Origem do público"),
            ("Não identificado", "Não identificado"),
            ("Outros", "Outros"),
            ("Ao vivo", "Ao vivo"),
            ("Alcance", "Alcance"),
            ("Visualizações", "Visualizações"),
            ("Interações", "Interações"),
        ],
    )
    def test_cada_termo_da_casa_nas_descricoes_e_verbete_do_context(self, termo, verbete):
        assert termo in _descricoes()
        assert verbete in _nomes_dos_verbetes()

    @pytest.mark.parametrize(
        ("verbete", "expressao"),
        [
            ("Visitantes", "pessoas diferentes"),
            ("Área do site", "não da procura real pelo serviço"),
            ("Contatos gerados", "WhatsApp"),
            ("Contatos gerados", "Fale Conosco"),
            ("Ao vivo", "tempo real"),
            ("Alcance", "contas diferentes"),
            ("Visualizações", "vezes"),
            ("Seguidores", "estoque"),
            ("Seguidores", "crescimento"),
            ("Principais publicações", "Stories"),
        ],
    )
    def test_o_que_o_verbete_diz_a_descricao_repete(self, verbete, expressao):
        assert expressao in _sem_negrito(_verbete(verbete))
        assert expressao in _descricoes()

    @pytest.mark.parametrize(
        ("proibido", "verbete"),
        [
            ("Braço", "Área do site"),
            ("impressões", "Alcance"),
            ("top posts", "Principais publicações"),
            ("Site Novo", "Site"),
            ("sessões", "Visitantes"),
            ("(not set)", "Não identificado"),
            ("dashboard de marketing", "Central de Comando"),
        ],
    )
    def test_as_descricoes_nao_usam_o_que_o_verbete_manda_evitar(self, proibido, verbete):
        evitar = next(linha for linha in _verbete(verbete).splitlines() if linha.startswith("_Evitar_"))

        assert proibido in evitar
        assert proibido.lower() not in _descricoes().lower()


class TestDescricaoDizAsDiferencasDoContratoAntigo:
    """Duas diferenças do contrato antigo ficam como estão (aceitas na #862), e a
    descrição conta ao Claude: `frescor.motivo` vem sempre, nulo sem falha, e o
    `anterior` de cada dia do movimento nunca é nulo."""

    def test_o_site_diz_que_o_motivo_vem_nulo_quando_nao_houve_falha(self):
        assert '"motivo" vem sempre, nulo quando não houve falha' in _descricao(conector_mcp.FERRAMENTA_SITE)

    def test_o_instagram_diz_que_o_motivo_vem_nulo_quando_nao_houve_falha(self):
        assert '"motivo" vem sempre, nulo quando não houve falha' in _descricao(conector_mcp.FERRAMENTA_INSTAGRAM)

    def test_o_site_diz_que_o_anterior_do_movimento_nunca_e_nulo(self):
        descricao = _descricao(conector_mcp.FERRAMENTA_SITE)

        assert '"movimento"' in descricao
        assert '"anterior" é sempre um número' in descricao

    def test_o_site_nao_afirma_que_zero_no_movimento_e_ninguem_ter_vindo(self):
        """O provedor põe zero em todo dia que a GA4 não devolveu (linha
        ilegível, dia antes de a propriedade medir): zero é ausência de dado
        do Google, não a certeza de que ninguém veio."""
        descricao = _descricao(conector_mcp.FERRAMENTA_SITE)

        assert "nenhum visitante naquele dia" not in descricao
        assert "zero quer dizer que o Google não trouxe visitante naquele dia" in descricao
