"""Template de email estratificado por gravidade e sigilo (issue #332, PRD #318).

RN-34: faixa de cor e rótulo por gravidade. RN-35: essencial acima da dobra.
RN-36: sigiloso sem nome do manifestante e sem dado clínico. Exercita o
catálogo pela interface pública (montar_*): o que o setor lê é o que se testa.
"""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import pytest

from app.services.ouvidoria_notificacoes import montar_alerta_sem_titular, montar_nova_demanda

FUSO = ZoneInfo("America/Sao_Paulo")
# Terça-feira útil, meio do expediente.
AGORA = dt.datetime(2026, 8, 25, 14, 0, tzinfo=FUSO)
SEM_FERIADOS: frozenset[dt.date] = frozenset()


def _manifestacao(**mudancas) -> dict:
    caso = {
        "id": "uuid-7",
        "protocolo": "2026-0007",
        "setor": "Recepcao",
        "categoria": "Atendimento",
        "extrato_para_o_setor": "Paciente relata demora no atendimento da recepção.",
        "gravidade": "medio",
        "prazo_area_em": dt.datetime(2026, 8, 31, 17, 0, tzinfo=FUSO).isoformat(),
        "sigilo_reforcado": False,
        "anonimo": False,
        "manifestante_nome": "Joana da Silva",
    }
    caso.update(mudancas)
    return caso


class TestFaixaDeGravidade:
    """Primeiro critério: cada gravidade rende faixa e rótulo na cor certa."""

    def test_caso_critico_rende_faixa_vermelha_com_rotulo_critico(self):
        _, html, _ = montar_nova_demanda(_manifestacao(gravidade="critico"), "Maria", AGORA, SEM_FERIADOS)

        assert "#B3261E" in html
        assert "CRÍTICO" in html

    @pytest.mark.parametrize(
        ("gravidade", "cor", "rotulo"),
        [
            ("critico", "#B3261E", "CRÍTICO"),
            ("alto", "#C77700", "ALTO"),
            ("medio", "#1F3864", "MÉDIO"),
            ("baixo", "#5F5E5A", "BAIXO"),
        ],
    )
    def test_cada_gravidade_rende_faixa_e_rotulo_na_cor_da_spec(self, gravidade, cor, rotulo):
        """RN-34: os hex vêm da spec da Diretoria (tabela 8.2)."""
        _, html, _ = montar_nova_demanda(_manifestacao(gravidade=gravidade), "Maria", AGORA, SEM_FERIADOS)

        assert cor in html
        assert rotulo in html

    def test_hex_e_default_trocavel_num_lugar_so(self, monkeypatch):
        """Quando o DP confirmar a paleta da casa, trocar FAIXAS_GRAVIDADE
        troca o email inteiro, sem mexer em template."""
        from app.services import ouvidoria_notificacoes as catalogo

        monkeypatch.setitem(catalogo.FAIXAS_GRAVIDADE, "critico", {"cor": "#AA0000", "rotulo": "CRÍTICO"})

        _, html, _ = montar_nova_demanda(_manifestacao(gravidade="critico"), "Maria", AGORA, SEM_FERIADOS)

        assert "#AA0000" in html
        assert "#B3261E" not in html


class TestAcimaDaDobra:
    """Segundo critério (RN-35): o essencial vem antes de qualquer conversa."""

    def test_protocolo_setor_prazo_e_contagem_vem_antes_da_saudacao(self):
        _, html, _ = montar_nova_demanda(_manifestacao(), "Maria", AGORA, SEM_FERIADOS)

        dobra = html.index("Olá")
        for essencial in ("2026-0007", "Recepcao", "31/08/2026 às 17h00", "vence em 4 dias úteis"):
            assert essencial in html, f"Faltou no email: {essencial}"
            assert html.index(essencial) < dobra, f"Abaixo da dobra: {essencial}"


class TestBotaoUnico:
    """Terceiro critério (RN-35): um único botão de ação por email."""

    def test_acionamento_tem_um_unico_link_de_acao(self):
        _, html, _ = montar_nova_demanda(_manifestacao(), "Maria", AGORA, SEM_FERIADOS)

        assert html.count("<a ") == 1

    def test_alerta_sem_titular_tem_um_unico_link_de_acao(self):
        _, html, _ = montar_alerta_sem_titular(_manifestacao(), "Diretora", "Carlos Gestor")

        assert html.count("<a ") == 1


class TestCatalogoNoTemplateNovo:
    """Quinto critério: os emails existentes do catálogo usam o template."""

    def test_alerta_sem_titular_tambem_carrega_a_faixa_da_gravidade(self):
        _, html, _ = montar_alerta_sem_titular(_manifestacao(gravidade="alto"), "Diretora", "Carlos Gestor")

        assert "#C77700" in html
        assert "ALTO" in html
        assert "2026-0007" in html


class TestSigilo:
    """Quarto critério (RN-36): caso sigiloso viaja sem nome do manifestante.
    O dado clínico nunca entra: o email só carrega o extrato escrito pelo
    ouvidor, nunca o relato original (whitelist de campos do catálogo)."""

    def test_caso_sigiloso_sai_sem_o_nome_do_manifestante_no_html_e_no_texto(self):
        _, html, texto = montar_nova_demanda(_manifestacao(sigilo_reforcado=True), "Maria", AGORA, SEM_FERIADOS)

        assert "Joana da Silva" not in html
        assert "Joana da Silva" not in texto
        assert "sigilo reforçado" in html.lower()


class TestSemTravessao:
    """Sexto critério (regra da casa, ADR 0013): nenhum template nem email
    rendido carrega travessão ou meia-risca."""

    def test_emails_rendidos_saem_sem_travessao_nem_meia_risca(self):
        emails = [
            montar_nova_demanda(_manifestacao(sigilo_reforcado=True), "Maria", AGORA, SEM_FERIADOS),
            montar_nova_demanda(_manifestacao(gravidade="critico"), "Maria", AGORA, SEM_FERIADOS),
            montar_alerta_sem_titular(_manifestacao(), "Diretora", "Carlos Gestor"),
        ]

        for assunto, html, texto in emails:
            for pedaco in (assunto, html, texto):
                assert "—" not in pedaco
                assert "–" not in pedaco
