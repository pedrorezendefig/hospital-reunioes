"""Apagar a Demanda, e a migration da ADR 0084 (issue #1549, PRD #1548).

Um pedido que não vale mais sai da lista da Tecnologia. Só se apaga até
Planejada: a conversa Registrada, quem apaga é o autor; o card criado (Em
análise ou Planejada), só o Desenvolvedor. De Em desenvolvimento em diante, o
app recusa.

No GitHub a issue-raiz e as partes abertas fecham como "not_planned", com um
comentário de motivo, e a issue nunca é apagada. No app a Demanda vira lápide:
a linha fica, com `apagada_em` e `apagada_por`, para o webhook reconhecer a
issue; a conversa, o planejamento e a Conversa da Demanda saem, e os anexos
saem do bucket.

Tudo pela ROTA, no molde de `test_tecnologia_conversa_da_demanda`.
"""

from __future__ import annotations

import re
from pathlib import Path

MIGRATIONS = Path(__file__).resolve().parents[2] / "supabase" / "migrations"
MIGRATION_130 = MIGRATIONS / "130_tecnologia_adr_0084.sql"


# ═══════════════════════════════════════════════════════════════════════════
# 1. A migration 130
# ═══════════════════════════════════════════════════════════════════════════


def _sql() -> str:
    return MIGRATION_130.read_text(encoding="utf-8")


def _sem_comentarios() -> str:
    return "\n".join(linha for linha in _sql().splitlines() if not linha.lstrip().startswith("--"))


class TestMigration:
    def test_cria_as_colunas_da_demanda_e_do_planejamento_da_adr_0084(self):
        sql = _sem_comentarios()

        for tabela, colunas in (
            (
                "tecnologia_demandas",
                ("origem", "apagada_em", "apagada_por", "em_producao_em", "demonstracao_url", "demonstracao_em"),
            ),
            ("tecnologia_planejamentos", ("documento", "revisao_iniciada_em", "revisao_por", "revisao_versao_base")),
        ):
            for coluna in colunas:
                assert re.search(
                    rf"ALTER TABLE {tabela} ADD COLUMN IF NOT EXISTS {coluna} ", sql
                ), f"{tabela}.{coluna}"

    def test_a_origem_nasce_diretor_e_so_aceita_diretor_ou_vitta(self):
        sql = _sem_comentarios()

        assert "ADD COLUMN IF NOT EXISTS origem TEXT NOT NULL DEFAULT 'diretor';" in sql
        check = sql[sql.index("ADD CONSTRAINT tecnologia_demandas_origem_check") :].split(";", 1)[0]
        assert "origem IN ('diretor', 'vitta')" in check

    def test_o_turno_do_planejamento_diz_quem_respondeu(self):
        """Os turnos moram no JSONB `mensagens`: o contrato do campo novo fica
        no comentário da coluna, como a migration 127 fez com `documentos`."""
        sql = _sql()
        comentario = sql[sql.index("COMMENT ON COLUMN tecnologia_planejamentos.mensagens IS") :].split("';", 1)[0]

        assert "respondido_por" in comentario

    def test_nenhuma_tabela_nova_nem_policy(self):
        sql = _sem_comentarios().upper()

        assert "CREATE TABLE" not in sql
        assert "CREATE POLICY" not in sql

    def test_termina_com_o_recibo_do_proprio_numero(self):
        assert _sem_comentarios().strip().endswith(
            "INSERT INTO migracoes_aplicadas (numero) VALUES (130) ON CONFLICT (numero) DO NOTHING;"
        )
