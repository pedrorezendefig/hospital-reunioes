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
from app.services.conhecimento import CONHECIMENTO_DIR  # noqa: E402
from app.services.email_service import TEMPLATES_DIR  # noqa: E402

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
        demandas=[_entregue_por_pr(gh, 673, "D1", **{"autor_id": DIRETOR["id"], **(demanda_campos or {})})],
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

    def test_webhook_repetido_e_reconciliacao_depois_nao_avisam_de_novo(self, monkeypatch, emails):
        cliente, sb = _subir(monkeypatch)

        _avisar(cliente, _corpo_do_deploy())
        _avisar(cliente, _corpo_do_deploy())
        monkeypatch.setattr(github_client, "ler_historico_de_deploys", lambda: HISTORICO)
        tecnologia_sincronizacao.reconciliar_em_producao(sb)

        assert len(_avisos(sb)) == 1
        assert len(emails) == 1

    def test_a_reconciliacao_avisa_quando_o_webhook_nao_chegou(self, monkeypatch, emails):
        _, sb = _subir(monkeypatch)
        monkeypatch.setattr(github_client, "ler_historico_de_deploys", lambda: HISTORICO)

        tecnologia_sincronizacao.reconciliar_em_producao(sb)
        tecnologia_sincronizacao.reconciliar_em_producao(sb)

        assert [a["destinatario_id"] for a in _avisos(sb)] == [DIRETOR["id"]]
        assert [e["para"] for e in emails] == [DIRETOR["email"]]


class TestQuemEAvisado:
    def test_card_vitta_avisa_os_super_admins_sem_login_do_github(self, monkeypatch, emails):
        cliente, sb = _subir(monkeypatch, {"origem": "vitta", "autor_id": DESENVOLVEDOR["id"]})

        _avisar(cliente, _corpo_do_deploy())

        assert sorted(a["destinatario_id"] for a in _avisos(sb)) == [DIRETOR["id"], DIRETORA["id"]]
        assert sorted(e["para"] for e in emails) == sorted([DIRETOR["email"], DIRETORA["email"]])

    def test_card_do_diretor_avisa_so_o_autor(self, monkeypatch, emails):
        cliente, sb = _subir(monkeypatch, {"autor_id": DIRETORA["id"]})

        _avisar(cliente, _corpo_do_deploy())

        assert [a["destinatario_id"] for a in _avisos(sb)] == [DIRETORA["id"]]


def _com_demonstracao(url: str) -> dict:
    return {**_issue(673), "body": f"## Para o diretor\n\nO selo se atualiza sozinho.\n\n<!-- demonstracao: {url} -->"}


class TestDemonstracaoAvisa:
    def _editar(self, monkeypatch, issue: dict, **campos):
        """Entrega o `issues.edited` da raiz e devolve o banco."""
        gh = _GithubFalso({673: issue})
        guardada = _ja_sincronizada(_GithubFalso({673: _issue(673)}), 673, autor_id=DIRETOR["id"], **campos)
        cliente, sb, _ = _montar(demandas=[guardada], participantes=CADASTRO, github=gh, monkeypatch=monkeypatch)
        _entregar(cliente, _corpo(acao="edited"))
        return sb

    def test_demonstracao_nova_gera_um_aviso(self, monkeypatch, emails):
        sb = self._editar(monkeypatch, _com_demonstracao(VIDEO))

        avisos = _avisos(sb)
        assert [(a["destinatario_id"], a["titulo"]) for a in avisos] == [(DIRETOR["id"], "Demonstração pronta")]
        assert [e["para"] for e in emails] == [DIRETOR["email"]]

    def test_o_mesmo_link_de_novo_nao_avisa(self, monkeypatch, emails):
        sb = self._editar(
            monkeypatch,
            _com_demonstracao(VIDEO),
            demonstracao_url=VIDEO,
            demonstracao_em="2026-11-08T10:00:00+00:00",
            o_que_muda="Antes.",
        )

        assert _avisos(sb) == []
        assert emails == []


BLOCO = (
    "**O que muda:** o prazo aparece por setor.\n\n"
    "**O que você precisa saber:**\n"
    "- O filtro fica no alto da lista.\n"
    "- Vale para **todos** os setores."
)


class TestOEmail:
    def test_o_email_traz_a_frase_os_topicos_e_o_link_do_card(self, monkeypatch, emails):
        cliente, _ = _subir(monkeypatch, {"titulo": "Prazo por setor", "o_que_muda": BLOCO})

        _avisar(cliente, _corpo_do_deploy())

        [email] = emails
        assert email["assunto"] == "Entrou no ar: Prazo por setor"
        link = "https://app.hsm.test/admin/tecnologia?demanda=D1"
        for corpo in (email["html"], email["texto"]):
            assert "o prazo aparece por setor." in corpo
            assert "O filtro fica no alto da lista." in corpo
            assert "Vale para todos os setores." in corpo
            assert "O que muda:" not in corpo
            assert link in corpo
        assert f'href="{link}"' in email["html"]
        assert "<li>O filtro fica no alto da lista.</li>" in email["html"]

    def test_o_template_do_email_nao_tem_travessao(self):
        texto = (TEMPLATES_DIR / "email_tecnologia_entrega.html").read_text(encoding="utf-8")

        assert "—" not in texto
        assert "–" not in texto


class TestOKit:
    def test_o_kit_da_tecnologia_diz_os_avisos_da_entrega(self):
        texto = (CONHECIMENTO_DIR / "tecnologia.md").read_text(encoding="utf-8")

        for trecho in ("entra em produção", "vídeo de demonstração fica pronto", "sino e por e-mail"):
            assert trecho in texto, trecho
