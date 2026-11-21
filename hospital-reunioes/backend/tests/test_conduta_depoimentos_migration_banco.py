"""A migration 193 do Canal de Conduta num Postgres de verdade (issue #1830).

Sobe um Postgres descartável, aplica a 175 e a 193 (a 193 duas vezes) sobre o
mínimo de antes e prova no banco:

- a etapa Apuração não avança com depoimento em aberto;
- uma versão nova do arquivo não apaga a anterior: o arquivo guardado não se
  altera nem se apaga, nem pela `service_role`;
- a declaração da lista de conferência guarda quem marcou e quando, e não se
  altera nem se apaga;
- o depoimento concluído não muda mais e não recebe arquivo nem declaração;
- o bucket cabe o áudio de 300 MB já cifrado;
- toda tabela nova tem RLS ligada e nenhuma policy.

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

MIGRATION = Path(__file__).resolve().parents[2] / "supabase" / "migrations" / "193_conduta_depoimentos.sql"

TABELAS_NOVAS = ("conduta_depoimentos", "conduta_depoimento_arquivos", "conduta_depoimento_conferencia")
# 300 MB de áudio, mais o nonce e a etiqueta da cifra (28 bytes).
AUDIO_CIFRADO_NO_TETO = 300 * 1024 * 1024 + 28


@pytest.fixture(scope="module")
def banco():
    bindir = _bin_do_postgres()
    if bindir is None:
        if os.environ.get("CI"):
            pytest.fail("O CI precisa do initdb para provar as travas do depoimento no banco.")
        pytest.skip("Sem initdb nesta máquina.")
    pg = _Postgres(bindir)
    pg.porta = "54193"
    pg.subir()
    try:
        pg.ok(ESQUEMA_ANTERIOR)
        pg.ok(MIGRATION_175.read_text(encoding="utf-8"))
        migration = MIGRATION.read_text(encoding="utf-8")
        pg.ok(migration)
        pg.ok(migration)  # rodar duas vezes é inofensivo
        yield pg
    finally:
        pg.descer()


def _caso(banco, etapa: str = "apuracao") -> str:
    protocolo = f"CC-{os.urandom(2).hex().upper()}-{os.urandom(2).hex().upper()}"
    return banco.ok(
        "INSERT INTO conduta_casos (protocolo, codigo_hash, relato_cifrado, etapa) "
        f"VALUES ('{protocolo}', 'hash', 'v1:AAAA', '{etapa}') RETURNING id;",
        papel="service_role",
    ).splitlines()[-1]


def _depoimento(banco, caso: str) -> str:
    return banco.ok(
        "INSERT INTO conduta_depoimentos (caso_id, nome_cifrado, cargo_cifrado, papel, criado_por) "
        f"VALUES ('{caso}', 'v1:NOME', 'v1:CARGO', 'testemunha', 'P1') RETURNING id;",
        papel="service_role",
    ).splitlines()[-1]


def _arquivo(banco, depoimento: str, versao: int = 1):
    return banco.sql(
        "INSERT INTO conduta_depoimento_arquivos "
        "(depoimento_id, tipo, versao, pagina, storage_path, content_type, tamanho_bytes, enviado_por) "
        f"VALUES ('{depoimento}', 'termo_assinado', {versao}, 1, 'depoimentos/{os.urandom(8).hex()}', "
        "'image/jpeg', 100, 'P1');",
        papel="service_role",
    )


def _marcar(banco, depoimento: str, item: str = "arquivos_corretos"):
    return banco.sql(
        "INSERT INTO conduta_depoimento_conferencia (depoimento_id, item, marcado_por) "
        f"VALUES ('{depoimento}', '{item}', 'P1');",
        papel="service_role",
    )


def _concluir(banco, depoimento: str):
    return banco.sql(
        f"UPDATE conduta_depoimentos SET concluido_em = now(), concluido_por = 'P1' WHERE id = '{depoimento}';",
        papel="service_role",
    )


def _avancar(banco, caso: str):
    return banco.sql(f"UPDATE conduta_casos SET etapa = 'voto' WHERE id = '{caso}';", papel="service_role")


def test_a_migration_cria_as_tres_tabelas():
    sql = re.sub(r"--[^\n]*", "", MIGRATION.read_text(encoding="utf-8"))
    assert sorted(re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)\s*\(", sql)) == sorted(TABELAS_NOVAS)


@pytest.mark.parametrize("tabela", TABELAS_NOVAS)
def test_toda_tabela_nova_tem_rls_ligada(banco, tabela):
    assert banco.ok(f"SELECT relrowsecurity FROM pg_class WHERE relname = '{tabela}';") == "t"


def test_nenhuma_policy_nas_tabelas_do_modulo(banco):
    assert banco.ok("SELECT count(*) FROM pg_policies WHERE tablename LIKE 'conduta_%';") == "0"


# ── A etapa Apuração não avança com depoimento em aberto ────────────────────


def test_a_apuracao_nao_avanca_com_depoimento_em_aberto(banco):
    caso = _caso(banco)
    _depoimento(banco, caso)

    r = _avancar(banco, caso)

    assert r.returncode != 0
    assert "depoimentos concluídos" in r.stderr
    assert banco.ok(f"SELECT etapa FROM conduta_casos WHERE id = '{caso}';") == "apuracao"


def test_com_todos_concluidos_a_apuracao_avanca(banco):
    caso = _caso(banco)
    depoimento = _depoimento(banco, caso)
    assert _concluir(banco, depoimento).returncode == 0

    assert _avancar(banco, caso).returncode == 0


def test_o_resto_do_caso_muda_com_depoimento_em_aberto(banco):
    caso = _caso(banco)
    _depoimento(banco, caso)

    r = banco.sql(f"UPDATE conduta_casos SET categoria = 'B' WHERE id = '{caso}';", papel="service_role")

    assert r.returncode == 0


def test_a_contestacao_da_triagem_sai_da_apuracao_com_depoimento_em_aberto(banco):
    """O rito Rápido e o Completo entram na Apuração antes da conferência, e o
    segundo leitor ainda contesta dali. Contestar não é avançar a Apuração."""
    caso = _caso(banco)
    _depoimento(banco, caso)

    r = banco.sql(f"UPDATE conduta_casos SET etapa = 'contestada' WHERE id = '{caso}';", papel="service_role")

    assert r.returncode == 0, r.stderr
    assert banco.ok(f"SELECT etapa FROM conduta_casos WHERE id = '{caso}';") == "contestada"


# ── O arquivo guardado e as versões ─────────────────────────────────────────


@pytest.mark.parametrize("papel", ["service_role", None])
def test_o_arquivo_guardado_nao_se_altera_nem_se_apaga(banco, papel):
    depoimento = _depoimento(banco, _caso(banco))
    assert _arquivo(banco, depoimento).returncode == 0

    troca = banco.sql(
        f"UPDATE conduta_depoimento_arquivos SET storage_path = 'outro' WHERE depoimento_id = '{depoimento}';",
        papel=papel,
    )
    apaga = banco.sql(f"DELETE FROM conduta_depoimento_arquivos WHERE depoimento_id = '{depoimento}';", papel=papel)

    assert troca.returncode != 0 and apaga.returncode != 0
    assert banco.ok(f"SELECT count(*) FROM conduta_depoimento_arquivos WHERE depoimento_id = '{depoimento}';") == "1"


def test_a_versao_nova_fica_ao_lado_da_anterior_e_a_mesma_versao_nao_repete(banco):
    depoimento = _depoimento(banco, _caso(banco))
    assert _arquivo(banco, depoimento, 1).returncode == 0
    assert _arquivo(banco, depoimento, 2).returncode == 0

    assert _arquivo(banco, depoimento, 2).returncode != 0
    assert banco.ok(f"SELECT count(*) FROM conduta_depoimento_arquivos WHERE depoimento_id = '{depoimento}';") == "2"


def test_os_arquivos_nao_se_truncam(banco):
    assert banco.sql("TRUNCATE conduta_depoimento_arquivos;").returncode != 0


# ── A declaração da lista ───────────────────────────────────────────────────


def test_a_declaracao_guarda_quem_e_quando_e_nao_se_altera(banco):
    depoimento = _depoimento(banco, _caso(banco))
    assert _marcar(banco, depoimento).returncode == 0
    assert (
        banco.ok(
            "SELECT marcado_por, marcado_em IS NOT NULL FROM conduta_depoimento_conferencia "
            f"WHERE depoimento_id = '{depoimento}';"
        )
        == "P1|t"
    )

    troca = banco.sql(
        f"UPDATE conduta_depoimento_conferencia SET marcado_por = 'P1' WHERE depoimento_id = '{depoimento}';",
        papel="service_role",
    )
    apaga = banco.sql(
        f"DELETE FROM conduta_depoimento_conferencia WHERE depoimento_id = '{depoimento}';", papel="service_role"
    )

    assert troca.returncode != 0 and apaga.returncode != 0
    assert _marcar(banco, depoimento).returncode != 0


def test_item_automatico_nao_entra_como_declaracao(banco):
    depoimento = _depoimento(banco, _caso(banco))

    assert _marcar(banco, depoimento, "audio").returncode != 0


# ── O depoimento concluído ──────────────────────────────────────────────────


def test_o_depoimento_concluido_nao_muda_nem_recebe_mais_nada(banco):
    depoimento = _depoimento(banco, _caso(banco))
    assert _concluir(banco, depoimento).returncode == 0

    reabre = banco.sql(
        f"UPDATE conduta_depoimentos SET concluido_em = NULL, concluido_por = NULL WHERE id = '{depoimento}';",
        papel="service_role",
    )

    assert reabre.returncode != 0
    assert _arquivo(banco, depoimento).returncode != 0
    assert _marcar(banco, depoimento).returncode != 0


def test_o_depoimento_nao_se_apaga(banco):
    depoimento = _depoimento(banco, _caso(banco))

    r = banco.sql(f"DELETE FROM conduta_depoimentos WHERE id = '{depoimento}';", papel="service_role")

    assert r.returncode != 0


def test_sem_gravacao_exige_motivo_e_pontos_cifrados(banco):
    depoimento = _depoimento(banco, _caso(banco))

    em_claro = banco.sql(
        "UPDATE conduta_depoimentos SET sem_gravacao_em = now(), sem_gravacao_por = 'P1', "
        f"sem_gravacao_motivo_cifrado = 'recusou', pontos_cifrados = 'v1:PONTOS' WHERE id = '{depoimento}';",
        papel="service_role",
    )
    cifrado = banco.sql(
        "UPDATE conduta_depoimentos SET sem_gravacao_em = now(), sem_gravacao_por = 'P1', "
        f"sem_gravacao_motivo_cifrado = 'v1:MOTIVO', pontos_cifrados = 'v1:PONTOS' WHERE id = '{depoimento}';",
        papel="service_role",
    )

    assert em_claro.returncode != 0
    assert cifrado.returncode == 0


def test_nome_e_cargo_so_entram_cifrados(banco):
    caso = _caso(banco)

    r = banco.sql(
        "INSERT INTO conduta_depoimentos (caso_id, nome_cifrado, cargo_cifrado, papel, criado_por) "
        f"VALUES ('{caso}', 'Fulano de Tal', 'v1:CARGO', 'acusado', 'P1');",
        papel="service_role",
    )

    assert r.returncode != 0


# ── O bucket e o recibo ─────────────────────────────────────────────────────


def test_o_bucket_cabe_o_audio_de_300_mb_cifrado(banco):
    limite = int(banco.ok("SELECT file_size_limit FROM storage.buckets WHERE id = 'conduta-arquivos';"))

    assert limite >= AUDIO_CIFRADO_NO_TETO


def test_nenhum_dado_de_pessoa_entra_pela_migration():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert re.search(r"INSERT INTO (participacoes|participantes)", sql, re.IGNORECASE) is None


def test_o_recibo_e_o_193(banco):
    assert banco.ok("SELECT max(numero) FROM migracoes_aplicadas;") == "193"
