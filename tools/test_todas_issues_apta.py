"""Quem entra na Onda da /todas-issues: no Projeto com `designado_tira_da_fila`, o assignee é o
dono do card, e a Onda de cada um pega só os cards dele (grill de 07/11/2026, P3)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / ".claude" / "skills" / "todas-issues" / "scripts"))
import todas_issues  # noqa: E402


def card(*donos: str, labels=("ready-for-agent",)) -> dict:
    return {"numero": 1, "labels": list(labels), "fase": "fila", "designada": bool(donos), "responsaveis": list(donos)}


def test_card_de_quem_roda_entra_na_onda():
    assert todas_issues.apta(card("pedrorezendefig"), True, "pedrorezendefig")


def test_card_de_outro_dono_fica_fora_da_onda():
    assert not todas_issues.apta(card("pedroribbe"), True, "pedrorezendefig")


def test_card_sem_dono_fica_fora_da_onda_onde_o_assignee_e_o_dono():
    assert not todas_issues.apta(card(), True, "pedrorezendefig")


def test_projeto_sem_a_regra_ignora_o_dono():
    assert todas_issues.apta(card("pedroribbe"), False, "pedrorezendefig")
    assert todas_issues.apta(card(), False, "pedrorezendefig")


def test_card_em_andamento_fica_fora_mesmo_sendo_de_quem_roda():
    em_andamento = card("pedrorezendefig", labels=("ready-for-agent", "in-progress"))
    assert not todas_issues.apta(em_andamento, True, "pedrorezendefig")
