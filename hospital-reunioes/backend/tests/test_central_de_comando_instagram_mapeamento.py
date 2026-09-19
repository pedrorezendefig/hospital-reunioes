"""As regras puras do provedor de Instagram, testadas direto (issue #819).

Porte de `src/lib/instagram/meta-mappers.test.ts` do repositório antigo, com as
MESMAS regras, adaptando o nome do provedor para "instagram" (a empresa dona da
rede nunca aparece em identificador nem em tela). Regras puras: nenhuma função
daqui fala com rede, banco ou relógio. O seam é a própria função de mapeamento,
como `area_da_pagina` e `origem_do_canal` do provedor do Google (PRD #809,
"Regras puras testadas direto").

Os valores esperados foram contados à mão a partir das entradas, e não pela
mesma conta do código: é a fonte independente contra a qual o mapeamento é
conferido.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date  # noqa: E402

from app.services.central_de_comando import provedor_instagram as ig  # noqa: E402
from app.services.central_de_comando.periodo import Intervalo  # noqa: E402


def iv(nome: str, valor: int) -> dict:
    """Um insight da conta, como a Graph API entrega com `metric_type=total_value`."""
    return {"name": nome, "total_value": {"value": valor}}


def follows(ganhos: int, perdidos: int) -> dict:
    """O insight `follows_and_unfollows` com o breakdown por `follow_type`."""
    return {
        "name": "follows_and_unfollows",
        "total_value": {
            "breakdowns": [
                {
                    "results": [
                        {"dimension_values": ["FOLLOWER"], "value": ganhos},
                        {"dimension_values": ["NON_FOLLOWER"], "value": perdidos},
                    ]
                }
            ]
        },
    }


class TestMontarSaude:
    def test_junta_seguidores_e_insights_atual_e_anterior_ausentes_viram_zero(self):
        atual = [
            iv("reach", 100),
            iv("views", 250),
            iv("total_interactions", 40),
            iv("accounts_engaged", 30),
            iv("likes", 25),
            iv("comments", 6),
            iv("saves", 5),
            iv("shares", 4),
        ]
        anterior = [iv("reach", 80)]

        saude = ig.montar_saude(18420, atual, anterior, follows(775, 34), follows(500, 20))

        assert saude.seguidores == 18420
        assert saude.alcance == 100
        assert saude.alcance_anterior == 80
        assert saude.visualizacoes == 250
        # `views` ausente no anterior vira 0, e nunca None.
        assert saude.visualizacoes_anterior == 0
        assert saude.interacoes == 40
        assert saude.contas_engajadas == 30
        assert saude.partes.curtidas == 25
        assert saude.partes.comentarios == 6
        assert saude.partes.salvamentos == 5
        assert saude.partes.compartilhamentos == 4
        # crescimento = ganhos - perdidos, no atual e no anterior.
        assert saude.crescimento == 741
        assert saude.crescimento_anterior == 480
        assert saude.seguidores_ganhos == 775
        assert saude.seguidores_perdidos == 34


class TestDeltaDeSeguidores:
    def test_le_follower_como_ganho_e_non_follower_como_perda(self):
        assert ig.delta_de_seguidores(follows(775, 34)) == (775, 34)

    def test_insight_ausente_ou_sem_breakdown_e_zero_a_zero(self):
        assert ig.delta_de_seguidores(None) == (0, 0)
        assert ig.delta_de_seguidores({"name": "follows_and_unfollows"}) == (0, 0)


class TestTipoDeMidia:
    def test_imagem(self):
        assert ig.tipo_de_midia("IMAGE", None) == "imagem"

    def test_carrossel(self):
        assert ig.tipo_de_midia("CAROUSEL_ALBUM", None) == "carrossel"

    def test_reel_e_video_pelo_media_product_type(self):
        assert ig.tipo_de_midia("VIDEO", "REELS") == "reel"
        assert ig.tipo_de_midia("VIDEO", "FEED") == "video"

    def test_qualquer_outro_cai_em_video(self):
        assert ig.tipo_de_midia("QUALQUER", None) == "video"


class TestDentroDoPeriodo:
    def test_filtra_pela_janela_inclusive_pela_data_do_timestamp(self):
        intervalo = Intervalo(inicio=date(2026, 6, 15), fim=date(2026, 6, 21))

        assert ig.dentro_do_periodo("2026-06-15T09:00:00Z", intervalo) is True
        assert ig.dentro_do_periodo("2026-06-21T23:00:00Z", intervalo) is True
        assert ig.dentro_do_periodo("2026-06-14T23:00:00Z", intervalo) is False


class TestParaPublicacao:
    def test_miniatura_cai_para_media_url_quando_nao_ha_thumbnail(self):
        midia = {
            "id": "9",
            "media_type": "IMAGE",
            "permalink": "https://x/p/9",
            "timestamp": "2026-06-18T00:00:00Z",
            "media_url": "https://x/img.jpg",
        }

        pub = ig.para_publicacao(midia, 77)

        assert pub.id == "9"
        assert pub.legenda is None
        assert pub.tipo == "imagem"
        assert pub.miniatura == "https://x/img.jpg"
        assert pub.link == "https://x/p/9"
        assert pub.data == "2026-06-18T00:00:00Z"
        assert pub.interacoes == 77

    def test_prefere_thumbnail_quando_existe(self):
        midia = {
            "id": "9",
            "media_type": "VIDEO",
            "media_product_type": "REELS",
            "permalink": "https://x/p/9",
            "timestamp": "2026-06-18T00:00:00Z",
            "media_url": "https://x/video.mp4",
            "thumbnail_url": "https://x/thumb.jpg",
            "caption": "Bastidores",
        }

        pub = ig.para_publicacao(midia, 5)

        assert pub.miniatura == "https://x/thumb.jpg"
        assert pub.tipo == "reel"
        assert pub.legenda == "Bastidores"


class TestRanquearPorInteracoes:
    def test_ordena_desc_e_corta_no_limite(self):
        posts = [
            ig.Publicacao("a", None, "imagem", "", "https://x/a", "2026-06-18T00:00:00Z", 10),
            ig.Publicacao("b", None, "imagem", "", "https://x/b", "2026-06-18T00:00:00Z", 90),
            ig.Publicacao("c", None, "imagem", "", "https://x/c", "2026-06-18T00:00:00Z", 50),
        ]

        ranqueadas = ig.ranquear_por_interacoes(posts, 2)

        assert [p.id for p in ranqueadas] == ["b", "c"]
