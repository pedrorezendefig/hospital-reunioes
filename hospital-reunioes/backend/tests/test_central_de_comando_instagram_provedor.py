"""O provedor de dados do Instagram pela porta dele (issue #819).

Porte de `meta-client.test.ts` e `meta-provider.test.ts` do repositório antigo:
a orquestração (Seguidores do perfil, insights do período e do anterior, o
crescimento da chamada dedicada; as Principais publicações filtradas pela
janela ANTES de ranquear) e a tradução de erro (token vencido, `code` 190, vira
`InstagramTokenExpiradoError`; o `code` 100, apesar do type OAuthException, NÃO
é token vencido; falha de rede vira `InstagramError`).

O seam é a porta pública do provedor (`saude_da_conta`, `principais_publicacoes`),
com a fronteira de rede dublada pelo `InstagramFalso` (`httpx.MockTransport`).
Nenhum teste fala com a rede: a trava de `tests/conftest.py` segue de pé, e o
último bloco prova que ela pega o provedor quando o dublê falta.
"""

from __future__ import annotations

import os
import sys

import httpx
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from central_de_comando_apoio import HOJE_DE_TESTE, erro_do_instagram  # noqa: E402
from conftest import TentativaDeRedeNoTeste  # noqa: E402

from app.config import settings  # noqa: E402
from app.services.central_de_comando import provedor_instagram as ig  # noqa: E402


class TestSaudeDaConta:
    def test_junta_seguidores_insights_e_crescimento_do_periodo_e_do_anterior(
        self, instagram_falso, instagram_configurado
    ):
        saude = ig.saude_da_conta("28d", HOJE_DE_TESTE)

        assert saude.seguidores == 18420
        assert saude.alcance == 41280
        assert saude.alcance_anterior == 37650
        assert saude.visualizacoes == 96540
        assert saude.visualizacoes_anterior == 88210
        assert saude.interacoes == 7820
        assert saude.interacoes_anterior == 6910
        assert saude.contas_engajadas == 5140
        assert (
            saude.partes.curtidas,
            saude.partes.comentarios,
            saude.partes.salvamentos,
            saude.partes.compartilhamentos,
        ) == (5980, 540, 820, 480)
        # crescimento = ganhos - perdidos, no atual (340-28) e no anterior (270-22).
        assert saude.crescimento == 312
        assert saude.crescimento_anterior == 248
        assert saude.seguidores_ganhos == 340
        assert saude.seguidores_perdidos == 28

    def test_seguidores_e_estoque_o_mesmo_em_qualquer_periodo(self, instagram_falso, instagram_configurado):
        """Seguidores vem do perfil, não de uma janela: 7 e 28 dias trazem o
        mesmo número. O que muda por período é o crescimento e o alcance."""
        de_28 = ig.saude_da_conta("28d", HOJE_DE_TESTE)
        de_7 = ig.saude_da_conta("7d", HOJE_DE_TESTE)

        assert de_28.seguidores == de_7.seguidores == 18420
        assert de_7.alcance == 10800
        assert de_7.crescimento == 82


class TestPrincipaisPublicacoes:
    def test_filtra_pela_janela_exclui_stories_e_ranqueia_por_interacoes(self, instagram_falso, instagram_configurado):
        publicacoes = ig.principais_publicacoes("28d", HOJE_DE_TESTE)

        # m1(1840) > m2(1520) > m3(1190). O Story e a antiga, fora, mesmo com
        # mais interações: a exclusão acontece antes do ranking.
        assert [p.id for p in publicacoes] == ["m1", "m2", "m3"]
        assert [p.interacoes for p in publicacoes] == [1840, 1520, 1190]
        assert all(p.link.startswith("https://") for p in publicacoes)
        assert "s1" not in [p.id for p in publicacoes]
        assert "antigo" not in [p.id for p in publicacoes]

    def test_respeita_o_limite(self, instagram_falso, instagram_configurado):
        publicacoes = ig.principais_publicacoes("28d", HOJE_DE_TESTE, limite=2)

        assert [p.id for p in publicacoes] == ["m1", "m2"]


class TestTokenVencido:
    def test_code_190_vira_token_expirado_com_frase_de_renovacao(self, instagram_falso, instagram_configurado):
        instagram_falso.forcar = erro_do_instagram(400, 190, "OAuthException", "Session has expired.")

        with pytest.raises(ig.InstagramTokenExpiradoError) as erro:
            ig.saude_da_conta("28d", HOJE_DE_TESTE)

        # A frase é fixa e vai para a tela (o motivo do frescor): fala em
        # renovar, diz "Instagram" e nunca a empresa dona da rede nem o token.
        assert "renov" in str(erro.value).lower()
        assert "instagram" in str(erro.value).lower()
        # Token expirado É uma falha da fonte: entra no último valor bom do cache.
        assert isinstance(erro.value, ig.InstagramError)

    def test_code_100_apesar_de_oauth_nao_e_token_expirado(self, instagram_falso, instagram_configurado):
        """Regressão da Central antiga: o erro #100 (janela grande demais) chega
        com type OAuthException, mas SÓ o code 190 é token vencido."""
        instagram_falso.forcar = erro_do_instagram(
            400, 100, "OAuthException", "(#100) There cannot be more than 30 days"
        )

        with pytest.raises(ig.InstagramError) as erro:
            ig.saude_da_conta("28d", HOJE_DE_TESTE)

        assert not isinstance(erro.value, ig.InstagramTokenExpiradoError)


class TestFonteFora:
    @pytest.mark.parametrize(
        "resposta",
        [
            erro_do_instagram(500, 1, "InternalError", "Please retry."),
            httpx.Response(200, content=b"<html>proxy</html>"),
        ],
        ids=["500", "corpo-ilegivel"],
    )
    def test_resposta_ruim_vira_instagram_error(self, instagram_falso, instagram_configurado, resposta):
        instagram_falso.forcar = resposta

        with pytest.raises(ig.InstagramError):
            ig.saude_da_conta("28d", HOJE_DE_TESTE)

    @pytest.mark.parametrize(
        "falha",
        [httpx.ReadTimeout("lento demais"), httpx.ConnectError("rede fora")],
        ids=["timeout", "rede-fora"],
    )
    def test_rede_fora_vira_instagram_error(self, instagram_falso, instagram_configurado, falha):
        instagram_falso.forcar = falha

        with pytest.raises(ig.InstagramError):
            ig.saude_da_conta("28d", HOJE_DE_TESTE)


class TestSemCredencial:
    @pytest.mark.parametrize(
        ("token", "conta", "faltando"),
        [
            ("", "", ["INSTAGRAM_ACCESS_TOKEN", "INSTAGRAM_BUSINESS_ACCOUNT_ID"]),
            ("", "17841400000000000", ["INSTAGRAM_ACCESS_TOKEN"]),
            ("token-de-teste-do-instagram", "", ["INSTAGRAM_BUSINESS_ACCOUNT_ID"]),
            ("   ", "17841400000000000", ["INSTAGRAM_ACCESS_TOKEN"]),
        ],
        ids=["nenhuma", "sem-token", "sem-conta", "token-em-branco"],
    )
    def test_falta_configurar_e_nao_configurado_com_o_que_falta_no_log(
        self, monkeypatch, instagram_falso, caplog, token, conta, faltando
    ):
        monkeypatch.setattr(settings, "instagram_access_token", token)
        monkeypatch.setattr(settings, "instagram_business_account_id", conta)

        with pytest.raises(ig.InstagramNaoConfiguradoError) as erro:
            ig.saude_da_conta("28d", HOJE_DE_TESTE)

        # A mensagem é a frase fixa, sem nome de variável (issue #843); o que
        # falta vai para o log, nunca o token.
        assert str(erro.value) == ig.FRASE_NAO_CONFIGURADO
        for nome in faltando:
            assert nome in caplog.text
        assert "token-de-teste-do-instagram" not in caplog.text
        # Não configurado nunca toca a rede: não há o que perguntar sem token.
        assert instagram_falso.pedidos == []


class TestTravaDeRede:
    def test_sem_o_duble_o_provedor_bate_na_trava_da_suite(self, instagram_configurado):
        """Sem a fixture `instagram_falso`, a chamada sairia de verdade para a
        Graph API. A trava de `tests/conftest.py` pega antes do primeiro
        pacote: é o que garante que nenhum teste do Instagram fala com a rede."""
        with pytest.raises(TentativaDeRedeNoTeste) as erro:
            ig.saude_da_conta("28d", HOJE_DE_TESTE)

        assert "graph.facebook.com" in str(erro.value)

    def test_o_provedor_nao_espera_o_instagram_para_sempre(self, instagram_falso, instagram_configurado):
        """Timeout curto no cliente (padrão da casa): erro honesto em segundos
        vale mais que tela pendurada."""
        ig.saude_da_conta("28d", HOJE_DE_TESTE)

        assert instagram_falso.clientes, "o provedor não criou cliente nenhum"
        for kwargs in instagram_falso.clientes:
            timeout = kwargs.get("timeout")
            assert isinstance(timeout, httpx.Timeout)
            assert timeout.read is not None and timeout.read <= 10
            assert timeout.connect is not None and timeout.connect <= 5
