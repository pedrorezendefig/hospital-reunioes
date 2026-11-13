"""Os cards da Ana aparecem na aba Tecnologia, so para acompanhar (issue #1714,
PRD #1710, ADR 0093, decisoes 4, 5, 6 e 9).

Quatro seams:

* **O espelho da Ana**, chamado direto: modulo puro com tabela de casos. A raiz
  da Ana vira Demanda; parte, PR e `area:os` ficam de fora. A regra do
  Hospital nao muda.
* **A conferencia de hora em hora**, com o cliente do GitHub falso: cria as
  raizes abertas da Ana que faltam, nunca a concluida, e nao duplica.
* **O bloco para leigo**, pela foto: "Para quem decide" vale como "Para o
  diretor".
* **O painel do card**, pela rota da lista que a tela le: sem Apagar, sem
  Revisar, e o link da issue no repositorio da Ana.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from test_tecnologia_chat import CHAT, _cenario  # noqa: E402
from test_tecnologia_vinculo import PEDRO  # noqa: E402
from test_tecnologia_vinculo import _demanda as _demanda_da_aba  # noqa: E402
from test_tecnologia_webhook_github import (  # noqa: E402
    _demanda,
    _demandas,
    _entregar,
    _GithubFalso,
    _montar,
    _reset_rate_limiter,  # noqa: F401  (autouse)
    _segredo_configurado,  # noqa: F401  (autouse)
    _sem_github_de_verdade,  # noqa: F401  (autouse)
)

from app.config import settings  # noqa: E402
from app.services import github_client, tecnologia_espelho  # noqa: E402
from app.services.tecnologia_espelho import CRIA, IGNORA, decidir  # noqa: E402
from app.services.tecnologia_vinculo import ETAPA_PLANEJADA  # noqa: E402

REPO_ANA = "pedrorezendefig/programa-ana"
HOSPITAL = "hospital"
ANA = "ana"


@pytest.fixture(autouse=True)
def _ana_configurada(monkeypatch):
    """O repositorio da Ana de pe, como estara no Coolify depois da tarefa
    humana #1717, com o token da integracao. Quem prova a Ana desligada e o
    teste que APAGA a variavel."""
    monkeypatch.setattr(settings, "github_integracao_repo_ana", REPO_ANA)
    monkeypatch.setattr(settings, "github_integracao_token", "token-de-teste")


def _issue_da_ana(numero: int = 12, *, labels=("type:feature",), corpo=None, estado="open", **campos) -> dict:
    """Uma issue do repositorio da Ana como o GitHub a manda. O PRD da Ana usa o
    bloco "Para quem decide" e nao tem `area:` de app."""
    dados = {
        "number": numero,
        "title": "Ana: responder o preparo do exame de sangue",
        "html_url": f"https://github.com/{REPO_ANA}/issues/{numero}",
        "state": estado,
        "state_reason": "completed" if estado == "closed" else None,
        "labels": [{"name": nome} for nome in labels],
        "body": corpo
        if corpo is not None
        else "## Para quem decide\n\n**O que muda:** a Ana responde o preparo.\n\n---\n\n## Problema\n\nX.",
        "user": {"login": "pedrorezendefig"},
        "author_association": "OWNER",
        "parent_issue_url": None,
    }
    dados.update(campos)
    return dados


# ═══════════════════════════════════════════════════════════════════════════
# 1. O espelho da Ana
# ═══════════════════════════════════════════════════════════════════════════


class TestOEspelhoDaAna:
    @pytest.mark.parametrize("labels", [("type:feature",), ("type:fix", "ready-for-agent"), ("ready-for-human",), ()])
    def test_a_raiz_da_ana_vira_demanda_sem_exigir_as_labels_do_app(self, labels):
        """A Ana nao usa `area:backend` nem as outras areas do app: a raiz dela
        vira Demanda pelas labels que tiver (ADR 0093, decisao 4)."""
        assert decidir(_issue_da_ana(labels=labels), None, projeto=ANA) == CRIA

    def test_a_parte_da_ana_pela_secao_pai_fica_de_fora(self):
        corpo = "## Para quem decide\n\nX.\n\n---\n\n## Pai\n\n#3\n\n## O que construir\n\nY."
        assert decidir(_issue_da_ana(corpo=corpo), None, projeto=ANA) == IGNORA

    def test_a_parte_da_ana_pelo_pai_nativo_fica_de_fora(self):
        url = f"https://api.github.com/repos/{REPO_ANA}/issues/3"
        assert decidir(_issue_da_ana(parent_issue_url=url), None, projeto=ANA) == IGNORA

    def test_o_pr_da_ana_fica_de_fora(self):
        assert decidir(_issue_da_ana(pull_request={"url": "x"}), None, projeto=ANA) == IGNORA

    def test_a_ferramenta_da_ana_com_area_os_fica_de_fora(self):
        assert decidir(_issue_da_ana(labels=("type:feature", "area:os")), None, projeto=ANA) == IGNORA

    @pytest.mark.parametrize("associacao", ["OWNER", "MEMBER", "COLLABORATOR"])
    def test_a_raiz_aberta_por_quem_e_do_time_vira_demanda(self, associacao):
        assert decidir(_issue_da_ana(author_association=associacao), None, projeto=ANA) == CRIA

    @pytest.mark.parametrize("associacao", ["NONE", "CONTRIBUTOR", "FIRST_TIME_CONTRIBUTOR", "FIRST_TIMER", "", None])
    def test_a_issue_aberta_por_quem_nao_e_do_time_fica_de_fora(self, associacao):
        """O repositorio da Ana e publico: qualquer conta do GitHub abre issue
        la, e sem label nenhuma. So o time (dono, membro ou colaborador) cria
        Demanda (revisao do PR #1746)."""
        assert decidir(_issue_da_ana(author_association=associacao), None, projeto=ANA) == IGNORA

    def test_a_issue_sem_a_associacao_do_autor_fica_de_fora(self):
        issue = _issue_da_ana()
        del issue["author_association"]
        assert decidir(issue, None, projeto=ANA) == IGNORA

    def test_a_concluida_da_ana_fica_de_fora(self):
        """Concluida antiga nao entra (ADR 0093): nem pelo `edited`, nem pela
        conferencia (revisao do PR #1746)."""
        assert decidir(_issue_da_ana(estado="closed"), None, projeto=ANA) == IGNORA

    def test_a_regra_do_hospital_nao_muda(self):
        """A mesma issue sem `area:` de app, no Hospital, segue de fora: a regra
        da Ana nao vaza para o repositorio do app."""
        assert decidir(_issue_da_ana(labels=("type:feature",)), None, projeto=HOSPITAL) == IGNORA
        assert decidir(_issue_da_ana(labels=("type:feature",)), None) == IGNORA


# ═══════════════════════════════════════════════════════════════════════════
# 2. O webhook da Ana e a conferencia de hora em hora
# ═══════════════════════════════════════════════════════════════════════════

PRODUTOS = [{"id": "prod-1", "nome": "Reuniões", "ativo": True, "ordem": 1}]
RIB = {**PEDRO, "id": "P4", "nome": "Pedro Rib", "github_login": "pedrorib"}


def _corpo_do_evento_da_ana(issue: dict, acao: str = "opened") -> bytes:
    import json

    payload = {"action": acao, "issue": issue, "repository": {"full_name": REPO_ANA}}
    return json.dumps(payload, indent=2).encode("utf-8")


class TestOWebhookDaAna:
    def test_o_opened_da_raiz_da_ana_cria_a_demanda_vitta_da_ana_com_o_dono_como_responsavel(self, monkeypatch):
        issue = _issue_da_ana(12, assignees=[{"login": "PedroRib"}])
        gh = _GithubFalso({12: issue}, sub_issues={12: []})
        cliente, sb, _ = _montar(
            demandas=[], participantes=[PEDRO, RIB], produtos=PRODUTOS, github=gh, monkeypatch=monkeypatch
        )

        resposta = _entregar(cliente, _corpo_do_evento_da_ana(issue))

        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["espelhada"] is True
        [demanda] = _demandas(sb)
        assert (demanda["projeto"], demanda["github_issue_numero"], demanda["origem"]) == (ANA, 12, "vitta")
        assert demanda["responsavel_id"] == "P4"

    def test_o_opened_de_quem_nao_e_do_time_nao_cria_demanda(self, monkeypatch):
        issue = _issue_da_ana(12, labels=(), author_association="NONE")
        gh = _GithubFalso({12: issue}, sub_issues={12: []})
        cliente, sb, _ = _montar(
            demandas=[], participantes=[PEDRO, RIB], produtos=PRODUTOS, github=gh, monkeypatch=monkeypatch
        )

        resposta = _entregar(cliente, _corpo_do_evento_da_ana(issue))

        assert resposta.status_code == 200, resposta.text
        assert resposta.json() == {"ignorado": "sem_vinculo"}
        assert _demandas(sb) == []

    def test_o_edited_de_uma_concluida_antiga_nao_cria_demanda(self, monkeypatch):
        issue = _issue_da_ana(9, estado="closed")
        gh = _GithubFalso({9: issue}, sub_issues={9: []})
        cliente, sb, _ = _montar(
            demandas=[], participantes=[PEDRO, RIB], produtos=PRODUTOS, github=gh, monkeypatch=monkeypatch
        )

        resposta = _entregar(cliente, _corpo_do_evento_da_ana(issue, acao="edited"))

        assert resposta.status_code == 200, resposta.text
        assert resposta.json() == {"ignorado": "sem_vinculo"}
        assert _demandas(sb) == []


class _GithubDaAna:
    """O repositorio da Ana como a conferencia o le: a lista das issues abertas,
    e a leitura de cada uma. A lista e o que o GitHub tem, aberta ou fechada: a
    conferencia nao confia so no filtro da consulta para deixar a concluida de
    fora."""

    def __init__(self, issues: list[dict]):
        self.issues = {i["number"]: i for i in issues}
        self.listagens: list[str] = []

    def ler_issues_abertas(self, *, projeto: str) -> list[dict]:
        self.listagens.append(projeto)
        return list(self.issues.values())

    def ler_issue(self, numero: int, *, projeto: str) -> dict:
        return self.issues[numero]

    def ler_sub_issues(self, numero: int, *, projeto: str) -> list[dict]:
        return []


def _conferir(monkeypatch, issues: list[dict], demandas: list[dict] | None = None):
    gh = _GithubDaAna(issues)
    _, sb, _ = _montar(demandas=demandas or [], participantes=[PEDRO], produtos=PRODUTOS, monkeypatch=monkeypatch)
    monkeypatch.setattr(github_client, "ler_issues_abertas", gh.ler_issues_abertas)
    monkeypatch.setattr(github_client, "ler_issue", gh.ler_issue)
    monkeypatch.setattr(github_client, "ler_sub_issues", gh.ler_sub_issues)
    return sb, gh


def _chaves(sb) -> list[tuple[str, int]]:
    return sorted((d["projeto"], d["github_issue_numero"]) for d in _demandas(sb))


class TestAConferenciaDeHoraEmHora:
    def test_cria_as_raizes_abertas_da_ana_que_faltam_e_nao_a_concluida(self, monkeypatch):
        parte = _issue_da_ana(13, corpo="## Pai\n\n#12\n\n## O que construir\n\nY.")
        concluida = _issue_da_ana(9, estado="closed")
        ferramenta = _issue_da_ana(14, labels=("area:os",))
        ja_tem = _demanda("DA", projeto=ANA, github_issue_numero=11)
        do_hospital = _demanda("DH", projeto=HOSPITAL, github_issue_numero=12)
        sb, gh = _conferir(
            monkeypatch,
            [_issue_da_ana(12), _issue_da_ana(11), parte, concluida, ferramenta],
            demandas=[ja_tem, do_hospital],
        )

        resultado = tecnologia_espelho.conferir_raizes_da_ana(sb)

        assert resultado == {"criadas": 1}
        assert _chaves(sb) == [(ANA, 11), (ANA, 12), (HOSPITAL, 12)]
        assert gh.listagens == [ANA]

    def test_nao_cria_a_raiz_aberta_por_quem_nao_e_do_time(self, monkeypatch):
        de_fora = _issue_da_ana(20, labels=(), author_association="NONE")
        sb, _ = _conferir(monkeypatch, [de_fora, _issue_da_ana(21, author_association="COLLABORATOR")])

        assert tecnologia_espelho.conferir_raizes_da_ana(sb) == {"criadas": 1}
        assert _chaves(sb) == [(ANA, 21)]

    def test_a_segunda_passada_nao_duplica(self, monkeypatch):
        sb, _ = _conferir(monkeypatch, [_issue_da_ana(12), _issue_da_ana(15)])

        tecnologia_espelho.conferir_raizes_da_ana(sb)
        segunda = tecnologia_espelho.conferir_raizes_da_ana(sb)

        assert segunda == {"criadas": 0}
        assert _chaves(sb) == [(ANA, 12), (ANA, 15)]

    def test_a_issue_apagada_nao_volta(self, monkeypatch):
        lapide = _demanda("DA", projeto=ANA, github_issue_numero=12, apagada_em="2026-11-10T10:00:00+00:00")
        sb, _ = _conferir(monkeypatch, [_issue_da_ana(12)], demandas=[lapide])

        assert tecnologia_espelho.conferir_raizes_da_ana(sb) == {"criadas": 0}
        assert len(_demandas(sb)) == 1

    def test_com_a_ana_desligada_nada_e_lido_e_nada_quebra(self, monkeypatch):
        monkeypatch.setattr(settings, "github_integracao_repo_ana", "")
        sb, gh = _conferir(monkeypatch, [_issue_da_ana(12)])

        assert tecnologia_espelho.conferir_raizes_da_ana(sb) == {"criadas": 0}
        assert gh.listagens == []
        assert _demandas(sb) == []


def test_a_leitura_das_abertas_pede_so_as_abertas_do_repositorio_do_projeto_sem_os_prs(monkeypatch):
    chamadas: list[tuple[str, str]] = []

    def _chamar(metodo, caminho, *, projeto, **_):
        chamadas.append((caminho, projeto))
        return [_issue_da_ana(12), _issue_da_ana(16, pull_request={"url": "x"})]

    monkeypatch.setattr(github_client, "_chamar", _chamar)

    assert [i["number"] for i in github_client.ler_issues_abertas(projeto=ANA)] == [12]
    assert chamadas == [("/issues?state=open&per_page=100&page=1", ANA)]


def test_o_job_de_hora_em_hora_confere_a_ana_antes_de_reler_as_demandas(monkeypatch):
    """A Demanda que a conferencia cria ganha a Etapa e o Responsavel na mesma
    passada: a releitura vem depois dela."""
    from app.cron import scheduler as scheduler_mod
    from app.services import tecnologia_sincronizacao

    ordem: list[str] = []
    monkeypatch.setattr(scheduler_mod, "_supabase", lambda: object())
    monkeypatch.setattr(tecnologia_espelho, "conferir_raizes_da_ana", lambda _sb: ordem.append("ana"))
    monkeypatch.setattr(tecnologia_sincronizacao, "reconciliar_vinculos", lambda _sb: ordem.append("vinculos"))
    monkeypatch.setattr(tecnologia_sincronizacao, "reconciliar_em_producao", lambda _sb: ordem.append("producao"))

    scheduler_mod.reconciliar_vinculos_tecnologia()

    assert ordem[:3] == ["ana", "vinculos", "producao"]


# ═══════════════════════════════════════════════════════════════════════════
# 3. O bloco para leigo da Ana
# ═══════════════════════════════════════════════════════════════════════════


class TestOBlocoParaQuemDecide:
    def test_o_bloco_para_quem_decide_vira_o_o_que_muda_e_a_parte_sem_bloco_fica_sem_texto(self):
        """ADR 0093, decisao 9. A parte sem bloco entra com texto nulo, e a tela
        diz "Descrição em preparação" no lugar dele (`SEM_O_QUE_MUDA`)."""
        from app.services.tecnologia_sincronizacao import mudanca_da_foto

        raiz = _issue_da_ana(
            12, corpo="## 🧭 Para quem decide\n\n**O que muda:** a Ana responde o preparo.\n\n---\n\n## Problema\n\nX."
        )
        com_bloco = _issue_da_ana(13, corpo="## Para quem decide\n\nO preparo do jejum.\n\n## Pai\n\n#12")
        sem_bloco = _issue_da_ana(14, corpo="## Pai\n\n#12\n\n## O que construir\n\nY.")

        mudanca = mudanca_da_foto(github_client.montar_foto(raiz, [com_bloco, sem_bloco]))

        assert mudanca["o_que_muda"] == "**O que muda:** a Ana responde o preparo."
        assert [p["o_que_muda"] for p in mudanca["partes"]] == ["O preparo do jejum.", None]


# ═══════════════════════════════════════════════════════════════════════════
# 4. O painel do card da Ana, pela rota que a tela le
# ═══════════════════════════════════════════════════════════════════════════


def _cards_do_painel() -> list[dict]:
    """O card da Ana e o card Vitta do Hospital, os dois Planejados e da
    melhoria: a Etapa e o tipo em que o Hospital mostra o Apagar."""
    comum = {"origem": "vitta", "tipo": "novo", "autor_id": PEDRO["id"], "etapa": ETAPA_PLANEJADA}
    return [
        _demanda_da_aba("d-ana", projeto=ANA, github_issue_numero=12, **comum),
        _demanda_da_aba("d-hospital", projeto=HOSPITAL, github_issue_numero=1700, **comum),
    ]


def _painel(monkeypatch, logado: dict = PEDRO):
    client, sb, gh = _cenario(monkeypatch, logado=logado, participantes=[PEDRO], demandas=_cards_do_painel())
    resposta = client.get(CHAT)
    assert resposta.status_code == 200, resposta.text
    return client, sb, gh, {d["id"]: d for d in resposta.json()}


class TestOPainelDoCardDaAna:
    def test_o_card_da_ana_nao_tem_apagar_nem_revisar_e_o_link_aponta_para_a_ana(self, monkeypatch):
        """O Desenvolvedor, que ve o Apagar no card Vitta do Hospital na mesma
        Etapa, nao o ve no da Ana (ADR 0093, decisao 5)."""
        _, _, _, cards = _painel(monkeypatch)

        ana, hospital = cards["d-ana"], cards["d-hospital"]
        assert (ana["pode_apagar"], ana["pode_revisar"]) == (False, False)
        assert ana["issue_url"] == f"https://github.com/{REPO_ANA}/issues/12"
        assert hospital["pode_apagar"] is True

    def test_o_apagar_do_card_da_ana_e_recusado_sem_tocar_no_github(self, monkeypatch):
        client, sb, _, _ = _painel(monkeypatch)
        fechadas: list = []
        monkeypatch.setattr(github_client, "fechar_como_nao_planejada", lambda *a, **kw: fechadas.append((a, kw)))

        resposta = client.delete(f"{CHAT}/d-ana")

        assert resposta.status_code == 409
        assert "acompanhar" in resposta.json()["detail"]
        assert not next(d for d in sb.tabelas["tecnologia_demandas"] if d["id"] == "d-ana").get("apagada_em")
        assert fechadas == []


# ═══════════════════════════════════════════════════════════════════════════
# 5. O Kit de conhecimento
# ═══════════════════════════════════════════════════════════════════════════


def test_o_produto_ana_no_kit_diz_que_os_pedidos_dela_aparecem_na_tecnologia_so_para_acompanhar():
    from app.services.conhecimento import CONHECIMENTO_DIR

    texto = (CONHECIMENTO_DIR / "ana.md").read_text(encoding="utf-8")
    secao = texto.split("## Os pedidos da Ana na aba Tecnologia", 1)[1].split("\n## ", 1)[0]

    assert "só para acompanhar" in secao
    assert "**Entregue**" in secao
    assert "não dá para apagar nem revisar" in secao.lower()
