"""A tela do Instagram da Central de Comando pela rota real (issue #819).

O seam é a ROTA HTTP (`GET /admin/central-de-comando/instagram`), com o gate de
Super admin de pé e a fronteira de rede dublada pelo `InstagramFalso`. O que se
observa é o que a tela recebe: os três números principais, o bloco de
engajamento, as Principais publicações e o frescor. O gate (só Super admin) e a
trava de rede são cobertos pela varredura de rotas de
`test_central_de_comando_visao_geral.py`, que enxerga a rota nova sozinha.

Porte da tela e dos estados de `instagram-screen.ts`/`page.tsx` do repositório
antigo: token vencido com número guardado mantém o último valor bom e avisa da
renovação; sem credencial é 503.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from central_de_comando_apoio import PREFIXO_DA_CENTRAL as PREFIXO  # noqa: E402
from central_de_comando_apoio import (  # noqa: E402
    SUPER_ADMIN,
    cliente_da_central,
    erro_do_instagram,
)

from app.config import settings  # noqa: E402
from app.services.central_de_comando import provedor_instagram  # noqa: E402

pytestmark = pytest.mark.usefixtures("gate_e_limitador_zerados")


@pytest.fixture(autouse=True)
def _no_dia_de_teste(hoje_da_central):
    """Todo teste daqui vive em 18/09/2026, o dia dos intervalos do dublê."""


@pytest.fixture
def cliente():
    return cliente_da_central(SUPER_ADMIN)


def _ler(cliente, periodo: str = "28d"):
    return cliente.get(f"{PREFIXO}/instagram", params={"periodo": periodo})


def _atualizar(cliente, periodo: str = "28d"):
    return cliente.post(f"{PREFIXO}/atualizar-agora", params={"tela": "instagram", "periodo": periodo})


@pytest.mark.usefixtures("instagram_configurado")
class TestPayloadDaTela:
    def test_traz_o_periodo_e_os_tres_numeros_principais(self, cliente, instagram_falso, relogio_da_central):
        corpo = _ler(cliente).json()

        assert corpo["periodo"] == {
            "chave": "28d",
            "dias": 28,
            "atual": {"inicio": "2026-08-21", "fim": "2026-09-17"},
            "anterior": {"inicio": "2026-07-24", "fim": "2026-08-20"},
        }
        assert corpo["alcance"] == {"atual": 41280, "anterior": 37650, "variacao": pytest.approx(3630 / 37650)}
        assert corpo["visualizacoes"] == {"atual": 96540, "anterior": 88210, "variacao": pytest.approx(8330 / 88210)}
        assert corpo["frescor"]["atualizacao_falhou"] is False

    def test_seguidores_e_estoque_com_crescimento_e_sem_variacao_percentual(
        self, cliente, instagram_falso, relogio_da_central
    ):
        seguidores = _ler(cliente).json()["seguidores"]

        assert seguidores == {
            "total": 18420,
            "crescimento": 312,
            "crescimento_anterior": 248,
            "ganhos": 340,
            "perdidos": 28,
        }
        # Estoque não tem variação percentual: o que se mostra é o crescimento.
        assert "variacao" not in seguidores

    def test_engajamento_traz_interacoes_as_quatro_partes_e_contas_engajadas(
        self, cliente, instagram_falso, relogio_da_central
    ):
        engajamento = _ler(cliente).json()["engajamento"]

        assert engajamento["interacoes"] == 7820
        assert engajamento["contas_engajadas"] == 5140
        assert engajamento["partes"] == [
            {"chave": "curtidas", "rotulo": "Curtidas", "valor": 5980},
            {"chave": "comentarios", "rotulo": "Comentários", "valor": 540},
            {"chave": "salvamentos", "rotulo": "Salvamentos", "valor": 820},
            {"chave": "compartilhamentos", "rotulo": "Compartilhamentos", "valor": 480},
        ]

    def test_principais_publicacoes_ordenadas_por_interacoes_com_link_sem_stories(
        self, cliente, instagram_falso, relogio_da_central
    ):
        publicacoes = _ler(cliente).json()["principais_publicacoes"]

        assert [p["id"] for p in publicacoes] == ["m1", "m2", "m3"]
        assert [p["interacoes"] for p in publicacoes] == [1840, 1520, 1190]
        assert all(p["link"].startswith("https://") for p in publicacoes)
        assert publicacoes[1]["tipo"] == "reel"
        assert publicacoes[1]["rotulo_tipo"] == "Reel"

    def test_sete_dias_traz_os_seus_numeros(self, cliente, instagram_falso, relogio_da_central):
        corpo = _ler(cliente, "7d").json()

        assert corpo["periodo"]["chave"] == "7d"
        assert corpo["alcance"]["atual"] == 10800
        assert corpo["seguidores"]["total"] == 18420
        assert corpo["seguidores"]["crescimento"] == 82


@pytest.mark.usefixtures("instagram_configurado")
class TestSoSeteEVinteOitoDias:
    @pytest.mark.parametrize("periodo", ["90d", "30d", "ano"])
    def test_periodo_fora_de_7_e_28_e_recusado_sem_tocar_a_fonte(self, cliente, instagram_falso, periodo):
        resposta = _ler(cliente, periodo)

        # 90d existe na Central, mas o Instagram só tem 7 e 28: 422 no registro,
        # antes de qualquer busca (por isso o dublê não recebe pedido nenhum).
        assert resposta.status_code == 422
        assert instagram_falso.pedidos == []

    def test_atualizar_agora_de_90_dias_e_recusado(self, cliente, instagram_falso):
        assert _atualizar(cliente, "90d").status_code == 422
        assert instagram_falso.pedidos == []


class TestSemCredencial:
    def test_sem_token_o_endpoint_responde_503_de_configuracao(self, monkeypatch, cliente, instagram_falso):
        monkeypatch.setattr(settings, "instagram_access_token", "")
        monkeypatch.setattr(settings, "instagram_business_account_id", "")

        resposta = _ler(cliente)

        assert resposta.status_code == 503
        detalhe = resposta.json()["detail"]
        # A frase fixa, sem nome de variável (issue #843).
        assert detalhe == provedor_instagram.FRASE_NAO_CONFIGURADO
        assert "INSTAGRAM_ACCESS_TOKEN" not in detalhe
        assert set(resposta.json()) == {"detail"}
        assert instagram_falso.pedidos == []


@pytest.mark.usefixtures("instagram_configurado")
class TestTokenVencido:
    def test_com_numero_guardado_mantem_o_ultimo_valor_bom_e_avisa_da_renovacao(
        self, cliente, instagram_falso, relogio_da_central
    ):
        """Aquece o cache com o token válido, passa da hora e o token vence: a
        tela recebe os números bons, marcados, com a frase de renovação. Nunca
        zera, nunca mostra erro técnico."""
        _ler(cliente)
        relogio_da_central.avancar(hours=2)
        instagram_falso.forcar = erro_do_instagram(400, 190, "OAuthException", "Session has expired.")

        resposta = _ler(cliente)

        assert resposta.status_code == 200, resposta.text
        corpo = resposta.json()
        assert corpo["seguidores"]["total"] == 18420
        assert corpo["alcance"]["atual"] == 41280
        assert corpo["frescor"]["atualizacao_falhou"] is True
        motivo = corpo["frescor"]["motivo"].lower()
        assert "renov" in motivo
        assert "instagram" in motivo

    def test_sem_numero_guardado_e_erro_honesto(self, cliente, instagram_falso, relogio_da_central):
        """Token vencido e nada guardado: 502, como qualquer falha da fonte sem
        último valor bom. Nunca zero, nunca lista vazia."""
        instagram_falso.forcar = erro_do_instagram(400, 190, "OAuthException", "Session has expired.")

        resposta = _ler(cliente)

        assert resposta.status_code == 502
        assert set(resposta.json()) == {"detail"}
        assert "seguidores" not in resposta.json()
