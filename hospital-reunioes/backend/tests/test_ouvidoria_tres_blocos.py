"""Os três blocos que chegam à área (issue #481, PRD #469, ADR 0041).

RN-78: o email de acionamento e a tela do responsável carregam RESUMO, RELATO
INTEGRAL e NOTA DA OUVIDORIA, nesta ordem e separados, para a área responder ao
paciente e não à interpretação da Ouvidoria (RN-60).

RN-79: caso com sigilo reforçado é a exceção, nas duas superfícies: sem
identificação de quem manifestou, e o extrato da Ouvidoria entra no lugar do
relato integral.

A montagem é uma função única (`ouvidoria_blocos.montar_blocos`), exercitada
aqui direto e pela interface pública do email (`montar_nova_demanda`).
"""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import pytest

from app.services.ouvidoria_blocos import (
    AVISO_ANONIMO,
    AVISO_SIGILO,
    CHAVE_NOTA,
    CHAVE_RELATO,
    CHAVE_RESUMO,
    ORIENTACAO_DE_AUTORIA,
    aviso_do_caso,
    montar_blocos,
)
from app.services.ouvidoria_notificacoes import montar_nova_demanda

FUSO = ZoneInfo("America/Sao_Paulo")
AGORA = dt.datetime(2026, 8, 25, 14, 0, tzinfo=FUSO)
SEM_FERIADOS: frozenset[dt.date] = frozenset()

RESUMO = "Paciente relata espera de duas horas na recepcao."
RELATO = "Cheguei as 8h com minha mae e so fomos atendidos as 10h30, sem ninguem explicar o motivo."
EXTRATO = "Apurar a fila da recepcao no turno da manha e responder o que foi feito."


def _manifestacao(**mudancas) -> dict:
    caso = {
        "id": "uuid-7",
        "protocolo": "2026-0007",
        "setor": "Recepcao",
        "categoria": "Atendimento",
        "resumo": RESUMO,
        "relato_integral": RELATO,
        "extrato_para_o_setor": EXTRATO,
        "gravidade": "medio",
        "prazo_area_em": dt.datetime(2026, 8, 31, 17, 0, tzinfo=FUSO).isoformat(),
        "sigilo_reforcado": False,
        "anonimo": False,
        "manifestante_nome": "Joana da Silva",
    }
    caso.update(mudancas)
    return caso


class TestMontagemUnicaDosBlocos:
    """Critério 4: a montagem é uma função única, testada direta."""

    def test_caso_comum_rende_resumo_relato_e_nota_nesta_ordem(self):
        blocos = montar_blocos(_manifestacao())

        assert [b["chave"] for b in blocos] == [CHAVE_RESUMO, CHAVE_RELATO, CHAVE_NOTA]
        assert [b["texto"] for b in blocos] == [RESUMO, RELATO, EXTRATO]

    def test_cada_bloco_leva_o_proprio_rotulo(self):
        """RN-60: os blocos nunca são fundidos, e cada um se anuncia."""
        rotulos = [b["rotulo"] for b in montar_blocos(_manifestacao())]

        assert rotulos == ["RESUMO", "RELATO INTEGRAL", "NOTA DA OUVIDORIA"]


class TestVarianteSigilosa:
    """Critério 3 e 4 (RN-79): sob sigilo reforçado o extrato entra no lugar do
    relato integral, e a palavra crua do manifestante não viaja."""

    def test_caso_sigiloso_nao_leva_o_relato_original(self):
        blocos = montar_blocos(_manifestacao(sigilo_reforcado=True))

        assert RELATO not in [b["texto"] for b in blocos]
        assert CHAVE_RELATO not in [b["chave"] for b in blocos]

    def test_no_lugar_do_relato_a_area_le_o_extrato_da_ouvidoria(self):
        blocos = montar_blocos(_manifestacao(sigilo_reforcado=True))

        assert [b["chave"] for b in blocos] == [CHAVE_NOTA]
        assert blocos[-1]["texto"] == EXTRATO

    def test_caso_sigiloso_tambem_deixa_o_resumo_para_tras(self):
        """O resumo não é texto da Ouvidoria: no canal aberto ele é o começo do
        que o cidadão digitou, e leva nome e leito junto. Sob a RN-79 ele sai
        pelo mesmo motivo do relato."""
        resumo_com_nome = "Sou a Maria Silva, do leito 302, e esperei tres horas."
        blocos = montar_blocos(_manifestacao(sigilo_reforcado=True, resumo=resumo_com_nome))

        assert CHAVE_RESUMO not in [b["chave"] for b in blocos]
        assert "Maria Silva" not in " ".join(b["texto"] for b in blocos)

    def test_caso_anonimo_recebe_a_mesma_protecao(self):
        """Quem não quis se identificar costuma se identificar dentro do próprio
        texto: mandar relato e resumo ao setor desfaria o anonimato."""
        blocos = montar_blocos(_manifestacao(anonimo=True))

        assert [b["chave"] for b in blocos] == [CHAVE_NOTA]


class TestEmailDeAcionamento:
    """Critério 1: o email de acionamento renderiza os três blocos separados,
    na ordem resumo, relato integral, nota da ouvidoria."""

    def test_html_traz_os_tres_blocos_rotulados_na_ordem(self):
        _, html, _ = montar_nova_demanda(_manifestacao(), "Carlos", AGORA, SEM_FERIADOS)

        assert html.index("RESUMO") < html.index("RELATO INTEGRAL") < html.index("NOTA DA OUVIDORIA")
        assert html.index(RESUMO) < html.index(RELATO) < html.index(EXTRATO)

    def test_texto_alternativo_traz_os_tres_blocos_na_mesma_ordem(self):
        """Quem lê o email em cliente sem HTML lê a mesma coisa, na mesma ordem."""
        _, _, texto = montar_nova_demanda(_manifestacao(), "Carlos", AGORA, SEM_FERIADOS)

        assert texto.index(RESUMO) < texto.index(RELATO) < texto.index(EXTRATO)
        assert texto.index("RESUMO") < texto.index("RELATO INTEGRAL") < texto.index("NOTA DA OUVIDORIA")

    def test_os_blocos_nao_saem_fundidos_num_paragrafo_so(self):
        """RN-60: o que o paciente disse e o que a Ouvidoria interpretou nunca
        se confundem, então cada bloco tem a própria caixa no HTML."""
        _, html, _ = montar_nova_demanda(_manifestacao(), "Carlos", AGORA, SEM_FERIADOS)

        entre_relato_e_nota = html[html.index(RELATO) : html.index(EXTRATO)]
        assert "</table>" in entre_relato_e_nota


class TestEmailSobSigilo:
    """Critério 3 (RN-79): o email do caso sigiloso não leva relato nem
    identificação, e o extrato ocupa o lugar do relato."""

    def test_email_sigiloso_sai_sem_relato_e_sem_identificacao(self):
        _, html, texto = montar_nova_demanda(_manifestacao(sigilo_reforcado=True), "Carlos", AGORA, SEM_FERIADOS)

        for pedaco in (html, texto):
            assert RELATO not in pedaco
            assert "Joana da Silva" not in pedaco
            assert "RELATO INTEGRAL" not in pedaco

    def test_email_sigiloso_mantem_a_nota_da_ouvidoria_e_avisa_o_sigilo(self):
        """A área continua com o que precisa para agir: o extrato é o que a
        Ouvidoria escreveu e autorizou a circular, e o aviso explica por que o
        resto do caso não veio."""
        _, html, texto = montar_nova_demanda(_manifestacao(sigilo_reforcado=True), "Carlos", AGORA, SEM_FERIADOS)

        for pedaco in (html, texto):
            assert EXTRATO in pedaco
            assert "sigilo reforçado" in pedaco.lower()
            assert RESUMO not in pedaco


class TestAvisoDoCasoProtegido:
    """O aviso sai do MESMO gate que corta os blocos: caso protegido que chega
    com um bloco só e nenhuma explicação é o mal-entendido que o aviso existe
    para evitar."""

    def test_caso_comum_nao_leva_aviso(self):
        assert aviso_do_caso(_manifestacao()) is None

    def test_caso_sigiloso_leva_o_aviso_de_sigilo(self):
        assert aviso_do_caso(_manifestacao(sigilo_reforcado=True)) == AVISO_SIGILO

    def test_caso_anonimo_leva_o_aviso_do_anonimato(self):
        """Sem aviso próprio, o acionamento anônimo chegaria mudo: com um bloco
        só e nenhuma razão para o resto ter ficado para trás."""
        assert aviso_do_caso(_manifestacao(anonimo=True)) == AVISO_ANONIMO

    @pytest.mark.parametrize("protegido", [{"sigilo_reforcado": True}, {"anonimo": True}])
    def test_as_duas_versoes_do_email_levam_o_aviso_inteiro(self, protegido):
        """Issue #511, item 2: a frase que diz o que FAZER com a autoria vivia
        solta no template HTML, e a versão texto do mesmo email saía sem ela.
        Quem lê em cliente sem HTML recebia o aviso pela metade, e justamente a
        metade que orienta."""
        caso = _manifestacao(**protegido)
        aviso = aviso_do_caso(caso)
        _, html, texto = montar_nova_demanda(caso, "Carlos", AGORA, SEM_FERIADOS)

        assert aviso is not None
        assert ORIENTACAO_DE_AUTORIA in aviso
        for pedaco in (html, texto):
            assert aviso in pedaco

    def test_email_do_caso_anonimo_explica_por_que_veio_so_a_nota(self):
        _, html, texto = montar_nova_demanda(_manifestacao(anonimo=True), "Carlos", AGORA, SEM_FERIADOS)

        for pedaco in (html, texto):
            assert AVISO_ANONIMO in pedaco
            assert RELATO not in pedaco
            assert RESUMO not in pedaco
