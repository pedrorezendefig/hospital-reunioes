"""O email ao Responsavel quando o card do diretor nasce (issue #1635, PRD #1632).

Depois do "Criar o card" que deu certo, no bug e na melhoria, quem foi
escolhido em "Quem cuida disto?" (ou o dono, sem escolha) recebe um email com
o bloco "Para o desenvolvedor" e tres links: a sessao no Vitta OS, a issue no
GitHub e a Demanda no app. O "Reenviar" que cria o card tambem manda; o
"Atualizar o card" e o "Designar de novo" nao.

Falha no email nao desfaz o card: vai para o log e para o sino de cada
Desenvolvedor, como a falha no envio. Responsavel sem email, ou card sem
Responsavel no app, conta como email que nao saiu.

Tudo pela ROTA, com o envio no modo mock do `email_service` (sem Resend nem
SMTP), gravado na porta do transporte.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from test_tecnologia_bloco_do_desenvolvedor import PARTES as PARTES_DA_MELHORIA  # noqa: E402
from test_tecnologia_bloco_do_desenvolvedor import _melhoria_resumida  # noqa: E402
from test_tecnologia_bug_bloco_do_desenvolvedor import PARTES as PARTES_DO_BUG  # noqa: E402
from test_tecnologia_bug_bloco_do_desenvolvedor import _bug_resumido  # noqa: E402
from test_tecnologia_chat import (  # noqa: E402
    _integracao_configurada,  # noqa: F401
    _llm_em_mock,  # noqa: F401
    _reset_rate_limiter,  # noqa: F401
)
from test_tecnologia_chat_le_o_codigo import CHAT, _resumo_da_melhoria  # noqa: E402
from test_tecnologia_vinculo import _pessoa  # noqa: E402

from app.config import settings  # noqa: E402
from app.services import tecnologia_email  # noqa: E402
from app.services.tecnologia_vinculo import bloco_do_desenvolvedor  # noqa: E402

FRONTEND = "https://app.hsm.test"
LUCAS = _pessoa("P5", "Lucas Sampaio", github_login="lucas")


@pytest.fixture(autouse=True)
def emails(monkeypatch, sem_transporte_de_email) -> list[dict]:
    """Cada email que sai, gravado na porta do transporte e passado adiante ao
    envio de verdade, que aqui esta no modo mock (sem Resend nem SMTP)."""
    enviados: list[dict] = []
    envio_de_verdade = tecnologia_email._enviar_email

    def _gravar(destinatario, assunto, html_content, texto_fallback, *a, **kw):
        enviados.append({"para": destinatario, "assunto": assunto, "html": html_content, "texto": texto_fallback})
        return envio_de_verdade(destinatario, assunto, html_content, texto_fallback, *a, **kw)

    monkeypatch.setattr(tecnologia_email, "_enviar_email", _gravar)
    monkeypatch.setattr(settings, "frontend_url", FRONTEND)
    return enviados


def _links(demanda_id: str) -> list[str]:
    """Os tres links do email, na ordem: Vitta OS, issue no GitHub, Demanda."""
    return [
        "http://127.0.0.1:4500/#/sessao/pedrorezendefig/hospital-reunioes/900",
        "https://github.com/pedrorezendefig/hospital-reunioes/issues/900",
        f"{FRONTEND}/admin/tecnologia?demanda={demanda_id}",
    ]


# ═══════════════════════════════════════════════════════════════════════════
# 1. O email do Criar o card
# ═══════════════════════════════════════════════════════════════════════════


class TestOEmailDoCriarOCard:
    def test_o_responsavel_do_bug_recebe_o_email_com_o_bloco_e_os_tres_links(self, monkeypatch, emails):
        client, sb, _, demanda_id, _ = _bug_resumido(monkeypatch, para_o_desenvolvedor=PARTES_DO_BUG)
        sb.tabelas["participantes"].append(dict(LUCAS))

        resposta = client.post(f"{CHAT}/{demanda_id}/criar-card", json={"responsavel_id": "P5"})

        assert resposta.status_code == 200, resposta.text
        [email] = emails
        assert email["para"] == "P5@hsm.com"
        assert email["assunto"] == "Card novo do diretor: Botão de responder some na Ouvidoria"
        assert bloco_do_desenvolvedor(PARTES_DO_BUG) in email["texto"]
        for link in _links(demanda_id):
            assert link in email["texto"], link
            assert f'href="{link}"' in email["html"], link
        for texto in PARTES_DO_BUG.values():
            assert texto in email["html"], texto
