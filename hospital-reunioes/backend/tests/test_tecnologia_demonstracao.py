"""A Demonstração no card (issue #1559, PRD #1548).

A sincronização lê na issue-raiz o marcador `<!-- demonstracao: https://... -->`
e grava o link e a data em que ele chegou. Só `https` entra. A data muda só
quando o link é novo ou trocou, e tirar o marcador da issue não apaga o link
já gravado. A lista entrega os dois campos à tela, que desenha o selo e a
seção do Documento do card.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from test_tecnologia_chat import CHAT, _cenario  # noqa: E402
from test_tecnologia_vinculo import DIRETOR  # noqa: E402
from test_tecnologia_vinculo import _demanda as _demanda_do_diretor  # noqa: E402
from test_tecnologia_webhook_github import (  # noqa: E402
    _corpo,
    _demandas,
    _entregar,
    _GithubFalso,
    _issue,
    _ja_sincronizada,
    _montar,
    _pr_do_app,  # noqa: F401  (autouse)
    _reset_rate_limiter,  # noqa: F401  (autouse)
    _segredo_configurado,  # noqa: F401  (autouse)
    _sem_github_de_verdade,  # noqa: F401  (autouse)
    _sem_pr_aberto,  # noqa: F401  (autouse)
)

from app.services.conhecimento import CONHECIMENTO_DIR  # noqa: E402

VIDEO = "https://youtu.be/demo-do-selo"
OUTRO_VIDEO = "https://youtu.be/demo-refeita"
GRAVADA_EM = "2026-11-08T10:00:00+00:00"


def _com_corpo(corpo: str) -> dict:
    return {**_issue(673), "body": f"## Para o diretor\n\nO selo se atualiza sozinho.\n\n{corpo}"}


def _sincronizar(issue: dict, monkeypatch, **campos) -> dict:
    """Entrega o `issues.edited` da raiz e devolve a Demanda como ficou."""
    gh = _GithubFalso({673: issue})
    cliente, sb, _ = _montar(
        demandas=[_ja_sincronizada(_GithubFalso({673: _issue(673)}), 673, **campos)], github=gh, monkeypatch=monkeypatch
    )
    _entregar(cliente, _corpo(acao="edited"))
    [demanda] = _demandas(sb)
    return demanda


class TestOMarcador:
    def test_o_marcador_com_https_grava_o_link_e_a_data(self, monkeypatch):
        demanda = _sincronizar(_com_corpo(f"<!-- demonstracao: {VIDEO} -->"), monkeypatch)

        assert demanda["demonstracao_url"] == VIDEO
        assert demanda["demonstracao_em"]

    @pytest.mark.parametrize(
        "marcador",
        [
            "<!-- demonstracao: http://youtu.be/demo-do-selo -->",
            "<!-- demonstracao: https:// -->",
            "<!-- demonstracao: javascript:alert(1) -->",
            '<!-- demonstracao: https://youtu.be/x"onclick="y -->',
        ],
    )
    def test_o_marcador_sem_https_ou_malformado_e_ignorado(self, monkeypatch, marcador):
        demanda = _sincronizar(_com_corpo(marcador), monkeypatch)

        assert (demanda.get("demonstracao_url"), demanda.get("demonstracao_em")) == (None, None)

    def test_o_mesmo_link_de_novo_nao_muda_a_data(self, monkeypatch):
        demanda = _sincronizar(
            _com_corpo(f"<!-- demonstracao: {VIDEO} -->"),
            monkeypatch,
            demonstracao_url=VIDEO,
            demonstracao_em=GRAVADA_EM,
        )

        assert (demanda["demonstracao_url"], demanda["demonstracao_em"]) == (VIDEO, GRAVADA_EM)

    def test_o_link_trocado_grava_o_novo_e_a_data_nova(self, monkeypatch):
        demanda = _sincronizar(
            _com_corpo(f"<!-- demonstracao: {OUTRO_VIDEO} -->"),
            monkeypatch,
            demonstracao_url=VIDEO,
            demonstracao_em=GRAVADA_EM,
        )

        assert demanda["demonstracao_url"] == OUTRO_VIDEO
        assert demanda["demonstracao_em"] not in (None, GRAVADA_EM)

    def test_tirar_o_marcador_da_issue_nao_apaga_o_link_gravado(self, monkeypatch):
        demanda = _sincronizar(
            {**_issue(673), "body": "## Para o diretor\n\nO selo agora diz outra coisa."},
            monkeypatch,
            demonstracao_url=VIDEO,
            demonstracao_em=GRAVADA_EM,
        )

        assert demanda["o_que_muda"] == "O selo agora diz outra coisa."
        assert (demanda["demonstracao_url"], demanda["demonstracao_em"]) == (VIDEO, GRAVADA_EM)


class TestALista:
    def test_a_lista_entrega_o_link_e_a_data_da_demonstracao(self, monkeypatch):
        client, _, _ = _cenario(
            monkeypatch,
            logado=DIRETOR,
            participantes=[DIRETOR],
            demandas=[
                _demanda_do_diretor(
                    "d-1",
                    autor_id=DIRETOR["id"],
                    github_issue_numero=673,
                    demonstracao_url=VIDEO,
                    demonstracao_em=GRAVADA_EM,
                )
            ],
        )

        [item] = client.get(CHAT).json()

        assert (item["demonstracao_url"], item["demonstracao_em"]) == (VIDEO, GRAVADA_EM)


class TestOKit:
    def test_o_kit_da_tecnologia_diz_a_demonstracao(self):
        texto = (CONHECIMENTO_DIR / "tecnologia.md").read_text(encoding="utf-8")

        for trecho in ("**Tem demonstração**", "**Demonstração**"):
            assert trecho in texto, trecho
