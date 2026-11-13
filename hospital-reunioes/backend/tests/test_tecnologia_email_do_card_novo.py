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
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from test_tecnologia_atualizar_o_card import ATUALIZAR, _montar_o_card  # noqa: E402
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
from test_tecnologia_designacao_falhou import _como, _demanda_com_designacao_falhada  # noqa: E402
from test_tecnologia_vinculo import PEDRO, _pessoa, _sem_github_de_verdade  # noqa: E402, F401

from app.config import settings  # noqa: E402
from app.services import github_client, tecnologia_email  # noqa: E402
from app.services.conhecimento import CONHECIMENTO_DIR  # noqa: E402
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

    def test_o_responsavel_da_melhoria_recebe_o_email_com_o_bloco_e_os_tres_links(self, monkeypatch, emails):
        client, sb, _, demanda_id, _, _ = _melhoria_resumida(
            monkeypatch, _resumo_da_melhoria(para_o_desenvolvedor=PARTES_DA_MELHORIA)
        )
        sb.tabelas["participantes"].append(dict(LUCAS))

        resposta = client.post(f"{CHAT}/{demanda_id}/criar-card", json={"responsavel_id": "P5"})

        assert resposta.status_code == 200, resposta.text
        [email] = emails
        assert email["para"] == "P5@hsm.com"
        assert email["assunto"].startswith("Card novo do diretor: ")
        assert bloco_do_desenvolvedor(PARTES_DA_MELHORIA) in email["texto"]
        for link in _links(demanda_id):
            assert link in email["texto"], link
            assert f'href="{link}"' in email["html"], link

    def test_sem_escolha_o_email_vai_para_o_dono_que_recebe_o_card(self, monkeypatch, emails):
        client, _, gh, demanda_id, _ = _bug_resumido(monkeypatch, para_o_desenvolvedor=PARTES_DO_BUG)

        assert client.post(f"{CHAT}/{demanda_id}/criar-card").status_code == 200

        assert gh.criadas[0]["assignees"] == ["pedrorezendefig"]
        assert [e["para"] for e in emails] == ["P1@hsm.com"]

    def test_o_email_avisa_que_o_link_do_vitta_os_abre_o_app_do_proprio_computador(self, monkeypatch, emails):
        client, _, _, demanda_id, _ = _bug_resumido(monkeypatch, para_o_desenvolvedor=PARTES_DO_BUG)

        assert client.post(f"{CHAT}/{demanda_id}/criar-card").status_code == 200

        [email] = emails
        aviso = "Este link abre o Vitta OS do seu próprio computador e só funciona com ele rodando."
        assert aviso in email["texto"]
        assert aviso in email["html"]


# ═══════════════════════════════════════════════════════════════════════════
# 2. O email que nao sai nao desfaz o card
# ═══════════════════════════════════════════════════════════════════════════


AVISO_DO_SINO = "O email de um card novo não saiu"


def _avisos(sb) -> list[dict]:
    return sb.tabelas.get("notificacoes", [])


def _desenvolvedores_avisados(sb, demanda_id: str) -> list[str]:
    avisos = [a for a in _avisos(sb) if a["titulo"] == AVISO_DO_SINO]
    for aviso in avisos:
        assert aviso["tipo"] == "TECNOLOGIA"
        assert aviso["referencia_id"] == demanda_id
    return sorted(a["destinatario_id"] for a in avisos)


class TestOEmailQueNaoSai:
    def test_envio_que_falha_cria_o_card_loga_e_avisa_cada_desenvolvedor(self, monkeypatch, caplog):
        client, sb, gh, demanda_id, _ = _bug_resumido(monkeypatch, para_o_desenvolvedor=PARTES_DO_BUG)
        sb.tabelas["participantes"].append(dict(LUCAS))

        def _cair(*_a, **_kw):
            raise RuntimeError("Resend respondeu 500")

        monkeypatch.setattr(tecnologia_email, "_enviar_email", _cair)

        with caplog.at_level("WARNING"):
            resposta = client.post(f"{CHAT}/{demanda_id}/criar-card")

        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["estado"] == "enviado"
        assert len(gh.criadas) == 1
        assert "Resend respondeu 500" in caplog.text
        assert _desenvolvedores_avisados(sb, demanda_id) == ["P1", "P5"]

    def test_transporte_que_devolve_false_cria_o_card_e_avisa_cada_desenvolvedor(self, monkeypatch):
        # Em producao o Resend fora do ar nao levanta: `_enviar_via_resend` pega
        # a excecao e devolve False. E esse False que tem que acender o sino.
        client, sb, gh, demanda_id, _ = _bug_resumido(monkeypatch, para_o_desenvolvedor=PARTES_DO_BUG)
        sb.tabelas["participantes"].append(dict(LUCAS))
        tentativas: list[str] = []

        def _nao_saiu(destinatario, *_a, **_kw):
            tentativas.append(destinatario)
            return False

        monkeypatch.setattr(tecnologia_email, "_enviar_email", _nao_saiu)

        resposta = client.post(f"{CHAT}/{demanda_id}/criar-card", json={"responsavel_id": "P5"})

        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["estado"] == "enviado"
        assert len(gh.criadas) == 1
        assert tentativas == ["P5@hsm.com"]
        assert _desenvolvedores_avisados(sb, demanda_id) == ["P1", "P5"]

    def test_responsavel_sem_email_no_cadastro_cria_o_card_e_avisa_no_sino(self, monkeypatch, emails):
        client, sb, gh, demanda_id, _ = _bug_resumido(monkeypatch, para_o_desenvolvedor=PARTES_DO_BUG)
        sb.tabelas["participantes"].append({**LUCAS, "email": None})

        resposta = client.post(f"{CHAT}/{demanda_id}/criar-card", json={"responsavel_id": "P5"})

        assert resposta.status_code == 200, resposta.text
        assert len(gh.criadas) == 1
        assert emails == []
        assert _desenvolvedores_avisados(sb, demanda_id) == ["P1", "P5"]

    def test_card_sem_responsavel_no_app_conta_como_email_que_nao_saiu(self, monkeypatch, emails):
        # O dono da configuracao nao esta no cadastro: o card nasce designado a
        # ele no GitHub e sem Responsavel no app.
        monkeypatch.setattr(settings, "github_login_dono", "dono-fora-do-cadastro")
        client, sb, gh, demanda_id, _ = _bug_resumido(monkeypatch, para_o_desenvolvedor=PARTES_DO_BUG)

        resposta = client.post(f"{CHAT}/{demanda_id}/criar-card")

        assert resposta.status_code == 200, resposta.text
        assert gh.criadas[0]["assignees"] == ["dono-fora-do-cadastro"]
        assert emails == []
        assert _desenvolvedores_avisados(sb, demanda_id) == ["P1"]

    def test_o_email_que_sai_nao_avisa_no_sino(self, monkeypatch, emails):
        client, sb, _, demanda_id, _ = _bug_resumido(monkeypatch, para_o_desenvolvedor=PARTES_DO_BUG)

        assert client.post(f"{CHAT}/{demanda_id}/criar-card").status_code == 200

        assert len(emails) == 1
        assert _desenvolvedores_avisados(sb, demanda_id) == []


# ═══════════════════════════════════════════════════════════════════════════
# 3. Quem manda e quem nao manda
# ═══════════════════════════════════════════════════════════════════════════


class TestQuemManda:
    def test_o_reenviar_que_cria_o_card_manda_o_email(self, monkeypatch, emails):
        client, _, gh, demanda_id, _ = _bug_resumido(monkeypatch, para_o_desenvolvedor=PARTES_DO_BUG)
        gh.erro_ao_criar = github_client.GithubIndisponivelError("GitHub respondeu 502")
        assert client.post(f"{CHAT}/{demanda_id}/criar-card").status_code == 502
        assert emails == []
        gh.erro_ao_criar = None

        assert client.post(f"{CHAT}/{demanda_id}/reenviar").status_code == 200

        [email] = emails
        assert email["para"] == "P1@hsm.com"
        assert _links(demanda_id)[0] in email["texto"]

    def test_o_atualizar_o_card_nao_manda_o_email(self, monkeypatch, emails):
        client, _, _ = _montar_o_card(monkeypatch)

        assert client.post(ATUALIZAR).status_code == 200

        assert emails == []

    def test_o_designar_de_novo_nao_manda_o_email(self, monkeypatch, emails):
        _, sb, gh, demanda_id, rede = _demanda_com_designacao_falhada(monkeypatch)
        rede.status_da_designacao = 200
        emails.clear()

        assert _como(PEDRO, sb, gh, monkeypatch).post(f"{CHAT}/{demanda_id}/designar-de-novo").status_code == 200

        assert emails == []


# ═══════════════════════════════════════════════════════════════════════════
# 4. O Kit de conhecimento
# ═══════════════════════════════════════════════════════════════════════════


def test_o_kit_diz_que_quem_cuida_recebe_um_email_quando_o_card_nasce():
    texto = (CONHECIMENTO_DIR / "tecnologia.md").read_text(encoding="utf-8")

    [paragrafo] = [p for p in texto.split("\n\n") if p.startswith("No resumo, no bug e na melhoria")]
    assert re.search(r"quando o card nasce, quem você escolheu[^.]*recebe um email com o (seu )?pedido", paragrafo)
