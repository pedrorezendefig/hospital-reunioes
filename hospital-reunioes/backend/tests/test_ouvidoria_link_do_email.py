"""Para onde o botão de cada email da Ouvidoria leva (issue #515).

São dois destinos, e a diferença é quem lê. Quem NÃO tem login (responsável do
setor, gestor da área) recebe o link tokenizado do portal e continua recebendo:
mandar essa gente para uma tela de login seria o contrário do que a história 4
do PRD #468 decidiu. Quem TEM login (Diretoria Executiva, admin da Ouvidoria)
recebia a fila inteira e passa a receber o endereço do caso,
`/ouvidoria/m/<protocolo>` (issue #476).

Os testes leem o `href` que sai do HTML e as URLs que saem da versão texto, e
comparam por igualdade: assertar "contém" não serviria, porque o endereço da
fila é prefixo do endereço do caso e um teste assim ficaria verde com o desvio
de volta.
"""

from __future__ import annotations

import datetime as dt
import re
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import pytest

from app.config import settings
from app.services import ouvidoria_notificacoes as notificacoes
from app.services.ouvidoria_notificacoes import (
    _link_do_caso,
    montar_alerta_cadastro_setor,
    montar_alerta_sem_titular,
    montar_critico_imediato,
    montar_escalonamento_diretoria,
    montar_nova_demanda,
    montar_prazo_rompido,
    montar_prorrogacao_solicitada,
    montar_vespera_vencimento,
)

FUSO = ZoneInfo("America/Sao_Paulo")
AGORA = dt.datetime(2026, 8, 25, 14, 0, tzinfo=FUSO)
SEM_FERIADOS: frozenset[dt.date] = frozenset()

PROTOCOLO = "2026-0007"
LINK_DO_CASO = f"{settings.frontend_url}/ouvidoria/m/{PROTOCOLO}"
LINK_DA_FILA = f"{settings.frontend_url}/ouvidoria"
LINK_DO_PORTAL = f"{settings.frontend_url}/ouvidoria-setor?protocolo={PROTOCOLO}"


def _manifestacao(**mudancas) -> dict:
    caso = {
        "id": "uuid-7",
        "protocolo": PROTOCOLO,
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


def _pedido() -> dict:
    return {
        "dias_uteis_pedidos": 2,
        "prazo_novo": dt.datetime(2026, 9, 2, 17, 0, tzinfo=FUSO).isoformat(),
        "justificativa": "A area depende de laudo externo.",
        "solicitante_nome": "Carlos",
    }


def _hrefs(html: str) -> set[str]:
    """Todo destino clicável do email. O template de cada um destes emails tem
    um botão só, então o conjunto tem que ser exatamente o destino esperado."""
    return set(re.findall(r'href="([^"]+)"', html))


def _urls(texto: str) -> set[str]:
    return set(re.findall(r"https?://\S+", texto))


class TestQuemTemLoginRecebeOCaso:
    """Tipo 2: Diretoria Executiva e admin da Ouvidoria têm painel, e o botão
    abre o caso em vez de largar a pessoa na fila para procurar."""

    def test_alerta_sem_titular_leva_ao_caso_no_html_e_no_texto(self):
        _, html, texto = montar_alerta_sem_titular(_manifestacao(), "Ana", "Bruno", AGORA, SEM_FERIADOS)

        assert _hrefs(html) == {LINK_DO_CASO}
        assert LINK_DO_CASO in _urls(texto)
        assert LINK_DA_FILA not in _urls(texto)

    def test_alerta_sem_titular_mantem_o_link_de_cadastro_de_responsaveis(self):
        """Esse link tem propósito próprio (cadastrar o titular que falta) e
        não some com a troca do botão principal."""
        _, _, texto = montar_alerta_sem_titular(_manifestacao(), "Ana", "Bruno", AGORA, SEM_FERIADOS)

        assert f"{settings.frontend_url}/ouvidoria/responsaveis" in _urls(texto)

    @pytest.mark.parametrize(
        "montar",
        [montar_escalonamento_diretoria, montar_alerta_cadastro_setor, montar_critico_imediato],
    )
    def test_degraus_da_diretoria_levam_ao_caso_no_html_e_no_texto(self, montar):
        _, html, texto = montar(_manifestacao(), "Ana", AGORA, SEM_FERIADOS)

        assert _hrefs(html) == {LINK_DO_CASO}
        assert _urls(texto) == {LINK_DO_CASO}

    def test_prorrogacao_a_decidir_leva_ao_caso_no_html_e_no_texto(self):
        _, html, texto = montar_prorrogacao_solicitada(_manifestacao(), "Ana", _pedido(), AGORA, SEM_FERIADOS)

        assert _hrefs(html) == {LINK_DO_CASO}
        assert _urls(texto) == {LINK_DO_CASO}


class TestQuemNaoTemLoginContinuaNoPortal:
    """Tipo 1: responsável do setor e gestor da área respondem sem login, pelo
    portal tokenizado. Nada aqui muda com a issue #515."""

    def test_nova_demanda_continua_no_portal_do_setor(self):
        _, html, texto = montar_nova_demanda(_manifestacao(), "Carlos", AGORA, SEM_FERIADOS)

        assert _hrefs(html) == {LINK_DO_PORTAL}
        assert _urls(texto) == {LINK_DO_PORTAL}

    def test_vespera_do_vencimento_continua_no_portal_do_setor(self):
        _, html, texto = montar_vespera_vencimento(_manifestacao(), "Carlos", AGORA, SEM_FERIADOS)

        assert _hrefs(html) == {LINK_DO_PORTAL}
        assert _urls(texto) == {LINK_DO_PORTAL}

    def test_cobranca_de_prazo_rompido_honra_o_link_tokenizado_do_despacho(self):
        tokenizado = f"{settings.frontend_url}/ouvidoria-setor/tok-abc"

        _, html, texto = montar_prazo_rompido(_manifestacao(), "Carlos", AGORA, SEM_FERIADOS, link=tokenizado)

        assert _hrefs(html) == {tokenizado}
        assert _urls(texto) == {tokenizado}


class TestOLinkRecebidoVenceOFallback:
    """Só o fallback muda: quem chama passando `link` continua mandando."""

    def test_escalonamento_diretoria_usa_o_link_recebido(self):
        recebido = f"{settings.frontend_url}/ouvidoria/painel"

        _, html, texto = montar_escalonamento_diretoria(_manifestacao(), "Ana", AGORA, SEM_FERIADOS, link=recebido)

        assert _hrefs(html) == {recebido}
        assert _urls(texto) == {recebido}


class TestOEnderecoDoCasoNasceNumLugarSo:
    def test_helper_monta_o_endereco_do_caso_a_partir_do_protocolo(self):
        assert _link_do_caso(_manifestacao()) == LINK_DO_CASO

    def test_endereco_do_caso_e_interno_ao_frontend(self):
        """Quem clica deslogado cai no login e volta pelo `?redirect=` da
        issue #477, que só aceita caminho interno."""
        destino = urlparse(_link_do_caso(_manifestacao()))
        frontend = urlparse(settings.frontend_url)

        assert (destino.scheme, destino.netloc) == (frontend.scheme, frontend.netloc)
        assert destino.path == f"/ouvidoria/m/{PROTOCOLO}"

    def test_todos_os_emails_de_quem_tem_login_seguem_o_mesmo_helper(self, monkeypatch):
        """Trocar o helper troca os cinco de uma vez: se algum montasse o
        endereço por conta própria, ficaria para trás aqui."""
        monkeypatch.setattr(notificacoes, "_link_do_caso", lambda _: "http://exemplo.invalido/caso")

        emails = [
            montar_alerta_sem_titular(_manifestacao(), "Ana", "Bruno", AGORA, SEM_FERIADOS),
            montar_escalonamento_diretoria(_manifestacao(), "Ana", AGORA, SEM_FERIADOS),
            montar_alerta_cadastro_setor(_manifestacao(), "Ana", AGORA, SEM_FERIADOS),
            montar_critico_imediato(_manifestacao(), "Ana", AGORA, SEM_FERIADOS),
            montar_prorrogacao_solicitada(_manifestacao(), "Ana", _pedido(), AGORA, SEM_FERIADOS),
        ]

        for _, html, _ in emails:
            assert _hrefs(html) == {"http://exemplo.invalido/caso"}
