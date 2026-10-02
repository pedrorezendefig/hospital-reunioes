"""O Ao vivo da Central de Comando pela rota real (issue #816, ADR 0058).

O Ao vivo é o único número em tempo real da Central: quantas pessoas estão no
Site agora (glossário, "Ao vivo"). Ele lê a fonte de tempo real do Google (o
`runRealtimeReport` da GA4) e NUNCA passa pelo cache, porque cache de 1 hora
mataria o "agora". Por isso não é tela do registro de `telas.py` e não tem
Atualizar agora.

O seam é o mesmo das outras fatias da Central: a ROTA HTTP, com
`require_super_admin` de pé, dublando só quem está logado e a fronteira de rede
do Google (o `httpx.MockTransport` do `google_falso`). O dublê de tempo real
mora aqui, no molde do `LoteDaGA4`: um respondedor que a fatia acrescenta ao
`google_falso.respondedores`, sem editar o `GoogleFalso`.

Cobre os critérios de aceite da #816 que valem no backend:

- o endpoint devolve o número de agora, e ninguém no Site é zero de verdade;
- cada consulta vai à fonte, sem cache (o número muda entre duas consultas, e o
  Ao vivo não é tela do registro que se possa forçar);
- o gate de Super admin pela rota real (403 e 401);
- a degradação honesta: fonte fora é 502, sem credencial é 503, nunca um zero
  inventado.
"""

from __future__ import annotations

import os
import sys

import httpx
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from central_de_comando_apoio import (  # noqa: E402
    FACILITADOR,
    SECRETARIA,
    SUPER_ADMIN,
    cliente_da_central,
    pessoa,
)
from central_de_comando_apoio import PREFIXO_DA_CENTRAL as PREFIXO  # noqa: E402
from conftest import TentativaDeRedeNoTeste  # noqa: E402

from app.config import settings  # noqa: E402
from app.services.central_de_comando import provedor_google  # noqa: E402

# O limitador de taxa e o participante do gate zerados antes e depois de cada
# teste (fixture de `central_de_comando_apoio.py`).
pytestmark = pytest.mark.usefixtures("gate_e_limitador_zerados")


class RespostaAoVivo:
    """O `runRealtimeReport` da GA4 de mentira, respondedor do `GoogleFalso`.

    Responde só ao pedido do Ao vivo (o `activeUsers` em tempo real, sem
    dimensão) com o número que o teste puser em `pessoas`, ou sem `rows` quando
    `pessoas` é `None`, que é como a GA4 diz que ninguém está no Site agora. O
    `kind` do relatório é posto pelo `GoogleFalso` (`analyticsData#runRealtime
    Report`). `pedidos` registra cada consulta, para provar que cada leitura
    vai mesmo à fonte.
    """

    def __init__(self, pessoas: int | None = 42):
        self.pessoas = pessoas
        self.pedidos: list[dict] = []

    def __call__(self, metodo: str, corpo: dict) -> dict | None:
        if metodo != "runRealtimeReport":
            return None
        if corpo.get("metrics") != [{"name": "activeUsers"}] or corpo.get("dimensions"):
            return None
        self.pedidos.append(corpo)
        if self.pessoas is None:
            return {"rowCount": 0}
        return {
            "metricHeaders": [{"name": "activeUsers", "type": "TYPE_INTEGER"}],
            "rows": [{"metricValues": [{"value": str(self.pessoas)}]}],
            "rowCount": 1,
        }


@pytest.fixture
def ao_vivo_na_ga4(google_falso) -> RespostaAoVivo:
    """O `runRealtimeReport` no Google de mentira. Pede o `google_falso`, então
    o cache da Central também nasce vazio."""
    resposta = RespostaAoVivo()
    google_falso.respondedores.append(resposta)
    return resposta


def _ao_vivo(logado: dict | None = SUPER_ADMIN) -> httpx.Response:
    return cliente_da_central(logado).get(f"{PREFIXO}/ao-vivo")


# ─── 1. O número de agora ────────────────────────────────────────────────────


@pytest.mark.usefixtures("central_configurada")
class TestPessoasNoSiteAgora:
    def test_super_admin_recebe_o_numero_de_agora(self, ao_vivo_na_ga4):
        ao_vivo_na_ga4.pessoas = 42

        resposta = _ao_vivo()

        assert resposta.status_code == 200, resposta.text
        assert resposta.json() == {"pessoas": 42}

    def test_ninguem_no_site_e_zero_de_verdade(self, ao_vivo_na_ga4):
        """A GA4 omite `rows` quando ninguém está online agora: é resposta, e
        zero é o número honesto (diferente do 502, em que a fonte não
        respondeu)."""
        ao_vivo_na_ga4.pessoas = None

        resposta = _ao_vivo()

        assert resposta.status_code == 200
        assert resposta.json() == {"pessoas": 0}


# ─── 2. Nunca do cache: cada consulta vai à fonte ───────────────────────────


@pytest.mark.usefixtures("central_configurada")
class TestNuncaDoCache:
    def test_cada_consulta_traz_o_numero_do_momento(self, ao_vivo_na_ga4):
        """O Ao vivo é tempo real: duas consultas seguidas trazem o número de
        cada momento, e a segunda não repete a primeira de um cache."""
        ao_vivo_na_ga4.pessoas = 10
        assert _ao_vivo().json() == {"pessoas": 10}

        ao_vivo_na_ga4.pessoas = 7
        assert _ao_vivo().json() == {"pessoas": 7}

        assert len(ao_vivo_na_ga4.pedidos) == 2, "cada consulta tem de ir à fonte, sem cache"

    def test_ao_vivo_nao_e_tela_que_se_possa_forcar(self, ao_vivo_na_ga4):
        """O Ao vivo não está no registro de telas (`telas.py`): não tem
        Atualizar agora, porque nunca é guardado. Pedir para forçá-lo é 422."""
        resposta = cliente_da_central(SUPER_ADMIN).post(f"{PREFIXO}/atualizar-agora?tela=ao-vivo&periodo=28d")

        assert resposta.status_code == 422


# ─── 3. O gate: só Super admin, pela rota real ──────────────────────────────


@pytest.mark.usefixtures("central_configurada")
class TestSoSuperAdminNoAoVivo:
    def test_super_admin_passa(self, ao_vivo_na_ga4):
        assert _ao_vivo(SUPER_ADMIN).status_code == 200

    @pytest.mark.parametrize("persona", [SECRETARIA, FACILITADOR], ids=["secretaria", "facilitador"])
    def test_quem_nao_e_super_admin_leva_403(self, persona, ao_vivo_na_ga4):
        assert _ao_vivo(persona).status_code == 403

    def test_anonimo_leva_401(self, ao_vivo_na_ga4):
        assert _ao_vivo(None).status_code == 401

    def test_super_admin_desligado_leva_403(self, ao_vivo_na_ga4):
        """Sessão viva de quem foi desligado não abre o número (issue #309)."""
        desligado = pessoa("super", "super_admin", ativo=False)
        cliente = cliente_da_central(desligado, participantes=[desligado])

        assert cliente.get(f"{PREFIXO}/ao-vivo").status_code == 403

    def test_quem_nao_passa_no_gate_nao_toca_a_fonte(self, ao_vivo_na_ga4):
        """O gate responde antes de a fonte de tempo real ser tocada."""
        _ao_vivo(SECRETARIA)
        _ao_vivo(None)

        assert ao_vivo_na_ga4.pedidos == []


# ─── 4. Degradação honesta: 502 e 503, nunca zero ──────────────────────────


@pytest.mark.usefixtures("central_configurada")
class TestAoVivoQuandoAFonteFalha:
    @pytest.mark.parametrize(
        ("falha", "trecho"),
        [
            (httpx.ReadTimeout("lento demais"), "tempo esperado"),
            (httpx.ConnectError("rede fora"), "Não foi possível falar"),
        ],
        ids=["timeout", "rede-fora"],
    )
    def test_fonte_que_nao_responde_e_502_sem_numero(self, google_falso, falha, trecho):
        google_falso.forcar = falha

        resposta = _ao_vivo()

        assert resposta.status_code == 502
        assert trecho in resposta.json()["detail"]
        assert "pessoas" not in resposta.json()

    def test_resposta_ilegivel_e_502(self, google_falso):
        google_falso.forcar = httpx.Response(200, content=b"<html>proxy</html>")

        assert _ao_vivo().status_code == 502

    def test_kind_de_relatorio_de_tendencia_nunca_vira_zero(self, google_falso):
        """Um `runReport` (o `kind` das telas de tendência) no lugar do tempo
        real não é "ninguém no Site": é resposta fora do formato, 502, nunca um
        zero que ninguém mediu."""
        google_falso.forcar = httpx.Response(200, json={"kind": "analyticsData#runReport", "rowCount": 0})

        resposta = _ao_vivo()

        assert resposta.status_code == 502
        assert "pessoas" not in resposta.json()

    @pytest.mark.parametrize(
        "rows",
        [{}, 0, "", 5, "linhas", {"linha": 1}],
        ids=["objeto-vazio", "zero", "texto-vazio", "numero", "texto", "objeto"],
    )
    def test_rows_que_nao_e_lista_e_502_nunca_zero(self, google_falso, rows):
        """O Ao vivo lê o `rows` pelo mesmo `_primeira_metrica` da Visão Geral
        (#834). Um `rows` que não é lista no `runRealtimeReport` é resposta
        fora do formato: 502 com a frase, e não "0 pessoas no Site". Inclusive
        o que é "falso" sem ser lista (`{}`, `0`, `''`), que lido como lista
        vazia viraria um zero que ninguém mediu."""
        google_falso.respondedores.insert(0, _ao_vivo_com_rows(rows))

        resposta = _ao_vivo()

        assert resposta.status_code == 502
        assert resposta.json()["detail"] == "O Google Analytics devolveu um relatório fora do formato esperado."
        assert "pessoas" not in resposta.json()


def _ao_vivo_com_rows(rows: object):
    """Uma GA4 que devolve o `runRealtimeReport` do Ao vivo com o `rows` como
    veio aqui."""

    def responder(metodo: str, corpo: dict) -> dict | None:
        if metodo != "runRealtimeReport":
            return None
        return {"rows": rows}

    return responder


class TestAoVivoSemCredencial:
    """Sem propriedade e sem chave, é 503 de configuração, nunca zero e sem
    tocar a rede (mesmo princípio da Visão Geral, ADR 0058, decisão 2)."""

    def test_falta_configurar_e_503_sem_numero_nem_rede(self, monkeypatch, google_falso):
        monkeypatch.setattr(settings, "ga4_property_id", "")
        monkeypatch.setattr(settings, "google_application_credentials_json", "")

        resposta = _ao_vivo()

        assert resposta.status_code == 503
        assert "pessoas" not in resposta.json()
        assert resposta.json()["detail"] == provedor_google.FRASE_NAO_CONFIGURADO
        assert google_falso.pedidos == []


# ─── 5. Nenhum teste fala com o Google ──────────────────────────────────────


@pytest.mark.usefixtures("central_configurada")
class TestTravaDeRedeNoAoVivo:
    def test_sem_o_duble_o_ao_vivo_bate_na_trava_da_suite(self):
        """Sem a fixture do dublê, a leitura de tempo real sairia de verdade
        para a GA4: a trava de `tests/conftest.py` a pega, e é isso que prova
        que o Ao vivo lê MESMO a fonte, e não um número guardado."""
        with pytest.raises(TentativaDeRedeNoTeste) as erro:
            provedor_google.pessoas_no_site_agora()

        assert "analyticsdata.googleapis.com" in str(erro.value)
