"""A Conversa da Demanda, com menção e aviso no sino (issue #1537, PRD #1529, ADR 0083, decisão 8).

A troca de mensagens entre o diretor e os Desenvolvedores dentro de uma
Demanda: tabela própria, separada da conversa com o agente, e que nunca vai
para o GitHub. Escreve e lê quem vê a Demanda (o `pode_ver`, a mesma regra da
lista). Menção é por nome, no formato dos comentários de Pendência
("@Nome Completo"). O aviso sai pelo sino e, desde a issue #1538, também
por e-mail, para o mesmo destinatário:

- menção avisa o mencionado;
- sem menção, a mensagem do autor da Demanda avisa o Responsável, e a do
  Desenvolvedor avisa o autor;
- ninguém é avisado da própria mensagem.

Tudo pela ROTA, no molde de `test_tecnologia_desenvolvedor`.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from test_tecnologia_vinculo import BASE, DIRETOR, PEDRO, _demanda, _montar, _pessoa  # noqa: E402

from app.config import settings  # noqa: E402
from app.limiter import limiter  # noqa: E402
from app.services import github_client, tecnologia_email  # noqa: E402

# Outro Desenvolvedor da Vitta e outra pessoa da diretoria (Super admin sem
# login do GitHub, que não vê a Demanda do DIRETOR).
LUCAS = _pessoa("P4", "Lucas Sampaio", github_login="lucas-vitta")
OUTRO_DIRETOR = _pessoa("P3", "Outro Diretor")

DEMANDA = "d-1"
CONVERSA = f"{BASE}/chat/{DEMANDA}/conversa"


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


@pytest.fixture(autouse=True)
def emails(monkeypatch) -> list[dict]:
    """Cada e-mail que sairia, gravado na porta do transporte (Resend, SMTP ou
    mock): daqui para dentro é o serviço de e-mail que já existe. Autouse
    porque toda mensagem da Conversa avisa por e-mail."""
    enviados: list[dict] = []

    def _gravar(destinatario, assunto, html_content, texto_fallback, *a, **kw):
        enviados.append({"para": destinatario, "assunto": assunto, "html": html_content, "texto": texto_fallback})
        return True

    monkeypatch.setattr(tecnologia_email, "_enviar_email", _gravar)
    monkeypatch.setattr(settings, "frontend_url", "https://app.hsm.test")
    return enviados


def _demanda_do_diretor(**campos) -> dict:
    """A Demanda do DIRETOR, já com card, de que o PEDRO é o Responsável."""
    base = {"autor_id": DIRETOR["id"], "responsavel_id": PEDRO["id"], "github_issue_numero": 900}
    base.update(campos)
    return _demanda(DEMANDA, titulo="O relatório some", **base)


def _cenario(monkeypatch, *, logado: dict, demanda: dict | None = None, sb=None):
    client, sb, _ = _montar(
        logado=logado,
        participantes=[PEDRO, DIRETOR, OUTRO_DIRETOR, LUCAS],
        demandas=[demanda or _demanda_do_diretor()],
        supabase=sb,
        monkeypatch=monkeypatch,
    )
    return client, sb


def _avisos(sb) -> list[tuple[str, str]]:
    """(destinatário, referência) de cada aviso do sino gravado."""
    return [(n["destinatario_id"], n["referencia_id"]) for n in sb.tabelas.get("notificacoes", [])]


# ═══════════════════════════════════════════════════════════════════════════
# 1. Quem escreve e lê
# ═══════════════════════════════════════════════════════════════════════════


class TestQuemEscreveELe:
    def test_o_autor_e_o_desenvolvedor_escrevem_e_leem_a_conversa(self, monkeypatch):
        diretor, sb = _cenario(monkeypatch, logado=DIRETOR)
        pedro, _ = _cenario(monkeypatch, logado=PEDRO, sb=sb)

        assert diretor.post(CONVERSA, json={"texto": "O relatório sumiu de novo hoje."}).status_code == 201
        assert pedro.post(CONVERSA, json={"texto": "Vi aqui, olho amanhã cedo."}).status_code == 201

        for client in (diretor, pedro):
            resposta = client.get(CONVERSA)
            assert resposta.status_code == 200, resposta.text
            assert [(m["autor"], m["texto"]) for m in resposta.json()["mensagens"]] == [
                ("Diretor do Hospital", "O relatório sumiu de novo hoje."),
                ("Pedro Vitta", "Vi aqui, olho amanhã cedo."),
            ]

    def test_quem_nao_ve_a_demanda_nao_le_nem_escreve_na_conversa(self, monkeypatch):
        diretor, sb = _cenario(monkeypatch, logado=DIRETOR)
        diretor.post(CONVERSA, json={"texto": "Só entre nós."})
        outro, _ = _cenario(monkeypatch, logado=OUTRO_DIRETOR, sb=sb)

        leitura = outro.get(CONVERSA)
        escrita = outro.post(CONVERSA, json={"texto": "Entrei pelo endereço."})

        assert leitura.status_code == 404
        assert "Só entre nós." not in leitura.text
        assert escrita.status_code == 404
        assert [m["texto"] for m in sb.tabelas["tecnologia_conversa_da_demanda"]] == ["Só entre nós."]


# ═══════════════════════════════════════════════════════════════════════════
# 2. O aviso no sino
# ═══════════════════════════════════════════════════════════════════════════


class TestAvisoNoSino:
    def test_mencao_avisa_o_mencionado_no_sino(self, monkeypatch):
        diretor, sb = _cenario(monkeypatch, logado=DIRETOR)

        diretor.post(CONVERSA, json={"texto": "@Lucas Sampaio, consegue ver isto hoje?"})

        # Só o mencionado: com menção, o Responsável (PEDRO) não é avisado.
        assert _avisos(sb) == [(LUCAS["id"], DEMANDA)]
        [aviso] = sb.tabelas["notificacoes"]
        assert aviso["tipo"] == "TECNOLOGIA"
        assert aviso["titulo"] == "Diretor do Hospital mencionou você"
        assert "O relatório some" in aviso["mensagem"]

    def test_mencao_de_quem_nao_ve_a_demanda_nao_avisa_ninguem_alem_do_padrao(self, monkeypatch):
        """O Outro Diretor não abre a Demanda: o "@" dele não vira menção, e a
        mensagem segue a regra de sem menção (avisa o Responsável)."""
        diretor, sb = _cenario(monkeypatch, logado=DIRETOR)

        diretor.post(CONVERSA, json={"texto": "@Outro Diretor, olha isso."})

        assert _avisos(sb) == [(PEDRO["id"], DEMANDA)]

    def test_mensagem_do_autor_sem_mencao_avisa_o_responsavel(self, monkeypatch):
        diretor, sb = _cenario(monkeypatch, logado=DIRETOR, demanda=_demanda_do_diretor(responsavel_id=LUCAS["id"]))

        diretor.post(CONVERSA, json={"texto": "Aconteceu de novo."})

        assert _avisos(sb) == [(LUCAS["id"], DEMANDA)]
        [aviso] = sb.tabelas["notificacoes"]
        assert aviso["titulo"] == "Diretor do Hospital escreveu na Demanda"

    def test_mensagem_de_desenvolvedor_sem_mencao_avisa_o_autor_da_demanda(self, monkeypatch):
        lucas, sb = _cenario(monkeypatch, logado=LUCAS)

        lucas.post(CONVERSA, json={"texto": "Qual navegador o senhor usa?"})

        assert _avisos(sb) == [(DIRETOR["id"], DEMANDA)]

    def test_ninguem_recebe_aviso_da_propria_mensagem(self, monkeypatch):
        """O Responsável que é o próprio autor não se avisa, e quem se menciona
        também não."""
        pedro, sb = _cenario(
            monkeypatch,
            logado=PEDRO,
            demanda=_demanda_do_diretor(autor_id=PEDRO["id"], responsavel_id=PEDRO["id"]),
        )

        pedro.post(CONVERSA, json={"texto": "Anotando para mim."})
        pedro.post(CONVERSA, json={"texto": "@Pedro Vitta lembrar de testar no celular."})

        assert _avisos(sb) == []


# ═══════════════════════════════════════════════════════════════════════════
# 3. O aviso por e-mail (issue #1538, ADR 0083, decisão 8)
# ═══════════════════════════════════════════════════════════════════════════


class TestAvisoPorEmail:
    def test_cada_aviso_do_sino_sai_tambem_por_email_para_o_mesmo_destinatario(self, monkeypatch, emails):
        diretor, sb = _cenario(monkeypatch, logado=DIRETOR)
        lucas, _ = _cenario(monkeypatch, logado=LUCAS, sb=sb)

        diretor.post(CONVERSA, json={"texto": "@Lucas Sampaio, consegue ver isto hoje?"})
        diretor.post(CONVERSA, json={"texto": "Aconteceu de novo."})
        lucas.post(CONVERSA, json={"texto": "Qual navegador o senhor usa?"})

        assert _avisos(sb) == [(LUCAS["id"], DEMANDA), (PEDRO["id"], DEMANDA), (DIRETOR["id"], DEMANDA)]
        assert [e["para"] for e in emails] == [LUCAS["email"], PEDRO["email"], DIRETOR["email"]]

    def test_o_email_traz_o_titulo_quem_escreveu_e_o_link_da_demanda(self, monkeypatch, emails):
        lucas, _ = _cenario(monkeypatch, logado=LUCAS)

        lucas.post(CONVERSA, json={"texto": "Qual navegador o senhor usa?"})

        [email] = emails
        link = f"https://app.hsm.test/admin/tecnologia?demanda={DEMANDA}"
        assert email["assunto"] == "Lucas Sampaio escreveu na Demanda: O relatório some"
        for corpo in (email["html"], email["texto"]):
            assert "O relatório some" in corpo
            assert "Lucas Sampaio" in corpo
            assert link in corpo
        assert f'href="{link}"' in email["html"]

    def test_o_email_nao_traz_numero_de_issue_nem_link_do_github(self, monkeypatch, emails):
        diretor, _ = _cenario(monkeypatch, logado=DIRETOR, demanda=_demanda_do_diretor(github_issue_numero=48213))

        diretor.post(CONVERSA, json={"texto": "@Lucas Sampaio, consegue ver isto hoje?"})

        [email] = emails
        for parte in ("assunto", "html", "texto"):
            assert "48213" not in email[parte], parte
            assert "github" not in email[parte].lower(), parte
            assert "issue" not in email[parte].lower(), parte

    def test_ninguem_recebe_email_da_propria_mensagem(self, monkeypatch, emails):
        pedro, _ = _cenario(
            monkeypatch,
            logado=PEDRO,
            demanda=_demanda_do_diretor(autor_id=PEDRO["id"], responsavel_id=PEDRO["id"]),
        )

        pedro.post(CONVERSA, json={"texto": "Anotando para mim."})
        pedro.post(CONVERSA, json={"texto": "@Pedro Vitta lembrar de testar no celular."})
        pedro.post(CONVERSA, json={"texto": "@Pedro Vitta e @Lucas Sampaio, combinado."})

        assert [e["para"] for e in emails] == [LUCAS["email"]]

    def test_falha_no_email_nao_impede_a_mensagem_nem_o_aviso_do_sino(self, monkeypatch, emails):
        def _cair(*a, **kw):
            raise RuntimeError("Resend fora do ar")

        monkeypatch.setattr(tecnologia_email, "_enviar_email", _cair)
        diretor, sb = _cenario(monkeypatch, logado=DIRETOR)

        resposta = diretor.post(CONVERSA, json={"texto": "@Lucas Sampaio, consegue ver isto hoje?"})

        assert resposta.status_code == 201, resposta.text
        assert [m["texto"] for m in sb.tabelas["tecnologia_conversa_da_demanda"]] == [
            "@Lucas Sampaio, consegue ver isto hoje?"
        ]
        assert _avisos(sb) == [(LUCAS["id"], DEMANDA)]


# ═══════════════════════════════════════════════════════════════════════════
# 4. Nada vai para o GitHub
# ═══════════════════════════════════════════════════════════════════════════


class TestNadaVaiParaOGithub:
    def test_nenhuma_chamada_ao_github_acontece_ao_enviar_mensagem(self, monkeypatch):
        """A Conversa vive só no app (ADR 0083, decisão 8): o repositório é
        público e a fala do diretor não vai para lá. Toda porta do cliente do
        GitHub fica gravando, inclusive a de baixo, por onde qualquer chamada
        passa."""
        diretor, sb = _cenario(monkeypatch, logado=DIRETOR)
        chamadas: list[str] = []
        for nome in ("_chamar", "ler_issue", "ler_sub_issues", "criar_issue"):
            monkeypatch.setattr(github_client, nome, lambda *a, _n=nome, **kw: chamadas.append(_n))

        resposta = diretor.post(CONVERSA, json={"texto": "@Lucas Sampaio, olha o print que mandei."})

        assert resposta.status_code == 201, resposta.text
        assert chamadas == []


# ═══════════════════════════════════════════════════════════════════════════
# 5. A migration 129
# ═══════════════════════════════════════════════════════════════════════════

MIGRATIONS = Path(__file__).resolve().parents[2] / "supabase" / "migrations"
MIGRATION_129 = MIGRATIONS / "129_tecnologia_conversa_da_demanda.sql"


def _sql() -> str:
    return MIGRATION_129.read_text(encoding="utf-8")


class TestMigration:
    def test_a_tabela_nova_tem_rls_ligado_e_nenhuma_policy(self):
        sql = _sql()

        assert "CREATE TABLE IF NOT EXISTS tecnologia_conversa_da_demanda (" in sql
        assert "ALTER TABLE tecnologia_conversa_da_demanda ENABLE ROW LEVEL SECURITY;" in sql
        # Default-deny: quem lê e escreve é o backend com a service_role.
        assert "CREATE POLICY" not in sql.upper()

    def test_o_sino_aceita_o_tipo_da_tecnologia_sem_perder_os_que_ja_existem(self):
        sql = _sql()
        check = sql[sql.index("ADD CONSTRAINT notificacoes_tipo_check") :]

        for tipo in (
            "MENCAO",
            "STATUS_ALTERADO",
            "COMENTARIO",
            "PRAZO_PROXIMO",
            "RESPONSAVEL_ATRIBUIDO",
            "ACEITE_INTERNO",
            "CONTAS_MEDICAS",
            "TECNOLOGIA",
        ):
            assert f"'{tipo}'" in check, tipo

    def test_termina_com_o_recibo_do_proprio_numero(self):
        corpo = "\n".join(linha for linha in _sql().splitlines() if not linha.startswith("--")).strip()

        assert corpo.endswith("INSERT INTO migracoes_aplicadas (numero) VALUES (129) ON CONFLICT (numero) DO NOTHING;")
