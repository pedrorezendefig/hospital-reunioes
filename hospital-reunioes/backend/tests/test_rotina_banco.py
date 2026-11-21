"""A Rotina e a Verificação num Postgres de verdade (issue #1874, migration 177).

Usa o Postgres descartável de `test_pendencia_historico_banco.py`: aplica a 177
duas vezes (rodar de novo é inofensivo) e prova no banco que Não realizada sem
anotação e o encerramento sem anotação são recusados, e que um ciclo só se
marca uma vez. Também lê o SQL: nada de job, trigger ou função que crie
Verificação.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(__file__))

from test_pendencia_historico_banco import ESQUEMA_ANTERIOR, _bin_do_postgres, _Postgres  # noqa: E402

MIGRATION_177 = Path(__file__).resolve().parents[2] / "supabase" / "migrations" / "177_rotina_e_verificacao.sql"


@pytest.fixture(scope="module")
def banco():
    bindir = _bin_do_postgres()
    if bindir is None:
        if os.environ.get("CI"):
            pytest.fail("O CI precisa do initdb para provar a Rotina no banco.")
        pytest.skip("Sem initdb nesta máquina.")
    pg = _Postgres(bindir)
    pg.porta = "54177"
    pg.subir()
    try:
        pg.ok(ESQUEMA_ANTERIOR)
        pg.ok("INSERT INTO reunioes (id_reuniao, json_ata) VALUES ('R9', '{}');")
        pg.ok("INSERT INTO participantes (id, nome_completo) VALUES ('P2', 'Ana Lima');")
        # O GRANT padrão do Supabase: toda tabela nova nasce aberta ao anon e ao
        # authenticated. Sem ele o `permission denied` viria de graça e o teste
        # de acesso não provaria o REVOKE da 177.
        pg.ok("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO anon, authenticated;")
        sql = MIGRATION_177.read_text(encoding="utf-8")
        pg.ok(sql)
        pg.ok(sql)  # rodar duas vezes é inofensivo
        pg.ok(
            "INSERT INTO rotinas (id, id_reuniao, quadro_pos, descricao, responsavel_id, responsavel_nome, "
            "frequencia, comeca_em) VALUES ('00000000-0000-0000-0000-000000000001', 'R9', 0, "
            "'Reunir a equipe', 'P2', 'Ana Lima', 'SEMANAL', '2026-11-23');",
            papel="service_role",
        )
        yield pg
    finally:
        pg.descer()


ROTINA = "'00000000-0000-0000-0000-000000000001'"


def _marcar(banco, inicio: str, resultado: str, anotacao: str | None):
    valor = "NULL" if anotacao is None else f"'{anotacao}'"
    return banco.sql(
        "INSERT INTO rotina_verificacoes (rotina_id, ciclo_inicio, ciclo_fim, resultado, anotacao, marcada_por_nome) "
        f"VALUES ({ROTINA}, '{inicio}', '{inicio}'::date + 6, '{resultado}', {valor}, 'Ana Lima');",
        papel="service_role",
    )


@pytest.mark.parametrize("anotacao", [None, "", "   "])
def test_o_banco_recusa_nao_realizada_sem_anotacao(banco, anotacao):
    r = _marcar(banco, "2026-11-23", "NAO_REALIZADA", anotacao)

    assert r.returncode != 0
    assert "check" in r.stderr.lower()


def test_um_ciclo_so_se_marca_uma_vez(banco):
    assert _marcar(banco, "2026-11-30", "REALIZADA", None).returncode == 0

    segunda = _marcar(banco, "2026-11-30", "NAO_REALIZADA", "Mudei de ideia")

    assert segunda.returncode != 0
    assert "duplicate key" in segunda.stderr


def test_o_banco_recusa_encerrar_sem_anotacao(banco):
    r = banco.sql(
        f"UPDATE rotinas SET status = 'ENCERRADA', encerrada_em = '2026-12-10', anotacao_encerramento = ' ' "
        f"WHERE id = {ROTINA};",
        papel="service_role",
    )

    assert r.returncode != 0
    assert banco.ok(f"SELECT status FROM rotinas WHERE id = {ROTINA};") == "ATIVA"


@pytest.mark.parametrize("tabela", ["rotinas", "rotina_verificacoes"])
def test_quem_nao_e_o_backend_nao_le_a_rotina(banco, tabela):
    r = banco.sql(f"SELECT count(*) FROM {tabela};", papel="authenticated")

    assert r.returncode != 0
    assert "permission denied" in r.stderr


def test_nenhum_job_nem_trigger_cria_verificacao():
    sql = MIGRATION_177.read_text(encoding="utf-8").upper()
    assert "CREATE TRIGGER" not in sql
    assert "CREATE OR REPLACE FUNCTION" not in sql and "CREATE FUNCTION" not in sql
    assert "CRON" not in re.sub(r"--.*", "", sql)
    # Nem o agendador do backend: o ciclo vem da data.
    agendador = (Path(__file__).resolve().parents[1] / "app" / "cron" / "scheduler.py").read_text(encoding="utf-8")
    assert "rotina" not in agendador.lower()


MIGRATION_194 = MIGRATION_177.with_name("194_revisao_da_rotina.sql")


def test_a_194_grava_a_revisao_que_mantem_a_rotina_e_roda_duas_vezes(banco):
    """A revisão de 90 dias (issue #1944): Manter grava o dia na Rotina."""
    sql = MIGRATION_194.read_text(encoding="utf-8")
    banco.ok(sql)
    banco.ok(sql)  # rodar duas vezes é inofensivo

    banco.ok(
        f"UPDATE rotinas SET revisada_em = '2027-03-01', revisada_por_nome = 'Pedro Rezende' WHERE id = {ROTINA};",
        papel="service_role",
    )

    assert banco.ok(f"SELECT revisada_em FROM rotinas WHERE id = {ROTINA};") == "2027-03-01"
    assert banco.ok("SELECT count(*) FROM migracoes_aplicadas WHERE numero = 194;") == "1"
