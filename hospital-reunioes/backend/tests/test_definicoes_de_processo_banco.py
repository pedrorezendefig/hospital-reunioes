"""As Definições de processo num Postgres de verdade (issue #1875, migration 178).

Usa o Postgres descartável de `test_pendencia_historico_banco.py`: aplica a 178
duas vezes (rodar de novo é inofensivo) e prova no banco que tirar da lista
sem anotação é recusado, que a mesma linha da Ata não entra duas vezes e que
só o backend lê a tabela.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(__file__))

from test_pendencia_historico_banco import ESQUEMA_ANTERIOR, _bin_do_postgres, _Postgres  # noqa: E402

MIGRATION_178 = (
    Path(__file__).resolve().parents[2] / "supabase" / "migrations" / "178_definicoes_de_processo_do_setor.sql"
)
ITEM = "'00000000-0000-0000-0000-000000000001'"


@pytest.fixture(scope="module")
def banco():
    bindir = _bin_do_postgres()
    if bindir is None:
        if os.environ.get("CI"):
            pytest.fail("O CI precisa do initdb para provar as Definições de processo no banco.")
        pytest.skip("Sem initdb nesta máquina.")
    pg = _Postgres(bindir)
    pg.porta = "54176"
    pg.subir()
    try:
        pg.ok(ESQUEMA_ANTERIOR)
        pg.ok("INSERT INTO reunioes (id_reuniao, json_ata) VALUES ('R9', '{}');")
        # O GRANT padrão do Supabase: toda tabela nova nasce aberta ao anon e ao
        # authenticated. Sem ele o `permission denied` viria de graça e o teste
        # de acesso não provaria o REVOKE da 178.
        pg.ok("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO anon, authenticated;")
        sql = MIGRATION_178.read_text(encoding="utf-8")
        pg.ok(sql)
        pg.ok(sql)  # rodar duas vezes é inofensivo
        pg.ok(
            f"INSERT INTO definicoes_processo (id, id_reuniao, quadro_pos, trecho) "
            f"VALUES ({ITEM}, 'R9', 1, 'Toda alta passa pelo checklist');",
            papel="service_role",
        )
        yield pg
    finally:
        pg.descer()


@pytest.mark.parametrize("anotacao", ["NULL", "''", "'   '"])
def test_o_banco_recusa_tirar_da_lista_sem_anotacao(banco, anotacao):
    r = banco.sql(
        f"UPDATE definicoes_processo SET status = 'RETIRADA', retirada_em = now(), "
        f"anotacao_retirada = {anotacao} WHERE id = {ITEM};",
        papel="service_role",
    )

    assert r.returncode != 0
    assert "check" in r.stderr.lower()
    assert banco.ok(f"SELECT status FROM definicoes_processo WHERE id = {ITEM};") == "ATIVA"


def test_a_mesma_linha_da_ata_nao_entra_duas_vezes(banco):
    r = banco.sql(
        "INSERT INTO definicoes_processo (id_reuniao, quadro_pos, trecho) VALUES ('R9', 1, 'De novo');",
        papel="service_role",
    )

    assert r.returncode != 0
    assert "duplicate key" in r.stderr


def test_quem_nao_e_o_backend_nao_le_a_lista(banco):
    r = banco.sql("SELECT count(*) FROM definicoes_processo;", papel="authenticated")

    assert r.returncode != 0
    assert "permission denied" in r.stderr
