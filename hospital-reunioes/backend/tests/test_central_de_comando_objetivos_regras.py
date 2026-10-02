"""As regras de sugestão dos Objetivos, testadas direto (issue #820, PRD #809).

Porte dos testes de `src/lib/objetivos/regras/*.test.ts` do repositório antigo:
cada regra dispara com o dado certo, cala com o dado errado, e sempre traz o
porquê (o dado que a disparou). São funções puras: sem rota, sem rede, sem
fixture.
"""

from __future__ import annotations

import pytest

from app.services.central_de_comando import provedor_google, provedor_instagram
from app.services.central_de_comando.objetivos.regras import (
    contatos_instrumentar,
    dispositivo_celular_domina,
    queda_de_alcance,
    queda_de_interacoes,
    reels_rendem_mais,
)
from app.services.central_de_comando.objetivos.regras._ajudantes import (
    nao_caiu,
    pct,
    queda_alem,
)
from app.services.central_de_comando.objetivos.tipos import (
    ContatoNaLente,
    Contexto,
    Extras,
    Numero,
)


def _numero(valor: int, anterior: int | None = None) -> Numero:
    return Numero(chave="x", rotulo="x", valor=valor, anterior=anterior)


def _publicacao(tipo: provedor_instagram.TipoDeMidia) -> provedor_instagram.Publicacao:
    return provedor_instagram.Publicacao(id="1", legenda=None, tipo=tipo, miniatura="", link="", data="", interacoes=0)


def _dispositivo(qual: provedor_google.Dispositivo, visitas: int) -> provedor_google.VisitasNoDispositivo:
    return provedor_google.VisitasNoDispositivo(dispositivo=qual, visitas=visitas)


class TestPct:
    def test_arredonda_a_fracao_para_percentual_inteiro_sem_sinal(self):
        assert pct(-0.2) == "20%"
        assert pct(0.123) == "12%"
        assert pct(0) == "0%"


class TestQuedaAlem:
    def test_devolve_a_fracao_negativa_quando_caiu_alem_do_limiar(self):
        assert queda_alem(80, 100, 0.05) == pytest.approx(-0.2)

    def test_none_quando_a_queda_e_menor_que_o_limiar(self):
        assert queda_alem(98, 100, 0.05) is None

    def test_none_quando_subiu_ou_ficou_estavel(self):
        assert queda_alem(120, 100, 0.05) is None
        assert queda_alem(100, 100, 0.05) is None

    def test_none_sem_base_de_comparacao(self):
        assert queda_alem(80, None, 0.05) is None
        assert queda_alem(80, 0, 0.05) is None


class TestNaoCaiu:
    def test_true_quando_subiu_estavel_ou_sem_base(self):
        assert nao_caiu(105, 100, 0.05) is True
        assert nao_caiu(100, None, 0.05) is True

    def test_false_quando_caiu_alem_do_limiar(self):
        assert nao_caiu(80, 100, 0.05) is False


class TestQuedaDeAlcance:
    @staticmethod
    def _ctx(valor: int | None = None, anterior: int | None = None) -> Contexto:
        numeros = {}
        if valor is not None:
            numeros["reach"] = Numero(chave="reach", rotulo="Alcance", valor=valor, anterior=anterior)
        return Contexto(numeros=numeros)

    def test_dispara_quando_o_alcance_caiu_alem_de_5_por_cento_com_o_porque_ancorado(self):
        s = queda_de_alcance(self._ctx(valor=30120, anterior=37650))
        assert s is not None
        assert s.id == "queda-de-alcance"
        assert s.tom == "atencao"
        assert "20%" in s.porque
        assert "37.650" in s.porque
        assert "30.120" in s.porque

    def test_nao_dispara_quando_a_queda_e_pequena(self):
        assert queda_de_alcance(self._ctx(valor=98, anterior=100)) is None

    def test_nao_dispara_quando_o_alcance_subiu(self):
        assert queda_de_alcance(self._ctx(valor=120, anterior=100)) is None

    def test_nao_dispara_sem_periodo_anterior_nem_sem_o_numero_de_alcance(self):
        assert queda_de_alcance(self._ctx(valor=100)) is None
        assert queda_de_alcance(self._ctx()) is None


class TestQuedaDeInteracoes:
    @staticmethod
    def _ctx(inter: Numero, reach: Numero | None = None) -> Contexto:
        extras = Extras(reach=reach) if reach is not None else Extras()
        return Contexto(numeros={"interactions": inter}, extras=extras)

    def test_dispara_quando_interacoes_caem_mas_o_alcance_se_mantem(self):
        s = queda_de_interacoes(self._ctx(_numero(80, 100), _numero(105, 100)))
        assert s is not None
        assert s.id == "queda-de-interacoes"
        assert "20%" in s.porque

    def test_nao_dispara_se_o_alcance_tambem_caiu(self):
        assert queda_de_interacoes(self._ctx(_numero(80, 100), _numero(70, 100))) is None

    def test_nao_dispara_sem_o_alcance_no_contexto(self):
        assert queda_de_interacoes(self._ctx(_numero(80, 100))) is None

    def test_nao_dispara_quando_a_queda_de_interacoes_e_pequena(self):
        assert queda_de_interacoes(self._ctx(_numero(98, 100), _numero(105, 100))) is None


class TestReelsRendemMais:
    @staticmethod
    def _ctx(posts: list[provedor_instagram.Publicacao]) -> Contexto:
        return Contexto(numeros={}, extras=Extras(publicacoes=tuple(posts)))

    def test_dispara_quando_os_reels_sao_maioria_do_top(self):
        s = reels_rendem_mais(
            self._ctx([_publicacao("reel"), _publicacao("reel"), _publicacao("reel"), _publicacao("imagem")])
        )
        assert s is not None
        assert s.tom == "positivo"
        assert "3 das 4" in s.porque

    def test_nao_dispara_no_empate(self):
        assert (
            reels_rendem_mais(
                self._ctx([_publicacao("reel"), _publicacao("reel"), _publicacao("imagem"), _publicacao("carrossel")])
            )
            is None
        )

    def test_nao_dispara_com_menos_de_2_publicacoes(self):
        assert reels_rendem_mais(self._ctx([_publicacao("reel")])) is None
        assert reels_rendem_mais(self._ctx([])) is None


class TestDispositivoCelularDomina:
    @staticmethod
    def _ctx(dispositivos: list[provedor_google.VisitasNoDispositivo]) -> Contexto:
        return Contexto(numeros={}, extras=Extras(dispositivos=tuple(dispositivos)))

    def test_dispara_quando_o_celular_passa_de_60_por_cento(self):
        s = dispositivo_celular_domina(self._ctx([_dispositivo("celular", 78), _dispositivo("computador", 22)]))
        assert s is not None
        assert s.tom == "neutro"
        assert "78%" in s.porque

    def test_nao_dispara_quando_esta_equilibrado(self):
        assert (
            dispositivo_celular_domina(self._ctx([_dispositivo("celular", 50), _dispositivo("computador", 50)])) is None
        )

    def test_nao_dispara_sem_dados_de_dispositivo(self):
        assert dispositivo_celular_domina(self._ctx([])) is None


class TestContatosInstrumentar:
    @staticmethod
    def _ctx(canais: list[ContatoNaLente]) -> Contexto:
        return Contexto(numeros={}, extras=Extras(canais=tuple(canais)))

    def test_dispara_quando_ha_canais_nao_medidos_listando_os_no_porque(self):
        s = contatos_instrumentar(
            self._ctx(
                [
                    ContatoNaLente(chave="agendar", rotulo="Cliques para agendar", estado="medido", cliques=145),
                    ContatoNaLente(chave="whatsapp", rotulo="WhatsApp", estado="nao-medido"),
                    ContatoNaLente(chave="telefone", rotulo="Telefone", estado="nao-medido"),
                ]
            )
        )
        assert s is not None
        assert s.tom == "neutro"
        assert "2 de 3" in s.porque
        assert "WhatsApp" in s.porque
        assert "Telefone" in s.porque

    def test_nao_dispara_quando_todos_os_canais_sao_medidos(self):
        assert (
            contatos_instrumentar(
                self._ctx(
                    [
                        ContatoNaLente(chave="agendar", rotulo="Cliques para agendar", estado="medido", cliques=1),
                        ContatoNaLente(chave="whatsapp", rotulo="WhatsApp", estado="medido", cliques=1),
                    ]
                )
            )
            is None
        )

    def test_nao_dispara_sem_canais_no_contexto(self):
        assert contatos_instrumentar(self._ctx([])) is None
