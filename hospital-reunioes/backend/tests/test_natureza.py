"""Testes da inferência da Natureza pelo nome do Setor (issue #173, ADR 0018).

A Natureza (assistencial/administrativa/apoio) é sugerida a partir do nome, como
a sigla. A heurística é determinística e vive em app.services.natureza, fonte
viva espelhada pelo backfill SQL da migration 054. Nomes sem sinal claro caem no
default explícito 'assistencial' (é um hospital).
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.natureza import inferir_natureza  # noqa: E402

# Tabela nome do Setor -> Natureza esperada. Cobre as três Naturezas, o casamento
# insensível a acento/maiúsculas, os acrônimos curtos (que não podem bater por
# dentro de outra palavra) e o caso desconhecido -> default.
CASOS: list[tuple[str, str]] = [
    # ── assistencial (default do hospital; reconhecido por ausência de sinal) ──
    ("UTI", "assistencial"),
    ("Centro Cirúrgico", "assistencial"),
    ("Unidade de Terapia Intensiva", "assistencial"),
    ("Enfermagem", "assistencial"),
    ("Ambulatório", "assistencial"),
    ("Farmácia", "assistencial"),
    ("Laboratório de Análises Clínicas", "assistencial"),
    # ── administrativa ──
    ("Faturamento", "administrativa"),
    ("Departamento Financeiro", "administrativa"),
    ("Recursos Humanos", "administrativa"),
    ("RH", "administrativa"),
    ("Departamento de Pessoal", "administrativa"),
    ("Compras", "administrativa"),
    ("Recepção", "administrativa"),
    ("Contabilidade", "administrativa"),
    # ── apoio ──
    ("Higienização", "apoio"),
    ("Serviço de Limpeza", "apoio"),
    ("Manutenção Predial", "apoio"),
    ("Almoxarifado", "apoio"),
    ("CME", "apoio"),
    ("Central de Material Esterilizado", "apoio"),
    ("Lavanderia", "apoio"),
    ("Nutrição e Dietética", "apoio"),
    ("Tecnologia da Informação", "apoio"),
    ("TI", "apoio"),
    ("Engenharia Clínica", "apoio"),  # apoio vence o "clínica" (sem lista assistencial)
    # ── desconhecido -> default explícito ──
    ("Setor Novo Qualquer", "assistencial"),
    ("Diretoria", "assistencial"),
    ("", "assistencial"),
]


@pytest.mark.parametrize(("nome", "esperado"), CASOS)
def test_inferir_natureza(nome: str, esperado: str):
    assert inferir_natureza(nome) == esperado


def test_acronimo_curto_nao_bate_por_substring():
    # "ti" (apoio) não pode casar dentro de "administrativo"/"assistencial";
    # a fronteira de palavra é o que separa o acrônimo do substring acidental.
    assert inferir_natureza("Setor Administrativo") == "administrativa"
    assert inferir_natureza("Assistência ao Paciente") == "assistencial"


def test_precedencia_administrativa_vence_apoio():
    # Sinais de duas Naturezas no mesmo nome (raro): a precedência é fixa e
    # determinística (administrativa > apoio), e o campo continua editável.
    assert inferir_natureza("Compras e Almoxarifado") == "administrativa"


def test_retorno_sempre_natureza_valida():
    validas = {"assistencial", "administrativa", "apoio"}
    for nome in ("qualquer coisa", "UTI", "Faturamento", "Lavanderia"):
        assert inferir_natureza(nome) in validas
