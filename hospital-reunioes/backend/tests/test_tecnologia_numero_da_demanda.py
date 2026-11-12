"""O Numero da Demanda no banco (issue #1585, PRD #1584).

O SQL e colado a mao no Studio: e lido aqui como texto. A prova de que ele
roda (preenchimento pela ordem de criacao, sequence que nao anda para tras,
rodar duas vezes) foi feita num Postgres descartavel e esta no corpo do PR.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.services.conhecimento import CONHECIMENTO_DIR

MIGRATION = Path(__file__).resolve().parents[2] / "supabase" / "migrations" / "134_tecnologia_numero_da_demanda.sql"


@pytest.fixture
def sql() -> str:
    texto = MIGRATION.read_text(encoding="utf-8")
    # So o SQL, sem os comentarios: o cabecalho cita as mesmas palavras.
    return re.sub(r"--[^\n]*", "", texto)


def _posicao(sql: str, trecho: str) -> int:
    achado = re.search(trecho, sql)
    assert achado, trecho
    return achado.start()


class TestMigracao:
    def test_as_demandas_existentes_ganham_numero_pela_ordem_de_criacao_com_empate_pelo_id(self, sql):
        assert re.search(r"row_number\(\) OVER \(ORDER BY criado_em, id\)", sql)

    def test_a_sequence_continua_do_maior_numero_sem_andar_para_tras(self, sql):
        setval = sql[_posicao(sql, r"SELECT setval\(") :]
        assert "max(numero)" in setval.split(";", 1)[0]
        assert "last_value" in setval.split(";", 1)[0]

    def test_o_default_nasce_so_depois_do_preenchimento(self, sql):
        """Com o default antes, o ADD COLUMN numeraria as linhas na ordem
        fisica, e nao na de criacao."""
        default = _posicao(sql, r"SET DEFAULT nextval\('tecnologia_demandas_numero_seq'\)")

        assert _posicao(sql, r"UPDATE tecnologia_demandas") < default
        assert _posicao(sql, r"SELECT setval\(") < default

    def test_o_numero_e_obrigatorio_e_unico(self, sql):
        assert re.search(r"ALTER COLUMN numero SET NOT NULL", sql)
        assert re.search(r"ADD CONSTRAINT tecnologia_demandas_numero_key UNIQUE \(numero\)", sql)

    def test_a_migration_grava_o_recibo_134_depois_do_commit(self, sql):
        """A guarda do CI (tools/checar_recibo_da_migration.py) exige o recibo
        como ultima instrucao; depois do COMMIT ele so e gravado se a
        transacao entrou."""
        recibo = _posicao(sql, r"INSERT INTO migracoes_aplicadas \(numero\) VALUES \(134\) ON CONFLICT")

        assert _posicao(sql, r"BEGIN;") < _posicao(sql, r"COMMIT;") < recibo


class TestKit:
    def test_o_kit_diz_que_cada_demanda_tem_numero_e_onde_ele_aparece(self):
        """O Assistente fala com o diretor pela lingua do Kit: sem a regra
        escrita, ele nao saberia o que e "a Demanda 42"."""
        texto = (CONHECIMENTO_DIR / "tecnologia.md").read_text(encoding="utf-8")

        secao = texto.split("## O que é uma Demanda", 1)[1].split("\n## ", 1)[0]
        for trecho in ("Demanda 42", "no topo do documento", "na lista", "antes do Criar o card"):
            assert trecho in secao, trecho
