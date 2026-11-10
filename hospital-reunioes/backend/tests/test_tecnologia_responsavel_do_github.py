"""O Responsável acompanha a troca de dono no GitHub (issue #1534, PRD #1529, ADR 0083, decisão 6).

Depois do card criado, o Responsável é derivado do GitHub, como a Etapa: a
troca de assignee na issue vinculada chega pelo webhook e grava na Demanda o
usuário cujo login do GitHub corresponde. Assignee sem usuário no app aparece
pelo login. O app não tem rota nem botão para trocar o Responsável.

Tudo pela ROTA. O card nasce pelo "Criar o card" de verdade (o molde de
`test_tecnologia_responsavel`), a troca chega pelo webhook com assinatura (o
molde de `test_tecnologia_webhook_github`) e a lista e a Demanda são lidas pela
API da aba, sobre a linha que o webhook gravou.
"""

from __future__ import annotations

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from test_tecnologia_chat import (  # noqa: E402
    CHAT,
    _ate_o_resumo,
    _cenario,
    _demandas,
    _integracao_configurada,  # noqa: F401
    _llm_em_mock,  # noqa: F401
    _reset_rate_limiter,  # noqa: F401
)
from test_tecnologia_responsavel import DIRETOR, LUCAS, PEDRO, RIB, _participantes  # noqa: E402
from test_tecnologia_webhook_github import (  # noqa: E402
    SEGREDO,
    _corpo,
    _entregar,
    _GithubFalso,
    _issue,
    _montar,
    _sem_github_de_verdade,  # noqa: F401
)
from test_tecnologia_webhook_github import _demandas as _demandas_do_webhook  # noqa: E402

from app.config import settings  # noqa: E402

REPO = "pedrorezendefig/hospital-reunioes"


@pytest.fixture(autouse=True)
def _webhook_configurado(monkeypatch):
    monkeypatch.setattr(settings, "github_webhook_secret", SEGREDO)
    monkeypatch.setattr(settings, "github_integracao_repo", REPO)
    monkeypatch.setattr(settings, "github_login_dono", "pedrorezendefig")


def _issue_designada(numero: int, *logins: str) -> dict:
    dados = _issue(numero, labels=("needs-triage",))
    dados["assignees"] = [{"login": login} for login in logins]
    dados["assignee"] = dados["assignees"][0] if logins else None
    return dados


def _card_criado(monkeypatch, responsavel_id: str | None = "P4"):
    """O diretor cria o card escolhendo o Responsável: devolve a tela e o banco."""
    client, sb, _ = _cenario(monkeypatch, logado=DIRETOR, participantes=_participantes())
    demanda_id = _ate_o_resumo(client, monkeypatch)
    corpo = {"responsavel_id": responsavel_id} if responsavel_id else {}
    assert client.post(f"{CHAT}/{demanda_id}/criar-card", json=corpo).status_code == 200
    return client, sb, demanda_id


def _troca_no_github(monkeypatch, sb, *logins: str, acao: str = "assigned"):
    """Alguém da Vitta troca o dono da issue no GitHub e o webhook entrega.

    A linha que o webhook grava volta para o banco da aba, que é de onde a
    lista e a Demanda leem."""
    linha = _demandas(sb)[0]
    numero = linha["github_issue_numero"]
    gh = _GithubFalso({numero: _issue_designada(numero, *logins)})
    cliente, sb_webhook, _ = _montar(
        demandas=[linha], participantes=_participantes(), github=gh, monkeypatch=monkeypatch
    )
    resposta = _entregar(cliente, _corpo(numero, acao=acao))
    sb.tabelas["tecnologia_demandas"] = [dict(d) for d in _demandas_do_webhook(sb_webhook)]
    return resposta


# ═══════════════════════════════════════════════════════════════════════════
# 1. A troca de assignee atualiza o Responsável
# ═══════════════════════════════════════════════════════════════════════════


class TestATrocaDeAssignee:
    def test_a_troca_de_dono_no_github_troca_o_responsavel_da_demanda(self, monkeypatch):
        _, sb, _ = _card_criado(monkeypatch, responsavel_id=RIB["id"])
        assert _demandas(sb)[0]["responsavel_id"] == RIB["id"]

        resposta = _troca_no_github(monkeypatch, sb, "Lucas-Sampaio")

        assert resposta.status_code == 200, resposta.text
        assert resposta.json() == {"recebido": True, "sincronizada": True}
        assert _demandas(sb)[0]["responsavel_id"] == LUCAS["id"]

    def test_tirar_o_dono_no_github_deixa_a_demanda_sem_responsavel(self, monkeypatch):
        _, sb, _ = _card_criado(monkeypatch, responsavel_id=RIB["id"])

        resposta = _troca_no_github(monkeypatch, sb, acao="unassigned")

        assert resposta.json() == {"recebido": True, "sincronizada": True}
        assert _demandas(sb)[0]["responsavel_id"] is None

    def test_com_dois_donos_no_github_vale_o_primeiro(self, monkeypatch):
        _, sb, _ = _card_criado(monkeypatch, responsavel_id=RIB["id"])

        _troca_no_github(monkeypatch, sb, "pedrorezendefig", "pedrorib")

        assert _demandas(sb)[0]["responsavel_id"] == PEDRO["id"]

    def test_a_entrega_repetida_da_troca_nao_reescreve_a_demanda(self, monkeypatch):
        _, sb, _ = _card_criado(monkeypatch, responsavel_id=RIB["id"])
        _troca_no_github(monkeypatch, sb, "lucas-sampaio")

        resposta = _troca_no_github(monkeypatch, sb, "lucas-sampaio")

        assert resposta.json() == {"recebido": True, "sincronizada": False}


# ═══════════════════════════════════════════════════════════════════════════
# 2. A lista e a Demanda mostram o Responsável novo
# ═══════════════════════════════════════════════════════════════════════════


class TestATelaMostraOResponsavelNovo:
    def test_a_lista_mostra_o_responsavel_novo(self, monkeypatch):
        client, sb, demanda_id = _card_criado(monkeypatch, responsavel_id=RIB["id"])
        _troca_no_github(monkeypatch, sb, "lucas-sampaio")

        lista = client.get(CHAT).json()

        assert [(d["id"], d["responsavel"]) for d in lista] == [(demanda_id, "Lucas Sampaio")]

    def test_a_demanda_aberta_mostra_o_responsavel_novo(self, monkeypatch):
        client, sb, demanda_id = _card_criado(monkeypatch, responsavel_id=RIB["id"])
        assert client.get(f"{CHAT}/{demanda_id}").json()["responsavel"] == "Pedro Rib"
        _troca_no_github(monkeypatch, sb, "lucas-sampaio")

        resposta = client.get(f"{CHAT}/{demanda_id}")

        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["responsavel"] == "Lucas Sampaio"

    def test_a_conversa_sem_card_nao_tem_responsavel(self, monkeypatch):
        client, _, _ = _cenario(monkeypatch, logado=DIRETOR, participantes=_participantes())
        demanda_id = _ate_o_resumo(client, monkeypatch)

        assert client.get(f"{CHAT}/{demanda_id}").json()["responsavel"] is None


# ═══════════════════════════════════════════════════════════════════════════
# 3. Assignee sem usuário no app
# ═══════════════════════════════════════════════════════════════════════════


class TestAssigneeSemUsuarioNoApp:
    def test_o_webhook_nao_quebra_e_a_demanda_fica_sem_responsavel_do_app(self, monkeypatch):
        _, sb, _ = _card_criado(monkeypatch, responsavel_id=RIB["id"])

        resposta = _troca_no_github(monkeypatch, sb, "Colaborador-de-Fora")

        assert resposta.status_code == 200, resposta.text
        assert resposta.json() == {"recebido": True, "sincronizada": True}
        assert _demandas(sb)[0]["responsavel_id"] is None

    def test_a_lista_e_a_demanda_mostram_o_login(self, monkeypatch):
        client, sb, demanda_id = _card_criado(monkeypatch, responsavel_id=RIB["id"])
        _troca_no_github(monkeypatch, sb, "Colaborador-de-Fora")

        assert client.get(CHAT).json()[0]["responsavel"] == "Colaborador-de-Fora"
        assert client.get(f"{CHAT}/{demanda_id}").json()["responsavel"] == "Colaborador-de-Fora"

    def test_sem_escolha_e_com_o_dono_fora_do_cadastro_o_card_mostra_o_login_do_dono(self, monkeypatch):
        monkeypatch.setattr(settings, "github_login_dono", "dono-sem-cadastro")
        client, sb, _ = _card_criado(monkeypatch, responsavel_id=None)

        assert _demandas(sb)[0]["responsavel_id"] is None
        assert client.get(CHAT).json()[0]["responsavel"] == "dono-sem-cadastro"


# ═══════════════════════════════════════════════════════════════════════════
# 4. Issue sem Demanda vinculada
# ═══════════════════════════════════════════════════════════════════════════


class TestIssueSemDemanda:
    @pytest.mark.parametrize("acao", ["assigned", "unassigned"])
    def test_a_troca_de_dono_numa_issue_sem_demanda_e_ignorada_sem_erro(self, monkeypatch, acao):
        gh = _GithubFalso({999: _issue_designada(999, "pedrorib")})
        cliente, sb, _ = _montar(participantes=_participantes(), github=gh, monkeypatch=monkeypatch)

        resposta = _entregar(cliente, _corpo(999, acao=acao))

        assert resposta.status_code == 200, resposta.text
        assert resposta.json() == {"ignorado": "sem_vinculo"}
        assert gh.leituras == []
        assert _demandas_do_webhook(sb) == []


# ═══════════════════════════════════════════════════════════════════════════
# 5. O app não troca o Responsável
# ═══════════════════════════════════════════════════════════════════════════


def _corpos_que_levam_responsavel() -> set[tuple[str, str]]:
    """Toda rota do app cujo corpo tem um campo de Responsável.

    A fonte é o schema OpenAPI, e não `app.routes` (issues #542 e #546)."""
    from app.main import app

    cache = app.openapi_schema
    try:
        esquema = app.openapi()
    finally:
        app.openapi_schema = cache
    componentes = esquema.get("components", {}).get("schemas", {})
    assert len(esquema["paths"]) > 50, "O schema voltou quase vazio: a varredura estaria olhando para nada"

    achados = set()
    for caminho, metodos in esquema["paths"].items():
        if "tecnologia" not in caminho and caminho != "/api/webhooks/github":
            # "Responsavel" e palavra de outros modulos (a Pendencia, o quadro
            # da Reuniao); o da Tecnologia so mora nas rotas da aba.
            continue
        for metodo, operacao in metodos.items():
            conteudo = (operacao.get("requestBody") or {}).get("content", {})
            for midia in conteudo.values():
                texto = repr(midia.get("schema"))
                refs = [r.rsplit("/", 1)[-1] for r in re.findall(r"#/components/schemas/[\w.-]+", texto)]
                campos = [c for ref in refs for c in (componentes.get(ref, {}).get("properties") or {})]
                campos += list((midia.get("schema") or {}).get("properties") or {})
                if any("responsavel" in campo.lower() for campo in campos):
                    achados.add((metodo.upper(), caminho))
    return achados


class TestOAppNaoTrocaOResponsavel:
    def test_so_o_criar_o_card_recebe_responsavel(self):
        assert _corpos_que_levam_responsavel() == {("POST", "/api/admin/tecnologia/chat/{demanda_id}/criar-card")}

    def test_criar_o_card_de_novo_nao_troca_o_responsavel(self, monkeypatch):
        client, sb, demanda_id = _card_criado(monkeypatch, responsavel_id=RIB["id"])

        resposta = client.post(f"{CHAT}/{demanda_id}/criar-card", json={"responsavel_id": LUCAS["id"]})

        assert resposta.status_code == 409, resposta.text
        assert _demandas(sb)[0]["responsavel_id"] == RIB["id"]
