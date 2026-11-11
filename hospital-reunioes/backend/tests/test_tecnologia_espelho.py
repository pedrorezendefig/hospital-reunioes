"""Os cards que a Vitta abre pelo terminal aparecem na aba (issue #1554, PRD #1548, ADR 0084, decisao 4).

Tres seams:

* **O espelho**, chamado direto: e modulo puro com tabela de casos. Uma funcao
  so decide se a issue vira Demanda de Origem Vitta.
* **O webhook**, pela ROTA de verdade com HMAC, no molde de
  `test_tecnologia_webhook_github`: o `issues.opened` da raiz de app cria a
  Demanda e a sincronizacao lhe da a Etapa e as partes.
* **A lista e a leitura**, pela rota da aba, no molde de
  `test_tecnologia_lista_filtros`: o diretor ve os cards Vitta, o selo e o
  filtro de Origem.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from test_tecnologia_chat import CHAT, _cenario  # noqa: E402
from test_tecnologia_vinculo import DIRETOR, PEDRO, _pessoa  # noqa: E402
from test_tecnologia_vinculo import _demanda as _demanda_da_aba  # noqa: E402
from test_tecnologia_webhook_github import (  # noqa: E402
    REPO,
    _demanda,
    _demandas,
    _entregar,
    _GithubFalso,
    _montar,
    _segredo_configurado,  # noqa: F401 (fixture autouse: o segredo e o repositorio de pe)
    _sem_github_de_verdade,  # noqa: F401 (fixture autouse: nenhuma chamada sai para a rede)
)

from app.limiter import limiter  # noqa: E402
from app.services.conhecimento import CONHECIMENTO_DIR  # noqa: E402
from app.services.tecnologia_espelho import CRIA, IGNORA, JA_EXISTE, decidir  # noqa: E402
from app.services.tecnologia_vinculo import ETAPA_EM_ANALISE, ETAPA_EM_DESENVOLVIMENTO  # noqa: E402

OUTRO_DIRETOR = _pessoa("P3", "Outra Diretora")


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


def _issue_raiz(numero: int = 1700, *, labels=("type:feature", "area:backend"), corpo=None, **campos) -> dict:
    """Uma issue-raiz do app como o GitHub a manda: PRD aberto pelo terminal."""
    dados = {
        "number": numero,
        "title": "Ouvidoria: prazo de resposta por setor",
        "html_url": f"https://github.com/{REPO}/issues/{numero}",
        "state": "open",
        "state_reason": None,
        "labels": [{"name": nome} for nome in labels],
        "body": corpo
        if corpo is not None
        else "## 👔 Para o diretor\n\n**O que muda:** o prazo aparece por setor.\n\n---\n\n## Problema\n\nX.",
        "user": {"login": "pedrorezendefig"},
        "parent_issue_url": None,
    }
    dados.update(campos)
    return dados


# ═══════════════════════════════════════════════════════════════════════════
# 1. A tabela de casos do espelho
# ═══════════════════════════════════════════════════════════════════════════


class TestTabelaDoEspelho:
    @pytest.mark.parametrize(
        "labels",
        [
            ("type:feature", "area:backend"),
            ("type:fix", "area:frontend"),
            ("type:bug", "area:supabase"),
            ("type:feature", "area:frontend", "area:skills"),
            ("Type:Feature", "Area:Backend", "ready-for-agent"),
        ],
    )
    def test_raiz_de_app_cria(self, labels):
        assert decidir(_issue_raiz(labels=labels), None) == CRIA

    def test_parte_ignora_pela_secao_pai_do_corpo(self):
        """Ao abrir, a parte ainda nao e sub-issue: o `/to-issues` a vincula
        depois. Quem a denuncia e a secao Pai do corpo."""
        corpo = "## 👔 Para o diretor\n\nX.\n\n---\n\n## Pai\n\n#1548\n\n## O que construir\n\nY."
        assert decidir(_issue_raiz(corpo=corpo), None) == IGNORA

    def test_parte_ignora_pelo_pai_nativo(self):
        url = f"https://api.github.com/repos/{REPO}/issues/1548"
        assert decidir(_issue_raiz(parent_issue_url=url), None) == IGNORA

    def test_fatia_avulsa_com_pai_nenhum_cria(self):
        corpo = "## Pai\n\nNenhum\n\n## O que construir\n\nY."
        assert decidir(_issue_raiz(corpo=corpo), None) == CRIA

    @pytest.mark.parametrize(
        "labels",
        [
            ("type:feature", "area:skills"),
            ("type:feature", "area:docs"),
            ("type:fix", "area:infra"),
            ("type:feature", "area:skills", "area:docs", "area:infra"),
            ("type:feature",),
        ],
    )
    def test_ferramenta_ou_sem_area_de_app_ignora(self, labels):
        assert decidir(_issue_raiz(labels=labels), None) == IGNORA

    @pytest.mark.parametrize("labels", [("area:backend",), ("type:chore", "area:backend"), ("type:docs", "area:frontend")])
    def test_sem_tipo_de_entrega_ignora(self, labels):
        assert decidir(_issue_raiz(labels=labels), None) == IGNORA

    def test_com_marcador_de_demanda_ignora(self):
        """O card que o diretor criou no chat ja tem Demanda: o `opened` chega
        antes de o app gravar o numero, e sem esta regra viraria duas."""
        corpo = '## Problema\n\nX.\n\n<!-- demanda-vitta id="d-123" -->\n'
        assert decidir(_issue_raiz(corpo=corpo), None) == IGNORA

    def test_repetido_devolve_ja_existe(self):
        assert decidir(_issue_raiz(), _demanda("D1", github_issue_numero=1700)) == JA_EXISTE

    def test_apagada_ignora(self):
        lapide = _demanda("D1", github_issue_numero=1700, apagada_em="2026-11-10T10:00:00+00:00")
        assert decidir(_issue_raiz(), lapide) == IGNORA

    def test_pull_request_ignora(self):
        assert decidir(_issue_raiz(pull_request={"url": "x"}), None) == IGNORA


# ═══════════════════════════════════════════════════════════════════════════
# 2. O webhook cria a Demanda Vitta
# ═══════════════════════════════════════════════════════════════════════════

PRODUTOS = [
    {"id": "prod-2", "nome": "Ouvidoria", "ativo": True, "ordem": 2},
    {"id": "prod-0", "nome": "Velho", "ativo": False, "ordem": 0},
    {"id": "prod-1", "nome": "Reuniões", "ativo": True, "ordem": 1},
]


def _corpo_do_evento(issue: dict, acao: str = "opened") -> bytes:
    import json

    payload = {"action": acao, "issue": issue, "repository": {"full_name": REPO}}
    return json.dumps(payload, indent=2).encode("utf-8")


def _entregar_issue(monkeypatch, issue: dict, *, acao="opened", demandas=None, participantes=None, partes=None):
    numero = issue["number"]
    gh = _GithubFalso({numero: issue}, sub_issues={numero: partes or []})
    cliente, sb, gh = _montar(
        demandas=demandas or [],
        participantes=participantes if participantes is not None else [PEDRO],
        produtos=PRODUTOS,
        github=gh,
        monkeypatch=monkeypatch,
    )
    resposta = _entregar(cliente, _corpo_do_evento(issue, acao))
    return resposta, sb, gh


def _parte(numero: int, *, estado="open", labels=("ready-for-agent",)) -> dict:
    return {
        "number": numero,
        "title": f"Parte {numero}",
        "html_url": f"https://github.com/{REPO}/issues/{numero}",
        "state": estado,
        "state_reason": "completed" if estado == "closed" else None,
        "labels": [{"name": n} for n in labels],
        "body": "## 👔 Para o diretor\n\n**O que muda:** uma parte.\n\n---\n",
    }


class TestWebhookCriaADemandaVitta:
    def test_opened_de_raiz_de_app_cria_a_demanda_vitta_com_etapa_e_partes(self, monkeypatch):
        issue = _issue_raiz(labels=("type:feature", "area:backend", "in-progress"))
        partes = [_parte(1701, estado="closed"), _parte(1702, labels=("in-progress",))]

        resposta, sb, _ = _entregar_issue(monkeypatch, issue, partes=partes)

        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["espelhada"] is True
        [demanda] = _demandas(sb)
        assert demanda["origem"] == "vitta"
        assert demanda["github_issue_numero"] == 1700
        assert demanda["titulo"] == "Ouvidoria: prazo de resposta por setor"
        assert demanda["tipo"] == "novo"
        assert demanda["autor_id"] == PEDRO["id"]
        assert demanda["produto_id"] == "prod-1"
        assert demanda["etapa"] == ETAPA_EM_DESENVOLVIMENTO
        assert (demanda["partes_entregues"], demanda["partes_total"]) == (1, 2)
        assert demanda["o_que_muda"] == "**O que muda:** o prazo aparece por setor."

    def test_o_bug_do_terminal_nasce_defeito(self, monkeypatch):
        resposta, sb, _ = _entregar_issue(monkeypatch, _issue_raiz(labels=("type:fix", "area:frontend")))

        assert resposta.status_code == 200
        assert _demandas(sb)[0]["tipo"] == "defeito"

    def test_edited_tambem_espelha(self, monkeypatch):
        resposta, sb, _ = _entregar_issue(monkeypatch, _issue_raiz(), acao="edited")

        assert resposta.status_code == 200
        assert [d["origem"] for d in _demandas(sb)] == ["vitta"]

    def test_autor_sem_cadastro_vira_o_dono_configurado(self, monkeypatch):
        issue = _issue_raiz(user={"login": "alguem-de-fora"})

        _, sb, _ = _entregar_issue(monkeypatch, issue)

        assert _demandas(sb)[0]["autor_id"] == PEDRO["id"]

    def test_autor_com_login_no_cadastro_e_ele(self, monkeypatch):
        rib = _pessoa("P4", "Pedro Rib", github_login="pedrorib")
        issue = _issue_raiz(user={"login": "PedroRib"})

        _, sb, _ = _entregar_issue(monkeypatch, issue, participantes=[PEDRO, rib])

        assert _demandas(sb)[0]["autor_id"] == "P4"

    def test_parte_aberta_nao_cria_nem_le_o_github(self, monkeypatch):
        corpo = "## Pai\n\n#1548\n\n## O que construir\n\nY."
        resposta, sb, gh = _entregar_issue(monkeypatch, _issue_raiz(corpo=corpo))

        assert resposta.json() == {"ignorado": "sem_vinculo"}
        assert _demandas(sb) == []
        assert gh.leituras == []

    def test_o_card_do_chat_aberto_nao_vira_segunda_demanda(self, monkeypatch):
        corpo = '## Problema\n\nX.\n\n<!-- demanda-vitta id="d-123" -->\n'
        resposta, sb, _ = _entregar_issue(monkeypatch, _issue_raiz(corpo=corpo))

        assert resposta.json() == {"ignorado": "sem_vinculo"}
        assert _demandas(sb) == []

    @pytest.mark.parametrize("acao", ["opened", "edited"])
    def test_a_issue_apagada_nao_volta(self, acao, monkeypatch):
        lapide = _demanda("D1", github_issue_numero=1700, apagada_em="2026-11-10T10:00:00+00:00")

        resposta, sb, gh = _entregar_issue(monkeypatch, _issue_raiz(), acao=acao, demandas=[lapide])

        assert resposta.status_code == 200
        assert [d["id"] for d in _demandas(sb)] == ["D1"]
        assert _demandas(sb)[0]["github_foto"] is None
        assert gh.leituras == []

    def test_a_releitura_manda_quando_o_payload_ficou_velho(self, monkeypatch):
        """O payload diz raiz de app, mas a issue relida ja virou parte: quem
        cria e a releitura, nunca o corpo do evento."""
        no_evento = _issue_raiz()
        relida = _issue_raiz(parent_issue_url=f"https://api.github.com/repos/{REPO}/issues/1548")
        gh = _GithubFalso({1700: relida})
        cliente, sb, _ = _montar(participantes=[PEDRO], produtos=PRODUTOS, github=gh, monkeypatch=monkeypatch)

        resposta = _entregar(cliente, _corpo_do_evento(no_evento))

        assert resposta.status_code == 200
        assert _demandas(sb) == []


# ═══════════════════════════════════════════════════════════════════════════
# 3. Quem ve: o diretor ve os cards Vitta
# ═══════════════════════════════════════════════════════════════════════════


def _cards() -> list[dict]:
    return [
        _demanda_da_aba(
            "d-vitta",
            github_issue_numero=1700,
            titulo="Ouvidoria: prazo por setor",
            origem="vitta",
            autor_id=PEDRO["id"],
            etapa=ETAPA_EM_ANALISE,
            criado_em="2026-11-10T10:00:00Z",
        ),
        _demanda_da_aba(
            "d-minha",
            github_issue_numero=1701,
            titulo="Botão de imprimir",
            origem="diretor",
            autor_id=DIRETOR["id"],
            etapa=ETAPA_EM_ANALISE,
            criado_em="2026-11-09T10:00:00Z",
        ),
        _demanda_da_aba(
            "d-outra",
            github_issue_numero=1702,
            titulo="Pedido da outra diretora",
            origem="diretor",
            autor_id=OUTRO_DIRETOR["id"],
            etapa=ETAPA_EM_ANALISE,
            criado_em="2026-11-08T10:00:00Z",
        ),
    ]


def _aba(monkeypatch, logado: dict):
    client, sb, _ = _cenario(
        monkeypatch, logado=logado, participantes=[PEDRO, DIRETOR, OUTRO_DIRETOR], demandas=_cards()
    )
    return client, sb


def _ids(resposta) -> list[str]:
    assert resposta.status_code == 200, resposta.text
    return [d["id"] for d in resposta.json()]


class TestQuemVe:
    def test_o_diretor_ve_as_dele_e_os_cards_vitta(self, monkeypatch):
        client, _ = _aba(monkeypatch, DIRETOR)

        assert _ids(client.get(CHAT)) == ["d-vitta", "d-minha"]

    def test_o_diretor_nao_ve_a_conversa_de_outro_autor_nem_em_todas(self, monkeypatch):
        client, _ = _aba(monkeypatch, DIRETOR)

        assert _ids(client.get(f"{CHAT}?filtro=todas")) == ["d-vitta", "d-minha"]
        assert client.get(f"{CHAT}/d-outra/conversa").status_code == 404

    def test_o_card_vitta_nao_e_do_diretor(self, monkeypatch):
        client, _ = _aba(monkeypatch, DIRETOR)

        vitta = next(d for d in client.get(CHAT).json() if d["id"] == "d-vitta")

        assert vitta["minha"] is False
        assert vitta["issue_numero"] is None
        assert vitta["pode_apagar"] is False

    def test_o_desenvolvedor_em_minhas_continua_so_com_as_dele(self, monkeypatch):
        client, _ = _aba(monkeypatch, PEDRO)

        assert _ids(client.get(CHAT)) == ["d-vitta"]


# ═══════════════════════════════════════════════════════════════════════════
# 4. O selo e o chip Origem
# ═══════════════════════════════════════════════════════════════════════════


class TestOrigemNaLista:
    def test_cada_linha_diz_a_origem(self, monkeypatch):
        client, _ = _aba(monkeypatch, PEDRO)

        origens = {d["id"]: d["origem"] for d in client.get(f"{CHAT}?filtro=todas").json()}

        assert origens == {"d-vitta": "vitta", "d-minha": "diretor", "d-outra": "diretor"}

    def test_a_demanda_de_antes_da_coluna_e_pedido_do_diretor(self, monkeypatch):
        antiga = _demanda_da_aba("d-antiga", autor_id=DIRETOR["id"])
        antiga.pop("origem", None)
        client, _, _ = _cenario(monkeypatch, logado=DIRETOR, participantes=[DIRETOR], demandas=[antiga])

        assert client.get(CHAT).json()[0]["origem"] == "diretor"

    @pytest.mark.parametrize(
        ("logado", "consulta", "esperado"),
        [
            (DIRETOR, "origem=vitta", ["d-vitta"]),
            (DIRETOR, "origem=diretor", ["d-minha"]),
            (PEDRO, "filtro=todas&origem=diretor", ["d-minha", "d-outra"]),
            (PEDRO, "filtro=todas&origem=vitta&etapa=em_analise", ["d-vitta"]),
        ],
    )
    def test_o_chip_origem_filtra(self, monkeypatch, logado, consulta, esperado):
        client, _ = _aba(monkeypatch, logado)

        assert _ids(client.get(f"{CHAT}?{consulta}")) == esperado

    def test_origem_desconhecida_e_recusada(self, monkeypatch):
        client, _ = _aba(monkeypatch, DIRETOR)

        assert client.get(f"{CHAT}?origem=terminal").status_code == 422


# ═══════════════════════════════════════════════════════════════════════════
# 5. A Demanda Vitta abre o documento e a Conversa da Demanda, sem o chat
# ═══════════════════════════════════════════════════════════════════════════


class TestDemandaVittaAberta:
    def test_o_diretor_le_e_escreve_na_conversa_da_demanda_vitta(self, monkeypatch):
        client, sb = _aba(monkeypatch, DIRETOR)

        assert client.get(f"{CHAT}/d-vitta/conversa").status_code == 200
        escrita = client.post(f"{CHAT}/d-vitta/conversa", json={"texto": "Quando fica pronto?"})

        assert escrita.status_code == 201, escrita.text
        [linha] = sb.tabelas["tecnologia_conversa_da_demanda"]
        assert (linha["demanda_id"], linha["autor_id"]) == ("d-vitta", DIRETOR["id"])

    def test_a_demanda_vitta_nao_tem_chat_do_agente(self, monkeypatch):
        client, _ = _aba(monkeypatch, DIRETOR)

        assert client.get(f"{CHAT}/d-vitta").status_code == 404


# ═══════════════════════════════════════════════════════════════════════════
# 6. O Kit de conhecimento
# ═══════════════════════════════════════════════════════════════════════════


def _secao(titulo: str) -> str:
    texto = (CONHECIMENTO_DIR / "tecnologia.md").read_text(encoding="utf-8")
    return texto.split(f"## {titulo}", 1)[1].split("\n## ", 1)[0]


class TestKit:
    def test_o_kit_diz_que_o_diretor_ve_os_cards_da_vitta(self):
        secao = _secao("Quem vê")
        for trecho in ("**Vitta**", "**Pedido do diretor**", "**Origem**"):
            assert trecho in secao, trecho
        assert "cada diretor vê só as suas conversas" not in secao

    def test_o_kit_diz_que_o_card_da_vitta_nao_tem_conversa_com_a_ia(self):
        secao = _secao("O que é uma Demanda")
        assert "pelo desenvolvimento" in secao
        assert "sem conversa com a IA" in secao

    def test_o_kit_diz_que_ajuste_interno_nao_aparece(self):
        secao = _secao("O que é uma Demanda")
        assert "ajustes internos" in secao

