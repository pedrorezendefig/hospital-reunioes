"""A migration 186 do Canal de Conduta num Postgres de verdade (issue #1826).

Sobe um Postgres descartável (o mesmo apoio da migration 169), monta o mínimo
de antes, aplica a migration duas vezes e prova no banco:

- a tabela tem RLS ligada e nenhuma policy;
- nenhuma versão se troca nem se apaga, nem pela `service_role`;
- a mesma versão de um item não entra duas vezes;
- não existe item de e-mail do DP.

Sem `initdb` na máquina o teste pula; no CI ele falha, para não ficar verde
sobre nada.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pytest
from test_pendencia_historico_banco import _bin_do_postgres, _Postgres

MIGRATION = Path(__file__).resolve().parents[2] / "supabase" / "migrations" / "186_conduta_configuracoes_com_versao.sql"

# O mínimo de antes da 186 (migrations 001 e 146).
ESQUEMA_ANTERIOR = """
CREATE ROLE anon NOLOGIN;
CREATE ROLE authenticated NOLOGIN;
CREATE ROLE service_role NOLOGIN NOSUPERUSER BYPASSRLS;

CREATE TABLE migracoes_aplicadas (numero INT PRIMARY KEY);
CREATE TABLE participantes (id VARCHAR(10) PRIMARY KEY, nome_completo TEXT);
INSERT INTO participantes (id, nome_completo) VALUES ('P1', 'Coordenadora de Teste');

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
    pg.porta = "54180"
    pg.subir()
    try:
        pg.ok(ESQUEMA_ANTERIOR)
        migration = MIGRATION.read_text(encoding="utf-8")
        pg.ok(migration)
        pg.ok(migration)  # rodar duas vezes é inofensivo
        yield pg
    finally:
        pg.descer()


def _inserir(banco, chave: str, versao: int, texto: str = "Ramal 2040"):
    return banco.sql(
        "INSERT INTO conduta_configuracoes (chave, versao, texto, autor_id) "
        f"VALUES ('{chave}', {versao}, '{texto}', 'P1');",
        papel="service_role",
    )


@pytest.fixture(scope="module")
def com_uma_versao(banco):
    r = _inserir(banco, "contato_dp", 1)
    assert r.returncode == 0, r.stderr
    return banco


def test_a_tabela_tem_rls_ligada_e_nenhuma_policy(banco):
    assert banco.ok("SELECT relrowsecurity FROM pg_class WHERE relname = 'conduta_configuracoes';") == "t"
    assert banco.ok("SELECT count(*) FROM pg_policies WHERE tablename = 'conduta_configuracoes';") == "0"


@pytest.mark.parametrize("papel", ["service_role", None])
def test_update_numa_versao_falha_no_banco(com_uma_versao, papel):
    r = com_uma_versao.sql("UPDATE conduta_configuracoes SET texto = 'outro' WHERE chave = 'contato_dp';", papel=papel)

    assert r.returncode != 0
    assert "imutáveis" in r.stderr
    assert com_uma_versao.ok("SELECT texto FROM conduta_configuracoes WHERE chave = 'contato_dp';") == "Ramal 2040"


@pytest.mark.parametrize("papel", ["service_role", None])
def test_delete_numa_versao_falha_no_banco(com_uma_versao, papel):
    r = com_uma_versao.sql("DELETE FROM conduta_configuracoes WHERE chave = 'contato_dp';", papel=papel)

    assert r.returncode != 0
    assert "imutáveis" in r.stderr
    assert com_uma_versao.ok("SELECT count(*) FROM conduta_configuracoes WHERE chave = 'contato_dp';") == "1"


def test_truncate_falha_no_banco(com_uma_versao):
    r = com_uma_versao.sql("TRUNCATE conduta_configuracoes;")

    assert r.returncode != 0
    assert "imutáveis" in r.stderr


def test_a_mesma_versao_de_um_item_nao_entra_duas_vezes(com_uma_versao):
    r = _inserir(com_uma_versao, "contato_dp", 1, "Ramal 3000")

    assert r.returncode != 0
    assert "conduta_configuracoes_chave_versao_key" in r.stderr


def test_a_versao_seguinte_entra_e_a_anterior_fica(com_uma_versao):
    assert _inserir(com_uma_versao, "orientacao_nsp", 1, "Fale com o NSP").returncode == 0
    assert _inserir(com_uma_versao, "orientacao_nsp", 2, "Ramal 2100 do NSP").returncode == 0

    assert com_uma_versao.ok("SELECT count(*) FROM conduta_configuracoes WHERE chave = 'orientacao_nsp';") == "2"


def test_o_banco_recusa_o_item_de_email_do_dp(banco):
    r = _inserir(banco, "email_dp", 1, "dp@hsm.test")

    assert r.returncode != 0
    assert "conduta_configuracoes_chave_check" in r.stderr


def test_o_banco_aceita_cada_item_da_tela_e_so_eles(banco):
    """A lista do CHECK e a da tela andam juntas: item da tela que o banco
    recusasse daria 500 ao salvar."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from app.services.conduta.configuracoes import ITENS

    definicao = banco.ok(
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = 'conduta_configuracoes_chave_check';"
    )

    assert sorted(re.findall(r"'(\w+)'::text", definicao)) == sorted(item.chave for item in ITENS)


def test_a_migration_nao_grava_nenhum_texto(banco):
    """Quem escreve é a coordenação, pela tela."""
    assert "INSERT INTO conduta_configuracoes" not in MIGRATION.read_text(encoding="utf-8")


def test_o_recibo_e_o_180(banco):
    assert banco.ok("SELECT max(numero) FROM migracoes_aplicadas;") == "186"
