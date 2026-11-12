"""Botão dos e-mails da Ouvidoria visível em todo cliente de e-mail (issue #1583).

O botão tinha só `background:linear-gradient(...)` com texto branco. Gmail e
Outlook descartam o gradiente, o fundo some e o texto branco fica invisível no
fundo branco: o responsável da área recebia o caso sem o botão para responder.
O botão agora declara a cor sólida duas vezes, `bgcolor` na célula que o
envolve (Outlook) e `background-color` no próprio link (Gmail); o gradiente
fica só como enfeite por cima, para quem o desenha.

O `email_ouvidoria_redirecionamento_area.html` fica de fora: não tem link de
propósito (issue #707).
"""

from __future__ import annotations

import datetime as dt
import re
from zoneinfo import ZoneInfo

import pytest
from jinja2 import ChainableUndefined

from app.services.email_service import jinja_env
from app.services.ouvidoria_notificacoes import montar_nova_demanda

LINK = "https://app.exemplo/ouvidoria-setor?token=abc123"

TEMPLATES_COM_BOTAO = [
    "email_ouvidoria_nova_demanda.html",
    "email_ouvidoria_degrau.html",
    "email_ouvidoria_devolvido.html",
    "email_ouvidoria_prazo_rompido.html",
    "email_ouvidoria_prorrogacao_solicitada.html",
    "email_ouvidoria_prorrogacao_decidida.html",
    "email_ouvidoria_sem_titular.html",
]

_COR = r"#[0-9A-Fa-f]{6}"


def _cor_solida_do_botao(html: str, link: str) -> tuple[str, str]:
    """Devolve (cor do `bgcolor` da célula, cor do `background-color` do link)."""
    botao = re.search(r'<a href="' + re.escape(link) + r'"\s+style="([^"]*)"', html)
    assert botao, "o e-mail perdeu o botão com o link do caso"

    estilo = botao.group(1)
    cor_do_link = re.search(r"(?:^|;)\s*background-color:\s*(" + _COR + ")", estilo)
    assert cor_do_link, f"o botão não declara cor de fundo sólida, só: {estilo}"

    inicio_da_celula = html.rfind("<td", 0, botao.start())
    celula = html[inicio_da_celula : html.index(">", inicio_da_celula) + 1]
    cor_da_celula = re.search(r'bgcolor="(' + _COR + ')"', celula)
    assert cor_da_celula, f"a célula do botão não tem bgcolor: {celula}"

    return cor_da_celula.group(1), cor_do_link.group(1)


@pytest.mark.parametrize("template", TEMPLATES_COM_BOTAO)
def test_botao_do_email_da_ouvidoria_tem_o_link_do_caso_e_cor_solida(template):
    ambiente = jinja_env.overlay(undefined=ChainableUndefined)
    html = ambiente.get_template(template).render(link=LINK)

    cor_da_celula, cor_do_link = _cor_solida_do_botao(html, LINK)

    assert cor_da_celula.lower() == cor_do_link.lower() == "#2b2e7e"


def test_responsavel_da_area_recebe_a_nova_demanda_com_botao_que_abre_o_caso():
    fuso = ZoneInfo("America/Sao_Paulo")
    caso = {
        "id": "uuid-1583",
        "protocolo": "2026-1583",
        "setor": "CTI",
        "categoria": "Atendimento",
        "extrato_para_o_setor": "Paciente relata demora no atendimento.",
        "gravidade": "medio",
        "prazo_area_em": dt.datetime(2026, 11, 20, 17, 0, tzinfo=fuso).isoformat(),
        "sigilo_reforcado": False,
        "anonimo": False,
        "manifestante_nome": "Joana da Silva",
    }
    agora = dt.datetime(2026, 11, 11, 9, 0, tzinfo=fuso)

    _, html, texto = montar_nova_demanda(caso, "Titular do CTI", agora, frozenset(), link=LINK)

    _cor_solida_do_botao(html, LINK)
    assert LINK in texto
