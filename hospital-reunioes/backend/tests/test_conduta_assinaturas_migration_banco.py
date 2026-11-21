"""A migration 192 das assinaturas do Canal de Conduta num Postgres de verdade (issue #1823).

Sobe um Postgres descartável (o mesmo apoio da migration 169), monta o mínimo
das tabelas de antes, aplica a migration duas vezes e prova no banco:

- a tabela única das assinaturas tem RLS ligada e nenhuma policy;
- o webhook acha o envio pela chave do documento, que não se repete;
- o Termo de Confidencialidade e Posse exige a Participação;
- tipo e situação fora da lista são recusados.

Sem `initdb` na máquina o teste pula; no CI ele falha, para não ficar verde
sobre nada.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from test_pendencia_historico_banco import _bin_do_postgres, _Postgres

MIGRATION = Path(__file__).resolve().parents[2] / "supabase" / "migrations" / "192_conduta_assinaturas.sql"

# O mínimo de antes da 192 (migrations 001, 146, 150 e 175).
ESQUEMA_ANTERIOR = """
CREATE ROLE anon NOLOGIN;
CREATE ROLE authenticated NOLOGIN;
CREATE ROLE service_role NOLOGIN NOSUPERUSER BYPASSRLS;

CREATE TABLE migracoes_aplicadas (numero INT PRIMARY KEY);
CREATE TABLE participantes (id VARCHAR(10) PRIMARY KEY, nome_completo TEXT);
CREATE TABLE colegiados (id UUID PRIMARY KEY DEFAULT gen_random_uuid(), slug TEXT NOT NULL UNIQUE);
CREATE TABLE participacoes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  colegiado_id UUID NOT NULL REFERENCES colegiados(id),
  participante_id VARCHAR(10) NOT NULL REFERENCES participantes(id)
);
CREATE TABLE conduta_casos (id UUID PRIMARY KEY DEFAULT gen_random_uuid());

INSERT INTO participantes (id, nome_completo) VALUES ('P1', 'Pessoa de Teste');
INSERT INTO colegiados (slug) VALUES ('conduta');
INSERT INTO participacoes (id, colegiado_id, participante_id)
  SELECT '00000000-0000-0000-0000-000000000001', id, 'P1' FROM colegiados;

GRANT ALL ON ALL TABLES IN SCHEMA public TO service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO service_role;
"""

PARTICIPACAO = "'00000000-0000-0000-0000-000000000001'"


@pytest.fixture(scope="module")
def banco():
    bindir = _bin_do_postgres()
    if bindir is None:
        if os.environ.get("CI"):
            pytest.fail("O CI precisa do initdb para provar as assinaturas no banco.")
        pytest.skip("Sem initdb nesta máquina.")
    pg = _Postgres(bindir)
    pg.porta = "54192"
    pg.subir()
    try:
        pg.ok(ESQUEMA_ANTERIOR)
        migration = MIGRATION.read_text(encoding="utf-8")
        pg.ok(migration)
        pg.ok(migration)  # rodar duas vezes é inofensivo
        yield pg
    finally:
        pg.descer()


def _assinatura(banco, *, tipo="termo_de_posse", participacao=PARTICIPACAO, chave="NULL", situacao="'gerado'"):
    return banco.sql(
        "INSERT INTO conduta_assinaturas (tipo, participacao_id, signatarios, documento_key, situacao) "
        f"VALUES ('{tipo}', {participacao}, ARRAY['P1'], {chave}, {situacao});",
        papel="service_role",
    )


def test_a_tabela_tem_rls_ligada_e_nenhuma_policy(banco):
    assert banco.ok("SELECT relrowsecurity FROM pg_class WHERE relname = 'conduta_assinaturas';") == "t"
    assert banco.ok("SELECT count(*) FROM pg_policies WHERE tablename = 'conduta_assinaturas';") == "0"


def test_o_termo_de_posse_guarda_signatarios_e_nasce_gerado(banco):
    r = _assinatura(banco, chave="'doc-1'")
    assert r.returncode == 0, r.stderr
    assert (
        banco.ok("SELECT situacao, signatarios FROM conduta_assinaturas WHERE documento_key = 'doc-1';").replace(
            " ", ""
        )
        == "gerado|{P1}"
    )


def test_a_chave_do_documento_nao_se_repete(banco):
    assert _assinatura(banco, chave="'doc-2'").returncode == 0
    assert _assinatura(banco, chave="'doc-2'").returncode != 0


def test_o_termo_de_posse_exige_a_participacao(banco):
    assert _assinatura(banco, participacao="NULL").returncode != 0


def test_os_outros_documentos_da_secao_8_cabem_na_mesma_tabela(banco):
    for tipo in ("termo_do_apurador", "relatorio_de_apuracao", "ata_de_deliberacao", "certidao_de_recusa"):
        r = _assinatura(banco, tipo=tipo, participacao="NULL")
        assert r.returncode == 0, (tipo, r.stderr)


def test_tipo_e_situacao_fora_da_lista_sao_recusados(banco):
    assert _assinatura(banco, tipo="contrato").returncode != 0
    assert _assinatura(banco, situacao="'perdido'").returncode != 0


def test_o_recibo_e_o_192(banco):
    assert banco.ok("SELECT max(numero) FROM migracoes_aplicadas;") == "192"
