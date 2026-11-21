"""A Contestação no Histórico da Pendência, num Postgres de verdade (issue #1870).

Contestar, ajustar e recusar gravam evento no histórico pela mesma função das
outras ações (`registrar_acao_da_pendencia`, migration 169). O CHECK de
`pendencia_historico.comando` só aceitava os comandos de antes; a migration
187 inclui os três, sem tirar nenhum.

Usa o Postgres descartável de `test_pendencia_historico_banco.py`: aplica a
169, a 171 e a 187 (esta duas vezes, para provar que rodar de novo é
inofensivo).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(__file__))

from test_pendencia_historico_banco import (  # noqa: E402
    ESQUEMA_ANTERIOR,
    MIGRATION,
    _bin_do_postgres,
    _Postgres,
)

PASTA = Path(__file__).resolve().parents[2] / "supabase" / "migrations"
MIGRATION_171 = PASTA / "171_nascimento_da_pendencia.sql"
MIGRATION_187 = PASTA / "187_contestacao_do_item_da_ata.sql"


@pytest.fixture(scope="module")
def banco():
    bindir = _bin_do_postgres()
    if bindir is None:
        if os.environ.get("CI"):
            pytest.fail("O CI precisa do initdb para provar a migration no banco.")
        pytest.skip("Sem initdb nesta máquina.")
    pg = _Postgres(bindir)
    pg.porta = "54174"
    pg.subir()
    try:
        pg.ok(ESQUEMA_ANTERIOR)
        # As colunas do responsável que a produção tem e o esquema mínimo não.
        pg.ok(
            "ALTER TABLE pendencias ADD COLUMN responsavel_nome TEXT, ADD COLUMN cargo TEXT;"
            "INSERT INTO participantes (id, nome_completo) VALUES ('P_ERR', 'Edu Errado'), ('P_OK', 'Carla Certa');"
        )
        pg.ok("INSERT INTO reunioes (id_reuniao, json_ata) VALUES ('R9', '{}');")
        pg.ok(MIGRATION.read_text(encoding="utf-8"))
        pg.ok(MIGRATION_171.read_text(encoding="utf-8"))
        contestacao = MIGRATION_187.read_text(encoding="utf-8")
        pg.ok(contestacao)
        pg.ok(contestacao)  # rodar duas vezes é inofensivo
        yield pg
    finally:
        pg.descer()


def _acao(banco, id_acao: str, comando: str, anotacao: str, prazo_novo: str = "NULL"):
    return banco.sql(
        f"SELECT registrar_acao_da_pendencia('{id_acao}', '{comando}', '{anotacao}', 'P01', 'Ana', "
        f"'PENDENTE', 'PENDENTE', {prazo_novo}, NULL, false);",
        papel="service_role",
    )


def test_contestar_ajustar_e_recusar_gravam_evento_no_historico(banco):
    banco.ok(
        "INSERT INTO pendencias (id_acao, id_reuniao, descricao_acao, prazo, status) "
        "VALUES ('A301', 'R9', 'Comprar luvas', '2026-12-01', 'PENDENTE');"
    )
    for comando, anotacao, prazo_novo in (
        ("contestar", "o prazo era março", "NULL"),
        ("ajustar", "combinado em março", "'2027-03-31'"),
        ("contestar", "o responsável é outro", "NULL"),
        ("recusar", "o responsável é esse mesmo", "NULL"),
    ):
        r = _acao(banco, "A301", comando, anotacao, prazo_novo)
        assert r.returncode == 0, r.stderr

    eventos = banco.ok(
        "SELECT comando, anotacao, prazo_depois FROM pendencia_historico WHERE id_acao = 'A301' ORDER BY id;"
    ).splitlines()
    assert eventos == [
        "nascimento|Nasceu do quadro da Ata da reuniao R9.|2026-12-01",
        "contestar|o prazo era março|2026-12-01",
        "ajustar|combinado em março|2027-03-31",
        "contestar|o responsável é outro|2027-03-31",
        "recusar|o responsável é esse mesmo|2027-03-31",
    ]
    assert banco.ok("SELECT status, prazo FROM pendencias WHERE id_acao = 'A301';") == "PENDENTE|2027-03-31"


def test_o_check_segue_recusando_comando_que_nao_existe(banco):
    banco.ok(
        "INSERT INTO pendencias (id_acao, id_reuniao, descricao_acao, prazo, status) "
        "VALUES ('A302', 'R9', 'Pintar sala', '2026-12-01', 'PENDENTE');"
    )
    r = _acao(banco, "A302", "apagar", "sumir com tudo")
    assert r.returncode != 0
    assert "pendencia_historico_comando_check" in r.stderr


def test_ajustar_e_recusar_tambem_exigem_anotacao_no_banco(banco):
    banco.ok(
        "INSERT INTO pendencias (id_acao, id_reuniao, descricao_acao, prazo, status) "
        "VALUES ('A303', 'R9', 'Trocar lâmpada', '2026-12-01', 'PENDENTE');"
    )
    for comando in ("ajustar", "recusar"):
        r = _acao(banco, "A303", comando, "   ")
        assert r.returncode != 0, comando
    assert banco.ok("SELECT count(*) FROM pendencia_historico WHERE id_acao = 'A303';") == "1"


def test_o_ajuste_troca_o_responsavel_na_pendencia_e_o_historico_guarda_a_troca(banco):
    banco.ok(
        "INSERT INTO pendencias (id_acao, id_reuniao, descricao_acao, prazo, status, "
        "responsavel_id, responsavel_nome, cargo) "
        "VALUES ('A304', 'R9', 'Comprar luvas', '2026-12-01', 'PENDENTE', 'P_ERR', 'Edu Errado', 'Copeiro');"
    )
    assert _acao(banco, "A304", "contestar", "a luva é com a Carla").returncode == 0
    r = banco.sql(
        "SELECT registrar_acao_da_pendencia('A304', 'ajustar', 'era a Carla', 'P01', 'Ana', "
        "'PENDENTE', 'PENDENTE', NULL, NULL, false, 'P_OK', 'Carla Certa', 'Enfermeira');",
        papel="service_role",
    )
    assert r.returncode == 0, r.stderr

    assert (
        banco.ok("SELECT responsavel_id, responsavel_nome, cargo, prazo FROM pendencias WHERE id_acao = 'A304';")
        == "P_OK|Carla Certa|Enfermeira|2026-12-01"
    )
    assert banco.ok(
        "SELECT comando, responsavel_antes, responsavel_depois FROM pendencia_historico "
        "WHERE id_acao = 'A304' ORDER BY id;"
    ).splitlines() == ["nascimento||", "contestar||", "ajustar|Edu Errado|Carla Certa"]
