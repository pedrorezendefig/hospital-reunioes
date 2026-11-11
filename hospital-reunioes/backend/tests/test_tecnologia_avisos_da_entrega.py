"""Os avisos de Em produção e de demonstração pronta (issue #1560, PRD #1548).

Na passagem para Em produção (o webhook de deploy e a reconciliação de hora em
hora) e na chegada de um link novo de Demonstração, sai um aviso TECNOLOGIA no
sino e um e-mail, com o link para o Documento do card. No card do diretor
avisa o autor; no card da Vitta, os Super admins que não são Desenvolvedores.
A carga do histórico não passa por esse caminho.

Os dublês são os do webhook do GitHub e do webhook de deploy: o mesmo Supabase
em memória, o mesmo GitHub falso e as mesmas travas autouse contra rede.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from test_tecnologia_webhook_deploy import (  # noqa: E402
    HISTORICO,
    _avisar,
    _corpo_do_deploy,
    _entregue_por_pr,
    _fechada_em,
    _segredo_do_deploy_configurado,  # noqa: F401  (autouse)
)
from test_tecnologia_webhook_github import (  # noqa: E402
    _corpo,
    _entregar,
    _entregue,
    _GithubFalso,
    _issue,
    _ja_sincronizada,
    _montar,
    _pessoa,
    _pr_do_app,  # noqa: F401  (autouse)
    _reset_rate_limiter,  # noqa: F401  (autouse)
    _segredo_configurado,  # noqa: F401  (autouse)
    _sem_github_de_verdade,  # noqa: F401  (autouse)
    _sem_pr_aberto,  # noqa: F401  (autouse)
)

from app.config import settings  # noqa: E402
from app.services import github_client, tecnologia_email, tecnologia_sincronizacao  # noqa: E402

DIRETOR = _pessoa("P1", "Diretor Geral", email="diretor@hsm.test")
DIRETORA = _pessoa("P3", "Diretora Clínica", email="clinica@hsm.test")
DESENVOLVEDOR = _pessoa("P2", "Pedro Rezende", email="pedro@vitta.test", github_login="pedrorezendefig")
DESLIGADO = _pessoa("P4", "Diretor Antigo", email="antigo@hsm.test", ativo=False)
CADASTRO = [DIRETOR, DIRETORA, DESENVOLVEDOR, DESLIGADO]

VIDEO = "https://youtu.be/demo-do-selo"


@pytest.fixture(autouse=True)
def emails(monkeypatch) -> list[dict]:
    """Cada e-mail que sairia, gravado na porta do transporte."""
    enviados: list[dict] = []

    def _gravar(destinatario, assunto, html_content, texto_fallback, *a, **kw):
        enviados.append({"para": destinatario, "assunto": assunto, "html": html_content, "texto": texto_fallback})
        return True

    monkeypatch.setattr(tecnologia_email, "_enviar_email", _gravar)
    monkeypatch.setattr(settings, "frontend_url", "https://app.hsm.test")
    return enviados


def _avisos(sb) -> list[dict]:
    return [n for n in sb.tabelas.get("notificacoes", []) if n.get("tipo") == "TECNOLOGIA"]


def _subir(monkeypatch, demanda_campos: dict | None = None):
    """O card Entregue da issue #673 e o webhook da subida que a leva a Em produção."""
    gh = _GithubFalso({673: _fechada_em(673, "2026-10-08T12:30:00Z")})
    cliente, sb, _ = _montar(
        demandas=[_entregue_por_pr(gh, 673, "D1", autor_id=DIRETOR["id"], **(demanda_campos or {}))],
        participantes=CADASTRO,
        github=gh,
        monkeypatch=monkeypatch,
    )
    return cliente, sb


class TestEmProducaoAvisa:
    def test_em_producao_avisa_o_autor_do_card_do_diretor_uma_vez(self, monkeypatch, emails):
        cliente, sb = _subir(monkeypatch)

        _avisar(cliente, _corpo_do_deploy())

        avisos = _avisos(sb)
        assert [(a["destinatario_id"], a["referencia_id"]) for a in avisos] == [(DIRETOR["id"], "D1")]
        assert [e["para"] for e in emails] == [DIRETOR["email"]]
