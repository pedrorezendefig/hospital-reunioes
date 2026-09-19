"""O frescor dos números da Central de Comando pela rota real (issue #815).

O seam é a ROTA HTTP, como em `test_central_de_comando_visao_geral.py`, com o
app mínimo com o gate de pé e as pessoas logadas de `central_de_comando_apoio.py`
(`cliente_da_central`). Dublados só o que é fronteira: quem está logado, a rede
do Google (`google_falso`) e os dois relógios da Central, o do dia
(`hoje_da_central`) e o do cache (`relogio_da_central`). O cache é o de
verdade, o do processo, e o `google_falso` o entrega vazio a cada teste; quem
não pede o `google_falso` e pode gravar no cache pede o `cache_da_central`.

O que se observa é o que a tela recebe: o número, o carimbo de frescor e se a
leitura foi ou não à fonte (`google_falso.pedidos`). Cada pergunta de
Visitantes é um pedido; a Visão Geral faz dois por leitura (o período e o
anterior).
"""

from __future__ import annotations

import os
import sys

import httpx
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from central_de_comando_apoio import PREFIXO_DA_CENTRAL as PREFIXO  # noqa: E402
from central_de_comando_apoio import (  # noqa: E402
    SECRETARIA,
    SUPER_ADMIN,
    cliente_da_central,
    erro_da_ga4,
)

from app.services.central_de_comando import telas  # noqa: E402

# Os pedidos que uma leitura da Visão Geral faz ao Google: o período e o anterior.
PEDIDOS_POR_LEITURA = 2

# O limitador de taxa e o participante do gate zerados antes e depois de cada
# teste (fixture de `central_de_comando_apoio.py`).
pytestmark = pytest.mark.usefixtures("gate_e_limitador_zerados")


@pytest.fixture(autouse=True)
def _central_no_dia_de_teste(hoje_da_central, central_configurada):
    """Todo teste daqui vive em 18/09/2026, com a Central ligada ao Google."""


@pytest.fixture
def cliente():
    """Um cliente só por teste: as leituras de um teste falam com o mesmo app."""
    return cliente_da_central(SUPER_ADMIN)


def _ler(cliente, periodo: str = "28d"):
    return cliente.get(f"{PREFIXO}/visao-geral", params={"periodo": periodo})


def _atualizar_agora(cliente, periodo: str = "28d", tela: str = "visao-geral"):
    return cliente.post(f"{PREFIXO}/atualizar-agora", params={"tela": tela, "periodo": periodo})


class TestFrescorNoPayload:
    def test_a_visao_geral_diz_de_quando_sao_os_numeros(self, cliente, google_falso, relogio_da_central):
        corpo = _ler(cliente).json()

        assert corpo["frescor"] == {
            "atualizado_em": "2026-09-18T13:45:00+00:00",
            "atualizacao_falhou": False,
            "motivo": None,
        }
        assert corpo["visitantes"]["atual"] == 12345


class TestUmaHoraDeCache:
    def test_segunda_leitura_da_mesma_tela_e_periodo_dentro_da_hora_nao_vai_a_fonte(
        self, cliente, google_falso, relogio_da_central
    ):
        primeira = _ler(cliente).json()
        google_falso.visitantes[("2026-08-21", "2026-09-17")] = 99999
        relogio_da_central.avancar(minutes=59)

        segunda = _ler(cliente).json()

        assert len(google_falso.pedidos) == PEDIDOS_POR_LEITURA
        assert segunda == primeira
        assert segunda["frescor"]["atualizado_em"] == "2026-09-18T13:45:00+00:00"

    def test_passada_a_hora_a_leitura_busca_numeros_novos(self, cliente, google_falso, relogio_da_central):
        _ler(cliente)
        google_falso.visitantes[("2026-08-21", "2026-09-17")] = 12400
        relogio_da_central.avancar(hours=1)

        corpo = _ler(cliente).json()

        assert len(google_falso.pedidos) == 2 * PEDIDOS_POR_LEITURA
        assert corpo["visitantes"]["atual"] == 12400
        assert corpo["frescor"]["atualizado_em"] == "2026-09-18T14:45:00+00:00"

    def test_outro_periodo_e_outra_chave(self, cliente, google_falso, relogio_da_central):
        """A chave é tela e período: os 28 dias guardados não respondem pelos 7."""
        _ler(cliente, "28d")

        corpo = _ler(cliente, "7d").json()

        assert len(google_falso.pedidos) == 2 * PEDIDOS_POR_LEITURA
        assert corpo["visitantes"]["atual"] == 3100
        assert corpo["periodo"]["chave"] == "7d"


class TestAtualizarAgora:
    def test_vai_a_fonte_mesmo_com_o_cache_valido_e_o_carimbo_muda(self, cliente, google_falso, relogio_da_central):
        _ler(cliente)
        google_falso.visitantes[("2026-08-21", "2026-09-17")] = 12400
        relogio_da_central.avancar(minutes=5)

        resposta = _atualizar_agora(cliente)

        assert resposta.status_code == 200, resposta.text
        corpo = resposta.json()
        assert len(google_falso.pedidos) == 2 * PEDIDOS_POR_LEITURA
        assert corpo["visitantes"]["atual"] == 12400
        assert corpo["frescor"] == {
            "atualizado_em": "2026-09-18T13:50:00+00:00",
            "atualizacao_falhou": False,
            "motivo": None,
        }

    def test_depois_dele_a_leitura_comum_ja_serve_o_numero_novo(self, cliente, google_falso, relogio_da_central):
        _ler(cliente)
        google_falso.visitantes[("2026-08-21", "2026-09-17")] = 12400
        relogio_da_central.avancar(minutes=5)
        _atualizar_agora(cliente)
        relogio_da_central.avancar(minutes=5)

        corpo = _ler(cliente).json()

        assert len(google_falso.pedidos) == 2 * PEDIDOS_POR_LEITURA
        assert corpo["visitantes"]["atual"] == 12400
        assert corpo["frescor"]["atualizado_em"] == "2026-09-18T13:50:00+00:00"

    def test_renova_so_o_periodo_pedido(self, cliente, google_falso, relogio_da_central):
        _ler(cliente, "7d")
        _ler(cliente, "28d")
        relogio_da_central.avancar(minutes=5)

        corpo = _atualizar_agora(cliente, "7d").json()
        relogio_da_central.avancar(minutes=1)
        de_28_dias = _ler(cliente, "28d").json()

        assert corpo["periodo"]["chave"] == "7d"
        assert corpo["frescor"]["atualizado_em"] == "2026-09-18T13:50:00+00:00"
        assert de_28_dias["frescor"]["atualizado_em"] == "2026-09-18T13:45:00+00:00"
        assert len(google_falso.pedidos) == 3 * PEDIDOS_POR_LEITURA

    @pytest.mark.parametrize("tela", ["ao-vivo", "", "../visao-geral", "Visao-Geral"])
    def test_tela_que_nao_esta_no_cache_e_recusada_sem_consultar_o_google(self, cliente, google_falso, tela):
        """Só tela registrada tem Atualizar agora. O Ao vivo não é tela do
        cache: ele não tem o que forçar, porque nunca é guardado. (O Instagram
        entrou no registro na #819, então saiu desta lista.)"""
        resposta = _atualizar_agora(cliente, tela=tela)

        assert resposta.status_code == 422
        assert google_falso.pedidos == []

    @pytest.mark.parametrize("periodo", ["30d", "7", "", "ano"])
    def test_periodo_que_nao_existe_e_recusado_sem_consultar_o_google(self, cliente, google_falso, periodo):
        resposta = _atualizar_agora(cliente, periodo)

        assert resposta.status_code == 422
        assert google_falso.pedidos == []

    def test_tem_limite_de_taxa_de_5_por_minuto(self, cliente, google_falso, relogio_da_central):
        """Cada Atualizar agora é uma ida garantida ao Google, que tem cota: o
        sexto seguido no mesmo minuto leva 429 e não chega à fonte. O limitador
        é zerado antes e depois de cada teste (`gate_e_limitador_zerados`, no
        `pytestmark` do topo do arquivo)."""
        respostas = [_atualizar_agora(cliente).status_code for _ in range(5)]
        pedidos_antes = len(google_falso.pedidos)

        sexto = _atualizar_agora(cliente)

        assert respostas == [200] * 5
        assert sexto.status_code == 429
        assert len(google_falso.pedidos) == pedidos_antes

    def test_o_limite_nao_trava_a_leitura_comum(self, cliente, google_falso, relogio_da_central):
        """Estourar o Atualizar agora não tira a tela do ar: a leitura comum
        tem o limite dela e segue servindo o que está guardado."""
        for _ in range(6):
            _atualizar_agora(cliente)

        assert _ler(cliente).status_code == 200

    def test_tela_registrada_ganha_o_atualizar_agora_sem_rota_nova(
        self, monkeypatch, cliente, relogio_da_central, cache_da_central
    ):
        """O ponto de extensão das fatias seguintes (#817, #818): a tela entra
        no registro de `telas.py` e o Atualizar agora já vale para ela, com o
        frescor no payload e a chave por período. Sem o `google_falso`, quem
        esvazia o cache do processo no fim é o `cache_da_central`."""
        idas: list[str] = []

        def montar(periodo):
            idas.append(periodo)
            return {"numero": len(idas)}

        monkeypatch.setitem(telas.TELAS, "tela-de-teste", telas.Tela(montar=montar, falhas=(RuntimeError,)))

        corpo = _atualizar_agora(cliente, "7d", tela="tela-de-teste").json()

        assert corpo == {
            "numero": 1,
            "frescor": {"atualizado_em": "2026-09-18T13:45:00+00:00", "atualizacao_falhou": False, "motivo": None},
        }
        assert idas == ["7d"]

    def test_periodo_que_a_tela_nao_tem_e_recusado(self, monkeypatch, cliente, cache_da_central):
        """O Instagram não tem 90 dias: tela registrada só com 7 e 28 recusa o
        Atualizar agora de 90, sem buscar nada."""
        idas: list[str] = []
        monkeypatch.setitem(
            telas.TELAS,
            "tela-de-teste",
            telas.Tela(montar=idas.append, falhas=(RuntimeError,), periodos=("7d", "28d")),
        )

        resposta = _atualizar_agora(cliente, "90d", tela="tela-de-teste")

        assert resposta.status_code == 422
        assert idas == []

    def test_quem_nao_e_super_admin_nao_forca_ida_nenhuma_ao_google(self, google_falso):
        """O gate do router vale para o Atualizar agora: secretária leva 403 e
        o Google nem é chamado."""
        resposta = _atualizar_agora(cliente_da_central(SECRETARIA))

        assert resposta.status_code == 403
        assert google_falso.pedidos == []


# ─── A fonte caiu: último valor bom, ou erro honesto ─────────────────────────


class TestFonteFora:
    def test_com_numero_guardado_a_tela_mostra_o_ultimo_valor_bom_e_o_aviso(
        self, cliente, google_falso, relogio_da_central
    ):
        """Passou da hora e o Google caiu: a tela recebe os números de 13h45,
        com a marca de que a atualização falhou e a frase do porquê. Nunca
        zero, nunca a tela vazia."""
        _ler(cliente)
        relogio_da_central.avancar(hours=2)
        google_falso.forcar = erro_da_ga4(500, "INTERNAL", "Internal error encountered.")

        resposta = _ler(cliente)

        assert resposta.status_code == 200, resposta.text
        corpo = resposta.json()
        assert corpo["visitantes"] == {"atual": 12345, "anterior": 10000, "variacao": pytest.approx(0.2345)}
        assert corpo["frescor"] == {
            "atualizado_em": "2026-09-18T13:45:00+00:00",
            "atualizacao_falhou": True,
            "motivo": "O Google Analytics respondeu HTTP 500.",
        }

    def test_atualizar_agora_que_falha_devolve_o_ultimo_valor_bom_e_o_aviso(
        self, cliente, google_falso, relogio_da_central
    ):
        _ler(cliente)
        relogio_da_central.avancar(minutes=10)
        google_falso.forcar = httpx.ReadTimeout("lento demais")

        resposta = _atualizar_agora(cliente)

        assert resposta.status_code == 200, resposta.text
        corpo = resposta.json()
        assert corpo["visitantes"]["atual"] == 12345
        assert corpo["frescor"]["atualizado_em"] == "2026-09-18T13:45:00+00:00"
        assert corpo["frescor"]["atualizacao_falhou"] is True
        assert "tempo esperado" in corpo["frescor"]["motivo"]

    def test_o_aviso_some_quando_a_fonte_volta(self, cliente, google_falso, relogio_da_central):
        _ler(cliente)
        relogio_da_central.avancar(hours=2)
        google_falso.forcar = erro_da_ga4(503, "UNAVAILABLE", "The service is currently unavailable.")
        _ler(cliente)
        google_falso.forcar = None
        relogio_da_central.avancar(minutes=1)

        corpo = _atualizar_agora(cliente).json()

        assert corpo["frescor"] == {
            "atualizado_em": "2026-09-18T15:46:00+00:00",
            "atualizacao_falhou": False,
            "motivo": None,
        }

    def test_sem_numero_guardado_e_erro_honesto(self, cliente, google_falso, relogio_da_central):
        """Nada para mostrar: 502 com a frase, como antes do cache."""
        google_falso.forcar = erro_da_ga4(500, "INTERNAL", "Internal error encountered.")

        leitura = _ler(cliente)
        atualizar = _atualizar_agora(cliente)

        for resposta in (leitura, atualizar):
            assert resposta.status_code == 502
            assert set(resposta.json()) == {"detail"}
            assert "HTTP 500" in resposta.json()["detail"]


# ─── O registro de telas, a porta das fatias seguintes ───────────────────────


class FonteDeTesteForaError(Exception):
    """A falha de fonte da tela de mentira, com frase fixa."""


@pytest.fixture
def tela_de_teste(monkeypatch, cache_da_central, relogio_da_central) -> list[str]:
    """Uma tela de mentira no registro, só com 7 e 28 dias (como o Instagram).
    Devolve a lista dos períodos que o `montar` dela buscou."""
    idas: list[str] = []

    def montar(periodo):
        idas.append(periodo)
        return {"periodo": periodo, "bloco": {"numeros": [1, 2]}}

    monkeypatch.setitem(
        telas.TELAS,
        "tela-de-teste",
        telas.Tela(montar=montar, falhas=(FonteDeTesteForaError,), periodos=("7d", "28d")),
    )
    return idas


class TestRegistroDeTelas:
    """`telas.ler`, que a rota de cada tela e o Atualizar agora chamam, testado
    direto com uma tela de mentira."""

    def test_quem_mexe_no_payload_devolvido_nao_mexe_no_guardado(self, tela_de_teste):
        """O payload guardado é o mesmo para todo Super admin por 1 hora: uma
        rota que anotasse algo no payload devolvido (um status por bloco, por
        exemplo) não pode mudar o que a leitura seguinte recebe."""
        primeiro = telas.ler("tela-de-teste", "28d")
        primeiro["bloco"]["numeros"].append(999)
        primeiro["periodo"] = "adulterado"

        segundo = telas.ler("tela-de-teste", "28d")

        assert segundo["bloco"] == {"numeros": [1, 2]}
        assert segundo["periodo"] == "28d"
        assert tela_de_teste == ["28d"]

    def test_periodo_que_a_tela_nao_tem_e_recusado_sem_buscar_nada(self, tela_de_teste):
        """A regra mora na porta, e não só na rota do Atualizar agora: a rota
        de leitura de uma tela sem 90 dias não guardaria 90 dias por esquecer
        de conferir."""
        with pytest.raises(telas.PedidoDeTelaInvalidoError, match="90d"):
            telas.ler("tela-de-teste", "90d")

        assert tela_de_teste == []

    def test_tela_que_nao_esta_no_registro_e_recusada(self, cache_da_central):
        with pytest.raises(telas.PedidoDeTelaInvalidoError, match="ao-vivo"):
            telas.ler("ao-vivo", "28d")

    def test_forcar_tambem_passa_pela_regra(self, tela_de_teste):
        with pytest.raises(telas.PedidoDeTelaInvalidoError):
            telas.ler("tela-de-teste", "90d", forcar=True)

        assert tela_de_teste == []
