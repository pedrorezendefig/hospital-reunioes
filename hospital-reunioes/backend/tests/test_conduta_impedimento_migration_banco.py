"""A migration 191 do Canal de Conduta num Postgres de verdade (issue #1828).

Sobe um Postgres descartável, aplica a 175 e a 191 (a 191 duas vezes) sobre o
mínimo de antes e prova no banco:

- toda tabela nova tem RLS ligada e nenhuma policy;
- o motivo do impedimento e o papel do suplente convocado só aceitam o que a
  regra conhece, e o papel só vale na convocação;
- uma contestação aberta por pessoa em cada caso, e ninguém contesta a si
  mesmo;
- o recibo é o 191.

Sem `initdb` na máquina o teste pula; no CI ele falha, para não ficar verde
sobre nada.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest
from test_conduta_migration_banco import ESQUEMA_ANTERIOR
from test_conduta_migration_banco import MIGRATION as MIGRATION_175
from test_pendencia_historico_banco import _bin_do_postgres, _Postgres

MIGRATION = Path(__file__).resolve().parents[2] / "supabase" / "migrations" / "191_conduta_impedimento_e_citado.sql"

TABELAS_NOVAS = ("conduta_contestacoes_de_participacao", "conduta_participacao_votos")


@pytest.fixture(scope="module")
def banco():
    bindir = _bin_do_postgres()
    if bindir is None:
        if os.environ.get("CI"):
            pytest.fail("O CI precisa do initdb para provar o impedimento no banco.")
        pytest.skip("Sem initdb nesta máquina.")
    pg = _Postgres(bindir)
    pg.porta = "54191"
    pg.subir()
    try:
        pg.ok(ESQUEMA_ANTERIOR)
        pg.ok("INSERT INTO participantes (id, nome_completo) VALUES ('P2', 'Outra Pessoa'), ('P3', 'Mais Uma');")
        pg.ok(MIGRATION_175.read_text(encoding="utf-8"))
        migration = MIGRATION.read_text(encoding="utf-8")
        pg.ok(migration)
        pg.ok(migration)  # rodar duas vezes é inofensivo
        yield pg
    finally:
        pg.descer()


def _caso(banco) -> str:
    protocolo = f"CC-{os.urandom(2).hex().upper()}-{os.urandom(2).hex().upper()}"
    return banco.ok(
        "INSERT INTO conduta_casos (protocolo, codigo_hash, relato_cifrado) "
        f"VALUES ('{protocolo}', 'hash', 'v1:AAAA') RETURNING id;",
        papel="service_role",
    ).splitlines()[-1]


def _atribuir(banco, caso: str, motivo: str, *, substitui_papel: str = "NULL", impedimento: str = "NULL"):
    return banco.sql(
        "INSERT INTO conduta_atribuicoes (caso_id, participante_id, motivo, substitui_papel, impedimento_motivo) "
        f"VALUES ('{caso}', 'P1', '{motivo}', {substitui_papel}, {impedimento});",
        papel="service_role",
    )


def _contestar(banco, caso: str, contestado: str = "P2", autor: str = "P1"):
    return banco.sql(
        "INSERT INTO conduta_contestacoes_de_participacao (caso_id, contestado_id, autor_id, motivo) "
        f"VALUES ('{caso}', '{contestado}', '{autor}', 'interesse') RETURNING id;",
        papel="service_role",
    )


def test_a_migration_cria_as_duas_tabelas():
    sql = re.sub(r"--[^\n]*", "", MIGRATION.read_text(encoding="utf-8"))
    assert sorted(re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)\s*\(", sql)) == sorted(TABELAS_NOVAS)


@pytest.mark.parametrize("tabela", TABELAS_NOVAS)
def test_toda_tabela_nova_tem_rls_ligada(banco, tabela):
    assert banco.ok(f"SELECT relrowsecurity FROM pg_class WHERE relname = '{tabela}';") == "t"


def test_nenhuma_policy_nas_tabelas_do_modulo(banco):
    assert banco.ok("SELECT count(*) FROM pg_policies WHERE tablename LIKE 'conduta_%';") == "0"


def test_o_motivo_do_impedimento_e_um_dos_conhecidos(banco):
    caso = _caso(banco)
    assert _atribuir(banco, caso, "membro_do_comite", impedimento="'citado'").returncode == 0
    assert _atribuir(banco, caso, "membro_do_comite", impedimento="'antipatia'").returncode != 0


def test_o_papel_do_substituido_so_vale_na_convocacao_do_suplente(banco):
    caso = _caso(banco)
    assert _atribuir(banco, caso, "suplente_convocado", substitui_papel="'coordenacao'").returncode == 0
    assert _atribuir(banco, caso, "apurador", substitui_papel="'coordenacao'").returncode != 0
    assert _atribuir(banco, caso, "suplente_convocado", substitui_papel="'presidencia'").returncode != 0


def test_uma_contestacao_aberta_por_pessoa_em_cada_caso(banco):
    caso = _caso(banco)
    primeira = _contestar(banco, caso)
    assert primeira.returncode == 0
    assert _contestar(banco, caso, autor="P3").returncode != 0

    banco.ok(
        "UPDATE conduta_contestacoes_de_participacao SET resultado = 'rejeitada', decidida_em = now() "
        f"WHERE caso_id = '{caso}';",
        papel="service_role",
    )
    assert _contestar(banco, caso, autor="P3").returncode == 0


def test_a_busca_das_contestacoes_do_caso_tem_indice(banco):
    # A tela do caso lê as contestações só por caso_id; o índice único parcial
    # (caso_id, contestado_id) WHERE decidida_em IS NULL não serve a essa busca.
    definicoes = banco.ok(
        "SELECT indexdef FROM pg_indexes WHERE tablename = 'conduta_contestacoes_de_participacao';"
    ).splitlines()
    assert any(d.rstrip().endswith("(caso_id)") for d in definicoes), definicoes


def test_ninguem_contesta_a_si_mesmo(banco):
    assert _contestar(banco, _caso(banco), contestado="P1", autor="P1").returncode != 0


def test_o_recibo_e_o_191(banco):
    assert banco.ok("SELECT max(numero) FROM migracoes_aplicadas;") == "191"
