"""A migration 194 do Canal de Conduta num Postgres de verdade (issue #1841).

Sobe um Postgres descartável (o mesmo apoio da migration 169), monta o mínimo
de antes, aplica a migration duas vezes e prova no banco:

- a tabela tem RLS ligada e nenhuma policy;
- nenhuma versão se troca nem se apaga, nem pela `service_role`;
- o mesmo número de versão não entra duas vezes;
- o bucket do PDF é privado e só aceita PDF.

Sem `initdb` na máquina o teste pula; no CI ele falha, para não ficar verde
sobre nada.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from test_pendencia_historico_banco import _bin_do_postgres, _Postgres

MIGRATION = Path(__file__).resolve().parents[2] / "supabase" / "migrations" / "194_conduta_codigo_de_conduta.sql"

# O mínimo de antes da 194 (migrations 001 e 146, e o `storage` do Supabase).
ESQUEMA_ANTERIOR = """
CREATE ROLE anon NOLOGIN;
CREATE ROLE authenticated NOLOGIN;
CREATE ROLE service_role NOLOGIN NOSUPERUSER BYPASSRLS;

CREATE TABLE migracoes_aplicadas (numero INT PRIMARY KEY);
CREATE TABLE participantes (id VARCHAR(10) PRIMARY KEY, nome_completo TEXT);
INSERT INTO participantes (id, nome_completo) VALUES ('P1', 'Coordenadora de Teste');

CREATE SCHEMA storage;
CREATE TABLE storage.buckets (
  id TEXT PRIMARY KEY, name TEXT, public BOOLEAN, file_size_limit BIGINT, allowed_mime_types TEXT[]
);

GRANT ALL ON ALL TABLES IN SCHEMA public TO service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO service_role;
"""


@pytest.fixture(scope="module")
def banco():
    bindir = _bin_do_postgres()
    if bindir is None:
        if os.environ.get("CI"):
            pytest.fail("O CI precisa do initdb para provar as versões no banco.")
        pytest.skip("Sem initdb nesta máquina.")
    pg = _Postgres(bindir)
    pg.porta = "54194"
    pg.subir()
    try:
        pg.ok(ESQUEMA_ANTERIOR)
        migration = MIGRATION.read_text(encoding="utf-8")
        pg.ok(migration)
        pg.ok(migration)  # rodar duas vezes é inofensivo
        yield pg
    finally:
        pg.descer()


def _inserir(banco, versao: int, vigente_desde: str = "2026-12-01"):
    return banco.sql(
        "INSERT INTO conduta_codigo_versoes (versao, vigente_desde, storage_path, nome_arquivo, tamanho_bytes, "
        f"autor_id) VALUES ({versao}, '{vigente_desde}', 'v{versao}-x.pdf', 'codigo.pdf', 1024, 'P1');",
        papel="service_role",
    )


@pytest.fixture(scope="module")
def com_uma_versao(banco):
    r = _inserir(banco, 1)
    assert r.returncode == 0, r.stderr
    return banco


def test_a_tabela_tem_rls_ligada_e_nenhuma_policy(banco):
    assert banco.ok("SELECT relrowsecurity FROM pg_class WHERE relname = 'conduta_codigo_versoes';") == "t"
    assert banco.ok("SELECT count(*) FROM pg_policies WHERE tablename = 'conduta_codigo_versoes';") == "0"


@pytest.mark.parametrize("papel", ["service_role", None])
def test_update_numa_versao_falha_no_banco(com_uma_versao, papel):
    r = com_uma_versao.sql(
        "UPDATE conduta_codigo_versoes SET vigente_desde = '2020-01-01' WHERE versao = 1;", papel=papel
    )

    assert r.returncode != 0
    assert "imutáveis" in r.stderr
    assert com_uma_versao.ok("SELECT vigente_desde FROM conduta_codigo_versoes WHERE versao = 1;") == "2026-12-01"


@pytest.mark.parametrize("papel", ["service_role", None])
def test_delete_numa_versao_falha_no_banco(com_uma_versao, papel):
    r = com_uma_versao.sql("DELETE FROM conduta_codigo_versoes WHERE versao = 1;", papel=papel)

    assert r.returncode != 0
    assert "imutáveis" in r.stderr
    assert com_uma_versao.ok("SELECT count(*) FROM conduta_codigo_versoes WHERE versao = 1;") == "1"


def test_truncate_falha_no_banco(com_uma_versao):
    r = com_uma_versao.sql("TRUNCATE conduta_codigo_versoes;")

    assert r.returncode != 0
    assert "imutáveis" in r.stderr


def test_o_mesmo_numero_de_versao_nao_entra_duas_vezes(com_uma_versao):
    r = _inserir(com_uma_versao, 1, "2027-01-01")

    assert r.returncode != 0
    assert "conduta_codigo_versoes_versao_key" in r.stderr


def test_o_bucket_do_pdf_e_privado_e_so_aceita_pdf(banco):
    linha = banco.ok(
        "SELECT public, file_size_limit, allowed_mime_types FROM storage.buckets WHERE id = 'conduta-codigo';"
    )

    assert linha == "f|20971520|{application/pdf}"


def test_a_migration_nao_grava_nenhuma_versao(banco):
    """Quem publica é a coordenação, pela tela."""
    assert "INSERT INTO conduta_codigo_versoes" not in MIGRATION.read_text(encoding="utf-8")


def test_o_recibo_e_o_194(banco):
    assert banco.ok("SELECT max(numero) FROM migracoes_aplicadas;") == "194"
