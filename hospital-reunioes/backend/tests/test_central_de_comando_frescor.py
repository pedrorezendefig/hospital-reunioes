"""O frescor dos números da Central de Comando pela rota real (issue #815).

O seam é a ROTA HTTP, com o app mínimo com o gate de pé e as pessoas logadas de
`central_de_comando_apoio.py` (`cliente_da_central`). Dublados só o que é
fronteira: quem está logado, a rede do Google (`google_falso` com o
`lote_da_ga4`) e os dois relógios da Central, o do dia (`hoje_da_central`) e o do
cache (`relogio_da_central`). O cache é o de verdade, o do processo, e o
`google_falso` o entrega vazio a cada teste.

**A tela usada aqui é a Dados do Google (#817).** É a tela de chave única mais
simples que passa pelo cache com frescor: uma leitura pergunta tudo à GA4 em
dois `batchRunReports` (sete relatórios, e o lote leva no máximo cinco). A Visão
Geral saiu do registro de chave única na #821 (virou tela
composta, um bloco por chave, cada bloco degradando sozinho): o frescor por
bloco dela é testado em `test_central_de_comando_visao_geral.py`, e o mecânico
do cache de #815 continua aqui, na tela que ainda é tudo ou nada.

O que se observa é o que a tela recebe: o número (as Visitas do dispositivo
líder), o carimbo de frescor e se a leitura foi ou não à fonte
(`google_falso.pedidos`).
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

# Uma leitura da tela Dados do Google faz dois `batchRunReports` (sete
# relatórios, cinco por lote).
PEDIDOS_POR_LEITURA = 2

# O intervalo de 28 dias, chave das tabelas do `lote_da_ga4`.
_28_DIAS = ("2026-08-21", "2026-09-17")

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
    return cliente.get(f"{PREFIXO}/dados-do-google", params={"periodo": periodo})


def _atualizar_agora(cliente, periodo: str = "28d", tela: str = "dados-do-google"):
    return cliente.post(f"{PREFIXO}/atualizar-agora", params={"tela": tela, "periodo": periodo})


def _lider(corpo: dict) -> int:
    """As Visitas do dispositivo líder: o número que estas mecânicas observam."""
    return corpo["dispositivos"][0]["visitas"]


class TestFrescorNoPayload:
    def test_a_tela_diz_de_quando_sao_os_numeros(self, cliente, google_falso, lote_da_ga4, relogio_da_central):
        corpo = _ler(cliente).json()

        assert corpo["frescor"] == {
            "atualizado_em": "2026-09-18T13:45:00+00:00",
            "atualizacao_falhou": False,
            "motivo": None,
        }
        assert _lider(corpo) == 7100


class TestUmaHoraDeCache:
    def test_segunda_leitura_da_mesma_tela_e_periodo_dentro_da_hora_nao_vai_a_fonte(
        self, cliente, google_falso, lote_da_ga4, relogio_da_central
    ):
        primeira = _ler(cliente).json()
        lote_da_ga4.visitas_por_dispositivo[_28_DIAS] = {"mobile": 8000}
        relogio_da_central.avancar(minutes=59)

        segunda = _ler(cliente).json()

        assert len(google_falso.pedidos) == PEDIDOS_POR_LEITURA
        assert segunda == primeira
        assert segunda["frescor"]["atualizado_em"] == "2026-09-18T13:45:00+00:00"

    def test_passada_a_hora_a_leitura_busca_numeros_novos(self, cliente, google_falso, lote_da_ga4, relogio_da_central):
        _ler(cliente)
        lote_da_ga4.visitas_por_dispositivo[_28_DIAS] = {"mobile": 8000}
        relogio_da_central.avancar(hours=1)

        corpo = _ler(cliente).json()

        assert len(google_falso.pedidos) == 2 * PEDIDOS_POR_LEITURA
        assert _lider(corpo) == 8000
        assert corpo["frescor"]["atualizado_em"] == "2026-09-18T14:45:00+00:00"

    def test_outro_periodo_e_outra_chave(self, cliente, google_falso, lote_da_ga4, relogio_da_central):
        """A chave é tela e período: os 28 dias guardados não respondem pelos 7."""
        _ler(cliente, "28d")

        corpo = _ler(cliente, "7d").json()

        assert len(google_falso.pedidos) == 2 * PEDIDOS_POR_LEITURA
        assert corpo["periodo"]["chave"] == "7d"
        assert _lider(corpo) == 1850


class TestAtualizarAgora:
    def test_vai_a_fonte_mesmo_com_o_cache_valido_e_o_carimbo_muda(
        self, cliente, google_falso, lote_da_ga4, relogio_da_central
    ):
        _ler(cliente)
        lote_da_ga4.visitas_por_dispositivo[_28_DIAS] = {"mobile": 8000}
        relogio_da_central.avancar(minutes=5)

        resposta = _atualizar_agora(cliente)

        assert resposta.status_code == 200, resposta.text
        corpo = resposta.json()
        assert len(google_falso.pedidos) == 2 * PEDIDOS_POR_LEITURA
        assert _lider(corpo) == 8000
        assert corpo["frescor"] == {
            "atualizado_em": "2026-09-18T13:50:00+00:00",
            "atualizacao_falhou": False,
            "motivo": None,
        }

    def test_depois_dele_a_leitura_comum_ja_serve_o_numero_novo(
        self, cliente, google_falso, lote_da_ga4, relogio_da_central
    ):
        _ler(cliente)
        lote_da_ga4.visitas_por_dispositivo[_28_DIAS] = {"mobile": 8000}
        relogio_da_central.avancar(minutes=5)
        _atualizar_agora(cliente)
        relogio_da_central.avancar(minutes=5)

        corpo = _ler(cliente).json()

        assert len(google_falso.pedidos) == 2 * PEDIDOS_POR_LEITURA
        assert _lider(corpo) == 8000
        assert corpo["frescor"]["atualizado_em"] == "2026-09-18T13:50:00+00:00"

    def test_renova_so_o_periodo_pedido(self, cliente, google_falso, lote_da_ga4, relogio_da_central):
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

    @pytest.mark.parametrize("tela", ["ao-vivo", "", "../dados-do-google", "Dados-do-Google"])
    def test_tela_que_nao_esta_no_cache_e_recusada_sem_consultar_o_google(self, cliente, google_falso, tela):
        """Só tela registrada tem Atualizar agora. O Ao vivo não é tela do cache;
        a Visão Geral é composta e o nome dela só vale exato (o Atualizar agora
        dela é despachado à parte)."""
        resposta = _atualizar_agora(cliente, tela=tela)

        assert resposta.status_code == 422
        assert google_falso.pedidos == []

    @pytest.mark.parametrize("periodo", ["30d", "7", "", "ano"])
    def test_periodo_que_nao_existe_e_recusado_sem_consultar_o_google(self, cliente, google_falso, periodo):
        resposta = _atualizar_agora(cliente, periodo)

        assert resposta.status_code == 422
        assert google_falso.pedidos == []

    def test_tem_limite_de_taxa_de_5_por_minuto(self, cliente, google_falso, lote_da_ga4, relogio_da_central):
        """Cada Atualizar agora é uma ida garantida ao Google, que tem cota: o
        sexto seguido no mesmo minuto leva 429 e não chega à fonte."""
        respostas = [_atualizar_agora(cliente).status_code for _ in range(5)]
        pedidos_antes = len(google_falso.pedidos)

        sexto = _atualizar_agora(cliente)

        assert respostas == [200] * 5
        assert sexto.status_code == 429
        assert len(google_falso.pedidos) == pedidos_antes

    def test_o_limite_nao_trava_a_leitura_comum(self, cliente, google_falso, lote_da_ga4, relogio_da_central):
        """Estourar o Atualizar agora não tira a tela do ar: a leitura comum tem
        o limite dela e segue servindo o que está guardado."""
        for _ in range(6):
            _atualizar_agora(cliente)

        assert _ler(cliente).status_code == 200

    def test_tela_registrada_ganha_o_atualizar_agora_sem_rota_nova(
        self, monkeypatch, cliente, relogio_da_central, cache_da_central
    ):
        """O ponto de extensão das fatias seguintes (#817, #818): a tela entra no
        registro de `telas.py` e o Atualizar agora já vale para ela, com o frescor
        no payload e a chave por período."""
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
        """O gate do router vale para o Atualizar agora: secretária leva 403 e o
        Google nem é chamado."""
        resposta = _atualizar_agora(cliente_da_central(SECRETARIA))

        assert resposta.status_code == 403
        assert google_falso.pedidos == []


# ─── A fonte caiu: último valor bom, ou erro honesto ─────────────────────────


class TestFonteFora:
    def test_com_numero_guardado_a_tela_mostra_o_ultimo_valor_bom_e_o_aviso(
        self, cliente, google_falso, lote_da_ga4, relogio_da_central
    ):
        """Passou da hora e o Google caiu: a tela recebe os números de 13h45, com
        a marca de que a atualização falhou e a frase do porquê. Nunca zero."""
        _ler(cliente)
        relogio_da_central.avancar(hours=2)
        google_falso.forcar = erro_da_ga4(500, "INTERNAL", "Internal error encountered.")

        resposta = _ler(cliente)

        assert resposta.status_code == 200, resposta.text
        corpo = resposta.json()
        assert _lider(corpo) == 7100
        assert corpo["frescor"] == {
            "atualizado_em": "2026-09-18T13:45:00+00:00",
            "atualizacao_falhou": True,
            "motivo": "O Google Analytics respondeu HTTP 500.",
        }

    def test_atualizar_agora_que_falha_devolve_o_ultimo_valor_bom_e_o_aviso(
        self, cliente, google_falso, lote_da_ga4, relogio_da_central
    ):
        _ler(cliente)
        relogio_da_central.avancar(minutes=10)
        google_falso.forcar = httpx.ReadTimeout("lento demais")

        resposta = _atualizar_agora(cliente)

        assert resposta.status_code == 200, resposta.text
        corpo = resposta.json()
        assert _lider(corpo) == 7100
        assert corpo["frescor"]["atualizado_em"] == "2026-09-18T13:45:00+00:00"
        assert corpo["frescor"]["atualizacao_falhou"] is True
        assert "tempo esperado" in corpo["frescor"]["motivo"]

    def test_o_aviso_some_quando_a_fonte_volta(self, cliente, google_falso, lote_da_ga4, relogio_da_central):
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

    def test_sem_numero_guardado_e_erro_honesto(self, cliente, google_falso, lote_da_ga4, relogio_da_central):
        """Nada para mostrar: 502 com a frase, como antes do cache. A tela de
        chave única segue tudo ou nada (a Visão Geral, composta, não)."""
        google_falso.forcar = erro_da_ga4(500, "INTERNAL", "Internal error encountered.")

        leitura = _ler(cliente)
        atualizar = _atualizar_agora(cliente)

        for resposta in (leitura, atualizar):
            assert resposta.status_code == 502
            assert set(resposta.json()) == {"detail"}
            assert "HTTP 500" in resposta.json()["detail"]


# ─── O registro de telas, a porta das fatias seguintes ───────────────────────


class TestEsperaDepoisDeFalha:
    """Com o Google fora, a leitura não volta a ele por 5 minutos (issue #858):
    a tela segue com o último valor bom e o aviso, sem nova ida. O Atualizar
    agora continua forçando."""

    def _google_caiu(self, cliente, google_falso, relogio_da_central):
        _ler(cliente)
        relogio_da_central.avancar(hours=2)
        google_falso.forcar = erro_da_ga4(500, "INTERNAL", "Internal error encountered.")
        _ler(cliente)
        return len(google_falso.pedidos)

    def test_leituras_seguidas_dentro_da_espera_nao_vao_ao_google(
        self, cliente, google_falso, lote_da_ga4, relogio_da_central
    ):
        idas = self._google_caiu(cliente, google_falso, relogio_da_central)
        relogio_da_central.avancar(minutes=4)

        respostas = [_ler(cliente) for _ in range(3)]

        assert len(google_falso.pedidos) == idas
        for resposta in respostas:
            assert resposta.status_code == 200, resposta.text
            assert _lider(resposta.json()) == 7100
            assert resposta.json()["frescor"]["atualizacao_falhou"] is True

    def test_passada_a_espera_a_leitura_tenta_o_google_de_novo(
        self, cliente, google_falso, lote_da_ga4, relogio_da_central
    ):
        idas = self._google_caiu(cliente, google_falso, relogio_da_central)
        relogio_da_central.avancar(minutes=5)
        google_falso.forcar = None

        corpo = _ler(cliente).json()

        assert len(google_falso.pedidos) > idas
        assert corpo["frescor"]["atualizacao_falhou"] is False

    def test_o_atualizar_agora_forca_a_ida_dentro_da_espera(
        self, cliente, google_falso, lote_da_ga4, relogio_da_central
    ):
        idas = self._google_caiu(cliente, google_falso, relogio_da_central)
        relogio_da_central.avancar(minutes=1)
        google_falso.forcar = None

        resposta = _atualizar_agora(cliente)

        assert resposta.status_code == 200, resposta.text
        assert len(google_falso.pedidos) > idas
        assert resposta.json()["frescor"]["atualizacao_falhou"] is False


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

    def test_a_frase_da_falha_fica_guardada_ate_a_proxima_busca_sem_prazo(
        self, monkeypatch, cache_da_central, relogio_da_central
    ):
        """O que o docstring de `Tela.falhas` promete sobre a frase da falha
        (revisão do PR #831, #834): ela fica guardada até a próxima busca
        daquela chave, sem prazo, porque o cache não despeja. O Google cai na
        sexta à noite e ninguém abre a Central até segunda: a frase segue
        guardada o fim de semana inteiro. Prometer "até 1 hora" dizia menos do
        que o cache guarda, e é por isso que só entra frase fixa e segura."""
        fonte_fora = {"agora": False}

        def montar(periodo):
            if fonte_fora["agora"]:
                raise FonteDeTesteForaError("A fonte de teste está fora.")
            return {"periodo": periodo}

        monkeypatch.setitem(
            telas.TELAS,
            "tela-de-teste",
            telas.Tela(montar=montar, falhas=(FonteDeTesteForaError,), periodos=("28d",)),
        )
        telas.ler("tela-de-teste", "28d")
        fonte_fora["agora"] = True
        telas.ler("tela-de-teste", "28d", forcar=True)
        relogio_da_central.avancar(hours=60)

        guardado = cache_da_central.frescor(("tela-de-teste", "28d"))

        assert guardado.motivo == "A fonte de teste está fora."
        promessa = " ".join((telas.Tela.__doc__ or "").split())
        assert "até a próxima busca daquela chave" in promessa
        assert "sem prazo" in promessa
        assert "1 hora" not in promessa
