"""Coletor das issues: autor, sem teto de 200 e bloqueios declarados no corpo.

Vieram do test_filtro_responsavel.py e do test_plano.py quando a aba Issues
nova (#942) aposentou o filtro antigo e o módulo do Plano; o coletor segue
entregando o mesmo shape. `gh` mockado por `_run`, sem rede.
"""

import json
import sys
from pathlib import Path

DASH = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DASH))

import collect


def test_coletor_traz_o_autor_da_issue(monkeypatch):
    item = {
        "number": 1,
        "title": "t",
        "state": "OPEN",
        "labels": [],
        "assignees": [],
        "author": {"login": "fulano"},
        "body": "",
    }
    monkeypatch.setattr(collect, "_run", lambda cmd, cwd, timeout=None: json.dumps([item]))
    assert "author" in collect.ISSUE_FIELDS.split(",")
    assert collect._gh_issues(DASH)[0]["author"] == "fulano"


def test_coletor_traz_issues_e_prs_sem_o_teto_de_200(monkeypatch):
    chamadas = []

    def fake_run(cmd, cwd, timeout=None):
        chamadas.append(cmd)
        return "[]"

    monkeypatch.setattr(collect, "_run", fake_run)
    collect._gh_issues(DASH)
    collect._gh_prs(DASH)
    limites = [int(c[c.index("--limit") + 1]) for c in chamadas]
    assert len(limites) == 2
    assert all(n >= 10000 for n in limites), limites


def test_bloqueios_do_corpo_le_secao_com_bullets():
    body = (
        "## O que construir\nAlgo que cita #99 sem ser bloqueio.\n\n"
        "## Bloqueada por\n\n- #85 (revisão e validação)\n- #86 (PDF institucional)\n\n"
        "## Outra seção\n- #77 também não é bloqueio.\n"
    )
    assert collect.bloqueios_do_corpo(body) == [85, 86]


def test_bloqueios_do_corpo_le_formato_inline_e_nenhuma():
    assert collect.bloqueios_do_corpo("Bloqueada por: #81 e #82.") == [81, 82]
    assert collect.bloqueios_do_corpo("## Bloqueada por\n\nNenhuma, pode começar já.\n") == []
    assert collect.bloqueios_do_corpo("") == []


def test_bloqueios_do_corpo_aceita_header_com_dois_pontos():
    assert collect.bloqueios_do_corpo("## Bloqueada por:\n\n- #85\n\n## Outra\n") == [85]


def test_corpo_da_issue_vira_blocked_by_na_coleta(monkeypatch):
    item = {"number": 7, "title": "t", "state": "OPEN", "labels": [], "assignees": [], "body": "Bloqueada por: #5"}
    monkeypatch.setattr(collect, "_run", lambda cmd, cwd, timeout=None: json.dumps([item]))
    assert collect._gh_issues(DASH)[0]["blocked_by"] == [5]


def test_coletor_nao_calcula_mais_o_claimed_at_do_plano():
    # A chave "plano" fora do /api/data é conferida no payload, em
    # test_coletor_fases.py::test_coleta_entrega_as_fases_no_payload.
    fonte = (DASH / "collect.py").read_text(encoding="utf-8")
    assert "claimed_at" not in fonte  # base do lead time do Plano, que saiu


def test_coletor_marca_a_issue_que_nasceu_de_uma_demanda(monkeypatch):
    """O marcador do Vinculo (ADR 0054) no corpo vira `demanda: True`; sem ele, False."""
    base = {"number": 1, "title": "t", "state": "OPEN", "labels": [], "assignees": [], "author": None}
    itens = [
        {**base, "number": 1, "body": 'Para o diretor\n\n<!-- demanda-vitta id="abc-123" -->'},
        {**base, "number": 2, "body": "issue comum"},
    ]
    monkeypatch.setattr(collect, "_run", lambda cmd, cwd, timeout=None: json.dumps(itens))
    por_n = {i["number"]: i for i in collect._gh_issues(DASH)}
    assert por_n[1]["demanda"] is True
    assert por_n[2]["demanda"] is False
