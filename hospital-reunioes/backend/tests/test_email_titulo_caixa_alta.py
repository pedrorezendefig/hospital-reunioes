"""Caixa alta no título dos e-mails (issue #1457, PRD #1428, ADR 0080).

O título que aparece embaixo da logo, no template base, sai em maiúscula pelo
filtro `upper` do Jinja: ele converte o acento certo e não depende de o cliente
de e-mail respeitar `text-transform`. O assunto e o corpo não mudam.
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from jinja2 import ChainableUndefined

from app.services import pops_email_service
from app.services.email_service import TEMPLATES_DIR, jinja_env
from app.services.ouvidoria_notificacoes import montar_nova_demanda
from app.services.reuniao_email_service import _montar_contexto, _renderizar

FUSO = ZoneInfo("America/Sao_Paulo")
AGORA = dt.datetime(2026, 8, 25, 14, 0, tzinfo=FUSO)

# O parágrafo do título, logo abaixo da logo, no email_base.html.
_TITULO = re.compile(r'<p style="color:#64748b;margin:10px 0 0;[^"]*">(.*?)</p>', re.S)


def _titulo(html: str) -> str:
    achado = _TITULO.search(html)
    assert achado, "o e-mail perdeu o título embaixo da logo"
    return achado.group(1).strip()


def _templates_que_usam_o_base() -> list[str]:
    return sorted(
        caminho.name
        for caminho in Path(TEMPLATES_DIR).glob("email_*.html")
        if caminho.name != "email_base.html" and "{% extends" in caminho.read_text(encoding="utf-8")
    )


@pytest.mark.parametrize("template", _templates_que_usam_o_base())
def test_titulo_de_todo_email_do_template_base_sai_em_caixa_alta(template):
    # ChainableUndefined: o template rende sem contexto; o título não depende dele.
    ambiente = jinja_env.overlay(undefined=ChainableUndefined)
    titulo = _titulo(ambiente.get_template(template).render())

    assert titulo
    assert titulo == titulo.upper()


def test_titulo_do_convite_de_reuniao_sai_em_caixa_alta_com_acento():
    reuniao = {"id_reuniao": "R-1", "titulo": "Reunião de Qualidade", "data": "2026-08-27"}
    html = _renderizar("email_convite_reuniao.html", _montar_contexto(reuniao, "Ana Souza", "Bruno Lima"))

    assert _titulo(html) == "GESTÃO DE ATAS E DECISÕES COM IA"


def test_email_da_ouvidoria_tem_titulo_em_caixa_alta_e_assunto_e_corpo_como_antes():
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
    assunto, html, _ = montar_nova_demanda(caso, "Maria", AGORA, frozenset())

    assert _titulo(html) == "OUVIDORIA"
    assert assunto == "Ouvidoria 2026-0007: nova demanda para Recepcao"
    assert "Paciente relata demora no atendimento da recepção." in html


class _Consulta:
    def __init__(self, linhas):
        self._linhas = linhas

    def __getattr__(self, _nome):
        return lambda *_a, **_k: self

    def execute(self):
        return type("R", (), {"data": self._linhas})()


class _Supabase:
    def table(self, _nome):
        return _Consulta([{"id": "p-1", "nome_completo": "Carla Dias", "email": "carla@hsm.test"}])


def test_email_do_pop_criado_tem_titulo_em_caixa_alta_e_assunto_e_corpo_como_antes(monkeypatch):
    enviados = []
    monkeypatch.setattr(
        pops_email_service,
        "_enviar_email",
        lambda destinatario, assunto, html, texto: enviados.append((assunto, html)) or True,
    )
    pop = {
        "codigo": "POP-001",
        "nome": "Higienização das mãos",
        "elaborador_id": "p-1",
        "prazo_elaboracao_dias": 5,
    }

    assert pops_email_service.send_pop_criado_notification(_Supabase(), pop, {"nome": "Enfermagem"}, "Diretoria")

    assunto, html = enviados[0]
    assert _titulo(html) == "GESTÃO DE POPS"
    assert assunto == "Novo POP para elaborar: POP-001 (Higienização das mãos)"
    assert "Carla Dias" in html
    assert "Higienização das mãos" in html
